"""Wanneer een entiteit geen lezing geeft.

When an entity gives no reading.

De koppelingslaag leest entiteiten op meer dan één plek: de wereld, de
aanwezigheidslistener, het herstel van het thuiskomstmoment en de kamerpoort.
Zij moeten het allemaal één keer eens zijn over wat "hier valt niets uit op te
maken" betekent. Daarom staat die regel hier, met een publieke naam: dit is
gedeelde kennis over een modulegrens heen, geen privéhulpje van de wereldbouwer.

The binding layer reads entities in more than one place: the world, the presence
listener, the homecoming restore and the room gate. They must all agree, once,
on what "nothing can be made of this" means. That rule therefore lives here,
with a public name: it is shared knowledge across a module boundary, not a
private helper of the world builder.
"""

from __future__ import annotations

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from .engine import DirectorConfig
from .engine.world import ReadableInput, UnreadableInput


def unreadable(state: str | None) -> bool:
    """Return whether an entity state carries no reading at all.

    Ontbrekend (`None`), `unavailable` en `unknown` zijn geen lezing. Elke
    andere stand is er wel een, ook `none`, `not_home` of `off`: die zeggen
    iets, al is het niet wat de integration hoopte.

    Missing (`None`), `unavailable` and `unknown` are no reading. Every other
    state is one, including `none`, `not_home` or `off`: they say something,
    even if it is not what the integration hoped for.
    """
    return state is None or state in (STATE_UNAVAILABLE, STATE_UNKNOWN)


def unreadable_inputs(hass: HomeAssistant, config: DirectorConfig) -> frozenset[UnreadableInput]:
    """Return every input of the three waiting brakes that gave no reading.

    Alleen wat deze installatie werkelijk gebruikt telt: een bewoner zonder
    aanwezigheids- of slaapsensor levert geen invoer, en de agenda's tellen
    alleen met een trefwoord. Zo kan een niet-geconfigureerde entiteit nooit een
    handstart laten staan.

    Only what this installation actually uses counts: a resident without a
    presence or sleep sensor supplies no input, and the calendars count only
    with a keyword. A non-configured entity can therefore never keep a hand
    start standing.
    """
    found: set[UnreadableInput] = set()
    for resident in config.residents:
        if resident.presence_entity and _no_reading(hass, resident.presence_entity):
            found.add(UnreadableInput(ReadableInput.PRESENCE, resident.resident_id))
        if resident.sleep_entity and _no_reading(hass, resident.sleep_entity):
            found.add(UnreadableInput(ReadableInput.SLEEP, resident.resident_id))
    if config.holiday_keyword.strip():
        for calendar in config.holiday_calendars:
            if calendar and _no_reading(hass, calendar):
                found.add(UnreadableInput(ReadableInput.HOLIDAY))
                break
    return frozenset(found)


def _no_reading(hass: HomeAssistant, entity_id: str) -> bool:
    """Return whether this entity is missing or reports no usable state."""
    state = hass.states.get(entity_id)
    return state is None or unreadable(state.state)
