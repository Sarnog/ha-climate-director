"""Tests voor de pure helpers uit de Home Assistant-laag.

Tests for the pure helpers in the Home Assistant layer.

Deze tests draaien tegen een gewone `homeassistant`-installatie (voor imports en
om echte API-signaturen te kunnen verifieren), maar niet tegen een draaiende
`hass`. Zie `tests/README.md` voor wat dat wel en niet dekt.

These tests run against a plain `homeassistant` installation (for imports and to
be able to verify real API signatures), but not against a running `hass`. See
`tests/README.md` for what that does and does not cover.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from conftest import house

from custom_components.climate_director.applier import _is_stop
from custom_components.climate_director.config_flow import (
    ClimateDirectorOptionsFlow,
    _all_source_ids,
    _deep_copy,
    _unique_id,
    _window_label,
    _zone_from_form,
)
from custom_components.climate_director.coordinator import (
    _as_float,
    _event_data,
    season_from_state,
    temperature_from_state,
)
from custom_components.climate_director.engine import (
    MODE_COOL,
    MODE_FAN_ONLY,
    MODE_HEAT,
    MODE_OFF,
    DirectorConfig,
    Plan,
    Reason,
    Season,
    UnitCommand,
    ZoneDecision,
    decide,
    gates,
)
from custom_components.climate_director.engine.diff import Change
from custom_components.climate_director.engine.serialise import config_from_dict, config_to_dict
from custom_components.climate_director.number import resolve_initial
from custom_components.climate_director.problems import MAX_LISTED, summarise


class TestSeasonFromState:
    @pytest.mark.parametrize(
        ("raw", "season"),
        [
            ("summer", Season.SUMMER),
            ("Zomer", Season.SUMMER),
            ("  ZOMER  ", Season.SUMMER),
            ("winter", Season.WINTER),
            ("Winter", Season.WINTER),
        ],
    )
    def test_recognised_names(self, raw: str, season: Season) -> None:
        assert season_from_state(raw) is season

    @pytest.mark.parametrize("raw", ["spring", "autumn", "fall", "herfst", "lente"])
    def test_shoulder_seasons_count_as_winter(self, raw: str) -> None:
        """Reading them as "no season" would silently disable cooling half the year."""
        assert season_from_state(raw) is Season.WINTER

    @pytest.mark.parametrize("raw", ["Sommer", "été", "Ete", "verano", "صيف", "الصيف"])
    def test_summer_in_every_offered_language(self, raw: str) -> None:
        """A season helper reports in the user's own language, not in English."""
        assert season_from_state(raw) is Season.SUMMER

    @pytest.mark.parametrize(
        "raw", ["Winter", "hiver", "invierno", "شتاء", "Herbst", "automne", "otoño"]
    )
    def test_winter_and_its_shoulders_in_every_offered_language(self, raw: str) -> None:
        assert season_from_state(raw) is Season.WINTER

    @pytest.mark.parametrize("raw", [None, "", "unavailable", "banaan"])
    def test_anything_else_is_unknown(self, raw: str | None) -> None:
        assert season_from_state(raw) is Season.UNKNOWN


class TestTemperatureFromState:
    def test_a_plain_sensor_reads_its_state(self) -> None:
        assert temperature_from_state("sensor.woonkamer", "21.4", {}) == 21.4

    def test_a_climate_entity_reads_its_measurement(self) -> None:
        """Its own state is the hvac mode, so the measurement is an attribute."""
        attributes = {"current_temperature": 21.4, "temperature": 23.0}
        assert temperature_from_state("climate.huiskamer", "heat", attributes) == 21.4

    def test_a_climate_setpoint_is_never_mistaken_for_the_room(self) -> None:
        """Reading the setpoint would make every zone think it had arrived."""
        assert temperature_from_state("climate.huiskamer", "heat", {"temperature": 23.0}) is None

    def test_a_weather_entity_reads_its_temperature_attribute(self) -> None:
        """Its state is the forecast condition, not a number."""
        assert temperature_from_state("weather.buienradar", "cloudy", {"temperature": 8.5}) == 8.5

    def test_an_unavailable_sensor_reports_nothing(self) -> None:
        assert temperature_from_state("sensor.woonkamer", "unavailable", {}) is None

    def test_an_entity_reporting_nothing_usable(self) -> None:
        assert temperature_from_state("sensor.woonkamer", "unknown", {}) is None


