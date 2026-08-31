"""Tests voor het omzetten van en naar de opslag van een config entry.

Tests for converting to and from a config entry's storage.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import time, timedelta

from conftest import house

from custom_components.climate_director.engine import (
    ConflictPolicy,
    DirectorConfig,
    PrecipitationSettings,
    Season,
    SourceRole,
    TimeWindow,
    WakeDeadline,
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

    def test_precipitation_settings_round_trip(self) -> None:
        config = replace(
            house(),
            precipitation=PrecipitationSettings(
                source="weather.buienradar",
                states=frozenset({"rainy", "snowy"}),
                grace=timedelta(minutes=30),
            ),
            zones=tuple(
                replace(zone, ignore_precipitation=True) if zone.zone_id == "zolder" else zone
                for zone in house().zones
            ),
        )
        assert config_from_dict(config_to_dict(config)) == config

    def test_a_sleep_window_keeps_its_days(self) -> None:
        """Een weekendritme staat in het slaapvenster, dus het moet blijven staan.

        Zonder dit valt `weekdays` weg bij het opslaan en telt de slaapsensor
        weer elke dag - precies wat de bewoner net uitzette.

        A weekend rhythm lives in the sleep window, so it has to survive. Without
        this `weekdays` is dropped on save and the sleep sensor counts every day
        again - exactly what the resident just switched off.
        """
        original = house()
        config = replace(
            original,
            residents=(
                replace(
                    original.residents[0],
                    sleep_window=TimeWindow(
                        start=time(23, 0), end=time(9, 0), weekdays=frozenset({4, 5})
                    ),
                ),
                *original.residents[1:],
            ),
        )
        assert config_from_dict(config_to_dict(config)) == config

    def test_a_wake_deadline_round_trips_with_its_days(self) -> None:
        """De uiterste opsta-tijd hoort bij de bewoner en moet blijven staan.

        Valt hij bij het opslaan weg, dan wacht het huis nergens meer op en
        begint het weer zodra de eerste opstaat - stil, en pas in het weekend
        te merken.

        The wake deadline belongs to the resident and has to survive. Dropped on
        save, the house waits for nobody any more and starts the moment the first
        one is up - quietly, and only noticeable at the weekend.
        """
        original = house()
        config = replace(
            original,
            residents=(
                replace(
                    original.residents[0],
                    wake_deadline=WakeDeadline(
                        at=time(11, 0), weekdays=frozenset({5, 6}), holiday=True
                    ),
                ),
                *original.residents[1:],
            ),
        )
        assert config_from_dict(config_to_dict(config)) == config

    def test_a_resident_without_a_deadline_stays_without_one(self) -> None:
        """Geen tijd is geen middernacht: dat zou het huis om 00:00 stilzetten.

        No time is not midnight: that would hold the house at 00:00.
        """
        stored = config_to_dict(house())
        stored["residents"][0]["wake_deadline"] = {"at": "", "weekdays": [5, 6]}
        assert config_from_dict(stored).residents[0].wake_deadline is None

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

    def test_summer_months_that_are_not_a_list_do_not_break_the_load(self) -> None:
        """Een getal of een tekst waar een lijst hoort, valt terug op niets.

        Zo'n waarde werd hier gewoon doorlopen: bij een tekst kwamen er losse
        letters uit en bij een getal een `TypeError` waarmee de hele
        installatie niet meer laadde.

        A number or a string where a list belongs falls back on nothing. Such a
        value used to be iterated all the same: a string yielded loose letters
        and a number a `TypeError` that stopped the installation from loading.
        """
        for junk in (7, "juli", {"maand": 7}):
            config = config_from_dict({"seasons": {"summer_months": junk}})
            assert config.seasons.summer_months == frozenset()

    def test_no_summer_months_at_all_keeps_the_default(self) -> None:
        """Niets ingevuld is iets anders dan onzin ingevuld."""
        assert config_from_dict({"seasons": {}}).seasons.summer_months == frozenset(range(4, 10))

    def test_junk_between_the_summer_months_is_skipped(self) -> None:
        config = config_from_dict({"seasons": {"summer_months": [6, "juli", None, 8]}})
        assert config.seasons.summer_months == frozenset({6, 8})

    def test_an_unrecognised_enum_value_falls_back(self) -> None:
        config = config_from_dict(
            {
                "circuits": [{"circuit_id": "c", "conflict_policy": "coin_toss"}],
                "seasons": {"source": "vibes"},
            }
        )
        (circuit,) = config.circuits
        assert circuit.conflict_policy is ConflictPolicy.PRIORITY
        assert config.seasons.source is SeasonSource.AUTO

    def test_a_circuit_without_the_flag_is_a_multi_split(self) -> None:
        """Zonder sleutel geldt de veilige kant: één taak tegelijk.

        Without the key the safe side applies: one duty at a time.
        """
        config = config_from_dict({"circuits": [{"circuit_id": "c", "name": "C"}]})
        assert config.circuits[0].simultaneous_heat_cool is False

    def test_a_boolean_is_not_read_as_a_number(self) -> None:
        """`True` is an `int` in Python; a priority of `True` would be a silent 1."""
        config = config_from_dict({"zones": [{"zone_id": "z", "priority": True, "sources": []}]})
        zone = config.zone("z")
        assert zone is not None
        assert zone.priority == 0


class TestPrecipitationStates:
    def test_an_empty_states_list_falls_back_on_the_default(self) -> None:
        """Het instellingenscherm schrijft `[]`; dat hoort de standaardset te zijn.

        The settings screen writes `[]`; that should be the default set.
        """
        config = config_from_dict({"precipitation": {"source": "weather.buienradar", "states": []}})
        assert config.precipitation.states == PrecipitationSettings().states

    def test_whitespace_only_states_fall_back_on_the_default(self) -> None:
        config = config_from_dict(
            {"precipitation": {"source": "weather.buienradar", "states": ["", "  "]}}
        )
        assert config.precipitation.states == PrecipitationSettings().states

    def test_a_missing_states_key_keeps_the_default(self) -> None:
        config = config_from_dict({"precipitation": {"source": "weather.buienradar"}})
        assert config.precipitation.states == PrecipitationSettings().states

    def test_an_explicit_set_survives(self) -> None:
        config = config_from_dict(
            {"precipitation": {"source": "weather.buienradar", "states": ["rainy"]}}
        )
        assert config.precipitation.states == frozenset({"rainy"})


class TestDurations:
    def test_durations_are_stored_as_seconds(self) -> None:
        stored = config_to_dict(house())
        assert stored["circuits"][0]["family_switch_delay"] == 5.0

    def test_and_read_back_as_timedeltas(self) -> None:
        config = config_from_dict({"circuits": [{"circuit_id": "c", "min_cycle_time": 180}]})
        (circuit,) = config.circuits
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


class TestOpenings:
    def test_an_opening_without_an_open_state_gets_on(self) -> None:
        """Existing installations keep reading the state 'on' as open."""
        config = config_from_dict({"openings": [{"entity_id": "binary_sensor.door"}]})
        assert config.openings[0].open_state == "on"

    def test_a_cover_open_state_survives(self) -> None:
        config = config_from_dict(
            {"openings": [{"entity_id": "cover.dakraam", "open_state": "open"}]}
        )
        assert config.openings[0].open_state == "open"

    def test_an_empty_open_state_falls_back_on_on(self) -> None:
        config = config_from_dict({"openings": [{"entity_id": "cover.dakraam", "open_state": ""}]})
        assert config.openings[0].open_state == "on"

    def test_the_open_state_round_trips(self) -> None:
        config = config_from_dict(
            {"openings": [{"entity_id": "cover.dakraam", "open_state": "open"}]}
        )
        assert config_from_dict(config_to_dict(config)) == config


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


class TestTheWholeDay:
    """Een opgeslagen vooruit-venster is onbekend en wordt genegeerd.

    A stored pre-conditioning window is unknown and is ignored.

    Het venster bestaat niet meer, maar `serialise` is vergevingsgezind: een
    configuratie die de oude sleutel nog bevat laadt gewoon, zonder venster.

    The window no longer exists, but `serialise` is forgiving: a configuration
    that still carries the old key loads fine, without a window.
    """

    def test_a_fresh_installation_has_no_window_key(self) -> None:
        stored = config_to_dict(config_from_dict({}))
        assert "precondition_window" not in stored["gates"]

    def test_an_old_window_is_ignored(self) -> None:
        stored = config_to_dict(house())
        stored["gates"]["precondition_window"] = {
            "start": "06:00:00",
            "end": "23:00:00",
        }
        config = config_from_dict(stored)
        assert config_to_dict(config) == config_to_dict(house())

    def test_an_old_all_day_choice_is_ignored_too(self) -> None:
        stored = config_to_dict(house())
        stored["gates"]["precondition_window"] = None
        assert config_to_dict(config_from_dict(stored)) == config_to_dict(house())


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


class TestNothingStoredCanStopTheLoad:
    """Wat er ook in de opslag staat, de integratie moet blijven laden.

    `config_from_dict` draait bij het opstarten. Loopt hij daar stuk, dan laadt de
    hele integratie niet en zie je alleen een fout in het log - geen zone, geen
    schakelaar, niets. Een half opgeslagen optie, een hand-bewerkte entry of een
    veld dat ooit een ander type had mag dat nooit veroorzaken. Wat structureel
    niet klopt hoort uit `validate()` te komen, met een naam erbij.

    `config_from_dict` runs at startup. Break there and the whole integration
    fails to load, leaving nothing but a line in the log - no zone, no switch,
    nothing. A half-written option, a hand-edited entry or a field that once held
    another type must never cause that. What is structurally wrong belongs in
    `validate()`, with a name attached.
    """

    #: Waarden die een JSON-opslag kan bevatten en die ooit crashes gaven.
    #: Values a JSON store can hold, each of which once caused a crash.
    ODD: tuple[object, ...] = (
        None,
        "",
        0,
        -1,
        3.5,
        True,
        False,
        [],
        {},
        "tekst",
        [1, 2],
        {"a": 1},
        1e400,
        -1e400,
        float("nan"),
        [9, -3, "x"],
    )

    SECTIONS = (
        "zones",
        "circuits",
        "residents",
        "openings",
        "generators",
        "gates",
        "seasons",
        "outdoor_sensor",
        "holiday_calendars",
        "holiday_keyword",
        "stuck_after",
        "exclusive_groups",
    )

    def test_ten_thousand_stored_configurations(self) -> None:
        import random

        random.seed(11)
        for _ in range(10_000):
            raw: dict[str, object] = {
                key: random.choice(self.ODD)
                for key in random.sample(self.SECTIONS, random.randint(1, len(self.SECTIONS)))
            }
            if random.random() < 0.5:
                raw["zones"] = [
                    {
                        "zone_id": random.choice(["z", "", None, 1]),
                        "sources": random.choice([[], [{"entity_id": "climate.a"}], None, "x", 3]),
                        "heat": random.choice([None, {}, {"target": random.choice(self.ODD)}]),
                        "gate": random.choice(["household", "presence", "onzin", None]),
                        "presence_timeout": random.choice(self.ODD),
                    }
                ]
            if random.random() < 0.3:
                raw["gates"] = {
                    "quiet_windows": random.choice(
                        [None, "x", 7, [{"weekdays": random.choice(self.ODD)}], [{}]]
                    )
                }
            config = config_from_dict(raw)
            config_to_dict(config)
            validate(config)

    def test_infinity_never_reaches_a_setting(self) -> None:
        """A number that is not finite is not a number worth keeping."""
        config = config_from_dict({"stuck_after": 1e400, "zones": [{"priority": float("nan")}]})
        assert config.stuck_after.total_seconds() == 900
        assert config.zones[0].priority == 0

    def test_an_impossible_weekday_is_dropped(self) -> None:
        """Folding 9 onto a Tuesday would put a window on a day nobody picked."""
        stored = config_from_dict(
            {"residents": [{"resident_id": "d", "windows": [{"weekdays": [9, 2, -3]}]}]}
        )
        assert stored.residents[0].windows[0].weekdays == frozenset({2})

    def test_a_list_that_is_not_a_list_is_empty(self) -> None:
        for value in (7, "tekst", True, {"a": 1}):
            assert config_from_dict({"zones": value}).zones == ()
