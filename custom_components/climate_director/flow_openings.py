"""De openingstappen. / The opening steps."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlowResult

from . import schemas
from .flow_surface import FlowSurface
from .flow_validation import (
    missing,
    unique_id,
)
from .schemas import ADD, BACK, CONF_NAME, EXIT, EXIT_DROP


async def openings(flow: FlowSurface, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
    """Pick an opening to edit, or add one, and set the house-wide stops."""
    if user_input is not None:
        # De huisbrede lijst hoort bij dit scherm en niet bij een losse
        # opening: hij hangt aan het apparaat, zodat een raam dat er later
        # bij komt vanzelf meetelt. Hij wordt daarom bij elke uitgang van
        # dit scherm weggeschreven, ook als je alleen doorklikt naar een
        # opening - anders was de keuze weg zodra je er nog iets naast deed.
        #
        # The house-wide list belongs to this screen rather than to a single
        # opening: it hangs on the appliance, so a window added later counts
        # by itself. It is therefore written on every way out of this
        # screen, including clicking through to an opening - otherwise the
        # choice would be gone the moment you did anything else beside it.
        flow._installation["house_wide_openings"] = list(
            user_input.get("house_wide_openings") or ()
        )
        choice = user_input["opening"]
        if choice == BACK:
            return await flow.async_step_init()
        flow._index = None if choice == ADD else int(choice)
        return await flow.async_step_opening()

    return flow.async_show_form(
        step_id="openings",
        data_schema=schemas.openings(flow),
    )


async def opening(flow: FlowSurface, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
    """Edit one opening."""
    openings = flow._list("openings")
    current = openings[flow._index] if flow._index is not None else {}

    errors: dict[str, str] = {}

    if user_input is not None:
        if user_input.get(EXIT) == EXIT_DROP:
            return await flow.async_step_openings()
        if not user_input.get("delete"):
            errors = missing(user_input, "entity_id", CONF_NAME)
        if errors:
            current = {**current, **user_input}

    if user_input is not None and not errors:
        if user_input.get("delete") and flow._index is not None:
            openings.pop(flow._index)
        else:
            opening = {
                "opening_id": current.get("opening_id")
                or unique_id(
                    user_input[CONF_NAME],
                    [str(entry.get("opening_id") or "") for entry in openings],
                ),
                "name": user_input[CONF_NAME],
                "entity_id": user_input["entity_id"],
                "zone_ids": user_input.get("zone_ids") or [],
                "open_state": user_input.get("open_state") or "on",
                "delay": user_input.get("delay") or 0,
            }
            if flow._index is None:
                openings.append(opening)
            else:
                openings[flow._index] = opening
        flow._index = None
        return await flow.async_step_init()

    return flow.async_show_form(
        step_id="opening",
        errors=errors,
        data_schema=schemas.opening(flow, current),
    )
