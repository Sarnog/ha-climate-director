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

from .capacity import apply_capacity, apply_short_cycle
from .circuit_policy import active_family, any_managed_running, choose_family, forced_families
from .circuit_requests import Grant, Outcome, Request
from .families import ACTIVE_FAMILIES, ModeFamily
from .models import Circuit, DirectorConfig
from .plan import CircuitDecision, Deferral, Reason
from .world import WorldState


def resolve(
    config: DirectorConfig,
    world: WorldState,
    circuit: Circuit,
    requests: tuple[Request, ...],
    standing: frozenset[str] = frozenset(),
) -> Outcome:
    """Resolve every request on one circuit into grants the hardware can honour.

    `standing` noemt de draaiende units die de director deze ronde met opzet
    niets stuurt - ook geen uit. Ze staan er dus nog als het plan geland is, en
    dat maakt ze voor dit circuit even dwingend als een unit die helemaal buiten
    de installatie valt.

    `standing` names the running units the director deliberately sends nothing
    this round - an off included. They are therefore still there once the plan
    has landed, which makes them as binding for this circuit as a unit outside
    the installation altogether.
    """
    ordered = tuple(sorted(requests, key=lambda request: request.rank))
    current = active_family(world, circuit)
    forced = forced_families(config, world, circuit, standing)

    if circuit.simultaneous_heat_cool:
        # Nothing to arbitrate: every unit has its own compressor duty. The
        # reported circuit family is the preferred zone's, purely as a label.
        granted = [
            Grant(request.zone.zone_id, request.source.source_id, request.family, Reason.REGULATING)
            for request in ordered
        ]
        label = ordered[0].family if ordered else ModeFamily.NEUTRAL
        return _finish(config, world, circuit, ordered, granted, label, None, (), standing=standing)

    chosen, reason = choose_family(world, circuit, ordered, current, forced)
    deferrals: list[Deferral] = []

    # A duty may not be swapped out before it has had its minimum run. Missing
    # timing metadata lets the swap through: freezing the installation over an
    # unknown timestamp is worse than swapping a little early.
    #
    # Staat de taak vast door een apparaat dat de director niet kan
    # wegschakelen, dan valt er niets te wisselen en heeft de timer niets te
    # beschermen. Hem dan toch laten winnen zette de eigen units in de
    # tegengestelde taak van wat er werkelijk op de buitenunit draait.
    #
    # When the duty is fixed by an appliance the director cannot stand down
    # there is no swap to make and nothing for the timer to protect. Letting it
    # win anyway put the director's own units in the duty opposing the one
    # really running on the outdoor unit.
    since = world.circuit_family_since.get(circuit.circuit_id)
    if (
        not forced
        and chosen is not current
        and current in ACTIVE_FAMILIES
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
        not forced
        and chosen is not current
        and current in ACTIVE_FAMILIES
        and bool(circuit.family_switch_delay)
        and any_managed_running(config, world, circuit, current)
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
        standing=standing,
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
    *,
    standing: frozenset[str] = frozenset(),
) -> Outcome:
    """Apply the capacity and short-cycle limits, then assemble the outcome."""
    granted = apply_capacity(config, world, circuit, requests, granted, standing)
    granted, cycle_deferrals = apply_short_cycle(world, circuit, requests, granted)

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
