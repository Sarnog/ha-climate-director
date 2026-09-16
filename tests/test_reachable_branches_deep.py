"""Kleine, bereikbare engine- en opslagtakken (ronde 30, fase 3b).

Small, reachable engine and storage branches (round 30, phase 3b).

De tweede helft van de dekkingsronde: de takken die geen eigen scherm hebben
maar wel degelijk te bereiken zijn — een commando zonder setpoint, een bron die
naar een onbekende zone wijst, een override die afloopt, een opgeslagen
override die terugkomt. Elk daarvan is een gewone toestand van de integratie,
geen verdediging tegen Home Assistant. Ronde 32 (R32-1) heeft de laatste zes
regels die nog met `# pragma: no cover` waren afgevangen ook gemeten; zie
`TestTheLastSixExcludedLines` onderaan. Het pakket draagt sindsdien **geen
enkele** pragma meer, en dat houdt `test_nothing_is_hidden_from_the_measurement`
vast.

The second half of the coverage round: the branches that have no screen of their
own but are perfectly reachable — a command without a setpoint, a source naming
an unknown zone, an override running out, a stored override coming back. Each of
these is an ordinary state of the integration, not a defence against Home
Assistant. Round 32 (R32-1) measured the last six lines that were still caught
with `# pragma: no cover` as well; see `TestTheLastSixExcludedLines` at the
bottom. The package has carried **no** pragma since, and
`test_nothing_is_hidden_from_the_measurement` holds that down.
"""

from __future__ import annotations

import dataclasses
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from conftest import climate, house, make_world
from coverage import Coverage
from homeassistant.util import dt as dt_util

import custom_components.climate_director.engine.sources as source_picker
import script.coverage_gate as coverage_gate
from custom_components.climate_director import problems, texts
from custom_components.climate_director.binary_sensor import ZoneBlockedSensor, ZoneFallbackSensor
from custom_components.climate_director.coordinator import ClimateDirectorCoordinator
from custom_components.climate_director.engine import diff, models, serialise, table_storage
from custom_components.climate_director.engine.decide import _group_holder, clamped_target
from custom_components.climate_director.engine.fields import FieldSpec
from custom_components.climate_director.engine.models import ModeFamily
from custom_components.climate_director.overrides import _OverridesMixin
from custom_components.climate_director.preconditions import _PreconditionsMixin
from custom_components.climate_director.schema_fields import _summer_months
from custom_components.climate_director.sensor import ZoneSourceSensor
from custom_components.climate_director.state_store import _StateStoreMixin
from custom_components.climate_director.switch import _DirectorSwitch, _opening_label
from custom_components.climate_director.world_builder import _WorldBuilderMixin

PACKAGE = Path(__file__).resolve().parents[1] / "custom_components" / "climate_director"

# -- de engine ----------------------------------------------------------------
# -- the engine ---------------------------------------------------------------


def test_a_command_without_a_setpoint_is_never_measured_against_one() -> None:
    """Een stand-commando zonder setpoint is nooit 'te ver' van iets."""
    assert diff._close(None, None) is True
    assert diff._close(20.0, None) is True


def test_clamping_a_command_without_a_setpoint_gives_nothing() -> None:
    """Zonder setpoint valt er niets af te kappen."""
    assert clamped_target(None, climate("heat")) is None


def test_a_group_holder_ignores_a_member_that_is_no_source() -> None:
    """Een apparaat dat in geen enkele bron voorkomt bezet de groep niet."""
    assert _group_holder(house(), make_world(), frozenset({"climate.geen_bron"})) is None


def test_a_dead_band_without_a_serving_source_holds_nothing() -> None:
    """Zonder geleverde bron, of met een bron die niet meer bestaat, houdt de band niets."""
    zone = house().zones[0]
    world = make_world()
    assert source_picker._held(zone, ModeFamily.HEAT, world, None, 2.0, []) is None
    assert source_picker._held(zone, ModeFamily.HEAT, world, "bestaat_niet", 2.0, []) is None


