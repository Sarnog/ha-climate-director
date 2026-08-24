"""Poorten: mag er in deze zone überhaupt geregeld worden.

Gates: may this zone be regulated at all.

Poorten kijken alleen naar omstandigheden, nooit naar temperaturen. Ze
beantwoorden "mag het", niet "moet het" - dat tweede is aan `hysteresis.py`.

Gates look only at circumstances, never at temperatures. They answer "is this
allowed", not "is this needed" - the latter belongs to `hysteresis.py`.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta

from .families import ModeFamily
from .hysteresis import source_counts_for
from .models import HOLIDAY_WEEKDAY, DirectorConfig, Opening, Resident, Zone, ZoneGate
from .plan import Plan, Reason
from .world import WorldState

#: Hoe lang een door een opening stilgezet apparaat zonder circuit minstens stil
#: moet staan voordat het weer mag starten. Kortcyclusbescherming hangt aan een
#: circuit, en een gasketel hangt aan geen circuit - dus dit is de rem die dat
#: pad miste, eerst alleen voor de huisbrede stop en sinds P3 voor élke
#: openingsstop. De stop zelf wordt hier nooit mee uitgesteld, alleen de
#: herstart.
#:
#: How long an opening-stopped appliance without a circuit must at least stand
#: still before it may start again. Short-cycle protection hangs on a circuit,
#: and a boiler hangs on no circuit - so this is the brake that path was
#: missing, first only for the house-wide stop and since P3 for every opening
#: stop. This never delays the stop itself, only the restart.
OPENING_MIN_REST = timedelta(minutes=3)


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
    if _quiet_hours(config, world) and not _zone_running(config, world, zone, previous):
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
        yield from _household(config, world)

    # Het smalst van allemaal, en daarom als laatste: iemand thuis zegt niets
    # over of er iemand op zolder zit.
    #
    # The narrowest of the lot, and therefore last: somebody being home says
    # nothing about whether anybody is in the attic.
    if not _room_occupied(world, zone):
        yield Reason.ZONE_UNOCCUPIED


def _household(config: DirectorConfig, world: WorldState) -> Iterator[Reason]:
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

    if _guests_carry_the_house(config, world):
        # Afwezigheid en rooster zeggen niets meer, slaap wel: zodra iemand
        # thuis is en naar bed gaat, is het huis weer van de bewoners.
        #
        # Absence and schedule no longer say anything, sleep still does: the
        # moment somebody is home and turns in, the house is the residents'
        # again.
        at_home = [
            resident for resident in config.residents if world.resident(resident.resident_id).home
        ]
        if (
            at_home
            and gates.require_awake
            and not any(
                world.resident(resident.resident_id).present_and_awake for resident in at_home
            )
        ):
            yield Reason.EVERYONE_ASLEEP
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

    if gates.require_awake and not any(
        _up_and_about(resident, world) for resident in config.residents
    ):
        yield Reason.EVERYONE_ASLEEP

    if gates.require_schedule and not _schedule_open(config, world):
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


def asleep_at(resident: Resident, is_asleep: bool, now: datetime) -> bool:
    """Return whether this resident counts as asleep at `now`.

    De sensor zegt wat hij ziet; het venster zegt wanneer dat iets betekent.
    Buiten die uren is een oplader gewoon een oplader.

    The sensor says what it sees; the window says when that means anything.
    Outside those hours a charger is just a charger.
    """
    if not is_asleep:
        return False
    window = resident.sleep_window
    if window is None:
        return True
    return window.contains(now.time(), now.weekday())


def asleep(resident: Resident, world: WorldState) -> bool:
    """Return whether this resident counts as asleep right now."""
    return asleep_at(resident, world.resident(resident.resident_id).asleep, world.now)


def _up_and_about(resident: Resident, world: WorldState) -> bool:
    """Return whether this resident is home and not asleep."""
    return world.resident(resident.resident_id).home and not asleep(resident, world)


def _guests_carry_the_house(config: DirectorConfig, world: WorldState) -> bool:
    """Return whether guest mode is standing in for the residents right now.

    Alleen overdag, of preciezer: binnen het ingestelde gastenvenster. Buiten
    dat venster nemen de gewone poorten het weer over, zodat een schakelaar die
    iemand vergeet uit te zetten het huis niet de hele nacht laat doordraaien.

    Only during the day, or more precisely: inside the configured guest window.
    Outside it the ordinary gates take over again, so a switch somebody forgets
    to turn off does not keep the house running all night.
    """
    if not world.guest_mode:
        return False
    window = config.gates.guest_window
    if window is None:
        return True
    return window.contains(world.now.time(), world.now.weekday())


def _quiet_hours(config: DirectorConfig, world: WorldState) -> bool:
    """Return whether this moment falls inside a quiet window.

    Een open roostervenster wint. De stilte is bedoeld voor thuiskomen op een
    uur waarop je zo naar bed gaat, niet voor opstaan - en wie om vijf uur
    's ochtends begint, heeft dat in zijn rooster gezet juist omdat het vroeg
    is. Zonder deze uitzondering zou de stilte het ochtendritme afknijpen dat
    het rooster net beschrijft.

    An open schedule window wins. The quiet is meant for coming home at an hour
    when you are about to turn in, not for getting up - and whoever starts at
    five in the morning put that in their schedule precisely because it is
    early. Without this exception the quiet would pinch off the very morning
    rhythm the schedule describes.

    Alleen het venster van wie thuis is telt: het rooster van iemand die weg is
    hoeft het huis niet te laten beginnen.

    Only the window of somebody who is home counts: the schedule of somebody who
    is out need not set the house going.

    Een vakantievenster geldt alleen op vakantiedagen, en dan elke dag van de
    week. Zijn er vakantievensters, dan nemen die het op een vakantie over van
    de gewone; zijn die er niet, dan telt een vakantie als zaterdag - precies
    zoals de bewonersroosters dat doen.

    A holiday window applies only on holidays, and then on any weekday. With
    holiday windows set they take over from the ordinary ones on a holiday;
    without them a holiday counts as a Saturday - exactly like the residents'
    schedules do.
    """
    moment = world.now.time()
    weekday = world.now.weekday()
    holiday = world.holiday_mode
    effective = HOLIDAY_WEEKDAY if holiday else weekday
    holiday_windows = [window for window in config.gates.quiet_windows if window.holiday]
    if holiday and holiday_windows:
        in_window = any(
            window.contains(moment, weekday, any_day=True) for window in holiday_windows
        )
    else:
        in_window = any(
            window.contains(moment, effective)
            for window in config.gates.quiet_windows
            if not window.holiday
        )
    if not in_window:
        return False

    return not any(
        world.resident(resident.resident_id).home
        and resident.takes_part(holiday=holiday, weekday=effective)
        and resident.wants_climate_at(moment, weekday, holiday=holiday)
        for resident in config.residents
    )


def _zone_running(
    config: DirectorConfig, world: WorldState, zone: Zone, previous: Plan | None
) -> bool:
    """Return whether any appliance that counts for this zone is doing something.

    Een gedeeld apparaat telt alleen voor de zone die het vorige plan een
    draaicommando gaf, zodat een ketel die voor een andere kamer brandt dit
    stiltevenster niet opheft. Kreeg niemand zo'n commando - na een herstart,
    of omdat iemand hem met de hand aanzette - dan draait hij voor het hele huis
    en heft hij het stiltevenster wél op.

    A shared appliance counts only for the zone that got a running command in
    the previous plan, so a boiler burning for another room does not lift this
    quiet window. With no such command - after a restart, or because somebody
    switched it on by hand - it runs for the whole house and does lift it.
    """
    return any(
        source_counts_for(config, zone, source, previous)
        and world.climate(source.entity_id).family is not ModeFamily.NEUTRAL
        for source in zone.sources
    )


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
        _standing_open(opening, world)
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
    if not any(_standing_open(opening, world) for opening in config.openings):
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
    zone niet. Dit leest daarom de boekhouding van het vorige plan: stond het
    apparaat daarop in `stopped_by_opening`, dan is de stop net voorbij en
    begint de rusttijd nu te lopen; liep er al een rusttijd, dan geldt de
    meegedragen eindtijd uit `opening_rest_until` verder.

    De boekhouding hangt aan het apparaat en niet aan de reden van het vorige
    commando: bij een gedeeld apparaat overleeft de reden van de zone met de
    meeste voorrang de collapse, en die is niet per se de opening.

    Alleen herstarts worden uitgesteld, nooit de stop zelf: de stop hangt aan de
    poorten, en die kennen deze rem niet.

    A circuit's short-cycle protection reads the appliance's `last_changed` and
    the circuit's `min_cycle_time`. An appliance without a circuit - by this
    design, the boiler - lacks that safety net on every path: the house-wide
    stop got it in H2, but the ordinary window gate of its own zone did not.
    This reads the previous plan's bookkeeping instead: if the appliance stood
    in `stopped_by_opening` there, the stop has just ended and the rest starts
    now; if a rest was already running, the carried deadline from
    `opening_rest_until` keeps applying.

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
    if deadline is not None:
        return deadline if world.now < deadline else None
    if entity_id in previous.stopped_by_opening:
        return world.now + OPENING_MIN_REST
    return None


def _schedule_open(config: DirectorConfig, world: WorldState) -> bool:
    """Return whether the household's schedules allow regulating right now.

    Only residents who actually have a schedule take part. Someone without one
    neither opens the gate nor holds it shut: they have said nothing about when
    they want the house to join in, and silence is not a vote either way.

    A participant does two things. Awake, with their window open, they open the
    gate. At home and asleep, with their window not yet open, they hold it shut
    - which is what makes the house wait for the last sleeper on a weekend
    morning instead of starting the moment the first person is up. Once their
    own window opens, their sleeping stops counting: the schedule said they
    meant to be up by then.
    """
    moment = world.now.time()
    weekday = world.now.weekday()
    holiday = world.holiday_mode

    effective = HOLIDAY_WEEKDAY if holiday else weekday
    participants = [
        resident
        for resident in config.residents
        if resident.takes_part(holiday=holiday, weekday=effective)
    ]
    if not participants:
        return False

    for resident in participants:
        state = world.resident(resident.resident_id)
        if (
            state.home
            and asleep(resident, world)
            and not resident.wants_climate_at(moment, weekday, holiday=holiday)
        ):
            return False

    return any(
        resident.wants_climate_at(moment, weekday, holiday=holiday)
        for resident in participants
        if _counts_towards_schedule(config, world, resident.resident_id)
    )


def _counts_towards_schedule(config: DirectorConfig, world: WorldState, resident_id: str) -> bool:
    """Return whether a resident's own schedule may open the schedule gate.

    Being home is required outright: a schedule says when somebody wants the
    house warm, not that it should be warm without them. Sleep mirrors the
    sleep gate instead of being hard-coded, so with `require_awake` off a
    schedule still counts while its owner sleeps.
    """
    resident = next((item for item in config.residents if item.resident_id == resident_id), None)
    if resident is None or not world.resident(resident_id).home:
        return False
    return not (config.gates.require_awake and asleep(resident, world))
