"""De momentopname: één `WorldState`, op één plek gebouwd.

The snapshot: one `WorldState`, built in one place.

`build_world` leest alles wat de engine nodig heeft uit de entiteitstoestanden
en stopt het in één dataobject. De lezers die hij aanroept staan hierbij, zodat
"hoe ziet de wereld er nu uit" op precies één plek beantwoord wordt — inclusief
de kleine helpers die een temperatuur, een seizoen of een stand uitlezen.

`build_world` reads everything the engine needs from the entity states and puts
it into one data object. The readers it calls live here, so "what does the world
look like right now" is answered in exactly one place — including the small
helpers that read a temperature, a season or a state.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.util import dt as dt_util

from .engine import (
    ClimateState,
    OpeningState,
    PresenceState,
    ResidentState,
    Season,
    WorldState,
)
from .engine.models import SeasonSource
from .units import to_celsius, unit_of_coordinator

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
    entity_id: str, state: str, attributes: Mapping[str, Any], *, unit: str | None = None
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

    `unit` is het eenhedenstelsel van de gebruiker; de waarde komt terug in
    graden Celsius. Een entiteit die haar eigen eenheid noemt in
    `unit_of_measurement` (een sensor) of `temperature_unit` (een weersbron)
    wordt in díe eenheid gelezen: een sensor zonder temperatuur-deviceclass
    rekent Home Assistant niet om, dus het systeemstelsel zou haar verkeerd
    lezen. Een `climate`-entiteit publiceert geen van beide en rekent zelf al
    om naar het systeemstelsel.

    `unit` is the user's temperature unit, as Home Assistant reports it; the
    value is returned in degrees Celsius. `None` means the caller already works
    in Celsius. An entity that names its own unit in `unit_of_measurement` (a
    sensor) or `temperature_unit` (a weather source) is read in that unit: a
    sensor without a temperature device class is not converted by Home
    Assistant, so the system unit would misread it. A `climate` entity
    publishes neither and already converts to the system unit itself.
    """
    reported = str(
        attributes.get("unit_of_measurement") or attributes.get("temperature_unit") or unit or ""
    )
    value = _as_float(state)
    if value is not None:
        return to_celsius(value, reported)
    if entity_id.startswith("weather."):
        return to_celsius(_as_float(attributes.get("temperature")), reported)
    return to_celsius(_as_float(attributes.get("current_temperature")), reported)


def season_from_state(raw: str | None) -> Season:
    """Return the season an entity's state names, or `UNKNOWN`.

    Spring and autumn map onto winter rather than onto nothing: `sensor.season`
    is a common source, and reading its shoulder seasons as "no season at all"
    would silently switch every season-gated duty off for half the year.
    """
    if not raw:
        return Season.UNKNOWN
    return _SEASON_NAMES.get(raw.strip().lower(), Season.UNKNOWN)


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


class _WorldBuilderMixin:
    """De momentopname en de lezers die hem vullen.

    The snapshot and the readers that fill it.
    """

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
            opening_bypasses=frozenset(
                opening_id for opening_id, on in self.opening_bypasses.items() if on
            ),
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
            current_temperature=to_celsius(
                _as_float(state.attributes.get("current_temperature")),
                unit_of_coordinator(self),
            ),
            target_temperature=to_celsius(
                _as_float(state.attributes.get("temperature")),
                unit_of_coordinator(self),
            ),
            hvac_modes=_as_modes(state.attributes.get("hvac_modes")),
            min_temp=to_celsius(
                _as_float(state.attributes.get("min_temp")), unit_of_coordinator(self)
            ),
            max_temp=to_celsius(
                _as_float(state.attributes.get("max_temp")), unit_of_coordinator(self)
            ),
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
        return temperature_from_state(
            entity_id, state.state, state.attributes, unit=unit_of_coordinator(self)
        )

    def _resident(self, presence: str, sleep: str, asleep_state: str) -> ResidentState:
        """Return one resident's state, with a stale sleep reading ignored.

        Opstaan en thuiskomen zijn twee verschillende dingen, en de slaapsensor
        kent alleen het eerste. "Telefoon op de draadloze lader" zegt iets over
        iemand die de hele tijd thuis was; wie binnenkomt met zijn telefoon nog
        aan de lader in de auto, is klaarwakker. Die melding is ouder dan de
        thuiskomst en zegt dus niets over nu.

        Daarom telt een slaapmelding alleen als hij van ná de thuiskomst is.
        Legt iemand zijn telefoon thuis opnieuw op de lader, dan is dat een
        verse melding en telt hij gewoon weer. Bij gelijke tijdstempels - na een
        herstart krijgt alles hetzelfde moment - telt de melding wél, want
        opschorten is de onschadelijke kant om fout te zitten.

        Getting up and coming home are two different things, and the sleep
        sensor knows only the first. "Phone on the wireless charger" says
        something about somebody who was home all along; whoever walks in with
        their phone still on the car charger is wide awake. That reading is
        older than the arrival and therefore says nothing about now.

        So a sleep reading only counts when it postdates the arrival. Put the
        phone back on the charger at home and that is a fresh reading, counting
        as before. On equal timestamps - after a restart everything carries the
        same moment - the reading does count, since suspending is the harmless
        direction to be wrong in.
        """
        home = False
        home_since = None
        if presence:
            state = self.hass.states.get(presence)
            home = state is not None and state.state.lower() in _HOME_STATES
            if home and state is not None:
                home_since = state.last_changed

        asleep = False
        if sleep:
            state = self.hass.states.get(sleep)
            asleep = state is not None and state.state == asleep_state
            if asleep and home_since is not None and state.last_changed < home_since:
                asleep = False

        return ResidentState(home=home, asleep=asleep)

    def _opening(self, entity_id: str, open_state: str) -> OpeningState:
        """Read one opening, honouring the state it was told counts as open.

        Een raamcontact meldt `on` als het openstaat, een cover meldt `open`.
        De stand wordt per opening ingesteld en staat standaard op `on`, zodat
        bestaande installaties hetzelfde blijven lezen.

        A window contact reports `on` when open, a cover reports `open`. The
        state is configured per opening and defaults to `on`, so existing
        installations keep reading the same thing.

        `_started_at` schuift bij elke reload op: een raam dat vlak vóór een
        wijziging in de options flow openging telt daarna meteen als lang genoeg
        open en slaat zijn `delay` over. Dat is de veilige kant, precies zoals
        L2 van ronde 8 al vastlegde.

        `_started_at` moves with every reload: a window that opened just before
        an options-flow change counts as open long enough right away and skips
        its `delay`. That is the safe side, exactly as L2 of round 8 already
        recorded.
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
        changed_at = dt_util.as_local(state.last_changed)
        # Na een herstart leest `last_changed` het herstartmoment, en een raam
        # dat al uren openstond zou dan als "net geopend" tellen - de zone
        # stookte nog `delay` lang door. Wie voor het opstartmoment openstaat
        # telt daarom als open lange tijd: de veilige kant, precies zoals
        # `min_cycle_time` zijn rust na een herstart ook aan de veilige kant
        # meet.
        #
        # After a restart `last_changed` reads the restart moment, and a window
        # that stood open for hours would then count as "just opened" - the zone
        # would keep heating for `delay` more. Whatever was open before the
        # start moment therefore counts as open long enough: the safe side,
        # exactly as `min_cycle_time` measures its rest after a restart on the
        # safe side too.
        started_at = getattr(self, "_started_at", None)
        if started_at is not None and changed_at is not None and changed_at < started_at:
            changed_at = None
        return OpeningState(
            open=is_open,
            changed_at=changed_at,
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
