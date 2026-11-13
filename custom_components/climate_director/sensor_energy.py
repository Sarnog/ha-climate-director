"""De kostensensor: welke bron een kWh warmte nu het goedkoopst levert.

The cost sensor: which source delivers a kWh of heat cheapest right now.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import Event, EventStateChangedData, callback
from homeassistant.helpers.event import async_track_state_change_event

from .coordinator import ClimateDirectorCoordinator
from .engine.energy import ELECTRIC, GAS, HeatCosts, heat_costs
from .entity import ClimateDirectorEntity


class HeatCostSensor(ClimateDirectorEntity, SensorEntity):
    """Which source would be cheapest for a kWh of heat right now.

    Alleen kijken, niet sturen: de bronkeuze kent deze sensor niet. Hij zet gas
    en de airco's naast elkaar op de prijzen van dit moment, zodat je in de
    geschiedenis kunt nagaan wanneer de goedkoopste bron een andere was dan de
    bron die de buitentemperatuur koos. Dat is de maat waarop een latere stap
    kan besluiten of kosten het ook echt mogen overnemen.

    Watching only, not steering: the source selection does not know this sensor.
    It sets gas and the air conditioners side by side at this moment's prices, so
    the history shows when the cheapest source differed from the one the outdoor
    temperature chose. That is the measure on which a later step can decide
    whether cost may really take over.
    """

    _attr_translation_key = "cheapest_heat"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [GAS, ELECTRIC]
    _attr_icon = "mdi:cash-multiple"

    def __init__(self, coordinator: ClimateDirectorCoordinator) -> None:
        """Set up the cost sensor."""
        super().__init__(coordinator, "cheapest_heat")

    async def async_added_to_hass(self) -> None:
        """Follow the price entities: a new price changes the answer at once."""
        await super().async_added_to_hass()
        entities = list(self.coordinator.config.energy.entities())

        @callback
        def _price_changed(_event: Event[EventStateChangedData]) -> None:
            self.async_write_ha_state()

        self.async_on_remove(async_track_state_change_event(self.hass, entities, _price_changed))

    def _number(self, entity_id: str) -> float | None:
        """Return the number an entity reports, or `None` when it reports none."""
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        try:
            return float(state.state)
        except ValueError:
            return None

    def _costs(self) -> HeatCosts:
        """Return the costs at this moment's readings."""
        energy = self.coordinator.config.energy
        world = self.coordinator.world
        return heat_costs(
            energy,
            self._number(energy.grid_price_sensor),
            self._number(energy.feed_in_sensor),
            self._number(energy.surplus_sensor),
            None if world is None else world.outdoor_temperature,
        )

    @property
    def native_value(self) -> str | None:
        """Return the cheapest source, or `None` when no cost can be worked out."""
        return self._costs().cheapest

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return both costs and what they were worked out from."""
        costs = self._costs()
        return {
            "gas_cost": None if costs.gas is None else round(costs.gas, 4),
            "electric_cost": None if costs.electric is None else round(costs.electric, 4),
            "cop": None if costs.cop is None else round(costs.cop, 2),
            "electricity_price": costs.electricity_price,
        }
