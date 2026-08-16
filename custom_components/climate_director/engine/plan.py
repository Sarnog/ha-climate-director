"""Uitvoer van de engine: het plan en de redenen erachter.

Output of the engine: the plan and the reasoning behind it.

Een `Plan` beschrijft gewenste eindtoestanden, geen handelingen. De applier
vergelijkt ze met de werkelijkheid en doet alleen wat nog niet klopt, waardoor
opnieuw beslissen op hetzelfde moment nooit extra service calls oplevert.

A `Plan` describes desired end states, not actions. The applier compares them
against reality and only does what does not match yet, so deciding again at the
same moment never produces extra service calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from .families import ModeFamily


class Reason(StrEnum):
    """Stable identifier for why the engine decided something.

    Stable rather than free text so the Home Assistant layer can translate it
    and users can branch on it in their own automations.
    """

    REGULATING = "regulating"
    SATISFIED = "satisfied"
    WITHIN_DEADBAND = "within_deadband"

    MASTER_DISABLED = "master_disabled"
    MANUAL_OVERRIDE = "manual_override"
    OPENING_OPEN = "opening_open"
    NOBODY_HOME = "nobody_home"
    EVERYONE_ASLEEP = "everyone_asleep"
    OUTSIDE_SCHEDULE = "outside_schedule"
    ZONE_UNOCCUPIED = "zone_unoccupied"

    NO_INDOOR_TEMPERATURE = "no_indoor_temperature"
    SEASON_BLOCKS_MODE = "season_blocks_mode"
    OUTDOOR_OUTSIDE_WINDOW = "outdoor_outside_window"
    MODE_NOT_CONFIGURED = "mode_not_configured"
    NO_SOURCE_AVAILABLE = "no_source_available"
    OTHER_SOURCE_CHOSEN = "other_source_chosen"

    CIRCUIT_CONFLICT_LOST = "circuit_conflict_lost"
    CIRCUIT_SWITCH_TOO_SOON = "circuit_switch_too_soon"
    CIRCUIT_SWITCH_PENDING = "circuit_switch_pending"
    CIRCUIT_AT_CAPACITY = "circuit_at_capacity"
    SHORT_CYCLE_PROTECTION = "short_cycle_protection"
    EXCLUSIVE_GROUP_LOST = "exclusive_group_lost"


@dataclass(frozen=True, slots=True)
class UnitCommand:
    """The end state one climate entity should be in."""

    entity_id: str
    hvac_mode: str
    temperature: float | None = None
    zone_id: str | None = None
    source_id: str | None = None
    reason: Reason = Reason.REGULATING


@dataclass(frozen=True, slots=True)
class ZoneDecision:
    """What a zone asked for and what it was granted."""

    zone_id: str
    wanted: ModeFamily
    granted: ModeFamily
    source_id: str | None = None
    reason: Reason = Reason.REGULATING

    @property
    def blocked(self) -> bool:
        """Return whether the zone got less than it asked for."""
        return self.wanted != self.granted


@dataclass(frozen=True, slots=True)
class CircuitDecision:
    """Which duty a circuit runs, and who lost out over it."""

    circuit_id: str
    family: ModeFamily
    winner_zone_id: str | None = None
    displaced_zone_ids: tuple[str, ...] = ()
    reason: Reason = Reason.REGULATING


@dataclass(frozen=True, slots=True)
class Deferral:
    """Something the engine wants but may not do yet.

    The binding layer schedules a fresh evaluation at `until`, so a plan that
    is held back by a timer resumes on its own instead of waiting for the next
    unrelated state change.
    """

    subject: str
    """Circuit id or climate entity id the wait applies to."""

    until: datetime
    reason: Reason


@dataclass(frozen=True, slots=True)
class Plan:
    """One complete, internally consistent decision."""

    commands: tuple[UnitCommand, ...] = ()
    zones: tuple[ZoneDecision, ...] = ()
    circuits: tuple[CircuitDecision, ...] = ()
    deferrals: tuple[Deferral, ...] = field(default_factory=tuple)

    def command_for(self, entity_id: str) -> UnitCommand | None:
        """Return the command aimed at this entity, if any."""
        return next((command for command in self.commands if command.entity_id == entity_id), None)

    def decision_for(self, zone_id: str) -> ZoneDecision | None:
        """Return the decision made for this zone, if any."""
        return next((zone for zone in self.zones if zone.zone_id == zone_id), None)

    def circuit_for(self, circuit_id: str) -> CircuitDecision | None:
        """Return the decision made for this circuit, if any."""
        return next(
            (circuit for circuit in self.circuits if circuit.circuit_id == circuit_id), None
        )

    @property
    def next_deferral(self) -> Deferral | None:
        """Return the deferral that expires first, if any."""
        return min(self.deferrals, key=lambda deferral: deferral.until, default=None)
