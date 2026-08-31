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

    def test_a_holiday_counts_as_a_saturday(self) -> None:
        config = self._weekend_house()
        world = make_world(
            now=at(10, 0, day=10),
            residents={"danny": awake(), "nancy": asleep()},
            holiday_mode=True,
        )
        assert gate_verdict(config, world, living_room(config)).reason is (
            Reason.WAITING_FOR_SLEEPER
        )

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
