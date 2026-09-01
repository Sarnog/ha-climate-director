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

import inspect
from datetime import datetime

import pytest
from conftest import gate_verdict, house

from custom_components.climate_director.applier import _is_stop
from custom_components.climate_director.config_flow import (
    ClimateDirectorOptionsFlow,
    _all_source_ids,
    _band_errors,
    _blank_to_none,
    _deep_copy,
    _next_priority,
    _unique_id,
    _window_label,
    _zone_errors,
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
)
from custom_components.climate_director.engine.diff import Change
from custom_components.climate_director.engine.models import Problem
from custom_components.climate_director.engine.serialise import config_from_dict, config_to_dict
from custom_components.climate_director.number import resolve_initial
from custom_components.climate_director.problems import MAX_LISTED, readable, summarise


@pytest.fixture(autouse=True)
def _seed_english_templates() -> None:
    """Fill the English-template cache, the way production does off the event loop.

    De productie vult deze cache in `texts.async_prepare` via
    `async_add_executor_job`; de synchrone tests hieronder hebben geen draaiende
    Home Assistant en vullen hem daarom met dezelfde pure lezer. Zo loopt
    `readable()` in de tests precies het pad dat het in productie loopt: alleen
    de cache lezen, nooit de schijf.

    Production fills this cache in `texts.async_prepare` through
    `async_add_executor_job`; the synchronous tests below have no running Home
    Assistant and therefore fill it with the same pure reader. That keeps
    `readable()` on exactly the path it takes in production: only reading the
    cache, never the disk.
    """
    from custom_components.climate_director import texts

    if texts.english_templates() is None:
        texts._ENGLISH_TEMPLATES = texts._read_english_templates()


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

    def test_a_sensor_reads_in_the_unit_it_reports(self) -> None:
        """`unit_of_measurement` wint van het systeemstelsel.

        A `sensor` without a temperature device class is not converted by Home
        Assistant, so its own attribute says what it means: 21 °C stays 21 °C on
        an imperial system, and 70 °F is read as 21.1 °C on a metric one.
        """
        assert (
            temperature_from_state(
                "sensor.woonkamer", "21", {"unit_of_measurement": "°C"}, unit="°F"
            )
            == 21.0
        )
        assert temperature_from_state(
            "sensor.woonkamer", "70", {"unit_of_measurement": "°F"}, unit="°C"
        ) == pytest.approx(21.111111, rel=1e-6)

    def test_a_sensor_without_a_unit_follows_the_system_unit(self) -> None:
        """Zonder eigen eenheid is het systeemstelsel de waarheid.

        Without its own unit the system unit is the truth.
        """
        assert temperature_from_state("sensor.woonkamer", "70", {}, unit="°F") == pytest.approx(
            21.111111, rel=1e-6
        )
        assert temperature_from_state("sensor.woonkamer", "21", {}, unit="°C") == 21.0

    @pytest.mark.parametrize(
        ("entity_id", "state", "attributes", "unit", "expected"),
        [
            # eigen eenheid = stelsel / own unit equals the system
            ("sensor.woonkamer", "21", {"unit_of_measurement": "°C"}, "°C", 21.0),
            ("weather.thuis", "sunny", {"temperature": 21.0, "temperature_unit": "°C"}, "°C", 21.0),
            # eigen eenheid overschreven / own unit overridden
            ("sensor.woonkamer", "21", {"unit_of_measurement": "°C"}, "°F", 21.0),
            ("weather.thuis", "sunny", {"temperature": 41.0, "temperature_unit": "°F"}, "°C", 5.0),
            # geen eigen eenheid / no own unit
            ("sensor.woonkamer", "70", {}, "°F", 21.111111),
            ("weather.thuis", "sunny", {"temperature": 70.0}, "°F", 21.111111),
        ],
    )
    def test_a_source_reads_in_the_unit_it_reports(
        self, entity_id: str, state: str, attributes: dict, unit: str, expected: float
    ) -> None:
        """Een sensor noemt zijn eenheid als `unit_of_measurement`, een weersbron als
        `temperature_unit`; zonder eigen eenheid volgt het systeemstelsel.

        A sensor names its unit as `unit_of_measurement`, a weather source as
        `temperature_unit`; without an own unit the system unit follows.
        """
        assert temperature_from_state(entity_id, state, attributes, unit=unit) == pytest.approx(
            expected, rel=1e-6
        )

    def test_a_climate_entity_follows_the_system_unit(self) -> None:
        """Een climate-entiteit publiceert geen eigen eenheid en rekent zelf al om.

        A climate entity publishes no own unit and converts itself already.
        """
        assert temperature_from_state(
            "climate.huiskamer", "heat", {"current_temperature": 70.0}, unit="°F"
        ) == pytest.approx(21.111111, rel=1e-6)


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

        data = _event_data(config, plan, decision, "°C")
        assert data["zone_id"] == "woonkamer"
        assert data["zone_name"] == "Woonkamer"
        assert data["reason"] == decision.reason.value
        assert data["hvac_mode"] == "heat"
        assert data["temperature"] == 23.0
        assert data["temperature_unit"] == "°C"

    def test_a_zone_without_a_command_still_produces_an_event(self) -> None:
        config = house()
        decision = ZoneDecision("woonkamer", Season.UNKNOWN, Season.UNKNOWN)  # type: ignore[arg-type]
        data = _event_data(config, Plan(), decision, "°C")
        assert data["entity_id"] is None
        assert data["hvac_mode"] is None

    def test_an_unknown_zone_falls_back_on_its_id(self) -> None:
        decision = ZoneDecision("kelder", Season.UNKNOWN, Season.UNKNOWN)  # type: ignore[arg-type]
        data = _event_data(house(), Plan(), decision, "°C")
        assert data["zone_name"] == "kelder"

    def test_the_unit_parameter_has_no_default(self) -> None:
        """F4 maakte `unit` verplicht; een teruggezette default zou weer stil
        Celsius-getallen met het label `°C` op een imperiale installatie
        publiceren, en geen test zou het merken.

        F4 made `unit` required; a reinstated default would silently publish
        Celsius numbers labelled `°C` on an imperial installation again, and no
        test would notice.
        """
        assert inspect.signature(_event_data).parameters["unit"].default is inspect.Parameter.empty


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
    """De regel valt terug op het Engels zodra een taal hem niet vertaalt.

    Een lege vertaalkaart is precies dat geval, en het is ook wat de tests
    hieronder gebruiken: zo blijft de terugval gemeten in plaats van aangenomen.

    The line falls back on English as soon as a language does not translate it.
    An empty translation map is exactly that case, and it is what the tests
    below use: that keeps the fallback measured rather than assumed.
    """

    def test_a_window_without_days_reads_as_every_day(self) -> None:
        label = _window_label({"start": "08:00:00", "end": "18:00:00"}, {})
        assert label == "08:00 - 18:00, every day"

    def test_an_empty_day_list_also_reads_as_every_day(self) -> None:
        """No days ticked means every day, not never."""
        label = _window_label({"start": "08:00:00", "end": "18:00:00", "weekdays": []}, {})
        assert label == "08:00 - 18:00, every day"

    def test_days_are_named_and_sorted(self) -> None:
        window = {"start": "06:30:00", "end": "12:00:00", "weekdays": [4, 2]}
        assert _window_label(window, {}) == "06:30 - 12:00, Wed, Fri"

    def test_nonsense_days_do_not_produce_a_dangling_comma(self) -> None:
        window = {"start": "08:00", "end": "18:00", "weekdays": [99, "maandag"]}
        assert _window_label(window, {}) == "08:00 - 18:00, every day"


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
            "gates": {"require_awake": False, "require_schedule": True},
        }
        return config_from_dict(stored)

    def _verdict(self, config: DirectorConfig, moment: datetime):
        from conftest import awake, make_world

        zone = config.zone("z")
        assert zone is not None
        world = make_world(now=moment, residents={"danny": awake()})
        return gate_verdict(config, world, zone)

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


