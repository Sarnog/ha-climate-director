"""Sessiebrede dekkingsbewaking voor formulieren.

Session-wide coverage guard for forms.

`conftest.py` houdt tijdens de run bij welke formulieren van deze integratie
werkelijk getekend worden. Deze test — bewust als laatste bestand verzameld,
want pytest verzamelt alfabetisch — houdt die verzameling aan het eind van de
run tegen de bron: élk `async_show_form(step_id=...)` in de integratie hoort
minstens één keer getekend te zijn, anders faalt de suite en noemt hij de
ontbrekende step_id's bij naam.

De bewaking is per definitie volgorde- en selectiegevoelig. Een gedeeltelijke
run tekent niet elk formulier, en zou de test vals rood laten staan; daarom
slaat hij over zodra de run niet compleet is, met de reden in het skipbericht.

`conftest.py` records during the run which of this integration's forms are
really drawn. This test — deliberately collected last, since pytest collects
alphabetically — holds that set against the source at the end of the run:
every `async_show_form(step_id=...)` in the integration must have been drawn at
least once, otherwise the suite fails and names the missing step ids.

The guard is by definition order- and selection-sensitive. A partial run does
not draw every form and would make the test falsely red; it therefore skips
whenever the run is not complete, with the reason in the skip message.
"""

from __future__ import annotations

import pytest
from conftest import DRAWN_FORMS, coverage_skip_reason, integration_forms


def test_every_form_in_the_source_is_drawn(request: pytest.FixtureRequest) -> None:
    """Elke step_id uit de bron is door minstens één test getekend.

    Every step id from the source has been drawn by at least one test.
    """
    reason = coverage_skip_reason(request.session)
    if reason is not None:
        pytest.skip(f"dekkingsbewaking overgeslagen: {reason}")

    missing = integration_forms() - DRAWN_FORMS
    assert not missing, (
        "deze formulieren uit de bron zijn door geen enkele test getekend: "
        f"{sorted(name for _module, name in missing)}"
    )
