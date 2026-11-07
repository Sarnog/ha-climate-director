"""De schakelaars en nummers van de installatie in een echte Home Assistant.

The installation's switches and numbers inside a real Home Assistant."""

from __future__ import annotations

import asyncio

import pytest
from harness_live import (
    LiveHome,
)
from live_helpers import (
    ATTIC,
    LIVING,
)

pytest_plugins = ["live_fixtures"]
pytestmark = pytest.mark.usefixtures("appliance")


class TestTheControls:
    """Schakelaars, getallen en knoppen, aangeroepen zoals een gebruiker het doet.

    Switches, numbers and buttons, called the way a user does.
    """

    async def test_the_master_switch_lets_everything_go(self, home: LiveHome) -> None:
        """Uit = noodknop: de director laat alles los, ook het uitzetten."""
        assert home.state(LIVING) == "heat"
        await home.call("switch", "turn_off", {"entity_id": home.by_key("master")})
        await asyncio.sleep(1.4)
        await home.hass.async_block_till_done()
        assert home.state(LIVING) == "heat"
        assert home.state(ATTIC) == "heat"

        await home.call("switch", "turn_on", {"entity_id": home.by_key("master")})
        await asyncio.sleep(1.4)
        await home.hass.async_block_till_done()
        assert home.state(LIVING) == "heat"

    async def test_a_hand_at_the_appliance_stands_while_the_director_is_off(
        self, home: LiveHome
    ) -> None:
        """Wie de ketel met de hand aanzet houdt hem aan zolang de noodknop uit staat."""
        await home.call("switch", "turn_off", {"entity_id": home.by_key("master")})
        await asyncio.sleep(1.4)
        await home.hass.async_block_till_done()
        home.clear_calls()

        home.set(LIVING, "heat", hvac_modes=["heat", "cool", "off"], temperature=21.0)
        await home.evaluate()
        steered = [data["entity_id"] for _name, data in home.climate_calls()]
        assert LIVING not in steered, "de director overstemt een hand terwijl hij uit staat"

    async def test_the_override_hands_a_zone_over(self, home: LiveHome) -> None:
        await home.call("switch", "turn_on", {"entity_id": home.by_key("zone_woonkamer_override")})
        await asyncio.sleep(1.4)
        await home.hass.async_block_till_done()

        home.set("sensor.woonkamer", "26.0")
        home.clear_calls()
        await home.evaluate()
        steered = [data["entity_id"] for _name, data in home.climate_calls()]
        assert LIVING not in steered, "een overgedragen zone hoort niets te krijgen"

    async def test_the_guest_switch_carries_an_empty_house(self, home: LiveHome) -> None:
        home.set("person.danny", "not_home")
        await home.evaluate()
        assert home.state(LIVING) == "off"

        await home.call("switch", "turn_on", {"entity_id": home.by_key("guest")})
        await asyncio.sleep(1.4)
        await home.hass.async_block_till_done()
        assert home.state(LIVING) == "heat"

    async def test_the_holiday_switch_is_accepted(self, home: LiveHome) -> None:
        await home.call("switch", "turn_on", {"entity_id": home.by_key("holiday")})
        await home.settle()
        assert home.state(home.by_key("holiday")) == "on"
        assert home.coordinator.holiday_mode is True

    async def test_priority_can_be_set_from_an_automation(self, home: LiveHome) -> None:
        await home.call(
            "number",
            "set_value",
            {"entity_id": home.by_key("zone_zolder_priority"), "value": 0},
        )
        await home.settle()
        assert home.coordinator.zone_priorities["zolder"] == 0

    async def test_the_duration_number_holds_its_bounds(self, home: LiveHome) -> None:
        entity_id = home.by_key("precondition_minutes")
        attributes = home.attributes(entity_id)
        assert attributes["min"] == 15
        assert attributes["max"] == 120

        await home.call("number", "set_value", {"entity_id": entity_id, "value": 90})
        await home.settle()
        assert home.coordinator.precondition_minutes == 90

        from homeassistant.exceptions import ServiceValidationError

        with pytest.raises(ServiceValidationError):
            await home.call("number", "set_value", {"entity_id": entity_id, "value": 500})

    async def test_the_button_starts_a_request_for_its_own_zone(self, home: LiveHome) -> None:
        home.set("person.danny", "not_home")
        await home.evaluate()
        assert home.state(LIVING) == "off"

        await home.call(
            "button", "press", {"entity_id": home.by_key("zone_woonkamer_precondition")}
        )
        await asyncio.sleep(1.4)
        await home.hass.async_block_till_done()
        assert home.state(LIVING) == "heat"
        assert home.state(ATTIC) == "off"