class TestCircuitCursors:
    """Circuits gained sub-steps, so they need a cursor of their own."""

    def _flow(self) -> ClimateDirectorOptionsFlow:
        flow = ClimateDirectorOptionsFlow()
        flow._installation = {
            "circuits": [
                {"circuit_id": "a", "name": "A", "units": ["climate.x", "climate.y"]},
                {"circuit_id": "b", "name": "B", "units": ["climate.z"]},
            ],
            "zones": [
                {
                    "zone_id": "woonkamer",
                    "name": "Woonkamer",
                    "priority": 2,
                    "sources": [{"entity_id": "climate.x"}],
                },
                {
                    "zone_id": "zolder",
                    "name": "Zolder",
                    "priority": 0,
                    "sources": [{"entity_id": "climate.y"}],
                },
                {
                    "zone_id": "kelder",
                    "name": "Kelder",
                    "priority": 0,
                    "sources": [{"entity_id": "climate.z"}],
                },
            ],
        }
        return flow

    def test_a_stale_cursor_yields_no_circuit(self) -> None:
        flow = self._flow()
        flow._circuit_index = 9
        assert flow._current_circuit() is None

    def test_only_the_zones_on_that_circuit_are_offered(self) -> None:
        flow = self._flow()
        flow._circuit_index = 0
        circuit = flow._current_circuit()
        assert circuit is not None
        assert [zone["zone_id"] for zone in flow._zones_on(circuit)] == ["zolder", "woonkamer"]

    def test_they_are_listed_in_the_order_they_win_in(self) -> None:
        """Priority 0 outranks priority 2, so the attic comes first."""
        flow = self._flow()
        flow._circuit_index = 0
        circuit = flow._current_circuit()
        assert circuit is not None
        assert flow._zones_on(circuit)[0]["name"] == "Zolder"

    def test_a_circuit_with_one_zone(self) -> None:
        flow = self._flow()
        flow._circuit_index = 1
        circuit = flow._current_circuit()
        assert circuit is not None
        assert [zone["zone_id"] for zone in flow._zones_on(circuit)] == ["kelder"]

    def test_the_circuit_cursor_is_not_shared_with_the_zone_one(self) -> None:
        flow = self._flow()
        flow._zone_index = 1
        flow._circuit_index = 0
        assert flow._zone_index == 1


