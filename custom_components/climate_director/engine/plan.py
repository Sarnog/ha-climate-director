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
    QUIET_HOURS = "quiet_hours"

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


#: Redenen die uit zichzelf horen op te lossen. Een zone die er lang op blijft
#: staan wacht op iets dat niet komt, en dat is een fout en geen toestand.
#:
#: Reasons that should resolve by themselves. A zone sitting on one for long is
#: waiting for something that is not coming, which is a fault and not a state.
WAITING_REASONS = frozenset(
    {
        Reason.CIRCUIT_SWITCH_PENDING,
        Reason.CIRCUIT_SWITCH_TOO_SOON,
        Reason.SHORT_CYCLE_PROTECTION,
        Reason.CIRCUIT_AT_CAPACITY,
    }
)


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

    closed_gates: tuple[Reason, ...] = field(default=(), compare=False)
    """Every gate standing shut for this zone, broadest first.

    `reason` noemt er één, want één dichte poort houdt de zone al tegen. Bij
    het inrichten wil je ze alle vier tegelijk zien, in plaats van ze er stuk
    voor stuk uit te peuteren.

    Telt bewust niet mee in de gelijkheid. De koppelingslaag vuurt zijn
    beslissings-event alleen als een besluit veránderde, en dat is deze lijst
    niet: gaat er een tweede poort dicht terwijl de eerste al dicht stond, dan
    verandert er voor een automatisering niets. De reden zelf telt wél mee,
    en die verspringt zodra de bovenste poort wisselt.

    `reason` names one, since one shut gate is enough to hold the zone back.
    While setting up you want to see all four at once rather than prising them
    out one at a time.

    Deliberately left out of equality. The binding layer fires its decision
    event only when a decision changed, and this list is not that: a second
    gate shutting while the first already stood shut changes nothing for an
    automation. The reason itself does count, and it moves the moment the
    topmost gate changes.
    """

    passed_over: tuple[str, ...] = ()
    """Preferred sources skipped because they could not be reached.

    Leeg is het normale geval. Staat er iets in, dan draait de zone op een
    tweede keus omdat het eerste apparaat niet te bereiken was - de kamer wordt
    warm, maar niet zoals bedoeld.

    Empty is the normal case. Anything in here means the zone is running on a
    second choice because the first appliance could not be reached - the room
    gets warm, but not the way it was meant to.
    """

    @property
    def blocked(self) -> bool:
        """Return whether the zone got less than it asked for."""
        return self.wanted != self.granted

    @property
    def on_fallback(self) -> bool:
        """Return whether this zone is running on a stand-in."""
        return bool(self.passed_over)


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
