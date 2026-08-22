"""Centrale verwarming tegenover een gezoneerd systeem.

Central heating against a zoned system.

Bij een gesloten systeem staat dezelfde thermostaat als bron onder meerdere
zones. De opdrachten worden per zone opgebouwd, dus zo'n apparaat kreeg er een
van elke zone - en die spreken elkaar tegen zodra de ene kamer warmte vraagt en
de andere niets. Welke er won hing af van de sorteervolgorde: toeval, geen
ontwerp.

With a closed system the same thermostat sits as a source under several zones.
Commands are built per zone, so such an appliance got one from each - and they
contradict each other the moment one room asks for heat and the other does not.
Which one won depended on sort order: chance, not design.
"""

from __future__ import annotations

from conftest import climate, make_world

from custom_components.climate_director.engine import (
    MODE_HEAT,
    MODE_OFF,
    DirectorConfig,
    Generator,
    HeatingLayout,
    ModeSettings,
    Plan,
    Source,
    SourceRole,
    UnitCommand,
    Zone,
    decide,
    validate,
)
from custom_components.climate_director.engine.serialise import (
    config_from_dict,
    config_to_dict,
)

HEAT = ModeSettings(target=21.0, start_at=20.0, hysteresis=1.0)
THERMOSTAT = "climate.thermostat"


def zone(zone_id: str, *sources: Source, priority: int = 0) -> Zone:
    """Return one room."""
    return Zone(
        zone_id=zone_id,
        name=zone_id,
        indoor_sensor=f"sensor.{zone_id}",
        priority=priority,
        sources=sources,
        heat=HEAT,
    )


def shared(source_id: str = "central") -> Source:
    """Return the one thermostat that heats the whole house."""
    return Source(source_id=source_id, entity_id=THERMOSTAT, role=SourceRole.HEAT_ONLY)


def house(**temperatures: float):
    """Return a world at the given indoor temperatures, cold outside."""
    return make_world(
        indoor=dict(temperatures),
        outdoor=5.0,
        climates={THERMOSTAT: climate("off")},
    )


class TestOneAppliance:
    """A shared source gets exactly one command, whatever the zones want."""

    config = DirectorConfig(
        zones=(
            zone("living_room", shared("central_lr"), priority=0),
            zone("bedroom", shared("central_br"), priority=1),
        ),
        heating_layout=HeatingLayout.CENTRAL,
    )

    def test_one_room_cold_the_other_warm(self) -> None:
        """The old behaviour sent both `off` and `heat` to the same entity."""
        plan = decide(self.config, house(living_room=18.0, bedroom=23.0))
        for_thermostat = [c for c in plan.commands if c.entity_id == THERMOSTAT]
        assert len(for_thermostat) == 1, for_thermostat
        assert for_thermostat[0].hvac_mode == MODE_HEAT

    def test_demand_beats_silence_whichever_room_asks(self) -> None:
        """A closed system cannot heat one room and not the other."""
        plan = decide(self.config, house(living_room=23.0, bedroom=18.0))
        for_thermostat = [c for c in plan.commands if c.entity_id == THERMOSTAT]
        assert len(for_thermostat) == 1
        assert for_thermostat[0].hvac_mode == MODE_HEAT

    def test_nobody_asking_switches_it_off(self) -> None:
        plan = decide(self.config, house(living_room=23.0, bedroom=23.0))
        for_thermostat = [c for c in plan.commands if c.entity_id == THERMOSTAT]
        assert len(for_thermostat) == 1
        assert for_thermostat[0].hvac_mode == MODE_OFF

    def test_the_leading_room_is_the_one_with_most_claim(self) -> None:
        """Two rooms asking at once: the appliance follows the ranking zone."""
        plan = decide(self.config, house(living_room=18.0, bedroom=18.0))
        command = next(c for c in plan.commands if c.entity_id == THERMOSTAT)
        assert command.zone_id == "living_room"

    def test_the_live_priority_beats_the_configured_one(self) -> None:
        """Een automatisering die de voorrang omzet, stuurt de gedeelde ketel.

        A automation that flips the priorities steers the shared boiler.
        """
        bedroom = Zone(
            zone_id="bedroom",
            name="bedroom",
            indoor_sensor="sensor.bedroom",
            priority=1,
            sources=(shared("central_br"),),
            heat=ModeSettings(target=23.0, start_at=22.0, hysteresis=1.0),
        )
        config = DirectorConfig(
            zones=(zone("living_room", shared("central_lr"), priority=0), bedroom),
            heating_layout=HeatingLayout.CENTRAL,
        )
        world = make_world(
            indoor={"living_room": 18.0, "bedroom": 18.0},
            outdoor=5.0,
            climates={THERMOSTAT: climate("off")},
            zone_priorities={"living_room": 9, "bedroom": 0},
        )
        plan = decide(config, world)
        command = plan.command_for(THERMOSTAT)
        assert command is not None
        assert command.zone_id == "bedroom"
        assert command.temperature == 23.0


