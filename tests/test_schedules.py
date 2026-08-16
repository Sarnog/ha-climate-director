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
        gates=GateSettings(require_occupancy=True, require_awake=True, require_schedule=True),
    )


def verdict(config: DirectorConfig, moment: datetime, **states: object):
    zone = config.zone("woonkamer")
    assert zone is not None
    world = make_world(now=moment, residents=dict(states))  # type: ignore[arg-type]
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
    def test_it_skips_the_schedule_entirely(self) -> None:
        config = household(NANCY_TUESDAY)
        zone = config.zone("woonkamer")
        assert zone is not None
        world = make_world(now=at(23, 0), residents={"nancy": awake()}, holiday_mode=True)
        assert gates.evaluate(config, world, zone).allowed