def test_a_dead_band_lets_go_outside_its_takeover_or_when_blocked() -> None:
    """Buiten de overname, of huisbreed stilgezet, houdt de band de bron niet vast."""
    zone = house().zones[0]
    world = make_world()
    source = zone.sources[0]
    outside = source_picker._held(
        zone, ModeFamily.HEAT, world, source.source_id, 2.0, [], only=frozenset({"climate.anders"})
    )
    assert outside is None
    blocked = source_picker._held(
        zone,
        ModeFamily.HEAT,
        world,
        source.source_id,
        2.0,
        [],
        blocked=frozenset({source.entity_id}),
    )
    assert blocked is None


def test_a_source_covering_an_unknown_zone_is_reported() -> None:
    """Een bron die een onbekende zone in zijn gebied noemt wordt gemeld."""
    base = house()
    zone = base.zones[0]
    source = dataclasses.replace(zone.sources[0], covers_zones=("bestaat_niet",))
    zone = dataclasses.replace(zone, sources=(source, *zone.sources[1:]))
    config = dataclasses.replace(base, zones=(zone, *base.zones[1:]))

    found = [problem.code for problem in models._rule_source_covered_zones(config)]
    assert found == ["source_unknown_covered_zone"]


def test_a_guest_window_without_a_start_is_dropped() -> None:
    """Een gastenvenster zonder begin- of eindtijd bestaat niet."""
    assert serialise._guest_window({}) is None
    assert serialise._guest_window({"start": "09:00:00"}) is None


# -- de veldtabel -------------------------------------------------------------
# -- the field table ----------------------------------------------------------


def test_an_optional_type_is_unwrapped() -> None:
    """`X | None` leest als `X`; een gewoon type blijft zichzelf."""
    assert table_storage._unwrap(int | None) is int
    assert table_storage._unwrap(int) is int


def test_a_number_without_a_known_unit_reads_as_a_float() -> None:
    """Een getalveld met een onbekende maat leest als gewoon getal."""
    field = FieldSpec(key="x", kind="number", unit="onbekend", default=0.0)
    assert table_storage.parse_leaf(field, 3.5) == 3.5


def test_an_unknown_field_type_is_refused() -> None:
    """Een veldtype dat de tabel niet kent is een fout in de tabel, geen datafout."""
    field = FieldSpec(key="x", kind="onbekend")
    with pytest.raises(AssertionError, match="onbekend veldtype"):
        table_storage.parse_leaf(field, 1)
    with pytest.raises(AssertionError, match="onbekend veldtype"):
        table_storage.write_leaf(field, 1)


def test_a_broken_stored_month_list_falls_back_on_the_default() -> None:
    """Een bewaarde zomermaandenlijst met onbruikbare waarden telt als geen lijst."""
    assert _summer_months("north", ["geen getal"]) == _summer_months("north", [])


def test_a_label_for_an_unknown_opening_falls_back_on_its_id() -> None:
    """Een overbruggingsschakelaar zonder vindbare opening leest als zijn id."""
    coordinator = SimpleNamespace(config=house())
    assert _opening_label(coordinator, "bestaat_niet") == "bestaat_niet"


def test_a_presence_entity_that_is_missing_counts_as_nobody_home() -> None:
    """Zonder aanwezigheidsentiteit is er niemand thuis, en dat is geen fout."""
    builder = _WorldBuilderMixin.__new__(_WorldBuilderMixin)
    builder.hass = SimpleNamespace(states=SimpleNamespace(get=lambda _entity_id: None))
    assert builder._presence("person.bestaat_niet", "on").occupied is False


# -- overrides ----------------------------------------------------------------


class OverrideHost(_OverridesMixin):
    """A stand-in for the coordinator with just the override state on it.

    A stand-in for the coordinator with just the override state on it.
    """

    def __init__(self, config: Any) -> None:
        self.config = config
        self.zone_overrides: dict[str, bool] = {}
        self.zone_override_until: dict[str, Any] = {}
        self.zone_override_when_done: dict[str, str] = {}
        self._cancel_override_wake: Any = None
        self.evaluations = 0

    def async_request_evaluation(self) -> None:
        self.evaluations += 1


