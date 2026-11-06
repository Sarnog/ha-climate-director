"""De toekenning: wie krijgt de taak. / The grant: who gets the task."""

from __future__ import annotations

from . import constraints, sources, takeover
from .candidates import apply_exclusive_groups, group_entities, handed_over, serving
from .command_reasons import idle_mode
from .families import (
    ModeFamily,
    family_of,
    is_compatible,
)
from .models import Circuit, DirectorConfig, Source, Zone
from .plan import (
    CircuitDecision,
    Deferral,
    Plan,
    Reason,
    UnitCommand,
)
from .world import WorldState


def resolve_with_fallbacks(
    config: DirectorConfig,
    world: WorldState,
    wishes: dict[str, constraints.Request],
    standing: frozenset[str],
    blocked: frozenset[str],
    previous: Plan | None,
    takeovers: tuple[takeover.Takeover, ...] = (),
) -> tuple[
    dict[str, constraints.Grant],
    tuple[CircuitDecision, ...],
    tuple[Deferral, ...],
    dict[str, frozenset[str]],
    dict[str, constraints.Request],
    dict[str, constraints.Request],
]:
    """Resolve every circuit, letting a refused zone fall back to its next source.

    Anker 7: een circuitweigering weigert het apparaat op dat circuit, niet de
    zone. Valt een verzoek uit met `SHORT_CYCLE_PROTECTION`,
    `CIRCUIT_AT_CAPACITY` of `CIRCUIT_CONFLICT_LOST`, dan dient de zone haar
    verzoek opnieuw in bij de volgende bron die dezelfde taak kan leveren, net
    zolang tot een bron hem krijgt of er geen kandidaat meer is. De huisbrede
    stop blijft op de zone liggen: die is al in `collect_wishes` afgehandeld;
    hier geldt hij alleen nog als kandidaat-filter. De lus gaat door tot een ronde
    niets meer verschuift; elke verschuiving voegt een bron aan de weigeringen toe, dus hij eindigt.

    Anchor 7: a circuit refusal refuses the appliance on that circuit, not the
    zone. When a request falls through with `SHORT_CYCLE_PROTECTION`,
    `CIRCUIT_AT_CAPACITY` or `CIRCUIT_CONFLICT_LOST`, the zone files its request
    again with the next source able to deliver the same duty, until a source
    gets it or no candidate remains. The house-wide stop stays on the zone: it
    was already handled in `collect_wishes`; here it only filters candidates.
    The loop runs on until nothing moves; every move adds a source to the refusals, so
    it ends.
    """
    grants: dict[str, constraints.Grant] = {}
    circuit_decisions: tuple[CircuitDecision, ...] = ()
    deferrals: tuple[Deferral, ...] = ()
    refused_by_circuit: dict[str, frozenset[str]] = {}
    all_deferrals: list[Deferral] = []
    dropped: dict[str, constraints.Request] = {}

    margin = config.outdoor_hysteresis
    # Een overgedragen apparaat valt ook hier af als kandidaat: de zone schuift
    # niet door naar een apparaat dat de beheerder al heeft (anker 11).
    # A handed-over appliance drops out as a candidate here too: the zone does
    # not slide on to an appliance the administrator already has (anchor 11).
    handed_over_ids = handed_over(config, world)
    while True:
        wishes, dropped_now = apply_exclusive_groups(config, world, wishes)
        dropped.update(dropped_now)
        grants, circuit_decisions, deferrals = resolve_circuits(config, world, wishes, standing)
        all_deferrals += [deferral for deferral in deferrals if deferral not in all_deferrals]
        changed = False
        for zone in config.zones:
            request = wishes.get(zone.zone_id)
            grant = grants.get(zone.zone_id)
            if request is None or grant is None or grant.granted:
                continue
            if grant.reason not in _CIRCUIT_REFUSALS:
                continue
            refused = refused_by_circuit.get(zone.zone_id, frozenset()) | {request.source.entity_id}
            stopped = frozenset() if world.precondition_ignores_openings(zone.zone_id) else blocked
            only, unbounded = takeover.narrowing(takeovers, zone.zone_id, request.family)
            alternative = sources.select(
                zone,
                request.family,
                world,
                serving(previous, zone.zone_id),
                margin,
                stopped,
                excluding=refused | handed_over_ids,
                only=only,
                unbounded=unbounded,
            )
            if alternative is None or alternative.entity_id in refused:
                continue
            wishes[zone.zone_id] = constraints.Request(
                zone=zone,
                source=alternative,
                family=request.family,
                deviation=request.deviation,
                priority=request.priority,
            )
            refused_by_circuit[zone.zone_id] = refused
            changed = True
        if not changed:
            break

    return grants, circuit_decisions, tuple(all_deferrals), refused_by_circuit, dropped, wishes


