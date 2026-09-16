#!/usr/bin/env python
"""Poort op de dekkingsmeting: geen enkele gemiste regel in de integratie.

Draai dit ná `coverage run -m pytest`. Het leest de meetgegevens die coverage
heeft achtergelaten en telt de gemiste regels. Dat is de deterministische kant
van de meting: welke *tak* wel of niet twee kanten op gaat wiebelt tussen twee
runs (ronde 31 mat 20 en 21 partiële takken op identieke code), maar of een
*regel* is uitgevoerd niet. Daarom is dit de bewaking van "nul gemiste regels"
en niet de percentage-ratel in `pyproject.toml` alleen: die zakt pas bij twee
gemiste regels, omdat hij de wiebel moet verdragen.

De poort keurt alleen een meting goed **waarin het pakket werkelijk voorkomt**.
Zonder dat voorwerk is "nul gemiste regels" vacuüm waar, en dat is gemeten
(ronde 31: `--data-file <bestaat niet>` gaf "OK" en exit 0). Daarom weigert hij
vier metingen: een ontbrekend gegevensbestand, een lege meting, een meting
zonder één bestand onder het pakket, en een meting waarin niet élk `.py`-bestand
van het pakket voorkomt — een module die nooit geïmporteerd wordt is anders
onzichtbaar.

Daar komt sinds ronde 34 (R34-3) een vijfde weigering bij: een meting waarin een
regel buiten de telling valt die geen naam heeft in `NAMED_EXCLUSIONS`. Coverage
laat regels weg op een patroon (`# pragma: no cover`, een `...` als blokinhoud,
een `if TYPE_CHECKING:`-blok), en een patroon verbergt stil: zo'n regel verdwijnt
uit "nul gemiste regels" zonder dat iemand hem noemt. De poort noemt ze daarom
allemaal, met hun inhoud erbij, en laat zowel een regel zonder naam als een naam
zonder regel vallen. Sinds ronde 35 (R35-5) telt alleen het begin van een
statement: een commentaarregel, een decorator of een vervolgregel kan zonder de
uitsluiting nooit een gemeten regel zijn, dus die vraagt geen naam — anders hing
de poort aan de letterlijke tekst van een commentaar.

Gebruik / usage:

    python -m coverage run -m pytest -q
    python script/coverage_gate.py

    Gate on the coverage measurement: not a single missed line in the
    integration. Run this after `coverage run -m pytest`. It reads the data
    coverage left behind and counts the missed lines. That is the deterministic
    side of the measurement: which *branch* goes both ways wobbles between two
    runs (round 31 measured 20 and 21 partial branches on identical code), but
    whether a *line* ran does not. Hence this guards "zero missed lines" rather
    than the percentage ratchet in `pyproject.toml` alone, which only drops at
    two missed lines because it has to absorb the wobble.

    The gate only approves a measurement **in which the package really
    appears**. Without that groundwork "zero missed lines" is vacuously true,
    and that was measured (round 31: `--data-file <does not exist>` printed "OK"
    and exited 0). Hence it refuses four measurements: a missing data file, an
    empty measurement, a measurement without a single file under the package,
    and a measurement missing one of the package's `.py` files — a module that
    is never imported is invisible otherwise.

    Round 34 (R34-3) adds a fifth refusal: a measurement in which a line falls
    outside the count without a name in `NAMED_EXCLUSIONS`. Coverage drops lines
    on a pattern (`# pragma: no cover`, a `...` as a block's content, an
    `if TYPE_CHECKING:` block), and a pattern hides silently: such a line
    disappears from "zero missed lines" without anyone naming it. Hence the gate
    names them all, with their content alongside, and drops both a line without
    a name and a name without a line. Since round 35 (R35-5) only the start of a
    statement counts: a comment line, a decorator or a continuation line could
    never be a measured line without the exclusion, so it asks for no name —
    otherwise the gate hung on the literal text of a comment.
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections import Counter
from pathlib import Path

from coverage import Coverage

#: De map waarvoor deze poort geldt: het pakket zelf.
#:
#: The directory this gate applies to: the package itself.
PACKAGE = Path(__file__).resolve().parents[1] / "custom_components" / "climate_director"

MEASUREMENT_HINT = (
    "Deze poort keurt alleen een meting goed waarin het pakket werkelijk\n"
    "voorkomt. Draai `python -m coverage run -m pytest -q` vanuit de map van de\n"
    "repository en wijs `--data-file` naar het bestand dat coverage achterliet.\n"
    "\n"
    "This gate only approves a measurement in which the package really appears.\n"
    "Run `python -m coverage run -m pytest -q` from the repository root and point\n"
    "`--data-file` at the file coverage left behind."
)

MISSED_HINT = (
    "Elke regel hoort door de suite geraakt te worden. Zoek de test die hier\n"
    "hoort — verzonnen invoer mag, als de eigenschap maar vastligt. Het pakket\n"
    "draagt bewust geen enkele `pragma: no cover`: die haalt een regel uit deze\n"
    'meting, en dan zegt "nul gemiste regels" niets meer over die regel.\n'
    "\n"
    "Every line should be touched by the suite. Find the test that belongs here —\n"
    "invented input is fine, as long as the property is pinned down. The package\n"
    "deliberately carries no `pragma: no cover` at all: it takes a line out of\n"
    'this measurement, and then "zero missed lines" says nothing about it.'
)

EXCLUSION_HINT = (
    "Een regel die buiten de meting valt hoort een naam te hebben in\n"
    '`NAMED_EXCLUSIONS`, met de reden erbij: pas dan is "nul gemiste regels" een\n'
    "uitspraak over elke regel. Kan de regel er echt niet komen (hij bestaat\n"
    "alleen voor de typecontrole), zet hem er dan bij; is hij wel te meten, zoek\n"
    "dan de test die er hoort. Andersom geldt het ook: een naam die niets meer\n"
    "verbergt hoort uit de lijst, want een verouderde whitelist wekt de indruk\n"
    "dat er iets afgesproken is.\n"
    "\n"
    "A line that falls outside the measurement should have a name in\n"
    '`NAMED_EXCLUSIONS`, with the reason alongside: only then is "zero missed\n'
    'lines" a statement about every line. If the line really cannot be reached\n'
    "(it exists for the type check only), add it there; if it can be measured,\n"
    "find the test that belongs to it. The reverse holds too: a name that hides\n"
    "nothing anymore belongs out of the list, since a stale whitelist suggests\n"
    "something was agreed."
)

#: De regels die de meting niet meerekent, met naam en toenaam. Alleen het begin
#: van een statement telt hier: een commentaarregel, een decorator of een
#: vervolgregel kan zonder uitsluiting nooit een gemeten regel zijn, dus die hoort
#: niet in deze lijst — anders hing de poort aan de letterlijke tekst van een
#: commentaar (ronde 35, R35-5).
#:
#: Coverage laat drie soorten regels weg op een patroon: `# pragma: no cover`,
#: een `...` als enige inhoud van een blok, en een `if TYPE_CHECKING:`-blok. Die
#: patronen staan sinds ronde 34 (R34-3) uitgeschreven in `pyproject.toml`, zodat
#: de meting niet op verborgen standaardpatronen leunt, maar een patroon verbergt
#: nog steeds stil: elke regel die eronder valt verdwijnt uit "nul gemiste regels"
#: zonder dat iemand hem noemt. Daarom staat hieronder elke statementregel met
#: zijn eigen inhoud — negen in `coordinator.py` (het `CoordinatorSurface`-
#: protocol, dat alleen voor de typecontrole bestaat: een `...`-stub wordt nooit
#: aangeroepen) en drie in elk van de vier mixins die dat protocol onder
#: `TYPE_CHECKING` importeren (die tak is bij het draaien nooit waar). De poort
#: eist dat de lijst precies klopt: een regel die buiten de meting valt zonder
#: hier te staan laat hem vallen, en een naam die niets meer verbergt ook.
#:
#: The lines the measurement does not count, by name. Only the start of a
#: statement counts here: a comment line, a decorator or a continuation line
#: could never be a measured line without the exclusion, so it does not belong in
#: this list — otherwise the gate hung on the literal text of a comment (round
#: 35, R35-5).
#:
#: Coverage drops three kinds of lines on a pattern: `# pragma: no cover`, a `...`
#: as a block's only content, and an `if TYPE_CHECKING:` block. Since round 34
#: (R34-3) those patterns are written out in `pyproject.toml`, so the measurement
#: does not lean on hidden defaults, but a pattern still hides silently: every
#: line it hits disappears from "zero missed lines" without anyone naming it.
#: Hence every statement line stands below with its own content — nine in
#: `coordinator.py` (the `CoordinatorSurface` protocol, which exists for the type
#: check only: a `...` stub is never called) and three in each of the four mixins
#: that import that protocol under `TYPE_CHECKING` (that branch is never true at
#: run time). The gate demands the list to be exact: a line that falls outside the
#: measurement without standing here drops it, and so does a name that hides
#: nothing anymore.
NAMED_EXCLUSIONS: dict[str, tuple[str, ...]] = {
    "coordinator.py": (
        "def entry(self) -> ClimateDirectorEntry: ...",
        "def async_request_evaluation(self) -> None: ...",
        "def _async_save_state(self) -> None: ...",
        "def _live_preconditions(self) -> dict[str, datetime]: ...",
        "def _wake_at_the_first_expiry(self) -> None: ...",
        "def _override_wake_at_first_expiry(self) -> None: ...",
        "def _calendar_says_holiday(self) -> bool: ...",
        "def _zones_handed_back(",
        ") -> set[str]: ...",
    ),
    "overrides.py": (
        "if TYPE_CHECKING:",
        "from .coordinator import CoordinatorSurface",
        "_CoordinatorBase = CoordinatorSurface",
    ),
    "preconditions.py": (
        "if TYPE_CHECKING:",
        "from .coordinator import CoordinatorSurface",
        "_CoordinatorBase = CoordinatorSurface",
    ),
    "state_store.py": (
        "if TYPE_CHECKING:",
        "from .coordinator import CoordinatorSurface",
        "_CoordinatorBase = CoordinatorSurface",
    ),
    "world_builder.py": (
        "if TYPE_CHECKING:",
        "from .coordinator import CoordinatorSurface",
        "_CoordinatorBase = CoordinatorSurface",
    ),
}


def measured_path(path: str) -> Path:
    """Een gemeten bestand als absoluut pad.

    Coverage bewaart een relatief pad zoals het op het moment van de run gold;
    die run gebeurt vanuit de map van de repository, dus daar wordt een relatief
    pad tegen opgelost.

    A measured file as an absolute path. Coverage stores a relative path as it
    applied at the time of the run; that run happens from the repository root,
    so a relative path is resolved against it.
    """
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (PACKAGE.parents[1] / candidate).resolve()


def measurement_problems(data_file: str, package: Path = PACKAGE) -> list[str]:
    """Wat er mis is met de meting zelf; een lege lijst betekent bruikbaar.

    What is wrong with the measurement itself; an empty list means usable.
    """
    if not Path(data_file).exists():
        return [
            f"het gegevensbestand `{data_file}` bestaat niet, dus er is niets "
            f"gemeten om goed te keuren"
        ]

    coverage = Coverage(data_file=data_file)
    coverage.load()
    measured = {measured_path(path) for path in coverage.get_data().measured_files()}
    if not measured:
        return [f"de meting in `{data_file}` is leeg: coverage heeft geen enkel bestand gemeten"]

    root = Path(package).resolve()
    if not any(root in path.parents for path in measured):
        return [
            f"geen enkel gemeten bestand valt onder {root}, dus deze meting gaat "
            f"niet over het pakket"
        ]

    expected = {path.resolve() for path in root.rglob("*.py")}
    absent = sorted(str(path.relative_to(root)) for path in expected - measured)
    if absent:
        return [
            "deze bestanden van het pakket komen in geen enkele meting voor, dus "
            "een module die nooit geïmporteerd wordt blijft onzichtbaar: " + ", ".join(absent)
        ]
    return []


def missed_lines(data_file: str, package: Path = PACKAGE) -> dict[str, list[int]]:
    """Return the missed lines per file in the measurement.

    Geeft de gemiste regels per bestand terug.
    """
    coverage = Coverage(data_file=data_file)
    coverage.load()
    data = coverage.get_data()
    root = Path(package).resolve()
    missed: dict[str, list[int]] = {}
    for path in sorted(data.measured_files()):
        if root not in measured_path(path).parents:
            continue
        _, _, _, missing, _ = coverage.analysis2(path)
        if missing:
            missed[path] = sorted(missing)
    return missed


def statement_lines(path: Path) -> set[int]:
    """De regelnummers waar een statement begint, uit de bron zelf.

    Niet elke regel die coverage overslaat zou zonder uitsluiting een gemeten
    regel zijn geweest. Staat er een `...`-stub in een klasse, dan slaat
    coverage de hele uitgesloten regio over — de decorator erboven, een
    commentaarregel ertussen en de vervolgregels van een meerregelige `def`
    horen daar bij. Die kunnen zonder de uitsluiting nooit gemeten worden, dus
    ze horen niet in de whitelist; anders hing de poort aan de letterlijke tekst
    van een commentaar (ronde 35, R35-5).

    De regelnummers komen uit `ast`: elke `ast.stmt` begint ergens, en een
    `Expr` met `...` als lichaam begint op de regel van die `...`. Daarmee valt
    de decorator af (`FunctionDef.lineno` wijst naar de `def`, niet naar de
    decorator) en de vervolgregel ook.

    The line numbers where a statement starts, from the source itself. Not every
    line coverage skips would have been a measured line without the exclusion.
    When a class holds a `...` stub, coverage skips the whole excluded region —
    the decorator above it, a comment line in between and the continuation lines
    of a multi-line `def` come along. Those could never be measured without the
    exclusion, so they do not belong in the whitelist; otherwise the gate hung on
    the literal text of a comment (round 35, R35-5).

    The line numbers come from `ast`: every `ast.stmt` starts somewhere, and an
    `Expr` with `...` as its body starts on the line of that `...`. That drops
    the decorator (`FunctionDef.lineno` points at the `def`, not at the
    decorator) and the continuation line too.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.lineno for node in ast.walk(tree) if isinstance(node, ast.stmt)}


