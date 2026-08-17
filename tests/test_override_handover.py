"""Een zone met een override is volledig overgedragen - de ketel inbegrepen.

A zone under override is handed over completely - the boiler included.

De override liet de eigen kraan van de zone met rust, maar niet de gedeelde
ketel. Die werd alsnog uitgezet zodra geen enkele niet-overgedragen zone warmte
vroeg. De kamer hield dus zijn kraan terwijl het water koud werd, en wie de zone
tijdelijk aan een eigen automatisering liet, kreeg twee bestuurders die elkaar
tegenwerkten.

The override left the zone's own valve alone, but not the shared boiler. That
was still switched off the moment no un-handed zone asked for heat. So the room
kept its valve while the water went cold, and anyone leaving a zone to an
automation of their own got two drivers working against each other.
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
)

HEAT = ModeSettings(target=21.0, start_at=20.0, hysteresis=1.0)
BOILER = "climate.boiler"


def room(zone_id: str, entity_id: str, priority: int = 0) -> Zone:
    """Return a room with one valve of its own."""
    return Zone(
        zone_id=zone_id,
        name=zone_id,
        indoor_sensor=f"sensor.{zone_id}",
        priority=priority,
        sources=(
            Source(source_id=f"{zone_id}_valve", entity_id=entity_id, role=SourceRole.HEAT_ONLY),
        ),
        heat=HEAT,
    )


CONFIG = DirectorConfig(
    zones=(room("living_room", "climate.valve_lr", 0), room("attic", "climate.valve_at", 1)),
    generators=(
        Generator(
            generator_id="boiler",
            name="Boiler",
            entity_id=BOILER,
            zone_ids=("living_room", "attic"),
        ),
    ),
)

#: De oude automatisering heeft de woonkamer aangezet; de ketel loopt.
#: The old automation has switched the living room on; the boiler runs.
RUNNING = {
    "climate.valve_lr": climate("heat"),
    "climate.valve_at": climate("off"),
    BOILER: climate("heat"),
}


def plan_for(overrides: dict[str, bool], **indoor: float):
    """Return the plan and its commands keyed by entity."""
    plan = decide(
        CONFIG,
        make_world(indoor=dict(indoor), outdoor=5.0, climates=RUNNING, zone_overrides=overrides),
    )
    return {command.entity_id: command.hvac_mode for command in plan.commands}


class TestTheBoilerIsHandedOverToo:
    """What the override promises, it has to keep for shared heat as well."""

    def test_the_boiler_is_left_alone(self) -> None:
        """Nobody else asking, but the handed-over room may still need it."""
        commands = plan_for({"living_room": True}, living_room=18.0, attic=23.0)
        assert BOILER not in commands, commands

    def test_the_zones_own_valve_is_left_alone_as_well(self) -> None:
        commands = plan_for({"living_room": True}, living_room=18.0, attic=23.0)
        assert "climate.valve_lr" not in commands

    def test_another_room_may_still_switch_it_on(self) -> None:
        """Switching on never clashes with a zone that wants heat."""
        commands = plan_for({"living_room": True}, living_room=18.0, attic=18.0)
        assert commands[BOILER] == MODE_HEAT
        assert commands["climate.valve_at"] == MODE_HEAT

    def test_without_an_override_it_is_switched_off_as_before(self) -> None:
        """The rule must not make the director shy in general."""
        commands = plan_for({}, living_room=23.0, attic=23.0)
        assert commands[BOILER] == MODE_OFF

    def test_every_zone_handed_over_means_no_command_at_all(self) -> None:
        commands = plan_for({"living_room": True, "attic": True}, living_room=18.0, attic=18.0)
        assert commands == {}

    def test_a_room_under_the_director_still_gets_its_own_valve(self) -> None:
        """One handed-over room must not stop the other from being regulated."""
        commands = plan_for({"living_room": True}, living_room=23.0, attic=18.0)
        assert commands["climate.valve_at"] == MODE_HEAT
        assert commands[BOILER] == MODE_HEAT


class TestMigratingOneRoomAtATime:
    """The reason this matters: taking over an installation in steps.

    Zet je de schaduwmodus uit terwijl je oude automatiseringen nog draaien,
    dan sturen twee partijen dezelfde apparaten aan. De override is het
    mechanisme om dat te voorkomen: zones die je nog niet gemigreerd hebt zet
    je op override, en die laat de director dan volledig los.

    Switch shadow mode off while your old automations still run and two parties
    steer the same appliances. The override is the mechanism to prevent that:
    put the zones you have not migrated yet under override, and the director
    lets go of them entirely.
    """

    def test_a_half_migrated_house_has_one_driver_per_room(self) -> None:
        commands = plan_for({"living_room": True}, living_room=18.0, attic=18.0)

        # De woonkamer hoort bij de oude automatisering: geen enkele opdracht.
        # The living room belongs to the old automation: no command at all.
        assert "climate.valve_lr" not in commands

        # De zolder is gemigreerd en wordt geregeld, ketel en al.
        # The attic is migrated and gets regulated, boiler included.
        assert commands["climate.valve_at"] == MODE_HEAT
        assert commands[BOILER] == MODE_HEAT
