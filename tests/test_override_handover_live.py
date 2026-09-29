"""Een override draagt een gedeelde bron over in een draaiende Home Assistant.

An override hands a shared source over inside a running Home Assistant.

Anker 11 belooft dat een zone onder override volledig overgedragen is, en de
ketel inbegrepen. `tests/test_override_handover.py` legt dat in de engine vast;
dit bestand meet hetzelfde door de echte actie `climate_director.set_override`
heen, met de cv-thermostaat als **bron** onder twee kamers - de vorm waarin de
productie-installatie hem draagt, en niet de `Generator` waar de belofte
oorspronkelijk alleen voor gebouwd was.

Anchor 11 promises that a zone under override is handed over completely, the
boiler included. `tests/test_override_handover.py` pins that down in the engine;
this file measures the same thing through the real
`climate_director.set_override` action, with the cv thermostat as a **source**
under two rooms - the shape the production installation carries it in, and not
the `Generator` the promise was originally built for alone.
"""

from __future__ import annotations

import asyncio
from typing import Any

from harness_live import (
    LiveHome,
    new_config_dir,
    settings,
    source,
    start_house,
    stop_house,
    zone,
)

BOILER = "climate.ketel"
LIVING_SENSOR = "sensor.woonkamer"
ATTIC_SENSOR = "sensor.zolder"


def installation() -> dict[str, Any]:
    """Return a two-room house with one shared boiler as a source in both."""
    return {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("w_ketel", BOILER, role="heat_only")],
                heat=settings(21.0, 20.0),
            ),
            zone(
                "zolder",
                sources=[source("z_ketel", BOILER, role="heat_only")],
                heat=settings(21.0, 20.0),
                priority=1,
            ),
        ],
        "outdoor_sensor": "sensor.buiten",
        "heating_layout": "central",
    }


def world(*, living: str, attic: str, boiler: str = "off") -> dict[str, tuple[str, dict[str, Any]]]:
    """Return a world with two indoor temperatures and the boiler in a mode."""
    return {
        LIVING_SENSOR: (living, {"unit_of_measurement": "°C"}),
        ATTIC_SENSOR: (attic, {"unit_of_measurement": "°C"}),
        "sensor.buiten": ("4.0", {}),
        BOILER: (boiler, {"hvac_modes": ["off", "heat"], "temperature": 19.0}),
    }


def reason_of(home: LiveHome, zone_id: str) -> str:
    """Return the reason of one zone's last decision."""
    decision = home.coordinator.data.decision_for(zone_id)
    assert decision is not None, f"geen beslissing voor {zone_id}"
    return decision.reason.value


async def start_override(home: LiveHome) -> None:
    """Hand the living room over by hand, for an hour, and let it land."""
    await home.call(
        "climate_director",
        "set_override",
        {"zone_id": "woonkamer", "hvac_mode": "heat", "temperature": 23, "minutes": 60},
    )
    await asyncio.sleep(1.5)
    await home.settle()


class TestAnOverrideOnASharedSource:
    """De belofte van anker 11, gemeten via de echte actie.

    Anchor 11's promise, measured through the real action.
    """

    async def test_the_boiler_is_not_steered_any_more(self) -> None:
        home = await start_house(
            installation(), config_dir=new_config_dir(), states=world(living="20.5", attic="18.0")
        )
        try:
            await start_override(home)
            assert home.state(BOILER) == "heat", "de override zet de ketel zelf"

            home.clear_calls()
            await home.evaluate()
            await home.settle()

            assert home.climate_calls() == [], "de director stuurde de overgedragen ketel"
            assert home.state(BOILER) == "heat", "de ketel hoort te blijven draaien"
            assert reason_of(home, "woonkamer") == "manual_override"
            assert reason_of(home, "zolder") == "no_source_available"
        finally:
            await stop_house(home)

    async def test_without_an_override_the_boiler_is_steered_as_before(self) -> None:
        """De tegenproef: zonder override verandert er niets aan de gewone gang."""
        home = await start_house(
            installation(), config_dir=new_config_dir(), states=world(living="18.0", attic="18.0")
        )
        try:
            assert home.state(BOILER) == "heat", "de ketel hoort gewoon aangestuurd te worden"

            home.clear_calls()
            home.hass.states.async_set(LIVING_SENSOR, "23.0", {"unit_of_measurement": "°C"})
            home.hass.states.async_set(ATTIC_SENSOR, "23.0", {"unit_of_measurement": "°C"})
            await asyncio.sleep(1.5)
            await home.settle()

            assert [call[0] for call in home.climate_calls()] == ["set_hvac_mode"]
            assert home.state(BOILER) == "off", "niemand vraagt nog warmte"
            assert reason_of(home, "woonkamer") == "satisfied"
        finally:
            await stop_house(home)