def hidden_lines(coverage: Coverage, package: Path = PACKAGE) -> dict[str, list[tuple[int, str]]]:
    """De regels buiten de meting die zonder uitsluiting een statement waren.

    Coverage geeft per bestand de regels terug die het overslaat. Alleen het
    begin van een statement telt hier mee (zie `statement_lines`): een
    commentaarregel, een decorator of een vervolgregel kan zonder de uitsluiting
    nooit een gemeten regel zijn, dus die vraagt geen naam. Een leeg veld kan
    nooit een gemiste regel zijn en telt ook niet mee, en een regelnummer voorbij
    het einde van het bestand (coverage noemt de regel ná een afgesloten blok er
    soms bij) evenmin. De rest moet een naam hebben in `NAMED_EXCLUSIONS`.

    The lines outside the measurement that would have been a statement without
    the exclusion. Coverage returns per file the lines it skips. Only the start
    of a statement counts here (see `statement_lines`): a comment line, a
    decorator or a continuation line could never be a measured line without the
    exclusion, so it asks for no name. An empty line can never be a missed line
    and does not count either, and neither does a line number past the end of the
    file (coverage sometimes names the line after a closed block). The rest has
    to have a name in `NAMED_EXCLUSIONS`.
    """
    root = Path(package).resolve()
    hidden: dict[str, list[tuple[int, str]]] = {}
    for path in sorted(root.rglob("*.py")):
        _, _, excluded, _, _ = coverage.analysis2(str(path))
        text = path.read_text(encoding="utf-8").splitlines()
        starts = statement_lines(path)
        kept = [
            (line, text[line - 1].strip())
            for line in sorted(excluded)
            if line in starts and line <= len(text) and text[line - 1].strip()
        ]
        if kept:
            hidden[str(path.relative_to(root))] = kept
    return hidden


