"""Het oppervlak van de coordinator dat de mixins gebruiken.

The coordinator surface the mixins use.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, datetime
from typing import Any, Literal

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers.storage import Store

from .engine import Plan, ResidentState, WorldState
from .engine.diff import Change
from .engine.families import ModeFamily
from .engine.models import DirectorConfig, Season


class CoordinatorSurface:
    """Het oppervlak van de coördinator dat de mixins gebruiken.

    The coordinator surface the mixins use.

    De mixins (`HandMixin`, `HandStartMixin`, `StateStoreMixin`, `PreconditionsMixin`,
    `OverridesMixin`, `ResidentReaderMixin`, `RoomPresenceMixin`, `WorldBuilderMixin`)
    erven dit oppervlak, en de coördinator erft van hén. Het noemt alleen leden
    (waarden en `Callable`-typen) en draagt geen methodelichaam, dus er is bij het
    draaien niets dat een echte methode kan overschaduwen; mypy ziet via dit
    oppervlak `self.config` en de rest, ook waar de methode in een andere mixin
    staat. Het is bewust geen `Protocol`: een protocol als basis zou de
    `__init__`-keten van `DataUpdateCoordinator` doorbreken.

    The mixins (`HandMixin`, `HandStartMixin`, `StateStoreMixin`, `PreconditionsMixin`,
    `OverridesMixin`, `ResidentReaderMixin`, `RoomPresenceMixin`, `WorldBuilderMixin`)
    inherit this surface, and the coordinator inherits from them. It names members
    only (values and `Callable` types) and carries no method body, so at run time
    nothing comes about that could shadow a real method; through this surface mypy
    sees `self.config` and the rest, also where the method stands in another mixin.
    It is deliberately no `Protocol`: a protocol as a base would break the
    `__init__` chain of `DataUpdateCoordinator`.
    """

    config: DirectorConfig
    hass: HomeAssistant
    name: str
    shadow: bool
    data: Plan
    _started_at: datetime | None
    _closing: bool
    _restored: bool
    master_enabled: bool
    holiday_mode: bool
    guest_mode: bool
    season_override: Season | None
    _hand_starts: dict[str, datetime]
    zone_overrides: dict[str, bool]
    zone_priorities: dict[str, int]
    zone_override_until: dict[str, datetime]
    zone_override_started: dict[str, datetime]
    zone_override_when_done: dict[str, str]
    zone_override_entity: dict[str, str]
    opening_bypasses: dict[str, bool]
    _precondition: dict[str, datetime]
    _precondition_bypass: set[str]
    _pending_override: dict[str, Change]
    _store: Store[dict[str, Any]]
    _handed_back: dict[str, date]
    _empty_since: dict[str, datetime]
    _occupied_rooms: set[str]
    _home_since: dict[str, datetime]
    _commanded_off: dict[str, datetime]
    _asleep_since: datetime | None
    _save_pending: bool
    _override_before_restore: set[str]
    _request_before_restore: set[str]
    _precipitation_seen_at: datetime | None
    _cancel_precondition_wake: CALLBACK_TYPE | None
    _cancel_override_wake: CALLBACK_TYPE | None

    entry: ConfigEntry[Any]
    async_request_evaluation: Callable[[], None]
    async_update_listeners: Callable[[], None]
    _async_save_state: Callable[[], None]
    build_world: Callable[[], WorldState]
    _we_wanted_it_on: Callable[[str, ModeFamily], bool]
    _hand_starts_payload: Callable[[], dict[str, Any]]
    _restore_hand_starts: Callable[[Mapping[str, Any], datetime], None]
    _note_by_hand_before_restore: Callable[[str, Literal["override", "request"]], None]
    _lift_hand: Callable[[str], None]
    _room_presence_payload: Callable[[], dict[str, Any]]
    _restore_room_presence: Callable[[Mapping[str, Any], datetime], None]
    _live_preconditions: Callable[[], dict[str, datetime]]
    _wake_at_the_first_expiry: Callable[[], None]
    _override_wake_at_first_expiry: Callable[[], None]
    _calendar_says_holiday: Callable[[], bool]
    _resident: Callable[[str, str, str, str], ResidentState]
    zones_handed_back: Callable[[datetime, dict[str, ResidentState]], set[str]]
    everyone_asleep: Callable[[datetime, dict[str, ResidentState]], bool]
    house_is_empty: Callable[[dict[str, ResidentState]], bool]
