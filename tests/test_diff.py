"""Tests voor het verschil tussen plan en werkelijkheid.

Tests for the difference between the plan and reality.
"""

from __future__ import annotations

from conftest import ATTIC, BEDROOM, GAS, LIVING, climate, everyone_up, house, make_world

from custom_components.climate_director.engine import (
    MODE_COOL,
    MODE_HEAT,
    MODE_OFF,
    Plan,
    Season,
    UnitCommand,
    decide,
)
from custom_components.climate_director.engine.diff import TEMPERATURE_TOLERANCE, changes


def world(**modes: str):
    """Return a world where each named entity sits in the given mode."""
    return make_world(
        outdoor=10.0,
        season=Season.WINTER,
        indoor={"woonkamer": 20.0, "zolder": 23.0, "slaapkamer": 23.0},
        climates={entity_id: climate(mode) for entity_id, mode in modes.items()},
        residents=everyone_up(),
    )


def plan_of(*commands: UnitCommand) -> Plan:
    return Plan(commands=tuple(commands))


class TestNothingToDo:
    def test_a_matching_state_produces_no_change(self) -> None:
        current = make_world(
            climates={LIVING: climate(MODE_HEAT, target=23.0)},
        )
        plan = plan_of(UnitCommand(LIVING, MODE_HEAT, 23.0))
        assert changes(plan, current) == ()

    def test_a_setpoint_within_tolerance_counts_as_equal(self) -> None:
        current = make_world(
            climates={LIVING: climate(MODE_HEAT, target=23.0 + TEMPERATURE_TOLERANCE / 2)}
        )
        plan = plan_of(UnitCommand(LIVING, MODE_HEAT, 23.0))
        assert changes(plan, current) == ()

    def test_just_inside_the_tolerance_is_equal_and_just_outside_is_not(self) -> None:
        """De grens van de tolerantie, van beide kanten.

        Precies óp de tolerantie wordt hier niet vastgelegd, en dat is met opzet:
        bij kamertemperaturen bestaat dat geval niet. `23,05 - 23,0` is in
        drijvende komma 0,050000000000000710 en dus nooit gelijk aan 0,05. Het
        verschil tussen `<` en `<=` op deze regel is daarmee niet waar te nemen;
        wat wél telt is dat de ene kant gelijk heet en de andere niet.

        The tolerance boundary, from both sides. Exactly on the tolerance is
        deliberately not pinned: at room temperatures that case does not exist.
        In floating point `23.05 - 23.0` is 0.050000000000000710 and therefore
        never equal to 0.05. The difference between `<` and `<=` on that line is
        thus unobservable; what does count is that one side reads as equal and
        the other does not.
        """
        near = make_world(
            climates={LIVING: climate(MODE_HEAT, target=23.0 + TEMPERATURE_TOLERANCE * 0.9)}
        )
        far = make_world(
            climates={LIVING: climate(MODE_HEAT, target=23.0 + TEMPERATURE_TOLERANCE * 1.1)}
        )
        plan = plan_of(UnitCommand(LIVING, MODE_HEAT, 23.0))

        assert changes(plan, near) == ()
        assert changes(plan, far) != ()

    def test_the_tolerance_counts_in_both_directions(self) -> None:
        """Een graad te laag is net zo goed een verschil als een graad te hoog."""
        colder = make_world(climates={LIVING: climate(MODE_HEAT, target=22.0)})
        plan = plan_of(UnitCommand(LIVING, MODE_HEAT, 23.0))
        assert changes(plan, colder) != ()

    def test_an_already_off_unit_is_left_alone(self) -> None:
        current = make_world(climates={GAS: climate(MODE_OFF)})
        assert changes(plan_of(UnitCommand(GAS, MODE_OFF)), current) == ()