def exclusion_problems(
    hidden: dict[str, list[tuple[int, str]]], package: Path = PACKAGE
) -> list[str]:
    """Elke regel buiten de meting heeft een naam, en elke naam een regel.

    Twee kanten, allebei even hard. Een regel die de meting overslaat zonder in
    `NAMED_EXCLUSIONS` te staan is een stil weggemoffelde regel: "nul gemiste
    regels" zegt dan niets over hem. En een naam die niets meer verbergt is een
    verouderde whitelist, die de indruk wekt dat er iets afgesproken is. Die
    tweede kant geldt voor de bestanden die in dit pakket bestaan: wie de poort
    op een ander pakket richt (de testopstelling doet dat met een verzonnen
    pakketje) heeft niets aan een oordeel over bestanden die daar niet liggen.

    Every line outside the measurement has a name, and every name a line. Two
    sides, equally hard. A line the measurement skips without standing in
    `NAMED_EXCLUSIONS` is a quietly hidden line: "zero missed lines" then says
    nothing about it. And a name that hides nothing anymore is a stale whitelist,
    which suggests something was agreed. That second side applies to the files
    that exist in this package: whoever points the gate at another package (the
    test setup does that with an invented one) has no use for a verdict about
    files that are not there.
    """
    root = Path(package).resolve()
    present = {str(path.relative_to(root)) for path in root.rglob("*.py")}
    problems: list[str] = []
    for name, found in sorted(hidden.items()):
        unnamed = Counter(content for _, content in found) - Counter(NAMED_EXCLUSIONS.get(name, ()))
        for line, content in found:
            if unnamed[content] <= 0:
                continue
            unnamed[content] -= 1
            problems.append(
                f"{name}:{line} valt buiten de meting zonder naam: {content} / "
                f"stands outside the measurement without a name"
            )
    for name, named in sorted(NAMED_EXCLUSIONS.items()):
        if name not in present:
            continue
        found = Counter(content for _, content in hidden.get(name, []))
        for content in named:
            if found[content] > 0:
                found[content] -= 1
                continue
            problems.append(
                f"{name}: de whitelist noemt een regel die de meting niet meer "
                f"overslaat: {content} / the whitelist names a line the measurement "
                f"no longer skips"
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-file",
        default=".coverage",
        help="het coverage-gegevensbestand / the coverage data file",
    )
    parser.add_argument(
        "--package",
        default=str(PACKAGE),
        help="de map waarvoor de poort geldt / the directory the gate applies to",
    )
    args = parser.parse_args(argv)

    package = Path(args.package)
    problems = measurement_problems(args.data_file, package)
    if problems:
        print("De meting is niet bruikbaar / the measurement cannot be used:")
        for problem in problems:
            print(f"  {problem}")
        print()
        print(MEASUREMENT_HINT)
        return 1

    coverage = Coverage(data_file=args.data_file)
    coverage.load()
    unnamed = exclusion_problems(hidden_lines(coverage, package), package)
    if unnamed:
        print("Regels buiten de meting / lines outside the measurement:")
        for problem in unnamed:
            print(f"  {problem}")
        print()
        print(EXCLUSION_HINT)
        return 1

    missed = missed_lines(args.data_file, package)
    if missed:
        print("Gemiste regels / missed lines:")
        for path, lines in missed.items():
            print(f"  {path}: {', '.join(str(line) for line in lines)}")
        print()
        print(MISSED_HINT)
        return 1
    named = sum(len(entries) for entries in NAMED_EXCLUSIONS.values())
    print(
        f"OK: geen enkele gemiste regel; regels buiten de meting: {named}, allemaal "
        f"met naam / no missed line; lines outside the measurement: {named}, all named."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
