"""De generatorstappen. / The generator steps."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigFlowResult

from . import schemas

if TYPE_CHECKING:
    from .config_flow import ClimateDirectorOptionsFlow

from .flow_validation import (
    blank_to_none,
    missing,
    unique_id,
)
from .schemas import ADD, BACK, CONF_NAME, EXIT, EXIT_DROP
from .units import temperature_unit_of, to_celsius


async def generators(
    flow: ClimateDirectorOptionsFlow, user_input: dict[str, Any] | None = None
) -> ConfigFlowResult:
    """Pick a shared heat source to edit, or add one."""
    if user_input is not None:
        choice = user_input["generator"]
        if choice == BACK:
            return await flow.async_step_init()
        flow._index = None if choice == ADD else int(choice)
        return await flow.async_step_generator()

    return flow.async_show_form(
        step_id="generators",
        data_schema=schemas.generators(flow),
    )


async def generator(
    flow: ClimateDirectorOptionsFlow, user_input: dict[str, Any] | None = None
) -> ConfigFlowResult:
    """Edit one shared heat source."""
    generators = flow._list("generators")
    current = generators[flow._index] if flow._index is not None else {}

    errors: dict[str, str] = {}

    if user_input is not None:
        if user_input.get(EXIT) == EXIT_DROP:
            return await flow.async_step_generators()
        if not user_input.get("delete"):
            errors = missing(user_input, "entity_id")
        if errors:
            current = {**current, **user_input}

    if user_input is not None and not errors:
        if user_input.get("delete") and flow._index is not None:
            generators.pop(flow._index)
        else:
            item = {
                "generator_id": current.get("generator_id")
                or unique_id(
                    user_input[CONF_NAME], [entry["generator_id"] for entry in generators]
                ),
                "name": user_input[CONF_NAME],
                "entity_id": user_input["entity_id"],
                "zone_ids": user_input.get("zone_ids") or [],
                "setpoint": to_celsius(
                    blank_to_none(user_input.get("setpoint")), temperature_unit_of(flow.hass)
                ),
            }
            if flow._index is None:
                generators.append(item)
            else:
                generators[flow._index] = item
        flow._index = None
        return await flow.async_step_init()

    return flow.async_show_form(
        step_id="generator",
        errors=errors,
        data_schema=schemas.generator(flow, current),
    )
