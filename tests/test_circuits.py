"""Tests voor koelcircuits: wat mag er tegelijk draaien op één buitenunit.

Tests for refrigerant circuits: what may run at once on one outdoor unit.

De vier installatievoorbeelden uit het ontwerpgesprek staan hier uitgeschreven
als scenario's, zodat de belofte "elk patroon van buitenunits is uit te
drukken" bewijsbaar blijft in plaats van een bewering.

The four installation examples from the design discussion are written out here
as scenarios, so the promise "any pattern of outdoor units can be expressed"
stays provable rather than merely claimed.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from conftest import at, climate, make_world

from custom_components.climate_director.engine import (
    MODE_COOL,
    MODE_FAN_ONLY,
    MODE_HEAT,
    MODE_OFF,
    Circuit,
    ConflictPolicy,
    DirectorConfig,
    ModeFamily,
    ModeSettings,
    Reason,
    Season,
    Source,
    Zone,
    constraints,
    decide,
)

HEAT_SETTINGS = ModeSettings(target=21.0, start_at=20.0, hysteresis=1.0)
COOL_SETTINGS = ModeSettings(target=22.0, start_at=24.0, hysteresis=1.0)

#: Indoor temperatures that unambiguously ask for one duty.
WANTS_HEAT = 18.0
WANTS_COOL = 26.0


def unit(name: str) -> str:
    """Return the climate entity id for a room."""
    return f"climate.{name}"


def rooms(*names: str) -> tuple[Zone, ...]:
    """Return one zone per room, ranked in the order given."""
    return tuple(
        Zone(
            zone_id=name,
            name=name.replace("_", " ").title(),
            indoor_sensor=f"sensor.{name}",
            priority=index,
            sources=(Source(source_id=f"{name}_unit", entity_id=unit(name)),),
            heat=HEAT_SETTINGS,
            cool=COOL_SETTINGS,
        )
        for index, name in enumerate(names)
    )


def multi_split(circuit_id: str, *names: str, **kwargs: object) -> Circuit:
    """Return a multi-split circuit: one outdoor unit, one duty at a time."""
    return Circuit(
        circuit_id=circuit_id,
        name=circuit_id,
        units=tuple(unit(name) for name in names),
        simultaneous_heat_cool=False,
        **kwargs,  # type: ignore[arg-type]
    )


def run(config: DirectorConfig, temperatures: dict[str, float], **world_kwargs: object):
    """Run a decision and return the commanded mode per climate entity."""
    world = make_world(
        indoor=dict(temperatures),
        climates={
            unit(name): climate(world_kwargs.pop(f"{name}_mode", "off"))  # type: ignore[arg-type]
            for name in temperatures
        },
        **world_kwargs,  # type: ignore[arg-type]
    )
    plan = decide(config, world)
    return {command.entity_id: command.hvac_mode for command in plan.commands}, plan


# ---------------------------------------------------------------------------
# Voorbeeld A: één multi-split met drie binnenunits.
# Example A: one multi-split with three indoor units.
# ---------------------------------------------------------------------------


def example_a() -> DirectorConfig:
    return DirectorConfig(
        zones=rooms("woonkamer", "zolder", "slaapkamer"),
        circuits=(multi_split("multisplit", "woonkamer", "zolder", "slaapkamer"),),
    )


class TestExampleA:
    """One outdoor unit, three indoor units: one duty across all of them."""

    temperatures = {
        "woonkamer": WANTS_HEAT,
        "zolder": WANTS_COOL,
        "slaapkamer": WANTS_COOL,
    }

    def test_the_preferred_zone_takes_the_circuit(self) -> None:
        modes, _ = run(example_a(), self.temperatures)
        assert modes[unit("woonkamer")] == MODE_HEAT

    def test_the_others_may_only_heat_be_off_or_circulate(self) -> None:
        modes, _ = run(example_a(), self.temperatures)
        allowed = {MODE_HEAT, MODE_OFF, MODE_FAN_ONLY}
        assert modes[unit("zolder")] in allowed
        assert modes[unit("slaapkamer")] in allowed

    def test_nobody_cools_while_the_circuit_heats(self) -> None:
        modes, _ = run(example_a(), self.temperatures)
        assert MODE_COOL not in modes.values()

    def test_losers_are_told_why(self) -> None:
        _, plan = run(example_a(), self.temperatures)
        attic = plan.decision_for("zolder")
        assert attic is not None
        assert attic.wanted is ModeFamily.COOL
        assert attic.granted is ModeFamily.NEUTRAL
        assert attic.reason is Reason.CIRCUIT_CONFLICT_LOST

    def test_agreeing_zones_all_run(self) -> None:
        modes, _ = run(
            example_a(),
            {"woonkamer": WANTS_COOL, "zolder": WANTS_COOL, "slaapkamer": WANTS_COOL},
        )
        assert all(mode == MODE_COOL for mode in modes.values())

    def test_fan_only_is_offered_when_configured(self) -> None:
        config = DirectorConfig(
            zones=rooms("woonkamer", "zolder", "slaapkamer"),
            circuits=(
                multi_split(
                    "multisplit",
                    "woonkamer",
                    "zolder",
                    "slaapkamer",
                    allow_fan_only_during_conflict=True,
                ),
            ),
        )
        modes, _ = run(config, self.temperatures)
        assert modes[unit("zolder")] == MODE_FAN_ONLY

    def test_a_satisfied_zone_is_switched_off_not_left_circulating(self) -> None:
        """Fan-only is for losing a conflict, not for being comfortable."""
        config = DirectorConfig(
            zones=rooms("woonkamer", "zolder", "slaapkamer"),
            circuits=(
                multi_split(
                    "multisplit",
                    "woonkamer",
                    "zolder",
                    "slaapkamer",
                    allow_fan_only_during_conflict=True,
                ),
            ),
        )
        modes, _ = run(
            config,
            {"woonkamer": WANTS_HEAT, "zolder": 21.0, "slaapkamer": 21.0},
        )
        assert modes[unit("zolder")] == MODE_OFF


# ---------------------------------------------------------------------------
# Voorbeeld B: drie losse splitunits, elk een eigen buitenunit.
# Example B: three separate single splits, each with its own outdoor unit.
# ---------------------------------------------------------------------------


def example_b() -> DirectorConfig:
    return DirectorConfig(zones=rooms("woonkamer", "zolder", "slaapkamer"))


class TestExampleB:
    """No circuits configured: every unit is free, which is the safe default."""

    def test_every_room_does_its_own_thing(self) -> None:
        modes, _ = run(
            example_b(),
            {"woonkamer": WANTS_HEAT, "zolder": WANTS_COOL, "slaapkamer": WANTS_COOL},
        )
        assert modes[unit("woonkamer")] == MODE_HEAT
        assert modes[unit("zolder")] == MODE_COOL
        assert modes[unit("slaapkamer")] == MODE_COOL

    def test_heating_and_cooling_run_side_by_side(self) -> None:
        modes, _ = run(
            example_b(),
            {"woonkamer": WANTS_HEAT, "zolder": WANTS_COOL, "slaapkamer": WANTS_HEAT},
        )
        assert MODE_HEAT in modes.values()
        assert MODE_COOL in modes.values()


# ---------------------------------------------------------------------------
# Voorbeeld C: een multi-split plus een losse splitunit.
# Example C: a multi-split plus a single split.
# ---------------------------------------------------------------------------


def example_c() -> DirectorConfig:
    return DirectorConfig(
        zones=rooms("zolder", "slaapkamer", "woonkamer"),
        circuits=(multi_split("boven", "zolder", "slaapkamer"),),
    )


class TestExampleC:
    """The living room hangs off its own outdoor unit and stays unconstrained."""

    temperatures = {
        "zolder": WANTS_COOL,
        "slaapkamer": WANTS_HEAT,
        "woonkamer": WANTS_HEAT,
    }

    def test_the_attic_takes_the_shared_circuit(self) -> None:
        modes, _ = run(example_c(), self.temperatures)
        assert modes[unit("zolder")] == MODE_COOL

    def test_the_bedroom_on_that_circuit_stands_down(self) -> None:
        modes, _ = run(example_c(), self.temperatures)
        assert modes[unit("slaapkamer")] in {MODE_COOL, MODE_OFF, MODE_FAN_ONLY}

    def test_the_living_room_is_untouched_by_the_conflict(self) -> None:
        modes, _ = run(example_c(), self.temperatures)
        assert modes[unit("woonkamer")] == MODE_HEAT

    def test_a_solo_unit_gets_no_circuit_decision(self) -> None:
        _, plan = run(example_c(), self.temperatures)
        assert [decision.circuit_id for decision in plan.circuits] == ["boven"]


# ---------------------------------------------------------------------------
# Voorbeeld D: twee multi-splits die de kamers kriskras verdelen.
# Example D: two multi-splits dividing the rooms crosswise.
# ---------------------------------------------------------------------------


def example_d() -> DirectorConfig:
    return DirectorConfig(
        zones=rooms("zolder", "slaapkamer_1", "woonkamer", "slaapkamer_2"),
        circuits=(
            multi_split("boven", "zolder", "slaapkamer_1"),
            multi_split("beneden", "slaapkamer_2", "woonkamer"),
        ),
    )


class TestExampleD:
    """Two circuits, so the two bedrooms are free of one another."""

    def test_the_bedrooms_can_run_opposing_duties(self) -> None:
        modes, _ = run(
            example_d(),
            {
                "zolder": WANTS_COOL,
                "slaapkamer_1": WANTS_COOL,
                "woonkamer": WANTS_HEAT,
                "slaapkamer_2": WANTS_HEAT,
            },
        )
        assert modes[unit("slaapkamer_1")] == MODE_COOL
        assert modes[unit("slaapkamer_2")] == MODE_HEAT

    def test_each_circuit_still_binds_its_own_pair(self) -> None:
        modes, _ = run(
            example_d(),
            {
                "zolder": WANTS_COOL,
                "slaapkamer_1": WANTS_HEAT,
                "woonkamer": WANTS_HEAT,
                "slaapkamer_2": WANTS_COOL,
            },
        )
        # Attic outranks bedroom 1; living room outranks bedroom 2.
        assert modes[unit("zolder")] == MODE_COOL
        assert modes[unit("slaapkamer_1")] == MODE_OFF
        assert modes[unit("woonkamer")] == MODE_HEAT
        assert modes[unit("slaapkamer_2")] == MODE_OFF

    def test_both_circuits_are_reported(self) -> None:
        _, plan = run(
            example_d(),
            {
                "zolder": WANTS_COOL,
                "slaapkamer_1": WANTS_COOL,
                "woonkamer": WANTS_HEAT,
                "slaapkamer_2": WANTS_HEAT,
            },
        )
        families = {decision.circuit_id: decision.family for decision in plan.circuits}
        assert families == {"boven": ModeFamily.COOL, "beneden": ModeFamily.HEAT}


# ---------------------------------------------------------------------------
# Heat recovery, conflictbeleid en de tijdslimieten.
# Heat recovery, conflict policies and the timing limits.
# ---------------------------------------------------------------------------


def test_heat_recovery_multi_split_is_not_crippled() -> None:
    """Three-pipe VRF really does both at once; the flag says so, not the size."""
    config = DirectorConfig(
        zones=rooms("woonkamer", "zolder"),
        circuits=(
            Circuit(
                circuit_id="vrf",
                name="VRF",
                units=(unit("woonkamer"), unit("zolder")),
                simultaneous_heat_cool=True,
            ),
        ),
    )
    modes, _ = run(config, {"woonkamer": WANTS_HEAT, "zolder": WANTS_COOL})
    assert modes[unit("woonkamer")] == MODE_HEAT
    assert modes[unit("zolder")] == MODE_COOL


class TestLivePriority:
    """Which room outranks which has to be changeable while the house runs."""

    config = DirectorConfig(
        zones=rooms("woonkamer", "zolder"),
        circuits=(multi_split("c", "woonkamer", "zolder"),),
    )
    temperatures = {"woonkamer": WANTS_HEAT, "zolder": WANTS_COOL}

    def test_the_configured_priority_decides_by_default(self) -> None:
        modes, _ = run(self.config, self.temperatures)
        assert modes[unit("woonkamer")] == MODE_HEAT
        assert modes[unit("zolder")] == MODE_OFF

    def test_a_live_priority_turns_the_outcome_around(self) -> None:
        """An automation can hand the attic the circuit without touching the config."""
        modes, _ = run(
            self.config,
            self.temperatures,
            zone_priorities={"woonkamer": 5, "zolder": 1},
        )
        assert modes[unit("zolder")] == MODE_COOL
        assert modes[unit("woonkamer")] == MODE_OFF

    def test_a_zone_without_a_live_value_keeps_its_configured_one(self) -> None:
        modes, _ = run(self.config, self.temperatures, zone_priorities={"zolder": 5})
        assert modes[unit("woonkamer")] == MODE_HEAT

    def test_it_also_settles_the_demand_policy_tie_break(self) -> None:
        config = DirectorConfig(
            zones=rooms("woonkamer", "zolder"),
            circuits=(
                multi_split("c", "woonkamer", "zolder", conflict_policy=ConflictPolicy.DEMAND),
            ),
        )
        # Both are exactly two degrees past their switch-on point, so only the
        # priority separates them.
        modes, _ = run(
            config,
            {"woonkamer": 18.0, "zolder": 18.0},
            zone_priorities={"woonkamer": 9, "zolder": 1},
        )
        assert modes[unit("zolder")] == MODE_HEAT


class TestConflictPolicies:
    temperatures = {"woonkamer": WANTS_HEAT, "zolder": 30.0}

    def _config(self, policy: ConflictPolicy) -> DirectorConfig:
        return DirectorConfig(
            zones=rooms("woonkamer", "zolder"),
            circuits=(multi_split("c", "woonkamer", "zolder", conflict_policy=policy),),
        )

    def test_priority(self) -> None:
        modes, _ = run(self._config(ConflictPolicy.PRIORITY), self.temperatures)
        assert modes[unit("woonkamer")] == MODE_HEAT

    def test_demand_lets_the_greater_need_win(self) -> None:
        # The attic is 6 degrees past its cooling point; the living room only 2
        # below its heating point.
        modes, _ = run(self._config(ConflictPolicy.DEMAND), self.temperatures)
        assert modes[unit("zolder")] == MODE_COOL
        assert modes[unit("woonkamer")] == MODE_OFF

    def test_first_come_keeps_the_running_duty(self) -> None:
        modes, _ = run(
            self._config(ConflictPolicy.FIRST_COME),
            self.temperatures,
            zolder_mode=MODE_COOL,
        )
        assert modes[unit("zolder")] == MODE_COOL
        assert modes[unit("woonkamer")] == MODE_OFF

    def test_first_come_falls_back_to_priority_when_idle(self) -> None:
        modes, _ = run(self._config(ConflictPolicy.FIRST_COME), self.temperatures)
        assert modes[unit("woonkamer")] == MODE_HEAT

    def test_season_lock(self) -> None:
        modes, _ = run(
            self._config(ConflictPolicy.SEASON_LOCK),
            self.temperatures,
            season=Season.SUMMER,
        )
        assert modes[unit("zolder")] == MODE_COOL

    def test_season_lock_falls_back_when_the_season_is_unknown(self) -> None:
        modes, _ = run(self._config(ConflictPolicy.SEASON_LOCK), self.temperatures)
        assert modes[unit("woonkamer")] == MODE_HEAT


class TestUnmanagedUnits:
    """An indoor unit the director does not manage still claims the compressor."""

    def test_it_locks_the_circuit(self) -> None:
        config = DirectorConfig(
            zones=rooms("woonkamer"),
            circuits=(
                Circuit(
                    circuit_id="c",
                    name="C",
                    units=(unit("woonkamer"), "climate.handbediend"),
                    simultaneous_heat_cool=False,
                ),
            ),
        )
        world = make_world(
            indoor={"woonkamer": WANTS_HEAT},
            climates={
                unit("woonkamer"): climate(MODE_OFF),
                "climate.handbediend": climate(MODE_COOL),
            },
        )
        plan = decide(config, world)
        command = plan.command_for(unit("woonkamer"))
        assert command is not None
        assert command.hvac_mode == MODE_OFF

    def test_it_is_never_commanded(self) -> None:
        config = DirectorConfig(
            zones=rooms("woonkamer"),
            circuits=(
                Circuit(
                    circuit_id="c",
                    name="C",
                    units=(unit("woonkamer"), "climate.handbediend"),
                    simultaneous_heat_cool=False,
                ),
            ),
        )
        world = make_world(
            indoor={"woonkamer": WANTS_HEAT},
            climates={
                unit("woonkamer"): climate(MODE_OFF),
                "climate.handbediend": climate(MODE_COOL),
            },
        )
        plan = decide(config, world)
        assert plan.command_for("climate.handbediend") is None


class TestSwitchTiming:
    def _config(self, **kwargs: object) -> DirectorConfig:
        return DirectorConfig(
            zones=rooms("woonkamer", "zolder"),
            circuits=(multi_split("c", "woonkamer", "zolder", **kwargs),),
        )

    def test_switch_delay_stops_before_it_starts(self) -> None:
        """Swapping duty stops the old one this cycle and starts the new one later."""
        config = self._config(family_switch_delay=timedelta(seconds=30))
        world = make_world(
            now=at(12, 0),
            indoor={"woonkamer": WANTS_HEAT, "zolder": 21.0},
            climates={unit("woonkamer"): climate(MODE_COOL), unit("zolder"): climate(MODE_OFF)},
        )
        plan = decide(config, world)
        command = plan.command_for(unit("woonkamer"))
        assert command is not None
        assert command.hvac_mode == MODE_OFF
        assert command.reason is Reason.CIRCUIT_SWITCH_PENDING
        assert plan.next_deferral is not None
        assert plan.next_deferral.until == at(12, 0) + timedelta(seconds=30)

    def test_without_a_delay_the_swap_happens_in_one_go(self) -> None:
        config = self._config()
        world = make_world(
            indoor={"woonkamer": WANTS_HEAT, "zolder": 21.0},
            climates={unit("woonkamer"): climate(MODE_COOL), unit("zolder"): climate(MODE_OFF)},
        )
        plan = decide(config, world)
        command = plan.command_for(unit("woonkamer"))
        assert command is not None
        assert command.hvac_mode == MODE_HEAT

    def test_minimum_run_time_holds_the_current_duty(self) -> None:
        config = self._config(min_family_switch_interval=timedelta(minutes=20))
        world = make_world(
            now=at(12, 0),
            indoor={"woonkamer": WANTS_HEAT, "zolder": 21.0},
            climates={unit("woonkamer"): climate(MODE_COOL), unit("zolder"): climate(MODE_OFF)},
            circuit_family_since={"c": at(11, 55)},
        )
        plan = decide(config, world)
        assert plan.next_deferral is not None
        assert plan.next_deferral.reason is Reason.CIRCUIT_SWITCH_TOO_SOON
        assert plan.next_deferral.until == at(11, 55) + timedelta(minutes=20)

    def test_minimum_run_time_expires(self) -> None:
        config = self._config(min_family_switch_interval=timedelta(minutes=20))
        world = make_world(
            now=at(12, 30),
            indoor={"woonkamer": WANTS_HEAT, "zolder": 21.0},
            climates={unit("woonkamer"): climate(MODE_COOL), unit("zolder"): climate(MODE_OFF)},
            circuit_family_since={"c": at(11, 55)},
        )
        plan = decide(config, world)
        command = plan.command_for(unit("woonkamer"))
        assert command is not None
        assert command.hvac_mode == MODE_HEAT

    def test_unknown_switch_time_does_not_freeze_the_installation(self) -> None:
        config = self._config(min_family_switch_interval=timedelta(minutes=20))
        world = make_world(
            indoor={"woonkamer": WANTS_HEAT, "zolder": 21.0},
            climates={unit("woonkamer"): climate(MODE_COOL), unit("zolder"): climate(MODE_OFF)},
        )
        plan = decide(config, world)
        command = plan.command_for(unit("woonkamer"))
        assert command is not None
        assert command.hvac_mode == MODE_HEAT


class TestShortCycleProtection:
    def _config(self) -> DirectorConfig:
        return DirectorConfig(
            zones=rooms("woonkamer"),
            circuits=(multi_split("c", "woonkamer", min_cycle_time=timedelta(minutes=3)),),
        )

    def test_a_unit_that_just_stopped_waits(self) -> None:
        world = make_world(
            now=at(12, 1),
            indoor={"woonkamer": WANTS_HEAT},
            climates={unit("woonkamer"): climate(MODE_OFF, changed_at=at(12, 0))},
        )
        plan = decide(self._config(), world)
        command = plan.command_for(unit("woonkamer"))
        assert command is not None
        assert command.hvac_mode == MODE_OFF
        assert command.reason is Reason.SHORT_CYCLE_PROTECTION
        assert plan.next_deferral is not None
        assert plan.next_deferral.until == at(12, 0) + timedelta(minutes=3)

    def test_it_starts_once_the_rest_is_over(self) -> None:
        world = make_world(
            now=at(12, 5),
            indoor={"woonkamer": WANTS_HEAT},
            climates={unit("woonkamer"): climate(MODE_OFF, changed_at=at(12, 0))},
        )
        plan = decide(self._config(), world)
        command = plan.command_for(unit("woonkamer"))
        assert command is not None
        assert command.hvac_mode == MODE_HEAT

    def test_it_never_delays_a_stop(self) -> None:
        """Protection that could keep a unit running would be a safety problem."""
        world = make_world(
            now=at(12, 1),
            indoor={"woonkamer": 21.0},
            climates={unit("woonkamer"): climate(MODE_HEAT, changed_at=at(12, 0))},
        )
        plan = decide(self._config(), world)
        command = plan.command_for(unit("woonkamer"))
        assert command is not None
        assert command.hvac_mode == MODE_OFF


class TestCapacity:
    def test_capacity_cap_trims_the_lowest_ranked_zones(self) -> None:
        config = DirectorConfig(
            zones=rooms("woonkamer", "zolder", "slaapkamer"),
            circuits=(
                multi_split("c", "woonkamer", "zolder", "slaapkamer", max_concurrent_units=2),
            ),
        )
        modes, plan = run(
            config,
            {"woonkamer": WANTS_HEAT, "zolder": WANTS_HEAT, "slaapkamer": WANTS_HEAT},
        )
        assert modes[unit("woonkamer")] == MODE_HEAT
        assert modes[unit("zolder")] == MODE_HEAT
        assert modes[unit("slaapkamer")] == MODE_OFF
        bedroom = plan.decision_for("slaapkamer")
        assert bedroom is not None
        assert bedroom.reason is Reason.CIRCUIT_AT_CAPACITY

    def test_unmanaged_units_occupy_capacity_too(self) -> None:
        config = DirectorConfig(
            zones=rooms("woonkamer", "zolder"),
            circuits=(
                Circuit(
                    circuit_id="c",
                    name="C",
                    units=(unit("woonkamer"), unit("zolder"), "climate.handbediend"),
                    simultaneous_heat_cool=False,
                    max_concurrent_units=2,
                ),
            ),
        )
        world = make_world(
            indoor={"woonkamer": WANTS_HEAT, "zolder": WANTS_HEAT},
            climates={
                unit("woonkamer"): climate(MODE_OFF),
                unit("zolder"): climate(MODE_OFF),
                "climate.handbediend": climate(MODE_HEAT),
            },
        )
        plan = decide(config, world)
        attic = plan.command_for(unit("zolder"))
        assert attic is not None
        assert attic.hvac_mode == MODE_OFF


def test_active_family_reads_unmanaged_units_too() -> None:
    circuit = multi_split("c", "woonkamer", "zolder")
    world = make_world(
        climates={unit("woonkamer"): climate(MODE_OFF), unit("zolder"): climate(MODE_COOL)}
    )
    assert constraints.active_family(world, circuit) is ModeFamily.COOL


@pytest.mark.parametrize("mode", [MODE_OFF, MODE_FAN_ONLY])
def test_idle_modes_do_not_claim_a_circuit(mode: str) -> None:
    circuit = multi_split("c", "woonkamer")
    world = make_world(climates={unit("woonkamer"): climate(mode)})
    assert constraints.active_family(world, circuit) is ModeFamily.NEUTRAL
