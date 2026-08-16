"""Uitputtende doorloop van alles wat een gebruiker kan instellen en meemaken.

An exhaustive sweep of everything a user can configure and run into.

De andere testbestanden schrijven gevallen uit die iemand kan navertellen. Dit
bestand doet het omgekeerde: het loopt hele productruimtes af en controleert
eigenschappen die in élke combinatie moeten gelden. Zulke tests noemen geen
gedrag, ze bewaken grenzen - en ze vinden de combinatie waar niemand aan dacht.

The other test files write out cases somebody could retell. This file does the
opposite: it walks whole product spaces and checks properties that must hold in
every combination. Such tests name no behaviour, they guard boundaries - and
they find the combination nobody thought of.
"""

from __future__ import annotations

import itertools
from datetime import datetime, time, timedelta

import pytest
from conftest import GAS_CUTOVER, house, make_world

from custom_components.climate_director.engine import (
    Circuit,
    ConflictPolicy,
    DirectorConfig,
    GateSettings,
    Generator,
    ModeFamily,
    ModeSettings,
    Opening,
    OutdoorWindow,
    Reason,
    Resident,
    Season,
    Source,
    SourceRole,
    TimeWindow,
    Zone,
    decide,
    family_of,
    gates,
    validate,
)
from custom_components.climate_director.engine.serialise import config_from_dict, config_to_dict
from custom_components.climate_director.engine.world import (
    ClimateState,
    OpeningState,
    PresenceState,
    ResidentState,
)

#: 11 augustus 2026 is een dinsdag, 15 augustus een zaterdag.
#: 11 August 2026 is a Tuesday, 15 August a Saturday.
TUESDAY = datetime(2026, 8, 11, 9, 0)
SATURDAY = datetime(2026, 8, 15, 9, 0)
NIGHT = datetime(2026, 8, 11, 3, 0)


def _residents() -> tuple[Resident, ...]:
    return (
        Resident(
            "danny",
            "Danny",
            windows=(TimeWindow(time(6, 0), time(22, 0), frozenset({0, 1, 2, 3, 4})),),
            presence_entity="person.danny",
            sleep_entity="sensor.danny_charger_type",
            sleep_state="wireless",
        ),
        Resident(
            "nancy",
            "Nancy",
            windows=(TimeWindow(time(11, 0), time(15, 0), frozenset({5, 6})),),
            presence_entity="person.nancy",
        ),
    )


def _config(**gate_kwargs: object) -> DirectorConfig:
    return DirectorConfig(
        zones=(
            Zone(
                "woonkamer",
                "Woonkamer",
                "sensor.woonkamer",
                sources=(Source("s", "climate.huiskamer"),),
                heat=ModeSettings(21.0, 20.0),
                presence_entity="binary_sensor.woonkamer",
            ),
        ),
        residents=_residents(),
        openings=(Opening("binary_sensor.deur", zone_ids=("woonkamer",)),),
        gates=GateSettings(**gate_kwargs),  # type: ignore[arg-type]
    )


def _zone(config: DirectorConfig) -> Zone:
    zone = config.zone("woonkamer")
    assert zone is not None
    return zone


def _state(home: bool, asleep: bool) -> ResidentState:
    return ResidentState(home=home, asleep=asleep)


PEOPLE = list(itertools.product([True, False], repeat=2))
FLAGS = list(itertools.product([True, False], repeat=2))
MOMENTS = [TUESDAY, SATURDAY, NIGHT]


def _worlds():
    """Yield every combination of the circumstances the gates look at."""
    for moment, danny, nancy, (master, override), (
        opening,
        occupied,
    ), guest, holiday in itertools.product(
        MOMENTS, PEOPLE, PEOPLE, FLAGS, FLAGS, [True, False], [True, False]
    ):
        yield make_world(
            now=moment,
            residents={"danny": _state(*danny), "nancy": _state(*nancy)},
            openings={"binary_sensor.deur": OpeningState(open=opening, changed_at=None)},
            presence={"woonkamer": PresenceState(occupied=occupied, changed_at=None)},
            master_enabled=master,
            holiday_mode=holiday,
            guest_mode=guest,
            zone_overrides={"woonkamer": override},
        )


