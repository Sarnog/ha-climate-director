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
from collections.abc import Mapping
from dataclasses import replace
from datetime import date, datetime, timedelta
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

from . import texts
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
from .engine.families import family_of
from .engine.models import SeasonSource
from .engine.serialise import config_from_dict

_LOGGER = logging.getLogger(__name__)

type ClimateDirectorEntry = ConfigEntry[ClimateDirectorCoordinator]

#: Toestanden die "thuis" betekenen voor een aanwezigheidsentiteit.
#: States meaning "home" for a presence entity.
_HOME_STATES = frozenset({"home", "on", "true"})

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
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.precondition"
        )
        self._waiting: dict[str, tuple[Reason, datetime]] = {}
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

        self._lock = asyncio.Lock()
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
        """Restore what a restart left behind, decide once, and arm the clock."""
        await self._async_restore_state()
        self._note_precipitation_now()
        await self._async_evaluate()
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
        niet in `_precipitation()`, dat alleen een antwoord teruggeeft. Alleen
        een overgang náár een neerslagstand telt; een overgang tussen twee droge
        standen (bewolkt -> zonnig) mag de nalooptijd niet verlengen.

        The moment belongs here, in the source's own state change - not in
        `_precipitation()`, which only returns an answer. Only a transition INTO
        a precipitation state counts; a transition between two dry states
        (cloudy -> sunny) must not extend the grace.
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
            # Switched on again, by hand or by us: taking part either way.
            cleared = False
            for zone in zones:
                cleared = self._handed_back.pop(zone, None) is not None or cleared
            if cleared:
                self._async_save_state()
            return

        # Alleen als wíj hem niet net hebben uitgezet. Ons eigen commando is
        # geen handmatige ingreep, en zou de zone anders permanent stilleggen.
        #
        # Only when we did not just switch it off ourselves. Our own command is
        # not a hand at the appliance, and would otherwise silence the zone for
        # good.
        if self._we_wanted_it_off(entity_id):
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
        weer aan.

        A shared boiler sits under more than one zone. Somebody pressing off on
        such an appliance says something about the appliance, not about whichever
        zone happens to be listed first - so every zone hanging off it should fall
        silent, otherwise the skipped zone switches it straight back on.
        """
        return tuple(
            zone.zone_id for zone, source in self.config.sources() if source.entity_id == entity_id
        )

    def _we_wanted_it_off(self, entity_id: str) -> bool:
        """Return whether the plan being carried out has this appliance standing still.

        Het plan dat op tafel ligt, niet het plan dat af is. Een apparaat meldt
        zijn nieuwe stand terwijl de service call nog loopt, en op dat moment
        staat het gepubliceerde besluit nog op de vorige ronde. Wie dáárin
        keek, zag "wij wilden hem aan" en boekte het eigen uitzetcommando als
        een hand aan het apparaat - waarna de zone de rest van de dag stil
        bleef staan. Dat is precies de fout die deze controle hoort te
        voorkomen.

        The plan on the table, not the plan that is finished. An appliance
        reports its new state while the service call is still running, and at
        that moment the published decision is still the previous round's.
        Looking there saw "we wanted it on" and recorded our own switch-off as a
        hand at the appliance - after which the zone stood still for the rest of
        the day. That is exactly the mistake this check exists to prevent.
        """
        plan = self._issued or self.data
        if plan is None:
            return False
        for command in plan.commands:
            if command.entity_id == entity_id:
                return family_of(command.hvac_mode) is ModeFamily.NEUTRAL
        return False

    def _zones_handed_back(self) -> set[str]:
        """Return the zones a hand stood down today, forgetting yesterday's.

        De datum is de hele vervaltermijn. Wie gisteravond de slaapkamer uitzette
        wil vanochtend niet dat hij nog steeds stilstaat, en een teller van
        vierentwintig uur zou dat wel doen.

        The date is the whole expiry. Whoever switched the bedroom off last night
        does not want it still standing still this morning, and a twenty-four
        hour timer would do exactly that.
        """
        if self._everyone_asleep() or self._house_is_empty():
            if self._handed_back:
                self._handed_back.clear()
                self._async_save_state()
            self.zone_overrides.clear()
            return set()

        today = dt_util.now().date()
        kept = {zone: day for zone, day in self._handed_back.items() if day == today}
        if kept != self._handed_back:
            self._handed_back = kept
            self._async_save_state()
        return set(self._handed_back)

    def _everyone_asleep(self) -> bool:
        """Return whether everybody who is home has turned in.

        Dan is de dag voorbij en hoort een zone die iemand met de hand stilzette
        weer mee te doen - precies zoals de automatiseringen het deden. Wachten
        tot middernacht zou de zone een paar uur langer stil houden dan iemand
        bedoelde, en dat merk je pas de volgende ochtend.

        The day is then over, and a zone somebody silenced by hand should join in
        again - exactly as the automations did it. Waiting for midnight would
        hold the zone still a few hours longer than anybody meant, and you only
        notice that the next morning.
        """
        at_home = [
            resident
            for resident in self.config.residents
            if resident.presence_entity and self._state_is(resident.presence_entity, "home")
        ]
        if not at_home:
            return False
        return all(
            bool(resident.sleep_entity)
            and self._state_is(resident.sleep_entity, resident.sleep_state)
            for resident in at_home
        )

    def _house_is_empty(self) -> bool:
        """Return whether none of the tracked residents is home.

        De noodknop van de beheerder hoort niet te blijven hangen. Is er niemand
        meer, dan is het geval waarvoor hij hem omzette voorbij - en niets is zo
        vervelend als thuiskomen in een huis dat al dagen niets doet omdat er ooit
        een schakelaar aan bleef staan.

        The administrator's emergency handle should not stay hanging. With nobody
        left, the case it was thrown for is over - and nothing is as annoying as
        coming home to a house that has done nothing for days because a switch
        was once left on.
        """
        tracked = [resident for resident in self.config.residents if resident.presence_entity]
        if not tracked:
            return False
        return not any(self._state_is(resident.presence_entity, "home") for resident in tracked)

    def _state_is(self, entity_id: str, wanted: str) -> bool:
        """Return whether that entity currently reads exactly that state."""
        state = self.hass.states.get(entity_id)
        return state is not None and state.state == wanted

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
        """Stop deciding and drop every pending timer."""
        self._cancel_pending_deferral()
        self._cancel_clock_reeval()
        self._debouncer.async_shutdown()
        await super().async_shutdown()

    # -- beslissen / deciding ------------------------------------------------

    async def _async_evaluate(self) -> None:
        """Read the world, decide, apply, and report."""
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
            self.last_changes = changes(plan, world)
            self.last_applied = ()

            try:
                self.last_applied = await apply(self.hass, self.last_changes, shadow=self.shadow)
            except Exception:  # noqa: BLE001 - one bad call must not stop the loop
                _LOGGER.exception("Applying the climate plan failed")

            self._fire_events(plan)
            self._fire_refusals(plan)
            self._note_waiting(plan)
            self._schedule_deferral(plan)
            self.async_set_updated_data(plan)

    # -- vooruit verwarmen / pre-conditioning --------------------------------

    def _live_preconditions(self) -> dict[str, datetime]:
        """Return the requests that have not run out, dropping the rest.

        Pruned on reading rather than on a timer: an expired request is over
        whether or not anything got round to noticing.
        """
        now = dt_util.now()
        self._precondition = {
            zone_id: until for zone_id, until in self._precondition.items() if now < until
        }
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
            self._preconditions_expire_at(until)
            self.async_request_evaluation()
        return dict.fromkeys(chosen, until)

    # -- met de hand gegeven, dus bewaren / given by hand, so kept ----------

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
        self._store.async_delay_save(
            lambda: {
                "until": {
                    zone_id: until.isoformat() for zone_id, until in self._precondition.items()
                },
                "bypass": sorted(self._precondition_bypass),
                "handed_back": {
                    zone_id: day.isoformat() for zone_id, day in self._handed_back.items()
                },
            },
            1,
        )

    async def _async_restore_state(self) -> None:
        """Read back what was standing before the restart.

        Verlopen verzoeken komen niet terug: de tijd liep door terwijl Home
        Assistant weg was, en een verzoek van gisteren alsnog uitvoeren is
        erger dan het te vergeten. Een handmatige uitzetting van gisteren
        vervalt om dezelfde reden - de datum is de hele vervaltermijn.

        Een ouder bestand draagt nog geen `handed_back`. Dat leest gewoon als
        niets, dus de opslagversie hoeft er niet voor omhoog: er valt niets te
        migreren aan een sleutel die er niet was.

        Expired requests do not come back: time ran on while Home Assistant was
        away, and carrying out yesterday's request after the fact is worse than
        forgetting it. Yesterday's hand-back lapses for the same reason - the
        date is the whole expiry.

        An older file carries no `handed_back` yet. That simply reads as
        nothing, so the storage version need not go up for it: there is nothing
        to migrate about a key that was never there.
        """
        stored = await self._store.async_load()
        if not stored:
            return

        now = dt_util.now()
        for zone_id, raw in (stored.get("until") or {}).items():
            until = dt_util.parse_datetime(str(raw))
            if until is not None and now < until:
                self._precondition[zone_id] = until
        self._precondition_bypass = {
            zone_id for zone_id in (stored.get("bypass") or ()) if zone_id in self._precondition
        }

        today = now.date()
        for zone_id, raw in (stored.get("handed_back") or {}).items():
            day = dt_util.parse_date(str(raw))
            if day == today:
                self._handed_back[zone_id] = day

        if self._precondition:
            self._preconditions_expire_at(max(self._precondition.values()))

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
        self._async_save_state()
        self.async_request_evaluation()

    @callback
    def _preconditions_expire_at(self, until: datetime) -> None:
        """Re-evaluate the moment the request runs out.

        Zonder dit blijft een lege woning doorstoken tot er toevallig iets
        anders verandert, en op een stille middag gebeurt dat lang niet.

        Without this an empty house keeps burning until something else happens
        to change, and on a quiet afternoon that is a long wait.
        """
        seconds = (until - dt_util.now()).total_seconds()
        if seconds <= 0:
            return
        async_call_later(self.hass, seconds + 1, lambda _now: self.async_request_evaluation())

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
        """
        return WorldState(
            now=dt_util.now(),
            outdoor_temperature=self._temperature(self.config.outdoor_sensor),
            season=self._season(),
            indoor_temperatures={
                zone.zone_id: self._temperature(zone.indoor_sensor) for zone in self.config.zones
            },
            climates={entity_id: self._climate(entity_id) for entity_id in self._climate_ids()},
            residents={
                resident.resident_id: self._resident(
                    resident.presence_entity, resident.sleep_entity, resident.sleep_state
                )
                for resident in self.config.residents
            },
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
            zone_overrides=self._overridden_zones(),
            zone_priorities=dict(self.zone_priorities),
            precipitation=self._precipitation(),
        )

    def _overridden_zones(self) -> dict[str, bool]:
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
        handed_back = self._zones_handed_back()
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
        return OpeningState(
            open=state.state == open_state,
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
                    world.now if current is not ModeFamily.NEUTRAL else None
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
            if decision.reason is not Reason.OPENING_OPEN:
                continue
            if not self._precondition.get(decision.zone_id):
                continue
            refused.add(decision.zone_id)

            if decision.zone_id in self._refused:
                continue
            self.hass.bus.async_fire(
                EVENT_PRECONDITION_REFUSED, self._refusal_data(decision.zone_id)
            )

        self._refused = refused

    def _refusal_data(self, zone_id: str) -> dict[str, Any]:
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
        openings = self._open_openings(zone_id)
        listed = ", ".join(self._friendly(entity_id) for entity_id in openings) or "-"
        minutes = round(self.config.gates.max_precondition.total_seconds() / 60)

        indoor = self.world.indoor(zone_id) if self.world is not None else None
        target: float | None = None
        settled = False
        if zone is not None and self.world is not None:
            demand, target = wanted_target(self.config, zone, self.world, self.data)
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
                "{zone} could not start pre-conditioning. Still open: {openings}. Close it, or "
                "let the request run anyway for {minutes} minutes.",
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

    def _open_openings(self, zone_id: str) -> list[str]:
        """Return the entity ids standing open for one zone, so the notice can name them."""
        if self.world is None:
            return []
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


def _as_modes(raw: Any) -> frozenset[str] | None:
    """Return the hvac modes an entity reports, or `None` when it reports none.

    None means unknown, and unknown gets the benefit of the doubt: the engine
    commands the mode anyway, exactly as before the check existed.
    """
    if not isinstance(raw, (list, tuple, set, frozenset)):
        return None
    modes = {str(item) for item in raw}
    return frozenset(modes) if modes else None
