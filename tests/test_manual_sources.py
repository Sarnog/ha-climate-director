"""Een bron die je zelf aanzet en die de director met rust laat.

A source you switch on yourself and the director leaves alone.

Een slaapkamerairco hoeft niet mee met een rooster. Je zet hem aan als je hem
wilt, en verder moet niemand eraan zitten. Maar hij hangt wel aan dezelfde
buitenunit als de rest, dus als de woonkamer wil koelen terwijl hij verwarmt,
moet hij wijken - anders houdt hij een kamer met meer voorrang tegen.

A bedroom air conditioner need not follow a schedule. You switch it on when you
want it, and nobody else should touch it. It does hang on the same outdoor unit
as the rest, though, so when the living room wants to cool while it heats, it
must give way - otherwise it holds back a room with more claim.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from conftest import awake, make_world

from custom_components.climate_director.engine import (
    Circuit,
    DirectorConfig,
    ModeSettings,
    Reason,
    Resident,
    Source,
    Zone,
    decide,
    validate,
)
from custom_components.climate_director.engine.families import ModeFamily, family_of
from custom_components.climate_director.engine.serialise import config_from_dict, config_to_dict
from custom_components.climate_director.engine.world import PresenceState

NOON = datetime(2026, 8, 11, 12, 0)

LIVING = "climate.huiskamer"
BEDROOM = "climate.master_bedroom"


def house(*, simultaneous: bool = False) -> DirectorConfig:
    """Return a living room the director drives and a bedroom it does not."""
    return DirectorConfig(
        zones=(
            Zone(
                "woonkamer",
                "Woonkamer",
                "sensor.woonkamer",
                sources=(Source("w", LIVING),),
                priority=0,
                heat=ModeSettings(21.0, 20.0),
                cool=ModeSettings(23.0, 24.0),
            ),
            Zone(
                "slaapkamer",
                "Slaapkamer",
                "sensor.slaapkamer",
                sources=(Source("s", BEDROOM, autostart=False),),
                priority=2,
                heat=ModeSettings(21.0, 20.0),
                cool=ModeSettings(23.0, 24.0),
            ),
        ),
        circuits=(
            Circuit(
                "airco",
                "Airco",
                units=(LIVING, BEDROOM),
                simultaneous_heat_cool=simultaneous,
            ),
        ),
        residents=(Resident("danny", "Danny", presence_entity="person.danny"),),
    )


def plan(config: DirectorConfig, living: float, bedroom: float, running: dict[str, str]):
    world = make_world(
        now=NOON,
        outdoor=10.0,
        indoor={"woonkamer": living, "slaapkamer": bedroom},
        climates=dict(running),
        residents={"danny": awake()},
        presence={zone.zone_id: PresenceState(occupied=True) for zone in config.zones},
    )
    return decide(config, world)


def command_for(result, entity_id: str):
    return next((item for item in result.commands if item.entity_id == entity_id), None)


class TestItIsNeverStarted:
    """The whole reason for the setting: leave my bedroom alone."""

    def test_a_cold_bedroom_gets_no_command(self) -> None:
        """Fifteen degrees and heating allowed, and still nothing happens."""
        result = plan(house(), living=21.5, bedroom=15.0, running={LIVING: "off", BEDROOM: "off"})
        assert command_for(result, BEDROOM) is None

    def test_a_hot_bedroom_gets_no_command(self) -> None:
        result = plan(house(), living=21.5, bedroom=30.0, running={LIVING: "off", BEDROOM: "off"})
        assert command_for(result, BEDROOM) is None

    def test_the_living_room_is_still_driven(self) -> None:
        """Only that one source steps aside; the rest of the house is unchanged."""
        result = plan(house(), living=15.0, bedroom=15.0, running={LIVING: "off", BEDROOM: "off"})
        command = command_for(result, LIVING)
        assert command is not None
        assert family_of(command.hvac_mode) is ModeFamily.HEAT

    def test_it_is_left_alone_while_running(self) -> None:
        """Somebody switched it on. Nothing here has any business switching it off."""
        result = plan(house(), living=21.5, bedroom=21.5, running={LIVING: "off", BEDROOM: "heat"})
        assert command_for(result, BEDROOM) is None

    def test_it_is_left_alone_when_the_rest_agrees(self) -> None:
        """It heats, the living room heats: nobody is in anybody's way."""
        result = plan(house(), living=15.0, bedroom=21.5, running={LIVING: "heat", BEDROOM: "heat"})
        assert command_for(result, BEDROOM) is None


