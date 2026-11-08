"""Een apparaat dat nooit antwoordt, in een draaiende Home Assistant.

An appliance that never answers, inside a running Home Assistant.

Zo liep het in een echt huis: de director stuurde "uit" naar een airco via een
cloudkoppeling, het apparaat ging uit, maar de aanroep kwam nooit terug. De
ronde bleef wachten, en met haar alles erna - ook de vangnetklok. Elf uur lang
besloot de director niets, terwijl de kamer afkoelde, en geen melder zag het.

That is how it went in a real house: the director sent "off" to an air
conditioner over a cloud link, the appliance went off, but the call never came
back. The round kept waiting, and everything after it with it - the safety-net
clock too. For eleven hours the director decided nothing while the room cooled,
and no sensor noticed.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import timedelta

import pytest
from harness_live import settings, source, start_house, stop_house, zone
from homeassistant.core import ServiceCall
from homeassistant.helpers.entity_platform import async_get_platforms
from homeassistant.util import dt as dt_util

from custom_components.climate_director import applier
from custom_components.climate_director.const import DOMAIN

ROOM = "climate.woonkamer"


def installation() -> dict:
    """Return one room with one appliance, the shape of the house it happened in."""
    return {
        "zones": [zone("woonkamer", sources=[source("airco", ROOM)], heat=settings(21.0, 20.0))],
        "outdoor_sensor": "sensor.buiten",
        "seasons": {"source": "entity", "entity_id": "sensor.seizoen"},
    }


def world() -> dict:
    """Return a cold room, so the appliance is running once the house is up."""
    return {
        "sensor.woonkamer": ("18.0", {}),
        "sensor.buiten": ("9.0", {}),
        "sensor.seizoen": ("winter", {}),
        ROOM: ("off", {}),
    }


def never_answer(home) -> list[str]:
    """Make `climate.set_hvac_mode` hang for good, and return what reached it."""
    reached: list[str] = []

    async def _hang(call: ServiceCall) -> None:
        reached.append(call.data["hvac_mode"])
        await asyncio.Event().wait()

    home.hass.services.async_register("climate", "set_hvac_mode", _hang)
    return reached


@pytest.fixture
def short_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Een fractie van een seconde in plaats van dertig, zodat de toets snel blijft."""
    monkeypatch.setattr(applier, "COMMAND_TIMEOUT_SECONDS", 0.05)


@pytest.mark.usefixtures("short_timeout")
async def test_a_hanging_stop_does_not_freeze_the_director() -> None:
    """De ronde loopt af, en de ronde daarna besluit gewoon weer.

    The round runs out, and the round after it simply decides again.
    """
    home = await start_house(installation(), states=world())
    try:
        assert home.state(ROOM) == "heat"
        reached = never_answer(home)

        home.set("sensor.woonkamer", "22.5")
        await asyncio.wait_for(home.evaluate(), timeout=5)
        assert reached == ["off"], "de stop hoort het apparaat wel te bereiken"
        first = home.coordinator.world.now

        # Weer koud: de volgende ronde moet er gewoon komen en weer willen stoken.
        # Cold again: the next round must simply come and want to heat again.
        home.set("sensor.woonkamer", "18.0")
        await asyncio.wait_for(home.evaluate(), timeout=5)
        assert home.coordinator.world.now > first
        assert home.values("zone_woonkamer_source")["wanted"] == "heat"
        assert home.value("stuck") == "off"
    finally:
        await stop_house(home)


async def test_the_stuck_sensor_sees_a_loop_that_stands_still() -> None:
    """Komt er geen ronde meer, dan slaat de melder op zijn eigen klok om.

    When no round comes anymore, the sensor turns on by its own clock.
    """
    home = await start_house(installation(), states=world())
    try:
        assert home.value("stuck") == "off"
        assert home.values("stuck")["seconds_since_last_round"] is None

        # Doen alsof de laatste ronde twintig minuten geleden was en er sindsdien
        # niets meer kwam - precies wat een hangende ronde achterlaat.
        # Pretend the latest round was twenty minutes ago and nothing came since -
        # exactly what a hanging round leaves behind.
        home.coordinator.world = replace(
            home.coordinator.world, now=dt_util.now() - timedelta(minutes=20)
        )
        entity_id = home.by_key("stuck")
        sensor = next(
            platform.entities[entity_id]
            for platform in async_get_platforms(home.hass, DOMAIN)
            if entity_id in platform.entities
        )
        sensor._async_look_again(dt_util.now())

        assert home.value("stuck") == "on"
        assert home.values("stuck")["seconds_since_last_round"] >= 20 * 60
        assert home.values("stuck")["zones"] == []
    finally:
        await stop_house(home)
