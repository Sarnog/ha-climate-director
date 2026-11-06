"""Bereikbare takken van de entiteiten, de teksten en de meldingen.

Reachable branches of the entities, the texts and the notices."""

from __future__ import annotations

import dataclasses
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import house, make_world
from flow_helpers import cold, two_rooms

from custom_components.climate_director import problems, texts
from custom_components.climate_director.binary_sensor import ZoneBlockedSensor, ZoneFallbackSensor
from custom_components.climate_director.coordinator import ClimateDirectorCoordinator
from custom_components.climate_director.engine.fields import FieldSpec
from custom_components.climate_director.preconditions import PreconditionsMixin
from custom_components.climate_director.sensor import ZoneSourceSensor
from custom_components.climate_director.switch import _opening_label
from custom_components.climate_director.world_builder import WorldBuilderMixin


def test_a_presence_entity_that_is_missing_counts_as_nobody_home() -> None:
    """Zonder aanwezigheidsentiteit is er niemand thuis, en dat is geen fout."""
    builder = WorldBuilderMixin.__new__(WorldBuilderMixin)
    builder.hass = SimpleNamespace(states=SimpleNamespace(get=lambda _entity_id: None))
    builder._empty_since = {}
    assert builder._presence("zolder", "person.bestaat_niet", "on").occupied is False


def test_a_temperature_placeholder_that_is_no_number_stays() -> None:
    """Een placeholder die geen getal is blijft staan zoals hij is."""
    hass = SimpleNamespace(config=SimpleNamespace(units=None))
    problem = SimpleNamespace(code="target_outside_band", params={"start": "geen getal"})
    assert problems._converted_params(hass, problem)["start"] == "geen getal"
    empty = SimpleNamespace(code="target_outside_band", params={})
    assert problems._converted_params(hass, empty) == {}


async def test_a_text_without_a_template_falls_back() -> None:
    """Een onbekende tekstsleutel levert de terugvaltekst op."""
    from harness_live import start_bare_house

    hass = await start_bare_house()
    try:
        assert texts.translated(hass, "bestaat_niet", "terugval") == "terugval"
    finally:
        await hass.async_stop()


def test_the_entities_say_nothing_before_the_first_decision() -> None:
    """Zonder plan geven de entiteiten geen waarde en geen attributen."""
    coordinator = SimpleNamespace(data=None)

    blocked = ZoneBlockedSensor.__new__(ZoneBlockedSensor)
    blocked.coordinator = coordinator
    blocked._zone_id = "woonkamer"
    assert blocked.is_on is None
    assert blocked.extra_state_attributes == {}

    fallback = ZoneFallbackSensor.__new__(ZoneFallbackSensor)
    fallback.coordinator = coordinator
    fallback._zone_id = "woonkamer"
    assert fallback.extra_state_attributes == {}

    source = ZoneSourceSensor.__new__(ZoneSourceSensor)
    source.coordinator = coordinator
    source._zone_id = "woonkamer"
    assert source.extra_state_attributes == {}


def test_an_entity_without_a_decision_for_its_zone_says_nothing() -> None:
    """Een plan zonder beslissing voor deze zone laat de entiteit leeg."""
    from custom_components.climate_director.engine import Plan

    coordinator = SimpleNamespace(data=Plan())

    blocked = ZoneBlockedSensor.__new__(ZoneBlockedSensor)
    blocked.coordinator = coordinator
    blocked._zone_id = "onbekend"
    assert blocked.is_on is None
    assert blocked.extra_state_attributes == {}

    fallback = ZoneFallbackSensor.__new__(ZoneFallbackSensor)
    fallback.coordinator = coordinator
    fallback._zone_id = "onbekend"
    assert fallback.extra_state_attributes == {}

    source = ZoneSourceSensor.__new__(ZoneSourceSensor)
    source.coordinator = coordinator
    source._zone_id = "onbekend"
    assert source.extra_state_attributes == {}


