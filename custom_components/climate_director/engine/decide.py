"""De beslisfunctie: van momentopname naar plan.

The decision function: from snapshot to plan.

`decide()` is de enige ingang van de engine en het enige punt waar besloten
wordt. Daardoor is een toestand als "gas en airco draaien tegelijk" niet iets
dat achteraf gedetecteerd moet worden - hij komt er simpelweg nooit uit.

`decide()` is the engine's only entry point and the only place a decision is
made. A state such as "boiler and heat pump both running" therefore needs no
detection after the fact - it simply never comes out.
"""

from __future__ import annotations

from datetime import datetime

from . import constraints, gates, hysteresis, sources
from .families import (
    MODE_FAN_ONLY,
    MODE_HEAT,
    MODE_OFF,
    ModeFamily,
    family_of,
    is_compatible,
    preferred_mode,
)
from .models import Circuit, DirectorConfig, Source, Zone
from .plan import (
    CircuitDecision,
    Deferral,
    Plan,
    Reason,
    UnitCommand,
    UntouchedSource,
    ZoneDecision,
)
from .world import ClimateState, WorldState

#: Solo circuit standing in for a source with an outdoor unit to itself.
_SOLO = Circuit(circuit_id="", name="", units=(), simultaneous_heat_cool=True)


def decide(config: DirectorConfig, world: WorldState, previous: Plan | None = None) -> Plan:
    """Return the complete, consistent end state the installation should be in.

    `previous` is het plan van de vorige ronde. De dode band en de stiltevensters
    moeten weten of deze zone zelf draait, en bij een gedeeld apparaat zegt de
    apparaattoestand dat niet: die telt alleen voor de zone die het commando
    kreeg.

    `previous` is the previous round's plan. The dead band and the quiet windows
    need to know whether this zone itself is running, and on a shared appliance
    the appliance state does not say that: it counts only for the zone that got
    the command.
    """
    blocked = gates.house_wide_blocked(config, world)
    wishes, refusals, shut, woulds, rest_deferrals = _collect_wishes(
        config, world, previous, blocked
    )
    wishes, dropped = _apply_exclusive_groups(config, world, wishes)

    standing = _standing_firm(config, world, refusals)
    grants, circuit_decisions, deferrals = _resolve_circuits(config, world, wishes, standing)
    reasons = _zone_reasons(config, grants, dropped, refusals)

    families = {decision.circuit_id: decision.family for decision in circuit_decisions}
    commands, untouched, generator_deferrals, stopped_now = _build_commands(
        config, world, grants, reasons, wishes, families, blocked, previous
    )
    stopped_by_opening, opening_rest_until = _opening_rest_bookkeeping(
        config, world, previous, commands, stopped_now, rest_deferrals, generator_deferrals
    )
    return Plan(
        commands=commands,
        zones=_build_zone_decisions(
            config, world, wishes, dropped, grants, refusals, shut, woulds, previous, blocked
        ),
        circuits=circuit_decisions,
        deferrals=(*deferrals, *rest_deferrals, *generator_deferrals),
        untouched=untouched,
        stopped_by_opening=stopped_by_opening,
        opening_rest_until=opening_rest_until,
    )


