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
"""

from __future__ import annotations

import argparse
import sys
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

    problems = measurement_problems(args.data_file, Path(args.package))
    if problems:
        print("De meting is niet bruikbaar / the measurement cannot be used:")
        for problem in problems:
            print(f"  {problem}")
        print()
        print(MEASUREMENT_HINT)
        return 1

    missed = missed_lines(args.data_file, Path(args.package))
    if missed:
        print("Gemiste regels / missed lines:")
        for path, lines in missed.items():
            print(f"  {path}: {', '.join(str(line) for line in lines)}")
        print()
        print(MISSED_HINT)
        return 1
    print("OK: geen enkele gemiste regel / no missed line.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
