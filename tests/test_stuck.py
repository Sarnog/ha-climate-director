"""Een zone die blijft wachten op iets dat niet komt.

A zone left waiting for something that is not coming.

De schaduwmodus vergelijkt het plan met de werkelijkheid, en loopt daarvoor over
de commando's. Een apparaat waar het plan géén commando voor heeft komt in die
vergelijking niet voor - dus een klem waarbij er niets wordt aangestuurd is voor
de mismatch-teller onzichtbaar. Deze melder kijkt naar het andere spoor: een
reden die uit zichzelf hoort op te lossen en dat niet doet.

Shadow mode compares the plan with reality by walking the commands. An appliance
the plan has no command for does not appear in that comparison - so a deadlock
in which nothing is steered is invisible to the mismatch count. This sensor
watches the other trail: a reason that should resolve by itself and does not.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from custom_components.climate_director.coordinator import ClimateDirectorCoordinator
from custom_components.climate_director.engine import (
    WAITING_REASONS,
    DirectorConfig,
    ModeFamily,
    ModeSettings,
    Reason,
    Source,
    Zone,
)
from custom_components.climate_director.engine.plan import Plan, ZoneDecision
from custom_components.climate_director.engine.serialise import config_from_dict, config_to_dict

WAITING = sorted(WAITING_REASONS, key=str)
SETTLED = [
    Reason.REGULATING,
    Reason.SATISFIED,
    Reason.ZONE_UNOCCUPIED,
    Reason.OUTDOOR_OUTSIDE_WINDOW,
    Reason.MASTER_DISABLED,
    Reason.NOBODY_HOME,
    Reason.CIRCUIT_CONFLICT_LOST,
]


def config(minutes: int = 15) -> DirectorConfig:
    return DirectorConfig(
        zones=(
            Zone(
                "woonkamer",
                "Woonkamer",
                "sensor.woonkamer",
                sources=(Source("w", "climate.huiskamer"),),
                heat=ModeSettings(21.0, 20.0),
            ),
        ),
        stuck_after=timedelta(minutes=minutes),
    )


def plan_with(reason: Reason) -> Plan:
    return Plan(
        zones=(
            ZoneDecision(
                zone_id="woonkamer",
                wanted=ModeFamily.HEAT,
                granted=ModeFamily.NEUTRAL,
                reason=reason,
            ),
        )
    )


def coordinator(minutes: int = 15):
    """Return a stand-in carrying only what the stuck methods touch."""

    class StandIn:
        def __init__(self) -> None:
            self.config = config(minutes)
            self._waiting: dict[str, tuple[Reason, datetime]] = {}

        _note_waiting = ClimateDirectorCoordinator._note_waiting
        waiting_seconds = ClimateDirectorCoordinator.waiting_seconds
        stuck_zones = ClimateDirectorCoordinator.stuck_zones

    return StandIn()


def age(item, zone_id: str, minutes: float) -> None:
    """Pretend that zone has been waiting that long."""
    reason, since = item._waiting[zone_id]
    item._waiting[zone_id] = (reason, since - timedelta(minutes=minutes))


class TestTheClockRuns:
    @pytest.mark.parametrize("reason", WAITING, ids=[r.value for r in WAITING])
    def test_a_waiting_reason_starts_it(self, reason: Reason) -> None:
        item = coordinator()
        item._note_waiting(plan_with(reason))
        assert "woonkamer" in item.waiting_seconds()

    @pytest.mark.parametrize("reason", SETTLED, ids=[r.value for r in SETTLED])
    def test_a_settled_reason_does_not(self, reason: Reason) -> None:
        """Nobody home is a state, not a wait. It may hold for weeks."""
        item = coordinator()
        item._note_waiting(plan_with(reason))
        assert item.waiting_seconds() == {}

    def test_the_same_reason_keeps_the_clock_running(self) -> None:
        item = coordinator()
        item._note_waiting(plan_with(Reason.CIRCUIT_SWITCH_PENDING))
        age(item, "woonkamer", 10)
        item._note_waiting(plan_with(Reason.CIRCUIT_SWITCH_PENDING))
        assert item.waiting_seconds()["woonkamer"] > 500

    def test_another_reason_resets_it(self) -> None:
        """The reason changing means something happened, so the wait is new."""
        item = coordinator()
        item._note_waiting(plan_with(Reason.CIRCUIT_SWITCH_PENDING))
        age(item, "woonkamer", 10)
        item._note_waiting(plan_with(Reason.SHORT_CYCLE_PROTECTION))
        assert item.waiting_seconds()["woonkamer"] < 5

    def test_getting_going_clears_it(self) -> None:
        item = coordinator()
        item._note_waiting(plan_with(Reason.CIRCUIT_SWITCH_PENDING))
        item._note_waiting(plan_with(Reason.REGULATING))
        assert item.waiting_seconds() == {}


class TestReportingIt:
    def test_a_short_wait_is_no_alarm(self) -> None:
        item = coordinator(minutes=15)
        item._note_waiting(plan_with(Reason.CIRCUIT_SWITCH_PENDING))
        age(item, "woonkamer", 5)
        assert item.stuck_zones() == {}

    def test_a_long_wait_is(self) -> None:
        item = coordinator(minutes=15)
        item._note_waiting(plan_with(Reason.CIRCUIT_SWITCH_PENDING))
        age(item, "woonkamer", 20)
        assert item.stuck_zones() == {"woonkamer": Reason.CIRCUIT_SWITCH_PENDING}

    def test_exactly_at_the_limit_counts(self) -> None:
        item = coordinator(minutes=15)
        item._note_waiting(plan_with(Reason.CIRCUIT_SWITCH_PENDING))
        age(item, "woonkamer", 15)
        assert item.stuck_zones()

    @pytest.mark.parametrize("minutes", [1, 5, 15, 60, 240])
    def test_the_limit_is_settable(self, minutes: int) -> None:
        item = coordinator(minutes=minutes)
        item._note_waiting(plan_with(Reason.CIRCUIT_SWITCH_PENDING))
        age(item, "woonkamer", minutes - 0.5)
        assert not item.stuck_zones()
        age(item, "woonkamer", 1)
        assert item.stuck_zones()

    def test_zero_switches_it_off(self) -> None:
        """A sensor you do not want should be silent, not permanently on."""
        item = coordinator(minutes=0)
        item._note_waiting(plan_with(Reason.CIRCUIT_SWITCH_PENDING))
        age(item, "woonkamer", 600)
        assert item.stuck_zones() == {}


class TestTheDeadlockItWasBuiltFor:
    """The v3.6.3 fault, from the outside: a zone waiting on a pause forever."""

    def test_it_would_have_been_caught(self) -> None:
        item = coordinator(minutes=15)
        # Elke minuut hetzelfde plan: de omschakeling blijft hangen.
        # The same plan every minute: the changeover stays pending.
        for _ in range(30):
            item._note_waiting(plan_with(Reason.CIRCUIT_SWITCH_PENDING))
        age(item, "woonkamer", 30)
        stuck = item.stuck_zones()
        assert stuck == {"woonkamer": Reason.CIRCUIT_SWITCH_PENDING}

    def test_a_changeover_that_completes_is_silent(self) -> None:
        """The same pause, resolving as it should, must raise nothing."""
        item = coordinator(minutes=15)
        item._note_waiting(plan_with(Reason.CIRCUIT_SWITCH_PENDING))
        age(item, "woonkamer", 5)
        item._note_waiting(plan_with(Reason.REGULATING))
        assert item.stuck_zones() == {}
        assert item.waiting_seconds() == {}


class TestTheSetting:
    def test_it_round_trips(self) -> None:
        original = config(minutes=42)
        assert config_from_dict(config_to_dict(original)) == original

    def test_older_options_get_the_default(self) -> None:
        assert config_from_dict({}).stuck_after == timedelta(minutes=15)

    def test_a_negative_time_is_reported(self) -> None:
        from custom_components.climate_director.engine import validate

        broken = DirectorConfig(zones=config().zones, stuck_after=timedelta(seconds=-1))
        assert any("stuck-detection time is negative" in item for item in validate(broken))
