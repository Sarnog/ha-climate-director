"""Poorten: mag er in deze zone überhaupt geregeld worden.

Gates: may this zone be regulated at all.

Poorten kijken alleen naar omstandigheden, nooit naar temperaturen. Ze
beantwoorden "mag het", niet "moet het" - dat tweede is aan `hysteresis.py`.

Gates look only at circumstances, never at temperatures. They answer "is this
allowed", not "is this needed" - the latter belongs to `hysteresis.py`.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import datetime

from . import hand_start
from .families import MODE_OFF
from .models import (
    DirectorConfig,
    Opening,
    Zone,
    ZoneGate,
)
from .plan import OPENING_MIN_REST, Plan, Reason  # noqa: F401  # OPENING_MIN_REST is a re-export
from .quiet import guests_carry_the_house, zone_running
from .schedule import schedule_open
from .world import WorldState


def closed(
    config: DirectorConfig, world: WorldState, zone: Zone, previous: Plan | None = None
) -> tuple[Reason, ...]:
    """Return every gate standing shut for this zone, broadest first.

    Het oordeel noemt er één, en bij het regelen is dat genoeg: één dichte
    poort houdt de zone tegen, welke het ook is. Bij het inrichten is het juist
    lastig, want je zet er één open, kijkt weer, en vindt de volgende. Deze
    lijst geeft ze in één keer.

    Poorten die niet meer van toepassing zijn staan er niet bij. Loopt er een
    vooruit-verzoek, dan zeggen de poorten over mensen niets meer, en ze toch
    noemen zou een hindernis suggereren die er niet is.

    The verdict names one, and while regulating that is enough: one shut gate
    holds the zone back, whichever it is. While setting up it is awkward,
    because you open one, look again, and find the next. This list gives them
    all at once.

    Gates that no longer apply are left out. With a pre-conditioning request
    running the gates about people no longer say anything, and naming them
    would suggest an obstacle that is not there.
    """
    return tuple(_closed(config, world, zone, previous))


def _closed(
    config: DirectorConfig, world: WorldState, zone: Zone, previous: Plan | None
) -> Iterator[Reason]:
    """Yield the shut gates in order, stopping where the rest stops applying."""
    if not world.master_enabled:
        yield Reason.MASTER_DISABLED

    if world.overridden(zone.zone_id):
        yield Reason.MANUAL_OVERRIDE

    # Een openstaand raam weigert alles, behalve een vooruit-verzoek waarbij
    # iemand uitdrukkelijk heeft gezegd: toch doen. Dat blijft een bewuste daad
    # van een mens, geen instelling die blijft hangen - hij vervalt vanzelf met
    # de timer van het verzoek.
    #
    # An open window refuses everything, except a pre-conditioning request on
    # which somebody expressly said: do it anyway. That stays a deliberate
    # human act rather than a setting that lingers - it lapses with the
    # request's own timer.
    if _any_opening_open(config, world, zone) and not world.precondition_ignores_openings(
        zone.zone_id
    ):
        yield Reason.OPENING_OPEN

    # Vooruit verwarmen: iemand heeft dit met de hand gevraagd en er loopt een
    # teller. Dit is het enige dat een leeg huis mag laten draaien, dus het staat
    # ná het raam en de override en vóór alles wat over mensen gaat.
    #
    # Pre-conditioning: somebody asked for this by hand and a timer is running.
    # This is the only thing allowed to run an empty house, so it sits after the
    # window and the override, and before everything about people.
    if _preconditioning(world, zone):
        return

    # De stiltevensters remmen het beginnen, niet het doorgaan. Een zone die al
    # draait houdt zijn gewone regeling - inclusief uitgaan zodra iedereen naar
    # bed is. Zet iemand zelf iets aan, dan draait dat mee alsof het altijd al
    # liep. Zo blijft de rem een rem en wordt het geen tweede rooster.
    #
    # The quiet windows brake starting, not continuing. A zone already running
    # keeps its ordinary regulation - going off once everybody has turned in
    # included. Switch something on yourself and it runs along as though it had
    # been going all the while. That keeps the brake a brake rather than a second
    # schedule.
    if hand_start.quiet_holds(config, world, zone, previous):
        yield Reason.QUIET_HOURS

    # Een zone die op de kamer draait laat het huishouden erbuiten. Wie er zit,
    # zit er - dat is een beter antwoord dan welk rooster ook kan geven.
    #
    # A zone running on the room leaves the household out of it. Whoever is
    # sitting there is sitting there - a better answer than any schedule gives.
    if zone.gate is ZoneGate.PRESENCE:
        if not _room_occupied(world, zone):
            yield Reason.ZONE_UNOCCUPIED
        return

    # Een configuratie zonder bewoners beschrijft een pand waar niemand gevolgd
    # wordt - een kantoor, een vakantiehuis, een serverruimte. De poorten die
    # over bewoners gaan slaan we daar over, want die kunnen nooit slagen. De
    # kamerpoort hieronder blijft wél gelden: die gaat over de ruimte, niet over
    # wie er in het huis is.
    #
    # A configuration without residents describes a building nobody is tracked
    # in - an office, a holiday home, a server room. The gates about residents
    # are skipped there, since they could never pass. The room gate below still
    # applies: that one is about the room, not about who is in the house.
    if config.residents:
        yield from _household(
            config, world, zone.zone_id, zone_running(config, world, zone, previous)
        )

    # Het smalst van allemaal, en daarom als laatste: iemand thuis zegt niets
    # over of er iemand op zolder zit.
    #
    # The narrowest of the lot, and therefore last: somebody being home says
    # nothing about whether anybody is in the attic.
    if not _room_occupied(world, zone):
        yield Reason.ZONE_UNOCCUPIED


def _household(
    config: DirectorConfig, world: WorldState, zone_id: str, running: bool
) -> Iterator[Reason]:
    """Yield the gates about the people in the house, the shut ones only.

    Gastenmodus neemt de poorten over die over afwezigheid gaan. Er logeert
    iemand die niet gevolgd wordt, dus een leeg lijkend huis zegt niets en
    hoort niet uit te gaan. Slaap blijft wél tellen: zodra een bewoner thuis
    is en naar bed gaat, is de dag voorbij en is het huis weer van hen.

    Guest mode takes over the gates that are about absence. Somebody untracked
    is staying, so a house that looks empty says nothing and should not shut
    down. Sleep still counts: once a resident is home and turns in, the day is
    over and the house is theirs again.
    """
    gates = config.gates

    if guests_carry_the_house(config, world):
        # Afwezigheid en rooster zeggen niets meer, slaap wel: zodra iemand
        # thuis is en naar bed gaat, is het huis weer van de bewoners.
        #
        # Absence and schedule no longer say anything, sleep still does: the
        # moment somebody is home and turns in, the house is the residents'
        # again.
        at_home = [
            resident for resident in config.residents if world.resident(resident.resident_id).home
        ]
        if at_home and gates.require_awake:
            if not any(
                world.resident(resident.resident_id).present_and_awake for resident in at_home
            ):
                yield Reason.EVERYONE_ASLEEP
            elif hand_start.waits_for_sleeper(world, zone_id, at_home):
                yield Reason.WAITING_FOR_SLEEPER
        return

    # Een leeg huis maakt de twee poorten hieronder betekenisloos: niemand kan
    # wakker zijn of een rooster openen als er niemand is. Ze er toch bij
    # noemen zou de lijst laten zwellen met gevolgen in plaats van oorzaken.
    #
    # An empty house makes the two gates below meaningless: nobody can be awake
    # or open a schedule when nobody is there. Naming them anyway would swell
    # the list with consequences rather than causes.
    if not any(world.resident(resident.resident_id).home for resident in config.residents):
        yield Reason.NOBODY_HOME
        return

    # Eerst: is er überhaupt iemand op. Zo niet, dan is dát de reden, en de
    # uitslaper hieronder noemen zou een gevolg voor een oorzaak aanzien.
    # Staat er wél iemand op, dan telt wie nog ligt: het huis wacht op de
    # laatste slaper tot diens uiterste tijd, en daarna niet meer.
    #
    # First: is anybody up at all. If not, that is the reason, and naming the
    # late riser below would mistake a consequence for a cause. With somebody
    # up, whoever is still in bed counts: the house waits for the last sleeper
    # until their deadline, and no longer than that.
    #
    # Staat iedereen die op is te vroeg op (*Opstaan zet het huis pas aan vanaf*),
    # dan begint het huis niet: `early_riser`. Een rem op beginnen, zoals het
    # stiltevenster, dus een zone die al draait regelt gewoon door. Binnen het
    # gastenvenster geldt de rem niet: die tak hierboven kent haar niet.
    #
    # When everybody who is up got up too early (*Getting up only starts the house
    # from*), the house does not start: `early_riser`. A brake on starting, like the
    # quiet window, so a zone already running carries on regulating. Inside the guest
    # window the brake does not apply: the branch above does not know it.
    if gates.require_awake:
        up = [resident for resident in config.residents if hand_start.up_and_about(resident, world)]
        if not up:
            yield Reason.EVERYONE_ASLEEP
        elif hand_start.early_riser_holds(world, zone_id, running, up):
            yield Reason.EARLY_RISER
        elif hand_start.waits_for_sleeper(world, zone_id, config.residents):
            yield Reason.WAITING_FOR_SLEEPER

    if gates.require_schedule and not schedule_open(config, world):
        yield Reason.OUTSIDE_SCHEDULE


def _preconditioning(world: WorldState, zone: Zone) -> bool:
    """Return whether a live request is warming this zone up for somebody's return.

    Eén definitie van "er loopt een verzoek", en die staat in
    `WorldState.preconditioning()`: daar zit de klok van het verzoek zelf in.
    Een tweede definitie hier zou alleen maar uit elkaar kunnen lopen.

    One definition of "a request is running", and it lives in
    `WorldState.preconditioning()`: the request's own clock sits there. A
    second definition here could only drift apart.
    """
    return world.preconditioning(zone.zone_id)


def _room_occupied(world: WorldState, zone: Zone) -> bool:
    """Return whether this room counts as occupied right now.

    A zone without a presence entity is never held back on this: not measuring
    a room is not the same as knowing it is empty.
    """
    if not zone.presence_entity:
        return True

    state = world.presence_of(zone.zone_id)
    if state.occupied:
        return True
    if not zone.presence_timeout:
        return False

    # Zonder tijdstempel valt niet aan te tonen dat de kamer nog binnen de
    # nalooptijd valt, en dan telt hij als leeg. Een lege kamer met rust laten
    # is de onschadelijke kant om fout te zitten.
    #
    # Without a timestamp there is no showing the room is still inside the
    # grace period, so it counts as empty. Leaving an empty room alone is the
    # harmless side to be wrong on.
    if state.changed_at is None:
        return False
    return world.now - state.changed_at < zone.presence_timeout


def _any_opening_open(config: DirectorConfig, world: WorldState, zone: Zone) -> bool:
    """Return whether an opening has suspended this zone long enough."""
    return any(
        opening_standing(opening, world)
        for opening in config.openings
        if opening.affects(zone.zone_id)
    )


def _standing_open(opening: Opening, world: WorldState) -> bool:
    """Return whether this opening has stood open past its own delay."""
    state = world.opening(opening.entity_id)
    if not state.open:
        return False
    # An open sensor without a timestamp counts as open long enough:
    # suspending climate control is the harmless direction to be wrong in,
    # and refusing to act on an unknown age would keep heating an open room.
    if state.changed_at is None:
        return True
    return world.now - state.changed_at >= opening.delay


def opening_standing(opening: Opening, world: WorldState) -> bool:
    """Return whether this opening counts as standing open, delay included.

    Anker 8: een overbrugde opening bestaat niet voor de director. Hij telt
    nergens meer mee - niet voor het opschorten van zijn eigen zones, en niet
    voor de huisbrede stop. `opening_standing` is de publieke lezer voor de
    koppelingslaag: die noemt in de weigeringsmelding en in de events alleen de
    openingen die de zone écht tegenhouden, en daar hoort een overbrugde opening
    niet bij, net zo min als een raam binnen zijn vertraging.

    Anchor 8: a bypassed opening does not exist for the director. It counts
    nowhere any more - neither for suspending its own zones, nor for the
    house-wide stop. `opening_standing` is the public reader for the binding
    layer: the refusal notice and the events name only the openings really
    holding the zone back, and a bypassed opening does not belong there, just
    as a window inside its delay does not.
    """
    if opening.opening_id in world.opening_bypasses:
        return False
    return _standing_open(opening, world)


def opening_bypassed_and_open(opening: Opening, world: WorldState) -> bool:
    """Return whether this opening is bypassed while it really stands open.

    De kant van anker 8 die wél moet opvallen: staat de overbrugging aan
    terwijl de opening werkelijk openstaat, dan stookt de installatie met een
    raam open zonder dat de poort er iets aan doet. De koppelingslaag meldt
    dat, zodat het niet een hele winter stil blijft.

    The side of anchor 8 that must stand out: with the bypass on while the
    opening really stands open, the installation heats with a window open
    without the gate doing anything about it. The binding layer reports that,
    so it does not stay silent for a whole winter.
    """
    return opening.opening_id in world.opening_bypasses and _standing_open(opening, world)


def house_wide_blocked(config: DirectorConfig, world: WorldState) -> frozenset[str]:
    """Return the appliances that must stand still while any opening is open.

    Het `affects()`-filter ontbreekt hier met opzet: deze lijst bestaat juist
    voor het apparaat dat het hele huis bedient, en dan is het niet uit te
    leggen dat de voordeur wel telt en het slaapkamerraam niet. Elke opening in
    de installatie telt dus mee, met zijn eigen vertraging.

    Een lege lijst geeft een lege verzameling, en daarmee verandert er niets
    aan het gedrag van een installatie die deze instelling niet gebruikt.

    The `affects()` filter is deliberately absent: this list exists precisely
    for the appliance serving the whole house, and there is no explaining why
    the front door would count and the bedroom window would not. Every opening
    in the installation therefore counts, each with its own delay.

    An empty list yields an empty set, so nothing changes for an installation
    not using this setting.
    """
    if not config.house_wide_openings:
        return frozenset()
    if not any(opening_standing(opening, world) for opening in config.openings):
        return frozenset()
    return frozenset(config.house_wide_openings)


def opening_rest_until(
    config: DirectorConfig, world: WorldState, previous: Plan | None, entity_id: str
) -> datetime | None:
    """Return when an opening-stopped appliance without a circuit may start again.

    De kortcyclusbescherming van een circuit kijkt naar `last_changed` van het
    apparaat en de `min_cycle_time` van het circuit. Een apparaat zonder circuit
    - bij dit ontwerp per definitie de gasketel - mist dat vangnet op élk pad:
    de huisbrede stop kreeg het in H2, maar de gewone raampoort van zijn eigen
    zone niet. Dit leest daarom alleen de eindtijd die `_opening_rest_bookkeeping`
    bij de stop zelf heeft vastgelegd (`world.now + OPENING_MIN_REST`, anker 5:
    gerekend vanaf de stop). Een verlopen eindtijd geeft `None`; een apparaat dat
    al langer dan drie minuten stilstaat heeft gerust en start meteen.

    De boekhouding hangt aan het apparaat en niet aan de reden van het vorige
    commando: bij een gedeeld apparaat overleeft de reden van de zone met de
    meeste voorrang de collapse, en die is niet per se de opening.

    Alleen herstarts worden uitgesteld, nooit de stop zelf: de stop hangt aan de
    poorten, en die kennen deze rem niet.

    A circuit's short-cycle protection reads the appliance's `last_changed` and
    the circuit's `min_cycle_time`. An appliance without a circuit - by this
    design, the boiler - lacks that safety net on every path: the house-wide
    stop got it in H2, but the ordinary window gate of its own zone did not.
    This reads only the deadline that `_opening_rest_bookkeeping` recorded at
    the stop itself (`world.now + OPENING_MIN_REST`, anchor 5: counted from the
    stop). An expired deadline yields `None`; an appliance that has stood still
    for longer than three minutes has rested and starts at once.

    The bookkeeping hangs on the appliance and not on the previous command's
    reason: on a shared appliance the reason of the highest-priority zone
    survives the collapse, and that need not be the opening.

    Only restarts are delayed, never the stop itself: the stop hangs on the
    gates, which know nothing of this brake.
    """
    if previous is None:
        return None
    if any(entity_id in circuit.units for circuit in config.circuits):
        return None
    deadline = previous.opening_rest_until.get(entity_id)
    if deadline is None:
        return None
    return deadline if world.now < deadline else None


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
    return frozenset(closed(config, without, zone, previous)) & hand_start.HAND_START_BRAKES
