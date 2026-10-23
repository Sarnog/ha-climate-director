"""Een override heft bij zijn begin de hand van zijn zone op (anker 11).

An override lifts its zone's hand at its beginning (anchor 11).

Een hand aan een apparaat en een override zijn allebei een ingreep van de
gebruiker. Zet iemand na een hand de overrideschakelaar of `set_override` aan,
dan is de override het jongste oordeel: de hand vervalt bij dat begin, en na
`clear_override` doet de zone weer mee in plaats van het apparaat dat de
override aanzette ongeregeld te laten draaien tot het huis slaapt, leeg is of de
volgende dag begint. Deze toetsen meten dat in een echte Home Assistant, via de
actie en via de schakelaar, en met de tegenproef: een override op een andere zone
laat de hand staan.

A hand at an appliance and an override are both interventions by the user. When
somebody turns the override switch or `set_override` on after a hand, the
override is the newer verdict: the hand lapses at that beginning, and after
`clear_override` the zone rejoins instead of leaving the appliance the override
switched on running unregulated until the house sleeps, empties or the next day
begins. These tests measure that inside a real Home Assistant, through the action
and through the switch, and with the counter-test: an override on another zone leaves
the hand standing.
"""

from __future__ import annotations

import asyncio
from typing import Any

from harness_live import new_config_dir, settings, source, start_house, stop_house, zone

BOILER = "climate.ketel"
AIRCO = "climate.airco_zolder"
LIVING = "sensor.woonkamer"
ATTIC = "sensor.zolder"
MODES = {"hvac_modes": ["off", "heat", "cool"], "current_temperature": 18.5}


def installation() -> dict[str, Any]:
    """Return a two-room house; the attic has its own air conditioner."""
    return {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("w_ketel", BOILER, role="heat_only")],
                heat=settings(21.0, 20.0),
            ),
            zone(
                "zolder",
                sources=[
                    source("z_airco", AIRCO, role="heat_cool"),
                    source("z_ketel", BOILER, role="heat_only"),
                ],
                heat=settings(21.0, 20.0),
                priority=1,
            ),
        ],
        "heating_layout": "central",
    }


def world(living: str, attic: str) -> dict[str, tuple[str, dict[str, Any]]]:
    """Return a world with the living room warm and the attic cold."""
    return {
        LIVING: (living, {"unit_of_measurement": "°C"}),
        ATTIC: (attic, {"unit_of_measurement": "°C"}),
        BOILER: ("off", {"hvac_modes": ["off", "heat"], "temperature": 19.0}),
        AIRCO: ("off", dict(MODES)),
    }


def reason_of(home: Any, zone_id: str = "zolder") -> str:
    """Return the reason of one zone's last decision."""
    decision = home.coordinator.data.decision_for(zone_id)
    assert decision is not None, f"geen beslissing voor {zone_id}"
    return decision.reason.value


async def settle(home: Any) -> None:
    """Let the debouncer's second pass and everything behind it finish."""
    await asyncio.sleep(1.5)
    await home.settle()


async def hand_at_the_air_conditioner(home: Any) -> None:
    """Let the attic heat, then switch its air conditioner off by hand."""
    await home.evaluate()
    await settle(home)
    assert home.state(AIRCO) == "heat", "de airco hoort eerst door de director aan te staan"
    home.hass.states.async_set(AIRCO, "off", dict(MODES))
    await settle(home)
    await home.evaluate()
    await settle(home)
    assert reason_of(home) == "manual_override", "de hand aan de airco staat niet"


async def test_set_override_lifts_the_hand_and_the_zone_rejoins() -> None:
    """`set_override` haalt de hand weg; na `clear_override` regelt de zone weer."""
    home = await start_house(
        installation(), config_dir=new_config_dir(), states=world("22.5", "18.5")
    )
    try:
        await hand_at_the_air_conditioner(home)
        assert set(home.coordinator._handed_back) == {"zolder"}

        home.clear_calls()
        await home.call(
            "climate_director",
            "set_override",
            {"zone_id": "zolder", "hvac_mode": "heat", "temperature": 22},
        )
        await settle(home)
        await home.evaluate()
        await settle(home)
        assert home.coordinator._handed_back == {}, "set_override liet de hand staan"

        await home.call("climate_director", "clear_override", {"zone_id": "zolder"})
        await settle(home)
        home.hass.states.async_set(ATTIC, "22.5", {"unit_of_measurement": "°C"})
        home.clear_calls()
        await settle(home)
        await home.evaluate()
        await settle(home)
        assert reason_of(home) != "manual_override", "de zolder doet na clear_override niet mee"
        assert home.state(AIRCO) == "off", "de airco hoort weer geregeld te worden"
    finally:
        await stop_house(home)


async def test_the_override_switch_lifts_the_hand_and_the_zone_rejoins() -> None:
    """De overrideschakelaar haalt de hand weg; na het uitzetten regelt de zone weer."""
    home = await start_house(
        installation(), config_dir=new_config_dir(), states=world("22.5", "18.5")
    )
    try:
        await hand_at_the_air_conditioner(home)
        assert set(home.coordinator._handed_back) == {"zolder"}

        switch = home.by_key("zone_zolder_override")
        await home.call("switch", "turn_on", {"entity_id": switch})
        await settle(home)
        assert home.coordinator._handed_back == {}, "de overrideschakelaar liet de hand staan"

        await home.call("switch", "turn_off", {"entity_id": switch})
        await settle(home)
        home.hass.states.async_set(ATTIC, "22.5", {"unit_of_measurement": "°C"})
        home.clear_calls()
        await settle(home)
        await home.evaluate()
        await settle(home)
        assert reason_of(home) != "manual_override", "de zolder doet na de schakelaar niet mee"
        assert home.state(AIRCO) == "off", "de airco hoort weer geregeld te worden"
    finally:
        await stop_house(home)


async def test_an_override_on_another_zone_leaves_the_hand_standing() -> None:
    """Alleen de zone van de override verliest haar hand (anker 11, de andere kant)."""
    home = await start_house(
        installation(), config_dir=new_config_dir(), states=world("22.5", "18.5")
    )
    try:
        await hand_at_the_air_conditioner(home)
        assert set(home.coordinator._handed_back) == {"zolder"}

        await home.call(
            "climate_director",
            "set_override",
            {"zone_id": "woonkamer", "hvac_mode": "heat", "temperature": 22},
        )
        await settle(home)
        assert set(home.coordinator._handed_back) == {"zolder"}, (
            "een override op de woonkamer hief de hand aan de zolder op"
        )

        await home.call("climate_director", "clear_override", {"zone_id": "woonkamer"})
        await settle(home)
        await home.evaluate()
        await settle(home)
        assert reason_of(home) == "manual_override"
        assert home.state(AIRCO) == "off", "de zolder-airco hoort uit te blijven"
    finally:
        await stop_house(home)
