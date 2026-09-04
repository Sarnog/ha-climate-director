"""De engine-grens uit ARCHITECTURE.md wordt bewaakt, niet alleen beloofd.

ARCHITECTURE.md zegt in beide talen: "`engine/` importeert Home Assistant
nergens." / "`engine/` imports Home Assistant nowhere." Dat is de belangrijkste
scheidslijn van het project — de engine is pure Python en daardoor als gewoon
dataobject na te bouwen en in milliseconden te testen zonder draaiende Home
Assistant. Tot nu toe hing die grens aan goed gedrag: geen enkele test wordt
rood zodra er toch een import in sluipt. Deze bewaking loopt met `ast.walk` over
élk bestand onder `custom_components/climate_director/engine/` en eist nul
`Import`/`ImportFrom` naar `homeassistant` — op modulehoogte én binnen een
functie, want `ast.walk` ziet beide. Zonder deze docstring haalt een volgende
ronde hem weg als "die importeert toch niets".

The engine border from ARCHITECTURE.md is guarded, not just promised.
ARCHITECTURE.md says in both languages: "`engine/` imports Home Assistant
nowhere." / "`engine/` importeert Home Assistant nergens." That is the most
important border of the project — the engine is pure Python and therefore
reproducible as a plain data object and testable in milliseconds without a
running Home Assistant. Until now that border rested on good behaviour: no test
turns red the moment an import slips in. This guard walks every file under
`custom_components/climate_director/engine/` with `ast.walk` and requires zero
`Import`/`ImportFrom` of `homeassistant` — at module level and inside a
function, because `ast.walk` sees both. Without this docstring a future round
would remove it as "it imports nothing anyway".
"""

from __future__ import annotations

import ast
from pathlib import Path

ENGINE_ROOT = (
    Path(__file__).resolve().parents[1] / "custom_components" / "climate_director" / "engine"
)


def _homeassistant_imports(path: Path) -> list[str]:
    """Elke `homeassistant`-import in `path`, met regelnummer.

    Every `homeassistant` import in `path`, with line number.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "homeassistant" or alias.name.startswith("homeassistant."):
                    found.append(f"{path.name}:{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "homeassistant" or module.startswith("homeassistant."):
                found.append(f"{path.name}:{node.lineno}: from {module} import ...")
    return found


def test_the_engine_imports_home_assistant_nowhere() -> None:
    offenders: list[str] = []
    for path in sorted(ENGINE_ROOT.rglob("*.py")):
        offenders.extend(_homeassistant_imports(path))
    assert not offenders, (
        "engine/ importeert Home Assistant; dat is de scheidslijn uit ARCHITECTURE.md:\n"
        + "\n".join(offenders)
    )
