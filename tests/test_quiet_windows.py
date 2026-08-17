"""Uren waarin de director uit zichzelf niets begint.

Hours in which the director starts nothing of its own accord.

Thuiskomen om elf uur 's avonds terwijl je zo naar bed gaat, hoeft het huis niet
te laten opstoken. Maar het is een rem op beginnen, niet op doorgaan: wat al
draait blijft gewoon geregeld, en zet iemand zelf iets aan, dan wordt dat
opgepakt. Zou de rem ook het doorgaan raken, dan was het een tweede rooster - en
dan zou je 's avonds niets meer met de hand kunnen aanzetten.

Coming home at eleven at night when you are about to turn in need not fire the
boiler. But it is a brake on starting, not on continuing: whatever already runs
stays regulated, and switching something on yourself is picked up. Were the brake
to touch continuing as well it would be a second schedule - and then you could no
longer switch anything on by hand in the evening.
"""

from __future__ import annotations

from datetime import datetime, time

import pytest
from conftest import awake, make_world

from custom_components.climate_director.engine import (
    DirectorConfig,
    GateSettings,
    ModeSettings,
    Reason,
    Resident,
    Source,
    TimeWindow,
    Zone,
    gates,
)
from custom_components.climate_director.engine.serialise import config_from_dict, config_to_dict
from custom_components.climate_director.engine.world import PresenceState

LIVING = "climate.huiskamer"

#: 17 augustus 2026 is een maandag, 21 augustus een vrijdag.
#: 17 August 2026 is a Monday, 21 August a Friday.
MONDAY = 17
FRIDAY = 21

WEEK = frozenset({0, 1, 2, 3, 6})
WEEKEND = frozenset({4, 5})

#: Zijn eigen vensters, omgekeerd: de uren waarin er niets mag beginnen.
#: His own windows, inverted: the hours in which nothing may start.
HIS = (
    TimeWindow(time(21, 0), time(9, 0), WEEK),
    TimeWindow(time(23, 0), time(9, 0), WEEKEND),
)


def house(*windows: TimeWindow) -> DirectorConfig:
    return DirectorConfig(
        zones=(
            Zone(
                "woonkamer",
                "Woonkamer",
                "sensor.woonkamer",
                sources=(Source("w", LIVING),),
                heat=ModeSettings(23.0, 22.0),
            ),
        ),
        residents=(Resident("danny", "Danny", presence_entity="person.danny"),),
        gates=GateSettings(quiet_windows=windows),
    )


def verdict(config: DirectorConfig, hour: int, running: str, *, day: int = MONDAY):
    zone = config.zone("woonkamer")
    assert zone is not None
    world = make_world(
        now=datetime(2026, 8, day, hour, 0),
        indoor={"woonkamer": 18.0},
        climates={LIVING: running},
        residents={"danny": awake()},
        presence={"woonkamer": PresenceState(occupied=True)},
    )
    return gates.evaluate(config, world, zone)


class TestItBrakesStarting:
    @pytest.mark.parametrize("hour", [21, 23, 3, 8])
    def test_nothing_starts_inside_the_window(self, hour: int) -> None:
        assert verdict(house(*HIS), hour, "off").reason is Reason.QUIET_HOURS

    @pytest.mark.parametrize("hour", [9, 12, 17, 20])
    def test_outside_it_everything_is_normal(self, hour: int) -> None:
        assert verdict(house(*HIS), hour, "off").allowed

    def test_the_weekday_matters(self) -> None:
        """At 22:00 the week is quiet; Friday runs until eleven."""
        assert verdict(house(*HIS), 22, "off", day=MONDAY).reason is Reason.QUIET_HOURS
        assert verdict(house(*HIS), 22, "off", day=FRIDAY).allowed


