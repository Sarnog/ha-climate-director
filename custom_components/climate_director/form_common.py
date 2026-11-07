"""De vaste rijen en kleine hulpjes van elk formulier.

The fixed rows and small helpers of every form.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.helpers import selector

from . import texts
from .const import CONF_SHADOW_MODE, DEFAULT_SHADOW_MODE
from .schema_fields import TEXT

ADD = "add_new"
BACK = "back_to_menu"
EXIT = "when_done"
EXIT_KEEP = "keep"
EXIT_DROP = "discard"
CONF_NAME = "name"

WEEKDAYS = texts.WEEKDAYS

_ADD_FALLBACK = {
    "zone": "+ Add zone",
    "source": "+ Add source",
    "circuit": "+ Add circuit",
    "generator": "+ Add heat source",
    "resident": "+ Add resident",
    "window": "+ Add schedule",
    "opening": "+ Add opening",
    "exclusive": "+ Add group",
    "quiet": "+ Add quiet window",
}


def back_option() -> selector.SelectOptionDict:
    """Return the "back to the main menu" row of a picker.

    De Engelse tekst blijft als terugval staan, net als bij de toevoegregel.
    Anders dan die regel hoeft hier geen sleutel bij: de terugval luidt in elke
    lijst hetzelfde, en de vertaling hangt aan de waarde `back_to_menu`.

    The English text stays as a fallback, as with the add row. Unlike that row
    this one needs no key: the fallback reads the same in every list, and the
    translation hangs off the `back_to_menu` value.
    """
    return selector.SelectOptionDict(value=BACK, label="< Back to the main menu")


def exit_row() -> selector.SelectSelector:
    """Return the row that closes a form, keeping or discarding what is on it.

    Home Assistant tekent precies één knop onder een formulier en laat een
    integratie er geen tweede bij zetten. Deze regel is daarom het dichtste bij
    een "Terug"-knop dat er is: dezelfde lijstopmaak als de keuzeschermen, zodat
    elk submenu er hetzelfde uitziet.

    Home Assistant draws exactly one button under a form and lets an integration
    add no second one. This row is therefore the closest thing to a "Back"
    button there is: the same list styling as the pickers, so every submenu
    looks alike.
    """
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                selector.SelectOptionDict(value=EXIT_KEEP, label="Keep these changes and go back"),
                selector.SelectOptionDict(value=EXIT_DROP, label="< Discard and go back"),
            ],
            mode=selector.SelectSelectorMode.LIST,
            translation_key="when_done",
        )
    )


def source_options(flow: Any) -> list[selector.SelectOptionDict]:
    """Return every source in the installation, labelled by zone and appliance."""
    options: list[selector.SelectOptionDict] = []
    for zone in flow._list("zones"):
        for source in zone.get("sources") or []:
            options.append(
                selector.SelectOptionDict(
                    value=source["source_id"],
                    label=(
                        f"{zone.get('name') or zone['zone_id']}"
                        f" - {source.get('name') or source['entity_id']}"
                    ),
                )
            )
    return options


def group_label(flow: Any, group: list[str]) -> str:
    """Return a readable name for one exclusive group."""
    known = {option["value"]: option["label"] for option in source_options(flow)}
    return " + ".join(known.get(source_id, source_id) for source_id in group) or "?"


def add_option(key: str) -> selector.SelectOptionDict:
    """Return the "add one" row of a picker.

    De Engelse tekst blijft als terugval staan: vertaalt Home Assistant de
    sleutel niet, dan staat er nog altijd iets leesbaars in plaats van niets.

    The English text stays as a fallback: if Home Assistant does not translate
    the key, something readable still shows rather than nothing.

    Een onbekende sleutel valt terug op een generieke tekst in plaats van het
    scherm op te blazen. Een terugval hoort nooit de reden te zijn dat er niets
    te zien is - dat was precies wat er misging toen hier een sleutel ontbrak.

    An unknown key falls back on generic wording rather than blowing the screen
    up. A fallback should never itself be the reason nothing shows - which is
    exactly what went wrong when a key was missing here.
    """
    return selector.SelectOptionDict(value=ADD, label=_ADD_FALLBACK.get(key, "+ Add"))


def window_label(window: dict[str, Any], selector_texts: dict[str, str]) -> str:
    """Return a one-line summary of a schedule window for the picker."""
    start = str(window.get("start", "?"))[:5]
    end = str(window.get("end", "?"))[:5]
    # Eerst filteren, dan sorteren. Een opgeslagen lijst met een string ertussen
    # laat `sorted` omvallen op de vergelijking, nog voordat de filter hem ziet.
    #
    # Filter first, then sort. A stored list with a string in it makes `sorted`
    # fall over on the comparison, before the filter ever sees it.
    weekdays = [
        day
        for day in (window.get("weekdays") or ())
        if isinstance(day, int) and not isinstance(day, bool) and 0 <= day < 7
    ]
    if not weekdays:
        return f"{start} - {end}, {texts.every_day(selector_texts)}"
    names = texts.weekday_names(selector_texts, short=True)
    return f"{start} - {end}, {', '.join(names[day] for day in sorted(weekdays))}"


def managed_entities(installation: dict[str, Any]) -> list[str]:
    """Return every climate entity this installation steers, sources first."""
    found: list[str] = []
    for zone in installation.get("zones") or []:
        for source in zone.get("sources") or []:
            if source.get("entity_id"):
                found.append(source["entity_id"])
    for generator in installation.get("generators") or []:
        if generator.get("entity_id"):
            found.append(generator["entity_id"])
    return list(dict.fromkeys(found))


def user() -> vol.Schema:
    """Return the wizard schema: name and shadow mode."""
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default="Climate Director"): TEXT,
            vol.Required(CONF_SHADOW_MODE, default=DEFAULT_SHADOW_MODE): bool,
        }
    )


def save() -> vol.Schema:
    """Return the save-screen schema: keep or discard and go back."""
    return vol.Schema({vol.Required(EXIT, default=EXIT_KEEP): exit_row()})
