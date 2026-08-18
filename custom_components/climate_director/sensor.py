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

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ClimateDirectorCoordinator, ClimateDirectorEntry
from .entity import ClimateDirectorEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ClimateDirectorEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the summary sensors, one per zone, and one per steered appliance."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [DecisionSensor(coordinator), MismatchSensor(coordinator)]
    entities.extend(
        ZoneSourceSensor(coordinator, zone.zone_id) for zone in coordinator.config.zones
    )
    # Een sensor per APPARAAT, niet per bron. Sinds een apparaat onder meerdere
    # zones mag staan - zo ziet een centrale verwarming eruit - leverde een
    # bron-voor-bron-lijst dubbele unieke ID's op, en gooide Home Assistant de
    # tweede en derde weg met een fout in het logboek.
    #
    # One sensor per APPLIANCE, not per source. Since an appliance may sit under
    # several zones - which is what central heating looks like - a source-by-
    # source list produced duplicate unique ids, and Home Assistant discarded the
    # second and third with an error in the log.
    entities.extend(
        CommandSensor(coordinator, entity_id)
        for entity_id in dict.fromkeys(
            source.entity_id for _, source in coordinator.config.sources() if source.entity_id
        )
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


class CommandSensor(ClimateDirectorEntity, SensorEntity):
    """The mode the director would put one appliance in.

    Deliberately a plain state rather than an attribute: Home Assistant records
    state history, which is what makes a shadow run comparable afterwards. Line
    this sensor's history up against the climate entity it names and every
    moment the director and the existing automations disagreed stands out.
    """

    _attr_translation_key = "would_command"
    _attr_icon = "mdi:script-text-outline"

    def __init__(self, coordinator: ClimateDirectorCoordinator, entity_id: str) -> None:
        """Set up the sensor for one steered appliance."""
        super().__init__(coordinator, f"command_{entity_id}")
        self._target = entity_id
        self._attr_translation_placeholders = {"entity": entity_id}

    @property
    def native_value(self) -> str | None:
        """Return the commanded hvac mode, or `unmanaged` when there is none."""
        plan = self.coordinator.data
        if plan is None:
            return None
        command = plan.command_for(self._target)
        return command.hvac_mode if command else "unmanaged"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the setpoint, the reason, and what the appliance is doing now."""
        plan = self.coordinator.data
        world = self.coordinator.world
        if plan is None:
            return {}
        command = plan.command_for(self._target)
        actual = world.climate(self._target) if world else None
        return {
            "target_entity": self._target,
            "temperature": command.temperature if command else None,
            "zone_id": command.zone_id if command else None,
            "reason": command.reason.value if command else None,
            "actual_hvac_mode": actual.hvac_mode if actual and actual.available else None,
            "actual_temperature": actual.target_temperature if actual else None,
            "agrees": (
                None
                if command is None or actual is None or not actual.available
                else actual.hvac_mode == command.hvac_mode
            ),
        }


class MismatchSensor(ClimateDirectorEntity, SensorEntity):
    """How many appliances sit somewhere other than where the plan wants them.

    In shadow mode this is the headline number of the whole exercise: zero means
    the director and whatever is actually steering the house agree. A brief
    non-zero reading is normal - one side acts a moment before the other - but a
    reading that stays up is a real disagreement worth looking into.
    """

    _attr_translation_key = "mismatch"
    _attr_icon = "mdi:not-equal-variant"
    _attr_native_unit_of_measurement = "appliances"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: ClimateDirectorCoordinator) -> None:
        """Set up the mismatch sensor."""
        super().__init__(coordinator, "mismatch")

    @property
    def native_value(self) -> int | None:
        """Return how many appliances would be changed right now."""
        if self.coordinator.data is None:
            return None
        return len(self.coordinator.last_changes)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return exactly which appliances differ, and how."""
        world = self.coordinator.world
        return {
            "shadow_mode": self.coordinator.shadow,
            "differences": [
                {
                    "entity_id": change.entity_id,
                    "wanted_hvac_mode": change.command.hvac_mode,
                    "wanted_temperature": change.command.temperature,
                    "actual_hvac_mode": (
                        world.climate(change.entity_id).hvac_mode if world else None
                    ),
                    "actual_temperature": (
                        world.climate(change.entity_id).target_temperature if world else None
                    ),
                    "reason": change.command.reason.value,
                }
                for change in self.coordinator.last_changes
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
