"""Units die blijven staan: wat de director deze ronde niet kan wegschakelen.

Units that stand firm: what the director cannot stand down this round.

Drie apparaten krijgen met opzet geen opdracht: een onbereikbaar apparaat, een
apparaat in een overgedragen zone, en een draaiend apparaat in een zone
waarvan de binnentemperatuur niet te lezen is. De eerste is weg en doet niets
meer; de andere twee draaien gewoon door.

Precies dat werd nergens meegeteld. Het circuit koos zijn taak alsof die units
er niet waren, en de capaciteitsgrens telde ze niet mee - waardoor de director
de tegengestelde taak op dezelfde buitenunit kon zetten, of er nog een unit bij
kon aanzetten. Dat is de ene toestand die dit ontwerp onbereikbaar hoort te
maken.

Three appliances deliberately get no command: an unreachable one, one in a
zone that has been handed over, and a running one in a zone whose indoor
temperature cannot be read. The first is gone and does nothing; the other two
simply keep running.

Exactly that was counted nowhere. The circuit picked its duty as though those
units did not exist, and the capacity limit left them out - letting the
director put the opposing duty on the same outdoor unit, or start yet another
unit beside them. That is the one state this design is meant to make
unreachable.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from conftest import assert_plan_holds, climate

from custom_components.climate_director.engine import (
    Circuit,
    DirectorConfig,
    ModeFamily,
    ModeSettings,
    Reason,
    Resident,
    ResidentState,
    Season,
    Source,
    WorldState,
    Zone,
    decide,
    validate,
)

NOW = datetime(2026, 7, 13, 14, 0)  # maandag

HEAT = ModeSettings(target=21.0, start_at=20.0, hysteresis=1.0)
COOL = ModeSettings(target=23.0, start_at=24.0, hysteresis=1.0)


def house(*, cap: int | None = None, autostart: bool = True) -> DirectorConfig:
    """Return two rooms on one multi-split that cannot do both duties at once."""
    return DirectorConfig(
        zones=(
            Zone(
                zone_id="woonkamer",
                name="Woonkamer",
                indoor_sensor="sensor.woonkamer",
                priority=0,
                sources=(Source(source_id="woon", entity_id="climate.woon"),),
                heat=HEAT,
                cool=COOL,
            ),
            Zone(
                zone_id="slaapkamer",
                name="Slaapkamer",
                indoor_sensor="sensor.slaapkamer",
                priority=1,
                sources=(
                    Source(
                        source_id="slaap",
                        entity_id="climate.slaap",
                        autostart=autostart,
                    ),
                ),
                heat=HEAT,
                cool=COOL,
            ),
        ),
        circuits=(
            Circuit(
                circuit_id="buiten",
                name="Buitenunit",
                units=("climate.woon", "climate.slaap"),
                simultaneous_heat_cool=False,
                max_concurrent_units=cap,
            ),
        ),
        residents=(Resident(resident_id="danny", presence_entity="person.danny"),),
    )


def world(
    *,
    bedroom_indoor: float | None,
    living_indoor: float,
    outdoor: float,
    season: Season,
    overridden: bool = False,
) -> WorldState:
    """Return a world with the bedroom unit already heating."""
    return WorldState(
        now=NOW,
        outdoor_temperature=outdoor,
        season=season,
        indoor_temperatures={"woonkamer": living_indoor, "slaapkamer": bedroom_indoor},
        climates={
            "climate.woon": climate("off", changed_at=NOW - timedelta(hours=2)),
            "climate.slaap": climate("heat", changed_at=NOW - timedelta(hours=2)),
        },
        residents={"danny": ResidentState(home=True, asleep=False)},
        zone_overrides={"slaapkamer": True} if overridden else {},
    )


def duties(plan, world_state) -> set[ModeFamily]:
    """Return the duties running on the circuit once this plan has landed."""
    from custom_components.climate_director.engine.families import family_of

    after = {
        entity_id: state.hvac_mode
        for entity_id, state in world_state.climates.items()
        if state.available
    }
    for command in plan.commands:
        after[command.entity_id] = command.hvac_mode
    return {family_of(mode) for mode in after.values()} & {ModeFamily.HEAT, ModeFamily.COOL}


def running_units(plan, world_state) -> int:
    """Return how many indoor units keep the compressor once this plan has landed."""
    from custom_components.climate_director.engine.families import family_of

    after = {
        entity_id: state.hvac_mode
        for entity_id, state in world_state.climates.items()
        if state.available
    }
    for command in plan.commands:
        after[command.entity_id] = command.hvac_mode
    return sum(
        1 for mode in after.values() if family_of(mode) in (ModeFamily.HEAT, ModeFamily.COOL)
    )


class TestABlindZoneHoldsItsCircuit:
    """Een kamer zonder leesbare thermometer laat zijn unit draaien - en dus zijn taak.

    A room without a readable thermometer leaves its unit running - and with it
    its duty.
    """

    @pytest.fixture
    def setup(self):
        config = house()
        state = world(
            bedroom_indoor=None,
            living_indoor=30.0,
            outdoor=30.0,
            season=Season.SUMMER,
        )
        return config, state, decide(config, state)

    def test_the_configuration_itself_is_sound(self, setup) -> None:
        config, _state, _plan = setup
        assert not validate(config)

    def test_the_unit_is_left_alone(self, setup) -> None:
        _config, _state, plan = setup
        left = plan.untouched_for("climate.slaap")
        assert left is not None
        assert left.reason is Reason.NO_INDOOR_TEMPERATURE

    def test_the_other_room_does_not_get_the_opposing_duty(self, setup) -> None:
        config, state, plan = setup
        assert len(duties(plan, state)) <= 1, [
            (command.entity_id, command.hvac_mode) for command in plan.commands
        ]
        assert_plan_holds(config, state, plan, where="blinde zone")

    def test_the_other_room_hears_why(self, setup) -> None:
        _config, _state, plan = setup
        decision = plan.decision_for("woonkamer")
        assert decision is not None
        assert decision.granted is ModeFamily.NEUTRAL
        assert decision.reason is Reason.CIRCUIT_CONFLICT_LOST

    def test_the_same_duty_is_still_allowed(self) -> None:
        """Wil de andere kamer hetzelfde, dan staat niets die in de weg."""
        config = house()
        state = world(
            bedroom_indoor=None,
            living_indoor=15.0,
            outdoor=0.0,
            season=Season.WINTER,
        )
        plan = decide(config, state)
        command = plan.command_for("climate.woon")
        assert command is not None
        assert command.hvac_mode == "heat"


class TestAHandedOverZoneHoldsItsCircuit:
    """Een overgedragen zone krijgt niets - ook geen uit - en houdt dus het circuit.

    A zone handed over gets nothing - an off included - and therefore holds the
    circuit.
    """

    @pytest.fixture
    def setup(self):
        config = house()
        state = world(
            bedroom_indoor=18.0,
            living_indoor=30.0,
            outdoor=30.0,
            season=Season.SUMMER,
            overridden=True,
        )
        return config, state, decide(config, state)

    def test_the_unit_is_left_alone(self, setup) -> None:
        _config, _state, plan = setup
        left = plan.untouched_for("climate.slaap")
        assert left is not None
        assert left.reason is Reason.MANUAL_OVERRIDE

    def test_the_other_room_does_not_get_the_opposing_duty(self, setup) -> None:
        config, state, plan = setup
        assert len(duties(plan, state)) <= 1, [
            (command.entity_id, command.hvac_mode) for command in plan.commands
        ]
        assert_plan_holds(config, state, plan, where="overgedragen zone")


class TestTheCapacityLimitCountsThem:
    """Wat blijft draaien bezet een plek op de buitenunit, hoe het ook heet.

    Whatever keeps running occupies a place on the outdoor unit, whatever the
    reason is called.
    """

    def test_a_blind_zone_fills_the_only_place(self) -> None:
        config = house(cap=1)
        state = world(
            bedroom_indoor=None,
            living_indoor=15.0,
            outdoor=0.0,
            season=Season.WINTER,
        )
        plan = decide(config, state)
        assert running_units(plan, state) <= 1, [
            (command.entity_id, command.hvac_mode) for command in plan.commands
        ]
        assert_plan_holds(config, state, plan, where="capaciteit met blinde zone")

    def test_the_other_room_hears_the_place_is_taken(self) -> None:
        config = house(cap=1)
        state = world(
            bedroom_indoor=None,
            living_indoor=15.0,
            outdoor=0.0,
            season=Season.WINTER,
        )
        decision = decide(config, state).decision_for("woonkamer")
        assert decision is not None
        assert decision.reason is Reason.CIRCUIT_AT_CAPACITY

    def test_a_free_place_is_still_used(self) -> None:
        """Twee plekken en een blinde zone: de andere kamer mag gewoon starten."""
        config = house(cap=2)
        state = world(
            bedroom_indoor=None,
            living_indoor=15.0,
            outdoor=0.0,
            season=Season.WINTER,
        )
        command = decide(config, state).command_for("climate.woon")
        assert command is not None
        assert command.hvac_mode == "heat"


class TestAHandOperatedUnitStillStepsAside:
    """Een handbediend apparaat wijkt wél - dat mag deze reparatie niet omdraaien.

    A hand-operated appliance does step aside - this repair must not reverse
    that.
    """

    def test_it_is_stood_down_for_the_opposing_duty(self) -> None:
        config = house(autostart=False)
        state = world(
            bedroom_indoor=18.0,
            living_indoor=30.0,
            outdoor=30.0,
            season=Season.SUMMER,
        )
        plan = decide(config, state)
        command = plan.command_for("climate.slaap")
        assert command is not None
        assert command.hvac_mode == "off"
        assert command.reason is Reason.CIRCUIT_CONFLICT_LOST

    def test_the_asking_room_gets_its_duty(self) -> None:
        config = house(autostart=False)
        state = world(
            bedroom_indoor=18.0,
            living_indoor=30.0,
            outdoor=30.0,
            season=Season.SUMMER,
        )
        command = decide(config, state).command_for("climate.woon")
        assert command is not None
        assert command.hvac_mode == "cool"
