#!/usr/bin/env python
"""Poort op de dekkingsmeting: geen enkele gemiste regel in de integratie.

Draai dit ná `coverage run -m pytest`. Het leest de meetgegevens die coverage
heeft achtergelaten en telt de gemiste regels. Dat is de deterministische kant
van de meting: welke *tak* wel of niet twee kanten op gaat wiebelt tussen twee
runs (ronde 31 mat 20 en 21 partiële takken op identieke code), maar of een
*regel* is uitgevoerd niet. Daarom is dit de bewaking van "nul gemiste regels"
en niet de percentage-ratel in `pyproject.toml` alleen: die zakt pas bij twee
gemiste regels, omdat hij de wiebel moet verdragen.

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
"""

from __future__ import annotations

import argparse
import sys

from coverage import Coverage

MISSED_HINT = (
    "Elke regel hoort door de suite geraakt te worden. Zoek de test die hier\n"
    "hoort, of zet een `pragma: no cover` met een reden die over de\n"
    "testbaarheid gaat (en niet over de dekking zelf).\n"
    "\n"
    "Every line should be touched by the suite. Find the test that belongs\n"
    "here, or add a `pragma: no cover` with a reason about testability (not\n"
    "about coverage itself)."
)


def missed_lines(data_file: str) -> dict[str, list[int]]:
    """Return the missed lines per file in the measurement.

    Geeft de gemiste regels per bestand terug.
    """
    coverage = Coverage(data_file=data_file)
    coverage.load()
    data = coverage.get_data()
    missed: dict[str, list[int]] = {}
    for path in sorted(data.measured_files()):
        _, _, _, missing, _ = coverage.analysis2(path)
        if missing:
            missed[path] = sorted(missing)
    return missed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-file",
        default=".coverage",
        help="het coverage-gegevensbestand / the coverage data file",
    )
    args = parser.parse_args()

    missed = missed_lines(args.data_file)
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
