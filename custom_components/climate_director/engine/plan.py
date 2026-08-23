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
    OPENING_OPEN_ELSEWHERE = "opening_open_elsewhere"
    NOBODY_HOME = "nobody_home"
    EVERYONE_ASLEEP = "everyone_asleep"
    OUTSIDE_SCHEDULE = "outside_schedule"
    ZONE_UNOCCUPIED = "zone_unoccupied"
    QUIET_HOURS = "quiet_hours"

    NO_INDOOR_TEMPERATURE = "no_indoor_temperature"
    NO_OUTDOOR_TEMPERATURE = "no_outdoor_temperature"
    SEASON_BLOCKS_MODE = "season_blocks_mode"
    OUTDOOR_OUTSIDE_WINDOW = "outdoor_outside_window"
    MODE_NOT_CONFIGURED = "mode_not_configured"
    NO_SOURCE_AVAILABLE = "no_source_available"
    OTHER_SOURCE_CHOSEN = "other_source_chosen"

    MANUAL_SOURCE = "manual_source"
    SOURCE_UNREACHABLE = "source_unreachable"

    CIRCUIT_CONFLICT_LOST = "circuit_conflict_lost"
    CIRCUIT_SWITCH_TOO_SOON = "circuit_switch_too_soon"
    CIRCUIT_SWITCH_PENDING = "circuit_switch_pending"
    CIRCUIT_AT_CAPACITY = "circuit_at_capacity"
    SHORT_CYCLE_PROTECTION = "short_cycle_protection"
    EXCLUSIVE_GROUP_LOST = "exclusive_group_lost"


#: Redenen die uit zichzelf horen op te lossen. Een zone die er lang op blijft
#: staan wacht op iets dat niet komt, en dat is een fout en geen toestand.
#:
#: Alle drie zijn het timers die in seconden of minuten aflopen. Een volle
#: buitenunit (`CIRCUIT_AT_CAPACITY`) stond er ook bij en hoort er niet: die
#: loopt pas leeg als een andere kamer ophoudt met vragen, en dat kan uren
#: duren zonder dat er iets mis is - een handbediende slaapkamerairco die de
#: hele avond aanstaat is precies waar die instelling voor bestaat. De melder
#: ging daardoor in een gesimuleerd jaar 352 keer af zonder aanleiding, en een
#: valse melding leert je de melder te negeren. De kamer die zijn plek niet
#: krijgt staat nog steeds als geblokkeerd te boek.
#:
#: Reasons that should resolve by themselves. A zone sitting on one for long is
#: waiting for something that is not coming, which is a fault and not a state.
#:
#: All three are timers running out in seconds or minutes. A full outdoor unit
#: (`CIRCUIT_AT_CAPACITY`) used to be listed here and does not belong: it only
#: frees up once another room stops asking, which may take hours with nothing
#: wrong - a hand-operated bedroom unit left on all evening is exactly what that
#: setting exists for. The sensor therefore went off 352 times in a simulated
#: year for no cause, and a false alarm teaches you to ignore the alarm. The room
#: that does not get its place still stands recorded as blocked.
WAITING_REASONS = frozenset(
    {
        Reason.CIRCUIT_SWITCH_PENDING,
        Reason.CIRCUIT_SWITCH_TOO_SOON,
        Reason.SHORT_CYCLE_PROTECTION,
    }
)

