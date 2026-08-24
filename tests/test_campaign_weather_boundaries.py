"""Het weer dat precies op de omslagpunten gaat zitten.

Weather that sits exactly on the switch points.

Drie scenario's die de andere campagnes niet dekken:

1. Een maand waarin het weer meermaals per dag omklapt tussen harde vorst en
   een extreme hittegolf, met het seizoen op zomer gepind zodat beide taken
   mogen. Zo wisselt één circuit werkelijk meermaals per dag tussen verwarmen
   en koelen, en de woonkamer tussen ketel en airco.
2. Een half jaar waarin de buitentemperatuur continu een beetje verschuift
   rond het gas/airco-omslagpunt, zodat de bronkeuze telkens opnieuw moet
   kiezen.
3. Een half jaar waarin de buitentemperatuur continu een beetje verschuift
   rond de punten waar de airco tussen verwarmen en koelen omslaat, met de
   dode band ertussen.

Overrides en vooruit-verzoeken zitten in alle drie, en er wordt gecontroleerd
dat ze ook echt voorkwamen.

Three scenarios the other campaigns do not cover:

1. A month in which the weather flips between hard frost and an extreme
   heatwave several times a day, with the season pinned to summer so both
   duties are allowed. One circuit really switches between heating and cooling
   several times a day, and the living room between boiler and heat pump.
2. Half a year in which the outdoor temperature continuously shifts a little
   around the gas/heat-pump cutover, so the source choice has to decide anew
   every time.
3. Half a year in which the outdoor temperature continuously shifts a little
   around the points where the heat pump flips between heating and cooling,
   with the dead band in between.

Overrides and pre-conditioning requests are in all three, and the run checks
that they really occurred.
"""

from __future__ import annotations

import random
from datetime import datetime, time, timedelta

from simulation import Scenario, run_month
from test_campaign_year import BUSY

from custom_components.climate_director.engine import (
    Circuit,
    DirectorConfig,
    GateSettings,
    ModeSettings,
    OutdoorWindow,
    Reason,
    Resident,
    Season,
    Source,
    SourceRole,
    TimeWindow,
    Zone,
    validate,
)
from custom_components.climate_director.engine.models import SeasonSettings

GAS = "climate.gasketel"
LIVING = "climate.woonkamer_airco"
ATTIC = "climate.zolder_airco"


def _modes() -> tuple[ModeSettings, ModeSettings]:
    """Return the existing installation's heat and cool bands."""
    return (
        ModeSettings(
            target=23.0,
            start_at=22.0,
            hysteresis=1.0,
            outdoor=OutdoorWindow(maximum=19.0),
        ),
        ModeSettings(
            target=23.0,
            start_at=24.0,
            hysteresis=1.0,
            outdoor=OutdoorWindow(minimum=24.0),
            seasons=frozenset({Season.SUMMER}),
        ),
    )


def two_room_house(*, attic_unbounded: bool) -> DirectorConfig:
    """Return the real setup shape: gas under 3.1, heat pump above it."""
    living_heat, living_cool = _modes()
    attic_heat, attic_cool = _modes()
    living = Zone(
        zone_id="woonkamer",
        name="Woonkamer",
        indoor_sensor="sensor.woonkamer",
        priority=0,
        sources=(
            Source(
                "gasketel",
                GAS,
                role=SourceRole.HEAT_ONLY,
                priority=0,
                outdoor=OutdoorWindow(maximum=3.1),
            ),
            Source(
                "woonkamer_airco",
                LIVING,
                role=SourceRole.HEAT_COOL,
                priority=1,
                outdoor=OutdoorWindow(minimum=3.1),
            ),
        ),
        heat=living_heat,
        cool=living_cool,
    )
    attic = Zone(
        zone_id="zolder",
        name="Zolder",
        indoor_sensor="sensor.zolder",
        priority=1,
        sources=(
            Source(
                "zolder_airco",
                ATTIC,
                role=SourceRole.HEAT_COOL,
                # In het fictieve dagvorst/hitte-scenario mag de zolderairco ook
                # bij vorst verwarmen, anders koelt het circuit nooit én
                # verwarmt het nooit op dezelfde dag.
                #
                # In the fictional daily-frost/heat scenario the attic unit may
                # also heat during frost, otherwise the circuit never cools and
                # heats on the same day.
                outdoor=OutdoorWindow() if attic_unbounded else OutdoorWindow(minimum=3.1),
            ),
        ),
        heat=attic_heat,
        cool=attic_cool,
    )
    return DirectorConfig(
        zones=(living, attic),
        circuits=(
            Circuit(
                circuit_id="multisplit",
                name="Multi-split",
                units=(LIVING, ATTIC),
                simultaneous_heat_cool=False,
                family_switch_delay=timedelta(seconds=60),
                min_family_switch_interval=timedelta(minutes=30),
                min_cycle_time=timedelta(minutes=3),
            ),
        ),
        residents=(
            Resident(
                "danny",
                "Danny",
                presence_entity="person.danny",
                sleep_entity="sensor.danny_lader",
                sleep_state="wireless",
            ),
            Resident(
                "nancy",
                "Nancy",
                presence_entity="person.nancy",
                sleep_entity="sensor.nancy_lader",
                sleep_state="wireless",
            ),
        ),
        gates=GateSettings(
            require_awake=True,
            max_precondition=timedelta(hours=2),
            guest_window=TimeWindow(time(8, 0), time(23, 0)),
        ),
        outdoor_sensor="sensor.buiten",
    )


