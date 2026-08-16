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

#: Een vakantiedag telt als zaterdag, tenzij er een eigen vakantierooster is.
#: A holiday counts as a Saturday, unless a holiday schedule says otherwise.
HOLIDAY_WEEKDAY = 5


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

    presence_entity: str = ""
    """Entity saying whether this room is occupied. Empty means never checked.

    Distinct from the installation-wide occupancy gate: somebody being home
    says nothing about whether they are in the attic. A room nobody sits in is
    a room worth leaving alone, however awake the household is.
    """

    presence_state: str = "on"
    """The `presence_entity` state that means occupied."""

    presence_timeout: timedelta = timedelta(0)
    """How long the room still counts as occupied after presence drops.

    Presence sensors flicker, and a zone that stops the moment somebody sits
    still would cycle its compressor for no reason. Zero means react at once.
    """

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
class Generator:
    """A heat source several zones draw on through their own valves.

    A wet system works differently from a multi-split. Radiator valves do not
    fight over a compressor duty - they all only ever heat - so there is nothing
    to arbitrate. What they do share is the appliance making the hot water: a
    valve opening achieves nothing while the boiler is cold, and the boiler
    running achieves nothing while every valve is shut.

    That is an *and*, not an exclusion, which is why this is not a `Circuit`.
    Systems that manage their own boiler (Tado, Netatmo and the like) need none
    of this: their bridge fires the burner the moment a valve asks. Declare a
    generator only where the appliance is a separate entity somebody has to
    switch.
    """

    generator_id: str
    name: str
    entity_id: str

    zone_ids: tuple[str, ...] = ()
    """Zones this generator serves. Empty means every zone."""

    setpoint: float | None = None
    """Flow setpoint. `None` follows the warmest target among the zones asking."""

    def serves(self, zone_id: str) -> bool:
        """Return whether this generator supplies `zone_id`."""
        return not self.zone_ids or zone_id in self.zone_ids


@dataclass(frozen=True, slots=True)
class TimeWindow:
    """A recurring window, optionally limited to certain weekdays."""

    start: time
    end: time
    weekdays: frozenset[int] | None = None
    """`datetime.weekday()` numbers (Monday is 0). `None` means every day."""

    holiday: bool = False
    """Whether this window applies on holidays instead of on ordinary days.

    A holiday window ignores its weekdays: a holiday is not a day of the week.
    """

    def contains(self, moment: time, weekday: int, *, any_day: bool = False) -> bool:
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
        if any_day:
            return True
        return self.weekdays is None or start_weekday in self.weekdays


@dataclass(frozen=True, slots=True)
class Resident:
    """Someone whose presence and sleep gate the installation."""

    resident_id: str
    name: str = ""
    windows: tuple[TimeWindow, ...] = ()
    """Times this resident wants climate control. Empty means always."""

    presence_entity: str = ""
    """Entity saying whether this person is home, usually a `person`."""

    sleep_entity: str = ""
    """Entity saying whether this person is asleep. Empty means never asleep."""

    sleep_state: str = "on"
    """The `sleep_entity` state that means asleep.

    Deliberately free text rather than a fixed `on`: a bed sensor reports `on`,
    a phone's charger-type sensor reports `wireless`, a sleep-tracker may report
    `asleep`. The engine never resolves these - they are opaque strings the
    binding layer reads entities with, exactly like `Zone.indoor_sensor`.
    """

    def windows_for(self, *, holiday: bool) -> tuple[TimeWindow, ...]:
        """Return the windows that apply today.

        On a holiday the resident's holiday windows take over if they set any.
        Without them a holiday counts as a Saturday, which is what a household
        means by one: the day the alarm stays off.
        """
        if holiday:
            special = tuple(window for window in self.windows if window.holiday)
            if special:
                return special
        return tuple(window for window in self.windows if not window.holiday)

    def takes_part(self, *, holiday: bool) -> bool:
        """Return whether this resident has anything to say about today."""
        return bool(self.windows_for(holiday=holiday))

    def wants_climate_at(self, moment: time, weekday: int, *, holiday: bool = False) -> bool:
        """Return whether this resident's schedule is open at that moment."""
        windows = self.windows_for(holiday=holiday)
        if not windows:
            return True
        if holiday and any(window.holiday for window in windows):
            return any(window.contains(moment, weekday, any_day=True) for window in windows)
        return any(
            window.contains(moment, HOLIDAY_WEEKDAY if holiday else weekday) for window in windows
        )


