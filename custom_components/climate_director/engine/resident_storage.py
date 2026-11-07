"""De ochtendinstellingen van een bewoner: lezen uit en schrijven naar de opslag.

A resident's morning settings: reading from and writing to storage.

Drie instellingen met dezelfde vorm - een tijd en de dagen waarop die geldt:
*Uitslapen tot*, *Wacht op deze slaper tot* en *Opstaan zet het huis pas aan vanaf*.
Ze staan hier apart zodat `serialise.py` onder de maat blijft. Dezelfde regel voor
alle drie: zonder tijd is er geen instelling, ook als er wel dagen staan - een
half ingevuld veld is niet "om middernacht".

Three settings with the same shape - a time and the days it applies on: *Sleeping in
until*, *Wait for this sleeper until* and *Getting up only starts the house from*.
They live apart here so `serialise.py` stays within the measure. The same rule for
all three: without a time there is no setting, even when days stand there - a
half-filled field is not "at midnight".
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import time
from typing import Any

from .installation_storage import sleep_window, time_window
from .models import Resident, RiseBrake, SleepIn, WakeDeadline
from .storage_values import as_dict, bool_or, items, text, time_or, weekdays


def sleep_in_from(raw: dict[str, Any]) -> SleepIn | None:
    """Return the sleep-in time, or `None` when no hour was filled in."""
    until = raw.get("until")
    if not until:
        return None
    return SleepIn(
        until=time_or(until, time(0, 0)),
        weekdays=weekdays(raw.get("weekdays")),
        holiday=bool_or(raw.get("holiday"), False),
    )


def wake_deadline_from(raw: dict[str, Any]) -> WakeDeadline | None:
    """Return the wake deadline, or `None` when no time was filled in.

    Geen tijd betekent: deze bewoner houdt niemand tegen. Een uiterste tijd om
    middernacht zou het huis stilzetten op een uur dat de gebruiker nooit koos.

    No time means: this resident holds nobody back. A deadline at midnight would hold
    the house on an hour the user never picked.
    """
    at = raw.get("at")
    if not at:
        return None
    return WakeDeadline(
        at=time_or(at, time(0, 0)),
        weekdays=weekdays(raw.get("weekdays")),
        holiday=bool_or(raw.get("holiday"), False),
    )


def rise_brake_from(raw: dict[str, Any]) -> RiseBrake | None:
    """Return the rise brake, or `None` when no time was filled in.

    Geen tijd betekent: opstaan zet het huis altijd aan, zoals vóór deze instelling.
    Een vinkje voor vakantiedagen is er niet: op een vakantiedag geldt de rem nooit.

    No time means: getting up always starts the house, as before this setting. There
    is no holiday tick: on a holiday the brake never applies.
    """
    at = raw.get("at")
    if not at:
        return None
    return RiseBrake(at=time_or(at, time(0, 0)), weekdays=weekdays(raw.get("weekdays")))


def _days(weekdays: frozenset[int] | None) -> list[int] | None:
    return None if weekdays is None else sorted(weekdays)


def sleep_in_to_dict(sleep_in: SleepIn | None) -> dict[str, Any] | None:
    """Return the sleep-in time in stored form."""
    if sleep_in is None:
        return None
    return {
        "until": sleep_in.until.isoformat(),
        "weekdays": _days(sleep_in.weekdays),
        "holiday": sleep_in.holiday,
    }


def wake_deadline_to_dict(deadline: WakeDeadline | None) -> dict[str, Any] | None:
    """Return the wake deadline in stored form."""
    if deadline is None:
        return None
    return {
        "at": deadline.at.isoformat(),
        "weekdays": _days(deadline.weekdays),
        "holiday": deadline.holiday,
    }


def rise_brake_to_dict(brake: RiseBrake | None) -> dict[str, Any] | None:
    """Return the rise brake in stored form."""
    if brake is None:
        return None
    return {"at": brake.at.isoformat(), "weekdays": _days(brake.weekdays)}


def resident(raw: Mapping[str, Any]) -> Resident:
    return Resident(
        resident_id=text(raw.get("resident_id")),
        name=text(raw.get("name")),
        windows=tuple(time_window(item) for item in items(raw, "windows")),
        presence_entity=text(raw.get("presence_entity")),
        sleep_entity=text(raw.get("sleep_entity")),
        sleep_state=text(raw.get("sleep_state")) or "on",
        sleep_window=sleep_window(as_dict(raw.get("sleep_window"))),
        sleep_in=sleep_in_from(as_dict(raw.get("sleep_in"))),
        wake_deadline=wake_deadline_from(as_dict(raw.get("wake_deadline"))),
        rise_brake=rise_brake_from(as_dict(raw.get("rise_brake"))),
    )


def resident_to_dict(resident: Resident) -> dict[str, Any]:
    return {
        "resident_id": resident.resident_id,
        "name": resident.name,
        "presence_entity": resident.presence_entity,
        "sleep_entity": resident.sleep_entity,
        "sleep_state": resident.sleep_state,
        "sleep_window": (
            None
            if resident.sleep_window is None
            else {
                "start": resident.sleep_window.start.isoformat(),
                "end": resident.sleep_window.end.isoformat(),
                "weekdays": (
                    None
                    if resident.sleep_window.weekdays is None
                    else sorted(resident.sleep_window.weekdays)
                ),
            }
        ),
        "sleep_in": sleep_in_to_dict(resident.sleep_in),
        "wake_deadline": wake_deadline_to_dict(resident.wake_deadline),
        "rise_brake": rise_brake_to_dict(resident.rise_brake),
        "windows": [
            {
                "start": window.start.strftime("%H:%M:%S"),
                "end": window.end.strftime("%H:%M:%S"),
                "weekdays": (None if window.weekdays is None else sorted(window.weekdays)),
                "holiday": window.holiday,
            }
            for window in resident.windows
        ],
    }
