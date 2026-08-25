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
    MODE_OFF,
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
    manual_only_problems,
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

    def test_a_zone_with_only_manual_sources_is_sound_but_noticed(self) -> None:
        """Een zone die alleen handbediend kan, is geen fout maar hoort een melding.

        Zo'n zone draait inderdaad nooit uit zichzelf - en dat mag de bedoeling
        zijn. De controlelijst hoort er daarom schoon over te blijven; de
        eenmalige melding (`manual_only_problems`) noemt hem wél, zodat de
        gebruiker weet dat dit zo ingesteld staat.

        Such a zone indeed never runs of its own accord - and that may well be
        the point. The problem list should therefore stay clean about it; the
        one-time notice (`manual_only_problems`) does name it, so the user knows
        this is how it is set up.
        """
        assert validate(house()) == ()
        noticed = [str(item) for item in manual_only_problems(house())]
        assert noticed, noticed
        assert all("automatic start off" in item for item in noticed), noticed

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

    def test_overlapping_bounds_are_no_complaint(self) -> None:
        """Elkaar kunnen tegenkomen is de reden dat de groep bestaat.

        Hier stond de omgekeerde eis: buitengrenzen die elkaar raken werden
        gemeld, met het advies ze aansluitend te maken. Dat advies maakt de
        groep juist zinloos - hij bestaat om te kiezen tussen apparaten die
        elkaar wel kunnen tegenkomen, en de eigen jaartest moest die melding al
        wegfilteren.

        Being able to meet is the reason the group exists. The opposite demand
        stood here: outdoor bounds that touch were reported, advising you to
        make them adjacent. That advice is what makes the group pointless - it
        exists to choose between appliances that can meet, and the year test had
        to filter that notice out already.
        """
        assert not validate(self._config(attic_from=3.0))

    def test_bounds_that_line_up_are_no_complaint_either(self) -> None:
        assert not validate(self._config(attic_from=3.1))

    def test_the_group_still_rules_them_out(self) -> None:
        """Geen melding betekent niet dat de groep niets doet."""
        from conftest import awake, make_world

        from custom_components.climate_director.engine.families import family_of

        config = self._config(attic_from=3.0)
        world = make_world(
            now=NOON,
            outdoor=5.0,
            indoor={"woonkamer": 15.0, "zolder": 15.0},
            climates={LIVING: MODE_OFF, "climate.zolder": MODE_OFF},
            residents={"danny": awake()},
        )
        started = [
            command
            for command in decide(config, world).commands
            if family_of(command.hvac_mode) is not ModeFamily.NEUTRAL
        ]
        assert len(started) <= 1, started


