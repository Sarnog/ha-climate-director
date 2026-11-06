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
from datetime import datetime, time, timedelta
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

    def started_at(
        self, moment: datetime, *, weekday: int | None = None, any_day: bool = False
    ) -> datetime | None:
        """Return when this window's current occurrence began, or `None` outside it.

        De **lopende** voorkomst, niet de vorige of de volgende. Een venster dat
        over middernacht loopt begint op zijn **startdag**: om 02:00 op woensdag
        begon een venster van 21:00 tot 09:00 op dinsdag om 21:00. Voor een
        vakantievenster (`any_day=True`) geldt hetzelfde met de dag waarop het
        venster begon, en de weekdagen doen dan niet mee - precies zoals bij
        `contains`.

        `weekday` is de dag waarvoor het venster gelezen moet worden, en valt
        standaard terug op de weekdag van `moment`. De aanroeper vult hem in als
        deze aanvraag als een andere dag telt: op een vakantie zonder eigen
        vakantievenster leest een gewoon venster als zaterdag, en dan hoort de
        begintijd ook vanaf díe dag gerekend te worden. Zonder die parameter zou
        het venster op zaterdag openstaan en de begintijd toch van de echte
        weekdag komen - dezelfde klasse als twee lezers van dezelfde entiteit die
        het oneens zijn.

        Valt `moment` niet in het venster, dan is er geen lopende voorkomst en is
        het antwoord `None`. Dat is geen fout maar het gewone geval buiten de
        stille uren: de aanroeper vraagt het alleen voor een venster dat open
        hoort te staan.

        The **current** occurrence, not the previous or the next one. A window
        crossing midnight begins on its **start day**: at 02:00 on Wednesday a
        window from 21:00 to 09:00 began on Tuesday at 21:00. For a holiday window
        (`any_day=True`) the same holds with the day the window began, and the
        weekdays do not take part - exactly as in `contains`.

        `weekday` is the day the window is read for, defaulting to the weekday of
        `moment`. The caller fills it in when this request counts as a different
        day: on a holiday without a holiday window of its own an ordinary window
        reads as a Saturday, and then the beginning has to be counted from that
        day too. Without that parameter the window would stand open on a Saturday
        while its beginning still came from the real weekday - the same class as
        two readers of one entity disagreeing.

        When `moment` does not fall inside the window there is no current
        occurrence and the answer is `None`. That is not an error but the ordinary
        case outside the quiet hours: the caller only asks it for a window that
        should stand open.
        """
        day = moment.weekday() if weekday is None else weekday
        if not self.contains(moment.time(), day, any_day=any_day):
            return None
        if self.start <= self.end or moment.time() >= self.end:
            start_weekday = day
        else:
            start_weekday = (day - 1) % 7
        start_day = moment.date() - timedelta(days=(day - start_weekday) % 7)
        return datetime.combine(start_day, self.start, tzinfo=moment.tzinfo)


@dataclass(frozen=True, slots=True)
class SleepIn:
    """Tot hoe laat de slaapsensor 's ochtends nog iets betekent.

    Het slaapvenster is de nacht: daarbinnen betekent "telefoon op de lader"
    dat iemand in bed ligt, en daarbuiten is een lader gewoon een lader. Dat
    venster doet twee dingen tegelijk - het zet het huis om bedtijd uit én het
    bepaalt hoe lang je 's ochtends mag doorslapen - en die twee vragen om
    verschillende antwoorden. Trek je het venster door tot een uur of één, dan
    telt de lader ook op een gewone woensdag als slapen en blijft het huis uit
    terwijl er iemand thuis zit te werken. Knip je het venster op de dagen die
    ertoe doen, dan zet niets het huis 's nachts nog uit.

    Daarom staat het uitslapen hier apart: het slaapvenster blijft de nacht, en
    dit rekt alleen de ochtend op, op de dagen dat dat mag.

    The sleep window is the night: inside it "phone on the charger" means
    somebody is in bed, and outside it a charger is just a charger. That window
    does two jobs at once - switching the house off at bedtime and setting how
    long you may sleep in - and those two want different answers. Stretch the
    window to one in the afternoon and the charger counts as sleep on an
    ordinary Wednesday too, leaving the house off while somebody is working
    from home. Cut the window down to the days that matter and nothing switches
    the house off at night any more.

    So sleeping in lives here on its own: the sleep window stays the night, and
    this stretches only the morning, on the days that allow it.
    """

    until: time
    """The hour the sleep sensor stops counting on a morning that allows it."""

    weekdays: frozenset[int] | None = None
    """The **mornings** this applies to. `None` means every day.

    Bewust de ochtend en niet de avond ervoor. Een slaapvenster loopt over
    middernacht en hangt daarom aan de dag waarop het begint - wie zaterdag wil
    uitslapen, vinkt daar vrijdag aan. Dat is een val die niemand verwacht.
    Deze tijd hangt aan de ochtend zelf: uitslapen op zaterdag is zaterdag.

    Deliberately the morning and not the evening before. A sleep window runs
    past midnight and therefore hangs on the day it starts - whoever wants to
    sleep in on Saturday ticks Friday. That is a trap nobody expects. This time
    hangs on the morning itself: sleeping in on Saturday is Saturday.
    """

    holiday: bool = False
    """Whether this also applies on a holiday, whatever the weekday."""

    def applies_on(self, weekday: int, *, holiday: bool) -> bool:
        """Return whether sleeping in is allowed on that morning."""
        if holiday and self.holiday:
            return True
        return self.weekdays is None or weekday in self.weekdays


