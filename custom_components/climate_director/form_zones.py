"""De zoneschermen. / The zone screens."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.helpers import selector

from .engine.fields import SOURCE_FIELDS
from .engine.models import Season, ZoneGate
from .form_common import (
    ADD,
    CONF_NAME,
    EXIT,
    EXIT_KEEP,
    add_option,
    back_option,
    exit_row,
)
from .schema_fields import (
    RANK,
    SECONDS,
    TEXT,
    band,
    choices,
    table_schema,
    temperature,
)
from .units import rounded_delta_from_celsius, rounded_from_celsius, temperature_unit_of


def zones(flow: Any) -> vol.Schema:
    """Return the zone picker schema."""
    zones = flow._list("zones")
    options = [
        selector.SelectOptionDict(value=str(index), label=zone.get("name") or zone["zone_id"])
        for index, zone in enumerate(zones)
    ]
    options.append(add_option("zone"))
    options.append(back_option())
    return vol.Schema(
        {
            vol.Required("zone", default=ADD): selector.SelectSelector(
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
            vol.Required(CONF_NAME, default=current.get("name", "")): TEXT,
            vol.Optional(
                "indoor_sensor",
                description={"suggested_value": current.get("indoor_sensor") or None},
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain=["sensor", "climate"])),
            vol.Required("priority", default=priority): RANK,
            vol.Required("gate", default=current.get("gate", ZoneGate.HOUSEHOLD.value)): choices(
                [item.value for item in ZoneGate], "zone_gate"
            ),
            vol.Optional(
                "presence_entity",
                description={"suggested_value": current.get("presence_entity") or None},
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["binary_sensor", "sensor", "input_boolean"])
            ),
            vol.Required("presence_state", default=current.get("presence_state", "on")): TEXT,
            vol.Optional(
                "presence_timeout",
                description={"suggested_value": current.get("presence_timeout") or None},
            ): SECONDS,
            vol.Required(
                "ignore_precipitation",
                default=current.get("ignore_precipitation", False),
            ): bool,
            vol.Required("enable_heat", default=bool(heat)): bool,
            vol.Required(
                "heat_target", default=rounded_from_celsius(heat.get("target", 21.0), unit)
            ): temperature(unit),
            vol.Required(
                "heat_start_at",
                default=rounded_from_celsius(heat.get("start_at", 20.0), unit),
            ): temperature(unit),
            vol.Required(
                "heat_hysteresis",
                default=rounded_delta_from_celsius(heat.get("hysteresis", 1.0), unit),
            ): band(unit),
            vol.Optional(
                "heat_outdoor_max",
                description={
                    "suggested_value": rounded_from_celsius(
                        (heat.get("outdoor") or {}).get("maximum"), unit
                    )
                },
            ): temperature(unit),
            vol.Required("enable_cool", default=bool(cool)): bool,
            vol.Required(
                "cool_target", default=rounded_from_celsius(cool.get("target", 23.0), unit)
            ): temperature(unit),
            vol.Required(
                "cool_start_at",
                default=rounded_from_celsius(cool.get("start_at", 24.0), unit),
            ): temperature(unit),
            vol.Required(
                "cool_hysteresis",
                default=rounded_delta_from_celsius(cool.get("hysteresis", 1.0), unit),
            ): band(unit),
            vol.Optional(
                "cool_outdoor_min",
                description={
                    "suggested_value": rounded_from_celsius(
                        (cool.get("outdoor") or {}).get("minimum"), unit
                    )
                },
            ): temperature(unit),
            vol.Required(
                "cool_summer_only",
                default=Season.SUMMER.value in (cool.get("seasons") or []),
            ): bool,
            vol.Required("delete", default=False): bool,
            vol.Required(EXIT, default=EXIT_KEEP): exit_row(),
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
    options.append(add_option("source"))
    options.append(back_option())
    return vol.Schema(
        {
            vol.Required("source", default=ADD): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    mode=selector.SelectSelectorMode.LIST,
                    translation_key="source_list",
                )
            )
        }
    )


def source(flow: Any, current: dict[str, Any]) -> vol.Schema:
    """Return the single source schema, read from the field table.

    De veldenlijst staat in `engine.fields.SOURCE_FIELDS`; de waardebron is de
    bron die bewerkt wordt. De verwijderregel en de afsluitregel horen bij de
    vorm van een lijst-itemscherm en niet bij de velden, dus die komen als
    voettekst mee.

    The field list lives in `engine.fields.SOURCE_FIELDS`; the value source is
    the source being edited. The delete row and the exit row belong to the shape
    of a list-item screen rather than to the fields, so they come along as a
    footer.
    """
    return table_schema(
        SOURCE_FIELDS,
        flow,
        values=current,
        footer={
            vol.Required("delete", default=False): bool,
            vol.Required(EXIT, default=EXIT_KEEP): exit_row(),
        },
    )
