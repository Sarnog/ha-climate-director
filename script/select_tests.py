"""Welke toetsen horen bij deze wijziging, en draai alleen die.

Which tests belong to this change, and run only those.

Een toets draait alleen als er iets veranderd is in het deel dat hij toetst. Wat
dat deel is, staat in `tests/impact_map.json`: per toetsbestand de bestanden van
de repo die hij **bij het draaien** uitvoerde (de pakketcode, gemeten met
coverage, met per toetsbestand een eigen context) en opende (een tekstbestand, een
vertaling, een gids, een script, en de mappen die hij doorliep). De kaart komt dus
uit de runtime en niet uit de spelling van de toets: een toets die een gids leest,
staat bij die gids, hoe hij het pad ook opbouwt. Daarnaast telt elke pakketmodule
die een toetsbestand rechtstreeks importeert, omdat code op moduleniveau maar één
keer draait, bij de eerste die hem importeert.

Alles draait als de kaart ontbreekt, als de basis onbekend is, als een toetsbestand
verdwijnt, of als er iets verandert dat elke toets raakt (`ALL_TRIGGERS` en de
hulpbestanden in `tests/` die geen `test_*.py` zijn). Elke run meet de invoer van de
toetsen die hij draaide opnieuw en vergelijkt die met de kaart: in de CI valt de
baan als de kaart iets mist, lokaal wordt de kaart bijgewerkt. Zo kan een toets die
iets nieuws gaat lezen niet ongemerkt uit de selectie vallen.

Gebruik:
    python script/select_tests.py          # toon de selectie (ALL, niets, of bestanden)
    python script/select_tests.py changes  # CI: schrijf de vlaggen naar $GITHUB_OUTPUT
    python script/run_tests.py             # draai de selectie (zie dat script)

De basis is `CD_BASE` (de CI zet daar de commit vóór de push of de basis van de pull
request). Lokaal is dat leeg, en dan is de basis `@{upstream}`: alles wat nog niet
gepusht is, plus de werkboom.

A test only runs when something changed in the part it tests. That part lives in
`tests/impact_map.json`: per test file the repository files it **executed while
running** (the package code, measured with coverage, with a context of its own per
test file) and opened (a text file, a translation, a guide, a script, and the
directories it walked). The map thus comes from the runtime and not from the
spelling of the test: a test that reads a guide stands with that guide, however it
builds the path. On top of that every package module a test file imports directly
counts, since module-level code runs only once, for whoever imports it first.

Everything runs when the map is missing, when the base is unknown, when a test file
disappears, or when something changes that touches every test (`ALL_TRIGGERS` and
the helper files in `tests/` that are not `test_*.py`). Every run measures the input
of the tests it ran again and compares it with the map: in CI the job drops when the
map misses something, locally the map is updated. That way a test that starts to
read something new cannot drop out of the selection unnoticed.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAP = ROOT / "tests" / "impact_map.json"
PACKAGE = "custom_components/climate_director/"

#: Een wijziging hier raakt elke toets: de toetsomgeving, de afhankelijkheden, de
#: kaart en de selectie zelf, en de baan die alles draait.
#: A change here touches every test: the test environment, the dependencies, the
#: map and the selection itself, and the job that runs it all.
ALL_TRIGGERS = frozenset(
    {
        "pyproject.toml",
        "requirements_test.txt",
        "script/select_tests.py",
        "script/run_tests.py",
        "script/coverage_gate.py",
        ".github/workflows/tests.yaml",
    }
)

#: De opname zelf: verandert een van deze, dan meet een run anders dan de run die de
#: kaart maakte (`script/run_tests.py`, `compare_and_keep`).
#: The recording itself: when one of these changes, a run measures differently from
#: the run that made the map (`script/run_tests.py`, `compare_and_keep`).
RECORDING = frozenset(
    {
        "tests/impact_recorder.py",
        "tests/conftest.py",
        "script/run_tests.py",
        "script/select_tests.py",
    }
)

#: Pakketbestanden waarvoor mypy draait, naast de pakketcode zelf.
#: Files that make mypy run, beside the package code itself.
MYPY_TRIGGERS = frozenset(
    {"pyproject.toml", "requirements_test.txt", ".github/workflows/tests.yaml"}
)

ALL = "ALL"


def git(*args: str) -> str:
    """Run git in the repository and return its output."""
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout


def known_commit(ref: str) -> bool:
    """Return whether `ref` names a commit this checkout has."""
    if not ref or set(ref) == {"0"}:
        return False
    found = subprocess.run(
        ["git", "cat-file", "-e", f"{ref}^{{commit}}"], cwd=ROOT, capture_output=True
    )
    return found.returncode == 0


def base_ref() -> str | None:
    """The commit to compare with, or `None` when that is unknown (then all runs)."""
    if "CD_BASE" in os.environ:
        base = os.environ["CD_BASE"].strip()
        return base if known_commit(base) else None
    upstream = subprocess.run(
        ["git", "rev-parse", "--verify", "-q", "@{upstream}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return upstream if known_commit(upstream) else None


def parse_name_status(output: str) -> dict[str, str]:
    """Map each path in `git diff --name-status --no-renames` output to its letter.

    Met `--no-renames` is een hernoeming een `D` plus een `A`, dus elke regel is
    `<letter><tab><pad>`.

    With `--no-renames` a rename is a `D` plus an `A`, so every line is
    `<letter><tab><path>`.
    """
    found: dict[str, str] = {}
    for line in output.splitlines():
        status, _, path = line.partition("\t")
        if path:
            found[path] = status[:1]
    return found


def changed_files(base: str) -> dict[str, str]:
    """Map each changed path to its status letter (`A`, `M`, `D`, ...).

    Buiten de CI tellen de werkboom en de nog niet gevolgde bestanden mee.

    Outside CI the working tree and the untracked files count too.
    """
    found = parse_name_status(git("diff", "--name-status", "--no-renames", base, "HEAD"))
    if not os.environ.get("CI"):
        found.update(parse_name_status(git("diff", "--name-status", "--no-renames", "HEAD")))
        for path in git("ls-files", "--others", "--exclude-standard").splitlines():
            found[path] = "A"
    return found


def load_map(path: Path | None = None) -> dict[str, list[str]] | None:
    """The impact map, or `None` when it is missing or unreadable."""
    try:
        data = json.loads((path or MAP).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def is_test_file(path: str) -> bool:
    """Return whether `path` is a test module."""
    return (
        path.startswith("tests/") and Path(path).name.startswith("test_") and path.endswith(".py")
    )


def touches_everything(path: str) -> bool:
    """Return whether a change to `path` makes every test run."""
    if path in ALL_TRIGGERS:
        return True
    return (
        path.startswith("tests/")
        and path.endswith(".py")
        and "/" not in path[len("tests/") :]
        and not Path(path).name.startswith("test_")
    )


def direct_imports(test_file: str, root: Path | None = None) -> set[str]:
    """The package modules a test file imports by name, as repository paths."""
    root = root or ROOT
    try:
        tree = ast.parse((root / test_file).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return set()
    found: set[str] = set()
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
            names.extend(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
    for name in names:
        if not name.startswith("custom_components.climate_director"):
            continue
        base = name.replace(".", "/")
        for candidate in (f"{base}.py", f"{base}/__init__.py"):
            if (root / candidate).is_file():
                found.add(candidate)
    return found


def select(changed: dict[str, str], impact: dict[str, list[str]] | None) -> str | list[str]:
    """Return `ALL`, or the sorted test files that belong to `changed`."""
    if impact is None:
        return ALL
    chosen: set[str] = set()
    for path, status in changed.items():
        if touches_everything(path):
            return ALL
        if is_test_file(path):
            if status == "D":
                return ALL
            # De toets zelf, en verderop wie hem leest (de bewakingen op de toetsen).
            # The test itself, and further down whoever reads it (the test guards).
            chosen.add(path)
        parent = path.rsplit("/", 1)[0] + "/" if "/" in path else "./"
        for test_file, inputs in impact.items():
            imported = path.startswith(PACKAGE) and path in direct_imports(test_file)
            if path in inputs or parent in inputs or imported:
                chosen.add(test_file)
    return sorted(test for test in chosen if (ROOT / test).is_file())


def needs_mypy(changed: Iterable[str]) -> bool:
    """Return whether the change touches what mypy checks."""
    return any(
        (path.startswith(PACKAGE) and path.endswith(".py")) or path in MYPY_TRIGGERS
        for path in changed
    )


def needs_lint(changed: Iterable[str]) -> bool:
    """Return whether the change touches something ruff reads."""
    return any(path.endswith((".py", ".toml")) for path in changed)


def current_selection() -> tuple[str | list[str], dict[str, str] | None]:
    """The selection for this checkout, and the changes it came from."""
    base = base_ref()
    if base is None:
        return ALL, None
    changed = changed_files(base)
    return select(changed, load_map()), changed


def main(argv: list[str]) -> int:
    selection, changed = current_selection()
    if argv[:1] == ["changes"]:
        files = list(changed or {})
        flags = {
            "tests": selection == ALL or bool(selection) or needs_lint(files),
            "mypy": changed is None or needs_mypy(files),
        }
        lines = [f"{key}={'true' if value else 'false'}" for key, value in flags.items()]
        output = os.environ.get("GITHUB_OUTPUT")
        if output:
            with open(output, "a", encoding="utf-8") as handle:
                handle.write("\n".join(lines) + "\n")
        print("\n".join(lines))
        print("selectie / selection:", selection if selection == ALL else len(selection))
        return 0
    if selection == ALL:
        print(ALL)
    else:
        print("\n".join(selection))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
