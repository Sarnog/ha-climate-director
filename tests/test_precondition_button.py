"""De knop per zone, en de duur die ernaast staat.

The per-zone button, and the duration standing beside it.

Vooruit verwarmen bestond al als actie. Een actie vind je alleen als je weet
dat hij bestaat, en er viel nergens op te drukken - de gebruiker zocht het in
de handleiding en vond het niet. Deze tests dekken wat de knop doorgeeft en wat
de duur na een herstart wordt.

Pre-conditioning already existed as an action. You only find an action if you
know it is there, and there was nothing to press - the user went looking in the
manual and did not find it. These tests cover what the button passes on and
what the duration becomes after a restart.
"""

from __future__ import annotations

import pytest

from custom_components.climate_director.button import ZonePreconditionButton
from custom_components.climate_director.const import (
    DEFAULT_PRECONDITION_MINUTES,
    MAX_PRECONDITION_MINUTES,
    MIN_PRECONDITION_MINUTES,
)
from custom_components.climate_director.number import resolve_minutes


class TestTheDurationAfterARestart:
    """Wat de duurentiteit terugvindt, en wat hij van rommel maakt.

    What the duration entity finds again, and what it makes of rubbish.
    """

    def test_a_fresh_entity_starts_on_an_hour(self) -> None:
        assert resolve_minutes(None) == DEFAULT_PRECONDITION_MINUTES

    def test_what_was_set_survives_a_restart(self) -> None:
        assert resolve_minutes("45") == 45

    def test_an_unreadable_state_falls_back(self) -> None:
        """`unavailable` and `unknown` are states too, and neither is a number."""
        assert resolve_minutes("unavailable") == DEFAULT_PRECONDITION_MINUTES
        assert resolve_minutes("unknown") == DEFAULT_PRECONDITION_MINUTES

    def test_too_short_is_pulled_up_rather_than_discarded(self) -> None:
        assert resolve_minutes("5") == MIN_PRECONDITION_MINUTES

    def test_too_long_is_pulled_down(self) -> None:
        assert resolve_minutes("999") == MAX_PRECONDITION_MINUTES

    def test_a_number_is_taken_as_readily_as_a_string(self) -> None:
        assert resolve_minutes(30.0) == 30


class TestTheButton:
    """Eén druk, één zone, de duur die ernaast staat.

    One press, one zone, the duration standing beside it.
    """

    class _Coordinator:
        def __init__(self, minutes: float = DEFAULT_PRECONDITION_MINUTES) -> None:
            self.precondition_minutes = minutes
            self.asked: list[tuple[list[str], float]] = []

        def async_precondition(self, zone_ids: list[str], minutes: float) -> dict:
            self.asked.append((zone_ids, minutes))
            return {}

    def _button(self, coordinator) -> ZonePreconditionButton:
        button = ZonePreconditionButton.__new__(ZonePreconditionButton)
        button.coordinator = coordinator
        button._zone_id = "zolder"
        return button

    async def test_it_asks_for_its_own_zone_only(self) -> None:
        coordinator = self._Coordinator()
        await self._button(coordinator).async_press()
        assert coordinator.asked == [(["zolder"], DEFAULT_PRECONDITION_MINUTES)]

    async def test_it_uses_the_duration_standing_beside_it(self) -> None:
        """The button holds no number of its own; two places would drift apart."""
        coordinator = self._Coordinator(minutes=90)
        await self._button(coordinator).async_press()
        assert coordinator.asked == [(["zolder"], 90)]

    async def test_a_second_press_asks_again(self) -> None:
        """Pressing again extends the request; the coordinator caps it."""
        coordinator = self._Coordinator()
        button = self._button(coordinator)
        await button.async_press()
        await button.async_press()
        assert len(coordinator.asked) == 2


@pytest.mark.parametrize(
    "platform",
    ["binary_sensor", "button", "number", "sensor", "switch"],
)
def test_every_platform_is_forwarded(platform: str) -> None:
    """A platform file nobody forwards produces no entities at all, silently."""
    from homeassistant.const import Platform

    from custom_components.climate_director.const import PLATFORMS

    assert Platform(platform) in PLATFORMS
