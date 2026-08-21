"""De klokgestuurde herbeoordeling als vangnet voor tijdregels.

The clock-driven re-evaluation as a safety net for time rules.

Een raamvertraging, een aanwezigheids-nalooptijd, de neerslag-grace, de
eerstvolgende vensterrand en middernacht verlopen vanzelf. Zonder klok wacht de
director op een toestandswijziging die misschien nooit komt; deze tick zorgt
dat er elke minuut opnieuw besloten wordt. Een ronde zonder verschil kost geen
service call, dus het vangnet is goedkoop.

A window delay, a presence grace period, the precipitation grace, the next
window edge and midnight lapse by themselves. Without a clock the director
waits for a state change that may never come; this tick makes it decide again
every minute. A round without a difference costs no service call, so the net is
cheap.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from custom_components.climate_director import coordinator as module
from custom_components.climate_director.coordinator import ClimateDirectorCoordinator


class _Debouncer:
    def __init__(self) -> None:
        self.scheduled = 0

    def async_schedule_call(self) -> None:
        self.scheduled += 1


class _Cancel:
    def __init__(self) -> None:
        self.called = 0

    def __call__(self) -> None:
        self.called += 1


class StandIn:
    def __init__(self) -> None:
        self.hass = object()
        self._clock_reeval_unsub: _Cancel | None = None
        self._debouncer = _Debouncer()

    _cancel_clock_reeval = ClimateDirectorCoordinator._cancel_clock_reeval
    _schedule_clock_reeval = ClimateDirectorCoordinator._schedule_clock_reeval
    _on_clock_reeval = ClimateDirectorCoordinator._on_clock_reeval
    async_request_evaluation = ClimateDirectorCoordinator.async_request_evaluation


@pytest.fixture
def scheduled(monkeypatch: pytest.MonkeyPatch):
    """Record every tick the coordinator arms, with its own cancel handle."""
    calls: list[tuple[float, object]] = []
    cancels: list[_Cancel] = []

    def _fake(hass, delay: float, action):
        cancel = _Cancel()
        cancels.append(cancel)
        calls.append((delay, action))
        return cancel

    monkeypatch.setattr(module, "async_call_later", _fake)
    return calls, cancels


class TestTheClockTick:
    def test_a_tick_is_armed(self, scheduled) -> None:
        calls, _ = scheduled
        item = StandIn()
        item._schedule_clock_reeval()
        assert len(calls) == 1
        assert calls[0][0] == module.CLOCK_REEVAL_SECONDS

    def test_the_tick_requests_an_evaluation_and_rearms(self, scheduled) -> None:
        calls, _ = scheduled
        item = StandIn()
        item._schedule_clock_reeval()
        _delay, action = calls[0]

        action(datetime(2026, 8, 11, 12, 1))

        assert item._debouncer.scheduled == 1
        assert len(calls) == 2
        assert calls[1][0] == module.CLOCK_REEVAL_SECONDS

    def test_arming_again_replaces_the_previous_tick(self, scheduled) -> None:
        calls, cancels = scheduled
        item = StandIn()
        item._schedule_clock_reeval()
        item._schedule_clock_reeval()

        assert cancels[0].called == 1
        assert len(calls) == 2
        assert item._clock_reeval_unsub is cancels[1]

    def test_cancelling_drops_the_tick(self, scheduled) -> None:
        _calls, cancels = scheduled
        item = StandIn()
        item._schedule_clock_reeval()
        item._cancel_clock_reeval()

        assert cancels[0].called == 1
        assert item._clock_reeval_unsub is None

        # Nog een keer annuleren is onschadelijk.
        # Cancelling once more is harmless.
        item._cancel_clock_reeval()
        assert cancels[0].called == 1
