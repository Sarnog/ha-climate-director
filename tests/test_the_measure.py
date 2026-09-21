"""De maat uit ARCHITECTURE.md wordt bewaakt, en kan alleen kleiner worden.

ARCHITECTURE.md stelt de norm in beide talen: een module blijft onder ~700
regels, een functie onder ~80. Zonder bewaking groeit dat binnen een jaar
terug — S1 t/m S5 hebben de ergste gevallen opgedeeld, maar niets houdt de
grens zelf vast. Deze test is de ratel die dat wél doet: de
uitzonderingslijst hieronder is letterlijk de stand van dit moment, met per
regel het gemeten aantal. Wordt een genoteerde module of functie groter dan
wat er staat, dan is deze test rood en mag de maat niet groeien; wordt hij
kleiner, dan is de test óók rood, met de melding "haal deze van de lijst" of
"zet het nieuwe getal erin". Zo kan de lijst alleen korter worden en is hij
nooit stiekem verouderd.

Definitie van "regels", zodat een volgende ronde over de telling niet hoeft
te twisten: een module telt als het aantal fysieke regels van het bestand
(`len(text.splitlines())`); een functie telt als `end_lineno - lineno + 1`,
van de eerste regel die `ast` aan de `def` toekent tot en met de laatste regel
van het blok. Er wordt met `ast.walk` over élk
bestand onder `custom_components/climate_director/` gelopen, niet met
`tree.body`: een geneste functie telt dus mee, en `AsyncFunctionDef` telt net
zo goed als `FunctionDef`.

Waarom een eigen bestand: `test_the_border.py` bewaakt één specifieke grens —
de engine importeert Home Assistant nergens — terwijl deze bewaking elke
module en elke functie van de hele integratie meet en een eigen
uitzonderingslijst heeft. Samenhouden zou twee verschillende dingen in één
docstring stoppen.

The measure from ARCHITECTURE.md is guarded, and it can only get smaller.
ARCHITECTURE.md sets the norm in both languages: a module stays under ~700
lines, a function under ~80. Without a guard this grows back within a year —
S1 through S5 split the worst cases, but nothing holds the line itself. This
test is the ratchet that does hold it: the exception list below is literally
the state of this moment, with the measured count per entry. When a listed
module or function grows beyond what is written here, this test is red and
the measure may not grow; when it shrinks, the test is red too, with the
message "remove it from the list" or "put the new number in". That way the
list can only get shorter and is never silently outdated.

Definition of "lines", so a next round does not have to argue about the
count: a module counts as the number of physical lines of the file
(`len(text.splitlines())`); a function counts as `end_lineno - lineno + 1`,
from the first line `ast` assigns to the `def` through the last line of the
block. Every file under
`custom_components/climate_director/` is walked with `ast.walk`, not with
`tree.body`: a nested function therefore counts, and `AsyncFunctionDef`
counts just as well as `FunctionDef`.

Why a file of its own: `test_the_border.py` guards one specific border — the
engine imports Home Assistant nowhere — whereas this guard measures every
module and every function of the whole integration and carries its own
exception list. Keeping them together would put two different things in one
docstring.
"""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "climate_director"

MODULE_LIMIT = 700
FUNCTION_LIMIT = 80

