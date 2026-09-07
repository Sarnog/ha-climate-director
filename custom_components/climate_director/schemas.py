"""Formulieropbouw voor de config flow en options flow.

Form building for the config flow and options flow.

Elk scherm bouwt hier zijn eigen `vol.Schema` uit de huidige waarden. De
`async_step_*`-methodes in `config_flow.py` houden de navigatie, de validatie
en het opslaan; dit bestand gaat alleen over wat het scherm toont.

Every screen builds its own `vol.Schema` here from the current values. The
`async_step_*` methods in `config_flow.py` keep the navigation, the validation
and the saving; this file is only about what the screen shows.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers import selector

from . import texts
from .const import CONF_SHADOW_MODE, DEFAULT_SHADOW_MODE
from .engine.models import (
    ConflictPolicy,
    HeatingLayout,
    PrecipitationSettings,
    Season,
    SeasonSettings,
    SeasonSource,
    SourceRole,
    ZoneGate,
)
from .units import (
    rounded_delta_from_celsius,
    rounded_from_celsius,
    temperature_unit_of,
)

CONF_NAME = "name"

_ADD = "add_new"
_BACK = "back_to_menu"
_EXIT = "when_done"
_EXIT_KEEP = "keep"
_EXIT_DROP = "discard"

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

#: Maandag is 0, gelijk aan `datetime.weekday()`, dat de engine ook gebruikt.
#: Deze Engelse namen zijn alleen de terugval in het schema: de keuzevelden
#: dragen `translation_key="weekday"`, dus de interface zet er de taal van de
#: gebruiker neer. Ze staan in `texts.py`, want de lijstregels lezen ze ook.
#:
#: Monday is 0, matching `datetime.weekday()`, which the engine uses too. These
#: English names are only the schema's fallback: the pickers carry
#: `translation_key="weekday"`, so the interface puts the user's language there.
#: They live in `texts.py`, since the list lines read them too.
_WEEKDAYS = texts.WEEKDAYS

#: Zomermaanden per halfrond, als maandnummers 1-12. De engine telt
#: april-september als zomer; wie op het zuidelijk halfrond woont, krijgt
#: oktober-maart. De noordelijke standaard komt uit de engine, zodat hij hier
#: niet stilletjes uit de pas kan lopen.
#:
#: Summer months per hemisphere, as month numbers 1-12. The engine counts
#: April-September as summer; the southern hemisphere gets October-March. The
#: northern default comes from the engine, so it cannot drift apart here.
_SUMMER_NORTH = SeasonSettings().summer_months
_SUMMER_SOUTH = frozenset({1, 2, 3, 10, 11, 12})


def _hemisphere(months: Any) -> str:
    """Return which hemisphere a stored summer-months set describes.

    Alles wat niet precies het zuidelijke rijtje is, telt als noordelijk. Dat is
    de veilige kant: een handmatig bewerkte of half geschreven waarde valt
    terug op de standaard in plaats van de wizard te laten struikelen.

    Anything that is not exactly the southern row counts as northern. That is
    the safe side: a hand-edited or half-written value falls back on the
    default rather than tripping the wizard up.
    """
    try:
        return "south" if frozenset(int(month) for month in months) == _SUMMER_SOUTH else "north"
    except (TypeError, ValueError):
        return "north"


def _temperature(unit: str) -> selector.NumberSelector:
    """Return a temperature selector in the user's unit.

    De engine bewaart alles in graden Celsius; het formulier toont de eenheid
    van Home Assistant. In Fahrenheit is hetzelfde zinnige bereik -20..40 °C
    precies -4..104 °F.

    The engine stores everything in degrees Celsius; the form shows Home
    Assistant's unit. In Fahrenheit the same sensible -20..40 °C range is
    exactly -4..104 °F.
    """
    if unit == UnitOfTemperature.FAHRENHEIT:
        return selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=-4,
                max=104,
                step=1,
                unit_of_measurement="°F",
                mode=selector.NumberSelectorMode.BOX,
            )
        )
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=-20,
            max=40,
            step=0.5,
            unit_of_measurement="°C",
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _band(unit: str) -> selector.NumberSelector:
    """Return a temperature-band selector in the user's unit.

    Een band is een verschil, dus in Fahrenheit telt alleen de schaalfactor:
    0..10 °C is 0..18 °F.

    A band is a difference, so in Fahrenheit only the scale factor counts:
    0..10 °C is 0..18 °F.
    """
    if unit == UnitOfTemperature.FAHRENHEIT:
        return selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0,
                max=18,
                step=0.2,
                unit_of_measurement="°F",
                mode=selector.NumberSelectorMode.BOX,
            )
        )
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0,
            max=10,
            step=0.1,
            unit_of_measurement="°C",
            mode=selector.NumberSelectorMode.BOX,
        )
    )


_MINUTES_OR_OFF = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=0, max=240, step=1, unit_of_measurement="min", mode=selector.NumberSelectorMode.BOX
    )
)

_MINUTES = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=1, max=480, step=1, unit_of_measurement="min", mode=selector.NumberSelectorMode.BOX
    )
)

_SECONDS = selector.NumberSelector(
    selector.NumberSelectorConfig(min=0, max=3600, step=1, mode=selector.NumberSelectorMode.BOX)
)
_RANK = selector.NumberSelector(
    selector.NumberSelectorConfig(min=0, max=99, step=1, mode=selector.NumberSelectorMode.BOX)
)
_CLIMATE = selector.EntitySelector(selector.EntitySelectorConfig(domain="climate"))
_CLIMATE_MULTI = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="climate", multiple=True)
)
_TEXT = selector.TextSelector()
_TIME = selector.TimeSelector()


def _choices(values: list[str], key: str = "") -> selector.SelectSelector:
    """Return a dropdown over plain string values.

    Met een vertaalsleutel toont Home Assistant de vertaalde namen in plaats van
    de opgeslagen waarden. Zonder sleutel blijft het bij de waarde zelf, wat voor
    een lijst die al leesbaar is genoeg is.

    With a translation key Home Assistant shows translated names instead of the
    stored values. Without one the value itself shows, which is enough for a list
    that reads well already.
    """
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=values,
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key=key or None,
        )
    )


def _back_option() -> selector.SelectOptionDict:
    """Return the "back to the main menu" row of a picker.

    De Engelse tekst blijft als terugval staan, net als bij de toevoegregel.
    Anders dan die regel hoeft hier geen sleutel bij: de terugval luidt in elke
    lijst hetzelfde, en de vertaling hangt aan de waarde `back_to_menu`.

    The English text stays as a fallback, as with the add row. Unlike that row
    this one needs no key: the fallback reads the same in every list, and the
    translation hangs off the `back_to_menu` value.
    """
    return selector.SelectOptionDict(value=_BACK, label="< Back to the main menu")


def _exit_row() -> selector.SelectSelector:
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
                selector.SelectOptionDict(value=_EXIT_KEEP, label="Keep these changes and go back"),
                selector.SelectOptionDict(value=_EXIT_DROP, label="< Discard and go back"),
            ],
            mode=selector.SelectSelectorMode.LIST,
            translation_key="when_done",
        )
    )


def _source_options(flow: Any) -> list[selector.SelectOptionDict]:
    """Return every source in the installation, labelled by zone and appliance."""
    options: list[selector.SelectOptionDict] = []
    for zone in flow._list("zones"):
        for source in zone.get("sources") or []:
            options.append(
                selector.SelectOptionDict(
                    value=source["source_id"],
                    label=f"{zone.get('name') or zone['zone_id']} - {source['entity_id']}",
                )
            )
    return options


def _group_label(flow: Any, group: list[str]) -> str:
    """Return a readable name for one exclusive group."""
    known = {option["value"]: option["label"] for option in _source_options(flow)}
    return " + ".join(known.get(source_id, source_id) for source_id in group) or "?"


def _add_option(key: str) -> selector.SelectOptionDict:
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
    return selector.SelectOptionDict(value=_ADD, label=_ADD_FALLBACK.get(key, "+ Add"))


def _window_label(window: dict[str, Any], selector_texts: dict[str, str]) -> str:
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


def _managed_entities(installation: dict[str, Any]) -> list[str]:
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
            vol.Required(CONF_NAME, default="Climate Director"): _TEXT,
            vol.Required(CONF_SHADOW_MODE, default=DEFAULT_SHADOW_MODE): bool,
        }
    )


def save() -> vol.Schema:
    """Return the save-screen schema: keep or discard and go back."""
    return vol.Schema({vol.Required(_EXIT, default=_EXIT_KEEP): _exit_row()})


def settings(flow: Any) -> vol.Schema:
    """Return the general settings schema from the current installation."""
    installation = flow._installation
    seasons = installation.get("seasons") or {}
    gates = installation.get("gates") or {}
    guest = gates.get("guest_window") or {}
    precipitation = installation.get("precipitation") or {}
    unit = temperature_unit_of(flow.hass)
    return vol.Schema(
        {
            vol.Optional(
                "outdoor_sensor",
                description={"suggested_value": installation.get("outdoor_sensor") or None},
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain=["sensor", "weather"])),
            vol.Required(
                "outdoor_hysteresis",
                default=rounded_delta_from_celsius(
                    float(installation.get("outdoor_hysteresis", 0.5)), unit
                ),
            ): _band(unit),
            vol.Required(
                "heating_layout",
                default=installation.get("heating_layout", HeatingLayout.PER_ZONE.value),
            ): _choices([item.value for item in HeatingLayout], "heating_layout"),
            vol.Required(
                "season_source", default=seasons.get("source", SeasonSource.AUTO.value)
            ): _choices([item.value for item in SeasonSource], "season_source"),
            vol.Optional(
                "season_entity",
                description={"suggested_value": seasons.get("entity_id") or None},
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["sensor", "input_select", "select", "season"])
            ),
            vol.Required(
                "hemisphere",
                default=_hemisphere(seasons.get("summer_months")),
            ): _choices(["north", "south"], "hemisphere"),
            vol.Required("require_awake", default=gates.get("require_awake", True)): bool,
            vol.Required("require_schedule", default=gates.get("require_schedule", False)): bool,
            vol.Optional(
                "holiday_calendars",
                description={"suggested_value": installation.get("holiday_calendars") or None},
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="calendar", multiple=True)
            ),
            vol.Optional(
                "holiday_keyword",
                description={"suggested_value": installation.get("holiday_keyword") or None},
            ): str,
            vol.Required(
                "max_precondition",
                default=int(gates.get("max_precondition", 7200)) // 60,
            ): _MINUTES,
            vol.Optional(
                "guest_start",
                description={"suggested_value": guest.get("start") or None},
            ): _TIME,
            vol.Optional(
                "guest_end",
                description={"suggested_value": guest.get("end") or None},
            ): _TIME,
            vol.Required(
                "stuck_after",
                default=int(installation.get("stuck_after", 900)) // 60,
            ): _MINUTES_OR_OFF,
            vol.Optional(
                "precipitation_source",
                description={"suggested_value": precipitation.get("source") or None},
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain=["weather", "sensor"])),
            vol.Required(
                "precipitation_states",
                default=", ".join(
                    precipitation.get("states") or sorted(PrecipitationSettings().states)
                ),
            ): _TEXT,
            vol.Required(
                "precipitation_grace",
                default=int(
                    precipitation.get("grace", PrecipitationSettings().grace.total_seconds())
                )
                // 60,
            ): _MINUTES,
            vol.Required(
                CONF_SHADOW_MODE,
                default=(
                    flow._shadow_mode if flow._shadow_mode is not None else DEFAULT_SHADOW_MODE
                ),
            ): bool,
            vol.Required(_EXIT, default=_EXIT_KEEP): _exit_row(),
        }
    )


def exclusives(flow: Any) -> vol.Schema:
    """Return the exclusive-group picker schema."""
    groups = flow._list("exclusive_groups")
    options = [
        selector.SelectOptionDict(value=str(index), label=_group_label(flow, group))
        for index, group in enumerate(groups)
    ]
    options.append(_add_option("exclusive"))
    options.append(_back_option())
    return vol.Schema(
        {
            vol.Required("group", default=_ADD): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    mode=selector.SelectSelectorMode.LIST,
                    translation_key="exclusive_list",
                )
            )
        }
    )


def exclusive(flow: Any, current: list[str]) -> vol.Schema:
    """Return the single exclusive-group schema."""
    return vol.Schema(
        {
            vol.Optional(
                "sources", description={"suggested_value": list(current) or None}
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=_source_options(flow),
                    mode=selector.SelectSelectorMode.LIST,
                    multiple=True,
                )
            ),
            vol.Required("delete", default=False): bool,
            vol.Required(_EXIT, default=_EXIT_KEEP): _exit_row(),
        }
    )


def quiets(flow: Any, selector_texts: dict[str, str]) -> vol.Schema:
    """Return the quiet-window picker schema."""
    windows = flow._quiet_windows()
    options = [
        selector.SelectOptionDict(value=str(index), label=_window_label(window, selector_texts))
        for index, window in enumerate(windows)
    ]
    options.append(_add_option("quiet"))
    options.append(_back_option())
    return vol.Schema(
        {
            vol.Required("quiet", default=_BACK if windows else _ADD): (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        mode=selector.SelectSelectorMode.LIST,
                        translation_key="quiet_list",
                    )
                )
            )
        }
    )


def quiet(current: dict[str, Any]) -> vol.Schema:
    """Return the single quiet-window schema."""
    weekdays = current.get("weekdays")
    return vol.Schema(
        {
            vol.Required("holiday", default=current.get("holiday", False)): bool,
            vol.Required("start", default=current.get("start", "21:00:00")): _TIME,
            vol.Required("end", default=current.get("end", "09:00:00")): _TIME,
            vol.Optional(
                "weekdays",
                description={
                    "suggested_value": (
                        None if weekdays is None else [str(day) for day in weekdays]
                    )
                },
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value=str(number), label=label)
                        for number, label in enumerate(_WEEKDAYS)
                    ],
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                    translation_key="weekday",
                )
            ),
            vol.Required("delete", default=False): bool,
            vol.Required(_EXIT, default=_EXIT_KEEP): _exit_row(),
        }
    )


def zones(flow: Any) -> vol.Schema:
    """Return the zone picker schema."""
    zones = flow._list("zones")
    options = [
        selector.SelectOptionDict(value=str(index), label=zone.get("name") or zone["zone_id"])
        for index, zone in enumerate(zones)
    ]
    options.append(_add_option("zone"))
    options.append(_back_option())
    return vol.Schema(
        {
            vol.Required("zone", default=_ADD): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    mode=selector.SelectSelectorMode.LIST,
                    translation_key="zone_list",
                )
            )
        }
    )


def zone(flow: Any, current: dict[str, Any], priority: int) -> vol.Schema:
    """Return the single zone schema."""
    heat = current.get("heat") or {}
    cool = current.get("cool") or {}
    unit = temperature_unit_of(flow.hass)
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=current.get("name", "")): _TEXT,
            vol.Optional(
                "indoor_sensor",
                description={"suggested_value": current.get("indoor_sensor") or None},
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain=["sensor", "climate"])),
            vol.Required("priority", default=priority): _RANK,
            vol.Required("gate", default=current.get("gate", ZoneGate.HOUSEHOLD.value)): _choices(
                [item.value for item in ZoneGate], "zone_gate"
            ),
            vol.Optional(
                "presence_entity",
                description={"suggested_value": current.get("presence_entity") or None},
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["binary_sensor", "sensor", "input_boolean"])
            ),
            vol.Required("presence_state", default=current.get("presence_state", "on")): _TEXT,
            vol.Optional(
                "presence_timeout",
                description={"suggested_value": current.get("presence_timeout") or None},
            ): _SECONDS,
            vol.Required(
                "ignore_precipitation",
                default=current.get("ignore_precipitation", False),
            ): bool,
            vol.Required("enable_heat", default=bool(heat)): bool,
            vol.Required(
                "heat_target", default=rounded_from_celsius(heat.get("target", 21.0), unit)
            ): _temperature(unit),
            vol.Required(
                "heat_start_at",
                default=rounded_from_celsius(heat.get("start_at", 20.0), unit),
            ): _temperature(unit),
            vol.Required(
                "heat_hysteresis",
                default=rounded_delta_from_celsius(heat.get("hysteresis", 1.0), unit),
            ): _band(unit),
            vol.Optional(
                "heat_outdoor_max",
                description={
                    "suggested_value": rounded_from_celsius(
                        (heat.get("outdoor") or {}).get("maximum"), unit
                    )
                },
            ): _temperature(unit),
            vol.Required("enable_cool", default=bool(cool)): bool,
            vol.Required(
                "cool_target", default=rounded_from_celsius(cool.get("target", 23.0), unit)
            ): _temperature(unit),
            vol.Required(
                "cool_start_at",
                default=rounded_from_celsius(cool.get("start_at", 24.0), unit),
            ): _temperature(unit),
            vol.Required(
                "cool_hysteresis",
                default=rounded_delta_from_celsius(cool.get("hysteresis", 1.0), unit),
            ): _band(unit),
            vol.Optional(
                "cool_outdoor_min",
                description={
                    "suggested_value": rounded_from_celsius(
                        (cool.get("outdoor") or {}).get("minimum"), unit
                    )
                },
            ): _temperature(unit),
            vol.Required(
                "cool_summer_only",
                default=Season.SUMMER.value in (cool.get("seasons") or []),
            ): bool,
            vol.Required("delete", default=False): bool,
            vol.Required(_EXIT, default=_EXIT_KEEP): _exit_row(),
        }
    )


def sources(flow: Any) -> vol.Schema:
    """Return the source picker schema of the current zone."""
    zone = flow._current_zone()
    sources = zone.setdefault("sources", [])
    options = [
        selector.SelectOptionDict(value=str(index), label=source["entity_id"])
        for index, source in enumerate(sources)
    ]
    options.append(_add_option("source"))
    options.append(_back_option())
    return vol.Schema(
        {
            vol.Required("source", default=_ADD): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    mode=selector.SelectSelectorMode.LIST,
                    translation_key="source_list",
                )
            )
        }
    )


def source(flow: Any, current: dict[str, Any]) -> vol.Schema:
    """Return the single source schema."""
    outdoor = current.get("outdoor") or {}
    unit = temperature_unit_of(flow.hass)
    return vol.Schema(
        {
            vol.Optional(
                "entity_id",
                description={"suggested_value": current.get("entity_id") or None},
            ): _CLIMATE,
            vol.Required("role", default=current.get("role", SourceRole.HEAT_COOL.value)): _choices(
                [item.value for item in SourceRole], "source_role"
            ),
            vol.Required("autostart", default=current.get("autostart", True)): bool,
            vol.Required("priority", default=current.get("priority", 0)): _RANK,
            vol.Optional(
                "outdoor_min",
                description={"suggested_value": rounded_from_celsius(outdoor.get("minimum"), unit)},
            ): _temperature(unit),
            vol.Optional(
                "outdoor_max",
                description={"suggested_value": rounded_from_celsius(outdoor.get("maximum"), unit)},
            ): _temperature(unit),
            vol.Optional(
                "min_cycle_time",
                description={"suggested_value": current.get("min_cycle_time")},
            ): _SECONDS,
            vol.Required("delete", default=False): bool,
            vol.Required(_EXIT, default=_EXIT_KEEP): _exit_row(),
        }
    )


def circuits(flow: Any) -> vol.Schema:
    """Return the circuit picker schema."""
    circuits = flow._list("circuits")
    options = [
        selector.SelectOptionDict(
            value=str(index), label=circuit.get("name") or circuit["circuit_id"]
        )
        for index, circuit in enumerate(circuits)
    ]
    options.append(_add_option("circuit"))
    options.append(_back_option())
    return vol.Schema(
        {
            vol.Required("circuit", default=_ADD): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    mode=selector.SelectSelectorMode.LIST,
                    translation_key="circuit_list",
                )
            )
        }
    )


def circuit(current: dict[str, Any]) -> vol.Schema:
    """Return the single circuit schema."""
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=current.get("name", "")): _TEXT,
            vol.Optional(
                "units", description={"suggested_value": current.get("units") or []}
            ): _CLIMATE_MULTI,
            vol.Required(
                "simultaneous_heat_cool",
                default=current.get("simultaneous_heat_cool", False),
            ): bool,
            vol.Required(
                "conflict_policy",
                default=current.get("conflict_policy", ConflictPolicy.PRIORITY.value),
            ): _choices([item.value for item in ConflictPolicy], "conflict_policy"),
            vol.Required(
                "allow_fan_only_during_conflict",
                default=current.get("allow_fan_only_during_conflict", False),
            ): bool,
            vol.Required(
                "family_switch_delay", default=current.get("family_switch_delay", 0)
            ): _SECONDS,
            vol.Required(
                "min_family_switch_interval",
                default=current.get("min_family_switch_interval", 0),
            ): _SECONDS,
            vol.Required("min_cycle_time", default=current.get("min_cycle_time", 180)): _SECONDS,
            vol.Optional(
                "max_concurrent_units",
                description={"suggested_value": current.get("max_concurrent_units")},
            ): _RANK,
            vol.Required("delete", default=False): bool,
            vol.Required(_EXIT, default=_EXIT_KEEP): _exit_row(),
        }
    )


def circuit_priorities(flow: Any) -> vol.Schema:
    """Return the circuit-priority picker schema of the current circuit."""
    circuit = flow._current_circuit()
    zones = flow._zones_on(circuit)
    options = [
        selector.SelectOptionDict(
            value=zone["zone_id"],
            label=f"{zone.get('name') or zone['zone_id']} — {zone.get('priority', 0)}",
        )
        for zone in zones
    ]
    options.append(_back_option())
    return vol.Schema(
        {
            vol.Required("zone", default=_BACK): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    mode=selector.SelectSelectorMode.LIST,
                    translation_key="circuit_priority_list",
                )
            )
        }
    )


def circuit_priority(zone: dict[str, Any]) -> vol.Schema:
    """Return the single circuit-priority schema."""
    return vol.Schema(
        {
            vol.Required("priority", default=zone.get("priority", 0)): _RANK,
            vol.Required(_EXIT, default=_EXIT_KEEP): _exit_row(),
        }
    )


def generators(flow: Any) -> vol.Schema:
    """Return the shared-heat-source picker schema."""
    generators = flow._list("generators")
    options = [
        selector.SelectOptionDict(value=str(index), label=item.get("name") or item["generator_id"])
        for index, item in enumerate(generators)
    ]
    options.append(_add_option("generator"))
    options.append(_back_option())
    return vol.Schema(
        {
            vol.Required("generator", default=_ADD): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    mode=selector.SelectSelectorMode.LIST,
                    translation_key="generator_list",
                )
            )
        }
    )


def generator(flow: Any, current: dict[str, Any]) -> vol.Schema:
    """Return the single shared-heat-source schema."""
    unit = temperature_unit_of(flow.hass)
    zone_options = [
        selector.SelectOptionDict(value=zone["zone_id"], label=zone.get("name") or zone["zone_id"])
        for zone in flow._list("zones")
    ]
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=current.get("name", "")): _TEXT,
            vol.Optional(
                "entity_id",
                description={"suggested_value": current.get("entity_id") or None},
            ): _CLIMATE,
            vol.Optional(
                "zone_ids",
                description={"suggested_value": current.get("zone_ids") or []},
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(options=zone_options, multiple=True)
            ),
            vol.Optional(
                "setpoint",
                description={
                    "suggested_value": rounded_from_celsius(current.get("setpoint"), unit)
                },
            ): _temperature(unit),
            vol.Required("delete", default=False): bool,
            vol.Required(_EXIT, default=_EXIT_KEEP): _exit_row(),
        }
    )


def residents(flow: Any) -> vol.Schema:
    """Return the resident picker schema."""
    residents = flow._list("residents")
    options = [
        selector.SelectOptionDict(
            value=str(index), label=person.get("name") or person["resident_id"]
        )
        for index, person in enumerate(residents)
    ]
    options.append(_add_option("resident"))
    options.append(_back_option())
    return vol.Schema(
        {
            vol.Required("resident", default=_ADD): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    mode=selector.SelectSelectorMode.LIST,
                    translation_key="resident_list",
                )
            )
        }
    )


def resident(current: dict[str, Any]) -> vol.Schema:
    """Return the single resident schema."""
    stored_days = (current.get("sleep_window") or {}).get("weekdays")
    sleep_days = None if stored_days is None else [str(day) for day in stored_days]
    stored_sleep_in_days = (current.get("sleep_in") or {}).get("weekdays")
    sleep_in_days = (
        None if stored_sleep_in_days is None else [str(day) for day in stored_sleep_in_days]
    )
    stored_wake_days = (current.get("wake_deadline") or {}).get("weekdays")
    wake_days = None if stored_wake_days is None else [str(day) for day in stored_wake_days]
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=current.get("name", "")): _TEXT,
            vol.Optional(
                "presence_entity",
                description={"suggested_value": current.get("presence_entity") or None},
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=["person", "device_tracker", "binary_sensor", "input_boolean"]
                )
            ),
            vol.Optional(
                "sleep_entity",
                description={"suggested_value": current.get("sleep_entity") or None},
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["binary_sensor", "sensor", "input_boolean"])
            ),
            vol.Required("sleep_state", default=current.get("sleep_state", "on")): _TEXT,
            vol.Optional(
                "sleep_from",
                description={"suggested_value": (current.get("sleep_window") or {}).get("start")},
            ): _TIME,
            vol.Optional(
                "sleep_until",
                description={"suggested_value": (current.get("sleep_window") or {}).get("end")},
            ): _TIME,
            vol.Optional(
                "sleep_days",
                description={"suggested_value": sleep_days},
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value=str(number), label=label)
                        for number, label in enumerate(_WEEKDAYS)
                    ],
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                    translation_key="weekday",
                )
            ),
            vol.Optional(
                "sleep_in_until",
                description={"suggested_value": (current.get("sleep_in") or {}).get("until")},
            ): _TIME,
            vol.Required(
                "sleep_in_holiday",
                default=(current.get("sleep_in") or {}).get("holiday", False),
            ): bool,
            vol.Optional(
                "sleep_in_days",
                description={"suggested_value": sleep_in_days},
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value=str(number), label=label)
                        for number, label in enumerate(_WEEKDAYS)
                    ],
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                    translation_key="weekday",
                )
            ),
            vol.Optional(
                "wake_by",
                description={"suggested_value": (current.get("wake_deadline") or {}).get("at")},
            ): _TIME,
            vol.Required(
                "wake_holiday",
                default=(current.get("wake_deadline") or {}).get("holiday", False),
            ): bool,
            vol.Optional(
                "wake_days",
                description={"suggested_value": wake_days},
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value=str(number), label=label)
                        for number, label in enumerate(_WEEKDAYS)
                    ],
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                    translation_key="weekday",
                )
            ),
            vol.Required("delete", default=False): bool,
            vol.Required(_EXIT, default=_EXIT_KEEP): _exit_row(),
        }
    )


def windows(flow: Any, selector_texts: dict[str, str]) -> vol.Schema:
    """Return the schedule-window picker schema of the current resident."""
    resident = flow._current_resident()
    windows = resident.setdefault("windows", [])
    options = [
        selector.SelectOptionDict(value=str(index), label=_window_label(window, selector_texts))
        for index, window in enumerate(windows)
    ]
    options.append(_add_option("window"))
    options.append(_back_option())
    return vol.Schema(
        {
            vol.Required("window", default=_BACK if windows else _ADD): (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        mode=selector.SelectSelectorMode.LIST,
                        translation_key="window_list",
                    )
                )
            )
        }
    )


def window(current: dict[str, Any]) -> vol.Schema:
    """Return the single schedule-window schema."""
    weekdays = current.get("weekdays")
    return vol.Schema(
        {
            vol.Required("holiday", default=current.get("holiday", False)): bool,
            vol.Required("start", default=current.get("start", "08:00:00")): _TIME,
            vol.Required("end", default=current.get("end", "23:00:00")): _TIME,
            vol.Optional(
                "weekdays",
                description={
                    "suggested_value": (
                        None if weekdays is None else [str(day) for day in weekdays]
                    )
                },
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value=str(number), label=label)
                        for number, label in enumerate(_WEEKDAYS)
                    ],
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                    translation_key="weekday",
                )
            ),
            vol.Required("delete", default=False): bool,
            vol.Required(_EXIT, default=_EXIT_KEEP): _exit_row(),
        }
    )


def openings(flow: Any) -> vol.Schema:
    """Return the opening picker schema, house-wide stops included."""
    openings = flow._list("openings")
    options = [
        selector.SelectOptionDict(value=str(index), label=opening["entity_id"])
        for index, opening in enumerate(openings)
    ]
    options.append(_add_option("opening"))
    options.append(_back_option())
    managed = _managed_entities(flow._installation)
    # De huisbrede lijst wordt hier alleen voor het scherm gefilterd en niet
    # weggeschreven: het veld zou anders een waarde tonen die zijn eigen
    # schema (`include_entities`) afkeurt, en dan weigert élke inzending,
    # "terug" inbegrepen. De opgeslagen lijst houdt het oude id, zodat het
    # opslaanscherm het via `validate()` kan melden; dit scherm bevestigen
    # schrijft wat het toont en haalt het er zo zelf uit.
    #
    # The house-wide list is filtered for this screen only and not written
    # away: the field would otherwise show a value its own schema
    # (`include_entities`) rejects, and then every submission would be
    # refused, "back" included. The stored list keeps the old id, so the
    # save screen can report it via `validate()`; confirming this screen
    # writes what it shows and thereby removes it by hand.
    suggested = [
        entity_id
        for entity_id in (flow._installation.get("house_wide_openings") or ())
        if entity_id in managed
    ]
    return vol.Schema(
        {
            vol.Required("opening", default=_ADD): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    mode=selector.SelectSelectorMode.LIST,
                    translation_key="opening_list",
                )
            ),
            # Alleen apparaten die deze installatie ook echt aanstuurt.
            # Een vrije keuzelijst zou een apparaat toelaten waar de
            # director nooit een commando aan geeft, en dan doet de
            # instelling stilletjes niets - precies het soort val dat
            # niemand terugvindt.
            #
            # Only appliances this installation actually steers. A free
            # picker would allow one the director never commands, and
            # then the setting quietly does nothing - exactly the kind
            # of trap nobody ever traces back.
            vol.Optional(
                "house_wide_openings",
                description={"suggested_value": suggested or None},
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="climate", multiple=True, include_entities=managed
                )
            ),
        }
    )


def opening(flow: Any, current: dict[str, Any]) -> vol.Schema:
    """Return the single opening schema."""
    zone_options = [
        selector.SelectOptionDict(value=zone["zone_id"], label=zone.get("name") or zone["zone_id"])
        for zone in flow._list("zones")
    ]
    return vol.Schema(
        {
            vol.Optional(
                "entity_id",
                description={"suggested_value": current.get("entity_id") or None},
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["binary_sensor", "cover", "sensor"])
            ),
            vol.Optional(
                "open_state",
                description={"suggested_value": current.get("open_state") or "on"},
            ): _TEXT,
            vol.Optional(
                "zone_ids",
                description={"suggested_value": current.get("zone_ids") or []},
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(options=zone_options, multiple=True)
            ),
            vol.Optional(
                "delay", description={"suggested_value": current.get("delay") or None}
            ): _SECONDS,
            vol.Required("delete", default=False): bool,
            vol.Required(_EXIT, default=_EXIT_KEEP): _exit_row(),
        }
    )
