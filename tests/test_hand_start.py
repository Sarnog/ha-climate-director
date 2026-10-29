"""De handstartpoort in de engine: welke drie remmen hij opzij zet.

The hand start gate in the engine: which three brakes it sets aside.

Een handstart is geen hand: hij zet een zone aan, niet uit. Daarom passeert hij
uitsluitend `WAITING_FOR_SLEEPER`, `EARLY_RISER` en `QUIET_HOURS`. De
hoofdschakelaar, een open raam, een leeg huis en de slaappoort blijven gelden.
Dezelfde module beantwoordt wanneer de handstart niets meer doet en dus mag
vervallen.

A hand start is not a hand: it switches a zone on, not off. It therefore passes
only `WAITING_FOR_SLEEPER`, `EARLY_RISER` and `QUIET_HOURS`. The master switch,
an open window, an empty house and the sleep gate keep applying. The same module
answers when the hand start no longer does anything and may lapse.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import time

from conftest import BACK_DOOR, asleep, at, awake, everyone_up, house, make_world

from custom_components.climate_director.engine import (
    DirectorConfig,
    GateSettings,
    OpeningState,
    Reason,
    RiseBrake,
    TimeWindow,
    WakeDeadline,
    Zone,
    gates,
    hand_start,
)
from custom_components.climate_director.engine.world import WorldState

LIVING = "woonkamer"


def living(config: DirectorConfig) -> Zone:
    """Return the living room, whose zone id every test here uses."""
    zone = config.zone(LIVING)
    assert zone is not None
    return zone


def with_hand_start(world: WorldState, *zone_ids: str) -> WorldState:
    """Return the same world with hand starts for the named zones."""
    return replace(world, zone_hand_starts=frozenset(zone_ids))


def weekend_house() -> DirectorConfig:
    """Return the house with a weekend wake deadline for both residents."""
    base = house()
    eleven = WakeDeadline(at=time(11, 0), weekdays=frozenset({5, 6}))
    return replace(
        base,
        residents=tuple(replace(resident, wake_deadline=eleven) for resident in base.residents),
    )


def after_a_slept_night(world: WorldState) -> WorldState:
    """Return the world as a morning after a night the house slept."""
    return replace(world, asleep_since=world.now.replace(hour=1, minute=0))


class TestWaitingForSleeper:
    def test_it_passes_the_wait_for_the_last_sleeper(self) -> None:
        """Een handstart laat de zone door terwijl de ander nog in bed ligt."""
        config = weekend_house()
        world = after_a_slept_night(
            make_world(now=at(10, 0, day=15), residents={"danny": awake(), "nancy": asleep()})
        )
        waiting = gate(config, world)
        assert waiting == (Reason.WAITING_FOR_SLEEPER,)

        assert gate(config, with_hand_start(world, LIVING)) == ()

    def test_it_does_not_pass_everyone_asleep(self) -> None:
        """De slaappoort is geen ochtendwacht en blijft dicht."""
        config = weekend_house()
        world = with_hand_start(
            make_world(
                now=at(23, 0, day=14),
                residents={"danny": asleep(), "nancy": asleep()},
            ),
            LIVING,
        )
        assert gate(config, world) == (Reason.EVERYONE_ASLEEP,)


class TestEarlyRiser:
    def test_it_passes_the_rise_brake(self) -> None:
        """Een handstart laat de zone door vóór de opsta-rem voorbij is."""
        base = house()
        brake = RiseBrake(at=time(9, 0), weekdays=frozenset({0}))
        config = replace(
            base,
            residents=tuple(replace(resident, rise_brake=brake) for resident in base.residents),
        )
        world = make_world(now=at(8, 0), residents=everyone_up())
        assert gate(config, world) == (Reason.EARLY_RISER,)
        assert gate(config, with_hand_start(world, LIVING)) == ()

    def test_it_does_not_pass_the_master_switch(self) -> None:
        """De hoofdschakelaar gaat vóór elke handstart."""
        config = house()
        world = with_hand_start(make_world(residents=everyone_up(), master_enabled=False), LIVING)
        assert gate(config, world) == (Reason.MASTER_DISABLED,)


class TestQuietHours:
    def quiet_house(self) -> DirectorConfig:
        """Return the house with a quiet window around the test moment."""
        return replace(
            house(),
            gates=GateSettings(
                require_awake=True,
                quiet_windows=(TimeWindow(time(11, 0), time(13, 0)),),
            ),
        )

    def test_it_passes_the_quiet_window(self) -> None:
        """Een handstart laat de zone in het stiltevenster beginnen."""
        config = self.quiet_house()
        world = make_world(now=at(12, 0), residents=everyone_up())
        assert gate(config, world) == (Reason.QUIET_HOURS,)
        assert gate(config, with_hand_start(world, LIVING)) == ()

    def test_a_running_zone_still_waits_for_the_end_of_the_window(self) -> None:
        """Een draaiende zone passeert het venster, maar de handstart blijft tot het einde.

        Na de eerste stop moet de zone in hetzelfde venster weer kunnen
        starten; daarom telt een draaiend eigen apparaat hier als uit.

        A running zone passes the window, but the hand start stays until the end.
        After the first stop the zone must be able to start again inside the same
        window; that is why a running appliance of its own counts as off here.
        """
        config = self.quiet_house()
        world = with_hand_start(
            make_world(now=at(12, 0), residents=everyone_up(), climates={LIVING: "heat"}),
            LIVING,
        )
        assert gate(config, world) == ()
        assert hand_start.brakes_remaining(config, world, living(config), None) == frozenset(
            {Reason.QUIET_HOURS}
        )

    def test_it_does_not_pass_an_open_window(self) -> None:
        """Een open raam blijft de zone tegenhouden."""
        config = self.quiet_house()
        world = with_hand_start(
            make_world(
                now=at(12, 1),
                residents=everyone_up(),
                openings={BACK_DOOR: OpeningState(open=True, changed_at=at(12, 0))},
            ),
            LIVING,
        )
        assert gate(config, world) == (Reason.OPENING_OPEN,)


class TestWhenTheHandStartStopsDoingSomething:
    def test_brakes_remain_while_the_sleeper_waits(self) -> None:
        """Zolang de slaper wacht, blijft de handstart nodig."""
        config = weekend_house()
        world = with_hand_start(
            after_a_slept_night(
                make_world(
                    now=at(10, 0, day=15),
                    residents={"danny": awake(), "nancy": asleep()},
                )
            ),
            LIVING,
        )
        assert hand_start.brakes_remaining(config, world, living(config), None) == frozenset(
            {Reason.WAITING_FOR_SLEEPER}
        )

    def test_no_brake_remains_after_the_deadline(self) -> None:
        """Na de uiterste tijd doet de handstart niets meer."""
        config = weekend_house()
        world = with_hand_start(
            after_a_slept_night(
                make_world(
                    now=at(11, 0, day=15),
                    residents={"danny": awake(), "nancy": asleep()},
                )
            ),
            LIVING,
        )
        assert hand_start.brakes_remaining(config, world, living(config), None) == frozenset()

    def test_it_passes_only_the_three_waiting_reasons(self) -> None:
        """Geen enkele andere reden gaat door de handstartpoort."""
        world = with_hand_start(make_world(), LIVING)
        for reason in Reason:
            assert hand_start.passes(world, LIVING, reason) is (
                reason in hand_start.HAND_START_BRAKES
            )

    def test_a_hand_start_on_another_zone_does_not_help(self) -> None:
        """De handstart hangt aan de zone, niet aan het huis."""
        config = weekend_house()
        world = with_hand_start(
            after_a_slept_night(
                make_world(
                    now=at(10, 0, day=15),
                    residents={"danny": awake(), "nancy": asleep()},
                )
            ),
            "zolder",
        )
        assert gate(config, world) == (Reason.WAITING_FOR_SLEEPER,)

    def test_a_zone_without_a_waiting_reason_keeps_its_hand_start_harmless(self) -> None:
        """Een handstart zonder wachtreden doet niets en vervalt meteen."""
        config = house()
        world = with_hand_start(make_world(residents=everyone_up()), LIVING)
        assert gate(config, world) == ()
        assert hand_start.brakes_remaining(config, world, living(config), None) == frozenset()


def gate(config: DirectorConfig, world: WorldState) -> tuple[Reason, ...]:
    """Return every gate still shut for the living room."""
    return gates.closed(config, world, living(config))
