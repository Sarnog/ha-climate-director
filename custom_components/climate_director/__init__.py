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

from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import ClimateDirectorCoordinator, ClimateDirectorEntry

__all__ = ["DOMAIN", "async_setup_entry", "async_unload_entry"]


async def async_setup_entry(hass: HomeAssistant, entry: ClimateDirectorEntry) -> bool:
    """Set up one installation."""
    coordinator = ClimateDirectorCoordinator(hass, entry)
    entry.runtime_data = coordinator

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
    return unloaded


async def _async_reload(hass: HomeAssistant, entry: ClimateDirectorEntry) -> None:
    """Reload after the options changed, since the whole layout may have."""
    await hass.config_entries.async_reload(entry.entry_id)
