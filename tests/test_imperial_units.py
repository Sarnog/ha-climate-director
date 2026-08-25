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
from homeassistant.util.unit_system import IMPERIAL_SYSTEM, METRIC_SYSTEM

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

    async def test_the_coordinator_follows_a_unit_change_without_a_restart(self) -> None:
        """De eenheid wordt elke keer opnieuw gelezen, niet alleen bij het opzetten.

        The unit is read afresh every time, not only at setup.
        """
        live = await _house(65.0)
        try:
            assert live.coordinator.temperature_unit == "°F"
            live.hass.config.units = METRIC_SYSTEM
            assert live.coordinator.temperature_unit == "°C"
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


class TestWhatTheUserSeesUsesTheUsersUnit:
    async def test_sensor_attributes_speak_fahrenheit(self) -> None:
        """De attributen van de waarneemsensoren volgen de eenheid van de gebruiker.

        In schaduwmodus blijft de wereld staan waar hij stond, zodat ook de
        actuele setpoint-attributen voorspelbaar zijn.

        The observation sensors' attributes follow the user's unit. In shadow
        mode the world stays where it was, so the actual-setpoint attributes are
        predictable too.
        """
        live = await start_house(
            installation(),
            states=fahrenheit_world(65.0),
            appliance="obedient",
            unit_system=IMPERIAL_SYSTEM,
            shadow=True,
        )
        try:
            await live.evaluate()
            commands = live.values("last_decision")["commands"]
            assert commands and commands[0]["temperature"] == 68.0
            command = live.values(f"command_{LIVING}")
            assert command["temperature"] == 68.0
            assert command["actual_temperature"] == 66.0
            differences = live.values("mismatch")["differences"]
            assert differences and differences[0]["wanted_temperature"] == 68.0
            assert differences[0]["actual_temperature"] == 66.0
        finally:
            await stop_house(live)

    async def test_the_decision_event_carries_the_unit(self) -> None:
        live = await _house(65.0)
        try:
            await live.evaluate()
            events = live.fired("climate_director_decision")
            assert events, "geen decision-event gevuurd"
            assert events[0]["temperature"] == 68.0
            assert events[0]["temperature_unit"] == "°F"
        finally:
            await stop_house(live)

    async def test_a_metric_installation_reports_celsius(self) -> None:
        live = await start_house(
            installation(),
            states={
                "sensor.woonkamer": ("18.5", {"unit_of_measurement": "°C"}),
                LIVING: ("off", {"temperature": 20.0, "current_temperature": 18.5}),
                "person.danny": ("home", {}),
            },
            appliance="obedient",
        )
        try:
            await live.evaluate()
            events = live.fired("climate_director_decision")
            assert events, "geen decision-event gevuurd"
            assert events[0]["temperature"] == 20.0
            assert events[0]["temperature_unit"] == "°C"
            assert live.values("last_decision")["commands"][0]["temperature"] == 20.0
        finally:
            await stop_house(live)
