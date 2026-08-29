"""Gedeelde bouwstenen voor de engine-tests.

Shared building blocks for the engine tests.

De engine importeert geen Home Assistant, dus hier is geen `hass`-fixture
nodig: elk scenario is een gewoon dataobject.

The engine imports no Home Assistant, so no `hass` fixture is needed here:
every scenario is a plain data object.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

import pytest

from custom_components.climate_director.engine import (
    Circuit,
    ClimateState,
    DirectorConfig,
    GateSettings,
    ModeSettings,
    Opening,
    OpeningState,
    OutdoorWindow,
    PresenceState,
    Resident,
    ResidentState,
    Season,
    Source,
    SourceRole,
    TimeWindow,
    WorldState,
    Zone,
    gates,
)
from custom_components.climate_director.engine.plan import Reason

# Entiteiten uit de bestaande opstelling, zodat scenario's herkenbaar blijven.
# Entities from the existing setup, so scenarios stay recognisable.
GAS = "climate.smart_thermostat_x"
LIVING = "climate.huiskamer"
ATTIC = "climate.zolder"
BEDROOM = "climate.master_bedroom"
BACK_DOOR = "binary_sensor.achterdeur_mc_contact"

MONDAY_NOON = datetime(2026, 8, 10, 12, 0)

#: (module, step_id) van elk formulier dat de suite werkelijk getekend heeft.
#: Sessieduur: de autouse-fixture `every_drawn_form_must_serialize` vult deze
#: verzameling, niemand maakt hem leeg. `pytest_sessionfinish` hieronder houdt
#: hem aan het eind van de run tegen de bron.
#:
#: (module, step_id) of every form the suite really drew. Session-lifetime:
#: the autouse fixture `every_drawn_form_must_serialize` fills this set, nobody
#: empties it. `pytest_sessionfinish` below holds it against the source at the
#: end of the run.
DRAWN_FORMS: set[tuple[str, str]] = set()

#: Welke `tests/test_*.py` pytest deze sessie werkelijk geprobeerd heeft te
#: verzamelen. `pytest_collectreport` vult deze verzameling per modulebestand;
#: samen met `session.items` maakt dat zichtbaar of een bestand zonder ook maar
#: één test de bewaking hieronder stilletjes zou uitzetten (dat hoort een fout
#: te zijn, geen skip).
#:
#: Which `tests/test_*.py` pytest actually tried to collect this session.
#: `pytest_collectreport` fills this set per module file; together with
#: `session.items` it makes visible whether a file without a single test would
#: silently disarm the guard below (that should be an error, not a skip).
ATTEMPTED_TEST_FILES: set[str] = set()


@dataclass(frozen=True, slots=True)
class Verdict:
    """Mag deze zone geregeld worden, en zo niet: welke poort noem je dan.

    May this zone be regulated, and if not: which gate do you name.

    Testgereedschap, geen engine. De engine geeft de hele lijst dichte poorten
    terug, want bij het inrichten wil je ze allemaal zien; deze samenvatting is
    wat de tests hieronder prettig leest. Hij stond ooit in de engine zelf en
    werd daar door niets gebruikt.

    Test tooling, not engine. The engine returns the whole list of shut gates,
    since while setting things up you want to see them all; this summary is what
    reads pleasantly in the tests below. It used to live in the engine itself,
    where nothing used it.
    """

    allowed: bool
    reason: Reason | None = None


def gate_verdict(config, world, zone, previous=None) -> Verdict:
    """Return whether `zone` may run, naming the gate a user would name first."""
    reason = next(iter(gates.closed(config, world, zone, previous)), None)
    return Verdict(reason is None, reason)


def at(hour: int = 12, minute: int = 0, *, day: int = 10) -> datetime:
    """Return a moment in August 2026; the 10th is a Monday."""
    return datetime(2026, 8, day, hour, minute)


def climate(
    mode: str = "off",
    *,
    available: bool = True,
    changed_at: datetime | None = None,
    target: float | None = None,
) -> ClimateState:
    """Return a climate entity state without spelling out every field."""
    return ClimateState(
        hvac_mode=mode,
        available=available,
        changed_at=changed_at,
        target_temperature=target,
    )


def make_world(
    *,
    now: datetime | None = None,
    outdoor: float | None = None,
    season: Season = Season.UNKNOWN,
    indoor: dict[str, float | None] | None = None,
    climates: dict[str, ClimateState | str] | None = None,
    residents: dict[str, ResidentState] | None = None,
    openings: dict[str, OpeningState] | None = None,
    presence: dict[str, PresenceState] | None = None,
    circuit_family_since: dict[str, datetime | None] | None = None,
    master_enabled: bool = True,
    holiday_mode: bool = False,
    guest_mode: bool = False,
    precondition_until: dict[str, datetime] | None = None,
    precondition_bypass: frozenset[str] = frozenset(),
    zone_overrides: dict[str, bool] | None = None,
    zone_priorities: dict[str, int] | None = None,
    precipitation: bool = False,
) -> WorldState:
    """Return a `WorldState`, accepting bare mode strings for climate entities."""
    resolved = {
        entity_id: climate(state) if isinstance(state, str) else state
        for entity_id, state in (climates or {}).items()
    }
    return WorldState(
        now=now or MONDAY_NOON,
        outdoor_temperature=outdoor,
        season=season,
        indoor_temperatures=dict(indoor or {}),
        climates=resolved,
        residents=dict(residents or {}),
        openings=dict(openings or {}),
        presence=dict(presence or {}),
        circuit_family_since=dict(circuit_family_since or {}),
        master_enabled=master_enabled,
        holiday_mode=holiday_mode,
        guest_mode=guest_mode,
        precondition_until=dict(precondition_until or {}),
        precondition_bypass=precondition_bypass,
        zone_overrides=dict(zone_overrides or {}),
        zone_priorities=dict(zone_priorities or {}),
        precipitation=precipitation,
    )


def awake(home: bool = True) -> ResidentState:
    """Return a resident who is up."""
    return ResidentState(home=home, asleep=False)


def asleep(home: bool = True) -> ResidentState:
    """Return a resident who is in bed."""
    return ResidentState(home=home, asleep=True)


def away() -> ResidentState:
    """Return a resident who is out."""
    return ResidentState(home=False, asleep=False)


def everyone_up() -> dict[str, ResidentState]:
    """Return both residents home and awake."""
    return {"danny": awake(), "nancy": awake()}


# ---------------------------------------------------------------------------
# De bestaande opstelling: systeem A uit de ontwerpgesprekken.
# The existing setup: system A from the design discussions.
# ---------------------------------------------------------------------------

#: Drempel waarboven de warmtepomp de gasketel vervangt (input_number.gasverwarming_aan).
GAS_CUTOVER = 3.0

#: Buiten warmer dan dit en verwarmen heeft geen zin
#: (input_number.maximum_buiten_temperatuur_verwarmen_airco).
HEAT_OUTDOOR_MAX = 19.0

#: Buiten kouder dan dit en koelen heeft geen zin
#: (input_number.minimum_buiten_temperatuur_koelen_airco).
COOL_OUTDOOR_MIN = 24.0


def living_room_heat() -> ModeSettings:
    """Return the living room's heating settings.

    `start_at` 22 with a 1.0 band reproduces the summer branch of the original
    automations exactly (on at 22 or below, off at 23 or above) and gives the
    winter branch the dead band it was missing - there, on and off both sat at
    23 and the zone could chatter on that single value.
    """
    return ModeSettings(
        target=23.0,
        start_at=22.0,
        hysteresis=1.0,
        outdoor=OutdoorWindow(maximum=HEAT_OUTDOOR_MAX),
    )


def living_room_cool() -> ModeSettings:
    """Return the living room's cooling settings, summer only."""
    return ModeSettings(
        target=23.0,
        start_at=24.0,
        hysteresis=1.0,
        outdoor=OutdoorWindow(minimum=COOL_OUTDOOR_MIN),
        seasons=frozenset({Season.SUMMER}),
    )


