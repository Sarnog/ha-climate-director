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
            self._unusable_latest = self.unusable_entities()

        build_world = ClimateDirectorCoordinator.build_world
        _overridden_zones = ClimateDirectorCoordinator._overridden_zones
        tracked_entities = ClimateDirectorCoordinator.tracked_entities
        unusable_entities = ClimateDirectorCoordinator.unusable_entities
        stuck_zones = ClimateDirectorCoordinator.stuck_zones
        waiting_seconds = ClimateDirectorCoordinator.waiting_seconds
        unusable_latest = ClimateDirectorCoordinator.unusable_latest
        _note_waiting = ClimateDirectorCoordinator._note_waiting
        _climate_ids = ClimateDirectorCoordinator._climate_ids
        _climate = ClimateDirectorCoordinator._climate
        _temperature = ClimateDirectorCoordinator._temperature
        _resident = ClimateDirectorCoordinator._resident
        _opening = ClimateDirectorCoordinator._opening
        _presence = ClimateDirectorCoordinator._presence
        _season = ClimateDirectorCoordinator._season
        _precipitation = ClimateDirectorCoordinator._precipitation
        _notice_precipitation = ClimateDirectorCoordinator._notice_precipitation
        _calendar_says_holiday = ClimateDirectorCoordinator._calendar_says_holiday
        _zones_handed_back = ClimateDirectorCoordinator._zones_handed_back
        _live_preconditions = ClimateDirectorCoordinator._live_preconditions
        _everyone_asleep = ClimateDirectorCoordinator._everyone_asleep
        _house_is_empty = ClimateDirectorCoordinator._house_is_empty
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

    def test_it_reads_the_modes_an_appliance_says_it_has(self) -> None:
        """De standenlijst komt mee, want daar kiest de engine op.

        Zonder deze lijst commandeert de engine een stand die het apparaat
        misschien niet kent; met de lijst kiest hij een stand die er wel is.

        The mode list comes along, since that is what the engine picks on.
        Without it the engine commands a mode the appliance may not have; with
        it, it picks one that exists.
        """
        states = self._states(
            **{
                LIVING: FakeState(
                    "heat",
                    {"temperature": 21.0, "hvac_modes": ["off", "heat", "cool", "fan_only"]},
                )
            }
        )
        world = coordinator(states).build_world()

        assert world.climate(LIVING).hvac_modes == frozenset({"off", "heat", "cool", "fan_only"})

    def test_an_appliance_that_lists_no_modes_gets_the_benefit_of_the_doubt(self) -> None:
        """Onbekend is niet hetzelfde als geen enkele stand.

        Een lege lijst of een onzinnige waarde betekent "ik weet het niet", en
        dan stuurt de engine gewoon zoals voordat deze controle bestond. Zou
        `None` als "kan niets" gelezen worden, dan valt zo'n apparaat stil.

        Unknown is not the same as no modes at all. An empty list or a nonsense
        value means "I do not know", and the engine then commands exactly as it
        did before the check existed.
        """
        for attributes in ({}, {"hvac_modes": []}, {"hvac_modes": "heat"}):
            states = self._states(**{LIVING: FakeState("heat", dict(attributes))})
            assert coordinator(states).build_world().climate(LIVING).hvac_modes is None

    def test_a_mode_list_of_other_types_is_read_as_text(self) -> None:
        """Een integratie die iets anders dan strings meldt, blokkeert niets."""
        states = self._states(**{LIVING: FakeState("heat", {"hvac_modes": ("off", 1)})})
        assert coordinator(states).build_world().climate(LIVING).hvac_modes == frozenset(
            {"off", "1"}
        )

    def test_a_cover_opening_reads_its_configured_open_state(self) -> None:
        """`cover.dakraam = open` schort de zone op, ook al is 'on' de standaard.

        `cover.dakraam = open` suspends the zone even though 'on' is the default.
        """
        config = DirectorConfig(
            zones=house().zones,
            openings=(Opening(entity_id="cover.dakraam", open_state="open"),),
        )
        states = self._states(**{"cover.dakraam": FakeState("open")})
        assert coordinator(states, config).build_world().opening("cover.dakraam").open is True

    def test_a_cover_that_is_not_open_reads_as_closed(self) -> None:
        config = DirectorConfig(
            zones=house().zones,
            openings=(Opening(entity_id="cover.dakraam", open_state="open"),),
        )
        states = self._states(**{"cover.dakraam": FakeState("closed")})
        assert coordinator(states, config).build_world().opening("cover.dakraam").open is False

    def test_an_opening_still_defaults_to_the_state_on(self) -> None:
        """Wie niets instelt houdt het oude gedrag: 'on' is open, 'open' niet.

        Whoever configures nothing keeps the old behaviour: 'on' is open, 'open' is not.
        """
        config = DirectorConfig(
            zones=house().zones,
            openings=(Opening(entity_id="binary_sensor.achterdeur"),),
        )
        states = self._states(
            **{
                "binary_sensor.achterdeur": FakeState("on"),
                "cover.dakraam": FakeState("open"),
            }
        )
        world = coordinator(states, config).build_world()
        assert world.opening("binary_sensor.achterdeur").open is True

    def test_an_opening_that_predates_the_start_counts_as_open_long_enough(self) -> None:
        """Na een herstart telt een al openstaand raam direct mee, niet pas na de delay.

        `last_changed` leest na een herstart het herstartmoment; wie de delay
        vanaf dat moment zou tellen stookt nog `delay` lang met een raam open.
        Daarom: wie vóór het opstartmoment openstond geldt als open lange tijd.

        After a restart `last_changed` reads the restart moment; counting the
        delay from that moment would keep heating with a window open for
        `delay` more. Hence: whatever stood open before the start moment counts
        as open long enough.
        """
        config = DirectorConfig(
            zones=house().zones,
            openings=(Opening(entity_id="binary_sensor.achterdeur", delay=timedelta(minutes=5)),),
        )
        item = coordinator(
            self._states(
                **{
                    "binary_sensor.achterdeur": FakeState(
                        "on", last_changed=NOW - timedelta(minutes=30)
                    )
                }
            ),
            config,
        )
        item._started_at = NOW
        assert item._opening("binary_sensor.achterdeur", "on").changed_at is None

    def test_an_opening_that_changed_after_the_start_keeps_its_timestamp(self) -> None:
        """Wie pas na het opstartmoment openging houdt zijn gewone delay."""
        config = DirectorConfig(
            zones=house().zones,
            openings=(Opening(entity_id="binary_sensor.achterdeur", delay=timedelta(minutes=5)),),
        )
        item = coordinator(
            self._states(**{"binary_sensor.achterdeur": FakeState("on", last_changed=NOW)}),
            config,
        )
        item._started_at = NOW - timedelta(minutes=10)
        assert item._opening("binary_sensor.achterdeur", "on").changed_at == NOW

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

    def _event(self, entity_id: str, old: str, new: str):
        """Return a state-change event like Home Assistant would hand over."""

        class Event:
            data = {
                "entity_id": entity_id,
                "old_state": FakeState(old),
                "new_state": FakeState(new),
            }

        return Event()

    def test_the_precipitation_reader_does_not_write(self) -> None:
        """De lezer geeft alleen een antwoord; het moment hoort in de listener.

        The reader only returns an answer; the moment belongs in the listener.
        """
        config = self._config(precipitation=PrecipitationSettings(source="weather.buienradar"))
        item = coordinator({"weather.buienradar": FakeState("rainy")}, config)
        assert item._precipitation() is True
        assert item._precipitation_seen_at is None

    def test_the_listener_records_the_moment_precipitation_is_reported(self) -> None:
        config = self._config(precipitation=PrecipitationSettings(source="weather.buienradar"))
        item = coordinator({"weather.buienradar": FakeState("cloudy")}, config)
        item._notice_precipitation(self._event("weather.buienradar", "cloudy", "rainy"))
        assert item._precipitation_seen_at == NOW

    def test_the_listener_stays_out_of_it_without_a_source(self) -> None:
        """Geen neerslagbron ingesteld: geen enkele wijziging noteert iets.

        No precipitation source configured: no change records anything.
        """
        item = coordinator({"weather.buienradar": FakeState("cloudy")}, self._config())
        item._notice_precipitation(self._event("weather.buienradar", "cloudy", "rainy"))
        assert item._precipitation_seen_at is None

    def test_the_listener_ignores_a_change_between_two_dry_states(self) -> None:
        """Bewolkt -> zonnig is geen neerslag en hoort de nalooptijd niet te verlengen.

        Cloudy -> sunny is not precipitation and must not extend the grace.
        """
        config = self._config(precipitation=PrecipitationSettings(source="weather.buienradar"))
        item = coordinator({"weather.buienradar": FakeState("cloudy")}, config)
        item._notice_precipitation(self._event("weather.buienradar", "cloudy", "sunny"))
        assert item._precipitation_seen_at is None


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

    async def test_a_start_sends_the_mode_first_and_the_setpoint_after(self) -> None:
        """De stand gaat als eigen aanroep, vóór het setpoint."""
        hass = FakeHass()
        pending = self._changes({LIVING: "off", BACKUP: "off", ATTIC: "off"})
        await apply(hass, pending, shadow=False)

        assert len(hass.services.calls) == 2
        domain, service, data = hass.services.calls[0]
        assert domain == "climate"
        assert service == "set_hvac_mode"
        assert data["hvac_mode"] == "heat"

        domain, service, data = hass.services.calls[1]
        assert domain == "climate"
        assert service == "set_temperature"
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


