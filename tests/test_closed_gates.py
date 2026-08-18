"""Tests voor de volledige lijst dichte poorten.

Tests for the full list of shut gates.

`evaluate()` noemt de eerste hindernis, want één dichte poort houdt de zone al
tegen. `closed()` noemt ze allemaal, zodat je bij het inrichten niet per poort
een ronde nodig hebt. De twee mogen daarbij nooit uit elkaar lopen: de eerste
uit de lijst is de reden die het oordeel geeft.

`evaluate()` names the first obstacle, since one shut gate is enough to hold
the zone back. `closed()` names them all, so setting up does not cost a round
per gate. The two must never drift apart: the first of the list is the reason
the verdict gives.
"""

from __future__ import annotations

from datetime import time, timedelta

from conftest import (
    BACK_DOOR,
    asleep,
    at,
    away,
    everyone_up,
    house,
    make_world,
    office_hours,
)

from custom_components.climate_director.engine import (
    DirectorConfig,
    GateSettings,
    OpeningState,
    PresenceState,
    Reason,
    Resident,
    TimeWindow,
    Zone,
    ZoneGate,
    gates,
)


def living_room(config: DirectorConfig) -> Zone:
    zone = config.zone("woonkamer")
    assert zone is not None
    return zone


def test_a_zone_with_nothing_in_its_way_reports_no_gates() -> None:
    config = house()
    world = make_world(residents=everyone_up())
    assert gates.closed(config, world, living_room(config)) == ()


def test_every_shut_gate_is_named_at_once() -> None:
    """Three obstacles, one look: the point of the whole list."""
    config = house()
    world = make_world(
        now=at(12, 1),
        residents={"danny": away(), "nancy": away()},
        master_enabled=False,
        openings={BACK_DOOR: OpeningState(open=True, changed_at=at(12, 0))},
    )
    assert gates.closed(config, world, living_room(config)) == (
        Reason.MASTER_DISABLED,
        Reason.OPENING_OPEN,
        Reason.NOBODY_HOME,
    )


def test_the_first_gate_is_the_reason_the_verdict_gives() -> None:
    """Two functions, one truth. Drift here and the sensors contradict each other."""
    config = house()
    world = make_world(
        now=at(12, 1),
        residents={"danny": away(), "nancy": away()},
        master_enabled=False,
        openings={BACK_DOOR: OpeningState(open=True, changed_at=at(12, 0))},
    )
    zone = living_room(config)
    assert gates.evaluate(config, world, zone).reason is gates.closed(config, world, zone)[0]


def test_an_empty_house_is_named_once_and_not_three_times() -> None:
    """Nobody home makes awake and schedule meaningless; those are consequences."""
    base = house()
    config = DirectorConfig(
        zones=base.zones,
        circuits=base.circuits,
        residents=(
            Resident(
                resident_id="danny",
                name="Danny",
                presence_entity="person.danny",
                windows=office_hours(),
            ),
        ),
        openings=base.openings,
        gates=GateSettings(require_awake=True, require_schedule=True),
        outdoor_sensor=base.outdoor_sensor,
    )
    world = make_world(now=at(20, 0), residents={"danny": away()})
    assert gates.closed(config, world, living_room(config)) == (Reason.NOBODY_HOME,)


def test_asleep_and_outside_the_schedule_are_both_named() -> None:
    """Two independent gates, both genuinely shut, both worth fixing."""
    base = house()
    config = DirectorConfig(
        zones=base.zones,
        circuits=base.circuits,
        residents=(
            Resident(
                resident_id="danny",
                name="Danny",
                presence_entity="person.danny",
                sleep_entity="sensor.danny_charger_type",
                sleep_state="wireless",
                windows=office_hours(),
            ),
        ),
        openings=base.openings,
        gates=GateSettings(require_awake=True, require_schedule=True),
        outdoor_sensor=base.outdoor_sensor,
    )
    world = make_world(now=at(20, 0), residents={"danny": asleep()})
    assert gates.closed(config, world, living_room(config)) == (
        Reason.EVERYONE_ASLEEP,
        Reason.OUTSIDE_SCHEDULE,
    )


def test_a_running_request_leaves_the_gates_about_people_out() -> None:
    """They no longer apply, and naming them would suggest an obstacle that is not there."""
    config = house()
    world = make_world(
        now=at(12, 0),
        residents={"danny": away(), "nancy": away()},
        precondition_until={"woonkamer": at(16)},
    )
    assert gates.closed(config, world, living_room(config)) == ()


def test_a_window_still_counts_during_a_request() -> None:
    config = house()
    world = make_world(
        now=at(12, 1),
        residents={"danny": away(), "nancy": away()},
        openings={BACK_DOOR: OpeningState(open=True, changed_at=at(12, 0))},
        precondition_until={"woonkamer": at(16)},
    )
    assert gates.closed(config, world, living_room(config)) == (Reason.OPENING_OPEN,)


