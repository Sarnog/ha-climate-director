"""Tests voor de poorten: mag er geregeld worden.

Tests for the gates: is regulating allowed.
"""

from __future__ import annotations

from datetime import timedelta

from conftest import (
    BACK_DOOR,
    asleep,
    at,
    awake,
    away,
    everyone_up,
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
    Zone,
    gates,
)


def living_room(config: DirectorConfig) -> Zone:
    zone = config.zone("woonkamer")
    assert zone is not None
    return zone


def test_allowed_when_someone_is_home_and_up() -> None:
    config = house()
    verdict = gates.evaluate(config, make_world(residents=everyone_up()), living_room(config))
    assert verdict.allowed


def test_master_switch_outranks_everything() -> None:
    config = house()
    world = make_world(residents=everyone_up(), master_enabled=False)
    verdict = gates.evaluate(config, world, living_room(config))
    assert not verdict.allowed
    assert verdict.reason is Reason.MASTER_DISABLED


def test_manual_override_blocks_its_own_zone_only() -> None:
    config = house()
    world = make_world(residents=everyone_up(), zone_overrides={"woonkamer": True})
    assert not gates.evaluate(config, world, living_room(config)).allowed
    attic = config.zone("zolder")
    assert attic is not None
    assert gates.evaluate(config, world, attic).allowed


def test_nobody_home() -> None:
    config = house()
    world = make_world(residents={"danny": away(), "nancy": away()})
    verdict = gates.evaluate(config, world, living_room(config))
    assert verdict.reason is Reason.NOBODY_HOME


def test_everyone_asleep() -> None:
    config = house()
    world = make_world(residents={"danny": asleep(), "nancy": away()})
    verdict = gates.evaluate(config, world, living_room(config))
    assert verdict.reason is Reason.EVERYONE_ASLEEP


def test_one_awake_is_enough() -> None:
    config = house()
    world = make_world(residents={"danny": asleep(), "nancy": awake()})
    assert gates.evaluate(config, world, living_room(config)).allowed


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
    assert gates.evaluate(relaxed, world, living_room(relaxed)).allowed


class TestOpenings:
    def test_open_long_enough_blocks(self) -> None:
        config = house()
        world = make_world(
            now=at(12, 1),
            residents=everyone_up(),
            openings={BACK_DOOR: OpeningState(open=True, changed_at=at(12, 0))},
        )
        verdict = gates.evaluate(config, world, living_room(config))
        assert verdict.reason is Reason.OPENING_OPEN

    def test_just_opened_does_not_block_yet(self) -> None:
        config = house()
        world = make_world(
            now=at(12, 0) + timedelta(seconds=5),
            residents=everyone_up(),
            openings={BACK_DOOR: OpeningState(open=True, changed_at=at(12, 0))},
        )
        assert gates.evaluate(config, world, living_room(config)).allowed

    def test_open_without_a_timestamp_blocks_immediately(self) -> None:
        """Suspending is the harmless direction to be wrong in."""
        config = house()
        world = make_world(
            residents=everyone_up(),
            openings={BACK_DOOR: OpeningState(open=True, changed_at=None)},
        )
        assert not gates.evaluate(config, world, living_room(config)).allowed

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
        verdict = gates.evaluate(config, world, living_room(config))
        assert verdict.reason is Reason.OPENING_OPEN

    def test_closed_opening_does_not_block(self) -> None:
        config = house()
        world = make_world(
            residents=everyone_up(),
            openings={BACK_DOOR: OpeningState(open=False, changed_at=at(11, 0))},
        )
        assert gates.evaluate(config, world, living_room(config)).allowed


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
        assert gates.evaluate(config, world, self._zone(config)).allowed

    def test_an_empty_room_is_left_alone(self) -> None:
        config = self._config()
        world = make_world(presence={"zolder": PresenceState(occupied=False)})
        verdict = gates.evaluate(config, world, self._zone(config))
        assert verdict.reason is Reason.ZONE_UNOCCUPIED

    def test_an_unknown_room_counts_as_empty(self) -> None:
        config = self._config()
        verdict = gates.evaluate(config, make_world(), self._zone(config))
        assert verdict.reason is Reason.ZONE_UNOCCUPIED

    def test_a_zone_without_a_presence_entity_is_never_held_back(self) -> None:
        """Not measuring a room is not the same as knowing it is empty."""
        zone = Zone("z", "Z", "sensor.t", sources=(Source("s", "climate.x"),))
        config = DirectorConfig(zones=(zone,))
        assert gates.evaluate(config, make_world(), zone).allowed

    def test_the_grace_period_rides_out_a_flicker(self) -> None:
        config = self._config(timedelta(minutes=5))
        world = make_world(
            now=at(12, 2),
            presence={"zolder": PresenceState(occupied=False, changed_at=at(12, 0))},
        )
        assert gates.evaluate(config, world, self._zone(config)).allowed

    def test_the_grace_period_expires(self) -> None:
        config = self._config(timedelta(minutes=5))
        world = make_world(
            now=at(12, 6),
            presence={"zolder": PresenceState(occupied=False, changed_at=at(12, 0))},
        )
        verdict = gates.evaluate(config, world, self._zone(config))
        assert verdict.reason is Reason.ZONE_UNOCCUPIED

    def test_without_a_timestamp_the_grace_period_cannot_be_claimed(self) -> None:
        config = self._config(timedelta(minutes=5))
        world = make_world(presence={"zolder": PresenceState(occupied=False, changed_at=None)})
        verdict = gates.evaluate(config, world, self._zone(config))
        assert verdict.reason is Reason.ZONE_UNOCCUPIED

    def test_presence_is_the_narrowest_gate(self) -> None:
        """Nobody home outranks nobody in the attic, since it explains more."""
        base = self._config()
        config = DirectorConfig(zones=base.zones, residents=(Resident("danny", "Danny"),))
        world = make_world(
            residents={"danny": away()},
            presence={"zolder": PresenceState(occupied=False)},
        )
        verdict = gates.evaluate(config, world, self._zone(config))
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
        assert gates.evaluate(config, make_world(), zone).allowed


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
        assert gates.evaluate(config, world, living_room(config)).allowed

    def test_outside_the_window(self) -> None:
        config = self._config()
        world = make_world(now=at(20, 0), residents=everyone_up())
        verdict = gates.evaluate(config, world, living_room(config))
        assert verdict.reason is Reason.OUTSIDE_SCHEDULE

    def test_holiday_mode_does_not_bypass_the_schedule(self) -> None:
        """A holiday counts as a Saturday, and a Saturday still has hours."""
        config = self._config()
        world = make_world(now=at(20, 0), residents=everyone_up(), holiday_mode=True)
        verdict = gates.evaluate(config, world, living_room(config))
        assert verdict.reason is Reason.OUTSIDE_SCHEDULE

    def test_guest_mode_sets_the_schedule_aside(self) -> None:
        config = self._config()
        world = make_world(now=at(20, 0), residents=everyone_up(), guest_mode=True)
        assert gates.evaluate(config, world, living_room(config)).allowed

    def test_holiday_mode_still_needs_someone_home(self) -> None:
        config = self._config()
        world = make_world(
            now=at(20, 0), residents={"danny": away(), "nancy": away()}, holiday_mode=True
        )
        verdict = gates.evaluate(config, world, living_room(config))
        assert verdict.reason is Reason.NOBODY_HOME

    def test_an_absent_person_does_not_open_the_schedule(self) -> None:
        config = self._config()
        world = make_world(now=at(9, 0), residents={"danny": away(), "nancy": awake()})
        assert gates.evaluate(config, world, living_room(config)).allowed
