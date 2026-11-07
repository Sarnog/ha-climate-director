"""De drie remmen die een handstart passeert, en wanneer hij nog nodig is.

The three brakes a hand start passes, and when it is still needed.

Een handstart is geen hand (anker 11): een hand zet een apparaat uit, een
handstart zet er een aan. De zone passeert daarom alleen de remmen die over
wachten gaan - `WAITING_FOR_SLEEPER`, `EARLY_RISER` en `QUIET_HOURS` - en
verder niets. Deze module bezit die regel; `gates.py` vraagt haar alleen.

A hand start is not a hand (anchor 11): a hand switches an appliance off, a hand
start switches one on. The zone therefore passes only the brakes about waiting -
`WAITING_FOR_SLEEPER`, `EARLY_RISER` and `QUIET_HOURS` - and nothing else. This
module owns that rule; `gates.py` merely asks it.
"""

from __future__ import annotations

from collections.abc import Iterable

from .models import DirectorConfig, Resident, Zone
from .night import asleep, rise_braked, slept_tonight
from .plan import Plan, Reason
from .quiet import quiet_hours, zone_running
from .world import ReadableInput, UnreadableInput, WorldState

#: De enige drie poorten die een handstart opzij zet.
#:
#: The only three gates a hand start sets aside.
HAND_START_BRAKES = frozenset(
    {
        Reason.WAITING_FOR_SLEEPER,
        Reason.EARLY_RISER,
        Reason.QUIET_HOURS,
    }
)


def brakes_readable(config: DirectorConfig, world: WorldState) -> bool:
    """Return whether every input feeding the three brakes gave a reading.

    Een handstart vervalt niet op grond van een ronde waarin een van de drie
    remmen zijn invoer niet kan lezen. De koppelingslaag levert één verzameling
    onleesbare invoeren; hier wordt alleen gekeken naar de invoeren die deze
    installatie werkelijk gebruikt. Een ontbrekende bewoner in de wereld telt
    als onleesbaar zodra een van zijn twee sensoren de remmen voedt. De
    feestdagenagenda telt alleen mee als er een trefwoord en minstens één
    agenda is ingesteld; zonder die twee voedt zij de remmen niet.

    A hand start does not lapse on the strength of a round in which one of the
    three brakes cannot read its input. The binding layer supplies one
    collection of unreadable inputs; only the inputs this installation actually
    uses are checked. A resident missing from the world counts as unreadable as
    soon as either of their sensors feeds the brakes. The holiday calendars
    count only when a keyword and at least one calendar are configured; without
    those two they do not feed the brakes.
    """
    for resident in config.residents:
        state = world.residents.get(resident.resident_id)
        presence_missing = UnreadableInput(ReadableInput.PRESENCE, resident.resident_id)
        if resident.presence_entity and (state is None or presence_missing in world.unreadable):
            return False
        sleep_missing = UnreadableInput(ReadableInput.SLEEP, resident.resident_id)
        if resident.sleep_entity and (state is None or sleep_missing in world.unreadable):
            return False
    if config.holiday_keyword.strip() and any(config.holiday_calendars):
        return UnreadableInput(ReadableInput.HOLIDAY) not in world.unreadable
    return True


def passes(world: WorldState, zone_id: str, reason: Reason) -> bool:
    """Return whether this zone's hand start lets `reason` through.

    Alleen een van de drie wachtredenen, en alleen met een handstart voor deze
    zone. Elke andere poort - de hoofdschakelaar, een opening, de kamerpoort -
    gaat hier dus nooit langs.

    Only one of the three waiting reasons, and only with a hand start for this
    zone. Every other gate - the master switch, an opening, the room gate -
    therefore never passes here.
    """
    return zone_id in world.zone_hand_starts and reason in HAND_START_BRAKES


def quiet_holds(
    config: DirectorConfig, world: WorldState, zone: Zone, previous: Plan | None
) -> bool:
    """Return whether the quiet window still holds this zone, hand start aside.

    Dezelfde poort als `_closed`, met de handstartregel erin: wat al draait
    houdt zijn gewone regeling, en een handstart zet dit ene venster opzij. De
    private lezers komen lui uit `gates`, want die module importeert deze.

    The same gate as `_closed`, with the hand-start rule inside: whatever runs
    keeps its ordinary regulation, and a hand start sets this one window aside.
    The private readers come lazily from `gates`, since that module imports this
    one.
    """
    return (
        not passes(world, zone.zone_id, Reason.QUIET_HOURS)
        and quiet_hours(config, world)
        and not zone_running(config, world, zone, previous)
    )


def early_riser_holds(
    world: WorldState, zone_id: str, running: bool, up: Iterable[Resident]
) -> bool:
    """Return whether the rise brake holds these residents, hand start aside."""
    return (
        not passes(world, zone_id, Reason.EARLY_RISER)
        and not running
        and all(rise_braked(resident, world) for resident in up)
    )


def waits_for_sleeper(world: WorldState, zone_id: str, residents: Iterable[Resident]) -> bool:
    """Return whether a sleeper still holds this zone, hand start aside."""
    return not passes(world, zone_id, Reason.WAITING_FOR_SLEEPER) and any(
        still_in_bed(resident, world) for resident in residents
    )


def up_and_about(resident: Resident, world: WorldState) -> bool:
    """Return whether this resident is home and not asleep."""
    return world.resident(resident.resident_id).home and not asleep(resident, world)


def still_in_bed(resident: Resident, world: WorldState) -> bool:
    """Return whether this sleeper still holds the house back.

    Drie dingen moeten tegelijk waar zijn: thuis, slapend, en vóór de uiterste
    tijd van vandaag. Wie geen uiterste tijd heeft ingevuld houdt nooit iemand
    tegen - dat is de stand van vóór deze instelling, en die blijft voor elke
    installatie die er niets mee doet precies zo.

    Wie weg is telt niet mee: slapen bij iemand anders is geen reden om dit
    huis koud te laten. Dat is dezelfde regel als bij de hand aan het apparaat.

    Three things must hold at once: home, asleep, and before today's deadline.
    Whoever filled in no deadline never holds anybody back - that is the state
    from before this setting, and it stays exactly that for every installation
    not using it.

    Somebody away does not count: sleeping at somebody else's place is no
    reason to leave this house cold. That is the same rule as for the hand at
    the appliance.

    En het huis moet deze nacht geslapen hebben: iedereen die thuis is, is naar
    bed geweest (`night.slept_tonight`). Gaat de één naar bed terwijl de ander nog
    op is, dan is het na middernacht al "vandaag, vóór de uiterste tijd", maar wie
    op is houdt het huis gewoon aan de gang. Is het moment onbekend - na een
    herstart terwijl iemand op was - dan wordt er niet gewacht.

    And the house must have slept this night: everybody at home has been to bed
    (`night.slept_tonight`). When one resident turns in while the other is still
    up, it is already "today, before the deadline" after midnight, but whoever is
    up simply keeps the house going. When the moment is unknown - after a restart
    while somebody was up - nobody is waited for.
    """
    if not world.resident(resident.resident_id).home or not asleep(resident, world):
        return False
    if not slept_tonight(resident, world):
        return False
    until = resident.waits_until(world.now.weekday(), holiday=world.holiday_mode)
    return until is not None and world.now.time() < until
