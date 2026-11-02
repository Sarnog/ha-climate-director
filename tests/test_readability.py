"""Welke invoeren van de drie wachtrema's geen lezing gaven.

Which inputs of the three waiting brakes gave no reading.

`readability.unreadable_inputs` leest de entiteiten van de installatie en levert
de verzameling die de engine als `WorldState.unreadable` krijgt. Deze toetsen
houden vast welke vorm, welke bewoner en welke agenda erin komt, los van een
draaiend huis; de livetoetsen in `test_hand_start_live.py` bewijzen wat de airco
daarvan merkt.

`readability.unreadable_inputs` reads the installation's entities and supplies the
collection the engine receives as `WorldState.unreadable`. These tests pin down
which form, which resident and which calendar ends up in it, apart from a running
house; the live tests in `test_hand_start_live.py` prove what the air conditioner
notices.

Dekking: deze toetsen lezen geen gids of vertaling. Gedekt: elke bewoner en elke
sensor apart, de drie vormen (`unavailable`, `unknown`, ontbrekend) en de lezingen
die wel tellen (`none`, `not_home`, `off`), een installatie zonder sensor, en de
agenda's met en zonder trefwoord. Niet gedekt: het gedrag van de zone zelf.

Coverage: these tests read no guide or translation. Covered: each resident and each
sensor apart, the three forms (`unavailable`, `unknown`, missing) and the readings
that do count (`none`, `not_home`, `off`), an installation without a sensor, and the
calendars with and without a keyword. Not covered: the zone's own behaviour.
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest
from conftest import house

from custom_components.climate_director.engine import DirectorConfig
from custom_components.climate_director.engine.world import ReadableInput, UnreadableInput
from custom_components.climate_director.readability import unreadable, unreadable_inputs

CALENDARS = ("calendar.feestdagen", "calendar.school")
FORMS = ["unavailable", "unknown", None]
READINGS = ["none", "not_home", "off", "home", "wireless"]


def _hass(states: dict[str, str | None]) -> Any:
    """Return a stand-in carrying only what `unreadable_inputs` asks for."""
    return SimpleNamespace(
        states=SimpleNamespace(
            get=lambda entity_id: (
                None if states.get(entity_id) is None else SimpleNamespace(state=states[entity_id])
            )
        )
    )


def _readable_world(config: DirectorConfig) -> dict[str, str | None]:
    """Return a state for every entity the installation reads, all readable."""
    states: dict[str, str | None] = {item: "on" for item in config.holiday_calendars}
    for resident in config.residents:
        states[resident.presence_entity] = "home"
        states[resident.sleep_entity] = "wireless"
    return states


def _config(**changes: Any) -> DirectorConfig:
    base = house()
    return replace(
        base,
        holiday_calendars=changes.pop("holiday_calendars", ()),
        holiday_keyword=changes.pop("holiday_keyword", ""),
        **changes,
    )


@pytest.mark.parametrize("state", [None, "unavailable", "unknown"])
def test_no_reading_is_missing_unavailable_or_unknown(state: str | None) -> None:
    assert unreadable(state) is True


@pytest.mark.parametrize("state", READINGS)
def test_every_other_state_is_a_reading(state: str) -> None:
    assert unreadable(state) is False


class TestPresenceAndSleep:
    """Aanwezigheid en slaap, per bewoner en per sensor."""

    @pytest.mark.parametrize("form", FORMS)
    @pytest.mark.parametrize("kind", [ReadableInput.PRESENCE, ReadableInput.SLEEP])
    @pytest.mark.parametrize("who", [0, 1])
    def test_each_resident_and_each_sensor_counts_alone(
        self, who: int, kind: ReadableInput, form: str | None
    ) -> None:
        config = _config()
        resident = config.residents[who]
        states = _readable_world(config)
        entity = (
            resident.presence_entity if kind is ReadableInput.PRESENCE else resident.sleep_entity
        )
        states[entity] = form

        found = unreadable_inputs(_hass(states), config)

        assert found == frozenset({UnreadableInput(kind, resident.resident_id)})

    @pytest.mark.parametrize("reading", READINGS)
    def test_a_reading_that_says_something_never_counts(self, reading: str) -> None:
        config = _config()
        states = dict.fromkeys(_readable_world(config), reading)

        assert unreadable_inputs(_hass(states), config) == frozenset()

    @pytest.mark.parametrize("kind", [ReadableInput.PRESENCE, ReadableInput.SLEEP])
    def test_a_sensor_the_resident_does_not_have_never_counts(self, kind: ReadableInput) -> None:
        config = _config()
        field = "presence_entity" if kind is ReadableInput.PRESENCE else "sleep_entity"
        bare = tuple(replace(resident, **{field: ""}) for resident in config.residents)
        config = replace(config, residents=bare)

        assert unreadable_inputs(_hass({}), config) == frozenset(
            {
                UnreadableInput(other, resident.resident_id)
                for resident in config.residents
                for other in (ReadableInput.PRESENCE, ReadableInput.SLEEP)
                if other is not kind
            }
        )

    def test_everything_gone_names_every_input(self) -> None:
        config = _config()

        assert unreadable_inputs(_hass({}), config) == frozenset(
            UnreadableInput(kind, resident.resident_id)
            for resident in config.residents
            for kind in (ReadableInput.PRESENCE, ReadableInput.SLEEP)
        )


class TestTheHolidayCalendars:
    """De feestdagenagenda's hangen aan het huis en tellen alleen met een trefwoord."""

    @pytest.mark.parametrize("form", FORMS)
    @pytest.mark.parametrize("which", [0, 1])
    def test_any_one_dropped_calendar_counts(self, which: int, form: str | None) -> None:
        config = _config(holiday_calendars=CALENDARS, holiday_keyword="vakantie")
        states = _readable_world(config)
        states[CALENDARS[which]] = form

        assert unreadable_inputs(_hass(states), config) == frozenset(
            {UnreadableInput(ReadableInput.HOLIDAY)}
        )

    @pytest.mark.parametrize("keyword", ["", "   "])
    def test_without_a_keyword_the_calendars_do_not_count(self, keyword: str) -> None:
        config = _config(holiday_calendars=CALENDARS, holiday_keyword=keyword)
        states = _readable_world(config)
        states[CALENDARS[0]] = "unavailable"
        states[CALENDARS[1]] = None

        assert unreadable_inputs(_hass(states), config) == frozenset()

    def test_a_readable_calendar_that_is_off_does_not_count(self) -> None:
        config = _config(holiday_calendars=CALENDARS, holiday_keyword="vakantie")
        states = dict.fromkeys(_readable_world(config), "off")
        states.update({item: "off" for item in CALENDARS})

        assert unreadable_inputs(_hass(states), config) == frozenset()

    def test_a_blank_calendar_entry_is_not_an_entity(self) -> None:
        config = _config(holiday_calendars=("", CALENDARS[0]), holiday_keyword="vakantie")

        assert unreadable_inputs(_hass(_readable_world(config)), config) == frozenset()
