"""Apparaten en hun samenhang. / Appliances and how they hang together."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from enum import StrEnum

from .families import ModeFamily
from .seasons import Season


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

    def contains(self, outdoor: float | None, margin: float = 0.0) -> bool:
        """Return whether `outdoor` falls inside this window.

        An unknown outdoor temperature satisfies an unbounded window but never
        a bounded one - a bound that cannot be checked is not met.

        `margin` verruimt beide grenzen, en is bedoeld voor wat al draait: net
        als binnen mag een taak doorlopen tot een dode band voorbij zijn grens,
        zodat een buitentemperatuur die rond die grens schommelt de bron niet
        heen en weer trekt. Wie stilstaat krijgt hem niet - die moet de grens
        gewoon halen, anders zou de band de grens simpelweg verschuiven.

        `margin` widens both bounds, and is meant for what already runs: just as
        indoors, a duty may carry on until one dead band past its bound, so an
        outdoor temperature hovering around that bound does not drag the source
        back and forth. Whatever stands still does not get it - that has to
        reach the bound itself, or the band would merely move the bound.
        """
        if self.unbounded:
            return True
        if outdoor is None:
            return False
        slack = abs(margin)
        if self.minimum is not None and outdoor < self.minimum - slack:
            return False
        return not (self.maximum is not None and outdoor >= self.maximum + slack)


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
    name: str = ""
    """Eigen naam; leeg laat de bronkiezer het apparaat zelf noemen.

    This source's own name; empty lets the source picker name the appliance.
    """

    role: SourceRole = SourceRole.HEAT_COOL
    priority: int = 0
    """Preference within a zone; the lowest number available wins."""

    outdoor: OutdoorWindow = field(default_factory=OutdoorWindow)
    """Outdoor range in which this source is the sensible choice."""

    autostart: bool = True
    """Whether the director may switch this source on of its own accord.

    Zet dit uit voor een apparaat dat je zelf aanzet en verder met rust gelaten
    wil hebben - een slaapkamerairco bijvoorbeeld. De director start hem dan
    nooit, en laat hem staan zoals hij staat. Alleen als hij een taak draait die
    het circuit niet toestaat wordt hij uitgezet, want anders zou hij een kamer
    met meer voorrang blokkeren.

    Turn this off for an appliance you switch on yourself and want left alone -
    a bedroom air conditioner, say. The director then never starts it and leaves
    it as it stands. Only when it runs a duty the circuit cannot allow is it
    switched off, since otherwise it would block a room with more claim.
    """

    min_cycle_time: timedelta | None = None
    """Own rest before this appliance may restart, when it sits on no circuit.

    Een bron op een circuit houdt de rusttijd van dat circuit; deze rem is een
    ondergrens per apparaat en geldt alleen voor een bron zonder circuit. Leeg
    of nul betekent: geen eigen rem.

    A source on a circuit keeps that circuit's rest; this brake is a
    per-appliance lower bound and only applies to a source without a circuit.
    Empty or zero means: no own brake.
    """

    covers_zones: tuple[str, ...] = ()
    """The zones this appliance heats or cools along with it the moment it runs.

    Anker 12. Leeg betekent *alleen de eigen zone*: het gedrag van vóór deze
    instelling, dus een gezoneerde installatie merkt er niets van. Hetzelfde
    apparaat staat vaak als aparte bron onder meerdere kamers; de gebieden
    worden daarom samengevoegd op `entity_id`, dus één keer invullen is genoeg.
    Dit is dezelfde vorm als `Generator.zone_ids`, met één bewust verschil: leeg
    is hier *niets* en daar *alles*, want een terugval die standaard aanstaat is
    geen terugval maar een verrassing.

    Anchor 12. Empty means *this zone only*: the behaviour from before this
    setting, so a zoned installation notices nothing. The same appliance often
    sits as a separate source under several rooms; the areas are therefore
    merged on `entity_id`, so filling it in once is enough. This is the same
    shape as `Generator.zone_ids`, with one deliberate difference: empty means
    *nothing* here and *everything* there, because a fallback that is on by
    default is no fallback but a surprise.
    """

    takeover_delay: timedelta = timedelta(minutes=5)
    """How long a source in this appliance's area must be unreachable first.

    Anker 12. De overname wacht vanaf het moment dat het apparaat onbereikbaar
    werd, zodat een klapperende integratie de brander niet elke paar minuten
    ontsteekt. Is dat moment onbekend, dan is er niets om op te wachten en gaat
    de overname meteen in. Nul is meteen.

    Anchor 12. The takeover waits from the moment the appliance became
    unreachable, so a flapping integration does not fire the burner every few
    minutes. If that moment is unknown there is nothing to wait for and the
    takeover starts at once. Zero is at once.
    """

    def supports(self, family: ModeFamily) -> bool:
        """Return whether this source can deliver `family`."""
        if family is ModeFamily.HEAT:
            return self.role in (SourceRole.HEAT_ONLY, SourceRole.HEAT_COOL)
        if family is ModeFamily.COOL:
            return self.role in (SourceRole.COOL_ONLY, SourceRole.HEAT_COOL)
        return False


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

    simultaneous_heat_cool: bool = False
    """`False` for an ordinary multi-split: one duty at a time across all units.

    `True` for a single split (its own outdoor unit) and for three-pipe VRF
    with heat recovery, which genuinely does both at once. Deliberately a flag
    rather than something derived from a unit count, so heat-recovery systems
    are not crippled by a blanket rule.

    De standaard is `False`, de veilige kant: een circuit dat beide kanten op
    mag terwijl de buitenunit dat niet aankan, is precies de toestand die dit
    ontwerp onbereikbaar hoort te maken.

    The default is `False`, the safe side: a circuit allowed to do both while
    the outdoor unit cannot is exactly the state this design is meant to make
    unreachable.
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
    be able to keep a unit running. The rest is measured from the entity's
    `last_changed`; right after a Home Assistant restart that reads the restart
    moment, so the protection is then on the safe side.

    Alleen starts worden uitgesteld, nooit stops - kortcyclusbeveiliging mag een
    unit nooit aan het draaien kunnen houden. De rust wordt gemeten vanaf
    `last_changed` van de entiteit; vlak na een herstart van Home Assistant is
    dat het moment van de herstart, dus dan is de beveiliging aan de veilige
    kant.
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
class Opening:
    """A door or window that suspends climate control while it stands open."""

    entity_id: str
    zone_ids: tuple[str, ...] = ()
    """Zones this opening suspends. Empty means the whole installation."""

    open_state: str = "on"
    """The entity state that counts as open; covers report `open` instead.

    Standaard `on`, precies zoals de oude automatiseringen een raamcontact
    lazen. Wie een `cover` als opening opgeeft - een dakraam bijvoorbeeld -
    zet dit op `open`, want die rapporteert nooit `on`.

    Defaults to `on`, exactly how the old automations read a window contact.
    Whoever points an opening at a `cover` - a skylight, say - sets this to
    `open`, since that never reports `on`.
    """

    delay: timedelta = timedelta(0)
    """How long it must stand open before anything is suspended.

    Zero suspends the moment it opens. Deliberately the default: a delay is
    a choice about a particular door, and inventing half a minute for one
    that was never given a value hides that choice.
    """

    opening_id: str = ""
    """A stable identity of its own, so the bypass switch outlives its sensor.

    Anker 8: een opening draagt een eigen `opening_id` en een naam, net als elk
    ander objecttype. Zonder eigen identiteit hangt de overbruggingsschakelaar
    aan de `entity_id` van de sensor en verdwijnt hij zodra die sensor vervangen
    wordt. Leeg betekent: nog geen identiteit (oude opslag); `serialise.py`
    vult dat aan met de `entity_id` zodat opslaan van de configuratie hem
    vastlegt.

    Anchor 8: an opening carries its own `opening_id` and a name, like every
    other object type. Without an identity of its own the bypass switch hangs
    on the sensor's `entity_id` and vanishes the moment that sensor is
    replaced. Empty means: no identity yet (old storage); `serialise.py` fills
    that in with the `entity_id` so saving the configuration pins it down.
    """

    name: str = ""
    """What the user calls this opening; empty falls back on the `entity_id`."""

    def affects(self, zone_id: str) -> bool:
        """Return whether this opening suspends `zone_id`."""
        return not self.zone_ids or zone_id in self.zone_ids


class HeatingLayout(StrEnum):
    """How the heating is laid out through the house.

    Dit verandert niets aan wie er mag draaien - dat blijft aan de poorten en de
    voorrang. Het legt vast wat de installatie *is*, zodat de controle kan
    waarschuwen als de invulling er niet bij past. Een gedeelde thermostaat
    onder vijf zones terwijl je "per zone" koos is bijna altijd een vergissing,
    en zonder deze keuze is dat niet van een bewuste opzet te onderscheiden.

    This changes nothing about who may run - that stays with the gates and the
    priorities. It records what the installation *is*, so the check can warn
    when the configuration does not match. A shared thermostat under five zones
    while you picked "per zone" is nearly always a mistake, and without this
    choice there is no telling that apart from a deliberate setup.
    """

    CENTRAL = "central"
    """One heat source for the whole house: a closed system that cannot heat one
    room without heating the rest."""

    PER_ZONE = "per_zone"
    """Every room settles its own heat, through valves or its own appliance."""