class TestAsFloat:
    @pytest.mark.parametrize(("raw", "expected"), [("21.5", 21.5), (3, 3.0), (2.5, 2.5)])
    def test_numbers(self, raw: object, expected: float) -> None:
        assert _as_float(raw) == expected

    @pytest.mark.parametrize("raw", [None, "unavailable", "unknown", "", "heat"])
    def test_non_numbers(self, raw: object) -> None:
        assert _as_float(raw) is None


class TestEventData:
    def test_it_carries_the_zone_the_reason_and_the_command(self) -> None:
        config = house()
        plan = decide(config, _warm_world())
        decision = plan.decision_for("woonkamer")
        assert decision is not None

        data = _event_data(config, plan, decision)
        assert data["zone_id"] == "woonkamer"
        assert data["zone_name"] == "Woonkamer"
        assert data["reason"] == decision.reason.value
        assert data["hvac_mode"] == "heat"
        assert data["temperature"] == 23.0

    def test_a_zone_without_a_command_still_produces_an_event(self) -> None:
        config = house()
        decision = ZoneDecision("woonkamer", Season.UNKNOWN, Season.UNKNOWN)  # type: ignore[arg-type]
        data = _event_data(config, Plan(), decision)
        assert data["entity_id"] is None
        assert data["hvac_mode"] is None

    def test_an_unknown_zone_falls_back_on_its_id(self) -> None:
        decision = ZoneDecision("kelder", Season.UNKNOWN, Season.UNKNOWN)  # type: ignore[arg-type]
        data = _event_data(house(), Plan(), decision)
        assert data["zone_name"] == "kelder"


def _warm_world():
    from conftest import climate, everyone_up, make_world

    from custom_components.climate_director.engine import MODE_OFF

    return make_world(
        outdoor=10.0,
        season=Season.WINTER,
        indoor={"woonkamer": 20.0, "zolder": 23.0, "slaapkamer": 23.0},
        climates={
            "climate.smart_thermostat_x": climate(MODE_OFF),
            "climate.huiskamer": climate(MODE_OFF),
            "climate.zolder": climate(MODE_OFF),
            "climate.master_bedroom": climate(MODE_OFF),
        },
        residents=everyone_up(),
    )


class TestUniqueId:
    def test_a_free_slug_is_used_as_is(self) -> None:
        assert _unique_id("Woonkamer", []) == "woonkamer"

    def test_a_taken_slug_gets_a_suffix(self) -> None:
        assert _unique_id("Woonkamer", ["woonkamer"]) == "woonkamer_2"

    def test_it_keeps_counting(self) -> None:
        assert _unique_id("Woonkamer", ["woonkamer", "woonkamer_2"]) == "woonkamer_3"

    def test_punctuation_only_gets_home_assistants_own_fallback(self) -> None:
        assert _unique_id("!!!", []) == "unknown"

    def test_an_empty_name_still_gets_an_id(self) -> None:
        """`slugify("")` really does return an empty string, unlike `slugify("!!!")`."""
        assert _unique_id("", []) == "item"


class TestWindowLabel:
    def test_a_window_without_days_reads_as_every_day(self) -> None:
        assert _window_label({"start": "08:00:00", "end": "18:00:00"}) == "08:00 - 18:00, every day"

    def test_an_empty_day_list_also_reads_as_every_day(self) -> None:
        """No days ticked means every day, not never."""
        label = _window_label({"start": "08:00:00", "end": "18:00:00", "weekdays": []})
        assert label == "08:00 - 18:00, every day"

    def test_days_are_named_and_sorted(self) -> None:
        window = {"start": "06:30:00", "end": "12:00:00", "weekdays": [4, 2]}
        assert _window_label(window) == "06:30 - 12:00, Wed, Fri"

    def test_nonsense_days_do_not_produce_a_dangling_comma(self) -> None:
        window = {"start": "08:00", "end": "18:00", "weekdays": [99, "maandag"]}
        assert _window_label(window) == "08:00 - 18:00, every day"


