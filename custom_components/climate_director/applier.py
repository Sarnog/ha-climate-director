"""Het plan uitvoeren - of, in schaduwmodus, uitdrukkelijk niet.

Executing the plan - or, in shadow mode, deliberately not.

Deze laag is dun met opzet: hij beslist niets. Hij vergelijkt het plan met de
werkelijkheid (`engine.diff`, puur) en zet het verschil om in service calls.

This layer is thin on purpose: it decides nothing. It compares the plan against
reality (`engine.diff`, pure) and turns the difference into service calls.
"""

from __future__ import annotations

import logging

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
)
from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant

from .engine import MODE_FAN_ONLY, MODE_OFF, Plan, WorldState
from .engine.diff import Change, changes

_LOGGER = logging.getLogger(__name__)


async def apply(
    hass: HomeAssistant, plan: Plan, world: WorldState, *, shadow: bool
) -> tuple[Change, ...]:
    """Bring the installation in line with `plan` and return what was changed.

    In shadow mode the changes are computed and logged but never executed, so
    the director can run alongside an existing set of automations for as long
    as it takes to trust it. The return value is the same either way, which is
    what makes the two modes comparable.
    """
    pending = changes(plan, world)
    if not pending:
        return ()

    if shadow:
        for change in pending:
            _LOGGER.info(
                "Shadow mode: would set %s to %s%s (%s)",
                change.entity_id,
                change.command.hvac_mode,
                (f" at {change.command.temperature}" if change.set_temperature else ""),
                change.command.reason.value,
            )
        return pending

    applied: list[Change] = []
    for change in pending:
        try:
            await _execute(hass, change)
        except Exception:
            _LOGGER.exception("Could not steer %s", change.entity_id)
            # Een mislukte stop breekt de aanname waar de rest van het plan op
            # rust. De starts die erachteraan komen zouden dan bovenop een
            # apparaat landen dat had moeten stoppen - precies de combinatie
            # die dit ontwerp onbereikbaar hoort te maken. Een mislukte start
            # is onschuldig: dan gebeurt er alleen minder dan gepland.
            #
            # A failed stop breaks the assumption the rest of the plan rests
            # on. The starts behind it would land on top of an appliance that
            # should have stopped - exactly the combination this design is
            # meant to make unreachable. A failed start is harmless: it only
            # means less happens than planned.
            if _is_stop(change):
                _LOGGER.error(
                    "Abandoning the rest of the plan: %s could not be stopped",
                    change.entity_id,
                )
                break
            continue
        applied.append(change)

    return tuple(applied)


def _is_stop(change: Change) -> bool:
    """Return whether this change takes an appliance out of active duty."""
    return change.command.hvac_mode in (MODE_OFF, MODE_FAN_ONLY)


async def _execute(hass: HomeAssistant, change: Change) -> None:
    """Issue the service calls one change needs.

    `climate.set_temperature` carries `hvac_mode` as well, so a unit that needs
    both a mode and a setpoint is served by a single call - two calls would
    briefly leave it running the new mode on the old setpoint.
    """
    command = change.command

    if change.set_temperature:
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_TEMPERATURE,
            {
                ATTR_ENTITY_ID: command.entity_id,
                ATTR_TEMPERATURE: command.temperature,
                ATTR_HVAC_MODE: command.hvac_mode,
            },
            blocking=True,
        )
        return

    if change.set_mode:
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_HVAC_MODE,
            {ATTR_ENTITY_ID: command.entity_id, ATTR_HVAC_MODE: command.hvac_mode},
            blocking=True,
        )
