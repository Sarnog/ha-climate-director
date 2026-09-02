"""Wat er gebeurt als het eigen apparaat van een zone niet te bereiken is.

What happens when a zone's own appliance cannot be reached.

Een onbereikbaar apparaat laat niets omvallen: `select()` slaat het over en de
volgende bron op voorkeur neemt het over. De kamer wordt gewoon warm. Precies
daar zit het gevaar - een vangnet dat werkt voel je niet, dus kan een kapotte
thermostaat wekenlang blijven hangen terwijl er elektrisch verwarmd wordt.
Daarom draagt het besluit mee wát er overgeslagen is.

An unreachable appliance breaks nothing: `select()` skips it and the next
source by preference takes over. The room simply gets warm. That is exactly
where the danger sits - a safety net that works is one you do not feel, so a
broken thermostat can stay broken for weeks while the heating runs on
electricity. Hence the decision carries what was skipped.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from conftest import climate, make_world

from custom_components.climate_director.engine import (
    MODE_HEAT,
    MODE_OFF,
    Circuit,
    DirectorConfig,
    ModeFamily,
    ModeSettings,
    Opening,
    OutdoorWindow,
    Reason,
    Source,
    SourceRole,
    Zone,
    decide,
    sources,
)
from custom_components.climate_director.engine.world import OpeningState

HEAT = ModeSettings(target=21.0, start_at=20.0, hysteresis=1.0)
COOL = ModeSettings(target=22.0, start_at=24.0, hysteresis=1.0)

GAS = "climate.gas_thermostat"
AIRCO = "climate.living_room_airco"


def living_room(*, cool: bool = True) -> Zone:
    """Return a room served by the gas heating first and an air conditioner second."""
    return Zone(
        zone_id="living_room",
        name="Living room",
        indoor_sensor="sensor.living_room",
        sources=(
            Source(source_id="gas", entity_id=GAS, priority=0, role=SourceRole.HEAT_ONLY),
            Source(
                source_id="airco",
                entity_id=AIRCO,
                priority=1,
                role=SourceRole.HEAT_COOL if cool else SourceRole.HEAT_ONLY,
            ),
        ),
        heat=HEAT,
        cool=COOL if cool else None,
    )


def world(*, gas_available: bool, indoor: float = 18.0, outdoor: float = 5.0):
    """Return a world in which the room wants heating."""
    return make_world(
        indoor={"living_room": indoor},
        outdoor=outdoor,
        climates={
            GAS: climate("off", available=gas_available),
            AIRCO: climate("off"),
        },
    )


class TestTheGasThermostatFallsAway:
    """The scenario the user asked for, start to finish."""

    def test_nothing_crashes(self) -> None:
        """An unreachable appliance is a state, not an accident."""
        config = DirectorConfig(zones=(living_room(),))
        plan = decide(config, world(gas_available=False))
        assert plan is not None

    def test_the_air_conditioner_takes_over(self) -> None:
        config = DirectorConfig(zones=(living_room(),))
        plan = decide(config, world(gas_available=False))
        commands = {command.entity_id: command.hvac_mode for command in plan.commands}
        assert commands.get(AIRCO) == MODE_HEAT
        assert GAS not in commands, "een onbereikbaar apparaat krijgt geen opdracht"

    def test_the_gas_is_used_while_it_answers(self) -> None:
        """The stand-in is a stand-in, not a new favourite."""
        config = DirectorConfig(zones=(living_room(),))
        plan = decide(config, world(gas_available=True))
        commands = {command.entity_id: command.hvac_mode for command in plan.commands}
        assert commands.get(GAS) == MODE_HEAT
        assert commands.get(AIRCO, MODE_OFF) == MODE_OFF

    def test_the_decision_names_what_was_skipped(self) -> None:
        config = DirectorConfig(zones=(living_room(),))
        plan = decide(config, world(gas_available=False))
        decision = plan.decision_for("living_room")
        assert decision is not None
        assert decision.on_fallback is True
        assert decision.passed_over == ("gas",)
        assert decision.source_id == "airco"

    def test_a_healthy_installation_says_nothing(self) -> None:
        """No news is the normal case; the sensor must stay off."""
        config = DirectorConfig(zones=(living_room(),))
        plan = decide(config, world(gas_available=True))
        decision = plan.decision_for("living_room")
        assert decision is not None
        assert decision.on_fallback is False
        assert decision.passed_over == ()


class TestWhatDoesNotCountAsFallingBack:
    """Not every unused appliance is a fault worth waking somebody for."""

    def test_a_second_choice_by_preference_is_normal(self) -> None:
        """Cooling on the air conditioner is not a fallback - gas cannot cool."""
        config = DirectorConfig(zones=(living_room(),))
        plan = decide(
            config,
            make_world(
                indoor={"living_room": 26.0},
                outdoor=30.0,
                climates={GAS: climate("off"), AIRCO: climate("off")},
            ),
        )
        decision = plan.decision_for("living_room")
        assert decision is not None
        assert decision.source_id == "airco"
        assert decision.passed_over == (), "gas kan niet koelen, dus valt er niets over te melden"

    def test_a_source_outside_its_outdoor_window_is_not_a_fault(self) -> None:
        """An appliance the installer parked for this weather was never up next."""
        zone = Zone(
            zone_id="living_room",
            name="Living room",
            indoor_sensor="sensor.living_room",
            sources=(
                Source(
                    source_id="heat_pump",
                    entity_id="climate.heat_pump",
                    priority=0,
                    role=SourceRole.HEAT_ONLY,
                    outdoor=OutdoorWindow(minimum=3.0),
                ),
                Source(source_id="gas", entity_id=GAS, priority=1, role=SourceRole.HEAT_ONLY),
            ),
            heat=HEAT,
        )
        plan = decide(
            DirectorConfig(zones=(zone,)),
            make_world(
                indoor={"living_room": 18.0},
                outdoor=-5.0,
                climates={
                    "climate.heat_pump": climate("off", available=False),
                    GAS: climate("off"),
                },
            ),
        )
        decision = plan.decision_for("living_room")
        assert decision is not None
        assert decision.source_id == "gas"
        assert decision.passed_over == (), "buiten zijn venster stond hij toch al stil"

    def test_a_lesser_source_that_drops_out_is_not_reported(self) -> None:
        """Only what outranks the appliance now running counts."""
        config = DirectorConfig(zones=(living_room(),))
        plan = decide(
            config,
            make_world(
                indoor={"living_room": 18.0},
                outdoor=5.0,
                climates={GAS: climate("off"), AIRCO: climate("off", available=False)},
            ),
        )
        decision = plan.decision_for("living_room")
        assert decision is not None
        assert decision.source_id == "gas"
        assert decision.passed_over == ()

    def test_a_zone_with_nothing_left_reports_nothing(self) -> None:
        """With every appliance gone there is no stand-in to speak of."""
        config = DirectorConfig(zones=(living_room(),))
        plan = decide(
            config,
            make_world(
                indoor={"living_room": 18.0},
                outdoor=5.0,
                climates={
                    GAS: climate("off", available=False),
                    AIRCO: climate("off", available=False),
                },
            ),
        )
        decision = plan.decision_for("living_room")
        assert decision is not None
        assert decision.passed_over == ()
        assert decision.granted is ModeFamily.NEUTRAL


class TestTheHelperOnItsOwn:
    """`passed_over` read directly, so its rules are pinned down."""

    @pytest.mark.parametrize("available", [True, False])
    def test_it_never_names_the_appliance_that_is_running(self, available: bool) -> None:
        zone = living_room()
        found = sources.passed_over(
            zone,
            ModeFamily.HEAT,
            world(gas_available=available),
        )
        assert "airco" not in found

    def test_it_is_empty_when_nothing_can_serve(self) -> None:
        """Without a chosen source there is nothing to have passed over."""
        zone = living_room()
        found = sources.passed_over(
            zone,
            ModeFamily.COOL,
            make_world(
                indoor={"living_room": 26.0},
                outdoor=30.0,
                climates={
                    GAS: climate("off", available=False),
                    AIRCO: climate("off", available=False),
                },
            ),
        )
        assert found == ()


PUMP = "climate.warmtepomp"
STOVE = "climate.elektrische_kachel"
NOW = datetime(2026, 1, 12, 10, 0)


def _zolder_with_reserve() -> Zone:
    """Return the switchback room: heat pump first, electric stove second."""
    return Zone(
        zone_id="zolder",
        name="Zolder",
        indoor_sensor="sensor.zolder",
        priority=1,
        sources=(
            Source(
                source_id="warmtepomp",
                entity_id=PUMP,
                priority=0,
                role=SourceRole.HEAT_COOL,
                outdoor=OutdoorWindow(minimum=3.1),
            ),
            Source(source_id="kachel", entity_id=STOVE, priority=2, role=SourceRole.HEAT_ONLY),
        ),
        heat=HEAT,
    )


def _living_room(priority: int, *, cool: bool = False) -> Zone:
    settings = {"heat": HEAT, "cool": COOL if cool else None}
    return Zone(
        zone_id="woonkamer",
        name="Woonkamer",
        indoor_sensor="sensor.woonkamer",
        priority=priority,
        sources=(Source(source_id="woonkamer_unit", entity_id="climate.woonkamer"),),
        **settings,
    )


def _refused_world(refusal: str, reserve_running: bool):
    """Return the config and world for one circuit refusal on the attic's first choice."""
    stove_mode = "heat" if reserve_running else "off"
    climates = {PUMP: climate("off"), STOVE: climate(stove_mode)}
    indoor = {"zolder": 18.0}
    zones = [_zolder_with_reserve()]

    if refusal == "short_cycle":
        circuits = (
            Circuit(
                "buitenunit",
                "Buitenunit",
                units=(PUMP,),
                min_cycle_time=timedelta(minutes=15),
            ),
        )
        climates[PUMP] = climate("off", changed_at=NOW - timedelta(minutes=2))
        outdoor = 4.0
    elif refusal == "capacity":
        zones.insert(0, _living_room(priority=0))
        circuits = (
            Circuit(
                "buitenunit",
                "Buitenunit",
                units=("climate.woonkamer", PUMP),
                max_concurrent_units=1,
            ),
        )
        indoor["woonkamer"] = 18.0
        climates["climate.woonkamer"] = climate("off")
        outdoor = 4.0
    else:
        assert refusal == "conflict"
        zones.insert(0, _living_room(priority=0, cool=True))
        circuits = (
            Circuit(
                "buitenunit",
                "Buitenunit",
                units=("climate.woonkamer", PUMP),
            ),
        )
        indoor["woonkamer"] = 26.0
        climates["climate.woonkamer"] = climate("off")
        outdoor = 4.0

    config = DirectorConfig(
        zones=tuple(zones),
        circuits=circuits,
        outdoor_sensor="sensor.buiten",
        outdoor_hysteresis=0.5,
    )
    world = make_world(now=NOW, outdoor=outdoor, indoor=indoor, climates=climates)
    return config, world