def resolve_circuits(
    config: DirectorConfig,
    world: WorldState,
    wishes: dict[str, constraints.Request],
    standing: frozenset[str] = frozenset(),
) -> tuple[dict[str, constraints.Grant], tuple[CircuitDecision, ...], tuple[Deferral, ...]]:
    """Run every circuit's constraints and collect the grants they produce."""
    by_circuit: dict[str, list[constraints.Request]] = {}
    solo: list[constraints.Request] = []

    for request in wishes.values():
        circuit = config.circuit_for_entity(request.source.entity_id)
        if circuit is None:
            solo.append(request)
        else:
            by_circuit.setdefault(circuit.circuit_id, []).append(request)

    grants: dict[str, constraints.Grant] = {}
    decisions: list[CircuitDecision] = []
    deferrals: list[Deferral] = []

    # Every configured circuit is resolved, including the ones nobody asked
    # anything of: those whose requests dropped away are still reported as idle.
    for circuit in config.circuits:
        outcome = constraints.resolve(
            config, world, circuit, tuple(by_circuit.get(circuit.circuit_id, ())), standing
        )
        decisions.append(outcome.decision)
        deferrals.extend(outcome.deferrals)
        grants.update((grant.zone_id, grant) for grant in outcome.grants)

    for request in solo:
        rest = request.source.min_cycle_time
        circuit = _SOLO if not rest else Circuit("", "", (), True, min_cycle_time=rest)
        outcome = constraints.resolve(config, world, circuit, (request,), standing)
        deferrals.extend(outcome.deferrals)
        grants.update((grant.zone_id, grant) for grant in outcome.grants)

    return grants, tuple(decisions), tuple(deferrals)


def zone_reasons(
    config: DirectorConfig,
    grants: dict[str, constraints.Grant],
    dropped: dict[str, constraints.Request],
    refusals: dict[str, Reason],
) -> dict[str, Reason]:
    """Return the single reason that explains each zone's outcome.

    Every zone gets one, so a unit being switched off can always say why rather
    than falling back on a generic "nothing to do".
    """
    reasons: dict[str, Reason] = {}
    for zone in config.zones:
        grant = grants.get(zone.zone_id)
        if grant is not None:
            reasons[zone.zone_id] = grant.reason
        elif zone.zone_id in dropped:
            reasons[zone.zone_id] = Reason.EXCLUSIVE_GROUP_LOST
        else:
            reasons[zone.zone_id] = refusals.get(zone.zone_id, Reason.SATISFIED)
    return reasons