def test_an_override_for_an_unknown_zone_is_refused() -> None:
    """Een override voor een zone die niet bestaat levert niets op."""
    assert OverrideHost(house()).override_source("bestaat_niet", "heat") is None


def test_an_override_in_a_neutral_mode_may_use_any_source() -> None:
    """`off` en `fan_only` passen op elke bron, ongeacht de rol."""
    zone = house().zones[0]
    assert OverrideHost(house())._override_source(zone, "off") is not None


def test_an_override_wake_with_nothing_pending_does_nothing() -> None:
    """Zonder lopende override valt er niets te wekken."""
    host = OverrideHost(house())
    host._override_wake_at_first_expiry()
    assert host._cancel_override_wake is None


def test_the_override_expiry_wakes_the_evaluation() -> None:
    """Als een override afloopt wordt er opnieuw beslist en opnieuw gewekt."""
    host = OverrideHost(house())
    host._on_override_expiry(dt_util.utcnow())
    assert host.evaluations == 1


# -- de opslag van de override-staat ------------------------------------------
# -- the storage of the override state ----------------------------------------


class StoreHost(_StateStoreMixin):
    """A stand-in for the coordinator on the storage side.

    A stand-in for the coordinator on the storage side.
    """

    def __init__(self, config: Any, *, with_overrides: bool = True) -> None:
        self.config = config
        if with_overrides:
            self.zone_overrides: dict[str, bool] = {}
            self.zone_override_until: dict[str, Any] = {}
            self.zone_override_when_done: dict[str, str] = {}
            self.zone_override_entity: dict[str, str] = {}
        self.wakes = 0

    def _override_wake_at_first_expiry(self) -> None:
        self.wakes += 1


def test_a_store_without_override_state_simply_returns() -> None:
    """Een stand-in zonder override-staat laadt gewoon wat hij kent."""
    store = StoreHost(house(), with_overrides=False)
    store._restore_overrides({}, dt_util.utcnow())
    assert store.wakes == 0


def test_a_live_override_comes_back_and_an_expired_one_does_not() -> None:
    """Een lopende override komt terug; een verlopen of onbekende niet."""
    now = dt_util.utcnow()
    zone_id = house().zones[0].zone_id
    expired_zone = house().zones[1].zone_id
    store = StoreHost(house())
    store._restore_overrides(
        {
            "override_until": {
                zone_id: (now + timedelta(hours=1)).isoformat(),
                "bestaat_niet": (now + timedelta(hours=1)).isoformat(),
                expired_zone: (now - timedelta(hours=1)).isoformat(),
                "geen tijd": "geen datum",
            },
            "override_when_done": {zone_id: "turn_off"},
            "override_entity": {zone_id: "climate.woonkamer"},
        },
        now,
    )

    assert store.zone_overrides[zone_id] is True
    assert store.zone_override_until[zone_id] > now
    assert store.zone_override_when_done[zone_id] == "turn_off"
    assert store.zone_override_entity[zone_id] == "climate.woonkamer"
    assert "bestaat_niet" not in store.zone_override_until
    assert expired_zone not in store.zone_override_until
    assert "geen tijd" not in store.zone_override_until
    assert store.wakes == 1


# -- problemen en teksten -----------------------------------------------------
# -- problems and texts -------------------------------------------------------


def test_a_temperature_placeholder_that_is_no_number_stays() -> None:
    """Een placeholder die geen getal is blijft staan zoals hij is."""
    hass = SimpleNamespace(config=SimpleNamespace(units=None))
    problem = SimpleNamespace(code="target_outside_band", params={"start": "geen getal"})
    assert problems._converted_params(hass, problem)["start"] == "geen getal"
    empty = SimpleNamespace(code="target_outside_band", params={})
    assert problems._converted_params(hass, empty) == {}


async def test_a_text_without_a_template_falls_back() -> None:
    """Een onbekende tekstsleutel levert de terugvaltekst op."""
    from harness_live import start_bare_house

    hass = await start_bare_house()
    try:
        assert texts.translated(hass, "bestaat_niet", "terugval") == "terugval"
    finally:
        await hass.async_stop()


# -- entiteiten en coördinator ------------------------------------------------
# -- entities and coordinator -------------------------------------------------


