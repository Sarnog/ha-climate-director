"""De capaciteit en de kortcyclus van een circuit.

The capacity and the short cycle of a circuit.

Hoeveel binnenunits tegelijk mogen draaien op één buitenunit, en welke starts te
snel op een stop volgen. Alleen starts worden tegengehouden, nooit stops.

How many indoor units may run at once on one outdoor unit, and which starts follow a
stop too soon. Only starts are held back, never stops.
"""

from __future__ import annotations

from .circuit_requests import Grant, Request
from .families import ModeFamily
from .models import Circuit, DirectorConfig
from .plan import Deferral, Reason
from .world import WorldState


def standing_claims(
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

    Telde alleen de eerste soort mee, dan beschermde de grens een huis
    mínder zodra je je slaapkamerairco netjes als handbediende bron
    configureert dan wanneer je hem helemaal weglaat - precies andersom dan
    het hoort.

    A limit in units is about what the outdoor unit can take, and that counts
    running indoor units rather than configuration. Whatever asks for nothing
    and keeps running occupies a slot just the same.

    Three kinds do that: a unit sitting in no zone at all, a unit in a zone that
    has been handed over - the director sends that nothing, an off included -
    and a hand-operated appliance doing the same duty as the one being asked
    for, since that one is not stood down.

    Counting only the first kind would make the limit protect a house
    *less* once you tidily configure your bedroom unit as a hand-operated
    source than when you leave it out altogether - exactly the wrong way round.
    """
    asking = {request.source.entity_id for request in requests}
    return sum(
        1
        for entity_id in circuit.units
        if entity_id not in asking
        and world.climate(entity_id).running
        and keeps_claiming(config, circuit, entity_id, standing)
    )


def keeps_claiming(
    config: DirectorConfig,
    circuit: Circuit,
    entity_id: str,
    standing: frozenset[str] = frozenset(),
) -> bool:
    """Return whether this running unit holds its place whatever we grant.

    Drie soorten doen dat, en geen van drieën vraagt deze ronde iets: een unit
    die in geen enkele zone staat, een unit die deze ronde met opzet niets
    krijgt (`standing`, uit `_standing_firm`) - daar zit ook de overgedragen
    unit in, want een override draagt het apparaat zelf over en niet de zone -
    en een handbediend apparaat, dat alleen opzij gaat als het iemand in de weg
    staat.

    Dat laatste wordt hier niet nagerekend maar aangenomen. Gaat het apparaat
    deze ronde alsnog opzij, dan is er één beoordelingsronde lang een plek te
    weinig, en die ronde volgt binnen een seconde op het commando dat hem
    uitzet. De omgekeerde fout - een plek te veel - zet een buitenunit aan het
    werk waar hij niet op gebouwd is, en dat duurt niet één ronde.

    Three kinds do, and none of the three asks for anything this round: a unit
    sitting in no zone at all, a unit that deliberately gets nothing this round
    (`standing`, from `_standing_firm`) - which includes the handed-over unit,
    since an override hands the appliance itself over rather than the zone - and
    a hand-operated appliance, which only steps aside when it is in somebody's
    way.

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
    return all(not source.autostart for _, source in owners)


def apply_capacity(
    config: DirectorConfig,
    world: WorldState,
    circuit: Circuit,
    requests: tuple[Request, ...],
    granted: list[Grant],
    standing: frozenset[str] = frozenset(),
) -> list[Grant]:
    """Trim the winners down to the outdoor unit's capacity."""
    cap = circuit.max_concurrent_units
    if cap is None or cap < 1:
        # Een met de hand bewerkte nul of negatief getal betekent geen grens,
        # niet "niemand mag ooit draaien". `validate()` meldt de configuratie;
        # de engine weigert hem niet in stilte.
        #
        # A hand-edited zero or negative number means no limit, not "nobody may
        # ever run". `validate()` reports the configuration; the engine does not
        # silently refuse it.
        return granted

    used = standing_claims(config, world, circuit, requests, standing)

    rank = {request.zone.zone_id: request.rank for request in requests}
    winners = sorted(
        (grant for grant in granted if grant.granted),
        key=lambda grant: rank.get(grant.zone_id, (0, grant.zone_id)),
    )

    # De grens telt draaiende apparaten, niet zones: een gedeeld apparaat onder
    # twee zones op één circuit levert één draaiende binnenunit op, niet twee.
    # Beslis daarom per apparaat in plaats van per toekenning. Een apparaat
    # neemt hoogstens één plek in, op de beste rang van de zones die erom
    # vragen - of het krijgt geen plek, en dan wordt elke zone erop geweigerd.
    # Anders zou de tweede zone op een geweigerd gedeeld apparaat haar
    # toekenning houden en het apparaat alsnog aanzetten.
    #
    # The limit counts running appliances, not zones: a shared appliance under
    # two zones on one circuit is one running indoor unit, not two. So decide
    # per appliance rather than per grant. An appliance takes at most one slot,
    # at the best rank of the zones asking for it - or it gets none, and then
    # every zone on it is refused. Otherwise the second zone on a refused shared
    # appliance kept its grant and started the appliance after all.
    entity_by_zone = {request.zone.zone_id: request.source.entity_id for request in requests}

    def key_of_zone(zone_id: str) -> tuple[int, str]:
        return rank.get(zone_id, (0, zone_id))

    best_rank: dict[str, tuple[int, str]] = {}
    ordered_entities: list[str] = []
    for grant in winners:
        entity_id = entity_by_zone.get(grant.zone_id) or f"\0{grant.zone_id}"
        if entity_id not in best_rank:
            # `winners` staat op rang: de eerste toekenning houdt meteen de beste rang.
            ordered_entities.append(entity_id)
            best_rank[entity_id] = key_of_zone(grant.zone_id)

    ordered_entities.sort(key=lambda entity_id: best_rank[entity_id])

    slots = used
    chosen: set[str] = set()
    for entity_id in ordered_entities:
        if slots >= cap:
            break
        chosen.add(entity_id)
        slots += 1

    denied = {
        grant.zone_id
        for grant in winners
        if (entity_by_zone.get(grant.zone_id) or f"\0{grant.zone_id}") not in chosen
    }

    return [
        Grant(grant.zone_id, grant.source_id, ModeFamily.NEUTRAL, Reason.CIRCUIT_AT_CAPACITY)
        if grant.zone_id in denied
        else grant
        for grant in granted
    ]


def apply_short_cycle(
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
