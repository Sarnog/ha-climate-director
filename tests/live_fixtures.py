"""Gedeelde fixtures voor de toetsen in een echte Home Assistant.

Shared fixtures for the tests inside a real Home Assistant.

De plugin wordt per toetsbestand geladen met `pytest_plugins = ["live_fixtures"]
pytestmark = pytest.mark.usefixtures("appliance")`.
Zo blijft de autouse-fixture voor de nagebouwde apparaten bij de live-toetsen en
raakt hij de engine-toetsen niet.

The plugin is loaded per test file with `pytest_plugins = ["live_fixtures"]
pytestmark = pytest.mark.usefixtures("appliance")`.
That keeps the autouse fixture for the stand-in appliances with the live tests
and leaves the engine tests untouched.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from harness_live import start_house, stop_house
from live_helpers import cold_two_rooms, two_zone_installation

from custom_components.climate_director import coordinator as coordinator_module


@pytest.fixture(params=["obedient", "stubborn"])
def appliance(request, monkeypatch):
    """Run every test against both appliance kinds the harness knows."""
    import harness_live

    monkeypatch.setattr(harness_live, "DEFAULT_APPLIANCE", request.param)


@pytest.fixture
async def home():
    """Return a running two-zone house that wants heat, torn down afterwards."""
    live = await start_house(two_zone_installation(), states=cold_two_rooms())
    try:
        yield live
    finally:
        await stop_house(live)


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch):
    """Return a handle that moves the integration's clock forward.

    Alleen de klok van de integratie schuift op; de tijdstempels van de
    entiteiten blijven staan waar Home Assistant ze zette. Dat is precies wat
    verstrijken van tijd betekent voor de vertragingen in deze integratie.

    Only the integration's clock moves; the entities' timestamps stay where Home
    Assistant put them. That is exactly what elapsed time means for this
    integration's delays.
    """
    from homeassistant.util import dt as dt_util

    real = dt_util.now
    shift = {"by": timedelta()}

    def _now():
        return real() + shift["by"]

    monkeypatch.setattr(coordinator_module.dt_util, "now", _now)

    class Handle:
        def advance(self, **kwargs) -> None:
            shift["by"] += timedelta(**kwargs)

    return Handle()
