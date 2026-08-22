"""Een rol die een stand vraagt die het apparaat niet kan, hoort onder Reparaties.

A role asking a mode the appliance cannot run belongs under Repairs.

Een bron met rol HEAT_COOL op een apparaat dat alleen `heat` en `off` meldt,
wordt voor koelen overgeslagen. De zone doet dan in stilte niets - precies de
klasse fout waar de onleesbare-entiteitenmelding voor bestaat. Er zit dezelfde
wachttijd op: een apparaat dat bij een herstart even niets meldt is geen
instelfout.

A source with role HEAT_COOL on an appliance reporting only `heat` and `off` is
skipped for cooling. The zone then silently does nothing - exactly the class of
fault the unreadable-entities notice exists for. It carries the same settling
time: an appliance briefly reporting nothing during a restart is no
configuration mistake.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from harness_live import LiveHome, settings, source, start_house, stop_house, zone
from homeassistant.helpers import issue_registry as ir

from custom_components.climate_director.const import DOMAIN

LIVING = "climate.woonkamer"


def installation() -> dict[str, Any]:
    return {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("woonkamer_airco", LIVING, role="heat_cool")],
                indoor_sensor="sensor.woonkamer",
                heat=settings(21.0, 20.0),
            )
        ],
        "outdoor_sensor": "sensor.buiten",
    }


def world() -> dict[str, tuple[str, dict[str, Any]]]:
    return {
        "sensor.woonkamer": ("18.0", {}),
        "sensor.buiten": ("4.0", {}),
        LIVING: ("off", {"hvac_modes": ["heat", "off"]}),
    }


@pytest.fixture
async def home():
    live = await start_house(installation(), states=world())
    try:
        yield live
    finally:
        await stop_house(live)


def issue_for(live: LiveHome):
    """Return the unsupported-modes notice for this installation, if it stands."""
    registry = ir.async_get(live.hass)
    return registry.async_get_issue(DOMAIN, f"unsupported_modes_{live.entry.entry_id}")


async def age(live: LiveHome, minutes: float) -> None:
    """Let the coordinator believe that much time has passed, and decide again."""
    from homeassistant.util import dt as dt_util

    from custom_components.climate_director import coordinator as module

    moved = dt_util.now() + timedelta(minutes=minutes)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(module.dt_util, "now", lambda: moved)
        await live.evaluate()


class TestARoleAskingAnImpossibleMode:
    async def test_a_short_mismatch_reports_nothing_yet(self, home: LiveHome) -> None:
        await home.evaluate()
        assert issue_for(home) is None

    async def test_a_lasting_mismatch_is_reported(self, home: LiveHome) -> None:
        await home.evaluate()
        await age(home, 10)
        issue = issue_for(home)
        assert issue is not None
        assert issue.translation_key == "unsupported_modes"

    async def test_the_notice_names_the_appliance(self, home: LiveHome) -> None:
        await home.evaluate()
        await age(home, 10)
        issue = issue_for(home)
        assert issue is not None
        placeholders = issue.translation_placeholders or {}
        assert LIVING in placeholders["entities"]
        assert placeholders["count"] == "1"

    async def test_it_clears_once_the_appliance_reports_the_mode(self, home: LiveHome) -> None:
        await home.evaluate()
        await age(home, 10)
        assert issue_for(home) is not None

        home.set(LIVING, "off", hvac_modes=["heat", "cool", "off"])
        await home.evaluate()
        assert issue_for(home) is None


class TestTearingDown:
    async def test_unloading_takes_the_notice_with_it(self) -> None:
        live = await start_house(installation(), states=world(), entry_id="afbreken")
        await live.evaluate()
        await age(live, 10)
        assert issue_for(live) is not None

        await live.hass.config_entries.async_unload(live.entry.entry_id)
        await live.hass.async_block_till_done()
        assert issue_for(live) is None
        await stop_house(live)
