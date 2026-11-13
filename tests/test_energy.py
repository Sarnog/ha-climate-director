"""Tests voor de energie-instellingen en de kostenvergelijking.

Tests for the energy settings and the cost comparison.
"""

from __future__ import annotations

from dataclasses import asdict, replace

import pytest

from custom_components.climate_director.engine.energy import (
    ELECTRIC,
    GAS,
    EnergySettings,
    heat_costs,
    parse_cop_curve,
)
from custom_components.climate_director.engine.serialise import config_from_dict, config_to_dict
from custom_components.climate_director.flow_validation import settings_errors

FULL = EnergySettings(
    grid_price_sensor="sensor.stroom",
    gas_price=1.8,
    cop_curve="-5:2.8, 7:3.8, 15:4.5",
)


class TestParseCopCurve:
    def test_points_with_commas(self) -> None:
        curve = parse_cop_curve("-5:2.8, 7:3.8, 15:4.5")
        assert curve is not None
        assert curve.points == ((-5.0, 2.8), (7.0, 3.8), (15.0, 4.5))

    def test_semicolons_and_any_order(self) -> None:
        curve = parse_cop_curve("15:4.5;7:3.8")
        assert curve is not None
        assert curve.points == ((7.0, 3.8), (15.0, 4.5))

    def test_a_typographic_minus_reads(self) -> None:
        curve = parse_cop_curve("−5:2.8")
        assert curve is not None
        assert curve.points == ((-5.0, 2.8),)

    def test_trailing_comma_and_blanks_are_fine(self) -> None:
        curve = parse_cop_curve("7:3.8, ,")
        assert curve is not None
        assert curve.points == ((7.0, 3.8),)

    @pytest.mark.parametrize(
        "text",
        ["", "   ", "7", "7:3.8:1", "a:3.8", "7:b", "7:0", "7:-1", "7:3.8, 7:4.0"]
        + ["7:inf", "7:nan", "inf:3.8", "nan:3.8", "-inf:3.8"],
    )
    def test_unreadable_text_gives_none(self, text: str) -> None:
        assert parse_cop_curve(text) is None


class TestSettings:
    def test_a_full_setting_is_configured(self) -> None:
        assert FULL.configured

    @pytest.mark.parametrize(
        "changes",
        [{"gas_price": 0.0}, {"grid_price_sensor": ""}, {"cop_curve": "  "}],
    )
    def test_a_missing_piece_is_not_configured(self, changes: dict) -> None:
        assert not replace(FULL, **changes).configured

    def test_the_default_is_not_configured(self) -> None:
        assert not EnergySettings().configured

    def test_entities_skip_the_empty_ones(self) -> None:
        settings = EnergySettings(grid_price_sensor="sensor.a", surplus_sensor="sensor.c")
        assert settings.entities() == ("sensor.a", "sensor.c")


class TestHeatCosts:
    def test_both_costs_and_the_cheapest(self) -> None:
        costs = heat_costs(FULL, 0.30, None, None, 8.0)
        assert costs.gas == pytest.approx(0.2047, abs=1e-4)
        assert costs.cop == pytest.approx(3.8875)
        assert costs.electric == pytest.approx(0.30 / 3.8875)
        assert costs.electricity_price == 0.30
        assert costs.cheapest == ELECTRIC

    def test_expensive_power_goes_to_gas(self) -> None:
        assert heat_costs(FULL, 0.90, None, None, 8.0).cheapest == GAS

    def test_a_surplus_uses_the_feed_in_price(self) -> None:
        costs = heat_costs(FULL, 0.90, 0.05, 2.0, 8.0)
        assert costs.electricity_price == 0.05
        assert costs.cheapest == ELECTRIC

    def test_a_set_but_unreadable_feed_in_price_during_surplus_is_unknown(self) -> None:
        settings = replace(FULL, feed_in_sensor="sensor.terug")
        costs = heat_costs(settings, 0.30, None, 2.0, 8.0)
        assert costs.electricity_price is None
        assert costs.electric is None
        assert costs.cheapest == GAS

    def test_an_unreadable_feed_in_price_without_surplus_uses_the_grid_price(self) -> None:
        settings = replace(FULL, feed_in_sensor="sensor.terug")
        assert heat_costs(settings, 0.30, None, 0.0, 8.0).electricity_price == 0.30
        assert heat_costs(settings, 0.30, None, None, 8.0).electricity_price == 0.30

    def test_unknown_outdoor_temperature_leaves_gas_alone(self) -> None:
        costs = heat_costs(FULL, 0.30, None, None, None)
        assert costs.electric is None
        assert costs.cheapest == GAS

    def test_an_unreadable_curve_leaves_gas_alone(self) -> None:
        broken = replace(FULL, cop_curve="kapot")
        costs = heat_costs(broken, 0.30, None, None, 8.0)
        assert costs.cop is None
        assert costs.cheapest == GAS

    def test_no_gas_price_leaves_electricity_alone(self) -> None:
        costs = heat_costs(replace(FULL, gas_price=0.0), 0.3, None, None, 8)
        assert costs.gas is None
        assert costs.cheapest == ELECTRIC

    def test_nothing_known_has_no_cheapest(self) -> None:
        costs = heat_costs(EnergySettings(), None, None, None, None)
        assert costs.cheapest is None


class TestStorage:
    def test_round_trip(self) -> None:
        stored = config_to_dict(config_from_dict({"energy": asdict(FULL)}))
        assert stored["energy"] == asdict(FULL)
        assert config_from_dict(stored).energy == FULL

    def test_missing_or_broken_storage_gives_the_defaults(self) -> None:
        assert config_from_dict({}).energy == EnergySettings()
        assert config_from_dict({"energy": "kapot"}).energy == EnergySettings()
        assert config_from_dict({"energy": {"gas_price": "veel"}}).energy == EnergySettings()


class TestSettingsScreen:
    def test_a_readable_curve_passes(self) -> None:
        assert settings_errors({"cop_curve": "-5:2.8, 7:3.8"}) == {}

    def test_an_empty_curve_passes(self) -> None:
        assert settings_errors({"cop_curve": ""}) == {}
        assert settings_errors({}) == {}

    def test_an_unreadable_curve_is_refused(self) -> None:
        assert settings_errors({"cop_curve": "kapot"}) == {"cop_curve": "cop_curve_invalid"}
