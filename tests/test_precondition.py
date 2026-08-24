"""Vooruit verwarmen: het enige dat een leeg huis mag laten draaien.

Pre-conditioning: the only thing allowed to run an empty house.

Alles in deze integratie is erop gebouwd dat een leeg huis met rust gelaten
wordt. Deze ene uitzondering doorbreekt dat met opzet, en is daarom de plek waar
het meeste mis kan gaan. Eén grens houdt hem in toom, en die is niet te
vergeten: het verzoek verloopt vanzelf. Er is geen venster meer; een handmatig
verzoek gaat altijd voor, ongeacht het uur. Er is geen schakelaar die aan kan
blijven staan - dat is het hele punt.

Everything in this integration is built on leaving an empty house alone. This
one exception breaks that on purpose, and is therefore where most can go wrong.
One bound holds it in check, and it cannot be forgotten: the request expires by
itself. There is no window anymore; a hand-given request always outranks the
automation, whatever the hour. There is no switch here that can be left on -
which is the whole point.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest
from conftest import asleep, awake, away, gate_verdict, make_world

from custom_components.climate_director.engine import (
    DirectorConfig,
    GateSettings,
    ModeSettings,
    Opening,
    Reason,
    Resident,
    Source,
    TimeWindow,
    Zone,
    ZoneGate,
    validate,
)
from custom_components.climate_director.engine.serialise import config_from_dict, config_to_dict
from custom_components.climate_director.engine.world import OpeningState, PresenceState

#: Dinsdag 11 augustus 2026.
#: Tuesday 11 August 2026.
DAY = datetime(2026, 8, 11)

DANNY = Resident(
    "danny",
    "Danny",
    windows=(TimeWindow(time(6, 0), time(9, 0)),),
    presence_entity="person.danny",
    sleep_entity="sensor.danny_charger_type",
    sleep_state="wireless",
)


def at(hour: int, minute: int = 0) -> datetime:
    return DAY.replace(hour=hour, minute=minute)


def house(**gate_kwargs: object) -> DirectorConfig:
    return DirectorConfig(
        zones=(
            Zone(
                "woonkamer",
                "Woonkamer",
                "sensor.woonkamer",
                sources=(Source("w", "climate.huiskamer"),),
                heat=ModeSettings(21.0, 20.0),
                presence_entity="binary_sensor.woonkamer",
            ),
        ),
        residents=(DANNY,),
        openings=(Opening("binary_sensor.raam", zone_ids=("woonkamer",)),),
        gates=GateSettings(**{"require_schedule": True, **gate_kwargs}),  # type: ignore[arg-type]
    )


def verdict(config: DirectorConfig, **kwargs: object):
    zone = config.zone("woonkamer")
    assert zone is not None
    return gate_verdict(config, make_world(**kwargs), zone)  # type: ignore[arg-type]


def empty_house(moment: datetime, until: datetime | None, **extra: object):
    """Return the arguments for a world where nobody is home and nothing is asked."""
    return dict(
        now=moment,
        residents={"danny": away()},
        presence={"woonkamer": PresenceState(occupied=False)},
        precondition_until={} if until is None else {"woonkamer": until},
        **extra,
    )


class TestItRunsAnEmptyHouse:
    """The one thing it is for: warm before somebody walks in."""

    def test_without_a_request_nothing_happens(self) -> None:
        result = verdict(house(), **empty_house(at(15), None))
        assert result.reason is Reason.NOBODY_HOME

    def test_with_a_request_it_runs(self) -> None:
        result = verdict(house(), **empty_house(at(15), at(16)))
        assert result.allowed

    def test_it_ignores_the_schedule(self) -> None:
        """Danny's window closed at nine; that is not what this is about."""
        result = verdict(house(), **empty_house(at(15), at(16)))
        assert result.allowed

    def test_it_ignores_an_empty_room(self) -> None:
        """The room being empty is the reason for asking, not a reason to refuse."""
        result = verdict(house(), **empty_house(at(15), at(16)))
        assert result.allowed


