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
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .applier import apply
from .const import (
    CONF_INSTALLATION,
    CONF_SHADOW_MODE,
    DEBOUNCE_SECONDS,
    DEFAULT_SHADOW_MODE,
    DOMAIN,
    EVENT_DECISION,
    MIN_DEFERRAL_SECONDS,
)
from .engine import (
    ClimateState,
    DirectorConfig,
    ModeFamily,
    OpeningState,
    Plan,
    ResidentState,
    Season,
    WorldState,
    ZoneDecision,
    decide,
)
from .engine.constraints import active_family
from .engine.diff import Change, changes
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
    "summer": Season.SUMMER,
    "zomer": Season.SUMMER,
    "winter": Season.WINTER,
    "spring": Season.WINTER,
    "lente": Season.WINTER,
    "autumn": Season.WINTER,
    "fall": Season.WINTER,
    "herfst": Season.WINTER,
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

        # Bedieningstoestand. De schakelentiteiten herstellen dit na een
        # herstart en schrijven het hier terug.
        #
        # Control state. The switch entities restore this after a restart and
        # write it back here.
        self.master_enabled = True
        self.holiday_mode = False
        self.zone_overrides: dict[str, bool] = {}

        self.world: WorldState | None = None
        self.last_changes: tuple[Change, ...] = ()
        """What the plan wants changed, whether or not it was carried out."""

        self.last_applied: tuple[Change, ...] = ()
        """What was actually carried out; always empty in shadow mode."""

        self._lock = asyncio.Lock()
        self._family_since: dict[str, datetime | None] = {}
        self._family_seen: dict[str, ModeFamily] = {}
        self._cancel_deferral: CALLBACK_TYPE | None = None
        self._debouncer = Debouncer(
            hass,
            _LOGGER,
            cooldown=DEBOUNCE_SECONDS,
            immediate=False,
            function=self._async_evaluate,
        )

    # -- opzetten / setting up ----------------------------------------------

    async def async_start(self) -> None:
        """Begin tracking entities and make a first decision."""
        entities = self.tracked_entities()
        if entities:
            self.config_entry.async_on_unload(
                async_track_state_change_event(self.hass, sorted(entities), self._handle_change)
            )
        self.config_entry.async_on_unload(self._cancel_pending_deferral)
        await self._async_evaluate()

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

        for zone in self.config.zones:
            if zone.indoor_sensor:
                entities.add(zone.indoor_sensor)
            entities.update(source.entity_id for source in zone.sources if source.entity_id)

        for circuit in self.config.circuits:
            entities.update(unit for unit in circuit.units if unit)

        for opening in self.config.openings:
            if opening.entity_id:
                entities.add(opening.entity_id)

        for resident in self.config.residents:
            if resident.presence_entity:
                entities.add(resident.presence_entity)
            if resident.sleep_entity:
                entities.add(resident.sleep_entity)

        return entities

    # -- aanleidingen / triggers --------------------------------------------

    @callback
    def _handle_change(self, event: Event[EventStateChangedData]) -> None:
        """Queue a fresh decision after a tracked entity changed."""
        self._debouncer.async_schedule_call()

    @callback
    def async_request_evaluation(self) -> None:
        """Ask for a fresh decision, from a switch or a service call."""
        self._debouncer.async_schedule_call()

    async def async_shutdown(self) -> None:
        """Stop deciding and drop every pending timer."""
        self._cancel_pending_deferral()
        self._debouncer.async_shutdown()
        await super().async_shutdown()

    # -- beslissen / deciding ------------------------------------------------

    async def _async_evaluate(self) -> None:
        """Read the world, decide, apply, and report."""
        async with self._lock:
            world = self.build_world()
            self._remember_families(world)
            world = self._with_family_history(world)

            plan = decide(self.config, world)
            self.world = world

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
            self._schedule_deferral(plan)
            self.async_set_updated_data(plan)

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
                opening.entity_id: self._opening(opening.entity_id)
                for opening in self.config.openings
                if opening.entity_id
            },
            master_enabled=self.master_enabled,
            holiday_mode=self.holiday_mode,
            zone_overrides=dict(self.zone_overrides),
        )

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
        return entities

    def _climate(self, entity_id: str) -> ClimateState:
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return ClimateState(available=False)
        return ClimateState(
            hvac_mode=state.state,
            current_temperature=_as_float(state.attributes.get("current_temperature")),
            target_temperature=_as_float(state.attributes.get("temperature")),
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

    def _opening(self, entity_id: str) -> OpeningState:
        state = self.hass.states.get(entity_id)
        if state is None:
            return OpeningState()
        return OpeningState(
            open=state.state == "on",
            changed_at=dt_util.as_local(state.last_changed),
        )

    def _season(self) -> Season:
        settings = self.config.seasons
        if settings.source is SeasonSource.SUMMER:
            return Season.SUMMER
        if settings.source is SeasonSource.WINTER:
            return Season.WINTER
        if settings.source is SeasonSource.ENTITY:
            state = self.hass.states.get(settings.entity_id) if settings.entity_id else None
            return season_from_state(state.state if state else None)
        return settings.for_month(dt_util.now().month)

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
        """Return the snapshot with the recorded duty-change times filled in."""
        return WorldState(
            now=world.now,
            outdoor_temperature=world.outdoor_temperature,
            season=world.season,
            indoor_temperatures=world.indoor_temperatures,
            climates=world.climates,
            residents=world.residents,
            openings=world.openings,
            circuit_family_since=dict(self._family_since),
            master_enabled=world.master_enabled,
            holiday_mode=world.holiday_mode,
            zone_overrides=world.zone_overrides,
        )

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


def _as_float(raw: Any) -> float | None:
    """Return `raw` as a float, or `None` when it is not a number."""
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None
