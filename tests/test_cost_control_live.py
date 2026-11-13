"""Schakelen op kosten in een echte Home Assistant.

Switching on cost in a real Home Assistant.

Dekking: met kostenbesturing aan kiest de goedkoopste soort welk apparaat
verwarmt, een nieuwe prijs verschuift dat meteen, onder de koudegrens wint gas,
uit laat het buitenvenster beslissen, en de omslagsensor volgt de prijs. Niet
gedekt: wat het apparaat daarna doet met het commando.

Coverage: with cost control on, the cheaper kind picks which appliance heats, a
new price moves that at once, below the cold limit gas wins, off lets the outdoor
window decide, and the changeover sensor follows the price. Not covered: what
the appliance does with the command afterwards.
"""

from __future__ import annotations

from typing import Any

import pytest
from harness_live import LiveHome, source, start_house, stop_house
from live_helpers import BOILER, LIVING, cold_two_rooms, settings

pytest_plugins = ["live_fixtures"]
pytestmark = pytest.mark.usefixtures("appliance")

ENERGY: dict[str, Any] = {
    "grid_price_sensor": "sensor.stroomprijs",
    "gas_price": 1.8,
    "kwh_per_m3": 9.77,
    "boiler_efficiency": 0.9,
    "cop_curve": "-5:2.0, 5:2.8, 15:4.5",
    "cost_control": True,
    "cold_limit": 2.0,
    "switch_margin": 10.0,
}


def installation(energy: dict[str, Any]) -> dict[str, Any]:
    """Return a room heated by a boiler in the cold and an air conditioner above 3 degrees."""
    return {
        "zones": [
            {
                "zone_id": "woonkamer",
                "name": "Woonkamer",
                "indoor_sensor": "sensor.woonkamer",
                "sources": [
                    source(
                        "ketel",
                        BOILER,
                        role="heat_only",
                        energy="gas",
                        priority=1,
                        outdoor={"minimum": None, "maximum": 3.0},
                    ),
                    source(
                        "airco",
                        LIVING,
                        role="heat_cool",
                        energy="electric",
                        priority=2,
                        outdoor={"minimum": 3.0, "maximum": None},
                    ),
                ],
                "heat": settings(21.0, 20.0),
            }
        ],
        "outdoor_sensor": "sensor.buiten",
        "energy": energy,
    }


def world(outdoor: str = "8.0", power: str = "0.30") -> dict[str, tuple[str, dict[str, Any]]]:
    states = {
        **cold_two_rooms(),
        "sensor.buiten": (outdoor, {}),
        "sensor.stroomprijs": (power, {}),
        BOILER: ("off", {"temperature": 19.0}),
    }
    return states


async def serving(home: LiveHome) -> str | None:
    """Decide once and return the source the plan names for the living room."""
    await home.evaluate()
    await home.settle()
    decision = home.coordinator.data.decision_for("woonkamer")
    return None if decision is None else decision.source_id


class TestCostControl:
    async def test_the_window_decides_when_cost_control_is_off(self) -> None:
        home = await start_house(
            installation({**ENERGY, "cost_control": False}), states=world(power="0.90")
        )
        try:
            assert await serving(home) == "airco"
            assert home.coordinator.round.heat_pick.preferred is None
        finally:
            await stop_house(home)

    async def test_dear_power_sends_the_heating_to_gas_inside_the_airco_window(self) -> None:
        home = await start_house(installation(ENERGY), states=world(power="0.90"))
        try:
            assert await serving(home) == "ketel"
        finally:
            await stop_house(home)

    async def test_cheap_power_picks_the_airco(self) -> None:
        home = await start_house(installation(ENERGY), states=world(power="0.10"))
        try:
            assert await serving(home) == "airco"
        finally:
            await stop_house(home)

    async def test_a_new_price_moves_the_choice_in_the_next_round(self) -> None:
        home = await start_house(installation(ENERGY), states=world(power="0.10"))
        try:
            assert await serving(home) == "airco"
            home.set("sensor.stroomprijs", "0.90")
            assert await serving(home) == "ketel"
        finally:
            await stop_house(home)

    async def test_below_the_cold_limit_gas_wins_whatever_the_price(self) -> None:
        home = await start_house(installation(ENERGY), states=world(outdoor="1.0", power="0.01"))
        try:
            assert await serving(home) == "ketel"
            assert home.coordinator.round.heat_pick.reason == "cold_limit"
        finally:
            await stop_house(home)

    async def test_cheap_power_beats_the_boiler_window_above_the_cold_limit(self) -> None:
        # 2,5 graden valt in het buitenvenster van de ketel (tot 3), maar de
        # koudegrens is 2: de goedkoopste soort mag dan ook echt kiezen.
        home = await start_house(installation(ENERGY), states=world(outdoor="2.5", power="0.01"))
        try:
            assert await serving(home) == "airco"
        finally:
            await stop_house(home)

    async def test_the_sensor_shows_what_the_preference_is(self) -> None:
        home = await start_house(installation(ENERGY), states=world(power="0.90"))
        try:
            await serving(home)
            attributes = home.values("cheapest_heat")
            assert attributes["cost_control"] is True
            assert attributes["preferred_source"] == "gas"
            assert attributes["preferred_reason"] == "cost"
            assert attributes["steered_zones"] == ["woonkamer"]
        finally:
            await stop_house(home)

    async def test_no_zone_is_steered_while_no_source_has_an_energy_kind(self) -> None:
        plain = installation(ENERGY)
        for item in plain["zones"][0]["sources"]:
            item["energy"] = "none"
        home = await start_house(plain, states=world())
        try:
            assert home.values("cheapest_heat")["steered_zones"] == []
        finally:
            await stop_house(home)

    async def test_the_price_entities_are_followed_only_with_cost_control_on(self) -> None:
        on = await start_house(installation(ENERGY), states=world())
        try:
            assert "sensor.stroomprijs" in on.coordinator.tracked_entities()
        finally:
            await stop_house(on)
        off = await start_house(installation({**ENERGY, "cost_control": False}), states=world())
        try:
            assert "sensor.stroomprijs" not in off.coordinator.tracked_entities()
        finally:
            await stop_house(off)


