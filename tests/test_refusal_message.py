"""De zin die met een geweigerd vooruit-verzoek meekomt.

The sentence that travels with a refused pre-conditioning request.

De integratie stuurt zelf geen berichten - waar een melding heen gaat is niets
waar een klimaatregelaar over hoort te beslissen. De tékst hoort hier wel
vandaan te komen: een blueprint kan niet vertalen, en wie zijn huis in het
Nederlands bedient wil geen Engelse melding op zijn telefoon.

Er zitten twee zinnen in de gebeurtenis: de weigering, en wat er te melden valt
zodra iemand op "toch doen" drukt.

The integration sends no messages of its own - where a notification goes is
nothing a climate controller should decide. The *text* does belong here: a
blueprint cannot translate, and whoever runs their house in Dutch does not want
an English notice on their phone.

Two sentences travel in the event: the refusal, and what there is to report the
moment somebody presses "do it anyway".
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from conftest import make_world

from custom_components.climate_director import texts
from custom_components.climate_director.coordinator import ClimateDirectorCoordinator
from custom_components.climate_director.engine import (
    DirectorConfig,
    GateSettings,
    ModeSettings,
    Opening,
    OpeningState,
    Season,
    Source,
    Zone,
)

ATTIC = "climate.zolder"
WINDOW = "binary_sensor.dakraam"
NOON = datetime(2026, 8, 18, 12, 0)


def config() -> DirectorConfig:
    return DirectorConfig(
        zones=(
            Zone(
                "zolder",
                "Zolder",
                "sensor.zolder",
                sources=(Source("z", ATTIC),),
                heat=ModeSettings(target=21.0, start_at=20.0),
                cool=ModeSettings(target=23.0, start_at=24.0),
            ),
        ),
        openings=(Opening(entity_id=WINDOW),),
        gates=GateSettings(max_precondition=timedelta(hours=2)),
    )


def coordinator(indoor: float | None = 15.0):
    """Return a stand-in carrying just enough to build one refusal."""

    class State:
        name = "Dakraam"

    class Registry:
        def get(self, entity_id: str):
            return State() if entity_id == WINDOW else None

    class Config:
        language = "en"

    class Hass:
        states = Registry()
        config = Config()

    class Entry:
        entry_id = "abc"

    class StandIn:
        def __init__(self) -> None:
            self.config = config()
            self.hass = Hass()
            self.config_entry = Entry()
            self.data = None
            self._precondition = {"zolder": NOON + timedelta(hours=1)}
            self.world = make_world(
                now=NOON,
                outdoor=8.0,
                indoor={} if indoor is None else {"zolder": indoor},
                climates={ATTIC: "off"},
                openings={WINDOW: OpeningState(open=True, changed_at=None)},
            )

        _refusal_data = ClimateDirectorCoordinator._refusal_data
        _friendly = ClimateDirectorCoordinator._friendly
        _open_openings = ClimateDirectorCoordinator._open_openings

        def refusal_data(self, zone_id: str):
            """Build one refusal the way the coordinator does, with its last plan."""
            return self._refusal_data(zone_id, self.data)

    return StandIn()


@pytest.fixture(autouse=True)
def _without_translations(monkeypatch: pytest.MonkeyPatch):
    """Keep the English fallback in place unless a test says otherwise.

    Opzoeken raakt een cache die alleen in een draaiende Home Assistant bestaat.
    Looking up touches a cache that only exists inside a running Home Assistant.
    """
    monkeypatch.setattr(texts, "lookup", lambda hass, code: None)


class TestTheFacts:
    def test_the_window_is_named_the_way_a_person_knows_it(self) -> None:
        data = coordinator().refusal_data("zolder")
        assert data["openings"] == [WINDOW]
        assert data["opening_names"] == ["Dakraam"]

    def test_the_room_and_its_target_are_carried_along(self) -> None:
        data = coordinator().refusal_data("zolder")
        assert data["zone"] == "Zolder"
        assert data["indoor_temperature"] == 15.0
        assert data["target_temperature"] == 21.0

    def test_the_override_duration_is_the_configured_maximum(self) -> None:
        """The blueprint leaves `minutes` empty, which grants exactly this."""
        assert coordinator().refusal_data("zolder")["override_minutes"] == 120


class TestWhichOpeningsAreNamed:
    """Alleen openingen die écht tegenhouden komen in de melding.

    Only openings really holding the zone back make it into the notice.
    """

    def _opening(self, *, delay: timedelta, changed_at: datetime | None) -> object:
        from dataclasses import replace

        item = coordinator()
        item.config = replace(item.config, openings=(Opening(entity_id=WINDOW, delay=delay),))
        item.world = make_world(
            now=NOON,
            outdoor=8.0,
            indoor={"zolder": 15.0},
            climates={ATTIC: "off"},
            openings={WINDOW: OpeningState(open=True, changed_at=changed_at)},
        )
        return item

    def test_an_opening_inside_its_delay_is_not_named(self) -> None:
        item = self._opening(delay=timedelta(minutes=5), changed_at=NOON)
        assert item._open_openings("zolder") == []

    def test_an_opening_past_its_delay_is_named(self) -> None:
        item = self._opening(delay=timedelta(minutes=5), changed_at=NOON - timedelta(minutes=6))
        assert item._open_openings("zolder") == [WINDOW]

    def test_an_opening_with_an_unknown_age_is_named(self) -> None:
        item = self._opening(delay=timedelta(minutes=5), changed_at=None)
        assert item._open_openings("zolder") == [WINDOW]


class TestTheRefusalSentence:
    def test_it_says_what_could_not_start_and_what_is_open(self) -> None:
        data = coordinator().refusal_data("zolder")
        assert data["title"] == "Pre-conditioning refused"
        assert "Zolder" in data["message"]
        assert "Dakraam" in data["message"]
        assert "120 minutes" in data["message"]

    def test_a_translation_wins_over_the_english(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def dutch(hass, code: str) -> str | None:
            return "{zone}: {openings} staat open" if code == "precondition_refused" else None

        monkeypatch.setattr(texts, "lookup", dutch)
        data = coordinator().refusal_data("zolder")
        assert data["message"] == "Zolder: Dakraam staat open"

    def test_a_broken_translation_falls_back_instead_of_raising(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A translation that drifted from the code may not take the event down."""
        monkeypatch.setattr(texts, "lookup", lambda hass, code: "{does_not_exist}")
        data = coordinator().refusal_data("zolder")
        assert "Zolder" in data["message"]


