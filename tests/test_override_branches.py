"""Bereikbare takken van een override en haar bewaarde staat.

Reachable branches of an override and its stored state."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from conftest import house
from homeassistant.util import dt as dt_util
from override_helpers import OverrideHost

from custom_components.climate_director.state_store import StateStoreMixin


def test_an_override_for_an_unknown_zone_is_refused() -> None:
    """Een override voor een zone die niet bestaat levert niets op."""
    assert OverrideHost(house()).override_source("bestaat_niet", "heat") is None


def test_an_override_in_a_neutral_mode_may_use_any_source() -> None:
    """`off` en `fan_only` passen op elke bron, ongeacht de rol."""
    zone = house().zones[0]
    assert OverrideHost(house())._override_source(zone, "off") is not None


def test_an_override_wake_with_nothing_pending_does_nothing() -> None:
    """Zonder lopende override valt er niets te wekken."""
    host = OverrideHost(house())
    host._override_wake_at_first_expiry()
    assert host._cancel_override_wake is None


def test_the_override_expiry_wakes_the_evaluation() -> None:
    """Als een override afloopt wordt er opnieuw beslist en opnieuw gewekt."""
    host = OverrideHost(house())
    host._on_override_expiry(dt_util.utcnow())
    assert host.evaluations == 1


class StoreHost(StateStoreMixin):
    """A stand-in for the coordinator on the storage side.

    A stand-in for the coordinator on the storage side.
    """

    def __init__(self, config: Any, *, with_overrides: bool = True) -> None:
        self.config = config
        if with_overrides:
            self.zone_overrides: dict[str, bool] = {}
            self.zone_override_until: dict[str, Any] = {}
            self.zone_override_when_done: dict[str, str] = {}
            self.zone_override_entity: dict[str, str] = {}
        # De notitie van wat de gebruiker vóór het herstel zelf deed: het herstel
        # leest hem. Deze stand-in draait geen opstart, dus de verzameling blijft
        # leeg en slaat niets over.
        #
        # The note of what the user did before the restore: the restore
        # reads it. This stand-in runs no startup, so the set stays empty and skips
        # nothing.
        self._override_before_restore: set[str] = set()
        self._request_before_restore: set[str] = set()
        self.wakes = 0

    def _override_wake_at_first_expiry(self) -> None:
        self.wakes += 1


def test_a_store_without_override_state_simply_returns() -> None:
    """Een stand-in zonder override-staat laadt gewoon wat hij kent."""
    store = StoreHost(house(), with_overrides=False)
    store._restore_overrides({}, dt_util.utcnow())
    assert store.wakes == 0


def test_a_live_override_comes_back_and_an_expired_one_does_not() -> None:
    """Een lopende override komt terug; een verlopen of onbekende niet."""
    now = dt_util.utcnow()
    zone_id = house().zones[0].zone_id
    expired_zone = house().zones[1].zone_id
    store = StoreHost(house())
    store._restore_overrides(
        {
            "override_until": {
                zone_id: (now + timedelta(hours=1)).isoformat(),
                "bestaat_niet": (now + timedelta(hours=1)).isoformat(),
                expired_zone: (now - timedelta(hours=1)).isoformat(),
                "geen tijd": "geen datum",
            },
            "override_when_done": {zone_id: "turn_off"},
            "override_entity": {zone_id: "climate.woonkamer"},
        },
        now,
    )

    assert store.zone_overrides[zone_id] is True
    assert store.zone_override_until[zone_id] > now
    assert store.zone_override_when_done[zone_id] == "turn_off"
    assert store.zone_override_entity[zone_id] == "climate.woonkamer"
    assert "bestaat_niet" not in store.zone_override_until
    assert expired_zone not in store.zone_override_until
    assert "geen tijd" not in store.zone_override_until
    assert store.wakes == 1


def test_a_live_handover_in_memory_survives_an_older_stored_duration() -> None:
    """Een lopende overdracht in het geheugen blijft staan naast een oudere opslag.

    Het herstel wist geen overdracht die in het geheugen al loopt: de opgeslagen
    looptijd komt er niet overheen. Een zone waar de gebruiker zelf een override
    zette wordt al overgeslagen op `_override_before_restore`; deze wacht dekt elke
    andere schrijver van `zone_override_until`, en daarom staat de eigenschap hier
    op verzonnen invoer vast.

    The restore does not wipe a handover that is already running in memory: the stored
    duration does not come over it. A zone the user set an override on is already
    skipped on `_override_before_restore`; this guard covers every other writer of
    `zone_override_until`, and that is why the property is pinned down here on
    invented input.
    """
    now = dt_util.utcnow()
    zone_id = house().zones[0].zone_id
    store = StoreHost(house())
    live = now + timedelta(hours=1)
    store.zone_override_until[zone_id] = live
    store.zone_overrides[zone_id] = True

    store._restore_overrides(
        {"override_until": {zone_id: (now + timedelta(hours=2)).isoformat()}}, now
    )

    assert store.zone_override_until[zone_id] == live
    assert store.zone_overrides[zone_id] is True