def test_openings_are_empty_before_the_first_world() -> None:
    """Zonder wereld is er geen openstaande opening om te melden."""
    coordinator = ClimateDirectorCoordinator.__new__(ClimateDirectorCoordinator)
    coordinator.world = None
    assert coordinator._open_openings("woonkamer", house_wide=True) == []


def test_preconditioning_that_is_switched_off_reports_nothing() -> None:
    """Met een maximum van nul doet een vooruit-verzoek niets, met een logregel."""
    gates = dataclasses.replace(house().gates, max_precondition=timedelta(0))
    config = dataclasses.replace(house(), gates=gates)
    host = PreconditionsMixin.__new__(PreconditionsMixin)
    host.config = config
    assert host.async_precondition(["woonkamer"], 30) == {}


def test_a_guest_house_waits_for_the_last_sleeper() -> None:
    """In gastenmodus wacht een huis met iemand thuis op wie nog in bed ligt."""
    from dataclasses import replace
    from datetime import time

    from conftest import asleep, at, awake, gate_verdict

    from custom_components.climate_director.engine import Reason, WakeDeadline
    from custom_components.climate_director.engine.gates import closed

    eleven = WakeDeadline(at=time(11, 0), weekdays=frozenset({5, 6}))
    base = house()
    config = replace(
        base,
        residents=tuple(replace(resident, wake_deadline=eleven) for resident in base.residents),
    )
    world = make_world(
        now=at(10, 0, day=15),
        residents={"danny": awake(), "nancy": asleep()},
        guest_mode=True,
        asleep_since=at(1, 0, day=15),
    )
    zone = config.zones[0]
    assert not gate_verdict(config, world, zone).allowed
    assert next(iter(closed(config, world, zone)), None) is Reason.WAITING_FOR_SLEEPER


def test_a_fallback_text_that_cannot_be_filled_comes_back_whole(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Een terugvaltekst met een ontbrekende plaatshouder komt er ook uit."""
    monkeypatch.setattr(texts, "lookup", lambda _hass, _code: None)
    assert texts.translated(object(), "bestaat_niet", "{ontbreekt}") == "{ontbreekt}"


def test_a_field_type_the_settings_table_does_not_know_is_refused() -> None:
    """Een veldtype of maat die de instellingentabel niet kent is een tabel fout."""
    from custom_components.climate_director import schema_fields

    unknown = FieldSpec(key="x", kind="onbekend")
    with pytest.raises(AssertionError, match="onbekend veldtype"):
        schema_fields._selector_for(unknown, SimpleNamespace(hass=None))
    with pytest.raises(AssertionError, match="onbekende maat"):
        schema_fields._stored_number(unknown, 5, "onbekend")
    with pytest.raises(AssertionError, match="onbekend veldtype"):
        schema_fields._stored_value(unknown, {}, {}, "°C")


async def test_an_unreadable_indoor_sensor_is_reported_by_its_state() -> None:
    """Een sensor die niet te lezen is wordt met zijn eigen toestand gemeld."""
    from harness_live import start_house, stop_house

    states = {**cold(), "sensor.woonkamer": ("unavailable", {})}
    live = await start_house(two_rooms(), states=states)
    try:
        assert live.coordinator.unusable_entities()["sensor.woonkamer"] == "unavailable"
    finally:
        await stop_house(live)


def test_a_label_for_an_unknown_opening_falls_back_on_its_id() -> None:
    """Een overbruggingsschakelaar zonder vindbare opening leest als zijn id."""
    coordinator = SimpleNamespace(config=house())
    assert _opening_label(coordinator, "bestaat_niet") == "bestaat_niet"


def test_an_unreadable_strings_file_yields_no_english_templates(monkeypatch) -> None:
    """texts.py: een onleesbaar `strings.json` geeft een lege terugval, geen fout.

    texts.py: an unreadable `strings.json` yields an empty fallback, not an error.
    """

    def refuse(_self, *_args, **_kwargs) -> str:
        raise OSError("onleesbaar")

    monkeypatch.setattr(Path, "read_text", refuse)
    assert texts._read_english_templates() == {}
