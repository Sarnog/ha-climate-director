"""Kleine, vergevingsgezinde opslaghelpers voor `serialise.py`.

Small, forgiving storage helpers for `serialise.py`.

Deze functies lezen één opgeslagen waarde en vallen terug op een standaard
zodra de waarde niet is wat ze belooft. Ze staan apart zodat `serialise.py`
onder de maat blijft, en ze zijn puur Python: geen Home Assistant, geen
selectors.

These functions read one stored value and fall back to a default the moment
the value is not what it promises. They live apart so `serialise.py` stays
within the measure, and they are pure Python: no Home Assistant, no selectors.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import time, timedelta
from typing import Any


def _weekdays(raw: Any) -> frozenset[int] | None:
    """Return the days a window is limited to, or `None` for every day.

    Een dagnummer buiten 0-6 is onzin en vervalt. Hem terugvouwen op een
    geldige dag zou een venster zetten op een dag die de gebruiker nooit koos,
    en dat is stiller mis dan hem weglaten. Blijft er niets over, dan geldt het
    venster weer elke dag - een venster op geen enkele dag bestaat niet.

    A day number outside 0-6 is nonsense and is dropped. Folding it back onto a
    valid day would put a window on a day the user never picked, which is more
    quietly wrong than leaving it out. If nothing is left the window applies
    every day again - a window on no day at all does not exist.
    """
    if raw is None:
        return None
    return (
        frozenset(_int(day, 0) for day in _sequence(raw) if _is_number(day) and 0 <= day <= 6)
        or None
    )


def _sequence(raw: Any) -> list[Any]:
    """Return the entries of a stored list, or nothing at all.

    Een opgeslagen lijst die geen lijst blijkt - een getal, een tekst, een dict -
    werd hiervoor gewoon doorlopen, en dan viel de hele integratie om op een
    `TypeError` bij het laden. Alles of niets is hier de veilige kant: een
    onleesbare lijst is een lege lijst, en de configuratiecontrole meldt daarna
    vanzelf wat er ontbreekt.

    A stored list that turns out not to be one - a number, a string, a dict -
    used to be iterated all the same, and the whole integration then fell over on
    a `TypeError` while loading. All or nothing is the safe side here: an
    unreadable list is an empty list, and the configuration check then reports
    what is missing of its own accord.
    """
    return list(raw) if isinstance(raw, list | tuple) else []


def _strings(raw: Any) -> list[str]:
    if isinstance(raw, str) or not isinstance(raw, Iterable):
        return []
    return [item for item in raw if isinstance(item, str)]


def _text(raw: Any) -> str:
    return raw if isinstance(raw, str) else ""


def _is_number(raw: Any) -> bool:
    """Return whether this value can stand in for a number here.

    Booleans zijn in Python getallen, maar `True` als temperatuur is een
    typefout en geen 1 graad. En oneindig of NaN haalt het door elke berekening
    heen tot er ergens een `int()` op stukloopt - dan laadt de hele integratie
    niet meer omdat er ooit iets raars in de opslag terechtkwam.

    Booleans are numbers in Python, but `True` as a temperature is a typing
    mistake rather than one degree. And infinity or NaN carries through every
    calculation until an `int()` somewhere breaks on it - and then the whole
    integration fails to load because something odd once found its way into
    storage.
    """
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        return False
    return math.isfinite(raw)


def _float(raw: Any, default: float) -> float:
    return float(raw) if _is_number(raw) else default


def _optional_float(raw: Any) -> float | None:
    return float(raw) if _is_number(raw) else None


def _int(raw: Any, default: int) -> int:
    return int(raw) if _is_number(raw) else default


def _optional_int(raw: Any) -> int | None:
    return int(raw) if _is_number(raw) else None


def _bool(raw: Any, default: bool) -> bool:
    return raw if isinstance(raw, bool) else default


def _seconds(raw: Any, default: float = 0.0) -> timedelta:
    """Return a duration; stored as plain seconds so the entry stays JSON."""
    return timedelta(seconds=_float(raw, default))


def _time(raw: Any, default: time) -> time:
    """Return a time from `HH:MM` or `HH:MM:SS`, falling back on `default`.

    A single-digit hour is padded first: the options flow always writes a padded
    time, but a hand-edited entry may well say `8:00`, and reading that as
    midnight would move somebody's schedule by eight hours without a word.
    """
    if not isinstance(raw, str):
        return default
    text = raw.strip()
    if len(text) > 1 and text[1] == ":":
        text = f"0{text}"
    try:
        return time.fromisoformat(text)
    except ValueError:
        return default


def _enum[T: str](enum_type: type[T], raw: Any, default: T) -> T:
    """Return the enum member named by `raw`, or `default` when unrecognised."""
    if not isinstance(raw, str):
        return default
    try:
        return enum_type(raw)
    except ValueError:
        return default
