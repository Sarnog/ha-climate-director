"""Temperaturen lezen uit alles wat Home Assistant aanbiedt.

Reading temperatures from everything Home Assistant offers."""

from __future__ import annotations

import pytest
from harness_live import (
    settings,
    source,
    start_house,
    stop_house,
    zone,
)
from live_helpers import (
    LIVING,
    cold_one_room,
    simple_installation,
)

pytest_plugins = ["live_fixtures"]
pytestmark = pytest.mark.usefixtures("appliance")


class TestReadingTemperaturesFromAnything:
    """Een kamertemperatuur mag uit een sensor, een weerbericht of een unit komen.

    A room temperature may come from a sensor, a weather forecast or a unit.
    """

    async def test_a_weather_entity_carries_the_outdoor_temperature(self) -> None:
        installation = {
            "zones": [
                zone(
                    "woonkamer",
                    sources=[
                        source(
                            "airco",
                            LIVING,
                            role="heat_cool",
                            outdoor={"maximum": 15.0},
                        )
                    ],
                    heat=settings(21.0, 20.0),
                )
            ],
            "outdoor_sensor": "weather.thuis",
        }
        home = await start_house(
            installation,
            states={**cold_one_room(), "weather.thuis": ("rainy", {"temperature": 4.0})},
        )
        try:
            assert home.coordinator.world.outdoor_temperature == 4.0
            assert home.state(LIVING) == "heat"
        finally:
            await stop_house(home)

    async def test_a_climate_entity_may_be_the_room_sensor(self) -> None:
        """Dan telt `current_temperature`, nooit het setpoint.

        Then `current_temperature` counts, never the setpoint.
        """
        installation = {
            "zones": [
                zone(
                    "woonkamer",
                    indoor_sensor=LIVING,
                    sources=[source("airco", LIVING, role="heat_cool")],
                    heat=settings(21.0, 20.0),
                )
            ]
        }
        home = await start_house(
            installation,
            states={LIVING: ("off", {"current_temperature": 17.0, "temperature": 25.0})},
        )
        try:
            assert home.coordinator.world.indoor("woonkamer") == 17.0
            assert home.state(LIVING) == "heat"
        finally:
            await stop_house(home)

    @pytest.mark.parametrize("reading", ["", "unknown", "unavailable", "kapot", "NaN"])
    async def test_an_unreadable_sensor_never_breaks_the_run(self, reading: str) -> None:
        home = await start_house(
            simple_installation(), states={**cold_one_room(), "sensor.woonkamer": (reading, {})}
        )
        try:
            assert home.coordinator.data is not None
            assert home.state(LIVING) == "off"
        finally:
            await stop_house(home)
