"""De kostensensor in een echte Home Assistant.

The cost sensor inside a real Home Assistant.

Dekking: de sensor die laat zien welke bron een kWh warmte nu het goedkoopst
levert, wat er gebeurt als een prijs verandert of niet te lezen is, en dat hij
alleen bestaat als er genoeg is ingesteld. Niet gedekt: de bronkeuze zelf, want
die kent deze sensor niet.

Coverage: the sensor showing which source delivers a kWh of heat cheapest right
now, what happens when a price changes or cannot be read, and that it only
exists when enough is set. Not covered: the source selection itself, since it
does not know this sensor.
"""

from __future__ import annotations

from typing import Any

import pytest
from harness_live import LiveHome, start_house, stop_house
from live_helpers import cold_two_rooms, two_zone_installation

pytest_plugins = ["live_fixtures"]
pytestmark = pytest.mark.usefixtures("appliance")

ENERGY: dict[str, Any] = {
    "grid_price_sensor": "sensor.stroomprijs",
    "feed_in_sensor": "sensor.terugleverprijs",
    "surplus_sensor": "sensor.overschot",
    "gas_price": 1.8,
    "kwh_per_m3": 9.77,
    "boiler_efficiency": 0.9,
    "cop_curve": "-5:2.8, 7:3.8, 15:4.5",
}


def world(**readings: str) -> dict[str, tuple[str, dict[str, Any]]]:
    """Return the cold two-room house with prices and an outdoor temperature."""
    states = {
        **cold_two_rooms(),
        "sensor.buiten": ("8.0", {}),
        "sensor.stroomprijs": ("0.30", {}),
        "sensor.terugleverprijs": ("0.05", {}),
        "sensor.overschot": ("0.0", {}),
    }
    states.update({f"sensor.{name}": (value, {}) for name, value in readings.items()})
    return states


async def start(energy: dict[str, Any] | None, **readings: str) -> LiveHome:
    """Start the house with this energy setting."""
    installation = two_zone_installation(outdoor_sensor="sensor.buiten")
    if energy is not None:
        installation["energy"] = energy
    return await start_house(installation, states=world(**readings))


class TestTheCostSensor:
    async def test_cheap_power_beats_gas(self) -> None:
        home = await start(ENERGY)
        try:
            assert home.value("cheapest_heat") == "electric"
            attributes = home.values("cheapest_heat")
            assert attributes["gas_cost"] == pytest.approx(0.2047, abs=1e-4)
            assert attributes["electric_cost"] == pytest.approx(0.0772, abs=1e-4)
            assert attributes["cop"] == pytest.approx(3.89, abs=0.01)
            assert attributes["electricity_price"] == pytest.approx(0.30)
        finally:
            await stop_house(home)

    async def test_a_new_price_changes_the_answer_at_once(self) -> None:
        home = await start(ENERGY)
        try:
            home.set("sensor.stroomprijs", "0.90")
            await home.settle()
            assert home.value("cheapest_heat") == "gas"
        finally:
            await stop_house(home)

    async def test_a_solar_surplus_makes_power_cheap_again(self) -> None:
        home = await start(ENERGY, stroomprijs="0.90")
        try:
            assert home.value("cheapest_heat") == "gas"
            home.set("sensor.overschot", "1.5")
            await home.settle()
            assert home.value("cheapest_heat") == "electric"
            assert home.values("cheapest_heat")["electricity_price"] == pytest.approx(0.05)
        finally:
            await stop_house(home)

    async def test_an_unreadable_power_price_gives_gas_alone(self) -> None:
        home = await start(ENERGY, stroomprijs="unavailable")
        try:
            assert home.value("cheapest_heat") == "gas"
            assert home.values("cheapest_heat")["electric_cost"] is None
        finally:
            await stop_house(home)

    async def test_an_unreadable_price_that_is_not_a_number_is_no_price(self) -> None:
        home = await start(ENERGY, stroomprijs="abc")
        try:
            assert home.values("cheapest_heat")["electric_cost"] is None
        finally:
            await stop_house(home)

    async def test_a_missing_price_entity_is_no_price(self) -> None:
        energy = {**ENERGY, "feed_in_sensor": "", "surplus_sensor": ""}
        home = await start(energy)
        try:
            assert home.value("cheapest_heat") == "electric"
        finally:
            await stop_house(home)

    async def test_a_deleted_price_entity_is_no_price(self) -> None:
        home = await start(ENERGY)
        try:
            home.hass.states.async_remove("sensor.stroomprijs")
            await home.settle()
            assert home.values("cheapest_heat")["electric_cost"] is None
        finally:
            await stop_house(home)

    async def test_nothing_known_gives_no_answer(self) -> None:
        energy = {**ENERGY, "boiler_efficiency": 0.0}
        home = await start(energy, stroomprijs="unavailable")
        try:
            assert home.value("cheapest_heat") == "unknown"
        finally:
            await stop_house(home)

    async def test_before_the_first_round_the_outdoor_temperature_is_unknown(self) -> None:
        from custom_components.climate_director.sensor import HeatCostSensor

        home = await start(ENERGY)
        try:
            sensor = HeatCostSensor(home.coordinator)
            sensor.hass = home.hass
            home.coordinator.world = None
            assert sensor.native_value == "gas"
            assert sensor.extra_state_attributes["cop"] is None
        finally:
            await stop_house(home)


class TestWhetherTheSensorExists:
    @pytest.mark.parametrize(
        "energy",
        [
            None,
            {**ENERGY, "gas_price": 0.0},
            {**ENERGY, "grid_price_sensor": ""},
            {**ENERGY, "cop_curve": ""},
        ],
        ids=["geen_instelling", "geen_gasprijs", "geen_stroomprijs", "geen_curve"],
    )
    async def test_not_enough_set_means_no_sensor(self, energy: dict[str, Any] | None) -> None:
        home = await start(energy)
        try:
            assert "cheapest_heat" not in home.registered()
        finally:
            await stop_house(home)

    async def test_enough_set_means_a_sensor_the_cleanup_keeps(self) -> None:
        from custom_components.climate_director import _wanted_entity_keys

        home = await start(ENERGY)
        try:
            assert "cheapest_heat" in home.registered()
            assert "cheapest_heat" in _wanted_entity_keys(home.coordinator.config)
        finally:
            await stop_house(home)
