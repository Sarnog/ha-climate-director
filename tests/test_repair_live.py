"""De reparatiemelding van een installatie in een echte Home Assistant.

The repair notice of an installation inside a real Home Assistant."""

from __future__ import annotations

import pytest
from harness_live import (
    LiveHome,
    settings,
    source,
    start_house,
    stop_house,
)
from live_helpers import (
    LIVING,
    cold_one_room,
    simple_installation,
)

from custom_components.climate_director.const import CONF_INSTALLATION, DOMAIN

pytest_plugins = ["live_fixtures"]
pytestmark = pytest.mark.usefixtures("appliance")


class TestTheRepairNotice:
    """Een configuratie die niet klopt hoort in Home Assistant zelf op te vallen.

    A configuration that does not add up should stand out in Home Assistant
    itself.
    """

    def _issues(self, home: LiveHome) -> dict:
        from homeassistant.helpers import issue_registry as ir

        registry = ir.async_get(home.hass)
        return {key: item for key, item in registry.issues.items() if key[0] == DOMAIN}

    async def test_a_sound_installation_raises_nothing(self) -> None:
        home = await start_house(simple_installation(), states=cold_one_room())
        try:
            assert self._issues(home) == {}
        finally:
            await stop_house(home)

    async def test_a_zone_without_a_source_is_reported(self) -> None:
        broken = {
            "zones": [
                {
                    "zone_id": "woonkamer",
                    "name": "Woonkamer",
                    "indoor_sensor": "sensor.woonkamer",
                    "sources": [],
                    "heat": settings(21.0, 20.0),
                }
            ]
        }
        home = await start_house(broken, states=cold_one_room())
        try:
            issues = self._issues(home)
            assert issues, "hier hoort een reparatiemelding te staan"
            issue = next(iter(issues.values()))
            assert issue.severity == "warning"
            assert issue.translation_key == "invalid_config"
        finally:
            await stop_house(home)

    async def test_the_notice_disappears_once_it_is_fixed(self) -> None:
        broken = {
            "zones": [
                {
                    "zone_id": "woonkamer",
                    "name": "Woonkamer",
                    "indoor_sensor": "",
                    "sources": [source("airco", LIVING)],
                    "heat": settings(21.0, 20.0),
                }
            ]
        }
        home = await start_house(broken, states=cold_one_room())
        try:
            assert self._issues(home)

            home.hass.config_entries.async_update_entry(
                home.entry, options={**home.entry.options, CONF_INSTALLATION: simple_installation()}
            )
            await home.hass.async_block_till_done()
            assert self._issues(home) == {}
        finally:
            await stop_house(home)