def test_the_entities_say_nothing_before_the_first_decision() -> None:
    """Zonder plan geven de entiteiten geen waarde en geen attributen."""
    coordinator = SimpleNamespace(data=None)

    blocked = ZoneBlockedSensor.__new__(ZoneBlockedSensor)
    blocked.coordinator = coordinator
    blocked._zone_id = "woonkamer"
    assert blocked.is_on is None
    assert blocked.extra_state_attributes == {}

    fallback = ZoneFallbackSensor.__new__(ZoneFallbackSensor)
    fallback.coordinator = coordinator
    fallback._zone_id = "woonkamer"
    assert fallback.extra_state_attributes == {}

    source = ZoneSourceSensor.__new__(ZoneSourceSensor)
    source.coordinator = coordinator
    source._zone_id = "woonkamer"
    assert source.extra_state_attributes == {}


def test_an_entity_without_a_decision_for_its_zone_says_nothing() -> None:
    """Een plan zonder beslissing voor deze zone laat de entiteit leeg."""
    from custom_components.climate_director.engine import Plan

    coordinator = SimpleNamespace(data=Plan())

    blocked = ZoneBlockedSensor.__new__(ZoneBlockedSensor)
    blocked.coordinator = coordinator
    blocked._zone_id = "onbekend"
    assert blocked.is_on is None
    assert blocked.extra_state_attributes == {}

    fallback = ZoneFallbackSensor.__new__(ZoneFallbackSensor)
    fallback.coordinator = coordinator
    fallback._zone_id = "onbekend"
    assert fallback.extra_state_attributes == {}

    source = ZoneSourceSensor.__new__(ZoneSourceSensor)
    source.coordinator = coordinator
    source._zone_id = "onbekend"
    assert source.extra_state_attributes == {}


def test_openings_are_empty_before_the_first_world() -> None:
    """Zonder wereld is er geen openstaande opening om te melden."""
    coordinator = ClimateDirectorCoordinator.__new__(ClimateDirectorCoordinator)
    coordinator.world = None
    assert coordinator._open_openings("woonkamer", house_wide=True) == []


def test_preconditioning_that_is_switched_off_reports_nothing() -> None:
    """Met een maximum van nul doet een vooruit-verzoek niets, met een logregel."""
    gates = dataclasses.replace(house().gates, max_precondition=timedelta(0))
    config = dataclasses.replace(house(), gates=gates)
    host = _PreconditionsMixin.__new__(_PreconditionsMixin)
    host.config = config
    assert host.async_precondition(["woonkamer"], 30) == {}


def test_a_guest_house_waits_for_the_last_sleeper() -> None:
    """In gastenmodus wacht een huis met iemand thuis op wie nog in bed ligt."""
    from dataclasses import replace
    from datetime import time

    from conftest import asleep, at, awake, gate_verdict

    from custom_components.climate_director.engine import Reason, WakeDeadline
    from custom_components.climate_director.engine.gates import closed

    eleven = WakeDeadline(at=time(11, 0), weekdays=frozenset({5, 6}))
    base = house()
    config = replace(
        base,
        residents=tuple(replace(resident, wake_deadline=eleven) for resident in base.residents),
    )
    world = make_world(
        now=at(10, 0, day=15),
        residents={"danny": awake(), "nancy": asleep()},
        guest_mode=True,
    )
    zone = config.zones[0]
    assert not gate_verdict(config, world, zone).allowed
    assert next(iter(closed(config, world, zone)), None) is Reason.WAITING_FOR_SLEEPER


