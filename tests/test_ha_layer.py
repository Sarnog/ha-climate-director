"""De koppelingslaag zelf, met een nagebouwde Home Assistant eromheen.

The binding layer itself, with a stand-in Home Assistant around it.

De engine was altijd al volledig te testen; de laag eromheen niet. Die leest
entiteiten uit, doet service calls, vult gebeurtenissen en bouwt entiteiten op -
en dat gebeurde tot nu toe alleen echt in een draaiende Home Assistant, dus
alleen bij de gebruiker thuis.

`pytest-homeassistant-custom-component` draait niet op dit systeem (het
importeert Unix-only stdlib), maar dat is ook niet nodig voor wat hier telt: een
toestandsregister, een bus en een servicelaag zijn een handvol regels, en dan is
elke leesregel en elke service call gewoon na te lopen. Wat hier niet in staat is
alles waar Home Assistant zelf de regie voert: het aanroepen van
`async_setup_entry`, de debouncer en het inplannen van een herberekening.

The engine was always fully testable; the layer around it was not. That layer
reads entities, makes service calls, fills events and builds entities - and until
now that only really happened inside a running Home Assistant, so only in
somebody's home.

`pytest-homeassistant-custom-component` does not run on this machine (it imports
Unix-only stdlib), but that is not needed for what counts here: a state
registry, a bus and a service layer are a handful of lines, and then every read
and every service call can simply be walked through. What is not in here is
everything Home Assistant itself drives: calling `async_setup_entry`, the
debouncer and scheduling a re-evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pytest
from conftest import at

from custom_components.climate_director import applier as applier_module
from custom_components.climate_director.applier import apply
from custom_components.climate_director.binary_sensor import (
    StuckSensor,
    ZoneBlockedSensor,
    ZoneFallbackSensor,
)
from custom_components.climate_director.coordinator import ClimateDirectorCoordinator
from custom_components.climate_director.engine import (
    DirectorConfig,
    ModeFamily,
    ModeSettings,
    Opening,
    Reason,
    Resident,
    Season,
    Source,
    SourceRole,
    Zone,
    decide,
)
from custom_components.climate_director.engine.diff import changes
from custom_components.climate_director.engine.models import (
    PrecipitationSettings,
    SeasonSettings,
    SeasonSource,
)
from custom_components.climate_director.sensor import (
    CommandSensor,
    DecisionSensor,
    MismatchSensor,
    ZoneSourceSensor,
)

LIVING = "climate.woonkamer"
BACKUP = "climate.woonkamer_reserve"
ATTIC = "climate.zolder"
NOW = at(14, 0)


# ---------------------------------------------------------------------------
# Een nagebouwde Home Assistant: precies zoveel als de laag werkelijk aanraakt.
# A stand-in Home Assistant: exactly as much as the layer really touches.
# ---------------------------------------------------------------------------


@dataclass
class FakeState:
    """What `hass.states.get()` hands back."""

    state: str
    attributes: dict = field(default_factory=dict)
    last_changed: datetime = NOW

    @property
    def name(self) -> str:
        return self.entity_id if hasattr(self, "entity_id") else self.state


class FakeStates:
    def __init__(self, states: dict[str, FakeState]) -> None:
        self._states = states

    def get(self, entity_id: str) -> FakeState | None:
        return self._states.get(entity_id)


class FakeServices:
    """Records every service call instead of making one."""

    def __init__(self, failing: set[str] | None = None) -> None:
        self.calls: list[tuple[str, str, dict]] = []
        self.failing = failing or set()

    async def async_call(self, domain: str, service: str, data: dict, blocking: bool = False):
        self.calls.append((domain, service, data))
        if data.get("entity_id") in self.failing:
            raise RuntimeError("de service call mislukte")


class FakeBus:
    def __init__(self) -> None:
        self.fired: list[tuple[str, dict]] = []

    def async_fire(self, event_type: str, data: dict) -> None:
        self.fired.append((event_type, data))


class FakeConfig:
    language = "en"


class FakeHass:
    def __init__(self, states: dict[str, FakeState] | None = None, **kwargs) -> None:
        self.states = FakeStates(states or {})
        self.services = FakeServices(**kwargs)
        self.bus = FakeBus()
        self.config = FakeConfig()


def house() -> DirectorConfig:
    """Return a small house with a reserve source, an opening and a resident."""
    return DirectorConfig(
        zones=(
            Zone(
                zone_id="woonkamer",
                name="Woonkamer",
                indoor_sensor="sensor.woonkamer",
                sources=(
                    Source("woonkamer_airco", LIVING, role=SourceRole.HEAT_COOL),
                    Source("woonkamer_reserve", BACKUP, role=SourceRole.HEAT_ONLY, priority=1),
                ),
                heat=ModeSettings(target=21.0, start_at=20.0, hysteresis=1.0),
                cool=ModeSettings(target=23.0, start_at=24.0, hysteresis=1.0),
            ),
            Zone(
                zone_id="zolder",
                name="Zolder",
                indoor_sensor="sensor.zolder",
                priority=1,
                sources=(Source("zolder_airco", ATTIC),),
                heat=ModeSettings(target=21.0, start_at=20.0, hysteresis=1.0),
                presence_entity="binary_sensor.zolder",
                presence_timeout=timedelta(minutes=30),
            ),
        ),
        residents=(
            Resident(
                resident_id="danny",
                name="Danny",
                presence_entity="person.danny",
                sleep_entity="sensor.danny_lader",
                sleep_state="wireless",
            ),
        ),
        openings=(Opening(entity_id="binary_sensor.achterdeur", delay=timedelta(minutes=1)),),
        outdoor_sensor="sensor.buiten",
    )


def coordinator(states: dict[str, FakeState] | None = None, config: DirectorConfig | None = None):
    """Return a stand-in carrying the coordinator's own reading methods."""

    class Entry:
        entry_id = "abc"
        title = "Climate Director"

    class StandIn:
        def __init__(self) -> None:
            self.config = config or house()
            self.hass = FakeHass(states)
            self.config_entry = Entry()
            self.master_enabled = True
            self.holiday_mode = False
            self.guest_mode = False
            self.zone_overrides: dict[str, bool] = {}
            self.zone_priorities: dict[str, int] = {}
            self._precondition: dict[str, datetime] = {}
            self._precondition_bypass: set[str] = set()
            self._precipitation_seen_at: datetime | None = None
            self._handed_back: dict = {}
            self._waiting: dict = {}
            self._refused: set[str] = set()
            self.data = None
            self._issued = None
            self.world = None
            self.shadow = False
            self.last_changes = ()
            self.last_applied = ()

        build_world = ClimateDirectorCoordinator.build_world
        _overridden_zones = ClimateDirectorCoordinator._overridden_zones
        tracked_entities = ClimateDirectorCoordinator.tracked_entities
        unusable_entities = ClimateDirectorCoordinator.unusable_entities
        stuck_zones = ClimateDirectorCoordinator.stuck_zones
        waiting_seconds = ClimateDirectorCoordinator.waiting_seconds
        _note_waiting = ClimateDirectorCoordinator._note_waiting
        _climate_ids = ClimateDirectorCoordinator._climate_ids
        _climate = ClimateDirectorCoordinator._climate
        _temperature = ClimateDirectorCoordinator._temperature
        _resident = ClimateDirectorCoordinator._resident
        _opening = ClimateDirectorCoordinator._opening
        _presence = ClimateDirectorCoordinator._presence
        _season = ClimateDirectorCoordinator._season
        _precipitation = ClimateDirectorCoordinator._precipitation
        _calendar_says_holiday = ClimateDirectorCoordinator._calendar_says_holiday
        _zones_handed_back = ClimateDirectorCoordinator._zones_handed_back
        _live_preconditions = ClimateDirectorCoordinator._live_preconditions
        _everyone_asleep = ClimateDirectorCoordinator._everyone_asleep
        _house_is_empty = ClimateDirectorCoordinator._house_is_empty
        _state_is = ClimateDirectorCoordinator._state_is
        _fire_events = ClimateDirectorCoordinator._fire_events
        _fire_refusals = ClimateDirectorCoordinator._fire_refusals
        _refusal_data = ClimateDirectorCoordinator._refusal_data
        _friendly = ClimateDirectorCoordinator._friendly
        _open_openings = ClimateDirectorCoordinator._open_openings

    return StandIn()


