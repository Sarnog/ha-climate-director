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

from .families import ACTIVE_FAMILIES, ModeFamily
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

    priority: int = 0
    """The priority in force, which may be a live value rather than the configured one."""

    @property
    def rank(self) -> tuple[int, str]:
        """Return the tie-break key: priority first, then zone id."""
        return (self.priority, self.zone.zone_id)


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
    forced = _forced_families(config, world, circuit, standing)

    if circuit.simultaneous_heat_cool:
        # Nothing to arbitrate: every unit has its own compressor duty. The
        # reported circuit family is the preferred zone's, purely as a label.
        granted = [
            Grant(request.zone.zone_id, request.source.source_id, request.family, Reason.REGULATING)
            for request in ordered
        ]
        label = ordered[0].family if ordered else ModeFamily.NEUTRAL
        return _finish(config, world, circuit, ordered, granted, label, None, (), standing=standing)

    chosen, reason = _choose_family(world, circuit, ordered, current, forced)
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
        not forced
        and chosen is not current
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
        standing=standing,
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
        if family in ACTIVE_FAMILIES:
            return family
    return ModeFamily.NEUTRAL


def _forced_families(
    config: DirectorConfig,
    world: WorldState,
    circuit: Circuit,
    standing: frozenset[str] = frozenset(),
) -> frozenset[ModeFamily]:
    """Return the duties forced on a circuit by units the director cannot steer.

    Twee soorten dwingen: een unit die in geen enkele zone staat, en een unit
    die deze ronde met opzet niets krijgt en gewoon doordraait. Die tweede werd
    hier niet meegeteld, en daardoor kon de director de tegengestelde taak op
    dezelfde buitenunit zetten terwijl er nog een unit in de eerste taak stond
    te draaien - precies de toestand die hier onbereikbaar hoort te zijn.

    Alle taken worden teruggegeven en niet alleen de eerste. Een mens kan met
    een afstandsbediening en een override twee taken tegelijk op een circuit
    zetten; wie dan alleen naar de eerste keek, zag de tweede over het hoofd en
    kon er een derde unit bij aanzetten.

    Two kinds compel: a unit sitting in no zone at all, and a unit that
    deliberately gets nothing this round and simply keeps running. That second
    one was left out here, which let the director put the opposing duty on the
    same outdoor unit while a unit still ran the first - exactly the state this
    is meant to make unreachable.

    Every duty is returned rather than only the first. A person can put two
    duties on one circuit at once with a remote and an override; looking at the
    first alone missed the second and allowed a third unit to be started beside
    them.
    """
    managed = {source.entity_id for _, source in config.sources_on(circuit)}
    return frozenset(
        family
        for entity_id in circuit.units
        if entity_id not in managed or entity_id in standing
        for family in (world.climate(entity_id).family,)
        if family in ACTIVE_FAMILIES
    )


def _choose_family(
    world: WorldState,
    circuit: Circuit,
    requests: tuple[Request, ...],
    current: ModeFamily,
    forced: frozenset[ModeFamily],
) -> tuple[ModeFamily, Reason]:
    """Return the duty the circuit should run, and why."""
    if not requests:
        return ModeFamily.NEUTRAL, Reason.SATISFIED

    wanted = {request.family for request in requests}

    # Staan er al twee taken te draaien op apparaten waar de director niet aan
    # mag komen, dan is er geen taak die dit circuit veilig kan draaien. Zo'n
    # toestand kan hij niet zelf maken en niet rechtzetten - maar hij hoort er
    # dan zeker geen unit bij te zetten.
    #
    # With two duties already running on appliances the director may not touch,
    # there is no duty this circuit can safely run. It can neither create nor
    # put right such a state - but it certainly should not add a unit to it.
    if len(forced) > 1:
        return ModeFamily.NEUTRAL, Reason.CIRCUIT_CONFLICT_LOST

    # A unit outside the director's control has already claimed the compressor;
    # nothing here can overrule that.
    if forced:
        locked = next(iter(forced))
        settled = wanted == {locked}
        return locked, Reason.REGULATING if settled else Reason.CIRCUIT_CONFLICT_LOST

    if len(wanted) == 1:
        return next(iter(wanted)), Reason.REGULATING

    if circuit.conflict_policy is ConflictPolicy.FIRST_COME and current in wanted:
        return current, Reason.CIRCUIT_CONFLICT_LOST

    if circuit.conflict_policy is ConflictPolicy.DEMAND:
        winner = max(requests, key=lambda request: (request.deviation, -request.priority))
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
    *,
    standing: frozenset[str] = frozenset(),
) -> Outcome:
    """Apply the capacity and short-cycle limits, then assemble the outcome."""
    granted = _apply_capacity(config, world, circuit, requests, granted, standing)
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


