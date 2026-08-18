"""Apparaten waar de director niets naartoe stuurt, en waarom niet.

Appliances the director issues nothing to, and why not.

Niets sturen is iets anders dan niets willen, en tot 6.5.0 zag je dat verschil
niet: de "zou aansturen"-sensor zei `unmanaged`, en dat woord betekent in deze
integratie al iets anders - een unit die aan een buitenunit hangt maar in geen
enkele zone staat. Wie het las dacht dat de director zijn apparaat niet kende,
terwijl hij er juist met opzet vanaf bleef.

Er zijn drie gevallen, en ze vragen niet hetzelfde van je: een overgedragen
zone (jij hebt hem overgenomen), een handbediend apparaat dat niemand in de weg
staat (zo hoort het), en een apparaat dat niet te bereiken is (daar is iets
stuk).

Issuing nothing is not the same as wanting nothing, and up to 6.5.0 you could
not see the difference: the "would command" sensor said `unmanaged`, and in
this integration that word already means something else - a unit hanging on an
outdoor unit but appearing in no zone. Whoever read it took it to mean the
director did not know their appliance, while it was deliberately keeping its
hands off.

There are three cases, and they do not ask the same of you: a zone handed over
(you took it), a hand-operated appliance nobody needs out of the way (as
intended), and an appliance that cannot be reached (something is broken).
"""

from __future__ import annotations

from datetime import datetime

from conftest import awake, climate, make_world

from custom_components.climate_director.engine import (
    Circuit,
    DirectorConfig,
    ModeSettings,
    Reason,
    Resident,
    Source,
    SourceRole,
    Zone,
    decide,
)
from custom_components.climate_director.engine.world import PresenceState

NOON = datetime(2026, 8, 11, 12, 0)

LIVING = "climate.huiskamer"
BEDROOM = "climate.master_bedroom"
BOILER = "climate.ketel"


def house() -> DirectorConfig:
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
            Circuit("airco", "Airco", units=(LIVING, BEDROOM), simultaneous_heat_cool=False),
        ),
        residents=(Resident("danny", "Danny", presence_entity="person.danny"),),
    )


def shared_boiler() -> DirectorConfig:
    """Return two rooms leaning on one boiler, one of them handed over."""
    zones = tuple(
        Zone(
            name,
            name.title(),
            f"sensor.{name}",
            sources=(Source(f"{name}_boiler", BOILER, role=SourceRole.HEAT_ONLY),),
            heat=ModeSettings(21.0, 20.0),
            priority=index,
        )
        for index, name in enumerate(("woonkamer", "zolder"))
    )
    return DirectorConfig(
        zones=zones,
        residents=(Resident("danny", "Danny", presence_entity="person.danny"),),
    )


def plan(
    config: DirectorConfig,
    *,
    indoor: dict[str, float] | None = None,
    climates: dict | None = None,
    overrides: dict[str, bool] | None = None,
):
    world = make_world(
        now=NOON,
        outdoor=10.0,
        indoor=indoor or {"woonkamer": 21.5, "slaapkamer": 21.5},
        climates=climates or {LIVING: "off", BEDROOM: "off"},
        residents={"danny": awake()},
        presence={zone.zone_id: PresenceState(occupied=True) for zone in config.zones},
        zone_overrides=overrides or {},
    )
    return decide(config, world)


class TestTheThreeCases:
    def test_a_hand_operated_appliance_is_left_alone(self) -> None:
        result = plan(house(), indoor={"woonkamer": 21.5, "slaapkamer": 15.0})
        left = result.untouched_for(BEDROOM)
        assert left is not None
        assert left.reason is Reason.MANUAL_SOURCE
        assert left.zone_id == "slaapkamer"
        assert result.command_for(BEDROOM) is None

    def test_a_handed_over_zone_is_left_alone(self) -> None:
        result = plan(house(), overrides={"woonkamer": True})
        left = result.untouched_for(LIVING)
        assert left is not None
        assert left.reason is Reason.MANUAL_OVERRIDE

    def test_an_unreachable_appliance_says_so(self) -> None:
        """Not the same thing: here something is broken rather than intended."""
        result = plan(
            house(),
            climates={LIVING: climate("off", available=False), BEDROOM: "off"},
        )
        left = result.untouched_for(LIVING)
        assert left is not None
        assert left.reason is Reason.SOURCE_UNREACHABLE