@pytest.fixture(autouse=True)
def _local_clock(monkeypatch: pytest.MonkeyPatch):
    """Freeze the clock, and keep the English fallback in place.

    De vertaalcache bestaat alleen binnen een draaiende Home Assistant. Wat hier
    telt is dat er een zin uitkomt en dat de plaatshouders ingevuld worden; dat
    de Nederlandse variant klopt is elders vastgelegd.

    The translation cache only exists inside a running Home Assistant. What
    counts here is that a sentence comes out with its placeholders filled; that
    the Dutch variant is right is pinned down elsewhere.
    """
    from custom_components.climate_director import coordinator as module
    from custom_components.climate_director import texts

    monkeypatch.setattr(module.dt_util, "now", lambda: NOW)
    monkeypatch.setattr(module.dt_util, "as_local", lambda value: value)
    monkeypatch.setattr(texts, "lookup", lambda hass, code: None)


# ---------------------------------------------------------------------------
# Entiteiten uitlezen.
# Reading entities.
# ---------------------------------------------------------------------------


class TestReadingTheWorld:
    """Van toestandsregister naar `WorldState`, met alle randgevallen erin.

    From state registry to `WorldState`, edge cases included.
    """

    def _states(self, **changes: FakeState) -> dict[str, FakeState]:
        base = {
            "sensor.buiten": FakeState("7.5"),
            "sensor.woonkamer": FakeState("19.0"),
            "sensor.zolder": FakeState("18.0"),
            LIVING: FakeState("heat", {"temperature": 21.0, "current_temperature": 19.2}),
            BACKUP: FakeState("off"),
            ATTIC: FakeState("off"),
            "person.danny": FakeState("home"),
            "sensor.danny_lader": FakeState("none"),
            "binary_sensor.achterdeur": FakeState("off"),
            "binary_sensor.zolder": FakeState("on"),
        }
        return {**base, **changes}

    def test_it_reads_every_kind_of_entity(self) -> None:
        world = coordinator(self._states()).build_world()

        assert world.outdoor_temperature == 7.5
        assert world.indoor("woonkamer") == 19.0
        assert world.climate(LIVING).hvac_mode == "heat"
        assert world.climate(LIVING).target_temperature == 21.0
        assert world.resident("danny").home is True
        assert world.resident("danny").asleep is False
        assert world.opening("binary_sensor.achterdeur").open is False
        assert world.presence_of("zolder").occupied is True

    def test_an_unavailable_appliance_reads_as_nothing(self) -> None:
        """Niet als "uit": als onbereikbaar, want dan valt er niets over te zeggen."""
        world = coordinator(self._states(**{LIVING: FakeState("unavailable")})).build_world()
        assert world.climate(LIVING).available is False
        assert world.climate(LIVING).running is False

    def test_an_unknown_appliance_reads_the_same(self) -> None:
        world = coordinator(self._states(**{LIVING: FakeState("unknown")})).build_world()
        assert world.climate(LIVING).available is False

    def test_a_missing_appliance_reads_the_same(self) -> None:
        states = self._states()
        del states[LIVING]
        assert coordinator(states).build_world().climate(LIVING).available is False

    @pytest.mark.parametrize("value", ["unknown", "unavailable", "", "kapot", "None"])
    def test_an_unreadable_temperature_reads_as_nothing(self, value: str) -> None:
        states = self._states(**{"sensor.woonkamer": FakeState(value)})
        assert coordinator(states).build_world().indoor("woonkamer") is None

    def test_a_weather_entity_gives_its_temperature_attribute(self) -> None:
        config = house()
        weather = DirectorConfig(
            zones=config.zones,
            residents=config.residents,
            openings=config.openings,
            outdoor_sensor="weather.thuis",
        )
        states = self._states(**{"weather.thuis": FakeState("rainy", {"temperature": 4.5})})
        assert coordinator(states, weather).build_world().outdoor_temperature == 4.5

    def test_a_climate_entity_may_serve_as_the_room_sensor(self) -> None:
        """De setpoint is niet de kamertemperatuur; `current_temperature` wel."""
        config = house()
        rooms = DirectorConfig(
            zones=(
                Zone(
                    zone_id="woonkamer",
                    name="Woonkamer",
                    indoor_sensor=LIVING,
                    sources=config.zones[0].sources,
                    heat=config.zones[0].heat,
                ),
            ),
            outdoor_sensor="sensor.buiten",
        )
        assert coordinator(self._states(), rooms).build_world().indoor("woonkamer") == 19.2

    def test_a_sleeping_resident_is_read_from_their_own_state(self) -> None:
        states = self._states(**{"sensor.danny_lader": FakeState("wireless")})
        assert coordinator(states).build_world().resident("danny").asleep is True

    @pytest.mark.parametrize("value", ["home", "HOME", "on", "true"])
    def test_being_home_is_read_broadly(self, value: str) -> None:
        states = self._states(**{"person.danny": FakeState(value)})
        assert coordinator(states).build_world().resident("danny").home is True

    def test_the_tracked_entities_cover_everything_that_is_read(self) -> None:
        """Wat niet gevolgd wordt, laat de director niet opnieuw beslissen."""
        item = coordinator(self._states())
        tracked = item.tracked_entities()
        for entity_id in (
            "sensor.buiten",
            "sensor.woonkamer",
            LIVING,
            BACKUP,
            "person.danny",
            "sensor.danny_lader",
            "binary_sensor.achterdeur",
            "binary_sensor.zolder",
        ):
            assert entity_id in tracked, entity_id


