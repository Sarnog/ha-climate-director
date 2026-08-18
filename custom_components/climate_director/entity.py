"""Gedeelde basis voor de entiteiten van Climate Director.

Shared base for Climate Director's entities.
"""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ClimateDirectorCoordinator


class ClimateDirectorEntity(CoordinatorEntity[ClimateDirectorCoordinator]):
    """Base entity: one device per installation, names from translations."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ClimateDirectorCoordinator, key: str) -> None:
        """Bind the entity to its installation."""
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=coordinator.config_entry.title,
            manufacturer="Sarnog",
            model="Climate Director",
            entry_type=DeviceEntryType.SERVICE,
            sw_version=coordinator.version or None,
        )
