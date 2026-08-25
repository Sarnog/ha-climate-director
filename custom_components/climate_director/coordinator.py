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

import asyncio
import logging
import math
import os
from collections.abc import Mapping
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import problems, texts
from .applier import apply
from .const import (
    CLOCK_REEVAL_SECONDS,
    CONF_INSTALLATION,
    CONF_SHADOW_MODE,
    DEBOUNCE_SECONDS,
    DEFAULT_PRECONDITION_MINUTES,
    DEFAULT_SHADOW_MODE,
    DOMAIN,
    EVENT_DECISION,
    EVENT_PRECONDITION_REFUSED,
    MIN_DEFERRAL_SECONDS,
    STORAGE_VERSION,
    UNUSABLE_GRACE_SECONDS,
)
from .engine import (
    WAITING_REASONS,
    ClimateState,
    DirectorConfig,
    ModeFamily,
    OpeningState,
    Plan,
    PresenceState,
    Reason,
    ResidentState,
    Season,
    WorldState,
    ZoneDecision,
    decide,
    wanted_target,
)
from .engine.constraints import active_family
from .engine.diff import Change, changes
from .engine.families import family_of, preferred_mode
from .engine.gates import asleep_at, house_wide_blocked
from .engine.models import SeasonSource
from .engine.serialise import config_from_dict

_LOGGER = logging.getLogger(__name__)

type ClimateDirectorEntry = ConfigEntry[ClimateDirectorCoordinator]

#: Toestanden die "thuis" betekenen voor een aanwezigheidsentiteit.
#: States meaning "home" for a presence entity.
_HOME_STATES = frozenset({"home", "on", "true"})

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

#: Hoe lang een eigen uit-commando geldt als verklaring voor een laat gemelde
#: `off`. Sommige integraties (melcloud) melden de stand pas een poll later;
#: meldt het apparaat dan alsnog `off`, dan is dat ons eigen commando en geen
#: hand aan het apparaat. Een kwartier dekt een trage poll ruimschoots, en is
#: kort genoeg dat een échte hand erna niet de hele dag onzichtbaar blijft.
#:
#: How long our own off command counts as the explanation for a late-reported
#: `off`. Some integrations (melcloud) report the state only a poll later; when
#: the appliance then reports `off`, that is our own command and not a hand at
#: the appliance. A quarter of an hour covers a slow poll amply, and is short
#: enough that a real hand afterwards does not stay invisible all day.
_COMMANDED_OFF_WINDOW = timedelta(minutes=15)

#: Seizoensnamen die uit een entiteit kunnen komen. Nederlands staat er bewust
#: bij: veel bestaande opstellingen hebben al een seizoenshelper die "Zomer" of
#: "Winter" rapporteert, en die hoort te blijven werken.
#:
#: Season names an entity may report. Dutch is deliberately included: many
#: existing setups already have a season helper reporting "Zomer" or "Winter",
#: and that should keep working.
_SEASON_NAMES: dict[str, Season] = {
    # Engels / English
    "summer": Season.SUMMER,
    "winter": Season.WINTER,
    "spring": Season.WINTER,
    "autumn": Season.WINTER,
    "fall": Season.WINTER,
    # Nederlands / Dutch
    "zomer": Season.SUMMER,
    "lente": Season.WINTER,
    "voorjaar": Season.WINTER,
    "herfst": Season.WINTER,
    "najaar": Season.WINTER,
    # Duits / German
    "sommer": Season.SUMMER,
    "frühling": Season.WINTER,
    "fruehling": Season.WINTER,
    "herbst": Season.WINTER,
    # Frans / French
    "été": Season.SUMMER,
    "ete": Season.SUMMER,
    "hiver": Season.WINTER,
    "printemps": Season.WINTER,
    "automne": Season.WINTER,
    # Spaans / Spanish
    "verano": Season.SUMMER,
    "invierno": Season.WINTER,
    "primavera": Season.WINTER,
    "otoño": Season.WINTER,
    "otono": Season.WINTER,
    # Arabisch / Arabic
    "صيف": Season.SUMMER,
    "الصيف": Season.SUMMER,
    "شتاء": Season.WINTER,
    "الشتاء": Season.WINTER,
    "ربيع": Season.WINTER,
    "خريف": Season.WINTER,
}


def temperature_from_state(
    entity_id: str, state: str, attributes: Mapping[str, Any]
) -> float | None:
    """Return the temperature an entity reports, or `None` when it reports none.

    Three shapes are read, in this order:

    * a plain numeric state, which is what a `sensor` gives;
    * `temperature` on a `weather` entity, whose own state is the forecast
      condition rather than a number;
    * `current_temperature` on anything else, so a zone can point straight at
      the indoor unit already measuring the room instead of needing a separate
      template sensor for it.

    The domain check matters: on a `climate` entity the `temperature` attribute
    is the *setpoint*, not the measurement. Reading that as the room temperature
    would make every zone believe it had already reached its target.
    """
    value = _as_float(state)
    if value is not None:
        return value
    if entity_id.startswith("weather."):
        return _as_float(attributes.get("temperature"))
    return _as_float(attributes.get("current_temperature"))


def season_from_state(raw: str | None) -> Season:
    """Return the season an entity's state names, or `UNKNOWN`.

    Spring and autumn map onto winter rather than onto nothing: `sensor.season`
    is a common source, and reading its shoulder seasons as "no season at all"
    would silently switch every season-gated duty off for half the year.
    """
    if not raw:
        return Season.UNKNOWN
    return _SEASON_NAMES.get(raw.strip().lower(), Season.UNKNOWN)


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