class TestEveryGateCombination:
    """1536 worlds against four gate settings: 6144 verdicts, no exceptions."""

    settings = [
        {},
        {"require_awake": False},
        {"require_schedule": True},
        {"require_awake": False, "require_schedule": True},
        {"guest_window": TimeWindow(time(8, 0), time(23, 0))},
    ]

    @pytest.mark.parametrize("kwargs", settings)
    def test_a_verdict_is_always_well_formed(self, kwargs: dict[str, object]) -> None:
        config = _config(**kwargs)
        zone = _zone(config)
        for world in _worlds():
            verdict = gates.evaluate(config, world, zone)
            assert verdict.allowed is (verdict.reason is None)

    @pytest.mark.parametrize("kwargs", settings)
    def test_the_master_switch_outranks_everything(self, kwargs: dict[str, object]) -> None:
        config = _config(**kwargs)
        zone = _zone(config)
        for world in _worlds():
            if not world.master_enabled:
                assert gates.evaluate(config, world, zone).reason is Reason.MASTER_DISABLED

    @pytest.mark.parametrize("kwargs", settings)
    def test_an_override_is_never_overruled(self, kwargs: dict[str, object]) -> None:
        config = _config(**kwargs)
        zone = _zone(config)
        for world in _worlds():
            if world.master_enabled and world.overridden("woonkamer"):
                assert gates.evaluate(config, world, zone).reason is Reason.MANUAL_OVERRIDE

    @pytest.mark.parametrize("kwargs", settings)
    def test_an_empty_room_is_never_regulated(self, kwargs: dict[str, object]) -> None:
        """The zone carries a presence sensor, so an empty room is a known fact."""
        config = _config(**kwargs)
        zone = _zone(config)
        for world in _worlds():
            if not world.presence_of("woonkamer").occupied:
                assert not gates.evaluate(config, world, zone).allowed


class TestSomebodyMustBeHome:
    """The condition the user asked for, checked against every world there is."""

    @pytest.mark.parametrize("kwargs", TestEveryGateCombination.settings)
    def test_an_empty_house_never_starts_anything(self, kwargs: dict[str, object]) -> None:
        config = _config(**kwargs)
        zone = _zone(config)
        for world in _worlds():
            if world.guest_mode:
                continue
            nobody = not any(
                world.resident(resident.resident_id).home for resident in config.residents
            )
            if nobody and world.master_enabled and not world.overridden("woonkamer"):
                verdict = gates.evaluate(config, world, zone)
                assert not verdict.allowed
                if not world.opening("binary_sensor.deur").open:
                    assert verdict.reason is Reason.NOBODY_HOME


class TestGuestModeNeverTakesAway:
    """Guest mode may only ever add permission, never remove it."""

    @pytest.mark.parametrize("kwargs", TestEveryGateCombination.settings)
    def test_it_is_monotone(self, kwargs: dict[str, object]) -> None:
        config = _config(**kwargs)
        zone = _zone(config)
        for world in _worlds():
            if world.guest_mode:
                continue
            without = gates.evaluate(config, world, zone)
            with_guests = gates.evaluate(config, _guest(world), zone)
            if without.allowed:
                assert with_guests.allowed, world


def _guest(world):
    """Return the same world with guest mode switched on."""
    return make_world(
        now=world.now,
        residents=dict(world.residents),
        openings=dict(world.openings),
        presence=dict(world.presence),
        master_enabled=world.master_enabled,
        holiday_mode=world.holiday_mode,
        guest_mode=True,
        zone_overrides=dict(world.zone_overrides),
    )


