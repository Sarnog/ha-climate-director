"""Dezelfde uitval, maar dan in een draaiende Home Assistant.

The same outages, but inside a running Home Assistant."""

from __future__ import annotations

from typing import Any

import pytest
from harness_live import settings, source, start_house, stop_house, zone

from custom_components.climate_director.engine import (
    Season,
)

# -- de opstelling / the setup ----------------------------------------------


UNREADABLE = ("unavailable", "unknown", "missing")


LIVE_FIRST = "climate.eerste"


LIVE_SECOND = "climate.tweede"


def live_installation() -> dict[str, Any]:
    """Return a one-room installation with a first choice and a stand-in."""
    return {
        "zones": [
            zone(
                "woonkamer",
                sources=[
                    source("eerste", LIVE_FIRST, role="heat_cool"),
                    source("tweede", LIVE_SECOND, role="heat_only", priority=1),
                ],
                heat=settings(21.0, 20.0),
            )
        ],
        "outdoor_sensor": "sensor.buiten",
        "seasons": {"source": "entity", "entity_id": "sensor.seizoen"},
    }


def live_world() -> dict[str, tuple[str, dict[str, Any]]]:
    """Return a cold world in which the first choice can serve the room."""
    return {
        "sensor.woonkamer": ("18.0", {}),
        "sensor.buiten": ("4.0", {}),
        "sensor.seizoen": ("winter", {}),
        LIVE_FIRST: ("off", {}),
        LIVE_SECOND: ("off", {}),
    }


@pytest.mark.parametrize("how", UNREADABLE)
async def test_a_broken_appliance_hands_over_to_the_stand_in(how: str) -> None:
    """`unavailable`, `unknown` en helemaal weg horen hetzelfde te doen.

    `unavailable`, `unknown` and gone altogether should all do the same.
    """
    states = live_world()
    if how == "missing":
        states.pop(LIVE_FIRST)
    else:
        states[LIVE_FIRST] = (how, {})

    home = await start_house(live_installation(), states=states)
    try:
        assert home.state(LIVE_SECOND) == "heat", f"de reserve viel niet in bij {how}"
        assert home.value("zone_woonkamer_fallback") == "on"
        assert home.values("zone_woonkamer_fallback")["unreachable"] == ["eerste"]
        assert home.value(f"command_{LIVE_FIRST}") == "unreachable"
        assert home.value("zone_woonkamer_source") == "tweede"
    finally:
        await stop_house(home)


@pytest.mark.parametrize("how", UNREADABLE)
async def test_a_room_without_a_reading_simply_stops(how: str) -> None:
    """Zonder kamertemperatuur valt er niets te regelen, en dat wordt gemeld.

    Without a room temperature there is nothing to regulate, and it is reported.
    """
    states = live_world()
    if how == "missing":
        states.pop("sensor.woonkamer")
    else:
        states["sensor.woonkamer"] = (how, {})

    home = await start_house(live_installation(), states=states)
    try:
        assert home.state(LIVE_FIRST) == "off"
        assert home.values("zone_woonkamer_source")["reason"] == "no_indoor_temperature"
        assert "sensor.woonkamer" in home.values("stuck")["unusable_entities"] or (how == "missing")
    finally:
        await stop_house(home)


@pytest.mark.parametrize("how", UNREADABLE)
async def test_the_unusable_list_names_whatever_cannot_be_read(how: str) -> None:
    states = live_world()
    if how == "missing":
        states.pop("sensor.buiten")
    else:
        states["sensor.buiten"] = (how, {})

    home = await start_house(live_installation(), states=states)
    try:
        unusable = home.coordinator.unusable_entities()
        assert unusable.get("sensor.buiten") == ("missing" if how == "missing" else how)
        # Opvallen doet hij onder Reparaties (na vijf minuten, zie
        # test_unreadable_entities.py) en in dit attribuut - niet meer via de
        # vastloopmelder, die weer alleen over wachtende zones gaat.
        #
        # Standing out happens under Repairs (after five minutes, see
        # test_unreadable_entities.py) and in this attribute - no longer through
        # the stuck sensor, which is once again only about waiting zones.
        assert "sensor.buiten" in home.values("stuck")["unusable_entities"]
    finally:
        await stop_house(home)