class TestAFailedSetpointComesBack:
    """Een mislukte `set_temperature` wordt de volgende ronde opnieuw aangeboden.

    A failed `set_temperature` is offered again the next round.
    """

    async def test_the_retry_runs_until_the_call_lands(self) -> None:
        from conftest import climate as state
        from conftest import make_world

        from custom_components.climate_director.engine import Plan
        from custom_components.climate_director.engine.plan import UnitCommand

        command = UnitCommand(entity_id=LIVING, hvac_mode="heat", temperature=21.0)
        plan = Plan(commands=(command,))
        world = make_world(climates={LIVING: state("heat", target=None)})
        sent: dict[str, tuple[str, float]] = {}

        def remember(executed: tuple) -> None:
            for change in executed:
                if change.set_temperature and change.command.temperature is not None:
                    sent[change.entity_id] = (
                        change.command.hvac_mode,
                        change.command.temperature,
                    )

        # Ronde 1: het setpoint wordt aangeboden, maar de aanroep mislukt.
        # Round 1: the setpoint is offered, but the call fails.
        failing = FakeHass(failing={LIVING})
        first = changes(plan, world, sent)
        assert first and first[0].set_temperature
        executed = await apply(failing, first, shadow=False)
        assert executed == ()
        remember(executed)

        # Ronde 2: zonder "uitgevoerd" in de boekhouding wordt het opnieuw
        # aangeboden, en nu komt de aanroep aan.
        # Round 2: with nothing "executed" in the bookkeeping it is offered
        # again, and now the call lands.
        healed = FakeHass()
        second = changes(plan, world, sent)
        assert second and second[0].set_temperature
        executed = await apply(healed, second, shadow=False)
        assert [change.entity_id for change in executed] == [LIVING]
        remember(executed)

        # Ronde 3: het setpoint is uitgevoerd, dus er valt niets meer te doen.
        # Round 3: the setpoint was executed, so nothing remains to do.
        assert changes(plan, world, sent) == ()


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