class TestGuestModeStopsAtBedtime:
    """A resident coming home and turning in ends the guests' day."""

    hours = [time(3, 0), time(9, 0), time(14, 0), time(22, 0), time(23, 30)]

    @pytest.mark.parametrize("hour", hours)
    def test_everybody_home_and_asleep_closes_the_gate(self, hour: time) -> None:
        config = _config()
        world = make_world(
            now=datetime.combine(TUESDAY.date(), hour),
            residents={"danny": _state(True, True), "nancy": _state(True, True)},
            presence={"woonkamer": PresenceState(occupied=True)},
            guest_mode=True,
        )
        assert gates.evaluate(config, world, _zone(config)).reason is Reason.EVERYONE_ASLEEP

    @pytest.mark.parametrize("hour", hours)
    def test_one_resident_still_up_keeps_it_open(self, hour: time) -> None:
        config = _config()
        world = make_world(
            now=datetime.combine(TUESDAY.date(), hour),
            residents={"danny": _state(True, False), "nancy": _state(True, True)},
            presence={"woonkamer": PresenceState(occupied=True)},
            guest_mode=True,
        )
        assert gates.evaluate(config, world, _zone(config)).allowed

    @pytest.mark.parametrize("hour", hours)
    def test_an_empty_house_stays_open(self, hour: time) -> None:
        """Nobody home means nobody asleep, so the guests keep the house."""
        config = _config()
        world = make_world(
            now=datetime.combine(TUESDAY.date(), hour),
            residents={"danny": _state(False, False), "nancy": _state(False, False)},
            presence={"woonkamer": PresenceState(occupied=True)},
            guest_mode=True,
        )
        assert gates.evaluate(config, world, _zone(config)).allowed


class TestTheGuestWindow:
    """Outside its hours, guest mode hands the house back to the ordinary gates."""

    config = _config(guest_window=TimeWindow(time(8, 0), time(23, 0)))

    @pytest.mark.parametrize("hour", [8, 12, 22])
    def test_inside_it_carries_an_empty_house(self, hour: int) -> None:
        world = make_world(
            now=TUESDAY.replace(hour=hour),
            residents={"danny": _state(False, False), "nancy": _state(False, False)},
            presence={"woonkamer": PresenceState(occupied=True)},
            guest_mode=True,
        )
        assert gates.evaluate(self.config, world, _zone(self.config)).allowed

    @pytest.mark.parametrize("hour", [0, 5, 7, 23])
    def test_outside_it_the_empty_house_wins(self, hour: int) -> None:
        world = make_world(
            now=TUESDAY.replace(hour=hour),
            residents={"danny": _state(False, False), "nancy": _state(False, False)},
            presence={"woonkamer": PresenceState(occupied=True)},
            guest_mode=True,
        )
        verdict = gates.evaluate(self.config, world, _zone(self.config))
        assert verdict.reason is Reason.NOBODY_HOME

    def test_a_window_crossing_midnight_still_works(self) -> None:
        config = _config(guest_window=TimeWindow(time(22, 0), time(2, 0)))
        for hour, carried in [(22, True), (23, True), (1, True), (2, False), (12, False)]:
            world = make_world(
                now=TUESDAY.replace(hour=hour),
                residents={"danny": _state(False, False), "nancy": _state(False, False)},
                presence={"woonkamer": PresenceState(occupied=True)},
                guest_mode=True,
            )
            assert gates.evaluate(config, world, _zone(config)).allowed is carried


class TestHolidayIsSaturdayEverywhere:
    """On a holiday every resident's schedule is read as a Saturday's."""

    config = _config(require_schedule=True)

    @pytest.mark.parametrize("day", range(7))
    def test_the_verdict_matches_a_real_saturday(self, day: int) -> None:
        monday = datetime(2026, 8, 10, 12, 0)
        saturday = datetime(2026, 8, 15, 12, 0)
        people = {"danny": _state(True, False), "nancy": _state(True, False)}
        presence = {"woonkamer": PresenceState(occupied=True)}

        holiday = gates.evaluate(
            self.config,
            make_world(
                now=monday + timedelta(days=day),
                residents=people,
                presence=presence,
                holiday_mode=True,
            ),
            _zone(self.config),
        )
        real = gates.evaluate(
            self.config,
            make_world(now=saturday, residents=people, presence=presence),
            _zone(self.config),
        )
        assert holiday.allowed is real.allowed