async def test_an_unreadable_season_entity_falls_back_to_no_season() -> None:
    """Een kapotte seizoenshelper mag geen taak stilletjes uitzetten.

    Het seizoen wordt dan onbekend, en alleen wat aan een seizoen gebonden is
    valt weg - de rest regelt gewoon door.

    A broken season helper must not quietly switch a duty off. The season
    becomes unknown, and only what is bound to a season falls away - the rest
    simply carries on.
    """
    states = live_world()
    states["sensor.seizoen"] = ("unavailable", {})
    home = await start_house(live_installation(), states=states)
    try:
        assert home.coordinator.world.season is Season.UNKNOWN
        assert home.state(LIVE_FIRST) == "heat", "verwarmen zonder seizoenseis loopt door"
    finally:
        await stop_house(home)


async def test_an_unrecognised_season_state_is_reported() -> None:
    """Een leesbare maar onherkenbare seizoensstaat hoort op te vallen.

    De entiteit bestaat en is leesbaar, dus de gewone onbruikbaarheidscontrole
    pakt hem niet - terwijl het seizoen wél UNKNOWN wordt en alles wat eraan
    hangt stilletjes wegvalt.

    A readable but unrecognised season state should stand out. The entity
    exists and reads fine, so the ordinary unusable check does not catch it -
    while the season does become UNKNOWN and everything hanging off it quietly
    falls away.
    """
    states = live_world()
    states["sensor.seizoen"] = ("droog", {})
    home = await start_house(live_installation(), states=states)
    try:
        unusable = home.coordinator.unusable_entities()
        assert unusable.get("sensor.seizoen") == "unrecognized season: droog"
        assert "sensor.seizoen" in home.values("stuck")["unusable_entities"]
    finally:
        await stop_house(home)


async def test_a_recognised_season_state_is_not_reported() -> None:
    states = live_world()
    states["sensor.seizoen"] = ("Zomer", {})
    home = await start_house(live_installation(), states=states)
    try:
        assert "sensor.seizoen" not in home.coordinator.unusable_entities()
    finally:
        await stop_house(home)


async def test_a_readable_sensor_without_a_number_is_reported() -> None:
    """Een sensor die bestaat en leesbaar is, maar geen getal geeft.

    De zone leest NO_INDOOR_TEMPERATURE en doet niets; de sensor hoort daarom
    in de onbruikbaarheidslijst te staan, waar de reparatiemelding hem oppikt.

    A sensor that exists and reads fine, but yields no number. The zone reads
    NO_INDOOR_TEMPERATURE and does nothing; the sensor therefore belongs in the
    unusable list, from where the repair notice picks it up.
    """
    states = live_world()
    states["sensor.woonkamer"] = ("warm", {})
    home = await start_house(live_installation(), states=states)
    try:
        unusable = home.coordinator.unusable_entities()
        assert unusable.get("sensor.woonkamer") == "no number"
        assert "sensor.woonkamer" in home.values("stuck")["unusable_entities"]
    finally:
        await stop_house(home)


async def test_a_sensor_with_a_number_is_not_reported() -> None:
    states = live_world()
    home = await start_house(live_installation(), states=states)
    try:
        assert "sensor.woonkamer" not in home.coordinator.unusable_entities()
    finally:
        await stop_house(home)


async def test_a_missing_climate_entity_never_gets_a_service_call() -> None:
    """Er wordt niets gestuurd naar een apparaat dat er niet is.

    Nothing is sent to an appliance that is not there.
    """
    states = live_world()
    states.pop(LIVE_FIRST)
    states.pop(LIVE_SECOND)
    home = await start_house(live_installation(), states=states)
    try:
        assert home.climate_calls() == []
        assert home.value("zone_woonkamer_source") == "none"
        assert home.values("zone_woonkamer_source")["reason"] == "no_source_available"
    finally:
        await stop_house(home)


