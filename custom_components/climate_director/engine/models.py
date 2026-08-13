"""Configuratiemodel van Climate Director.

Configuration model for Climate Director.

Drie niveaus staan hier los van elkaar:

* **Zone** - een ruimte. Beschrijft *wat je wilt*.
* **Koelcircuit** - een buitenunit met de binnenunits die eraan hangen.
  Beschrijft *wat technisch tegelijk kan*.
* **Installatie** (`DirectorConfig`) - het geheel.

Een circuit spant willekeurige zones, en een zone mag binnenunits van meerdere
circuits hebben. De twee assen kruisen elkaar en zijn nergens aan elkaar
vastgeknoopt.

Three levels stand apart here:

* **Zone** - a room. Describes *what you want*.
* **Refrigerant circuit** - one outdoor unit and the indoor units on it.
  Describes *what is technically possible at the same time*.
* **Installation** (`DirectorConfig`) - the whole.

A circuit spans arbitrary zones, and a zone may hold indoor units from several
circuits. The two axes cross and are never tied to one another.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time, timedelta
from enum import StrEnum

from .families import ModeFamily


class Season(StrEnum):
    """Coarse season used to gate whole modes on and off."""

    SUMMER = "summer"
    WINTER = "winter"
    UNKNOWN = "unknown"


class SourceRole(StrEnum):
    """Which duties a source is able to deliver."""

    HEAT_ONLY = "heat_only"
    COOL_ONLY = "cool_only"
    HEAT_COOL = "heat_cool"


class ConflictPolicy(StrEnum):
    """How a circuit picks a winner when zones want opposing duties."""

    PRIORITY = "priority"
    """Lowest `Zone.priority` number wins."""

    FIRST_COME = "first_come"
    """The duty already running keeps the circuit; a new one waits."""

    DEMAND = "demand"
    """The largest deviation from setpoint wins."""

    SEASON_LOCK = "season_lock"
    """The season dictates the duty; anything opposing it stands down."""


@dataclass(frozen=True, slots=True)
class OutdoorWindow:
    """Half-open outdoor-temperature range `[minimum, maximum)`.

    Half-open on purpose: two adjacent windows written as `(None, 3.0)` and
    `(3.0, None)` then cover the whole scale with neither a gap nor an
    overlap, so no outdoor temperature can ever fall between two sources.
    """

    minimum: float | None = None
    maximum: float | None = None

    @property
    def unbounded(self) -> bool:
        """Return whether this window accepts every temperature."""
        return self.minimum is None and self.maximum is None

    @property
    def empty(self) -> bool:
        """Return whether this window can never be satisfied.

        Since the range is half-open, a minimum equal to the maximum admits
        nothing either - which is a configuration mistake, not a narrow window.
        """
        return (
            self.minimum is not None and self.maximum is not None and self.minimum >= self.maximum
        )

    def contains(self, outdoor: float | None) -> bool:
        """Return whether `outdoor` falls inside this window.

        An unknown outdoor temperature satisfies an unbounded window but never
        a bounded one - a bound that cannot be checked is not met.
        """
        if self.unbounded:
            return True
        if outdoor is None:
            return False
        if self.minimum is not None and outdoor < self.minimum:
            return False
        return not (self.maximum is not None and outdoor >= self.maximum)


@dataclass(frozen=True, slots=True)
class ModeSettings:
    """Everything needed to decide whether one duty should run in one zone.

    `start_at` and `hysteresis` replace the four separate minimum/maximum
    indoor thresholds that hand-built automations tend to grow, and make the
    dead band explicit instead of accidental:

    * heating starts at `indoor <= start_at` and stops at
      `indoor >= start_at + hysteresis`;
    * cooling starts at `indoor >= start_at` and stops at
      `indoor <= start_at - hysteresis`.
    """

    target: float
    """Setpoint handed to the climate entity once this duty runs."""

    start_at: float
    """Indoor temperature at which this duty starts."""

    hysteresis: float = 1.0
    """Width of the dead band. Zero means the duty may chatter on `start_at`."""

    outdoor: OutdoorWindow = field(default_factory=OutdoorWindow)
    """Outdoor range in which this duty is worth running at all."""

    seasons: frozenset[Season] | None = None
    """Seasons this duty is allowed in. `None` means every season."""

    def allowed_in(self, season: Season) -> bool:
        """Return whether this duty may run during `season`."""
        return self.seasons is None or season in self.seasons


@dataclass(frozen=True, slots=True)
class Source:
    """One appliance able to serve a zone: an indoor unit, a boiler, a stove."""

    source_id: str
    entity_id: str
    role: SourceRole = SourceRole.HEAT_COOL
    priority: int = 0
    """Preference within a zone; the lowest number available wins."""

    outdoor: OutdoorWindow = field(default_factory=OutdoorWindow)
    """Outdoor range in which this source is the sensible choice."""

    def supports(self, family: ModeFamily) -> bool:
        """Return whether this source can deliver `family`."""
        if family is ModeFamily.HEAT:
            return self.role in (SourceRole.HEAT_ONLY, SourceRole.HEAT_COOL)
        if family is ModeFamily.COOL:
            return self.role in (SourceRole.COOL_ONLY, SourceRole.HEAT_COOL)
        return False


@dataclass(frozen=True, slots=True)
class Zone:
    """A room, with the sources able to serve it and the comfort it aims for."""

    zone_id: str
    name: str
    indoor_sensor: str
    sources: tuple[Source, ...] = ()
    priority: int = 0
    """Weight in circuit conflicts; the lowest number wins."""

    heat: ModeSettings | None = None
    cool: ModeSettings | None = None

    def settings_for(self, family: ModeFamily) -> ModeSettings | None:
        """Return the settings for `family`, or `None` if the zone forbids it."""
        if family is ModeFamily.HEAT:
            return self.heat
        if family is ModeFamily.COOL:
            return self.cool
        return None


@dataclass(frozen=True, slots=True)
class Circuit:
    """One outdoor unit and the indoor units sharing its refrigerant."""

    circuit_id: str
    name: str
    units: tuple[str, ...] = ()
    """Climate entity ids sharing this outdoor unit.

    Authoritative membership, and deliberately entity ids rather than source
    ids: an indoor unit the director does not manage still claims the
    compressor, so its duty has to be taken into account.
    """

    simultaneous_heat_cool: bool = True
    """`False` for an ordinary multi-split: one duty at a time across all units.

    `True` for a single split (its own outdoor unit) and for three-pipe VRF
    with heat recovery, which genuinely does both at once. Deliberately a flag
    rather than something derived from a unit count, so heat-recovery systems
    are not crippled by a blanket rule.
    """

    conflict_policy: ConflictPolicy = ConflictPolicy.PRIORITY
    allow_fan_only_during_conflict: bool = False
    """Whether a zone that loses its circuit may keep circulating air."""

    family_switch_delay: timedelta = timedelta(0)
    """Pause between stopping the old duty and starting the new one."""

    min_family_switch_interval: timedelta = timedelta(0)
    """Shortest time the circuit must hold a duty before swapping to the other."""

    min_cycle_time: timedelta = timedelta(0)
    """Rest a unit must take after stopping before it may start again.

    Only ever delays starting, never stopping - short-cycle protection must not
    be able to keep a unit running.
    """

    max_concurrent_units: int | None = None
    """Cap on simultaneously running indoor units, for undersized outdoor units."""


@dataclass(frozen=True, slots=True)
class TimeWindow:
    """A recurring window, optionally limited to certain weekdays."""

    start: time
    end: time
    weekdays: frozenset[int] | None = None
    """`datetime.weekday()` numbers (Monday is 0). `None` means every day."""

    def contains(self, moment: time, weekday: int) -> bool:
        """Return whether `moment` on `weekday` falls inside this window.

        A window whose end lies before its start runs through midnight. It is
        anchored on the weekday it *starts*, so a Friday 22:00-02:00 window
        still counts at 01:00 on Saturday.
        """
        if self.start <= self.end:
            in_window = self.start <= moment < self.end
            start_weekday = weekday
        else:
            after_midnight = moment < self.end
            in_window = self.start <= moment or after_midnight
            start_weekday = (weekday - 1) % 7 if after_midnight else weekday
        if not in_window:
            return False
        return self.weekdays is None or start_weekday in self.weekdays


@dataclass(frozen=True, slots=True)
class Resident:
    """Someone whose presence and sleep gate the installation."""

    resident_id: str
    name: str = ""
    windows: tuple[TimeWindow, ...] = ()
    """Times this resident wants climate control. Empty means always."""

    def wants_climate_at(self, moment: time, weekday: int) -> bool:
        """Return whether this resident's schedule is open at that moment."""
        if not self.windows:
            return True
        return any(window.contains(moment, weekday) for window in self.windows)