def manual_conflict(
    config: DirectorConfig,
    world: WorldState,
    zone: Zone,
    source: Source,
    wishes: dict[str, constraints.Request],
    families: dict[str, ModeFamily],
    grants: dict[str, constraints.Grant],
) -> UnitCommand | None:
    """Return the command standing a manual source down, or `None` to leave it.

    Draait het circuit een taak, dan is dat het antwoord: deze unit doet mee of
    hij gaat opzij. Vragen is namelijk niet krijgen - vragen twee kamers om
    tegengestelde taken, dan wint er één, en wie naar de vraag keek liet deze
    unit doorkoelen omdat een kamer daarom gevraagd had, terwijl die kamer net
    was weggestemd en het circuit stond te verwarmen.

    Krijgt niemand iets toegekend, dan telt de vraag alsnog. Dat scheelt een
    klem: zolang deze unit draait houdt hij het circuit op zijn taak, dus de
    ander krijgt niets toegekend - en zou hij daarop wachten, dan wachtten ze
    allebei tot Sint-Juttemis. Wie in de weg staat gaat opzij, ook als de
    omschakeling nog een pauze te gaan heeft.

    If the circuit runs a duty, that is the answer: this unit joins in or steps
    aside. Asking is not getting - when two rooms ask for opposing duties one
    wins, and whoever looked at the asking let this unit carry on cooling
    because a room had asked for it, while that room had just been outvoted and
    the circuit stood there heating.

    When nobody is granted anything the asking counts after all. That avoids a
    deadlock: while this unit runs it holds the circuit to its duty, so the
    other is granted nothing - and were this to wait on that, both would wait
    forever. Whoever is in the way steps aside, even when the changeover still
    has a pause to sit out.
    """
    running = family_of(world.climate(source.entity_id).hvac_mode)
    if running is ModeFamily.NEUTRAL:
        return None

    # Een exclusieve groep gaat over apparaten die elkaar uitsluiten, niet over
    # taken die botsen: staat er een ander lid op het punt te draaien, dan moet
    # deze uit, ook al doen ze hetzelfde en delen ze geen buitenunit. Zonder dit
    # zou een handbediend apparaat de groep straffeloos negeren, want het doet
    # zelf nooit een aanvraag - en dan is de hele groep een papieren regel.
    #
    # An exclusive group is about appliances ruling each other out, not about
    # duties clashing: if another member is about to run, this one goes off even
    # when they do the same thing and share no outdoor unit. Without this a
    # hand-operated appliance would ignore the group with impunity, since it
    # never files a request of its own - leaving the group a rule on paper.
    if exclusive_rival(config, zone, source, wishes, grants):
        return stand_down(config, world, zone, source, Reason.EXCLUSIVE_GROUP_LOST)

    circuit = config.circuit_for_entity(source.entity_id)
    if circuit is None or circuit.simultaneous_heat_cool:
        return None

    # De toegekende taak van het circuit gaat voor: die is de uitkomst, niet de
    # wens. Is hij neutraal, dan kreeg niemand iets en valt er terug te vallen
    # op wat er gevraagd wordt.
    #
    # The circuit's granted duty comes first: that is the outcome rather than
    # the wish. If it is neutral nobody was granted anything and there is the
    # asking to fall back on.
    running_now = families.get(circuit.circuit_id, ModeFamily.NEUTRAL)
    if running_now is not ModeFamily.NEUTRAL:
        # De kernregel uit `families.is_compatible`: alleen de actieve taak van
        # het circuit - plus `off`/`fan_only` - mag blijven draaien. Dit is de
        # enige plek waar een draaiende handbediende unit tegen de toegekende
        # taak gehouden wordt.
        #
        # The core rule from `families.is_compatible`: only the circuit's active
        # duty - plus `off`/`fan_only` - may keep running. This is the one place
        # where a running hand-operated unit is held against the granted duty.
        if is_compatible(world.climate(source.entity_id).hvac_mode, running_now):
            return None
        return stand_down(config, world, zone, source, Reason.CIRCUIT_CONFLICT_LOST)

    # Alleen verzoeken die dít circuit aanspreken tellen mee. Een kamer die
    # ergens een bron op dit circuit heeft staan maar zijn warmte deze ronde
    # van een ander apparaat krijgt, vraagt hier niets - en mag deze unit dus
    # ook niet laten blijven staan. Wie dat wel meetelde liet een handbediende
    # unit doorkoelen omdat een andere kamer "ook koelen wilde", terwijl die
    # kamer op een reservebron buiten het circuit draaide en het circuit
    # ondertussen aan een derde kamer werd toegekend om te verwarmen.
    #
    # Only requests that address *this* circuit count. A room with a source on
    # this circuit somewhere but taking its heat from another appliance this
    # round is asking nothing here - and so may not keep this unit standing.
    # Counting it did let a hand-operated unit carry on cooling because another
    # room "wanted cooling too", while that room ran on a reserve source off the
    # circuit and the circuit was meanwhile granted to a third room to heat.
    wanted = {
        request.family
        for zone_id, request in wishes.items()
        if zone_id != zone.zone_id
        and request.family is not ModeFamily.NEUTRAL
        and request.source.entity_id in circuit.units
    }
    if not wanted or running in wanted:
        return None

    return stand_down(config, world, zone, source, Reason.CIRCUIT_CONFLICT_LOST)