def _collect_wishes(
    config: DirectorConfig,
    world: WorldState,
    previous: Plan | None,
    blocked: frozenset[str] = frozenset(),
) -> tuple[
    dict[str, constraints.Request],
    dict[str, Reason],
    dict[str, tuple[Reason, ...]],
    dict[str, ModeFamily],
    tuple[Deferral, ...],
]:
    """Return each zone's request, its refusal reason, every gate shut on it,
    the duty it would want regardless of those gates, and the house-wide rest
    deferrals.

    De dichte poorten worden voor elke zone opgehaald, ook voor de zones die
    gewoon doorlopen: dan staat er een lege lijst, en dat is precies wat een
    zone zonder hindernis hoort te melden. De gewenste taak wordt óók voor
    geblokkeerde zones uitgerekend: zonder die wens valt niet te zien of een
    dichte poort een kamer tegenhoudt die anders wél geregeld zou worden.

    The shut gates are collected for every zone, including the ones that carry
    straight on: those get an empty list, which is exactly what a zone without
    an obstacle should report. The wanted duty is computed for blocked zones
    too: without that wish there is no telling whether a shut gate is holding
    back a room that would otherwise be regulated.
    """
    wishes: dict[str, constraints.Request] = {}
    refusals: dict[str, Reason] = {}
    shut: dict[str, tuple[Reason, ...]] = {}
    woulds: dict[str, ModeFamily] = {}
    rest_deferrals: list[Deferral] = []

    margin = config.outdoor_hysteresis

    for zone in config.zones:
        shut[zone.zone_id] = gates.closed(config, world, zone, previous)
        demand = hysteresis.evaluate(
            zone, world, hysteresis.running_family(config, zone, world, previous), margin
        )
        woulds[zone.zone_id] = demand.family
        if shut[zone.zone_id]:
            refusals[zone.zone_id] = shut[zone.zone_id][0]
            continue

        if demand.family is ModeFamily.NEUTRAL:
            refusals[zone.zone_id] = demand.reason
            continue

        # Een vooruit-verzoek waarbij iemand uitdrukkelijk "toch doen" zei, gaat
        # langs de huisbrede stop heen - precies zoals het langs de gewone
        # raampoort hierboven gaat. Een uitzondering, op een plek.
        #
        # A pre-conditioning request on which somebody expressly said "do it
        # anyway" passes the house-wide stop - exactly as it passes the ordinary
        # window gate above. One exception, in one place.
        serving = _serving(previous, zone.zone_id)
        stopped = frozenset() if world.precondition_ignores_openings(zone.zone_id) else blocked
        first_choice = sources.select(zone, demand.family, world, serving, margin)
        if first_choice is not None and first_choice.entity_id in stopped:
            # De huisbrede stop stopt de zone, niet alleen het apparaat. Zou de
            # bronkeuze de stilgezette eerste keus gewoon overslaan, dan gleed
            # de kamer stilletjes door naar de tweede keus en stond de airco
            # elektrisch te verwarmen omdat er elders een deur openstaat -
            # precies wat je pas op de energierekening merkt. De "geblokkeerd"-
            # melder hoort hier dus te branden, net als bij de gewone raampoort.
            #
            # The house-wide stop stops the zone, not just the appliance. Were
            # source selection to simply skip the stopped first choice, the room
            # would slide silently onto the second choice and the air
            # conditioner would be heating electrically because a door stands
            # open elsewhere - exactly what you only notice on the energy bill.
            # The "blocked" sensor should therefore burn here, just as with the
            # ordinary window gate.
            refusals[zone.zone_id] = Reason.OPENING_OPEN_ELSEWHERE
            shut[zone.zone_id] = (*shut[zone.zone_id], Reason.OPENING_OPEN_ELSEWHERE)
            continue

        source = first_choice
        if source is None:
            refusals[zone.zone_id] = Reason.NO_SOURCE_AVAILABLE
            continue

        rest_until = None
        if not world.precondition_ignores_openings(zone.zone_id):
            rest_until = gates.opening_rest_until(config, world, previous, source.entity_id)
        if rest_until is not None and world.now < rest_until:
            # De stop is voorbij, maar het apparaat mag nog niet aan. Precies
            # zoals een circuit dat doet: de zone wacht met een
            # `SHORT_CYCLE_PROTECTION`, en de vangnetklok in de koppelingslaag
            # krijgt de deferral en komt vanzelf terug zodra de rusttijd om is.
            #
            # The stop has ended but the appliance may not start yet. Exactly
            # like a circuit: the zone waits with `SHORT_CYCLE_PROTECTION`, and
            # the binding layer's safety clock gets the deferral and returns on
            # its own once the rest has passed.
            refusals[zone.zone_id] = Reason.SHORT_CYCLE_PROTECTION
            shut[zone.zone_id] = (*shut[zone.zone_id], Reason.SHORT_CYCLE_PROTECTION)
            deferral = Deferral(source.entity_id, rest_until, Reason.SHORT_CYCLE_PROTECTION)
            if deferral not in rest_deferrals:
                rest_deferrals.append(deferral)
            continue

        wishes[zone.zone_id] = constraints.Request(
            zone=zone,
            source=source,
            family=demand.family,
            deviation=demand.deviation,
            priority=world.priority_for(zone.zone_id, zone.priority),
        )

    return wishes, refusals, shut, woulds, tuple(rest_deferrals)


def _serving(previous: Plan | None, zone_id: str) -> str | None:
    """Return the source that really delivered this zone last round, if any.

    De dode band op de buitentemperatuur hangt hieraan: alleen wat draaide mag
    doorlopen tot een band voorbij zijn grens. Een zone die vorige ronde niets
    kreeg heeft niets vast te houden.

    The outdoor dead band hangs off this: only what ran may carry on until one
    band past its bound. A zone that got nothing last round has nothing to hold
    on to.
    """
    if previous is None:
        return None
    decision = previous.decision_for(zone_id)
    if decision is None or decision.granted is ModeFamily.NEUTRAL:
        return None
    return decision.source_id


def _apply_exclusive_groups(
    config: DirectorConfig, world: WorldState, wishes: dict[str, constraints.Request]
) -> tuple[dict[str, constraints.Request], dict[str, constraints.Request]]:
    """Split the requests into those that keep a shared appliance and those that lose it.

    Zones keep their own mutual exclusion for free - a zone only ever picks one
    source - so this covers only appliances shared across zones. Losers are
    returned rather than discarded, so the plan can still report what they
    wanted and why they did not get it.

    Een lid dat nog draait in een zone die de director met rust laat, bezet de
    groep. Zo'n lid vraagt deze ronde niets - maar een ander lid mag er niet
    naast gaan draaien, want precies die combinatie hoort de groep uit te
    sluiten. Een handbediend lid heeft daarbij niet het laatste woord: vraagt
    een ander lid met méér voorrang om te draaien, dan wijkt het handbediende
    lid en gaat dat verzoek door. Een lid in een overgedragen zone is
    onverslaanbaar, want daar stuurt de director niets naartoe, ook geen uit.

    A member still running in a zone the director leaves alone occupies the
    group. Such a member asks for nothing this round - but another member may
    not start beside it, because that is exactly the combination the group
    exists to rule out. A hand-operated member does not have the last word,
    though: when another member with more claim asks to run, the hand-operated
    member yields and that request goes through. A member in a handed-over zone
    is unbeatable, since the director sends that zone nothing, an off included.
    """
    if not config.exclusive_groups:
        return wishes, {}

    kept = dict(wishes)
    dropped: dict[str, constraints.Request] = {}
    for group in config.exclusive_groups:
        members = _group_entities(config, group)
        contenders = sorted(
            (request for request in kept.values() if request.source.entity_id in members),
            key=lambda request: request.rank,
        )
        holder = _group_holder(config, world, members)
        if holder is None:
            winner = contenders[0].source.entity_id if contenders else None
        elif holder[1] is None or not contenders or not _outranks(contenders[0], holder[1]):
            winner = holder[0]
        else:
            winner = contenders[0].source.entity_id
        for loser in (item for item in contenders if item.source.entity_id != winner):
            dropped[loser.zone.zone_id] = kept.pop(loser.zone.zone_id)
    return kept, dropped


