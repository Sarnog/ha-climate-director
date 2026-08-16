"""Tests voor een gedeelde warmtebron met radiatorkranen per kamer.

Tests for a shared heat source with radiator valves per room.

Een cv-systeem werkt anders dan een multi-split. Kranen vechten niet om een
compressortaak - ze verwarmen allemaal alleen maar - dus er valt niets te
verdelen. Wat ze wél delen is het apparaat dat het water warm maakt.

A wet system works differently from a multi-split. Valves do not fight over a
compressor duty - they all only ever heat - so there is nothing to arbitrate.
What they do share is the appliance making the water hot.
"""

from __future__ import annotations

from conftest import climate, make_world

from custom_components.climate_director.engine import (
    MODE_HEAT,
    MODE_OFF,
    DirectorConfig,
    Generator,
    ModeSettings,
    Source,
    SourceRole,
    Zone,
    decide,
    validate,
)

BOILER = "climate.cv_ketel"
ROOMS = ("woonkamer", "keuken", "studeerkamer")


def valve(room: str) -> str:
    """Return the radiator valve's entity id for a room."""
    return f"climate.trv_{room}"


def house(*, generator: Generator | None = None, targets: dict[str, float] | None = None):
    """Return a wet installation: one valve per room, optionally a boiler."""
    targets = targets or {}
    zones = tuple(
        Zone(
            zone_id=room,
            name=room.title(),
            indoor_sensor=f"sensor.{room}",
            sources=(Source(f"{room}_trv", valve(room), role=SourceRole.HEAT_ONLY),),
            heat=ModeSettings(target=targets.get(room, 21.0), start_at=20.0, hysteresis=0.5),
        )
        for room in ROOMS
    )
    return DirectorConfig(zones=zones, generators=(generator,) if generator else ())


def world(**indoor: float):
    """Return a world with every valve and the boiler idle."""
    return make_world(
        indoor=dict(indoor),
        climates={valve(room): climate(MODE_OFF) for room in ROOMS} | {BOILER: climate(MODE_OFF)},
    )


def modes(plan) -> dict[str, str]:
    return {command.entity_id: command.hvac_mode for command in plan.commands}


class TestValvesWithoutAGenerator:
    """Tado and the like fire their own burner; nothing extra is needed."""

    def test_each_room_gets_its_own_answer(self) -> None:
        plan = decide(house(), world(woonkamer=18.0, keuken=22.0, studeerkamer=19.0))
        assert modes(plan)[valve("woonkamer")] == MODE_HEAT
        assert modes(plan)[valve("keuken")] == MODE_OFF
        assert modes(plan)[valve("studeerkamer")] == MODE_HEAT

    def test_valves_never_fight_one_another(self) -> None:
        """No circuit is involved, so no room can displace another."""
        plan = decide(house(), world(woonkamer=18.0, keuken=18.0, studeerkamer=18.0))
        assert all(mode == MODE_HEAT for mode in modes(plan).values())


class TestASharedBoiler:
    generator = Generator("cv", "CV", BOILER)

    def test_it_runs_while_any_room_asks(self) -> None:
        plan = decide(
            house(generator=self.generator),
            world(woonkamer=18.0, keuken=22.0, studeerkamer=22.0),
        )
        assert modes(plan)[BOILER] == MODE_HEAT

    def test_it_stops_once_no_room_asks(self) -> None:
        plan = decide(
            house(generator=self.generator),
            world(woonkamer=22.0, keuken=22.0, studeerkamer=22.0),
        )
        assert modes(plan)[BOILER] == MODE_OFF

    def test_it_follows_the_warmest_demand(self) -> None:
        """The coldest setpoint would leave the room asking hardest short."""
        plan = decide(
            house(generator=self.generator, targets={"woonkamer": 21.0, "keuken": 23.0}),
            world(woonkamer=18.0, keuken=18.0, studeerkamer=22.0),
        )
        command = plan.command_for(BOILER)
        assert command is not None
        assert command.temperature == 23.0

    def test_a_fixed_setpoint_wins_over_the_rooms(self) -> None:
        plan = decide(
            house(generator=Generator("cv", "CV", BOILER, setpoint=60.0)),
            world(woonkamer=18.0, keuken=22.0, studeerkamer=22.0),
        )
        command = plan.command_for(BOILER)
        assert command is not None
        assert command.temperature == 60.0

    def test_the_boiler_starts_after_the_valves(self) -> None:
        """Firing it first would heat water against closed radiators."""
        plan = decide(
            house(generator=self.generator),
            world(woonkamer=18.0, keuken=22.0, studeerkamer=22.0),
        )
        order = [command.entity_id for command in plan.commands]
        assert order.index(valve("woonkamer")) < order.index(BOILER)

    def test_an_unavailable_boiler_is_not_commanded(self) -> None:
        state = world(woonkamer=18.0, keuken=22.0, studeerkamer=22.0)
        state = make_world(
            indoor=state.indoor_temperatures,
            climates=dict(state.climates) | {BOILER: climate(MODE_OFF, available=False)},
        )
        assert decide(house(generator=self.generator), state).command_for(BOILER) is None


class TestAGeneratorServingSomeRooms:
    """A house where only part of the rooms hang off one boiler."""

    generator = Generator("cv", "CV", BOILER, zone_ids=("woonkamer", "keuken"))

    def test_a_room_it_serves_fires_it(self) -> None:
        plan = decide(
            house(generator=self.generator),
            world(woonkamer=18.0, keuken=22.0, studeerkamer=22.0),
        )
        assert modes(plan)[BOILER] == MODE_HEAT

    def test_a_room_it_does_not_serve_leaves_it_alone(self) -> None:
        plan = decide(
            house(generator=self.generator),
            world(woonkamer=22.0, keuken=22.0, studeerkamer=18.0),
        )
        assert modes(plan)[BOILER] == MODE_OFF
        assert modes(plan)[valve("studeerkamer")] == MODE_HEAT


class TestValidation:
    def test_a_sound_wet_installation_has_no_problems(self) -> None:
        assert validate(house(generator=Generator("cv", "CV", BOILER))) == ()

    def test_a_generator_that_is_also_a_source(self) -> None:
        """It would receive two commands, one per role, and they could disagree."""
        config = house(generator=Generator("cv", "CV", valve("woonkamer")))
        assert any("already a zone's source" in problem for problem in validate(config))

    def test_a_generator_naming_an_unknown_zone(self) -> None:
        config = house(generator=Generator("cv", "CV", BOILER, zone_ids=("kelder",)))
        assert any("unknown zone kelder" in problem for problem in validate(config))