def house() -> DirectorConfig:
    """Return the existing installation: one multi-split plus a gas boiler.

    The boiler sits on no circuit, so it has an outdoor unit to itself by
    definition. The three indoor units share one, and therefore one duty.

    Every heat-pump source carries the same outdoor cutover as the living
    room's. That is what keeps the boiler and the heat pump apart house-wide:
    below the cutover no indoor unit is eligible at all, so the combination the
    old safety automation watched for cannot be assembled.
    """
    living = Zone(
        zone_id="woonkamer",
        name="Woonkamer",
        indoor_sensor="sensor.temperatuur_sensor_woonkamer_selectie",
        priority=0,
        sources=(
            Source(
                source_id="woonkamer_airco",
                entity_id=LIVING,
                role=SourceRole.HEAT_COOL,
                outdoor=OutdoorWindow(minimum=GAS_CUTOVER),
            ),
            Source(
                source_id="gasketel",
                entity_id=GAS,
                role=SourceRole.HEAT_ONLY,
                outdoor=OutdoorWindow(maximum=GAS_CUTOVER),
            ),
        ),
        heat=living_room_heat(),
        cool=living_room_cool(),
    )
    attic = Zone(
        zone_id="zolder",
        name="Zolder",
        indoor_sensor="sensor.zolder_temperatuur",
        priority=1,
        sources=(
            Source(
                source_id="zolder_airco",
                entity_id=ATTIC,
                outdoor=OutdoorWindow(minimum=GAS_CUTOVER),
            ),
        ),
        heat=living_room_heat(),
        cool=living_room_cool(),
    )
    bedroom = Zone(
        zone_id="slaapkamer",
        name="Slaapkamer",
        indoor_sensor="sensor.slaapkamer_temperatuur",
        priority=2,
        sources=(
            Source(
                source_id="slaapkamer_airco",
                entity_id=BEDROOM,
                outdoor=OutdoorWindow(minimum=GAS_CUTOVER),
            ),
        ),
        heat=living_room_heat(),
        cool=living_room_cool(),
    )
    return DirectorConfig(
        zones=(living, attic, bedroom),
        circuits=(
            Circuit(
                circuit_id="multisplit",
                name="Multi-split",
                units=(LIVING, ATTIC, BEDROOM),
                simultaneous_heat_cool=False,
                family_switch_delay=timedelta(seconds=5),
            ),
        ),
        residents=(
            # De entiteiten waar de koppelingslaag ze mee uitleest. De engine
            # raakt ze nooit aan, maar zonder aanwezigheidsentiteit kan een
            # bewoner nooit thuis zijn, en daar klaagt `validate()` terecht over.
            #
            # The entities the binding layer reads them with. The engine never
            # touches them, but without a presence entity a resident can never
            # be home, which `validate()` rightly complains about.
            Resident(
                resident_id="danny",
                name="Danny",
                presence_entity="person.danny",
                sleep_entity="sensor.danny_charger_type",
                sleep_state="wireless",
            ),
            Resident(
                resident_id="nancy",
                name="Nancy",
                presence_entity="person.nancy",
                sleep_entity="sensor.nancy_charger_type",
                sleep_state="wireless",
            ),
        ),
        openings=(Opening(entity_id=BACK_DOOR, delay=timedelta(seconds=30)),),
        gates=GateSettings(require_awake=True),
        # De engine leest deze entiteit nooit zelf - de koppelingslaag doet dat
        # en zet het resultaat in `WorldState`. Hij hoort hier omdat elk
        # begrensd buitenvenster in deze opstelling zonder buitentemperatuur
        # nooit voldaan kan worden, en `validate()` daar terecht over klaagt.
        #
        # The engine never reads this entity itself - the binding layer does and
        # puts the result in `WorldState`. It belongs here because every bounded
        # outdoor window in this setup can never be satisfied without an outdoor
        # temperature, which `validate()` rightly complains about.
        outdoor_sensor="sensor.buienradar_temperature",
    )


