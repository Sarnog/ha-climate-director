"""Het afbreken van een ronde en een ronde die te lang duurt.

Stopping a round and a round that takes too long."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from harness_live import (
    start_house,
    stop_house,
)
from homeassistant.helpers.storage import Store
from live_helpers import (
    ATTIC,
    LIVING,
    SPARE,
    two_zone_installation,
)

from custom_components.climate_director.const import STORAGE_VERSION
from custom_components.climate_director.coordinator import storage_key

pytest_plugins = ["live_fixtures"]
pytestmark = pytest.mark.usefixtures("appliance")


class TestUnloadingDuringARunningRound:
    """Afsluiten wacht de lopende ronde uit, zodat er niets meer achteraan komt.

    Unloading waits out the running round, so nothing comes after it.
    """

    @staticmethod
    def _warm_house() -> dict[str, tuple[str, dict[str, Any]]]:
        """Alles draait al zoals de director het wil: de eerste ronde is stil.

        Everything already runs the way the director wants it: the first round
        is silent.
        """
        return {
            "sensor.woonkamer": ("18.0", {}),
            "sensor.zolder": ("17.0", {}),
            "sensor.buiten": ("4.0", {}),
            LIVING: ("heat", {"temperature": 21.0}),
            SPARE: ("off", {"temperature": 19.0}),
            ATTIC: ("heat", {"temperature": 20.0}),
            "person.danny": ("home", {}),
            "sensor.danny_lader": ("none", {}),
            "binary_sensor.achterdeur": ("off", {}),
        }

    async def test_no_service_call_lands_after_the_unload(self) -> None:
        import contextlib

        live = await start_house(two_zone_installation(), states=self._warm_house())
        started = asyncio.Event()
        proceed = asyncio.Event()

        async def slow_set_mode(call):
            started.set()
            await proceed.wait()
            live.calls.append(("set_hvac_mode", dict(call.data)))
            live.hass.states.async_set(call.data["entity_id"], call.data["hvac_mode"])

        live.hass.services.async_register("climate", "set_hvac_mode", slow_set_mode)
        try:
            assert live.climate_calls() == [], "de eerste ronde hoort niets te sturen"

            # De woonkamer wordt te warm; de director wil de airco uitzetten.
            # The living room turns too warm; the director wants the unit off.
            live.set("sensor.woonkamer", "23.0")
            round_task = asyncio.create_task(live.coordinator.async_evaluate())
            await asyncio.wait_for(started.wait(), timeout=5)

            unload_task = asyncio.create_task(
                live.hass.config_entries.async_unload(live.entry.entry_id)
            )
            await asyncio.sleep(0)
            await live.hass.async_block_till_done()

            assert not unload_task.done(), "de unload hoort op de lopende ronde te wachten"

            proceed.set()
            await round_task
            await unload_task
            await live.hass.async_block_till_done()

            calls_during = live.climate_calls()
            assert calls_during == [("set_hvac_mode", {"entity_id": LIVING, "hvac_mode": "off"})]

            await asyncio.sleep(0)
            await live.hass.async_block_till_done()
            assert live.climate_calls() == calls_during, "ná de unload mag er niets meer bijkomen"
        finally:
            proceed.set()
            with contextlib.suppress(Exception):
                await stop_house(live)

    async def test_a_pending_store_save_does_not_resurrect_a_removed_file(self) -> None:
        """P1: een uitgestelde opslag mag een verwijderd bestand niet terugschrijven.

        P1: a delayed store write must not resurrect a removed file.
        """

        live = await start_house(two_zone_installation(), states=self._warm_house())
        try:
            store = Store(live.hass, STORAGE_VERSION, storage_key(live.entry.entry_id))
            live.coordinator.async_save_state()
            await live.coordinator.async_shutdown()

            await store.async_remove()
            await asyncio.sleep(1.1)
            await live.hass.async_block_till_done()
            assert await store.async_load() is None
        finally:
            await stop_house(live)

    async def test_shutdown_cancels_the_pending_override_wake(self) -> None:
        """Afsluiten annuleert de wekker van een override die nog loopt.

        Bleef die wekker staan, dan wekte hij na het uitladen een coordinator die
        er niet meer is.

        Shutdown cancels the timer of an override that is still running. Left in
        place, it would wake a coordinator after the unload that no longer exists.
        """

        live = await start_house(two_zone_installation(), states=self._warm_house())
        cancelled: list[str] = []
        try:
            live.coordinator._cancel_override_wake = lambda: cancelled.append("cancelled")
            await live.coordinator.async_shutdown()
            assert cancelled == ["cancelled"]
            assert live.coordinator._cancel_override_wake is None
        finally:
            await stop_house(live)

    async def test_shutdown_does_not_reach_into_the_stores_private_cleanup(
        self, monkeypatch
    ) -> None:
        """L3: `async_save` ruimt zijn eigen uitgestelde schrijfactie al op.

        De coordinator hoeft de private `_async_cleanup_delay_listener` van HA's
        `Store` niet aan te roepen; `async_save` doet dat zelf. Wie hem direct
        aanroept steunt op een implementatiedetail dat elke HA-versie mag
        veranderen.

        `async_save` clears its own delayed write. The coordinator must not call
        HA `Store`'s private `_async_cleanup_delay_listener`; `async_save` does
        that itself, and calling it directly leans on an implementation detail
        any HA version may change.
        """
        live = await start_house(two_zone_installation(), states=self._warm_house())
        try:
            store = live.coordinator.store
            saved: list[object] = []

            async def fake_save(payload: object) -> None:
                saved.append(payload)

            def boom() -> None:
                raise AssertionError("the private Store cleanup was called directly")

            monkeypatch.setattr(store, "async_save", fake_save)
            monkeypatch.setattr(store, "_async_cleanup_delay_listener", boom)

            await live.coordinator.async_shutdown()
            assert saved == [live.coordinator.store_payload()]
        finally:
            await stop_house(live)

    async def test_reload_does_not_let_the_old_plan_land_after_the_new_one(self) -> None:
        import contextlib

        live = await start_house(two_zone_installation(), states=self._warm_house())
        started = asyncio.Event()
        proceed = asyncio.Event()

        async def slow_set_mode(call):
            started.set()
            await proceed.wait()
            live.calls.append(("set_hvac_mode", dict(call.data)))
            live.hass.states.async_set(call.data["entity_id"], call.data["hvac_mode"])

        live.hass.services.async_register("climate", "set_hvac_mode", slow_set_mode)
        try:
            assert live.climate_calls() == [], "de eerste ronde hoort niets te sturen"

            live.set("sensor.woonkamer", "23.0")
            round_task = asyncio.create_task(live.coordinator.async_evaluate())
            await asyncio.wait_for(started.wait(), timeout=5)

            reload_task = asyncio.create_task(
                live.hass.config_entries.async_reload(live.entry.entry_id)
            )
            await asyncio.sleep(0)
            await live.hass.async_block_till_done()

            assert not reload_task.done(), "de reload hoort op de lopende ronde te wachten"

            proceed.set()
            await round_task
            await reload_task
            await live.hass.async_block_till_done()

            # Eén commando, en dat is het commando van vóór de reload. Het oude
            # plan mag niet nog eens landen nadat de nieuwe installatie er staat.
            # One command, and it is the one from before the reload. The old plan
            # may not land again once the new installation stands.
            assert live.climate_calls() == [
                ("set_hvac_mode", {"entity_id": LIVING, "hvac_mode": "off"})
            ]
        finally:
            proceed.set()
            with contextlib.suppress(Exception):
                await stop_house(live)
