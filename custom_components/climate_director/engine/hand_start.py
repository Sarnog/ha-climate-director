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
from dataclasses import replace

from .families import MODE_OFF
from .models import DirectorConfig, Resident, Zone
from .night import asleep, slept_tonight
from .plan import Plan, Reason
from .world import WorldState

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


def brakes_remaining(
    config: DirectorConfig, world: WorldState, zone: Zone, previous: Plan | None
) -> frozenset[Reason]:
    """Return the three brakes that still hold this zone without its hand start.

    De wereld wordt voor deze ene zone van haar handstart ontdaan en opnieuw
    door de poorten gehaald. Haar eigen apparaten tellen daarbij als uit: een
    zone die al draait passeert het stiltevenster en de opsta-rem, maar dat is
    juist de zone die na de eerste stop weer moet kunnen starten. Wat daarvan
    overblijft is precies de vraag of de handstart nog iets doet: is de
    verzameling leeg, dan vervalt hij in deze ronde. De andere poorten tellen
    hier bewust niet mee - een open raam houdt de zone tegen, maar maakt de
    handstart niet overbodig.

    The world is stripped of this one zone's hand start and put through the
    gates again. Its own appliances count as off there: a zone already running
    passes the quiet window and the rise brake, but that is exactly the zone
    that must be able to start again after the first stop. What remains is
    exactly the question whether the hand start still does anything: when the
    set is empty it lapses this round. The other gates deliberately do not count
    here - an open window holds the zone back, but does not make the hand start
    superfluous.
    """
    # Lazy, want `gates` importeert deze module voor `passes` en de twee
    # slaaphulpen. Een import bovenaan zou een kring maken.
    #
    # Lazy, since `gates` imports this module for `passes` and the two sleep
    # helpers. An import at the top would make a cycle.
    from .gates import closed

    climates = dict(world.climates)
    for source in zone.sources:
        state = climates.get(source.entity_id)
        if state is not None:
            climates[source.entity_id] = replace(state, hvac_mode=MODE_OFF)
    without = replace(
        world,
        climates=climates,
        zone_hand_starts=world.zone_hand_starts - {zone.zone_id},
    )
    return frozenset(closed(config, without, zone, previous)) & HAND_START_BRAKES


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
    from .gates import _quiet_hours, _zone_running

    return (
        not passes(world, zone.zone_id, Reason.QUIET_HOURS)
        and _quiet_hours(config, world)
        and not _zone_running(config, world, zone, previous)
    )


def early_riser_holds(
    world: WorldState, zone_id: str, running: bool, up: Iterable[Resident]
) -> bool:
    """Return whether the rise brake holds these residents, hand start aside."""
    from .night import rise_braked

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
