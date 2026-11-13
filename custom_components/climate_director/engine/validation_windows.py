"""De controles op vensters en agenda's.

The checks on windows and calendars.

De vensters zonder lengte, het halve gastenvenster en de feestdagenagenda's.

The windows without length, the half-filled guest window and the holiday calendars.
"""

from __future__ import annotations

from collections.abc import Iterator

from .models import DirectorConfig
from .problem import Problem
from .validation_shared import windows


def rule_windows_without_length(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for a window whose start equals its end.

    Zo'n venster is nooit open: het begin valt samen met het einde, en de
    vergelijking leest dat als een leeg venster. Dat is van buiten niet te
    onderscheiden van een venster dat iemand expres dicht liet.

    Such a window is never open: its start coincides with its end, and the
    comparison reads that as an empty window. From the outside that cannot be
    told apart from a window somebody deliberately left shut.
    """
    for label, window in windows(config):
        if window.start == window.end:
            yield Problem(
                "window_without_length",
                f"{label} starts and ends at the same time, so it is never open",
                window=label,
            )


def rule_guest_window_half_filled(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for a guest window with only one end filled in.

    Half een venster is geen venster: de gastenmodus geldt dan de hele dag.
    Dat is een stille verbreding van wat iemand invulde.

    Half a window is no window: guest mode then applies all day. That is a
    silent widening of what somebody filled in.
    """
    if config.gates.guest_window_incomplete:
        yield Problem(
            "guest_window_half_filled",
            "the guest window has only one end filled in, so guest mode applies all day",
        )


def rule_holiday_calendars(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint when holiday calendars have nothing to match on.

    Agenda's zonder trefwoord kunnen nooit een vakantiedag aanzetten; de
    instelling staat er dan wel, maar doet niets.

    Calendars without a keyword can never switch a holiday on; the setting is
    there, but does nothing.
    """
    if config.holiday_calendars and not config.holiday_keyword.strip():
        yield Problem(
            "calendars_without_keyword",
            "holiday calendars are set but no keyword is, so no event can ever "
            "switch holiday mode on",
        )
