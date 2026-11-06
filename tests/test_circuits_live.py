"""De regels van een gedeeld circuit in een echte Home Assistant.

The rules of a shared circuit inside a real Home Assistant."""

from __future__ import annotations

from harness_live import (
    start_house,
    stop_house,
)
from live_helpers import (
    ATTIC,
    LIVING,
    opposing_world,
    two_room_circuit,
)


class TestTheCircuitRules:
    """Wat er gebeurt als twee kamers het tegelijk anders willen.

    What happens when two rooms want opposite things at once.
    """

    async def test_priority_hands_the_circuit_to_the_first_room(self) -> None:
        home = await start_house(
            two_room_circuit(conflict_policy="priority"), states=opposing_world()
        )
        try:
            assert home.state(LIVING) == "cool"
            assert home.state(ATTIC) == "off"
            assert home.values("zone_zolder_source")["reason"] == "circuit_conflict_lost"
        finally:
            await stop_house(home)

    async def test_a_lost_room_may_keep_circulating_air_when_allowed(self) -> None:
        home = await start_house(
            two_room_circuit(conflict_policy="priority", allow_fan_only_during_conflict=True),
            states=opposing_world(),
        )
        try:
            assert home.state(ATTIC) == "fan_only"
        finally:
            await stop_house(home)

    async def test_demand_hands_it_to_the_room_that_needs_it_most(self) -> None:
        """De zolder wijkt drie graden af, de woonkamer twee.

        The attic deviates by three degrees, the living room by two.
        """
        home = await start_house(
            two_room_circuit(conflict_policy="demand"),
            states={**opposing_world(), "sensor.zolder": ("17.0", {})},
        )
        try:
            assert home.state(ATTIC) == "heat"
            assert home.state(LIVING) == "off"
        finally:
            await stop_house(home)

    async def test_the_season_lock_hands_it_to_the_summer_duty(self) -> None:
        home = await start_house(
            two_room_circuit(conflict_policy="season_lock"),
            states={**opposing_world(), "sensor.zolder": ("15.0", {})},
        )
        try:
            assert home.state(LIVING) == "cool", "de zomer kiest koelen, hoe groot de vraag ook is"
        finally:
            await stop_house(home)

    async def test_first_come_lets_the_running_duty_keep_the_circuit(self) -> None:
        home = await start_house(
            two_room_circuit(conflict_policy="first_come"),
            states={**opposing_world(), "sensor.zolder": ("15.0", {}), ATTIC: ("heat", {})},
        )
        try:
            assert home.state(ATTIC) == "heat"
            assert home.state(LIVING) == "off"
        finally:
            await stop_house(home)

    async def test_the_capacity_limit_keeps_the_second_room_out(self) -> None:
        home = await start_house(
            two_room_circuit(max_concurrent_units=1),
            states={
                "sensor.woonkamer": ("18.0", {}),
                "sensor.zolder": ("18.0", {}),
                LIVING: ("off", {}),
                ATTIC: ("off", {}),
            },
        )
        try:
            assert home.state(LIVING) == "heat"
            assert home.state(ATTIC) == "off"
            assert home.values("zone_zolder_source")["reason"] == "circuit_at_capacity"
        finally:
            await stop_house(home)

    async def test_a_duty_swap_stops_before_it_starts(self) -> None:
        """Met een omschakelpauze gebeurt het stoppen nu en het starten straks.

        With a switch pause the stopping happens now and the starting later.
        """
        home = await start_house(
            two_room_circuit(family_switch_delay=300),
            states={
                "sensor.woonkamer": ("26.0", {}),
                "sensor.zolder": ("26.0", {}),
                LIVING: ("heat", {}),
                ATTIC: ("off", {}),
            },
        )
        try:
            assert home.state(LIVING) == "off", "eerst loslaten"
            assert home.values("zone_woonkamer_source")["reason"] == "circuit_switch_pending"
            assert home.values("last_decision")["deferrals"]
            await home.evaluate()
            assert home.state(LIVING) == "cool", "en daarna pas de andere taak"
        finally:
            await stop_house(home)