class TestTheCircuitRefusedZoneTriesItsNextSource:
    """Ronde 21, anker 7: a circuit refusal refuses the appliance, not the zone."""

    @pytest.mark.parametrize("refusal", ["short_cycle", "capacity", "conflict"])
    @pytest.mark.parametrize("reserve_running", [True, False])
    def test_the_zone_runs_its_reserve_after_a_circuit_refusal(
        self, refusal: str, reserve_running: bool
    ) -> None:
        plan = decide(*_refused_world(refusal, reserve_running))
        decision = plan.decision_for("zolder")
        assert decision is not None
        assert decision.source_id == "kachel"
        assert decision.granted is ModeFamily.HEAT
        assert decision.reason is Reason.REGULATING
        assert decision.passed_over == ("warmtepomp",)
        commands = {command.entity_id: command for command in plan.commands}
        assert commands[STOVE].hvac_mode == MODE_HEAT
        assert commands[PUMP].hvac_mode == MODE_OFF
        assert commands[PUMP].reason is Reason.OTHER_SOURCE_CHOSEN

    def test_the_short_cycle_clock_still_returns_to_the_first_choice(self) -> None:
        """De uitwijkklok van de geweigerde eerste keus blijft in het plan staan.

        The refused first choice keeps its fallback clock, so the binding layer
        comes back once the rest has passed and the zone can switch back.
        """
        config, world = _refused_world("short_cycle", reserve_running=True)
        plan = decide(config, world)
        assert any(
            deferral.subject == PUMP and deferral.reason is Reason.SHORT_CYCLE_PROTECTION
            for deferral in plan.deferrals
        )

    def test_a_house_wide_stop_still_refuses_the_zone_instead(self) -> None:
        """Een huisbreed stilgezette eerste keus schuift niet door.

        A first choice stopped house-wide refuses the zone instead of moving on.
        """
        config = DirectorConfig(
            zones=(_zolder_with_reserve(),),
            circuits=(Circuit("buitenunit", "Buitenunit", units=(PUMP,)),),
            openings=(Opening("binary_sensor.dakraam", zone_ids=("hal",), delay=timedelta(0)),),
            house_wide_openings=(PUMP,),
            outdoor_sensor="sensor.buiten",
            outdoor_hysteresis=0.5,
        )
        world = make_world(
            now=NOW,
            outdoor=4.0,
            indoor={"zolder": 18.0},
            climates={PUMP: climate("off"), STOVE: climate("off")},
            openings={
                "binary_sensor.dakraam": OpeningState(
                    open=True, changed_at=NOW - timedelta(hours=1)
                )
            },
        )
        plan = decide(config, world)
        decision = plan.decision_for("zolder")
        assert decision is not None
        assert decision.reason is Reason.OPENING_OPEN_ELSEWHERE
        assert decision.source_id is None
        commands = {command.entity_id: command for command in plan.commands}
        assert commands[STOVE].hvac_mode == MODE_OFF
        assert commands[STOVE].reason is Reason.OPENING_OPEN_ELSEWHERE
