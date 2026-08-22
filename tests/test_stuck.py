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
    Reason.CIRCUIT_AT_CAPACITY,
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


class TestAFullOutdoorUnitIsNoDeadlock:
    """Vol is geen klem: er wacht niemand op iets dat niet komt.

    Full is no deadlock: nobody is waiting for something that is not coming.

    De andere wachtredenen zijn timers die in seconden of minuten aflopen - een
    omschakelpauze, een minimale looptijd, een kortcyclusrust. Een volle
    buitenunit is dat niet: die loopt pas leeg als een andere kamer ophoudt met
    vragen, en dat kan uren duren zonder dat er iets mis is. Een handbediende
    slaapkamerairco die de hele avond aanstaat is precies het geval waar de
    instelling voor bedoeld is.

    Stond het er wel bij, dan ging de melder in een gesimuleerd jaar 352 keer af
    - bijna elke dag een keer, en nooit ergens voor. Precies wat de eigen regel
    verbiedt: een valse melding leert je de melder te negeren.

    De kamer die zijn plek niet krijgt hoort het nog steeds: die staat als
    geblokkeerd te boek, want hij vroeg meer dan hij kreeg.

    The other waiting reasons are timers running out in seconds or minutes - a
    changeover pause, a minimum run, a short-cycle rest. A full outdoor unit is
    not: it only frees up once another room stops asking, and that may take
    hours with nothing wrong. A hand-operated bedroom unit left on all evening
    is exactly the case the setting exists for.

    Listed there, the sensor went off 352 times in a simulated year - nearly one
    a day, and never for anything. Precisely what its own rule forbids: a false
    alarm teaches you to ignore the alarm.

    The room that does not get its place still hears about it: it stands
    recorded as blocked, since it asked for more than it got.
    """

    def test_it_is_not_a_waiting_reason(self) -> None:
        assert Reason.CIRCUIT_AT_CAPACITY not in WAITING_REASONS

    def test_a_whole_evening_at_capacity_raises_nothing(self) -> None:
        item = coordinator(minutes=15)
        # Vier uur lang elke ronde hetzelfde: de buitenunit blijft vol.
        # Four hours of the same every round: the outdoor unit stays full.
        for _ in range(240):
            item._note_waiting(plan_with(Reason.CIRCUIT_AT_CAPACITY))
        assert item.waiting_seconds() == {}
        assert item.stuck_zones() == {}

    def test_the_other_three_are_still_watched(self) -> None:
        """De timers die wél horen af te lopen, blijven bewaakt."""
        assert set(WAITING_REASONS) == {
            Reason.CIRCUIT_SWITCH_PENDING,
            Reason.CIRCUIT_SWITCH_TOO_SOON,
            Reason.SHORT_CYCLE_PROTECTION,
        }

    def test_the_zone_still_reports_being_blocked(self) -> None:
        """Niet melden als klem is iets anders dan verzwijgen."""
        from custom_components.climate_director.engine.plan import ZoneDecision as Decision

        decision = Decision(
            zone_id="woonkamer",
            wanted=ModeFamily.HEAT,
            granted=ModeFamily.NEUTRAL,
            reason=Reason.CIRCUIT_AT_CAPACITY,
        )
        assert decision.blocked


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


class TestUnitsBelongingToNobody:
    """A unit on a circuit but in no zone: exactly what caught the user out.

    Zo'n unit houdt het hele circuit op zijn taak zodra hij draait, en de
    director kan hem niet uitzetten want hij is van niemand. Van buiten lijkt
    dat op "de director doet niets", en daar kwam de gebruiker pas achter door
    de installatie handmatig door te rekenen.

    Such a unit holds the whole circuit to its duty the moment it runs, and the
    director cannot stand it down because it belongs to nobody. From the outside
    that looks like "the director does nothing", which the user only found out
    by working the installation through by hand.
    """

    def _config(self, units: tuple[str, ...]) -> DirectorConfig:
        from custom_components.climate_director.engine import Circuit

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
            circuits=(Circuit("airco", "Airco", units=units),),
        )

    def _problems(self, units: tuple[str, ...]) -> list[str]:
        from custom_components.climate_director.engine import validate

        return [item for item in validate(self._config(units)) if "in no zone" in item]

    def test_a_stray_unit_is_reported(self) -> None:
        found = self._problems(("climate.huiskamer", "climate.master_bedroom"))
        assert found
        assert "climate.master_bedroom" in found[0]

    def test_every_stray_unit_is_named(self) -> None:
        found = self._problems(("climate.huiskamer", "climate.a", "climate.b"))
        assert len(found) == 2

    def test_a_circuit_of_only_known_units_is_sound(self) -> None:
        assert not self._problems(("climate.huiskamer",))

    def test_a_manual_source_still_counts_as_known(self) -> None:
        """Turning autostart off does not make a unit stray; it is still a source."""
        from custom_components.climate_director.engine import Circuit, validate

        config = DirectorConfig(
            zones=(
                Zone(
                    "slaapkamer",
                    "Slaapkamer",
                    "climate.master_bedroom",
                    sources=(Source("s", "climate.master_bedroom", autostart=False),),
                    heat=ModeSettings(21.0, 20.0),
                ),
            ),
            circuits=(Circuit("airco", "Airco", units=("climate.master_bedroom",)),),
        )
        assert not [item for item in validate(config) if "in no zone" in item]


class TestEntitiesThatCannotBeRead:
    """A mistyped or dropped-out entity fails silently, so it gets said out loud."""

    def _coordinator(self, states: dict[str, str | None]):
        class Registry:
            def get(self, entity_id):
                value = states.get(entity_id, "__absent__")
                if value == "__absent__" or value is None:
                    return None
                return type("S", (), {"state": value})()

        class Hass:
            def __init__(self) -> None:
                self.states = Registry()

        class StandIn:
            def __init__(self) -> None:
                self.config = config()
                self.hass = Hass()

            tracked_entities = ClimateDirectorCoordinator.tracked_entities
            unusable_entities = ClimateDirectorCoordinator.unusable_entities

        return StandIn()

    def test_everything_readable_is_quiet(self) -> None:
        item = self._coordinator({"sensor.woonkamer": "21.0", "climate.huiskamer": "off"})
        assert item.unusable_entities() == {}

    def test_a_missing_entity_is_named(self) -> None:
        """The classic typo: the id is wrong, so the zone silently never runs."""
        item = self._coordinator({"climate.huiskamer": "off"})
        assert item.unusable_entities() == {"sensor.woonkamer": "missing"}

    @pytest.mark.parametrize("state", ["unavailable", "unknown"])
    def test_an_unreadable_entity_is_named(self, state: str) -> None:
        item = self._coordinator({"sensor.woonkamer": state, "climate.huiskamer": "off"})
        assert item.unusable_entities() == {"sensor.woonkamer": state}

    def test_several_are_all_named(self) -> None:
        item = self._coordinator({"sensor.woonkamer": "unavailable"})
        assert set(item.unusable_entities()) == {"sensor.woonkamer", "climate.huiskamer"}