BOILER = "climate.cv_ketel"
LIVING_WINDOW = "binary_sensor.raam_woonkamer"
FRONT_DOOR = "binary_sensor.voordeur"


class TestTheHouseWideRefusal:
    """Een verzoek dat op de huisbrede stop strandt, meldt zich net zo goed.

    A request stranded on the house-wide stop reports itself just the same.
    """

    def _config(self) -> DirectorConfig:
        """Return two rooms sharing one boiler, each with a door of its own."""

        def warmth() -> ModeSettings:
            return ModeSettings(target=21.0, start_at=20.0, hysteresis=1.0)

        living = Zone(
            zone_id="woonkamer",
            name="Woonkamer",
            indoor_sensor="sensor.woonkamer",
            priority=0,
            sources=(Source("ketel_wk", BOILER, role=SourceRole.HEAT_ONLY),),
            heat=warmth(),
        )
        hall = Zone(
            zone_id="hal",
            name="Hal",
            indoor_sensor="sensor.hal",
            priority=1,
            sources=(Source("ketel_hal", BOILER, role=SourceRole.HEAT_ONLY),),
            heat=warmth(),
        )
        return DirectorConfig(
            zones=(living, hall),
            openings=(
                Opening(entity_id=LIVING_WINDOW, zone_ids=("woonkamer",)),
                Opening(entity_id=FRONT_DOOR, zone_ids=("hal",)),
            ),
            house_wide_openings=(BOILER,),
        )

    def _world(self, *, open_living: bool, open_front: bool, bypass: bool = False):
        from conftest import OpeningState, awake, make_world

        openings: dict[str, OpeningState] = {}
        if open_living:
            openings[LIVING_WINDOW] = OpeningState(open=True, changed_at=NOW - timedelta(minutes=5))
        if open_front:
            openings[FRONT_DOOR] = OpeningState(open=True, changed_at=NOW - timedelta(minutes=5))
        return make_world(
            now=NOW,
            outdoor=5.0,
            indoor={"woonkamer": 18.0, "hal": 22.0},
            climates={BOILER: "off"},
            residents={"danny": awake()},
            openings=openings,
            precondition_until={"woonkamer": NOW + timedelta(hours=1)},
            precondition_bypass=frozenset({"woonkamer"}) if bypass else frozenset(),
        )

    def _fired(self, *, open_living: bool, open_front: bool):
        config = self._config()
        world = self._world(open_living=open_living, open_front=open_front)
        plan = decide(config, world)
        item = coordinator({}, config)
        item.world = world
        item._precondition = {"woonkamer": NOW + timedelta(hours=1)}
        item._fire_refusals(plan)
        return item

    @pytest.mark.parametrize(
        ("open_living", "open_front", "expected"),
        [
            (True, False, [LIVING_WINDOW]),
            (False, True, [FRONT_DOOR]),
            (True, True, [LIVING_WINDOW, FRONT_DOOR]),
        ],
    )
    def test_the_event_names_every_opening_that_holds_the_request_back(
        self, open_living: bool, open_front: bool, expected: list[str]
    ) -> None:
        item = self._fired(open_living=open_living, open_front=open_front)

        assert item.hass.bus.fired, "een geweigerd verzoek meldde zichzelf niet"
        event, data = item.hass.bus.fired[0]
        assert event == "climate_director_precondition_refused"
        assert data["openings"] == expected

    def test_a_request_told_to_ignore_openings_fires_nothing(self) -> None:
        config = self._config()
        world = self._world(open_living=False, open_front=True, bypass=True)
        plan = decide(config, world)
        item = coordinator({}, config)
        item.world = world
        item._precondition = {"woonkamer": NOW + timedelta(hours=1)}
        item._fire_refusals(plan)

        assert item.hass.bus.fired == []

    def test_a_refusal_that_changes_reason_still_fires_once(self) -> None:
        config = self._config()
        item = coordinator({}, config)
        item._precondition = {"woonkamer": NOW + timedelta(hours=1)}

        world = self._world(open_living=False, open_front=True)
        item.world = world
        item._fire_refusals(decide(config, world))

        world = self._world(open_living=True, open_front=True)
        item.world = world
        item._fire_refusals(decide(config, world))

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

    def test_the_stuck_sensor_names_unreadable_entities_without_alarming(self, running) -> None:
        """Onleesbare entiteiten staan in het attribuut, maar zetten de melder niet aan.

        Het toestandsregister is hier leeg, dus alles is onleesbaar. Daar hoort
        sinds deze ronde een eigen reparatiemelding bij; de vastloopmelder gaat
        weer alleen over een zone die te lang op dezelfde wachtreden staat,
        precies wat zijn naam zegt. De lijst blijft er wel in staan, want de
        bewakingsblueprint leest hem.

        Unreadable entities sit in the attribute but do not raise the sensor.
        The state registry is empty here, so everything is unreadable. That has a
        repair notice of its own as of this round; the stuck sensor is once again
        only about a zone sitting on the same waiting reason too long, exactly
        what its name says. The list stays in the attribute, since the monitoring
        blueprint reads it.
        """
        sensor = _bind(StuckSensor, running)
        assert sensor.is_on is False
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
        item._note_waiting(self._plan_with(Reason.SHORT_CYCLE_PROTECTION))
        assert "woonkamer" in item.waiting_seconds()

    def test_a_full_outdoor_unit_does_not(self) -> None:
        """Vol is een toestand, geen wacht: die mag uren duren zonder alarm."""
        item = coordinator({})
        item._note_waiting(self._plan_with(Reason.CIRCUIT_AT_CAPACITY))
        assert item.waiting_seconds() == {}

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


def test_an_unreachable_generator_reads_unreachable_not_left_alone() -> None:
    """De CommandSensor belooft onderscheid; een kapotte ketel is 'unreachable'.

    The CommandSensor promises a distinction; a broken boiler is 'unreachable'.
    """
    from conftest import climate, make_world

    from custom_components.climate_director.engine import MODE_OFF, Generator

    boiler = "climate.ketel"
    config = DirectorConfig(
        zones=(
            Zone(
                "woonkamer",
                "Woonkamer",
                "sensor.woonkamer",
                sources=(Source("trv", "climate.trv_woonkamer", role=SourceRole.HEAT_ONLY),),
                heat=ModeSettings(21.0, 20.0),
            ),
        ),
        generators=(Generator("cv", "CV", boiler),),
    )
    world = make_world(
        indoor={"woonkamer": 18.0},
        climates={"climate.trv_woonkamer": "off", boiler: climate(MODE_OFF, available=False)},
    )
    plan = decide(config, world)

    item = coordinator({}, config)
    item.data = plan
    item.world = world
    sensor = _bind(CommandSensor, item, _target=boiler)
    assert sensor.native_value == "unreachable"
    assert sensor.extra_state_attributes["reason"] == "source_unreachable"
