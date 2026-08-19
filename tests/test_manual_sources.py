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
    Opening,
    OutdoorWindow,
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
        """Een zone die alleen handbediend kan, hoort in de controlelijst te staan.

        Zo'n zone draait inderdaad nooit uit zichzelf - en dat mag de bedoeling
        zijn, maar dan hoort de gebruiker dat zwart-op-wit te zien. Van buiten
        is zo'n installatie namelijk niet te onderscheiden van een zone waarvan
        iemand per ongeluk automatisch starten heeft uitgezet.

        Such a zone indeed never runs of its own accord - and that may well be
        the point, but then the user should see that in black and white. From
        the outside such a setup is indistinguishable from a zone where somebody
        accidentally switched automatic start off.
        """
        complaints = [str(item) for item in validate(house())]
        assert complaints, complaints
        assert all("automatic start off" in item for item in complaints), complaints

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


class TestExclusiveGroupsRuleEachOtherOut:
    """Gas en warmtepomp horen elkaar uit te sluiten, niet toevallig te missen.

    Zonder groep berust die interlock volledig op buitengrenzen die elkaar netjes
    aanvullen. Eén getal verkeerd en ze draaien samen, zonder dat er iets van
    gemeld wordt - want los van elkaar is er niets mis met beide instellingen.

    Without a group that interlock rests entirely on outdoor bounds that happen
    to complement each other. One wrong number and they run together, with
    nothing reported - because taken separately there is nothing wrong with
    either setting.
    """

    def _config(self, attic_from: float, group: tuple[str, ...] | None = ("gas", "attic")):
        from custom_components.climate_director.engine import OutdoorWindow, SourceRole

        return DirectorConfig(
            zones=(
                Zone(
                    "woonkamer",
                    "Woonkamer",
                    "sensor.woonkamer",
                    sources=(
                        Source(
                            "gas",
                            "climate.gas",
                            role=SourceRole.HEAT_ONLY,
                            outdoor=OutdoorWindow(maximum=3.1),
                        ),
                    ),
                    heat=ModeSettings(21.0, 20.0),
                ),
                Zone(
                    "zolder",
                    "Zolder",
                    "sensor.zolder",
                    sources=(
                        Source(
                            "attic", "climate.zolder", outdoor=OutdoorWindow(minimum=attic_from)
                        ),
                    ),
                    heat=ModeSettings(21.0, 20.0),
                ),
            ),
            outdoor_sensor="sensor.buiten",
            exclusive_groups=() if group is None else (frozenset(group),),
        )

    def _overlaps(self, config) -> list[str]:
        return [item for item in validate(config) if "exclusive" in item and "apply" in item]

    def test_bounds_that_meet_are_reported(self) -> None:
        """The real mistake: one unit left at 3.0 while the rest moved to 3.1."""
        found = self._overlaps(self._config(attic_from=3.0))
        assert found
        assert "between 3.0 and 3.1" in found[0]

    def test_bounds_that_line_up_are_silent(self) -> None:
        assert not self._overlaps(self._config(attic_from=3.1))

    def test_without_a_group_nothing_is_checked(self) -> None:
        """Overlapping bounds are perfectly normal until you declare exclusivity."""
        assert not self._overlaps(self._config(attic_from=3.0, group=None))

    def test_two_unbounded_sources_are_reported(self) -> None:
        from custom_components.climate_director.engine import OutdoorWindow

        config = self._config(attic_from=3.1)
        loose = DirectorConfig(
            zones=(
                Zone(
                    "a",
                    "A",
                    "sensor.a",
                    sources=(Source("one", "climate.one", outdoor=OutdoorWindow()),),
                    heat=ModeSettings(21.0, 20.0),
                ),
                Zone(
                    "b",
                    "B",
                    "sensor.b",
                    sources=(Source("two", "climate.two", outdoor=OutdoorWindow()),),
                    heat=ModeSettings(21.0, 20.0),
                ),
            ),
            exclusive_groups=(frozenset({"one", "two"}),),
        )
        assert not self._overlaps(config)
        found = self._overlaps(loose)
        assert found and "every outdoor temperature" in found[0]


