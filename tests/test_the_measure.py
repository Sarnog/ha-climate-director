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
MODULE_EXCEPTIONS: dict[str, int] = {
    "engine/models.py": 2033,
    "coordinator.py": 1698,
    "engine/decide.py": 1618,
    "config_flow.py": 1412,
    "schemas.py": 893,
}

FUNCTION_EXCEPTIONS: dict[tuple[str, str], int] = {
    ("engine/decide.py", "_build_commands"): 200,
    ("engine/decide.py", "_generator_commands"): 192,
    ("coordinator.py", "__init__"): 179,
    ("engine/models.py", "_rule_zones"): 142,
    ("engine/constraints.py", "resolve"): 128,
    ("coordinator.py", "_refusal_data"): 119,
    ("coordinator.py", "_notice_hand"): 117,
    ("engine/decide.py", "_collect_wishes"): 114,
    ("engine/decide.py", "_manual_conflict"): 103,
    ("schemas.py", "resident"): 98,
    ("engine/hysteresis.py", "_candidate"): 97,
    ("config_flow.py", "async_step_resident"): 91,
    ("engine/decide.py", "_resolve_with_fallbacks"): 83,
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