# De stand van dit moment, gemeten op cf3e4bf (2026-09-07). Deze lijst is de
# uitzondering op de norm uit ARCHITECTURE.md, niet de norm zelf: hij kan
# alleen kleiner worden.
#
# The state of this moment, measured on cf3e4bf (2026-09-07). This list is the
# exception to the norm in ARCHITECTURE.md, not the norm itself: it can only
# get shorter.
# Sinds cf3e4bf zijn er zes genoteerde getallen bewogen, en dat was een bewuste
# keuze: `engine/models.py` 2039 → 2100 (anker 12 voegt `covers_zones` en
# `takeover_delay` aan `Source` toe, plus de regel die een onbekende zone in
# dat gebied meldt), `engine/decide.py` 1618 → 1647 (de overname moet vóór de
# bronkeuze staan en wordt door de functies heen meegegeven), `_build_commands`
# 200 → 202, `_collect_wishes` 114 → 126, `_resolve_with_fallbacks` 83 → 87,
# en `_build_zone_decisions` is met 82 nieuw op de lijst. Let op dat de regel
# `only, unbounded = takeover.narrowing(...)` op drie paden staat
# (`_collect_wishes`, `_resolve_with_fallbacks`, `_build_zone_decisions`) —
# de vorm "op het ene pad gerepareerd, op het pad ernaast vergeten", vandaag
# gedekt door 32 tests. Een veld toevoegen kan niet zonder regels; de ratel
# maakt die groei zichtbaar in plaats van hem te verbieden. Verhoog een
# genoteerd getal daarom alleen met een reden erbij, precies zoals hier.
#
# Since cf3e4bf six noted numbers have moved, and that was a deliberate choice:
# `engine/models.py` 2039 → 2100 (anchor 12 adds `covers_zones` and
# `takeover_delay` to `Source`, plus the rule reporting an unknown zone in that
# area), `engine/decide.py` 1618 → 1647 (the takeover must sit before source
# selection and is passed through the functions), `_build_commands` 200 → 202,
# `_collect_wishes` 114 → 126, `_resolve_with_fallbacks` 83 → 87, and
# `_build_zone_decisions` is new on the list at 82. Note that the line
# `only, unbounded = takeover.narrowing(...)` stands on three paths
# (`_collect_wishes`, `_resolve_with_fallbacks`, `_build_zone_decisions`) —
# the shape "fixed on one path, forgotten on the one beside it", today covered
# by 32 tests. Adding a field cannot happen without lines; the ratchet makes
# that growth visible rather than forbidding it. Only ever raise a noted
# number with a reason alongside, exactly as here.
#
# Ronde 25, fase 1 (anker 8): de opening kreeg een eigen identiteit en een
# overbruggingsschakelaar; dat raakt de models, de coordinator, de config flow
# en de schema's, dus deze vijf getallen groeiden mee. De lijst zelf is even
# lang gebleven.
#
# Round 25, phase 1 (anchor 8): the opening gained an identity of its own and a
# bypass switch; that touches the models, the coordinator, the config flow and
# the schemas, so these five numbers grew along. The list itself stayed the
# same length.
#
# Ronde 26 (R2): `engine/models.py` 2120 → 2143 door de nieuwe
# `_rule_duplicate_opening_ids` — een dubbel opening_id moet een `Problem`-code
# krijgen in plaats van stil twee schakelaars te laten delen. Een nieuwe
# validatieregel kan niet zonder regels; de ratel maakt die groei zichtbaar.
#
# Round 26 (R2): `engine/models.py` 2120 → 2143 through the new
# `_rule_duplicate_opening_ids` — a doubled opening id must get a `Problem`
# code instead of silently sharing two switches. A new validation rule cannot
# exist without lines; the ratchet makes that growth visible.
#
# Ronde 27 (R27-2): `config_flow.py` 1418 → 1444 door `_normalise_opening_ids`
# — de options flow leest de ruwe opslag, dus een opening zonder `opening_id`
# kreeg bij de eerste bewerking een id uit de naam en daarmee een nieuwe
# `unique_id`. De afleiding zelf woont in `engine/serialise.opening_ids`, dat
# daardoor onder de 700 blijft: `_unique_opening_id` ging erin op in plaats van
# ernaast te staan. Wat hier groeit is de aanroep plus de uitleg waarom.
#
# Round 27 (R27-2): `config_flow.py` 1418 → 1444 through `_normalise_opening_ids`
# — the options flow reads the raw storage, so an opening without an
# `opening_id` got an id from its name on the first edit, and with it a new
# `unique_id`. The derivation itself lives in `engine/serialise.opening_ids`,
# which stays under 700 because of it: `_unique_opening_id` merged into that
# function instead of standing beside it. What grows here is the call plus the
# explanation of why.
#
# Ronde 30, fase 4 (mypy strict schoon): `coordinator.py` 1756 → 1840 door het
# `CoordinatorSurface`-protocol plus de `entry`-property. De vier mixins liggen
# op de coördinator maar erven er niet van — de coördinator erft van hén — dus
# zonder dat protocol ziet mypy hun `self` als de mixin en klaagt hij op elk
# coordinator-attribuut: 106 van de 156 fouten. Het protocol is er alleen onder
# `TYPE_CHECKING`; buiten de typecontrole bestaat het niet. `config_flow.py`
# 1444 → 1451 door `_groups()`: de exclusieve groepen zijn een lijst van
# lijsten, en één getypeerde lezer is eerlijker dan twee `list[dict]`-casts op
# de plek waar de bron-ID's wonen.
#
# Round 30, phase 4 (mypy strict clean): `coordinator.py` 1756 → 1840 through the
# `CoordinatorSurface` protocol plus the `entry` property. The four mixins sit on
# the coordinator but do not inherit from it — the coordinator inherits from
# them — so without that protocol mypy sees their `self` as the mixin and
# complains about every coordinator attribute: 106 of the 156 errors. The
# protocol exists only under `TYPE_CHECKING`; outside the type check it does not.
# `config_flow.py` 1444 → 1451 through `_groups()`: the exclusive groups are a
# list of lists, and one typed reader is more honest than two `list[dict]` casts
# where the source ids live.
#
# Ronde 33 (override op het dashboard): `coordinator.py` 1840 → 1842 en
# `coordinator.py::__init__` 197 → 198 door de **starttijd** van een override
# (`zone_override_started`). Eén regel in het `CoordinatorSurface`-protocol en
# één in `__init__`, want de mixin `overrides.py` zet die tijd en mypy moet hem
# daar kennen; zonder die twee regels klapt de typecontrole op een lid dat de
# coördinator werkelijk draagt. De rest van deze ronde woont in `sensor.py` (de
# eindtijdsensor met zijn apparaatklasse), `state_store.py` (opslag en herstel,
# met een oude opslag die zonder dat veld gewoon laadt) en `__init__.py` (de
# servicelaag die een entiteit als doel aanneemt) — alle drie onder hun maat.
#
# Round 33 (override on the dashboard): `coordinator.py` 1840 → 1842 and
# `coordinator.py::__init__` 197 → 198 through an override's **start time**
# (`zone_override_started`). One line in the `CoordinatorSurface` protocol and
# one in `__init__`, because the `overrides.py` mixin sets that time and mypy has
# to know it there; without those two lines the type check trips over a member
# the coordinator really carries. The rest of this round lives in `sensor.py`
# (the end-time sensor with its device class), `state_store.py` (storage and
# restore, where an old file without that field simply loads) and `__init__.py`
# (the service layer accepting an entity as its target) — all three below their
# measure.
#
# Ronde 34 (R34-7): `coordinator.py` 1842 → 1852 door de declaratie van
# `async_update_listeners` in het `CoordinatorSurface`-protocol, met de reden
# erbij waarom die geen kale `...`-stub is: de mixin `overrides.py` laat de
# eindtijdsensor na het uitzetten van de schakelaar, `set_override` en
# `clear_override` direct meeschrijven in plaats van pas bij de volgende
# beslisronde, en mypy moet die methode daar kennen. De methode zelf komt van
# `DataUpdateCoordinator`; een lege stub zou de concrete klasse abstract maken.
# De reparatie woont in `overrides.py` (één publishmethode voor de drie paden) en
# `switch.py` (de schakelaar roept hem aan) — allebei onder hun maat.
#
# Round 34 (R34-7): `coordinator.py` 1842 → 1852 through the declaration of
# `async_update_listeners` in the `CoordinatorSurface` protocol, with the reason
# alongside why it is no bare `...` stub: the `overrides.py` mixin has the
# end-time sensor write along at once after switching the override off,
# `set_override` and `clear_override`, instead of only at the next decision
# round, and mypy has to know that method there. The method itself comes from
# `DataUpdateCoordinator`; an empty stub would make the concrete class abstract.
# The repair lives in `overrides.py` (one publish method for the three paths) and
# `switch.py` (the switch calls it) — both below their measure.
# Anker 13 (het stiltevenster remt alleen thuiskomers): `engine/models.py` 2143 →
# 2198 door `TimeWindow.started_at`, de methode die teruggeeft wanneer de lopende
# voorkomst van een venster begon. Eén methode met de middernacht- en de
# vakantievorm in de docstring; zonder die methode zou de poort dezelfde
# middernachtberekening nog een keer opschrijven en dan kunnen de twee uit elkaar
# lopen. `engine/gates.py` blijft onder de 700 met de drie uitzonderingen erin,
# `engine/world.py` met `ResidentState.home_since` ook.
#
# Anchor 13 (the quiet window brakes only homecomers): `engine/models.py` 2143 →
# 2198 through `TimeWindow.started_at`, the method returning when a window's
# current occurrence began. One method with the midnight and the holiday shape in
# its docstring; without it the gate would write that same midnight calculation a
# second time, and then the two could drift apart. `engine/gates.py` stays under
# 700 with the three exceptions in it, `engine/world.py` with
# `ResidentState.home_since` too.
MODULE_EXCEPTIONS: dict[str, int] = {
    "engine/models.py": 2198,
    "coordinator.py": 1852,
    "engine/decide.py": 1677,
    "config_flow.py": 1451,
    "schemas.py": 900,
}