class TestItRunsOut:
    """The timer is the whole safety argument, so it gets its own tests."""

    @pytest.mark.parametrize("minutes", [1, 30, 120])
    def test_before_the_moment_it_runs(self, minutes: int) -> None:
        until = at(15) + timedelta(minutes=minutes)
        assert verdict(house(), **empty_house(at(15), until)).allowed

    def test_at_the_exact_moment_it_is_over(self) -> None:
        """A moment that has arrived has passed; there is no lingering."""
        result = verdict(house(), **empty_house(at(15), at(15)))
        assert result.reason is Reason.NOBODY_HOME

    def test_after_the_moment_it_is_over(self) -> None:
        result = verdict(house(), **empty_house(at(15), at(14, 59)))
        assert result.reason is Reason.NOBODY_HOME

    def test_a_request_for_another_zone_does_nothing_here(self) -> None:
        config = house()
        result = verdict(
            config,
            now=at(15),
            residents={"danny": away()},
            presence={"woonkamer": PresenceState(occupied=False)},
            precondition_until={"zolder": at(16)},
        )
        assert result.reason is Reason.NOBODY_HOME


class TestARequestCountsAtEveryHour:
    """Geen venster meer: een verzoek gedraagt zich op elk uur hetzelfde.

    No window anymore: a request behaves the same at every hour.
    """

    @pytest.mark.parametrize(("hour", "minute"), [(3, 0), (12, 0), (23, 30)])
    @pytest.mark.parametrize(
        ("bypass", "door_open"),
        [(True, True), (False, True), (False, False)],
        ids=["bypass_open", "geen_bypass_open", "geen_bypass_dicht"],
    )
    def test_the_door_gate_is_the_only_bound(
        self, hour: int, minute: int, bypass: bool, door_open: bool
    ) -> None:
        moment = at(hour, minute)
        result = verdict(
            house(),
            **empty_house(
                moment,
                moment + timedelta(hours=1),
                precondition_bypass=frozenset({"woonkamer"}) if bypass else frozenset(),
                openings=(
                    {"binary_sensor.raam": OpeningState(open=True, changed_at=None)}
                    if door_open
                    else {}
                ),
            ),
        )
        if door_open and not bypass:
            assert result.reason is Reason.OPENING_OPEN
        else:
            assert result.allowed


class TestWhatItStillObeys:
    """It steps over the gates about people. Never over the house itself."""

    def test_the_master_switch(self) -> None:
        result = verdict(house(), **empty_house(at(15), at(16), master_enabled=False))
        assert result.reason is Reason.MASTER_DISABLED

    def test_a_manual_override(self) -> None:
        result = verdict(house(), **empty_house(at(15), at(16), zone_overrides={"woonkamer": True}))
        assert result.reason is Reason.MANUAL_OVERRIDE

    def test_an_open_window(self) -> None:
        """Heating the street is exactly what nobody asked for."""
        result = verdict(
            house(),
            **empty_house(
                at(15),
                at(16),
                openings={"binary_sensor.raam": OpeningState(open=True, changed_at=None)},
            ),
        )
        assert result.reason is Reason.OPENING_OPEN


