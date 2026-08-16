"""Config flow en options flow van Climate Director.

Climate Director's config flow and options flow.

De installatie wordt volledig via de UI opgebouwd en als één dict in
`entry.options[CONF_INSTALLATION]` bewaard - hetzelfde formaat dat
`engine.serialise` leest. Deze module bevat daarom geen kennis van klimaatregels,
alleen van formulieren.

The installation is built entirely through the UI and stored as one dict in
`entry.options[CONF_INSTALLATION]` - the same format `engine.serialise` reads.
This module therefore holds no knowledge of climate rules, only of forms.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.util import slugify

from .const import CONF_INSTALLATION, CONF_SHADOW_MODE, DEFAULT_SHADOW_MODE, DOMAIN
from .coordinator import ClimateDirectorEntry
from .engine.models import ConflictPolicy, Season, SeasonSource, SourceRole, ZoneGate

CONF_NAME = "name"

_ADD = "add_new"
_BACK = "back_to_menu"
_CANCEL = "discard"

_ADD_FALLBACK = {
    "zone": "+ Add zone",
    "source": "+ Add source",
    "circuit": "+ Add circuit",
    "generator": "+ Add heat source",
    "resident": "+ Add resident",
    "window": "+ Add schedule",
    "opening": "+ Add opening",
}

#: Maandag is 0, gelijk aan `datetime.weekday()`, dat de engine ook gebruikt.
#: Monday is 0, matching `datetime.weekday()`, which the engine uses too.
_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

_TEMPERATURE = selector.NumberSelector(
    selector.NumberSelectorConfig(min=-20, max=40, step=0.5, mode=selector.NumberSelectorMode.BOX)
)
_BAND = selector.NumberSelector(
    selector.NumberSelectorConfig(min=0, max=10, step=0.1, mode=selector.NumberSelectorMode.BOX)
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


def _back_option(key: str) -> selector.SelectOptionDict:
    """Return the "back to the main menu" row of a picker.

    De Engelse tekst blijft als terugval staan, net als bij de toevoegregel.
    The English text stays as a fallback, as with the add row.
    """
    return selector.SelectOptionDict(value=_BACK, label="< Back to the main menu")


def _add_option(key: str) -> selector.SelectOptionDict:
    """Return the "add one" row of a picker.

    De Engelse tekst blijft als terugval staan: vertaalt Home Assistant de
    sleutel niet, dan staat er nog altijd iets leesbaars in plaats van niets.

    The English text stays as a fallback: if Home Assistant does not translate
    the key, something readable still shows rather than nothing.
    """
    return selector.SelectOptionDict(value=_ADD, label=_ADD_FALLBACK[key])


class ClimateDirectorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create one installation; everything else happens in the options flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for a name and create an empty installation."""
        if user_input is not None:
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data={},
                options={
                    CONF_INSTALLATION: {},
                    CONF_SHADOW_MODE: user_input[CONF_SHADOW_MODE],
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default="Climate Director"): _TEXT,
                    vol.Required(CONF_SHADOW_MODE, default=DEFAULT_SHADOW_MODE): bool,
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ClimateDirectorEntry) -> OptionsFlow:
        """Return the options flow, where the installation is actually built."""
        return ClimateDirectorOptionsFlow()


