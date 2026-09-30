"""Een hand aan een apparaat van de zone laat de gedeelde ketel met rust.

A hand at an appliance of the zone leaves the shared boiler alone.

`tests/test_hand_does_not_hand_over.py` legt dat in de engine vast; dit bestand
meet hetzelfde in een draaiende Home Assistant, met de cv-thermostaat als
**bron** onder twee kamers. De zolder heeft een airco van zichzelf en de ketel als
tweede bron: iemand zet die airco met de afstandsbediening uit, en daarna wordt de
woonkamer koud. De ketel hoort dan voor de woonkamer te gaan draaien - een hand
draagt niets over (anker 11). De tweede toets meet de andere kant: een hand aan de
gedeelde ketel zelf legt elke kamer erop stil, want dat apparaat is van niemand in
het bijzonder.

`tests/test_hand_does_not_hand_over.py` pins that down in the engine; this file
measures the same inside a running Home Assistant, with the cv thermostat as a
**source** under two rooms. The attic has an air conditioner of its own and the
boiler as its second source: somebody switches that air conditioner off with the
remote, and then the living room goes cold. The boiler should then run for the
living room - a hand hands nothing over (anchor 11). The second test measures the
other side: a hand at the shared boiler itself silences every room hanging off it,
since that appliance belongs to no room in particular.
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
AIRCO = "climate.airco_zolder"
LIVING = "sensor.woonkamer"
ATTIC = "sensor.zolder"
MODES = {"hvac_modes": ["off", "heat", "cool"], "current_temperature": 18.5}


def installation() -> dict[str, Any]:
    """Return two rooms; only the attic has an appliance of its own.

    De woonkamer hangt uitsluitend aan de ketel, zodat een overgedragen ketel daar
    meteen als `no_source_available` te lezen is.

    The living room hangs on the boiler alone, so a handed-over boiler reads there
    as `no_source_available` straight away.
    """
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


def world(
    *, living: str, attic: str, boiler: str = "off", airco: str = "off"
) -> dict[str, tuple[str, dict[str, Any]]]:
    """Return a world with both indoor temperatures, the boiler and the airco."""
    return {
        LIVING: (living, {"unit_of_measurement": "°C"}),
        ATTIC: (attic, {"unit_of_measurement": "°C"}),
        BOILER: (boiler, {"hvac_modes": ["off", "heat"], "temperature": 19.0}),
        AIRCO: (airco, dict(MODES)),
    }


def reason_of(home: LiveHome, zone_id: str) -> str:
    """Return the reason of one zone's last decision."""
    decision = home.coordinator.data.decision_for(zone_id)
    assert decision is not None, f"geen beslissing voor {zone_id}"
    return decision.reason.value


async def settle(home: LiveHome) -> None:
    """Let the debouncer's pass and everything behind it finish."""
    await asyncio.sleep(1.5)
    await home.settle()


class TestAHandAtTheAtticAirConditioner:
    """De hand raakt alleen de zolder; de woonkamer houdt de ketel.

    The hand touches the attic alone; the living room keeps the boiler.
    """

    async def test_the_living_room_gets_the_boiler(self) -> None:
        home = await start_house(
            installation(), config_dir=new_config_dir(), states=world(living="22.5", attic="18.5")
        )
        try:
            await home.evaluate()
            await settle(home)
            assert home.state(AIRCO) == "heat", "de zolder verwarmt met zijn eigen airco"
            assert home.state(BOILER) == "off", "de woonkamer vraagt nog niets"

            home.clear_calls()
            home.hass.states.async_set(AIRCO, "off", dict(MODES))
            await settle(home)
            assert home.coordinator._handed_back.get("zolder") is not None, (
                "de hand aan de airco is niet opgemerkt"
            )
            assert home.climate_calls() == [], "de director zette de airco zelf weer aan"
            assert reason_of(home, "zolder") == "manual_override", "de zolder hoort stil te staan"

            home.clear_calls()
            home.hass.states.async_set(LIVING, "18.0", {"unit_of_measurement": "°C"})
            await settle(home)

            # De zolder komt hier terug: onze eigen aanzet van de gedeelde ketel
            # geldt voor elke zone die eraan hangt als "weer aangezet", en dat is
            # het oude gedrag van een hand - dezelfde uitkomst als vóór de
            # override-overdracht, met precies deze stappen nagemeten. Wat deze
            # toets vastlegt is de kern van de reparatie: de woonkamer krijgt de
            # ketel, want een hand draagt hem niet over.
            #
            # The attic rejoins here: our own switch-on of the shared boiler counts
            # for every zone hanging off it as "switched on again", and that is the
            # old meaning of a hand - the same outcome as before the override
            # handover, measured with exactly these steps. What this test pins down
            # is the heart of the repair: the living room gets the boiler, since a
            # hand does not hand it over.
            assert home.state(BOILER) == "heat", (
                "de woonkamer hoort de ketel te krijgen; de hand aan de zolder draagt hem niet over"
            )
            assert reason_of(home, "woonkamer") == "regulating"
        finally:
            await stop_house(home)


class TestAHandAtTheSharedBoiler:
    """Een hand aan de ketel zelf legt elke kamer erop stil.

    A hand at the boiler itself silences every room hanging off it.
    """

    async def test_no_room_turns_the_boiler_back_on(self) -> None:
        home = await start_house(
            installation(), config_dir=new_config_dir(), states=world(living="18.0", attic="23.0")
        )
        try:
            await home.evaluate()
            await settle(home)
            assert home.state(BOILER) == "heat", "de woonkamer vroeg de ketel"

            home.clear_calls()
            home.hass.states.async_set(
                BOILER, "off", {"hvac_modes": ["off", "heat"], "temperature": 19.0}
            )
            await settle(home)

            assert set(home.coordinator._handed_back) == {"woonkamer", "zolder"}, (
                "een hand aan de gedeelde ketel hoort elke kamer erop stil te leggen"
            )
            assert home.climate_calls() == [], "een van de kamers zette de ketel weer aan"
            assert home.state(BOILER) == "off"
        finally:
            await stop_house(home)