def test_a_fallback_text_that_cannot_be_filled_comes_back_whole(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Een terugvaltekst met een ontbrekende plaatshouder komt er ook uit."""
    monkeypatch.setattr(texts, "lookup", lambda _hass, _code: None)
    assert texts.translated(object(), "bestaat_niet", "{ontbreekt}") == "{ontbreekt}"


def test_a_field_type_the_settings_table_does_not_know_is_refused() -> None:
    """Een veldtype of maat die de instellingentabel niet kent is een tabel fout."""
    from custom_components.climate_director import schema_fields

    unknown = FieldSpec(key="x", kind="onbekend")
    with pytest.raises(AssertionError, match="onbekend veldtype"):
        schema_fields._selector_for(unknown, SimpleNamespace(hass=None))
    with pytest.raises(AssertionError, match="onbekende maat"):
        schema_fields._stored_number(unknown, 5, "onbekend")
    with pytest.raises(AssertionError, match="onbekend veldtype"):
        schema_fields._stored_value(unknown, {}, {}, "°C")


async def test_an_unreadable_indoor_sensor_is_reported_by_its_state() -> None:
    """Een sensor die niet te lezen is wordt met zijn eigen toestand gemeld."""
    from harness_live import start_house, stop_house
    from test_campaign_editing import cold, two_rooms

    states = {**cold(), "sensor.woonkamer": ("unavailable", {})}
    live = await start_house(two_rooms(), states=states)
    try:
        assert live.coordinator.unusable_entities()["sensor.woonkamer"] == "unavailable"
    finally:
        await stop_house(live)


# -- overnames / takeovers ----------------------------------------------------


def _takeover_house(*, extra_source: bool = False) -> Any:
    """Return two rooms where one appliance also covers the other's room."""
    sources: list[dict[str, Any]] = [
        {"source_id": "airco", "entity_id": "climate.a", "covers_zones": ["zolder"]}
    ]
    if extra_source:
        sources.append({"source_id": "kachel", "entity_id": "climate.c"})
    return serialise.config_from_dict(
        {
            "zones": [
                {
                    "zone_id": "woonkamer",
                    "name": "Woonkamer",
                    "indoor_sensor": "sensor.woonkamer",
                    "sources": sources,
                },
                {
                    "zone_id": "zolder",
                    "name": "Zolder",
                    "indoor_sensor": "sensor.zolder",
                    "sources": [{"source_id": "ketel", "entity_id": "climate.b"}],
                },
            ]
        }
    )


def test_an_area_whose_appliance_is_unreachable_does_not_take_over() -> None:
    """Een onbereikbaar apparaat neemt niets over, al staat zijn gebied er wel."""
    from custom_components.climate_director.engine import takeover

    config = _takeover_house()
    world = make_world(climates={"climate.a": climate("off", available=False)})
    assert takeover.in_force(config, world) == ()


def test_a_taken_area_without_anything_around_keeps_its_commands() -> None:
    """Draait de overnemer alleen, dan valt er niets stil te leggen."""
    from custom_components.climate_director.engine import takeover
    from custom_components.climate_director.engine.plan import UnitCommand
    from custom_components.climate_director.engine.takeover import Takeover

    config = _takeover_house()
    world = make_world()
    takeovers = (
        Takeover("climate.a", frozenset({"woonkamer"}), frozenset({ModeFamily.HEAT})),
        Takeover("climate.b", frozenset({"zolder"}), frozenset({ModeFamily.HEAT})),
    )
    commands = [UnitCommand(entity_id="climate.a", hvac_mode="heat", temperature=21.0)]
    assert takeover.stop_others(config, world, takeovers, commands, []) == commands


def test_a_hand_operated_appliance_in_a_taken_area_is_stood_down() -> None:
    """Een handbediend apparaat in het gebied gaat uit; een onbereikbaar niet."""
    from custom_components.climate_director.engine import Reason, UntouchedSource, takeover
    from custom_components.climate_director.engine.plan import UnitCommand
    from custom_components.climate_director.engine.takeover import Takeover

    config = _takeover_house(extra_source=True)
    world = make_world()
    takeovers = (Takeover("climate.a", frozenset({"woonkamer"}), frozenset({ModeFamily.HEAT})),)
    commands = [UnitCommand(entity_id="climate.a", hvac_mode="heat", temperature=21.0)]
    untouched = [
        UntouchedSource("climate.c", "woonkamer", Reason.MANUAL_SOURCE),
        UntouchedSource("climate.d", "woonkamer", Reason.MANUAL_SOURCE),
    ]
    # `climate.c` is bereikbaar maar staat uit, `climate.d` valt buiten het
    # gebied: geen van beide levert een commando op.
    assert takeover.stop_others(config, world, takeovers, commands, untouched) == commands


def test_an_unreadable_strings_file_yields_no_english_templates(monkeypatch) -> None:
    """texts.py: een onleesbaar `strings.json` geeft een lege terugval, geen fout.

    texts.py: an unreadable `strings.json` yields an empty fallback, not an error.
    """
    from pathlib import Path

    def refuse(_self, *_args, **_kwargs) -> str:
        raise OSError("onleesbaar")

    monkeypatch.setattr(Path, "read_text", refuse)
    assert texts._read_english_templates() == {}


# -- de laatste zes uitgesloten regels ----------------------------------------
# -- the last six excluded lines ---------------------------------------------


class TestTheLastSixExcludedLines:
    """De zes regels die ronde 31 nog met een pragma afving (ronde 32, R32-1).

    The six lines round 31 still caught with a pragma (round 32, R32-1).

    Alle zes stonden met de reden "onbereikbaar in een test" in de bron, en alle
    zes zijn met een monkeypatch, een stand-in of een rechtstreekse aanroep te
    bereiken — precies de techniek die `4a5b9e8` voor de vijf eerdere pragma's
    gebruikte. Ze verliezen daarom hun `# pragma: no cover`: de bewaking is dat
    ze gedekt zijn, niet dat ze uitgesloten zijn.

    All six stood in the source with the reason "unreachable in a test", and all
    six can be reached with a monkeypatch, a stand-in or a direct call — exactly
    the technique `4a5b9e8` used for the five earlier pragmas. They therefore
    lose their `# pragma: no cover`: the guard is that they are covered, not
    that they are excluded.
    """

    async def test_a_failing_apply_is_logged_and_the_round_goes_on(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """coordinator.py: een ronde waarin `apply` gooit wordt gemeld en gaat door."""
        from harness_live import start_house, stop_house
        from test_campaign_editing import cold, two_rooms

        from custom_components.climate_director import coordinator as coordinator_module

        logged: list[str] = []
        monkeypatch.setattr(
            coordinator_module._LOGGER,
            "exception",
            lambda message, *args: logged.append(message % args),
        )

        async def refuse(*_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("kapot")

        monkeypatch.setattr(coordinator_module, "apply", refuse)

        live = await start_house(two_rooms(), states=cold())
        try:
            await live.evaluate()
            assert live.coordinator.last_changes, "deze ronde hoort iets te willen sturen"
            assert logged, "een mislukte `apply` hoort gemeld te worden"
            assert "Applying the climate plan failed" in logged[0]
            assert live.coordinator.last_applied == ()
            assert live.coordinator.data is not None, "de ronde hoort gewoon door te gaan"
        finally:
            await stop_house(live)

    def test_a_configured_sensor_that_is_not_tracked_is_skipped(self) -> None:
        """coordinator.py: een geconfigureerde sensor die niet gevolgd wordt."""
        config = dataclasses.replace(house(), outdoor_sensor="sensor.buiten")
        coordinator = SimpleNamespace(
            config=config,
            hass=SimpleNamespace(states=SimpleNamespace(get=lambda _entity_id: None)),
            tracked_entities=lambda: set(),
        )
        assert ClimateDirectorCoordinator.unusable_entities(coordinator) == {}

    def test_a_guest_window_that_is_no_mapping_is_dropped(self) -> None:
        """serialise.py: een gastenvenster dat geen mapping is bestaat niet."""
        assert serialise._guest_window("x") is None

    def test_an_override_without_a_source_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """overrides.py: zonder bron weigert de override en meldt dat."""
        host = OverrideHost(house())
        monkeypatch.setattr(host, "override_source", lambda *_args, **_kwargs: None)
        assert host.async_set_override("woonkamer", "heat", 21.0, 60, "turn_off") is False

    def test_an_override_that_expired_between_two_readings_waits_for_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """overrides.py: de tweede kloklezing valt ná `until`, dus niets in te plannen."""
        now = dt_util.utcnow()
        readings = iter([now, now + timedelta(hours=2)])
        monkeypatch.setattr(dt_util, "now", lambda: next(readings))

        host = OverrideHost(house())
        zone_id = house().zones[0].zone_id
        host.zone_overrides[zone_id] = True
        host.zone_override_until[zone_id] = now + timedelta(hours=1)
        host._override_wake_at_first_expiry()
        assert host._cancel_override_wake is None

    def test_the_base_switch_refuses_to_push(self) -> None:
        """switch.py: de basis van de schakelaars is abstract en zegt dat."""
        switch = _DirectorSwitch.__new__(_DirectorSwitch)
        with pytest.raises(NotImplementedError):
            switch._push()


def test_nothing_is_hidden_from_the_measurement() -> None:
    """Het pakket draagt geen enkele `pragma: no cover` meer (ronde 32, R32-1).

    De dekkingspoort (`script/coverage_gate.py`) kan alleen zien wat coverage
    meekrijgt: een `pragma: no cover` haalt een regel uit de meting, en dan zegt
    "nul gemiste regels" niets meer over die regel. Daarom is de eigenschap die
    hier vastligt: het pakket sluit geen enkele regel uit. Wie er ooit een nodig
    heeft, past deze test aan met de reden erbij — en dat is dan een bewuste
    beslissing in plaats van een stilzwijgende uitsluiting.

    The coverage gate (`script/coverage_gate.py`) can only see what coverage is
    given: a `pragma: no cover` takes a line out of the measurement, and then
    "zero missed lines" no longer says anything about that line. Hence the
    property pinned here: the package excludes no line at all. Whoever needs one
    someday edits this test and adds the reason — making it a deliberate
    decision instead of a silent exclusion.
    """
    offenders = [
        f"{path.relative_to(PACKAGE)}:{number}: {line.strip()}"
        for path in sorted(PACKAGE.rglob("*.py"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if "pragma: no cover" in line
    ]
    assert not offenders, (
        "deze regels zijn uit de dekkingsmeting gehouden in plaats van gemeten: "
        + ", ".join(offenders)
    )


def test_every_line_outside_the_measurement_has_a_name() -> None:
    """Elke regel die buiten de meting valt heeft een naam (ronde 34, R34-2).

    De poort (`script/coverage_gate.py`) kan alleen zien wat coverage meekrijgt,
    en coverage houdt drie soorten regels buiten de telling op een patroon. Een
    patroon verbergt stil, en daarom noemt de poort elke regel met naam en
    toenaam in `NAMED_EXCLUSIONS`. Deze test eist dat die lijst **precies** klopt
    met wat de meting overslaat: geen regel zonder naam, geen naam zonder regel.

    De meting heeft daar geen gegevensbestand voor nodig — wat coverage uitsluit
    hangt aan het bestand en het patroon, niet aan wat er gedraaid is. Zonder
    enige uitsluiting zou deze test niets meten, en dat is dan ook een fout.

    Ronde 36 (R36-4): die meting krijgt `data_file=None` mee, en dat is geen
    detail. `Coverage()` zonder dat argument wijst naar het standaardbestand
    `.coverage`, en `hidden_lines()` roept `analysis2()` aan; gemeten liet dat het
    bestaande `.coverage` leeg achter (39 → 0 gemeten bestanden), waarna
    `coverage report` en de poort "de meting is leeg" meldden. `Coverage` zelf
    beschrijft `data_file=None` als "geen gegevensbestand": dan wordt er niets
    gelezen en niets geschreven. Een test hoort de meting waar hij naast staat
    niet aan te raken; `test_the_guards_themselves.py` pint dat met een verzonnen
    meetbestand vast.

    Every line that falls outside the measurement has a name (round 34, R34-2).
    The gate (`script/coverage_gate.py`) can only see what coverage is given, and
    coverage keeps three kinds of lines out of the count on a pattern. A pattern
    hides silently, so the gate names every line in `NAMED_EXCLUSIONS`. This test
    demands that the list matches **exactly** what the measurement skips: no line
    without a name, no name without a line.

    That measurement needs no data file — what coverage excludes hangs on the file
    and the pattern, not on what ran. Without any exclusion this test would
    measure nothing, and that too is an error.

    Round 36 (R36-4): that measurement takes `data_file=None`, and that is no
    detail. `Coverage()` without that argument points at the default
    `.coverage`, and `hidden_lines()` calls `analysis2()`; measured, that left
    the existing `.coverage` empty (39 → 0 measured files), after which
    `coverage report` and the gate said "the measurement is empty". `Coverage`
    itself describes `data_file=None` as "no data file at all": then nothing is
    read and nothing is written. A test should not touch the measurement next to
    it; `test_the_guards_themselves.py` pins that down with an invented
    measurement.
    """
    hidden = coverage_gate.hidden_lines(Coverage(data_file=None), PACKAGE)
    assert hidden, "de meting sluit geen enkele regel uit, dus deze test meet niets"
    assert coverage_gate.exclusion_problems(hidden, PACKAGE) == []


#: Het aantal benoemde uitsluitingen van de poort. De whitelist mag alleen korter
#: worden: elke regel die erbij komt is een regel die de meting niet meer dekt, en
#: zonder deze ratel groeit dat stil door. Het getal is gemeten op `c3e7957` +
#: ronde 35 (R35-5): negen statements in `coordinator.py` en drie in elk van de
#: vier mixins die het protocol onder `TYPE_CHECKING` importeren.
#:
#: The number of named exclusions of the gate. The whitelist may only get shorter:
#: every line added to it is a line the measurement no longer covers, and without
#: this ratchet that grows silently. The number was measured on `c3e7957` + round
#: 35 (R35-5): nine statements in `coordinator.py` and three in each of the four
#: mixins that import the protocol under `TYPE_CHECKING`.
NAMED_EXCLUSIONS_BUDGET = 21


def test_the_named_exclusions_are_a_ratchet() -> None:
    """Het aantal benoemde uitsluitingen mag alleen dalen (ronde 35, R35-4).

    De whitelist is er voor regels die de meting niet kán meenemen; elke regel die
    erbij komt is er één die de meting niet meer dekt. Zonder deze ratel groeit dat
    stil door — gemeten in ronde 34: een nieuwe dode stub plus zijn naam in
    `NAMED_EXCLUSIONS` liet de hele suite én de poort groen, terwijl de maat in
    `test_the_measure.py` alleen de modulegrootte zag. Wordt het getal groter, dan
    is deze test rood en somt hij de huidige inhoud op (met de nieuwe naam erbij);
    wordt het kleiner, dan is hij óók rood met de vraag het getal te verlagen. Zo
    kan de whitelist alleen korter worden.

    The number of named exclusions may only go down (round 35, R35-4). The
    whitelist exists for lines the measurement cannot include; every line added to
    it is one the measurement no longer covers. Without this ratchet that grows
    silently — measured in round 34: a new dead stub plus its name in
    `NAMED_EXCLUSIONS` left the whole suite and the gate green, while the measure
    in `test_the_measure.py` only saw the module size. When the number grows, this
    test is red and lists the current content (with the new name in it); when it
    shrinks, it is red too, asking for the number to be lowered. That way the
    whitelist can only get shorter.
    """
    counted = sum(len(entries) for entries in coverage_gate.NAMED_EXCLUSIONS.values())
    if counted == NAMED_EXCLUSIONS_BUDGET:
        return
    listed = "; ".join(
        f"{name}: {', '.join(entries)}"
        for name, entries in sorted(coverage_gate.NAMED_EXCLUSIONS.items())
    )
    if counted > NAMED_EXCLUSIONS_BUDGET:
        raise AssertionError(
            f"de whitelist van de poort is gegroeid: {counted} benoemde uitsluitingen, "
            f"genoteerd {NAMED_EXCLUSIONS_BUDGET}. Elke regel erbij is een regel die de "
            f"meting niet meer dekt; haal hem eruit of verantwoord hem. Nu: {listed}"
        )
    raise AssertionError(
        f"de whitelist van de poort is korter geworden: {counted}, genoteerd "
        f"{NAMED_EXCLUSIONS_BUDGET}. Zet het nieuwe getal erin (lager mag altijd). Nu: {listed}"
    )
