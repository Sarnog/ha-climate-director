"""Tests voor het kostenrekenwerk (gas tegenover elektrisch).

Tests for the cost arithmetic (gas against electric).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.climate_director.engine.cost import (
    CopCurve,
    PricePoint,
    cheapest,
    electric_cost,
    gas_cost,
    surplus_price,
    window_average,
)

START = datetime(2026, 11, 12, 16, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)


def hourly(*values: float) -> list[PricePoint]:
    """Consecutive hourly prices from START."""
    return [
        PricePoint(START + index * HOUR, START + (index + 1) * HOUR, value)
        for index, value in enumerate(values)
    ]


class TestCopCurve:
    curve = CopCurve(points=((-5.0, 2.0), (7.0, 4.0), (15.0, 5.0)))

    def test_exact_point(self) -> None:
        assert self.curve.cop_at(7.0) == 4.0

    def test_between_two_points_is_linear(self) -> None:
        assert self.curve.cop_at(1.0) == pytest.approx(3.0)
        assert self.curve.cop_at(11.0) == pytest.approx(4.5)

    def test_flat_below_the_first_point(self) -> None:
        assert self.curve.cop_at(-30.0) == 2.0

    def test_flat_above_the_last_point(self) -> None:
        assert self.curve.cop_at(40.0) == 5.0

    def test_points_in_any_order(self) -> None:
        shuffled = CopCurve(points=((15.0, 5.0), (-5.0, 2.0), (7.0, 4.0)))
        assert shuffled.cop_at(1.0) == pytest.approx(3.0)

    def test_unknown_outdoor_temperature(self) -> None:
        assert self.curve.cop_at(None) is None

    def test_empty_curve(self) -> None:
        assert CopCurve(points=()).cop_at(5.0) is None

    def test_points_without_a_positive_cop_are_ignored(self) -> None:
        curve = CopCurve(points=((-5.0, 0.0), (7.0, 4.0)))
        assert curve.cop_at(-20.0) == 4.0

    def test_only_unusable_points(self) -> None:
        assert CopCurve(points=((0.0, 0.0), (5.0, -1.0))).cop_at(2.0) is None


class TestGasCost:
    def test_cost_of_a_kwh_of_heat(self) -> None:
        # 1,80 per m3 bij 9,77 kWh/m3 en rendement 0,9
        assert gas_cost(1.80, 9.77, 0.9) == pytest.approx(0.2047, abs=1e-4)

    def test_free_gas_is_a_price(self) -> None:
        assert gas_cost(0.0, 9.77, 0.9) == 0.0

    @pytest.mark.parametrize(
        ("price", "kwh", "efficiency"),
        [
            (None, 9.77, 0.9),
            (-0.1, 9.77, 0.9),
            (1.8, 0.0, 0.9),
            (1.8, -1.0, 0.9),
            (1.8, 9.77, 0.0),
            (1.8, 9.77, -0.5),
            (1.8, 9.77, 1.21),
        ],
    )
    def test_unusable_input(self, price, kwh, efficiency) -> None:
        assert gas_cost(price, kwh, efficiency) is None

    def test_the_upper_efficiency_bound_is_usable(self) -> None:
        assert gas_cost(1.8, 9.77, 1.2) is not None


class TestElectricCost:
    def test_price_over_cop(self) -> None:
        assert electric_cost(0.30, 3.0) == pytest.approx(0.10)

    @pytest.mark.parametrize(
        ("price", "cop"),
        [(None, 3.0), (0.3, None), (0.3, 0.0), (0.3, -1.0)],
    )
    def test_unusable_input(self, price, cop) -> None:
        assert electric_cost(price, cop) is None

    def test_a_negative_price_is_usable(self) -> None:
        assert electric_cost(-0.05, 3.0) == pytest.approx(-0.05 / 3.0)


class TestSurplusPrice:
    def test_surplus_costs_the_feed_in_price(self) -> None:
        assert surplus_price(0.30, 0.05, 1.2) == 0.05

    def test_no_surplus_costs_the_grid_price(self) -> None:
        assert surplus_price(0.30, 0.05, 0.0) == 0.30
        assert surplus_price(0.30, 0.05, -0.4) == 0.30

    def test_unknown_surplus_counts_as_none(self) -> None:
        assert surplus_price(0.30, 0.05, None) == 0.30

    def test_surplus_without_a_feed_in_price_uses_the_grid_price(self) -> None:
        assert surplus_price(0.30, None, 2.0) == 0.30

    def test_nothing_known(self) -> None:
        assert surplus_price(None, None, None) is None


class TestWindowAverage:
    def test_one_price_over_the_whole_window(self) -> None:
        assert window_average(hourly(0.2), START, HOUR) == pytest.approx(0.2)

    def test_time_weighted_over_several_hours(self) -> None:
        assert window_average(hourly(0.1, 0.3), START, 2 * HOUR) == pytest.approx(0.2)

    def test_window_starting_inside_a_price(self) -> None:
        prices = hourly(0.1, 0.3)
        # Een kwartier uit uur 1 (0,1) en drie kwartier uit uur 2 (0,3).
        average = window_average(prices, START + timedelta(minutes=45), HOUR)
        assert average == pytest.approx(0.25 * 0.1 + 0.75 * 0.3)

    def test_prices_outside_the_window_are_ignored(self) -> None:
        assert window_average(hourly(9.0, 0.2, 9.0), START + HOUR, HOUR) == pytest.approx(0.2)

    def test_a_gap_in_the_list_gives_none(self) -> None:
        prices = [hourly(0.1)[0], hourly(0.1, 0.1, 0.3)[2]]
        assert window_average(prices, START, 3 * HOUR) is None

    def test_list_ending_early_gives_none(self) -> None:
        assert window_average(hourly(0.1), START, 2 * HOUR) is None

    def test_empty_list(self) -> None:
        assert window_average([], START, HOUR) is None

    @pytest.mark.parametrize("horizon", [timedelta(0), timedelta(hours=-1)])
    def test_no_window(self, horizon) -> None:
        assert window_average(hourly(0.2), START, horizon) is None


class TestCheapest:
    def test_lowest_cost_wins(self) -> None:
        assert cheapest({"gas": 0.20, "airco": 0.10}) == "airco"

    def test_nothing_known(self) -> None:
        assert cheapest({}) is None
        assert cheapest({"gas": None, "airco": None}) is None

    def test_unknown_costs_are_skipped(self) -> None:
        assert cheapest({"gas": None, "airco": 0.3}) == "airco"

    def test_equal_cost_goes_to_the_smallest_id(self) -> None:
        assert cheapest({"b": 0.1, "a": 0.1}) == "a"

    def test_holding_source_stays_within_the_margin(self) -> None:
        # airco is 10% goedkoper, de marge is 15%: gas houdt de keus.
        assert cheapest({"gas": 0.20, "airco": 0.18}, holding="gas", margin=0.15) == "gas"

    def test_holding_source_loses_beyond_the_margin(self) -> None:
        assert cheapest({"gas": 0.20, "airco": 0.10}, holding="gas", margin=0.15) == "airco"

    def test_exactly_at_the_margin_the_new_source_wins(self) -> None:
        assert cheapest({"gas": 1.0, "airco": 0.75}, holding="gas", margin=0.25) == "airco"

    def test_without_a_margin_the_holder_keeps_a_tie_only(self) -> None:
        assert cheapest({"gas": 0.2, "airco": 0.2}, holding="gas") == "gas"
        assert cheapest({"gas": 0.2, "airco": 0.19}, holding="gas") == "airco"

    def test_holding_source_with_unknown_cost_is_not_kept(self) -> None:
        assert cheapest({"gas": None, "airco": 0.3}, holding="gas", margin=0.5) == "airco"

    def test_holding_source_not_in_the_list(self) -> None:
        assert cheapest({"airco": 0.3}, holding="gas", margin=0.5) == "airco"

    def test_holder_is_also_the_cheapest(self) -> None:
        assert cheapest({"gas": 0.1, "airco": 0.2}, holding="gas", margin=0.15) == "gas"