@dataclass(frozen=True, slots=True)
class Opening:
    """A door or window that suspends climate control while it stands open."""

    entity_id: str
    zone_ids: tuple[str, ...] = ()
    """Zones this opening suspends. Empty means the whole installation."""

    delay: timedelta = timedelta(seconds=30)
    """How long it must stand open before anything is suspended."""

    def affects(self, zone_id: str) -> bool:
        """Return whether this opening suspends `zone_id`."""
        return not self.zone_ids or zone_id in self.zone_ids


@dataclass(frozen=True, slots=True)
class GateSettings:
    """Which conditions must hold before the director regulates at all."""

    require_occupancy: bool = True
    """Someone must be home."""

    require_awake: bool = True
    """Someone home must also be awake."""

    require_schedule: bool = False
    """Someone's schedule window must be open."""

    holiday_bypasses_schedule: bool = True
    """Holiday mode ignores the schedule gate, keeping presence and sleep."""


@dataclass(frozen=True, slots=True)
class DirectorConfig:
    """A whole installation."""

    zones: tuple[Zone, ...] = ()
    circuits: tuple[Circuit, ...] = ()
    residents: tuple[Resident, ...] = ()
    openings: tuple[Opening, ...] = ()
    exclusive_groups: tuple[frozenset[str], ...] = ()
    """Source-id groups of which at most one member may run at a time."""

    gates: GateSettings = field(default_factory=GateSettings)

    def zone(self, zone_id: str) -> Zone | None:
        """Return the zone with this id, if it exists."""
        return next((zone for zone in self.zones if zone.zone_id == zone_id), None)

    def circuit(self, circuit_id: str) -> Circuit | None:
        """Return the circuit with this id, if it exists."""
        return next(
            (circuit for circuit in self.circuits if circuit.circuit_id == circuit_id), None
        )

    def sources(self) -> tuple[tuple[Zone, Source], ...]:
        """Return every `(zone, source)` pair in the installation."""
        return tuple((zone, source) for zone in self.zones for source in zone.sources)

    def source(self, source_id: str) -> Source | None:
        """Return the source with this id, if it exists."""
        return next((source for _, source in self.sources() if source.source_id == source_id), None)

    def circuit_for_entity(self, entity_id: str) -> Circuit | None:
        """Return the circuit a climate entity sits on, if any.

        An entity on no circuit has an outdoor unit to itself and is therefore
        unconstrained - which is exactly the right default for a single split.
        """
        return next((circuit for circuit in self.circuits if entity_id in circuit.units), None)

    def sources_on(self, circuit: Circuit) -> tuple[tuple[Zone, Source], ...]:
        """Return every managed `(zone, source)` pair sitting on `circuit`."""
        return tuple(
            (zone, source) for zone, source in self.sources() if source.entity_id in circuit.units
        )