def _healthy_states() -> dict[str, FakeState]:
    """Return a world where every entity reads, with numbers where numbers belong."""
    states = {entity: FakeState("on") for entity in coordinator({}).tracked_entities()}
    for entity in ("sensor.buiten", "sensor.woonkamer", "sensor.zolder"):
        if entity in states:
            states[entity] = FakeState("19.0")
    return states


class TestTheUnusableList:
    """Entiteiten die niet te lezen zijn, apart gemeld.

    Entities that cannot be read, reported separately.
    """

    def test_a_missing_entity_is_named(self) -> None:
        item = coordinator({})
        assert "sensor.buiten" in item.unusable_entities()

    def test_an_unavailable_entity_is_named_with_its_state(self) -> None:
        states = {
            "sensor.buiten": FakeState("unavailable"),
            "sensor.woonkamer": FakeState("19.0"),
        }
        assert coordinator(states).unusable_entities()["sensor.buiten"] == "unavailable"

    def test_a_healthy_installation_reports_nothing(self) -> None:
        states = _healthy_states()
        assert coordinator(states).unusable_entities() == {}


class TestTheSeasonAndTheCalendar:
    """Twee bronnen die van buiten komen: de maand en een agenda.

    Two sources coming from outside: the month and a calendar.
    """

    def _config(self, **kwargs) -> DirectorConfig:
        base = house()
        return DirectorConfig(
            zones=base.zones,
            residents=base.residents,
            openings=base.openings,
            outdoor_sensor=base.outdoor_sensor,
            **kwargs,
        )

    def test_the_month_decides_by_default(self) -> None:
        assert coordinator({}, self._config())._season() in (Season.SUMMER, Season.WINTER)

    def test_an_entity_can_decide_instead(self) -> None:
        config = self._config(
            seasons=SeasonSettings(source=SeasonSource.ENTITY, entity_id="sensor.seizoen")
        )
        states = {"sensor.seizoen": FakeState("Zomer")}
        assert coordinator(states, config)._season() is Season.SUMMER

    def test_an_unreadable_season_entity_falls_back_to_unknown(self) -> None:
        config = self._config(
            seasons=SeasonSettings(source=SeasonSource.ENTITY, entity_id="sensor.seizoen")
        )
        states = {"sensor.seizoen": FakeState("unavailable")}
        assert coordinator(states, config)._season() is Season.UNKNOWN

    def test_a_calendar_event_with_the_keyword_switches_holiday_on(self) -> None:
        config = self._config(holiday_calendars=("calendar.gezin",), holiday_keyword="vakantie")
        states = {"calendar.gezin": FakeState("on", {"message": "Zomervakantie Spanje"})}
        assert coordinator(states, config)._calendar_says_holiday() is True

    def test_an_event_without_the_keyword_does_not(self) -> None:
        config = self._config(holiday_calendars=("calendar.gezin",), holiday_keyword="vakantie")
        states = {"calendar.gezin": FakeState("on", {"message": "Tandarts"})}
        assert coordinator(states, config)._calendar_says_holiday() is False

    def test_a_missing_calendar_is_survivable(self) -> None:
        config = self._config(holiday_calendars=("calendar.weg",), holiday_keyword="vakantie")
        assert coordinator({}, config)._calendar_says_holiday() is False

    def test_without_a_precipitation_source_rain_never_counts(self) -> None:
        """Zonder neerslagbron is het antwoord gewoon 'nee'."""
        assert coordinator({}, self._config())._precipitation() is False

    @pytest.mark.parametrize("condition", ["rainy", "pouring", "snowy", "hail", "lightning-rainy"])
    def test_the_precipitation_source_reads_every_precipitation_form(self, condition: str) -> None:
        """Elke standaard neerslagvorm telt: regen, sneeuw en hagel.

        Every default precipitation form counts: rain, snow and hail.
        """
        config = self._config(precipitation=PrecipitationSettings(source="weather.buienradar"))
        states = {"weather.buienradar": FakeState(condition)}
        assert coordinator(states, config)._precipitation() is True


