"""De vensterstappen. / The window steps."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config_flow import ClimateDirectorOptionsFlow

from homeassistant.config_entries import ConfigFlowResult

from . import schemas, texts
from .schemas import ADD, BACK, EXIT, EXIT_DROP


async def windows(
    flow: ClimateDirectorOptionsFlow, user_input: dict[str, Any] | None = None
) -> ConfigFlowResult:
    """Pick a schedule window of the current resident, add one, or go back."""
    resident = flow._current_resident()
    if resident is None:
        return await flow.async_step_init()
    if user_input is not None:
        choice = user_input["window"]
        if choice == BACK:
            return await flow.async_step_init()
        flow._window_index = None if choice == ADD else int(choice)
        return await flow.async_step_window()

    selector_texts = await texts.async_selector_texts(flow.hass)
    return flow.async_show_form(
        step_id="windows",
        data_schema=schemas.windows(flow, selector_texts),
        description_placeholders={"resident": resident.get("name") or resident["resident_id"]},
    )


async def window(
    flow: ClimateDirectorOptionsFlow, user_input: dict[str, Any] | None = None
) -> ConfigFlowResult:
    """Edit one schedule window."""
    resident = flow._current_resident()
    if resident is None:
        return await flow.async_step_init()
    windows = resident.setdefault("windows", [])
    current = windows[flow._window_index] if flow._window_index is not None else {}

    if user_input is not None:
        if user_input.get(EXIT) == EXIT_DROP:
            return await flow.async_step_windows()
        if user_input.get("delete") and flow._window_index is not None:
            windows.pop(flow._window_index)
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
            if flow._window_index is None:
                windows.append(window)
            else:
                windows[flow._window_index] = window
        flow._window_index = None
        return await flow.async_step_windows()

    return flow.async_show_form(
        step_id="window",
        data_schema=schemas.window(current),
    )
