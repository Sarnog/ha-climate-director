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

from datetime import datetime, timedelta

import pytest
from homeassistant.util import dt as dt_util

from custom_components.climate_director import coordinator as module
from custom_components.climate_director.coordinator import ClimateDirectorCoordinator
from custom_components.climate_director.engine import Reason
from custom_components.climate_director.engine.plan import Deferral, Plan


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
        self._cancel_deferral: _Cancel | None = None
        self._cancel_precondition_wake: _Cancel | None = None
        self._precondition: dict[str, datetime] = {}
        self._precondition_bypass: set[str] = set()
        self._debouncer = _Debouncer()

    _cancel_clock_reeval = ClimateDirectorCoordinator._cancel_clock_reeval
    _schedule_clock_reeval = ClimateDirectorCoordinator._schedule_clock_reeval
    _on_clock_reeval = ClimateDirectorCoordinator._on_clock_reeval
    _schedule_deferral = ClimateDirectorCoordinator._schedule_deferral
    _cancel_pending_deferral = ClimateDirectorCoordinator._cancel_pending_deferral
    _live_preconditions = ClimateDirectorCoordinator._live_preconditions
    _wake_at_the_first_expiry = ClimateDirectorCoordinator._wake_at_the_first_expiry
    _preconditions_expire_at = ClimateDirectorCoordinator._preconditions_expire_at
    _on_precondition_expiry = ClimateDirectorCoordinator._on_precondition_expiry
    _cancel_pending_precondition_wake = ClimateDirectorCoordinator._cancel_pending_precondition_wake
    async_request_evaluation = ClimateDirectorCoordinator.async_request_evaluation


def waiting(minutes: float) -> Plan:
    """Return a plan that may not do what it wants for another `minutes`."""
    return Plan(
        deferrals=(
            Deferral(
                "circuit",
                dt_util.now() + timedelta(minutes=minutes),
                Reason.SHORT_CYCLE_PROTECTION,
            ),
        )
    )


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


class TestTheDeferral:
    """Een plan dat op een timer wacht, wekt zichzelf.

    Zonder deze afspraak blijft een kortcyclusblokkade wachten op een
    toestandswijziging die op een stille nacht nooit komt.

    A plan waiting on a timer wakes itself. Without this appointment a
    short-cycle block waits for a state change that on a quiet night never
    comes.
    """

    def test_a_plan_without_a_timer_arms_nothing(self, scheduled) -> None:
        calls, _ = scheduled
        item = StandIn()
        item._schedule_deferral(Plan())
        assert calls == []
        assert item._cancel_deferral is None

    def test_a_waiting_plan_arms_an_appointment(self, scheduled) -> None:
        calls, cancels = scheduled
        item = StandIn()
        item._schedule_deferral(waiting(10))
        assert len(calls) == 1
        assert 0 < calls[0][0] <= 600
        assert item._cancel_deferral is cancels[0]

    def test_a_timer_already_past_still_waits_a_moment(self, scheduled) -> None:
        """Nooit nul: een afspraak in het verleden hoort niet meteen te vuren."""
        calls, _ = scheduled
        item = StandIn()
        item._schedule_deferral(waiting(-5))
        assert calls[0][0] == module.MIN_DEFERRAL_SECONDS

    def test_the_appointment_asks_for_a_fresh_decision_and_clears_itself(self, scheduled) -> None:
        """`_resume` is het hele punt: hij beslist opnieuw en laat geen handvat achter.

        `_resume` is the whole point: it decides again and leaves no handle
        behind that a later cancel would try to use.
        """
        calls, _ = scheduled
        item = StandIn()
        item._schedule_deferral(waiting(10))
        _delay, resume = calls[0]

        resume(datetime(2026, 8, 11, 12, 1))

        assert item._debouncer.scheduled == 1
        assert item._cancel_deferral is None

    def test_a_new_plan_replaces_the_standing_appointment(self, scheduled) -> None:
        calls, cancels = scheduled
        item = StandIn()
        item._schedule_deferral(waiting(10))
        item._schedule_deferral(waiting(20))

        assert cancels[0].called == 1
        assert len(calls) == 2
        assert item._cancel_deferral is cancels[1]

    def test_a_plan_without_a_timer_drops_the_standing_appointment(self, scheduled) -> None:
        """Anders vuurt er nog een afspraak voor een wachtrij die niet meer bestaat."""
        _calls, cancels = scheduled
        item = StandIn()
        item._schedule_deferral(waiting(10))
        item._schedule_deferral(Plan())

        assert cancels[0].called == 1
        assert item._cancel_deferral is None