def _group_entities(config: DirectorConfig, group: frozenset[str]) -> frozenset[str]:
    """Return the appliances an exclusive group covers.

    Een groep wordt bewaard als bron-ID's, want zo kiest de gebruiker ze ook:
    het scherm toont "Woonkamer - climate.ketel". Maar hetzelfde apparaat staat
    vaak onder meerdere kamers, en heeft dan per kamer een eigen bron-ID. Wie er
    één aanvinkt is klaar in zijn hoofd, en de andere kamer startte dat apparaat
    vervolgens gewoon buiten de groep om - zonder dat er iets over klaagde.

    De groep gaat dus over het apparaat. En daarmee is een tweede kamer die
    ditzelfde apparaat vraagt geen tegenstander: dat is één apparaat dat draait,
    en precies dat is wat de groep tot één beperkt.

    A group is stored as source ids, since that is how the user picks them: the
    screen shows "Living room - climate.ketel". But the same appliance often
    sits under several rooms, and then has a source id per room. Tick one and
    you are done in your head, after which the other room simply started that
    appliance right past the group - with nothing complaining about it.

    So the group is about the appliance. And with that, a second room asking for
    that same appliance is no rival: that is one appliance running, which is
    exactly what the group limits things to.
    """
    return frozenset(
        source.entity_id for _, source in config.sources() if source.source_id in group
    )


def _group_holder(
    config: DirectorConfig, world: WorldState, members: frozenset[str]
) -> tuple[str, tuple[int, str] | None] | None:
    """Return the strongest appliance running in a zone the director leaves alone.

    Twee soorten bezetten de groep: een unit in een overgedragen zone - daar
    stuurt de director niets naartoe, ook geen uit - en een handbediende bron,
    die alleen opzij gaat als iemand hem in de weg zit. De eerste is
    onverslaanbaar (`None` als rang); de tweede draagt de rang van de zone met
    de meeste voorrang waarin hij staat, zodat hij vergelijkbaar is met een
    verzoek.

    Two kinds occupy the group: a unit in a handed-over zone - the director
    sends that nothing, an off included - and a hand-operated source, which
    only steps aside when it is in somebody's way. The first is unbeatable
    (`None` as rank); the second carries the rank of its strongest zone, making
    it comparable to a request.
    """
    strongest: tuple[tuple[int, str], str] | None = None
    for entity_id in sorted(members):
        owners = [
            (zone, source) for zone, source in config.sources() if source.entity_id == entity_id
        ]
        if not owners:
            continue
        if not world.climate(entity_id).running:
            continue
        if any(world.overridden(zone.zone_id) for zone, _ in owners):
            return entity_id, None
        if not all(not source.autostart for _, source in owners):
            continue
        rank = min(
            (world.priority_for(zone.zone_id, zone.priority), zone.zone_id) for zone, _ in owners
        )
        if strongest is None or rank < strongest[0]:
            strongest = (rank, entity_id)
    if strongest is None:
        return None
    return strongest[1], strongest[0]


def _outranks(request: constraints.Request, holder_rank: tuple[int, str]) -> bool:
    """Return whether a request carries more claim than a running member."""
    return request.rank < holder_rank


def _standing_firm(
    config: DirectorConfig, world: WorldState, refusals: dict[str, Reason]
) -> frozenset[str]:
    """Return the running appliances this round will leave exactly as they are.

    Twee gevallen krijgen niets én draaien door: een unit in een overgedragen
    zone, en een draaiende unit in een zone waarvan de binnentemperatuur niet
    te lezen is. Het derde ongemoeide geval - een onbereikbaar apparaat - staat
    er niet bij: daarvan is niet te zien wat het doet, en de engine leest het
    als stil.

    Een handbediende bron staat er alleen bij als de zone is overgedragen. Bij
    een onleesbare thermometer wordt die namelijk niet met rust gelaten maar
    door `_manual_conflict` beoordeeld, en die kan hem alsnog wegschakelen.

    Een gedeeld apparaat telt alleen mee als élke zone die het bedient het met
    rust laat. Doet één zone dat niet, dan krijgt het apparaat via die zone
    gewoon een opdracht en valt er niets vast te houden.

    Two cases get nothing and keep running: a unit in a zone that has been
    handed over, and a running unit in a zone whose indoor or outdoor
    temperature cannot be read. The third untouched case - an unreachable
    appliance - is absent: there is no telling what it does, and the engine
    reads it as standing still.

    A hand-operated source only counts when its zone has been handed over. On
    an unreadable thermometer it is not left alone but judged by
    `_manual_conflict`, which may stand it down after all.

    A shared appliance counts only when every zone it serves leaves it alone.
    If one of them does not, the appliance gets a command through that zone and
    there is nothing to hold on to.
    """

    def left_alone(zone: Zone, source: Source) -> bool:
        if world.overridden(zone.zone_id):
            return True
        return source.autostart and refusals.get(zone.zone_id) in (
            Reason.NO_INDOOR_TEMPERATURE,
            Reason.NO_OUTDOOR_TEMPERATURE,
        )

    owners: dict[str, list[bool]] = {}
    for zone, source in config.sources():
        owners.setdefault(source.entity_id, []).append(left_alone(zone, source))

    return frozenset(
        entity_id
        for entity_id, verdicts in owners.items()
        if world.climate(entity_id).running and all(verdicts)
    )