class TestItDoesNotBrakeContinuing:
    @pytest.mark.parametrize("running", ["heat", "cool", "dry"])
    def test_something_already_running_stays_regulated(self, running: str) -> None:
        assert verdict(house(*HIS), 23, running).allowed

    def test_switching_it_on_yourself_is_picked_up(self) -> None:
        """The whole point: you may still decide to stay up."""
        assert verdict(house(*HIS), 2, "heat").allowed

    def test_fan_only_does_not_count_as_running(self) -> None:
        """Circulating air is not climate control, so it may not start either."""
        assert verdict(house(*HIS), 23, "fan_only").reason is Reason.QUIET_HOURS


class TestWithoutWindows:
    @pytest.mark.parametrize("hour", [0, 3, 12, 23])
    def test_the_brake_is_off(self, hour: int) -> None:
        assert verdict(house(), hour, "off").allowed


class TestItSurvivesStorage:
    def test_it_round_trips(self) -> None:
        config = house(*HIS)
        assert config_from_dict(config_to_dict(config)) == config

    def test_older_options_have_no_windows(self) -> None:
        assert config_from_dict({}).gates.quiet_windows == ()

    def test_rubbish_is_ignored(self) -> None:
        stored = config_from_dict({"gates": {"quiet_windows": ["nonsense", None, 42]}})
        assert stored.gates.quiet_windows == ()


class TestAnOpenScheduleWins:
    """Het rooster beschrijft juist het vroege uur; de stilte mag dat niet knijpen.

    De stilte is bedoeld voor thuiskomen op een uur waarop je zo naar bed gaat.
    Wie om vijf uur 's ochtends begint heeft dat in zijn rooster gezet omdat het
    vroeg is - dan zou een stiltevenster van 21:00 tot 09:00 precies het ritme
    afknijpen dat het rooster beschrijft.

    The quiet is meant for coming home at an hour when you are about to turn in.
    Whoever starts at five in the morning put that in their schedule because it
    is early - a quiet window from 21:00 to 09:00 would then pinch off the very
    rhythm the schedule describes.
    """

    #: Nancy staat op dinsdag en donderdag vroeg op.
    #: Nancy is up early on Tuesdays and Thursdays.
    nancy = Resident(
        "nancy",
        "Nancy",
        windows=(TimeWindow(time(5, 0), time(8, 0), frozenset({1, 3})),),
        presence_entity="person.nancy",
    )

    def _config(self) -> DirectorConfig:
        base = house(*HIS)
        return DirectorConfig(zones=base.zones, residents=(self.nancy,), gates=base.gates)

    def _verdict(self, hour: int, *, day: int, home: bool = True):
        from conftest import away

        config = self._config()
        zone = config.zone("woonkamer")
        assert zone is not None
        world = make_world(
            now=datetime(2026, 8, day, hour, 0),
            indoor={"woonkamer": 18.0},
            climates={LIVING: "off"},
            residents={"nancy": awake() if home else away()},
            presence={"woonkamer": PresenceState(occupied=True)},
        )
        return gates.evaluate(config, world, zone)

    def test_her_early_window_beats_the_quiet(self) -> None:
        """Tuesday 06:00: inside the quiet window, but her schedule is open."""
        assert self._verdict(6, day=18).allowed

    def test_outside_her_window_the_quiet_holds(self) -> None:
        """Tuesday 04:00: too early even for her."""
        assert self._verdict(4, day=18).reason is Reason.QUIET_HOURS

    def test_on_a_day_without_a_window_the_quiet_holds(self) -> None:
        """Wednesday 06:00: her window is Tuesday and Thursday only."""
        assert self._verdict(6, day=19).reason is Reason.QUIET_HOURS

    def test_the_evening_stays_quiet(self) -> None:
        """Tuesday 23:00: nobody's window is open, so coming home starts nothing."""
        assert self._verdict(23, day=18).reason is Reason.QUIET_HOURS

    def test_a_window_of_somebody_away_does_not_count(self) -> None:
        """Her schedule need not set the house going while she is out."""
        assert self._verdict(6, day=18, home=False).reason is Reason.QUIET_HOURS
