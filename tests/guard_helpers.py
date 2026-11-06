"""Hulpjes voor de grensbewaking: welke Home Assistant-imports staan waar.

Helpers for the border guard: which Home Assistant imports stand where."""

from __future__ import annotations

import ast
from pathlib import Path

ENGINE_ROOT = (
    Path(__file__).resolve().parents[1] / "custom_components" / "climate_director" / "engine"
)


def homeassistant_imports(path: Path) -> list[tuple[int, str]]:
    """Elke `homeassistant`-import in `path`, als (regelnummer, tekst).

    Every `homeassistant` import in `path`, as (line number, text).
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "homeassistant" or alias.name.startswith("homeassistant."):
                    found.append((node.lineno, f"import {alias.name}"))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "homeassistant" or module.startswith("homeassistant."):
                found.append((node.lineno, f"from {module} import ..."))
    return found


def border_offenders(root: Path | None = None) -> list[str]:
    """Geef elke `homeassistant`-import onder `root`, één leesbare regel per plek.

    `root` is standaard de echte `engine/`-map. De bestanden worden eerst in een
    lijst verzameld en die lijst MOET niet leeg zijn: resolveert het pad niet
    meer — bijvoorbeeld omdat een herstructurering `engine/` heeft verplaatst —
    dan scant de bewaking stilletjes niets en staat ze groen te wezen terwijl ze
    niets bewaakt. Die assertie hoort nooit af te gaan, en juist daarom is hij
    onmisbaar; haal hem niet weg als dode code. De melding noemt het pad
    relatief tegen `root`, zodat twee gelijknamige bestanden in verschillende
    submappen uit elkaar te houden zijn.

    Return every `homeassistant` import under `root`, one readable line each.

    `root` defaults to the real `engine/` directory. The files are collected in
    a list first and that list MUST not be empty: if the path no longer resolves
    — for instance because a restructuring moved `engine/` — the guard silently
    scans nothing and sits there green while guarding nothing. That assertion
    should never fire, and that is exactly why it is indispensable; do not
    remove it as dead code. The message names the path relative to `root`, so
    two files with the same name in different subdirectories stay
    distinguishable.
    """
    if root is None:
        root = ENGINE_ROOT
    files = sorted(root.rglob("*.py"))
    assert files, f"engine-grensbewaking: geen bestanden gevonden onder {root}"
    offenders: list[str] = []
    for path in files:
        for lineno, text in homeassistant_imports(path):
            offenders.append(f"{path.relative_to(root).as_posix()}:{lineno}: {text}")
    return offenders
