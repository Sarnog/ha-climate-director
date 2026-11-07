"""De circuit- en generatorschermen. / The circuit and generator screens."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.helpers import selector

from .engine.models import ConflictPolicy
from .form_common import (
    ADD,
    BACK,
    CONF_NAME,
    EXIT,
    EXIT_KEEP,
    add_option,
    back_option,
    exit_row,
)
from .schema_fields import (
    CLIMATE,
    CLIMATE_MULTI,
    RANK,
    SECONDS,
    TEXT,
    choices,
    temperature,
)
from .units import rounded_from_celsius, temperature_unit_of


def circuits(flow: Any) -> vol.Schema:
    """Return the circuit picker schema."""
    circuits = flow._list("circuits")
    options = [
        selector.SelectOptionDict(
            value=str(index), label=circuit.get("name") or circuit["circuit_id"]
        )
        for index, circuit in enumerate(circuits)
    ]
    options.append(add_option("circuit"))
    options.append(back_option())
    return vol.Schema(
        {
            vol.Required("circuit", default=ADD): selector.SelectSelector(
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
            vol.Required(CONF_NAME, default=current.get("name", "")): TEXT,
            vol.Optional(
                "units", description={"suggested_value": current.get("units") or []}
            ): CLIMATE_MULTI,
            vol.Required(
                "simultaneous_heat_cool",
                default=current.get("simultaneous_heat_cool", False),
            ): bool,
            vol.Required(
                "conflict_policy",
                default=current.get("conflict_policy", ConflictPolicy.PRIORITY.value),
            ): choices([item.value for item in ConflictPolicy], "conflict_policy"),
            vol.Required(
                "allow_fan_only_during_conflict",
                default=current.get("allow_fan_only_during_conflict", False),
            ): bool,
            vol.Required(
                "family_switch_delay", default=current.get("family_switch_delay", 0)
            ): SECONDS,
            vol.Required(
                "min_family_switch_interval",
                default=current.get("min_family_switch_interval", 0),
            ): SECONDS,
            vol.Required("min_cycle_time", default=current.get("min_cycle_time", 180)): SECONDS,
            vol.Optional(
                "max_concurrent_units",
                description={"suggested_value": current.get("max_concurrent_units")},
            ): RANK,
            vol.Required("delete", default=False): bool,
            vol.Required(EXIT, default=EXIT_KEEP): exit_row(),
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
    options.append(back_option())
    return vol.Schema(
        {
            vol.Required("zone", default=BACK): selector.SelectSelector(
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
            vol.Required("priority", default=zone.get("priority", 0)): RANK,
            vol.Required(EXIT, default=EXIT_KEEP): exit_row(),
        }
    )


def generators(flow: Any) -> vol.Schema:
    """Return the shared-heat-source picker schema."""
    generators = flow._list("generators")
    options = [
        selector.SelectOptionDict(value=str(index), label=item.get("name") or item["generator_id"])
        for index, item in enumerate(generators)
    ]
    options.append(add_option("generator"))
    options.append(back_option())
    return vol.Schema(
        {
            vol.Required("generator", default=ADD): selector.SelectSelector(
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
            vol.Required(CONF_NAME, default=current.get("name", "")): TEXT,
            vol.Optional(
                "entity_id",
                description={"suggested_value": current.get("entity_id") or None},
            ): CLIMATE,
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
            ): temperature(unit),
            vol.Required("delete", default=False): bool,
            vol.Required(EXIT, default=EXIT_KEEP): exit_row(),
        }
    )
