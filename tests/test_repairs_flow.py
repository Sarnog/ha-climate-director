"""De oplosflow voor de eenmalige handbediend-melding.

The fix flow for the one-time hand-operated notice.

De flow repareert niets maar bewaart een handtekening in de entry-opties,
zodat dezelfde situatie zich niet opnieuw meldt. Deze tests pinnen dat vast
zonder heel Home Assistant op te tuigen.

The flow fixes nothing but stores a signature in the entry options, so the same
situation does not report itself again. These tests pin that down without
setting up a whole Home Assistant.
"""

from __future__ import annotations

from typing import Any

from custom_components.climate_director.const import CONF_MANUAL_SOURCES_SEEN, DOMAIN
from custom_components.climate_director.repairs import (
    ManualSourcesFlow,
    async_create_fix_flow,
)


class FakeEntry:
    def __init__(self, entry_id: str) -> None:
        self.entry_id = entry_id
        self.options: dict[str, Any] = {}


class FakeConfigEntries:
    def __init__(self, entry: FakeEntry | None) -> None:
        self._entry = entry
        self.updated: dict[str, Any] | None = None

    def async_get_entry(self, entry_id: str) -> FakeEntry | None:
        if self._entry is not None and self._entry.entry_id == entry_id:
            return self._entry
        return None

    def async_update_entry(self, entry: FakeEntry, *, options: dict[str, Any]) -> None:
        self.updated = options


class FakeHass:
    def __init__(self, entries: FakeConfigEntries) -> None:
        self.config_entries = entries


def make_flow(entry: FakeEntry | None) -> tuple[ManualSourcesFlow, FakeConfigEntries]:
    entries = FakeConfigEntries(entry)
    hass = FakeHass(entries)
    flow = ManualSourcesFlow()
    flow.hass = hass  # type: ignore[assignment]
    flow.handler = DOMAIN
    flow.issue_id = f"manual_sources_{entry.entry_id if entry else 'none'}"
    flow.data = {"entry_id": entry.entry_id if entry else None, "signature": "ketel;airco"}
    return flow, entries


async def test_submitting_stores_the_signature_in_the_entry_options() -> None:
    entry = FakeEntry("live")
    flow, entries = make_flow(entry)

    result = await flow.async_step_init({})

    assert result["type"] == "create_entry"
    assert entries.updated == {CONF_MANUAL_SOURCES_SEEN: "ketel;airco"}


async def test_submitting_without_an_entry_still_finishes() -> None:
    """Een verwijderde entry mag de oplosflow niet laten hangen.

    A deleted entry must not hang the fix flow.
    """
    flow, entries = make_flow(None)

    result = await flow.async_step_init({})

    assert result["type"] == "create_entry"
    assert entries.updated is None


async def test_a_missing_entry_id_is_tolerated() -> None:
    entry = FakeEntry("live")
    flow, entries = make_flow(entry)
    flow.data = {"signature": "ketel"}

    result = await flow.async_step_init({})

    assert result["type"] == "create_entry"
    assert entries.updated is None


async def test_the_fix_flow_factory_returns_the_manual_sources_flow() -> None:
    flow = await async_create_fix_flow(None, "manual_sources_live", None)  # type: ignore[arg-type]
    assert isinstance(flow, ManualSourcesFlow)