def _resolve_circuits(
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
    # anything of: a circuit whose requests all dropped away still has to be
    # reported as idle rather than silently omitted.
    for circuit in config.circuits:
        outcome = constraints.resolve(
            config, world, circuit, tuple(by_circuit.get(circuit.circuit_id, ())), standing
        )
        decisions.append(outcome.decision)
        deferrals.extend(outcome.deferrals)
        for grant in outcome.grants:
            grants[grant.zone_id] = grant

    for request in solo:
        outcome = constraints.resolve(config, world, _SOLO, (request,), standing)
        deferrals.extend(outcome.deferrals)
        for grant in outcome.grants:
            grants[grant.zone_id] = grant

    return grants, tuple(decisions), tuple(deferrals)


def _zone_reasons(
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


def _manual_conflict(
    config: DirectorConfig,
    world: WorldState,
    zone: Zone,
    source: Source,
    wishes: dict[str, constraints.Request],
    families: dict[str, ModeFamily],
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
    if _exclusive_rival(config, zone, source, wishes):
        return _stand_down(config, world, zone, source, Reason.EXCLUSIVE_GROUP_LOST)

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
        return _stand_down(config, world, zone, source, Reason.CIRCUIT_CONFLICT_LOST)

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

    return _stand_down(config, world, zone, source, Reason.CIRCUIT_CONFLICT_LOST)


def _exclusive_rival(
    config: DirectorConfig,
    zone: Zone,
    source: Source,
    wishes: dict[str, constraints.Request],
) -> bool:
    """Return whether another appliance in this source's exclusive group wants to run.

    Op apparaat, niet op bron-ID: hetzelfde apparaat onder een andere kamer is
    geen ander lid maar hetzelfde lid, en die hoeft nergens voor te wijken.

    By appliance rather than by source id: the same appliance under another room
    is not another member but the same one, and that need not step aside for
    anything.
    """
    for group in config.exclusive_groups:
        members = _group_entities(config, group)
        if source.entity_id not in members:
            continue
        for zone_id, request in wishes.items():
            if (
                zone_id != zone.zone_id
                and request.source.entity_id in members
                and request.source.entity_id != source.entity_id
            ):
                return True
    return False


def _stand_down(
    config: DirectorConfig, world: WorldState, zone: Zone, source: Source, reason: Reason
) -> UnitCommand:
    """Return the command putting one source back to standing still."""
    return UnitCommand(
        entity_id=source.entity_id,
        hvac_mode=_idle_mode(config, world, source, reason),
        temperature=None,
        zone_id=zone.zone_id,
        source_id=source.source_id,
        reason=reason,
    )


def _build_commands(
    config: DirectorConfig,
    world: WorldState,
    grants: dict[str, constraints.Grant],
    reasons: dict[str, Reason],
    wishes: dict[str, constraints.Request],
    families: dict[str, ModeFamily],
    blocked: frozenset[str] = frozenset(),
    previous: Plan | None = None,
) -> tuple[
    tuple[UnitCommand, ...],
    tuple[UntouchedSource, ...],
    tuple[Deferral, ...],
    frozenset[str],
]:
    """Return the end state for every managed climate entity, and what is left alone.

    Sources that were not chosen are commanded off explicitly rather than left
    alone. That is what makes two appliances running against each other
    unreachable instead of merely unlikely.

    Drie gevallen krijgen wél niets, en alle drie met opzet. Die worden
    apart teruggegeven in plaats van stil overgeslagen: van buiten is "de
    director laat dit met rust" niet te onderscheiden van "de director doet
    niets", en dat verschil is nu juist wat je wilt weten.

    Three cases do get nothing, all three deliberately. Those are returned
    separately rather than quietly skipped: from the outside "the director is
    leaving this alone" is indistinguishable from "the director does nothing",
    and that difference is exactly what you want to know.
    """
    commands: list[UnitCommand] = []
    untouched: list[UntouchedSource] = []

    for zone, source in config.sources():
        if not world.climate(source.entity_id).available:
            untouched.append(
                UntouchedSource(source.entity_id, zone.zone_id, Reason.SOURCE_UNREACHABLE)
            )
            continue

        # Een zone met een override is van de beheerder, niet van de director.
        # Overnemen betekent hier: niet aansturen - ook niet uitzetten. Wie de
        # noodknop gebruikt wil het apparaat zelf zetten en houden, ongeacht
        # buitengrenzen, seizoen of een openstaand raam. Zou de director hem
        # alsnog uitzetten, dan was de override geen noodknop maar een slot.
        #
        # A zone under override belongs to the administrator, not to the
        # director. Taking over means: issue nothing - not even an off. Whoever
        # reaches for the override wants to set the appliance themselves and
        # keep it there, whatever the outdoor bounds, the season or an open
        # window say. Were the director to switch it off anyway, the override
        # would be a lock rather than an override.
        if world.overridden(zone.zone_id):
            untouched.append(
                UntouchedSource(source.entity_id, zone.zone_id, Reason.MANUAL_OVERRIDE)
            )
            continue

        grant = grants.get(zone.zone_id)
        chosen = grant is not None and grant.granted and grant.source_id == source.source_id

        # Een handbediende bron wordt niet aangestuurd tenzij hij in de weg
        # staat. Hem "voor de zekerheid" uitzetten zou precies het apparaat
        # uitschakelen dat iemand net met de hand heeft aangezet.
        #
        # A manual source is left alone unless it is in the way. Switching it
        # off "to be safe" would turn off exactly the appliance somebody just
        # switched on by hand.
        if not source.autostart:
            standing_down = _manual_conflict(config, world, zone, source, wishes, families)
            if standing_down is not None:
                commands.append(standing_down)
            else:
                untouched.append(
                    UntouchedSource(source.entity_id, zone.zone_id, Reason.MANUAL_SOURCE)
                )
            continue

        if chosen and grant is not None:
            settings = zone.settings_for(grant.family)
            commands.append(
                UnitCommand(
                    entity_id=source.entity_id,
                    hvac_mode=preferred_mode(grant.family),
                    temperature=_clamped_target(
                        settings.target if settings else None,
                        world.climate(source.entity_id),
                    ),
                    zone_id=zone.zone_id,
                    source_id=source.source_id,
                    reason=Reason.REGULATING,
                )
            )
            continue

        # A zone that is being served has its other sources stood down for that
        # reason, not for whatever kept the chosen source waiting.
        served = grant is not None and grant.granted
        reason = (
            Reason.OTHER_SOURCE_CHOSEN if served else reasons.get(zone.zone_id, Reason.SATISFIED)
        )

        # Zonder leesbare binnen- of buitentemperatuur valt er niets te
        # beslissen, en dan is uitzetten de enige fout die je kunt maken: een
        # draaiend apparaat zou uitgaan omdat de sensor kapot is. Dat apparaat
        # wordt met rust gelaten; wie uit staat krijgt gewoon zijn uit-commando,
        # want "elke beheerde bron krijgt een commando" blijft gelden.
        #
        # Without a readable indoor or outdoor temperature there is nothing to
        # decide, and switching off is the only mistake to make then: a running
        # appliance would go off because the sensor is broken. That appliance is
        # left alone; one that is off simply gets its off command, since "every
        # managed source gets a command" still holds.
        if reason in (Reason.NO_INDOOR_TEMPERATURE, Reason.NO_OUTDOOR_TEMPERATURE) and (
            world.climate(source.entity_id).running
        ):
            untouched.append(UntouchedSource(source.entity_id, zone.zone_id, reason))
            continue

        commands.append(
            UnitCommand(
                entity_id=source.entity_id,
                hvac_mode=_idle_mode(config, world, source, reason),
                temperature=None,
                zone_id=zone.zone_id,
                source_id=source.source_id,
                reason=reason,
            )
        )

    generator_commands, generator_untouched, generator_deferrals = _generator_commands(
        config, world, grants, previous
    )
    commands.extend(generator_commands)
    untouched.extend(generator_untouched)
    pre_collapse = list(commands)
    commands = _collapse_shared(config, world, commands)
    commands = _stop_blocked(config, world, grants, blocked, commands)
    # De openingsstop hangt aan het apparaat, niet aan de reden die de collapse
    # overleefde. Bij een gedeelde ketel wint de reden van de zone met de meeste
    # voorrang, en dat is niet altijd de opening; de pre-collapse-opdrachten
    # weten nog wél welke apparaten erdoor stilgezet werden.
    #
    # The opening stop hangs on the appliance, not on the reason that survived
    # the collapse. On a shared boiler the reason of the highest-priority zone
    # wins, and that is not always the opening; the pre-collapse commands still
    # know which appliances it stopped.
    stopped_now = frozenset(
        command.entity_id
        for command in (*pre_collapse, *commands)
        if command.reason in (Reason.OPENING_OPEN, Reason.OPENING_OPEN_ELSEWHERE)
        and command.hvac_mode == MODE_OFF
    )

    # Een gedeeld apparaat staat onder meerdere zones. Krijgt het via één zone
    # toch een opdracht, dan wordt het niet met rust gelaten - hoe de andere
    # zones erover dachten doet er dan niet meer toe.
    #
    # A shared appliance sits under several zones. If one of them commands it
    # after all, it is not being left alone - what the other zones thought of
    # it no longer matters.
    commanded = {command.entity_id for command in commands}
    left_alone = tuple(
        item for item in _first_per_entity(untouched) if item.entity_id not in commanded
    )

    # Stops before starts. On a circuit that has to swap duty, starting the new
    # one before the old has let go would put two duties on one compressor for
    # as long as the calls take to land.
    ordered = tuple(sorted(commands, key=lambda command: _command_order(config, command)))
    return ordered, left_alone, generator_deferrals, stopped_now


def _opening_rest_bookkeeping(
    config: DirectorConfig,
    world: WorldState,
    previous: Plan | None,
    commands: tuple[UnitCommand, ...],
    stopped_now: frozenset[str],
    rest_deferrals: tuple[Deferral, ...],
    generator_deferrals: tuple[Deferral, ...],
) -> tuple[frozenset[str], dict[str, datetime]]:
    """Return this plan's per-appliance opening-rest bookkeeping.

    De rust hangt aan het apparaat, niet aan de reden van het vorige commando.
    `stopped_by_opening` noemt de apparaten die deze ronde door een opening
    zijn stilgezet; `opening_rest_until` draagt de eindtijden van al lopende
    rusten mee zolang het apparaat niet draait. Zo overleeft de rust een
    collapse die een andere reden liet winnen én een tussenronde waarin het
    apparaat om een andere reden uit stond.

    The rest hangs on the appliance, not on the previous command's reason.
    `stopped_by_opening` names the appliances an opening stopped this round;
    `opening_rest_until` carries the deadlines of already running rests while
    the appliance stays off. That way the rest survives a collapse that let
    another reason win, and an intermediate round in which the appliance stood
    off for another reason.
    """
    if previous is None:
        return stopped_now, dict(
            (deferral.subject, deferral.until)
            for deferral in (*rest_deferrals, *generator_deferrals)
            if deferral.reason is Reason.SHORT_CYCLE_PROTECTION
        )

    commanded_running = {
        command.entity_id
        for command in commands
        if command.hvac_mode not in (MODE_OFF, MODE_FAN_ONLY)
    }
    commanded = {command.entity_id for command in commands}
    carried_stopped = set(previous.stopped_by_opening)
    carried_until = dict(previous.opening_rest_until)
    dropped = {
        entity
        for entity in (*carried_stopped, *carried_until)
        if entity in commanded_running
        or (entity not in commanded and world.climate(entity).running)
    }

    fresh_until = {
        deferral.subject: deferral.until
        for deferral in (*rest_deferrals, *generator_deferrals)
        if deferral.reason is Reason.SHORT_CYCLE_PROTECTION
    }
    opening_rest_until = {
        entity: until for entity, until in carried_until.items() if entity not in dropped
    }
    opening_rest_until.update(fresh_until)
    stopped_by_opening = frozenset(
        ({entity for entity in carried_stopped if entity not in dropped} | set(stopped_now))
        - set(fresh_until)
    )
    return stopped_by_opening, opening_rest_until


def _stop_blocked(
    config: DirectorConfig,
    world: WorldState,
    grants: dict[str, constraints.Grant],
    blocked: frozenset[str],
    commands: list[UnitCommand],
) -> list[UnitCommand]:
    """Return the commands with every house-wide stopped appliance forced off.

    De bronkeuze laat een stilgezet apparaat al vallen, dus in de gewone gang
    van zaken verandert dit niets. Het staat er voor de paden die buiten die
    keuze omgaan - een gedeelde ketel die zijn commando van een andere zone
    kreeg, en de generator, die helemaal geen bronkeuze doorloopt. Zo kan er
    langs geen enkele weg alsnog een `heat` uitkomen.

    Wat de director met rust laat blijft met rust: een overgedragen zone en een
    handbediende bron krijgen geen commando, en die staan hier dus ook niet in.
    Deze instelling stuurt wat de director stuurt; hij is geen uitknop die over
    een override heen gaat.

    Source selection already drops a stopped appliance, so in the ordinary run
    of things this changes nothing. It is here for the paths going round that
    choice - a shared boiler that got its command from another zone, and the
    generator, which never runs through source selection at all. That way no
    route can let a `heat` come out after all.

    Whatever the director leaves alone stays left alone: a zone handed over and
    a hand-operated source get no command, and are therefore absent here too.
    This setting steers what the director steers; it is no off switch reaching
    over an override.
    """
    if not blocked:
        return commands
    return [
        command
        if command.entity_id not in blocked
        or command.hvac_mode == MODE_OFF
        or _ignores_openings(config, world, grants, command)
        else UnitCommand(
            entity_id=command.entity_id,
            hvac_mode=MODE_OFF,
            temperature=None,
            zone_id=command.zone_id,
            source_id=command.source_id,
            reason=Reason.OPENING_OPEN_ELSEWHERE,
        )
        for command in commands
    ]


def _ignores_openings(
    config: DirectorConfig,
    world: WorldState,
    grants: dict[str, constraints.Grant],
    command: UnitCommand,
) -> bool:
    """Return whether this command carries a pre-conditioning "do it anyway".

    Een zonecommando draagt zijn eigen zone. Een generator hoort bij geen zone,
    dus daar telt of een van de zones die hij bedient dat verzoek draagt en op
    dit moment ook echt bediend wordt - anders zou een uitzondering in een kamer
    die niets krijgt de ketel alsnog laten branden.

    A zone command carries its own zone. A generator belongs to no zone, so
    there it counts whether one of the zones it serves carries that request and
    is actually being served right now - otherwise an exception in a room
    getting nothing would keep the boiler burning after all.
    """
    if command.zone_id:
        return world.precondition_ignores_openings(command.zone_id)
    return any(
        world.precondition_ignores_openings(zone.zone_id)
        and (grant := grants.get(zone.zone_id)) is not None
        and grant.granted
        for generator in config.generators
        if generator.entity_id == command.entity_id
        for zone in config.zones
        if generator.serves(zone.zone_id)
    )


def _first_per_entity(untouched: list[UntouchedSource]) -> list[UntouchedSource]:
    """Return one entry per appliance, keeping the first zone that reported it."""
    seen: dict[str, UntouchedSource] = {}
    for item in untouched:
        seen.setdefault(item.entity_id, item)
    return list(seen.values())


def _collapse_shared(
    config: DirectorConfig, world: WorldState, commands: list[UnitCommand]
) -> list[UnitCommand]:
    """Return one command per appliance, so a shared source never gets two.

    Bij een centrale verwarming staat dezelfde thermostaat als bron onder
    meerdere zones. De opdrachten worden per zone opgebouwd, dus zo'n apparaat
    kreeg er een van elke zone - en die spreken elkaar tegen zodra de ene kamer
    warmte vraagt en de andere niets. Twee tegengestelde opdrachten naar een
    apparaat is nooit goed; welke er wint hing af van de volgorde, en dat is
    geen ontwerp maar toeval.

    Vraag wint van stilte: een gesloten systeem heeft nu eenmaal geen manier om
    de ene kamer wel en de andere niet te verwarmen. Vragen er meer zones
    tegelijk, dan volgt het apparaat de zone met de meeste voorrang - net zoals
    een gewone thermostaat de leidende kamer volgt. Die voorrang is de live
    waarde, niet de ingestelde: een automatisering die `number.<zone>_prioriteit`
    verzet hoort de gedeelde ketel net zo goed te sturen als de rest.

    With central heating the same thermostat sits as a source under several
    zones. Commands are built per zone, so such an appliance got one from each -
    and they contradict each other the moment one room asks for heat and the
    other does not. Two opposing commands to one appliance is never right; which
    won depended on ordering, and that is chance rather than design.

    Demand beats silence: a closed system simply has no way to heat one room and
    not the other. If several zones ask at once, the appliance follows the zone
    with the most claim - just as an ordinary thermostat follows the leading
    room. That claim is the live priority, not the configured one: an automation
    moving `number.<zone>_priority` should steer the shared boiler just as much
    as the rest.
    """
    ranked: dict[str, UnitCommand] = {}
    for command in commands:
        sitting = ranked.get(command.entity_id)
        if sitting is None or _claim(config, world, command) < _claim(config, world, sitting):
            ranked[command.entity_id] = command
    return list(ranked.values())


def _claim(config: DirectorConfig, world: WorldState, command: UnitCommand) -> tuple[int, int, str]:
    """Return how strong a command's claim on its appliance is; lower wins."""
    running = command.hvac_mode not in (MODE_OFF, MODE_FAN_ONLY)
    zone = config.zone(command.zone_id) if command.zone_id else None
    priority = world.priority_for(command.zone_id, zone.priority) if zone else 0
    return (0 if running else 1, priority, command.zone_id or "")


def _generator_commands(
    config: DirectorConfig,
    world: WorldState,
    grants: dict[str, constraints.Grant],
    previous: Plan | None = None,
) -> tuple[list[UnitCommand], list[UntouchedSource], tuple[Deferral, ...]]:
    """Return the command for each shared heat source, and the ones left alone.

    A generator runs while any zone it serves is being heated, and stops once
    none is. There is nothing to arbitrate here - radiator valves all only ever
    heat - so this is a plain follow-along, not a conflict to resolve.

    De tweede lijst is voor `Plan.untouched`: een onbereikbare ketel hoort daar
    met `SOURCE_UNREACHABLE` in, niet stilletjes nergens. Een generator hoort
    bij geen enkele zone, dus zijn `UntouchedSource.zone_id` is leeg - behalve
    bij een override, waar de zone die de override draagt genoemd wordt.

    The second list feeds `Plan.untouched`: an unreachable boiler belongs there
    as `SOURCE_UNREACHABLE`, not silently nowhere. A generator belongs to no
    zone, so its `UntouchedSource.zone_id` is empty - except under an override,
    where the zone carrying the override is named.
    """
    commands: list[UnitCommand] = []
    untouched: list[UntouchedSource] = []
    deferrals: list[Deferral] = []

    for generator in config.generators:
        if not world.climate(generator.entity_id).available:
            untouched.append(UntouchedSource(generator.entity_id, "", Reason.SOURCE_UNREACHABLE))
            continue

        asking = [
            zone
            for zone in config.zones
            if generator.serves(zone.zone_id)
            and (grant := grants.get(zone.zone_id)) is not None
            and grant.granted
            and grant.family is ModeFamily.HEAT
        ]

        if not asking:
            # Een zone met een override is overgedragen: de director weet niet
            # meer wat daar nodig is. Hem dan toch de gedeelde ketel laten
            # uitzetten maakt de override een halve maatregel - de kamer mag
            # zijn eigen kraan houden, maar het water wordt koud. Wie de
            # noodknop gebruikt, of een zone tijdelijk aan een eigen
            # automatisering laat, verwacht dat de director van die warmte
            # afblijft.
            #
            # Aanzetten mag wel: dat botst nooit met een zone die warmte wil.
            # Alleen het uitzetten wordt hier ingehouden.
            #
            # A zone under override has been handed over: the director no
            # longer knows what it needs. Letting it switch off the shared
            # boiler anyway would make the override a half measure - the room
            # keeps its own valve, but the water goes cold. Whoever reaches for
            # the override, or leaves a zone to an automation of their own,
            # expects the director to keep its hands off that heat.
            #
            # Switching on stays allowed: that never clashes with a zone that
            # wants heat. Only the switching off is withheld here.
            overridden = next(
                (
                    zone.zone_id
                    for zone in config.zones
                    if generator.serves(zone.zone_id) and world.overridden(zone.zone_id)
                ),
                "",
            )
            if overridden:
                untouched.append(
                    UntouchedSource(generator.entity_id, overridden, Reason.MANUAL_OVERRIDE)
                )
                continue

            commands.append(
                UnitCommand(
                    entity_id=generator.entity_id,
                    hvac_mode=MODE_OFF,
                    source_id=generator.generator_id,
                    reason=Reason.SATISFIED,
                )
            )
            continue

        # Zonder vaste waarde volgt de bron de warmste vraag. Het koudste
        # setpoint nemen zou de kamer die het hardst om warmte vraagt nooit
        # laten halen wat hij vroeg.
        #
        # Without a fixed value the source follows the warmest demand. Taking
        # the coldest setpoint would leave the room asking hardest never
        # reaching what it asked for.
        setpoint = generator.setpoint
        if setpoint is None:
            targets = [zone.heat.target for zone in asking if zone.heat]
            setpoint = max(targets) if targets else None

        rest_until = None
        if not any(world.precondition_ignores_openings(zone.zone_id) for zone in asking):
            rest_until = gates.opening_rest_until(config, world, previous, generator.entity_id)
        if rest_until is not None and world.now < rest_until:
            # De huisbrede stop geldt ook voor een generator; de herstart wacht
            # dezelfde rusttijd als een bron zonder circuit.
            #
            # The house-wide stop covers a generator too; the restart waits the
            # same rest as a source without a circuit.
            commands.append(
                UnitCommand(
                    entity_id=generator.entity_id,
                    hvac_mode=MODE_OFF,
                    source_id=generator.generator_id,
                    reason=Reason.SHORT_CYCLE_PROTECTION,
                )
            )
            deferral = Deferral(generator.entity_id, rest_until, Reason.SHORT_CYCLE_PROTECTION)
            if deferral not in deferrals:
                deferrals.append(deferral)
            continue

        commands.append(
            UnitCommand(
                entity_id=generator.entity_id,
                hvac_mode=MODE_HEAT,
                temperature=_clamped_target(setpoint, world.climate(generator.entity_id)),
                source_id=generator.generator_id,
                reason=Reason.REGULATING,
            )
        )

    return commands, untouched, tuple(deferrals)


def _idle_mode(config: DirectorConfig, world: WorldState, source: Source, reason: Reason) -> str:
    """Return how a source stands down: off, or circulating air.

    Fan-only is only ever offered to a zone that lost its circuit to another
    zone. A zone that is simply warm enough has nothing to circulate for, and
    leaving its fan running would read as a fault. And fan-only is only offered
    when the unit reports it can run that mode; a unit that knows just heat,
    cool and off would refuse the command, so it falls back on off.
    """
    if reason is not Reason.CIRCUIT_CONFLICT_LOST:
        return MODE_OFF
    circuit = config.circuit_for_entity(source.entity_id)
    if (
        circuit is not None
        and circuit.allow_fan_only_during_conflict
        and world.climate(source.entity_id).supports(MODE_FAN_ONLY)
    ):
        return MODE_FAN_ONLY
    return MODE_OFF


def _clamped_target(target: float | None, state: ClimateState) -> float | None:
    """Clamp a setpoint to what the appliance says it accepts.

    Home Assistant weigert een setpoint buiten `min_temp`/`max_temp` met een
    `ServiceValidationError`, en de stand ging dan nooit meer mee. Beter: vraag
    het dichtstbijzijnde setpoint dat het apparaat wél aanneemt, zodat de stand
    gewoon landt. Geen opgave betekent onbekend, en onbekend wordt doorgelaten.

    Home Assistant refuses a setpoint outside `min_temp`/`max_temp` with a
    `ServiceValidationError`, and the mode then never went along. Better: ask
    for the nearest setpoint the appliance does accept, so the mode simply
    lands. No listing means unknown, and unknown is passed through.
    """
    if target is None:
        return None
    if state.min_temp is not None and target < state.min_temp:
        return state.min_temp
    if state.max_temp is not None and target > state.max_temp:
        return state.max_temp
    return target


def _command_order(config: DirectorConfig, command: UnitCommand) -> tuple[int, str]:
    """Return the ordering key that puts stops ahead of starts.

    A shared heat source starts last of all. Firing the boiler before the
    valves are open would have it heat water against closed radiators; the
    other way round the room is simply cold for a moment longer.
    """
    generators = {item.entity_id for item in config.generators}
    if command.hvac_mode == MODE_OFF:
        rank = 0
    elif command.hvac_mode == MODE_FAN_ONLY:
        rank = 1
    elif command.entity_id in generators:
        rank = 3
    else:
        rank = 2
    return (rank, command.entity_id)


def _build_zone_decisions(
    config: DirectorConfig,
    world: WorldState,
    wishes: dict[str, constraints.Request],
    dropped: dict[str, constraints.Request],
    grants: dict[str, constraints.Grant],
    refusals: dict[str, Reason],
    shut: dict[str, tuple[Reason, ...]],
    woulds: dict[str, ModeFamily],
    previous: Plan | None = None,
    blocked: frozenset[str] = frozenset(),
) -> tuple[ZoneDecision, ...]:
    """Return one decision per zone, saying what it asked for and what it got."""
    decisions: list[ZoneDecision] = []

    for zone in config.zones:
        request = wishes.get(zone.zone_id)
        would = woulds.get(zone.zone_id, ModeFamily.NEUTRAL)

        if request is None:
            # A zone that lost a shared appliance still had a wish; keep it, so
            # the decision reads "wanted heat, got nothing" rather than hiding
            # the request that was made.
            loser = dropped.get(zone.zone_id)
            decisions.append(
                ZoneDecision(
                    zone_id=zone.zone_id,
                    wanted=loser.family if loser else ModeFamily.NEUTRAL,
                    granted=ModeFamily.NEUTRAL,
                    source_id=loser.source.source_id if loser else None,
                    reason=(
                        Reason.EXCLUSIVE_GROUP_LOST
                        if loser
                        else refusals.get(zone.zone_id, Reason.SATISFIED)
                    ),
                    closed_gates=shut.get(zone.zone_id, ()),
                    would_want=would,
                )
            )
            continue

        grant = grants.get(zone.zone_id)
        decisions.append(
            ZoneDecision(
                zone_id=zone.zone_id,
                wanted=request.family,
                granted=grant.family if grant is not None else ModeFamily.NEUTRAL,
                source_id=request.source.source_id,
                reason=grant.reason if grant is not None else Reason.NO_SOURCE_AVAILABLE,
                closed_gates=shut.get(zone.zone_id, ()),
                passed_over=sources.passed_over(
                    zone,
                    request.family,
                    world,
                    _serving(previous, zone.zone_id),
                    config.outdoor_hysteresis,
                    blocked,
                ),
                would_want=would,
            )
        )

    return tuple(decisions)
