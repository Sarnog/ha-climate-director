"""Climate Director - orkestreert bestaande climate-entiteiten.

Climate Director - orchestrates existing climate entities.

Deze integratie is opgebouwd in twee helften. `engine/` bevat de volledige
besliskunde als pure Python zonder Home Assistant-imports; de rest van dit
pakket koppelt die engine aan Home Assistant.

This integration is built in two halves. `engine/` holds all decision logic as
pure Python without Home Assistant imports; the rest of this package binds that
engine to Home Assistant.
"""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv

from . import problems
from .const import ATTR_ENTRY_ID, DOMAIN, PLATFORMS, SERVICE_EVALUATE
from .coordinator import ClimateDirectorCoordinator, ClimateDirectorEntry

_LOGGER = logging.getLogger(__name__)

__all__ = ["DOMAIN", "async_setup_entry", "async_unload_entry"]

_EVALUATE_SCHEMA = vol.Schema({vol.Optional(ATTR_ENTRY_ID): vol.All(cv.ensure_list, [cv.string])})


async def async_setup_entry(hass: HomeAssistant, entry: ClimateDirectorEntry) -> bool:
    """Set up one installation."""
    coordinator = ClimateDirectorCoordinator(hass, entry)
    entry.runtime_data = coordinator

    found = problems.async_report(hass, entry.entry_id, entry.title, coordinator.config)
    if found:
        _LOGGER.warning(
            "%s has %d configuration problem(s): %s", entry.title, len(found), "; ".join(found)
        )

    _async_register_services(hass)

    # De platforms gaan eerst omhoog, zodat de schakelaars hun bewaarde stand
    # al hersteld hebben voordat er voor het eerst besloten wordt. Anders zou
    # een uitgeschakelde hoofdschakelaar één ronde lang aan lijken te staan.
    #
    # Platforms come up first, so the switches have restored their saved state
    # before the first decision. Otherwise a master switch left off would look
    # on for one round.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await coordinator.async_start()

    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ClimateDirectorEntry) -> bool:
    """Tear one installation down."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_shutdown()
        problems.async_clear(hass, entry.entry_id)
    return unloaded


async def _async_reload(hass: HomeAssistant, entry: ClimateDirectorEntry) -> None:
    """Reload after the options changed, since the whole layout may have."""
    await hass.config_entries.async_reload(entry.entry_id)


@callback
def _async_register_services(hass: HomeAssistant) -> None:
    """Register the domain's actions once, however many installations there are.

    Actions belong to the domain rather than to an entry, so registering them
    per entry would have the second installation overwrite the first's handler.
    """
    if hass.services.has_service(DOMAIN, SERVICE_EVALUATE):
        return

    async def _async_evaluate(call: ServiceCall) -> None:
        """Ask one or every installation to decide again right now."""
        wanted = set(call.data.get(ATTR_ENTRY_ID) or ())
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            if wanted and entry.entry_id not in wanted:
                continue
            entry.runtime_data.async_request_evaluation()

    hass.services.async_register(DOMAIN, SERVICE_EVALUATE, _async_evaluate, _EVALUATE_SCHEMA)