class TestTheChoiceIsRecorded:
    """The setting survives a save, and an old installation is not guessed at twice."""

    def test_it_round_trips(self) -> None:
        for layout in HeatingLayout:
            config = DirectorConfig(zones=(zone("a", shared()),), heating_layout=layout)
            assert config_from_dict(config_to_dict(config)).heating_layout is layout

    def test_an_old_installation_with_a_shared_source_reads_as_central(self) -> None:
        """Inferred, so upgrading never raises a warning about a choice never made."""
        stored = {
            "zones": [
                {"zone_id": "a", "sources": [{"source_id": "s1", "entity_id": THERMOSTAT}]},
                {"zone_id": "b", "sources": [{"source_id": "s2", "entity_id": THERMOSTAT}]},
            ]
        }
        assert config_from_dict(stored).heating_layout is HeatingLayout.CENTRAL

    def test_an_old_installation_with_its_own_appliances_reads_as_zoned(self) -> None:
        stored = {
            "zones": [
                {"zone_id": "a", "sources": [{"source_id": "s1", "entity_id": "climate.a"}]},
                {"zone_id": "b", "sources": [{"source_id": "s2", "entity_id": "climate.b"}]},
            ]
        }
        assert config_from_dict(stored).heating_layout is HeatingLayout.PER_ZONE

    def test_an_old_installation_with_only_a_shared_cooler_reads_as_zoned(self) -> None:
        """Een gedeelde airco die alleen koelt zegt niets over de verwarmingsindeling.

        A shared cooler says nothing about the heating layout, so the reader may
        not turn it into central heating and the check may not complain about it.
        """
        stored = {
            "zones": [
                {
                    "zone_id": "a",
                    "sources": [
                        {"source_id": "s1", "entity_id": "climate.chiller", "role": "cool_only"}
                    ],
                    "cool": {"target": 22.0, "start_at": 24.0},
                },
                {
                    "zone_id": "b",
                    "sources": [
                        {"source_id": "s2", "entity_id": "climate.chiller", "role": "cool_only"}
                    ],
                    "cool": {"target": 22.0, "start_at": 24.0},
                },
            ]
        }
        config = config_from_dict(stored)
        assert config.heating_layout is HeatingLayout.PER_ZONE
        codes = [getattr(item, "code", "") for item in validate(config)]
        assert not [code for code in codes if code.startswith("layout_")], codes

    def test_a_stored_choice_beats_the_guess(self) -> None:
        """Once chosen, nothing infers over it."""
        stored = {
            "heating_layout": "per_zone",
            "zones": [
                {"zone_id": "a", "sources": [{"source_id": "s1", "entity_id": THERMOSTAT}]},
                {"zone_id": "b", "sources": [{"source_id": "s2", "entity_id": THERMOSTAT}]},
            ],
        }
        assert config_from_dict(stored).heating_layout is HeatingLayout.PER_ZONE

    def test_nonsense_falls_back_to_the_guess(self) -> None:
        assert config_from_dict({"heating_layout": 7}).heating_layout is HeatingLayout.PER_ZONE