#: Poorten die "tegengehouden" betekenen: omstandigheden waar niemand om
#: vroeg. De hoofdschakelaar en de override staan er bewust niet bij: wie
#: die omzet zegt niet "dit kan nu niet" maar "ik neem het over", en dat is
#: geen blokkade om te melden.
#:
#: Gates that mean "held back": circumstances nobody asked for. The master
#: switch and the override are deliberately absent: whoever throws those is
#: not saying "this cannot run now" but "I am taking over", and that is no
#: blockage to report.
HOLDING_GATES = frozenset(
    {
        Reason.OPENING_OPEN,
        Reason.OPENING_OPEN_ELSEWHERE,
        Reason.QUIET_HOURS,
        Reason.ZONE_UNOCCUPIED,
        Reason.NOBODY_HOME,
        Reason.EVERYONE_ASLEEP,
        Reason.OUTSIDE_SCHEDULE,
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
class UntouchedSource:
    """An appliance the director issues nothing to, and why not.

    Niet aansturen is iets anders dan niets willen. Deze drie gevallen zijn
    alle drie met opzet - een overgedragen zone, een handbediend apparaat dat
    niemand in de weg staat, en een apparaat dat niet te bereiken is - en van
    buiten zagen ze er alle drie hetzelfde uit als "de director doet niets".

    Issuing nothing is not the same as wanting nothing. All three of these
    cases are deliberate - a zone handed over, a hand-operated appliance nobody
    needs out of the way, and an appliance that cannot be reached - and from
    the outside all three looked the same as "the director does nothing".
    """

    entity_id: str
    zone_id: str
    reason: Reason


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

    would_want: ModeFamily = field(default=ModeFamily.NEUTRAL, compare=False)
    """The duty this zone would want, its shut gates aside.

    Een zone met een dichte poort vraagt nooit iets, dus `wanted` blijft
    neutraal. Dit veld onthoudt wat de temperatuurregeling gewild zou hebben,
    en dat is precies wat `held_back` nodig heeft om "een dichte poort houdt
    een kamer tegen die wél iets nodig had" te onderscheiden van "een dichte
    poort terwijl de kamer toch al goed ligt".

    Zoals `closed_gates` bewust buiten de gelijkheid: een temperatuur die de
    dode band oversteekt verandert de melder, niet het besluit, en de
    koppelingslaag vuurt zijn event alleen bij een veranderd besluit.

    A zone with a shut gate never asks for anything, so `wanted` stays
    neutral. This field remembers what the temperature regulation would have
    wanted, which is exactly what `held_back` needs to tell "a shut gate is
    holding back a room that did need regulating" from "a shut gate while the
    room is comfortable anyway".

    Like `closed_gates`, deliberately outside equality: a temperature crossing
    the dead band changes the sensor, not the decision, and the binding layer
    fires its event only on a changed decision.
    """

    @property
    def blocked(self) -> bool:
        """Return whether the zone got less than it asked for."""
        return self.wanted != self.granted

    @property
    def held_back(self) -> bool:
        """Return whether a shut gate keeps a willing zone from regulating.

        Alleen de poorten over omstandigheden tellen. De hoofdschakelaar en
        de override zijn bewuste ingrepen van een mens, en die winnen: wie een
        zone overdraagt of de hele director uitzet wil geen "geblokkeerd"-
        melder per kamer zien branden.

        Only the gates about circumstances count. The master switch and the
        override are deliberate human acts, and they win: whoever hands a zone
        over or switches the whole director off does not want a "blocked"
        sensor burning in every room.
        """
        if self.would_want is ModeFamily.NEUTRAL:
            return False
        shut = set(self.closed_gates)
        if Reason.MANUAL_OVERRIDE in shut or Reason.MASTER_DISABLED in shut:
            return False
        return bool(shut & HOLDING_GATES)

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

    untouched: tuple[UntouchedSource, ...] = ()
    """The appliances this plan deliberately issues nothing to.

    Elk apparaat komt in precies één van de twee lijsten terecht: het krijgt
    een opdracht, of het staat hier met de reden waarom niet.

    Every appliance ends up in exactly one of the two lists: it gets a command,
    or it stands here with the reason why not.
    """

    def command_for(self, entity_id: str) -> UnitCommand | None:
        """Return the command aimed at this entity, if any."""
        return next((command for command in self.commands if command.entity_id == entity_id), None)

    def untouched_for(self, entity_id: str) -> UntouchedSource | None:
        """Return why this entity is being left alone, if it is."""
        return next((item for item in self.untouched if item.entity_id == entity_id), None)

    def decision_for(self, zone_id: str) -> ZoneDecision | None:
        """Return the decision made for this zone, if any."""
        return next((zone for zone in self.zones if zone.zone_id == zone_id), None)

    @property
    def next_deferral(self) -> Deferral | None:
        """Return the deferral that expires first, if any."""
        return min(self.deferrals, key=lambda deferral: deferral.until, default=None)
