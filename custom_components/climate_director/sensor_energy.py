"""De kostensensoren: welke bron een kWh warmte nu het goedkoopst levert, en waar het omslaat.

The cost sensors: which source delivers a kWh of heat cheapest right now, and
where it swaps over.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import Event, EventStateChangedData, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.util import dt as dt_util

from .coordinator import ClimateDirectorCoordinator
from .cost_steering import costs_now, heating_kinds, read_number
from .engine import ModeFamily, SourceEnergy
from .engine.energy import ELECTRIC, GAS, BreakEven, HeatCosts, break_even
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

    def _costs(self) -> HeatCosts:
        """Return the costs at this moment's readings."""
        world = self.coordinator.world
        return costs_now(
            self.hass,
            self.coordinator.config.energy,
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
            "cost_control": self.coordinator.config.energy.cost_control,
            "preferred_source": self.coordinator.round.heat_pick.preferred,
            "preferred_reason": self.coordinator.round.heat_pick.reason,
            "steered_zones": self._steered_zones(),
            "zone_preferences": {
                zone_id: pick.preferred
                for zone_id, pick in self.coordinator.round.zone_heat_picks.items()
            },
        }

    def _steered_zones(self) -> list[str]:
        """Return the zones that have both a gas and an electric source able to heat.

        Alleen in die zones kan de kostenvoorkeur iets kiezen; staat hier niets
        terwijl kostenbesturing aanstaat, dan heeft nog geen bron een energiebron.

        Only in those zones can the cost preference pick anything; if this is empty
        while cost control is on, no source has an energy kind yet.
        """
        if not self.coordinator.config.energy.cost_control:
            return []
        return [
            zone.zone_id
            for zone in self.coordinator.config.zones
            if zone.cost_control
            and {source.energy for source in zone.sources if source.supports(ModeFamily.HEAT)}
            >= {SourceEnergy.GAS, SourceEnergy.ELECTRIC}
        ]


class BreakEvenSensor(ClimateDirectorEntity, SensorEntity):
    """The outdoor temperature below which gas is cheaper than the air conditioners.

    Voor vaste prijzen is dit één getal dat je zo kunt lezen; bij een dynamisch
    contract beweegt het mee met de prijs. Alleen kijken: de bronkeuze leest hem
    niet. Is elektrisch overal goedkoper of gas overal, dan is er geen
    omslagtemperatuur en staat dat in het kenmerk `verdict`.

    For fixed prices this is one number you can read at once; with a dynamic
    contract it moves with the price. Watching only: the source selection does not
    read it. If electric is cheaper everywhere or gas is, there is no changeover
    temperature and the `verdict` attribute says so.
    """

    _attr_translation_key = "heat_break_even"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: ClimateDirectorCoordinator) -> None:
        """Set up the changeover sensor."""
        super().__init__(coordinator, "heat_break_even")

    async def async_added_to_hass(self) -> None:
        """Follow the price entities: a new price moves the changeover."""
        await super().async_added_to_hass()
        entities = list(self.coordinator.config.energy.entities())

        @callback
        def _price_changed(_event: Event[EventStateChangedData]) -> None:
            self.async_write_ha_state()

        self.async_on_remove(async_track_state_change_event(self.hass, entities, _price_changed))

    def _answer(self) -> BreakEven:
        energy = self.coordinator.config.energy
        price = read_number(self.hass, energy.grid_price_sensor)
        if price is None and energy.grid_price > 0:
            price = energy.grid_price
        if price is None:
            return BreakEven(None, None)
        return break_even(energy, price, read_number(self.hass, energy.gas_price_sensor))

    @property
    def native_value(self) -> float | None:
        """Return the changeover temperature, or `None` when there is none."""
        temperature = self._answer().temperature
        return None if temperature is None else round(temperature, 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return whether there is a changeover at all, and the price it assumed."""
        return {"verdict": self._answer().verdict}


#: Hoe vaak de verwarmingsuren bijgewerkt worden, en hoeveel tijd één stap
#: hoogstens telt: na een onderbreking (slaapstand, herstart) telt de gemiste tijd
#: niet mee. / How often the heating hours are updated, and the most time one step
#: counts: after an interruption (suspend, restart) the missed time does not count.
HEAT_HOURS_STEP = timedelta(minutes=1)
HEAT_HOURS_MAX_GAP = timedelta(minutes=5)


class HeatHoursSensor(ClimateDirectorEntity, RestoreSensor):
    """How many hours a kind of source (gas or electric) has been heating.

    Een teller die alleen oploopt, dus Home Assistant bewaart hem als lange-
    termijnstatistiek, per uur en onbeperkt. Zet je hem naast de gasmeter en de
    airco-stroom, dan zie je per uur of er alleen gas, alleen de airco of allebei
    verwarmden. Dat zijn precies de gegevens om de COP-curve uit te rekenen, en
    het uur waarin de ketel niet verwarmde is het uur waarin de gasmeter alleen
    warm water (douchen) meet.

    A counter that only rises, so Home Assistant keeps it as a long-term
    statistic, hourly and without limit. Put next to the gas meter and the air
    conditioner power, it shows per hour whether only gas, only the air conditioner
    or both were heating. That is exactly the data for working out the COP curve,
    and the hour in which the boiler was not heating is the hour in which the gas
    meter reads hot water (showers) alone.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_suggested_display_precision = 1

    _kind = ""

    def __init__(self, coordinator: ClimateDirectorCoordinator) -> None:
        """Set up the counter for its kind of source."""
        super().__init__(coordinator, f"heat_hours_{self._kind}")
        self._hours = 0.0
        self._last: datetime | None = None

    async def async_added_to_hass(self) -> None:
        """Pick the count up where it was left, and start counting."""
        await super().async_added_to_hass()
        last = await self.async_get_last_sensor_data()
        if last is not None and isinstance(last.native_value, int | float):
            self._hours = float(last.native_value)
        self.async_on_remove(async_track_time_interval(self.hass, self._count, HEAT_HOURS_STEP))
        self._last = dt_util.utcnow()

    @callback
    def _count(self, now: datetime) -> None:
        """Add the time since the last step when this kind was heating."""
        gap = now - self._last if self._last is not None else HEAT_HOURS_STEP
        self._last = now
        if self._kind in heating_kinds(self.hass, self.coordinator.config):
            self._hours += min(gap, HEAT_HOURS_MAX_GAP).total_seconds() / 3600
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        """Return the hours counted so far."""
        return round(self._hours, 3)


class GasHeatHoursSensor(HeatHoursSensor):
    """The hours gas (the boiler) has been heating."""

    _attr_translation_key = "heat_hours_gas"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:fire"
    _kind = GAS


class ElectricHeatHoursSensor(HeatHoursSensor):
    """The hours the air conditioners have been heating."""

    _attr_translation_key = "heat_hours_electric"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:heat-pump"
    _kind = ELECTRIC
