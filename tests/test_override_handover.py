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
    Circuit,
    DirectorConfig,
    Generator,
    ModeFamily,
    ModeSettings,
    Reason,
    Source,
    SourceRole,
    Zone,
    decide,
)

HEAT = ModeSettings(target=21.0, start_at=20.0, hysteresis=1.0)
COOL = ModeSettings(target=24.0, start_at=25.0, hysteresis=1.0)
BOILER = "climate.boiler"
SHARED = "climate.ketel"


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


# ---------------------------------------------------------------------------
# De bronvariant: dezelfde ketel als bron onder twee kamers, geen Generator.
# The source variant: the same boiler as a source under two rooms, no Generator.
# ---------------------------------------------------------------------------


def shared_room(zone_id: str, *extra: Source, priority: int = 0, cool=None) -> Zone:
    """Return a room whose first source is the shared boiler."""
    return Zone(
        zone_id=zone_id,
        name=zone_id,
        indoor_sensor=f"sensor.{zone_id}",
        priority=priority,
        sources=(
            Source(source_id=f"{zone_id}_ketel", entity_id=SHARED, role=SourceRole.HEAT_ONLY),
            *extra,
        ),
        heat=HEAT,
        cool=cool,
    )


SHARED_CONFIG = DirectorConfig(zones=(shared_room("living_room"), shared_room("attic", priority=1)))


def shared_plan(overrides: dict[str, bool], climates: dict[str, object], **indoor: float):
    """Return the plan for the two-room house with one shared boiler."""
    return decide(
        SHARED_CONFIG,
        make_world(indoor=dict(indoor), outdoor=5.0, climates=climates, zone_overrides=overrides),
    )


