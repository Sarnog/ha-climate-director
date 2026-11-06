"""De bewoner en zijn ochtendinstellingen. / The resident and their morning settings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from .seasons import HOLIDAY_WEEKDAY
from .windows import TimeWindow


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
