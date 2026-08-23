"""Een dode band op de buitentemperatuur, zodat de omslag niet klappert.

A dead band on the outdoor temperature, so the changeover does not chatter.

De binnentemperatuur heeft een dode band: aan- en uitschakelen gebeuren op twee
verschillende waarden, want anders pendelt een zone op precies één getal. De
buitentemperatuur had die niet. Elke grens daar was hard: de bron-grens die de
gasketel van de warmtepomp scheidt, en de zonegrens die zegt of er bij dit weer
überhaupt verwarmd of gekoeld mag worden.

En buiten schommelt het nu eenmaal rond zo'n grens. In een gesimuleerde maand
waarin de buitentemperatuur telkens een halve graad rond de omslag van 3,1
graden bewoog, wisselde de woonkamer 296 keer rechtstreeks tussen gas en airco -
ruim acht keer per dag, elk een brander die ontsteekt of een compressor die
start. De kortcyclusbescherming ving daar niets van op: die hangt aan een
circuit, en een gasketel hangt aan geen circuit.

De regel is dezelfde als binnen: wat draait mag doorlopen tot een dode band
voorbij zijn grens. Wat stilstaat moet de grens gewoon halen.

The indoor temperature has a dead band: switching on and off happen at two
different values, since otherwise a zone chatters on exactly one number. The
outdoor temperature had none. Every bound there was hard: the source bound
separating the boiler from the heat pump, and the zone bound saying whether this
weather allows heating or cooling at all.

And outside, the weather simply hovers around such a bound. In a simulated month
where the outdoor temperature moved half a degree back and forth around the 3.1
degree changeover, the living room swapped between gas and air conditioner 296
times - over eight times a day, each one a burner igniting or a compressor
starting. Short-cycle protection caught none of it: that hangs on a circuit, and
a gas boiler hangs on no circuit.

The rule is the same as indoors: what runs may carry on until one dead band past
its bound. What stands still has to reach the bound itself.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from conftest import awake, make_world

from custom_components.climate_director.engine import (
    DirectorConfig,
    ModeFamily,
    ModeSettings,
    OutdoorWindow,
    Reason,
    Resident,
    Source,
    SourceRole,
    Zone,
    decide,
    validate,
)
from custom_components.climate_director.engine.serialise import config_from_dict, config_to_dict

NOON = datetime(2026, 3, 9, 12, 0)

AIRCO = "climate.woonkamer_airco"
BOILER = "climate.ketel"
RESERVE = "climate.reserve"

CUTOVER = 3.1


def house(*, band: float = 0.5) -> DirectorConfig:
    """Return the living room with a boiler below the cutover and a heat pump above."""
    return DirectorConfig(
        zones=(
            Zone(
                "woonkamer",
                "Woonkamer",
                "sensor.woonkamer",
                sources=(
                    Source(
                        "woonkamer_airco",
                        AIRCO,
                        role=SourceRole.HEAT_COOL,
                        priority=0,
                        outdoor=OutdoorWindow(minimum=CUTOVER),
                    ),
                    Source(
                        "gasketel",
                        BOILER,
                        role=SourceRole.HEAT_ONLY,
                        priority=1,
                        outdoor=OutdoorWindow(maximum=CUTOVER),
                    ),
                ),
                heat=ModeSettings(21.0, 20.0, outdoor=OutdoorWindow(maximum=19.0)),
            ),
        ),
        residents=(Resident("danny", presence_entity="person.danny"),),
        outdoor_sensor="sensor.buiten",
        outdoor_hysteresis=band,
    )


def running(config: DirectorConfig, outdoor: float, previous=None, *, modes=None):
    """Return the plan for a cold living room at that outdoor temperature."""
    world = make_world(
        now=NOON,
        outdoor=outdoor,
        indoor={"woonkamer": 15.0},
        climates=modes or {AIRCO: "off", BOILER: "off"},
        residents={"danny": awake()},
    )
    return decide(config, world, previous)


def serving(plan) -> str | None:
    """Return which source is serving the living room, if any."""
    decision = plan.decision_for("woonkamer")
    if decision is None or decision.granted is ModeFamily.NEUTRAL:
        return None
    return decision.source_id


def test_an_unreadable_outdoor_sensor_keeps_the_running_boiler_on() -> None:
    """Vorst of niet: zonder buitentemperatuur mag een brandende ketel niet uit.

    De buitengrens is een begrensde grens, en een grens die je niet kunt
    controleren is niet gehaald. Dat gaf `outdoor_outside_window`, en die reden
    zet een draaiend apparaat gewoon uit - alsof de ketel bij vorst uit mag
    omdat de buitensensor het even niet doet. Dat is de enige fout die je kunt
    maken, dus een brandende ketel hoort met rust gelaten te worden, net als
    bij een onleesbare binnentemperatuur.

    Frost or not: without an outdoor temperature a burning boiler must not go
    off. The outdoor bound is a bounded one, and a bound you cannot check is not
    met. That used to give `outdoor_outside_window`, and that reason simply
    switches a running appliance off - as if the boiler may go off in frost
    because the outdoor sensor is down for a moment. That is the one mistake to
    make, so a burning boiler should be left alone, just as with an unreadable
    indoor temperature.
    """
    world = make_world(
        now=NOON,
        outdoor=None,
        indoor={"woonkamer": 15.0},
        climates={AIRCO: "off", BOILER: "heat"},
        residents={"danny": awake()},
    )
    plan = decide(house(), world, None)

    assert plan.command_for(BOILER) is None, "een brandende ketel hoort niet uit te gaan"
    left = plan.untouched_for(BOILER)
    assert left is not None and left.reason is Reason.NO_OUTDOOR_TEMPERATURE
    assert plan.decision_for("woonkamer").reason is Reason.NO_OUTDOOR_TEMPERATURE


class TestTheSettingItself:
    def test_it_defaults_to_half_a_degree(self) -> None:
        assert DirectorConfig().outdoor_hysteresis == 0.5

    def test_it_round_trips(self) -> None:
        config = house(band=1.5)
        assert config_from_dict(config_to_dict(config)) == config

    def test_an_older_installation_gets_the_default(self) -> None:
        assert config_from_dict({}).outdoor_hysteresis == 0.5

    def test_a_negative_band_is_reported(self) -> None:
        found = validate(house(band=-1.0))
        assert any("outdoor" in str(item) for item in found), found

    def test_a_sound_installation_is_quiet(self) -> None:
        assert not validate(house())


class TestTheSourceBound:
    """De grens tussen de gasketel en de warmtepomp."""

    def test_it_picks_the_boiler_below_the_cutover(self) -> None:
        assert serving(running(house(), 2.0)) == "gasketel"

    def test_it_picks_the_heat_pump_above_the_cutover(self) -> None:
        assert serving(running(house(), 5.0)) == "woonkamer_airco"

    def test_a_running_boiler_holds_just_past_the_cutover(self) -> None:
        """Precies waar het klapperde: 3,1 net gepasseerd terwijl de ketel brandt."""
        first = running(house(), 2.9, modes={AIRCO: "off", BOILER: "heat"})
        assert serving(first) == "gasketel"
        second = running(house(), 3.3, first, modes={AIRCO: "off", BOILER: "heat"})
        assert serving(second) == "gasketel"

    def test_it_lets_go_once_the_band_is_passed(self) -> None:
        first = running(house(), 2.9, modes={AIRCO: "off", BOILER: "heat"})
        second = running(house(), 3.7, first, modes={AIRCO: "off", BOILER: "heat"})
        assert serving(second) == "woonkamer_airco"

    def test_a_running_heat_pump_holds_just_below_the_cutover(self) -> None:
        first = running(house(), 3.3, modes={AIRCO: "heat", BOILER: "off"})
        assert serving(first) == "woonkamer_airco"
        second = running(house(), 2.9, first, modes={AIRCO: "heat", BOILER: "off"})
        assert serving(second) == "woonkamer_airco"

    def test_a_source_that_was_not_running_gets_no_stickiness(self) -> None:
        """De rem geldt voor wie draait, niet voor wie stilstaat."""
        assert serving(running(house(), 3.3, None)) == "woonkamer_airco"

    def test_a_band_of_zero_switches_on_the_dot(self) -> None:
        config = house(band=0.0)
        first = running(config, 2.9, modes={AIRCO: "off", BOILER: "heat"})
        second = running(config, 3.2, first, modes={AIRCO: "off", BOILER: "heat"})
        assert serving(second) == "woonkamer_airco"

    def test_a_better_source_still_wins_inside_its_own_window(self) -> None:
        """De rem houdt een tweede keus niet vast als de eerste gewoon weer kan.

        Draaide de zone op een reservebron omdat de airco onbereikbaar was, dan
        hoort hij terug te schuiven zodra de airco er weer is - dat is geen
        omslag op temperatuur maar een uitwijking die voorbij is.
        """
        config = house()
        zone = config.zones[0]
        with_reserve = DirectorConfig(
            zones=(
                Zone(
                    zone.zone_id,
                    zone.name,
                    zone.indoor_sensor,
                    sources=(
                        *zone.sources,
                        Source("reserve", RESERVE, role=SourceRole.HEAT_COOL, priority=5),
                    ),
                    heat=zone.heat,
                ),
            ),
            residents=config.residents,
            outdoor_sensor=config.outdoor_sensor,
            outdoor_hysteresis=config.outdoor_hysteresis,
        )
        # De airco is weg, dus de reserve valt in - binnen zijn eigen venster.
        first = running(with_reserve, 5.0, modes={BOILER: "off", RESERVE: "heat"})
        assert serving(first) == "reserve"
        # De airco is terug: de uitwijking is voorbij en hij hoort weer te winnen.
        second = running(
            with_reserve, 5.0, first, modes={AIRCO: "off", BOILER: "off", RESERVE: "heat"}
        )
        assert serving(second) == "woonkamer_airco"


class TestTheZoneBound:
    """De grens die zegt of er bij dit weer überhaupt verwarmd mag worden."""

    def test_it_stops_above_the_bound(self) -> None:
        plan = running(house(), 21.0)
        decision = plan.decision_for("woonkamer")
        assert decision is not None
        assert decision.reason is Reason.OUTDOOR_OUTSIDE_WINDOW

    def test_a_running_zone_holds_just_past_the_bound(self) -> None:
        config = house()
        first = running(config, 18.5, modes={AIRCO: "heat", BOILER: "off"})
        assert serving(first) == "woonkamer_airco"
        second = running(config, 19.3, first, modes={AIRCO: "heat", BOILER: "off"})
        assert serving(second) == "woonkamer_airco"

    def test_it_lets_go_once_the_band_is_passed(self) -> None:
        config = house()
        first = running(config, 18.5, modes={AIRCO: "heat", BOILER: "off"})
        second = running(config, 19.8, first, modes={AIRCO: "heat", BOILER: "off"})
        assert serving(second) is None

    def test_a_zone_that_was_not_running_gets_no_stickiness(self) -> None:
        plan = running(house(), 19.3, modes={AIRCO: "off", BOILER: "off"})
        assert serving(plan) is None


class TestItReallyStopsTheChatter:
    """Een maand schommelen rond de omslag, geteld."""

    @staticmethod
    def _swaps(band: float) -> int:
        import random

        config = house(band=band)
        rng = random.Random(4242)
        previous = None
        modes = {AIRCO: "off", BOILER: "off"}
        last: str | None = None
        swaps = 0
        # Vier weken, elke tien minuten, telkens rond de 3,1 graden.
        for _ in range(4 * 7 * 24 * 6):
            outdoor = round(CUTOVER + rng.uniform(-0.45, 0.45), 2)
            plan = running(config, outdoor, previous, modes=dict(modes))
            for command in plan.commands:
                modes[command.entity_id] = command.hvac_mode
            now = serving(plan)
            if now is not None and last is not None and now != last:
                swaps += 1
            last = now or last
            previous = plan
        return swaps

    def test_without_a_band_it_chatters(self) -> None:
        assert self._swaps(0.0) > 200

    def test_with_the_default_band_it_does_not(self) -> None:
        assert self._swaps(0.5) == 0

    @pytest.mark.parametrize("band", [0.1, 0.2])
    def test_even_a_small_band_helps(self, band: float) -> None:
        assert self._swaps(band) < self._swaps(0.0)