class ClimateDirectorCoordinator(DataUpdateCoordinator[Plan]):
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
        self.config: DirectorConfig = config_from_dict(
            entry.options.get(CONF_INSTALLATION) or entry.data.get(CONF_INSTALLATION) or {}
        )
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
        self._precondition: dict[str, datetime] = {}
        self._precondition_bypass: set[str] = set()
        self._refused: set[str] = set()
        # De bestandsnaam zegt nog "precondition" omdat hij dat ooit alleen
        # was. Hernoemen zou de lopende verzoeken van elke bestaande
        # installatie weggooien, en daar is de naam van een bestand het niet
        # waard.
        #
        # The file name still says "precondition" because that is all it once
        # held. Renaming it would throw away the running requests of every
        # existing installation, and a file name is not worth that.
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, storage_key(entry.entry_id)
        )
        self._waiting: dict[str, tuple[Reason, datetime]] = {}
        self._unusable_since: dict[str, datetime] = {}
        self._unusable_latest: dict[str, str] = {}
        """De onleesbare entiteiten van de laatste beslissingsronde.

        The unreadable entities of the latest decision round.
        """
        """Sinds wanneer elke ingestelde entiteit onleesbaar is.

        Since when each configured entity has been unreadable.
        """
        self._unsupported_since: dict[str, datetime] = {}
        """Sinds wanneer elke bron een stand vraagt die het apparaat niet kan.

        Since when each source asks a mode its appliance cannot run.
        """
        self._unapplied: dict[str, tuple[tuple[object, ...], int, datetime]] = {}
        """Hetzelfde verschil per apparaat: hoe vaak achter elkaar, en sinds wanneer.

        The same difference per appliance: how often in a row, and since when.
        """
        self._commanded_off: dict[str, datetime] = {}
        """Sinds wanneer elk apparaat voor het laatst een uit-commando kreeg.

        Since when each appliance last received an off command.
        """
        self.zone_overrides: dict[str, bool] = {}
        self._handed_back: dict[str, date] = {}
        self.zone_priorities: dict[str, int] = {}
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
        self._issued: Plan | None = None
        """Het plan dat nu uitgevoerd wordt, nog voordat het gepubliceerd is.

        `self.data` loopt een stap achter zolang de service calls draaien, en
        precies in dat gaatje meldt een apparaat zijn nieuwe stand. Zie
        `_we_wanted_it_off`.

        The plan being carried out, before it is published. `self.data` lags by
        one step while the service calls run, and an appliance reports its new
        state in exactly that gap. See `_we_wanted_it_off`.
        """

        self.last_changes: tuple[Change, ...] = ()
        """What the plan wants changed, whether or not it was carried out."""

        self.last_applied: tuple[Change, ...] = ()
        """What was actually carried out; always empty in shadow mode."""

        self._sent_setpoints: dict[str, tuple[str, float]] = {}
        """Het laatst werkelijk uitgevoerde `(hvac_mode, temperature)` per apparaat.

        `engine.diff.changes()` gebruikt dit als "al verstuurd" voor een apparaat
        dat geen setpoint terugmeldt. Alleen wat `apply()` écht heeft uitgevoerd
        komt erin; een setpoint waarvan de aanroep mislukte dus niet.

        The last really executed `(hvac_mode, temperature)` per appliance.
        `engine.diff.changes()` uses this as "already sent" for an appliance that
        reports no setpoint. Only what `apply()` really executed enters it, so a
        setpoint whose call failed does not.
        """

        self._lock = asyncio.Lock()
        self._closing = False
        """Zodra de installatie afgebroken wordt, mag er niets meer naar buiten.

        Once the installation is being torn down, nothing may go out anymore.
        """
        self._family_since: dict[str, datetime | None] = {}
        self._family_seen: dict[str, ModeFamily] = {}
        self._precipitation_seen_at: datetime | None = None
        """Wanneer de neerslagbron voor het laatst neerslag meldde.

        De nalooptijd hangt hieraan: een bui van vijf minuten hoort de regeling
        niet te laten stuiteren, dus zodra de bron neerslag meldt blijft dat
        nog even gelden nadat het ophoudt. Dit moment wordt vastgelegd in de
        toestandswijziging van de bron (`_notice_precipitation`) en bij het
        opstarten (`_note_precipitation_now`), nooit in de lezer zelf. Zonder
        opstartstap begint een herstart op "geen neerslag", en dat is de
        onschadelijke kant om fout te zitten: dan geldt de gewone buitengrens
        gewoon weer.

        The moment the precipitation source last reported precipitation. The
        grace period hangs off this: a five-minute shower should not make the
        regulation bounce, so once the source reports precipitation it keeps
        counting for a while after it stops. This moment is recorded in the
        source's own state change (`_notice_precipitation`) and at startup
        (`_note_precipitation_now`), never in the reader itself. Without the
        startup step a restart begins on "no precipitation", which is the
        harmless side to be wrong on: the ordinary outdoor bound simply applies
        again.
        """
        self._cancel_deferral: CALLBACK_TYPE | None = None
        self._clock_reeval_unsub: CALLBACK_TYPE | None = None
        self._cancel_precondition_wake: CALLBACK_TYPE | None = None
        self._debouncer = Debouncer(
            hass,
            _LOGGER,
            cooldown=DEBOUNCE_SECONDS,
            immediate=False,
            function=self._async_evaluate,
        )

    # -- opzetten / setting up ----------------------------------------------

    async def async_start(self) -> None:
        """Begin tracking entities; the first decision waits for Home Assistant.

        De eerste beslissing hoort niet thuis in het opzetten van de entry. Op
        dat moment is Home Assistant nog aan het opstarten: herstelde standen,
        automatiseringen en andere integraties komen pas daarna. Wie dan al
        beslist, ziet een half geladen wereld en kan een apparaat uitzetten dat
        er gewoon hoort te draaien.

        The first decision does not belong in the entry setup. At that point
        Home Assistant is still starting: restored states, automations and other
        integrations come only later. Whoever decides then sees a half-loaded
        world and can switch off an appliance that should simply be running.
        """
        entities = self.tracked_entities()
        if entities:
            self.config_entry.async_on_unload(
                async_track_state_change_event(self.hass, sorted(entities), self._handle_change)
            )
        self.config_entry.async_on_unload(self._cancel_pending_deferral)
        self.config_entry.async_on_unload(self._cancel_clock_reeval)
        self.config_entry.async_on_unload(async_at_started(self.hass, self._async_on_hass_started))

    async def _async_on_hass_started(self, _hass: HomeAssistant) -> None:
        """Restore what a restart left behind, decide once, and arm the clock.

        Herstellen, neerslag noteren en beslissen zijn drie stappen op één pad.
        Slaat er één om, dan is de schade het grootst als daardoor ook de
        vangnetklok nooit loopt: dan wacht elke tijdregel op een toevallige
        wijziging die nooit komt. De klok wordt daarom hoe dan ook gezet, en de
        uitzondering wordt gelogd in plaats van de integratie stil te leggen.

        Restoring, noting precipitation and deciding are three steps on one
        path. When one falls over the damage is greatest if the safety-net clock
        never starts either: every time rule then waits for a chance change that
        never comes. The clock is therefore armed no matter what, and the
        exception is logged rather than silencing the integration.
        """
        try:
            await self._async_restore_state()
            self._note_precipitation_now()
            await self._async_evaluate()
        except Exception:
            _LOGGER.exception("The first decision of %s failed", self.name)
        finally:
            self._schedule_clock_reeval()

    def tracked_entities(self) -> set[str]:
        """Return every entity whose change could alter a decision.

        Circuit units are included even when the director does not manage them:
        an indoor unit somebody switches on by remote still claims the
        compressor, and the plan has to be recomputed when it does.
        """
        entities: set[str] = set()

        if self.config.outdoor_sensor:
            entities.add(self.config.outdoor_sensor)
        if self.config.seasons.source is SeasonSource.ENTITY and self.config.seasons.entity_id:
            entities.add(self.config.seasons.entity_id)
        if self.config.precipitation.enabled:
            entities.add(self.config.precipitation.source)

        for zone in self.config.zones:
            if zone.indoor_sensor:
                entities.add(zone.indoor_sensor)
            if zone.presence_entity:
                entities.add(zone.presence_entity)
            entities.update(source.entity_id for source in zone.sources if source.entity_id)

        for circuit in self.config.circuits:
            entities.update(unit for unit in circuit.units if unit)

        entities.update(item.entity_id for item in self.config.generators if item.entity_id)

        for opening in self.config.openings:
            if opening.entity_id:
                entities.add(opening.entity_id)

        entities.update(item for item in self.config.holiday_calendars if item)

        for resident in self.config.residents:
            if resident.presence_entity:
                entities.add(resident.presence_entity)
            if resident.sleep_entity:
                entities.add(resident.sleep_entity)

        return entities

    def _calendar_says_holiday(self) -> bool:
        """Return whether a configured calendar has a holiday running right now.

        Een agenda-item telt zodra het loopt en het trefwoord erin voorkomt.
        Zonder trefwoord blijven de agenda's buiten beschouwing: raden welk item
        vakantie bedoelde is niet aan de integratie.

        An event counts once it is running and carries the keyword. Without a
        keyword the calendars are left alone: guessing which event meant a
        holiday is not the integration's call to make.
        """
        keyword = self.config.holiday_keyword.strip().casefold()
        if not keyword:
            return False

        for entity_id in self.config.holiday_calendars:
            state = self.hass.states.get(entity_id)
            if state is None or state.state != "on":
                continue
            haystack = " ".join(
                str(state.attributes.get(field) or "")
                for field in ("message", "summary", "description", "location")
            ).casefold()
            if keyword in haystack:
                return True

        return False

    # -- aanleidingen / triggers --------------------------------------------

    @callback
    def _handle_change(self, event: Event[EventStateChangedData]) -> None:
        """Queue a fresh decision after a tracked entity changed."""
        self._notice_precipitation(event)
        self._notice_hand(event)
        self._debouncer.async_schedule_call()

    @callback
    def _notice_precipitation(self, event: Event[EventStateChangedData]) -> None:
        """Remember the moment the precipitation source reports precipitation.

        Het moment hoort hier thuis, in de toestandswijziging van de bron zelf -
        niet in `_precipitation()`, dat alleen een antwoord teruggeeft. Elke
        nieuwe stand die neerslag is telt - dus ook een overgang tussen twee
        neerslagstanden (regen -> plensbui), want dan duurt de neerslag voort
        en hoort de nalooptijd mee te schuiven. Een overgang tussen twee droge
        standen (bewolkt -> zonnig) mag de nalooptijd niet verlengen.

        The moment belongs here, in the source's own state change - not in
        `_precipitation()`, which only returns an answer. Every new state that
        is precipitation counts - so also a transition between two
        precipitation states (rain -> pouring), since the precipitation then
        continues and the grace should move along. A transition between two dry
        states (cloudy -> sunny) must not extend the grace.
        """
        settings = self.config.precipitation
        if not settings.enabled or event.data["entity_id"] != settings.source:
            return
        new_state = event.data["new_state"]
        if new_state is None or new_state.state not in settings.states:
            return
        self._precipitation_seen_at = dt_util.now()

    @callback
    def _notice_hand(self, event: Event[EventStateChangedData]) -> None:
        """Record an appliance somebody switched off, or switched back on.

        Iemand die bij het apparaat zelf op uit drukt zegt daarmee iets, en dat
        overstemmen door het meteen weer aan te zetten is het ergste wat deze
        integratie kan doen. Dus: die zone valt stil tot dezelfde hand hem weer
        aanzet, of tot de volgende dag - want een besluit van gisteravond hoort
        vanochtend niet meer te gelden.

        Somebody pressing off on the appliance itself is saying something, and
        overriding that by switching it straight back on is the worst thing this
        integration can do. So: that zone falls silent until the same hand turns
        it back on, or until the next day - since last night's decision should
        not still hold this morning.
        """
        # In schaduwmodus stuurt de director niets, dus valt er ook niemand te
        # overstemmen - en daarmee vervalt de reden waarom dit bestaat. Wat er
        # wél gebeurt is dat de bestaande automatiseringen de hele dag apparaten
        # aan- en uitzetten. Elk van die uitzettingen las als een hand, waarna
        # de zone werd overgedragen en er niets meer te vergelijken viel. Juist
        # dat vergelijken is het enige product van deze modus.
        #
        # In shadow mode the director steers nothing, so there is nobody to
        # overrule - and with that the reason this exists falls away. What does
        # happen is that the existing automations switch appliances on and off
        # all day. Every one of those switch-offs read as a hand, after which
        # the zone was handed over and there was nothing left to compare. That
        # comparing is this mode's only product.
        if self.shadow:
            return

        entity_id = event.data["entity_id"]
        zones = self._zones_of(entity_id)
        if not zones:
            return

        new_state = event.data["new_state"]
        old_state = event.data["old_state"]
        if new_state is None or old_state is None:
            return

        # Wegvallen en terugkomen is geen hand aan het apparaat. `unavailable`
        # en `unknown` zijn geen standen maar het ontbreken van een stand, en
        # `family_of()` leest ze - terecht - als "geen idee wat dit ding doet".
        # Daardoor las een apparaat dat terugkwam op `off` als iemand die het
        # net had uitgezet, en viel die zone de rest van de dag stil. Andersom
        # net zo: een apparaat dat wegvalt zou een handmatige uitzetting
        # opheffen alsof iemand hem weer had aangezet.
        #
        # Dropping out and coming back is not a hand at the appliance.
        # `unavailable` and `unknown` are not modes but the absence of one, and
        # `family_of()` reads them - rightly - as "no telling what this thing is
        # doing". So an appliance coming back on `off` read as somebody having
        # just switched it off, and that zone fell silent for the rest of the
        # day. The other way round just as much: an appliance dropping out would
        # lift a hand-back as though somebody had switched it on again.
        if _unreadable(old_state.state) or _unreadable(new_state.state):
            return

        was = family_of(old_state.state)
        now = family_of(new_state.state)
        if was is now:
            return

        if now is not ModeFamily.NEUTRAL:
            # Weer aangezet, met de hand of door ons: hoe dan ook meedoen.
            # Zodra het apparaat op eigen kracht weer een actieve stand meldt,
            # is de verklaring "ons uit-commando" per definitie verbruikt - hoe
            # het `off` ertussenin ook gemeld is, ook via `unavailable`.
            #
            # Switched on again, by hand or by us: taking part either way. Once
            # the appliance reports an active mode on its own again, the "our
            # off command" explanation is spent by definition - however the
            # `off` in between was reported, `unavailable` included.
            self._commanded_off.pop(entity_id, None)
            cleared = False
            for zone in zones:
                cleared = self._handed_back.pop(zone, None) is not None or cleared
            if cleared:
                self._async_save_state()
            return

        # Ook een hand die het apparaat uitzet verbruikt het setpoint: bij de
        # volgende start hoort het opnieuw mee te gaan, want niemand weet wat
        # het apparaat in de tussentijd met zijn eigen setpoint deed.
        #
        # A hand switching the appliance off spends the setpoint too: the next
        # start must carry it again, since nobody knows what the appliance did
        # with its own setpoint in the meantime.
        self._sent_setpoints.pop(entity_id, None)

        # Alleen als wíj hem niet net hebben uitgezet. Ons eigen commando is
        # geen handmatige ingreep, en zou de zone anders permanent stilleggen.
        #
        # Only when we did not just switch it off ourselves. Our own command is
        # not a hand at the appliance, and would otherwise silence the zone for
        # good.
        if self._we_wanted_it_off(entity_id):
            # Ons uit-commando is nu aangekomen: de notitie die de late melding
            # moest verklaren is verbruikt. Een volgende `off` - nadat wij hem
            # zelf weer hebben aangezet - is dus weer gewoon een hand aan het
            # apparaat. Het venster blijft alleen nog als vangnet voor een
            # melding die nóóit aankomt.
            #
            # Our off command has now arrived: the note that had to explain the
            # late report is spent. A next `off` - after we switched it back on
            # ourselves - is therefore an ordinary hand at the appliance again.
            # The window remains only as a safety net for a report that never
            # arrives.
            self._commanded_off.pop(entity_id, None)
            return

        today = dt_util.now().date()
        if any(self._handed_back.get(zone) != today for zone in zones):
            for zone in zones:
                self._handed_back[zone] = today
            self._async_save_state()

    def _zones_of(self, entity_id: str) -> tuple[str, ...]:
        """Return every zone this climate entity serves, if the director drives it.

        Een gedeelde ketel staat onder meer dan één zone. Iemand die bij zo'n
        apparaat zelf op uit drukt zegt iets over dat apparaat, niet over de
        eerste zone die het toevallig bedient - dus elke zone die eraan hangt
        hoort stil te vallen, anders zet de overgeslagen zone het apparaat meteen
        weer aan. Een generator staat niet tussen de bronnen maar bedient
        dezelfde zones; ook die hoort mee te tellen, anders wordt een hand aan
        de gedeelde ketel nooit opgemerkt.

        A shared boiler sits under more than one zone. Somebody pressing off on
        such an appliance says something about the appliance, not about whichever
        zone happens to be listed first - so every zone hanging off it should fall
        silent, otherwise the skipped zone switches it straight back on. A
        generator is not listed among the sources but serves the same zones; it
        has to count too, otherwise a hand at the shared boiler is never noticed.
        """
        zones = [
            zone.zone_id for zone, source in self.config.sources() if source.entity_id == entity_id
        ]
        for generator in self.config.generators:
            if generator.entity_id != entity_id:
                continue
            zones.extend(
                zone.zone_id
                for zone in self.config.zones
                if generator.serves(zone.zone_id) and zone.zone_id not in zones
            )
        return tuple(zones)

    def _note_commanded_off(self, applied: tuple[Change, ...]) -> None:
        """Remember when we last told each appliance to stand down.

        `_we_wanted_it_off` kijkt hierin in plaats van alleen naar het plan dat
        nú op tafel ligt: een apparaat dat zijn stand pas een poll later meldt,
        rapporteert ons eigen `off` soms pas nadat het plan alweer is
        omgeslagen. Het plan zegt dan \"we wilden hem aan\", en zonder deze
        boekhouding las dat late bericht als een hand aan het apparaat.

        `_we_wanted_it_off` looks here rather than only at the plan on the
        table right now: an appliance reporting its state one poll late
        sometimes reports our own `off` only after the plan has flipped back.
        The plan then says \"we wanted it on\", and without this bookkeeping
        that late report read as a hand at the appliance.
        """
        now = dt_util.now()
        for change in applied:
            if family_of(change.command.hvac_mode) is not ModeFamily.NEUTRAL:
                continue
            # Het apparaat gaat uit: een setpoint dat bij het uitzetten vergeten
            # wordt (of met de hand verzet) hoort bij de volgende start gewoon
            # opnieuw te gaan. Anders bleef "al verstuurd" eeuwig staan en kwam
            # het setpoint nooit meer mee.
            #
            # The appliance is going off: a setpoint forgotten on the way out
            # (or moved by hand) must simply be sent again at the next start.
            # Otherwise "already sent" stood forever and the setpoint never
            # came along again.
            self._sent_setpoints.pop(change.entity_id, None)
            reported = self.hass.states.get(change.entity_id)
            if (
                reported is not None
                and not _unreadable(reported.state)
                and family_of(reported.state) is ModeFamily.NEUTRAL
            ):
                # Het apparaat meldt ons uit-commando al: er is geen late
                # melding meer te verklaren, en een oude notitie is daarmee ook
                # verbruikt. `_notice_hand` kan deze notitie niet zelf opruimen
                # op dit moment, want die liep al tijdens `apply` - vóórdat
                # deze boekhouding geschreven werd.
                #
                # The appliance already reports our off command: there is no
                # late report left to explain, and any old note is spent with
                # it. `_notice_hand` cannot clear it here itself, because it
                # already ran during `apply` - before this bookkeeping was
                # written.
                self._commanded_off.pop(change.entity_id, None)
            else:
                self._commanded_off[change.entity_id] = now

    def _we_wanted_it_off(self, entity_id: str) -> bool:
        """Return whether we told this appliance to stand down, or meant to.

        Eerst de boekhouding van wat er écht is uitgezonden: die dekt ook het
        apparaat dat zijn stand pas een poll later meldt, wanneer het plan
        alweer is omgeslagen. Daarna het plan dat op tafel ligt, niet het plan
        dat af is - een apparaat meldt zijn nieuwe stand terwijl de service
        call nog loopt, en op dat moment staat het gepubliceerde besluit nog op
        de vorige ronde.

        First the bookkeeping of what was really sent: that also covers the
        appliance reporting its state one poll late, when the plan has already
        flipped back. Then the plan on the table, not the plan that is
        finished - an appliance reports its new state while the service call is
        still running, and at that moment the published decision is still the
        previous round's.
        """
        when = self._commanded_off.get(entity_id)
        if when is not None and dt_util.now() - when <= _COMMANDED_OFF_WINDOW:
            return True

        plan = self._issued or self.data
        if plan is None:
            return False
        for command in plan.commands:
            if command.entity_id == entity_id:
                return family_of(command.hvac_mode) is ModeFamily.NEUTRAL
        return False

    def _zones_handed_back(self, now: datetime, residents: dict[str, ResidentState]) -> set[str]:
        """Return the zones a hand stood down today, forgetting yesterday's.

        De datum is de hele vervaltermijn. Wie gisteravond de slaapkamer uitzette
        wil vanochtend niet dat hij nog steeds stilstaat, en een teller van
        vierentwintig uur zou dat wel doen.

        Dit gaat alleen over de hand aan het apparaat. De overrideschakelaar
        staat daar los van en blijft staan tot iemand hem zelf uitzet: dat is
        geen besluit van vanavond maar een besluit dat je terugdraait. Ze werden
        hier allebei weggegooid, waardoor een zone die je met opzet had
        overgedragen de eerste nacht alweer meedeed.

        The date is the whole expiry. Whoever switched the bedroom off last night
        does not want it still standing still this morning, and a twenty-four
        hour timer would do exactly that.

        This is only about the hand at the appliance. The override switch stands
        apart from it and holds until somebody turns it off themselves: that is
        not tonight's decision but one you undo. Both were thrown away here, so a
        zone deliberately handed over rejoined on the first night.
        """
        if self._everyone_asleep(now, residents) or self._house_is_empty(residents):
            if self._handed_back:
                self._handed_back.clear()
                self._async_save_state()
            return set()

        today = now.date()
        kept = {zone: day for zone, day in self._handed_back.items() if day == today}
        if kept != self._handed_back:
            self._handed_back = kept
            self._async_save_state()
        return set(self._handed_back)

    def _everyone_asleep(self, now: datetime, residents: dict[str, ResidentState]) -> bool:
        """Return whether everybody who is home has turned in.

        Dan is de dag voorbij en hoort een zone die iemand met de hand stilzette
        weer mee te doen - precies zoals de automatiseringen het deden. Wachten
        tot middernacht zou de zone een paar uur langer stil houden dan iemand
        bedoelde, en dat merk je pas de volgende ochtend.

        Het slaapvenster telt hier net zo hard als in de engine: buiten die uren
        is een oplader gewoon een oplader, en is de dag niet voorbij.

        The day is then over, and a zone somebody silenced by hand should join in
        again - exactly as the automations did it. Waiting for midnight would
        hold the zone still a few hours longer than anybody meant, and you only
        notice that the next morning.

        The sleep window counts here exactly as it does in the engine: outside
        those hours a charger is just a charger, and the day is not over.
        """
        at_home = [
            resident
            for resident in self.config.residents
            if resident.presence_entity and residents[resident.resident_id].home
        ]
        if not at_home:
            return False
        return all(
            bool(resident.sleep_entity)
            and asleep_at(resident, residents[resident.resident_id].asleep, now)
            for resident in at_home
        )

    def _house_is_empty(self, residents: dict[str, ResidentState]) -> bool:
        """Return whether none of the tracked residents is home.

        Wie een apparaat met de hand uitzette deed dat voor de kamer waar hij op
        dat moment in zat. Is er niemand meer, dan is dat geval voorbij, en
        niets is zo vervelend als thuiskomen in een kamer die al dagen stilstaat
        omdat er ooit iemand op uit heeft gedrukt.

        Whoever switched an appliance off by hand did that for the room they were
        sitting in at the time. With nobody left, that case is over - and nothing
        is as annoying as coming home to a room that has stood still for days
        because somebody once pressed off.
        """
        tracked = [resident for resident in self.config.residents if resident.presence_entity]
        if not tracked:
            return False
        return not any(residents[resident.resident_id].home for resident in tracked)

    @callback
    def async_request_evaluation(self) -> None:
        """Ask for a fresh decision, from a switch or a service call."""
        self._debouncer.async_schedule_call()

    @callback
    def _cancel_clock_reeval(self) -> None:
        """Drop the scheduled safety-net tick, if there is one."""
        if self._clock_reeval_unsub is not None:
            self._clock_reeval_unsub()
            self._clock_reeval_unsub = None

    @callback
    def _schedule_clock_reeval(self) -> None:
        """Arm the periodic safety-net evaluation, replacing any earlier one.

        Het vangnet voor tijdregels die vanzelf verlopen: een raamvertraging,
        een aanwezigheids-nalooptijd, de neerslag-grace, de eerstvolgende
        vensterrand en middernacht. Zonder deze klok hangt zo'n omslagpunt op
        toeval - er moet toevallig iets anders veranderen voordat er opnieuw
        besloten wordt. Een ronde zonder verschil kost geen service call, dus
        elke minuut is goedkoop.

        The safety net for time rules that lapse by themselves: a window delay,
        a presence grace period, the precipitation grace, the next window edge
        and midnight. Without this clock such a turning point depends on chance
        - something else must happen to change before another decision is made.
        A round without a difference costs no service call, so every minute is
        cheap.
        """
        self._cancel_clock_reeval()
        self._clock_reeval_unsub = async_call_later(
            self.hass, CLOCK_REEVAL_SECONDS, self._on_clock_reeval
        )

    @callback
    def _on_clock_reeval(self, _now: datetime) -> None:
        """Re-evaluate on the clock, and arm the next tick."""
        self._clock_reeval_unsub = None
        self.async_request_evaluation()
        self._schedule_clock_reeval()

    async def async_shutdown(self) -> None:
        """Stop deciding and drop every pending timer.

        Eerst de lopende ronde laten uitlopen: die kan service calls hebben
        uitstaan en schrijft daarna nog naar buiten (meldingen, timers). Wie
        hier meteen doorging, zag na de unload nog een melding herleven of een
        timer ontstaan die nooit meer wordt opgeruimd. Een ronde die langer dan
        vijf seconden blijft hangen, wordt niet langer tegengehouden - dan is
        het gedrag hetzelfde als vóór deze wacht, en dat is de veilige kant.

        First let the running round finish: it may have service calls out and
        writes outwards afterwards (notices, timers). Going on immediately let a
        notice revive or a timer come into being after the unload, never to be
        cleaned up again. A round hanging around for more than five seconds is
        no longer held up - behaviour is then the same as before this wait, and
        that is the safe side.
        """
        self._closing = True
        try:
            # Vijf seconden is genoeg voor een lopende ronde; langer wachten
            # bevriest de configuratiepagina tijdens een herlaadbeurt.
            #
            # Five seconds is enough for a running round; waiting longer freezes
            # the configuration page during a reload.
            async with asyncio.timeout(5):
                async with self._lock:
                    pass
        except TimeoutError:
            _LOGGER.warning("Een beslisronde liep nog bij het afsluiten van %s", self.name)
        self._cancel_pending_deferral()
        self._cancel_clock_reeval()
        self._cancel_pending_precondition_wake()
        self._debouncer.async_shutdown()
        # Een uitgestelde opslag kan nog uitstaan: de store schrijft één seconde
        # na de laatste wijziging. Bij een herlaadbeurt is dat geen bezwaar, maar
        # bij een verwijdering zou die schrijfactie het bestand terugschrijven ná
        # `async_remove_entry`. Daarom hier zelf wegschrijven en de uitgestelde
        # schrijfactie afbreken, zodat het bestand na een verwijdering echt weg
        # blijft.
        #
        # A delayed store write may still be pending: the store writes one second
        # after the last change. On a reload that is fine, but on a removal that
        # write would resurrect the file after `async_remove_entry`. So write it
        # away here and cancel the delayed write, so the file really stays gone
        # after a removal.
        await self._store.async_save(self._store_payload())
        self._store._async_cleanup_delay_listener()  # noqa: SLF001 - HA's Store has no public cancel
        await super().async_shutdown()

    # -- beslissen / deciding ------------------------------------------------

    async def _async_evaluate(self) -> None:
        """Read the world, decide, apply, and report."""
        if self._closing:
            return
        async with self._lock:
            world = self.build_world()
            self._remember_families(world)
            world = self._with_family_history(world)

            plan = decide(self.config, world, self.data)
            self.world = world
            self._issued = plan

            # De verschillenlijst wordt hier bewaard, niet wat de applier
            # ervan uitgevoerd kreeg. In schaduwmodus is dit precies "wat de
            # director gedaan zou hebben terwijl iets anders het huis stuurt" -
            # het getal waar de hele meeloopfase om draait.
            #
            # The difference list is kept here, not what the applier managed to
            # execute. In shadow mode this is exactly "what the director would
            # have done while something else steers the house" - the number the
            # whole shadow phase is about.
            self.last_changes = changes(plan, world, self._sent_setpoints)
            self.last_applied = ()

            try:
                self.last_applied = await apply(self.hass, self.last_changes, shadow=self.shadow)
            except Exception:  # noqa: BLE001 - one bad call must not stop the loop
                _LOGGER.exception("Applying the climate plan failed")
            self._note_commanded_off(self.last_applied)
            for change in self.last_applied:
                if change.set_temperature and change.command.temperature is not None:
                    self._sent_setpoints[change.entity_id] = (
                        change.command.hvac_mode,
                        change.command.temperature,
                    )

            if self._closing:
                return
            # Het publiceren van het plan hoort altijd te gebeuren, ook als een
            # van de meldingen eromheen een uitzondering gooit. Gebeurde dat
            # niet, dan bleef elke entiteit ronde na ronde op het vorige plan
            # staan terwijl de lus gewoon doordraaide - de stilste manier om
            # een huis te bevriezen.
            #
            # Publishing the plan must always happen, even when one of the
            # notices around it raises. Otherwise every entity stayed on the
            # previous plan round after round while the loop kept running - the
            # quietest way to freeze a house.
            try:
                self._fire_events(plan)
                self._fire_refusals(plan)
                self._note_waiting(plan)
                self._report_unreadable()
                self._report_unsupported_modes()
                self._report_command_not_taking()
                self._schedule_deferral(plan)
            finally:
                self.async_set_updated_data(plan)

    # -- vooruit verwarmen / pre-conditioning --------------------------------

    def live_preconditions(self) -> dict[str, datetime]:
        """Return the requests that have not run out, without touching anything.

        Voor wie alleen wil weten hoe het ervoor staat: de diagnose. Die hoort
        niets te wijzigen aan het huis waar hij een storing van vastlegt.

        For anyone who only wants to know where things stand: the diagnostics.
        Those should alter nothing about the house whose fault they capture.
        """
        return _still_running(self._precondition, dt_util.now())

    def _live_preconditions(self) -> dict[str, datetime]:
        """Return the requests that have not run out, dropping the rest.

        Pruned on reading rather than on a timer: an expired request is over
        whether or not anything got round to noticing.
        """
        self._precondition = _still_running(self._precondition, dt_util.now())
        self._precondition_bypass &= set(self._precondition)
        return dict(self._precondition)

    @callback
    def async_precondition(
        self,
        zone_ids: list[str] | None,
        minutes: float | None,
        *,
        ignore_openings: bool = False,
    ) -> dict[str, datetime]:
        """Start warming the named zones up for somebody on their way home.

        The request is capped at the configured maximum, so asking for longer
        than the installation allows shortens the request rather than refusing
        it: the intent was clear, only the number was wrong.

        `minutes` is `None` when the call omitted the duration - then the
        configured maximum applies, which is what the blueprint relies on when
        it confirms a refused request. A non-positive number is refused instead:
        zero minutes is no request, and treating it as the maximum would turn a
        typo into the longest run the installation allows.

        `minutes` is `None` als de aanroep de duur wegliet - dan geldt het
        ingestelde maximum, precies wat de blueprint verwacht als hij een
        geweigerd verzoek bevestigt. Een niet-positief getal wordt geweigerd:
        nul minuten is geen verzoek, en dat als maximum tellen zou van een
        typefout de langste run maken die de installatie toestaat.

        `ignore_openings` laat het verzoek doorgaan met een raam of deur open.
        Standaard weigert dat, en terecht - stoken tegen de buitenlucht in is
        weggegooid geld. Wie het raam zelf openzette weet dat en mag zeggen:
        toch doen. De keuze hoort bij het verzoek, niet bij de aanroep, want de
        poort wordt telkens opnieuw beoordeeld.

        `ignore_openings` lets the request run with a window or door open. That
        is refused by default, and rightly so - heating against the outside air
        is money thrown away. Whoever opened the window knows that and may say:
        do it anyway. The choice belongs to the request rather than to the call,
        since the gate is judged afresh every time.
        """
        ceiling = self.config.gates.max_precondition
        if ceiling.total_seconds() <= 0:
            # De instellingen laten dit niet toe, maar een met de hand bewerkte
            # configuratie kan het wel. Dan mag de knop niet in stilte niets
            # doen - de validate()-waarschuwing op het bewaarscherm noemt het,
            # en dit logbericht legt het vast voor wie de melding wegklikte.
            #
            # The settings do not allow this, but a hand-edited configuration
            # can. The button then may not silently do nothing - the validate()
            # warning on the save screen names it, and this log line records it
            # for whoever dismissed the notice.
            _LOGGER.warning("Pre-conditioning is disabled: max_precondition is zero or negative")
            return {}
        if minutes is None:
            length = ceiling
        else:
            if minutes <= 0:
                return {}
            length = min(timedelta(minutes=minutes), ceiling)
        until = dt_util.now() + length

        known = {zone.zone_id for zone in self.config.zones}
        unknown = sorted(set(zone_ids or ()) - known)
        if unknown:
            _LOGGER.warning(
                "Pre-conditioning asked for unknown zones, ignored: %s",
                ", ".join(unknown),
            )
        chosen = [zone_id for zone_id in (zone_ids or known) if zone_id in known]
        for zone_id in chosen:
            self._precondition[zone_id] = until
            if ignore_openings:
                self._precondition_bypass.add(zone_id)
            else:
                self._precondition_bypass.discard(zone_id)

        if chosen:
            self._async_save_state()
            self._wake_at_the_first_expiry()
            self.async_request_evaluation()
        return dict.fromkeys(chosen, until)

    # -- met de hand gegeven, dus bewaren / given by hand, so kept ----------

    def _store_payload(self) -> dict[str, Any]:
        """Return the hand-given state worth keeping across a restart."""
        return {
            "until": {zone_id: until.isoformat() for zone_id, until in self._precondition.items()},
            "bypass": sorted(self._precondition_bypass),
            "handed_back": {zone_id: day.isoformat() for zone_id, day in self._handed_back.items()},
        }

    @callback
    def _async_save_state(self) -> None:
        """Write away wat een mens met de hand heeft gezegd.

        Een verzoek is het enige dat een leeg huis mag laten draaien, en het is
        met de hand gegeven. Herstart Home Assistant tien minuten later, dan is
        het zonder dit spoorloos weg - en de gebruiker komt thuis in een koud
        huis zonder te weten waarom.

        Hetzelfde geldt voor een apparaat dat iemand bij het apparaat zelf heeft
        uitgezet. Dat besluit hoort tot de volgende dag te blijven staan, en een
        herstart is geen reden om er alsnog overheen te gaan - dat is precies
        het ergste wat deze integratie kan doen.

        Wat hier NIET in staat, en na een herstart dus opnieuw begint: de
        wachtteller achter de vastloopmelder, en het moment waarop een circuit
        zijn taak aannam. Die eerste meldt hooguit een kwartier later, die
        tweede geeft een apparaat hooguit een extra pauze. Allebei tijdelijk, en
        allebei aan de veilige kant.

        Write away what a person said by hand.

        A request is the only thing allowed to run an empty house, and it was
        given by hand. If Home Assistant restarts ten minutes later it is gone
        without trace - and the user comes home to a cold house with no idea
        why.

        The same holds for an appliance somebody switched off at the appliance
        itself. That decision should stand until the next day, and a restart is
        no reason to override it after all - which is precisely the worst thing
        this integration can do.

        What is NOT in here, and therefore starts afresh after a restart: the
        waiting clock behind the stuck sensor, and the moment a circuit took on
        its duty. The first reports a quarter of an hour later at worst, the
        second costs an appliance one extra pause at worst. Both temporary, and
        both on the safe side.
        """
        self._store.async_delay_save(self._store_payload, 1)

    async def _async_restore_state(self) -> None:
        """Read back what was standing before the restart.

        Verlopen verzoeken komen niet terug: de tijd liep door terwijl Home
        Assistant weg was, en een verzoek van gisteren alsnog uitvoeren is
        erger dan het te vergeten. Een handmatige uitzetting van gisteren
        vervalt om dezelfde reden - de datum is de hele vervaltermijn.

        Een ouder bestand draagt nog geen `handed_back`. Dat leest gewoon als
        niets, dus de opslagversie hoeft er niet voor omhoog: er valt niets te
        migreren aan een sleutel die er niet was.

        Elk veld wordt net zo vergevingsgezind gelezen als `serialise.py`: een
        waarde met een andere vorm dan verwacht telt als afwezig, niet als
        reden om de hele integratie stil te leggen. Alleen een bestand dat in
        het geheel niet te lezen is wordt opzij gezet.

        Expired requests do not come back: time ran on while Home Assistant was
        away, and carrying out yesterday's request after the fact is worse than
        forgetting it. Yesterday's hand-back lapses for the same reason - the
        date is the whole expiry.

        An older file carries no `handed_back` yet. That simply reads as
        nothing, so the storage version need not go up for it: there is nothing
        to migrate about a key that was never there.

        Every field is read as forgivingly as `serialise.py`: a value of a
        different shape than expected counts as absent, not as a reason to
        silence the whole integration. Only a file that cannot be read at all
        is put aside.
        """
        try:
            stored = await self._store.async_load()
        except Exception:
            _LOGGER.exception("Reading the stored state of %s failed", self.name)
            await self._quarantine_storage()
            return

        if not stored:
            return

        if not isinstance(stored, Mapping):
            _LOGGER.error("The stored state of %s has no readable shape", self.name)
            await self._quarantine_storage()
            return

        now = dt_util.now()

        until_raw = stored.get("until")
        if isinstance(until_raw, Mapping):
            for zone_id, raw in until_raw.items():
                until = dt_util.parse_datetime(str(raw))
                if until is not None and now < until:
                    self._precondition[zone_id] = until

        bypass_raw = stored.get("bypass")
        if isinstance(bypass_raw, (list, tuple, set)):
            self._precondition_bypass = {
                zone_id for zone_id in bypass_raw if zone_id in self._precondition
            }

        handed_raw = stored.get("handed_back")
        if isinstance(handed_raw, Mapping):
            today = now.date()
            for zone_id, raw in handed_raw.items():
                day = dt_util.parse_date(str(raw))
                if day == today:
                    self._handed_back[zone_id] = day

        self._wake_at_the_first_expiry()

    async def _quarantine_storage(self) -> None:
        """Move an unreadable state file aside and tell the user.

        Het bestand is onleesbaar of heeft een vorm die nergens op lijkt. De
        director begint dan met een lege staat - verzoeken en handmatige
        uitzettingen van voor de herstart zijn weg - en het bestand gaat opzij
        zodat elke volgende herstart er niet opnieuw over struikelt. De melding
        zegt dat het gebeurd is; het bestand zelf blijft staan voor wie het uit
        een back-up terug wil zetten.

        The file is unreadable or shaped like nothing at all. The director then
        starts with an empty state - requests and hand-backs from before the
        restart are gone - and the file is moved aside so every next restart
        does not trip over it again. The notice says it happened; the file
        itself stays for anyone wanting to put it back from a backup.
        """
        path = Path(self._store.path)
        # Geen `isoformat()`: de dubbele punten daarin mogen niet in een
        # Windows-bestandsnaam. Not `isoformat()`: its colons are not allowed
        # in a Windows file name.
        stamp = dt_util.utcnow().strftime("%Y%m%dT%H%M%S%f")
        corrupt = path.with_name(f"{path.name}.corrupt.{stamp}")
        try:
            await self.hass.async_add_executor_job(os.rename, path, corrupt)
        except OSError:
            _LOGGER.exception("Moving the unreadable state file %s aside failed", path)
        problems.async_report_corrupt_storage(
            self.hass,
            self.config_entry.entry_id,
            self.config_entry.title,
            str(corrupt),
        )

    @callback
    def async_cancel_precondition(self, zone_ids: list[str] | None) -> None:
        """Call the whole thing off, for the named zones or for all of them."""
        known = {zone.zone_id for zone in self.config.zones}
        if zone_ids is None:
            self._precondition.clear()
            self._precondition_bypass.clear()
        else:
            unknown = sorted(set(zone_ids) - known)
            if unknown:
                _LOGGER.warning(
                    "Cancel pre-conditioning asked for unknown zones, ignored: %s",
                    ", ".join(unknown),
                )
            for zone_id in zone_ids:
                self._precondition.pop(zone_id, None)
                self._precondition_bypass.discard(zone_id)
        # De wekker gaat mee met de verzoeken die er nog staan. Is er niets
        # meer, dan blijft de staande wekker gewoon aflopen: hij vraagt dan een
        # beslisronde die niets te doen vindt, en een ronde zonder verschil kost
        # geen service call.
        #
        # The alarm follows the requests still standing. With nothing left the
        # standing alarm simply runs out: it then asks for a round that finds
        # nothing to do, and a round without a difference costs no service call.
        self._wake_at_the_first_expiry()
        self._async_save_state()
        self.async_request_evaluation()

    @callback
    def _wake_at_the_first_expiry(self) -> None:
        """Set the alarm on the first request that is still to run out.

        Op de opgeschoonde lijst, niet op de ruwe. Een verzoek dat er nog in
        staat maar allang voorbij is, wint anders de `min()`, waarna
        `_preconditions_expire_at` ziet dat dat moment achter ons ligt en
        helemaal geen wekker zet - ook niet voor het verzoek dat wel loopt.

        On the pruned list, not on the raw one. A request still sitting there
        but long since over otherwise wins the `min()`, after which
        `_preconditions_expire_at` sees that moment lies behind us and sets no
        alarm at all - not even for the request that is running.
        """
        pending = self._live_preconditions()
        if pending:
            self._preconditions_expire_at(min(pending.values()))

    @callback
    def _preconditions_expire_at(self, until: datetime) -> None:
        """Re-evaluate the moment the request runs out.

        Zonder dit blijft een lege woning doorstoken tot er toevallig iets
        anders verandert, en op een stille middag gebeurt dat lang niet.

        Er staat er altijd maar één, op het eerstvolgende verzoek dat afloopt;
        gaat die af, dan zet hij zichzelf op het verzoek daarna. Zonder dat
        handvat bleef er bij elk verzoek een wekker hangen die na het afsluiten
        van de installatie alsnog afging, op een coordinator die er niet meer
        was.

        Without this an empty house keeps burning until something else happens
        to change, and on a quiet afternoon that is a long wait.

        There is only ever one, set on the first request to run out; when it
        fires it sets itself on the next one. Without that handle every request
        left an alarm hanging that went off after the installation was torn
        down, on a coordinator that was no longer there.
        """
        self._cancel_pending_precondition_wake()
        seconds = (until - dt_util.now()).total_seconds()
        if seconds <= 0:
            return
        self._cancel_precondition_wake = async_call_later(
            self.hass, seconds + 1, self._on_precondition_expiry
        )

    @callback
    def _on_precondition_expiry(self, _now: datetime) -> None:
        """Decide again now a request has run out, and wait for the next one."""
        self._cancel_precondition_wake = None
        self.async_request_evaluation()
        self._wake_at_the_first_expiry()

    @callback
    def _cancel_pending_precondition_wake(self) -> None:
        """Drop the scheduled wake-up, if there is one."""
        if self._cancel_precondition_wake is not None:
            self._cancel_precondition_wake()
            self._cancel_precondition_wake = None

    # -- onbruikbare entiteiten / unusable entities --------------------------

    def unusable_entities(self) -> dict[str, str]:
        """Return the configured entities that cannot be read right now.

        Een verkeerd getikte entiteit bestaat gewoon niet, en een sensor die
        wegvalt leest als niets. In beide gevallen valt er niets om: de poort
        die erop leunt gaat dicht, de zone doet niets, en dat is van buiten niet
        te onderscheiden van een zone die niets hoeft te doen. Daarom staat het
        hier apart, in plaats van dat je het uit een stille zone moet afleiden.

        A mistyped entity simply does not exist, and a sensor that drops out
        reads as nothing. Neither breaks anything: the gate leaning on it closes,
        the zone does nothing, and from the outside that is indistinguishable
        from a zone with nothing to do. Hence this, rather than leaving you to
        infer it from a silent zone.
        """
        found: dict[str, str] = {}
        for entity_id in sorted(self.tracked_entities()):
            state = self.hass.states.get(entity_id)
            if state is None:
                found[entity_id] = "missing"
            elif _unreadable(state.state):
                found[entity_id] = state.state

        # Een leesbare seizoensentiteit met een onherkenbare staat is net zo
        # stil kapot als een onleesbare: het seizoen wordt UNKNOWN en alles wat
        # eraan hangt - zomerkoeling bijvoorbeeld - valt weg zonder dat er iets
        # van te zien is. De entiteit bestaat en is leesbaar, dus de gewone
        # controle hierboven pakt hem niet.
        #
        # A readable season entity with an unrecognised state is just as
        # silently broken as an unreadable one: the season becomes UNKNOWN and
        # everything hanging off it - summer cooling, say - falls away with
        # nothing to show for it. The entity exists and reads fine, so the
        # ordinary check above does not catch it.
        if self.config.seasons.source is SeasonSource.ENTITY and self.config.seasons.entity_id:
            entity_id = self.config.seasons.entity_id
            state = self.hass.states.get(entity_id)
            if (
                state is not None
                and not _unreadable(state.state)
                and season_from_state(state.state) is Season.UNKNOWN
            ):
                found[entity_id] = f"unrecognized season: {state.state}"

        # Een leesbare temperatuursensor die geen getal oplevert is net zo stil
        # kapot als een onleesbare: de zone leest NO_INDOOR_TEMPERATURE en doet
        # niets, zonder dat er iets van te zien is. De entiteit bestaat en is
        # leesbaar, dus de gewone controle hierboven pakt hem niet.
        #
        # A readable temperature sensor that yields no number is just as
        # silently broken as an unreadable one: the zone reads
        # NO_INDOOR_TEMPERATURE and does nothing, with nothing to show for it.
        # The entity exists and reads fine, so the ordinary check above does
        # not catch it.
        sensors: set[str] = set()
        if self.config.outdoor_sensor:
            sensors.add(self.config.outdoor_sensor)
        for zone in self.config.zones:
            if zone.indoor_sensor:
                sensors.add(zone.indoor_sensor)
        for entity_id in sorted(sensors):
            if entity_id in found:
                continue
            state = self.hass.states.get(entity_id)
            if state is None or _unreadable(state.state):
                continue
            attributes = getattr(state, "attributes", {})
            if temperature_from_state(entity_id, state.state, attributes) is None:
                found[entity_id] = "no number"

        return found

    @callback
    def _report_unreadable(self) -> None:
        """Put the entities that stay unreadable under Repairs, or take them away."""
        problems.async_report_unreadable(
            self.hass,
            self.config_entry.entry_id,
            self.config_entry.title,
            self._note_unusable(),
        )

    @callback
    def _note_unusable(self) -> dict[str, str]:
        """Record since when each entity has been unreadable, and return the lasting ones.

        Geschreven op het beslispad en niet in de lezer: `unusable_entities()`
        geeft alleen een antwoord, en een lezer met een bijwerking is precies
        de fout die de neerslagnalooptijd ooit onzichtbaar maakte.

        De teller begint opnieuw zodra een entiteit terugkomt. Wie een minuut
        wegvalt bij een herstart is geen storing; wie een kwartier weg is wel.

        Written on the decision path rather than in the reader:
        `unusable_entities()` only gives an answer, and a reader with a side
        effect is exactly the mistake that once made the precipitation grace
        invisible.

        The clock restarts the moment an entity returns. Dropping out for a
        minute during a restart is no fault; being gone for a quarter of an hour
        is.
        """
        now = dt_util.now()
        found = self.unusable_entities()
        self._unusable_latest = found
        self._unusable_since = {
            entity_id: self._unusable_since.get(entity_id, now) for entity_id in found
        }
        grace = timedelta(seconds=UNUSABLE_GRACE_SECONDS)
        return {
            entity_id: state
            for entity_id, state in found.items()
            if now - self._unusable_since[entity_id] >= grace
        }

    # -- ongeschikte standen / unsupported modes ------------------------------

    def unsupported_modes(self) -> dict[str, str]:
        """Return the sources whose role asks what the appliance cannot deliver.

        De rol zegt wat de installatie wil, het apparaat wat het kan. Een bron
        met rol HEAT_COOL op een apparaat dat alleen `heat` en `off` meldt,
        wordt door de engine voor koelen overgeslagen - en dat is van buiten
        niet te onderscheiden van een zone die niets hoeft. Hetzelfde geldt voor
        een setpoint buiten `min_temp`/`max_temp`: de engine klemt het dan naar
        de dichtstbijzijnde grens, maar de gevraagde temperatuur wordt nooit
        gehaald. Onleesbare apparaten blijven hier buiten: die hebben hun eigen
        melding.

        The role says what the installation wants, the appliance what it can. A
        source with role HEAT_COOL on an appliance reporting only `heat` and
        `off` is skipped for cooling by the engine - and from the outside that
        is indistinguishable from a zone with nothing to do. The same holds for
        a setpoint outside `min_temp`/`max_temp`: the engine clamps it to the
        nearest bound, but the asked temperature is never reached. Unreadable
        appliances are left out here: they have a notice of their own.
        """
        found: dict[str, set[str]] = {}
        for zone, source in self.config.sources():
            state = self.hass.states.get(source.entity_id)
            if state is None or _unreadable(state.state):
                continue
            complaints: set[str] = set()
            # De rol hangt aan de bron, niet aan het apparaat. Hetzelfde apparaat
            # kan in kamer A HEAT_ONLY zijn en in kamer B HEAT_COOL; een wacht
            # op het apparaat sloeg de koelrol van kamer B dan over. De set
            # hieronder ontdubbelt toch al.
            #
            # The role hangs on the source, not on the appliance. The same
            # appliance can be HEAT_ONLY in room A and HEAT_COOL in room B; a
            # guard on the appliance then skipped room B's cool role. The set
            # below deduplicates anyway.
            modes = _as_modes(state.attributes.get("hvac_modes"))
            if modes is not None:
                complaints.update(
                    preferred_mode(family)
                    for family in (ModeFamily.HEAT, ModeFamily.COOL)
                    if source.supports(family) and preferred_mode(family) not in modes
                )
            minimum = _as_float(state.attributes.get("min_temp"))
            maximum = _as_float(state.attributes.get("max_temp"))
            for family in (ModeFamily.HEAT, ModeFamily.COOL):
                if not source.supports(family):
                    continue
                settings = zone.settings_for(family)
                if settings is None:
                    continue
                if minimum is not None and settings.target < minimum:
                    complaints.add(f"{preferred_mode(family)} {settings.target}° < {minimum}°")
                if maximum is not None and settings.target > maximum:
                    complaints.add(f"{preferred_mode(family)} {settings.target}° > {maximum}°")
            if complaints:
                found.setdefault(source.entity_id, set()).update(complaints)
        return {entity_id: ", ".join(sorted(parts)) for entity_id, parts in found.items()}

    @callback
    def _note_unsupported(self) -> dict[str, str]:
        """Record since when each source has asked an unsupported mode, with grace."""
        now = dt_util.now()
        found = self.unsupported_modes()
        self._unsupported_since = {
            entity_id: self._unsupported_since.get(entity_id, now) for entity_id in found
        }
        grace = timedelta(seconds=UNUSABLE_GRACE_SECONDS)
        return {
            entity_id: modes
            for entity_id, modes in found.items()
            if now - self._unsupported_since[entity_id] >= grace
        }

    @callback
    def _report_unsupported_modes(self) -> None:
        """Put the roles asking impossible modes under Repairs, or take them away."""
        problems.async_report_unsupported_modes(
            self.hass,
            self.config_entry.entry_id,
            self.config_entry.title,
            self._note_unsupported(),
        )

    # -- commando's die niet aankomen / commands not taking --------------------

    @callback
    def _note_unapplied(self) -> dict[str, str]:
        """Count how often each difference was offered without taking effect.

        Een apparaat dat de aanroep aanneemt maar niet uitvoert, of zichzelf
        terugzet, levert elke ronde hetzelfde verschil op. Na een aantal rondes
        is dat geen toeval meer en hoort er een melding te komen. In
        schaduwmodus wordt er niets uitgevoerd, dus daar telt dit nooit - de
        verschillenlijst is dan per definitie permanent gevuld.

        An appliance that accepts the call but does not carry it out, or resets
        itself, yields the same difference every round. After a number of rounds
        that is no longer chance and a notice should appear. In shadow mode
        nothing is executed, so this never counts there - the difference list is
        by definition permanently filled then.
        """
        if self.shadow:
            self._unapplied = {}
            return {}

        now = dt_util.now()
        offered = {change.entity_id for change in self.last_changes}
        for entity_id in list(self._unapplied):
            if entity_id not in offered:
                del self._unapplied[entity_id]

        grace = timedelta(seconds=UNUSABLE_GRACE_SECONDS)
        found: dict[str, str] = {}
        for change in self.last_changes:
            fingerprint = (
                change.command.hvac_mode,
                change.command.temperature,
                change.set_mode,
                change.set_temperature,
            )
            previous, count, since = self._unapplied.get(change.entity_id, (None, 0, now))
            if previous == fingerprint:
                count += 1
            else:
                count, since = 1, now
            self._unapplied[change.entity_id] = (fingerprint, count, since)
            if count >= _COMMAND_NOT_TAKING_ROUNDS and now - since >= grace:
                found[change.entity_id] = _wanted(change)
        return found

    @callback
    def _report_command_not_taking(self) -> None:
        """Put appliances that never take their command under Repairs, or take them away."""
        problems.async_report_command_not_taking(
            self.hass,
            self.config_entry.entry_id,
            self.config_entry.title,
            self._note_unapplied(),
        )

    # -- vastgelopen zones / stuck zones -------------------------------------

    @callback
    def _note_waiting(self, plan: Plan) -> None:
        """Remember since when each zone has been on its current waiting reason.

        De tijdstempel verspringt zodra de reden verandert, want dan is er wel
        iets gebeurd. Blijft dezelfde reden staan, dan loopt de teller door.

        The timestamp moves the moment the reason changes, since something did
        happen then. While the reason stays the same, the clock keeps running.
        """
        now = dt_util.now()
        fresh: dict[str, tuple[Reason, datetime]] = {}
        for decision in plan.zones:
            if decision.reason not in WAITING_REASONS:
                continue
            since = self._waiting.get(decision.zone_id)
            fresh[decision.zone_id] = (
                since if since and since[0] is decision.reason else (decision.reason, now)
            )
        self._waiting = fresh

    def waiting_seconds(self) -> dict[str, float]:
        """Return how long each waiting zone has been on its reason."""
        now = dt_util.now()
        return {
            zone_id: (now - since).total_seconds()
            for zone_id, (_reason, since) in self._waiting.items()
        }

    def unusable_latest(self) -> dict[str, str]:
        """Return the unreadable entities of the latest decision round.

        De entiteitenlaag hoort niet aan `_unusable_latest` te zitten: dat is
        een privéveld van de coordinator en de grens van wat hij naar buiten
        brengt verandert mee met hem. Dit is de publieke lezer.

        The entity layer should not touch `_unusable_latest`: that is a private
        coordinator field, and the boundary of what it exposes moves with it.
        This is the public reader.
        """
        return self._unusable_latest

    def stuck_zones(self) -> dict[str, Reason]:
        """Return the zones that have waited longer than the installation allows.

        Een pauze bij het wisselen van taak hoort seconden te duren. Staat een
        zone er een kwartier op, dan wacht hij niet meer maar zit hij vast - en
        dat is van buiten niet te onderscheiden van niets doen.

        A pause when switching duty should last seconds. A zone sitting on one
        for a quarter of an hour is no longer waiting but stuck - and from the
        outside that is indistinguishable from doing nothing at all.
        """
        limit = self.config.stuck_after.total_seconds()
        if limit <= 0:
            return {}
        now = dt_util.now()
        return {
            zone_id: reason
            for zone_id, (reason, since) in self._waiting.items()
            if (now - since).total_seconds() >= limit
        }

    def build_world(self) -> WorldState:
        """Return a snapshot of everything the engine needs.

        Times are local and timezone-aware throughout. That matters: schedule
        windows are read in local time, while entity timestamps arrive in UTC,
        and mixing the two would put an opening's age hours out.

        De bewoners worden hier als eerste gelezen en daarna doorgegeven: de
        overridelagen lezen een aanwezigheidsentiteit dan niet zelf nog eens,
        zodat "is iemand thuis" op precies één plek beantwoord wordt. Twee
        lezers van dezelfde entiteit mogen het nooit oneens zijn.

        The residents are read first and passed on from here: the override
        layers below no longer read a presence entity themselves, so "is
        somebody home" is answered in exactly one place. Two readers of the
        same entity may never disagree.
        """
        now = dt_util.now()
        residents = {
            resident.resident_id: self._resident(
                resident.presence_entity, resident.sleep_entity, resident.sleep_state
            )
            for resident in self.config.residents
        }
        return WorldState(
            now=now,
            outdoor_temperature=self._temperature(self.config.outdoor_sensor),
            season=self._season(),
            indoor_temperatures={
                zone.zone_id: self._temperature(zone.indoor_sensor) for zone in self.config.zones
            },
            climates={entity_id: self._climate(entity_id) for entity_id in self._climate_ids()},
            residents=residents,
            openings={
                opening.entity_id: self._opening(opening.entity_id, opening.open_state)
                for opening in self.config.openings
                if opening.entity_id
            },
            presence={
                zone.zone_id: self._presence(zone.presence_entity, zone.presence_state)
                for zone in self.config.zones
                if zone.presence_entity
            },
            master_enabled=self.master_enabled,
            holiday_mode=self.holiday_mode or self._calendar_says_holiday(),
            guest_mode=self.guest_mode,
            precondition_until=self._live_preconditions(),
            precondition_bypass=frozenset(self._precondition_bypass),
            zone_overrides=self._overridden_zones(now, residents),
            zone_priorities=dict(self.zone_priorities),
            precipitation=self._precipitation(),
        )

    def _overridden_zones(
        self, now: datetime, residents: dict[str, ResidentState]
    ) -> dict[str, bool]:
        """Return which zones are handed over, from either of the two ways in.

        Er zijn twee manieren waarop een zone van de gebruiker wordt: de
        schakelaar omzetten, of bij het apparaat zelf op uit drukken. Ze staan
        los van elkaar, dus één van de twee is genoeg - wie ze samenvoegde met
        de schakelaar als laatste, liet een schakelaar die gewoon uit staat de
        handmatige uitzetting wissen. En die schakelaar staat er voor elke zone,
        en staat standaard uit: dan werkte "zelf uitzetten" dus nergens. Een
        hand aan een gedeeld apparaat telt voor elke zone die het bedient.

        There are two ways a zone becomes the user's: throwing the switch, or
        pressing off on the appliance itself. They stand apart, so either one is
        enough - whoever merged them with the switch last let a switch that is
        simply off erase the hand-back. And that switch exists for every zone,
        and is off by default: so "switching off yourself" worked nowhere. A
        hand at a shared appliance counts for every zone it serves.
        """
        handed_back = self._zones_handed_back(now, residents)
        thrown = {zone_id for zone_id, on in self.zone_overrides.items() if on}
        return dict.fromkeys(handed_back | thrown, True)

    def _climate_ids(self) -> set[str]:
        """Return every climate entity the engine may need to read."""
        entities = {
            source.entity_id
            for zone in self.config.zones
            for source in zone.sources
            if source.entity_id
        }
        for circuit in self.config.circuits:
            entities.update(unit for unit in circuit.units if unit)
        entities.update(item.entity_id for item in self.config.generators if item.entity_id)
        return entities

    def _climate(self, entity_id: str) -> ClimateState:
        state = self.hass.states.get(entity_id)
        if state is None or _unreadable(state.state):
            return ClimateState(available=False)
        return ClimateState(
            hvac_mode=state.state,
            current_temperature=_as_float(state.attributes.get("current_temperature")),
            target_temperature=_as_float(state.attributes.get("temperature")),
            hvac_modes=_as_modes(state.attributes.get("hvac_modes")),
            min_temp=_as_float(state.attributes.get("min_temp")),
            max_temp=_as_float(state.attributes.get("max_temp")),
            available=True,
            changed_at=dt_util.as_local(state.last_changed),
        )

    def _temperature(self, entity_id: str) -> float | None:
        """Return the temperature an entity reports, whatever shape it takes."""
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        return temperature_from_state(entity_id, state.state, state.attributes)

    def _resident(self, presence: str, sleep: str, asleep_state: str) -> ResidentState:
        home = False
        if presence:
            state = self.hass.states.get(presence)
            home = state is not None and state.state.lower() in _HOME_STATES

        asleep = False
        if sleep:
            state = self.hass.states.get(sleep)
            asleep = state is not None and state.state == asleep_state

        return ResidentState(home=home, asleep=asleep)

    def _opening(self, entity_id: str, open_state: str) -> OpeningState:
        """Read one opening, honouring the state it was told counts as open.

        Een raamcontact meldt `on` als het openstaat, een cover meldt `open`.
        De stand wordt per opening ingesteld en staat standaard op `on`, zodat
        bestaande installaties hetzelfde blijven lezen.

        A window contact reports `on` when open, a cover reports `open`. The
        state is configured per opening and defaults to `on`, so existing
        installations keep reading the same thing.
        """
        state = self.hass.states.get(entity_id)
        if state is None:
            return OpeningState()
        # Een cover die onderweg is (`opening`/`closing`) staat niet dicht en
        # telt dus als open; een raamcontact kent die tussenstanden niet en
        # vergelijkt gewoon letterlijk.
        #
        # A cover that is on its way (`opening`/`closing`) is not closed and so
        # counts as open; a window contact has no such in-between states and is
        # simply compared literally.
        reported = state.state
        if open_state == "open":
            is_open = reported in ("open", "opening", "closing")
        else:
            is_open = reported == open_state
        return OpeningState(
            open=is_open,
            changed_at=dt_util.as_local(state.last_changed),
        )

    def _presence(self, entity_id: str, occupied_state: str) -> PresenceState:
        """Return whether a room is occupied, and since when."""
        state = self.hass.states.get(entity_id)
        if state is None:
            return PresenceState()
        return PresenceState(
            occupied=state.state == occupied_state,
            changed_at=dt_util.as_local(state.last_changed),
        )

    def _season(self) -> Season:
        if getattr(self, "season_override", None) is not None:
            return self.season_override
        settings = self.config.seasons
        if settings.source is SeasonSource.SUMMER:
            return Season.SUMMER
        if settings.source is SeasonSource.WINTER:
            return Season.WINTER
        if settings.source is SeasonSource.ENTITY:
            state = self.hass.states.get(settings.entity_id) if settings.entity_id else None
            return season_from_state(state.state if state else None)
        return settings.for_month(dt_util.now().month)

    def _precipitation(self) -> bool:
        """Return whether the configured source reports precipitation, with grace.

        Dit is een lezer en schrijft dus niets. Het moment waarop de bron voor
        het laatst neerslag meldde wordt vastgelegd in `_notice_precipitation`
        (de toestandswijziging van de bron zelf) en bij het opstarten in
        `_note_precipitation_now`; hier wordt het alleen uitgelezen. Eerder
        gebeurde dat wél hier, en daardoor verliep de nalooptijd alleen tijdens
        een beoordelingsronde - een verborgen bijwerking op een pad dat "lezen"
        heet.

        This is a reader and therefore writes nothing. The moment the source
        last reported precipitation is recorded in `_notice_precipitation` (the
        source's own state change) and at startup in `_note_precipitation_now`;
        here it is only read. It used to be written here, which made the grace
        lapse only during an evaluation round - a hidden side effect on a path
        that calls itself "read".
        """
        settings = self.config.precipitation
        if not settings.enabled:
            return False
        state = self.hass.states.get(settings.source)
        if state is not None and state.state in settings.states:
            return True
        seen = self._precipitation_seen_at
        return seen is not None and dt_util.now() - seen < settings.grace

    def _note_precipitation_now(self) -> None:
        """Remember rain that was already falling before this process started.

        De listener ziet alleen overgangen. Wie herstart terwijl het regent,
        heeft geen overgang gezien, en zonder deze stap zou de nalooptijd voor
        die bui verloren zijn - terwijl de lezer zelf nooit mag schrijven. Dit
        is naast de listener de enige plek die het moment vastlegt.

        The listener only sees transitions. Restarting while it rains means no
        transition was seen, and without this step the grace for that shower
        would be lost - while the reader itself must never write. Besides the
        listener this is the only place that records the moment.
        """
        settings = self.config.precipitation
        if not settings.enabled:
            return
        state = self.hass.states.get(settings.source)
        if state is not None and state.state in settings.states:
            self._precipitation_seen_at = dt_util.now()

    # -- circuitgeschiedenis / circuit history -------------------------------

    def _remember_families(self, world: WorldState) -> None:
        """Record when each circuit last took on the duty it is running.

        Read from the observed states rather than from the previous plan: a
        unit switched by remote changes a circuit's duty just as effectively as
        the director does, and the minimum-run timer has to respect that.
        """
        for circuit in self.config.circuits:
            current = active_family(world, circuit)
            if self._family_seen.get(circuit.circuit_id) != current:
                self._family_seen[circuit.circuit_id] = current
                self._family_since[circuit.circuit_id] = (
                    world.now if current in (ModeFamily.HEAT, ModeFamily.COOL) else None
                )

    def _with_family_history(self, world: WorldState) -> WorldState:
        """Return the snapshot with the recorded duty-change times filled in.

        Eén veld vervangen, de rest overnemen zoals hij is. Dat gebeurde ooit
        door de momentopname met de hand opnieuw op te bouwen, en toen viel er
        stilletjes een veld uit: `precondition_bypass` bleef leeg, waardoor
        "toch doen" bij een openstaand raam nooit werkte in een draaiende Home
        Assistant - terwijl elke engine-test hem wél doorgaf. Een veld dat er
        later bij komt kan zo niet meer vergeten worden.

        Replace one field and carry the rest across as it stands. This once
        rebuilt the snapshot by hand, and a field quietly fell out of it:
        `precondition_bypass` stayed empty, so "do it anyway" on an open window
        never worked inside a running Home Assistant - while every engine test
        did pass it along. A field added later can no longer be forgotten this
        way.
        """
        return replace(world, circuit_family_since=dict(self._family_since))

    # -- naar buiten / outward ----------------------------------------------

    def _fire_events(self, plan: Plan) -> None:
        """Fire one event per zone whose outcome changed.

        Only on change: a decision is recomputed on every state change of every
        tracked entity, and firing each time would drown any automation
        listening for it.
        """
        previous = {zone.zone_id: zone for zone in (self.data.zones if self.data else ())}

        for decision in plan.zones:
            if previous.get(decision.zone_id) == decision:
                continue
            self.hass.bus.async_fire(EVENT_DECISION, _event_data(self.config, plan, decision))

    def _fire_refusals(self, plan: Plan) -> None:
        """Say so when a pre-conditioning request strands on an open window.

        Zonder dit verdwijnt het verzoek in stilte: de zone meldt `opening_open`,
        maar dat ziet er van buiten hetzelfde uit als een raam dat gewoon
        openstaat terwijl niemand iets vroeg. Wie op een knop drukte hoort te
        horen waarom er niets gebeurt, en welk raam het is.

        Alleen bij een wisseling, niet bij elke beoordeling - anders verzuipt
        elke automatisering die meeluistert.

        Without this the request vanishes silently: the zone reports
        `opening_open`, but from the outside that looks the same as a window
        simply standing open while nobody asked for anything. Whoever pressed a
        button deserves to hear why nothing happens, and which window it is.

        Only on a change, not on every evaluation - otherwise any automation
        listening drowns.
        """
        refused: set[str] = set()
        for decision in plan.zones:
            if decision.reason not in (Reason.OPENING_OPEN, Reason.OPENING_OPEN_ELSEWHERE):
                continue
            if not self._precondition.get(decision.zone_id):
                continue
            refused.add(decision.zone_id)

            if decision.zone_id in self._refused:
                continue
            self.hass.bus.async_fire(
                EVENT_PRECONDITION_REFUSED, self._refusal_data(decision.zone_id, plan)
            )

        self._refused = refused

    def _refusal_data(self, zone_id: str, plan: Plan | None) -> dict[str, Any]:
        """Return the payload of one refusal, the sentences included.

        De zinnen worden hier al gemaakt, in de taal van de interface. Een
        blueprint kan niet vertalen en een gebruiker die zijn huis in het
        Nederlands bedient wil geen Engelse melding op zijn telefoon. Waar de
        melding heen gaat blijft aan de gebruiker; alleen de tekst komt hier
        vandaan.

        Er zitten twee zinnen in: de weigering, en wat er te melden valt zodra
        iemand op "toch doen" drukt. Die tweede staat er nu al in omdat hij
        precies dan nodig is, en dan is de gebeurtenis allang geweest.

        The sentences are made here, in the language of the interface. A
        blueprint cannot translate, and somebody running their house in Dutch
        does not want an English notice on their phone. Where the notice goes
        stays the user's business; only the text comes from here.

        Two sentences go in: the refusal, and what there is to report the
        moment somebody presses "do it anyway". The second is in here already
        because that is exactly when it is needed, and by then the event is
        long past.
        """
        zone = self.config.zone(zone_id)
        name = zone.name if zone else zone_id
        decision = plan.decision_for(zone_id) if plan is not None else None
        held_elsewhere = decision is not None and (
            decision.reason is Reason.OPENING_OPEN_ELSEWHERE
            or Reason.OPENING_OPEN_ELSEWHERE in decision.closed_gates
        )
        house_wide = held_elsewhere or (
            zone is not None
            and any(source.entity_id in self.config.house_wide_openings for source in zone.sources)
            and self.world is not None
            and bool(house_wide_blocked(self.config, self.world))
        )
        openings = self._open_openings(zone_id, house_wide=house_wide)
        listed = ", ".join(self._friendly(entity_id) for entity_id in openings) or "-"
        minutes = round(self.config.gates.max_precondition.total_seconds() / 60)

        indoor = self.world.indoor(zone_id) if self.world is not None else None
        target: float | None = None
        settled = False
        if zone is not None and self.world is not None:
            demand, target = wanted_target(self.config, zone, self.world, plan)
            settled = demand.reason in (Reason.SATISFIED, Reason.WITHIN_DEADBAND)

        if indoor is None:
            code = "precondition_confirmed_unknown"
            fallback = (
                "{zone} is going ahead, ignoring {openings}. The room temperature cannot be "
                "read, so nothing will happen until it can."
            )
        elif target is not None:
            code = "precondition_confirmed"
            fallback = (
                "{zone} is going ahead, ignoring {openings}. Now {indoor} degrees, aiming for "
                "{target} degrees."
            )
        elif settled:
            code = "precondition_confirmed_satisfied"
            fallback = (
                "{zone} is going ahead, ignoring {openings}. Now {indoor} degrees - the room is "
                "already right, so nothing happens for the moment."
            )
        else:
            # Geen streeftemperatuur en niet tevreden: het seizoen of de
            # configuratie laat hier niets toe. "De kamer ligt al goed" zou dan
            # een leugen zijn tegen iemand die op vijftien graden zit.
            #
            # No target and not satisfied: the season or the configuration
            # allows nothing here. "The room is already right" would then be a
            # lie to somebody sitting at fifteen degrees.
            code = "precondition_confirmed_idle"
            fallback = (
                "{zone} is going ahead, ignoring {openings}. Now {indoor} degrees - there is "
                "nothing this room may do at the moment, so nothing happens."
            )

        filling = {
            "zone": name,
            "openings": listed,
            "indoor": texts.number(indoor),
            "target": texts.number(target),
            "minutes": minutes,
        }
        return {
            "entry_id": self.config_entry.entry_id,
            "zone_id": zone_id,
            "zone": name,
            "openings": openings,
            "opening_names": [self._friendly(entity_id) for entity_id in openings],
            "until": self._precondition[zone_id].isoformat(),
            "indoor_temperature": indoor,
            "target_temperature": target,
            "override_minutes": minutes,
            "title": texts.translated(
                self.hass, "precondition_refused_title", "Pre-conditioning refused", **filling
            ),
            "message": texts.translated(
                self.hass,
                "precondition_refused",
                "{zone} could not start pre-conditioning. Still open: {openings}. Close what is "
                "open, or let the request run anyway for {minutes} minutes.",
                **filling,
            ),
            "confirmed_title": texts.translated(
                self.hass, "precondition_confirmed_title", "Pre-conditioning is running", **filling
            ),
            "confirmed_message": texts.translated(self.hass, code, fallback, **filling),
            "confirm_label": texts.translated(
                self.hass, "precondition_confirm_label", "Do it anyway", **filling
            ),
        }

    def _friendly(self, entity_id: str) -> str:
        """Return the name somebody would recognise, or the entity id."""
        state = self.hass.states.get(entity_id)
        return state.name if state is not None else entity_id

    def _open_openings(self, zone_id: str, *, house_wide: bool = False) -> list[str]:
        """Return the entity ids standing open, so the notice can name them.

        Met `house_wide` telt élke openstaande opening mee in plaats van alleen
        die van de zone. De deur die een huisbreed stilgezet apparaat stopt hoort
        per definitie bij een andere kamer, dus de gewone zonefilter zou een
        gerepareerd event alsnog `openings: "-"` laten melden.

        With `house_wide` every opening standing open counts rather than only the
        zone's own. The door stopping a house-wide stopped appliance belongs to
        another room by definition, so the ordinary zone filter would still have a
        repaired event report `openings: "-"`.
        """
        if self.world is None:
            return []
        if house_wide:
            return sorted(
                opening.entity_id
                for opening in self.config.openings
                if self.world.opening(opening.entity_id).open
            )
        return sorted(
            opening.entity_id
            for opening in self.config.openings
            if (not opening.zone_ids or zone_id in opening.zone_ids)
            and self.world.opening(opening.entity_id).open
        )

    def _schedule_deferral(self, plan: Plan) -> None:
        """Re-evaluate when a timer in the plan expires.

        Without this, a plan held back by short-cycle protection would wait for
        an unrelated state change to resume - which on a quiet night may never
        come.
        """
        self._cancel_pending_deferral()

        deferral = plan.next_deferral
        if deferral is None:
            return

        delay = max((deferral.until - dt_util.now()).total_seconds(), MIN_DEFERRAL_SECONDS)

        @callback
        def _resume(_now: datetime) -> None:
            self._cancel_deferral = None
            self.async_request_evaluation()

        self._cancel_deferral = async_call_later(self.hass, delay, _resume)

    @callback
    def _cancel_pending_deferral(self) -> None:
        """Drop the scheduled re-evaluation, if there is one."""
        if self._cancel_deferral is not None:
            self._cancel_deferral()
            self._cancel_deferral = None


