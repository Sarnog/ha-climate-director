"""Het opstarten van Home Assistant: de eerste beslissing wacht op het herstel.

Deciding on the startup of Home Assistant: the first decision waits for the restore.

Bij het opzetten van de config entry zijn de entiteiten er al, maar Home Assistant
is nog bezig: herstelde standen, automatiseringen en andere integraties komen pas
daarna. Wat er dan wél al gebeurt is een toestandswijziging van een gevolgde
entiteit - een sensor die binnenkomt terwijl de integraties laden. Die wekt de
debouncer, en zonder een poort besloot de director een seconde later op een half
herstelde wereld: een apparaat dat iemand eerder die dag met de hand uitzette stond dan
al weer aan, en bleef de rest van de dag aan. `tests/test_startup.py` legt de
poort in de coordinator vast; dit bestand meet hem in een echte Home Assistant,
met het harnas in `CoreState.starting` in plaats van meteen op `running`.

When the config entry is set up the entities exist, but Home Assistant is still
busy: restored states, automations and other integrations come only afterwards.
What does already happen is a state change of a tracked entity - a sensor arriving
while the integrations load. That wakes the debouncer, and without a gate the
director decided a second later on a half-restored world: an appliance somebody
switched off by hand earlier that day stood on again and stayed on for the rest of the
day. `tests/test_startup.py` pins the gate down in the coordinator; this file
measures it inside a real Home Assistant, with the harness in `CoreState.starting`
rather than on `running` at once.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import timedelta
from typing import Any

from harness_live import (
    LiveHome,
    new_config_dir,
    settings,
    source,
    start_house,
    stop_house,
    zone,
)
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState
from homeassistant.util import dt as dt_util

LIVING = "climate.woonkamer"
SENSOR = "sensor.woonkamer"
OUTDOOR = "sensor.buiten"

#: De sleutel waaronder de coordinator zijn stand bewaart, met de entry-id van
#: dit harnas (`live`).
#: The key the coordinator stores its state under, with this harness's entry id
#: (`live`).
STORE_KEY = "climate_director.live.precondition"


def store_path(config_dir: str) -> str:
    """Return the path of the file a previous run leaves its state in."""
    return os.path.join(config_dir, ".storage", STORE_KEY)


def write_store(config_dir: str, data: dict[str, Any]) -> None:
    """Write a state file exactly as a previous run left it behind.

    Hetzelfde bestand dat de opslag van de integratie zelf schrijft; een test die
    een herstart nabouwt hoeft de integratie daarvoor niet eerst te laten
    wegschrijven.

    The same file the integration's own store writes; a test rebuilding a restart
    need not have the integration write it out first.
    """
    os.makedirs(os.path.dirname(store_path(config_dir)), exist_ok=True)
    payload = {
        "version": 1,
        "minor_version": 1,
        "key": STORE_KEY,
        "data": data,
    }
    with open(store_path(config_dir), "w", encoding="utf-8") as handle:
        json.dump(payload, handle)


def installation() -> dict[str, Any]:
    """Return a cold single-zone house with one boiler."""
    return {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("woonkamer_ketel", LIVING)],
                heat=settings(21.0, 20.0),
            )
        ],
        "outdoor_sensor": OUTDOOR,
    }


def cold_world() -> dict[str, tuple[str, dict[str, Any]]]:
    """Return a world in which the living room wants heat and the boiler is off."""
    return {
        SENSOR: ("18.5", {"unit_of_measurement": "°C"}),
        OUTDOOR: ("4.0", {}),
        LIVING: ("off", {"hvac_modes": ["off", "heat"], "temperature": 19.0}),
    }


async def settle_the_debouncer(home: LiveHome) -> None:
    """Let the debouncer's second pass and everything behind it finish."""
    await asyncio.sleep(1.5)
    await home.settle()


async def start_up(home: LiveHome) -> None:
    """Let Home Assistant report that it has started, and settle."""
    home.hass.set_state(CoreState.running)
    home.hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await home.hass.async_block_till_done()
    await settle_the_debouncer(home)