class TestItGivesWay:
    """Running against the circuit is the one thing it may not do."""

    def test_it_is_switched_off_for_a_clashing_duty(self) -> None:
        """It heats, the living room needs to cool, and they share a compressor."""
        result = plan(house(), living=30.0, bedroom=21.5, running={LIVING: "off", BEDROOM: "heat"})
        command = command_for(result, BEDROOM)
        assert command is not None
        assert family_of(command.hvac_mode) is ModeFamily.NEUTRAL
        assert command.reason is Reason.CIRCUIT_CONFLICT_LOST

    def test_the_living_room_gets_what_it_asked_for(self) -> None:
        result = plan(house(), living=30.0, bedroom=21.5, running={LIVING: "off", BEDROOM: "heat"})
        command = command_for(result, LIVING)
        assert command is not None
        assert family_of(command.hvac_mode) is ModeFamily.COOL

    def test_a_circuit_that_can_do_both_leaves_it_alone(self) -> None:
        """With nothing to fight over there is nothing to stand down for."""
        config = house(simultaneous=True)
        result = plan(config, living=30.0, bedroom=21.5, running={LIVING: "off", BEDROOM: "heat"})
        assert command_for(result, BEDROOM) is None

    def test_an_idle_bedroom_needs_no_standing_down(self) -> None:
        result = plan(house(), living=30.0, bedroom=21.5, running={LIVING: "off", BEDROOM: "off"})
        assert command_for(result, BEDROOM) is None

    def test_it_does_not_block_the_living_room(self) -> None:
        """The point of standing it down: the room with more claim gets served."""
        result = plan(house(), living=30.0, bedroom=21.5, running={LIVING: "off", BEDROOM: "heat"})
        served = {item.zone_id for item in result.zones if item.granted is not ModeFamily.NEUTRAL}
        assert "woonkamer" in served


class TestTheZoneItself:
    def test_it_never_reports_being_served(self) -> None:
        result = plan(house(), living=21.5, bedroom=15.0, running={LIVING: "off", BEDROOM: "off"})
        bedroom = next(item for item in result.zones if item.zone_id == "slaapkamer")
        assert bedroom.granted is ModeFamily.NEUTRAL

    def test_a_zone_with_only_manual_sources_is_reported(self) -> None:
        """It can never run on its own, and saying so beats silent nothing."""
        assert any("can never run on its own" in item for item in validate(house()))

    def test_a_zone_with_one_of_each_is_sound(self) -> None:
        config = DirectorConfig(
            zones=(
                Zone(
                    "z",
                    "Z",
                    "sensor.z",
                    sources=(Source("a", "climate.a"), Source("b", "climate.b", autostart=False)),
                    heat=ModeSettings(21.0, 20.0),
                ),
            )
        )
        assert not any("can never run on its own" in item for item in validate(config))


class TestItSurvivesStorage:
    def test_it_round_trips(self) -> None:
        config = house()
        assert config_from_dict(config_to_dict(config)) == config

    def test_older_options_keep_starting_their_appliances(self) -> None:
        """Every source stored before this setting existed must keep its behaviour."""
        config = config_from_dict(
            {"zones": [{"zone_id": "z", "sources": [{"source_id": "a", "entity_id": "climate.a"}]}]}
        )
        assert config.zones[0].sources[0].autostart is True


class TestTheChangeoverPauseDoesNotDeadlock:
    """A pause before switching duty must not keep the manual unit alive.

    De klem: zolang de handbediende unit draait houdt hij het circuit op zijn
    taak, dus de woonkamer krijgt niets toegekend. Keken we naar toekenningen in
    plaats van naar vragen, dan wachtte de een op de ander en gebeurde er nooit
    meer iets - met een pauze van vijf seconden al genoeg om vast te lopen.

    The deadlock: while the manual unit runs it holds the circuit to its duty,
    so the living room is granted nothing. Were we to look at grants rather than
    at wishes, each would wait on the other and nothing would ever happen again
    - a five second pause being quite enough to hang on.
    """

    def _config(self, pause: int) -> DirectorConfig:
        base = house()
        circuit = base.circuits[0]
        return DirectorConfig(
            zones=base.zones,
            circuits=(
                Circuit(
                    circuit.circuit_id,
                    circuit.name,
                    units=circuit.units,
                    simultaneous_heat_cool=False,
                    family_switch_delay=timedelta(seconds=pause),
                    min_family_switch_interval=timedelta(minutes=3),
                ),
            ),
            residents=base.residents,
        )

    @pytest.mark.parametrize("pause", [0, 5, 15, 300])
    def test_it_stands_down_whatever_the_pause(self, pause: int) -> None:
        result = plan(
            self._config(pause),
            living=30.0,
            bedroom=21.5,
            running={LIVING: "off", BEDROOM: "heat"},
        )
        command = command_for(result, BEDROOM)
        assert command is not None, f"pauze {pause}s liet de slaapkamer draaien"
        assert family_of(command.hvac_mode) is ModeFamily.NEUTRAL

    def test_a_wish_is_enough_even_without_a_grant(self) -> None:
        """The living room may still be waiting out the pause; it asked, and that counts."""
        result = plan(
            self._config(300),
            living=30.0,
            bedroom=21.5,
            running={LIVING: "off", BEDROOM: "heat"},
        )
        living = next(item for item in result.zones if item.zone_id == "woonkamer")
        assert living.granted is ModeFamily.NEUTRAL
        assert command_for(result, BEDROOM) is not None

    def test_nobody_asking_still_leaves_it_alone(self) -> None:
        """No wish anywhere means it is in nobody's way, pause or no pause."""
        result = plan(
            self._config(300),
            living=21.5,
            bedroom=21.5,
            running={LIVING: "off", BEDROOM: "heat"},
        )
        assert command_for(result, BEDROOM) is None