def _event_data(config: DirectorConfig, plan: Plan, decision: ZoneDecision) -> dict[str, Any]:
    """Return the payload of one `climate_director_decision` event."""
    zone = config.zone(decision.zone_id)
    command = next((item for item in plan.commands if item.source_id == decision.source_id), None)
    return {
        "zone_id": decision.zone_id,
        "zone_name": zone.name if zone else decision.zone_id,
        "wanted": decision.wanted.value,
        "granted": decision.granted.value,
        "source_id": decision.source_id,
        "entity_id": command.entity_id if command else None,
        "hvac_mode": command.hvac_mode if command else None,
        "temperature": command.temperature if command else None,
        "reason": decision.reason.value,
    }


def _still_running(requests: Mapping[str, datetime], now: datetime) -> dict[str, datetime]:
    """Return the pre-conditioning requests that have not run out at `now`.

    Een gewone functie in plaats van een methode: hij wordt zowel gelezen als
    opgeruimd aangeroepen, en dan hoort er geen twijfel te bestaan over welke
    van de twee je krijgt.

    A plain function rather than a method: it is called both to read and to
    prune, and then there should be no doubt about which of the two you get.
    """
    return {zone_id: until for zone_id, until in requests.items() if now < until}


def _unreadable(state: str) -> bool:
    """Return whether an entity state carries no reading at all.

    Eén plek waar de koppelingslaag bepaalt wat "hier valt niets uit op te
    maken" betekent, zodat het uitlezen van een apparaat en het opmerken van
    een hand aan datzelfde apparaat het nooit oneens kunnen zijn.

    One place where the binding layer settles what "nothing can be made of
    this" means, so reading an appliance and noticing a hand at that same
    appliance can never disagree.
    """
    return state in (STATE_UNAVAILABLE, STATE_UNKNOWN)


