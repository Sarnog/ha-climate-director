"""Draai alleen de toetsen van deze wijziging, met hun dekking en hun kaart.

Run only the tests of this change, with their coverage and their map.

1. De selectie komt uit `script/select_tests.py`. Is die leeg, dan draait er niets.
2. De toetsen draaien onder coverage; `tests/conftest.py` geeft elk toetsbestand een
   eigen context en noteert welke repo-bestanden het opent (`CD_IMPACT_LOG`).
3. Dekking: draait alles, dan meet `coverage report` het hele pakket (de drempel uit
   `pyproject.toml`) en houdt `script/coverage_gate.py` de regels buiten de meting
   bij naam. Draait een selectie, dan meet het rapport alleen de gewijzigde
   pakketbestanden, op 100 % - de selectie bevat elke toets die zo'n bestand
   uitvoert, dus die meting is volledig.
4. Kaart: wat de gedraaide toetsen uitvoerden en openden, hoort in
   `tests/impact_map.json` te staan. In de CI valt de baan als er iets ontbreekt
   (en bij een volledige run ook als de kaart iets te veel noemt); lokaal wordt de
   kaart bijgewerkt, en die wijziging hoort in de commit.

`--no-coverage` draait dezelfde selectie zonder coverage en zonder kaart: dat is de
baan op de oudste ondersteunde Home Assistant.

1. The selection comes from `script/select_tests.py`. When it is empty, nothing runs.
2. The tests run under coverage; `tests/conftest.py` gives every test file a context
   of its own and notes which repository files it opens (`CD_IMPACT_LOG`).
3. Coverage: when everything runs, `coverage report` measures the whole package
   (the threshold from `pyproject.toml`) and `script/coverage_gate.py` keeps the
   lines outside the measurement by name. When a selection runs, the report
   measures only the changed package files, at 100 % - the selection holds every
   test that executes such a file, so that measurement is complete.
4. Map: what the tests that ran executed and opened belongs in
   `tests/impact_map.json`. In CI the job drops when something is missing (and on a
   full run also when the map names something too many); locally the map is
   updated, and that change belongs in the commit.

`--no-coverage` runs the same selection without coverage and without the map: that
is the job on the oldest supported Home Assistant.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import select_tests as sel  # noqa: E402

ROOT = sel.ROOT
PYTHON = sys.executable


def run(*args: str, env: dict[str, str] | None = None) -> int:
    """Run a command in the repository and return its exit code."""
    print("+", " ".join(args), flush=True)
    return subprocess.run(list(args), cwd=ROOT, env=env).returncode


def executed_by_test_file(coverage_file: Path) -> dict[str, set[str]]:
    """Per test file the package files it executed, from the coverage contexts."""
    from coverage import CoverageData

    data = CoverageData(basename=str(coverage_file))
    data.read()
    found: dict[str, set[str]] = {}
    for measured in data.measured_files():
        relative = Path(measured).resolve().relative_to(ROOT).as_posix()
        contexts: set[str] = set()
        for labels in data.contexts_by_lineno(measured).values():
            contexts.update(labels)
        for context in contexts:
            if context.startswith("tests/"):
                found.setdefault(context, set()).add(relative)
    return found


class Recorded:
    """What one run saw per test file: everything, and the part a map must carry.

    Een pakketbestand dat alleen als tekst geopend werd, telt voor de selectie maar
    niet voor de eis aan de kaart: `linecache` opent zo'n bestand voor een
    waarschuwing of een traceback alleen bij de eerste toets die erom vraagt, dus dat
    hangt af van de volgorde. Wat een toets van het pakket uitvoert komt uit coverage
    en is wel een eis, net als elke map, tekst en elk script dat hij opent.

    A package file that was only opened as text counts for the selection but not for
    the demand on the map: `linecache` opens such a file for a warning or a traceback
    only for the first test that asks, so that depends on the order. What a test
    executes of the package comes from coverage and is a demand, just like every
    directory, text and script it opens.
    """

    def __init__(self) -> None:
        self.inputs: dict[str, set[str]] = {}
        self.required: dict[str, set[str]] = {}

    def add(self, test_file: str, path: str, required: bool) -> None:
        if path == test_file:
            return
        self.inputs.setdefault(test_file, set()).add(path)
        self.required.setdefault(test_file, set())
        if required:
            self.required[test_file].add(path)


def recorded_inputs(coverage_file: Path | None, reads_file: Path) -> Recorded:
    """Per test file everything it executed and opened in this run."""
    found = Recorded()
    try:
        reads = json.loads(reads_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        reads = {}
    for test_file, paths in reads.items():
        for path in paths:
            package_source = path.startswith(sel.PACKAGE) and path.endswith(".py")
            found.add(test_file, path, required=not package_source)
    if coverage_file is not None and coverage_file.is_file():
        for test_file, paths in executed_by_test_file(coverage_file).items():
            for path in paths:
                found.add(test_file, path, required=True)
    return found


def compare_and_keep(recorded: Recorded, full: bool) -> int:
    """Compare this run's inputs with the map; write the map locally, judge it in CI."""
    impact = sel.load_map() or {}
    merged = {} if full else {key: set(value) for key, value in impact.items()}
    for test_file, paths in recorded.inputs.items():
        merged[test_file] = merged.get(test_file, set()) | paths
    missing = {
        test_file: sorted(paths - set(impact.get(test_file, [])))
        for test_file, paths in recorded.required.items()
        if paths - set(impact.get(test_file, []))
    }
    surplus = sorted(set(impact) - set(recorded.inputs)) if full else []
    body = {key: sorted(value) for key, value in sorted(merged.items())}
    text = json.dumps(body, indent=1) + "\n"
    if os.environ.get("CI"):
        artifact = os.environ.get("CD_IMPACT_ARTIFACT")
        if artifact:
            Path(artifact).write_text(text, encoding="utf-8")
        if not sel.MAP.is_file():
            # Zonder kaart draait altijd alles; er valt dan niets te vergelijken.
            # Without a map everything always runs; there is nothing to compare then.
            print("Nog geen tests/impact_map.json: alles gedraaid / no map yet: ran everything.")
            return 0
        if missing or surplus:
            print("De kaart klopt niet met deze run / the map does not match this run:")
            for test_file, paths in sorted(missing.items()):
                print(f"  {test_file} mist / misses: {', '.join(paths[:8])}")
            for test_file in surplus:
                print(f"  {test_file} staat op de kaart maar draaide niet / mapped, did not run")
            print("Draai `script/test` lokaal en commit tests/impact_map.json.")
            return 1
        return 0
    old = sel.MAP.read_text(encoding="utf-8") if sel.MAP.is_file() else ""
    if text != old:
        sel.MAP.write_text(text, encoding="utf-8")
        print("tests/impact_map.json bijgewerkt / updated: commit het mee / commit it along.")
    return 0


