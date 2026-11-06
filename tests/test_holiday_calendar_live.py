"""De vakantieagenda als invoer van de poorten.

The holiday calendar as an input of the gates."""

from __future__ import annotations

from typing import Any

from harness_live import (
    start_house,
    stop_house,
)
from live_helpers import (
    cold_at_home,
    gated_house,
)


class TestTheHolidayCalendar:
    """Een agenda mag het huis op vakantie zetten, maar alleen met trefwoord.

    A calendar may put the house on holiday, but only with a keyword.
    """

    def _house(self, keyword: str) -> dict[str, Any]:
        found = gated_house()
        found["holiday_calendars"] = ["calendar.familie"]
        found["holiday_keyword"] = keyword
        return found

    async def test_a_running_event_with_the_keyword_counts(self) -> None:
        home = await start_house(
            self._house("vakantie"),
            states={
                **cold_at_home(),
                "calendar.familie": ("on", {"message": "Zomervakantie Spanje"}),
            },
        )
        try:
            assert home.coordinator.world.holiday_mode is True
        finally:
            await stop_house(home)

    async def test_an_event_without_the_keyword_does_not(self) -> None:
        home = await start_house(
            self._house("vakantie"),
            states={**cold_at_home(), "calendar.familie": ("on", {"message": "Tandarts"})},
        )
        try:
            assert home.coordinator.world.holiday_mode is False
        finally:
            await stop_house(home)

    async def test_without_a_keyword_the_calendar_is_left_alone(self) -> None:
        home = await start_house(
            self._house(""),
            states={**cold_at_home(), "calendar.familie": ("on", {"message": "Vakantie"})},
        )
        try:
            assert home.coordinator.world.holiday_mode is False
        finally:
            await stop_house(home)

    async def test_an_event_that_is_not_running_does_not_count(self) -> None:
        home = await start_house(
            self._house("vakantie"),
            states={**cold_at_home(), "calendar.familie": ("off", {"message": "Vakantie"})},
        )
        try:
            assert home.coordinator.world.holiday_mode is False
        finally:
            await stop_house(home)