class TestItStaysConsistentWithTheCommands:
    """Elk apparaat staat in precies één van de twee lijsten.

    Every appliance sits in exactly one of the two lists.
    """

    def test_a_driven_appliance_is_not_in_the_list(self) -> None:
        result = plan(house(), indoor={"woonkamer": 18.0, "slaapkamer": 21.5})
        assert result.command_for(LIVING) is not None
        assert result.untouched_for(LIVING) is None

    def test_no_appliance_is_in_both(self) -> None:
        result = plan(house(), indoor={"woonkamer": 18.0, "slaapkamer": 15.0})
        commanded = {command.entity_id for command in result.commands}
        left = {item.entity_id for item in result.untouched}
        assert not commanded & left

    def test_every_source_is_accounted_for(self) -> None:
        """A source in neither list is one nobody can explain."""
        config = house()
        result = plan(config, indoor={"woonkamer": 18.0, "slaapkamer": 15.0})
        known = {source.entity_id for _, source in config.sources()}
        seen = {command.entity_id for command in result.commands} | {
            item.entity_id for item in result.untouched
        }
        assert known <= seen

    def test_a_manual_appliance_in_the_way_gets_a_command_instead(self) -> None:
        """Standing aside is a command, so it is not being left alone."""
        result = plan(
            house(),
            indoor={"woonkamer": 30.0, "slaapkamer": 21.5},
            climates={LIVING: "off", BEDROOM: "heat"},
        )
        assert result.command_for(BEDROOM) is not None
        assert result.untouched_for(BEDROOM) is None

    def test_a_shared_appliance_commanded_by_one_zone_is_not_left_alone(self) -> None:
        """The attic hands over, the living room still wants the boiler: it is driven."""
        config = shared_boiler()
        world = make_world(
            now=NOON,
            outdoor=5.0,
            indoor={"woonkamer": 18.0, "zolder": 18.0},
            climates={BOILER: "off"},
            residents={"danny": awake()},
            zone_overrides={"zolder": True},
        )
        result = decide(config, world)
        assert result.command_for(BOILER) is not None
        assert result.untouched_for(BOILER) is None

    def test_a_shared_appliance_nobody_commands_is_named_once(self) -> None:
        config = shared_boiler()
        world = make_world(
            now=NOON,
            outdoor=5.0,
            indoor={"woonkamer": 18.0, "zolder": 18.0},
            climates={BOILER: "off"},
            residents={"danny": awake()},
            zone_overrides={"woonkamer": True, "zolder": True},
        )
        result = decide(config, world)
        entries = [item for item in result.untouched if item.entity_id == BOILER]
        assert len(entries) == 1
        assert entries[0].reason is Reason.MANUAL_OVERRIDE


class TestTheSensorSaysWhichIsWhich:
    """De sensor moet de twee gevallen uit elkaar houden, want dat was het punt.

    The sensor has to keep the two cases apart, which was the whole point.
    """

    def _sensor(self, result):
        from custom_components.climate_director.sensor import CommandSensor

        sensor = CommandSensor.__new__(CommandSensor)

        class Coordinator:
            data = result
            world = None

        sensor.coordinator = Coordinator()
        return sensor

    def _value(self, result, entity_id: str) -> str | None:
        sensor = self._sensor(result)
        sensor._target = entity_id
        return sensor.native_value

    def test_a_command_still_reads_as_the_mode(self) -> None:
        result = plan(house(), indoor={"woonkamer": 18.0, "slaapkamer": 21.5})
        assert self._value(result, LIVING) == "heat"

    def test_left_alone_is_not_called_unmanaged_any_more(self) -> None:
        result = plan(house(), indoor={"woonkamer": 21.5, "slaapkamer": 15.0})
        assert self._value(result, BEDROOM) == "left_alone"

    def test_unreachable_is_its_own_state(self) -> None:
        result = plan(
            house(),
            climates={LIVING: climate("off", available=False), BEDROOM: "off"},
        )
        assert self._value(result, LIVING) == "unreachable"

    def test_the_reason_names_the_exact_case(self) -> None:
        result = plan(house(), overrides={"woonkamer": True})
        sensor = self._sensor(result)
        sensor._target = LIVING
        assert sensor.extra_state_attributes["reason"] == "manual_override"
        assert sensor.extra_state_attributes["zone_id"] == "woonkamer"
