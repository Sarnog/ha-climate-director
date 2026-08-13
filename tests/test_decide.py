"""Tests voor de beslisfunctie als geheel.

Tests for the decision function as a whole.
"""

from __future__ import annotations

from conftest import (
    ATTIC,
    BEDROOM,
    GAS,
    LIVING,
    climate,
    everyone_up,
    house,
    make_world,
)

from custom_components.climate_director.engine import (
    MODE_COOL,
    MODE_FAN_ONLY,
    MODE_HEAT,
    MODE_OFF,
    DirectorConfig,
    ModeFamily,
    ModeSettings,
    Reason,
    Season,
    Source,
    SourceRole,
    Zone,
    decide,
)


def cold_house(**kwargs: object):
    """Return a world where the living room wants heating from the boiler."""
    defaults: dict[str, object] = {
        "outdoor": 1.0,
        "season": Season.WINTER,
        "indoor": {"woonkamer": 20.0, "zolder": 20.0, "slaapkamer": 20.0},
        "climates": {
            GAS: climate(MODE_OFF),
            LIVING: climate(MODE_OFF),
            ATTIC: climate(MODE_OFF),
            BEDROOM: climate(MODE_OFF),
        },
        "residents": everyone_up(),
    }
    defaults.update(kwargs)
    return make_world(**defaults)  # type: ignore[arg-type]


class TestEveryEntityIsCommanded:
    def test_unchosen_sources_are_switched_off_explicitly(self) -> None:
        """This is what makes two appliances fighting each other unreachable."""
        plan = decide(house(), cold_house(outdoor=10.0))
        living = plan.command_for(LIVING)
        boiler = plan.command_for(GAS)
        assert living is not None and living.hvac_mode == MODE_HEAT
        assert boiler is not None and boiler.hvac_mode == MODE_OFF

    def test_the_boiler_wins_below_the_cutover(self) -> None:
        plan = decide(house(), cold_house(outdoor=1.0))
        living = plan.command_for(LIVING)
        boiler = plan.command_for(GAS)
        assert boiler is not None and boiler.hvac_mode == MODE_HEAT
        assert living is not None and living.hvac_mode == MODE_OFF

    def test_boiler_and_heat_pump_never_run_together(self) -> None:
        for outdoor in [-10.0, 0.0, 2.9, 3.0, 3.1, 10.0, 18.9]:
            plan = decide(house(), cold_house(outdoor=outdoor))
            running = [
                command.entity_id
                for command in plan.commands
                if command.hvac_mode not in (MODE_OFF, MODE_FAN_ONLY)
            ]
            assert not ({GAS} <= set(running) and {LIVING} <= set(running)), outdoor

    def test_a_stood_down_source_says_why_it_is_off(self) -> None:
        """The boiler is off because the heat pump took the zone, not "nothing to do"."""
        command = decide(house(), cold_house(outdoor=10.0)).command_for(GAS)
        assert command is not None
        assert command.reason is Reason.OTHER_SOURCE_CHOSEN

    def test_a_gate_blocked_zone_passes_its_cause_to_the_command(self) -> None:
        command = decide(house(), cold_house(master_enabled=False)).command_for(GAS)
        assert command is not None
        assert command.reason is Reason.MASTER_DISABLED

    def test_every_zone_gets_a_decision(self) -> None:
        plan = decide(house(), cold_house())
        assert {decision.zone_id for decision in plan.zones} == {
            "woonkamer",
            "zolder",
            "slaapkamer",
        }


class TestCommandOrder:
    def test_stops_are_ordered_before_starts(self) -> None:
        """Otherwise two duties briefly share one compressor while calls land."""
        plan = decide(house(), cold_house(outdoor=10.0))
        ranks = [0 if command.hvac_mode == MODE_OFF else 1 for command in plan.commands]
        assert ranks == sorted(ranks)


class TestAvailability:
    def test_an_unavailable_entity_is_not_commanded(self) -> None:
        world = cold_house(
            climates={
                GAS: climate(MODE_OFF, available=False),
                LIVING: climate(MODE_OFF),
                ATTIC: climate(MODE_OFF),
                BEDROOM: climate(MODE_OFF),
            }
        )
        plan = decide(house(), world)
        assert plan.command_for(GAS) is None

    def test_the_zone_falls_back_to_another_source(self) -> None:
        """With the boiler gone below the cutover, nothing else can heat."""
        world = cold_house(
            climates={
                GAS: climate(MODE_OFF, available=False),
                LIVING: climate(MODE_OFF),
                ATTIC: climate(MODE_OFF),
                BEDROOM: climate(MODE_OFF),
            }
        )
        decision = decide(house(), world).decision_for("woonkamer")
        assert decision is not None
        assert decision.reason is Reason.NO_SOURCE_AVAILABLE


class TestBlockedZones:
    def test_a_blocked_zone_reports_the_gate_that_stopped_it(self) -> None:
        plan = decide(house(), cold_house(master_enabled=False))
        decision = plan.decision_for("woonkamer")
        assert decision is not None
        assert decision.reason is Reason.MASTER_DISABLED

    def test_a_blocked_zone_is_switched_off(self) -> None:
        world = cold_house(
            master_enabled=False,
            climates={
                GAS: climate(MODE_HEAT),
                LIVING: climate(MODE_OFF),
                ATTIC: climate(MODE_OFF),
                BEDROOM: climate(MODE_OFF),
            },
        )
        command = decide(house(), world).command_for(GAS)
        assert command is not None
        assert command.hvac_mode == MODE_OFF