class TestSomebodyComesHome:
    """The handover the user asked for: arriving keeps it going, absence ends it."""

    def test_while_the_request_runs_arriving_changes_nothing(self) -> None:
        assert verdict(
            house(),
            now=at(15),
            residents={"danny": awake()},
            presence={"woonkamer": PresenceState(occupied=True)},
            precondition_until={"woonkamer": at(16)},
        ).allowed

    def test_after_it_runs_out_being_home_carries_on(self) -> None:
        """Nothing switches off at the handover: the ordinary gates take over."""
        config = house(require_schedule=False)
        assert verdict(
            config,
            now=at(16),
            residents={"danny": awake()},
            presence={"woonkamer": PresenceState(occupied=True)},
            precondition_until={"woonkamer": at(16)},
        ).allowed

    def test_after_it_runs_out_an_empty_house_goes_off(self) -> None:
        config = house(require_schedule=False)
        result = verdict(
            config,
            now=at(16),
            residents={"danny": away()},
            presence={"woonkamer": PresenceState(occupied=False)},
            precondition_until={"woonkamer": at(16)},
        )
        assert result.reason is Reason.NOBODY_HOME

    def test_a_request_at_night_goes_through_even_while_everyone_sleeps(self) -> None:
        """Geen venster meer: een handmatig verzoek om 03:00 gaat gewoon voor.

        No window anymore: a hand-given request at 03:00 simply outranks the
        automation.
        """
        result = verdict(
            house(),
            now=at(3),
            residents={"danny": asleep()},
            presence={"woonkamer": PresenceState(occupied=True)},
            precondition_until={"woonkamer": at(4)},
        )
        assert result.allowed


class TestPresenceDrivenZonesTakeItToo:
    def test_a_room_that_runs_on_its_sensor_can_be_warmed_ahead(self) -> None:
        config = DirectorConfig(
            zones=(
                Zone(
                    "woonkamer",
                    "Woonkamer",
                    "sensor.woonkamer",
                    sources=(Source("w", "climate.huiskamer"),),
                    heat=ModeSettings(21.0, 20.0),
                    gate=ZoneGate.PRESENCE,
                    presence_entity="binary_sensor.woonkamer",
                ),
            ),
            residents=(DANNY,),
        )
        assert verdict(config, **empty_house(at(15), at(16))).allowed
        assert not verdict(config, **empty_house(at(15), None)).allowed


class TestTheSettingsSurvive:
    def test_they_round_trip(self) -> None:
        config = house(max_precondition=timedelta(minutes=45))
        assert config_from_dict(config_to_dict(config)) == config

    def test_older_options_with_a_window_are_forgiven(self) -> None:
        """Een opgeslagen venster wordt genegeerd; de sleutel is gewoon onbekend.

        A stored window is ignored; the key is simply unknown.
        """
        stored = config_to_dict(house())
        stored["gates"]["precondition_window"] = {
            "start": "06:00:00",
            "end": "23:00:00",
        }
        config = config_from_dict(stored)
        assert config.gates.max_precondition == timedelta(hours=2)
        assert config_from_dict(config_to_dict(config)) == config

    def test_a_maximum_of_zero_is_reported(self) -> None:
        config = DirectorConfig(
            zones=(
                Zone(
                    "z",
                    "Z",
                    "sensor.z",
                    sources=(Source("s", "climate.z"),),
                    heat=ModeSettings(21.0, 20.0),
                ),
            ),
            gates=GateSettings(max_precondition=timedelta(0)),
        )
        assert any("no request can ever run" in item for item in validate(config))


