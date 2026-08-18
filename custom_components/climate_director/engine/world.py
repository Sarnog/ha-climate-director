"""Momentopname van de wereld waar de engine op beslist.

Snapshot of the world the engine decides on.

`WorldState` is de enige invoer naast de configuratie. De engine leest nooit
zelf entiteiten uit; de koppelingslaag vult deze momentopname en krijgt er een
`Plan` voor terug. Daardoor is elk scenario als dataobject na te bouwen en te
testen zonder Home Assistant.

`WorldState` is the only input besides the configuration. The engine never
reads entities itself; the binding layer fills this snapshot and gets a `Plan`
back for it. Every scenario is therefore reproducible as a data object and
testable without Home Assistant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .families import MODE_OFF, ModeFamily, family_of
from .models import Season


@dataclass(frozen=True, slots=True)
class ClimateState:
    """What a climate entity reports right now."""

    hvac_mode: str = MODE_OFF
    current_temperature: float | None = None
    target_temperature: float | None = None
    available: bool = True
    changed_at: datetime | None = None
    """When this entity last changed state, for short-cycle protection."""

    @property
    def family(self) -> ModeFamily:
        """Return the compressor duty this entity currently claims."""
        return family_of(self.hvac_mode)

    @property
    def running(self) -> bool:
        """Return whether this entity currently claims the compressor."""
        return self.family in (ModeFamily.HEAT, ModeFamily.COOL, ModeFamily.AMBIGUOUS)


@dataclass(frozen=True, slots=True)
class ResidentState:
    """Where a resident is and whether they are awake."""

    home: bool = False
    asleep: bool = False

    @property
    def present_and_awake(self) -> bool:
        """Return whether this resident is home and out of bed."""
        return self.home and not self.asleep


@dataclass(frozen=True, slots=True)
class OpeningState:
    """Whether a door or window stands open, and since when."""

    open: bool = False
    changed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class PresenceState:
    """Whether a room is occupied, and since when.

    The timestamp is what lets a zone ride out a presence sensor blinking off
    for a moment instead of stopping its compressor over it.
    """

    occupied: bool = False
    changed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class WorldState:
    """Everything the engine needs to know at one moment in time."""

    now: datetime
    outdoor_temperature: float | None = None
    season: Season = Season.UNKNOWN

    indoor_temperatures: dict[str, float | None] = field(default_factory=dict)
    """Keyed by `zone_id`."""

    climates: dict[str, ClimateState] = field(default_factory=dict)
    """Keyed by climate entity id."""

    residents: dict[str, ResidentState] = field(default_factory=dict)
    """Keyed by `resident_id`."""

    openings: dict[str, OpeningState] = field(default_factory=dict)
    """Keyed by opening entity id."""

    presence: dict[str, PresenceState] = field(default_factory=dict)
    """Room occupancy, keyed by `zone_id`."""

    circuit_family_since: dict[str, datetime | None] = field(default_factory=dict)
    """When each circuit last took on its current duty, keyed by `circuit_id`."""

    master_enabled: bool = True
    holiday_mode: bool = False

    precondition_bypass: frozenset[str] = frozenset()
    """Zones whose pre-conditioning request may run with an opening open.

    Standaard weigert een openstaand raam een verzoek, en dat hoort ook: stoken
    tegen de buitenlucht in is weggegooid geld. Maar wie het raam zelf heeft
    opengezet weet dat, en mag zeggen: toch doen. Die keuze hoort bij het
    verzoek en niet bij de aanroep, want de poort wordt telkens opnieuw
    beoordeeld - zonder dit zou het verzoek een minuut later alsnog sneuvelen.

    By default an open window refuses a request, and rightly so: heating
    against the outside air is money thrown away. But whoever opened the window
    knows that, and may say: do it anyway. That choice belongs to the request
    rather than to the call, since the gate is judged afresh every time -
    without this the request would die a minute later after all.
    """

    precondition_until: dict[str, datetime] = field(default_factory=dict)
    """Per zone, the moment a human's pre-conditioning request runs out.

    Absolute rather than a countdown on purpose: a moment that has passed is
    over, whatever happened in between - a restart, a stopped clock, a plan that
    took a while. There is no way for this to quietly stay alive.
    """

    guest_mode: bool = False
    """Keeps the house running while the tracked people are away.

    Somebody is staying who is not one of the residents, so presence, sleep and
    schedules say nothing useful about whether the rooms are in use.
    """

    zone_overrides: dict[str, bool] = field(default_factory=dict)
    """Manual override per `zone_id`; a missing zone counts as no override."""

    zone_priorities: dict[str, int] = field(default_factory=dict)
    """Live priority per `zone_id`, overriding the configured one.

    Kept out of the configuration on purpose: which room outranks which is
    something an automation may well want to change by the hour, and
    rewriting a config entry for that would reload the whole installation.
    """

    def climate(self, entity_id: str) -> ClimateState:
        """Return a climate entity's state, or an unavailable placeholder."""
        return self.climates.get(entity_id, ClimateState(available=False))

    def indoor(self, zone_id: str) -> float | None:
        """Return a zone's indoor temperature, or `None` when unknown."""
        return self.indoor_temperatures.get(zone_id)

    def resident(self, resident_id: str) -> ResidentState:
        """Return a resident's state, or an away placeholder."""
        return self.residents.get(resident_id, ResidentState())

    def opening(self, entity_id: str) -> OpeningState:
        """Return an opening's state, or a closed placeholder."""
        return self.openings.get(entity_id, OpeningState())

    def presence_of(self, zone_id: str) -> PresenceState:
        """Return a zone's occupancy, or an empty-room placeholder."""
        return self.presence.get(zone_id, PresenceState())

    def priority_for(self, zone_id: str, configured: int) -> int:
        """Return the priority in force for a zone, live value first."""
        return self.zone_priorities.get(zone_id, configured)

    def precondition_ignores_openings(self, zone_id: str) -> bool:
        """Return whether this zone's request was told to ignore an open window."""
        return self.preconditioning(zone_id) and zone_id in self.precondition_bypass

    def preconditioning(self, zone_id: str) -> bool:
        """Return whether a live pre-conditioning request covers this zone."""
        until = self.precondition_until.get(zone_id)
        return until is not None and self.now < until

    def overridden(self, zone_id: str) -> bool:
        """Return whether a manual override holds this zone."""
        return self.zone_overrides.get(zone_id, False)
