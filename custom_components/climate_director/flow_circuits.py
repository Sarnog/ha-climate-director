"""De circuitstappen. / The circuit steps."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlowResult

from . import schemas
from .flow_surface import FlowSurface
from .flow_validation import (
    blank_to_none,
    missing,
    unique_id,
)
from .schemas import ADD, BACK, CONF_NAME, EXIT, EXIT_DROP


async def circuits(flow: FlowSurface, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
    """Pick a refrigerant circuit to edit, or add one."""
    if user_input is not None:
        choice = user_input["circuit"]
        if choice == BACK:
            return await flow.async_step_init()
        flow._circuit_index = None if choice == ADD else int(choice)
        return await flow.async_step_circuit()

    return flow.async_show_form(
        step_id="circuits",
        data_schema=schemas.circuits(flow),
    )


async def circuit(flow: FlowSurface, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
    """Edit one refrigerant circuit."""
    circuits = flow._list("circuits")
    current = circuits[flow._circuit_index] if flow._circuit_index is not None else {}

    errors: dict[str, str] = {}

    if user_input is not None:
        if user_input.get(EXIT) == EXIT_DROP:
            return await flow.async_step_circuits()
        if not user_input.get("delete"):
            errors = missing(user_input, "units")
        if errors:
            current = {**current, **user_input}

    if user_input is not None and not errors:
        if user_input.get("delete") and flow._circuit_index is not None:
            circuits.pop(flow._circuit_index)
            flow._circuit_index = None
            return await flow.async_step_init()

        circuit = {
            "circuit_id": current.get("circuit_id")
            or unique_id(
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
            "max_concurrent_units": blank_to_none(user_input.get("max_concurrent_units")),
        }
        if flow._circuit_index is None:
            circuits.append(circuit)
            flow._circuit_index = len(circuits) - 1
        else:
            circuits[flow._circuit_index] = circuit
        return await flow.async_step_circuit_priorities()

    return flow.async_show_form(
        step_id="circuit",
        errors=errors,
        data_schema=schemas.circuit(current),
    )


async def circuit_priorities(
    flow: FlowSurface, user_input: dict[str, Any] | None = None
) -> ConfigFlowResult:
    """Pick a zone on this circuit whose priority to change, or go back.

    Priority lives on the zone, because that is what it belongs to, but it
    only ever matters on a shared outdoor unit. Reachable from both places,
    writing the same field, so the two can never disagree.
    """
    circuit = flow._current_circuit()
    if circuit is None:
        return await flow.async_step_init()
    if user_input is not None:
        choice = user_input["zone"]
        if choice == BACK:
            return await flow.async_step_init()
        flow._priority_zone_id = choice
        return await flow.async_step_circuit_priority()

    return flow.async_show_form(
        step_id="circuit_priorities",
        data_schema=schemas.circuit_priorities(flow),
        description_placeholders={"circuit": circuit.get("name") or circuit["circuit_id"]},
    )


async def circuit_priority(
    flow: FlowSurface, user_input: dict[str, Any] | None = None
) -> ConfigFlowResult:
    """Set one zone's priority from the circuit it sits on."""
    zone = next(
        (item for item in flow._list("zones") if item["zone_id"] == flow._priority_zone_id),
        None,
    )
    if zone is None:
        flow._priority_zone_id = None
        return await flow.async_step_circuit_priorities()

    errors: dict[str, str] = {}

    if user_input is not None:
        if user_input.get(EXIT) == EXIT_DROP:
            return await flow.async_step_circuit_priorities()
        wanted = int(user_input["priority"])
        if flow._priority_clash(zone["zone_id"], wanted):
            errors["priority"] = "duplicate_priority"
        else:
            zone["priority"] = wanted
            flow._priority_zone_id = None
            return await flow.async_step_circuit_priorities()

    return flow.async_show_form(
        step_id="circuit_priority",
        errors=errors,
        data_schema=schemas.circuit_priority(zone),
        description_placeholders={"zone": zone.get("name") or zone["zone_id"]},
    )
