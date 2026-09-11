"""Anker 11: een override met een looptijd draagt zijn eigen einde.

Anchor 11: an override with a duration carries its own ending.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from harness_live import LiveHome, start_house, stop_house
from homeassistant.util import dt as dt_util
from test_campaign_live_ha import cold_world, installation

from custom_components.climate_director.const import DOMAIN


@pytest.fixture
async def home() -> LiveHome:
    live = await start_house(installation(), states=cold_world())
    try:
        yield live
    finally:
        await stop_house(live)


async def call_set_override(
    home: LiveHome, *, minutes: float | None = 60, when_done: str = "turn_off"
) -> None:
    data: dict = {
        "zone_id": "woonkamer",
        "hvac_mode": "cool",
        "temperature": 18.5,
        "when_done": when_done,
    }
    if minutes is not None:
        data["minutes"] = minutes
    await home.call(DOMAIN, "set_override", data)
    await home.evaluate()


async def test_set_override_sets_the_appliance_in_the_same_round(home: LiveHome) -> None:
    home.clear_calls()
    await call_set_override(home, when_done="leave")

    calls = home.climate_calls()
    modes = [data.get("hvac_mode") for _service, data in calls if "hvac_mode" in data]
    assert modes == ["cool"], calls
    assert any("temperature" in data for _service, data in calls), calls
    # De overdracht stond al aan vóór de beslissing, dus er volgt geen `off`
    # op het net gezette apparaat binnen dezelfde ronde.
    assert "off" not in modes, calls
    assert home.coordinator.zone_overrides["woonkamer"] is True
    assert home.state(home.by_key("zone_woonkamer_override")) == "on"


async def test_set_override_without_minutes_never_expires(home: LiveHome) -> None:
    await call_set_override(home, minutes=None)
    assert home.coordinator.zone_override_until == {}
    assert home.coordinator.zone_overrides["woonkamer"] is True


async def test_expiry_with_turn_off_sends_one_off_and_hands_back(home: LiveHome) -> None:
    await call_set_override(home, when_done="turn_off")
    home.clear_calls()
    home.coordinator.zone_override_until["woonkamer"] = dt_util.now() - timedelta(seconds=1)
    await home.evaluate()

    modes = [data.get("hvac_mode") for _service, data in home.climate_calls()]
    assert modes == ["off"], home.climate_calls()
    assert home.coordinator.zone_overrides.get("woonkamer", False) is False
    assert home.coordinator.zone_override_until == {}
    assert home.state(home.by_key("zone_woonkamer_override")) == "off"


async def test_expiry_with_leave_sends_nothing_and_hands_back(home: LiveHome) -> None:
    await call_set_override(home, when_done="leave")
    home.clear_calls()
    home.coordinator.zone_override_until["woonkamer"] = dt_util.now() - timedelta(seconds=1)
    await home.evaluate()

    assert home.climate_calls() == []
    assert home.coordinator.zone_overrides.get("woonkamer", False) is False
    assert home.coordinator.zone_override_until == {}
    assert home.state(home.by_key("zone_woonkamer_override")) == "off"


async def test_switching_the_override_off_by_hand_lapses_the_duration_silently(
    home: LiveHome,
) -> None:
    await call_set_override(home, when_done="turn_off")
    assert home.coordinator.zone_override_until

    switch = home.by_key("zone_woonkamer_override")
    home.clear_calls()
    await home.call("switch", "turn_off", {"entity_id": switch})
    await home.evaluate()

    # Met de hand uit = geen commando van het aflopen zelf; de looptijd
    # vervalt stil en de engine neemt de zone gewoon weer over. Dat de engine
    # daarna zelf warmte stuurt is gewone regeling, geen afloopkeuze.
    modes = [data.get("hvac_mode") for _service, data in home.climate_calls()]
    assert "off" not in modes, home.climate_calls()
    assert home.coordinator.zone_override_until == {}
    assert home.coordinator.zone_override_when_done == {}


async def test_clear_override_behaves_like_the_hand_off_of_the_switch(
    home: LiveHome,
) -> None:
    await call_set_override(home, when_done="turn_off")
    assert home.coordinator.zone_override_until

    home.clear_calls()
    await home.call(DOMAIN, "clear_override", {"zone_id": "woonkamer"})
    await home.evaluate()

    modes = [data.get("hvac_mode") for _service, data in home.climate_calls()]
    assert "off" not in modes, home.climate_calls()
    assert home.coordinator.zone_override_until == {}
    assert home.coordinator.zone_overrides.get("woonkamer", False) is False


async def test_an_unknown_zone_is_refused_like_precondition(home: LiveHome) -> None:
    from homeassistant.exceptions import ServiceValidationError

    with pytest.raises(ServiceValidationError, match="onbekende zone|Unknown zone"):
        await home.call(
            DOMAIN,
            "set_override",
            {"zone_id": "bestaat_niet", "hvac_mode": "cool", "minutes": 60},
        )


def heat_only_installation() -> dict:
    """Return a house whose only source can heat, never cool."""
    return {
        "zones": [
            {
                "zone_id": "woonkamer",
                "name": "Woonkamer",
                "indoor_sensor": "sensor.woonkamer",
                "sources": [
                    {
                        "source_id": "woonkamer_ketel",
                        "entity_id": "climate.woonkamer",
                        "role": "heat_only",
                    }
                ],
                "heat": {"target": 21.0, "start_at": 20.0, "hysteresis": 1.0},
            }
        ],
        "outdoor_sensor": "sensor.buiten",
    }


def warm_world() -> dict:
    """Return a settled world for the heat-only house."""
    return {
        "sensor.woonkamer": ("21.0", {}),
        "sensor.buiten": ("4.0", {}),
        "climate.woonkamer": ("off", {"hvac_modes": ["heat", "off"]}),
    }


async def test_a_zone_without_a_source_for_the_mode_is_refused() -> None:
    """Geen bron voor de stand = dezelfde vertaalde fout als een onbekende zone.

    No source for the mode = the same translated error as an unknown zone.
    """
    from homeassistant.exceptions import ServiceValidationError

    live = await start_house(heat_only_installation(), states=warm_world())
    try:
        with pytest.raises(ServiceValidationError, match="geen bron|no source"):
            await live.call(
                DOMAIN,
                "set_override",
                {"zone_id": "woonkamer", "hvac_mode": "cool", "minutes": 60},
            )
        # De stand die wél een bron heeft, blijft gewoon werken.
        # The mode that does have a source keeps working.
        await live.call(
            DOMAIN,
            "set_override",
            {"zone_id": "woonkamer", "hvac_mode": "heat", "minutes": 60},
        )
        assert live.coordinator.zone_overrides.get("woonkamer", False) is True
    finally:
        await stop_house(live)


async def test_the_handover_stands_before_the_apply() -> None:
    """De volgorde-valkuil: zet je de overdracht pas ná het toepassen, dan
    gooit de engine het net gezette apparaat er meteen weer uit.

    The order trap: set the handover only after applying, and the engine
    throws the appliance you just set straight out again.
    """
    live = await start_house(installation(), states=cold_world())
    try:
        live.clear_calls()
        # Wat de valkuil zou doen: eerst de stand zetten, pas daarna de zone
        # overdragen. In deze opstelling deelt de airco een exclusieve groep,
        # dus de eerste beslissing na het zetten weigert hem met
        # `exclusive_group_lost` en stuurt `off`.
        live.coordinator.async_set_override(
            "woonkamer", "cool", 18.5, minutes=60, when_done="turn_off"
        )
        await live.evaluate()
        modes = [data.get("hvac_mode") for _service, data in live.climate_calls()]
        assert "off" not in modes, live.climate_calls()
    finally:
        await stop_house(live)
