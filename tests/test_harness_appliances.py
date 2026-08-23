"""De twee apparaattypen van het harnas, en wat ze verschillend doen.

The harness's two appliance kinds, and what they do differently.

Het oude harnas kende maar één type: elke aanroep werd meteen en volledig
teruggeschreven. Echte integraties doen dat niet allemaal - melcloud verzet de
stand niet via `set_temperature`, en Home Assistant weigert een setpoint buiten
het bereik van het apparaat. Die verschillen zitten nu in het harnas, zodat de
campagnes tegen beide typen kunnen draaien.

The old harness knew only one kind: every call was written straight back, in
full. Real integrations do not all do that - melcloud does not move the mode
through `set_temperature`, and Home Assistant refuses a setpoint outside the
appliance's range. Those differences now live in the harness, so the campaigns
can run against both kinds.
"""

from __future__ import annotations

from typing import Any

import pytest
from harness_live import settings, source, start_house, stop_house, zone
from homeassistant.exceptions import ServiceValidationError

from custom_components.climate_director.const import CONF_INSTALLATION

LIVING = "climate.woonkamer"


def installation() -> dict[str, Any]:
    """Return a one-room installation that wants heat."""
    return {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("airco", LIVING, role="heat_cool")],
                heat=settings(21.0, 20.0),
            )
        ]
    }


def cold() -> dict[str, tuple[str, dict[str, Any]]]:
    """Return a cold room and an idle appliance."""
    return {"sensor.woonkamer": ("18.0", {}), LIVING: ("off", {})}


async def test_the_obedient_kind_moves_the_mode_through_set_temperature() -> None:
    """Het oude gedrag: stand en setpoint in één aanroep, en de stand komt aan."""
    home = await start_house(installation(), states=cold(), appliance="obedient")
    try:
        await home.call(
            "climate",
            "set_temperature",
            {"entity_id": LIVING, "temperature": 21.0, "hvac_mode": "heat"},
        )
        assert home.state(LIVING) == "heat"
        assert home.attributes(LIVING)["temperature"] == 21.0
    finally:
        await stop_house(home)


async def test_the_stubborn_kind_ignores_the_mode_in_set_temperature() -> None:
    """Zoals melcloud: `set_temperature` verzet het setpoint, niet de stand."""
    home = await start_house(installation(), states=cold(), appliance="stubborn")
    try:
        await home.call(
            "climate",
            "set_temperature",
            {"entity_id": LIVING, "temperature": 21.0, "hvac_mode": "heat"},
        )
        assert home.state(LIVING) == "off", "de stand hoort niet via set_temperature te gaan"
        assert home.attributes(LIVING)["temperature"] == 21.0
    finally:
        await stop_house(home)


async def test_the_stubborn_kind_refuses_a_setpoint_outside_its_range() -> None:
    """Zoals Home Assistant: een setpoint buiten min/max is een ServiceValidationError."""
    home = await start_house(installation(), states=cold(), appliance="stubborn")
    try:
        with pytest.raises(ServiceValidationError):
            await home.call(
                "climate",
                "set_temperature",
                {"entity_id": LIVING, "temperature": 40.0, "hvac_mode": "heat"},
            )
    finally:
        await stop_house(home)


async def test_a_delayed_report_lands_one_round_later() -> None:
    """`report_delay_rounds` stelt de teruggave uit tot de volgende ronde."""
    warm = {"sensor.woonkamer": ("22.0", {}), LIVING: ("off", {})}
    home = await start_house(installation(), states=warm)
    try:
        home.appliance["report_delay_rounds"] = 1
        await home.call("climate", "set_hvac_mode", {"entity_id": LIVING, "hvac_mode": "heat"})
        assert home.state(LIVING) == "off", "de melding hoort nog uit te staan"
        await home.settle()
        assert home.state(LIVING) == "heat", "na één ronde hoort de melding er te zijn"
    finally:
        await stop_house(home)


async def test_the_installation_runs_on_both_kinds() -> None:
    """De integratie zelf start op beide typen; de campagnes draaien er straks tegen."""
    for kind in ("obedient", "stubborn"):
        home = await start_house(installation(), states=cold(), appliance=kind)
        try:
            assert home.entry.options[CONF_INSTALLATION]["zones"][0]["zone_id"] == "woonkamer"
        finally:
            await stop_house(home)
