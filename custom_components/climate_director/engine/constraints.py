"""Circuitbeperkingen: wat mag er tegelijk draaien op één buitenunit.

Circuit constraints: what may run at the same time on one outdoor unit.

De regel die alles hier stuurt:

    Zij **F** de actieve taak van een circuit, met HEAT = {`heat`} en
    COOL = {`cool`, `dry`}. Elke binnenunit op dat circuit staat in
    **F ∪ {`off`, `fan_only`}**.

Circuits met `simultaneous_heat_cool` kennen die beperking niet: een splitunit
heeft zijn eigen buitenunit, en driepijps-VRF met warmteterugwinning kan
werkelijk tegelijk verwarmen en koelen.

The rule that drives everything here:

    Let **F** be a circuit's active duty, with HEAT = {`heat`} and
    COOL = {`cool`, `dry`}. Every indoor unit on that circuit sits in
    **F ∪ {`off`, `fan_only`}**.

Circuits with `simultaneous_heat_cool` do not carry that constraint: a single
split has its own outdoor unit, and three-pipe VRF with heat recovery really
does heat and cool at once.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .families import ModeFamily
from .models import Circuit, ConflictPolicy, DirectorConfig, Season, Source, Zone
from .plan import CircuitDecision, Deferral, Reason
from .world import WorldState


@dataclass(frozen=True, slots=True)
class Request:
    """One zone asking a circuit for a duty."""

    zone: Zone
    source: Source
    family: ModeFamily
    deviation: float = 0.0

    @property
    def rank(self) -> tuple[int, str]:
        """Return the tie-break key: priority first, then zone id."""
        return (self.zone.priority, self.zone.zone_id)


@dataclass(frozen=True, slots=True)
class Grant:
    """What a zone actually got."""

    zone_id: str
    source_id: str
    family: ModeFamily
    reason: Reason

    @property
    def granted(self) -> bool:
        """Return whether the zone may run its duty."""
        return self.family is not ModeFamily.NEUTRAL


@dataclass(frozen=True, slots=True)
class Outcome:
    """The full result of resolving one circuit."""

    decision: CircuitDecision
    grants: tuple[Grant, ...] = ()
    deferrals: tuple[Deferral, ...] = field(default_factory=tuple)


def resolve(
    config: DirectorConfig,
    world: WorldState,
    circuit: Circuit,
    requests: tuple[Request, ...],
) -> Outcome:
    """Resolve every request on one circuit into grants the hardware can honour."""
    ordered = tuple(sorted(requests, key=lambda request: request.rank))
    current = active_family(world, circuit)
    locked = _unmanaged_family(config, world, circuit)

    if circuit.simultaneous_heat_cool:
        # Nothing to arbitrate: every unit has its own compressor duty. The
        # reported circuit family is the preferred zone's, purely as a label.
        granted = [
            Grant(request.zone.zone_id, request.source.source_id, request.family, Reason.REGULATING)
            for request in ordered
        ]
        label = ordered[0].family if ordered else ModeFamily.NEUTRAL
        return _finish(config, world, circuit, ordered, granted, label, None, ())

    chosen, reason = _choose_family(world, circuit, ordered, current, locked)
    deferrals: list[Deferral] = []

    # A duty may not be swapped out before it has had its minimum run. Missing
    # timing metadata lets the swap through: freezing the installation over an
    # unknown timestamp is worse than swapping a little early.
    since = world.circuit_family_since.get(circuit.circuit_id)
    if (
        chosen is not current
        and current is not ModeFamily.NEUTRAL
        and circuit.min_family_switch_interval
        and since is not None
        and world.now - since < circuit.min_family_switch_interval
    ):
        deferrals.append(
            Deferral(
                circuit.circuit_id,
                since + circuit.min_family_switch_interval,
                Reason.CIRCUIT_SWITCH_TOO_SOON,
            )
        )
        chosen, reason = current, Reason.CIRCUIT_SWITCH_TOO_SOON

    # Swapping duty means stopping the old one first. With a configured pause,
    # this cycle only stops; the new duty starts on the follow-up evaluation.
    pending = (
        chosen is not current
        and current is not ModeFamily.NEUTRAL
        and bool(circuit.family_switch_delay)
        and _any_managed_running(config, world, circuit, current)
    )
    if pending:
        deferrals.append(
            Deferral(
                circuit.circuit_id,
                world.now + circuit.family_switch_delay,
                Reason.CIRCUIT_SWITCH_PENDING,
            )
        )

    granted = []
    for request in ordered:
        if pending:
            granted.append(
                Grant(
                    request.zone.zone_id,
                    request.source.source_id,
                    ModeFamily.NEUTRAL,
                    Reason.CIRCUIT_SWITCH_PENDING,
                )
            )
        elif request.family is chosen:
            granted.append(
                Grant(
                    request.zone.zone_id,
                    request.source.source_id,
                    request.family,
                    Reason.REGULATING,
                )
            )
        else:
            granted.append(
                Grant(
                    request.zone.zone_id,
                    request.source.source_id,
                    ModeFamily.NEUTRAL,
                    Reason.CIRCUIT_CONFLICT_LOST,
                )
            )

    winner = next((grant.zone_id for grant in granted if grant.granted), None)
    return _finish(
        config,
        world,
        circuit,
        ordered,
        granted,
        ModeFamily.NEUTRAL if pending else chosen,
        winner,
        tuple(deferrals),
        reason,
    )


def active_family(world: WorldState, circuit: Circuit) -> ModeFamily:
    """Return the duty a circuit is running right now.

    Reads every entity on the circuit, including indoor units the director does
    not manage: an unmanaged unit still claims the compressor. Modes that leave
    the duty to the unit itself (`heat_cool`, `auto`) carry no readable duty and
    are skipped. On the contradictory reading of two units in opposing duties,
    the first in configured order wins, so the answer stays deterministic.
    """
    for entity_id in circuit.units:
        family = world.climate(entity_id).family
        if family in (ModeFamily.HEAT, ModeFamily.COOL):
            return family
    return ModeFamily.NEUTRAL


def _unmanaged_family(config: DirectorConfig, world: WorldState, circuit: Circuit) -> ModeFamily:
    """Return the duty forced on a circuit by units the director cannot steer."""
    managed = {source.entity_id for _, source in config.sources_on(circuit)}
    for entity_id in circuit.units:
        if entity_id in managed:
            continue
        family = world.climate(entity_id).family
        if family in (ModeFamily.HEAT, ModeFamily.COOL):
            return family
    return ModeFamily.NEUTRAL


def _choose_family(
    world: WorldState,
    circuit: Circuit,
    requests: tuple[Request, ...],
    current: ModeFamily,
    locked: ModeFamily,
) -> tuple[ModeFamily, Reason]:
    """Return the duty the circuit should run, and why."""
    if not requests:
        return ModeFamily.NEUTRAL, Reason.SATISFIED

    wanted = {request.family for request in requests}

    # A unit outside the director's control has already claimed the compressor;
    # nothing here can overrule that.
    if locked is not ModeFamily.NEUTRAL:
        settled = wanted == {locked}
        return locked, Reason.REGULATING if settled else Reason.CIRCUIT_CONFLICT_LOST

    if len(wanted) == 1:
        return next(iter(wanted)), Reason.REGULATING

    if circuit.conflict_policy is ConflictPolicy.FIRST_COME and current in wanted:
        return current, Reason.CIRCUIT_CONFLICT_LOST

    if circuit.conflict_policy is ConflictPolicy.DEMAND:
        winner = max(requests, key=lambda request: (request.deviation, -request.zone.priority))
        return winner.family, Reason.CIRCUIT_CONFLICT_LOST

    if circuit.conflict_policy is ConflictPolicy.SEASON_LOCK:
        preferred = {
            Season.SUMMER: ModeFamily.COOL,
            Season.WINTER: ModeFamily.HEAT,
        }.get(world.season)
        if preferred in wanted:
            return preferred, Reason.CIRCUIT_CONFLICT_LOST

    # Priority, and the fallback for every policy that could not decide.
    return requests[0].family, Reason.CIRCUIT_CONFLICT_LOST


def _any_managed_running(
    config: DirectorConfig, world: WorldState, circuit: Circuit, family: ModeFamily
) -> bool:
    """Return whether the director still has a unit running `family` here."""
    return any(
        world.climate(source.entity_id).family is family for _, source in config.sources_on(circuit)
    )


def _finish(
    config: DirectorConfig,
    world: WorldState,
    circuit: Circuit,
    requests: tuple[Request, ...],
    granted: list[Grant],
    family: ModeFamily,
    winner: str | None,
    deferrals: tuple[Deferral, ...],
    reason: Reason = Reason.REGULATING,
) -> Outcome:
    """Apply the capacity and short-cycle limits, then assemble the outcome."""
    granted = _apply_capacity(config, world, circuit, requests, granted)
    granted, cycle_deferrals = _apply_short_cycle(world, circuit, requests, granted)

    displaced = tuple(grant.zone_id for grant in granted if not grant.granted)
    if winner is None:
        winner = next((grant.zone_id for grant in granted if grant.granted), None)
    if not any(grant.granted for grant in granted):
        family = ModeFamily.NEUTRAL

    decision = CircuitDecision(
        circuit_id=circuit.circuit_id,
        family=family,
        winner_zone_id=winner,
        displaced_zone_ids=displaced,
        reason=reason,
    )
    return Outcome(decision, tuple(granted), deferrals + cycle_deferrals)


def _apply_capacity(
    config: DirectorConfig,
    world: WorldState,
    circuit: Circuit,
    requests: tuple[Request, ...],
    granted: list[Grant],
) -> list[Grant]:
    """Trim the winners down to the outdoor unit's capacity."""
    cap = circuit.max_concurrent_units
    if cap is None:
        return granted

    # Units the director cannot steer still occupy capacity.
    managed = {source.entity_id for _, source in config.sources_on(circuit)}
    used = sum(
        1
        for entity_id in circuit.units
        if entity_id not in managed and world.climate(entity_id).running
    )

    rank = {request.zone.zone_id: request.rank for request in requests}
    winners = sorted(
        (grant for grant in granted if grant.granted),
        key=lambda grant: rank.get(grant.zone_id, (0, grant.zone_id)),
    )

    denied: set[str] = set()
    for position, grant in enumerate(winners):
        if used + position >= cap:
            denied.add(grant.zone_id)

    return [
        Grant(grant.zone_id, grant.source_id, ModeFamily.NEUTRAL, Reason.CIRCUIT_AT_CAPACITY)
        if grant.zone_id in denied
        else grant
        for grant in granted
    ]


