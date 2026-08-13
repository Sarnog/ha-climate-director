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

    circuit_family_since: dict[str, datetime | None] = field(default_factory=dict)
    """When each circuit last took on its current duty, keyed by `circuit_id`."""

    master_enabled: bool = True
    holiday_mode: bool = False

    zone_overrides: dict[str, bool] = field(default_factory=dict)
    """Manual override per `zone_id`; a missing zone counts as no override."""

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

    def overridden(self, zone_id: str) -> bool:
        """Return whether a manual override holds this zone."""
        return self.zone_overrides.get(zone_id, False)
