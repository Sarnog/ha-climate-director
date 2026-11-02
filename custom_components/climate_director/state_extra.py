"""Bewaarde momenten en de eigen uitzetting die een herstart overleeft.

Stored moments and our own switch-off that survives a restart.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from homeassistant.util import dt as dt_util

from .const import COMMANDED_WINDOW


def stored_time(raw: object) -> datetime | None:
    """Return the moment in a stored value, or `None` when there is none to read.

    `dt_util.parse_datetime` geeft `None` terug voor iets dat het niet herkent,
    maar gooit een `ValueError` voor iets dat er wel op lijkt en het niet is:
    `"2026-13-45T10:00:00+00:00"` heeft geen maand 13. Zo'n waarde hoort net zo
    goed als afwezig te tellen. Een tijdstip zonder tijdzone leest wel, maar het
    laat zich niet met de klok van de integratie vergelijken - dat geeft een
    `TypeError` zodra er iets beslist wordt - dus telt ook dat als afwezig. Elk
    opgeslagen tijdstip leest daarom langs deze functie.

    `dt_util.parse_datetime` returns `None` for something it does not recognise,
    but raises a `ValueError` for something that does look like a date and is not
    one: `"2026-13-45T10:00:00+00:00"` has no month 13. Such a value should count
    as absent just the same. A moment without a time zone does read, but it
    cannot be compared with the integration's clock - that raises a `TypeError`
    the moment anything is decided - so that counts as absent too. Every stored
    moment therefore reads through this function.
    """
    try:
        moment = dt_util.parse_datetime(str(raw))
    except ValueError:
        return None
    if moment is None or moment.tzinfo is None:
        return None
    return moment


def restore_commanded_off(raw: object, now: datetime) -> dict[str, datetime]:
    """Return the still-valid own switch-offs from a stored value.

    Een eigen `off` verklaart een late melding maar kort: na het venster is een
    `off` weer een hand aan het apparaat. Een oude uitzetting uit de opslag mag
    daarom niet als verklaring terugkomen.

    Our own `off` explains a late report only briefly: after the window an `off`
    is a hand at the appliance again. An old switch-off from the store must
    therefore not come back as an explanation.
    """
    if not isinstance(raw, Mapping):
        return {}
    found: dict[str, datetime] = {}
    for entity_id, value in raw.items():
        when = stored_time(value)
        if when is not None and now - when <= COMMANDED_WINDOW:
            found[str(entity_id)] = when
    return found
