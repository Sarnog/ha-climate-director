"""Een herstart van de wizard en de bewaarde standen.

A restart of the wizard and the stored states."""

from __future__ import annotations

import pytest
from harness_live import (
    new_config_dir,
    settings,
    source,
    start_house,
    stop_house,
    zone,
)
from live_helpers import (
    ATTIC,
    LIVING,
    cold_one_room,
    simple_installation,
)

pytest_plugins = ["live_fixtures"]
pytestmark = pytest.mark.usefixtures("appliance")


class TestAcrossARestart:
    """Standen die een gebruiker zette horen na een herstart nog te staan.

    States a user set should still stand after a restart.
    """

    async def test_the_master_switch_stays_off(self) -> None:
        config_dir = new_config_dir()
        home = await start_house(
            simple_installation(),
            states=cold_one_room(),
            entry_id="herstart",
            config_dir=config_dir,
        )
        try:
            assert home.state(LIVING) == "heat"
            await home.call("switch", "turn_off", {"entity_id": home.by_key("master")})
            await home.evaluate()
            # Noodknop: de director stuurt niets, dus de airco blijft draaien.
            # Emergency stop: the director sends nothing, so the airco keeps running.
            assert home.state(LIVING) == "heat"
        finally:
            await stop_house(home)

        again = await start_house(
            simple_installation(),
            states=cold_one_room(),
            entry_id="herstart",
            config_dir=config_dir,
        )
        try:
            assert again.value("master") == "off", "de hoofdschakelaar hoort uit te blijven"
            # Ook na een herstart stuurt de noodknop niets: het apparaat blijft
            # zoals het opgestart is.
            # After a restart too the emergency stop sends nothing: the appliance
            # stays as it started up.
            assert again.state(LIVING) == "off"
            assert not again.climate_calls(), "een uitgezette noodknop hoort niets te sturen"
        finally:
            await stop_house(again)

    async def test_a_priority_set_by_an_automation_comes_back(self) -> None:
        config_dir = new_config_dir()
        installation = {
            "zones": [
                zone(
                    "woonkamer",
                    sources=[source("airco", LIVING, role="heat_cool")],
                    heat=settings(21.0, 20.0),
                    priority=0,
                ),
                zone(
                    "zolder",
                    sources=[source("airco2", ATTIC, role="heat_cool")],
                    heat=settings(21.0, 20.0),
                    priority=1,
                ),
            ]
        }
        states = {**cold_one_room(), "sensor.zolder": ("18.0", {}), ATTIC: ("off", {})}

        home = await start_house(
            installation, states=states, entry_id="voorrang", config_dir=config_dir
        )
        try:
            await home.call(
                "number",
                "set_value",
                {"entity_id": home.by_key("zone_zolder_priority"), "value": 4},
            )
            await home.settle()
            assert home.coordinator.zone_priorities["zolder"] == 4
        finally:
            await stop_house(home)

        again = await start_house(
            installation, states=states, entry_id="voorrang", config_dir=config_dir
        )
        try:
            assert again.coordinator.zone_priorities["zolder"] == 4, (
                "wat een automatisering zette hoort een herstart te overleven"
            )
        finally:
            await stop_house(again)

    async def test_a_changed_configuration_wins_from_the_restored_priority(self) -> None:
        """Wie in de wizard iets nieuws zegt, overstemt de bewaarde waarde.

        Whoever says something new in the wizard overrules the stored value.
        """
        from custom_components.climate_director.number import resolve_initial

        assert resolve_initial(configured=2, last_value=4, last_configured=2) == 4
        assert resolve_initial(configured=3, last_value=4, last_configured=2) == 3
        assert resolve_initial(configured=3, last_value=None, last_configured=None) == 3
