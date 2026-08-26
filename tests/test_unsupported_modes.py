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
from homeassistant.util.unit_system import IMPERIAL_SYSTEM, METRIC_SYSTEM

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
        assert home.coordinator._unsupported_since == {}


class TestTheSameApplianceInTwoRoles:
    async def test_the_cool_role_in_the_second_zone_is_checked(self) -> None:
        """Hetzelfde apparaat, twee zones, twee rollen: beide rollen tellen.

        The same appliance, two zones, two roles: both roles count.
        """
        installation = {
            "zones": [
                zone(
                    "woonkamer",
                    sources=[source("wk_heat", LIVING, role="heat_only")],
                    indoor_sensor="sensor.woonkamer",
                    heat=settings(21.0, 20.0),
                ),
                zone(
                    "zolder",
                    sources=[source("z_airco", LIVING, role="heat_cool")],
                    indoor_sensor="sensor.zolder",
                    heat=settings(21.0, 20.0),
                    cool=settings(23.0, 24.0),
                ),
            ],
            "outdoor_sensor": "sensor.buiten",
        }
        live = await start_house(installation, states=world())
        try:
            await live.evaluate()
            await age(live, 10)
            issue = issue_for(live)
            assert issue is not None
            placeholders = issue.translation_placeholders or {}
            assert "cool" in placeholders["entities"]
        finally:
            await stop_house(live)


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


class TestTheNoticeNamesTheUsersUnit:
    """De reparatiemelding noemt de eenheid waarin de gebruiker rekent.

    The repair notice names the unit the user counts in.
    """

    def _installation(self) -> dict[str, Any]:
        return {
            "zones": [
                zone(
                    "woonkamer",
                    sources=[source("woonkamer_airco", LIVING, role="heat_only")],
                    indoor_sensor="sensor.woonkamer",
                    heat=settings(21.0, 20.0),
                )
            ],
            "outdoor_sensor": "sensor.buiten",
        }

    def _states(self, unit: str, max_temp: float) -> dict[str, tuple[str, dict[str, Any]]]:
        return {
            "sensor.woonkamer": ("18.0", {"unit_of_measurement": unit}),
            "sensor.buiten": ("4.0", {"unit_of_measurement": unit}),
            LIVING: ("off", {"hvac_modes": ["heat", "off"], "max_temp": max_temp}),
        }

    @pytest.mark.parametrize(
        ("unit_system", "max_temp", "expected"),
        [
            (IMPERIAL_SYSTEM, 61.0, "heat 70.0 °F > 61.0 °F"),
            (METRIC_SYSTEM, 16.0, "heat 21.0 °C > 16.0 °C"),
        ],
    )
    async def test_the_setpoint_complaint_names_the_unit(
        self, unit_system, max_temp: float, expected: str
    ) -> None:
        """21 °C is 70 °F; het apparaat meldt een maximum dat lager ligt.

        De melding hoort de eenheid van de gebruiker te noemen, afgerond, in
        plaats van een kale graad met de engine-waarde erin.

        21 °C is 70 °F; the appliance reports a maximum below that. The notice
        should name the user's unit, rounded, rather than a bare degree with
        the engine value in it.
        """
        live = await start_house(
            self._installation(),
            states=self._states(unit_system.temperature_unit, max_temp),
            unit_system=unit_system,
        )
        try:
            await live.evaluate()
            await age(live, 10)
            issue = issue_for(live)
            assert issue is not None
            placeholders = issue.translation_placeholders or {}
            assert expected in placeholders["entities"]
        finally:
            await stop_house(live)
