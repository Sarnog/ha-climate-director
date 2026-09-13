"""R27-3: een override-setpoint blijft binnen het bereik van het apparaat.

R27-3: an override setpoint stays inside the appliance's range.

`_async_set_override` gaf het setpoint ongeklemd door. Een koppig apparaat
weigert een waarde buiten zijn `min_temp`/`max_temp` stil - `applier.apply()`
vangt die weigering op - dus de override liep door met een setpoint dat nooit
aankwam: de zone stond op "van mij" terwijl het apparaat op zijn oude waarde
bleef staan. Het engine-pad klemde al (`engine.clamped_target`); dit bestand
pint vast dat het override-pad dezelfde regel volgt, in beide eenheden.

`_async_set_override` passed the setpoint through unclamped. A stubborn
appliance quietly refuses a value outside its `min_temp`/`max_temp` -
`applier.apply()` catches that refusal - so the override carried on with a
setpoint that never arrived: the zone stood on "mine" while the appliance stayed
on its old value. The engine path already clamped (`engine.clamped_target`);
this file pins down that the override path follows the same rule, in both unit
systems.
"""

from __future__ import annotations

from typing import Any

import pytest
from harness_live import LiveHome, settings, source, start_house, stop_house, zone
from homeassistant.util.unit_system import IMPERIAL_SYSTEM, METRIC_SYSTEM

from custom_components.climate_director.const import DOMAIN

LIVING = "climate.woonkamer"
METRIC_RANGE = (10.0, 30.0)
IMPERIAL_RANGE = (50.0, 86.0)


def installation() -> dict[str, Any]:
    """Return one room that may both heat and cool, so either mode can be asked."""
    return {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("woonkamer_ketel", LIVING)],
                indoor_sensor="sensor.woonkamer",
                heat=settings(21.0, 20.0),
                cool=settings(23.0, 24.0),
            )
        ],
        "outdoor_sensor": "sensor.buiten",
    }


def world(indoor: str, unit: str, minimum: float, maximum: float) -> dict[str, Any]:
    """Return a house whose appliance reports its own temperature range."""
    return {
        "sensor.woonkamer": (indoor, {"unit_of_measurement": unit}),
        "sensor.buiten": ("4.0", {"unit_of_measurement": unit}),
        LIVING: (
            "off",
            {"min_temp": minimum, "max_temp": maximum, "hvac_modes": ["heat", "cool", "off"]},
        ),
    }


async def house(unit_system: str, minimum: float, maximum: float) -> LiveHome:
    """Start the house with a wise appliance and widen its range.

    Het harnas kent "stubborn" met een vast bereik van 10-30 °C; voor het
    imperiale geval zetten we dat bereik op 50-86 °F, wat hetzelfde is. Zo
    weigert het apparaat in beide stelsels precies wat er buiten valt.

    The harness knows "stubborn" with a fixed range of 10-30 °C; for the imperial
    case we put that range at 50-86 °F, which is the same thing. That way the
    appliance refuses exactly what falls outside in both systems.
    """
    imperial = unit_system is IMPERIAL_SYSTEM
    unit = "°F" if imperial else "°C"
    indoor = "68.0" if imperial else "20.0"
    home = await start_house(
        installation(),
        states=world(indoor, unit, minimum, maximum),
        appliance="stubborn",
        unit_system=unit_system,
    )
    home.appliance["min_temp"] = minimum
    home.appliance["max_temp"] = maximum
    return home


async def set_override(home: LiveHome, temperature: float | None) -> None:
    """Hand the zone over for an hour and decide once.

    `home.evaluate()` staat er los bij: `home.settle()` start geen beslisronde,
    dus zonder deze aanroep blijft het override-commando in de wachtrij staan.

    `home.evaluate()` stands apart: `home.settle()` starts no decision round, so
    without this call the override command stays in the queue.
    """
    data: dict[str, Any] = {"zone_id": "woonkamer", "hvac_mode": "cool", "minutes": 60}
    if temperature is not None:
        data["temperature"] = temperature
    await home.call(DOMAIN, "set_override", data)
    await home.evaluate()


def setpoints(home: LiveHome) -> list[float]:
    """Return every setpoint the applier sent, in order."""
    return [data["temperature"] for _service, data in home.climate_calls() if "temperature" in data]


