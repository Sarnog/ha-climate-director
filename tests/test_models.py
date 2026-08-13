"""Tests voor het configuratiemodel: vensters, tijdvensters en validatie.

Tests for the configuration model: windows, time windows and validation.
"""

from __future__ import annotations

from datetime import time

import pytest
from conftest import GAS, LIVING, house

from custom_components.climate_director.engine import (
    Circuit,
    DirectorConfig,
    ModeSettings,
    OutdoorWindow,
    Resident,
    Season,
    Source,
    SourceRole,
    TimeWindow,
    Zone,
    validate,
)
from custom_components.climate_director.engine.families import ModeFamily


class TestOutdoorWindow:
    def test_unbounded_accepts_everything_including_unknown(self) -> None:
        window = OutdoorWindow()
        assert window.contains(-40.0)
        assert window.contains(50.0)
        assert window.contains(None)

    def test_bounded_window_rejects_unknown_temperature(self) -> None:
        """A bound that cannot be checked is not met."""
        assert not OutdoorWindow(minimum=3.0).contains(None)

    def test_half_open_boundaries(self) -> None:
        """`[minimum, maximum)`: the minimum is inside, the maximum is not."""
        window = OutdoorWindow(minimum=3.0, maximum=19.0)
        assert window.contains(3.0)
        assert not window.contains(19.0)
        assert not window.contains(2.9)
        assert window.contains(18.9)

    def test_adjacent_windows_leave_no_gap_and_no_overlap(self) -> None:
        """This is what keeps a boiler and a heat pump from both qualifying."""
        boiler = OutdoorWindow(maximum=3.0)
        heat_pump = OutdoorWindow(minimum=3.0)
        for tenth in range(-100, 101):
            outdoor = tenth / 10
            assert boiler.contains(outdoor) != heat_pump.contains(outdoor)


class TestTimeWindow:
    def test_plain_window(self) -> None:
        window = TimeWindow(time(8, 0), time(18, 0))
        assert window.contains(time(8, 0), 0)
        assert window.contains(time(17, 59), 0)
        assert not window.contains(time(18, 0), 0)
        assert not window.contains(time(7, 59), 0)

    def test_weekday_restriction(self) -> None:
        window = TimeWindow(time(8, 0), time(18, 0), frozenset({5, 6}))
        assert window.contains(time(12, 0), 5)
        assert not window.contains(time(12, 0), 0)

    def test_window_through_midnight(self) -> None:
        window = TimeWindow(time(22, 0), time(2, 0))
        assert window.contains(time(23, 0), 0)
        assert window.contains(time(1, 0), 1)
        assert not window.contains(time(3, 0), 1)

    def test_window_through_midnight_is_anchored_on_its_start_day(self) -> None:
        """A Friday 22:00-02:00 window still counts at 01:00 on Saturday."""
        window = TimeWindow(time(22, 0), time(2, 0), frozenset({4}))
        assert window.contains(time(23, 0), 4)
        assert window.contains(time(1, 0), 5)
        assert not window.contains(time(23, 0), 5)


class TestResident:
    def test_no_windows_means_always(self) -> None:
        assert Resident("danny").wants_climate_at(time(3, 0), 6)

    def test_any_matching_window_is_enough(self) -> None:
        resident = Resident(
            "danny",
            windows=(
                TimeWindow(time(6, 0), time(9, 0)),
                TimeWindow(time(17, 0), time(23, 0)),
            ),
        )
        assert resident.wants_climate_at(time(7, 0), 0)
        assert resident.wants_climate_at(time(18, 0), 0)
        assert not resident.wants_climate_at(time(12, 0), 0)


class TestSourceRoles:
    @pytest.mark.parametrize(
        ("role", "heat", "cool"),
        [
            (SourceRole.HEAT_ONLY, True, False),
            (SourceRole.COOL_ONLY, False, True),
            (SourceRole.HEAT_COOL, True, True),
        ],
    )
    def test_supports(self, role: SourceRole, heat: bool, cool: bool) -> None:
        source = Source("s", "climate.x", role=role)
        assert source.supports(ModeFamily.HEAT) is heat
        assert source.supports(ModeFamily.COOL) is cool

    def test_no_source_supports_a_neutral_duty(self) -> None:
        source = Source("s", "climate.x")
        assert not source.supports(ModeFamily.NEUTRAL)
        assert not source.supports(ModeFamily.AMBIGUOUS)


