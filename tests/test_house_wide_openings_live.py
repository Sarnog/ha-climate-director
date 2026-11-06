"""Een gewijzigd apparaat en de huisbrede stoplijst, in een echte flow.

A changed appliance and the house-wide stop list, in a real flow."""

from __future__ import annotations

from typing import Any

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
)

from custom_components.climate_director.const import CONF_INSTALLATION

pytest_plugins = ["live_fixtures"]
pytestmark = pytest.mark.usefixtures("appliance")


class TestAChangedApplianceOnTheHouseWideStopList:
    """Wie het apparaat van een bron wijzigt, hoort wat er met de stoplijst gebeurt.

    Changing a source's appliance must be reported on the house-wide stop list.
    """

    def _installation(self) -> dict[str, Any]:
        """One room whose only source steers LIVING, with LIVING house-wide stopped."""
        return {
            "zones": [
                zone(
                    "woonkamer",
                    sources=[source("airco", LIVING, role="heat_cool")],
                    heat=settings(21.0, 20.0),
                )
            ],
            "openings": [{"entity_id": "binary_sensor.achterdeur"}],
            "house_wide_openings": [LIVING],
        }

    async def test_the_save_screen_reports_the_dropped_appliance(self) -> None:
        """Na een gewijzigd apparaat meldt het opslaanscherm het oude id, in plaats
        van het stilletjes uit de huisbrede stoplijst te halen.

        After a changed appliance the save screen reports the old id instead of
        silently dropping it from the house-wide stop list.
        """
        home = await start_house(self._installation(), states=cold_one_room())
        try:
            flow = home.hass.config_entries.options
            result = await flow.async_init(home.entry.entry_id)
            result = await flow.async_configure(result["flow_id"], {"next_step_id": "zones"})
            result = await flow.async_configure(result["flow_id"], {"zone": "0"})
            result = await flow.async_configure(
                result["flow_id"],
                {
                    "name": "Woonkamer",
                    "indoor_sensor": "sensor.woonkamer",
                    "priority": 0,
                    "gate": "household",
                    "presence_state": "on",
                    "enable_heat": True,
                    "heat_target": 21.0,
                    "heat_start_at": 20.0,
                    "heat_hysteresis": 1.0,
                    "enable_cool": False,
                    "cool_target": 23.0,
                    "cool_start_at": 24.0,
                    "cool_hysteresis": 1.0,
                    "cool_summer_only": True,
                    "delete": False,
                    "when_done": "keep",
                },
            )
            assert result["step_id"] == "sources"
            result = await flow.async_configure(result["flow_id"], {"source": "0"})

            # The source keeps its id but now steers another appliance.
            result = await flow.async_configure(
                result["flow_id"],
                {
                    "entity_id": "climate.andere",
                    "role": "heat_cool",
                    "autostart": True,
                    "priority": 0,
                    "delete": False,
                    "when_done": "keep",
                },
            )
            assert result["step_id"] == "sources"
            result = await flow.async_configure(result["flow_id"], {"source": "back_to_menu"})
            result = await flow.async_configure(result["flow_id"], {"next_step_id": "save"})

            assert result["type"] == "form"
            assert result["step_id"] == "save"
            assert LIVING in result["description_placeholders"]["problems"]
            assert "never steers it" in result["description_placeholders"]["problems"]
            # The stored list still holds the old id: nothing was silently dropped.
            assert LIVING in home.entry.options[CONF_INSTALLATION]["house_wide_openings"]
        finally:
            await stop_house(home)

    async def test_confirming_the_openings_screen_removes_it_by_hand(self) -> None:
        """Het openingsscherm bevestigen schrijft wat het toont en ruimt zo op.

        Confirming the openings screen writes what it shows and thereby tidies up.
        """
        home = await start_house(self._installation(), states=cold_one_room())
        try:
            flow = home.hass.config_entries.options
            result = await flow.async_init(home.entry.entry_id)
            result = await flow.async_configure(result["flow_id"], {"next_step_id": "zones"})
            result = await flow.async_configure(result["flow_id"], {"zone": "0"})
            result = await flow.async_configure(
                result["flow_id"],
                {
                    "name": "Woonkamer",
                    "indoor_sensor": "sensor.woonkamer",
                    "priority": 0,
                    "gate": "household",
                    "presence_state": "on",
                    "enable_heat": True,
                    "heat_target": 21.0,
                    "heat_start_at": 20.0,
                    "heat_hysteresis": 1.0,
                    "enable_cool": False,
                    "cool_target": 23.0,
                    "cool_start_at": 24.0,
                    "cool_hysteresis": 1.0,
                    "cool_summer_only": True,
                    "delete": False,
                    "when_done": "keep",
                },
            )
            assert result["step_id"] == "sources"
            result = await flow.async_configure(result["flow_id"], {"source": "0"})
            result = await flow.async_configure(
                result["flow_id"],
                {
                    "entity_id": "climate.andere",
                    "role": "heat_cool",
                    "autostart": True,
                    "priority": 0,
                    "delete": False,
                    "when_done": "keep",
                },
            )
            result = await flow.async_configure(result["flow_id"], {"source": "back_to_menu"})
            result = await flow.async_configure(result["flow_id"], {"next_step_id": "openings"})
            # The picker shows only steered appliances, so the stale id is gone
            # from the suggested value; confirming writes exactly that list.
            result = await flow.async_configure(result["flow_id"], {"opening": "back_to_menu"})
            result = await flow.async_configure(result["flow_id"], {"next_step_id": "save"})
            await home.hass.async_block_till_done()
            assert result["type"] == "create_entry"
            assert LIVING not in home.entry.options[CONF_INSTALLATION]["house_wide_openings"]
        finally:
            await stop_house(home)