@dataclass(frozen=True, slots=True)
class Opening:
    """A door or window that suspends climate control while it stands open."""

    entity_id: str
    zone_ids: tuple[str, ...] = ()
    """Zones this opening suspends. Empty means the whole installation."""

    delay: timedelta = timedelta(0)
    """How long it must stand open before anything is suspended.

    Zero suspends the moment it opens. Deliberately the default: a delay is
    a choice about a particular door, and inventing half a minute for one
    that was never given a value hides that choice.
    """

    def affects(self, zone_id: str) -> bool:
        """Return whether this opening suspends `zone_id`."""
        return not self.zone_ids or zone_id in self.zone_ids


@dataclass(frozen=True, slots=True)
class GateSettings:
    """Which conditions must hold before the director regulates at all."""

    require_awake: bool = True
    """Someone home must also be awake."""

    require_schedule: bool = False
    """Someone's schedule window must be open."""

    guest_window: TimeWindow | None = None
    """Hours in which guest mode carries the house. `None` means all day.

    Guest mode stands in for people the integration cannot see, and people are
    only unaccounted for while they are up. Outside these hours the ordinary
    gates take over again.
    """


class SeasonSource(StrEnum):
    """Where the coarse season comes from."""

    AUTO = "auto"
    """Derived from the month."""

    ENTITY = "entity"
    """Read from an entity, so an existing helper keeps working."""

    SUMMER = "summer"
    WINTER = "winter"
    """Pinned by hand."""


@dataclass(frozen=True, slots=True)
class SeasonSettings:
    """How to resolve the season the zones are gated on."""

    source: SeasonSource = SeasonSource.AUTO
    entity_id: str = ""
    summer_months: frozenset[int] = frozenset({4, 5, 6, 7, 8, 9})
    """Month numbers counting as summer when `source` is `AUTO`."""

    def for_month(self, month: int) -> Season:
        """Return the season `AUTO` would pick for this month."""
        return Season.SUMMER if month in self.summer_months else Season.WINTER


