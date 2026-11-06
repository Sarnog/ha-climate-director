"""De kandidaten: wie mag meedoen en wie houdt een groep.

The candidates: who may join and who holds a group.
"""

from __future__ import annotations

from . import constraints, gates, hysteresis, sources, takeover
from .command_reasons import opening_rest_hold
from .families import (
    ModeFamily,
)
from .models import DirectorConfig, Source, Zone
from .plan import (
    Deferral,
    Plan,
    Reason,
)
from .world import WorldState


def handed_over(config: DirectorConfig, world: WorldState) -> frozenset[str]:
    """Return every appliance a handed-over zone has given up (anker 11).

    Niet de zone maar het apparaat is overgedragen: draagt een zone over, dan
    stuurt de director dat apparaat nergens meer naartoe, ook niet vanuit een
    andere zone. Voor die andere zones is het dus geen kandidaat, net als
    `excluding` in `sources.select`; het anker draagt de aanvaarde prijs.

    Niet elke zone in `zone_overrides` draagt over. Een zone die alleen door een
    hand stilstaat valt stil zonder dat er een apparaat wordt overgedragen
    (`world.zone_hands`), en dan blijft een gedeeld apparaat voor de andere zones
    beschikbaar. Alleen de schakelaar en de actie `set_override` zetten een zone in
    `zone_overrides` zonder in `zone_hands`, en dat zijn precies de twee die het
    anker noemt.

    Not the zone but the appliance is handed over: when a zone hands over, the
    director sends that appliance nothing anywhere, not from another zone either.
    For those other zones it is therefore no candidate, just as `excluding` in
    `sources.select`; the anchor carries the accepted price.

    Not every zone in `zone_overrides` hands over. A zone standing still through a
    hand alone falls silent without an appliance being handed over
    (`world.zone_hands`), and then a shared appliance stays available to the other
    zones. Only the switch and the `set_override` action put a zone in
    `zone_overrides` without putting it in `zone_hands`, and those are exactly the
    two the anchor names.
    """
    return frozenset(
        source.entity_id
        for zone, source in config.sources()
        if world.overridden(zone.zone_id) and zone.zone_id not in world.zone_hands
    )


def collect_wishes(
    config: DirectorConfig,
    world: WorldState,
    previous: Plan | None,
    blocked: frozenset[str] = frozenset(),
    takeovers: tuple[takeover.Takeover, ...] = (),
) -> tuple[
    dict[str, constraints.Request],
    dict[str, Reason],
    dict[str, tuple[Reason, ...]],
    dict[str, hysteresis.Demand],
    tuple[Deferral, ...],
]:
    """Return each zone's request, its refusal reason, every gate shut on it,
    what it would want regardless of those gates (the duty, or the duty that
    refused and why), and the house-wide rest deferrals.

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
    demands: dict[str, hysteresis.Demand] = {}
    rest_deferrals: list[Deferral] = []

    margin = config.outdoor_hysteresis
    # Wat een overgedragen zone heeft overgedragen is in elke andere zone geen
    # kandidaat (anker 11). / What a handed-over zone handed over is no candidate
    # in every other zone (anchor 11).
    handed_over_ids = handed_over(config, world)

    for zone in config.zones:
        shut[zone.zone_id] = gates.closed(config, world, zone, previous)
        demand = hysteresis.evaluate(
            zone, world, hysteresis.running_family(config, zone, world, previous), margin
        )
        demands[zone.zone_id] = demand
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
        serving_ids = serving(previous, zone.zone_id)
        stopped = frozenset() if world.precondition_ignores_openings(zone.zone_id) else blocked
        only, unbounded = takeover.narrowing(takeovers, zone.zone_id, demand.family)
        first_choice = sources.select(
            zone,
            demand.family,
            world,
            serving_ids,
            margin,
            excluding=handed_over_ids,
            only=only,
            unbounded=unbounded,
        )
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
            # Onder een overname is er maar één kandidaat, en die kan er niet
            # zijn. Dan is de kamer niet bronloos maar overgenomen, en dat is
            # wat de melder hoort te zeggen. / Under a takeover there is one
            # candidate, and it may not be there. The room is then not
            # source-less but taken over, and that is what the sensor should
            # say.
            refusals[zone.zone_id] = (
                Reason.SHARED_SOURCE_TOOK_OVER if only else Reason.NO_SOURCE_AVAILABLE
            )
            continue

        if opening_rest_hold(
            config,
            world,
            previous,
            source.entity_id,
            ignores_openings=world.precondition_ignores_openings(zone.zone_id),
            deferrals=rest_deferrals,
        ):
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
            continue

        wishes[zone.zone_id] = constraints.Request(
            zone=zone,
            source=source,
            family=demand.family,
            deviation=demand.deviation,
            priority=world.priority_for(zone.zone_id, zone.priority),
        )

    return wishes, refusals, shut, demands, tuple(rest_deferrals)


def serving(previous: Plan | None, zone_id: str) -> str | None:
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


def apply_exclusive_groups(
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
        members = group_entities(config, group)
        contenders = sorted(
            (request for request in kept.values() if request.source.entity_id in members),
            key=lambda request: request.rank,
        )
        holder = group_holder(config, world, members)
        if holder is None:
            winner = contenders[0].source.entity_id if contenders else None
        elif holder[1] is None or not contenders or not outranks(contenders[0], holder[1]):
            winner = holder[0]
        else:
            winner = contenders[0].source.entity_id
        for loser in (item for item in contenders if item.source.entity_id != winner):
            dropped[loser.zone.zone_id] = kept.pop(loser.zone.zone_id)
    return kept, dropped


def group_entities(config: DirectorConfig, group: frozenset[str]) -> frozenset[str]:
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


def group_holder(
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


def outranks(request: constraints.Request, holder_rank: tuple[int, str]) -> bool:
    """Return whether a request carries more claim than a running member."""
    return request.rank < holder_rank


def standing_firm(
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
    door `manual_conflict` beoordeeld, en die kan hem alsnog wegschakelen.

    Een apparaat dat een overgedragen zone heeft overgedragen staat er huisbreed
    bij: het is van de beheerder, ook in de andere zones die het als bron
    dragen. Daarmee houdt het zijn taak vast op het circuit waar het op staat, en
    dat is precies wat anker 11 belooft.

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
    `manual_conflict`, which may stand it down after all.

    An appliance that a handed-over zone handed over counts house-wide: it
    belongs to the administrator, in the other zones carrying it as a source
    too. That is how it holds on to its duty on the circuit it sits on, which is
    exactly what anchor 11 promises.

    A shared appliance counts only when every zone it serves leaves it alone.
    If one of them does not, the appliance gets a command through that zone and
    there is nothing to hold on to.
    """
    handed_over_ids = handed_over(config, world)

    def left_alone(zone: Zone, source: Source) -> bool:
        if source.entity_id in handed_over_ids:
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