class TestModeSettings:
    def test_seasons_none_means_every_season(self) -> None:
        settings = ModeSettings(target=21.0, start_at=21.0)
        assert all(settings.allowed_in(season) for season in Season)

    def test_seasons_restrict(self) -> None:
        settings = ModeSettings(21.0, 21.0, seasons=frozenset({Season.SUMMER}))
        assert settings.allowed_in(Season.SUMMER)
        assert not settings.allowed_in(Season.WINTER)


class TestLookups:
    def test_circuit_for_entity(self) -> None:
        config = house()
        assert config.circuit_for_entity(LIVING) is not None
        assert config.circuit_for_entity(GAS) is None

    def test_sources_on_circuit_skips_the_boiler(self) -> None:
        config = house()
        circuit = config.circuit("multisplit")
        assert circuit is not None
        entities = {source.entity_id for _, source in config.sources_on(circuit)}
        assert GAS not in entities
        assert LIVING in entities

    def test_source_and_zone_lookup(self) -> None:
        config = house()
        assert config.zone("woonkamer") is not None
        assert config.zone("kelder") is None
        assert config.source("gasketel") is not None
        assert config.source("onbekend") is None


class TestValidate:
    def test_sound_configuration_has_no_problems(self) -> None:
        assert validate(house()) == ()

    def test_duplicate_zone_id(self) -> None:
        zone = Zone("z", "Z", "sensor.t", sources=(Source("s", "climate.x"),))
        problems = validate(DirectorConfig(zones=(zone, zone)))
        assert any("duplicate zone id" in problem for problem in problems)

    def test_unit_on_two_circuits(self) -> None:
        config = DirectorConfig(
            circuits=(
                Circuit("a", "A", units=("climate.x",)),
                Circuit("b", "B", units=("climate.x",)),
            )
        )
        assert any("sits on both circuit" in problem for problem in validate(config))

    def test_entity_used_by_two_sources(self) -> None:
        config = DirectorConfig(
            zones=(
                Zone("a", "A", "sensor.a", sources=(Source("s1", "climate.x"),)),
                Zone("b", "B", "sensor.b", sources=(Source("s2", "climate.x"),)),
            )
        )
        assert any("more than one source" in problem for problem in validate(config))

    def test_zone_without_sources(self) -> None:
        config = DirectorConfig(zones=(Zone("a", "A", "sensor.a"),))
        assert any("has no sources" in problem for problem in validate(config))

    def test_zone_wants_a_duty_no_source_can_deliver(self) -> None:
        config = DirectorConfig(
            zones=(
                Zone(
                    "a",
                    "A",
                    "sensor.a",
                    sources=(Source("s", "climate.x", role=SourceRole.HEAT_ONLY),),
                    cool=ModeSettings(21.0, 24.0),
                ),
            )
        )
        assert any("no source for it" in problem for problem in validate(config))

    def test_negative_hysteresis(self) -> None:
        config = DirectorConfig(
            zones=(
                Zone(
                    "a",
                    "A",
                    "sensor.a",
                    sources=(Source("s", "climate.x"),),
                    heat=ModeSettings(21.0, 21.0, hysteresis=-1.0),
                ),
            )
        )
        assert any("negative heat hysteresis" in problem for problem in validate(config))

    def test_outdoor_window_that_admits_nothing(self) -> None:
        config = DirectorConfig(
            zones=(
                Zone(
                    "a",
                    "A",
                    "sensor.a",
                    sources=(Source("s", "climate.x", outdoor=OutdoorWindow(10.0, 5.0)),),
                    heat=ModeSettings(21.0, 20.0, outdoor=OutdoorWindow(8.0, 8.0)),
                ),
            )
        )
        problems = validate(config)
        assert any("source s has an outdoor window" in problem for problem in problems)
        assert any("heat outdoor window" in problem for problem in problems)

    def test_exclusive_group_naming_an_unknown_source(self) -> None:
        config = DirectorConfig(exclusive_groups=(frozenset({"ghost"}),))
        assert any("unknown source ghost" in problem for problem in validate(config))
