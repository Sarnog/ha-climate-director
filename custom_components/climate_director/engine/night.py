"""De nacht van het huis: wanneer is iedereen die thuis is gaan slapen.

The house's night: when did everybody at home go to sleep.

*Wacht op deze slaper* houdt het huis 's ochtends tegen tot de laatste slaper wakker
is. Dat wachten hoort bij de ochtend, niet bij de avond ervoor: gaat de één om
elf uur naar bed terwijl de ander nog op is, dan is het na middernacht al "vandaag,
vóór de uiterste tijd", maar de nacht is voor het huis nog niet begonnen. Pas als
iedereen die thuis is slaapt, begint de nacht; wie daarna opstaat, staat op. Het moment
waarop de nacht begon blijft daarna staan tot het buiten de lopende nacht valt: wie
's ochtends alleen opstaat, maakt de nacht waarin het huis sliep niet ongedaan.

Dit bestand beantwoordt twee vragen. Wanneer begon de lopende nacht van een
bewoner - de laatste start van zijn slaapvenster. En valt het moment waarop het
huis ging slapen (`WorldState.asleep_since`, door de koppelingslaag bijgehouden en
bewaard over een herstart) in die nacht. Een moment van de nacht ervoor telt niet
mee; een onbekend moment ook niet, en dan wordt er niet gewacht: wie op is houdt
het huis aan de gang.

*Wait for this sleeper* holds the house back in the morning until the last sleeper
is awake. That waiting belongs to the morning, not to the evening before: when one
resident turns in at eleven while the other is still up, it is already "today,
before the deadline" after midnight, but the house's night has not begun yet. The
night begins only once everybody at home is asleep; whoever gets up after that is
getting up. The moment the night began stays after that until it falls outside the
running night: whoever gets up alone in the morning does not undo the night in which
the house slept.

This file answers two questions. When did a resident's current night begin - the
latest start of their sleep window. And does the moment the house went to sleep
(`WorldState.asleep_since`, kept by the binding layer and stored across a restart)
fall inside that night. A moment from the night before does not count; an unknown
moment does not either, and then nobody is waited for: whoever is up keeps the house
going.

Hier staat ook wie als slapend telt (`asleep_at`, `asleep`) en het bijhouden van het
moment zelf (`house_asleep_since`), zodat alles over de slaap van het huis op één
plek woont; `gates.py` leest het. Also here: who counts as asleep (`asleep_at`,
`asleep`) and keeping the moment itself (`house_asleep_since`), so everything about
the house's sleep lives in one place; `gates.py` reads it.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .models import DirectorConfig, Resident
from .world import WorldState


def asleep_at(resident: Resident, is_asleep: bool, now: datetime, *, holiday: bool = False) -> bool:
    """Return whether this resident counts as asleep at `now`.

    De sensor zegt wat hij ziet; het venster zegt wanneer dat iets betekent.
    Buiten die uren is een oplader gewoon een oplader. Op een ochtend waarop
    uitslapen mag, loopt dat venster door tot de tijd die de bewoner daarvoor
    heeft opgegeven - zie `Resident.sleep_in`, en zie waarom dat niet gewoon een
    langer slaapvenster is.

    The sensor says what it sees; the window says when that means anything.
    Outside those hours a charger is just a charger. On a morning that allows
    sleeping in, that window runs on until the time the resident gave for it -
    see `Resident.sleep_in`, and why that is not simply a longer sleep window.
    """
    if not is_asleep:
        return False
    window = resident.sleep_window
    if window is None:
        return True
    if window.contains(now.time(), now.weekday()):
        return True
    return resident.sleeps_in_at(now.time(), now.weekday(), holiday=holiday)


def asleep(resident: Resident, world: WorldState) -> bool:
    """Return whether this resident counts as asleep right now."""
    return asleep_at(
        resident,
        world.resident(resident.resident_id).asleep,
        world.now,
        holiday=world.holiday_mode,
    )


def night_began(resident: Resident, now: datetime) -> datetime | None:
    """Return when this resident's current night began, or `None` without a sleep window.

    De laatste start van het slaapvenster op of vóór `now`, op een dag waarop dat
    venster geldt. Om 07:00 op zaterdag, met een venster van 21:00 tot 08:00, is dat
    vrijdag 21:00; met *Uitslapen tot* 13:00 om 12:00 nog steeds. Zonder slaapvenster
    telt de slaapsensor de klok rond en is er geen begin om aan af te lezen.

    The latest start of the sleep window at or before `now`, on a day that window
    applies to. At 07:00 on Saturday, with a window from 21:00 to 08:00, that is
    Friday 21:00; with *Sleeping in until* 13:00, at 12:00 still. Without a sleep
    window the sleep sensor counts around the clock and there is no beginning to read.
    """
    window = resident.sleep_window
    if window is None:
        return None
    starts = (
        datetime.combine(now.date() - timedelta(days=back), window.start, tzinfo=now.tzinfo)
        for back in range(8)
    )
    return next(
        (
            start
            for start in starts
            if start <= now and (window.weekdays is None or start.weekday() in window.weekdays)
        ),
        None,
    )


def slept_tonight(resident: Resident, world: WorldState) -> bool:
    """Return whether the house went to sleep during this resident's current night.

    Zonder bekend moment is het antwoord nee. Zonder slaapvenster telt elk bekend
    moment: de koppelingslaag vergeet het zodra er niemand thuis meer slaapt, en dat
    is dan de grens tussen twee nachten.

    Without a known moment the answer is no. Without a sleep window any known moment
    counts: the binding layer forgets it as soon as nobody at home sleeps any more,
    and that is then the border between two nights.
    """
    since = world.asleep_since
    if since is None:
        return False
    began = night_began(resident, world.now)
    return began is None or since >= began


def _night_runs_for_somebody(at_home: list[Resident], world: WorldState) -> bool:
    """Return whether the moment still falls inside somebody's running night.

    Alleen een bewoner **mét** slaapvenster heeft een nacht om aan af te lezen: voor wie
    zonder venster thuis is telt de slaapsensor de klok rond en is er geen grens waar het
    moment in moet vallen (`slept_tonight` zegt daar ja bij elk bekend moment). Een huis
    waar niemand een slaapvenster heeft houdt het moment dus niet vast - de grens tussen
    twee nachten is daar het moment zelf, en dat vervalt zodra er niemand thuis meer
    slaapt. De opsta-rem leest daar niet aan: zonder venster eist die geen nacht
    (`rise_braked`).

    Only a resident **with** a sleep window has a night to read: for whoever is home
    without one the sleep sensor counts around the clock and there is no boundary the
    moment has to fall inside (`slept_tonight` says yes at any known moment there). A house
    in which nobody has a sleep window therefore does not hold the moment - the boundary
    between two nights is the moment itself there, and it lapses the moment nobody at home
    is asleep any more. The rise brake does not read it there: without a window it demands
    no night (`rise_braked`).
    """
    return any(
        resident.sleep_window is not None and slept_tonight(resident, world) for resident in at_home
    )


def house_asleep_since(config: DirectorConfig, world: WorldState) -> datetime | None:
    """Return when everybody at home went to sleep, carrying `world.asleep_since` on.

    De koppelingslaag roept dit elke ronde aan en bewaart de uitkomst voor de volgende.
    Drie gevallen. Slaapt er niemand die thuis is, dan blijft het moment staan zolang het
    nog in de lopende nacht van iemand valt: wie om half zes opstaat maakt de nacht niet
    ongedaan, en wie 's avonds laat nog op is houdt het moment niet vast. Valt het
    erbuiten, dan is de nacht voorbij (of nog niet begonnen) en is het moment weg. Is er
    nog iemand thuis op terwijl een ander slaapt, dan blijft staan wat er stond. Slaapt
    iedereen die thuis is, dan blijft een moment uit deze nacht staan, en anders is het
    nu: het huis gaat op dit moment slapen.

    The binding layer calls this every round and keeps the outcome for the next. Three
    cases. When nobody at home is asleep, the moment stays as long as it still falls
    inside somebody's running night: whoever gets up at half past five does not undo the
    night, and whoever is still up late in the evening does not hold the moment. When it
    falls outside, the night is over (or has not begun) and the moment goes. When somebody
    at home is still up while another sleeps, whatever stood stays. When everybody at home
    is asleep, a moment from this night stays, and otherwise it is now: the house goes to
    sleep at this moment.
    """
    at_home = [
        resident for resident in config.residents if world.resident(resident.resident_id).home
    ]
    sleeping = [resident for resident in at_home if asleep(resident, world)]
    if not sleeping:
        return world.asleep_since if _night_runs_for_somebody(at_home, world) else None
    if len(sleeping) < len(at_home):
        return world.asleep_since
    if all(slept_tonight(resident, world) for resident in sleeping):
        return world.asleep_since
    return world.now


def rise_braked(resident: Resident, world: WorldState) -> bool:
    """Return whether this resident, getting up early, does not count as up yet.

    *Opstaan zet het huis pas aan vanaf*: vóór die tijd, op de dagen van de rem en op
    een dag die geen vakantie is, telt deze bewoner niet als "op". Een bewoner **met**
    een slaapvenster wordt alleen geremd als hij **opstaat** - na een nacht waarin het
    huis sliep (`slept_tonight`) -: wie 's avonds laat nog op is, is geen vroege
    opstaander, en een onbekend moment remt niemand. Zonder slaapvenster is er geen
    nacht om aan af te lezen: de slaapsensor telt de klok rond, dus wie op is, staat op,
    ook als het moment van het huis onbekend is. Of er daarna nog iets draait, beslist
    de poort: dit is een rem op beginnen, niet op doorgaan.

    *Getting up only starts the house from*: before that time, on the brake's days
    and on a day that is no holiday, this resident does not count as "up". A resident
    **with** a sleep window is only braked when he **gets up** - after a night the
    house slept (`slept_tonight`): whoever is still up late in the evening is no early
    riser, and an unknown moment brakes nobody. Without a sleep window there is no
    night to read: the sleep sensor counts around the clock, so whoever is up has got
    up, even when the house's moment is unknown. Whether anything runs already is up to
    the gate: this is a brake on starting, not on continuing.
    """
    brake = resident.rise_brake
    if brake is None or world.holiday_mode or not brake.applies_on(world.now.weekday()):
        return False
    if world.now.time() >= brake.at:
        return False
    return resident.sleep_window is None or slept_tonight(resident, world)