class TestNextPriority:
    """A new zone counts up rather than joining everyone else on zero."""

    def test_the_first_zone_starts_at_zero(self) -> None:
        assert _next_priority([]) == 0

    def test_each_new_zone_takes_the_next_number(self) -> None:
        zones = [{"priority": 0}]
        assert _next_priority(zones) == 1
        assert _next_priority([*zones, {"priority": 1}]) == 2

    def test_it_never_collides_after_a_deletion(self) -> None:
        """Counting the list would reuse a number a surviving zone still holds."""
        assert _next_priority([{"priority": 0}, {"priority": 5}]) == 6

    def test_zones_without_a_priority_are_ignored(self) -> None:
        assert _next_priority([{"name": "no priority yet"}]) == 0

    def test_a_boolean_is_not_read_as_a_number(self) -> None:
        assert _next_priority([{"priority": True}]) == 0


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


def _no_hass():
    """Return a stand-in without translations, so the English text stays put.

    `texts.lookup` loopt door Home Assistants vertaalcache heen, en die heeft
    meer van `hass` nodig dan alleen de taal: de lijst met geladen componenten
    en het dataregister voor de singleton-cache.

    `texts.lookup` runs through Home Assistant's translation cache, which needs
    more of `hass` than just the language: the list of loaded components and
    the data register for the singleton cache.
    """

    class Config:
        language = "en"
        top_level_components = set()

    class Hass:
        config = Config()
        data = {}

    return Hass()


