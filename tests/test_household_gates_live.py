"""De huishoudpoorten in een echte Home Assistant.

The household gates inside a real Home Assistant."""

from __future__ import annotations

from datetime import timedelta

from harness_live import (
    start_house,
    stop_house,
)
from live_helpers import (
    LIVING,
    cold_at_home,
    gated_house,
)

from custom_components.climate_director import coordinator as coordinator_module


class TestTheHouseholdGates:
    """Wie thuis is, wakker is en binnen zijn rooster valt.

    Who is home, awake and inside their schedule.
    """

    async def test_nobody_home_stops_the_house(self) -> None:
        home = await start_house(
            gated_house(), states={**cold_at_home(), "person.danny": ("not_home", {})}
        )
        try:
            assert home.state(LIVING) == "off"
            assert home.values("zone_woonkamer_source")["reason"] == "nobody_home"
        finally:
            await stop_house(home)

    async def test_asleep_stops_the_house_when_awake_is_required(self) -> None:
        home = await start_house(
            gated_house(require_awake=True),
            states={**cold_at_home(), "sensor.danny_lader": ("wireless", {})},
        )
        try:
            assert home.values("zone_woonkamer_source")["reason"] == "everyone_asleep"
        finally:
            await stop_house(home)

    async def test_switching_the_awake_requirement_off_lets_it_run(self) -> None:
        home = await start_house(
            gated_house(require_awake=False),
            states={**cold_at_home(), "sensor.danny_lader": ("wireless", {})},
        )
        try:
            assert home.state(LIVING) == "heat"
        finally:
            await stop_house(home)

    async def test_a_guest_carries_the_house_inside_the_guest_window(self) -> None:
        home = await start_house(
            gated_house(guest_window={"start": "00:00:00", "end": "23:59:00"}),
            states={**cold_at_home(), "person.danny": ("not_home", {})},
        )
        try:
            assert home.state(LIVING) == "off"
            await home.call("switch", "turn_on", {"entity_id": home.by_key("guest")})
            await home.evaluate()
            assert home.state(LIVING) == "heat"
        finally:
            await stop_house(home)

    async def test_a_guest_outside_the_guest_window_changes_nothing(self) -> None:
        """Een venster van een minuut, twee uur geleden: daar zitten we nooit in.

        Het venster wordt uit dezelfde klok afgeleid waar de coordinator de wereld
        op bouwt, zodat de test op elk uur van de dag hetzelfde meet. Een vast
        venster (03:00:00-03:01:00) was 59 minuten per dag rood zodra de run in
        uur 3 viel maar de minuut al voorbij was.

        A one-minute window two hours ago: we are never inside it.

        The window is derived from the same clock the coordinator builds the world
        on, so the test measures the same at any hour of the day. A fixed window
        (03:00:00-03:01:00) was red for 59 minutes a day whenever the run fell in
        hour 3 but the minute had already passed.
        """
        now = coordinator_module.dt_util.now()
        window_start = now - timedelta(hours=2)
        window_end = window_start + timedelta(minutes=1)
        home = await start_house(
            gated_house(
                guest_window={
                    "start": window_start.strftime("%H:%M:%S"),
                    "end": window_end.strftime("%H:%M:%S"),
                }
            ),
            states={**cold_at_home(), "person.danny": ("not_home", {})},
        )
        try:
            await home.call("switch", "turn_on", {"entity_id": home.by_key("guest")})
            await home.evaluate()
            assert home.state(LIVING) == "off"
        finally:
            await stop_house(home)
