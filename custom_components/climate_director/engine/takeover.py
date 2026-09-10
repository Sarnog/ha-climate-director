"""Wie het gebied van een weggevallen bron overneemt.

Who takes over the area of a source that dropped out.

Anker 12. Een bron draagt `covers_zones`: de zones die hij meeverwarmt of
meekoelt zodra hij draait. Valt een beheerde bron in dat gebied weg, dan neemt
de bron met het gebied de taak over, en levert er in dat hele gebied geen ander
klimaatapparaat meer warmte of koeling. Anders verwarmt de ketel het hele huis
terwijl de airco's doorstoken, of wordt dezelfde ruimte tegelijk verwarmd en
gekoeld.

Anchor 12. A source carries `covers_zones`: the zones it heats or cools along
with it the moment it runs. When a managed source in that area drops out, the
source with the area takes the duty over, and no other climate appliance in that
whole area delivers heat or cooling any more. Otherwise the boiler heats the
whole house while the air conditioners carry on, or the same room is heated and
cooled at once.

De module doet twee dingen en houdt ze uit elkaar, want ze hangen aan
verschillende momenten. `in_force()` zegt wélke overnames op dit moment gelden -
dat is invoer voor de bronkeuze, dus vóór het plan. `stop_others()` zet de
apparaten stil die daardoor niets meer mogen leveren - dat kan pas ná het plan,
want het hangt eraan of de overnemer werkelijk een taak kreeg.

The module does two things and keeps them apart, because they hang off different
moments. `in_force()` says which takeovers hold right now - that is input to
source selection, so before the plan. `stop_others()` stands down the appliances
that may no longer deliver anything - that can only happen after the plan, since
it depends on whether the taker-over really got a duty.

Home Assistant komt hier niet voor: dit is engine, en de enige invoer is de
configuratie plus de momentopname.

Home Assistant does not appear here: this is engine, and the only input is the
configuration plus the snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from .families import MODE_FAN_ONLY, MODE_OFF, ModeFamily
from .models import DirectorConfig
from .plan import Reason, UnitCommand, UntouchedSource
from .world import WorldState


@dataclass(frozen=True, slots=True)
class Takeover:
    """One appliance covering an area whose source dropped out."""

    entity_id: str
    """The appliance taking the duty over."""

    zones: frozenset[str]
    """Het hele gebied: de eigen zones van dit apparaat plus wat het meebedient.

    The whole area: this appliance's own zones plus what it serves along.
    """

    families: frozenset[ModeFamily]
    """The duties this appliance can actually take over.

    Een ketel neemt verwarmen over en koelen niet. Zonder dit onderscheid zou
    een onbereikbare airco in de zomer het hele huis van koeling afsnijden,
    omdat de ketel het gebied draagt maar niets kan leveren.

    A boiler takes heating over and cooling not. Without this distinction an
    unreachable air conditioner in summer would cut the whole house off from
    cooling, because the boiler carries the area but can deliver nothing.
    """


def areas(config: DirectorConfig) -> dict[str, frozenset[str]]:
    """Return the area every appliance carries, merged on `entity_id`.

    Hetzelfde apparaat staat vaak als aparte bron onder meerdere kamers. De
    gebieden worden daarom samengevoegd op `entity_id`, precies zoals een
    uitsluitende groep dat doet: één keer invullen is genoeg, en de eigen zones
    van élke rij horen er vanzelf bij. Een zone die niet bestaat telt niet mee -
    `validate()` meldt die apart, en stil meerekenen zou een gebied groter maken
    dan de installatie kent.

    The same appliance often sits as a separate source under several rooms. The
    areas are therefore merged on `entity_id`, exactly as an exclusive group
    does: filling it in once is enough, and the own zones of every row belong to
    it by themselves. A zone that does not exist does not count - `validate()`
    reports that separately, and counting it quietly would make an area larger
    than the installation knows.
    """
    known = {zone.zone_id for zone in config.zones}
    merged: dict[str, set[str]] = {}
    for _, source in config.sources():
        if source.covers_zones:
            merged.setdefault(source.entity_id, set()).update(
                zone_id for zone_id in source.covers_zones if zone_id in known
            )
    for zone, source in config.sources():
        if source.entity_id in merged:
            merged[source.entity_id].add(zone.zone_id)
    return {entity_id: frozenset(zones) for entity_id, zones in merged.items()}


def in_force(config: DirectorConfig, world: WorldState) -> tuple[Takeover, ...]:
    """Return every takeover that holds at this moment.

    Een overname geldt zodra een beheerde bron in het gebied onbereikbaar is en
    dat lang genoeg is, terwijl de overnemer zelf wél bereikbaar is en de taak
    kan leveren. Een leeg `covers_zones` laat deze uitzondering nergens
    ontstaan, dus een installatie die het veld niet invult merkt hier niets van.

    A takeover holds the moment a managed source in the area is unreachable and
    has been for long enough, while the taker-over itself is reachable and can
    deliver the duty. An empty `covers_zones` never lets this exception arise, so
    an installation that leaves the field empty notices nothing.
    """
    found: list[Takeover] = []
    for entity_id, zones in sorted(areas(config).items()):
        if not world.climate(entity_id).available:
            continue
        families = _families(config, entity_id)
        if not families:
            continue
        if not _dropped_out(config, world, entity_id, zones, _delay(config, entity_id)):
            continue
        found.append(Takeover(entity_id, zones, families))
    return tuple(found)


def covering(takeovers: tuple[Takeover, ...], zone_id: str, family: ModeFamily) -> Takeover | None:
    """Return the takeover serving this zone for this duty, if there is one."""
    for item in takeovers:
        if zone_id in item.zones and family in item.families:
            return item
    return None


def narrowing(
    takeovers: tuple[Takeover, ...], zone_id: str, family: ModeFamily
) -> tuple[frozenset[str] | None, frozenset[str]]:
    """Return `(only, unbounded)` for one zone's duty under a takeover.

    `only` beperkt de bronkeuze tot de overnemer: de kamer schuift niet door
    naar haar volgende bron, want dan verwarmde die kamer alsnog elektrisch
    binnen een gebied dat de ketel al warm maakt. `unbounded` zet het
    buitenvenster van de overnemer opzij: de scheiding op buitentemperatuur
    blijft bestaan, maar is geen reden meer om een huis koud te laten staan.

    `only` limits source selection to the taker-over: the room does not slide on
    to its next source, since that room would then be heating electrically
    inside an area the boiler is already warming. `unbounded` sets the
    taker-over's outdoor window aside: the split on outdoor temperature stays,
    but is no longer a reason to leave a house standing cold.
    """
    item = covering(takeovers, zone_id, family)
    if item is None:
        return None, frozenset()
    return frozenset({item.entity_id}), frozenset({item.entity_id})


def stop_others(
    config: DirectorConfig,
    world: WorldState,
    takeovers: tuple[Takeover, ...],
    commands: list[UnitCommand],
    untouched: list[UntouchedSource],
) -> list[UnitCommand]:
    """Return the commands with everything else in a taken-over area stood down.

    Alleen zolang de overnemer werkelijk een taak draait: dan pas kan er
    tegelijk verwarmd en gekoeld worden, en dan pas stookt een airco mee in een
    kamer die de ketel al warm maakt. Een apparaat dat al uit of op alleen
    ventileren staat blijft zoals het staat - dat levert niets, precies zoals de
    huisbrede stop het al doet.

    Only while the taker-over really runs a duty: only then can one room be
    heated and cooled at once, and only then does an air conditioner add to a
    room the boiler is already warming. An appliance already off or on fan only
    stays as it stands - that delivers nothing, exactly as the house-wide stop
    already has it.

    Een handbediend apparaat gaat hier wél uit, en dat is het bewuste verschil
    met "een handbediende bron wordt met rust gelaten": hij staat niet in de weg
    van een circuit maar van de natuurkunde. Een overgedragen zone blijft
    onaangeroerd - die is van de beheerder - en een onbereikbaar apparaat valt
    niets aan te sturen.

    A hand-operated appliance does go off here, and that is the deliberate
    difference with "a manual source is left alone": it is not in the way of a
    circuit but of physics. A zone handed over stays untouched - that belongs to
    the administrator - and an unreachable appliance has nothing to command.
    """
    running = {
        item.entity_id
        for item in takeovers
        if any(
            command.entity_id == item.entity_id
            and command.hvac_mode not in (MODE_OFF, MODE_FAN_ONLY)
            for command in commands
        )
    }
    if not running:
        return commands
    covered = _covered(config, takeovers, running)
    if not covered:
        return commands

    stood_down = [
        command
        if command.entity_id not in covered or command.hvac_mode in (MODE_OFF, MODE_FAN_ONLY)
        else UnitCommand(
            entity_id=command.entity_id,
            hvac_mode=MODE_OFF,
            temperature=None,
            zone_id=command.zone_id,
            source_id=command.source_id,
            reason=Reason.SHARED_SOURCE_TOOK_OVER,
        )
        for command in commands
    ]
    already = {command.entity_id for command in stood_down}
    for item in untouched:
        if item.reason is not Reason.MANUAL_SOURCE:
            continue
        if item.entity_id in already or item.entity_id not in covered:
            continue
        if not world.climate(item.entity_id).running:
            continue
        already.add(item.entity_id)
        stood_down.append(
            UnitCommand(
                entity_id=item.entity_id,
                hvac_mode=MODE_OFF,
                temperature=None,
                zone_id=item.zone_id,
                reason=Reason.SHARED_SOURCE_TOOK_OVER,
            )
        )
    return stood_down


def _covered(
    config: DirectorConfig, takeovers: tuple[Takeover, ...], running: set[str]
) -> frozenset[str]:
    """Return the appliances standing inside an area whose taker-over runs."""
    covered: set[str] = set()
    for item in takeovers:
        if item.entity_id not in running:
            continue
        for zone, source in config.sources():
            if zone.zone_id in item.zones and source.entity_id not in running:
                covered.add(source.entity_id)
    return frozenset(covered)


def _families(config: DirectorConfig, entity_id: str) -> frozenset[ModeFamily]:
    """Return the duties this appliance can deliver, over all its source rows."""
    return frozenset(
        family
        for family in (ModeFamily.HEAT, ModeFamily.COOL)
        for _, source in config.sources()
        if source.entity_id == entity_id and source.supports(family)
    )


def _delay(config: DirectorConfig, entity_id: str) -> timedelta:
    """Return the wait this appliance keeps before taking over.

    De rijen van hetzelfde apparaat delen één gebied, dus ze delen ook één
    wachttijd. De langste wint: een rem is een rem, en de veilige kant van een
    rem is de lange kant. Alleen de rijen die het gebied dragen tellen mee -
    "één keer invullen is genoeg" zou anders ongedaan gemaakt worden door de
    standaard op een rij die niets invulde.

    The rows of the same appliance share one area, so they share one wait too.
    The longest wins: a brake is a brake, and the safe side of a brake is the
    long side. Only the rows carrying the area count - "filling it in once is
    enough" would otherwise be undone by the default on a row that filled in
    nothing.
    """
    return max(
        (
            source.takeover_delay
            for _, source in config.sources()
            if source.entity_id == entity_id and source.covers_zones
        ),
        default=timedelta(0),
    )


def _dropped_out(
    config: DirectorConfig,
    world: WorldState,
    entity_id: str,
    zones: frozenset[str],
    delay: timedelta,
) -> bool:
    """Return whether a source in this area has been unreachable long enough.

    Onbereikbaar is wat de wereld onbereikbaar noemt (`ClimateState.available`):
    `unavailable`, `unknown`, of een entiteit die er niet is. Een apparaat dat
    zijn commando niet aanneemt telt hier niet mee - dat is bedieningstoestand
    en die woont buiten de engine. Is het moment van uitvallen onbekend, dan is
    er niets om op te wachten en gaat de overname meteen in.

    Unreachable is what the world calls unreachable (`ClimateState.available`):
    `unavailable`, `unknown`, or an entity that is not there. An appliance not
    taking its command does not count here - that is control state and lives
    outside the engine. If the moment of dropping out is unknown there is
    nothing to wait for and the takeover starts at once.
    """
    for zone, source in config.sources():
        if zone.zone_id not in zones or source.entity_id == entity_id:
            continue
        state = world.climate(source.entity_id)
        if state.available:
            continue
        if state.changed_at is None or world.now - state.changed_at >= delay:
            return True
    return False