class TestTheCheckWarns:
    """A warning, never a block: the director keeps regulating either way."""

    def test_zoned_but_wired_centrally(self) -> None:
        config = DirectorConfig(
            zones=(zone("a", shared("s1")), zone("b", shared("s2"))),
            heating_layout=HeatingLayout.PER_ZONE,
        )
        found = validate(config)
        assert any(getattr(item, "code", "") == "layout_zoned_with_shared_source" for item in found)

    def test_central_but_wired_per_room(self) -> None:
        config = DirectorConfig(
            zones=(
                zone("a", Source(source_id="s1", entity_id="climate.a")),
                zone("b", Source(source_id="s2", entity_id="climate.b")),
            ),
            heating_layout=HeatingLayout.CENTRAL,
        )
        found = validate(config)
        assert any(
            getattr(item, "code", "") == "layout_central_without_shared_source" for item in found
        )

    def test_a_matching_installation_is_quiet(self) -> None:
        for layout, sources in (
            (HeatingLayout.CENTRAL, (shared("s1"), shared("s2"))),
            (
                HeatingLayout.PER_ZONE,
                (
                    Source(source_id="s1", entity_id="climate.a"),
                    Source(source_id="s2", entity_id="climate.b"),
                ),
            ),
        ):
            config = DirectorConfig(
                zones=(zone("a", sources[0]), zone("b", sources[1])),
                heating_layout=layout,
            )
            codes = [getattr(item, "code", "") for item in validate(config)]
            assert not [code for code in codes if code.startswith("layout_")], (layout, codes)

    def test_one_zone_is_never_wrong(self) -> None:
        """With a single room the distinction has no meaning yet."""
        for layout in HeatingLayout:
            config = DirectorConfig(zones=(zone("a", shared()),), heating_layout=layout)
            codes = [getattr(item, "code", "") for item in validate(config)]
            assert not [code for code in codes if code.startswith("layout_")]

    def test_a_cooling_only_shared_appliance_does_not_count(self) -> None:
        """This is about heating; a shared cooler says nothing about the layout."""
        cooler = Source(source_id="chiller", entity_id="climate.chiller", role=SourceRole.COOL_ONLY)
        config = DirectorConfig(
            zones=(
                zone("a", Source(source_id="s1", entity_id="climate.a"), cooler),
                zone("b", Source(source_id="s2", entity_id="climate.b"), cooler),
            ),
            heating_layout=HeatingLayout.PER_ZONE,
        )
        codes = [getattr(item, "code", "") for item in validate(config)]
        assert "layout_zoned_with_shared_source" not in codes


class TestAZonedSystemNeedNotHaveManyBoilers:
    """Gezoneerd verwarmen doe je meestal met EEN ketel en kleppen.

    Motorische zoneventielen of zonepompen op een enkele ketel, elk met een
    eigen thermostaat - of lichter, slimme radiatorkranen. Twee losse ketels is
    de uitzondering, niet de regel. Een controle die "gedeelde warmtebron" met
    "centraal systeem" gelijkstelt, wijst zo'n installatie dus ten onrechte af.

    Zoned heating usually runs on ONE boiler with valves: motorised zone valves
    or zone pumps on a single boiler, each with its own thermostat - or lighter,
    smart radiator valves. Two separate boilers is the exception, not the rule.
    A check equating "shared heat source" with "central system" would therefore
    reject such an installation wrongly.
    """

    def valve_system(self, layout: HeatingLayout) -> DirectorConfig:
        """Return one boiler serving two zones, each with its own valve."""
        return DirectorConfig(
            zones=(
                zone(
                    "living_room",
                    Source(
                        source_id="valve_lr",
                        entity_id="climate.valve_lr",
                        role=SourceRole.HEAT_ONLY,
                    ),
                ),
                zone(
                    "bedroom",
                    Source(
                        source_id="valve_br",
                        entity_id="climate.valve_br",
                        role=SourceRole.HEAT_ONLY,
                    ),
                ),
            ),
            generators=(
                Generator(
                    generator_id="boiler",
                    name="Boiler",
                    entity_id="climate.boiler",
                    zone_ids=("living_room", "bedroom"),
                ),
            ),
            heating_layout=layout,
        )

    def test_valves_on_one_boiler_are_zoned(self) -> None:
        codes = [
            getattr(item, "code", "")
            for item in validate(self.valve_system(HeatingLayout.PER_ZONE))
        ]
        assert not [code for code in codes if code.startswith("layout_")]

    def test_calling_that_central_is_flagged(self) -> None:
        codes = [
            getattr(item, "code", "") for item in validate(self.valve_system(HeatingLayout.CENTRAL))
        ]
        assert "layout_central_without_shared_source" in codes

    def test_only_the_asking_room_opens_its_valve(self) -> None:
        """One boiler, but the cold room alone gets heat."""
        plan = decide(
            self.valve_system(HeatingLayout.PER_ZONE),
            make_world(
                indoor={"living_room": 18.0, "bedroom": 23.0},
                outdoor=5.0,
                climates={
                    "climate.valve_lr": climate("off"),
                    "climate.valve_br": climate("off"),
                    "climate.boiler": climate("off"),
                },
            ),
        )
        commands = {c.entity_id: c.hvac_mode for c in plan.commands}
        assert commands["climate.valve_lr"] == MODE_HEAT
        assert commands["climate.valve_br"] == MODE_OFF
        assert commands["climate.boiler"] == MODE_HEAT, "de ketel loopt mee met de vragende zone"

    def test_an_own_appliance_plus_a_shared_boiler_is_zoned(self) -> None:
        """Each room can heat itself; the shared source is only the stand-in.

        Dit is de gewone opstelling van iemand met aircos en gasverwarming. Hem
        waarschuwen zou betekenen dat het vangnet zelf een fout lijkt.

        This is the ordinary setup of somebody with air conditioners and gas
        heating. Warning about it would make the safety net itself look wrong.
        """
        config = DirectorConfig(
            zones=(
                zone(
                    "living_room",
                    Source(source_id="airco_lr", entity_id="climate.airco_lr", priority=0),
                    Source(
                        source_id="gas_lr",
                        entity_id=THERMOSTAT,
                        priority=1,
                        role=SourceRole.HEAT_ONLY,
                    ),
                ),
                zone(
                    "bedroom",
                    Source(source_id="airco_br", entity_id="climate.airco_br", priority=0),
                    Source(
                        source_id="gas_br",
                        entity_id=THERMOSTAT,
                        priority=1,
                        role=SourceRole.HEAT_ONLY,
                    ),
                ),
            ),
            heating_layout=HeatingLayout.PER_ZONE,
        )
        codes = [getattr(item, "code", "") for item in validate(config)]
        assert not [code for code in codes if code.startswith("layout_")], codes

    def test_rooms_with_nothing_of_their_own_are_still_flagged(self) -> None:
        """Two rooms leaning on one appliance and nothing else cannot be zoned."""
        config = DirectorConfig(
            zones=(zone("a", shared("s1")), zone("b", shared("s2"))),
            heating_layout=HeatingLayout.PER_ZONE,
        )
        codes = [getattr(item, "code", "") for item in validate(config)]
        assert "layout_zoned_with_shared_source" in codes

    def test_one_stranded_room_is_not_enough(self) -> None:
        """A single room on the shared appliance can still be settled on its own."""
        config = DirectorConfig(
            zones=(
                zone("a", shared("s1")),
                zone("b", Source(source_id="own", entity_id="climate.b"), shared("s2")),
            ),
            heating_layout=HeatingLayout.PER_ZONE,
        )
        codes = [getattr(item, "code", "") for item in validate(config)]
        assert "layout_zoned_with_shared_source" not in codes


