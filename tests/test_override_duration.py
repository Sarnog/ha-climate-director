"""Anker 11: een override met een looptijd draagt zijn eigen einde.

Anchor 11: an override with a duration carries its own ending.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from harness_live import LiveHome, new_config_dir, start_house, stop_house
from homeassistant.util import dt as dt_util
from test_campaign_live_ha import LIVING, cold_world, installation

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


# ---------------------------------------------------------------------------
# De eindtijdsensor: wat het dashboard laat zien (ronde 33).
# The end-time sensor: what the dashboard shows (round 33).
# ---------------------------------------------------------------------------

ENDS = "zone_woonkamer_override_ends"
OVERRIDE = "zone_woonkamer_override"
OTHER_ENDS = "zone_zolder_override_ends"


def sensor_state(until: datetime) -> str:
    """Return the state a timestamp sensor takes for `until`.

    Home Assistant zet een `datetime` met tijdzone om naar UTC en naar hele
    seconden; dat is wat de kaart als eindtijd leest.
    """
    return dt_util.as_utc(until).isoformat(timespec="seconds")


async def call_with_target(home: LiveHome, service: str, data: dict, entity_id: str) -> None:
    """Call an action the way the card does: no data, the entity as the target.

    `simple-timer-card` stuurt bij een timestamp-sensor geen `data` mee maar zet
    de sensor zelf als `target.entity_id`; Home Assistant plakt dat doel vóór de
    schemavalidatie aan de data.
    """
    await home.hass.services.async_call(
        DOMAIN, service, data, target={"entity_id": entity_id}, blocking=True
    )
    await home.hass.async_block_till_done()


async def test_the_end_time_sensor_shows_the_running_override(home: LiveHome) -> None:
    """De toestand is de eindtijd, met de starttijd als attribuut."""
    await call_set_override(home, minutes=60)
    sensor = home.by_key(ENDS)
    until = home.coordinator.zone_override_until["woonkamer"]

    assert home.state(sensor) == sensor_state(until)
    attributes = home.attributes(sensor)
    assert attributes["zone_id"] == "woonkamer"
    assert attributes["when_done"] == "turn_off"
    assert attributes["target_entity"] == LIVING
    assert (
        dt_util.parse_datetime(attributes["start_time"])
        == (home.coordinator.zone_override_started["woonkamer"])
    )


async def test_the_start_time_is_the_moment_the_end_time_counts_from(home: LiveHome) -> None:
    """Eén kloklezing: de starttijd en de looptijd horen bij elkaar te passen.

    Twee lezingen naast elkaar zouden een voortgangsring opleveren die niet bij
    zijn eigen eindtijd past.
    """
    await call_set_override(home, minutes=45)
    started = home.coordinator.zone_override_started["woonkamer"]
    until = home.coordinator.zone_override_until["woonkamer"]
    assert until - started == timedelta(minutes=45)


async def test_only_the_overridden_zone_has_an_end_time(home: LiveHome) -> None:
    await call_set_override(home, minutes=60)
    assert home.state(home.by_key(ENDS)) != "unknown"
    assert home.state(home.by_key(OTHER_ENDS)) == "unknown"


async def test_without_an_override_the_end_time_is_unknown(home: LiveHome) -> None:
    sensor = home.by_key(ENDS)
    assert home.state(sensor) == "unknown"
    assert home.attributes(sensor)["start_time"] if False else True  # zie hieronder
    assert "start_time" not in home.attributes(sensor)
    assert home.attributes(sensor)["when_done"] is None
    assert home.attributes(sensor)["target_entity"] is None


async def test_an_override_without_minutes_has_no_end_time(home: LiveHome) -> None:
    """Een override zonder looptijd vervalt nooit, dus er valt niets af te tellen."""
    await call_set_override(home, minutes=None)
    assert home.coordinator.zone_overrides["woonkamer"] is True
    assert home.state(home.by_key(ENDS)) == "unknown"
    assert "start_time" not in home.attributes(home.by_key(ENDS))


async def test_the_switch_turned_on_by_hand_has_no_end_time(home: LiveHome) -> None:
    await home.call("switch", "turn_on", {"entity_id": home.by_key(OVERRIDE)})
    await home.evaluate()
    assert home.state(home.by_key(ENDS)) == "unknown"


@pytest.mark.parametrize("when_done", ["turn_off", "leave"])
async def test_the_end_time_disappears_when_the_override_lapses(
    home: LiveHome, when_done: str
) -> None:
    await call_set_override(home, when_done=when_done)
    assert home.state(home.by_key(ENDS)) != "unknown"

    home.coordinator.zone_override_until["woonkamer"] = dt_util.now() - timedelta(seconds=1)
    await home.evaluate()

    assert home.state(home.by_key(ENDS)) == "unknown"
    assert home.coordinator.zone_override_started == {}


async def test_the_end_time_disappears_when_the_switch_goes_off_by_hand(home: LiveHome) -> None:
    """Met de hand uitzetten laat de looptijd stil vervallen - en de sensor mee.

    De schakelaar schrijft alleen `zone_overrides`; de ronde daarna ruimt de
    looptijd op en publiceert het plan, waarna de sensor opnieuw schrijft.
    """
    await call_set_override(home, minutes=60)
    await home.call("switch", "turn_off", {"entity_id": home.by_key(OVERRIDE)})
    await home.evaluate()

    assert home.state(home.by_key(ENDS)) == "unknown"
    assert home.coordinator.zone_override_started == {}
    assert home.coordinator.zone_override_until == {}


async def test_clear_override_makes_the_end_time_unknown(home: LiveHome) -> None:
    await call_set_override(home, minutes=60)
    await home.call(DOMAIN, "clear_override", {"zone_id": "woonkamer"})
    await home.evaluate()
    assert home.state(home.by_key(ENDS)) == "unknown"


async def test_the_diagnostics_show_the_start_time(home: LiveHome) -> None:
    """De diagnose draagt de starttijd mee, zodat een override na te spelen is."""
    from custom_components.climate_director.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    await call_set_override(home, minutes=60)
    started = home.coordinator.zone_override_started["woonkamer"]
    found = await async_get_config_entry_diagnostics(home.hass, home.entry)
    assert found["control_state"]["zone_override_started"] == {"woonkamer": started.isoformat()}


# ---------------------------------------------------------------------------
# De entiteit als doel: precies wat de annuleerknop van de kaart stuurt.
# The entity as the target: exactly what the card's cancel button sends.
# ---------------------------------------------------------------------------


async def test_the_card_cancels_with_only_the_sensor_as_its_target(home: LiveHome) -> None:
    await call_set_override(home, minutes=60)
    sensor = home.by_key(ENDS)

    home.clear_calls()
    await call_with_target(home, "clear_override", {}, sensor)
    await home.evaluate()

    assert home.coordinator.zone_overrides.get("woonkamer", False) is False
    assert home.coordinator.zone_override_until == {}
    assert home.state(sensor) == "unknown"
    modes = [data.get("hvac_mode") for _service, data in home.climate_calls()]
    assert "off" not in modes, home.climate_calls()


async def test_the_override_switch_works_as_the_target_too(home: LiveHome) -> None:
    await call_set_override(home, minutes=60)
    switch = home.by_key(OVERRIDE)
    await call_with_target(home, "clear_override", {}, switch)
    await home.evaluate()
    assert home.coordinator.zone_overrides.get("woonkamer", False) is False


async def test_set_override_accepts_only_an_entity_as_its_target(home: LiveHome) -> None:
    sensor = home.by_key(ENDS)
    home.clear_calls()
    await call_with_target(
        home,
        "set_override",
        {"hvac_mode": "cool", "temperature": 18.5, "minutes": 60, "when_done": "leave"},
        sensor,
    )
    await home.evaluate()

    assert home.coordinator.zone_overrides["woonkamer"] is True
    assert home.coordinator.zone_override_until
    modes = [
        data.get("hvac_mode") for _service, data in home.climate_calls() if "hvac_mode" in data
    ]
    assert modes == ["cool"], home.climate_calls()


async def test_a_matching_zone_next_to_the_entity_is_allowed(home: LiveHome) -> None:
    """Entiteit én zone mogen samen, zolang ze hetzelfde zeggen."""
    sensor = home.by_key(ENDS)
    await call_with_target(home, "clear_override", {"zone_id": "woonkamer"}, sensor)
    sensor = home.by_key(ENDS)
    await call_with_target(
        home, "set_override", {"zone_id": "woonkamer", "hvac_mode": "cool", "minutes": 30}, sensor
    )
    assert home.coordinator.zone_overrides["woonkamer"] is True


async def test_a_zone_that_does_not_match_the_entity_is_refused(home: LiveHome) -> None:
    from homeassistant.exceptions import ServiceValidationError

    sensor = home.by_key(ENDS)
    with pytest.raises(ServiceValidationError, match="does not belong|hoort niet bij"):
        await call_with_target(home, "clear_override", {"zone_id": "zolder"}, sensor)


@pytest.mark.parametrize(
    "entity_id",
    ["sensor.buiten", "climate.woonkamer", "binary_sensor.achterdeur"],
)
async def test_an_entity_that_is_no_override_is_refused(home: LiveHome, entity_id: str) -> None:
    """Alleen de schakelaar en de eindtijdsensor van een zone tellen als doel."""
    from homeassistant.exceptions import ServiceValidationError

    with pytest.raises(ServiceValidationError, match="not an override|geen override"):
        await call_with_target(home, "clear_override", {}, entity_id)


async def test_one_of_our_own_other_entities_is_refused_too(home: LiveHome) -> None:
    """Een sensor van deze integratie die geen override is, is evengoed een typefout."""
    from homeassistant.exceptions import ServiceValidationError

    with pytest.raises(ServiceValidationError, match="not an override|geen override"):
        await call_with_target(home, "clear_override", {}, home.by_key("zone_woonkamer_source"))


async def test_an_entity_with_a_wrong_entry_id_is_refused(home: LiveHome) -> None:
    from homeassistant.exceptions import ServiceValidationError

    with pytest.raises(ServiceValidationError, match="Unknown installation|Onbekende installatie"):
        await call_with_target(
            home, "clear_override", {"entry_id": "bestaat_niet"}, home.by_key(ENDS)
        )


async def test_an_entity_of_an_unloaded_installation_is_refused(home: LiveHome) -> None:
    """Een register kan een entiteit van een niet-geladen installatie dragen."""
    from homeassistant.exceptions import ServiceValidationError

    sensor = home.by_key(ENDS)
    await home.hass.config_entries.async_unload(home.entry.entry_id)
    await home.hass.async_block_till_done()

    with pytest.raises(ServiceValidationError, match="Unknown installation|Onbekende installatie"):
        await call_with_target(home, "clear_override", {}, sensor)


async def test_without_a_zone_and_without_an_entity_is_refused(home: LiveHome) -> None:
    from homeassistant.exceptions import ServiceValidationError

    with pytest.raises(ServiceValidationError, match="needs a zone|heeft een zone"):
        await home.call(DOMAIN, "clear_override", {})


async def test_two_override_entities_may_be_targeted_at_once(home: LiveHome) -> None:
    """Meerdere entiteiten zijn net zo goed een doel; de zone bepaalt de rest."""
    sensor = home.by_key(ENDS)
    switch = home.by_key(OVERRIDE)
    await home.hass.services.async_call(
        DOMAIN,
        "clear_override",
        {},
        target={"entity_id": [sensor, switch]},
        blocking=True,
    )
    await home.hass.async_block_till_done()
    await call_set_override(home, minutes=60)
    assert home.coordinator.zone_overrides["woonkamer"] is True


# ---------------------------------------------------------------------------
# Een herstart: de starttijd hoort mee te komen, en een oude opslag laadt ook.
# A restart: the start time travels along, and an old store loads too.
# ---------------------------------------------------------------------------


async def test_the_start_time_survives_a_restart() -> None:
    config_dir = new_config_dir()
    home = await start_house(
        installation(), states=cold_world(), entry_id="einde", config_dir=config_dir
    )
    try:
        await call_set_override(home, minutes=60)
        until = home.coordinator.zone_override_until["woonkamer"]
        started = home.coordinator.zone_override_started["woonkamer"]
    finally:
        await stop_house(home)

    again = await start_house(
        installation(), states=cold_world(), entry_id="einde", config_dir=config_dir
    )
    try:
        sensor = again.by_key(ENDS)
        assert again.state(sensor) == sensor_state(until)
        assert again.attributes(sensor)["start_time"] == started.isoformat()
        assert again.coordinator.zone_override_started["woonkamer"] == started
    finally:
        await stop_house(again)


async def test_an_old_store_without_a_start_time_still_loads() -> None:
    """Een opslag van vóór deze versie draagt geen `override_started`.

    De eindtijd komt gewoon terug en de sensor telt af; alleen de starttijd is
    onbekend, dus die laten we weg in plaats van er iets voor te verzinnen.
    """
    config_dir = new_config_dir()
    home = await start_house(
        installation(), states=cold_world(), entry_id="oud", config_dir=config_dir
    )
    try:
        await call_set_override(home, minutes=60)
        until = home.coordinator.zone_override_until["woonkamer"]
        store = Path(home.coordinator._store.path)
    finally:
        await stop_house(home)

    stored = json.loads(store.read_text(encoding="utf-8"))
    assert "override_started" in stored["data"]
    del stored["data"]["override_started"]
    store.write_text(json.dumps(stored), encoding="utf-8")

    again = await start_house(
        installation(), states=cold_world(), entry_id="oud", config_dir=config_dir
    )
    try:
        sensor = again.by_key(ENDS)
        assert again.state(sensor) == sensor_state(until)
        assert again.coordinator.zone_override_started == {}
        assert "start_time" not in again.attributes(sensor)
    finally:
        await stop_house(again)


async def test_a_leftover_start_time_without_an_ending_is_dropped() -> None:
    """Een starttijd zonder levende eindtijd blijft nergens staan.

    Dat is wat een huis oplevert dat uit stond toen de looptijd afliep: de opslag
    draagt de starttijd nog, maar de eindtijd is verstreken. Er valt dan niets af
    te tellen, dus ook geen starttijd om een ring op te hangen.
    """
    config_dir = new_config_dir()
    home = await start_house(
        installation(), states=cold_world(), entry_id="rest", config_dir=config_dir
    )
    try:
        await call_set_override(home, minutes=60)
        store = Path(home.coordinator._store.path)
    finally:
        await stop_house(home)

    stored = json.loads(store.read_text(encoding="utf-8"))
    assert stored["data"]["override_started"]["woonkamer"]
    lapsed = dt_util.now() - timedelta(minutes=5)
    stored["data"]["override_until"]["woonkamer"] = lapsed.isoformat()
    store.write_text(json.dumps(stored), encoding="utf-8")

    again = await start_house(
        installation(), states=cold_world(), entry_id="rest", config_dir=config_dir
    )
    try:
        assert again.coordinator.zone_override_started == {}
        assert "woonkamer" not in again.coordinator.zone_override_until
        assert again.state(again.by_key(ENDS)) == "unknown"
    finally:
        await stop_house(again)