FUNCTION_EXCEPTIONS: dict[tuple[str, str], int] = {
    ("engine/decide.py", "_build_commands"): 202,
    ("engine/decide.py", "_generator_commands"): 192,
    ("coordinator.py", "__init__"): 198,
    ("engine/models.py", "_rule_zones"): 142,
    ("engine/constraints.py", "resolve"): 128,
    ("coordinator.py", "_refusal_data"): 119,
    ("coordinator.py", "_notice_hand"): 117,
    ("engine/decide.py", "_collect_wishes"): 126,
    ("engine/decide.py", "_manual_conflict"): 103,
    ("engine/decide.py", "_build_zone_decisions"): 111,
    ("schemas.py", "resident"): 98,
    ("engine/hysteresis.py", "_candidate"): 97,
    ("config_flow.py", "async_step_resident"): 91,
    ("engine/decide.py", "_resolve_with_fallbacks"): 87,
    ("preconditions.py", "async_precondition"): 83,
}


def _python_files(root: Path) -> list[Path]:
    """Elk `.py`-bestand onder `root`; een lege lijst is een fout, geen groene test.

    Every `.py` file under `root`; an empty list is an error, not a green test.
    """
    files = sorted(root.rglob("*.py"))
    assert files, f"maatbewaking: geen bestanden gevonden onder {root}"
    return files


