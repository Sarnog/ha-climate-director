"""De engine-grens uit ARCHITECTURE.md wordt bewaakt, niet alleen beloofd.

ARCHITECTURE.md zegt in beide talen: "`engine/` importeert Home Assistant
nergens." / "`engine/` imports Home Assistant nowhere." Dat is de belangrijkste
scheidslijn van het project — de engine is pure Python en daardoor als gewoon
dataobject na te bouwen en in milliseconden te testen zonder draaiende Home
Assistant. Tot nu toe hing die grens aan goed gedrag: geen enkele test wordt
rood zodra er toch een import in sluipt. Deze bewaking loopt met `ast.walk` over
élk bestand onder `custom_components/climate_director/engine/` en eist nul
`Import`/`ImportFrom` naar `homeassistant` — op modulehoogte én binnen een
functie, want `ast.walk` ziet beide. Ze merkt het ook wanneer de scan niets te
scannen vindt: een lege bestandenlijst is een fout, geen groene test. Zonder
deze docstring haalt een volgende ronde haar weg als "die importeert toch
niets".

The engine border from ARCHITECTURE.md is guarded, not just promised.
ARCHITECTURE.md says in both languages: "`engine/` imports Home Assistant
nowhere." / "`engine/` importeert Home Assistant nergens." That is the most
important border of the project — the engine is pure Python and therefore
reproducible as a plain data object and testable in milliseconds without a
running Home Assistant. Until now that border rested on good behaviour: no test
turns red the moment an import slips in. This guard walks every file under
`custom_components/climate_director/engine/` with `ast.walk` and requires zero
`Import`/`ImportFrom` of `homeassistant` — at module level and inside a
function, because `ast.walk` sees both. It also notices when the scan finds
nothing to scan: an empty file list is an error, not a green test. Without this
docstring a future round would remove it as "it imports nothing anyway".
"""

from __future__ import annotations

import ast
from pathlib import Path

ENGINE_ROOT = (
    Path(__file__).resolve().parents[1] / "custom_components" / "climate_director" / "engine"
)


def _homeassistant_imports(path: Path) -> list[tuple[int, str]]:
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
        for lineno, text in _homeassistant_imports(path):
            offenders.append(f"{path.relative_to(root).as_posix()}:{lineno}: {text}")
    return offenders


def test_the_engine_imports_home_assistant_nowhere() -> None:
    offenders = border_offenders()
    assert not offenders, (
        "engine/ importeert Home Assistant; dat is de scheidslijn uit ARCHITECTURE.md:\n"
        + "\n".join(offenders)
    )
