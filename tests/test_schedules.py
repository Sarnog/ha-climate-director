"""De roosterpoort, uitgeschreven met de gevallen die hem bepalen.

The schedule gate, written out with the cases that define it.

Een rooster hoort bij een bewoner en niet bij een ruimte, en het gaat over
wanneer iemand wil dat het huis meedoet. Twee regels maken het geheel:
wie geen rooster heeft doet niet mee, en wie thuis nog slaapt terwijl zijn eigen
venster nog niet open is houdt het huis tegen.

A schedule belongs to a resident rather than to a room, and it is about when
somebody wants the house to join in. Two rules make the whole: whoever has no
schedule does not take part, and whoever is home asleep while their own window
has not opened yet holds the house back.
"""

from __future__ import annotations

from datetime import datetime, time

import pytest
from conftest import asleep, awake, away, make_world

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

WEEKDAYS = frozenset({0, 1, 2, 3, 4})
WEEKEND = frozenset({5, 6})

#: 11 augustus 2026 is een dinsdag, 15 augustus een zaterdag.
#: 11 August 2026 is a Tuesday, 15 August a Saturday.
TUESDAY = 11
SATURDAY = 15


def at(hour: int, minute: int = 0, *, day: int = TUESDAY) -> datetime:
    return datetime(2026, 8, day, hour, minute)


def household(*residents: Resident) -> DirectorConfig:
    """Return an installation whose only gate that matters is the schedule."""
    return DirectorConfig(
        zones=(
            Zone(
                "woonkamer",
                "Woonkamer",
                "sensor.woonkamer",
                sources=(Source("s", "climate.huiskamer"),),
                heat=ModeSettings(21.0, 20.0),
            ),
        ),
        residents=residents,
        gates=GateSettings(require_awake=True, require_schedule=True),
    )


def verdict(config: DirectorConfig, moment: datetime, **states: object):
    return _verdict(config, moment, states)


def holiday_verdict(config: DirectorConfig, moment: datetime, **states: object):
    return _verdict(config, moment, states, holiday_mode=True)


def guest_verdict(config: DirectorConfig, moment: datetime, **states: object):
    return _verdict(config, moment, states, guest_mode=True)


def _verdict(config: DirectorConfig, moment: datetime, states: dict[str, object], **flags: bool):
    zone = config.zone("woonkamer")
    assert zone is not None
    world = make_world(now=moment, residents=states, **flags)  # type: ignore[arg-type]
    return gates.evaluate(config, world, zone)


NANCY_TUESDAY = Resident(
    "nancy",
    "Nancy",
    windows=(TimeWindow(time(5, 0), time(9, 30), frozenset({1})),),
    presence_entity="person.nancy",
)
DANNY_NO_SCHEDULE = Resident("danny", "Danny", presence_entity="person.danny")


class TestARegisteredScheduleStarts:
    """Nancy is up at 08:45 on a Tuesday, inside her window."""

    def test_it_opens(self) -> None:
        config = household(NANCY_TUESDAY)
        assert verdict(config, at(8, 45), nancy=awake()).allowed

    def test_outside_her_hours_it_stays_shut(self) -> None:
        config = household(NANCY_TUESDAY)
        assert verdict(config, at(10, 0), nancy=awake()).reason is Reason.OUTSIDE_SCHEDULE

    def test_on_a_day_she_has_no_window_it_stays_shut(self) -> None:
        config = household(NANCY_TUESDAY)
        assert verdict(config, at(8, 45, day=SATURDAY), nancy=awake()).reason is (
            Reason.OUTSIDE_SCHEDULE
        )


class TestSomebodyWithoutASchedule:
    """Danny said nothing about when he wants the house to join in."""

    def test_him_getting_up_alone_does_nothing(self) -> None:
        config = household(DANNY_NO_SCHEDULE)
        assert verdict(config, at(8, 45), danny=awake()).reason is Reason.OUTSIDE_SCHEDULE

    def test_he_does_not_hold_the_house_back_either(self) -> None:
        """Silence is not a vote either way: Nancy's window still counts."""
        config = household(NANCY_TUESDAY, DANNY_NO_SCHEDULE)
        assert verdict(config, at(8, 45), nancy=awake(), danny=asleep()).allowed


