"""De nalooptijd van een kamer begint alleen bij een echte overgang naar leeg.

The room's grace period starts only at a real transition to empty.

Een aanwezigheidssensor die na een herstart van Home Assistant, of na een
verbroken verbinding, opnieuw `off` meldt, draagt een vers `last_changed`. Een
kamer die al uren leeg is telde daardoor nog een hele nalooptijd als bezet en
werd al die tijd verwarmd of gekoeld. Deze toetsen meten dat in een echte Home
Assistant: een start met de sensor op `off`, een sensor die `unavailable` ->
`off` gaat terwijl het huis draait, en de tegenproef dat een vertrek vlak vóór
een herstart zijn nalooptijd houdt.

A presence sensor reporting `off` again after a Home Assistant restart, or after
a broken connection, carries a fresh `last_changed`. A room that had been empty
for hours therefore counted as occupied for a whole grace period and was heated
or cooled all that time. These tests measure that inside a real Home Assistant: a
start with the sensor on `off`, a sensor going `unavailable` -> `off` while the
house runs, and the counter-test that a departure just before a restart keeps its
grace period.
"""

from __future__ import annotations

import asyncio
from typing import Any

from harness_live import new_config_dir, settings, source, start_house, stop_house, zone

OCCUPANCY = "binary_sensor.zolder_bezet"
AC = "climate.zolder"
SENSOR = "sensor.zolder"
OUTDOOR = "sensor.buiten"


def installation(timeout: float) -> dict[str, Any]:
    """Return one cold attic whose room gate has a short grace period."""
    return {
        "zones": [
            zone(
                "zolder",
                sources=[source("zolder_airco", AC)],
                indoor_sensor=SENSOR,
                heat=settings(21.0, 20.0),
                presence_entity=OCCUPANCY,
                presence_timeout=timeout,
            )
        ],
        "outdoor_sensor": OUTDOOR,
    }


def world(*, occupied: str = "off", ac: str = "off") -> dict[str, tuple[str, dict[str, Any]]]:
    """Return a cold world in which the attic wants heat, with the sensor as given."""
    return {
        SENSOR: ("18.5", {"unit_of_measurement": "°C"}),
        OUTDOOR: ("4.0", {}),
        OCCUPANCY: (occupied, {}),
        AC: (ac, {"hvac_modes": ["off", "heat", "cool"], "current_temperature": 18.5}),
    }


def reason_of(home: Any) -> str:
    """Return the reason of the attic's last decision."""
    decision = home.coordinator.data.decision_for("zolder")
    assert decision is not None, "geen beslissing voor zolder"
    return decision.reason.value


async def settle_the_debouncer(home: Any) -> None:
    """Let the debouncer's one-second pass and everything behind it finish."""
    await asyncio.sleep(1.5)
    await home.settle()


async def test_a_start_with_the_sensor_off_leaves_the_room_empty() -> None:
    """Na een herstart met de sensor op `off` is de kamer leeg, niet in nalooptijd.

    After a restart with the sensor on `off` the room is empty, not in a grace
    period.
    """
    home = await start_house(installation(10.0), states=world(occupied="off"))
    try:
        await settle_the_debouncer(home)
        await home.evaluate()
        assert reason_of(home) == "zone_unoccupied"
        assert home.state(AC) == "off"
    finally:
        await stop_house(home)


async def test_an_unavailable_reading_does_not_restart_the_grace() -> None:
    """`unavailable` -> `off` is geen vertrek en mag de nalooptijd niet herstarten."""
    home = await start_house(installation(3.0), states=world(occupied="off"))
    try:
        # Op de ongecorrigeerde boom telt de kamer hier nog 3 s als bezet; daarna
        # is de verse nalooptijd van de start voorbij.
        await asyncio.sleep(4.0)
        await settle_the_debouncer(home)
        home.hass.states.async_set(OCCUPANCY, "unavailable", {})
        await settle_the_debouncer(home)
        home.hass.states.async_set(OCCUPANCY, "off", {})
        await settle_the_debouncer(home)
        await home.evaluate()
        assert reason_of(home) == "zone_unoccupied"
        assert home.state(AC) == "off"
    finally:
        await stop_house(home)


async def test_a_departure_just_before_a_restart_keeps_its_grace() -> None:
    """Wie net de kamer uitliep houdt zijn nalooptijd, ook over een herstart heen.

    Somebody who has just left the room keeps the grace period, across a restart
    too.
    """
    config_dir = new_config_dir()
    home = await start_house(
        installation(5.0), config_dir=config_dir, states=world(occupied="on", ac="heat")
    )
    try:
        await settle_the_debouncer(home)
        home.hass.states.async_set(OCCUPANCY, "off", {})
        await settle_the_debouncer(home)
        # De opslag schrijft met een seconde vertraging; die moet de herstart halen.
        await asyncio.sleep(1.2)
    finally:
        await stop_house(home)

    home = await start_house(installation(5.0), config_dir=config_dir, states=world())
    try:
        await settle_the_debouncer(home)
        await home.evaluate()
        assert reason_of(home) == "regulating", "de nalooptijd is na de herstart niet doorgegaan"
        assert home.state(AC) == "heat"
        await asyncio.sleep(6.0)
        await settle_the_debouncer(home)
        await home.evaluate()
        assert reason_of(home) == "zone_unoccupied"
    finally:
        await stop_house(home)