class TestAnExclusiveGroupBindsAManualSource:
    """De groep moet ook gelden voor wat jij met de hand aanzet.

    Een exclusieve groep werkt op aanvragen, en een handbediende bron doet er
    nooit een - die is uitgesloten van de bronkeuze. Zonder aparte behandeling
    negeert hij de groep dus straffeloos: gas en slaapkamerairco draaien samen
    en niets houdt ze tegen. Dan is de groep een regel op papier, en dat is
    erger dan geen groep, want je denkt beschermd te zijn.

    An exclusive group works on requests, and a hand-operated source never files
    one - it is excluded from source selection. Without separate handling it
    therefore ignores the group with impunity: gas and the bedroom unit run
    together and nothing stops them. The group is then a rule on paper, which is
    worse than no group, since you believe yourself protected.
    """

    def _config(self, *, grouped: bool = True) -> DirectorConfig:
        from custom_components.climate_director.engine import SourceRole

        return DirectorConfig(
            zones=(
                Zone(
                    "woonkamer",
                    "Woonkamer",
                    "sensor.woonkamer",
                    sources=(Source("gas", "climate.gas", role=SourceRole.HEAT_ONLY),),
                    priority=0,
                    heat=ModeSettings(21.0, 20.0),
                ),
                Zone(
                    "slaapkamer",
                    "Slaapkamer",
                    "sensor.slaapkamer",
                    sources=(Source("bed", BEDROOM, autostart=False),),
                    priority=2,
                    heat=ModeSettings(21.0, 20.0),
                    cool=ModeSettings(23.0, 24.0),
                ),
            ),
            residents=(Resident("danny", "Danny", presence_entity="person.danny"),),
            exclusive_groups=(frozenset({"gas", "bed"}),) if grouped else (),
        )

    def _plan(self, config: DirectorConfig, bedroom: str):
        world = make_world(
            now=NOON,
            outdoor=0.0,
            indoor={"woonkamer": 15.0, "slaapkamer": 21.5},
            climates={"climate.gas": "off", BEDROOM: bedroom},
            residents={"danny": awake()},
            presence={zone.zone_id: PresenceState(occupied=True) for zone in config.zones},
        )
        return decide(config, world)

    def test_it_stands_down_for_the_gas(self) -> None:
        """The living room wants the boiler; the bedroom unit is in its group."""
        result = self._plan(self._config(), bedroom="heat")
        command = command_for(result, BEDROOM)
        assert command is not None
        assert family_of(command.hvac_mode) is ModeFamily.NEUTRAL
        assert command.reason is Reason.EXCLUSIVE_GROUP_LOST

    def test_even_when_they_do_the_same_thing(self) -> None:
        """No circuit and the same duty: only the group rules this out."""
        result = self._plan(self._config(), bedroom="heat")
        assert command_for(result, BEDROOM) is not None

    def test_it_also_stands_down_while_cooling(self) -> None:
        result = self._plan(self._config(), bedroom="cool")
        assert command_for(result, BEDROOM) is not None

    def test_without_the_group_it_is_left_alone(self) -> None:
        """Two appliances in separate rooms may run together; that is normal."""
        assert command_for(self._plan(self._config(grouped=False), bedroom="heat"), BEDROOM) is None

    def test_an_idle_one_is_not_touched(self) -> None:
        assert command_for(self._plan(self._config(), bedroom="off"), BEDROOM) is None

    def test_the_gas_still_gets_its_turn(self) -> None:
        command = command_for(self._plan(self._config(), bedroom="heat"), "climate.gas")
        assert command is not None
        assert family_of(command.hvac_mode) is ModeFamily.HEAT


class TestTheOverrideHandsTheZoneOver:
    """De override is een noodknop van de beheerder, geen slot.

    Wie hem gebruikt wil het apparaat zelf zetten en houden - ook als het buiten
    te koel is om te koelen, ook met een raam open, ook als het binnen al goed
    is. De director stuurt die zone dan niets meer, en dus ook geen uit. Zou hij
    hem alsnog uitzetten, dan was de override precies het tegenovergestelde van
    wat de naam belooft.

    The override is the administrator's emergency handle, not a lock. Whoever
    uses it wants to set the appliance themselves and keep it there - even when
    it is too cool outside to cool, even with a window open, even when the room
    is already fine. The director then sends that zone nothing at all, an off
    included. Were it to switch off anyway, the override would be the exact
    opposite of what its name promises.
    """

    def _config(self) -> DirectorConfig:
        return DirectorConfig(
            zones=(
                Zone(
                    "woonkamer",
                    "Woonkamer",
                    "sensor.woonkamer",
                    sources=(Source("w", LIVING),),
                    heat=ModeSettings(23.0, 22.0),
                    # Koelen mag alleen boven 24 buiten - dat is precies het
                    # geval uit het voorbeeld: binnen te warm, buiten te koel.
                    #
                    # Cooling is allowed above 24 outdoors only - exactly the
                    # case from the example: too warm inside, too cool outside.
                    cool=ModeSettings(23.0, 24.0, outdoor=OutdoorWindow(minimum=24.0)),
                ),
            ),
            residents=(Resident("danny", "Danny", presence_entity="person.danny"),),
            openings=(Opening("binary_sensor.raam", zone_ids=("woonkamer",)),),
        )

    def _plan(self, running: str, *, override: bool, **extra: object):
        from custom_components.climate_director.engine.world import OpeningState

        config = self._config()
        world = make_world(
            now=NOON,
            outdoor=extra.pop("outdoor", 15.0),
            indoor={"woonkamer": extra.pop("indoor", 26.0)},
            climates={LIVING: running},
            residents={"danny": awake()},
            presence={"woonkamer": PresenceState(occupied=True)},
            zone_overrides={"woonkamer": override},
            openings=(
                {"binary_sensor.raam": OpeningState(open=True, changed_at=None)}
                if extra.pop("window_open", False)
                else {}
            ),
        )
        return decide(config, world), config

    def test_a_running_appliance_is_left_alone(self) -> None:
        """Outdoor is 15, cooling starts at 24: without the override it goes off."""
        result, _ = self._plan("cool", override=True)
        assert command_for(result, LIVING) is None

    def test_without_the_override_it_is_switched_off(self) -> None:
        result, _ = self._plan("cool", override=False)
        command = command_for(result, LIVING)
        assert command is not None
        assert family_of(command.hvac_mode) is ModeFamily.NEUTRAL

    def test_an_open_window_does_not_reach_it_either(self) -> None:
        """The one thing that overrules everything else still yields to the override."""
        result, _ = self._plan("cool", override=True, window_open=True)
        assert command_for(result, LIVING) is None

    def test_a_satisfied_room_is_left_alone_too(self) -> None:
        """The dead band is the director's rule, and the director is standing back."""
        result, _ = self._plan("cool", override=True, indoor=18.0)
        assert command_for(result, LIVING) is None

    def test_an_idle_appliance_is_not_started(self) -> None:
        """Hands off means hands off in both directions."""
        result, _ = self._plan("off", override=True, indoor=15.0)
        assert command_for(result, LIVING) is None

    def test_the_zone_still_reports_why(self) -> None:
        result, _ = self._plan("cool", override=True)
        decision = next(item for item in result.zones if item.zone_id == "woonkamer")
        assert decision.reason is Reason.MANUAL_OVERRIDE
