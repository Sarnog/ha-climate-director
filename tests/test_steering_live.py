"""Echte opdrachten, regen, schaduwmodus en de soorten nagebouwde apparaten.

Real commands, rain, shadow mode and the kinds of stand-in appliances."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from harness_live import (
    LiveHome,
    start_house,
    stop_house,
)
from live_helpers import (
    ATTIC,
    LIVING,
    SPARE,
    cold_two_rooms,
    two_zone_installation,
)

pytest_plugins = ["live_fixtures"]
pytestmark = pytest.mark.usefixtures("appliance")


class TestSteeringForReal:
    """De opdrachten komen als echte acties bij de apparaten aan.

    The commands arrive at the appliances as real actions.
    """

    async def test_both_rooms_were_started(self, home: LiveHome) -> None:
        assert home.state(LIVING) == "heat"
        assert home.state(ATTIC) == "heat"
        assert home.attributes(LIVING)["temperature"] == 21.0

    async def test_the_stand_in_was_not_started(self, home: LiveHome) -> None:
        assert home.state(SPARE) == "off"

    async def test_deciding_again_changes_nothing(self, home: LiveHome) -> None:
        home.clear_calls()
        await home.evaluate()
        assert home.climate_calls() == []

    async def test_a_warm_room_is_switched_off_again(self, home: LiveHome) -> None:
        home.set("sensor.woonkamer", "23.0")
        await home.evaluate()
        assert home.state(LIVING) == "off"

    async def test_the_dead_band_keeps_it_running(self, home: LiveHome) -> None:
        # Aan bij 20, uit pas bij 21: 20,5 hoort door te draaien.
        # On at 20, off only at 21: 20.5 should keep running.
        home.set("sensor.woonkamer", "20.5")
        await home.evaluate()
        assert home.state(LIVING) == "heat"

    async def test_an_open_door_stops_the_house(self, home: LiveHome) -> None:
        home.set("binary_sensor.achterdeur", "on")
        await home.evaluate()
        assert home.state(LIVING) == "off"
        assert home.state(ATTIC) == "off"

    async def test_the_debouncer_carries_a_state_change_through(self, home: LiveHome) -> None:
        """Zonder aanroep van buiten: alleen een sensor die verandert.

        Without a call from outside: only a sensor that changes.
        """
        home.set("sensor.woonkamer", "22.0")
        await asyncio.sleep(1.4)
        await home.hass.async_block_till_done()
        assert home.state(LIVING) == "off"


class TestPrecipitation:
    """Regen zet de 'zet een raam open'-grens opzij, met nalooptijd."""

    def _two_zone_installation(self, grace: int) -> dict[str, Any]:
        found = two_zone_installation()
        found["zones"][0]["heat"] = {
            **found["zones"][0]["heat"],
            "outdoor": {"minimum": None, "maximum": 25.0},
        }
        found["precipitation"] = {
            "source": "weather.buienradar",
            "states": ["rainy", "pouring"],
            "grace": grace,
        }
        return found

    def _states(self) -> dict[str, tuple[str, dict[str, Any]]]:
        return {
            **cold_two_rooms(),
            "sensor.buiten": ("26.0", {}),
            "weather.buienradar": ("rainy", {}),
        }

    async def test_rain_lifts_the_zone_bound_and_stopping_rain_drops_it(self) -> None:
        """Buiten 26 graden is boven de verwarmgrens; regen zet die opzij."""
        live = await start_house(self._two_zone_installation(grace=0), states=self._states())
        try:
            assert live.state(LIVING) == "heat"
            live.set("weather.buienradar", "cloudy")
            await live.evaluate()
            assert live.state(LIVING) == "off"
        finally:
            await stop_house(live)

    async def test_rain_keeps_counting_for_the_grace_period(self) -> None:
        """Een bui van vijf minuten hoort de regeling niet te laten stuiteren."""
        live = await start_house(self._two_zone_installation(grace=900), states=self._states())
        try:
            assert live.state(LIVING) == "heat"
            live.set("weather.buienradar", "cloudy")
            await live.evaluate()
            assert live.state(LIVING) == "heat", "de nalooptijd hoort regen te laten meetellen"
        finally:
            await stop_house(live)


class TestShadowMode:
    """In schaduwmodus gebeurt er niets, en wordt alles wel opgeschreven.

    In shadow mode nothing happens, and everything is written down.
    """

    async def test_nothing_is_steered_but_it_is_reported(self) -> None:
        live = await start_house(two_zone_installation(), states=cold_two_rooms(), shadow=True)
        try:
            assert live.climate_calls() == []
            assert live.state(LIVING) == "off"
            would = live.values("last_decision")["would_change"]
            assert LIVING in would
            assert ATTIC in would
            assert live.values("last_decision")["shadow_mode"] is True
        finally:
            await stop_house(live)


class TestTheHarnessApplianceKinds:
    """De nieuwe apparaattypes van het harnas leggen M2 en M3 live vast.

    The harness's new appliance kinds pin M2 and M3 down live.
    """

    async def test_a_refused_setpoint_is_offered_again(self) -> None:
        """Een geweigerd setpoint wordt de volgende ronde opnieuw aangeboden.

        A refused setpoint is offered again the next round.
        """
        live = await start_house(
            two_zone_installation(), states=cold_two_rooms(), appliance="refuses_set_temperature"
        )
        try:
            await live.evaluate()
            offered = [call for name, call in live.calls if name == "set_temperature"]
            assert offered, "het setpoint is nooit aangeboden"

            await live.settle()
            await live.evaluate()
            offered = [call for name, call in live.calls if name == "set_temperature"]
            assert len(offered) >= 2, "het geweigerde setpoint is niet opnieuw aangeboden"
        finally:
            await stop_house(live)

    async def test_a_forgotten_setpoint_is_sent_again_on_the_next_start(self) -> None:
        """Een apparaat dat zijn setpoint bij `off` vergeet, krijgt het opnieuw.

        An appliance forgetting its setpoint on `off` gets it again at the next
        start.
        """
        live = await start_house(
            two_zone_installation(), states=cold_two_rooms(), appliance="forgets_setpoint"
        )
        try:
            await live.settle()
            assert live.state(LIVING) == "heat"
            assert live.attributes(LIVING).get("temperature") == 21.0

            live.set("sensor.woonkamer", "23.0")
            await live.settle()
            await live.evaluate()
            assert live.state(LIVING) == "off"
            assert "temperature" not in live.attributes(LIVING)

            live.set("sensor.woonkamer", "18.0")
            await live.settle()
            await live.evaluate()
            assert live.state(LIVING) == "heat"
            offered = [call for name, call in live.calls if name == "set_temperature"]
            assert offered, "het vergeten setpoint is niet opnieuw meegestuurd"
        finally:
            await stop_house(live)

    async def test_a_drop_out_off_then_own_start_then_a_hand_is_noticed(self) -> None:
        """Ons uit via unavailable, zelf weer aan, dan een hand: die is een hand.

        Our off via unavailable, on again by us, then a hand: that is a hand.
        """
        states = {
            "sensor.woonkamer": ("22.0", {}),
            "sensor.zolder": ("22.0", {}),
            "sensor.buiten": ("4.0", {}),
            LIVING: ("heat", {"hvac_modes": ["heat", "off"], "temperature": 21.0}),
            SPARE: ("off", {"hvac_modes": ["heat", "off"]}),
            ATTIC: ("off", {"hvac_modes": ["heat", "off"]}),
            "person.danny": ("home", {}),
            "sensor.danny_lader": ("none", {}),
            "binary_sensor.achterdeur": ("off", {}),
        }
        live = await start_house(
            two_zone_installation(), states=states, appliance="drops_out_on_off"
        )
        try:
            await live.settle()
            assert live.state(LIVING) == "off"

            live.set("sensor.woonkamer", "18.0")
            await live.settle()
            await live.evaluate()
            assert live.state(LIVING) == "heat"

            live.set(LIVING, "off", hvac_modes=["heat", "off"], temperature=21.0)
            await live.settle()
            await live.evaluate()
            assert live.state(LIVING) == "off", "de director zet de hand weer aan"
            assert "woonkamer" in live.coordinator.handed_back
        finally:
            await stop_house(live)