class TestScheduleWindowsReachTheEngine:
    """The form's output has to survive storage and land in the gate."""

    def _config(self, weekdays: list[int] | None) -> DirectorConfig:
        stored = {
            "residents": [
                {
                    "resident_id": "danny",
                    "presence_entity": "person.danny",
                    "windows": [{"start": "08:00:00", "end": "18:00:00", "weekdays": weekdays}],
                }
            ],
            "zones": [
                {
                    "zone_id": "z",
                    "indoor_sensor": "sensor.t",
                    "sources": [{"source_id": "s", "entity_id": "climate.x"}],
                    "heat": {"target": 21.0, "start_at": 20.0, "hysteresis": 1.0},
                }
            ],
            "gates": {"require_occupancy": True, "require_awake": False, "require_schedule": True},
        }
        return config_from_dict(stored)

    def _verdict(self, config: DirectorConfig, moment: datetime):
        from conftest import awake, make_world

        zone = config.zone("z")
        assert zone is not None
        world = make_world(now=moment, residents={"danny": awake()})
        return gates.evaluate(config, world, zone)

    def test_inside_the_window(self) -> None:
        config = self._config([0, 1, 2, 3, 4])
        assert self._verdict(config, datetime(2026, 8, 10, 9, 0)).allowed

    def test_outside_the_hours(self) -> None:
        config = self._config([0, 1, 2, 3, 4])
        verdict = self._verdict(config, datetime(2026, 8, 10, 19, 0))
        assert verdict.reason is Reason.OUTSIDE_SCHEDULE

    def test_outside_the_days(self) -> None:
        """The 15th of August 2026 is a Saturday."""
        config = self._config([0, 1, 2, 3, 4])
        verdict = self._verdict(config, datetime(2026, 8, 15, 9, 0))
        assert verdict.reason is Reason.OUTSIDE_SCHEDULE

    def test_no_days_means_every_day(self) -> None:
        config = self._config(None)
        assert self._verdict(config, datetime(2026, 8, 15, 9, 0)).allowed


class TestPriorityAfterRestart:
    """What a restart or a reload should start the priority entity from."""

    def test_a_fresh_entity_takes_the_configured_value(self) -> None:
        assert resolve_initial(configured=0, last_value=None, last_configured=None) == 0

    def test_a_restored_value_survives_a_restart(self) -> None:
        """Losing what an automation set on every restart would make it pointless."""
        assert resolve_initial(configured=0, last_value=7, last_configured=0) == 7

    def test_an_edited_configuration_wins_over_the_restored_value(self) -> None:
        """The options flow is the newer statement of intent."""
        assert resolve_initial(configured=3, last_value=7, last_configured=0) == 3

    def test_a_restored_value_without_its_origin_is_not_trusted(self) -> None:
        assert resolve_initial(configured=2, last_value=7, last_configured=None) == 2


class TestProblemSummary:
    def test_a_short_list_is_shown_in_full(self) -> None:
        summary = summarise(("first", "second"))
        assert summary == "- first\n- second"
        assert "more" not in summary

    def test_exactly_the_cap_needs_no_tail(self) -> None:
        summary = summarise(tuple(f"problem {index}" for index in range(MAX_LISTED)))
        assert summary.count("\n") == MAX_LISTED - 1
        assert "more" not in summary

    def test_one_over_the_cap_counts_the_remainder(self) -> None:
        summary = summarise(tuple(f"problem {index}" for index in range(MAX_LISTED + 1)))
        assert summary.endswith("- ... and 1 more")

    def test_a_long_list_counts_correctly(self) -> None:
        summary = summarise(tuple(f"problem {index}" for index in range(MAX_LISTED + 7)))
        assert summary.endswith("- ... and 7 more")

    def test_nothing_wrong_produces_nothing(self) -> None:
        assert summarise(()) == ""


class TestDeepCopy:
    def test_nested_structures_are_detached(self) -> None:
        original = {"zones": [{"sources": [{"entity_id": "climate.x"}]}]}
        copy = _deep_copy(original)
        copy["zones"][0]["sources"][0]["entity_id"] = "climate.y"
        assert original["zones"][0]["sources"][0]["entity_id"] == "climate.x"

    def test_scalars_pass_through(self) -> None:
        assert _deep_copy(("a", 1, None)) == ("a", 1, None)