def _as_float(raw: Any) -> float | None:
    """Return `raw` as a float, or `None` when it is not a usable number.

    `nan` and `inf` count as no reading too. Every comparison with them is
    false, so a broken sensor reporting one would satisfy each bounded outdoor
    window at once and quietly pick a source that an unreadable temperature
    should have shut out - while `unavailable` and `unknown` are translated to
    `None` further up and behave the other way. One rule for every unreadable
    value, not two.
    """
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _wanted(change: Change) -> str:
    """Return what a change asks for, short enough to read in a notice.

    De stand is er altijd; het setpoint alleen als het meegestuurd wordt. Een
    apparaat dat uitgezet moet worden krijgt geen temperatuur mee, en die dan
    toch noemen zou een lezer op het verkeerde been zetten.

    The mode is always there; the setpoint only when it is sent along. An
    appliance that has to be switched off gets no temperature with it, and
    naming one anyway would put a reader on the wrong foot.
    """
    if change.set_temperature and change.command.temperature is not None:
        return f"{change.command.hvac_mode}, {change.command.temperature} °C"
    return change.command.hvac_mode


def _as_modes(raw: Any) -> frozenset[str] | None:
    """Return the hvac modes an entity reports, or `None` when it reports none.

    None means unknown, and unknown gets the benefit of the doubt: the engine
    commands the mode anyway, exactly as before the check existed.
    """
    if not isinstance(raw, (list, tuple, set, frozenset)):
        return None
    modes = {str(item) for item in raw}
    return frozenset(modes) if modes else None