def main(argv: list[str]) -> int:
    with_coverage = "--no-coverage" not in argv
    selection, changed = sel.current_selection()
    if selection != sel.ALL and not selection:
        print("Geen toetsen nodig voor deze wijziging / no tests needed for this change.")
        return 0
    full = selection == sel.ALL
    targets = [] if full else list(selection)
    print(f"Selectie / selection: {'ALL' if full else len(targets)} toetsbestanden")
    if not with_coverage:
        return run(PYTHON, "-m", "pytest", "-q", *targets)

    with tempfile.TemporaryDirectory() as scratch:
        reads_file = Path(scratch) / "reads.json"
        env = dict(os.environ, CD_IMPACT_LOG=str(reads_file))
        coverage_file = ROOT / ".coverage"
        status = run(PYTHON, "-m", "coverage", "run", "-m", "pytest", "-q", *targets, env=env)
        if full:
            status = run(PYTHON, "-m", "coverage", "report") or status
            status = run(PYTHON, "script/coverage_gate.py") or status
        else:
            package = sorted(
                path
                for path, state in (changed or {}).items()
                if path.startswith(sel.PACKAGE) and path.endswith(".py") and state != "D"
            )
            if package:
                status = (
                    run(
                        PYTHON,
                        "-m",
                        "coverage",
                        "report",
                        "--fail-under=100",
                        f"--include={','.join(package)}",
                    )
                    or status
                )
        if status == 0:
            status = compare_and_keep(recorded_inputs(coverage_file, reads_file), full)
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