async def test_an_appliance_that_comes_back_is_picked_up_again() -> None:
    """Terug in de lucht betekent: weer de eerste keus.

    Back online means: the first choice again.
    """
    states = live_world()
    states[LIVE_FIRST] = ("unavailable", {})
    home = await start_house(live_installation(), states=states)
    try:
        assert home.state(LIVE_SECOND) == "heat"
        home.climate(LIVE_FIRST, "off")
        await home.evaluate()
        assert home.state(LIVE_FIRST) == "heat"
        assert home.state(LIVE_SECOND) == "off"
        assert home.value("zone_woonkamer_fallback") == "off"
    finally:
        await stop_house(home)


OUTDOOR_UNREADABLE = ("unavailable", "unknown", "NaN", "missing")


OUTDOOR_PLACEMENTS = ("zone_heat", "zone_cool", "source", "source_and_zone")


def _live_bounded_placement(placement: str) -> tuple[dict[str, Any], str, str, str, float]:
    """Return (installation, running appliance, other appliance, duty, indoor)."""
    gas = "climate.gasketel"
    airco = "climate.airco"

    if placement == "zone_heat":
        return (
            {
                "zones": [
                    zone(
                        "woonkamer",
                        sources=[source("gas", gas, role="heat_only")],
                        indoor_sensor="sensor.woonkamer",
                        heat=settings(21.0, 20.0, outdoor={"minimum": None, "maximum": 19.0}),
                    )
                ],
                "outdoor_sensor": "sensor.buiten",
            },
            gas,
            gas,
            "heat",
            18.0,
        )

    if placement == "zone_cool":
        return (
            {
                "zones": [
                    zone(
                        "woonkamer",
                        sources=[source("airco", airco, role="heat_cool")],
                        indoor_sensor="sensor.woonkamer",
                        cool=settings(23.0, 24.0, outdoor={"minimum": 24.0, "maximum": None}),
                    )
                ],
                "outdoor_sensor": "sensor.buiten",
            },
            airco,
            airco,
            "cool",
            26.0,
        )

    sources = [
        source(
            "gas",
            gas,
            role="heat_only",
            priority=1,
            outdoor={"minimum": None, "maximum": 3.1},
        ),
        source(
            "airco",
            airco,
            role="heat_cool",
            priority=0,
            outdoor={"minimum": 3.1, "maximum": None},
        ),
    ]
    heat = (
        settings(21.0, 20.0, outdoor={"minimum": None, "maximum": 19.0})
        if placement == "source_and_zone"
        else settings(21.0, 20.0)
    )
    return (
        {
            "zones": [
                zone(
                    "woonkamer",
                    sources=sources,
                    indoor_sensor="sensor.woonkamer",
                    heat=heat,
                )
            ],
            "outdoor_sensor": "sensor.buiten",
        },
        gas,
        airco,
        "heat",
        18.0,
    )


@pytest.mark.parametrize("placement", OUTDOOR_PLACEMENTS)
@pytest.mark.parametrize("how", OUTDOOR_UNREADABLE)
async def test_an_unreadable_outdoor_sensor_leaves_a_running_appliance_alone(
    placement: str, how: str
) -> None:
    """Vier plekken voor de grens, vier manieren onleesbaar: nooit iets uitzetten.

    Four places for the bound, four ways to be unreadable: never switch
    anything off.
    """
    installation, running, other, duty, indoor = _live_bounded_placement(placement)
    states: dict[str, tuple[str, dict[str, Any]]] = {
        "sensor.woonkamer": (str(indoor), {}),
        running: (duty, {"hvac_modes": ["heat", "cool", "off"]}),
    }
    if other != running:
        states[other] = ("off", {"hvac_modes": ["heat", "cool", "off"]})
    if how == "missing":
        states.pop("sensor.buiten", None)
    else:
        states["sensor.buiten"] = (how, {})

    home = await start_house(installation, states=states)
    try:
        assert home.state(running) == duty, f"{placement}/{how}: draaiend apparaat ging uit"
        reason = home.values("zone_woonkamer_source").get("reason")
        assert reason == "no_outdoor_temperature", f"{placement}/{how}: reden is {reason}"
    finally:
        await stop_house(home)
