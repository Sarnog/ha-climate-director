"""De bewoner- en vensterschermen. / The resident and window screens."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.helpers import selector

from .form_common import (
    ADD,
    BACK,
    CONF_NAME,
    EXIT,
    EXIT_KEEP,
    WEEKDAYS,
    add_option,
    back_option,
    exit_row,
    window_label,
)
from .schema_fields import (
    TEXT,
    TIME,
)


def residents(flow: Any) -> vol.Schema:
    """Return the resident picker schema."""
    residents = flow._list("residents")
    options = [
        selector.SelectOptionDict(
            value=str(index), label=person.get("name") or person["resident_id"]
        )
        for index, person in enumerate(residents)
    ]
    options.append(add_option("resident"))
    options.append(back_option())
    return vol.Schema(
        {
            vol.Required("resident", default=ADD): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    mode=selector.SelectSelectorMode.LIST,
                    translation_key="resident_list",
                )
            )
        }
    )


def resident(current: dict[str, Any]) -> vol.Schema:
    """Return the single resident schema.

    De opsta-instellingen van één bewoner staan bij elkaar: eerst *Wacht op deze
    slaper tot* met zijn vinkje en dagen, direct daaronder *Opstaan zet het huis pas
    aan vanaf* met zijn dagen (zonder vinkje voor vakantiedagen: daar geldt de rem
    nooit). One resident's getting-up settings stand together: first *Wait for this
    sleeper until* with its tick and days, right below it *Getting up only starts the
    house from* with its days (no holiday tick: the brake never applies there).
    """
    wake = current.get("wake_deadline") or {}
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=current.get("name", "")): TEXT,
            vol.Optional(
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
                selector.EntitySelectorConfig(domain=["binary_sensor", "sensor", "input_boolean"])
            ),
            vol.Required("sleep_state", default=current.get("sleep_state", "on")): TEXT,
            vol.Optional(
                "sleep_from",
                description={"suggested_value": (current.get("sleep_window") or {}).get("start")},
            ): TIME,
            vol.Optional(
                "sleep_until",
                description={"suggested_value": (current.get("sleep_window") or {}).get("end")},
            ): TIME,
            vol.Optional(
                "sleep_days",
                description={"suggested_value": stored_days(current.get("sleep_window"))},
            ): weekday_picker(),
            vol.Optional(
                "sleep_in_until",
                description={"suggested_value": (current.get("sleep_in") or {}).get("until")},
            ): TIME,
            vol.Required(
                "sleep_in_holiday",
                default=(current.get("sleep_in") or {}).get("holiday", False),
            ): bool,
            vol.Optional(
                "sleep_in_days",
                description={"suggested_value": stored_days(current.get("sleep_in"))},
            ): weekday_picker(),
            vol.Optional("wake_by", description={"suggested_value": wake.get("at")}): TIME,
            vol.Required("wake_holiday", default=wake.get("holiday", False)): bool,
            vol.Optional(
                "wake_days", description={"suggested_value": stored_days(wake)}
            ): weekday_picker(),
            vol.Optional(
                "rise_from",
                description={"suggested_value": (current.get("rise_brake") or {}).get("at")},
            ): TIME,
            vol.Optional(
                "rise_days",
                description={"suggested_value": stored_days(current.get("rise_brake"))},
            ): weekday_picker(),
            vol.Required("delete", default=False): bool,
            vol.Required(EXIT, default=EXIT_KEEP): exit_row(),
        }
    )


def weekday_picker() -> selector.SelectSelector:
    """Return the weekday picker the resident screen uses four times."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                selector.SelectOptionDict(value=str(number), label=label)
                for number, label in enumerate(WEEKDAYS)
            ],
            multiple=True,
            mode=selector.SelectSelectorMode.LIST,
            translation_key="weekday",
        )
    )


def stored_days(block: Any) -> list[str] | None:
    """Return the stored weekdays of one resident setting as the picker wants them."""
    days = (block or {}).get("weekdays")
    return None if days is None else [str(day) for day in days]


def windows(flow: Any, selector_texts: dict[str, str]) -> vol.Schema:
    """Return the schedule-window picker schema of the current resident."""
    resident = flow._current_resident()
    windows = resident.setdefault("windows", [])
    options = [
        selector.SelectOptionDict(value=str(index), label=window_label(window, selector_texts))
        for index, window in enumerate(windows)
    ]
    options.append(add_option("window"))
    options.append(back_option())
    return vol.Schema(
        {
            vol.Required("window", default=BACK if windows else ADD): (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        mode=selector.SelectSelectorMode.LIST,
                        translation_key="window_list",
                    )
                )
            )
        }
    )


def window(current: dict[str, Any]) -> vol.Schema:
    """Return the single schedule-window schema."""
    weekdays = current.get("weekdays")
    return vol.Schema(
        {
            vol.Required("holiday", default=current.get("holiday", False)): bool,
            vol.Required("start", default=current.get("start", "08:00:00")): TIME,
            vol.Required("end", default=current.get("end", "23:00:00")): TIME,
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