@dataclass(frozen=True, slots=True)
class WakeDeadline:
    """The hour from which one resident's sleep stops holding the house back.

    Een huis met twee slapers hoort niet te beginnen zodra de eerste opstaat:
    wie nog ligt, ligt er nog. Maar eindeloos wachten is net zo fout - dan
    houdt één uitslaper de rest van het huis de hele dag koud. Deze tijd is de
    uiterste: daarna telt de slaper niet meer mee, en gaat het huis mee met wie
    wél op is.

    Los van het rooster, met opzet. Een roostervenster zegt wanneer iemand
    klimaat wil en zet het aan het eind ook weer uit; deze tijd zegt alleen
    wanneer je niet langer op hem hoeft te wachten. Ze in één getal vangen zou
    de vroegste starttijd en de uiterste wachttijd aan elkaar knopen, en dat
    zijn twee verschillende dingen.

    A house with two sleepers should not start the moment the first one is up:
    whoever is still in bed is still in bed. But waiting forever is just as
    wrong - one late riser would then keep the rest of the house cold all day.
    This time is the outside limit: past it the sleeper no longer counts, and
    the house follows whoever is up.

    Deliberately apart from the schedule. A schedule window says when somebody
    wants climate control and switches it off again at its end; this time only
    says when you need no longer wait for them. Catching both in one number
    would tie the earliest start to the longest wait, and those are two
    different things.
    """

    at: time
    """The moment sleep stops counting. Before it a sleeper holds the house."""

    weekdays: frozenset[int] | None = None
    """`datetime.weekday()` numbers (Monday is 0). `None` means every day."""

    holiday: bool = False
    """Whether this deadline also applies on a holiday, whatever the weekday.

    Een vakantiedag telt bij de roosters als zaterdag, want een vrije dag lijkt
    op een zaterdag. Voor een uiterste opsta-tijd gaat die vergelijking niet
    op: een vakantie van de één is een gewone werkdag van de ander, en dan
    houdt de uitslaper het huis op terwijl er iemand zit te werken. De dagen
    betekenen hier dus wat er staat, en wie ook op een vakantiedag gewacht wil
    worden zegt dat hier met zoveel woorden.

    A holiday counts as a Saturday for the schedules, since a day off resembles
    a Saturday. For a wake deadline that comparison does not hold: one person's
    holiday is another's working day, and the late riser then holds the house up
    while somebody is working. So the days here mean what they say, and whoever
    wants to be waited for on a holiday too says so in as many words.
    """

    def applies_on(self, weekday: int) -> bool:
        """Return whether this deadline is set for that weekday."""
        return self.weekdays is None or weekday in self.weekdays


