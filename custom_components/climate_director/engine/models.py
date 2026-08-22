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
#: Hoeveel ruimte de stiltevensters minstens moeten laten voordat een dag als
#: dichtgetimmerd geldt. Een gat van één minuut is geen ruimte maar toeval.
#:
#: How much room the quiet windows must leave at least before a day counts as
#: boarded up. A gap of one minute is not room but coincidence.
QUIET_ROOM_MINUTES = 15

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


class ZoneGate(StrEnum):
    """What decides whether a zone may run at all.

    Niet elke ruimte hoort aan hetzelfde touwtje. Een woonkamer volgt het ritme
    van het huishouden, een zolderkamer volgt of er iemand zit. Dat verschil is
    een eigenschap van de ruimte, geen uitzondering in de logica.

    Not every room hangs on the same string. A living room follows the rhythm of
    the household, an attic room follows whether somebody is sitting in it. That
    difference is a property of the room, not an exception in the logic.
    """

    HOUSEHOLD = "household"
    """The household gates decide: somebody home, awake, inside the schedule.

    A presence sensor on the zone still narrows this further: being home says
    nothing about whether anybody is in the attic.
    """

    PRESENCE = "presence"
    """The room's own presence sensor decides, on its own.

    Somebody sitting in the room is a better answer than any schedule could
    give, so the household gates step aside entirely. The master switch, a
    manual override and an open window still apply: those are not about people.
    """


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

    gate: ZoneGate = ZoneGate.HOUSEHOLD
    """What decides whether this zone may run: the household, or the room.

    `PRESENCE` lets an occupied room overrule the schedule, which is what a room
    somebody only uses now and then needs. It requires a `presence_entity`:
    without one there is nothing left to decide with.
    """

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

    ignore_precipitation: bool = False
    """Whether this zone keeps its outdoor window even during precipitation.

    Een zolder zonder ramen heeft niets aan de "zet een raam open"-regel, dus
    daar mag neerslag de buitengrens niet opzij zetten.

    An attic without windows gains nothing from the "open a window" rule, so
    there precipitation must not set the outdoor bound aside.
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
    sleep_window: TimeWindow | None = None
    """Hours in which this resident's sleep sensor counts. `None` means always.

    Een telefoon die om drie uur 's middags op de lader ligt betekent niet dat
    er iemand naar bed gaat. Zonder venster telt elke lading als slapen, en dan
    zet het huis zichzelf midden op de dag uit. De dagen van de week tellen mee,
    zodat een weekendritme apart te zetten is.

    A phone on the charger at three in the afternoon does not mean somebody is
    turning in. Without a window every charge counts as sleeping, and the house
    switches itself off in the middle of the day. Weekdays are honoured, so a
    weekend rhythm can be set apart.
    """

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

    def _applies_on(self, window: TimeWindow, weekday: int) -> bool:
        """Return whether that window could be open at all on that weekday."""
        if window.weekdays is None or weekday in window.weekdays:
            return True
        # Een venster over middernacht loopt door in de volgende dag, dus dan
        # telt gisteren ook mee.
        #
        # A window crossing midnight runs on into the next day, so yesterday
        # counts as well.
        crosses_midnight = window.end <= window.start
        return crosses_midnight and (weekday - 1) % 7 in window.weekdays

    def windows_for(self, *, holiday: bool, weekday: int | None = None) -> tuple[TimeWindow, ...]:
        """Return the windows that apply today.

        On a holiday the resident's holiday windows take over if they set any.
        Without them a holiday counts as a Saturday, which is what a household
        means by one: the day the alarm stays off.
        """
        if holiday:
            special = tuple(window for window in self.windows if window.holiday)
            if special:
                return special
        ordinary = tuple(window for window in self.windows if not window.holiday)
        if weekday is None:
            return ordinary
        return tuple(window for window in ordinary if self._applies_on(window, weekday))

    def takes_part(self, *, holiday: bool, weekday: int | None = None) -> bool:
        """Return whether this resident has anything to say about today.

        Alleen wie vandaag een venster heeft doet vandaag mee. Wie er geen heeft
        opent de poort niet en houdt hem ook niet tegen - net als wie helemaal
        geen rooster invulde. Anders zou een bewoner met alleen weekendvensters
        het huis elke doordeweekse ochtend tegenhouden tot hij wakker wordt, en
        dat is geen rooster maar een slot.

        Only somebody with a window today takes part today. Whoever has none
        neither opens the gate nor holds it shut - just like somebody who filled
        in no schedule at all. Otherwise a resident with weekend windows only
        would hold the house back every weekday morning until they woke up,
        which is not a schedule but a lock.
        """
        return bool(self.windows_for(holiday=holiday, weekday=weekday))

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

    quiet_windows: tuple[TimeWindow, ...] = ()
    """Hours in which the director may not start anything of its own accord.

    Thuiskomen om elf uur 's avonds terwijl je zo naar bed gaat, hoeft het huis
    niet te laten opstoken. Binnen deze vensters begint de director dus niets
    uit zichzelf. Wat al draait blijft gewoon geregeld, en zet je zelf iets aan,
    dan pakt hij dat op en regelt door - het is een rem op beginnen, niet op
    doorgaan. Leeg laten zet de rem uit.

    Coming home at eleven at night when you are about to turn in need not fire
    the boiler. Inside these windows the director therefore starts nothing of its
    own accord. Whatever already runs stays regulated, and if you switch
    something on yourself it is picked up and carried on - this is a brake on
    starting, not on continuing. Leaving it empty releases the brake.
    """

    precondition_window: TimeWindow | None = field(
        default_factory=lambda: TimeWindow(time(6, 0), time(23, 0))
    )
    """Hours in which a pre-conditioning request may run. `None` means all day.

    Vooruit verwarmen is het enige dat een leeg huis mag laten draaien, en dus
    het enige dat 's nachts echt geld kan kosten. Standaard 06:00 tot 23:00, en
    daarbuiten telt een verzoek eenvoudig niet mee.

    Pre-conditioning is the only thing allowed to run an empty house, and so the
    only thing that can really cost money overnight. 06:00 to 23:00 by default,
    and outside it a request simply does not count.
    """

    max_precondition: timedelta = timedelta(hours=2)
    """Longest a single request may last, however long somebody asks for.

    A request cannot be forgotten, only mistyped - so the ceiling is what keeps
    a slip of the thumb from becoming an afternoon of heating an empty house.
    """

    guest_window: TimeWindow | None = None
    """Hours in which guest mode carries the house. `None` means all day.

    Guest mode stands in for people the integration cannot see, and people are
    only unaccounted for while they are up. Outside these hours the ordinary
    gates take over again.
    """


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
class PrecipitationSettings:
    """Which source counts as precipitation, and how long it keeps counting.

    De buitengrens per zone is een zuinigheidsregel die ervan uitgaat dat je
    bij mooi weer beter een raam openzet dan de airco aan. Valt er neerslag,
    dan gaat die aanname niet op — en zolang een neerslagbron neerslag meldt,
    slaat de engine de buitengrens per zone over, precies zoals een
    vooruit-verzoek dat al doet.

    The per-zone outdoor bound is a thrift rule that assumes you are better off
    opening a window than switching the air conditioner on in nice weather.
    When precipitation falls that assumption does not hold — and as long as a
    precipitation source reports precipitation, the engine skips the per-zone
    outdoor bound, exactly as a pre-conditioning request already does.
    """

    source: str = ""
    """Entity carrying the reading. Empty switches the whole feature off."""

    states: frozenset[str] = frozenset({"rainy", "pouring", "snowy", "hail", "lightning-rainy"})
    """States of that entity that count as precipitation.

    Voor een `weather`-entiteit zijn dit zijn condities; voor een sensor zijn
    het zijn standen.

    For a `weather` entity these are its conditions; for a sensor its states.
    """

    grace: timedelta = timedelta(minutes=15)
    """How long a reading keeps counting after it stops.

    Een bui van vijf minuten hoort de regeling niet te laten stuiteren.

    A five-minute shower should not make the regulation bounce.
    """

    @property
    def enabled(self) -> bool:
        """Return whether a source is configured at all."""
        return bool(self.source)


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
    precipitation: PrecipitationSettings = field(default_factory=PrecipitationSettings)

    heating_layout: HeatingLayout = HeatingLayout.PER_ZONE
    """What kind of heating installation this is; see `HeatingLayout`."""

    outdoor_sensor: str = ""
    """Entity carrying the outdoor temperature. Empty leaves it unknown."""

    outdoor_hysteresis: float = 0.5
    """Dead band on every outdoor bound, in degrees.

    Binnen heeft elke zone een dode band, want anders pendelt hij op één getal.
    Buiten was elke grens hard - de grens die de gasketel van de warmtepomp
    scheidt, en de grens die zegt of dit weer verwarmen of koelen toelaat - en
    juist daar schommelt het weer omheen. Een gesimuleerde maand rond de omslag
    van 3,1 graden leverde 296 wisselingen tussen gas en airco op: ruim acht per
    dag, elk een brander die ontsteekt of een compressor die start. De
    kortcyclusbescherming ving daar niets van, want die hangt aan een circuit en
    een gasketel hangt aan geen circuit.

    De band geldt alleen voor wat al draait: die mag doorlopen tot een dode band
    voorbij zijn grens. Wie stilstaat moet de grens gewoon halen, anders zou de
    band de grens alleen maar verschuiven. Nul zet hem uit.

    Indoors every zone has a dead band, since otherwise it chatters on a single
    number. Outdoors every bound was hard - the one separating the boiler from
    the heat pump, and the one saying whether this weather allows heating or
    cooling - and that is exactly what the weather hovers around. A simulated
    month around the 3.1 degree changeover produced 296 swaps between boiler and
    heat pump: over eight a day, each one a burner igniting or a compressor
    starting. Short-cycle protection caught none of it, since that hangs on a
    circuit and a gas boiler hangs on no circuit.

    The band applies only to what already runs: that may carry on until one dead
    band past its bound. Whatever stands still has to reach the bound itself, or
    the band would merely move the bound. Zero switches it off.
    """

    stuck_after: timedelta = timedelta(minutes=15)
    """How long a zone may sit on a waiting reason before it counts as stuck.

    Ruim boven elke pauze die je redelijkerwijs instelt, want een valse melding
    leert je de melder te negeren. Nul zet de melder uit.

    Comfortably above any pause you would reasonably configure, since a false
    alarm teaches you to ignore the alarm. Zero switches it off.
    """

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


class Problem(str):
    """One configuration complaint, readable as text and identifiable by code.

    Een `str`-subklasse met opzet: alles wat er al mee werkte - de diagnose, het
    logboek, de tests - blijft werken alsof er niets veranderd is. De code komt
    er alleen bij, zodat de Home Assistant-laag er een vertaling bij kan zoeken.
    De Engelse tekst blijft de terugval, dus een melding zonder vertaling is
    nooit erger dan hij was.

    A `str` subclass on purpose: everything already working with these - the
    diagnostics, the log, the tests - keeps working as though nothing changed.
    The code is merely added, so the Home Assistant layer can look up a
    translation for it. The English text stays the fallback, so a complaint
    without a translation is never worse off than it was.
    """

    code: str
    params: dict[str, str]

    def __new__(cls, code: str, text: str, **params: object) -> Problem:
        """Return the complaint, carrying its code and placeholders."""
        item = super().__new__(cls, text)
        item.code = code
        item.params = {key: str(value) for key, value in params.items()}
        return item


def manual_only_problems(config: DirectorConfig) -> tuple[Problem, ...]:
    """Return the duties that only hand-operated sources can deliver.

    Een zone waarvan een gewenste taak (verwarmen of koelen) alleen door bronnen
    met automatisch starten uit geleverd kan worden, start die taak nooit uit
    zichzelf. Dat mag de bedoeling zijn - een handbediende slaapkamerairco is
    een prima keuze - maar van buiten is het niet te onderscheiden van een per
    ongeluk uitgezette autostart. Daarom is dit bewust géén `validate()`-fout:
    het is een eenmalige melding die de gebruiker kan afvinken, geen blijvend
    probleem op de controlelijst.

    A zone whose wanted duty (heating or cooling) can only be delivered by
    sources with automatic start off never starts that duty of its own accord.
    That may well be the point - a hand-operated bedroom airco is a fine choice
    - but from the outside it is indistinguishable from an autostart switched
    off by accident. Hence this is deliberately no `validate()` error: it is a
    one-time notice the user can tick off, not a permanent entry on the problem
    list.
    """
    found: list[Problem] = []
    for zone in config.zones:
        for family in (ModeFamily.HEAT, ModeFamily.COOL):
            if zone.settings_for(family) is None:
                continue
            if not any(source.supports(family) for source in zone.sources):
                continue  # that is a real configuration problem, not this notice
            if not any(source.supports(family) and source.autostart for source in zone.sources):
                found.append(
                    Problem(
                        "zone_only_manual_sources",
                        f"zone {zone.zone_id} wants {family.value} but every source "
                        "able to deliver it has automatic start off",
                        zone=zone.name or zone.zone_id,
                        zone_id=zone.zone_id,
                        mode=family.value,
                    )
                )
    return tuple(found)


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

    # Hetzelfde apparaat twee keer in EEN kamer is onzin: welke van de twee
    # bronnen wint, is dan willekeurig, en er valt niets te kiezen. Over
    # meerdere kamers heen is het juist normaal - dat is precies hoe een
    # centrale verwarming eruitziet, en hoe een gedeelde ketel als reserve
    # onder elke zone komt te staan. Dat mocht hier ooit niet, omdat zo'n
    # apparaat dan twee tegengestelde opdrachten kon krijgen; sinds die
    # opdrachten samenvallen tot een per apparaat is dat bezwaar weg.
    #
    # The same appliance twice in ONE room is nonsense: which of the two
    # sources wins is then arbitrary, and there is nothing to choose between.
    # Across rooms it is ordinary - that is exactly what central heating looks
    # like, and how a shared boiler ends up under every zone as a stand-in.
    # This used to be forbidden here because such an appliance could then get
    # two opposing commands; since those collapse into one per appliance, that
    # objection is gone.
    for zone in config.zones:
        for entity_id in _duplicates([source.entity_id for source in zone.sources]):
            problems.append(
                Problem(
                    "entity_twice_in_one_zone",
                    f"zone {zone.zone_id} uses {entity_id} for more than one source",
                    zone=zone.name or zone.zone_id,
                    entity=entity_id,
                )
            )

    # Een unit die wel aan een buitenunit hangt maar in geen enkele zone staat,
    # is voor de director onbeheerd. Draait hij, dan zet hij het hele circuit op
    # zijn taak en kan geen kamer er meer iets anders vragen - en omdat hij van
    # niemand is, zet de director hem ook nooit uit. Van buiten is dat niet te
    # onderscheiden van "de director doet niets", dus het hoort gemeld te worden
    # vóór iemand zich erop verkijkt.
    #
    # A unit that hangs on an outdoor unit but appears in no zone is unmanaged
    # as far as the director is concerned. If it runs it holds the whole circuit
    # to its duty and no room can ask for anything else - and since it belongs
    # to nobody, the director never switches it off either. From the outside
    # that is indistinguishable from "the director does nothing", so it should
    # be reported before somebody is caught out by it.
    in_a_zone = {source.entity_id for _zone, source in config.sources()}
    problems += [
        Problem(
            "unit_in_no_zone",
            f"unit {unit} is on circuit {circuit.circuit_id} but in no zone, so it can "
            f"lock that circuit without the director being able to stand it down",
            unit=unit,
            circuit=circuit.circuit_id,
        )
        for circuit in config.circuits
        for unit in circuit.units
        if unit not in in_a_zone
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
            problems.append(
                Problem(
                    "zone_without_sources",
                    f"zone {zone.zone_id} has no sources",
                    zone=zone.zone_id,
                )
            )
        if not zone.indoor_sensor:
            problems.append(
                Problem(
                    "zone_without_sensor",
                    f"zone {zone.zone_id} has no indoor temperature sensor",
                    zone=zone.zone_id,
                )
            )
        if zone.heat is None and zone.cool is None:
            problems.append(f"zone {zone.zone_id} may neither heat nor cool")
        if zone.gate is ZoneGate.PRESENCE and not zone.presence_entity:
            problems.append(
                Problem(
                    "zone_presence_without_sensor",
                    f"zone {zone.zone_id} runs on room presence but has no presence entity, "
                    f"so it can never run",
                    zone=zone.zone_id,
                )
            )
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

            # De streeftemperatuur is wat het apparaat te horen krijgt; het
            # aanpunt is waar de zone besluit te beginnen. Ligt het streven aan
            # de verkeerde kant daarvan, dan start de zone keurig en zet hij
            # het apparaat vervolgens op een temperatuur waar het niets voor
            # hoeft te doen. Van buiten lijkt dat op een apparaat dat weigert.
            #
            # The target is what the appliance is told; the switch-on point is
            # where the zone decides to begin. If the target sits on the wrong
            # side of it, the zone starts dutifully and then sets the appliance
            # to a temperature it need do nothing for. From the outside that
            # looks like an appliance refusing.
            askew = (
                settings.target < settings.start_at
                if family is ModeFamily.HEAT
                else settings.target > settings.start_at
            )
            if askew:
                problems.append(
                    Problem(
                        "target_outside_band",
                        f"zone {zone.zone_id} starts {family.value} at {settings.start_at} "
                        f"but aims for {settings.target}",
                        zone=zone.name or zone.zone_id,
                        mode=family.value,
                        start=f"{settings.start_at:g}",
                        target=f"{settings.target:g}",
                    )
                )

    source_entities = {source.entity_id for _, source in config.sources()}
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
                    Problem(
                        "shared_priority",
                        f"zones {seen[zone.priority]} and {zone.zone_id} share priority "
                        f"{zone.priority} on circuit {circuit.circuit_id}",
                        first=seen[zone.priority],
                        second=zone.zone_id,
                        priority=zone.priority,
                        circuit=circuit.circuit_id,
                    )
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

    if config.stuck_after.total_seconds() < 0:
        problems.append("the stuck-detection time is negative")

    if config.outdoor_hysteresis < 0:
        problems.append("the outdoor dead band is negative")

    if config.gates.max_precondition.total_seconds() <= 0:
        problems.append(
            "the maximum pre-conditioning time is zero or negative, so no request can ever run"
        )

    if config.holiday_calendars and not config.holiday_keyword.strip():
        problems.append(
            Problem(
                "calendars_without_keyword",
                "holiday calendars are set but no keyword is, so no event can ever "
                "switch holiday mode on",
            )
        )

    problems += [
        Problem(
            "resident_without_presence",
            f"resident {resident.resident_id} has no presence entity, so can never be home",
            resident=resident.resident_id,
        )
        for resident in config.residents
        if not resident.presence_entity
    ]

    known_sources = set(source_ids)
    problems += _overlapping_bounds(config)

    for group in config.exclusive_groups:
        problems += [
            f"exclusive group names unknown source {source_id}"
            for source_id in sorted(group - known_sources)
        ]

    problems += _layout_problems(config)
    problems += _quiet_problems(config)
    problems += _timing_problems(config)

    return tuple(problems)


def _quiet_problems(config: DirectorConfig) -> list[Problem]:
    """Return a complaint when the quiet windows leave no room to start.

    Een stiltevenster is de omgekeerde van een rooster: het zegt wanneer er
    níets mag beginnen. Wie dat verkeerd om leest en er vensters in zet die
    samen de klok rondgaan, krijgt een huis dat uit zichzelf nooit meer iets
    doet - en dat ziet er van buiten precies zo uit als een integratie die stuk
    is.

    Er is één ontsnapping: een bewoner die thuis is met een open roostervenster
    verslaat de stilte. Heeft niemand een rooster, dan is die ontsnapping er
    niet.

    Een kwartier is de grens. Niet nul: een gat van één minuut per dag is geen
    ruimte maar toeval, en dan begint er alleen iets als de klok precies goed
    valt.

    A quiet window is the inverse of a schedule: it says when nothing may start.
    Read that the wrong way round and put in windows that together go round the
    clock, and you get a house that never does anything of its own accord again
    - which looks, from the outside, exactly like a broken integration.

    There is one escape: a resident who is home with an open schedule window
    beats the quiet. If nobody has a schedule, that escape does not exist.

    A quarter of an hour is the line. Not zero: a gap of one minute a day is not
    room but coincidence, and then something only starts if the clock happens to
    fall right.
    """
    windows = [window for window in config.gates.quiet_windows if not window.holiday]
    if not windows:
        return []
    if any(resident.windows for resident in config.residents):
        return []

    silent = [day for day in range(7) if _free_minutes(windows, day) < QUIET_ROOM_MINUTES]
    if not silent:
        return []

    return [
        Problem(
            "quiet_covers_the_day",
            f"the quiet windows leave under {QUIET_ROOM_MINUTES} minutes on {len(silent)} day(s) "
            "and nobody has a schedule to beat them, so nothing can start on those days",
            days=str(len(silent)),
            minutes=str(QUIET_ROOM_MINUTES),
        )
    ]


def _free_minutes(windows: list[TimeWindow], weekday: int) -> int:
    """Return how many minutes of that day no quiet window covers.

    Geteld zoals `TimeWindow.contains` het leest: het beginpunt telt mee, het
    eindpunt niet. Zou dit ruimer tellen, dan zou een venster dat om 12:00
    eindigt en een venster dat om 12:00 begint samen als sluitend gelden
    terwijl er in werkelijkheid een minuut tussen zit.

    Counted the way `TimeWindow.contains` reads it: the start counts, the end
    does not. Counting this more loosely would let a window ending at 12:00 and
    one starting at 12:00 pass as watertight while a minute really sits between
    them.
    """
    covered = [False] * (24 * 60)
    for window in windows:
        start = window.start.hour * 60 + window.start.minute
        end = window.end.hour * 60 + window.end.minute

        # Een venster over middernacht hangt aan zijn startdag. Op déze dag telt
        # zowel het stuk na de start als het stuk dat gisteren begon.
        #
        # A window through midnight hangs off its starting day. On *this* day
        # both the piece after the start and the piece begun yesterday count.
        if start < end:
            spans = [(start, end, weekday)]
        elif start == end:
            spans = []
        else:
            spans = [(start, 24 * 60, weekday), (0, end, (weekday - 1) % 7)]

        for first, last, owning_day in spans:
            if window.weekdays is not None and owning_day not in window.weekdays:
                continue
            for minute in range(first, last):
                covered[minute] = True

    return covered.count(False)


def _timing_problems(config: DirectorConfig) -> list[Problem]:
    """Return a complaint about switch timings on a circuit that never switches.

    Een buitenunit die verwarmen en koelen tegelijk aankan wisselt nooit van
    taak, dus een omschakelpauze en een minimale looptijd voor die wissel doen
    daar niets. Ze staan er dan wel, en dan ga je ervan uit dat ze werken.

    De kortcyclustijd en de capaciteitsgrens blijven wél gelden; die gaan over
    losse units en niet over de taak van het circuit.

    An outdoor unit that can heat and cool at once never switches duty, so a
    switch pause and a minimum run before that switch do nothing there. They
    still sit in the settings, and then you assume they work.

    The short-cycle time and the capacity limit do still apply; those are about
    individual units rather than about the circuit's duty.
    """
    return [
        Problem(
            "switch_timings_without_a_switch",
            f"circuit {circuit.circuit_id} can run both duties at once, so its switch pause "
            "and minimum run before switching never apply",
            circuit=circuit.name or circuit.circuit_id,
        )
        for circuit in config.circuits
        if circuit.simultaneous_heat_cool
        and (circuit.family_switch_delay or circuit.min_family_switch_interval)
    ]


def _layout_problems(config: DirectorConfig) -> list[str]:
    """Return the complaints about a heating layout that does not match the wiring.

    Waarschuwingen, geen blokkade. De director regelt gewoon door; dit zegt
    alleen dat de installatie er anders uitziet dan wat je koos, en dat is bijna
    altijd een vergissing die je pas merkt als het huis op de verkeerde plek
    warm wordt.

    Warnings, not a block. The director carries on regulating; this only says
    the installation looks different from what you picked, which is nearly
    always a mistake you notice when the wrong part of the house gets warm.
    """
    if len(config.zones) < 2:
        return []

    def heats(source: Source) -> bool:
        return bool(source.entity_id) and source.supports(ModeFamily.HEAT)

    # Welke zones leunen op welk verwarmingsapparaat.
    # Which zones lean on which heating appliance.
    shared: dict[str, list[str]] = {}
    for zone in config.zones:
        for entity_id in {source.entity_id for source in zone.sources if heats(source)}:
            shared.setdefault(entity_id, []).append(zone.zone_id)
    spanning = {entity_id: zones for entity_id, zones in shared.items() if len(zones) > 1}

    if config.heating_layout is HeatingLayout.PER_ZONE:
        # Een gedeeld apparaat is op zichzelf geen bewijs van een gesloten
        # systeem. Een gezoneerde cv werkt juist met EEN ketel en kleppen per
        # zone, en een kamer met een eigen airco plus de gasverwarming als
        # reserve is ook gewoon gezoneerd - die kan zichzelf verwarmen.
        #
        # Het gaat mis wanneer kamers uitsluitend op hetzelfde apparaat
        # aangewezen zijn: dan is er niets meer om per kamer te regelen, en
        # verwarmt aanzetten voor de een de ander mee.
        #
        # A shared appliance is no proof of a closed system by itself. A zoned
        # boiler system works precisely with ONE boiler and valves per zone, and
        # a room with its own air conditioner plus the gas heating as a stand-in
        # is zoned too - it can heat itself.
        #
        # It goes wrong when rooms depend on the same appliance and nothing
        # else: then there is nothing left to settle per room, and switching it
        # on for one warms the other along with it.
        for entity_id, zone_ids in sorted(spanning.items()):
            stranded = sorted(
                zone_id
                for zone_id in zone_ids
                if (zone := config.zone(zone_id)) is not None
                and not [
                    source
                    for source in zone.sources
                    if heats(source) and source.entity_id != entity_id
                ]
            )
            if len(stranded) > 1:
                return [
                    Problem(
                        "layout_zoned_with_shared_source",
                        (
                            f"heating is set to per zone, but {entity_id} is the only "
                            f"heat source of {len(stranded)} zones"
                        ),
                        entity=entity_id,
                        count=str(len(stranded)),
                        zones=", ".join(stranded),
                    )
                ]
        return []

    if config.heating_layout is HeatingLayout.CENTRAL and not spanning:
        return [
            Problem(
                "layout_central_without_shared_source",
                "heating is set to central, but no heat source is shared between zones",
                count=str(len(config.zones)),
            )
        ]

    return []


def _duplicates(values: list[str]) -> list[str]:
    """Return the values occurring more than once, in first-seen order."""
    seen: set[str] = set()
    duplicated: list[str] = []
    for value in values:
        if value in seen and value not in duplicated:
            duplicated.append(value)
        seen.add(value)
    return duplicated


def _overlapping_bounds(config: DirectorConfig) -> list[str]:
    """Return the pairs in one exclusive group whose outdoor ranges overlap.

    Bronnen in een exclusieve groep horen elkaar uit te sluiten. Doen hun
    buitengrenzen dat al, dan komen ze elkaar nooit tegen en hoeft er nooit
    iemand te wijken. Overlappen ze, dan kan er bij een bepaalde temperatuur
    alsnog gekozen moeten worden - en dat is precies het moment waarop iemand
    dacht dat het onmogelijk was. Eén verkeerd getal is genoeg.

    Sources in an exclusive group are meant to rule each other out. If their
    outdoor bounds already do so, they never meet and nobody ever has to give
    way. If the bounds overlap, at some temperature a choice still has to be
    made - which is exactly the moment somebody thought was impossible. One
    wrong number is enough.
    """
    found: list[str] = []
    for group in config.exclusive_groups:
        members = [source for source in (config.source(item) for item in sorted(group)) if source]
        for index, first in enumerate(members):
            for second in members[index + 1 :]:
                overlap = _windows_overlap(first.outdoor, second.outdoor)
                if overlap is not None:
                    found.append(
                        Problem(
                            "exclusive_overlap",
                            f"sources {first.source_id} and {second.source_id} are "
                            f"exclusive but both apply {overlap}, so at that outdoor "
                            f"temperature one has to give way instead of never meeting",
                            first=first.source_id,
                            second=second.source_id,
                            overlap=overlap,
                        )
                    )
    return found


def _windows_overlap(first: OutdoorWindow, second: OutdoorWindow) -> str | None:
    """Return a readable description of where two outdoor ranges meet, or `None`."""
    low = max(
        (bound for bound in (first.minimum, second.minimum) if bound is not None),
        default=None,
    )
    high = min(
        (bound for bound in (first.maximum, second.maximum) if bound is not None),
        default=None,
    )
    if low is not None and high is not None and low >= high:
        return None
    if low is None and high is None:
        return "at every outdoor temperature"
    if low is None:
        return f"below {high}"
    if high is None:
        return f"from {low} upwards"
    return f"between {low} and {high}"
