"""De brede kortcyclusmeting draait mee, in verkorte vorm.

The broad short-cycle measurement runs along, in shortened form.

Het volledige instrument (`tests/measure_short_cycles.py`) meet 400 huizen ×
180 minuten en is te traag voor elke testronde; deze test draait dezelfde sweep
op 40 huizen, met een vaste seed, zodat de eigenschap breed gemeten wordt
zonder dat iemand eraan hoeft te denken.

The full instrument (`tests/measure_short_cycles.py`) measures 400 houses ×
180 minutes and is too slow for every test run; this test runs the same sweep
over 40 houses, with a fixed seed, so the property is measured broadly without
anyone having to remember.
"""

from __future__ import annotations

from measure_short_cycles import main


def test_the_short_cycle_sweep_stays_green(capsys) -> None:
    """Elk apparaat zonder circuit houdt zijn rusttijd, breed gemeten.

    Every appliance without a circuit keeps its rest time, measured broadly.
    """
    assert main(runs=40, minutes=180, seed=20260825) == 0
    output = capsys.readouterr().out
    assert "FOUT" not in output
