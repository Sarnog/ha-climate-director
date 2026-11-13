"""De koppeling tussen Home Assistant en de engine.

The binding between Home Assistant and the engine.

De coordinator doet precies drie dingen: hij leest entiteiten uit tot één
`WorldState`, laat `decide()` daar een `Plan` van maken, en zorgt dat er
opnieuw besloten wordt zodra dat zin heeft. Hij bevat zelf geen besliskunde -
staat er ooit een `if` over temperaturen in dit bestand, dan hoort die in
`engine/`.

The coordinator does exactly three things: it reads entities into one
`WorldState`, has `decide()` turn that into a `Plan`, and makes sure a fresh
decision happens whenever that is worthwhile. It holds no decision logic itself
- if an `if` about temperatures ever appears in this file, it belongs in
`engine/`.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import (
    coordinator_events,
    coordinator_lifecycle,
    coordinator_reporting,
    coordinator_round,
    coordinator_tracking,
    cost_steering,
)
from .const import (
    CONF_INSTALLATION,
    CONF_SHADOW_MODE,
    DEBOUNCE_SECONDS,
    DEFAULT_PRECONDITION_MINUTES,
    DEFAULT_SHADOW_MODE,
    DOMAIN,
    STORAGE_VERSION,
)
from .coordinator_state import (
    EventsState,
    LifecycleState,
    ReportingState,
    RoundState,
    TrackingState,
)
from .engine import (
    DirectorConfig,
    Plan,
    Season,
    WorldState,
)
from .engine.diff import Change
from .engine.serialise import config_from_dict
from .hand_start import HandStartMixin
from .overrides import OverridesMixin
from .preconditions import PreconditionsMixin
from .resident_reader import ResidentReaderMixin
from .room_presence import RoomPresenceMixin
from .state_store import StateStoreMixin
from .units import (
    temperature_unit_of,
)
from .world_builder import (
    WorldBuilderMixin,
)

_LOGGER = logging.getLogger(__name__)

type ClimateDirectorEntry = ConfigEntry[ClimateDirectorCoordinator]

#: Hoe vaak hetzelfde verschil achter elkaar aangeboden moet zijn voordat er
#: een reparatiemelding komt. Met de vangnetklok van 60 seconden is dit
#: ongeveer tien minuten. Het aantal rondes alleen is niet genoeg: de
#: ontdubbelaar wacht maar een seconde, dus tien beslisrondes kunnen ook binnen
#: tien seconden voorbij zijn. Daarom geldt `UNUSABLE_GRACE_SECONDS` ernaast,
#: net als bij de andere twee meldingen.
#:
#: How many times the same difference must have been offered in a row before a
#: repair notice appears. With the 60-second safety-net clock this is about ten
#: minutes. The round count alone is not enough: the debouncer waits only a
#: second, so ten decision rounds can just as well be over within ten seconds.
#: Hence `UNUSABLE_GRACE_SECONDS` applies alongside it, as it does for the other
#: two notices.
_COMMAND_NOT_TAKING_ROUNDS = 10


def storage_key(entry_id: str) -> str:
    """Return the key one installation keeps its by-hand state under.

    Op één plek, want hij wordt op twee plekken gebruikt: de coordinator
    schrijft hem vol en het verwijderen van een installatie gooit hem weg. Twee
    keer uitgeschreven zou betekenen dat een hernoeming het opruimen stilletjes
    laat missen.

    In one place, since it is used in two: the coordinator fills it and removing
    an installation throws it away. Spelling it out twice would mean a rename
    quietly makes the cleanup miss.
    """
    return f"{DOMAIN}.{entry_id}.precondition"


class ClimateDirectorCoordinator(
    RoomPresenceMixin,
    HandStartMixin,
    StateStoreMixin,
    PreconditionsMixin,
    OverridesMixin,
    ResidentReaderMixin,
    WorldBuilderMixin,
    DataUpdateCoordinator[Plan],
):
    """Reads the world, runs the engine, applies the outcome."""

    def __init__(self, hass: HomeAssistant, entry: ClimateDirectorEntry) -> None:
        """Set up the coordinator for one installation."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=entry.title or DOMAIN,
            update_interval=None,
        )
        self.entry: ClimateDirectorEntry = entry
        self.tracking = TrackingState()
        self.round = RoundState(
            debouncer=Debouncer(
                hass,
                _LOGGER,
                cooldown=DEBOUNCE_SECONDS,
                immediate=False,
                function=self.async_evaluate,
            )
        )
        self.reporting = ReportingState()
        self.events = EventsState()
        self.lifecycle = LifecycleState()
        self.config: DirectorConfig = config_from_dict(
            entry.options.get(CONF_INSTALLATION) or entry.data.get(CONF_INSTALLATION) or {}
        )
        self._started_at = dt_util.now()
        """Het opstartmoment; openingen die daarvoor al openstonden tellen direct.

        The start moment; openings already open before it count immediately.
        """
        self.shadow: bool = entry.options.get(CONF_SHADOW_MODE, DEFAULT_SHADOW_MODE)
        self.version: str = ""
        """Het geinstalleerde versienummer, voor in het apparaatpaneel.

        Bij een handmatig geinstalleerde integratie is dit het enige plekje
        waar je kunt zien welke versie er draait; HACS toont het niet.

        The installed version, for the device panel. With a manually
        installed integration this is the only place to see which version is
        running; HACS does not show it.
        """
        # Bedieningstoestand. De schakelentiteiten herstellen dit na een
        # herstart en schrijven het hier terug.
        #
        # Control state. The switch entities restore this after a restart and
        # write it back here.
        self.master_enabled = True
        self.holiday_mode = False
        self.guest_mode = False
        self.precondition_minutes: float = DEFAULT_PRECONDITION_MINUTES
        """Hoe lang een druk op de vooruit-knop duurt.

        De duurentiteit herstelt dit na een herstart en schrijft het hier
        terug, net als de schakelaars. Het staat hier en niet op de knop, zodat
        elke zone dezelfde duur gebruikt en er maar op één plek aan gedraaid
        hoeft te worden.

        How long a press of the pre-conditioning button lasts. The duration
        entity restores this after a restart and writes it back here, just like
        the switches. It lives here rather than on the button so every zone uses
        the same duration and there is only one place to change it.
        """
        self.precondition_until: dict[str, datetime] = {}
        self.precondition_bypass: set[str] = set()
        # De bestandsnaam zegt nog "precondition" omdat hij dat ooit alleen
        # was. Hernoemen zou de lopende verzoeken van elke bestaande
        # installatie weggooien, en daar is de naam van een bestand het niet
        # waard.
        #
        # The file name still says "precondition" because that is all it once
        # held. Renaming it would throw away the running requests of every
        # existing installation, and a file name is not worth that.
        self.store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, storage_key(entry.entry_id)
        )
        """Sinds wanneer elke ingestelde entiteit onleesbaar is.

        Since when each configured entity has been unreadable.
        """
        self.zone_overrides: dict[str, bool] = {}
        self._hand_starts: dict[str, datetime] = {}
        self.handed_back: dict[str, date] = {}
        self._empty_since: dict[str, datetime] = {}
        """Wanneer elke kamer leeg werd of wegviel; zie `room_presence.py`.
        When each room became empty or dropped out; see `room_presence.py`.
        """
        self._occupied_rooms: set[str] = set()
        """Welke kamers bezet waren; zie `room_presence.py`.
        Which rooms were occupied; see `room_presence.py`.
        """
        self.zone_priorities: dict[str, int] = {}
        self.zone_override_until: dict[str, datetime] = {}
        self.zone_override_started: dict[str, datetime] = {}
        self.zone_override_when_done: dict[str, str] = {}
        self.zone_override_entity: dict[str, str] = {}
        self._pending_override: dict[str, Change] = {}
        self._cancel_override_wake: CALLBACK_TYPE | None = None
        self.opening_bypasses: dict[str, bool] = {}
        """Per `opening_id`, of de overbrugging aanstaat (anker 8).

        De schakelaars schrijven hierheen, net als de overrideschakelaars; de
        momentopname geeft de aanstaande ids door als
        `WorldState.opening_bypasses`. Er is geen looptijd: een overbrugging
        blijft staan tot iemand de schakelaar zelf terugzet.

        The switches write here, just like the override switches; the snapshot
        passes the ids that are on through as `WorldState.opening_bypasses`.
        There is no duration: a bypass holds until someone turns the switch off
        themselves.
        """
        self.season_override: Season | None = None
        """Een met de hand gekozen seizoen via de select-entiteit, of `None`.

        Staat er een override, dan wint die van de maand, de entiteit en de
        vaste instelling - de gebruiker heeft net nog met de hand gekozen. De
        select-entiteit herstelt zijn stand na een herstart en schrijft hem
        hier terug, net als de schakelaars.

        A season picked by hand through the select entity, or `None`. With an
        override it beats the month, the entity and the fixed setting - the
        user has just chosen by hand. The select entity restores its state
        after a restart and writes it back here, just like the switches.
        """
        self.world: WorldState | None = None

        self.last_changes: tuple[Change, ...] = ()
        """What the plan wants changed, whether or not it was carried out."""

        self.last_applied: tuple[Change, ...] = ()
        """What was actually carried out; always empty in shadow mode."""

        self._save_pending = False
        """Wat tijdens het opstarten te bewaren viel gaat ná het herstel één keer weg.

        Wat `async_save_state` vóór het herstel niet mocht schrijven, staat hier;
        `state_store._async_save_pending_state` haalt het op.

        What needed saving during the startup goes out once after the restore. What
        `async_save_state` was not allowed to write before the restore stands here;
        `state_store._async_save_pending_state` picks it up.
        """
        self.override_before_restore: set[str] = set()
        self.request_before_restore: set[str] = set()
        """De zones waar de gebruiker vóór het herstel zelf een override of een
        vooruit-verzoek zette of stopte.

        De notitie telt per soort: `_restore_overrides` leest alleen de
        overridenotitie en het herstel van `until` alleen de verzoeknotitie. Zo
        houdt een vers verzoek geen opgeslagen override meer tegen, en een verse
        override geen opgeslagen verzoek. Alleen een handeling van de gebruiker
        telt, en beide notities gaan weg zodra het herstel geweest is.

        The zones where the user set or stopped an override or a pre-conditioning
        request before the restore. The note counts per kind:
        `_restore_overrides` reads only the override note and the restore of
        `until` only the request note. A fresh request therefore no longer holds
        back a stored override, and a fresh override no longer holds back a
        stored request. Only an action by the user counts, and both notes go as
        soon as the restore has been.
        """
        self.home_since: dict[str, datetime] = {}
        """Wanneer elke bewoner thuiskwam, en alleen voor wie er nu is.

        Anker 13: het stiltevenster remt alleen wie er ná zijn begin thuiskomt, en
        dit is het moment waarmee dat gemeten wordt - één moment voor de
        stiltepoort én voor de bestaande slaap-vs-thuiskomst-vergelijking. Het
        wordt gevuld door de toestandswijziging van de aanwezigheidsentiteit
        (thuis worden), door het herstel uit de opslag, en bij het opstarten door
        de terugval op `last_changed`. Wie weggaat verliest zijn moment: weg is
        weg, en een moment voor iemand die er niet is zou de poort op een leugen
        laten rusten.

        Anchor 13: the quiet window brakes only whoever comes home after it began,
        and this is the moment that measures it - one moment for the quiet gate
        and for the existing sleep-versus-homecoming comparison. It is filled by
        the presence entity's state change (coming home), by the restore from
        storage, and at startup by the fallback to `last_changed`. Whoever leaves
        loses their moment: away is away, and a moment for somebody who is not
        there would rest the gate on a lie.
        """
        self.asleep_since: datetime | None = None
        """Wanneer iedereen thuis ging slapen / when everybody at home went to sleep."""
        self._cancel_precondition_wake: CALLBACK_TYPE | None = None

    @property
    def temperature_unit(self) -> str:
        """De eenheid waarin Home Assistant nu temperaturen aanlevert en verwacht.

        Elke keer opnieuw gelezen, net als in `applier.py` en `config_flow.py`:
        wisselt de gebruiker het stelsel, dan volgt de coordinator meteen in
        plaats van pas na een herstart.

        Read afresh every time, like `applier.py` and `config_flow.py` do: when
        the user switches systems the coordinator follows at once instead of only
        after a restart.
        """
        return temperature_unit_of(self.hass)

    # -- aanleidingen / triggers --------------------------------------------

    # -- beslissen / deciding ------------------------------------------------

    # -- onbruikbare entiteiten / unusable entities --------------------------

    # -- ongeschikte standen / unsupported modes ------------------------------

    # -- commando's die niet aankomen / commands not taking --------------------

    # -- seizoensselect / season select ---------------------------------------

    # -- vastgelopen zones / stuck zones -------------------------------------

    # -- circuitgeschiedenis / circuit history -------------------------------

    # -- naar buiten / outward ----------------------------------------------

    @callback
    def async_request_evaluation(self) -> None:
        """Ask for a fresh decision, from a switch or a service call."""
        self.round.debouncer.async_schedule_call()

    def _calendar_says_holiday(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_lifecycle.calendar_says_holiday(self, *args, **kwargs)

    def _live_preconditions(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_round.live_preconditions(self, *args, **kwargs)

    def we_wanted_it_on(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_tracking.we_wanted_it_on(self, *args, **kwargs)

    async def async_start(self, *args: Any, **kwargs: Any) -> Any:
        return await coordinator_lifecycle.async_start(self, *args, **kwargs)

    async def async_on_hass_started(self, *args: Any, **kwargs: Any) -> Any:
        return await coordinator_lifecycle.async_on_hass_started(self, *args, **kwargs)

    def tracked_entities(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_lifecycle.tracked_entities(self, *args, **kwargs)

    async def async_shutdown(self) -> None:
        await coordinator_lifecycle.async_shutdown(self)
        await super().async_shutdown()

    @callback
    def handle_change(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_tracking.handle_change(self, *args, **kwargs)

    @callback
    def notice_precipitation(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_tracking.notice_precipitation(self, *args, **kwargs)

    @callback
    def notice_hand(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_tracking.notice_hand(self, *args, **kwargs)

    def note_commanded_off(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_tracking.note_commanded_off(self, *args, **kwargs)

    def note_commanded_on(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_tracking.note_commanded_on(self, *args, **kwargs)

    def we_wanted_it_off(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_tracking.we_wanted_it_off(self, *args, **kwargs)

    async def async_evaluate(self, *args: Any, **kwargs: Any) -> Any:
        return await coordinator_round.async_evaluate(self, *args, **kwargs)

    def remember_families(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_round.remember_families(self, *args, **kwargs)

    def with_family_history(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_round.with_family_history(self, *args, **kwargs)

    def with_heat_pick(self, *args: Any, **kwargs: Any) -> Any:
        return cost_steering.with_heat_pick(self, *args, **kwargs)

    def schedule_deferral(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_round.schedule_deferral(self, *args, **kwargs)

    @callback
    def cancel_pending_deferral(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_round.cancel_pending_deferral(self, *args, **kwargs)

    @callback
    def cancel_clock_reeval(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_round.cancel_clock_reeval(self, *args, **kwargs)

    @callback
    def schedule_clock_reeval(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_round.schedule_clock_reeval(self, *args, **kwargs)

    @callback
    def on_clock_reeval(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_round.on_clock_reeval(self, *args, **kwargs)

    def unusable_entities(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_reporting.unusable_entities(self, *args, **kwargs)

    @callback
    def report_unreadable(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_reporting.report_unreadable(self, *args, **kwargs)

    @callback
    def note_unusable(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_reporting.note_unusable(self, *args, **kwargs)

    def unsupported_modes(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_reporting.unsupported_modes(self, *args, **kwargs)

    @callback
    def note_unsupported(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_reporting.note_unsupported(self, *args, **kwargs)

    @callback
    def report_unsupported_modes(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_reporting.report_unsupported_modes(self, *args, **kwargs)

    @callback
    def note_unapplied(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_reporting.note_unapplied(self, *args, **kwargs)

    @callback
    def report_command_not_taking(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_reporting.report_command_not_taking(self, *args, **kwargs)

    @callback
    def report_bypassed_openings(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_reporting.report_bypassed_openings(self, *args, **kwargs)

    def season_override_problems(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_reporting.season_override_problems(self, *args, **kwargs)

    @callback
    def report_season_override(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_reporting.report_season_override(self, *args, **kwargs)

    @callback
    def note_waiting(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_reporting.note_waiting(self, *args, **kwargs)

    def waiting_seconds(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_reporting.waiting_seconds(self, *args, **kwargs)

    def unusable_latest(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_reporting.unusable_latest(self, *args, **kwargs)

    def stuck_zones(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_reporting.stuck_zones(self, *args, **kwargs)

    def note_precipitation_now(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_reporting.note_precipitation_now(self, *args, **kwargs)

    def note_home_now(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_tracking.note_home_now(self, *args, **kwargs)

    def fire_events(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_events.fire_events(self, *args, **kwargs)

    def fire_refusals(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_events.fire_refusals(self, *args, **kwargs)

    def refusal_data(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_events.refusal_data(self, *args, **kwargs)

    def friendly(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_events.friendly(self, *args, **kwargs)

    def open_openings(self, *args: Any, **kwargs: Any) -> Any:
        return coordinator_events.open_openings(self, *args, **kwargs)