class TestWhoseRunningItIs:
    """Een gedeeld apparaat telt alleen voor de zone die het commando kreeg.

    A shared appliance counts only for the zone that got the command.
    """

    config = DirectorConfig(
        zones=(
            zone("living_room", shared("central_lr"), priority=0),
            zone("bedroom", shared("central_br"), priority=1),
        ),
        heating_layout=HeatingLayout.CENTRAL,
    )

    def _previous(self, zone_id: str) -> Plan:
        return Plan(
            commands=(
                UnitCommand(
                    entity_id=THERMOSTAT,
                    hvac_mode=MODE_HEAT,
                    zone_id=zone_id,
                    source_id=f"central_{zone_id}",
                ),
            )
        )

    def test_the_dead_band_does_not_follow_a_shared_boiler_of_another_zone(self) -> None:
        """De ketel draait voor de woonkamer; de slaapkamer ligt op de startgrens.

        The boiler runs for the living room; the bedroom sits on its switch-on edge.
        """
        from custom_components.climate_director.engine import Reason

        world = make_world(
            indoor={"living_room": 21.5, "bedroom": 20.5},
            outdoor=5.0,
            climates={THERMOSTAT: climate("heat")},
        )
        plan = decide(self.config, world, self._previous("living_room"))
        bedroom = plan.decision_for("bedroom")
        assert bedroom is not None
        # Binnen de band, niet erdoorheen: de slaapkamer ziet zichzelf als
        # stilstaand, dus zijn startpunt blijft op 20 staan.
        #
        # Inside the band, not past it: the bedroom sees itself as not
        # running, so its switch-on point stays at 20.
        assert bedroom.reason is Reason.WITHIN_DEADBAND

    def test_a_shared_boiler_running_elsewhere_does_not_lift_the_quiet_window(self) -> None:
        """Stiltevenster blijft staan: de ketel brandt voor een andere kamer.

        The quiet window holds: the boiler burns for another room.
        """
        from datetime import datetime, time

        from conftest import awake

        from custom_components.climate_director.engine import (
            GateSettings,
            Reason,
            Resident,
            TimeWindow,
        )
        from custom_components.climate_director.engine import gates as gates_module

        config = DirectorConfig(
            zones=self.config.zones,
            heating_layout=HeatingLayout.CENTRAL,
            residents=(Resident("danny", "Danny", presence_entity="person.danny"),),
            gates=GateSettings(quiet_windows=(TimeWindow(time(21, 0), time(9, 0)),)),
        )
        world = make_world(
            now=datetime(2026, 8, 17, 22, 0),
            indoor={"living_room": 21.5, "bedroom": 20.5},
            outdoor=5.0,
            climates={THERMOSTAT: climate("heat")},
            residents={"danny": awake()},
        )
        bedroom = config.zone("bedroom")
        living = config.zone("living_room")
        assert bedroom is not None and living is not None
        assert (
            gates_module.evaluate(config, world, bedroom, self._previous("living_room")).reason
            is Reason.QUIET_HOURS
        )
        assert gates_module.evaluate(config, world, living, self._previous("living_room")).allowed


