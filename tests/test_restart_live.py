"""Een herstart met een lopend verzoek en een bewaarde prioriteit.

A restart with a running request and a stored priority."""

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


class TestAcrossARestart:
    """Een verzoek en een handmatige uitzetting overleven een herstart.

    A request and a hand-operated stand-down survive a restart.
    """

    async def test_a_running_request_comes_back(self) -> None:
        live = await start_house(
            two_zone_installation(), states=cold_two_rooms(), entry_id="restart_probe"
        )
        config_dir = live.config_dir
        try:
            live.set("person.danny", "not_home")
            await live.evaluate()
            live.coordinator.async_precondition(["woonkamer"], 90)
            await live.evaluate()
            assert live.state(LIVING) == "heat"
        finally:
            await stop_house(live)

        again = await start_house(
            two_zone_installation(),
            states={**cold_two_rooms(), "person.danny": ("not_home", {})},
            entry_id="restart_probe",
            config_dir=config_dir,
        )
        try:
            assert again.coordinator._live_preconditions(), (
                "het verzoek hoort de herstart te overleven"
            )
            assert again.state(LIVING) == "heat"
        finally:
            await stop_house(again)
