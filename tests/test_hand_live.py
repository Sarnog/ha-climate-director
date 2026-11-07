"""De hand aan het apparaat en de handstart in een echte Home Assistant.

The hand at the appliance and the hand start inside a real Home Assistant."""

from __future__ import annotations

import pytest
from harness_live import (
    start_house,
    stop_house,
)
from live_helpers import (
    ATTIC,
    LIVING,
    SPARE,
    two_zone_installation,
)

pytest_plugins = ["live_fixtures"]
pytestmark = pytest.mark.usefixtures("appliance")


class TestHandingBackLifecycle:
    """De levensloop van een hand aan het apparaat, met de klok ertussen.

    The lifecycle of a hand at the appliance, with the clock in between.
    """

    async def test_off_then_on_then_a_hand_off_is_noticed(self) -> None:
        """Ons eigen uit, zelf weer aan, dan een hand op uit: dat is een hand.

        Our own off, on again by us, then a hand on off: that is a hand.
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
        live = await start_house(two_zone_installation(), states=states)
        try:
            # Eerste ronde: de kamer is warm, dus ons eigen uit-commando.
            # First round: the room is warm, so our own off command.
            assert live.state(LIVING) == "off"

            live.set("sensor.woonkamer", "18.0")
            await live.settle()
            await live.evaluate()
            assert live.state(LIVING) == "heat"

            live.set(LIVING, "off", hvac_modes=["heat", "off"], temperature=21.0)
            await live.settle()
            await live.evaluate()
            assert live.state(LIVING) == "off", "de director zet de hand weer aan"
            assert "woonkamer" in live.coordinator._handed_back
        finally:
            await stop_house(live)