class TestSomethingToDo:
    def test_a_different_mode_is_a_change(self) -> None:
        current = make_world(climates={LIVING: climate(MODE_OFF)})
        result = changes(plan_of(UnitCommand(LIVING, MODE_HEAT, 23.0)), current)
        assert len(result) == 1
        assert result[0].set_mode
        assert result[0].set_temperature

    def test_only_the_setpoint_differing_is_a_change(self) -> None:
        current = make_world(climates={LIVING: climate(MODE_HEAT, target=20.0)})
        result = changes(plan_of(UnitCommand(LIVING, MODE_HEAT, 23.0)), current)
        assert len(result) == 1
        assert not result[0].set_mode
        assert result[0].set_temperature

    def test_an_unknown_current_setpoint_counts_as_different(self) -> None:
        current = make_world(climates={LIVING: climate(MODE_HEAT, target=None)})
        result = changes(plan_of(UnitCommand(LIVING, MODE_HEAT, 23.0)), current)
        assert result[0].set_temperature

    def test_an_unknown_current_setpoint_is_sent_once(self) -> None:
        """Zonder meting tegenover het setpoint: één keer sturen, dan zwijgen.

        With no measurement to hold against the setpoint: send it once, then
        stay quiet.
        """
        current = make_world(climates={LIVING: climate(MODE_HEAT, target=None)})
        plan = plan_of(UnitCommand(LIVING, MODE_HEAT, 23.0))
        first = changes(plan, current)
        assert first[0].set_temperature
        assert changes(plan, current, previous=plan) == ()

    def test_a_changed_setpoint_is_sent_again_despite_the_missing_reading(self) -> None:
        current = make_world(climates={LIVING: climate(MODE_HEAT, target=None)})
        previous = plan_of(UnitCommand(LIVING, MODE_HEAT, 23.0))
        result = changes(plan_of(UnitCommand(LIVING, MODE_HEAT, 22.0)), current, previous=previous)
        assert result[0].set_temperature


class TestSwitchingOff:
    def test_switching_off_never_pushes_a_setpoint(self) -> None:
        """A unit going off keeps its setpoint; sending one changes nothing visible."""
        current = make_world(climates={LIVING: climate(MODE_HEAT, target=20.0)})
        result = changes(plan_of(UnitCommand(LIVING, MODE_OFF, 23.0)), current)
        assert len(result) == 1
        assert result[0].set_mode
        assert not result[0].set_temperature


class TestUnavailable:
    def test_an_unavailable_entity_is_skipped(self) -> None:
        current = make_world(climates={LIVING: climate(MODE_OFF, available=False)})
        assert changes(plan_of(UnitCommand(LIVING, MODE_HEAT, 23.0)), current) == ()

    def test_an_unknown_entity_is_skipped(self) -> None:
        assert changes(plan_of(UnitCommand(LIVING, MODE_HEAT, 23.0)), make_world()) == ()


class TestAgainstTheRealEngine:
    def test_a_settled_installation_needs_no_calls(self) -> None:
        """Deciding again without anything moving must be free."""
        current = make_world(
            outdoor=10.0,
            season=Season.WINTER,
            indoor={"woonkamer": 20.5, "zolder": 23.0, "slaapkamer": 23.0},
            climates={
                GAS: climate(MODE_OFF),
                LIVING: climate(MODE_HEAT, target=23.0),
                ATTIC: climate(MODE_OFF),
                BEDROOM: climate(MODE_OFF),
            },
            residents=everyone_up(),
        )
        assert changes(decide(house(), current), current) == ()

    def test_a_cold_start_needs_exactly_one_call(self) -> None:
        current = world(**{GAS: MODE_OFF, LIVING: MODE_OFF, ATTIC: MODE_OFF, BEDROOM: MODE_OFF})
        result = changes(decide(house(), current), current)
        assert [change.entity_id for change in result] == [LIVING]

    def test_a_handover_stops_before_it_starts(self) -> None:
        """The boiler must be told to stop ahead of the heat pump starting."""
        current = make_world(
            outdoor=10.0,
            season=Season.WINTER,
            indoor={"woonkamer": 20.0, "zolder": 23.0, "slaapkamer": 23.0},
            climates={
                GAS: climate(MODE_HEAT, target=23.0),
                LIVING: climate(MODE_OFF),
                ATTIC: climate(MODE_OFF),
                BEDROOM: climate(MODE_OFF),
            },
            residents=everyone_up(),
        )
        result = changes(decide(house(), current), current)
        assert [change.entity_id for change in result] == [GAS, LIVING]
        assert result[0].command.hvac_mode == MODE_OFF
        assert result[1].command.hvac_mode == MODE_HEAT

    def test_cooling_is_reached_the_same_way(self) -> None:
        current = make_world(
            outdoor=28.0,
            season=Season.SUMMER,
            indoor={"woonkamer": 26.0, "zolder": 23.0, "slaapkamer": 23.0},
            climates={
                GAS: climate(MODE_OFF),
                LIVING: climate(MODE_OFF),
                ATTIC: climate(MODE_OFF),
                BEDROOM: climate(MODE_OFF),
            },
            residents=everyone_up(),
        )
        result = changes(decide(house(), current), current)
        assert [change.command.hvac_mode for change in result] == [MODE_COOL]
