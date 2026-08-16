"""Per zone of hij tegengehouden wordt, en of er ergens iets vastloopt.

Per zone whether it is held back, and whether anything is stuck.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ClimateDirectorCoordinator, ClimateDirectorEntry
from .entity import ClimateDirectorEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ClimateDirectorEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one blocked sensor per zone, and one stuck sensor for the whole."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [
        ZoneBlockedSensor(coordinator, zone.zone_id) for zone in coordinator.config.zones
    ]
    entities.append(StuckSensor(coordinator))
    async_add_entities(entities)


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


class StuckSensor(ClimateDirectorEntity, BinarySensorEntity):
    """On when a zone keeps waiting for something that is not coming.

    De andere melders zeggen wat er nu is; deze zegt dat er iets niet meer
    verandert. Een pauze bij het wisselen van taak hoort seconden te duren, dus
    een zone die er een kwartier op staat wacht niet meer - die zit vast. Zo'n
    klem is van buiten niet te onderscheiden van "de director besluit niets",
    en dat is de stilste manier waarop deze integratie kan falen.

    The other sensors say what is; this one says that something has stopped
    changing. A pause when switching duty should last seconds, so a zone sitting
    on one for a quarter of an hour is no longer waiting - it is stuck. From the
    outside such a deadlock is indistinguishable from "the director decides
    nothing", which is the quietest way this integration can fail.
    """

    _attr_translation_key = "stuck"
    _attr_icon = "mdi:progress-alert"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ClimateDirectorCoordinator) -> None:
        """Set up the installation-wide stuck sensor."""
        super().__init__(coordinator, "stuck")

    @property
    def is_on(self) -> bool | None:
        """Return whether any zone has been waiting too long."""
        if self.coordinator.data is None:
            return None
        return bool(self.coordinator.stuck_zones())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return which zones are stuck, on what, and for how long."""
        stuck = self.coordinator.stuck_zones()
        return {
            "zones": sorted(stuck),
            "reasons": {zone_id: reason.value for zone_id, reason in sorted(stuck.items())},
            "waiting_seconds": {
                zone_id: round(seconds)
                for zone_id, seconds in sorted(self.coordinator.waiting_seconds().items())
            },
        }