def test_an_empty_room_is_named_alongside_the_household() -> None:
    """The narrowest gate is reached even when a broader one already shut."""
    base = house()
    attic = Zone(
        zone_id="zolder",
        name="Zolder",
        indoor_sensor="sensor.zolder_temperatuur",
        sources=base.zones[1].sources,
        heat=base.zones[1].heat,
        presence_entity="binary_sensor.zolder_aanwezig",
    )
    config = DirectorConfig(
        zones=(attic,),
        circuits=base.circuits,
        residents=base.residents,
        openings=base.openings,
        gates=GateSettings(require_awake=True),
        outdoor_sensor=base.outdoor_sensor,
    )
    world = make_world(
        residents={"danny": asleep(), "nancy": asleep()},
        presence={"zolder": PresenceState(occupied=False)},
    )
    assert gates.closed(config, world, attic) == (
        Reason.EVERYONE_ASLEEP,
        Reason.ZONE_UNOCCUPIED,
    )


def test_a_room_gated_zone_keeps_the_household_out_of_it() -> None:
    """`PRESENCE` says the room decides; the people gates never get a say."""
    base = house()
    attic = Zone(
        zone_id="zolder",
        name="Zolder",
        indoor_sensor="sensor.zolder_temperatuur",
        sources=base.zones[1].sources,
        heat=base.zones[1].heat,
        gate=ZoneGate.PRESENCE,
        presence_entity="binary_sensor.zolder_aanwezig",
    )
    config = DirectorConfig(
        zones=(attic,),
        circuits=base.circuits,
        residents=base.residents,
        openings=base.openings,
        gates=GateSettings(require_awake=True),
        outdoor_sensor=base.outdoor_sensor,
    )
    world = make_world(
        residents={"danny": away(), "nancy": away()},
        presence={"zolder": PresenceState(occupied=False)},
    )
    assert gates.closed(config, world, attic) == (Reason.ZONE_UNOCCUPIED,)


def test_quiet_hours_join_the_list() -> None:
    base = house()
    config = DirectorConfig(
        zones=base.zones,
        circuits=base.circuits,
        residents=base.residents,
        openings=base.openings,
        gates=GateSettings(
            require_awake=True,
            quiet_windows=(TimeWindow(time(21, 0), time(9, 0)),),
        ),
        outdoor_sensor=base.outdoor_sensor,
    )
    world = make_world(now=at(22, 0), residents={"danny": asleep(), "nancy": asleep()})
    assert gates.closed(config, world, living_room(config)) == (
        Reason.QUIET_HOURS,
        Reason.EVERYONE_ASLEEP,
    )


def test_the_plan_carries_the_list_to_the_binding_layer() -> None:
    """Without this the sensors have nothing to show."""
    from custom_components.climate_director.engine import decide

    config = house()
    world = make_world(residents={"danny": away(), "nancy": away()}, master_enabled=False)
    plan = decide(config, world)
    decision = plan.decision_for("woonkamer")
    assert decision is not None
    assert decision.closed_gates == (Reason.MASTER_DISABLED, Reason.NOBODY_HOME)


def test_a_zone_that_carries_on_reports_an_empty_list() -> None:
    from custom_components.climate_director.engine import decide

    config = house()
    world = make_world(
        residents=everyone_up(),
        indoor={"sensor.temperatuur_sensor_woonkamer_selectie": 18.0},
        outdoor=10.0,
        now=at(12, 0) - timedelta(0),
    )
    plan = decide(config, world)
    decision = plan.decision_for("woonkamer")
    assert decision is not None
    assert decision.closed_gates == ()


class TestItDoesNotSetOffTheDecisionEvent:
    """De koppelingslaag vuurt alleen bij een veránderd besluit.

    `_fire_events` vergelijkt de nieuwe beslissing met de vorige en zwijgt als
    ze gelijk zijn - anders verzuipt elke automatisering die meeluistert. Gaat
    er een tweede poort dicht terwijl de eerste al dicht stond, dan verandert
    er voor zo'n automatisering niets: de reden is dezelfde, het gevolg ook.
    Daarom telt de lijst niet mee in de gelijkheid.

    The binding layer only fires on a changed decision.

    `_fire_events` compares the new decision with the previous one and stays
    quiet when they are equal - otherwise every automation listening drowns. A
    second gate shutting while the first already stood shut changes nothing for
    such an automation: same reason, same outcome. Hence the list is left out
    of equality.
    """

    def _decision(self, *gates_shut: Reason) -> object:
        from custom_components.climate_director.engine import ModeFamily
        from custom_components.climate_director.engine.plan import ZoneDecision

        return ZoneDecision(
            zone_id="woonkamer",
            wanted=ModeFamily.NEUTRAL,
            granted=ModeFamily.NEUTRAL,
            reason=Reason.NOBODY_HOME,
            closed_gates=gates_shut,
        )

    def test_a_second_shut_gate_is_not_a_new_decision(self) -> None:
        assert self._decision(Reason.NOBODY_HOME) == self._decision(
            Reason.NOBODY_HOME, Reason.ZONE_UNOCCUPIED
        )

    def test_a_different_reason_still_is(self) -> None:
        """The reason does count; it moves the moment the topmost gate changes."""
        from custom_components.climate_director.engine import ModeFamily
        from custom_components.climate_director.engine.plan import ZoneDecision

        other = ZoneDecision(
            zone_id="woonkamer",
            wanted=ModeFamily.NEUTRAL,
            granted=ModeFamily.NEUTRAL,
            reason=Reason.MASTER_DISABLED,
        )
        assert self._decision(Reason.NOBODY_HOME) != other
