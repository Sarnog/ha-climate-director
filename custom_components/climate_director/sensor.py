"""Waarneemsensoren: wat besloot de director, en waarom.

Observation sensors: what the director decided, and why.

In schaduwmodus zijn dit de enige zichtbare uitkomsten van de integratie. Ze
zijn daarom bewust uitgebreid: het doel van die modus is kunnen zien wat er
gebeurd zou zijn, zonder dat er iets gebeurt.

In shadow mode these are the integration's only visible output. They are
deliberately detailed for that reason: the point of that mode is being able to
see what would have happened, without anything happening.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ClimateDirectorCoordinator, ClimateDirectorEntry
from .entity import ClimateDirectorEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ClimateDirectorEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one summary sensor plus one sensor per zone."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [DecisionSensor(coordinator)]
    entities.extend(
        ZoneSourceSensor(coordinator, zone.zone_id) for zone in coordinator.config.zones
    )
    async_add_entities(entities)


class DecisionSensor(ClimateDirectorEntity, SensorEntity):
    """Summary of the last decision across the whole installation."""

    _attr_translation_key = "last_decision"
    _attr_icon = "mdi:clipboard-text-clock"

    def __init__(self, coordinator: ClimateDirectorCoordinator) -> None:
        """Set up the summary sensor."""
        super().__init__(coordinator, "last_decision")

    @property
    def native_value(self) -> str | None:
        """Return how many zones are actively being served."""
        plan = self.coordinator.data
        if plan is None:
            return None
        active = sum(1 for zone in plan.zones if zone.granted.value in ("heat", "cool"))
        return f"{active}/{len(plan.zones)}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the full decision, so shadow mode is inspectable."""
        plan = self.coordinator.data
        if plan is None:
            return {}
        return {
            "shadow_mode": self.coordinator.shadow,
            "commands": [
                {
                    "entity_id": command.entity_id,
                    "hvac_mode": command.hvac_mode,
                    "temperature": command.temperature,
                    "zone_id": command.zone_id,
                    "reason": command.reason.value,
                }
                for command in plan.commands
            ],
            "would_change": [change.entity_id for change in self.coordinator.last_changes],
            "circuits": [
                {
                    "circuit_id": circuit.circuit_id,
                    "family": circuit.family.value,
                    "winner": circuit.winner_zone_id,
                    "displaced": list(circuit.displaced_zone_ids),
                }
                for circuit in plan.circuits
            ],
            "deferrals": [
                {
                    "subject": deferral.subject,
                    "until": deferral.until.isoformat(),
                    "reason": deferral.reason.value,
                }
                for deferral in plan.deferrals
            ],
        }


class ZoneSourceSensor(ClimateDirectorEntity, SensorEntity):
    """Which source is serving one zone, and why."""

    _attr_translation_key = "zone_source"
    _attr_icon = "mdi:thermostat-box"

    def __init__(self, coordinator: ClimateDirectorCoordinator, zone_id: str) -> None:
        """Set up the sensor for one zone."""
        super().__init__(coordinator, f"zone_{zone_id}_source")
        self._zone_id = zone_id
        zone = coordinator.config.zone(zone_id)
        self._attr_translation_placeholders = {"zone": zone.name if zone else zone_id}

    @property
    def native_value(self) -> str | None:
        """Return the active source id, or `none` when the zone stands down."""
        plan = self.coordinator.data
        if plan is None:
            return None
        decision = plan.decision_for(self._zone_id)
        if decision is None or decision.granted.value not in ("heat", "cool"):
            return "none"
        return decision.source_id

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return what this zone asked for, what it got and why."""
        plan = self.coordinator.data
        if plan is None:
            return {}
        decision = plan.decision_for(self._zone_id)
        if decision is None:
            return {}
        return {
            "wanted": decision.wanted.value,
            "granted": decision.granted.value,
            "reason": decision.reason.value,
            "blocked": decision.blocked,
        }