class TestThePreconditionWakeUp:
    """Een vooruit-verzoek loopt af, en dan hoort er opnieuw besloten te worden.

    Zonder wekker blijft een leeg huis doorstoken tot er toevallig iets anders
    verandert. En zonder handvat aan die wekker blijft hij na het afsluiten van
    de installatie staan en gaat hij alsnog af, op een coordinator die er niet
    meer is.

    A pre-conditioning request runs out, and then a fresh decision is due.
    Without an alarm an empty house keeps burning until something else happens
    to change. Without a handle on that alarm it survives the teardown and goes
    off anyway, on a coordinator that is no longer there.
    """

    def test_it_wakes_up_when_the_request_runs_out(self, scheduled) -> None:
        calls, cancels = scheduled
        item = StandIn()
        item._preconditions_expire_at(dt_util.now() + timedelta(minutes=30))

        assert len(calls) == 1
        assert item._cancel_precondition_wake is cancels[0]

    def test_a_request_that_already_ran_out_arms_nothing(self, scheduled) -> None:
        calls, _ = scheduled
        item = StandIn()
        item._preconditions_expire_at(dt_util.now() - timedelta(minutes=1))

        assert calls == []
        assert item._cancel_precondition_wake is None

    def test_a_second_request_replaces_the_standing_alarm(self, scheduled) -> None:
        """Anders hangt er per verzoek een wekker, en die gaan allemaal af."""
        calls, cancels = scheduled
        item = StandIn()
        item._preconditions_expire_at(dt_util.now() + timedelta(minutes=30))
        item._preconditions_expire_at(dt_util.now() + timedelta(minutes=10))

        assert cancels[0].called == 1
        assert len(calls) == 2
        assert item._cancel_precondition_wake is cancels[1]

    def test_it_decides_again_and_sets_itself_on_the_next_request(self, scheduled) -> None:
        calls, _ = scheduled
        item = StandIn()
        now = dt_util.now()
        item._precondition = {
            "woonkamer": now - timedelta(minutes=1),
            "zolder": now + timedelta(minutes=20),
        }
        item._preconditions_expire_at(now)
        item._preconditions_expire_at(min(item._precondition.values()))
        calls.clear()

        item._on_precondition_expiry(now)

        assert item._debouncer.scheduled == 1
        # Het verlopen verzoek is opgeruimd, en de zolder krijgt zijn eigen wekker.
        # The expired request is cleared, and the attic gets its own alarm.
        assert list(item._precondition) == ["zolder"]
        assert len(calls) == 1

    def test_the_last_request_leaves_no_alarm_behind(self, scheduled) -> None:
        calls, _ = scheduled
        item = StandIn()
        item._preconditions_expire_at(dt_util.now() + timedelta(minutes=5))
        calls.clear()

        item._on_precondition_expiry(dt_util.now())

        assert item._cancel_precondition_wake is None
        assert calls == []

    def test_the_alarm_can_be_dropped(self, scheduled) -> None:
        """Bij het afsluiten van de installatie moet hij weg."""
        _calls, cancels = scheduled
        item = StandIn()
        item._preconditions_expire_at(dt_util.now() + timedelta(minutes=5))
        item._cancel_pending_precondition_wake()

        assert cancels[0].called == 1
        assert item._cancel_precondition_wake is None

        # Nog een keer is onschadelijk.
        # Once more is harmless.
        item._cancel_pending_precondition_wake()
        assert cancels[0].called == 1