class TestChangeoverSensor:
    async def test_it_gives_the_temperature_below_which_gas_wins(self) -> None:
        home = await start_house(installation(ENERGY), states=world(power="0.50"))
        try:
            assert home.values("heat_break_even")["verdict"] == "crossover"
            assert float(home.value("heat_break_even")) == pytest.approx(0.5, abs=0.1)
        finally:
            await stop_house(home)

    async def test_it_follows_the_price(self) -> None:
        home = await start_house(installation(ENERGY), states=world(power="0.30"))
        try:
            assert home.values("heat_break_even")["verdict"] == "electric_always"
            home.set("sensor.stroomprijs", "1.50")
            await home.settle()
            assert home.values("heat_break_even")["verdict"] == "gas_always"
        finally:
            await stop_house(home)

    async def test_it_works_with_a_fixed_power_price(self) -> None:
        energy = {**ENERGY, "grid_price_sensor": "", "grid_price": 0.50}
        home = await start_house(installation(energy), states=world())
        try:
            assert home.values("heat_break_even")["verdict"] == "crossover"
        finally:
            await stop_house(home)


def living_with(own: dict[str, Any]) -> dict[str, Any]:
    """Return the house of `installation` with settings added to its living room."""
    base = installation(ENERGY)
    living = {**base["zones"][0], **own.get("living", {})}
    return {**base, "zones": [living]}


class TestPerZone:
    async def test_a_zone_that_does_not_follow_the_cost_control_keeps_its_windows(self) -> None:
        # Dure stroom stuurt een volgende zone naar gas; deze zone niet.
        home = await start_house(
            living_with({"living": {"cost_control": False}}), states=world(power="0.90")
        )
        try:
            assert await serving(home) == "airco"
            assert home.values("cheapest_heat")["steered_zones"] == []
        finally:
            await stop_house(home)

    async def test_a_zone_with_its_own_cold_limit_goes_to_gas_above_the_house_limit(self) -> None:
        home = await start_house(
            living_with({"living": {"cold_limit": 10.0}}), states=world(outdoor="8.0", power="0.01")
        )
        try:
            assert await serving(home) == "ketel"
            attributes = home.values("cheapest_heat")
            assert attributes["zone_preferences"] == {"woonkamer": "gas"}
            # het huis zelf kiest nog steeds op kosten
            assert attributes["preferred_source"] == "electric"
        finally:
            await stop_house(home)

    async def test_a_zone_cold_limit_lets_electric_return_one_band_above_it(self) -> None:
        home = await start_house(
            living_with({"living": {"cold_limit": 10.0}}), states=world(outdoor="8.0", power="0.01")
        )
        try:
            assert await serving(home) == "ketel"
            home.set("sensor.buiten", "10.2")
            assert await serving(home) == "ketel"  # nog binnen de dode band
            home.set("sensor.buiten", "14.0")
            assert await serving(home) == "airco"
        finally:
            await stop_house(home)


class TestSeasonLock:
    async def test_summer_picks_the_airco_even_when_gas_is_cheaper(self) -> None:
        installed = installation({**ENERGY, "season_lock": True})
        installed["seasons"] = {"source": "summer"}
        home = await start_house(installed, states=world(power="0.90"))
        try:
            assert await serving(home) == "airco"
            assert home.values("cheapest_heat")["preferred_reason"] == "season_lock"
        finally:
            await stop_house(home)

    async def test_winter_decides_on_cost_with_the_lock_on(self) -> None:
        installed = installation({**ENERGY, "season_lock": True})
        installed["seasons"] = {"source": "winter"}
        home = await start_house(installed, states=world(power="0.90"))
        try:
            assert await serving(home) == "ketel"
        finally:
            await stop_house(home)
