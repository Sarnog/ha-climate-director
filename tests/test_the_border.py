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

from guard_helpers import border_offenders


def test_the_engine_imports_home_assistant_nowhere() -> None:
    offenders = border_offenders()
    assert not offenders, (
        "engine/ importeert Home Assistant; dat is de scheidslijn uit ARCHITECTURE.md:\n"
        + "\n".join(offenders)
    )