class TestQuietHoursAndASharedBoiler:
    """Stiltevenster x gedeelde ketel: een rem op beginnen, niet op doorgaan.

    Zonder vorig plan mag een brandende gedeelde ketel niet uitgaan; hij draait
    voor het hele huis en niet namens één kamer. De eerste test hieronder is de
    regressiebewaker voor het solo-geval, de andere twee pinnen de gedeelde
    variant vast.

    With no previous plan a burning shared boiler must not be switched off; it
    runs for the whole house and not on one room's behalf. The first test below
    is the regression guard for the solo case, the other two pin down the shared
    one.
    """

    def _config(self) -> DirectorConfig:
        from datetime import time

        from custom_components.climate_director.engine import GateSettings, TimeWindow

        return DirectorConfig(
            zones=(
                zone("woonkamer", shared("central_woonkamer"), priority=0),
                zone("zolder", shared("central_zolder"), priority=1),
            ),
            heating_layout=HeatingLayout.CENTRAL,
            gates=GateSettings(quiet_windows=(TimeWindow(time(21, 0), time(9, 0)),)),
        )

    def _world(self, *, boiler: str = MODE_HEAT):
        from datetime import datetime

        return make_world(
            now=datetime(2026, 8, 17, 22, 0),
            indoor={"woonkamer": 18.0, "zolder": 18.0},
            outdoor=5.0,
            climates={THERMOSTAT: climate(boiler)},
        )

    def test_a_solo_appliance_keeps_running_without_a_previous_plan(self) -> None:
        """Eén zone op een eigen bron: zonder vorig plan blijft hij gewoon draaien.

        A zone on its own appliance keeps running without a previous plan.
        """
        from datetime import time

        from custom_components.climate_director.engine import GateSettings, ModeFamily, TimeWindow

        config = DirectorConfig(
            zones=(
                zone(
                    "zolder",
                    Source(source_id="eigen", entity_id=THERMOSTAT, role=SourceRole.HEAT_ONLY),
                ),
            ),
            gates=GateSettings(quiet_windows=(TimeWindow(time(21, 0), time(9, 0)),)),
        )
        plan = decide(config, self._world(), None)
        decision = plan.decision_for("zolder")
        assert decision is not None
        assert decision.granted is ModeFamily.HEAT
        command = plan.command_for(THERMOSTAT)
        assert command is not None
        assert command.hvac_mode == MODE_HEAT

    def test_a_shared_appliance_stays_on_without_a_previous_plan(self) -> None:
        """Gedeelde ketel, geen vorig plan: hij blijft draaien in plaats van uit te gaan.

        A shared boiler with no previous plan keeps running instead of being
        switched off.
        """
        from custom_components.climate_director.engine import Reason

        plan = decide(self._config(), self._world(), None)
        woonkamer = plan.decision_for("woonkamer")
        assert woonkamer is not None
        assert Reason.QUIET_HOURS not in woonkamer.closed_gates
        command = plan.command_for(THERMOSTAT)
        assert command is not None
        assert command.hvac_mode == MODE_HEAT

    def test_and_switching_it_on_by_hand_keeps_it_on(self) -> None:
        """Met de hand aangezet blijft hij aan: de volgende ronde draait hem niet terug.

        Switched on by hand it stays on: the next round does not turn it back.
        """
        config = self._config()
        first = decide(config, self._world(), None)
        second = decide(config, self._world(), first)
        command = second.command_for(THERMOSTAT)
        assert command is not None
        assert command.hvac_mode == MODE_HEAT
