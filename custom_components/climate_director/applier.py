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

from .engine import MODE_FAN_ONLY, MODE_OFF
from .engine.diff import Change

_LOGGER = logging.getLogger(__name__)


async def apply(
    hass: HomeAssistant, pending: tuple[Change, ...], *, shadow: bool
) -> tuple[Change, ...]:
    """Carry out `pending` and return what was actually changed.

    Works out nothing itself: which changes are needed is `engine.diff`'s job,
    and the caller keeps that list so it can be reported whether or not it was
    executed. In shadow mode the changes are logged and never carried out, so
    the director can run alongside an existing set of automations for as long
    as it takes to trust it.
    """
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
        return ()

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

    De stand gaat als eigen aanroep, vóór het setpoint. Home Assistant geeft
    `hvac_mode` in `climate.set_temperature` alleen door aan de entiteit en doet
    er zelf niets mee: sommige entiteiten verzetten de stand dan wel
    (matter, melcloud's AtaDeviceClimate), andere negeren hem (core's
    `generic_thermostat`, melcloud's AtwDeviceZoneClimate). Eén seconde op het
    oude setpoint weegt niet op tegen een apparaat dat nooit aangaat.

    The mode goes as its own call, before the setpoint. Home Assistant only
    passes `hvac_mode` inside `climate.set_temperature` on to the entity and
    does nothing with it itself: some entities do move the mode then (matter,
    melcloud's AtaDeviceClimate), others ignore it (core's
    `generic_thermostat`, melcloud's AtwDeviceZoneClimate). One second on the
    old setpoint does not weigh up against an appliance that never turns on.
    """
    command = change.command

    if change.set_mode:
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_HVAC_MODE,
            {ATTR_ENTITY_ID: command.entity_id, ATTR_HVAC_MODE: command.hvac_mode},
            blocking=True,
        )

    if change.set_temperature:
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_TEMPERATURE,
            {
                ATTR_ENTITY_ID: command.entity_id,
                ATTR_TEMPERATURE: command.temperature,
            },
            blocking=True,
        )
