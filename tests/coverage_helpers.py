"""Hulpjes voor de dekkingsmeting: welke regels vallen buiten de telling.

Helpers for the coverage measurement: which lines fall outside the count.
"""

from __future__ import annotations

from pathlib import Path

from coverage import Coverage

import script.coverage_gate as coverage_gate

PACKAGE = Path(__file__).resolve().parents[1] / "custom_components" / "climate_director"


def named_exclusion_problems() -> list[str]:
    """Return the lines the measurement hides without a name, if any.

    De meting heeft geen gegevensbestand nodig: wat coverage uitsluit hangt aan
    het bestand en het patroon, niet aan wat er gedraaid is. `data_file=None`
    houdt de bestaande `.coverage` buiten beeld.

    The measurement needs no data file: what coverage excludes hangs on the file
    and the pattern, not on what ran. `data_file=None` keeps the existing
    `.coverage` out of the picture.
    """
    hidden = coverage_gate.hidden_lines(Coverage(data_file=None), PACKAGE)
    assert hidden, "de meting sluit geen enkele regel uit, dus deze helper meet niets"
    return coverage_gate.exclusion_problems(hidden, PACKAGE)