class TestExclusiveGroups:
    def _config(self) -> DirectorConfig:
        shared = ModeSettings(target=21.0, start_at=20.0, hysteresis=1.0)
        return DirectorConfig(
            zones=(
                Zone(
                    "kantoor",
                    "Kantoor",
                    "sensor.kantoor",
                    priority=0,
                    sources=(Source("kachel_kantoor", "climate.kachel", SourceRole.HEAT_ONLY),),
                    heat=shared,
                ),
                Zone(
                    "hal",
                    "Hal",
                    "sensor.hal",
                    priority=1,
                    sources=(Source("kachel_hal", "climate.kachel_hal", SourceRole.HEAT_ONLY),),
                    heat=shared,
                ),
            ),
            exclusive_groups=(frozenset({"kachel_kantoor", "kachel_hal"}),),
        )

    def test_only_the_preferred_zone_gets_the_shared_appliance(self) -> None:
        world = make_world(
            indoor={"kantoor": 18.0, "hal": 18.0},
            climates={"climate.kachel": climate(), "climate.kachel_hal": climate()},
        )
        plan = decide(self._config(), world)
        office = plan.command_for("climate.kachel")
        hall = plan.command_for("climate.kachel_hal")
        assert office is not None and office.hvac_mode == MODE_HEAT
        assert hall is not None and hall.hvac_mode == MODE_OFF

    def test_the_loser_is_told_why(self) -> None:
        world = make_world(
            indoor={"kantoor": 18.0, "hal": 18.0},
            climates={"climate.kachel": climate(), "climate.kachel_hal": climate()},
        )
        decision = decide(self._config(), world).decision_for("hal")
        assert decision is not None
        assert decision.reason is Reason.EXCLUSIVE_GROUP_LOST

    def test_the_loser_keeps_the_wish_it_made(self) -> None:
        """ "Wanted heat, got nothing" reads better than hiding the request."""
        world = make_world(
            indoor={"kantoor": 18.0, "hal": 18.0},
            climates={"climate.kachel": climate(), "climate.kachel_hal": climate()},
        )
        decision = decide(self._config(), world).decision_for("hal")
        assert decision is not None
        assert decision.wanted is ModeFamily.HEAT
        assert decision.granted is ModeFamily.NEUTRAL
        assert decision.source_id == "kachel_hal"

    def test_the_losers_command_carries_the_same_reason(self) -> None:
        world = make_world(
            indoor={"kantoor": 18.0, "hal": 18.0},
            climates={"climate.kachel": climate(), "climate.kachel_hal": climate()},
        )
        command = decide(self._config(), world).command_for("climate.kachel_hal")
        assert command is not None
        assert command.reason is Reason.EXCLUSIVE_GROUP_LOST


class TestIdempotence:
    def test_deciding_twice_on_the_same_world_gives_the_same_plan(self) -> None:
        config, world = house(), cold_house(outdoor=10.0)
        assert decide(config, world) == decide(config, world)

    def test_a_settled_installation_is_commanded_to_where_it_already_is(self) -> None:
        """The applier can then compare and do nothing at all."""
        world = cold_house(
            outdoor=10.0,
            indoor={"woonkamer": 20.5, "zolder": 23.0, "slaapkamer": 23.0},
            climates={
                GAS: climate(MODE_OFF),
                LIVING: climate(MODE_HEAT),
                ATTIC: climate(MODE_OFF),
                BEDROOM: climate(MODE_OFF),
            },
        )
        plan = decide(house(), world)
        assert {command.entity_id: command.hvac_mode for command in plan.commands} == {
            GAS: MODE_OFF,
            LIVING: MODE_HEAT,
            ATTIC: MODE_OFF,
            BEDROOM: MODE_OFF,
        }


class TestSetpoints:
    def test_the_configured_target_is_handed_to_the_unit(self) -> None:
        plan = decide(house(), cold_house(outdoor=10.0))
        command = plan.command_for(LIVING)
        assert command is not None
        assert command.temperature == 23.0

    def test_a_unit_being_switched_off_carries_no_setpoint(self) -> None:
        plan = decide(house(), cold_house(outdoor=10.0))
        command = plan.command_for(GAS)
        assert command is not None
        assert command.temperature is None

    def test_cooling_uses_its_own_target(self) -> None:
        world = cold_house(
            outdoor=28.0,
            season=Season.SUMMER,
            indoor={"woonkamer": 26.0, "zolder": 26.0, "slaapkamer": 26.0},
        )
        command = decide(house(), world).command_for(LIVING)
        assert command is not None
        assert command.hvac_mode == MODE_COOL
        assert command.temperature == 23.0


class TestAmbiguousModesAreNeverCommanded:
    def test_the_director_always_picks_a_concrete_duty(self) -> None:
        """`heat_cool` on a shared circuit would let the unit swap duty itself."""
        plan = decide(house(), cold_house(outdoor=10.0))
        assert all(
            command.hvac_mode in (MODE_OFF, MODE_FAN_ONLY, MODE_HEAT, MODE_COOL)
            for command in plan.commands
        )

    def test_a_unit_left_in_heat_cool_is_steered_back(self) -> None:
        world = cold_house(
            outdoor=10.0,
            climates={
                GAS: climate(MODE_OFF),
                LIVING: climate("heat_cool"),
                ATTIC: climate(MODE_OFF),
                BEDROOM: climate(MODE_OFF),
            },
        )
        command = decide(house(), world).command_for(LIVING)
        assert command is not None
        assert command.hvac_mode == MODE_HEAT


def test_a_zone_whose_indoor_temperature_is_missing_stands_down() -> None:
    world = cold_house(indoor={"zolder": 20.0, "slaapkamer": 20.0})
    decision = decide(house(), world).decision_for("woonkamer")
    assert decision is not None
    assert decision.wanted is ModeFamily.NEUTRAL
    assert decision.reason is Reason.NO_INDOOR_TEMPERATURE