class TestTheWeekendWait:
    """Danny is up early, Nancy is not. The house waits for her."""

    danny = Resident(
        "danny",
        "Danny",
        windows=(TimeWindow(time(8, 0), time(15, 0), WEEKEND),),
        presence_entity="person.danny",
    )
    nancy = Resident(
        "nancy",
        "Nancy",
        windows=(TimeWindow(time(11, 0), time(15, 0), WEEKEND),),
        presence_entity="person.nancy",
    )

    def config(self) -> DirectorConfig:
        return household(self.danny, self.nancy)

    def test_it_waits_while_she_sleeps_before_her_window(self) -> None:
        result = verdict(self.config(), at(9, 0, day=SATURDAY), danny=awake(), nancy=asleep())
        assert result.reason is Reason.OUTSIDE_SCHEDULE

    def test_it_starts_once_she_is_up(self) -> None:
        assert verdict(self.config(), at(9, 0, day=SATURDAY), danny=awake(), nancy=awake()).allowed

    def test_it_starts_at_eleven_even_if_she_sleeps_on(self) -> None:
        """Her own window opening says she meant to be up by then."""
        assert verdict(
            self.config(), at(11, 0, day=SATURDAY), danny=awake(), nancy=asleep()
        ).allowed

    def test_with_her_away_it_starts_when_he_gets_up(self) -> None:
        assert verdict(self.config(), at(9, 0, day=SATURDAY), danny=awake(), nancy=away()).allowed

    def test_he_still_has_to_be_up_himself(self) -> None:
        result = verdict(self.config(), at(9, 0, day=SATURDAY), danny=asleep(), nancy=away())
        assert not result.allowed


class TestNobodyScheduledAtAll:
    def test_the_gate_stays_shut(self) -> None:
        """Turning the gate on with no schedules is a mistake, not a free pass."""
        config = household(DANNY_NO_SCHEDULE)
        assert verdict(config, at(12, 0), danny=awake()).reason is Reason.OUTSIDE_SCHEDULE

    @pytest.mark.parametrize("hour", [0, 6, 12, 18, 23])
    def test_at_no_hour_of_the_day(self, hour: int) -> None:
        config = household(DANNY_NO_SCHEDULE)
        assert not verdict(config, at(hour), danny=awake()).allowed


class TestHolidayMode:
    """A holiday is a Saturday, unless somebody wrote a holiday window."""

    def test_a_weekend_window_applies_on_a_holiday_weekday(self) -> None:
        """Nancy's Saturday hours hold on a Tuesday once the house is on holiday."""
        weekender = Resident(
            "nancy",
            "Nancy",
            windows=(TimeWindow(time(11, 0), time(15, 0), WEEKEND),),
            presence_entity="person.nancy",
        )
        config = household(weekender)
        assert not verdict(config, at(12, 0), nancy=awake()).allowed
        assert holiday_verdict(config, at(12, 0), nancy=awake()).allowed

    def test_a_weekday_window_stops_applying(self) -> None:
        """A holiday is not a working day, so Nancy's Tuesday hours do not hold."""
        config = household(NANCY_TUESDAY)
        assert holiday_verdict(config, at(8, 45), nancy=awake()).reason is (Reason.OUTSIDE_SCHEDULE)

    def test_the_weekend_wait_still_holds(self) -> None:
        """The house waits for the late sleeper on a holiday just as on a Saturday."""
        config = household(
            Resident(
                "danny",
                "Danny",
                windows=(TimeWindow(time(8, 0), time(15, 0), WEEKEND),),
                presence_entity="person.danny",
            ),
            Resident(
                "nancy",
                "Nancy",
                windows=(TimeWindow(time(11, 0), time(15, 0), WEEKEND),),
                presence_entity="person.nancy",
            ),
        )
        early = holiday_verdict(config, at(9, 0), danny=awake(), nancy=asleep())
        assert early.reason is Reason.OUTSIDE_SCHEDULE
        assert holiday_verdict(config, at(11, 0), danny=awake(), nancy=asleep()).allowed


class TestAHolidayWindow:
    """A window marked as a holiday window takes over from the ordinary ones."""

    nancy = Resident(
        "nancy",
        "Nancy",
        windows=(
            TimeWindow(time(11, 0), time(15, 0), WEEKEND),
            TimeWindow(time(6, 0), time(23, 0), holiday=True),
        ),
        presence_entity="person.nancy",
    )

    def test_it_replaces_the_ordinary_windows(self) -> None:
        config = household(self.nancy)
        assert holiday_verdict(config, at(7, 0), nancy=awake()).allowed

    def test_it_ignores_its_days_of_the_week(self) -> None:
        """A holiday is not a day of the week, so a Tuesday holiday counts too."""
        nancy = Resident(
            "nancy",
            "Nancy",
            windows=(TimeWindow(time(6, 0), time(23, 0), WEEKEND, holiday=True),),
            presence_entity="person.nancy",
        )
        assert holiday_verdict(household(nancy), at(7, 0), nancy=awake()).allowed

    def test_it_does_nothing_on_an_ordinary_day(self) -> None:
        config = household(self.nancy)
        assert verdict(config, at(7, 0, day=SATURDAY), nancy=awake()).reason is (
            Reason.OUTSIDE_SCHEDULE
        )

    def test_somebody_with_only_a_holiday_window_sits_out_ordinary_days(self) -> None:
        """He said nothing about working days, so he neither opens nor blocks."""
        danny = Resident(
            "danny",
            "Danny",
            windows=(TimeWindow(time(6, 0), time(23, 0), holiday=True),),
            presence_entity="person.danny",
        )
        config = household(NANCY_TUESDAY, danny)
        assert verdict(config, at(8, 45), nancy=awake(), danny=asleep()).allowed