def one_room_house() -> DirectorConfig:
    """Return one room with the gas/heat-pump cutover, for the boundary walks."""
    heat, cool = _modes()
    living = Zone(
        zone_id="woonkamer",
        name="Woonkamer",
        indoor_sensor="sensor.woonkamer",
        sources=(
            Source(
                "gasketel",
                GAS,
                role=SourceRole.HEAT_ONLY,
                priority=0,
                outdoor=OutdoorWindow(maximum=3.1),
            ),
            Source(
                "woonkamer_airco",
                LIVING,
                role=SourceRole.HEAT_COOL,
                priority=1,
                outdoor=OutdoorWindow(minimum=3.1),
            ),
        ),
        heat=heat,
        cool=cool,
    )
    return DirectorConfig(
        zones=(living,),
        residents=(
            Resident(
                "danny",
                "Danny",
                presence_entity="person.danny",
                sleep_entity="sensor.danny_lader",
                sleep_state="wireless",
            ),
        ),
        gates=GateSettings(
            require_awake=True,
            max_precondition=timedelta(hours=2),
            guest_window=TimeWindow(time(8, 0), time(23, 0)),
        ),
        outdoor_sensor="sensor.buiten",
    )


# -- weer / weather -----------------------------------------------------------


def _daily_extremes(now: datetime, rng: random.Random) -> tuple[float, Season]:
    """Hard frost and an extreme heatwave several times a day, season pinned to summer.

    Drie cycli per etmaal: twee uur vorst, zes uur hittegolf. Het seizoen blijft
    zomer zodat de airco op dezelfde dag mag verwarmen én koelen.

    Three cycles per day: two hours of frost, six of heatwave. The season stays
    summer so the heat pump may heat and cool on the same day.
    """
    minutes = now.hour * 60 + now.minute
    cold = (minutes % (8 * 60)) < 2 * 60
    base = -12.0 if cold else 36.0
    return round(base + rng.uniform(-1.5, 1.5), 1), Season.SUMMER


def _hovering(mean: float, sigma: float, low: float, high: float):
    """Return a weather function whose outdoor temperature wanders around `mean`."""

    def weather(now: datetime, rng: random.Random) -> tuple[float, Season]:
        state["value"] = min(max(state["value"] + rng.gauss(0, sigma), low), high)
        return round(state["value"], 1), SeasonSettings().for_month(now.month)

    state = {"value": mean}
    return weather


# -- scenario's / scenarios ----------------------------------------------------


def _scenario(name, config, start, weather, *, days, leak_rate=0.02) -> Scenario:
    zone_ids = {zone.zone_id for zone in config.zones}
    start_indoor = {"woonkamer": 22.0}
    if "zolder" in zone_ids:
        start_indoor["zolder"] = 22.0
    return Scenario(
        name=name,
        config=config,
        start=start,
        start_indoor=start_indoor,
        weather=weather,
        days=days,
        profile=BUSY,
        leak_rate=leak_rate,
        duty_rate=0.4,
    )