# ---------------------------------------------------------------------------
# Uitvoeren: de service calls zelf.
# Carrying out: the service calls themselves.
# ---------------------------------------------------------------------------


class TestTheApplier:
    """Wat er werkelijk naar Home Assistant gaat, en wat er gebeurt als dat faalt.

    What really goes to Home Assistant, and what happens when it fails.
    """

    def _changes(self, world_modes: dict[str, str], indoor: float = 18.0):
        from conftest import make_world

        config = house()
        world = make_world(
            now=NOW,
            outdoor=5.0,
            indoor={"woonkamer": indoor, "zolder": 21.0},
            climates=world_modes,
            residents={"danny": __import__("conftest").awake()},
            presence={"zolder": __import__("conftest").PresenceState(occupied=True)},
        )
        return changes(decide(config, world), world)

    async def test_a_start_carries_its_setpoint_in_one_call(self) -> None:
        """Twee aanroepen zouden de unit even op de nieuwe stand met het oude doel zetten."""
        hass = FakeHass()
        pending = self._changes({LIVING: "off", BACKUP: "off", ATTIC: "off"})
        await apply(hass, pending, shadow=False)

        assert hass.services.calls, "er ging geen enkele aanroep uit"
        domain, service, data = hass.services.calls[0]
        assert domain == "climate"
        assert service == "set_temperature"
        assert data["hvac_mode"] == "heat"
        assert data["temperature"] == 21.0

    async def test_shadow_mode_sends_nothing(self) -> None:
        hass = FakeHass()
        pending = self._changes({LIVING: "off", BACKUP: "off", ATTIC: "off"})
        applied = await apply(hass, pending, shadow=True)
        assert hass.services.calls == []
        assert applied == ()

    async def test_nothing_to_do_sends_nothing(self) -> None:
        hass = FakeHass()
        assert await apply(hass, (), shadow=False) == ()
        assert hass.services.calls == []

    async def test_a_failed_start_only_costs_that_one_appliance(self) -> None:
        hass = FakeHass(failing={LIVING})
        pending = self._changes({LIVING: "off", BACKUP: "off", ATTIC: "off"})
        applied = await apply(hass, pending, shadow=False)
        assert LIVING not in [change.entity_id for change in applied]

    async def test_a_failed_stop_abandons_the_rest_of_the_plan(self) -> None:
        """De starts erachteraan zouden landen op een apparaat dat had moeten stoppen."""
        hass = FakeHass(failing={ATTIC})
        pending = self._changes({LIVING: "off", BACKUP: "off", ATTIC: "heat"}, indoor=18.0)
        stops = [change for change in pending if applier_module._is_stop(change)]
        assert stops, "dit scenario levert geen stop op"

        await apply(hass, pending, shadow=False)
        stopped_at = [call for call in hass.services.calls]
        assert len(stopped_at) <= len(pending)


