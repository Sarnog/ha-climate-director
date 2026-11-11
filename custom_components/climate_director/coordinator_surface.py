"""Het oppervlak van de coordinator dat de mixins gebruiken.

The coordinator surface the mixins use.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine, Mapping
from datetime import date, datetime
from typing import Any, Literal

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant
from homeassistant.helpers.storage import Store

from .coordinator_state import (
    EventsState,
    LifecycleState,
    ReportingState,
    RoundState,
    TrackingState,
)
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
    precondition_until: dict[str, datetime]
    precondition_bypass: set[str]
    _pending_override: dict[str, Change]
    store: Store[dict[str, Any]]
    handed_back: dict[str, date]
    _empty_since: dict[str, datetime]
    _occupied_rooms: set[str]
    home_since: dict[str, datetime]
    asleep_since: datetime | None
    _save_pending: bool
    tracking: TrackingState
    round: RoundState
    reporting: ReportingState
    events: EventsState
    lifecycle: LifecycleState
    world: WorldState | None
    last_changes: tuple[Change, ...]
    last_applied: tuple[Change, ...]
    override_before_restore: set[str]
    request_before_restore: set[str]
    _cancel_precondition_wake: CALLBACK_TYPE | None
    _cancel_override_wake: CALLBACK_TYPE | None

    entry: ConfigEntry[Any]
    async_request_evaluation: Callable[[], None]
    async_update_listeners: Callable[[], None]
    async_save_state: Callable[[], None]
    build_world: Callable[[], WorldState]
    we_wanted_it_on: Callable[[str, ModeFamily], bool]
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

    # De bewerkingen van de coordinator-onderdelen, voor wie ze aanroept.
    # The operations of the coordinator parts, for whoever calls them.
    async_evaluate: Callable[[], Coroutine[Any, Any, None]]
    async_on_hass_started: Callable[[HomeAssistant], Coroutine[Any, Any, None]]
    async_set_updated_data: Callable[[Plan], None]
    tracked_entities: Callable[[], set[str]]
    unusable_entities: Callable[[], dict[str, str]]
    unsupported_modes: Callable[[], dict[str, str]]
    zones_of: Callable[[str], tuple[str, ...]]
    handle_change: Callable[[Event[EventStateChangedData]], None]
    notice_hand: Callable[[Event[EventStateChangedData]], None]
    notice_precipitation: Callable[[Event[EventStateChangedData]], None]
    note_commanded_off: Callable[[tuple[Change, ...]], None]
    note_commanded_on: Callable[[tuple[Change, ...]], None]
    we_wanted_it_off: Callable[[str], bool]
    note_home_now: Callable[[], None]
    note_precipitation_now: Callable[[], None]
    remember_families: Callable[[WorldState], None]
    with_family_history: Callable[[WorldState], WorldState]
    schedule_deferral: Callable[[Plan], None]
    cancel_pending_deferral: Callable[[], None]
    cancel_clock_reeval: Callable[[], None]
    schedule_clock_reeval: Callable[[], None]
    on_clock_reeval: Callable[[datetime], None]
    report_unreadable: Callable[[], None]
    report_unsupported_modes: Callable[[], None]
    report_command_not_taking: Callable[[], None]
    report_bypassed_openings: Callable[[], None]
    report_season_override: Callable[[], None]
    note_unusable: Callable[[], dict[str, str]]
    note_unsupported: Callable[[], dict[str, str]]
    note_unapplied: Callable[[], dict[str, str]]
    season_override_problems: Callable[[], dict[str, str]]
    note_waiting: Callable[[Plan], None]
    fire_events: Callable[[Plan], None]
    fire_refusals: Callable[[Plan], None]
    refusal_data: Callable[[str, Plan | None], dict[str, Any]]
    friendly: Callable[[str], str]
    open_openings: Callable[..., list[str]]
    notice_home: Callable[[Event[EventStateChangedData]], None]
    notice_room_empty: Callable[[Event[EventStateChangedData]], None]
    notice_hand_start: Callable[[Event[EventStateChangedData]], None]
    note_room_presence_now: Callable[[], None]
    settle_hand_starts: Callable[[WorldState], WorldState]
    cancel_pending_override_wake: Callable[[], None]
    cancel_pending_precondition_wake: Callable[[], None]
    consume_expired_overrides: Callable[[datetime], tuple[Change, ...]]
    consume_pending_override_changes: Callable[[WorldState], tuple[Change, ...]]
    drop_lapsed_override_timers: Callable[[], None]
    note_house_asleep: Callable[[WorldState], WorldState]
    async_restore_state: Callable[[], Coroutine[Any, Any, None]]
    async_save_pending_state: Callable[[], None]
    store_payload: Callable[[], dict[str, Any]]
