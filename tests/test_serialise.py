"""Tests voor het omzetten van en naar de opslag van een config entry.

Tests for converting to and from a config entry's storage.
"""

from __future__ import annotations

from datetime import time, timedelta

from conftest import house

from custom_components.climate_director.engine import (
    ConflictPolicy,
    DirectorConfig,
    Season,
    SourceRole,
    validate,
)
from custom_components.climate_director.engine.models import SeasonSource
from custom_components.climate_director.engine.serialise import config_from_dict, config_to_dict


class TestRoundTrip:
    def test_the_existing_installation_survives_a_round_trip(self) -> None:
        original = house()
        assert config_from_dict(config_to_dict(original)) == original

    def test_a_round_trip_stays_stable_on_a_second_pass(self) -> None:
        stored = config_to_dict(house())
        assert config_to_dict(config_from_dict(stored)) == stored

    def test_an_empty_installation_round_trips(self) -> None:
        assert config_from_dict(config_to_dict(DirectorConfig())) == DirectorConfig()

    def test_the_stored_form_is_plain_json_types(self) -> None:
        """A config entry stores JSON; a timedelta or an enum would not survive."""

        def walk(value: object) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    assert isinstance(key, str)
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)
            else:
                assert value is None or isinstance(value, str | int | float | bool), value

        walk(config_to_dict(house()))


class TestForgivingReads:
    def test_an_empty_dict_gives_an_empty_installation(self) -> None:
        assert config_from_dict({}) == DirectorConfig()

    def test_unknown_keys_are_ignored(self) -> None:
        config = config_from_dict({"zones": [], "invented_in_a_later_version": 42})
        assert config == DirectorConfig()

    def test_a_missing_field_falls_back_on_its_default(self) -> None:
        config = config_from_dict({"zones": [{"zone_id": "z", "sources": [{"entity_id": "c.x"}]}]})
        zone = config.zone("z")
        assert zone is not None
        assert zone.priority == 0
        assert zone.sources[0].role is SourceRole.HEAT_COOL

    def test_junk_in_a_list_is_skipped_rather_than_fatal(self) -> None:
        config = config_from_dict({"zones": ["not a zone", {"zone_id": "z"}, None]})
        assert [zone.zone_id for zone in config.zones] == ["z"]

    def test_an_unrecognised_enum_value_falls_back(self) -> None:
        config = config_from_dict(
            {
                "circuits": [{"circuit_id": "c", "conflict_policy": "coin_toss"}],
                "seasons": {"source": "vibes"},
            }
        )
        circuit = config.circuit("c")
        assert circuit is not None
        assert circuit.conflict_policy is ConflictPolicy.PRIORITY
        assert config.seasons.source is SeasonSource.AUTO

    def test_a_boolean_is_not_read_as_a_number(self) -> None:
        """`True` is an `int` in Python; a priority of `True` would be a silent 1."""
        config = config_from_dict({"zones": [{"zone_id": "z", "priority": True, "sources": []}]})
        zone = config.zone("z")
        assert zone is not None
        assert zone.priority == 0


class TestDurations:
    def test_durations_are_stored_as_seconds(self) -> None:
        stored = config_to_dict(house())
        assert stored["circuits"][0]["family_switch_delay"] == 5.0

    def test_and_read_back_as_timedeltas(self) -> None:
        config = config_from_dict({"circuits": [{"circuit_id": "c", "min_cycle_time": 180}]})
        circuit = config.circuit("c")
        assert circuit is not None
        assert circuit.min_cycle_time == timedelta(minutes=3)

    def test_an_opening_without_a_delay_gets_none(self) -> None:
        """Inventing half a minute would hide a choice the user never made."""
        config = config_from_dict({"openings": [{"entity_id": "binary_sensor.door"}]})
        assert config.openings[0].delay == timedelta(0)

    def test_an_explicit_zero_delay_survives(self) -> None:
        config = config_from_dict({"openings": [{"entity_id": "binary_sensor.door", "delay": 0}]})
        assert config.openings[0].delay == timedelta(0)

    def test_a_given_delay_is_kept(self) -> None:
        config = config_from_dict({"openings": [{"entity_id": "binary_sensor.door", "delay": 45}]})
        assert config.openings[0].delay == timedelta(seconds=45)

    def test_a_presence_timeout_defaults_to_none(self) -> None:
        config = config_from_dict({"zones": [{"zone_id": "z", "presence_entity": "b.p"}]})
        assert config.zones[0].presence_timeout == timedelta(0)


class TestScheduleWindows:
    def test_times_round_trip(self) -> None:
        stored = {
            "residents": [
                {
                    "resident_id": "danny",
                    "windows": [{"start": "08:00:00", "end": "18:30:00", "weekdays": [0, 1]}],
                }
            ]
        }
        window = config_from_dict(stored).residents[0].windows[0]
        assert window.start == time(8, 0)
        assert window.end == time(18, 30)
        assert window.weekdays == frozenset({0, 1})

    def test_a_short_time_is_accepted(self) -> None:
        stored = {
            "residents": [{"resident_id": "d", "windows": [{"start": "8:00", "end": "18:00"}]}]
        }
        window = config_from_dict(stored).residents[0].windows[0]
        assert window.start == time(8, 0)
        assert window.weekdays is None

    def test_an_unreadable_time_does_not_raise(self) -> None:
        stored = {"residents": [{"resident_id": "d", "windows": [{"start": "kwart over acht"}]}]}
        window = config_from_dict(stored).residents[0].windows[0]
        assert window.start == time(0, 0)


class TestSeasons:
    def test_a_summer_only_duty_round_trips(self) -> None:
        config = config_from_dict(config_to_dict(house()))
        zone = config.zone("woonkamer")
        assert zone is not None
        assert zone.cool is not None
        assert zone.cool.seasons == frozenset({Season.SUMMER})

    def test_no_season_restriction_stays_none(self) -> None:
        config = config_from_dict(config_to_dict(house()))
        zone = config.zone("woonkamer")
        assert zone is not None
        assert zone.heat is not None
        assert zone.heat.seasons is None

    def test_summer_months_have_a_sensible_default(self) -> None:
        settings = config_from_dict({}).seasons
        assert settings.for_month(7) is Season.SUMMER
        assert settings.for_month(1) is Season.WINTER


def test_a_round_tripped_installation_still_validates() -> None:
    assert validate(config_from_dict(config_to_dict(house()))) == ()