def module_sizes(root: Path | None = None) -> dict[str, int]:
    """Meet elke module als het aantal fysieke regels van het bestand.

    Measure every module as the number of physical lines of the file.
    """
    if root is None:
        root = PACKAGE_ROOT
    sizes: dict[str, int] = {}
    for path in _python_files(root):
        text = path.read_text(encoding="utf-8")
        sizes[path.relative_to(root).as_posix()] = len(text.splitlines())
    return sizes


def function_sizes(root: Path | None = None) -> dict[tuple[str, str, int], int]:
    """Meet elke functie als `end_lineno - lineno + 1`, via `ast.walk`.

    `ast.walk` ziet geneste functies en `AsyncFunctionDef` net zo goed als
    `FunctionDef`. Bestaan er twee functies met dezelfde naam in één bestand,
    dan tellen ze apart, met het regelnummer in de sleutel.

    Measure every function as `end_lineno - lineno + 1`, through `ast.walk`.
    `ast.walk` sees nested functions and `AsyncFunctionDef` just as well as
    `FunctionDef`. When two functions share a name in one file, they count
    separately, with the line number in the key.
    """
    if root is None:
        root = PACKAGE_ROOT
    sizes: dict[tuple[str, str, int], int] = {}
    for path in _python_files(root):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        rel = path.relative_to(root).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                key = (rel, node.name, node.lineno)
                end = node.end_lineno
                assert end is not None, (
                    "een uit de bron geparsete functie hoort een end_lineno te hebben"
                )
                lines = end - node.lineno + 1
                sizes[key] = lines
    return sizes


def _drift_note(kind: str, name: str, noted: int, actual: int, limit: int) -> str:
    """Eén leesbare melding wanneer een genoteerde uitzondering bewogen is.

    One readable message when a listed exception has moved.
    """
    if actual > noted:
        return (
            f"{kind} {name}: {actual} regels, genoteerd {noted} — gegroeid; "
            "dat mag niet, de maat kan alleen kleiner worden"
        )
    if actual <= limit:
        return (
            f"{kind} {name}: {actual} regels, genoteerd {noted} — "
            "niet meer boven de maat; haal deze van de lijst"
        )
    return (
        f"{kind} {name}: {actual} regels, genoteerd {noted} — kleiner geworden; "
        "haal deze van de lijst of zet het nieuwe getal erin"
    )


def test_the_measure_is_a_ratchet() -> None:
    """De uitzonderingslijst klopt exact, en niets boven de maat staat erbuiten.

    The exception list matches exactly, and nothing above the measure sits
    outside it.
    """
    modules = module_sizes()
    functions = function_sizes()
    problems: list[str] = []

    for name, noted in sorted(MODULE_EXCEPTIONS.items()):
        actual = modules.get(name)
        if actual is None:
            problems.append(
                f"module {name}: genoteerd als {noted} regels, maar het bestand bestaat niet meer"
            )
        elif actual != noted:
            problems.append(_drift_note("module", name, noted, actual, MODULE_LIMIT))

    for name, actual in modules.items():
        if actual > MODULE_LIMIT and name not in MODULE_EXCEPTIONS:
            problems.append(
                f"module {name}: {actual} regels, boven de {MODULE_LIMIT} en niet genoteerd — "
                "de maat mag niet groeien"
            )

    for key, noted in sorted(FUNCTION_EXCEPTIONS.items()):
        actual = max(
            (lines for (rel, name, _lineno), lines in functions.items() if (rel, name) == key),
            default=None,
        )
        label = f"{key[0]}::{key[1]}"
        if actual is None:
            problems.append(
                f"functie {label}: genoteerd als {noted} regels, maar bestaat niet meer"
            )
        elif actual != noted:
            problems.append(_drift_note("functie", label, noted, actual, FUNCTION_LIMIT))

    for function_key, actual in functions.items():
        if (
            actual > FUNCTION_LIMIT
            and (function_key[0], function_key[1]) not in FUNCTION_EXCEPTIONS
        ):
            label = f"{function_key[0]}::{function_key[1]}@{function_key[2]}"
            problems.append(
                f"functie {label}: {actual} regels, boven de {FUNCTION_LIMIT} en niet genoteerd — "
                "de maat mag niet groeien"
            )

    assert not problems, "de maat is bewogen:\n" + "\n".join(problems)
