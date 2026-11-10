"""Het oppervlak van de coordinator dat de mixins gebruiken.

The coordinator surface the mixins use.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Literal, Protocol

from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers.storage import Store

from .engine import Plan, ResidentState, WorldState
from .engine.diff import Change
from .engine.families import ModeFamily
from .engine.models import DirectorConfig, Season

if TYPE_CHECKING:
    from .coordinator import ClimateDirectorEntry


class CoordinatorSurface(Protocol):
    """Het oppervlak van de coördinator dat de mixins gebruiken.

    The coordinator surface the mixins use.

    De mixins (`HandStartMixin`, `StateStoreMixin`, `PreconditionsMixin`,
    `OverridesMixin`, `ResidentReaderMixin`, `RoomPresenceMixin`,
    `WorldBuilderMixin`) liggen op de coördinator maar erven er niet van: de
    coördinator erft van hén. Zonder deze declaratie ziet mypy hun `self` als de
    mixin zelf en klaagt hij op elk coordinator-attribuut. Elke mixin erft onder
    `TYPE_CHECKING` van dit protocol, zodat `self.config` en de rest kloppen;
    buiten de typecontrole bestaat het niet, en de coördinator erft het zo
    binnen - de waarden zelf staan in zijn `__init__`.

    The mixins (`HandStartMixin`, `StateStoreMixin`, `PreconditionsMixin`,
    `OverridesMixin`, `ResidentReaderMixin`, `RoomPresenceMixin`,
    `WorldBuilderMixin`) sit on the coordinator but do not inherit from it: the
    coordinator inherits from them. Without this declaration mypy sees their
    `self` as the mixin itself and complains about every coordinator attribute.
    Under `TYPE_CHECKING` each mixin inherits from this protocol, so `self.config`
    and the rest resolve; outside the type check it does not exist, and the
    coordinator inherits it like any other base - the values themselves stand in
    its `__init__`.
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

    @property
    def entry(self) -> ClimateDirectorEntry: ...

    def async_request_evaluation(self) -> None: ...
    # Komt van `DataUpdateCoordinator` en wordt hier nergens overschreven. Voor
    # mypy maakt een kale `...` de klasse abstract ("implicitly abstract because
    # it has an empty function body"); bij het draaien komt hij van die klasse.
    #
    # Comes from `DataUpdateCoordinator` and is overridden nowhere here. To mypy
    # a bare `...` makes the class abstract ("implicitly abstract because it has
    # an empty function body"); at run time the method comes from that class.
    def async_update_listeners(self) -> None:
        return None

    def _async_save_state(self) -> None: ...
    def build_world(self) -> WorldState: ...
    def _we_wanted_it_on(self, entity_id: str, family: ModeFamily) -> bool: ...
    def _hand_starts_payload(self) -> dict[str, Any]: ...
    def _restore_hand_starts(self, stored: Mapping[str, Any], now: datetime) -> None: ...
    def _note_by_hand_before_restore(
        self, zone_id: str, kind: Literal["override", "request"]
    ) -> None: ...
    def _lift_hand(self, zone_id: str) -> None: ...
    def _room_presence_payload(self) -> dict[str, Any]: ...
    def _restore_room_presence(self, stored: Mapping[str, Any], now: datetime) -> None: ...
    def _live_preconditions(self) -> dict[str, datetime]: ...
    def _wake_at_the_first_expiry(self) -> None: ...
    def _override_wake_at_first_expiry(self) -> None: ...
    def _calendar_says_holiday(self) -> bool: ...
    def _resident(
        self, resident_id: str, presence: str, sleep: str, asleep_state: str
    ) -> ResidentState: ...
    def zones_handed_back(self, now: datetime, residents: dict[str, ResidentState]) -> set[str]: ...
    def everyone_asleep(self, now: datetime, residents: dict[str, ResidentState]) -> bool: ...
    def house_is_empty(self, residents: dict[str, ResidentState]) -> bool: ...
