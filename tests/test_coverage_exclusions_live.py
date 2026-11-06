"""Bereikbare randen van de koppeling die anders buiten de meting vallen.

Reachable edges of the binding that would otherwise fall outside the measurement."""

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
    LIVING,
    cold_two_rooms,
    two_zone_installation,
)

from custom_components.climate_director import coordinator as coordinator_module

pytest_plugins = ["live_fixtures"]
pytestmark = pytest.mark.usefixtures("appliance")


class TestBranchesThatWerePragmaUntilNow:
    """De takken die eerder met een pragma waren afgevangen.

    The branches that used to be caught with a pragma.

    Elk van deze vier is in het live harnas te bereiken: een afsluiting die op
    een lopende ronde wacht, een opslag die niet te lezen is, een toestand die
    niet opzij te zetten is, en een bewaarde prioriteit die geen getal is. Ze
    verliezen daarom hun `# pragma: no cover`: de bewaking is dat ze gedekt
    zijn, niet dat ze uitgesloten zijn.

    Each of these four is reachable in the live harness: a shutdown waiting on
    a running round, an unreadable store, a state file that cannot be moved
    aside, and a stored priority that is no number. They therefore lose their
    `# pragma: no cover`: the guard is that they are covered, not excluded.
    """

    async def test_a_round_that_outlives_the_wait_is_warned_about(self, monkeypatch) -> None:
        """coordinator.py: een ronde die de vijf-secondenwacht overleeft wordt gemeld.

        coordinator.py: a round outliving the five-second wait is reported.
        """
        import contextlib

        live = await start_house(two_zone_installation(), states=cold_two_rooms())
        warnings: list[str] = []
        monkeypatch.setattr(
            coordinator_module._LOGGER,
            "warning",
            lambda message, *args: warnings.append(message % args),
        )

        held = asyncio.Event()

        async def hold_the_lock() -> None:
            async with live.coordinator._lock:
                held.set()
                await asyncio.sleep(30)

        task = live.hass.async_create_task(hold_the_lock())
        try:
            await held.wait()
            await live.coordinator.async_shutdown()
            assert any("Een beslisronde liep nog" in warning for warning in warnings), (
                "de afsluiting hoort te melden dat een ronde nog liep"
            )
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            await stop_house(live)

    async def test_an_unreadable_store_is_quarantined_and_the_clock_starts(
        self, monkeypatch
    ) -> None:
        """state_store.py: een opslag die gooit gaat opzij, met melding en klok.

        state_store.py: a store that throws goes aside, with a notice and a clock.
        """
        from homeassistant.helpers import issue_registry as ir

        original = Store.async_load

        async def unreadable(store) -> Any:
            if store.key.startswith("climate_director"):
                raise OSError("onleesbaar")
            return await original(store)

        monkeypatch.setattr(Store, "async_load", unreadable)

        home = await start_house(
            two_zone_installation(), states=cold_two_rooms(), entry_id="onleesbaar"
        )
        try:
            assert home.state(LIVING) == "heat", "de director hoort met een lege staat te beslissen"
            assert home.coordinator._clock_reeval_unsub is not None, "de klok hoort te staan"
            registry = ir.async_get(home.hass)
            assert ("climate_director", "corrupt_storage_onleesbaar") in registry.issues
        finally:
            await stop_house(home)

    async def test_a_state_file_that_cannot_be_moved_aside_still_reports(self, monkeypatch) -> None:
        """state_store.py: mislukt verplaatsen meldt nog steeds en gooit niet.

        state_store.py: a failed move still reports and does not throw.
        """
        from custom_components.climate_director import state_store

        home = await start_house(
            two_zone_installation(), states=cold_two_rooms(), entry_id="vergrendeld"
        )
        logged: list[str] = []
        monkeypatch.setattr(
            state_store._LOGGER,
            "exception",
            lambda message, *args: logged.append(message % args),
        )

        def refuse(_source, _target) -> None:
            raise OSError("vergrendeld")

        try:
            with monkeypatch.context() as context:
                context.setattr(state_store.os, "rename", refuse)
                await home.coordinator._quarantine_storage()
            assert logged, "een mislukte verplaatsing hoort gemeld te worden"
        finally:
            await stop_house(home)

    async def test_a_restored_priority_that_is_no_number_falls_back(self) -> None:
        """number.py: een bewaarde prioriteit die geen getal is valt terug.

        number.py: a stored priority that is no number falls back.
        """
        from types import SimpleNamespace

        from custom_components.climate_director.number import ZonePriorityNumber

        home = await start_house(two_zone_installation(), states=cold_two_rooms())
        try:
            zone_id = home.coordinator.config.zones[0].zone_id
            entity = ZonePriorityNumber(home.coordinator, zone_id)

            async def last_state() -> Any:
                return SimpleNamespace(state="onzin", attributes={})

            entity.async_get_last_state = last_state  # type: ignore[method-assign]
            await entity.async_added_to_hass()
            assert entity.native_value == home.coordinator.config.zone(zone_id).priority
        finally:
            await stop_house(home)