def watch_worlds(home: LiveHome) -> list[Any]:
    """Return a list that every world the director builds is appended to.

    Een beslissing bouwt haar wereld één keer, in `_async_evaluate`; de lijst
    liegt er dus niet over of er beslist is. Dat is precies wat "de eerste
    beslissing ziet het" meetbaar maakt: op het moment van de beslissing zelf, in
    plaats van achteraf uit een stand die later alsnog hersteld wordt.

    A decision builds its world once, in `_async_evaluate`; the list therefore
    does not lie about whether a decision was taken. That is exactly what makes
    "the first decision sees it" measurable: at the moment of the decision
    itself, rather than afterwards from a state that gets restored later on
    anyway.
    """
    built: list[Any] = []
    original = home.coordinator.build_world

    def spy() -> Any:
        found = original()
        built.append(found)
        return found

    home.coordinator.build_world = spy  # type: ignore[method-assign]
    return built


def reason_of(home: LiveHome, zone_id: str = "woonkamer") -> str:
    """Return the reason of one zone's last decision."""
    decision = home.coordinator.data.decision_for(zone_id)
    assert decision is not None, f"geen beslissing voor {zone_id}"
    return decision.reason.value


class TestAHandFromBeforeTheRestart:
    """Een hand-uitzetting van vandaag overleeft het opstarten.

    A hand-back from today survives the startup.
    """

    async def test_the_appliance_stays_off_through_the_startup(self) -> None:
        config_dir = new_config_dir()
        write_store(config_dir, {"handed_back": {"woonkamer": dt_util.now().date().isoformat()}})

        home = await start_house(
            installation(),
            config_dir=config_dir,
            core_state=CoreState.starting,
            states=cold_world(),
        )
        try:
            built = watch_worlds(home)
            home.clear_calls()

            # Tijdens het opstarten komt er een nieuwe sensormeting binnen.
            home.hass.states.async_set(SENSOR, "18.4", {"unit_of_measurement": "°C"})
            await settle_the_debouncer(home)

            assert built == [], "er is beslist vóór het herstel van de opslag"
            assert home.climate_calls() == [], "de director stuurde tijdens het opstarten"
            assert home.state(LIVING) == "off"

            await start_up(home)

            assert reason_of(home) == "manual_override"
            assert home.state(LIVING) == "off", "het apparaat hoort uit te blijven"
        finally:
            await stop_house(home)


class TestARequestFromBeforeTheRestart:
    """Een vooruit-verzoek van vóór de herstart zit in de eerste beslissing.

    A pre-conditioning request from before the restart is in the first decision.
    """

    async def test_the_first_decision_sees_the_request(self) -> None:
        config_dir = new_config_dir()
        until = dt_util.now() + timedelta(minutes=30)
        write_store(config_dir, {"until": {"woonkamer": until.isoformat()}})

        home = await start_house(
            installation(),
            config_dir=config_dir,
            core_state=CoreState.starting,
            states=cold_world(),
        )
        try:
            built = watch_worlds(home)
            home.clear_calls()

            home.hass.states.async_set(SENSOR, "18.4", {"unit_of_measurement": "°C"})
            await settle_the_debouncer(home)

            assert built == [], "er is beslist vóór het herstel van de opslag"
            assert home.climate_calls() == []

            await start_up(home)

            assert built, "de eerste beslissing is nooit gevallen"
            assert built[0].preconditioning("woonkamer"), (
                "de eerste beslissing kent het bewaarde vooruit-verzoek niet"
            )
            assert reason_of(home) == "regulating"
            assert home.state(LIVING) == "heat"
        finally:
            await stop_house(home)


class TestWithoutAnythingToRestore:
    """De poort legt de integratie niet stil: zonder herstel doet hij gewoon zijn werk.

    The gate does not silence the integration: without anything to restore it
    simply does its work.
    """

    async def test_the_zone_is_regulated_after_the_startup(self) -> None:
        home = await start_house(
            installation(),
            core_state=CoreState.starting,
            states=cold_world(),
        )
        try:
            built = watch_worlds(home)
            home.clear_calls()

            home.hass.states.async_set(SENSOR, "18.4", {"unit_of_measurement": "°C"})
            await settle_the_debouncer(home)

            assert built == [], "er is beslist vóór het herstel van de opslag"

            await start_up(home)

            assert reason_of(home) == "regulating"
            assert home.state(LIVING) == "heat"
            assert [call[0] for call in home.climate_calls()], "de ketel is nooit aangestuurd"
        finally:
            await stop_house(home)