class ClimateDirectorOptionsFlow(OptionsFlow):
    """Menu-driven editor for zones, sources, circuits, residents and openings."""

    def __init__(self) -> None:
        """Start with an empty edit cursor."""
        self._installation: dict[str, Any] = {}
        self._shadow_mode: bool | None = None
        # Elke geneste lijst krijgt een eigen cursor. Eén gedeelde cursor laat
        # een bewerking in de ene lijst de plek in de andere verzetten.
        #
        # Every nested list gets its own cursor. One shared cursor lets an edit
        # in one list move the position in another.
        self._zone_index: int | None = None
        self._source_index: int | None = None
        self._circuit_index: int | None = None
        self._priority_zone_id: str | None = None
        self._resident_index: int | None = None
        self._window_index: int | None = None
        self._index: int | None = None

    # -- ingang / entry point ------------------------------------------------

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the main menu."""
        if not self._installation:
            stored = self.config_entry.options.get(CONF_INSTALLATION) or {}
            self._installation = _deep_copy(stored)
        if self._shadow_mode is None:
            self._shadow_mode = self.config_entry.options.get(CONF_SHADOW_MODE, DEFAULT_SHADOW_MODE)

        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "settings",
                "zones",
                "circuits",
                "generators",
                "residents",
                "openings",
                "save",
            ],
        )

    async def async_step_save(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Write the edited installation back to the config entry.

        Everything is written here and nowhere else. Saving a setting halfway
        through would reload the entry while the user is still editing, which
        pulls the ground out from under the flow they are standing in.
        """
        options = dict(self.config_entry.options)
        options[CONF_INSTALLATION] = self._installation
        if self._shadow_mode is not None:
            options[CONF_SHADOW_MODE] = self._shadow_mode
        return self.async_create_entry(data=options)

    # -- algemene instellingen / general settings ----------------------------

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the outdoor sensor, the season source, the gates and shadow mode."""
        if user_input is not None:
            self._installation["outdoor_sensor"] = user_input.get("outdoor_sensor", "")
            self._installation["seasons"] = {
                "source": user_input["season_source"],
                "entity_id": user_input.get("season_entity", ""),
            }
            self._installation["gates"] = {
                "require_awake": user_input["require_awake"],
                "require_schedule": user_input["require_schedule"],
                "guest_window": {
                    "start": user_input.get("guest_start") or "",
                    "end": user_input.get("guest_end") or "",
                },
                "precondition_window": {
                    "start": user_input.get("precondition_start") or "",
                    "end": user_input.get("precondition_end") or "",
                },
                "max_precondition": int(user_input.get("max_precondition") or 0) * 60,
            }
            self._installation["holiday_calendars"] = list(
                user_input.get("holiday_calendars") or ()
            )
            self._installation["holiday_keyword"] = (
                user_input.get("holiday_keyword") or ""
            ).strip()
            self._shadow_mode = user_input[CONF_SHADOW_MODE]
            return await self.async_step_init()

        seasons = self._installation.get("seasons") or {}
        gates = self._installation.get("gates") or {}
        guest = gates.get("guest_window") or {}
        precondition = gates.get("precondition_window") or {}
        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "outdoor_sensor",
                        description={
                            "suggested_value": self._installation.get("outdoor_sensor") or None
                        },
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=["sensor", "weather"])
                    ),
                    vol.Required(
                        "season_source", default=seasons.get("source", SeasonSource.AUTO.value)
                    ): _choices([item.value for item in SeasonSource], "season_source"),
                    vol.Optional(
                        "season_entity",
                        description={"suggested_value": seasons.get("entity_id") or None},
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=["sensor", "input_select", "select"])
                    ),
                    vol.Required("require_awake", default=gates.get("require_awake", True)): bool,
                    vol.Required(
                        "require_schedule", default=gates.get("require_schedule", False)
                    ): bool,
                    vol.Optional(
                        "holiday_calendars",
                        description={
                            "suggested_value": self._installation.get("holiday_calendars") or None
                        },
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="calendar", multiple=True)
                    ),
                    vol.Optional(
                        "precondition_start",
                        description={"suggested_value": precondition.get("start") or "06:00:00"},
                    ): _TIME,
                    vol.Optional(
                        "precondition_end",
                        description={"suggested_value": precondition.get("end") or "23:00:00"},
                    ): _TIME,
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
                    vol.Optional(
                        "holiday_keyword",
                        description={
                            "suggested_value": self._installation.get("holiday_keyword") or None
                        },
                    ): str,
                    vol.Required(
                        CONF_SHADOW_MODE,
                        default=(
                            self._shadow_mode
                            if self._shadow_mode is not None
                            else DEFAULT_SHADOW_MODE
                        ),
                    ): bool,
                }
            ),
        )

    # -- zones ---------------------------------------------------------------

    async def async_step_zones(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pick a zone to edit, or add one."""
        zones = self._list("zones")
        if user_input is not None:
            choice = user_input["zone"]
            if choice == _BACK:
                return await self.async_step_init()
            self._zone_index = None if choice == _ADD else int(choice)
            return await self.async_step_zone()

        options = [
            selector.SelectOptionDict(value=str(index), label=zone.get("name") or zone["zone_id"])
            for index, zone in enumerate(zones)
        ]
        options.append(_add_option("zone"))
        options.append(_back_option("zone"))
        return self.async_show_form(
            step_id="zones",
            data_schema=vol.Schema(
                {
                    vol.Required("zone", default=_ADD): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.LIST,
                            translation_key="zone_list",
                        )
                    )
                }
            ),
        )

    async def async_step_zone(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Edit one zone's comfort settings."""
        zones = self._list("zones")
        current = zones[self._zone_index] if self._zone_index is not None else {}

        errors: dict[str, str] = {}

        if user_input is not None:
            if user_input.get(_CANCEL):
                return await self.async_step_zones()
            if user_input.get("delete") and self._zone_index is not None:
                zones.pop(self._zone_index)
                self._zone_index = None
                return await self.async_step_init()

            zone = _zone_from_form(user_input, current)
            if self._priority_clash(zone["zone_id"], zone["priority"]):
                errors["priority"] = "duplicate_priority"
            if not errors:
                if self._zone_index is None:
                    zones.append(zone)
                    self._zone_index = len(zones) - 1
                else:
                    zones[self._zone_index] = zone
                return await self.async_step_sources()

        heat = current.get("heat") or {}
        cool = current.get("cool") or {}
        priority = current.get("priority", _next_priority(zones))
        return self.async_show_form(
            step_id="zone",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=current.get("name", "")): _TEXT,
                    vol.Required(
                        "indoor_sensor",
                        description={"suggested_value": current.get("indoor_sensor") or None},
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=["sensor", "climate"])
                    ),
                    vol.Required("priority", default=priority): _RANK,
                    vol.Required(
                        "gate", default=current.get("gate", ZoneGate.HOUSEHOLD.value)
                    ): _choices([item.value for item in ZoneGate], "zone_gate"),
                    vol.Optional(
                        "presence_entity",
                        description={"suggested_value": current.get("presence_entity") or None},
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=["binary_sensor", "sensor", "input_boolean"]
                        )
                    ),
                    vol.Required(
                        "presence_state", default=current.get("presence_state", "on")
                    ): _TEXT,
                    vol.Optional(
                        "presence_timeout",
                        description={"suggested_value": current.get("presence_timeout") or None},
                    ): _SECONDS,
                    vol.Required("enable_heat", default=bool(heat)): bool,
                    vol.Required("heat_target", default=heat.get("target", 21.0)): _TEMPERATURE,
                    vol.Required("heat_start_at", default=heat.get("start_at", 20.0)): _TEMPERATURE,
                    vol.Required("heat_hysteresis", default=heat.get("hysteresis", 1.0)): _BAND,
                    vol.Optional(
                        "heat_outdoor_max",
                        description={"suggested_value": (heat.get("outdoor") or {}).get("maximum")},
                    ): _TEMPERATURE,
                    vol.Required("enable_cool", default=bool(cool)): bool,
                    vol.Required("cool_target", default=cool.get("target", 23.0)): _TEMPERATURE,
                    vol.Required("cool_start_at", default=cool.get("start_at", 24.0)): _TEMPERATURE,
                    vol.Required("cool_hysteresis", default=cool.get("hysteresis", 1.0)): _BAND,
                    vol.Optional(
                        "cool_outdoor_min",
                        description={"suggested_value": (cool.get("outdoor") or {}).get("minimum")},
                    ): _TEMPERATURE,
                    vol.Required(
                        "cool_summer_only",
                        default=Season.SUMMER.value in (cool.get("seasons") or []),
                    ): bool,
                    vol.Required("delete", default=False): bool,
                    vol.Required(_CANCEL, default=False): bool,
                }
            ),
        )

    # -- bronnen / sources ---------------------------------------------------

    async def async_step_sources(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a source of the current zone to edit, add one, or go back."""
        zone = self._current_zone()
        if zone is None:
            return await self.async_step_init()
        sources = zone.setdefault("sources", [])

        if user_input is not None:
            choice = user_input["source"]
            if choice == _BACK:
                return await self.async_step_init()
            self._source_index = None if choice == _ADD else int(choice)
            return await self.async_step_source()

        options = [
            selector.SelectOptionDict(value=str(index), label=source["entity_id"])
            for index, source in enumerate(sources)
        ]
        options.append(_add_option("source"))
        options.append(_back_option("source"))
        return self.async_show_form(
            step_id="sources",
            data_schema=vol.Schema(
                {
                    vol.Required("source", default=_ADD): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.LIST,
                            translation_key="source_list",
                        )
                    )
                }
            ),
            description_placeholders={"zone": zone.get("name") or zone["zone_id"]},
        )

    async def async_step_source(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Edit one source of the current zone."""
        zone = self._current_zone()
        if zone is None:
            return await self.async_step_init()
        sources = zone.setdefault("sources", [])
        current = sources[self._source_index] if self._source_index is not None else {}

        if user_input is not None:
            if user_input.get(_CANCEL):
                return await self.async_step_sources()
            if user_input.get("delete") and self._source_index is not None:
                sources.pop(self._source_index)
            else:
                source = {
                    "source_id": current.get("source_id")
                    or _unique_id(
                        f"{zone['zone_id']}_{user_input['entity_id'].split('.')[-1]}",
                        _all_source_ids(self._installation),
                    ),
                    "entity_id": user_input["entity_id"],
                    "role": user_input["role"],
                    "autostart": user_input["autostart"],
                    "priority": int(user_input["priority"]),
                    "outdoor": {
                        "minimum": user_input.get("outdoor_min"),
                        "maximum": user_input.get("outdoor_max"),
                    },
                }
                if self._source_index is None:
                    sources.append(source)
                else:
                    sources[self._source_index] = source
            self._source_index = None
            return await self.async_step_sources()

        outdoor = current.get("outdoor") or {}
        return self.async_show_form(
            step_id="source",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "entity_id",
                        description={"suggested_value": current.get("entity_id") or None},
                    ): _CLIMATE,
                    vol.Required(
                        "role", default=current.get("role", SourceRole.HEAT_COOL.value)
                    ): _choices([item.value for item in SourceRole], "source_role"),
                    vol.Required("autostart", default=current.get("autostart", True)): bool,
                    vol.Required("priority", default=current.get("priority", 0)): _RANK,
                    vol.Optional(
                        "outdoor_min",
                        description={"suggested_value": outdoor.get("minimum")},
                    ): _TEMPERATURE,
                    vol.Optional(
                        "outdoor_max",
                        description={"suggested_value": outdoor.get("maximum")},
                    ): _TEMPERATURE,
                    vol.Required("delete", default=False): bool,
                    vol.Required(_CANCEL, default=False): bool,
                }
            ),
        )

    # -- circuits ------------------------------------------------------------

    async def async_step_circuits(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a refrigerant circuit to edit, or add one."""
        circuits = self._list("circuits")
        if user_input is not None:
            choice = user_input["circuit"]
            if choice == _BACK:
                return await self.async_step_init()
            self._circuit_index = None if choice == _ADD else int(choice)
            return await self.async_step_circuit()

        options = [
            selector.SelectOptionDict(
                value=str(index), label=circuit.get("name") or circuit["circuit_id"]
            )
            for index, circuit in enumerate(circuits)
        ]
        options.append(_add_option("circuit"))
        options.append(_back_option("circuit"))
        return self.async_show_form(
            step_id="circuits",
            data_schema=vol.Schema(
                {
                    vol.Required("circuit", default=_ADD): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.LIST,
                            translation_key="circuit_list",
                        )
                    )
                }
            ),
        )

    async def async_step_circuit(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit one refrigerant circuit."""
        circuits = self._list("circuits")
        current = circuits[self._circuit_index] if self._circuit_index is not None else {}

        if user_input is not None:
            if user_input.get(_CANCEL):
                return await self.async_step_circuits()
            if user_input.get("delete") and self._circuit_index is not None:
                circuits.pop(self._circuit_index)
                self._circuit_index = None
                return await self.async_step_init()

            circuit = {
                "circuit_id": current.get("circuit_id")
                or _unique_id(
                    user_input[CONF_NAME],
                    [item["circuit_id"] for item in circuits],
                ),
                "name": user_input[CONF_NAME],
                "units": user_input["units"],
                "simultaneous_heat_cool": user_input["simultaneous_heat_cool"],
                "conflict_policy": user_input["conflict_policy"],
                "allow_fan_only_during_conflict": user_input["allow_fan_only_during_conflict"],
                "family_switch_delay": user_input["family_switch_delay"],
                "min_family_switch_interval": user_input["min_family_switch_interval"],
                "min_cycle_time": user_input["min_cycle_time"],
                "max_concurrent_units": user_input.get("max_concurrent_units"),
            }
            if self._circuit_index is None:
                circuits.append(circuit)
                self._circuit_index = len(circuits) - 1
            else:
                circuits[self._circuit_index] = circuit
            return await self.async_step_circuit_priorities()

        return self.async_show_form(
            step_id="circuit",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=current.get("name", "")): _TEXT,
                    vol.Required(
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
                    vol.Required(
                        "min_cycle_time", default=current.get("min_cycle_time", 180)
                    ): _SECONDS,
                    vol.Optional(
                        "max_concurrent_units",
                        description={"suggested_value": current.get("max_concurrent_units")},
                    ): _RANK,
                    vol.Required("delete", default=False): bool,
                    vol.Required(_CANCEL, default=False): bool,
                }
            ),
        )

    # -- prioriteiten op een circuit / priorities on a circuit ---------------

    async def async_step_circuit_priorities(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a zone on this circuit whose priority to change, or go back.

        Priority lives on the zone, because that is what it belongs to, but it
        only ever matters on a shared outdoor unit. Reachable from both places,
        writing the same field, so the two can never disagree.
        """
        circuit = self._current_circuit()
        if circuit is None:
            return await self.async_step_init()
        zones = self._zones_on(circuit)

        if user_input is not None:
            choice = user_input["zone"]
            if choice == _BACK:
                return await self.async_step_init()
            self._priority_zone_id = choice
            return await self.async_step_circuit_priority()

        options = [
            selector.SelectOptionDict(
                value=zone["zone_id"],
                label=f"{zone.get('name') or zone['zone_id']} — {zone.get('priority', 0)}",
            )
            for zone in zones
        ]
        options.append(_back_option("circuit_priority"))
        return self.async_show_form(
            step_id="circuit_priorities",
            data_schema=vol.Schema(
                {
                    vol.Required("zone", default=_BACK): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.LIST,
                            translation_key="circuit_priority_list",
                        )
                    )
                }
            ),
            description_placeholders={"circuit": circuit.get("name") or circuit["circuit_id"]},
        )

    async def async_step_circuit_priority(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set one zone's priority from the circuit it sits on."""
        zone = next(
            (item for item in self._list("zones") if item["zone_id"] == self._priority_zone_id),
            None,
        )
        if zone is None:
            self._priority_zone_id = None
            return await self.async_step_circuit_priorities()

        errors: dict[str, str] = {}

        if user_input is not None:
            wanted = int(user_input["priority"])
            if self._priority_clash(zone["zone_id"], wanted):
                errors["priority"] = "duplicate_priority"
            else:
                zone["priority"] = wanted
                self._priority_zone_id = None
                return await self.async_step_circuit_priorities()

        return self.async_show_form(
            step_id="circuit_priority",
            errors=errors,
            data_schema=vol.Schema(
                {vol.Required("priority", default=zone.get("priority", 0)): _RANK}
            ),
            description_placeholders={"zone": zone.get("name") or zone["zone_id"]},
        )

    # -- warmtebronnen / heat generators -------------------------------------

    async def async_step_generators(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a shared heat source to edit, or add one."""
        generators = self._list("generators")
        if user_input is not None:
            choice = user_input["generator"]
            if choice == _BACK:
                return await self.async_step_init()
            self._index = None if choice == _ADD else int(choice)
            return await self.async_step_generator()

        options = [
            selector.SelectOptionDict(
                value=str(index), label=item.get("name") or item["generator_id"]
            )
            for index, item in enumerate(generators)
        ]
        options.append(_add_option("generator"))
        options.append(_back_option("generator"))
        return self.async_show_form(
            step_id="generators",
            data_schema=vol.Schema(
                {
                    vol.Required("generator", default=_ADD): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.LIST,
                            translation_key="generator_list",
                        )
                    )
                }
            ),
        )

    async def async_step_generator(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit one shared heat source."""
        generators = self._list("generators")
        current = generators[self._index] if self._index is not None else {}

        if user_input is not None:
            if user_input.get(_CANCEL):
                return await self.async_step_generators()
            if user_input.get("delete") and self._index is not None:
                generators.pop(self._index)
            else:
                item = {
                    "generator_id": current.get("generator_id")
                    or _unique_id(
                        user_input[CONF_NAME], [entry["generator_id"] for entry in generators]
                    ),
                    "name": user_input[CONF_NAME],
                    "entity_id": user_input["entity_id"],
                    "zone_ids": user_input.get("zone_ids") or [],
                    "setpoint": user_input.get("setpoint"),
                }
                if self._index is None:
                    generators.append(item)
                else:
                    generators[self._index] = item
            self._index = None
            return await self.async_step_init()

        zone_options = [
            selector.SelectOptionDict(
                value=zone["zone_id"], label=zone.get("name") or zone["zone_id"]
            )
            for zone in self._list("zones")
        ]
        return self.async_show_form(
            step_id="generator",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=current.get("name", "")): _TEXT,
                    vol.Required(
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
                        "setpoint", description={"suggested_value": current.get("setpoint")}
                    ): _TEMPERATURE,
                    vol.Required("delete", default=False): bool,
                    vol.Required(_CANCEL, default=False): bool,
                }
            ),
        )

    # -- bewoners / residents ------------------------------------------------

    async def async_step_residents(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a resident to edit, or add one."""
        residents = self._list("residents")
        if user_input is not None:
            choice = user_input["resident"]
            if choice == _BACK:
                return await self.async_step_init()
            self._resident_index = None if choice == _ADD else int(choice)
            return await self.async_step_resident()

        options = [
            selector.SelectOptionDict(
                value=str(index), label=person.get("name") or person["resident_id"]
            )
            for index, person in enumerate(residents)
        ]
        options.append(_add_option("resident"))
        options.append(_back_option("resident"))
        return self.async_show_form(
            step_id="residents",
            data_schema=vol.Schema(
                {
                    vol.Required("resident", default=_ADD): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.LIST,
                            translation_key="resident_list",
                        )
                    )
                }
            ),
        )

    async def async_step_resident(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit one resident."""
        residents = self._list("residents")
        current = residents[self._resident_index] if self._resident_index is not None else {}

        if user_input is not None:
            if user_input.get(_CANCEL):
                return await self.async_step_residents()
            if user_input.get("delete") and self._resident_index is not None:
                residents.pop(self._resident_index)
                self._resident_index = None
                return await self.async_step_init()

            person = {
                "resident_id": current.get("resident_id")
                or _unique_id(
                    user_input[CONF_NAME],
                    [item["resident_id"] for item in residents],
                ),
                "name": user_input[CONF_NAME],
                "presence_entity": user_input["presence_entity"],
                "sleep_entity": user_input.get("sleep_entity", ""),
                "sleep_state": user_input.get("sleep_state") or "on",
                # De roosters van deze bewoner blijven staan; die worden in de
                # volgende stap bewerkt, niet in dit formulier.
                #
                # This resident's schedules are kept; they are edited in the
                # next step, not in this form.
                "windows": current.get("windows") or [],
            }
            if self._resident_index is None:
                residents.append(person)
                self._resident_index = len(residents) - 1
            else:
                residents[self._resident_index] = person
            return await self.async_step_windows()

        return self.async_show_form(
            step_id="resident",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=current.get("name", "")): _TEXT,
                    vol.Required(
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
                        selector.EntitySelectorConfig(
                            domain=["binary_sensor", "sensor", "input_boolean"]
                        )
                    ),
                    vol.Required("sleep_state", default=current.get("sleep_state", "on")): _TEXT,
                    vol.Required("delete", default=False): bool,
                    vol.Required(_CANCEL, default=False): bool,
                }
            ),
        )

    # -- roosters / schedules ------------------------------------------------

    async def async_step_windows(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a schedule window of the current resident, add one, or go back."""
        resident = self._current_resident()
        if resident is None:
            return await self.async_step_init()
        windows = resident.setdefault("windows", [])

        if user_input is not None:
            choice = user_input["window"]
            if choice == _BACK:
                return await self.async_step_init()
            self._window_index = None if choice == _ADD else int(choice)
            return await self.async_step_window()

        options = [
            selector.SelectOptionDict(value=str(index), label=_window_label(window))
            for index, window in enumerate(windows)
        ]
        options.append(_add_option("window"))
        options.append(_back_option("window"))
        return self.async_show_form(
            step_id="windows",
            data_schema=vol.Schema(
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
            ),
            description_placeholders={"resident": resident.get("name") or resident["resident_id"]},
        )

    async def async_step_window(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Edit one schedule window."""
        resident = self._current_resident()
        if resident is None:
            return await self.async_step_init()
        windows = resident.setdefault("windows", [])
        current = windows[self._window_index] if self._window_index is not None else {}

        if user_input is not None:
            if user_input.get(_CANCEL):
                return await self.async_step_windows()
            if user_input.get("delete") and self._window_index is not None:
                windows.pop(self._window_index)
            else:
                window = {
                    "start": user_input["start"],
                    "end": user_input["end"],
                    # Geen dagen aangevinkt betekent elke dag, niet nooit. Een
                    # rooster zonder dagen zou de bewoner permanent buitensluiten.
                    #
                    # No days ticked means every day, not never. A schedule with
                    # no days would lock the resident out permanently.
                    "weekdays": ([int(day) for day in user_input.get("weekdays") or ()] or None),
                    "holiday": user_input.get("holiday", False),
                }
                if self._window_index is None:
                    windows.append(window)
                else:
                    windows[self._window_index] = window
            self._window_index = None
            return await self.async_step_windows()

        weekdays = current.get("weekdays")
        return self.async_show_form(
            step_id="window",
            data_schema=vol.Schema(
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
                        )
                    ),
                    vol.Required("delete", default=False): bool,
                    vol.Required(_CANCEL, default=False): bool,
                }
            ),
        )

    # -- openingen / openings ------------------------------------------------

    async def async_step_openings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick an opening to edit, or add one."""
        openings = self._list("openings")
        if user_input is not None:
            choice = user_input["opening"]
            if choice == _BACK:
                return await self.async_step_init()
            self._index = None if choice == _ADD else int(choice)
            return await self.async_step_opening()

        options = [
            selector.SelectOptionDict(value=str(index), label=opening["entity_id"])
            for index, opening in enumerate(openings)
        ]
        options.append(_add_option("opening"))
        options.append(_back_option("opening"))
        return self.async_show_form(
            step_id="openings",
            data_schema=vol.Schema(
                {
                    vol.Required("opening", default=_ADD): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.LIST,
                            translation_key="opening_list",
                        )
                    )
                }
            ),
        )

    async def async_step_opening(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit one opening."""
        openings = self._list("openings")
        current = openings[self._index] if self._index is not None else {}

        if user_input is not None:
            if user_input.get(_CANCEL):
                return await self.async_step_openings()
            if user_input.get("delete") and self._index is not None:
                openings.pop(self._index)
            else:
                opening = {
                    "entity_id": user_input["entity_id"],
                    "zone_ids": user_input.get("zone_ids") or [],
                    "delay": user_input.get("delay") or 0,
                }
                if self._index is None:
                    openings.append(opening)
                else:
                    openings[self._index] = opening
            self._index = None
            return await self.async_step_init()

        zone_options = [
            selector.SelectOptionDict(
                value=zone["zone_id"], label=zone.get("name") or zone["zone_id"]
            )
            for zone in self._list("zones")
        ]
        return self.async_show_form(
            step_id="opening",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "entity_id",
                        description={"suggested_value": current.get("entity_id") or None},
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=["binary_sensor", "cover", "sensor"])
                    ),
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
                    vol.Required(_CANCEL, default=False): bool,
                }
            ),
        )

    # -- hulpjes / helpers ---------------------------------------------------

    def _list(self, key: str) -> list[dict[str, Any]]:
        """Return the editable list stored under `key`, creating it if needed."""
        return self._installation.setdefault(key, [])

    def _priority_clash(self, zone_id: str, priority: int) -> bool:
        """Return whether another zone on the same circuit already holds this number.

        Only zones sharing an outdoor unit are checked. Rooms on separate
        circuits never compete, so making them pick different numbers would be
        an obstacle without a reason behind it.
        """
        for circuit in self._list("circuits"):
            units = set(circuit.get("units") or ())
            on_it = [
                zone
                for zone in self._list("zones")
                if any(source.get("entity_id") in units for source in zone.get("sources") or ())
            ]
            if not any(zone["zone_id"] == zone_id for zone in on_it):
                continue
            if any(
                zone["zone_id"] != zone_id and zone.get("priority") == priority for zone in on_it
            ):
                return True
        return False

    def _current_circuit(self) -> dict[str, Any] | None:
        """Return the circuit being edited, or `None` when the cursor is stale."""
        circuits = self._list("circuits")
        if self._circuit_index is None or not 0 <= self._circuit_index < len(circuits):
            return None
        return circuits[self._circuit_index]

    def _zones_on(self, circuit: dict[str, Any]) -> list[dict[str, Any]]:
        """Return the zones with a source on this circuit, most preferred first."""
        units = set(circuit.get("units") or ())
        on_it = [
            zone
            for zone in self._list("zones")
            if any(source.get("entity_id") in units for source in zone.get("sources") or ())
        ]
        return sorted(on_it, key=lambda zone: (zone.get("priority", 0), zone["zone_id"]))

    def _current_resident(self) -> dict[str, Any] | None:
        """Return the resident being edited, or `None` when the cursor is stale."""
        residents = self._list("residents")
        if self._resident_index is None or not 0 <= self._resident_index < len(residents):
            return None
        return residents[self._resident_index]

    def _current_zone(self) -> dict[str, Any] | None:
        """Return the zone being edited, or `None` when the cursor is stale.

        A stale cursor sends the user back to the menu rather than raising:
        a config flow that crashes leaves a half-built installation behind with
        no way back into it.
        """
        zones = self._list("zones")
        if self._zone_index is None or not 0 <= self._zone_index < len(zones):
            return None
        return zones[self._zone_index]


