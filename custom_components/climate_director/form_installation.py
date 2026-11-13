"""De installatieschermen. / The installation screens."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.helpers import selector

from .engine.fields import ENERGY_FIELDS, SETTINGS_FIELDS
from .flow_surface import FlowSurface
from .form_common import (
    ADD,
    BACK,
    EXIT,
    EXIT_KEEP,
    WEEKDAYS,
    add_option,
    back_option,
    exit_row,
    group_label,
    source_options,
    window_label,
)
from .schema_fields import (
    TIME,
    table_schema,
)


def settings(flow: Any) -> vol.Schema:
    """Return the general settings schema from the current installation.

    De veldenlijst staat in `engine.fields.SETTINGS_FIELDS`; deze functie is
    alleen nog de vertaling naar `vol.Schema`, plus de afsluitregel die elk
    scherm draagt.

    The field list lives in `engine.fields.SETTINGS_FIELDS`; this function is
    now only the translation into `vol.Schema`, plus the exit row every screen
    carries.
    """
    return table_schema(
        SETTINGS_FIELDS,
        flow,
        values=flow._installation,
        footer={vol.Required(EXIT, default=EXIT_KEEP): exit_row()},
    )


def energy(flow: Any) -> vol.Schema:
    """Return the energy screen schema from the current installation.

    Zelfde vorm als `settings`: de veldenlijst staat in `engine.fields`, hier
    alleen de vertaling naar `vol.Schema` plus de afsluitregel.

    Same shape as `settings`: the field list lives in `engine.fields`, here only
    the translation into `vol.Schema` plus the exit row.
    """
    return table_schema(
        ENERGY_FIELDS,
        flow,
        values=flow._installation,
        footer={vol.Required(EXIT, default=EXIT_KEEP): exit_row()},
    )


def exclusives(flow: Any) -> vol.Schema:
    """Return the exclusive-group picker schema."""
    groups = flow._list("exclusive_groups")
    options = [
        selector.SelectOptionDict(value=str(index), label=group_label(flow, group))
        for index, group in enumerate(groups)
    ]
    options.append(add_option("exclusive"))
    options.append(back_option())
    return vol.Schema(
        {
            vol.Required("group", default=ADD): selector.SelectSelector(
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
                    options=source_options(flow),
                    mode=selector.SelectSelectorMode.LIST,
                    multiple=True,
                )
            ),
            vol.Required("delete", default=False): bool,
            vol.Required(EXIT, default=EXIT_KEEP): exit_row(),
        }
    )


def quiets(flow: Any, selector_texts: dict[str, str]) -> vol.Schema:
    """Return the quiet-window picker schema."""
    windows = quiet_windows(flow)
    options = [
        selector.SelectOptionDict(value=str(index), label=window_label(window, selector_texts))
        for index, window in enumerate(windows)
    ]
    options.append(add_option("quiet"))
    options.append(back_option())
    return vol.Schema(
        {
            vol.Required("quiet", default=BACK if windows else ADD): (
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
            vol.Required("start", default=current.get("start", "21:00:00")): TIME,
            vol.Required("end", default=current.get("end", "09:00:00")): TIME,
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
                        for number, label in enumerate(WEEKDAYS)
                    ],
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                    translation_key="weekday",
                )
            ),
            vol.Required("delete", default=False): bool,
            vol.Required(EXIT, default=EXIT_KEEP): exit_row(),
        }
    )


def quiet_windows(flow: FlowSurface) -> list[dict[str, Any]]:
    """Return the stored quiet windows, creating the list on first use."""
    gates = flow._installation.setdefault("gates", {})
    windows: list[dict[str, Any]] = gates.setdefault("quiet_windows", [])
    return windows