class TestZoneFromForm:
    form = {
        "name": "Woonkamer",
        "indoor_sensor": "sensor.woonkamer",
        "priority": 0,
        "enable_heat": True,
        "heat_target": 23.0,
        "heat_start_at": 22.0,
        "heat_hysteresis": 1.0,
        "heat_outdoor_max": 19.0,
        "enable_cool": True,
        "cool_target": 23.0,
        "cool_start_at": 24.0,
        "cool_hysteresis": 1.0,
        "cool_outdoor_min": 24.0,
        "cool_summer_only": True,
    }

    def test_the_result_is_readable_by_the_engine(self) -> None:
        stored = {"zones": [_zone_from_form(self.form, {})]}
        zone = config_from_dict(stored).zone("woonkamer")
        assert zone is not None
        assert zone.heat is not None
        assert zone.heat.start_at == 22.0
        assert zone.heat.outdoor.maximum == 19.0
        assert zone.cool is not None
        assert zone.cool.seasons == frozenset({Season.SUMMER})

    def test_editing_keeps_the_id_and_the_sources(self) -> None:
        current = {"zone_id": "living", "sources": [{"source_id": "s", "entity_id": "climate.x"}]}
        zone = _zone_from_form(self.form, current)
        assert zone["zone_id"] == "living"
        assert zone["sources"] == current["sources"]

    def test_a_disabled_duty_becomes_none(self) -> None:
        form = dict(self.form, enable_cool=False)
        zone = config_from_dict({"zones": [_zone_from_form(form, {})]}).zone("woonkamer")
        assert zone is not None
        assert zone.cool is None

    def test_cooling_without_the_summer_restriction(self) -> None:
        form = dict(self.form, cool_summer_only=False)
        zone = config_from_dict({"zones": [_zone_from_form(form, {})]}).zone("woonkamer")
        assert zone is not None
        assert zone.cool is not None
        assert zone.cool.seasons is None


def test_all_source_ids_walks_every_zone() -> None:
    assert set(_all_source_ids(config_to_dict(house()))) == {
        "woonkamer_airco",
        "gasketel",
        "zolder_airco",
        "slaapkamer_airco",
    }


class TestOptionsFlowCursors:
    def test_the_zone_cursor_is_not_shared_with_the_other_lists(self) -> None:
        """Sources read the zone cursor later; a circuit edit must not move it."""
        flow = ClimateDirectorOptionsFlow()
        flow._zone_index = 1
        flow._index = 7
        assert flow._zone_index == 1

    def test_a_stale_cursor_yields_no_zone_instead_of_raising(self) -> None:
        flow = ClimateDirectorOptionsFlow()
        flow._installation = {"zones": [{"zone_id": "a"}]}
        flow._zone_index = 5
        assert flow._current_zone() is None

    def test_an_unset_cursor_yields_no_zone(self) -> None:
        flow = ClimateDirectorOptionsFlow()
        flow._installation = {"zones": [{"zone_id": "a"}]}
        assert flow._current_zone() is None

    def test_a_valid_cursor_yields_the_zone(self) -> None:
        flow = ClimateDirectorOptionsFlow()
        flow._installation = {"zones": [{"zone_id": "a"}, {"zone_id": "b"}]}
        flow._zone_index = 1
        zone = flow._current_zone()
        assert zone is not None
        assert zone["zone_id"] == "b"


class TestStopDetection:
    """A failed stop abandons the plan; a failed start does not."""

    @pytest.mark.parametrize("mode", [MODE_OFF, MODE_FAN_ONLY])
    def test_idle_modes_count_as_stops(self, mode: str) -> None:
        assert _is_stop(Change(UnitCommand("climate.x", mode), True, False))

    @pytest.mark.parametrize("mode", [MODE_HEAT, MODE_COOL])
    def test_active_modes_do_not(self, mode: str) -> None:
        assert not _is_stop(Change(UnitCommand("climate.x", mode, 21.0), True, True))
