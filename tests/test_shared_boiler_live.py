"""De gedeelde warmtebron volgt de kranen.

The shared heat source follows the valves."""

from __future__ import annotations

from harness_live import (
    start_house,
    stop_house,
)
from live_helpers import (
    BOILER,
    LIVING,
    VALVE,
    boiler_house,
)


class TestTheSharedBoiler:
    """De ketel volgt de kranen, en start als laatste.

    The boiler follows the valves, and starts last.
    """

    async def test_the_boiler_follows_the_warmest_demand(self) -> None:
        home = await start_house(
            boiler_house(),
            states={
                "sensor.woonkamer": ("18.0", {}),
                "sensor.keuken": ("17.0", {}),
                LIVING: ("off", {}),
                VALVE: ("off", {}),
                BOILER: ("off", {}),
            },
        )
        try:
            assert home.state(BOILER) == "heat"
            assert home.attributes(BOILER)["temperature"] == 21.0, "de warmste vraag wint"
        finally:
            await stop_house(home)

    async def test_a_fixed_setpoint_overrules_the_rooms(self) -> None:
        home = await start_house(
            boiler_house(setpoint=55.0),
            states={
                "sensor.woonkamer": ("18.0", {}),
                "sensor.keuken": ("17.0", {}),
                LIVING: ("off", {}),
                VALVE: ("off", {}),
                BOILER: ("off", {}),
            },
        )
        try:
            assert home.attributes(BOILER)["temperature"] == 55.0
        finally:
            await stop_house(home)

    async def test_the_boiler_goes_off_once_every_room_is_warm(self) -> None:
        home = await start_house(
            boiler_house(),
            states={
                "sensor.woonkamer": ("23.0", {}),
                "sensor.keuken": ("23.0", {}),
                LIVING: ("off", {}),
                VALVE: ("off", {}),
                BOILER: ("heat", {}),
            },
        )
        try:
            assert home.state(BOILER) == "off"
        finally:
            await stop_house(home)

    async def test_the_valves_open_before_the_boiler_fires(self) -> None:
        home = await start_house(
            boiler_house(),
            states={
                "sensor.woonkamer": ("18.0", {}),
                "sensor.keuken": ("17.0", {}),
                LIVING: ("off", {}),
                VALVE: ("off", {}),
                BOILER: ("off", {}),
            },
        )
        try:
            ordered = [data["entity_id"] for _name, data in home.climate_calls()]
            assert ordered[-1] == BOILER, "de ketel hoort als laatste aan de beurt te zijn"
            assert ordered.index(BOILER) > ordered.index(VALVE)
        finally:
            await stop_house(home)
