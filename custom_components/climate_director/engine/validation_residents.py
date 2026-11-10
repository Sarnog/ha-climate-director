"""De controles op bewoners.

The checks on residents.

De bewoner zonder aanwezigheid, de slaapinstellingen en het stiltevenster.

The resident without presence, the sleep settings and the quiet window.
"""

from __future__ import annotations

from collections.abc import Iterator

from .models import QUIET_ROOM_MINUTES, DirectorConfig, TimeWindow
from .problem import Problem


def rule_resident_without_presence(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for every resident who can never be home.

    Een bewoner zonder aanwezigheidsentiteit telt nooit als thuis; elke poort
    die op die bewoner wacht, wacht voor niets.

    A resident without a presence entity never counts as home; every gate
    waiting on that resident waits for nothing.
    """
    for resident in config.residents:
        if not resident.presence_entity:
            yield Problem(
                "resident_without_presence",
                f"resident {resident.resident_id} has no presence entity, so can never be home",
                resident=resident.resident_id,
            )


def rule_dead_sleep_settings(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for a sleep setting that can never take effect.

    Een slaapvenster, uitslapen of uiterste tijd zonder slaapsensor kan nooit
    iets doen: de bewoner slaapt dan nooit. De opsta-rem is alleen dood als er
    ook een slaapvenster staat; zonder venster telt de slaapsensor de klok rond
    en remt de opsta-rem wel.

    A sleep window, sleeping in or a deadline without a sleep sensor can never
    do anything: the resident then never sleeps. The rise brake is dead only
    when a sleep window is set too; without a window the sleep sensor counts
    around the clock and the rise brake does brake.
    """
    for resident in config.residents:
        if resident.sleep_entity:
            continue
        dead: list[str] = []
        if resident.sleep_window is not None:
            dead.append("sleep window")
        if resident.sleep_in is not None:
            dead.append("sleep in until")
        if resident.wake_deadline is not None:
            dead.append("wait for this sleeper until")
        if resident.rise_brake is not None and resident.sleep_window is not None:
            dead.append("rise from")
        if dead:
            yield Problem(
                "resident_settings_without_sleep_sensor",
                f"resident {resident.resident_id} has sleep settings but no sleep sensor, "
                f"so they can never take effect: {', '.join(dead)}",
                resident=resident.name or resident.resident_id,
                settings=", ".join(dead),
            )


def quiet_problems(config: DirectorConfig) -> list[Problem]:
    """Return a complaint when the quiet windows leave no room to start.

    Een stiltevenster is het omgekeerde van een rooster: het zegt wanneer er
    níets mag beginnen. Wie dat verkeerd om leest en er vensters in zet die
    samen de klok rondgaan, krijgt een huis dat uit zichzelf nooit meer iets
    doet - en dat ziet er van buiten precies zo uit als een integratie die stuk
    is.

    Er is één ontsnapping: een bewoner die thuis is met een open roostervenster
    verslaat de stilte. Heeft niemand een rooster, dan is die ontsnapping er
    niet.

    Een kwartier is de grens. Niet nul: een gat van één minuut per dag is geen
    ruimte maar toeval, en dan begint er alleen iets als de klok precies goed
    valt.

    A quiet window is the inverse of a schedule: it says when nothing may start.
    Read that the wrong way round and put in windows that together go round the
    clock, and you get a house that never does anything of its own accord again
    - which looks, from the outside, exactly like a broken integration.

    There is one escape: a resident who is home with an open schedule window
    beats the quiet. If nobody has a schedule, that escape does not exist.

    A quarter of an hour is the line. Not zero: a gap of one minute a day is not
    room but coincidence, and then something only starts if the clock happens to
    fall right.
    """
    windows = [window for window in config.gates.quiet_windows if not window.holiday]
    if not windows:
        return []
    if any(resident.windows for resident in config.residents):
        return []

    silent = [day for day in range(7) if free_minutes(windows, day) < QUIET_ROOM_MINUTES]
    if not silent:
        return []

    return [
        Problem(
            "quiet_covers_the_day",
            f"the quiet windows leave under {QUIET_ROOM_MINUTES} minutes on {len(silent)} day(s) "
            "and nobody has a schedule to beat them, so nothing can start on those days",
            days=str(len(silent)),
            minutes=str(QUIET_ROOM_MINUTES),
        )
    ]


def free_minutes(windows: list[TimeWindow], weekday: int) -> int:
    """Return how many minutes of that day no quiet window covers.

    Geteld zoals `TimeWindow.contains` het leest: het beginpunt telt mee, het
    eindpunt niet. Zou dit ruimer tellen, dan zou een venster dat om 12:00
    eindigt en een venster dat om 12:00 begint samen als sluitend gelden
    terwijl er in werkelijkheid een minuut tussen zit.

    Counted the way `TimeWindow.contains` reads it: the start counts, the end
    does not. Counting this more loosely would let a window ending at 12:00 and
    one starting at 12:00 pass as watertight while a minute really sits between
    them.
    """
    covered = [False] * (24 * 60)
    for window in windows:
        start = window.start.hour * 60 + window.start.minute
        end = window.end.hour * 60 + window.end.minute

        # Een venster over middernacht hangt aan zijn startdag. Op déze dag telt
        # zowel het stuk na de start als het stuk dat gisteren begon.
        #
        # A window through midnight hangs off its starting day. On *this* day
        # both the piece after the start and the piece begun yesterday count.
        if start < end:
            spans = [(start, end, weekday)]
        elif start == end:
            spans = []
        else:
            spans = [(start, 24 * 60, weekday), (0, end, (weekday - 1) % 7)]

        for first, last, owning_day in spans:
            if window.weekdays is not None and owning_day not in window.weekdays:
                continue
            for minute in range(first, last):
                covered[minute] = True

    return covered.count(False)
