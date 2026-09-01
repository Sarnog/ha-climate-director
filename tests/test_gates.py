"""Tests voor de poorten: mag er geregeld worden.

Tests for the gates: is regulating allowed.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import time, timedelta

from conftest import (
    BACK_DOOR,
    asleep,
    at,
    awake,
    away,
    everyone_up,
    gate_verdict,
    house,
    make_world,
    office_hours,
)

from custom_components.climate_director.engine import (
    DirectorConfig,
    GateSettings,
    Opening,
    OpeningState,
    PresenceState,
    Reason,
    Resident,
    SleepIn,
    Source,
    TimeWindow,
    WakeDeadline,
    Zone,
)


def living_room(config: DirectorConfig) -> Zone:
    zone = config.zone("woonkamer")
    assert zone is not None
    return zone


def test_allowed_when_someone_is_home_and_up() -> None:
    config = house()
    verdict = gate_verdict(config, make_world(residents=everyone_up()), living_room(config))
    assert verdict.allowed


def test_master_switch_outranks_everything() -> None:
    config = house()
    world = make_world(residents=everyone_up(), master_enabled=False)
    verdict = gate_verdict(config, world, living_room(config))
    assert not verdict.allowed
    assert verdict.reason is Reason.MASTER_DISABLED


def test_manual_override_blocks_its_own_zone_only() -> None:
    config = house()
    world = make_world(residents=everyone_up(), zone_overrides={"woonkamer": True})
    assert not gate_verdict(config, world, living_room(config)).allowed
    attic = config.zone("zolder")
    assert attic is not None
    assert gate_verdict(config, world, attic).allowed


def test_nobody_home() -> None:
    config = house()
    world = make_world(residents={"danny": away(), "nancy": away()})
    verdict = gate_verdict(config, world, living_room(config))
    assert verdict.reason is Reason.NOBODY_HOME


def test_everyone_asleep() -> None:
    config = house()
    world = make_world(residents={"danny": asleep(), "nancy": away()})
    verdict = gate_verdict(config, world, living_room(config))
    assert verdict.reason is Reason.EVERYONE_ASLEEP


def test_one_awake_is_enough() -> None:
    config = house()
    world = make_world(residents={"danny": asleep(), "nancy": awake()})
    assert gate_verdict(config, world, living_room(config)).allowed


def test_sleep_gate_can_be_switched_off() -> None:
    config = house()
    relaxed = DirectorConfig(
        zones=config.zones,
        circuits=config.circuits,
        residents=config.residents,
        openings=config.openings,
        gates=GateSettings(require_awake=False),
    )
    world = make_world(residents={"danny": asleep(), "nancy": away()})
    assert gate_verdict(relaxed, world, living_room(relaxed)).allowed


def test_a_sleep_window_only_counts_on_its_own_days() -> None:
    """Weekendritme: de slaapsensor telt alleen in het weekend mee.

    Doordeweeks is een oplader op zaterdagochtend-uren gewoon een oplader, en
    dan hoort de slaappoort dicht te blijven.

    A weekend rhythm: the sleep sensor only counts at the weekend. On a working
    day a charger during those hours is just a charger, and then the sleep gate
    must stay out of it.
    """
    config = house()
    weekend = frozenset({5, 6})
    config = DirectorConfig(
        zones=config.zones,
        circuits=config.circuits,
        residents=tuple(
            Resident(
                resident_id=person.resident_id,
                name=person.name,
                sleep_window=TimeWindow(time(9, 0), time(12, 0), weekdays=weekend),
                presence_entity=person.presence_entity,
            )
            for person in config.residents
        ),
        openings=config.openings,
        gates=config.gates,
    )
    # 10 augustus 2026 is een maandag, 15 augustus een zaterdag.
    # 10 August 2026 is a Monday, 15 August a Saturday.
    monday = make_world(now=at(10, 0, day=10), residents={"danny": asleep(), "nancy": away()})
    saturday = make_world(now=at(10, 0, day=15), residents={"danny": asleep(), "nancy": away()})

    assert gate_verdict(config, monday, living_room(config)).allowed
    assert gate_verdict(config, saturday, living_room(config)).reason is Reason.EVERYONE_ASLEEP


class TestOpenings:
    def test_open_long_enough_blocks(self) -> None:
        config = house()
        world = make_world(
            now=at(12, 1),
            residents=everyone_up(),
            openings={BACK_DOOR: OpeningState(open=True, changed_at=at(12, 0))},
        )
        verdict = gate_verdict(config, world, living_room(config))
        assert verdict.reason is Reason.OPENING_OPEN

    def test_just_opened_does_not_block_yet(self) -> None:
        config = house()
        world = make_world(
            now=at(12, 0) + timedelta(seconds=5),
            residents=everyone_up(),
            openings={BACK_DOOR: OpeningState(open=True, changed_at=at(12, 0))},
        )
        assert gate_verdict(config, world, living_room(config)).allowed

    def test_open_without_a_timestamp_blocks_immediately(self) -> None:
        """Suspending is the harmless direction to be wrong in."""
        config = house()
        world = make_world(
            residents=everyone_up(),
            openings={BACK_DOOR: OpeningState(open=True, changed_at=None)},
        )
        assert not gate_verdict(config, world, living_room(config)).allowed

    def test_without_a_delay_it_blocks_the_moment_it_opens(self) -> None:
        """No delay given means no delay wanted, not half a minute of grace."""
        base = house()
        config = DirectorConfig(
            zones=base.zones,
            circuits=base.circuits,
            residents=base.residents,
            openings=(Opening(entity_id=BACK_DOOR),),
            gates=base.gates,
            outdoor_sensor=base.outdoor_sensor,
        )
        world = make_world(
            now=at(12, 0),
            residents=everyone_up(),
            openings={BACK_DOOR: OpeningState(open=True, changed_at=at(12, 0))},
        )
        verdict = gate_verdict(config, world, living_room(config))
        assert verdict.reason is Reason.OPENING_OPEN

    def test_closed_opening_does_not_block(self) -> None:
        config = house()
        world = make_world(
            residents=everyone_up(),
            openings={BACK_DOOR: OpeningState(open=False, changed_at=at(11, 0))},
        )
        assert gate_verdict(config, world, living_room(config)).allowed


class TestZonePresence:
    """The attic only wants heating when somebody is actually in it."""

    def _config(self, timeout: timedelta = timedelta(0)) -> DirectorConfig:
        zone = Zone(
            "zolder",
            "Zolder",
            "sensor.zolder",
            sources=(Source("s", "climate.zolder"),),
            presence_entity="binary_sensor.eplite_zolder_occupancy",
            presence_timeout=timeout,
        )
        return DirectorConfig(zones=(zone,))

    def _zone(self, config: DirectorConfig) -> Zone:
        zone = config.zone("zolder")
        assert zone is not None
        return zone

    def test_an_occupied_room_passes(self) -> None:
        config = self._config()
        world = make_world(presence={"zolder": PresenceState(occupied=True)})
        assert gate_verdict(config, world, self._zone(config)).allowed

    def test_an_empty_room_is_left_alone(self) -> None:
        config = self._config()
        world = make_world(presence={"zolder": PresenceState(occupied=False)})
        verdict = gate_verdict(config, world, self._zone(config))
        assert verdict.reason is Reason.ZONE_UNOCCUPIED

    def test_an_unknown_room_counts_as_empty(self) -> None:
        config = self._config()
        verdict = gate_verdict(config, make_world(), self._zone(config))
        assert verdict.reason is Reason.ZONE_UNOCCUPIED

    def test_a_zone_without_a_presence_entity_is_never_held_back(self) -> None:
        """Not measuring a room is not the same as knowing it is empty."""
        zone = Zone("z", "Z", "sensor.t", sources=(Source("s", "climate.x"),))
        config = DirectorConfig(zones=(zone,))
        assert gate_verdict(config, make_world(), zone).allowed

    def test_the_grace_period_rides_out_a_flicker(self) -> None:
        config = self._config(timedelta(minutes=5))
        world = make_world(
            now=at(12, 2),
            presence={"zolder": PresenceState(occupied=False, changed_at=at(12, 0))},
        )
        assert gate_verdict(config, world, self._zone(config)).allowed

    def test_the_grace_period_expires(self) -> None:
        config = self._config(timedelta(minutes=5))
        world = make_world(
            now=at(12, 6),
            presence={"zolder": PresenceState(occupied=False, changed_at=at(12, 0))},
        )
        verdict = gate_verdict(config, world, self._zone(config))
        assert verdict.reason is Reason.ZONE_UNOCCUPIED

    def test_without_a_timestamp_the_grace_period_cannot_be_claimed(self) -> None:
        config = self._config(timedelta(minutes=5))
        world = make_world(presence={"zolder": PresenceState(occupied=False, changed_at=None)})
        verdict = gate_verdict(config, world, self._zone(config))
        assert verdict.reason is Reason.ZONE_UNOCCUPIED

    def test_presence_is_the_narrowest_gate(self) -> None:
        """Nobody home outranks nobody in the attic, since it explains more."""
        base = self._config()
        config = DirectorConfig(zones=base.zones, residents=(Resident("danny", "Danny"),))
        world = make_world(
            residents={"danny": away()},
            presence={"zolder": PresenceState(occupied=False)},
        )
        verdict = gate_verdict(config, world, self._zone(config))
        assert verdict.reason is Reason.NOBODY_HOME


class TestNoResidents:
    def test_presence_gates_do_not_apply_without_residents(self) -> None:
        """An office or holiday home has nobody to track; do not lock it out."""
        config = DirectorConfig(
            zones=(Zone("a", "A", "sensor.a", sources=(Source("s", "climate.x"),)),),
            gates=GateSettings(require_awake=True),
        )
        zone = config.zone("a")
        assert zone is not None
        assert gate_verdict(config, make_world(), zone).allowed


class TestSchedule:
    def _config(self, **gate_kwargs: bool) -> DirectorConfig:
        base = house()
        return DirectorConfig(
            zones=base.zones,
            circuits=base.circuits,
            residents=(
                Resident("danny", "Danny", windows=office_hours()),
                Resident("nancy", "Nancy", windows=office_hours()),
            ),
            openings=base.openings,
            gates=GateSettings(require_schedule=True, **gate_kwargs),
        )

    def test_inside_the_window(self) -> None:
        config = self._config()
        world = make_world(now=at(9, 0), residents=everyone_up())
        assert gate_verdict(config, world, living_room(config)).allowed

    def test_outside_the_window(self) -> None:
        config = self._config()
        world = make_world(now=at(20, 0), residents=everyone_up())
        verdict = gate_verdict(config, world, living_room(config))
        assert verdict.reason is Reason.OUTSIDE_SCHEDULE

    def test_holiday_mode_does_not_bypass_the_schedule(self) -> None:
        """A holiday counts as a Saturday, and a Saturday still has hours."""
        config = self._config()
        world = make_world(now=at(20, 0), residents=everyone_up(), holiday_mode=True)
        verdict = gate_verdict(config, world, living_room(config))
        assert verdict.reason is Reason.OUTSIDE_SCHEDULE

    def test_guest_mode_sets_the_schedule_aside(self) -> None:
        config = self._config()
        world = make_world(now=at(20, 0), residents=everyone_up(), guest_mode=True)
        assert gate_verdict(config, world, living_room(config)).allowed

    def test_holiday_mode_still_needs_someone_home(self) -> None:
        config = self._config()
        world = make_world(
            now=at(20, 0), residents={"danny": away(), "nancy": away()}, holiday_mode=True
        )
        verdict = gate_verdict(config, world, living_room(config))
        assert verdict.reason is Reason.NOBODY_HOME

    def test_an_absent_person_does_not_open_the_schedule(self) -> None:
        config = self._config()
        world = make_world(now=at(9, 0), residents={"danny": away(), "nancy": awake()})
        assert gate_verdict(config, world, living_room(config)).allowed


class TestWaitingForSleeper:
    """De uiterste opsta-tijd: wachten op de laatste slaper, maar niet eeuwig.

    The wake deadline: waiting for the last sleeper, though not forever.
    """

    @staticmethod
    def _with_deadlines(config: DirectorConfig, **deadlines: WakeDeadline | None) -> DirectorConfig:
        """Return the same house with a wake deadline per resident."""
        return replace(
            config,
            residents=tuple(
                replace(resident, wake_deadline=deadlines.get(resident.resident_id))
                for resident in config.residents
            ),
        )

    def _weekend_house(self) -> DirectorConfig:
        eleven = WakeDeadline(at=time(11, 0), weekdays=frozenset({5, 6}))
        return self._with_deadlines(house(), danny=eleven, nancy=eleven)

    def test_without_a_deadline_the_first_one_up_decides(self) -> None:
        config = house()
        world = make_world(now=at(10, 0, day=15), residents={"danny": awake(), "nancy": asleep()})
        assert gate_verdict(config, world, living_room(config)).allowed

    def test_waits_while_the_other_is_still_in_bed(self) -> None:
        config = self._weekend_house()
        world = make_world(now=at(10, 0, day=15), residents={"danny": awake(), "nancy": asleep()})
        verdict = gate_verdict(config, world, living_room(config))
        assert verdict.reason is Reason.WAITING_FOR_SLEEPER

    def test_waking_up_early_releases_the_house(self) -> None:
        config = self._weekend_house()
        world = make_world(now=at(10, 30, day=15), residents=everyone_up())
        assert gate_verdict(config, world, living_room(config)).allowed

    def test_the_deadline_releases_the_house_on_its_own(self) -> None:
        config = self._weekend_house()
        world = make_world(now=at(11, 0, day=15), residents={"danny": awake(), "nancy": asleep()})
        assert gate_verdict(config, world, living_room(config)).allowed

    def test_it_works_the_other_way_round_too(self) -> None:
        config = self._weekend_house()
        early = make_world(now=at(10, 0, day=15), residents={"danny": asleep(), "nancy": awake()})
        late = make_world(now=at(11, 0, day=15), residents={"danny": asleep(), "nancy": awake()})
        assert gate_verdict(config, early, living_room(config)).reason is (
            Reason.WAITING_FOR_SLEEPER
        )
        assert gate_verdict(config, late, living_room(config)).allowed

    def test_a_sleeper_who_is_out_holds_nobody(self) -> None:
        config = self._weekend_house()
        world = make_world(
            now=at(10, 0, day=15), residents={"danny": awake(), "nancy": asleep(home=False)}
        )
        assert gate_verdict(config, world, living_room(config)).allowed

    def test_nobody_up_reads_as_everyone_asleep(self) -> None:
        """Anders zou een gevolg voor een oorzaak doorgaan.

        Otherwise a consequence would pass for a cause.
        """
        config = self._weekend_house()
        world = make_world(now=at(10, 0, day=15), residents={"danny": asleep(), "nancy": asleep()})
        assert gate_verdict(config, world, living_room(config)).reason is Reason.EVERYONE_ASLEEP

    def test_the_deadline_only_counts_on_its_own_days(self) -> None:
        """10 augustus 2026 is een maandag; het weekendrooster raakt hem niet.

        10 August 2026 is a Monday; the weekend arrangement does not touch it.
        """
        config = self._weekend_house()
        world = make_world(now=at(10, 0, day=10), residents={"danny": awake(), "nancy": asleep()})
        assert gate_verdict(config, world, living_room(config)).allowed

    def test_a_holiday_weekday_is_not_a_saturday(self) -> None:
        """De schoolvakantie van de één is de werkdag van de ander.

        Telde een vakantiedag hier als zaterdag, dan hield de uitslaper het huis
        op terwijl de ander gewoon thuis zat te werken. De dagen betekenen dus
        wat er staat; wie ook op een vakantiedag gewacht wil worden, vinkt dat
        aan - zie de test hieronder.

        One person's school holiday is another's working day. Were a holiday to
        count as a Saturday here, the late riser would hold the house up while
        the other was simply working from home. So the days mean what they say;
        whoever wants to be waited for on a holiday too ticks that - see the
        test below.
        """
        config = self._weekend_house()
        world = make_world(
            now=at(10, 0, day=10),
            residents={"danny": awake(), "nancy": asleep()},
            holiday_mode=True,
        )
        assert gate_verdict(config, world, living_room(config)).allowed

    def test_a_holiday_saturday_is_still_a_saturday(self) -> None:
        """Anders zou een vakantieweek het weekend anders laten werken.

        Otherwise a week off would make the weekend behave differently.
        """
        config = self._weekend_house()
        for holiday in (False, True):
            world = make_world(
                now=at(10, 0, day=15),
                residents={"danny": awake(), "nancy": asleep()},
                holiday_mode=holiday,
            )
            assert gate_verdict(config, world, living_room(config)).reason is (
                Reason.WAITING_FOR_SLEEPER
            ), holiday

    def test_the_holiday_tick_makes_it_count_on_any_holiday(self) -> None:
        """Wie ook op een vrije doordeweekse dag gewacht wil worden, zegt dat.

        Whoever wants to be waited for on a weekday off says so.
        """
        eleven = WakeDeadline(at=time(11, 0), weekdays=frozenset({5, 6}), holiday=True)
        config = self._with_deadlines(house(), danny=eleven, nancy=eleven)
        monday = make_world(
            now=at(10, 0, day=10),
            residents={"danny": awake(), "nancy": asleep()},
            holiday_mode=True,
        )
        assert gate_verdict(config, monday, living_room(config)).reason is (
            Reason.WAITING_FOR_SLEEPER
        )
        # Zonder vakantie blijft de maandag een gewone maandag.
        # Without a holiday the Monday stays an ordinary Monday.
        ordinary = make_world(
            now=at(10, 0, day=10), residents={"danny": awake(), "nancy": asleep()}
        )
        assert gate_verdict(config, ordinary, living_room(config)).allowed

    def test_one_resident_may_be_waited_for_and_the_other_not(self) -> None:
        config = self._with_deadlines(house(), nancy=WakeDeadline(at=time(11, 0)), danny=None)
        waiting = make_world(now=at(10, 0, day=15), residents={"danny": awake(), "nancy": asleep()})
        free = make_world(now=at(10, 0, day=15), residents={"danny": asleep(), "nancy": awake()})
        assert gate_verdict(config, waiting, living_room(config)).reason is (
            Reason.WAITING_FOR_SLEEPER
        )
        assert gate_verdict(config, free, living_room(config)).allowed

    def test_the_sleep_gate_switched_off_switches_the_waiting_off_too(self) -> None:
        """Zonder slaappoort zegt slapen niets, en dan zegt de uiterste tijd niets.

        Without the sleep gate, sleeping says nothing, and then the deadline
        says nothing either.
        """
        config = self._weekend_house()
        relaxed = replace(config, gates=GateSettings(require_awake=False))
        world = make_world(now=at(10, 0, day=15), residents={"danny": awake(), "nancy": asleep()})
        assert gate_verdict(relaxed, world, living_room(config)).allowed


class TestSleepingIn:
    """Het uitslapen rekt de ochtend op, en alleen op de dagen die dat mogen.

    Sleeping in stretches the morning, and only on the days that allow it.
    """

    @staticmethod
    def _house(sleep_in: SleepIn | None, window: TimeWindow) -> DirectorConfig:
        config = house()
        return replace(
            config,
            residents=tuple(
                replace(resident, sleep_window=window, sleep_in=sleep_in)
                for resident in config.residents
            ),
        )

    def _night(self) -> TimeWindow:
        return TimeWindow(start=time(21, 0), end=time(8, 0))

    def _weekend(self) -> SleepIn:
        return SleepIn(until=time(13, 0), weekdays=frozenset({5, 6}))

    def test_without_sleeping_in_the_window_is_the_whole_story(self) -> None:
        config = self._house(None, self._night())
        world = make_world(now=at(10, 0, day=15), residents={"danny": asleep(), "nancy": away()})
        assert gate_verdict(config, world, living_room(config)).allowed

    def test_the_morning_is_stretched_on_a_day_that_allows_it(self) -> None:
        """15 augustus 2026 is een zaterdag. 15 August 2026 is a Saturday."""
        config = self._house(self._weekend(), self._night())
        world = make_world(now=at(10, 0, day=15), residents={"danny": asleep(), "nancy": away()})
        assert gate_verdict(config, world, living_room(config)).reason is Reason.EVERYONE_ASLEEP

    def test_it_stops_at_the_hour_that_was_given(self) -> None:
        config = self._house(self._weekend(), self._night())
        world = make_world(now=at(13, 0, day=15), residents={"danny": asleep(), "nancy": away()})
        assert gate_verdict(config, world, living_room(config)).allowed

    def test_an_ordinary_weekday_is_not_stretched(self) -> None:
        """Anders blijft het huis uit terwijl er iemand thuis zit te werken.

        Otherwise the house stays off while somebody is working from home.
        """
        config = self._house(self._weekend(), self._night())
        world = make_world(now=at(10, 0, day=10), residents={"danny": asleep(), "nancy": away()})
        assert gate_verdict(config, world, living_room(config)).allowed

    def test_the_night_still_switches_the_house_off(self) -> None:
        """Het slaapvenster blijft doen wat het deed, op elke dag.

        The sleep window keeps doing what it did, on every day.
        """
        config = self._house(self._weekend(), self._night())
        world = make_world(now=at(23, 0, day=10), residents={"danny": asleep(), "nancy": away()})
        assert gate_verdict(config, world, living_room(config)).reason is Reason.EVERYONE_ASLEEP

    def test_the_holiday_tick_stretches_any_holiday(self) -> None:
        config = self._house(
            SleepIn(until=time(13, 0), weekdays=frozenset({5, 6}), holiday=True), self._night()
        )
        monday = make_world(
            now=at(10, 0, day=10), residents={"danny": asleep(), "nancy": away()}, holiday_mode=True
        )
        assert gate_verdict(config, monday, living_room(config)).reason is Reason.EVERYONE_ASLEEP

    def test_without_the_tick_a_holiday_weekday_is_an_ordinary_weekday(self) -> None:
        config = self._house(self._weekend(), self._night())
        monday = make_world(
            now=at(10, 0, day=10), residents={"danny": asleep(), "nancy": away()}, holiday_mode=True
        )
        assert gate_verdict(config, monday, living_room(config)).allowed

    def test_sleeping_in_and_the_deadline_work_together(self) -> None:
        """Uitslapen zegt hoe lang slaap telt, de uiterste tijd hoe lang je wacht.

        Sleeping in says how long sleep counts, the deadline how long you wait.
        """
        config = replace(
            self._house(self._weekend(), self._night()),
            residents=tuple(
                replace(
                    resident,
                    sleep_window=self._night(),
                    sleep_in=self._weekend(),
                    wake_deadline=WakeDeadline(at=time(11, 0), weekdays=frozenset({5, 6})),
                )
                for resident in house().residents
            ),
        )
        zone = living_room(config)
        # Eén op, één in bed: wachten tot de uiterste tijd.
        waiting = make_world(now=at(10, 0, day=15), residents={"danny": awake(), "nancy": asleep()})
        assert gate_verdict(config, waiting, zone).reason is Reason.WAITING_FOR_SLEEPER
        released = make_world(
            now=at(11, 0, day=15), residents={"danny": awake(), "nancy": asleep()}
        )
        assert gate_verdict(config, released, zone).allowed
        # Allebei in bed: het huis wacht op de eerste die werkelijk opstaat.
        both = make_world(now=at(11, 0, day=15), residents={"danny": asleep(), "nancy": asleep()})
        assert gate_verdict(config, both, zone).reason is Reason.EVERYONE_ASLEEP
        assert (
            gate_verdict(
                config,
                make_world(
                    now=at(12, 30, day=15), residents={"danny": asleep(), "nancy": asleep()}
                ),
                zone,
            ).reason
            is Reason.EVERYONE_ASLEEP
        )
