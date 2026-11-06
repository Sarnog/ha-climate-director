"""Opstarten met een half geladen wereld zet niets uit.

Starting with a half-loaded world switches nothing off."""

from __future__ import annotations

import pytest
from harness_live import (
    start_house,
    stop_house,
)
from live_helpers import (
    LIVING,
    cold_two_rooms,
    two_zone_installation,
)

pytest_plugins = ["live_fixtures"]
pytestmark = pytest.mark.usefixtures("appliance")


class TestStartupWithHalfLoadedState:
    """Opstarten met een half geladen wereld mag niets uitzetten.

    Starting up with a half-loaded world must not switch anything off.
    """

    async def test_an_unreadable_sensor_leaves_the_running_appliance_alone(self) -> None:
        """De sensor ontbreekt nog, het apparaat draait: geen `set_hvac_mode`.

        The sensor is still missing and the appliance runs: no `set_hvac_mode`.
        """
        states = cold_two_rooms()
        del states["sensor.woonkamer"]
        states[LIVING] = ("heat", {"temperature": 21.0})

        home = await start_house(two_zone_installation(), states=states)
        try:
            calls = home.climate_calls()
            assert not [call for call in calls if call[1].get("entity_id") == LIVING]
        finally:
            await stop_house(home)