def _zone_from_form(user_input: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Return the stored zone described by a submitted zone form."""
    heat = (
        {
            "target": user_input["heat_target"],
            "start_at": user_input["heat_start_at"],
            "hysteresis": user_input["heat_hysteresis"],
            "outdoor": {"minimum": None, "maximum": user_input.get("heat_outdoor_max")},
            "seasons": None,
        }
        if user_input["enable_heat"]
        else None
    )
    cool = (
        {
            "target": user_input["cool_target"],
            "start_at": user_input["cool_start_at"],
            "hysteresis": user_input["cool_hysteresis"],
            "outdoor": {"minimum": user_input.get("cool_outdoor_min"), "maximum": None},
            "seasons": [Season.SUMMER.value] if user_input["cool_summer_only"] else None,
        }
        if user_input["enable_cool"]
        else None
    )
    return {
        "zone_id": current.get("zone_id") or slugify(user_input[CONF_NAME]) or "zone",
        "name": user_input[CONF_NAME],
        "indoor_sensor": user_input["indoor_sensor"],
        "priority": int(user_input["priority"]),
        "sources": current.get("sources") or [],
        "heat": heat,
        "cool": cool,
        "gate": user_input.get("gate") or ZoneGate.HOUSEHOLD.value,
        "presence_entity": user_input.get("presence_entity") or "",
        "presence_state": user_input.get("presence_state") or "on",
        "presence_timeout": user_input.get("presence_timeout") or 0,
    }


def _next_priority(zones: list[dict[str, Any]]) -> int:
    """Return the priority a newly added zone should start on.

    Every zone defaulting to zero would leave them all tied, and a tie falls
    back on the zone id - so the room that happens to come first alphabetically
    would quietly win every circuit. Counting up instead means the order rooms
    are added in is the order they win in, which is both predictable and easy
    to correct.
    """
    used = [
        zone["priority"]
        for zone in zones
        if isinstance(zone.get("priority"), int) and not isinstance(zone.get("priority"), bool)
    ]
    return max(used) + 1 if used else 0


def _window_label(window: dict[str, Any]) -> str:
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
        return f"{start} - {end}, every day"
    return f"{start} - {end}, {', '.join(_WEEKDAYS[day][:3] for day in sorted(weekdays))}"


def _all_source_ids(installation: dict[str, Any]) -> list[str]:
    """Return every source id in use, so a new one can avoid them."""
    return [
        source["source_id"]
        for zone in installation.get("zones") or []
        for source in zone.get("sources") or []
        if "source_id" in source
    ]


def _unique_id(name: str, taken: list[str]) -> str:
    """Return a slug of `name` that is not in `taken`."""
    base = slugify(name) or "item"
    if base not in taken:
        return base
    index = 2
    while f"{base}_{index}" in taken:
        index += 1
    return f"{base}_{index}"


def _deep_copy(value: Any) -> Any:
    """Return a mutable deep copy of stored options.

    Config entry options are shared, immutable-by-convention structures; editing
    them in place would change the running configuration before the user has
    pressed save, and would leave a half-edited installation behind if they
    abandoned the flow.
    """
    if isinstance(value, dict):
        return {key: _deep_copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_deep_copy(item) for item in value]
    return value