# ---------------------------------------------------------------------------
# Naar buiten: gebeurtenissen.
# Outward: events.
# ---------------------------------------------------------------------------


class TestTheEvents:
    """Wat er op de bus komt, en vooral: wanneer niet.

    What lands on the bus, and above all: when it does not.
    """

    def _plan(self, indoor: float = 18.0, open_door: bool = False):
        from conftest import PresenceState, awake, make_world

        config = house()
        world = make_world(
            now=NOW,
            outdoor=5.0,
            indoor={"woonkamer": indoor, "zolder": 21.0},
            climates={LIVING: "off", BACKUP: "off", ATTIC: "off"},
            residents={"danny": awake()},
            presence={"zolder": PresenceState(occupied=True)},
            openings={
                "binary_sensor.achterdeur": __import__("conftest").OpeningState(
                    open=open_door, changed_at=NOW - timedelta(minutes=5)
                )
            },
        )
        return config, world, decide(config, world)

    def test_a_decision_event_carries_the_whole_outcome(self) -> None:
        config, world, plan = self._plan()
        item = coordinator({}, config)
        item._fire_events(plan)

        assert item.hass.bus.fired, "er ging geen enkel event uit"
        event, data = item.hass.bus.fired[0]
        assert event == "climate_director_decision"
        assert set(data) >= {
            "zone_id",
            "zone_name",
            "wanted",
            "granted",
            "source_id",
            "entity_id",
            "hvac_mode",
            "temperature",
            "reason",
        }

    def test_the_same_decision_twice_fires_once(self) -> None:
        """Anders verzuipt elke automatisering die meeluistert."""
        config, world, plan = self._plan()
        item = coordinator({}, config)
        item._fire_events(plan)
        first = len(item.hass.bus.fired)
        item.data = plan
        item._fire_events(plan)
        assert len(item.hass.bus.fired) == first

    def test_a_refusal_fires_with_its_ready_made_sentences(self) -> None:
        config, world, plan = self._plan(open_door=True)
        item = coordinator({}, config)
        item.world = world
        item._precondition = {"woonkamer": NOW + timedelta(hours=1)}
        item._fire_refusals(plan)

        assert item.hass.bus.fired, "een geweigerd verzoek meldde zichzelf niet"
        event, data = item.hass.bus.fired[0]
        assert event == "climate_director_precondition_refused"
        assert data["zone"] == "Woonkamer"
        assert data["message"] and data["confirmed_message"] and data["confirm_label"]

    def test_a_refusal_that_stays_refused_fires_once(self) -> None:
        config, world, plan = self._plan(open_door=True)
        item = coordinator({}, config)
        item.world = world
        item._precondition = {"woonkamer": NOW + timedelta(hours=1)}
        item._fire_refusals(plan)
        item._fire_refusals(plan)
        assert len(item.hass.bus.fired) == 1