class TestProblemSummary:
    def test_a_short_list_is_shown_in_full(self) -> None:
        summary = summarise(_no_hass(), ("first", "second"))
        assert summary == "- first\n- second"
        assert "more" not in summary

    def test_exactly_the_cap_needs_no_tail(self) -> None:
        summary = summarise(_no_hass(), tuple(f"problem {index}" for index in range(MAX_LISTED)))
        assert summary.count("\n") == MAX_LISTED - 1
        assert "more" not in summary

    def test_one_over_the_cap_counts_the_remainder(self) -> None:
        summary = summarise(
            _no_hass(), tuple(f"problem {index}" for index in range(MAX_LISTED + 1))
        )
        assert summary.endswith("- ... and 1 more")

    def test_a_long_list_counts_correctly(self) -> None:
        summary = summarise(
            _no_hass(), tuple(f"problem {index}" for index in range(MAX_LISTED + 7))
        )
        assert summary.endswith("- ... and 7 more")

    def test_nothing_wrong_produces_nothing(self) -> None:
        assert summarise(_no_hass(), ()) == ""

    def test_a_translation_with_a_format_spec_falls_back_to_english(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Een kapotte vertaling mag een melding niet breken; dan blijft Engels staan.

        Sinds H4 is dat de Engelse sjabloon uit `strings.json`, die nog door de
        placeholders en de eenheidomrekening gaat — niet de rauwe engine-tekst.

        A broken translation may not break a notice; the English sentence stays.
        Since H4 that is the English template from `strings.json`, which still
        passes through the placeholders and the unit conversion — not the raw
        engine text.
        """
        from custom_components.climate_director import texts

        monkeypatch.setattr(texts, "lookup", lambda hass, code: "{zone:d}")
        problem = Problem("zone_without_sources", "zone z has no sources", zone="z")
        assert readable(_no_hass(), problem) == (
            "Zone z has no appliance at all, so there is nothing to steer. Add a source."
        )


class TestTheEnglishTemplateIsTheSecondFallback:
    """`readable()` valt terug via de Engelse zin uit `strings.json`.

    `readable()` falls back through the English sentence from `strings.json`.
    """

    def _hass(self, unit: str):
        class Units:
            temperature_unit = unit

        class Config:
            language = "en"
            units = Units()

        class Hass:
            config = Config()
            data = {}

        return Hass()

    @pytest.mark.parametrize(
        ("unit", "expected_parts"),
        [
            ("°C", ("20.0 °C", "19.8 °C")),
            ("°F", ("68.0 °F", "67.6 °F")),
        ],
    )
    def test_an_empty_translation_cache_still_names_the_unit(
        self, monkeypatch: pytest.MonkeyPatch, unit: str, expected_parts: tuple[str, str]
    ) -> None:
        """H4: met een lege vertaalcache noemt de zin nog steeds de eenheid.

        De vertaalcache is leeg als het laden bij het opzetten is misgegaan;
        dan blijft de Engelse sjabloon uit `strings.json` over, en die gaat nog
        steeds door de omrekening naar de eenheid van de gebruiker.

        H4: with an empty translation cache the sentence still names the unit.
        The cache is empty when loading went wrong at setup; the English
        template from `strings.json` remains, and it still passes through the
        conversion into the user's unit.
        """
        from custom_components.climate_director import texts

        monkeypatch.setattr(texts, "lookup", lambda hass, code: None)
        problem = Problem(
            "target_outside_band",
            "zone woonkamer starts heat at 20 but aims for 19.8",
            zone="Woonkamer",
            mode="heat",
            start="20",
            target="19.8",
        )
        sentence = readable(self._hass(unit), problem)
        for part in expected_parts:
            assert part in sentence


class TestTheEnglishTemplatesLiveInTheCache:
    """H5: de Engelse terugval leest alleen de cache, nooit de schijf.

    H5: the English fallback reads only the cache, never the disk.
    """

    def test_a_filled_cache_never_goes_to_disk(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Zodra de cache gevuld is, gaat `readable()` niet meer naar de schijf.

        `Path.read_text` gooit hier; zou `readable()` er toch aankomen, dan faalt
        de test met een `AssertionError`. De cache is gevuld door de autouse
        fixture hierboven, net zoals `texts.async_prepare` dat in productie doet.

        Once the cache is filled, `readable()` no longer goes to disk.
        `Path.read_text` raises here; if `readable()` still reached it, the test
        would fail with an `AssertionError`. The cache is filled by the autouse
        fixture above, just as `texts.async_prepare` does in production.
        """
        from pathlib import Path

        from custom_components.climate_director import texts

        def _boom(*args: object, **kwargs: object) -> str:
            raise AssertionError("readable() ging naar de schijf / readable() went to disk")

        monkeypatch.setattr(Path, "read_text", _boom)
        monkeypatch.setattr(texts, "lookup", lambda hass, code: None)
        problem = Problem("zone_without_sources", "zone z has no sources", zone="z")
        assert readable(_no_hass(), problem) == (
            "Zone z has no appliance at all, so there is nothing to steer. Add a source."
        )

    def test_readable_never_opens_a_file(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """L2: `readable()` doet nooit schijftoegang, hoe de module ook geschreven is.

        Een audithook op `open` ziet élke bestandsopening, óók via `pathlib` of
        een hulpmodule; de vorige bewaking verbood drie namen en liet een
        herschrijving als `json_loads(pathlib.Path(...).read_text(...))` erlangs.
        De caches worden leeggemaakt, zodat het pad dat ooit naar de schijf ging
        werkelijk doorlopen wordt; de uitkomst is dan de rauwe engine-tekst, de
        allerlaatste terugval.

        L2: `readable()` never touches the disk, however the module is written.

        An audit hook on `open` sees every file open, also through `pathlib` or a
        helper module; the previous guard banned three names and let a rewrite
        such as `json_loads(pathlib.Path(...).read_text(...))` pass. The caches
        are emptied, so the path that once went to disk is actually walked; the
        outcome is then the raw engine text, the very last fallback.
        """
        import sys

        from custom_components.climate_director import problems, texts

        opened: list[str] = []
        watching = False

        def _audit(event: str, args: tuple[object, ...]) -> None:
            if event == "open" and watching and args:
                opened.append(str(args[0]))

        sys.addaudithook(_audit)

        # Maak elke modulecache leeg waar de terugval zich achter zou kunnen
        # verschuilen. De huidige code kent er maar één (in `texts`); de oude
        # vorm had er zelf een in `problems`, en die ontbreekt vandaag dus
        # (`raising=False`). `monkeypatch` zet de caches na de test terug, zodat
        # de test geen spoor achterlaat in de sessie.
        #
        # Empty every module cache the fallback could hide behind. The current
        # code has only one (in `texts`); the old shape had its own in
        # `problems`, which is therefore absent today (`raising=False`).
        # `monkeypatch` restores the caches after the test, so the test leaves
        # no trace in the session.
        monkeypatch.setattr(problems, "_ENGLISH_TEMPLATES", None, raising=False)
        monkeypatch.setattr(texts, "_ENGLISH_TEMPLATES", None)

        monkeypatch.setattr(texts, "lookup", lambda hass, code: None)
        problem = Problem("zone_without_sources", "zone z has no sources", zone="z")
        try:
            watching = True
            sentence = readable(_no_hass(), problem)
        finally:
            watching = False

        assert not opened, f"readable() opende bestanden / opened files: {opened}"
        assert sentence == "zone z has no sources"

    def test_every_problem_code_has_an_english_template(self) -> None:
        """Elke `Problem`-code staat in `strings.json["exceptions"]`.

        De Engelse terugval dekt élke code; mist er één, dan valt die ene melding
        terug op de rauwe engine-tekst zonder eenheidomrekening. De codes worden
        met een AST-loop uit de engine verzameld, niet uit een met de hand
        bijgehouden lijst; `45` is de telling die de loop vandaag moet vinden en
        bewaakt dat de loop zelf nog werkt.

        Every `Problem` code is in `strings.json["exceptions"]`.
        The English fallback covers every code; if one is missing, that one
        notice falls back to the raw engine text without unit conversion. The
        codes are gathered from the engine with an AST walk, not from a
        hand-kept list; `45` is the count the walk must find today and guards
        that the walk itself still works.
        """
        import ast
        from pathlib import Path

        from custom_components.climate_director import texts
        from custom_components.climate_director.engine import models as engine_models

        tree = ast.parse(Path(engine_models.__file__).read_text(encoding="utf-8"))
        codes = [
            node.args[0].value
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Problem"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ]
        assert len(codes) == 45
        templates = texts.english_templates()
        assert templates is not None
        missing = [code for code in codes if code not in templates]
        assert not missing, f"missing English templates: {missing}"


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
        zone = _zone_from_form(self.form, current, stored_id=current.get("zone_id"))
        assert zone["zone_id"] == "living"
        assert zone["sources"] == current["sources"]

    def test_editing_keeps_bounds_and_seasons_the_form_does_not_show(self) -> None:
        """De zijden die het formulier niet toont, mogen niet op None terugvallen.

        The sides the form does not show must not fall back to None.
        """
        current = {
            "zone_id": "living",
            "sources": [{"source_id": "s", "entity_id": "climate.x"}],
            "heat": {
                "target": 21.0,
                "start_at": 20.0,
                "hysteresis": 1.0,
                "outdoor": {"minimum": 5.0, "maximum": 19.0},
                "seasons": ["winter", "summer"],
            },
            "cool": {
                "target": 23.0,
                "start_at": 24.0,
                "hysteresis": 1.0,
                "outdoor": {"minimum": 24.0, "maximum": 35.0},
                "seasons": ["summer"],
            },
        }
        zone = _zone_from_form(self.form, current, stored_id=current.get("zone_id"))
        assert zone["heat"]["outdoor"]["minimum"] == 5.0
        assert zone["heat"]["outdoor"]["maximum"] == 19.0
        assert zone["heat"]["seasons"] == ["winter", "summer"]
        assert zone["cool"]["outdoor"]["minimum"] == 24.0
        assert zone["cool"]["outdoor"]["maximum"] == 35.0

    def test_a_newly_enabled_duty_starts_without_hidden_bounds(self) -> None:
        """Wie verwarmen pas aanzet, krijgt geen verborgen waarden uit het niets.

        Enabling heating for the first time should not conjure hidden values.
        """
        current = {
            "zone_id": "living",
            "sources": [{"source_id": "s", "entity_id": "climate.x"}],
        }
        zone = _zone_from_form(self.form, current, stored_id=current.get("zone_id"))
        assert zone["heat"]["outdoor"]["minimum"] is None
        assert zone["heat"]["seasons"] is None
        assert zone["cool"]["outdoor"]["maximum"] is None

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


class TestBlankToNone:
    """J4: `_blank_to_none` is het contract dat leeg nooit als `""` opslaat.

    Sinds K1 kan de interface een leeggemaakt veld alleen nog als ontbrekende
    sleutel aanleveren, en de schemavalidatie weigert `""` voor de getalvelden
    die `_blank_to_none` bewaakt. Het contract van de helper zelf blijft het
    vangnet voor elke route die er ooit wél een `""` heen stuurt, en wordt
    daarom hier als eigenschap vastgepind.

    J4: `_blank_to_none` is the contract that never stores empty as `""`.

    Since K1 the frontend can only deliver a cleared field as a missing key, and
    schema validation refuses `""` for the numeric fields `_blank_to_none`
    guards. The helper's own contract remains the safety net for any route that
    ever does send a `""` there, and is therefore pinned as a property here.
    """

    def test_none_and_an_empty_string_become_none(self) -> None:
        assert _blank_to_none(None) is None
        assert _blank_to_none("") is None

    def test_real_values_stay(self) -> None:
        assert _blank_to_none(0) == 0
        assert _blank_to_none([]) == []
        assert _blank_to_none("open") == "open"


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


class TestTheBandIsRefusedAtTheScreen:
    """Een streeftemperatuur aan de verkeerde kant van het aanpunt komt er niet in.

    De zone start dan keurig en zet het apparaat vervolgens op een temperatuur
    waar het niets voor hoeft te doen. Van buiten lijkt dat op een apparaat dat
    weigert - een fout waar je een dag mee zoekt, en die het scherm waarop je
    hem intikt meteen kan zien.

    A target on the wrong side of the switch-on point does not get in.

    The zone then starts dutifully and sets the appliance to a temperature it
    need do nothing for. From the outside that looks like an appliance refusing
    - a fault you can spend a day chasing, and one the screen you type it on can
    see at once.
    """

    def _zone(self, heat: dict | None = None, cool: dict | None = None) -> dict:
        return {"zone_id": "zolder", "name": "Zolder", "heat": heat, "cool": cool}

    def test_a_sound_zone_passes(self) -> None:
        zone = self._zone(
            heat={"target": 21.0, "start_at": 20.0},
            cool={"target": 23.0, "start_at": 24.0},
        )
        assert _band_errors(zone) == {}

    def test_heating_that_aims_below_where_it_starts_is_refused(self) -> None:
        zone = self._zone(heat={"target": 19.0, "start_at": 20.0})
        assert _band_errors(zone) == {"heat_target": "target_outside_band"}

    def test_cooling_that_aims_above_where_it_starts_is_refused(self) -> None:
        zone = self._zone(cool={"target": 25.0, "start_at": 24.0})
        assert _band_errors(zone) == {"cool_target": "target_outside_band"}

    def test_both_are_named_at_once(self) -> None:
        """Fixing one and finding the other on the next screen is a round too many."""
        zone = self._zone(
            heat={"target": 19.0, "start_at": 20.0},
            cool={"target": 25.0, "start_at": 24.0},
        )
        assert _band_errors(zone) == {
            "heat_target": "target_outside_band",
            "cool_target": "target_outside_band",
        }

    def test_equal_is_allowed(self) -> None:
        """Starting and aiming at the same degree is narrow, not wrong."""
        zone = self._zone(
            heat={"target": 20.0, "start_at": 20.0},
            cool={"target": 24.0, "start_at": 24.0},
        )
        assert _band_errors(zone) == {}

    def test_a_mode_that_is_off_says_nothing(self) -> None:
        """A zone that may not cool has no cooling band to be wrong about."""
        assert _band_errors(self._zone()) == {}

    def test_the_complaint_matches_the_one_validate_makes(self) -> None:
        """Two places may not disagree about what a sound band is."""
        from custom_components.climate_director.engine import ModeSettings, validate
        from custom_components.climate_director.engine.models import DirectorConfig, Source, Zone

        config = DirectorConfig(
            zones=(
                Zone(
                    "zolder",
                    "Zolder",
                    "sensor.zolder",
                    sources=(Source("z", "climate.zolder"),),
                    heat=ModeSettings(target=19.0, start_at=20.0),
                ),
            )
        )
        codes = [getattr(item, "code", "") for item in validate(config)]
        assert "target_outside_band" in codes
        assert _band_errors({"heat": {"target": 19.0, "start_at": 20.0}, "cool": None}) != {}


class TestTheScreenRefusesWhatCanNeverWork:
    """Drie instellingen die een zone stilzetten zonder dat er iets kapot is.

    Alle drie leverden een zone op die keurig verscheen, met al zijn
    entiteiten, en vervolgens nooit iets deed. Dat is de stilste manier waarop
    deze integratie kan falen, en het scherm waarop je ze intikt kan ze alle
    drie meteen zien. `validate()` zag ze ook al, maar pas achteraf - en tot je
    die melding opmerkt zoek je in de verkeerde hoek.

    Three settings that silence a zone without anything being broken.

    All three produced a zone that appeared neatly, with all its entities, and
    then never did anything. That is the quietest way this integration can
    fail, and the screen you type them on can see all three at once.
    `validate()` saw them too, but only afterwards - and until you notice that
    notice you are looking in the wrong place.
    """

    def _zone(self, **changes) -> dict:
        zone = {
            "zone_id": "zolder",
            "name": "Zolder",
            "heat": {"target": 21.0, "start_at": 20.0},
            "cool": {"target": 23.0, "start_at": 24.0},
            "gate": "household",
            "presence_entity": "",
        }
        return {**zone, **changes}

    def test_a_sound_zone_passes(self) -> None:
        assert _zone_errors(self._zone()) == {}

    def test_the_room_gate_needs_a_room_sensor(self) -> None:
        """Without one the room counts as empty for good."""
        assert _zone_errors(self._zone(gate="presence")) == {
            "presence_entity": "presence_gate_without_sensor"
        }

    def test_the_room_gate_with_a_sensor_is_fine(self) -> None:
        zone = self._zone(gate="presence", presence_entity="binary_sensor.zolder")
        assert _zone_errors(zone) == {}

    def test_a_zone_that_may_do_nothing_is_refused(self) -> None:
        assert _zone_errors(self._zone(heat=None, cool=None)) == {
            "enable_heat": "zone_without_modes"
        }

    def test_cooling_may_not_start_below_heating(self) -> None:
        """Both would then ask for the same room at once."""
        zone = self._zone(cool={"target": 18.0, "start_at": 19.0})
        assert _zone_errors(zone)["cool_start_at"] == "bands_overlap"

    def test_cooling_may_not_start_exactly_where_heating_does(self) -> None:
        zone = self._zone(cool={"target": 19.0, "start_at": 20.0})
        assert _zone_errors(zone)["cool_start_at"] == "bands_overlap"

    def test_a_zone_that_only_cools_never_overlaps(self) -> None:
        assert _zone_errors(self._zone(heat=None)) == {}

    def test_it_gathers_every_complaint_at_once(self) -> None:
        """Fixing one and meeting the next on the following screen is a round too many."""
        zone = self._zone(
            gate="presence",
            heat={"target": 19.0, "start_at": 20.0},
            cool={"target": 25.0, "start_at": 19.0},
        )
        assert set(_zone_errors(zone)) == {
            "presence_entity",
            "heat_target",
            "cool_target",
            "cool_start_at",
        }

    def test_the_band_check_still_stands_on_its_own(self) -> None:
        """`_zone_errors` gathers; the parts keep working separately."""
        zone = self._zone(heat={"target": 19.0, "start_at": 20.0})
        assert _band_errors(zone) == {"heat_target": "target_outside_band"}
