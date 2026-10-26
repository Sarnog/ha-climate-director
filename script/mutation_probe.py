"""Run each mutation in a throwaway copy of the repo and report what stays green.

Elke mutatie draait in een kopie van de repo, en alleen tegen de toetsen die het
gemuteerde bestand raken (`tests/impact_map.json`, via `script/select_tests.py`);
zonder kaart de volledige suite. Een mutatie draait alleen als haar deel veranderde
(het gemuteerde bestand, een van haar toetsen, of de probe zelf) ten opzichte van
`CD_BASE`; zonder bekende basis draaien ze allemaal. Een mutatie die groen blijft is
een gat: geen enkele test bewaakt die eigenschap. De uitvoer is een lijst van die
gaten; de baan is niet-blokkerend, zodat een gat de rest van de CI niet tegenhoudt,
maar zichtbaar is.

Each mutation runs in a throwaway copy of the repo, and only against the tests that
touch the mutated file (`tests/impact_map.json`, through `script/select_tests.py`);
without a map the full suite. A mutation only runs when its part changed (the
mutated file, one of its tests, or the probe itself) against `CD_BASE`; without a
known base they all run. A mutation that stays green is a hole: no test guards that
property. The output is the list of those holes; the job is non-blocking, so a hole
does not hold up the rest of CI but stays visible.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "script"))
import select_tests as sel  # noqa: E402

MUTATIONS = [
    {
        "name": "passed-over-meldt-alles",
        "file": "custom_components/climate_director/engine/sources.py",
        "old": (
            "not world.climate(source.entity_id).available\n"
            "            or source.entity_id in refused\n"
            "            or source.entity_id in blocked"
        ),
        "new": "True",
    },
    {
        "name": "duits-formeel-weer-toegestaan",
        "file": "custom_components/climate_director/translations/de.json",
        "old": "du ",
        "new": "Sie ",
    },
    {
        "name": "circuitlus-zonder-ondergrens",
        "file": "custom_components/climate_director/engine/decide.py",
        "old": "attempts = max(1, max((len(zone.sources) for zone in config.zones), default=0))",
        "new": "attempts = 0",
    },
    {
        "name": "bron-rusttijd-genegeerd",
        "file": "custom_components/climate_director/engine/decide.py",
        "old": 'circuit = _SOLO if not rest else Circuit("", "", (), True, min_cycle_time=rest)',
        "new": "circuit = _SOLO",
    },
]


def _apply(root: Path, mutation: dict) -> None:
    path = root / mutation["file"]
    text = path.read_text(encoding="utf-8")
    assert mutation["old"] in text, f"{mutation['name']}: patroon niet gevonden"
    path.write_text(text.replace(mutation["old"], mutation["new"], 1), encoding="utf-8")


def tests_for(mutation: dict, impact: dict[str, list[str]] | None) -> list[str]:
    """The test files that touch the mutated file; `[]` means the full suite."""
    chosen = sel.select({mutation["file"]: "M"}, impact)
    return [] if chosen == sel.ALL else list(chosen)


def relevant(mutation: dict, tests: list[str], changed: dict[str, str] | None) -> bool:
    """Return whether the mutation's part changed; without a known base, always."""
    if changed is None or not tests:
        return True
    own = {mutation["file"], "script/mutation_probe.py", *tests}
    return any(path in own or sel.touches_everything(path) for path in changed)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="alleen deze mutaties, komma-gescheiden")
    args = parser.parse_args()
    only = set(args.only.split(",")) if args.only else None

    impact = sel.load_map()
    base = sel.base_ref()
    changed = sel.changed_files(base) if base is not None else None
    uncaught: list[str] = []
    for mutation in MUTATIONS:
        if only and mutation["name"] not in only:
            continue
        tests = tests_for(mutation, impact)
        if not only and not relevant(mutation, tests, changed):
            print(f"{mutation['name']}: overgeslagen, niets veranderd / skipped, nothing changed")
            continue
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            shutil.copytree(
                REPO,
                target,
                ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache"),
            )
            _apply(target, mutation)
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *tests],
                cwd=target,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                uncaught.append(mutation["name"])
                print(f"{mutation['name']}: NIET gevangen")
            else:
                print(f"{mutation['name']}: gevangen")

    if uncaught:
        print("ongedekt: " + ", ".join(uncaught))
    else:
        print("ongedekt: geen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