def validate(config: DirectorConfig) -> tuple[str, ...]:
    """Return every structural problem found in `config`, newest checks last.

    Returns an empty tuple for a sound configuration. Meant for the config flow
    and for tests; `decide()` itself never raises on a flawed configuration,
    since refusing to regulate a whole house over one bad zone is worse than
    regulating the sound zones and reporting the rest.
    """
    problems: list[str] = []

    zone_ids = [zone.zone_id for zone in config.zones]
    problems += [f"duplicate zone id: {zone_id}" for zone_id in _duplicates(zone_ids)]

    circuit_ids = [circuit.circuit_id for circuit in config.circuits]
    problems += [f"duplicate circuit id: {circuit_id}" for circuit_id in _duplicates(circuit_ids)]

    source_ids = [source.source_id for _, source in config.sources()]
    problems += [f"duplicate source id: {source_id}" for source_id in _duplicates(source_ids)]

    entity_ids = [source.entity_id for _, source in config.sources()]
    problems += [
        f"climate entity {entity_id} is used by more than one source"
        for entity_id in _duplicates(entity_ids)
    ]

    seen_units: dict[str, str] = {}
    for circuit in config.circuits:
        for unit in circuit.units:
            if unit in seen_units:
                problems.append(
                    f"unit {unit} sits on both circuit {seen_units[unit]} "
                    f"and circuit {circuit.circuit_id}"
                )
            else:
                seen_units[unit] = circuit.circuit_id

    for zone in config.zones:
        if not zone.sources:
            problems.append(f"zone {zone.zone_id} has no sources")
        for source in zone.sources:
            if source.outdoor.empty:
                problems.append(
                    f"source {source.source_id} has an outdoor window that admits nothing"
                )
        for family in (ModeFamily.HEAT, ModeFamily.COOL):
            settings = zone.settings_for(family)
            if settings is None:
                continue
            if settings.hysteresis < 0:
                problems.append(f"zone {zone.zone_id} has a negative {family.value} hysteresis")
            if settings.outdoor.empty:
                problems.append(
                    f"zone {zone.zone_id} has a {family.value} outdoor window that admits nothing"
                )
            if not any(source.supports(family) for source in zone.sources):
                problems.append(
                    f"zone {zone.zone_id} wants {family.value} but has no source for it"
                )

    known_sources = set(source_ids)
    for group in config.exclusive_groups:
        problems += [
            f"exclusive group names unknown source {source_id}"
            for source_id in sorted(group - known_sources)
        ]

    return tuple(problems)


def _duplicates(values: list[str]) -> list[str]:
    """Return the values occurring more than once, in first-seen order."""
    seen: set[str] = set()
    duplicated: list[str] = []
    for value in values:
        if value in seen and value not in duplicated:
            duplicated.append(value)
        seen.add(value)
    return duplicated