class TestDailyExtremesForAMonth:
    """Een maand lang meermaals per dag vorst en hittegolf.

    A month of frost and heatwave several times a day.
    """

    def test_both_duties_switch_several_times_a_day(self) -> None:
        config = two_room_house(attic_unbounded=True)
        assert not validate(config), validate(config)
        scenario = _scenario(
            "dagelijkse_extremen",
            config,
            datetime(2026, 7, 1, 0, 0),
            _daily_extremes,
            days=30,
            leak_rate=0.06,
        )
        run = run_month(scenario, seed=20260701)

        assert run.commanded["heat"] > 100, run.commanded
        assert run.commanded["cool"] > 100, run.commanded
        # De woonkamer wisselt werkelijk tussen ketel en airco.
        # The living room really switches between boiler and heat pump.
        assert run.reasons[Reason.OTHER_SOURCE_CHOSEN.value] > 0, run.reasons
        # Het circuit wisselt werkelijk van taak, met pauze en minimumlooptijd.
        # The circuit really switches duty, with its pause and minimum run.
        assert (
            run.reasons[Reason.CIRCUIT_SWITCH_PENDING.value]
            + run.reasons[Reason.CIRCUIT_SWITCH_TOO_SOON.value]
            > 0
        ), run.reasons
        # Overrides en vooruit-verzoeken kwamen voor.
        # Overrides and pre-conditioning requests occurred.
        assert run.events["override"] > 0, run.events
        assert run.events["precondition"] > 0, run.events
        assert run.reasons[Reason.MANUAL_OVERRIDE.value] > 0, run.reasons
        for zone_id, temperature in run.indoor.items():
            assert -10.0 < temperature < 45.0, (zone_id, temperature)


class TestHalfAYearAroundTheGasCutover:
    """Een half jaar lang continu een beetje rond het gas/airco-omslagpunt.

    Half a year of continuous small shifts around the gas/heat-pump cutover.
    """

    def test_the_source_flips_and_the_promises_hold(self) -> None:
        config = one_room_house()
        assert not validate(config), validate(config)
        scenario = _scenario(
            "gas_airco_grens",
            config,
            datetime(2026, 1, 1, 0, 0),
            _hovering(3.1, 0.25, 2.0, 4.2),
            days=182,
        )
        run = run_month(scenario, seed=20260101)

        assert run.commanded["heat"] > 100, run.commanded
        assert run.commanded["cool"] == 0, run.commanded
        # De bron wisselt werkelijk; de niet-gekozene wordt telkens uitgezet.
        # The source really flips; the loser is stood down every time.
        assert run.reasons[Reason.OTHER_SOURCE_CHOSEN.value] > 0, run.reasons
        assert run.events["override"] > 0, run.events
        assert run.events["precondition"] > 0, run.events
        assert run.reasons[Reason.MANUAL_OVERRIDE.value] > 0, run.reasons


class TestHalfAYearAroundTheHeatCoolSwitch:
    """Een half jaar lang continu een beetje rond de koel/verwarm-omslagpunten.

    Half a year of continuous small shifts around the heat/cool switch points.
    """

    def test_the_heat_pump_heats_and_cools_in_turn(self) -> None:
        config = one_room_house()
        assert not validate(config), validate(config)
        scenario = _scenario(
            "airco_koel_verwarm_grens",
            config,
            datetime(2026, 7, 1, 0, 0),
            _hovering(21.5, 0.4, 16.0, 27.0),
            days=182,
        )
        run = run_month(scenario, seed=20260701)

        assert run.commanded["heat"] > 100, run.commanded
        assert run.commanded["cool"] > 100, run.commanded
        # In de dode band tussen 19 en 24 gebeurt niets; dat moet ook gemeld zijn.
        # Nothing happens in the dead band between 19 and 24; that is reported too.
        assert run.reasons[Reason.OUTDOOR_OUTSIDE_WINDOW.value] > 0, run.reasons
        assert run.events["override"] > 0, run.events
        assert run.events["precondition"] > 0, run.events
        assert run.reasons[Reason.MANUAL_OVERRIDE.value] > 0, run.reasons
        for zone_id, temperature in run.indoor.items():
            assert -10.0 < temperature < 45.0, (zone_id, temperature)