def _standing_claims(
    config: DirectorConfig,
    world: WorldState,
    circuit: Circuit,
    requests: tuple[Request, ...],
    standing: frozenset[str] = frozenset(),
) -> int:
    """Return how many units keep the compressor whatever this round grants.

    Een grens in stuks gaat over wat de buitenunit aankan, en die telt geen
    configuratie maar draaiende binnenunits. Wie er niet om vraagt en toch
    doordraait, bezet dus net zo goed een plek.

    Drie soorten doen dat: een unit die in geen enkele zone staat, een unit in
    een overgedragen zone - daar stuurt de director niets naartoe, ook geen uit
    - en een handbediend apparaat dat hetzelfde doet als wat er nu gevraagd
    wordt, want dat wordt niet weggeschakeld.

    Tot 6.6.0 telde alleen de eerste soort mee. Daardoor beschermde de grens
    een huis mínder zodra je je slaapkamerairco netjes als handbediende bron
    configureerde dan wanneer je hem helemaal wegliet - precies andersom dan
    het hoort.

    A limit in units is about what the outdoor unit can take, and that counts
    running indoor units rather than configuration. Whatever asks for nothing
    and keeps running occupies a slot just the same.

    Three kinds do that: a unit sitting in no zone at all, a unit in a zone that
    has been handed over - the director sends that nothing, an off included -
    and a hand-operated appliance doing the same duty as the one being asked
    for, since that one is not stood down.

    Up to 6.6.0 only the first kind counted. That made the limit protect a house
    *less* once you tidily configured your bedroom unit as a hand-operated
    source than when you left it out altogether - exactly the wrong way round.
    """
    asking = {request.source.entity_id for request in requests}
    return sum(
        1
        for entity_id in circuit.units
        if entity_id not in asking
        and world.climate(entity_id).running
        and _keeps_claiming(config, world, circuit, entity_id, standing)
    )


def _keeps_claiming(
    config: DirectorConfig,
    world: WorldState,
    circuit: Circuit,
    entity_id: str,
    standing: frozenset[str] = frozenset(),
) -> bool:
    """Return whether this running unit holds its place whatever we grant.

    Drie soorten doen dat, en geen van drieën vraagt deze ronde iets: een unit
    die in geen enkele zone staat, een unit in een overgedragen zone - daar
    stuurt de director niets naartoe, ook geen uit - en een handbediend
    apparaat, dat alleen opzij gaat als het iemand in de weg staat.

    Dat laatste wordt hier niet nagerekend maar aangenomen. Gaat het apparaat
    deze ronde alsnog opzij, dan is er één beoordelingsronde lang een plek te
    weinig, en die ronde volgt binnen een seconde op het commando dat hem
    uitzet. De omgekeerde fout - een plek te veel - zet een buitenunit aan het
    werk waar hij niet op gebouwd is, en dat duurt niet één ronde.

    Three kinds do, and none of the three asks for anything this round: a unit
    sitting in no zone at all, a unit in a zone that has been handed over -
    the director sends that nothing, an off included - and a hand-operated
    appliance, which only steps aside when it is in somebody's way.

    That last one is assumed rather than worked out here. If the appliance does
    step aside this round, there is one evaluation round with a place too few,
    and that round follows within a second of the command switching it off. The
    opposite mistake - a place too many - puts an outdoor unit to work it was
    not built for, and that does not last one round.
    """
    if entity_id in standing:
        return True
    owners = [
        (zone, source)
        for zone, source in config.sources_on(circuit)
        if source.entity_id == entity_id
    ]
    if not owners:
        return True
    if any(world.overridden(zone.zone_id) for zone, _ in owners):
        return True
    return all(not source.autostart for _, source in owners)


def _apply_capacity(
    config: DirectorConfig,
    world: WorldState,
    circuit: Circuit,
    requests: tuple[Request, ...],
    granted: list[Grant],
    standing: frozenset[str] = frozenset(),
) -> list[Grant]:
    """Trim the winners down to the outdoor unit's capacity."""
    cap = circuit.max_concurrent_units
    if cap is None:
        return granted

    used = _standing_claims(config, world, circuit, requests, standing)

    rank = {request.zone.zone_id: request.rank for request in requests}
    winners = sorted(
        (grant for grant in granted if grant.granted),
        key=lambda grant: rank.get(grant.zone_id, (0, grant.zone_id)),
    )

    # De grens telt draaiende apparaten, niet zones: een gedeeld apparaat onder
    # twee zones op één circuit levert één draaiende binnenunit op, niet twee.
    # Tel je per zone, dan krijgt de tweede kamer onterecht
    # `CIRCUIT_AT_CAPACITY` terwijl hetzelfde apparaat toch al draait.
    #
    # The limit counts running appliances, not zones: a shared appliance under
    # two zones on one circuit is one running indoor unit, not two. Counting per
    # zone would wrongly hand the second room `CIRCUIT_AT_CAPACITY` while that
    # very appliance runs anyway.
    entity_by_zone = {request.zone.zone_id: request.source.entity_id for request in requests}

    denied: set[str] = set()
    slots = used
    seen_entities: set[str] = set()
    for grant in winners:
        entity_id = entity_by_zone.get(grant.zone_id)
        if entity_id is not None:
            if entity_id in seen_entities:
                continue
            seen_entities.add(entity_id)
        if slots >= cap:
            denied.add(grant.zone_id)
        else:
            slots += 1

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
