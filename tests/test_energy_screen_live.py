"""Het energiescherm in de opties-flow van een echte Home Assistant.

The energy screen in the options flow of a real Home Assistant.

Dekking: het scherm opent vanuit het hoofdmenu, bewaart wat erop staat in
`energy`, weigert een COP-curve die niet te lezen is, laat bij weggooien alles
staan en raakt de algemene instellingen niet aan. Niet gedekt: de vormgeving.

Coverage: the screen opens from the main menu, stores what is on it in
`energy`, refuses a COP curve that does not read, leaves everything alone when
discarded and does not touch the general settings. Not covered: the layout.
"""

from __future__ import annotations

from typing import Any

import pytest
from flow_helpers import cold, menu, save, two_rooms
from harness_live import start_house, stop_house

pytest_plugins = ["live_fixtures"]
pytestmark = pytest.mark.usefixtures("appliance")

FILLED: dict[str, Any] = {
    "grid_price_sensor": "sensor.stroomprijs",
    "grid_price": 0.31,
    "feed_in_sensor": "sensor.terugleverprijs",
    "feed_in_price": 0.07,
    "surplus_sensor": "sensor.overschot",
    "gas_price_sensor": "sensor.gasprijs",
    "gas_price": 1.87,
    "kwh_per_m3": 9.77,
    "boiler_efficiency": 0.9,
    "cop_curve": "2:2.0, 5:2.8, 8:3.0",
    "cost_control": True,
    "season_lock": False,
    "cold_limit": 2.0,
    "switch_margin": 10.0,
    "when_done": "keep",
}


async def test_the_screen_opens_with_the_fields_in_reading_order() -> None:
    home = await start_house(two_rooms(), states=cold())
    try:
        result = await menu(home, "energy")
        assert result["step_id"] == "energy"
        assert [str(key) for key in result["data_schema"].schema] == [
            "grid_price_sensor",
            "grid_price",
            "feed_in_sensor",
            "feed_in_price",
            "surplus_sensor",
            "gas_price_sensor",
            "gas_price",
            "kwh_per_m3",
            "boiler_efficiency",
            "cop_curve",
            "cost_control",
            "season_lock",
            "cold_limit",
            "switch_margin",
            "when_done",
        ]
    finally:
        await stop_house(home)


async def test_a_filled_screen_is_stored_under_energy() -> None:
    home = await start_house(two_rooms(), states=cold())
    try:
        result = await menu(home, "energy")
        result = await home.hass.config_entries.options.async_configure(result["flow_id"], FILLED)
        assert result["type"] == "menu"
        stored = await save(home, result["flow_id"])
        assert stored["energy"] == {
            "grid_price_sensor": "sensor.stroomprijs",
            "grid_price": 0.31,
            "feed_in_sensor": "sensor.terugleverprijs",
            "feed_in_price": 0.07,
            "surplus_sensor": "sensor.overschot",
            "gas_price_sensor": "sensor.gasprijs",
            "gas_price": 1.87,
            "kwh_per_m3": 9.77,
            "boiler_efficiency": 0.9,
            "cop_curve": "2:2.0, 5:2.8, 8:3.0",
            "cost_control": True,
            "season_lock": False,
            "cold_limit": 2.0,
            "switch_margin": 10.0,
        }
    finally:
        await stop_house(home)


async def test_a_curve_that_does_not_read_is_refused() -> None:
    home = await start_house(two_rooms(), states=cold())
    try:
        result = await menu(home, "energy")
        result = await home.hass.config_entries.options.async_configure(
            result["flow_id"], {**FILLED, "cop_curve": "kapot"}
        )
        assert result["step_id"] == "energy"
        assert result["errors"] == {"cop_curve": "cop_curve_invalid"}
        assert "energy" not in home.entry.options["installation"]
    finally:
        await stop_house(home)


async def test_discarding_stores_nothing_and_returns_to_the_menu() -> None:
    home = await start_house(two_rooms(), states=cold())
    try:
        result = await menu(home, "energy")
        result = await home.hass.config_entries.options.async_configure(
            result["flow_id"], {**FILLED, "when_done": "discard"}
        )
        assert result["type"] == "menu"
        stored = await save(home, result["flow_id"])
        assert "grid_price_sensor" not in stored.get("energy", {})
    finally:
        await stop_house(home)


async def test_saving_the_energy_screen_leaves_the_general_settings_alone() -> None:
    installation = {**two_rooms(), "outdoor_sensor": "sensor.buiten", "outdoor_hysteresis": 1.5}
    home = await start_house(installation, states=cold())
    try:
        result = await menu(home, "energy")
        result = await home.hass.config_entries.options.async_configure(result["flow_id"], FILLED)
        stored = await save(home, result["flow_id"])
        assert stored["outdoor_sensor"] == "sensor.buiten"
        assert stored["outdoor_hysteresis"] == 1.5
    finally:
        await stop_house(home)
