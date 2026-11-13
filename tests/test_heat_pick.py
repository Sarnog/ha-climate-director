"""Tests voor schakelen op kosten: de voorkeur, de bronkeuze en de omslagtemperatuur.

Tests for switching on cost: the preference, the source selection and the
changeover temperature.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from conftest import climate, make_world

from custom_components.climate_director.engine import (
    ModeFamily,
    OutdoorWindow,
    Source,
    SourceEnergy,
    Zone,
    sources,
)
from custom_components.climate_director.engine.cost import CopCurve
from custom_components.climate_director.engine.energy import (
    BREAK_EVEN,
    ELECTRIC,
    ELECTRIC_ALWAYS,
    GAS,
    GAS_ALWAYS,
    EnergySettings,
    HeatCosts,
    break_even,
)
from custom_components.climate_director.engine.heat_pick import (
    COLD_LIMIT,
    COST,
    NO_OUTDOOR,
    OFF,
    SEASON_LOCK,
    UNKNOWN,
    HeatPick,
    pick_heat_source,
)
from custom_components.climate_director.engine.models import Season

SETTINGS = EnergySettings(
    grid_price_sensor="sensor.stroom",
    gas_price=1.8,
    cop_curve="-5:2.0, 5:2.8, 15:4.5",
    cost_control=True,
    cold_limit=2.0,
    switch_margin=10.0,
)


def costs(gas: float | None, electric: float | None) -> HeatCosts:
    return HeatCosts(gas=gas, electric=electric, cop=3.0, electricity_price=0.3, cheapest=None)


class TestPickHeatSource:
    def test_off_gives_no_preference(self) -> None:
        settings = replace(SETTINGS, cost_control=False)
        assert pick_heat_source(settings, costs(0.2, 0.1), 8.0) == HeatPick(None, OFF)

    def test_unknown_outdoor_gives_no_preference(self) -> None:
        assert pick_heat_source(SETTINGS, costs(0.2, 0.1), None) == HeatPick(None, NO_OUTDOOR)

    def test_the_cheaper_source_wins(self) -> None:
        assert pick_heat_source(SETTINGS, costs(0.2, 0.1), 8.0) == HeatPick(ELECTRIC, COST)
        assert pick_heat_source(SETTINGS, costs(0.1, 0.2), 8.0) == HeatPick(GAS, COST)

    def test_unknown_costs_give_no_preference(self) -> None:
        assert pick_heat_source(SETTINGS, costs(None, None), 8.0) == HeatPick(None, UNKNOWN)

    def test_one_known_cost_is_enough(self) -> None:
        assert pick_heat_source(SETTINGS, costs(0.2, None), 8.0) == HeatPick(GAS, COST)

    def test_the_cold_limit_always_goes_to_gas(self) -> None:
        assert pick_heat_source(SETTINGS, costs(0.5, 0.01), 1.9) == HeatPick(GAS, COLD_LIMIT)

    def test_the_limit_itself_is_not_cold(self) -> None:
        assert pick_heat_source(SETTINGS, costs(0.5, 0.01), 2.0).reason == COST

    def test_no_cold_limit_when_empty(self) -> None:
        settings = replace(SETTINGS, cold_limit=None)
        assert pick_heat_source(settings, costs(0.5, 0.01), -10.0) == HeatPick(ELECTRIC, COST)

    def test_electric_returns_one_dead_band_above_the_limit(self) -> None:
        held = HeatPick(GAS, COLD_LIMIT)
        inside = pick_heat_source(SETTINGS, costs(0.5, 0.01), 2.3, held, 0.5)
        assert inside == HeatPick(GAS, COLD_LIMIT)
        outside = pick_heat_source(SETTINGS, costs(0.5, 0.01), 2.5, held, 0.5)
        assert outside == HeatPick(ELECTRIC, COST)

    def test_without_the_cold_limit_the_band_adds_nothing(self) -> None:
        held = HeatPick(GAS, COST)
        assert pick_heat_source(SETTINGS, costs(0.5, 0.01), 2.1, held, 0.5).preferred == ELECTRIC

    def test_the_running_source_keeps_the_zone_within_the_margin(self) -> None:
        held = HeatPick(GAS, COST)
        # elektrisch is 5% goedkoper, de marge is 10%: gas houdt de keus
        assert pick_heat_source(SETTINGS, costs(0.20, 0.19), 8.0, held).preferred == GAS
        assert pick_heat_source(SETTINGS, costs(0.20, 0.17), 8.0, held).preferred == ELECTRIC

    def test_a_preference_held_by_the_cold_limit_does_not_hold_on_cost(self) -> None:
        held = HeatPick(GAS, COLD_LIMIT)
        assert pick_heat_source(SETTINGS, costs(0.20, 0.19), 8.0, held).preferred == ELECTRIC


class TestSeasonLock:
    LOCKED = replace(SETTINGS, season_lock=True)

    def test_summer_picks_electric_whatever_the_price_or_the_cold(self) -> None:
        pick = pick_heat_source(self.LOCKED, costs(0.1, 0.9), 1.0, season=Season.SUMMER)
        assert pick == HeatPick(ELECTRIC, SEASON_LOCK)

    def test_summer_needs_no_outdoor_temperature(self) -> None:
        pick = pick_heat_source(self.LOCKED, costs(None, None), None, season=Season.SUMMER)
        assert pick == HeatPick(ELECTRIC, SEASON_LOCK)

    def test_winter_and_unknown_seasons_decide_on_cost(self) -> None:
        for season in (Season.WINTER, Season.UNKNOWN):
            pick = pick_heat_source(self.LOCKED, costs(0.1, 0.9), 8.0, season=season)
            assert pick == HeatPick(GAS, COST)

    def test_the_lock_off_leaves_summer_alone(self) -> None:
        pick = pick_heat_source(SETTINGS, costs(0.1, 0.9), 8.0, season=Season.SUMMER)
        assert pick == HeatPick(GAS, COST)

    def test_cost_control_off_still_means_no_preference(self) -> None:
        settings = replace(self.LOCKED, cost_control=False)
        assert pick_heat_source(settings, costs(0.1, 0.9), 8.0, season=Season.SUMMER).reason == OFF


class TestBreakEven:
    def test_a_crossover_on_the_curve(self) -> None:
        # gas 1,80 / (9,77 * 0,9) = 0,2047 per kWh; bij 0,50 per kWh stroom is
        # COP 2,44 nodig, en de curve haalt dat tussen -5 (2,0) en 5 (2,8).
        result = break_even(SETTINGS, 0.50)
        assert result.verdict == BREAK_EVEN
        assert result.temperature == pytest.approx(-5 + 10 * (2.4425 - 2.0) / 0.8, abs=0.05)

    def test_cheap_power_is_cheaper_everywhere(self) -> None:
        assert break_even(SETTINGS, 0.30) == break_even(SETTINGS, 0.30)
        assert break_even(SETTINGS, 0.30).verdict == ELECTRIC_ALWAYS

    def test_dear_power_is_dearer_everywhere(self) -> None:
        assert break_even(SETTINGS, 1.5).verdict == GAS_ALWAYS

    def test_a_negative_price_is_cheaper_everywhere(self) -> None:
        assert break_even(SETTINGS, -0.05).verdict == ELECTRIC_ALWAYS

    def test_a_reading_for_the_gas_price_wins_over_the_fixed_one(self) -> None:
        cheap = break_even(SETTINGS, 0.50, gas_reading=0.9)
        assert cheap.verdict == GAS_ALWAYS
        assert break_even(SETTINGS, 0.50).verdict == BREAK_EVEN

    @pytest.mark.parametrize(
        "settings, price",
        [
            (replace(SETTINGS, cop_curve="kapot"), 0.3),
            (replace(SETTINGS, gas_price=0.0), 0.3),
            (SETTINGS, None),
        ],
    )
    def test_nothing_usable_gives_no_answer(self, settings, price) -> None:
        assert break_even(settings, price).verdict is None


class TestCurveCrossing:
    curve = CopCurve(points=((-5.0, 2.0), (7.0, 4.0), (15.0, 5.0)))

    def test_inside_a_segment(self) -> None:
        assert self.curve.first_temperature_with(3.0) == pytest.approx(1.0)

    def test_already_above_at_the_cold_end(self) -> None:
        assert self.curve.first_temperature_with(1.5) is None

    def test_never_reached(self) -> None:
        assert self.curve.first_temperature_with(6.0) is None

    def test_an_empty_curve(self) -> None:
        assert CopCurve(points=()).first_temperature_with(3.0) is None


BOILER = "climate.ketel"
AIRCO = "climate.airco"


def zone(**changes) -> Zone:
    """A boiler for the cold and an airco for the mild, as outdoor windows."""
    boiler = Source(
        "ketel",
        BOILER,
        priority=1,
        energy=SourceEnergy.GAS,
        outdoor=OutdoorWindow(None, 3.0),
    )
    airco = Source(
        "airco",
        AIRCO,
        priority=2,
        energy=SourceEnergy.ELECTRIC,
        outdoor=OutdoorWindow(3.0, None),
    )
    return Zone(
        zone_id="z",
        name="Z",
        indoor_sensor="sensor.t",
        sources=(
            replace(boiler, **changes.get("boiler", {})),
            replace(airco, **changes.get("airco", {})),
        ),
    )


def world(outdoor: float, pick: str | None, **kwargs):
    base = make_world(
        outdoor=outdoor, climates={BOILER: climate("off"), AIRCO: climate("off")}, **kwargs
    )
    return replace(base, heat_pick=pick)


class TestSelectWithAPreference:
    def test_without_a_preference_the_window_decides(self) -> None:
        assert sources.select(zone(), ModeFamily.HEAT, world(8.0, None)).entity_id == AIRCO
        assert sources.select(zone(), ModeFamily.HEAT, world(1.0, None)).entity_id == BOILER

    def test_gas_is_picked_in_the_airco_window(self) -> None:
        chosen = sources.select(zone(), ModeFamily.HEAT, world(8.0, "gas"))
        assert chosen is not None and chosen.entity_id == BOILER

    def test_electric_is_picked_in_the_boiler_window(self) -> None:
        chosen = sources.select(zone(), ModeFamily.HEAT, world(1.0, "electric"))
        assert chosen is not None and chosen.entity_id == AIRCO

    def test_the_other_kind_stays_as_a_fallback(self) -> None:
        down = make_world(
            outdoor=8.0, climates={BOILER: climate("off", available=False), AIRCO: climate("off")}
        )
        chosen = sources.select(zone(), ModeFamily.HEAT, replace(down, heat_pick="gas"))
        assert chosen is not None and chosen.entity_id == AIRCO

    def test_a_preference_does_not_touch_cooling(self) -> None:
        chosen = sources.select(zone(), ModeFamily.COOL, world(28.0, "gas"))
        assert chosen is not None and chosen.entity_id == AIRCO

    def test_a_source_without_an_energy_kind_keeps_its_window(self) -> None:
        plain = zone(boiler={"energy": SourceEnergy.NONE})
        # de ketel heeft geen soort: zijn venster geldt nog, dus op 8 graden is hij geen kandidaat
        chosen = sources.select(plain, ModeFamily.HEAT, world(8.0, "gas"))
        assert chosen is not None and chosen.entity_id == AIRCO

    def test_priority_decides_between_equals(self) -> None:
        two_gas = zone(airco={"energy": SourceEnergy.GAS})
        chosen = sources.select(two_gas, ModeFamily.HEAT, world(8.0, "gas"))
        assert chosen is not None and chosen.entity_id == BOILER

    def test_passed_over_agrees_with_the_choice(self) -> None:
        down = make_world(
            outdoor=8.0, climates={BOILER: climate("off", available=False), AIRCO: climate("off")}
        )
        passed = sources.passed_over(zone(), ModeFamily.HEAT, replace(down, heat_pick="gas"))
        assert passed == ("ketel",)