class TestSerialisationSurvivesEverything:
    """Every configuration this integration can hold must round-trip unchanged."""

    def _matrix(self):
        for role, policy, simultaneous, holiday_window in itertools.product(
            SourceRole, ConflictPolicy, [True, False], [True, False]
        ):
            yield DirectorConfig(
                zones=(
                    Zone(
                        "z",
                        "Z",
                        "sensor.z",
                        sources=(
                            Source(
                                "s",
                                "climate.z",
                                role=role,
                                priority=2,
                                outdoor=OutdoorWindow(minimum=3.0, maximum=18.5),
                            ),
                        ),
                        priority=1,
                        heat=ModeSettings(21.0, 20.0, 0.5, seasons=frozenset({Season.WINTER})),
                        cool=ModeSettings(23.0, 25.0),
                        presence_entity="binary_sensor.z",
                        presence_timeout=timedelta(seconds=90),
                    ),
                ),
                circuits=(
                    Circuit(
                        "c",
                        "C",
                        units=("climate.z",),
                        simultaneous_heat_cool=simultaneous,
                        conflict_policy=policy,
                        family_switch_delay=timedelta(seconds=15),
                        min_cycle_time=timedelta(minutes=3),
                    ),
                ),
                generators=(Generator("g", "CV", "climate.cv", zone_ids=("z",)),),
                residents=(
                    Resident(
                        "d",
                        "D",
                        windows=(TimeWindow(time(6, 0), time(23, 0), holiday=holiday_window),),
                        presence_entity="person.d",
                        sleep_entity="sensor.d",
                        sleep_state="wireless",
                    ),
                ),
                openings=(
                    Opening("binary_sensor.o", zone_ids=("z",), delay=timedelta(seconds=30)),
                ),
                gates=GateSettings(
                    require_awake=False,
                    require_schedule=True,
                    guest_window=TimeWindow(time(8, 0), time(23, 0)),
                ),
                holiday_calendars=("calendar.a", "calendar.b"),
                holiday_keyword="vakantie",
            )

    def test_it_survives_the_trip(self) -> None:
        for config in self._matrix():
            assert config_from_dict(config_to_dict(config)) == config

    def test_the_dictionary_is_stable(self) -> None:
        """Twice through changes nothing, so stored options never churn."""
        for config in self._matrix():
            once = config_to_dict(config)
            assert config_to_dict(config_from_dict(once)) == once

    @pytest.mark.parametrize(
        "raw",
        [
            {},
            {"zones": None},
            {"zones": []},
            {"gates": "nonsense"},
            {"gates": {"guest_window": {"start": "8:00", "end": ""}}},
            {"holiday_calendars": "calendar.a"},
            {"holiday_calendars": None, "holiday_keyword": None},
            {"residents": [{"resident_id": "d", "windows": [{"start": "x", "end": "y"}]}]},
        ],
    )
    def test_rubbish_never_raises(self, raw: dict) -> None:
        """Stored options can be older, hand-edited or half-written; none may crash."""
        config = config_from_dict(raw)
        assert config_to_dict(config) is not None
        assert isinstance(validate(config), tuple)


