"""Per zone: wordt hij tegengehouden, en waardoor.

Per zone: is it being held back, and by what.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ClimateDirectorCoordinator, ClimateDirectorEntry
from .entity import ClimateDirectorEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ClimateDirectorEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one blocked sensor per zone."""
    coordinator = entry.runtime_data
    async_add_entities(
        ZoneBlockedSensor(coordinator, zone.zone_id) for zone in coordinator.config.zones
    )


class ZoneBlockedSensor(ClimateDirectorEntity, BinarySensorEntity):
    """On when a zone wanted something it did not get."""

    _attr_translation_key = "zone_blocked"
    _attr_icon = "mdi:hand-back-left"

    def __init__(self, coordinator: ClimateDirectorCoordinator, zone_id: str) -> None:
        """Set up the sensor for one zone."""
        super().__init__(coordinator, f"zone_{zone_id}_blocked")
        self._zone_id = zone_id
        zone = coordinator.config.zone(zone_id)
        self._attr_translation_placeholders = {"zone": zone.name if zone else zone_id}

    @property
    def is_on(self) -> bool | None:
        """Return whether this zone got less than it asked for."""
        plan = self.coordinator.data
        if plan is None:
            return None
        decision = plan.decision_for(self._zone_id)
        return decision.blocked if decision else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the cause, as a stable identifier rather than free text."""
        plan = self.coordinator.data
        if plan is None:
            return {}
        decision = plan.decision_for(self._zone_id)
        return {"reason": decision.reason.value} if decision else {}
