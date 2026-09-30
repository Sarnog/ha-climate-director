"""Wat de "op reserve"-sensor meldt als een apparaat is overgedragen.

What the "on reserve" sensor reports when an appliance has been handed over.

De sensor hoort te melden dat er iets *stuk* is of dat een voorkeursapparaat
overgeslagen moest worden. Een apparaat dat de gebruiker zelf heeft overgedragen
is geen van beide: de director komt er niet aan, en de kamer warmt met de volgende
bron precies zoals bedoeld. De melding hoort daarom uit te blijven, terwijl een
onbereikbare bron vóór de overgedragen ketel gewoon gemeld blijft worden.

The sensor is meant to report that something is *broken* or that a preferred
appliance had to be skipped. An appliance the user has handed over themselves is
neither: the director does not touch it, and the room warms with the next source
exactly as intended. The notice is therefore meant to stay off, while an
unreachable source ahead of the handed-over boiler keeps being reported.
"""

from __future__ import annotations

from typing import Any

from harness_live import (
    new_config_dir,
    settings,
    source,
    start_house,
    stop_house,
    zone,
)

KETEL = "climate.ketel"
KLEP = "climate.klep"
OUD = "climate.klep_oud"
LIVING_SENSOR = "sensor.woonkamer"
ATTIC_SENSOR = "sensor.zolder"
MODES = {"hvac_modes": ["off", "heat"], "current_temperature": 19.0}


def installation(*, broken: bool = False) -> dict[str, Any]:
    """Return a living room on the boiler and an attic with a valve of its own.

    De zolder hangt aan dezelfde ketel als de woonkamer en heeft daarnaast een
    eigen klep, zodat hij doorschuift zodra die ketel overgedragen is. Met
    `broken` staat er ook nog een kapotte klep vóór de ketel in de voorkeur.

    The attic hangs off the same boiler as the living room and has a valve of its
    own beside it, so it moves on as soon as that boiler is handed over. With
    `broken` a broken valve also stands ahead of the boiler in preference.
    """
    attic = [
        source("z_ketel", KETEL, role="heat_only", priority=1),
        source("z_klep", KLEP, role="heat_only", priority=2),
    ]
    if broken:
        attic.insert(0, source("z_oud", OUD, role="heat_only", priority=0))
    return {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("w_ketel", KETEL, role="heat_only")],
                heat=settings(21.0, 20.0),
            ),
            zone("zolder", sources=attic, heat=settings(21.0, 20.0)),
        ],
        "heating_layout": "central",
    }


def world(*, broken: bool = False) -> dict[str, tuple[str, dict[str, Any]]]:
    """Return a cold house, with the broken valve unreachable when asked for."""
    found: dict[str, tuple[str, dict[str, Any]]] = {
        LIVING_SENSOR: ("18.5", {"unit_of_measurement": "°C"}),
        ATTIC_SENSOR: ("18.5", {"unit_of_measurement": "°C"}),
        KETEL: ("off", dict(MODES)),
        KLEP: ("off", dict(MODES)),
    }
    if broken:
        found[OUD] = ("unavailable", {"unit_of_measurement": "°C"})
    return found


async def hand_over_the_living_room(home) -> None:
    """Hand the living room over to the user, as the action does."""
    await home.call(
        "climate_director",
        "set_override",
        {"zone_id": "woonkamer", "hvac_mode": "heat", "temperature": 23, "minutes": 60},
    )
    await home.settle()


class TestTheAtticIsNotOnReserveForAHandedOverBoiler:
    """N3: de zolder staat niet "op reserve" voor een overgedragen ketel.

    N3: the attic does not stand "on reserve" for a handed-over boiler.

    De woonkamer draagt de ketel over; de zolder zakt naar zijn eigen klep. Dat is
    geen storing maar de bedoeling, dus de sensor hoort uit te blijven en de kamer
    hoort gewoon te regelen.
    """

    async def test_the_sensor_stays_off_and_the_valve_serves(self) -> None:
        home = await start_house(installation(), config_dir=new_config_dir(), states=world())
        try:
            await home.evaluate()
            await home.settle()
            assert home.value("zone_zolder_fallback") == "off", (
                "zonder overdracht valt er niets te melden"
            )

            await hand_over_the_living_room(home)
            await home.evaluate()
            await home.settle()

            assert home.value("zone_zolder_fallback") == "off", (
                "een overgedragen ketel is geen storing"
            )
            assert home.values("zone_zolder_fallback")["unreachable"] == []
            assert home.values("zone_zolder_fallback")["serving"] == "z_klep"
            decision = home.coordinator.data.decision_for("zolder")
            assert decision is not None
            assert decision.source_id == "z_klep", "de overgedragen ketel is geen kandidaat"
            assert home.state(KLEP) == "heat", "de zolder hoort op zijn eigen klep te warmen"
        finally:
            await stop_house(home)


class TestABrokenSourceAheadOfTheHandoverIsStillReported:
    """De tegenproef: een onbereikbare bron vóór de overgedragen ketel blijft staan.

    The counter test: an unreachable source ahead of the handed-over boiler stays.

    De kapotte klep staat in de voorkeur vóór de ketel, dus de zolder zakt twee
    treden: langs de onbereikbare klep en langs de overgedragen ketel, naar zijn
    eigen klep. Alleen de onbereikbare hoort in de melding te staan.
    """

    async def test_the_broken_valve_is_named(self) -> None:
        home = await start_house(
            installation(broken=True), config_dir=new_config_dir(), states=world(broken=True)
        )
        try:
            await hand_over_the_living_room(home)
            await home.evaluate()
            await home.settle()

            assert home.value("zone_zolder_fallback") == "on"
            assert home.values("zone_zolder_fallback")["unreachable"] == ["z_oud"]
            assert home.values("zone_zolder_fallback")["serving"] == "z_klep"
        finally:
            await stop_house(home)