def exclusive_rival(
    config: DirectorConfig,
    zone: Zone,
    source: Source,
    wishes: dict[str, constraints.Request],
    grants: dict[str, constraints.Grant],
) -> bool:
    """Return whether another appliance in this source's exclusive group wants to run.

    Op apparaat, niet op bron-ID: hetzelfde apparaat onder een andere kamer is
    geen ander lid maar hetzelfde lid, en die hoeft nergens voor te wijken.

    Wijken voor de vraag, niet voor een timer: een tegenstander die alleen op
    een timer of op een volle buitenunit wacht gaat deze ronde niet draaien, dus
    een handbediend apparaat hoeft er niet voor opzij - de director start hem
    nooit uit zichzelf, dus zo'n uit-commando was een blijvende instelling kwijt.
    Bij een echt taakconflict wijkt hij wél, anders wachten beide leden op
    elkaar tot Sint-Juttemis.

    By appliance rather than by source id: the same appliance under another room
    is not another member but the same one, and that need not step aside for
    anything.

    Yield to the asking, not to a timer: a rival that is only waiting on a timer
    or on a full outdoor unit will not run this round, so a hand-operated
    appliance need not step aside for it - the director never starts it of its
    own accord, so such an off command would lose a permanent setting. On a real
    duty conflict it does yield, otherwise both members wait for each other
    forever.
    """
    for group in config.exclusive_groups:
        members = group_entities(config, group)
        if source.entity_id not in members:
            continue
        for zone_id, request in wishes.items():
            if (
                zone_id != zone.zone_id
                and request.source.entity_id in members
                and request.source.entity_id != source.entity_id
            ):
                rival_grant = grants.get(zone_id)
                if rival_grant is not None and rival_grant.reason in (
                    Reason.SHORT_CYCLE_PROTECTION,
                    Reason.CIRCUIT_SWITCH_PENDING,
                    Reason.CIRCUIT_AT_CAPACITY,
                ):
                    continue
                return True
    return False


def stand_down(
    config: DirectorConfig, world: WorldState, zone: Zone, source: Source, reason: Reason
) -> UnitCommand:
    """Return the command putting one source back to standing still."""
    return UnitCommand(
        entity_id=source.entity_id,
        hvac_mode=idle_mode(config, world, source.entity_id, reason),
        temperature=None,
        zone_id=zone.zone_id,
        source_id=source.source_id,
        reason=reason,
    )


#: Solo circuit standing in for a source with an outdoor unit to itself.
_SOLO = Circuit(circuit_id="", name="", units=(), simultaneous_heat_cool=True)

#: Circuitweigeringen waarop de zone haar volgende bron mag proberen (anker 7).
#:
#: Circuit refusals after which the zone may try its next source (anchor 7).
_CIRCUIT_REFUSALS = (
    Reason.SHORT_CYCLE_PROTECTION,
    Reason.CIRCUIT_AT_CAPACITY,
    Reason.CIRCUIT_CONFLICT_LOST,
)
