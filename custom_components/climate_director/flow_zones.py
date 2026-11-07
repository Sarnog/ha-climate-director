"""De zonestappen. / The zone steps."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigFlowResult

from . import schemas

if TYPE_CHECKING:
    from .config_flow import ClimateDirectorOptionsFlow

from .flow_validation import (
    heat_cool_from_form,
    missing,
    next_priority,
    zone_errors,
    zone_from_form,
)
from .schemas import ADD, BACK, EXIT, EXIT_DROP
from .units import temperature_unit_of


async def zones(
    flow: ClimateDirectorOptionsFlow, user_input: dict[str, Any] | None = None
) -> ConfigFlowResult:
    """Pick a zone to edit, or add one."""
    if user_input is not None:
        choice = user_input["zone"]
        if choice == BACK:
            return await flow.async_step_init()
        flow._zone_index = None if choice == ADD else int(choice)
        return await flow.async_step_zone()

    return flow.async_show_form(
        step_id="zones",
        data_schema=schemas.zones(flow),
    )


async def zone(
    flow: ClimateDirectorOptionsFlow, user_input: dict[str, Any] | None = None
) -> ConfigFlowResult:
    """Edit one zone's comfort settings."""
    zones = flow._list("zones")
    current = zones[flow._zone_index] if flow._zone_index is not None else {}
    stored_id = current.get("zone_id") if flow._zone_index is not None else None

    errors: dict[str, str] = {}

    if user_input is not None:
        if user_input.get(EXIT) == EXIT_DROP:
            return await flow.async_step_zones()
        if not user_input.get("delete"):
            errors = missing(user_input, "indoor_sensor")
        if errors:
            current = {**current, **user_input}
            # De defaults lezen `current.get("heat")`/`current.get("cool")`,
            # en die sleutels zitten niet in `user_input`. Zonder deze stap
            # toonde het formulier na een fout de nieuwe naam naast de oude
            # temperaturen.
            #
            # The defaults read `current.get("heat")`/`current.get("cool")`,
            # and those keys are not in `user_input`. Without this step the
            # form showed the new name beside the old temperatures after an
            # error.
            current["heat"], current["cool"] = heat_cool_from_form(
                user_input, current, unit=temperature_unit_of(flow.hass)
            )

    if user_input is not None and not errors:
        if user_input.get("delete") and flow._zone_index is not None:
            removed = zones.pop(flow._zone_index)
            flow._zone_index = None
            flow._drop_zone_references(removed)
            return await flow.async_step_init()

        taken: list[str] = [
            str(item["zone_id"])
            for index, item in enumerate(zones)
            if index != flow._zone_index and item.get("zone_id")
        ]
        zone = zone_from_form(
            user_input,
            current,
            taken,
            stored_id=stored_id,
            unit=temperature_unit_of(flow.hass),
        )
        errors |= zone_errors(zone)
        if flow._priority_clash(zone["zone_id"], zone["priority"]):
            errors["priority"] = "duplicate_priority"
        if errors:
            # Het formulier komt terug met wat er ingevuld stónd, niet met
            # wat er stond voordat je begon. Anders wijst de melding een
            # veld aan dat inmiddels weer zijn oude waarde toont, en zoek
            # je naar een fout die er niet meer lijkt te zijn.
            #
            # The form comes back with what was filled in, not with what
            # stood there before you started. Otherwise the complaint points
            # at a field that has reverted to its old value, and you go
            # looking for a mistake that no longer appears to be there.
            current = zone
        if not errors:
            if flow._zone_index is None:
                zones.append(zone)
                flow._zone_index = len(zones) - 1
            else:
                zones[flow._zone_index] = zone
            return await flow.async_step_sources()

    priority = current.get("priority", next_priority(zones))
    return flow.async_show_form(
        step_id="zone",
        errors=errors,
        data_schema=schemas.zone(flow, current, priority),
    )