@pytest.fixture
def config() -> DirectorConfig:
    """Return the existing installation as a fixture."""
    return house()


@pytest.fixture(autouse=True)
def every_drawn_form_must_serialize(monkeypatch: pytest.MonkeyPatch) -> None:
    """Haal élk formulier dat de suite tekent door de frontend-omzetter.

    Home Assistant tekent een formulier pas nadat
    `FlowManagerView._prepare_result_json` het schema door
    `voluptuous_serialize.convert(schema, custom_serializer=cv.custom_serializer)`
    heeft gehaald. Deze fixture onderschept `FlowHandler.async_show_form` en
    doet diezelfde omzetting op élk formulierresultaat — de wizard, het
    bewaarscherm en elke foutherhaling inbegrepen. De omzetting geldt alleen voor
    flows van deze integratie, zodat een vreemde flow in de testomgeving dit
    project niet rood kan zetten. Zo is élk scherm van deze integratie dat de
    suite ergens tekent aantoonbaar te tekenen.

    De dekking volgt daarmee wat de tests toevallig aandoen; deze fixture
    bewaakt dus de getekende schermen, foutherhalingen en tussenschermen die een
    expliciete doorloop mist. Dat élk scherm uit de bron ook een doorloop heeft,
    bewaakt `TestEveryFormInTheSourceIsWalkedTo` in
    `tests/test_campaign_editing.py` — samen bewaken ze twee verschillende
    dingen, niet dezelfde invariant twee keer.

    Push every form the suite draws through the frontend converter.

    Home Assistant only draws a form after `FlowManagerView._prepare_result_json`
    has pushed the schema through `voluptuous_serialize.convert(schema,
    custom_serializer=cv.custom_serializer)`. This fixture intercepts
    `FlowHandler.async_show_form` and does that same conversion on every form
    result — the wizard, the save screen and every error re-display included.
    The conversion applies only to flows of this integration, so a foreign flow
    in the test environment cannot turn this project red. Every screen of this
    integration the suite draws somewhere is thereby provably drawable.

    Its coverage follows whatever the tests happen to touch; this fixture
    guards the drawn screens, error re-displays and intermediate screens an
    explicit walk misses. That every screen from the source also has a walk is
    guarded by `TestEveryFormInTheSourceIsWalkedTo` in
    `tests/test_campaign_editing.py` — together they guard two different
    things, not the same invariant twice.
    """
    import voluptuous_serialize
    from homeassistant.data_entry_flow import FlowHandler, FlowResultType
    from homeassistant.helpers import config_validation as cv

    original = FlowHandler.async_show_form

    def checked(self, **kwargs):
        result = original(self, **kwargs)
        module = type(self).__module__
        if module == "custom_components.climate_director" or module.startswith(
            "custom_components.climate_director."
        ):
            result_type = result.get("type")
            if result_type == FlowResultType.FORM:
                DRAWN_FORMS.add((module, result.get("step_id")))
            schema = result.get("data_schema") if result_type == FlowResultType.FORM else None
            if schema is not None:
                voluptuous_serialize.convert(schema, custom_serializer=cv.custom_serializer)
        return result

    monkeypatch.setattr(FlowHandler, "async_show_form", checked)