class TestAnOverrideSetpointStaysInsideTheAppliance:
    """Een override vraagt wat het apparaat aanneemt, net als het engine-pad."""

    @pytest.mark.parametrize(
        ("unit_system", "minimum", "maximum", "wanted", "expected"),
        [
            (METRIC_SYSTEM, *METRIC_RANGE, 40.0, 30.0),
            (METRIC_SYSTEM, *METRIC_RANGE, 5.0, 10.0),
            (IMPERIAL_SYSTEM, *IMPERIAL_RANGE, 104.0, 86.0),
            (IMPERIAL_SYSTEM, *IMPERIAL_RANGE, 41.0, 50.0),
        ],
    )
    async def test_a_setpoint_outside_the_range_lands_on_the_bound(
        self,
        unit_system: str,
        minimum: float,
        maximum: float,
        wanted: float,
        expected: float,
    ) -> None:
        """Te hoog of te laag wordt de dichtstbijzijnde grens, niet geweigerd."""
        home = await house(unit_system, minimum, maximum)
        try:
            home.clear_calls()
            await set_override(home, wanted)

            assert setpoints(home) == [expected], home.climate_calls()
            assert home.attributes(LIVING)["temperature"] == expected
            assert home.coordinator.zone_overrides["woonkamer"] is True
        finally:
            await stop_house(home)

    async def test_a_setpoint_inside_the_range_is_passed_through(self) -> None:
        """Een setpoint binnen het bereik blijft ongemoeid: 68 °F is 20 °C."""
        home = await house(IMPERIAL_SYSTEM, *IMPERIAL_RANGE)
        try:
            home.clear_calls()
            await set_override(home, 68.0)

            assert setpoints(home) == [68.0], home.climate_calls()
        finally:
            await stop_house(home)

    async def test_without_a_temperature_nothing_is_set(self) -> None:
        """Zonder temperatuur zet de override alleen de stand, geen setpoint."""
        home = await house(METRIC_SYSTEM, *METRIC_RANGE)
        try:
            home.clear_calls()
            await set_override(home, None)

            assert setpoints(home) == [], home.climate_calls()
            assert home.coordinator.zone_overrides["woonkamer"] is True
        finally:
            await stop_house(home)


class TestTheClampHangsOnSending:
    """R28-2: de klem hangt aan het versturen, niet aan de aanroep.

    Tussen de service-aanroep en de beslisronde waarin het commando de deur uit
    gaat, kan het apparaat zijn bereik gaan melden - of juist kwijtraken. De
    klem hoort daarom bij de ronde, waar de wereld al in de hand is, en niet bij
    de aanroep. Anders gaat er een setpoint uit dat het apparaat weigert, en
    loopt de override door met een waarde die nooit aankwam: de zone staat op
    "van mij" terwijl het apparaat op zijn oude waarde blijft staan.

    R28-2: the clamp hangs on sending, not on the call.

    Between the service call and the decision round that puts the command on the
    wire, the appliance can start reporting its range - or lose it. The clamp
    therefore belongs with the round, where the world is already in hand, and
    not with the call. Otherwise a setpoint goes out that the appliance refuses,
    and the override carries on with a value that never arrived: the zone stands
    on "mine" while the appliance stays on its old value.
    """

    async def test_a_range_that_arrives_after_the_call_is_still_honoured(self) -> None:
        """Het bereik komt binnen ná de aanroep en vóór de ronde: klem naar 30.

        Het apparaat is op het moment van de aanroep onbereikbaar - de
        cloud-drop-out waarin `min_temp`/`max_temp` ontbreken - en meldt zijn
        bereik van 10-30 pas vóór de beslisronde.

        The range arrives after the call and before the round: clamp to 30. The
        appliance is unreachable at the moment of the call - the cloud drop-out
        in which `min_temp`/`max_temp` are missing - and only reports its 10-30
        range before the decision round.
        """
        states = {
            "sensor.woonkamer": ("20.0", {"unit_of_measurement": "°C"}),
            "sensor.buiten": ("4.0", {"unit_of_measurement": "°C"}),
            LIVING: ("unavailable", {"hvac_modes": ["heat", "cool", "off"]}),
        }
        home = await start_house(
            installation(), states=states, appliance="stubborn", unit_system=METRIC_SYSTEM
        )
        try:
            home.clear_calls()

            await home.call(
                DOMAIN,
                "set_override",
                {"zone_id": "woonkamer", "hvac_mode": "cool", "minutes": 60, "temperature": 40.0},
            )

            # Het apparaat is er weer, mét zijn bereik, vóór de beslisronde.
            # The appliance is back, with its range, before the decision round.
            home.set(
                LIVING,
                "off",
                hvac_modes=["heat", "cool", "off"],
                min_temp=10.0,
                max_temp=30.0,
            )

            await home.evaluate()

            assert setpoints(home) == [30.0], home.climate_calls()
            assert home.coordinator.zone_overrides["woonkamer"] is True
        finally:
            await stop_house(home)


class TestTheEnginePathKeepsClamping:
    async def test_a_target_outside_the_range_lands_on_the_bound(self) -> None:
        """Het engine-pad klemde al; dat blijft zo, in dezelfde vorm.

        The engine path already clamped; that stays, in the same shape.
        """
        data = installation()
        # Een doel boven het bereik van het apparaat en een koude kamer: het
        # engine-pad hoort naar de bovengrens te klemmen, net als het
        # override-pad.
        # A target above the appliance's range and a cold room: the engine path
        # has to clamp to the upper bound, just like the override path.
        data["zones"][0]["heat"]["target"] = 40.0
        home = await start_house(
            data,
            states={
                "sensor.woonkamer": ("2.0", {"unit_of_measurement": "°C"}),
                "sensor.buiten": ("4.0", {"unit_of_measurement": "°C"}),
                LIVING: (
                    "off",
                    {"min_temp": 10.0, "max_temp": 30.0, "hvac_modes": ["heat", "off"]},
                ),
            },
            appliance="stubborn",
            unit_system=METRIC_SYSTEM,
        )
        try:
            await home.evaluate()
            assert setpoints(home) == [30.0], home.climate_calls()
        finally:
            await stop_house(home)