class TestSomebodyMustBeHome:
    """Nothing may start on an empty house, whatever else says otherwise."""

    def test_an_open_window_is_not_enough(self) -> None:
        config = household(NANCY_TUESDAY)
        assert verdict(config, at(8, 45), nancy=away()).reason is Reason.NOBODY_HOME

    def test_guest_mode_carries_the_house_instead(self) -> None:
        """Somebody is staying who is not tracked, so absence says nothing."""
        config = household(NANCY_TUESDAY)
        assert guest_verdict(config, at(8, 45), nancy=away()).allowed

    def test_guest_mode_also_sets_the_schedule_aside(self) -> None:
        """A guest keeps their own hours, and the residents' windows are not theirs."""
        config = household(NANCY_TUESDAY)
        assert guest_verdict(config, at(3, 0), nancy=away()).allowed

    def test_guest_mode_leaves_the_room_gate_alone(self) -> None:
        """Guest mode is about people, not about which rooms are in use."""
        config = household(NANCY_TUESDAY)
        zone = config.zone("woonkamer")
        assert zone is not None
        empty = Zone(
            zone.zone_id,
            zone.name,
            zone.indoor_sensor,
            sources=zone.sources,
            heat=zone.heat,
            presence_entity="binary_sensor.woonkamer",
        )
        world = make_world(now=at(12, 0), residents={"nancy": away()}, guest_mode=True)
        assert gates.evaluate(config, world, empty).reason is Reason.ZONE_UNOCCUPIED


class TestOnlyTodaysSchedulesCount:
    """A window on other days says nothing about today, blocking included.

    De regel "wie thuis is en slaapt terwijl zijn eigen venster nog niet open is
    houdt het huis tegen" is bedoeld voor de zaterdagochtend, waar iedereen een
    venster heeft. Wie op een dag helemaal geen venster heeft, hoort die dag
    niet mee te doen - anders houdt een bewoner met alleen weekendvensters het
    huis elke doordeweekse ochtend tegen tot hij wakker wordt, en dat is geen
    rooster maar een slot.

    The rule "whoever is home asleep while their own window has not opened holds
    the house back" is meant for a Saturday morning, where everybody has a
    window. Somebody with no window at all on a given day should not take part
    that day - otherwise a resident with weekend windows only holds the house
    back every weekday morning until they wake, which is not a schedule but a
    lock.
    """

    weekender = Resident(
        "danny",
        "Danny",
        windows=(TimeWindow(time(8, 0), time(15, 0), WEEKEND),),
        presence_entity="person.danny",
    )
    early = Resident(
        "nancy",
        "Nancy",
        windows=(TimeWindow(time(5, 0), time(8, 0), frozenset({1})),),
        presence_entity="person.nancy",
    )

    def config(self) -> DirectorConfig:
        return household(self.weekender, self.early)

    def test_a_weekend_sleeper_no_longer_blocks_a_weekday(self) -> None:
        """The case from the live installation: her window opens, he sleeps on."""
        result = verdict(self.config(), at(6, 0), danny=asleep(), nancy=awake())
        assert result.allowed

    def test_he_still_does_not_open_it_himself(self) -> None:
        """Saying nothing cuts both ways: no block, and no opening either."""
        result = verdict(self.config(), at(9, 0), danny=awake(), nancy=awake())
        assert result.reason is Reason.OUTSIDE_SCHEDULE

    def test_the_weekend_wait_is_untouched(self) -> None:
        """Both have a Saturday window, so there the rule still holds."""
        config = household(
            self.weekender,
            Resident(
                "nancy",
                "Nancy",
                windows=(TimeWindow(time(11, 0), time(15, 0), WEEKEND),),
                presence_entity="person.nancy",
            ),
        )
        early = verdict(config, at(9, 0, day=SATURDAY), danny=awake(), nancy=asleep())
        assert early.reason is Reason.OUTSIDE_SCHEDULE
        assert verdict(config, at(11, 0, day=SATURDAY), danny=awake(), nancy=asleep()).allowed

    def test_a_window_crossing_midnight_still_counts_the_next_morning(self) -> None:
        """A Monday night window runs into Tuesday, so Tuesday is still their day."""
        night = Resident(
            "nancy",
            "Nancy",
            windows=(TimeWindow(time(22, 0), time(6, 0), frozenset({0})),),
            presence_entity="person.nancy",
        )
        assert night.takes_part(holiday=False, weekday=1)
        assert not night.takes_part(holiday=False, weekday=3)

    def test_a_resident_without_any_schedule_is_unchanged(self) -> None:
        config = household(NANCY_TUESDAY, DANNY_NO_SCHEDULE)
        assert verdict(config, at(8, 45), nancy=awake(), danny=asleep()).allowed