class TestAnExclusiveGroupBindsAManualSource:
    """De groep geldt twee kanten op, ook voor wat jij met de hand aanzet.

    Een exclusieve groep werkt op aanvragen, en een handbediende bron doet er
    nooit een - die is uitgesloten van de bronkeuze. Draait hij, dan bezet hij
    de groep: een ander lid moet wachten, net zoals hij zou wachten als dat
    andere lid al draaide. Zo kunnen gas en slaapkamerairco nooit samen draaien,
    wie van de twee er ook als eerste was.

    An exclusive group works on requests, and a hand-operated source never files
    one - it is excluded from source selection. When it runs it occupies the
    group: another member has to wait, just as it would if that other member
    were already running. That way gas and the bedroom unit can never run
    together, whichever of the two was there first.
    """

    def _config(
        self, *, grouped: bool = True, living_priority: int = 0, bedroom_priority: int = 2
    ) -> DirectorConfig:
        from custom_components.climate_director.engine import SourceRole

        return DirectorConfig(
            zones=(
                Zone(
                    "woonkamer",
                    "Woonkamer",
                    "sensor.woonkamer",
                    sources=(Source("gas", "climate.gas", role=SourceRole.HEAT_ONLY),),
                    priority=living_priority,
                    heat=ModeSettings(21.0, 20.0),
                ),
                Zone(
                    "slaapkamer",
                    "Slaapkamer",
                    "sensor.slaapkamer",
                    sources=(Source("bed", BEDROOM, autostart=False),),
                    priority=bedroom_priority,
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

    def test_a_running_one_yields_to_a_stronger_request(self) -> None:
        """Draait de slaapkamerairco, dan wijkt hij voor een gasverzoek met meer voorrang.

        When the bedroom unit runs, it yields to a boiler request with more claim.
        """
        result = self._plan(self._config(), bedroom="heat")
        boiler = command_for(result, "climate.gas")
        bedroom = command_for(result, BEDROOM)
        assert boiler is not None and family_of(boiler.hvac_mode) is ModeFamily.HEAT
        assert bedroom is not None and bedroom.hvac_mode == MODE_OFF
        assert bedroom.reason is Reason.EXCLUSIVE_GROUP_LOST

    def test_even_when_they_do_the_same_thing(self) -> None:
        """No circuit and the same duty: only the group rules this out."""
        result = self._plan(self._config(), bedroom="heat")
        bedroom = command_for(result, BEDROOM)
        assert bedroom is not None and bedroom.reason is Reason.EXCLUSIVE_GROUP_LOST

    def test_it_also_yields_while_cooling(self) -> None:
        result = self._plan(self._config(), bedroom="cool")
        boiler = command_for(result, "climate.gas")
        bedroom = command_for(result, BEDROOM)
        assert boiler is not None and family_of(boiler.hvac_mode) is ModeFamily.HEAT
        assert bedroom is not None and bedroom.hvac_mode == MODE_OFF
        assert bedroom.reason is Reason.EXCLUSIVE_GROUP_LOST

    def test_without_a_stronger_request_it_keeps_the_group(self) -> None:
        """Zonder verzoek met méér voorrang blijft de slaapkamerairco draaien.

        Without a request that outranks it, the bedroom unit keeps the group.
        """
        result = self._plan(self._config(living_priority=2, bedroom_priority=0), bedroom="heat")
        assert command_for(result, BEDROOM) is None
        boiler = command_for(result, "climate.gas")
        assert boiler is not None and boiler.hvac_mode == MODE_OFF
        assert boiler.reason is Reason.EXCLUSIVE_GROUP_LOST

    def test_without_the_group_it_is_left_alone(self) -> None:
        """Two appliances in separate rooms may run together; that is normal."""
        assert command_for(self._plan(self._config(grouped=False), bedroom="heat"), BEDROOM) is None

    def test_an_idle_one_is_not_touched(self) -> None:
        assert command_for(self._plan(self._config(), bedroom="off"), BEDROOM) is None

    def test_the_gas_still_gets_its_turn_when_the_bedroom_is_idle(self) -> None:
        command = command_for(self._plan(self._config(), bedroom="off"), "climate.gas")
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


class TestItOnlyCountsWhatIsOnItsOwnCircuit:
    """Wie "hetzelfde wil" maar op een ander apparaat, staat deze unit niet bij.

    Whoever "wants the same" but on another appliance is no ally to this unit.

    Een handbediende unit blijft staan zolang een andere kamer op dat circuit
    dezelfde taak vraagt - anders zou hij wijken voor niets. Maar er werd
    gekeken naar élke zone die ergens een bron op dit circuit heeft, ook als
    het verzoek van die zone naar een heel ander apparaat ging. Vroeg zo'n
    zone koelen via een reservebron buiten het circuit, dan telde dat als
    "koelen is hier gewenst" en bleef de handbediende unit koelen - terwijl het
    circuit ondertussen aan een derde kamer werd toegekend om te verwarmen.

    A hand-operated unit stays put as long as another room on that circuit asks
    for the same duty - otherwise it would step aside for nothing. But every
    zone with a source somewhere on this circuit counted, even when that zone's
    request went to a wholly different appliance. If such a zone asked to cool
    through a reserve source off the circuit, that counted as "cooling is wanted
    here" and the hand-operated unit kept cooling - while the circuit was
    meanwhile granted to a third room to heat.
    """

    OWN = "climate.eigen"
    RESERVE = "climate.reserve"
    OTHER = "climate.andere"

    def config(self) -> DirectorConfig:
        warm = ModeSettings(21.0, 20.0)
        chill = ModeSettings(23.0, 24.0)
        return DirectorConfig(
            zones=(
                Zone(
                    "slaapkamer",
                    "Slaapkamer",
                    "sensor.slaapkamer",
                    sources=(Source("slaap", BEDROOM, autostart=False),),
                    priority=0,
                    heat=warm,
                    cool=chill,
                ),
                Zone(
                    "zolder",
                    "Zolder",
                    "sensor.zolder",
                    sources=(
                        # De eigen unit hangt aan het circuit maar mag bij deze
                        # buitentemperatuur niet; de reserve staat er los van.
                        Source("zolder_eigen", self.OWN, outdoor=OutdoorWindow(minimum=3.1)),
                        Source("zolder_reserve", self.RESERVE, priority=5),
                    ),
                    priority=1,
                    heat=warm,
                    cool=chill,
                ),
                Zone(
                    "woonkamer",
                    "Woonkamer",
                    "sensor.woonkamer",
                    sources=(Source("woon", self.OTHER),),
                    priority=2,
                    heat=warm,
                    cool=chill,
                ),
            ),
            circuits=(
                Circuit(
                    circuit_id="buiten",
                    name="Buitenunit",
                    units=(BEDROOM, self.OWN, self.OTHER),
                    simultaneous_heat_cool=False,
                ),
            ),
            residents=(Resident("danny", presence_entity="person.danny"),),
            outdoor_sensor="sensor.buiten",
        )

    def plan(self):
        config = self.config()
        world = make_world(
            now=NOON,
            outdoor=-12.0,
            indoor={"slaapkamer": 22.0, "zolder": 28.0, "woonkamer": 15.0},
            climates={
                BEDROOM: "cool",
                self.OWN: MODE_OFF,
                self.RESERVE: MODE_OFF,
                self.OTHER: MODE_OFF,
            },
            residents={"danny": awake()},
        )
        return config, world, decide(config, world)

    def test_the_configuration_is_sound(self) -> None:
        assert not validate(self.config())

    def test_the_attic_really_falls_back_off_the_circuit(self) -> None:
        _config, _world, result = self.plan()
        decision = result.decision_for("zolder")
        assert decision is not None
        assert decision.source_id == "zolder_reserve"

    def test_the_hand_operated_unit_steps_aside(self) -> None:
        _config, _world, result = self.plan()
        command = command_for(result, BEDROOM)
        assert command is not None, "de handbediende unit bleef koelen"
        assert family_of(command.hvac_mode) is ModeFamily.NEUTRAL

    def test_the_circuit_ends_up_in_one_duty(self) -> None:
        """Alleen de units op deze buitenunit tellen; de reserve heeft een eigen."""
        config, world, result = self.plan()
        units = config.circuits[0].units
        after = {
            entity_id: state.hvac_mode
            for entity_id, state in world.climates.items()
            if state.available and entity_id in units
        }
        for command in result.commands:
            if command.entity_id in units:
                after[command.entity_id] = command.hvac_mode
        duties = {family_of(mode) for mode in after.values()} & {
            ModeFamily.HEAT,
            ModeFamily.COOL,
        }
        assert len(duties) <= 1, after


class TestItFollowsTheDutyTheCircuitActuallyRuns:
    """Een kamer die het circuit verliest, houdt deze unit niet overeind.

    A room that loses the circuit does not keep this unit standing.

    De unit blijft staan zolang een andere kamer op dit circuit dezelfde taak
    vraagt. Maar vragen is niet krijgen: vragen er twee kamers om tegengestelde
    taken, dan wint er één en gaat het circuit op díé taak draaien. De
    handbediende unit keek naar de vraag en niet naar de uitkomst, dus bleef hij
    koelen omdat een kamer dat gevraagd had - terwijl diezelfde kamer net was
    weggestemd en het circuit stond te verwarmen.

    The unit stays put as long as another room on this circuit asks for the same
    duty. But asking is not getting: when two rooms ask for opposing duties one
    wins and the circuit runs *that* duty. The hand-operated unit looked at the
    asking rather than at the outcome, so it kept cooling because a room had
    asked for it - while that same room had just been outvoted and the circuit
    stood there heating.
    """

    HOT = "climate.warme_kamer"
    COLD = "climate.koude_kamer"

    def config(self) -> DirectorConfig:
        warm = ModeSettings(21.0, 20.0)
        chill = ModeSettings(23.0, 24.0)
        return DirectorConfig(
            zones=(
                Zone(
                    "keuken",
                    "Keuken",
                    "sensor.keuken",
                    sources=(Source("keuken", self.COLD),),
                    priority=0,
                    heat=warm,
                    cool=chill,
                ),
                Zone(
                    "woonkamer",
                    "Woonkamer",
                    "sensor.woonkamer",
                    sources=(Source("woon", self.HOT),),
                    priority=1,
                    heat=warm,
                    cool=chill,
                ),
                Zone(
                    "slaapkamer",
                    "Slaapkamer",
                    "sensor.slaapkamer",
                    sources=(Source("slaap", BEDROOM, autostart=False),),
                    priority=2,
                    heat=warm,
                    cool=chill,
                ),
            ),
            circuits=(
                Circuit(
                    circuit_id="buiten",
                    name="Buitenunit",
                    units=(self.COLD, self.HOT, BEDROOM),
                    simultaneous_heat_cool=False,
                ),
            ),
            residents=(Resident("danny", presence_entity="person.danny"),),
        )

    def plan(self):
        config = self.config()
        world = make_world(
            now=NOON,
            # De keuken heeft de meeste voorrang en wil verwarmen; de woonkamer
            # wil koelen en verliest. De slaapkamer staat met de hand op koelen.
            indoor={"keuken": 15.0, "woonkamer": 30.0, "slaapkamer": 22.0},
            climates={self.COLD: MODE_OFF, self.HOT: MODE_OFF, BEDROOM: "cool"},
            residents={"danny": awake()},
        )
        return config, world, decide(config, world)

    def test_the_circuit_really_runs_the_other_duty(self) -> None:
        _config, _world, result = self.plan()
        circuit = result.circuits[0]
        assert circuit.family is ModeFamily.HEAT
        assert circuit.winner_zone_id == "keuken"

    def test_the_losing_room_asked_for_the_same_duty(self) -> None:
        """Zonder die verliezer bewijst deze test niets."""
        _config, _world, result = self.plan()
        decision = result.decision_for("woonkamer")
        assert decision is not None
        assert decision.wanted is ModeFamily.COOL
        assert decision.granted is ModeFamily.NEUTRAL

    def test_the_hand_operated_unit_steps_aside(self) -> None:
        _config, _world, result = self.plan()
        command = command_for(result, BEDROOM)
        assert command is not None, "de handbediende unit bleef koelen"
        assert family_of(command.hvac_mode) is ModeFamily.NEUTRAL
        assert command.reason is Reason.CIRCUIT_CONFLICT_LOST

    def test_it_stays_put_when_the_circuit_runs_its_own_duty(self) -> None:
        """Draait het circuit wél zijn taak, dan hoeft hij nergens voor te wijken."""
        config = self.config()
        world = make_world(
            now=NOON,
            indoor={"keuken": 30.0, "woonkamer": 30.0, "slaapkamer": 22.0},
            climates={self.COLD: MODE_OFF, self.HOT: MODE_OFF, BEDROOM: "cool"},
            residents={"danny": awake()},
        )
        result = decide(config, world)
        assert result.circuits[0].family is ModeFamily.COOL
        assert command_for(result, BEDROOM) is None
        assert result.untouched_for(BEDROOM) is not None

    def test_it_stays_put_when_nobody_asks_for_anything(self) -> None:
        """Een stil circuit is geen reden om iemands airco uit te zetten."""
        config = self.config()
        world = make_world(
            now=NOON,
            indoor={"keuken": 22.0, "woonkamer": 22.0, "slaapkamer": 22.0},
            climates={self.COLD: MODE_OFF, self.HOT: MODE_OFF, BEDROOM: "cool"},
            residents={"danny": awake()},
        )
        result = decide(config, world)
        assert result.circuits[0].family is ModeFamily.NEUTRAL
        assert command_for(result, BEDROOM) is None


class TestAManualSourceDoesNotYieldToAWaitingRival:
    """Een handbediend apparaat wijkt voor de vraag, niet voor een timer (D4).

    A hand-operated appliance yields to the asking, not to a timer (D4).
    """

    HELPER = "climate.helper"

    def _bedroom(self) -> Zone:
        return Zone(
            "slaapkamer",
            "Slaapkamer",
            "sensor.slaapkamer",
            priority=2,
            sources=(Source("s", BEDROOM, autostart=False),),
            heat=ModeSettings(21.0, 20.0),
            cool=ModeSettings(23.0, 24.0),
        )

    def _config(self, circuit: Circuit, *, living_priority: int = 0) -> DirectorConfig:
        return DirectorConfig(
            zones=(
                Zone(
                    "woonkamer",
                    "Woonkamer",
                    "sensor.woonkamer",
                    priority=living_priority,
                    sources=(Source("w", LIVING),),
                    heat=ModeSettings(21.0, 20.0),
                    cool=ModeSettings(23.0, 24.0),
                ),
                self._bedroom(),
            ),
            circuits=(
                circuit,
                Circuit("bedroom", "Bedroom", units=(BEDROOM,), simultaneous_heat_cool=True),
            ),
            exclusive_groups=(frozenset({"w", "s"}),),
            residents=(Resident("danny", "Danny", presence_entity="person.danny"),),
        )

    def _config_with_helper(
        self, circuit: Circuit, *, living_priority: int, helper_priority: int
    ) -> DirectorConfig:
        return DirectorConfig(
            zones=(
                Zone(
                    "woonkamer",
                    "Woonkamer",
                    "sensor.woonkamer",
                    priority=living_priority,
                    sources=(Source("w", LIVING),),
                    heat=ModeSettings(21.0, 20.0),
                    cool=ModeSettings(23.0, 24.0),
                ),
                Zone(
                    "helper",
                    "Helper",
                    "sensor.helper",
                    priority=helper_priority,
                    sources=(Source("h", self.HELPER),),
                    heat=ModeSettings(21.0, 20.0),
                    cool=ModeSettings(23.0, 24.0),
                ),
                self._bedroom(),
            ),
            circuits=(
                circuit,
                Circuit("bedroom", "Bedroom", units=(BEDROOM,), simultaneous_heat_cool=True),
            ),
            exclusive_groups=(frozenset({"w", "s"}),),
            residents=(Resident("danny", "Danny", presence_entity="person.danny"),),
        )

    def _plan(
        self,
        config: DirectorConfig,
        *,
        living_mode: str = "off",
        living_changed_at: datetime | None = None,
        helper_mode: str = "off",
        indoor: dict[str, float] | None = None,
        extra_climates: dict[str, str] | None = None,
    ):
        from conftest import climate

        temperatures = {
            "woonkamer": 15.0,
            "slaapkamer": 21.5,
            "helper": 21.5,
            **(indoor or {}),
        }
        world = make_world(
            now=NOON,
            indoor=temperatures,
            climates={
                LIVING: climate(living_mode, changed_at=living_changed_at),
                BEDROOM: climate("heat"),
                self.HELPER: climate(helper_mode),
                **(extra_climates or {}),
            },
            residents={"danny": awake()},
        )
        return decide(config, world)

    def test_a_rival_held_by_short_cycle_protection_does_not_push_it_away(self) -> None:
        circuit = Circuit(
            "living",
            "Living",
            units=(LIVING,),
            simultaneous_heat_cool=True,
            min_cycle_time=timedelta(minutes=10),
        )
        plan = self._plan(
            self._config(circuit),
            living_mode="off",
            living_changed_at=NOON - timedelta(minutes=1),
        )
        assert plan.untouched_for(BEDROOM) is not None
        living = command_for(plan, LIVING)
        assert living is not None and living.hvac_mode == MODE_OFF

    def test_a_rival_held_by_a_switch_pause_does_not_push_it_away(self) -> None:
        circuit = Circuit(
            "living",
            "Living",
            units=(LIVING, self.HELPER),
            simultaneous_heat_cool=False,
            family_switch_delay=timedelta(minutes=5),
        )
        config = self._config_with_helper(circuit, living_priority=0, helper_priority=1)
        plan = self._plan(
            config,
            living_mode="off",
            helper_mode="heat",
            indoor={"woonkamer": 30.0, "helper": 21.5},
        )
        assert plan.untouched_for(BEDROOM) is not None

    def test_a_rival_without_a_place_does_not_push_it_away(self) -> None:
        circuit = Circuit(
            "living",
            "Living",
            units=(LIVING, "climate.stranger"),
            simultaneous_heat_cool=False,
            max_concurrent_units=1,
        )
        config = self._config(circuit)
        plan = self._plan(
            config,
            living_mode="off",
            helper_mode="off",
            indoor={"woonkamer": 30.0},
            extra_climates={"climate.stranger": "cool"},
        )
        assert plan.untouched_for(BEDROOM) is not None

    def test_a_real_duty_conflict_still_pushes_it_away(self) -> None:
        circuit = Circuit(
            "living",
            "Living",
            units=(LIVING, self.HELPER),
            simultaneous_heat_cool=False,
        )
        config = self._config_with_helper(circuit, living_priority=1, helper_priority=0)
        plan = self._plan(
            config,
            living_mode="off",
            helper_mode="off",
            indoor={"woonkamer": 15.0, "helper": 30.0},
        )
        bedroom = command_for(plan, BEDROOM)
        assert bedroom is not None and bedroom.hvac_mode == MODE_OFF
        assert bedroom.reason is Reason.EXCLUSIVE_GROUP_LOST