def _module_of(root, path) -> str:
    """Return the dotted module name of one integration source file."""
    parts = list(path.relative_to(root).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return "custom_components.climate_director" + (f".{'.'.join(parts)}" if parts else "")


def async_show_form_calls() -> list[tuple[str, str | None, object | None]]:
    """Return every `async_show_form(step_id=...)` call in the integration source.

    `(module, step_id, data_schema)` — `step_id` is `None` when it is not a
    literal, `data_schema` is the AST node or `None` when the call carries none.
    De loop gaat over álle `*.py` onder `custom_components/climate_director/`,
    ongeacht of er een `data_schema=` bij staat en ongeacht of de aanroep
    `self.`-gebonden is.

    `(module, step_id, data_schema)` — `step_id` is `None` when it is not a
    literal, `data_schema` is the AST node or `None` when the call carries none.
    The walk covers every `*.py` under `custom_components/climate_director/`,
    whether or not a `data_schema=` is present and whether or not the call is
    bound to `self.`.
    """
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "custom_components" / "climate_director"
    found: list[tuple[str, str | None, object | None]] = []
    for path in sorted(root.rglob("*.py")):
        module = _module_of(root, path)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "async_show_form":
                continue
            step_id: str | None = None
            schema: object | None = None
            for keyword in node.keywords:
                if keyword.arg == "step_id" and isinstance(keyword.value, ast.Constant):
                    step_id = keyword.value.value
                if keyword.arg == "data_schema":
                    schema = keyword.value
            found.append((module, step_id, schema))
    return found


def integration_forms() -> set[tuple[str, str]]:
    """Return every `(module, step_id)` the integration can draw, from the AST."""
    return {
        (module, step_id)
        for module, step_id, _schema in async_show_form_calls()
        if step_id is not None
    }


def fixable_issue_keys() -> set[str]:
    """Return every `translation_key` whose `async_create_issue` is fixable.

    Uit `problems.py`, met een AST: de bron, geen handkaart. Een
    `is_fixable=True` waarvan de `translation_key` geen letterlijke string is,
    valt niet stilzwijgend uit de inventarisatie — dat is een duidelijke fout,
    want dan is de bewaking blind voor precies die melding.

    From `problems.py`, with an AST: the source, not a hand-kept map. An
    `is_fixable=True` whose `translation_key` is not a literal string does not
    silently drop out of the inventory — it is a clear error, since the guard
    would then be blind to exactly that notice.
    """
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "custom_components" / "climate_director"
    source = (root / "problems.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    found: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "async_create_issue":
            continue
        keywords = {keyword.arg: keyword.value for keyword in node.keywords}
        fixable = keywords.get("is_fixable")
        if not (isinstance(fixable, ast.Constant) and fixable.value is True):
            continue
        key = keywords.get("translation_key")
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            found.add(key.value)
        else:
            raise AssertionError(
                f"problems.py:{node.lineno}: is_fixable=True maar de "
                "translation_key is geen letterlijke string"
            )
    return found


def fix_flow_steps() -> set[str]:
    """Return every `step_id` a repairs fix-flow can draw, from the whole tree.

    De loop gaat over álle `*.py` onder `custom_components/climate_director/`
    en filtert op de klasse in plaats van op een bestandsnaam: élke klasse die
    van `RepairsFlow` erft, draagt bij met zijn
    `async_show_form(step_id=...)`-aanroepen. Een tweede fix-flow in een nieuw
    bestand doet dus vanzelf mee.

    The walk covers every `*.py` under `custom_components/climate_director/`
    and filters on the class rather than on a filename: every class inheriting
    `RepairsFlow` contributes its `async_show_form(step_id=...)` calls. A
    second fix flow in a new file therefore joins in by itself.
    """
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "custom_components" / "climate_director"
    found: set[str] = set()
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if not any(
                isinstance(base, ast.Name) and base.id == "RepairsFlow" for base in node.bases
            ):
                continue
            for method in node.body:
                if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for sub in ast.walk(method):
                    if (
                        isinstance(sub, ast.Call)
                        and isinstance(sub.func, ast.Attribute)
                        and sub.func.attr == "async_show_form"
                    ):
                        for keyword in sub.keywords:
                            if keyword.arg == "step_id" and isinstance(keyword.value, ast.Constant):
                                found.add(keyword.value.value)
    return found


def coverage_skip_reason(session: pytest.Session) -> str | None:
    """Return why the coverage guard must stand down, or `None` when it may run.

    De dekkingsbewaking is per definitie selectiegevoelig: een gedeeltelijke run
    tekent niet elk formulier, en dan zou de bewaking vals rood staan. De
    bewaking staat daarom alleen aan wanneer de run compleet is — geen
    `-k`/`-m`/`--lf`/`--deselect`, en pytest heeft werkelijk élk
    `tests/test_*.py` geprobeerd te verzamelen. Of een verzameld bestand ook
    minstens één test opgeleverd heeft, is hier bewust géén skipreden: een leeg
    testbestand hoort de bewaking niet uit te zetten, het hoort zelf een fout te
    zijn — dat doet `pytest_sessionfinish`.

    The coverage guard is by definition selection-sensitive: a partial run does
    not draw every form, and the guard would then stand falsely red. The guard
    therefore only runs when the run is complete — no
    `-k`/`-m`/`--lf`/`--deselect`, and pytest really tried to collect every
    `tests/test_*.py`. Whether a collected file also yielded at least one test
    is deliberately no skip reason here: an empty test file should not disarm
    the guard, it should itself be an error — that is what
    `pytest_sessionfinish` does.
    """
    from pathlib import Path

    if session.config.option.keyword:
        return "er is een `-k`-filter gezet"
    if session.config.option.markexpr:
        return "er is een `-m`-filter gezet"
    if getattr(session.config.option, "lf", False):
        return "`--lf` draait alleen de laatst gefaalde tests"
    if getattr(session.config.option, "deselect", None):
        return "er is een `--deselect`-filter gezet"
    if getattr(session.config.option, "collectonly", False):
        return "`--collect-only` verzamelt alleen en tekent geen formulier"
    tests_dir = Path(__file__).resolve().parent
    expected = {path.name for path in tests_dir.glob("test_*.py")}
    if expected != ATTEMPTED_TEST_FILES:
        return (
            f"de run is niet compleet: {len(ATTEMPTED_TEST_FILES)} van de "
            f"{len(expected)} testbestanden verzameld"
        )
    return None


def pytest_collectreport(report) -> None:
    """Onthoud welke `tests/test_*.py` pytest werkelijk probeert te verzamelen.

    Deze verzameling is de tegenhanger van `session.items`: een bestand dat
    pytest wél bezoekt maar dat geen enkel item oplevert — een leeg bestand, een
    module-level skip, een bestand waarvan de laatste test net verwijderd is —
    staat wél in `ATTEMPTED_TEST_FILES` maar niet tussen de verzamelde items.
    Zonder dit onderscheid zou zo'n bestand de dekkingsbewaking stilletjes op
    skip zetten; nu wordt het in `pytest_sessionfinish` een fout.

    Remember which `tests/test_*.py` pytest really tried to collect.

    This set is the counterpart of `session.items`: a file pytest does visit but
    that yields no item at all — an empty file, a module-level skip, a file
    whose last test was just removed — is in `ATTEMPTED_TEST_FILES` but not
    among the collected items. Without that distinction such a file would
    silently put the coverage guard on skip; now it becomes an error in
    `pytest_sessionfinish`.
    """
    from pathlib import Path

    path = getattr(report, "fspath", None)
    if path is None:
        return
    name = Path(path).name
    if name.startswith("test_") and name.endswith(".py"):
        ATTEMPTED_TEST_FILES.add(name)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Velt het dekkings-oordeel aan het eind van de run, niet als test.

    Deze bewaking stond ooit in `tests/test_zz_coverage.py`, een test die op de
    bestandsnaam vertrouwde om als laatste te draaien. Een ordeningsplugin die
    de itemlijst omdraait zette hem daardoor vals rood; een leeg testbestand
    zette hem stilletjes op skip. Daarom is het nu deze hook: die draait per
    constructie als laatste, dus de volgorde van de items doet er niet meer toe,
    en een bestand zonder items is zelf een fout in plaats van een skip.

    Bewust geaccepteerd gevolg: de dekkingsbewaking is géén test meer. Hij telt
    niet mee in de suitetelling (2355 → 2354) en is niet met `-k` te draaien.
    Zoek dus geen `test_zz_coverage.py`; de bewaking staat hier, en een
    gedeeltelijke run meldt hieronder zichtbaar dat hij overgeslagen is.

    Passes the coverage verdict at the end of the run, not as a test.

    This guard used to live in `tests/test_zz_coverage.py`, a test that relied
    on its filename to run last. An ordering plugin that reverses the item list
    made it falsely red; an empty test file silently put it on skip. Hence it is
    now this hook: it runs last by construction, so item order no longer
    matters, and a file without items is itself an error rather than a skip.

    Deliberately accepted consequence: the coverage guard is no longer a test.
    It does not count in the suite total (2355 → 2354) and cannot be run with
    `-k`. So do not look for `test_zz_coverage.py`; the guard lives here, and a
    partial run visibly reports below that it stood down.
    """
    from pathlib import Path

    reporter = session.config.pluginmanager.get_plugin("terminalreporter")

    reason = coverage_skip_reason(session)
    if reason is not None:
        if reporter is not None:
            reporter.write_line(
                f"SKIPPED: de dekkingsbewaking (pytest_sessionfinish) is overgeslagen: {reason}"
            )
        return

    collected = {Path(item.path).name for item in session.items}
    empty = sorted(ATTEMPTED_TEST_FILES - collected)
    if empty:
        names = ", ".join(empty)
        if reporter is not None:
            reporter.write_line(f"FAILED: deze testbestanden leveren geen enkele test op: {names}")
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
        return

    missing = integration_forms() - DRAWN_FORMS
    if missing:
        names = sorted(name for _module, name in missing)
        if reporter is not None:
            reporter.write_line(
                f"FAILED: deze formulieren uit de bron zijn door geen enkele test getekend: {names}"
            )
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def office_hours() -> tuple:
    """Return a weekday 08:00-18:00 schedule window."""

    return (TimeWindow(time(8, 0), time(18, 0), frozenset({0, 1, 2, 3, 4})),)


# ---------------------------------------------------------------------------
# De beloftes die elk plan moet houden, welke installatie er ook onder ligt.
# The promises every plan must keep, whatever installation lies under it.
# ---------------------------------------------------------------------------


def assert_plan_holds(config, world, plan, where: str = "") -> None:
    """Assert what may never come out of `decide()`, for any configuration.

    Bedoeld voor de brede tests die duizenden willekeurige installaties en een
    hele maand doorlopen: die kunnen niet per geval een verwachting opschrijven,
    dus leggen ze vast wat er nooit uit mag komen. Wat hier stukloopt, loopt bij
    een gebruiker stuk terwijl het huis koud staat.

    Meant for the broad tests that walk thousands of random installations and a
    whole month: those cannot write down an expectation per case, so they pin
    down what may never come out. What breaks here breaks for a user while the
    house sits cold.
    """
    from custom_components.climate_director.engine import ModeFamily
    from custom_components.climate_director.engine.families import family_of

    mark = f"{where}: " if where else ""

    steered = [command.entity_id for command in plan.commands]
    assert len(steered) == len(set(steered)), f"{mark}twee opdrachten voor een apparaat"

    known = {source.entity_id for _, source in config.sources() if source.entity_id}
    known |= {item.entity_id for item in config.generators if item.entity_id}
    assert set(steered) <= known, f"{mark}opdracht naar een onbekend apparaat"

    assert len(plan.zones) == len(config.zones), f"{mark}niet elke zone kreeg een besluit"
    assert len({zone.zone_id for zone in plan.zones}) == len(plan.zones), (
        f"{mark}een zone kreeg twee besluiten"
    )

    left = {item.entity_id for item in plan.untouched}
    assert not left & set(steered), f"{mark}apparaat in beide lijsten"

    # Een zone die is overgedragen krijgt niets, ook geen uit - tenzij het
    # apparaat gedeeld wordt met een zone die wel meedoet.
    #
    # A zone handed over gets nothing, an off included - unless the appliance is
    # shared with a zone that does take part.
    for zone in config.zones:
        if not world.overridden(zone.zone_id):
            continue
        for source in zone.sources:
            shared = any(
                other.zone_id != zone.zone_id
                and not world.overridden(other.zone_id)
                and any(item.entity_id == source.entity_id for item in other.sources)
                for other in config.zones
            )
            if not shared:
                assert plan.command_for(source.entity_id) is None, (
                    f"{mark}{zone.zone_id} is overgedragen en kreeg toch een opdracht"
                )

    # Een bron die overal handbediend is, wordt nooit gestart.
    # A source that is hand-operated everywhere is never started.
    owners: dict[str, list] = {}
    for _, source in config.sources():
        owners.setdefault(source.entity_id, []).append(source)
    for entity_id, sources in owners.items():
        if any(source.autostart for source in sources):
            continue
        command = plan.command_for(entity_id)
        if command is not None:
            assert family_of(command.hvac_mode) is ModeFamily.NEUTRAL, (
                f"{mark}handbediende {entity_id} werd gestart"
            )

    # Een zone met een dichte poort draait nooit.
    # A zone with a shut gate never runs.
    for decision in plan.zones:
        if decision.closed_gates:
            assert decision.granted is ModeFamily.NEUTRAL, (
                f"{mark}{decision.zone_id} draait terwijl {decision.closed_gates} dicht staat"
            )

    for circuit in config.circuits:
        if circuit.simultaneous_heat_cool:
            continue

        ordered = {
            family_of(command.hvac_mode)
            for command in plan.commands
            if command.entity_id in circuit.units
        } & {ModeFamily.HEAT, ModeFamily.COOL}
        assert len(ordered) <= 1, f"{mark}{circuit.circuit_id} krijgt {ordered} tegelijk"

        # Een unit die deze ronde géén commando krijgt en doordraait, houdt het
        # circuit vast - AMBIGUOUS inbegrepen: een stand die de engine niet kent
        # kan de compressor net zo goed laten draaien. De director mag er geen
        # taak naast zetten die daarmee botst.
        #
        # A unit that gets no command this round and keeps running holds the
        # circuit - AMBIGUOUS included: a mode the engine does not know may run
        # the compressor just the same. The director may not put a duty beside
        # it that clashes.
        commanded = {
            command.entity_id for command in plan.commands if command.entity_id in circuit.units
        }
        standing_families = {
            world.climate(entity_id).family
            for entity_id in circuit.units
            if entity_id not in commanded and world.climate(entity_id).running
        } - {ModeFamily.NEUTRAL}
        if ordered and standing_families:
            assert standing_families <= ordered, (
                f"{mark}{circuit.circuit_id} draait {sorted(standing_families)} terwijl "
                f"de director {sorted(ordered)} opdraagt"
            )

        if circuit.max_concurrent_units is None:
            continue

        # De grens gaat over wat de director erbij zet. Staan er al meer units
        # te draaien dan de buitenunit aankan, dan heeft een mens dat gedaan -
        # met een afstandsbediening, een override of een handbediend apparaat -
        # en daar mag de director niets meer bovenop doen. Hij mag er dan ook
        # niet dwars voor gaan liggen: een override uitzetten is precies wat een
        # override niet is.
        #
        # The limit is about what the director adds. If more units already run
        # than the outdoor unit can take, a person did that - with a remote, an
        # override or a hand-operated appliance - and the director may add
        # nothing on top. Nor may it get in the way: switching an override off
        # is exactly what an override is not.
        put_to_work = {
            command.entity_id
            for command in plan.commands
            if command.entity_id in circuit.units
            and family_of(command.hvac_mode) in (ModeFamily.HEAT, ModeFamily.COOL)
        }
        left_running = {
            entity_id
            for entity_id in circuit.units
            if entity_id not in {command.entity_id for command in plan.commands}
            and world.climate(entity_id).running
        }
        assert not put_to_work or len(put_to_work | left_running) <= circuit.max_concurrent_units, (
            f"{mark}director zet {sorted(put_to_work)} aan terwijl {sorted(left_running)} al "
            f"draait op een circuit voor {circuit.max_concurrent_units}"
        )