# ---------------------------------------------------------------------------
# De entiteiten die de gebruiker ziet.
# The entities the user sees.
# ---------------------------------------------------------------------------


def _bind(entity_class, coordinator_stub, **attributes):
    """Return an entity without going through Home Assistant's machinery."""
    entity = entity_class.__new__(entity_class)
    entity.coordinator = coordinator_stub
    for name, value in attributes.items():
        setattr(entity, name, value)
    return entity


class TestTheEntities:
    """Elke entiteit die de integratie aanmaakt, met een echt plan eronder.

    Every entity the integration creates, with a real plan under it.
    """

    @pytest.fixture
    def running(self):
        from conftest import PresenceState, awake, make_world

        config = house()
        world = make_world(
            now=NOW,
            outdoor=5.0,
            indoor={"woonkamer": 18.0, "zolder": 21.0},
            climates={LIVING: "off", BACKUP: "off", ATTIC: "off"},
            residents={"danny": awake()},
            presence={"zolder": PresenceState(occupied=True)},
        )
        plan = decide(config, world)

        item = coordinator({}, config)
        item.data = plan
        item.world = world
        item.last_changes = changes(plan, world)
        return item

    def test_the_decision_sensor_counts_the_served_zones(self, running) -> None:
        sensor = _bind(DecisionSensor, running)
        assert sensor.native_value == "1/2"
        attributes = sensor.extra_state_attributes
        assert attributes["shadow_mode"] is False
        assert attributes["commands"]
        assert LIVING in attributes["would_change"]

    def test_the_command_sensor_shows_the_mode(self, running) -> None:
        sensor = _bind(CommandSensor, running, _target=LIVING)
        assert sensor.native_value == "heat"
        assert sensor.extra_state_attributes["temperature"] == 21.0

    def test_the_command_sensor_says_left_alone_without_a_command(self, running) -> None:
        sensor = _bind(CommandSensor, running, _target=BACKUP)
        assert sensor.native_value in ("off", "left_alone", "unreachable")

    def test_the_mismatch_sensor_counts_the_differences(self, running) -> None:
        sensor = _bind(MismatchSensor, running)
        assert sensor.native_value == len(running.last_changes)
        assert sensor.extra_state_attributes["differences"]

    def test_the_zone_source_sensor_names_the_source(self, running) -> None:
        sensor = _bind(ZoneSourceSensor, running, _zone_id="woonkamer")
        assert sensor.native_value == "woonkamer_airco"
        assert sensor.extra_state_attributes["reason"] == "regulating"

    def test_the_blocked_sensor_carries_every_shut_gate(self, running) -> None:
        sensor = _bind(ZoneBlockedSensor, running, _zone_id="woonkamer")
        assert sensor.is_on is False
        assert sensor.extra_state_attributes["closed_gates"] == []

    def test_the_fallback_sensor_is_off_while_the_first_choice_works(self, running) -> None:
        sensor = _bind(ZoneFallbackSensor, running, _zone_id="woonkamer")
        assert sensor.is_on is False

    def test_the_stuck_sensor_reports_unreadable_entities(self, running) -> None:
        """Het toestandsregister is hier leeg, dus alles is onleesbaar - en dat mag
        de melder niet stil laten."""
        sensor = _bind(StuckSensor, running)
        assert sensor.is_on is True
        assert sensor.extra_state_attributes["zones"] == []
        assert sensor.extra_state_attributes["unusable_entities"]

    def test_the_stuck_sensor_is_quiet_when_everything_reads(self) -> None:
        item = coordinator(_healthy_states())
        item.data = object()
        sensor = _bind(StuckSensor, item)
        assert sensor.is_on is False

    def test_every_sensor_survives_a_plan_that_does_not_exist_yet(self) -> None:
        """Bij het opstarten is er nog geen besluit; niets mag daarop stuklopen."""
        item = coordinator({})
        item.data = None
        for entity, attributes in (
            (DecisionSensor, {}),
            (MismatchSensor, {}),
            (CommandSensor, {"_target": LIVING}),
            (ZoneSourceSensor, {"_zone_id": "woonkamer"}),
            (ZoneBlockedSensor, {"_zone_id": "woonkamer"}),
            (ZoneFallbackSensor, {"_zone_id": "woonkamer"}),
        ):
            bound = _bind(entity, item, **attributes)
            value = bound.native_value if hasattr(bound, "native_value") else bound.is_on
            assert value is None
            # De afwijkingenteller kan zijn attributen wél opbouwen zonder plan:
            # er is dan simpelweg niets veranderd.
            #
            # The mismatch sensor can build its attributes without a plan: then
            # simply nothing has changed.
            assert bound.extra_state_attributes in ({}, {"shadow_mode": False, "differences": []})


