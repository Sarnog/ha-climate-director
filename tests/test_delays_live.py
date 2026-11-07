"""Vertragingen, nalooptijd, kortcyclus en de vastloopmelder.

Delays, grace, short cycle and the stuck detector."""

from __future__ import annotations

from datetime import timedelta
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
    ATTIC,
    LIVING,
)

from custom_components.climate_director import coordinator as coordinator_module


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch):
    """Return a handle that moves the integration's clock forward."""
    from homeassistant.util import dt as dt_util

    real = dt_util.now
    shift = {"by": timedelta()}

    def _now():
        return real() + shift["by"]

    monkeypatch.setattr(coordinator_module.dt_util, "now", _now)

    class Handle:
        def advance(self, **kwargs: Any) -> None:
            shift["by"] += timedelta(**kwargs)

    return Handle()


class TestTheDelays:
    """Vertragingen, nalooptijden en pauzes, met de klok vooruit gezet.

    Delays, grace periods and pauses, with the clock moved forward.
    """

    async def test_an_opening_only_bites_after_its_delay(self, clock) -> None:
        installation = {
            "zones": [
                zone(
                    "woonkamer",
                    sources=[source("airco", LIVING, role="heat_cool")],
                    heat=settings(21.0, 20.0),
                )
            ],
            "openings": [{"entity_id": "binary_sensor.deur", "delay": 300}],
        }
        home = await start_house(
            installation,
            states={
                "sensor.woonkamer": ("18.0", {}),
                LIVING: ("off", {}),
                "binary_sensor.deur": ("off", {}),
            },
        )
        try:
            assert home.state(LIVING) == "heat"
            home.set("binary_sensor.deur", "on")
            await home.evaluate()
            assert home.state(LIVING) == "heat", "vijf minuten zijn nog niet om"

            clock.advance(minutes=6)
            await home.evaluate()
            assert home.state(LIVING) == "off"
        finally:
            await stop_house(home)

    async def test_a_room_stays_occupied_for_its_grace_period(self, clock) -> None:
        installation = {
            "zones": [
                zone(
                    "zolder",
                    sources=[source("airco", ATTIC, role="heat_cool")],
                    heat=settings(21.0, 20.0),
                    gate="presence",
                    presence_entity="binary_sensor.zolder_aanwezig",
                    presence_timeout=900,
                )
            ]
        }
        home = await start_house(
            installation,
            states={
                "sensor.zolder": ("18.0", {}),
                ATTIC: ("off", {}),
                "binary_sensor.zolder_aanwezig": ("on", {}),
            },
        )
        try:
            assert home.state(ATTIC) == "heat"
            home.set("binary_sensor.zolder_aanwezig", "off")
            # Het vertrek wordt genoteerd in de toestandswijziging van de sensor;
            # deze toets slaat de debouncer over en moet die wijziging dus eerst
            # laten aankomen. Zonder dat leest de ronde een kamer zonder moment,
            # en dat telt als leeg - de onschadelijke kant.
            #
            # The departure is noted in the sensor's own state change; this test
            # skips the debouncer and must therefore let that change arrive first.
            # Without it the round reads a room without a moment, and that counts
            # as empty - the harmless side.
            await home.settle()
            await home.evaluate()
            assert home.state(ATTIC) == "heat", "de nalooptijd van een kwartier loopt nog"

            clock.advance(minutes=16)
            await home.evaluate()
            assert home.state(ATTIC) == "off"
            assert home.values("zone_zolder_source")["reason"] == "zone_unoccupied"
        finally:
            await stop_house(home)

    async def test_short_cycle_protection_holds_a_restart_back(self, clock) -> None:
        installation = {
            "zones": [
                zone(
                    "woonkamer",
                    sources=[source("airco", LIVING, role="heat_cool")],
                    heat=settings(21.0, 20.0),
                )
            ],
            "circuits": [
                {
                    "circuit_id": "buiten",
                    "name": "Buiten",
                    "units": [LIVING],
                    "simultaneous_heat_cool": False,
                    "min_cycle_time": 900,
                }
            ],
        }
        home = await start_house(
            installation,
            states={"sensor.woonkamer": ("23.0", {}), LIVING: ("off", {})},
        )
        try:
            assert home.state(LIVING) == "off"
            home.set("sensor.woonkamer", "18.0")
            await home.evaluate()
            assert home.state(LIVING) == "off", "de unit stopte net; starten mag nog niet"
            assert home.values("zone_woonkamer_source")["reason"] == "short_cycle_protection"
            assert home.values("last_decision")["deferrals"], "er hoort een herkansing te staan"

            clock.advance(minutes=16)
            await home.evaluate()
            assert home.state(LIVING) == "heat"
        finally:
            await stop_house(home)

    async def test_a_zone_that_keeps_waiting_is_reported_as_stuck(self, clock) -> None:
        installation = {
            "zones": [
                zone(
                    "woonkamer",
                    sources=[source("airco", LIVING, role="heat_cool")],
                    heat=settings(21.0, 20.0),
                )
            ],
            "circuits": [
                {
                    "circuit_id": "buiten",
                    "name": "Buiten",
                    "units": [LIVING],
                    "simultaneous_heat_cool": False,
                    "min_cycle_time": 36000,
                }
            ],
            "stuck_after": 900,
        }
        home = await start_house(
            installation,
            states={"sensor.woonkamer": ("18.0", {}), LIVING: ("off", {})},
        )
        try:
            await home.evaluate()
            assert home.coordinator.stuck_zones() == {}
            clock.advance(minutes=20)
            await home.evaluate()
            assert "woonkamer" in home.coordinator.stuck_zones()
            assert home.value("stuck") == "on"
            assert home.values("stuck")["zones"] == ["woonkamer"]
        finally:
            await stop_house(home)
