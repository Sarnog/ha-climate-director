"""Tijdvensters met dagen en vakantievlag. / Time windows with days and a holiday flag."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta


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