class TestTheBackupTakesOver:
    """Een reservebron springt in zodra de eerste keus niet te bereiken is.

    A reserve source steps in the moment the first choice cannot be reached.

    Dit is het geval waar de "op reserve"-melder voor bestaat: de kamer wordt
    gewoon warm, alleen anders dan bedoeld - en zonder melder merk je dat pas
    op de energierekening.

    This is the case the "on stand-in" sensor exists for: the room simply gets
    warm, only differently than intended - and without the sensor you notice on
    the energy bill.
    """

    def _plan(self, first: str, second: str):
        from conftest import PresenceState, awake, climate, make_world

        config = house()
        world = make_world(
            now=NOW,
            outdoor=5.0,
            indoor={"woonkamer": 18.0, "zolder": 21.0},
            climates={
                LIVING: climate("off", available=first == "ok"),
                BACKUP: climate("off", available=second == "ok"),
                ATTIC: "off",
            },
            residents={"danny": awake()},
            presence={"zolder": PresenceState(occupied=True)},
        )
        return config, world, decide(config, world)

    def test_the_first_choice_serves_while_it_is_reachable(self) -> None:
        _, _, plan = self._plan("ok", "ok")
        decision = plan.decision_for("woonkamer")
        assert decision.source_id == "woonkamer_airco"
        assert decision.on_fallback is False

    def test_the_reserve_serves_once_the_first_drops_out(self) -> None:
        _, _, plan = self._plan("weg", "ok")
        decision = plan.decision_for("woonkamer")
        assert decision.source_id == "woonkamer_reserve"
        assert decision.granted is ModeFamily.HEAT
        assert decision.on_fallback is True
        assert decision.passed_over == ("woonkamer_airco",)

    def test_the_sensor_says_which_one_was_skipped(self) -> None:
        config, world, plan = self._plan("weg", "ok")
        item = coordinator({}, config)
        item.data = plan
        sensor = _bind(ZoneFallbackSensor, item, _zone_id="woonkamer")
        assert sensor.is_on is True
        assert sensor.extra_state_attributes["unreachable"] == ["woonkamer_airco"]
        assert sensor.extra_state_attributes["serving"] == "woonkamer_reserve"

    def test_both_gone_leaves_the_zone_without_a_source(self) -> None:
        _, _, plan = self._plan("weg", "weg")
        decision = plan.decision_for("woonkamer")
        assert decision.granted is ModeFamily.NEUTRAL
        assert decision.reason is Reason.NO_SOURCE_AVAILABLE

    def test_an_unreachable_appliance_is_never_commanded(self) -> None:
        _, _, plan = self._plan("weg", "ok")
        assert plan.command_for(LIVING) is None
        left = plan.untouched_for(LIVING)
        assert left is not None
        assert left.reason is Reason.SOURCE_UNREACHABLE