@dataclass(frozen=True, slots=True)
class DirectorConfig:
    """A whole installation."""

    zones: tuple[Zone, ...] = ()
    circuits: tuple[Circuit, ...] = ()
    residents: tuple[Resident, ...] = ()
    openings: tuple[Opening, ...] = ()
    generators: tuple[Generator, ...] = ()
    exclusive_groups: tuple[frozenset[str], ...] = ()
    """Source-id groups of which at most one member may run at a time."""

    gates: GateSettings = field(default_factory=GateSettings)
    seasons: SeasonSettings = field(default_factory=SeasonSettings)

    outdoor_sensor: str = ""
    """Entity carrying the outdoor temperature. Empty leaves it unknown."""

    holiday_calendars: tuple[str, ...] = ()
    """Calendars whose running events may put the house on holiday."""

    holiday_keyword: str = ""
    """Word an event must carry to count.

    Empty switches the calendars off entirely rather than letting every event
    through: a calendar full of dentist appointments is not a holiday calendar,
    and guessing which of its events meant a holiday is not the integration's
    call to make.
    """

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

    # Een begrensd buitenvenster kan zonder buitentemperatuur nooit voldaan
    # worden, dus alles wat er een heeft valt stil. Dat is de stilste manier
    # waarop een installatie kan blijven staan: elke zone besluit netjes "niets
    # te doen", en nergens staat waarom. Daarom is het een eigen melding.
    #
    # A bounded outdoor window can never be satisfied without an outdoor
    # temperature, so anything carrying one falls still. That is the quietest
    # way an installation can seize up: every zone decides "nothing to do", and
    # nowhere does it say why. Hence a problem of its own.
    outdoor_known = bool(config.outdoor_sensor)

    for zone in config.zones:
        if not zone.sources:
            problems.append(f"zone {zone.zone_id} has no sources")
        if not zone.indoor_sensor:
            problems.append(f"zone {zone.zone_id} has no indoor temperature sensor")
        if zone.heat is None and zone.cool is None:
            problems.append(f"zone {zone.zone_id} may neither heat nor cool")
        if zone.presence_timeout.total_seconds() < 0:
            problems.append(f"zone {zone.zone_id} has a negative presence timeout")
        if (
            zone.heat is not None
            and zone.cool is not None
            and zone.cool.start_at <= zone.heat.start_at
        ):
            # Anders vragen verwarmen en koelen tegelijk om dezelfde kamer. De
            # engine kiest dan wel deterministisch, maar dat het zover komt is
            # een instelfout die niemand bedoeld kan hebben.
            #
            # Otherwise heating and cooling ask for the same room at once. The
            # engine still picks deterministically, but getting there is a
            # mistake nobody can have meant.
            problems.append(
                f"zone {zone.zone_id} starts cooling at or below where it starts heating"
            )
        for source in zone.sources:
            if source.outdoor.empty:
                problems.append(
                    f"source {source.source_id} has an outdoor window that admits nothing"
                )
            elif not outdoor_known and not source.outdoor.unbounded:
                problems.append(
                    f"source {source.source_id} is limited by outdoor temperature, "
                    "but no outdoor sensor is set"
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
            elif not outdoor_known and not settings.outdoor.unbounded:
                problems.append(
                    f"zone {zone.zone_id} limits {family.value} by outdoor temperature, "
                    "but no outdoor sensor is set"
                )
            if not any(source.supports(family) for source in zone.sources):
                problems.append(
                    f"zone {zone.zone_id} wants {family.value} but has no source for it"
                )

    source_entities = set(entity_ids)
    for generator in config.generators:
        if generator.entity_id in source_entities:
            problems.append(
                f"generator {generator.generator_id} uses climate entity "
                f"{generator.entity_id}, which is already a zone's source"
            )
        unknown = [zone_id for zone_id in generator.zone_ids if zone_id not in set(zone_ids)]
        problems += [
            f"generator {generator.generator_id} names unknown zone {zone_id}"
            for zone_id in unknown
        ]

    # Twee zones op één buitenunit met hetzelfde nummer laten de uitkomst
    # afhangen van hun zone-id, dus alfabetisch. Dat crasht niets en beschadigt
    # niets - de tie-break is deterministisch en het circuit houdt zich aan zijn
    # ene taak - maar welke kamer wint is dan onzichtbaar en willekeurig.
    #
    # Two zones on one outdoor unit sharing a number leave the outcome hanging
    # on their zone id, so alphabetical. That crashes nothing and damages
    # nothing - the tie-break is deterministic and the circuit still keeps to
    # its one duty - but which room wins becomes invisible and arbitrary.
    for circuit in config.circuits:
        seen: dict[int, str] = {}
        for zone, _ in config.sources_on(circuit):
            if zone.priority in seen and seen[zone.priority] != zone.zone_id:
                problems.append(
                    f"zones {seen[zone.priority]} and {zone.zone_id} share priority "
                    f"{zone.priority} on circuit {circuit.circuit_id}"
                )
            else:
                seen[zone.priority] = zone.zone_id

        if circuit.max_concurrent_units is not None and circuit.max_concurrent_units < 1:
            problems.append(f"circuit {circuit.circuit_id} allows no unit to run at all")
        for label, span in (
            ("family switch delay", circuit.family_switch_delay),
            ("minimum switch interval", circuit.min_family_switch_interval),
            ("minimum cycle time", circuit.min_cycle_time),
        ):
            if span.total_seconds() < 0:
                problems.append(f"circuit {circuit.circuit_id} has a negative {label}")

    known_zones = set(zone_ids)
    for opening in config.openings:
        problems += [
            f"opening {opening.entity_id} names unknown zone {zone_id}"
            for zone_id in opening.zone_ids
            if zone_id not in known_zones
        ]
        if opening.delay.total_seconds() < 0:
            problems.append(f"opening {opening.entity_id} has a negative delay")

    if config.gates.require_schedule and not any(resident.windows for resident in config.residents):
        problems.append(
            "the schedule gate is on but nobody has a schedule, so nothing can ever run"
        )

    if config.holiday_calendars and not config.holiday_keyword.strip():
        problems.append(
            "holiday calendars are set but no keyword is, so no event can ever "
            "switch holiday mode on"
        )

    problems += [
        f"resident {resident.resident_id} has no presence entity, so can never be home"
        for resident in config.residents
        if not resident.presence_entity
    ]

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
