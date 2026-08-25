"""De integratie volgt het eenhedenstelsel van Home Assistant.

The integration follows Home Assistant's unit system.

De engine rekent in graden Celsius; de koppelingslaag zet de metingen van Home
Assistant om naar Celsius en de setpoints terug naar de eenheid van de
gebruiker. Dit bestand bewijst dat met een installatie op Fahrenheit.

The engine works in degrees Celsius; the binding layer converts Home Assistant's
readings into Celsius and the setpoints back into the user's unit. This file
proves that with an installation on Fahrenheit.
"""

from __future__ import annotations

from typing import Any

from harness_live import LiveHome, settings, source, start_house, stop_house, zone
from homeassistant.util.unit_system import IMPERIAL_SYSTEM

LIVING = "climate.woonkamer"


def installation() -> dict[str, Any]:
    """Return one zone that heats from 19 °C and aims for 20 °C (66/68 °F)."""
    return {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("woonkamer_airco", LIVING, role="heat_cool")],
                heat=settings(20.0, 19.0),
            )
        ],
        "residents": [{"resident_id": "danny", "name": "Danny", "presence_entity": "person.danny"}],
    }


def fahrenheit_world(
    indoor: float, setpoint: float = 66.0
) -> dict[str, tuple[str, dict[str, Any]]]:
    """Return a world whose temperatures Home Assistant reports in Fahrenheit."""
    return {
        "sensor.woonkamer": (f"{indoor}", {"unit_of_measurement": "°F"}),
        LIVING: ("off", {"temperature": setpoint, "current_temperature": indoor}),
        "person.danny": ("home", {}),
    }


async def _house(indoor: float) -> LiveHome:
    return await start_house(
        installation(),
        states=fahrenheit_world(indoor),
        appliance="obedient",
        unit_system=IMPERIAL_SYSTEM,
    )


class TestTheIntegrationFollowsTheUsersUnit:
    async def test_the_coordinator_reads_the_imperial_unit(self) -> None:
        live = await _house(65.0)
        try:
            assert live.coordinator.temperature_unit == "°F"
        finally:
            await stop_house(live)

    async def test_a_room_at_65_fahrenheit_wants_heat_at_68(self) -> None:
        """65 °F is 18.3 °C, under the 19 °C switch-on point: heat, at 68 °F."""
        live = await _house(65.0)
        try:
            await live.evaluate()
            calls = live.climate_calls()
            assert ("set_hvac_mode", {"entity_id": LIVING, "hvac_mode": "heat"}) in calls
            assert ("set_temperature", {"entity_id": LIVING, "temperature": 68.0}) in calls
        finally:
            await stop_house(live)

    async def test_a_room_at_72_fahrenheit_stays_off(self) -> None:
        """72 °F is 22.2 °C, above the 20 °C target: no heat is asked for."""
        live = await _house(72.0)
        try:
            await live.evaluate()
            calls = live.climate_calls()
            assert ("set_hvac_mode", {"entity_id": LIVING, "hvac_mode": "heat"}) not in calls
        finally:
            await stop_house(live)