class TestThePlanIsAlwaysConsistent:
    """The real installation, swept across the whole outdoor and indoor range."""

    def _worlds(self):
        config = house()
        appliances = [source.entity_id for zone in config.zones for source in zone.sources]
        indoor_points = [15.0, 19.5, 20.0, 21.0, 24.0, 28.0, None]
        outdoor_points = [-10.0, GAS_CUTOVER - 0.1, GAS_CUTOVER, GAS_CUTOVER + 0.1, 25.0, None]
        for outdoor, indoor, season, running in itertools.product(
            outdoor_points, indoor_points, Season, ["off", "heat", "cool"]
        ):
            yield (
                config,
                make_world(
                    now=TUESDAY,
                    outdoor=outdoor,
                    season=season,
                    indoor={zone.zone_id: indoor for zone in config.zones},
                    climates={entity: running for entity in appliances},
                    residents={
                        resident.resident_id: _state(True, False) for resident in config.residents
                    },
                    presence={zone.zone_id: PresenceState(occupied=True) for zone in config.zones},
                ),
            )

    def test_the_sweep_is_not_vacuous(self) -> None:
        """A sweep where nothing ever runs proves nothing, so prove it runs."""
        seen = set()
        for config, world in self._worlds():
            for command in decide(config, world).commands:
                seen.add(family_of(command.hvac_mode))
        assert {ModeFamily.HEAT, ModeFamily.COOL, ModeFamily.NEUTRAL} <= seen, seen

    def test_every_command_names_a_configured_appliance(self) -> None:
        for config, world in self._worlds():
            known = {source.entity_id for zone in config.zones for source in zone.sources}
            known |= {item.entity_id for item in config.generators}
            for command in decide(config, world).commands:
                assert command.entity_id in known

    def test_no_appliance_is_commanded_twice(self) -> None:
        for config, world in self._worlds():
            commanded = [command.entity_id for command in decide(config, world).commands]
            assert len(commanded) == len(set(commanded))

    def test_a_shared_circuit_never_runs_two_duties(self) -> None:
        for config, world in self._worlds():
            plan = decide(config, world)
            modes = {command.entity_id: command.hvac_mode for command in plan.commands}
            for circuit in config.circuits:
                if circuit.simultaneous_heat_cool:
                    continue
                families = {
                    family_of(modes[unit])
                    for unit in circuit.units
                    if unit in modes and family_of(modes[unit]) is not ModeFamily.NEUTRAL
                }
                assert len(families) <= 1, (circuit.circuit_id, families)

    def test_gas_and_the_heat_pumps_never_heat_together(self) -> None:
        """The interlock the old automations kept by hand, checked in bulk."""
        for config, world in self._worlds():
            plan = decide(config, world)
            heating = {
                command.entity_id
                for command in plan.commands
                if family_of(command.hvac_mode) is ModeFamily.HEAT
            }
            gas = {item.entity_id for item in config.generators}
            if heating & gas:
                assert not (heating - gas), heating

    def test_deciding_twice_gives_the_same_plan(self) -> None:
        for config, world in self._worlds():
            assert decide(config, world) == decide(config, world)

    def test_every_zone_gets_exactly_one_decision(self) -> None:
        for config, world in self._worlds():
            plan = decide(config, world)
            decided = [item.zone_id for item in plan.zones]
            assert sorted(decided) == sorted(zone.zone_id for zone in config.zones)

    def test_a_blocked_zone_is_never_commanded_to_run(self) -> None:
        config = house()
        for zone in config.zones:
            world = make_world(
                now=TUESDAY,
                outdoor=0.0,
                indoor={item.zone_id: 10.0 for item in config.zones},
                climates={
                    source.entity_id: "off" for item in config.zones for source in item.sources
                },
                residents={
                    resident.resident_id: _state(True, False) for resident in config.residents
                },
                presence={item.zone_id: PresenceState(occupied=True) for item in config.zones},
                zone_overrides={zone.zone_id: True},
            )
            plan = decide(config, world)
            entities = {source.entity_id for source in zone.sources}
            for command in plan.commands:
                if command.entity_id in entities:
                    assert family_of(command.hvac_mode) is ModeFamily.NEUTRAL


