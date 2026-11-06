"""De installatiestappen. / The installation steps."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigFlowResult

from . import schemas, texts
from .engine.fields import SETTINGS_FIELDS

if TYPE_CHECKING:
    from .config_flow import ClimateDirectorOptionsFlow

from .flow_validation import (
    settings_errors,
)
from .schema_fields import write_table
from .schemas import ADD, BACK, EXIT, EXIT_DROP


async def settings(
    flow: ClimateDirectorOptionsFlow, user_input: dict[str, Any] | None = None
) -> ConfigFlowResult:
    """Edit the outdoor sensor, the season source, the gates and shadow mode."""
    if user_input is not None:
        if user_input.get(EXIT) == EXIT_DROP:
            return await flow.async_step_init()
        errors = settings_errors(user_input)
        if errors:
            return flow.async_show_form(
                step_id="settings",
                data_schema=schemas.settings(flow),
                errors=errors,
            )
        # Elke rij van de tabel schrijft zichzelf terug naar haar puntpad;
        # de eigenzinnige velden (zomermaanden, neerslagstanden, het
        # vakantietrefwoord en de schaduwmodus) dragen daarvoor een `hook`
        # in `engine/fields.py`. Optionele velden worden daar bewust leeg
        # gelezen: de echte HA-interface stuurt een voorgevulde selector mee
        # bij het opslaan, dus alleen een leeggemaakt veld komt leeg binnen.
        # Wie daar "afwezig = bewaren" van maakt, blokkeert het leegmaken
        # van de buitensensor en de neerslagbron.
        #
        # Every row of the table writes itself back to its dotted path; the
        # idiosyncratic fields (summer months, precipitation states, the
        # holiday keyword and shadow mode) carry a `hook` in
        # `engine/fields.py` for that. Optional fields are deliberately read
        # as empty there: the real HA frontend submits a pre-filled selector
        # on save, so only a field the user cleared arrives empty. Turning
        # that into "absent = keep" would stop users from clearing the
        # outdoor sensor and the precipitation source.
        #
        # `gates` wordt daarbij bijgewerkt en niet vervangen: het
        # stiltevensterscherm schrijft in dezelfde sleutel
        # (`quiet_windows`), en een compleet nieuw dict zou dat werk
        # stilletjes wissen.
        #
        # `gates` is updated rather than replaced along the way: the quiet
        # window screen writes into the same key (`quiet_windows`), and a
        # brand-new dict would silently erase that work.
        write_table(SETTINGS_FIELDS, user_input, flow._installation, flow=flow)
        # Het vooruit-venster bestaat niet meer. Een installatie die het
        # ooit opsloeg houdt de dode sleutel niet langer vast zodra er hier
        # iets gewijzigd wordt.
        #
        # The pre-conditioning window no longer exists. An installation
        # that once stored it no longer keeps the dead key once anything is
        # changed here.
        flow._installation.setdefault("gates", {}).pop("precondition_window", None)
        return await flow.async_step_init()

    return flow.async_show_form(
        step_id="settings",
        data_schema=schemas.settings(flow),
    )


async def exclusives(
    flow: ClimateDirectorOptionsFlow, user_input: dict[str, Any] | None = None
) -> ConfigFlowResult:
    """Pick an exclusive group to edit, or add one."""
    if user_input is not None:
        choice = user_input["group"]
        if choice == BACK:
            return await flow.async_step_init()
        flow._index = None if choice == ADD else int(choice)
        return await flow.async_step_exclusive()

    return flow.async_show_form(
        step_id="exclusives",
        data_schema=schemas.exclusives(flow),
    )


async def exclusive(
    flow: ClimateDirectorOptionsFlow, user_input: dict[str, Any] | None = None
) -> ConfigFlowResult:
    """Edit one exclusive group: the sources that may never run together."""
    groups = flow._groups()
    current: list[str] = groups[flow._index] if flow._index is not None else []

    errors: dict[str, str] = {}

    if user_input is not None:
        if user_input.get(EXIT) == EXIT_DROP:
            return await flow.async_step_exclusives()
        if user_input.get("delete") and flow._index is not None:
            groups.pop(flow._index)
            flow._index = None
            return await flow.async_step_exclusives()
        chosen = list(user_input.get("sources") or ())
        if len(chosen) < 2:
            errors["sources"] = "too_few"
        else:
            if flow._index is None:
                groups.append(chosen)
            else:
                groups[flow._index] = chosen
            flow._index = None
            return await flow.async_step_exclusives()
        current = chosen

    return flow.async_show_form(
        step_id="exclusive",
        errors=errors,
        data_schema=schemas.exclusive(flow, current),
    )


async def quiets(
    flow: ClimateDirectorOptionsFlow, user_input: dict[str, Any] | None = None
) -> ConfigFlowResult:
    """Pick a quiet window to edit, add one, or go back."""
    if user_input is not None:
        choice = user_input["quiet"]
        if choice == BACK:
            return await flow.async_step_init()
        flow._index = None if choice == ADD else int(choice)
        return await flow.async_step_quiet()

    selector_texts = await texts.async_selector_texts(flow.hass)
    return flow.async_show_form(
        step_id="quiets",
        data_schema=schemas.quiets(flow, selector_texts),
    )


async def quiet(
    flow: ClimateDirectorOptionsFlow, user_input: dict[str, Any] | None = None
) -> ConfigFlowResult:
    """Edit one quiet window: when the director may not start anything."""
    windows = quiet_windows(flow)
    current = windows[flow._index] if flow._index is not None else {}

    if user_input is not None:
        if user_input.get(EXIT) == EXIT_DROP:
            return await flow.async_step_quiets()
        if user_input.get("delete") and flow._index is not None:
            windows.pop(flow._index)
        else:
            window = {
                "start": user_input["start"],
                "end": user_input["end"],
                "weekdays": ([int(day) for day in user_input.get("weekdays") or ()] or None),
                "holiday": user_input.get("holiday", False),
            }
            if flow._index is None:
                windows.append(window)
            else:
                windows[flow._index] = window
        flow._index = None
        return await flow.async_step_quiets()

    return flow.async_show_form(
        step_id="quiet",
        data_schema=schemas.quiet(current),
    )


def quiet_windows(flow: ClimateDirectorOptionsFlow) -> list[dict[str, Any]]:
    """Return the stored quiet windows, creating the list on first use."""
    gates = flow._installation.setdefault("gates", {})
    windows: list[dict[str, Any]] = gates.setdefault("quiet_windows", [])
    return windows