@dataclass(frozen=True, slots=True)
class RiseBrake:
    """Until when getting up does not set the house going, for one resident.

    Wie op een werkdag om kwart voor zes opstaat en om half zeven de deur uit gaat,
    hoeft het huis niet aan te zetten. Vóór deze tijd, op deze dagen, telt deze
    bewoner niet als "op" voor de wakker-poort. Nooit op een vakantiedag, en alleen
    een rem op beginnen: wat al draait, blijft draaien.

    Whoever gets up at a quarter to six on a working day and leaves at half past six
    need not set the house going. Before this time, on these days, this resident does
    not count as "up" for the wake gate. Never on a holiday, and only a brake on
    starting: whatever runs already keeps running.
    """

    at: time
    """From this time on, getting up starts the house again."""

    weekdays: frozenset[int] | None = None
    """`datetime.weekday()` numbers (Monday is 0). `None` means every day."""

    def applies_on(self, weekday: int) -> bool:
        """Return whether the brake is set for that weekday."""
        return self.weekdays is None or weekday in self.weekdays


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

    sleep_in: SleepIn | None = None
    """Until when the sleep sensor still counts on a morning that allows it.

    `None` betekent: geen uitslapen, dus het slaapvenster is het hele verhaal.
    `None` means: no sleeping in, so the sleep window is the whole story.
    """

    wake_deadline: WakeDeadline | None = None
    """Until when this resident's sleep holds the house back. `None` means never.

    Leeg laten houdt het gedrag zoals het was: wie slaapt houdt niemand tegen,
    en de eerste die opstaat zet het huis aan. Pas wie hier een tijd invult
    vraagt om wachten - en zegt er in dezelfde adem bij tot hoe laat.

    Leaving it empty keeps behaviour as it was: a sleeper holds nobody back, and
    the first one up sets the house going. Only whoever fills in a time here is
    asking to be waited for - and says in the same breath until when.
    """

    rise_brake: RiseBrake | None = None
    """Until when this resident getting up does not start the house. `None`: never."""

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

    def sleeps_in_at(self, moment: time, weekday: int, *, holiday: bool = False) -> bool:
        """Return whether this resident may still be asleep at that moment.

        Alleen de ochtend wordt opgerekt; de nacht doet het slaapvenster zelf.
        Only the morning is stretched; the night is the sleep window's own work.
        """
        sleep_in = self.sleep_in
        if sleep_in is None:
            return False
        if not sleep_in.applies_on(weekday, holiday=holiday):
            return False
        return moment < sleep_in.until

    def waits_until(self, weekday: int, *, holiday: bool = False) -> time | None:
        """Return the time this resident's sleep stops holding the house back.

        `None` betekent: deze bewoner houdt vandaag niemand tegen. Dat is de
        stand zonder instelling, en ook de stand op een dag die niet in de
        dagen van de uiterste tijd staat - wie alleen in het weekend uitslaapt,
        houdt het huis doordeweeks niet op.

        Een vakantiedag telt hier **niet** vanzelf als zaterdag - anders houdt
        de schoolvakantie van de één het huis op terwijl de ander gewoon thuis
        zit te werken. Wie ook op een vakantiedag gewacht wil worden, vinkt dat
        bij de uiterste tijd zelf aan.

        `None` means: this resident holds nobody back today. That is the state
        without the setting, and the state on a day outside the deadline's own
        days - whoever sleeps in at the weekend only does not hold the house up
        on a working day.

        A holiday does **not** count as a Saturday here - otherwise one person's
        school holiday holds the house up while the other is simply working from
        home. Whoever wants to be waited for on a holiday too ticks that on the
        deadline itself.
        """
        deadline = self.wake_deadline
        if deadline is None:
            return None
        if holiday and deadline.holiday:
            return deadline.at
        return deadline.at if deadline.applies_on(weekday) else None

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

    guest_window_incomplete: bool = False
    """Whether only one end of the guest window was filled in.

    Niet bewaard en niet gebruikt door de poorten: `serialise.py` zet dit uit
    de ruwe opslag, en `validate()` meldt het. Zonder deze vlag zou een half
    venster stil als "de hele dag" lezen en was er niets te melden.

    Not stored and not used by the gates: `serialise.py` sets it from the raw
    store, and `validate()` reports it. Without this flag a half window would
    quietly read as "all day" and there would be nothing to report.
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

    house_wide_openings: tuple[str, ...] = ()
    """Appliances that stop while any opening in the installation stands open.

    Een opening werkt op zones: raakt hij een zone, dan valt daar alles stil.
    Bij een centraal geregelde verwarming klopt dat niet. De ketel staat als
    bron onder alle zones, en zolang één andere zone warmte vraagt blijft hij
    branden met de deur open, want vraag wint van stilte (`_collapse_shared` in
    `decide.py`). De opening aan álle zones koppelen lost de ketel op, maar zet
    daarmee ook de airco's in die kamers stil - het hele jaar door, terwijl die
    per kamer geregeld horen te worden.

    Deze lijst hangt daarom aan het apparaat en niet aan de opening: dan hoeft
    de ketel niet bij elke deur opnieuw aangevinkt te worden, en telt een raam
    dat er later bij komt vanzelf mee. Leeg is het gedrag van vóór deze
    instelling, dus een gezoneerde cv blijft gewoon per zone geregeld.

    An opening acts on zones: once it affects a zone, everything there stops.
    For centrally controlled heating that is wrong. The boiler sits as a source
    under every zone, and as long as one other zone asks for heat it keeps
    running with the door open, because demand beats silence (`_collapse_shared`
    in `decide.py`). Linking the opening to *every* zone settles the boiler, but
    it also stops the air conditioners in those rooms - all year round, while
    those belong under per-room control.

    This list therefore hangs on the appliance rather than on the opening: the
    boiler need not be ticked again at every door, and a window added later
    counts by itself. Empty is the behaviour from before this setting, so a
    zoned boiler stays governed per zone.
    """

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

    def sources(self) -> tuple[tuple[Zone, Source], ...]:
        """Return every `(zone, source)` pair in the installation."""
        return tuple((zone, source) for zone in self.zones for source in zone.sources)

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