def _apply_short_cycle(
    world: WorldState,
    circuit: Circuit,
    requests: tuple[Request, ...],
    granted: list[Grant],
) -> tuple[list[Grant], tuple[Deferral, ...]]:
    """Hold back starts from units that stopped too recently.

    Only starts are delayed, never stops: short-cycle protection that could
    keep a unit running would turn a comfort feature into a safety problem.
    """
    if not circuit.min_cycle_time:
        return granted, ()

    entities = {request.zone.zone_id: request.source.entity_id for request in requests}
    deferrals: list[Deferral] = []
    result: list[Grant] = []

    for grant in granted:
        entity_id = entities.get(grant.zone_id)
        state = world.climate(entity_id) if entity_id else None
        too_soon = (
            grant.granted
            and state is not None
            and not state.running
            and state.changed_at is not None
            and world.now - state.changed_at < circuit.min_cycle_time
        )
        if too_soon and state is not None and state.changed_at is not None:
            deferrals.append(
                Deferral(
                    entity_id or circuit.circuit_id,
                    state.changed_at + circuit.min_cycle_time,
                    Reason.SHORT_CYCLE_PROTECTION,
                )
            )
            result.append(
                Grant(
                    grant.zone_id,
                    grant.source_id,
                    ModeFamily.NEUTRAL,
                    Reason.SHORT_CYCLE_PROTECTION,
                )
            )
        else:
            result.append(grant)

    return result, tuple(deferrals)
