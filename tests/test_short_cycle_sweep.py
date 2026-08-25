"""De brede kortcyclusmeting draait mee, in verkorte vorm.

The broad short-cycle measurement runs along, in shortened form.

Het volledige instrument (`measure-short-cycles.py`) meet 400 huizen × 180
minuten en is te traag voor elke testronde; deze test draait dezelfde sweep op
40 huizen, met een vaste seed, zodat de eigenschap breed gemeten wordt zonder
dat iemand eraan hoeft te denken.

The full instrument (`measure-short-cycles.py`) measures 400 houses × 180
minutes and is too slow for every test run; this test runs the same sweep over
40 houses, with a fixed seed, so the property is measured broadly without
anyone having to remember.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

SKILL = (
    pathlib.Path(__file__).resolve().parents[1]
    / ".claude"
    / "skills"
    / "climate-director"
    / "measure-short-cycles.py"
)


@pytest.fixture(scope="module")
def measure():
    """Load the measurement instrument once for this module."""
    spec = importlib.util.spec_from_file_location("measure_short_cycles", SKILL)
    assert spec is not None and spec.loader is not None, f"instrument niet gevonden: {SKILL}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_short_cycle_sweep_stays_green(measure, capsys) -> None:
    """Elk apparaat zonder circuit houdt zijn rusttijd, breed gemeten.

    Every appliance without a circuit keeps its rest time, measured broadly.
    """
    assert measure.main(runs=40, minutes=180, seed=20260825) == 0
    output = capsys.readouterr().out
    assert "FOUT" not in output