class TestTheSentenceAfterTheButton:
    def test_it_names_the_ignored_sensor_and_both_temperatures(self) -> None:
        data = coordinator().refusal_data("zolder")
        assert data["confirmed_title"] == "Pre-conditioning is running"
        assert "Dakraam" in data["confirmed_message"]
        assert "15 degrees" in data["confirmed_message"]
        assert "21 degrees" in data["confirmed_message"]

    def test_a_room_that_is_already_right_says_so(self) -> None:
        """Nothing will happen, and that is not a shortcoming - so say it."""
        data = coordinator(indoor=21.5).refusal_data("zolder")
        assert "already right" in data["confirmed_message"]
        assert data["target_temperature"] is None

    def test_an_unreadable_room_says_that_instead_of_printing_nothing(self) -> None:
        data = coordinator(indoor=None).refusal_data("zolder")
        assert "cannot be read" in data["confirmed_message"]
        assert "None" not in data["confirmed_message"]

    def test_a_room_that_may_do_nothing_is_not_called_already_right(self) -> None:
        """Vijftien graden en "de kamer ligt al goed" is een leugen.

        Een zone die alleen in de zomer mag koelen en niet mag verwarmen heeft
        geen streeftemperatuur, net als een kamer die al goed ligt - maar de
        reden is een heel andere, en de gebruiker zit op vijftien graden.

        Fifteen degrees and "the room is already right" is a lie. A zone that
        may only cool in summer and may not heat has no target, just like a
        room that is already right - but the reason is a very different one,
        and the user is sitting at fifteen degrees.
        """
        item = coordinator(indoor=15.0)
        item.config = DirectorConfig(
            zones=(
                Zone(
                    "zolder",
                    "Zolder",
                    "sensor.zolder",
                    sources=(Source("z", ATTIC),),
                    cool=ModeSettings(
                        target=23.0, start_at=24.0, seasons=frozenset({Season.SUMMER})
                    ),
                ),
            ),
            openings=(Opening(entity_id=WINDOW),),
            gates=GateSettings(max_precondition=timedelta(hours=2)),
        )
        data = item.refusal_data("zolder")
        assert data["target_temperature"] is None
        assert "already right" not in data["confirmed_message"]
        assert "nothing this room may do" in data["confirmed_message"]
        assert "15 degrees" in data["confirmed_message"]


class TestTheNumberFormatting:
    def test_a_whole_degree_loses_its_decimal(self) -> None:
        assert texts.number(21.0) == "21"

    def test_half_a_degree_keeps_it(self) -> None:
        assert texts.number(21.5) == "21.5"

    def test_nothing_reads_as_a_dash(self) -> None:
        assert texts.number(None) == "-"