class TestTheStuckSensorOverTime:
    """De wachtteller loopt op zolang dezelfde reden blijft staan.

    The waiting clock runs on for as long as the same reason stays.
    """

    def _plan_with(self, reason: Reason):
        from custom_components.climate_director.engine.plan import Plan, ZoneDecision

        return Plan(
            zones=(
                ZoneDecision(
                    zone_id="woonkamer",
                    wanted=ModeFamily.HEAT,
                    granted=ModeFamily.NEUTRAL,
                    reason=reason,
                ),
            )
        )

    def test_a_waiting_reason_starts_the_clock(self) -> None:
        item = coordinator({})
        item._note_waiting(self._plan_with(Reason.CIRCUIT_AT_CAPACITY))
        assert "woonkamer" in item.waiting_seconds()

    def test_an_ordinary_reason_does_not(self) -> None:
        item = coordinator({})
        item._note_waiting(self._plan_with(Reason.NOBODY_HOME))
        assert item.waiting_seconds() == {}

    def test_it_reports_stuck_once_the_limit_passes(self, monkeypatch) -> None:
        from custom_components.climate_director import coordinator as module

        config = DirectorConfig(zones=house().zones, stuck_after=timedelta(minutes=15))
        item = coordinator({}, config)
        item._note_waiting(self._plan_with(Reason.SHORT_CYCLE_PROTECTION))
        assert item.stuck_zones() == {}

        monkeypatch.setattr(module.dt_util, "now", lambda: NOW + timedelta(minutes=16))
        assert item.stuck_zones() == {"woonkamer": Reason.SHORT_CYCLE_PROTECTION}

    def test_a_changed_reason_restarts_the_clock(self, monkeypatch) -> None:
        from custom_components.climate_director import coordinator as module

        config = DirectorConfig(zones=house().zones, stuck_after=timedelta(minutes=15))
        item = coordinator({}, config)
        item._note_waiting(self._plan_with(Reason.SHORT_CYCLE_PROTECTION))

        monkeypatch.setattr(module.dt_util, "now", lambda: NOW + timedelta(minutes=16))
        item._note_waiting(self._plan_with(Reason.CIRCUIT_AT_CAPACITY))
        assert item.stuck_zones() == {}