class TestTheRequestItself:
    """The bookkeeping behind the action, without a Home Assistant to run it in.

    `async_precondition` raakt alleen `self.config` en `self._precondition`, dus
    een nagemaakte coordinator is genoeg om de klemming en de zonekeuze te
    controleren - en dat is precies waar het mis kan gaan.

    `async_precondition` touches only `self.config` and `self._precondition`, so
    a stand-in coordinator is enough to check the clamping and the zone
    selection - which is exactly where this can go wrong.
    """

    def _coordinator(self, ceiling: timedelta = timedelta(hours=2)):
        from custom_components.climate_director.coordinator import ClimateDirectorCoordinator

        config = DirectorConfig(
            zones=(
                Zone("woonkamer", "Woonkamer", "sensor.a"),
                Zone("zolder", "Zolder", "sensor.b"),
            ),
            gates=GateSettings(max_precondition=ceiling),
        )

        class StandIn:
            def __init__(self) -> None:
                self.config = config
                self._precondition: dict[str, datetime] = {}
                self._precondition_bypass: set[str] = set()
                self.asked = 0
                self.saved = 0

            def async_request_evaluation(self) -> None:
                self.asked += 1

            def _async_save_state(self) -> None:
                self.saved += 1

            def _preconditions_expire_at(self, until: datetime) -> None:
                self.expiry = until

            async_precondition = ClimateDirectorCoordinator.async_precondition
            async_cancel_precondition = ClimateDirectorCoordinator.async_cancel_precondition
            live_preconditions = ClimateDirectorCoordinator.live_preconditions
            _live_preconditions = ClimateDirectorCoordinator._live_preconditions
            _wake_at_the_first_expiry = ClimateDirectorCoordinator._wake_at_the_first_expiry

        return StandIn()

    def test_it_covers_only_the_zones_asked_for(self) -> None:
        coordinator = self._coordinator()
        granted = coordinator.async_precondition(["zolder"], 30)
        assert set(granted) == {"zolder"}

    def test_no_zones_means_the_whole_house(self) -> None:
        coordinator = self._coordinator()
        granted = coordinator.async_precondition(None, 30)
        assert set(granted) == {"woonkamer", "zolder"}

    def test_an_unknown_zone_is_dropped_and_warned_about(self, caplog) -> None:
        coordinator = self._coordinator()
        assert coordinator.async_precondition(["kelder"], 30) == {}
        assert coordinator.asked == 0
        assert "unknown zones" in caplog.text
        assert "kelder" in caplog.text

    def test_cancelling_an_unknown_zone_is_warned_about(self, caplog) -> None:
        coordinator = self._coordinator()
        coordinator.async_precondition(None, 30)
        coordinator.async_cancel_precondition(["kelder"])
        assert "unknown zones" in caplog.text
        assert set(coordinator._live_preconditions()) == {"woonkamer", "zolder"}

    def test_asking_for_too_long_shortens_it(self) -> None:
        """The intent was clear, only the number was wrong."""
        coordinator = self._coordinator(ceiling=timedelta(minutes=45))
        granted = coordinator.async_precondition(["zolder"], 600)
        assert granted["zolder"] - datetime.now().astimezone() <= timedelta(minutes=45)

    def test_asking_for_nothing_does_nothing(self) -> None:
        """Nul minuten is geen verzoek; het maximum geldt alleen bij weglaten.

        Zero minutes is no request; the maximum applies only when omitted.
        """
        coordinator = self._coordinator(ceiling=timedelta(minutes=45))
        assert coordinator.async_precondition(["zolder"], 0) == {}
        assert coordinator.asked == 0
        assert coordinator.saved == 0

    def test_no_minutes_means_the_installation_maximum(self) -> None:
        """Weglaten (`None`) geeft het maximum, waar de blueprint op rekent.

        Omitting (`None`) gives the maximum, which is what the blueprint relies on.
        """
        coordinator = self._coordinator(ceiling=timedelta(minutes=45))
        granted = coordinator.async_precondition(["zolder"], None)
        assert granted["zolder"] - datetime.now().astimezone() > timedelta(minutes=44)

    def test_a_negative_number_is_refused(self) -> None:
        coordinator = self._coordinator()
        assert coordinator.async_precondition(["zolder"], -600) == {}
        assert coordinator.asked == 0

    def test_cancelling_one_zone_leaves_the_other(self) -> None:
        coordinator = self._coordinator()
        coordinator.async_precondition(None, 30)
        coordinator.async_cancel_precondition(["zolder"])
        assert set(coordinator._live_preconditions()) == {"woonkamer"}

    def test_cancelling_everything(self) -> None:
        coordinator = self._coordinator()
        coordinator.async_precondition(None, 30)
        coordinator.async_cancel_precondition(None)
        assert coordinator._live_preconditions() == {}

    def test_expired_requests_are_forgotten_on_reading(self) -> None:
        coordinator = self._coordinator()
        coordinator._precondition = {"zolder": datetime.now().astimezone() - timedelta(minutes=1)}
        assert coordinator._live_preconditions() == {}
