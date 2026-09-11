"""De reparatiemelding voor een overbrugde open opening loopt de hele keten.

The repair notice for a bypassed open opening runs the whole chain.

`test_opening_bypass.py` dekt de eigenschap van de vlag in de engine, maar geen
enkele test riep `coordinator._report_bypassed_openings` of
`problems.async_report_bypassed_openings` aan: de mutatie
`if False and opening_bypassed_and_open(...)` in `_report_bypassed_openings`
liet de volledige suite groen. Dit bestand pint de keten vast in het live
harnas, met de échte `issue_registry`: overbrugging aan + opening open geeft de
melding met de placeholders, opening dicht óf schakelaar uit haalt hem weg, en
na een herstart komt hij terug zolang beide nog aanstaan.

`test_opening_bypass.py` covers the flag's property in the engine, but no test
called `coordinator._report_bypassed_openings` or
`problems.async_report_bypassed_openings`: the mutation
`if False and opening_bypassed_and_open(...)` in `_report_bypassed_openings`
left the full suite green. This file pins the chain down in the live harness,
against the real `issue_registry`: bypass on + opening open raises the notice
with its placeholders, closing the opening or turning the switch off takes it
away, and after a restart it comes back for as long as both still hold.
"""

from __future__ import annotations

from typing import Any

import pytest
from harness_live import LiveHome, settings, source, start_house, stop_house, zone
from homeassistant.helpers import issue_registry as ir

from custom_components.climate_director.const import DOMAIN

BACK_DOOR = "binary_sensor.achterdeur"


def installation() -> dict[str, Any]:
    """Return a single-zone house whose back door can be bypassed."""
    return {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("woonkamer_ketel", "climate.woonkamer")],
                indoor_sensor="sensor.woonkamer",
                heat=settings(21.0, 20.0),
            )
        ],
        "outdoor_sensor": "sensor.buiten",
        "openings": [
            {
                "entity_id": BACK_DOOR,
                "opening_id": "achterdeur",
                "name": "Achterdeur",
                "zone_ids": ["woonkamer"],
                "open_state": "on",
                "delay": 0,
            }
        ],
    }


def world(*, opening: str = "on") -> dict[str, tuple[str, dict[str, Any]]]:
    """Return a settled house; the room is warm enough to leave the boiler off."""
    return {
        "sensor.woonkamer": ("21.0", {}),
        "sensor.buiten": ("4.0", {}),
        "climate.woonkamer": ("off", {"hvac_modes": ["heat", "off"]}),
        BACK_DOOR: (opening, {}),
    }


def issue_for(home: LiveHome):
    """Return the bypassed-openings notice for this installation, if it stands."""
    registry = ir.async_get(home.hass)
    return registry.async_get_issue(DOMAIN, f"bypassed_openings_{home.entry.entry_id}")


async def bypass_on(home: LiveHome) -> None:
    """Turn the bypass switch on and decide once, deterministically."""
    await home.call("switch", "turn_on", {"entity_id": home.by_key("opening_achterdeur_bypass")})
    await home.evaluate()


@pytest.fixture
async def home() -> LiveHome:
    live = await start_house(installation(), states=world())
    try:
        yield live
    finally:
        await stop_house(live)


class TestTheBypassedOpeningsNotice:
    async def test_a_bypassed_open_opening_is_reported_in_the_real_registry(
        self, home: LiveHome
    ) -> None:
        assert issue_for(home) is None

        await bypass_on(home)

        issue = issue_for(home)
        assert issue is not None
        assert issue.translation_key == "bypassed_openings"
        placeholders = issue.translation_placeholders or {}
        assert placeholders["name"] == home.entry.title
        assert placeholders["count"] == "1"
        assert BACK_DOOR in placeholders["openings"]
        assert "Achterdeur" in placeholders["openings"]

    @pytest.mark.parametrize("way", ["close_opening", "switch_off"])
    async def test_the_notice_goes_when_either_side_falls_away(
        self, home: LiveHome, way: str
    ) -> None:
        await bypass_on(home)
        assert issue_for(home) is not None

        if way == "close_opening":
            home.set(BACK_DOOR, "off")
        else:
            await home.call(
                "switch", "turn_off", {"entity_id": home.by_key("opening_achterdeur_bypass")}
            )
        await home.evaluate()

        assert issue_for(home) is None


class TestAcrossARestart:
    async def test_the_notice_comes_back_while_both_sides_still_hold(self) -> None:
        live = await start_house(installation(), states=world(), entry_id="bypass_restart")
        config_dir = live.config_dir
        try:
            await bypass_on(live)
            assert issue_for(live) is not None
        finally:
            await stop_house(live)

        again = await start_house(
            installation(),
            states=world(),
            entry_id="bypass_restart",
            config_dir=config_dir,
        )
        try:
            await again.evaluate()
            issue = issue_for(again)
            assert issue is not None
            assert issue.translation_key == "bypassed_openings"
        finally:
            await stop_house(again)
