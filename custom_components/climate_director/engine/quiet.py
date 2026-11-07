"""Het stiltevenster en de draaiende zone.

The quiet window and the running zone.
"""

from __future__ import annotations

from datetime import datetime

from .families import ModeFamily
from .hysteresis import source_counts_for
from .models import HOLIDAY_WEEKDAY, DirectorConfig, TimeWindow, Zone
from .plan import Plan
from .world import WorldState


def guests_carry_the_house(config: DirectorConfig, world: WorldState) -> bool:
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


def quiet_hours(config: DirectorConfig, world: WorldState) -> bool:
    """Return whether this moment falls inside a quiet window that still brakes.

    Drie uitzonderingen, in deze volgorde, en alle drie op hetzelfde venster:
    gastenmodus binnen het gastenvenster heft de stilte op (er logeert iemand, dus
    "het huis is leeg" zegt niets); een bewoner die al thuis was vóórdat dit
    venster begon regelt gewoon door (anker 13 - de rem is voor thuiskomers); en
    een open roostervenster van iemand die thuis is wint.

    Die laatste is de oudste: de stilte is bedoeld voor thuiskomen op een uur
    waarop je zo naar bed gaat, niet voor opstaan - en wie om vijf uur 's ochtends
    begint, heeft dat in zijn rooster gezet juist omdat het vroeg is. Zonder die
    uitzondering zou de stilte het ochtendritme afknijpen dat het rooster net
    beschrijft. Alleen het venster van wie thuis is telt: het rooster van iemand
    die weg is hoeft het huis niet te laten beginnen.

    Anker 13 maakt dit smaller: een venster remt alleen wie er ná zijn begin
    thuiskwam, dus wie er al zat houdt het huis aan de gang. Staat er geen
    thuiskomstmoment bekend, dan remt het venster wél - stilte is de veilige kant.
    Bij meerdere vensters tegelijk moet **elk** open venster zo iemand aanwijzen;
    dat is de strengste lezing van de vraag "was hij vóór het begin van elk open
    venster thuis", en voor de gewone, niet-overlappende vensters maakt het geen
    verschil.

    Een vakantievenster geldt alleen op vakantiedagen, en dan elke dag van de
    week. Zijn er vakantievensters, dan nemen die het op een vakantie over van de
    gewone; zijn die er niet, dan telt een vakantie als zaterdag - precies zoals de
    bewonersroosters dat doen.

    Three exceptions, in this order, and all three about the same window: guest
    mode inside the guest window lifts the quiet (somebody untracked is staying, so
    "the house is empty" says nothing); a resident who was already home before this
    window began simply carries on regulating (anchor 13 - the brake is for
    homecomers); and an open schedule window of somebody who is home wins.

    The last is the oldest: the quiet is meant for coming home at an hour when you
    are about to turn in, not for getting up - and whoever starts at five in the
    morning put that in their schedule precisely because it is early. Without that
    exception the quiet would pinch off the very morning rhythm the schedule
    describes. Only the window of somebody who is home counts: the schedule of
    somebody who is out need not set the house going.

    Anchor 13 makes this narrower: a window brakes only whoever came home after it
    began, so whoever was already sitting there keeps the house going. With no
    known homecoming moment the window does brake - quiet is the safe side. With
    several windows open at once **every** open window has to point at such a
    resident; that is the strictest reading of the question "was he home before the
    beginning of every open window", and for the ordinary, non-overlapping windows
    it makes no difference.

    A holiday window applies only on holidays, and then on any weekday. With
    holiday windows set they take over from the ordinary ones on a holiday; without
    them a holiday counts as a Saturday - exactly like the residents' schedules do.
    """
    open_windows = open_quiet_windows(config, world)
    if not open_windows:
        return False

    if guests_carry_the_house(config, world):
        return False

    if all(was_home_before(config, world, started) for _window, started in open_windows):
        return False

    moment = world.now.time()
    weekday = world.now.weekday()
    holiday = world.holiday_mode
    effective = HOLIDAY_WEEKDAY if holiday else weekday
    return not any(
        world.resident(resident.resident_id).home
        and resident.takes_part(holiday=holiday, weekday=effective)
        and resident.wants_climate_at(moment, weekday, holiday=holiday)
        for resident in config.residents
    )


def open_quiet_windows(
    config: DirectorConfig, world: WorldState
) -> tuple[tuple[TimeWindow, datetime], ...]:
    """Return the quiet windows standing open right now, with their beginning.

    Precies dezelfde keuze als buiten een vakantie: op een vakantie met eigen
    vakantievensters tellen alleen die, en dan op elke dag; anders de gewone
    vensters met de vakantiedag als zaterdag. Eén functie, omdat de lezer hierboven
    en de uitzondering van anker 13 hetzelfde venster moeten zien - en de begintijd
    komt uit datzelfde venster, zodat "staat open" en "begon om" niet uit elkaar
    kunnen lopen.

    Exactly the same choice as outside a holiday: on a holiday with holiday windows
    of its own only those count, and then on any day; otherwise the ordinary
    windows with the holiday counted as a Saturday. One function, because the
    reader above and anchor 13's exception must see the same window - and the
    beginning comes from that same window, so "stands open" and "began at" cannot
    drift apart.
    """
    weekday = world.now.weekday()
    holiday_windows = tuple(window for window in config.gates.quiet_windows if window.holiday)
    if world.holiday_mode and holiday_windows:
        candidates = ((window, weekday, True) for window in holiday_windows)
    else:
        effective = HOLIDAY_WEEKDAY if world.holiday_mode else weekday
        candidates = (
            (window, effective, False)
            for window in config.gates.quiet_windows
            if not window.holiday
        )
    return tuple(
        (window, started)
        for window, day, any_day in candidates
        if (started := window.started_at(world.now, weekday=day, any_day=any_day)) is not None
    )


def was_home_before(config: DirectorConfig, world: WorldState, window_start: datetime) -> bool:
    """Return whether somebody who is home was already home before this window began.

    Anker 13: wie al thuis was toen het venster inging, zit er wakker bij en houdt
    het huis aan de gang. Alleen een bewoner die thuis **is** telt mee: wie weg is
    is geen thuiskomer en ook geen aanwezige, en zijn moment is bij het vertrek al
    vervallen. Zonder bekend thuiskomstmoment is het antwoord `nee` - dan remt het
    venster, want stilte is de veilige kant om fout te zitten.

    Anchor 13: whoever was already home when the window began is sitting there
    awake and keeps the house going. Only a resident who **is** home counts:
    somebody away is neither a homecomer nor present, and their moment already
    lapsed on leaving. Without a known homecoming moment the answer is `no` - then
    the window brakes, since quiet is the safe side to be wrong on.
    """
    return any(
        state.home and state.home_since is not None and state.home_since < window_start
        for state in (world.resident(resident.resident_id) for resident in config.residents)
    )


def zone_running(
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