class TestUnreadableStatesNeverCrash:
    """Sensors go unavailable, and a plan still has to come out."""

    @pytest.mark.parametrize("mode", ["unavailable", "unknown", "", "heat", "cool", "dry", "auto"])
    def test_any_climate_state_is_survivable(self, mode: str) -> None:
        config = house()
        world = make_world(
            now=TUESDAY,
            outdoor=None,
            indoor={zone.zone_id: None for zone in config.zones},
            climates={
                source.entity_id: ClimateState(hvac_mode=mode)
                for zone in config.zones
                for source in zone.sources
            },
            residents={resident.resident_id: _state(True, False) for resident in config.residents},
        )
        assert decide(config, world) is not None


class TestTheCalendarReading:
    """The holiday calendars, read without a Home Assistant to run them in.

    De methode raakt alleen `self.config` en `self.hass.states`, dus een
    nagemaakte omgeving is genoeg - en dat houdt deze test snel en eerlijk.

    The method touches only `self.config` and `self.hass.states`, so a stand-in
    is enough - which keeps this test fast and honest.
    """

    class _State:
        def __init__(self, state: str, **attributes: str) -> None:
            self.state = state
            self.attributes = attributes

    def _read(self, calendars, keyword, states):
        from custom_components.climate_director.coordinator import ClimateDirectorCoordinator

        class Registry:
            def get(self, entity_id):
                return states.get(entity_id)

        class Hass:
            def __init__(self) -> None:
                self.states = Registry()

        stand_in = type(
            "StandIn",
            (),
            {
                "config": DirectorConfig(
                    holiday_calendars=tuple(calendars), holiday_keyword=keyword
                ),
                "hass": Hass(),
            },
        )()
        return ClimateDirectorCoordinator._calendar_says_holiday(stand_in)

    def test_a_running_event_with_the_word_counts(self) -> None:
        states = {"calendar.gezin": self._State("on", message="Vakantie Frankrijk")}
        assert self._read(["calendar.gezin"], "vakantie", states)

    def test_the_match_ignores_case(self) -> None:
        states = {"calendar.gezin": self._State("on", message="VAKANTIE")}
        assert self._read(["calendar.gezin"], "Vakantie", states)

    def test_an_event_without_the_word_does_not(self) -> None:
        states = {"calendar.gezin": self._State("on", message="Tandarts")}
        assert not self._read(["calendar.gezin"], "vakantie", states)

    def test_an_event_that_is_not_running_does_not(self) -> None:
        states = {"calendar.gezin": self._State("off", message="Vakantie")}
        assert not self._read(["calendar.gezin"], "vakantie", states)

    def test_without_a_keyword_the_calendars_are_ignored(self) -> None:
        """The user asked for exactly this: no keyword, no calendar-driven holiday."""
        states = {"calendar.gezin": self._State("on", message="Vakantie")}
        assert not self._read(["calendar.gezin"], "", states)
        assert not self._read(["calendar.gezin"], "   ", states)

    def test_any_of_several_calendars_may_carry_it(self) -> None:
        states = {
            "calendar.werk": self._State("off", message="Vakantie"),
            "calendar.school": self._State("on", message="Zomervakantie"),
        }
        assert self._read(["calendar.werk", "calendar.school"], "vakantie", states)

    def test_a_missing_calendar_is_survivable(self) -> None:
        """Somebody removes the calendar entity; nothing may crash over it."""
        assert not self._read(["calendar.weg"], "vakantie", {})

    def test_the_word_may_sit_in_the_description(self) -> None:
        states = {"calendar.gezin": self._State("on", description="Twee weken vakantie")}
        assert self._read(["calendar.gezin"], "vakantie", states)

    def test_missing_attributes_are_survivable(self) -> None:
        assert not self._read(["calendar.gezin"], "vakantie", {"calendar.gezin": self._State("on")})

    def test_configuring_calendars_without_a_keyword_is_reported(self) -> None:
        config = DirectorConfig(
            zones=(
                Zone(
                    "z",
                    "Z",
                    "sensor.z",
                    sources=(Source("s", "climate.z"),),
                    heat=ModeSettings(21.0, 20.0),
                ),
            ),
            holiday_calendars=("calendar.gezin",),
        )
        assert any("no keyword" in item for item in validate(config))