class TestASharedSourceIsHandedOverToo:
    """Anker 11 geldt ook voor een apparaat dat als bron onder de zone hangt.

    Anchor 11 holds for an appliance hanging under the zone as a source too.
    """

    def test_nothing_is_sent_to_the_shared_source(self) -> None:
        """De andere zone is tevreden, maar de ketel krijgt evengoed niets."""
        plan = shared_plan(
            {"living_room": True}, {SHARED: climate(MODE_HEAT)}, living_room=18.0, attic=23.0
        )
        assert plan.commands == ()
        assert [(item.entity_id, item.reason) for item in plan.untouched] == [
            (SHARED, Reason.MANUAL_OVERRIDE)
        ]

    def test_the_other_zone_cannot_choose_it(self) -> None:
        """De zolder wil warmte, maar de ketel is geen kandidaat meer."""
        plan = shared_plan(
            {"living_room": True}, {SHARED: climate(MODE_HEAT)}, living_room=18.0, attic=18.0
        )
        attic = plan.decision_for("attic")
        assert attic is not None
        assert attic.granted is ModeFamily.NEUTRAL
        assert attic.reason is Reason.NO_SOURCE_AVAILABLE
        assert attic.passed_over == ()
        assert plan.commands == ()

    def test_a_second_source_still_serves_the_other_zone(self) -> None:
        """Een zone met een eigen tweede bron schuift daar gewoon naartoe."""
        config = DirectorConfig(
            zones=(
                shared_room("living_room"),
                shared_room(
                    "attic",
                    Source("attic_klep", "climate.klep", role=SourceRole.HEAT_ONLY),
                    priority=1,
                ),
            )
        )
        plan = decide(
            config,
            make_world(
                indoor={"living_room": 18.0, "attic": 18.0},
                outdoor=5.0,
                climates={SHARED: climate(MODE_HEAT), "climate.klep": climate(MODE_OFF)},
                zone_overrides={"living_room": True},
            ),
        )
        assert {command.entity_id: command.hvac_mode for command in plan.commands} == {
            "climate.klep": MODE_HEAT
        }

    def test_without_an_override_the_shared_source_is_commanded(self) -> None:
        """De regel mag de director niet in het algemeen schuw maken."""
        plan = shared_plan({}, {SHARED: climate(MODE_OFF)}, living_room=18.0, attic=23.0)
        assert {command.entity_id: command.hvac_mode for command in plan.commands} == {
            SHARED: MODE_HEAT
        }

    def test_a_running_handed_over_appliance_holds_its_duty(self) -> None:
        """Het circuit mag de tegenovergestelde taak niet gaan draaien.

        De overgedragen ketel staat te verwarmen, en de zolder wil koelen op een
        unit van hetzelfde circuit. Zonder de overgedragen ketel als vaststaand
        apparaat zou dat circuit koelen en zou er één ruimte verwarmd en gekoeld
        tegelijk worden - precies wat dit ontwerp onbereikbaar hoort te maken.

        The handed-over boiler is heating, and the attic wants to cool on a unit
        of the same circuit. Without the handed-over boiler counted as standing
        firm, that circuit would cool and one room would be heated and cooled at
        once - exactly what this design is meant to make unreachable.
        """
        config = DirectorConfig(
            zones=(
                shared_room("living_room"),
                shared_room(
                    "attic",
                    Source("attic_andere", "climate.andere", role=SourceRole.HEAT_COOL),
                    priority=1,
                    cool=COOL,
                ),
            ),
            circuits=(
                Circuit(
                    circuit_id="c",
                    name="C",
                    units=(SHARED, "climate.andere"),
                    simultaneous_heat_cool=False,
                ),
            ),
        )
        plan = decide(
            config,
            make_world(
                indoor={"living_room": 18.0, "attic": 27.0},
                outdoor=5.0,
                climates={SHARED: climate(MODE_HEAT), "climate.andere": climate(MODE_OFF)},
                zone_overrides={"living_room": True},
            ),
        )
        attic = plan.decision_for("attic")
        assert attic is not None
        assert attic.granted is ModeFamily.NEUTRAL
        assert attic.reason is Reason.CIRCUIT_CONFLICT_LOST
        assert SHARED not in {command.entity_id for command in plan.commands}

    def test_a_running_handed_over_appliance_holds_its_capacity_slot(self) -> None:
        """Het overgedragen apparaat bezet zijn plek op het circuit.

        De capaciteit hing aan een eigen controle in `constraints._keeps_claiming`;
        sinds anker 11 loopt dat via `standing`, en deze toets houdt vast dat die
        weg hetzelfde doet: de ketel draait, niemand stuurt hem, en de zolder mag
        er niet naast gaan draaien.

        The handed-over appliance occupies its slot on the circuit. Capacity used
        to hang on a check of its own in `constraints._keeps_claiming`; since
        anchor 11 that runs through `standing`, and this test pins down that the
        new route does the same: the boiler runs, nobody steers it, and the attic
        may not start beside it.
        """
        config = DirectorConfig(
            zones=(
                shared_room("living_room"),
                shared_room(
                    "attic",
                    Source("attic_andere", "climate.andere", role=SourceRole.HEAT_ONLY),
                    priority=1,
                ),
            ),
            circuits=(
                Circuit(
                    circuit_id="c",
                    name="C",
                    units=(SHARED, "climate.andere"),
                    max_concurrent_units=1,
                ),
            ),
        )
        plan = decide(
            config,
            make_world(
                indoor={"living_room": 18.0, "attic": 18.0},
                outdoor=5.0,
                climates={SHARED: climate(MODE_HEAT), "climate.andere": climate(MODE_OFF)},
                zone_overrides={"living_room": True},
            ),
        )
        attic = plan.decision_for("attic")
        assert attic is not None
        assert attic.granted is ModeFamily.NEUTRAL
        assert attic.reason is Reason.CIRCUIT_AT_CAPACITY
        commands = {command.entity_id: command.hvac_mode for command in plan.commands}
        assert commands.get("climate.andere") == MODE_OFF, "de zolderunit mag niet gaan draaien"
        assert SHARED not in commands, "de overgedragen ketel krijgt niets"
