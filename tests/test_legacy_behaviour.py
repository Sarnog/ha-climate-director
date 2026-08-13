"""De bestaande automatiseringen, uitgeschreven als scenario's.

The existing automations, written out as scenarios.

Elke test hieronder komt overeen met gedrag dat nu in Home Assistant in
automatiseringen en scripts vastligt. Samen vormen ze de meetlat voor fase 2:
draait de engine in schaduwmodus mee, dan hoort hij op elk van deze momenten
hetzelfde te besluiten als de bestaande opzet.

Every test below matches behaviour currently living in Home Assistant
automations and scripts. Together they are the yardstick for phase 2: with the
engine running alongside in shadow mode, it should decide the same thing as the
existing setup at each of these moments.
"""

from __future__ import annotations

from datetime import timedelta

from conftest import (
    ATTIC,
    BACK_DOOR,
    BEDROOM,
    GAS,
    LIVING,
    asleep,
    at,
    awake,
    away,
    climate,
    everyone_up,
    house,
    make_world,
)

from custom_components.climate_director.engine import (
    MODE_COOL,
    MODE_HEAT,
    MODE_OFF,
    OpeningState,
    Reason,
    Season,
    decide,
)

ALL_UNITS = (GAS, LIVING, ATTIC, BEDROOM)


def world(
    *,
    outdoor: float,
    living: float,
    season: Season = Season.WINTER,
    modes: dict[str, str] | None = None,
    residents: dict | None = None,
    **kwargs: object,
):
    """Return a world for the existing installation."""
    running = {entity_id: MODE_OFF for entity_id in ALL_UNITS}
    running.update(modes or {})
    return make_world(
        outdoor=outdoor,
        season=season,
        indoor={"woonkamer": living, "zolder": living, "slaapkamer": living},
        climates={entity_id: climate(mode) for entity_id, mode in running.items()},
        residents=residents if residents is not None else everyone_up(),
        **kwargs,  # type: ignore[arg-type]
    )


def modes_of(plan) -> dict[str, str]:
    return {command.entity_id: command.hvac_mode for command in plan.commands}


class TestHeatSourceCutover:
    """Automation 1778524556831: switching between boiler and heat pump."""

    def test_boiler_hands_over_to_the_heat_pump_when_it_warms_up(self) -> None:
        plan = decide(house(), world(outdoor=5.0, living=20.0, modes={GAS: MODE_HEAT}))
        modes = modes_of(plan)
        assert modes[GAS] == MODE_OFF
        assert modes[LIVING] == MODE_HEAT

    def test_heat_pump_hands_back_to_the_boiler_when_it_freezes(self) -> None:
        plan = decide(house(), world(outdoor=1.0, living=20.0, modes={LIVING: MODE_HEAT}))
        modes = modes_of(plan)
        assert modes[LIVING] == MODE_OFF
        assert modes[GAS] == MODE_HEAT

    def test_the_secondary_units_are_forced_off_on_handover(self) -> None:
        """The original automations did this by hand, nineteen times over."""
        plan = decide(
            house(),
            world(outdoor=1.0, living=20.0, modes={LIVING: MODE_HEAT, ATTIC: MODE_HEAT}),
        )
        modes = modes_of(plan)
        assert modes[ATTIC] == MODE_OFF
        assert modes[BEDROOM] == MODE_OFF


class TestNeutralWeather:
    """Automation 1778524556831: everything off between the two windows."""

    def test_too_warm_to_heat_and_too_cold_to_cool(self) -> None:
        plan = decide(
            house(),
            world(outdoor=21.0, living=22.0, season=Season.SUMMER, modes={LIVING: MODE_HEAT}),
        )
        assert all(mode == MODE_OFF for mode in modes_of(plan).values())

    def test_the_reason_names_the_outdoor_window(self) -> None:
        plan = decide(house(), world(outdoor=21.0, living=22.0, season=Season.SUMMER))
        decision = plan.decision_for("woonkamer")
        assert decision is not None
        assert decision.reason is Reason.OUTDOOR_OUTSIDE_WINDOW


class TestIndoorLimits:
    """Automation 1778524556831: stop once the room has come round."""

    def test_heating_stops_when_the_room_is_warm_enough(self) -> None:
        plan = decide(house(), world(outdoor=5.0, living=23.0, modes={LIVING: MODE_HEAT}))
        assert modes_of(plan)[LIVING] == MODE_OFF

    def test_cooling_stops_when_the_room_is_cool_enough(self) -> None:
        plan = decide(
            house(),
            world(
                outdoor=28.0,
                living=23.0,
                season=Season.SUMMER,
                modes={LIVING: MODE_COOL},
            ),
        )
        assert modes_of(plan)[LIVING] == MODE_OFF

    def test_heating_keeps_going_inside_the_dead_band(self) -> None:
        """The original winter branch had no band here and could chatter."""
        plan = decide(house(), world(outdoor=5.0, living=22.5, modes={LIVING: MODE_HEAT}))
        assert modes_of(plan)[LIVING] == MODE_HEAT


class TestColdStart:
    """Automation 1770710173972: starting from everything off."""

    def test_the_boiler_starts_below_the_cutover(self) -> None:
        plan = decide(house(), world(outdoor=1.0, living=20.0))
        assert modes_of(plan)[GAS] == MODE_HEAT

    def test_the_heat_pump_starts_above_it(self) -> None:
        plan = decide(house(), world(outdoor=10.0, living=20.0))
        assert modes_of(plan)[LIVING] == MODE_HEAT

    def test_cooling_starts_in_summer_when_it_is_hot_both_sides(self) -> None:
        plan = decide(house(), world(outdoor=28.0, living=26.0, season=Season.SUMMER))
        assert modes_of(plan)[LIVING] == MODE_COOL

    def test_no_cooling_in_winter_however_hot_it_gets(self) -> None:
        """The season sensor gated this in the original setup too."""
        plan = decide(house(), world(outdoor=28.0, living=26.0, season=Season.WINTER))
        assert modes_of(plan)[LIVING] == MODE_OFF


class TestPresence:
    """Automations 1698780639730, 1698780956791, 1670602387793, 1670602406347."""

    def test_the_last_person_leaving_shuts_everything_down(self) -> None:
        plan = decide(
            house(),
            world(
                outdoor=5.0,
                living=20.0,
                modes={LIVING: MODE_HEAT},
                residents={"danny": away(), "nancy": away()},
            ),
        )
        assert all(mode == MODE_OFF for mode in modes_of(plan).values())

    def test_one_person_staying_home_keeps_it_running(self) -> None:
        plan = decide(
            house(),
            world(
                outdoor=5.0,
                living=20.0,
                modes={LIVING: MODE_HEAT},
                residents={"danny": away(), "nancy": awake()},
            ),
        )
        assert modes_of(plan)[LIVING] == MODE_HEAT

    def test_coming_home_starts_it_again(self) -> None:
        """Automation 1740085447392."""
        plan = decide(
            house(),
            world(outdoor=5.0, living=20.0, residents={"danny": awake(), "nancy": away()}),
        )
        assert modes_of(plan)[LIVING] == MODE_HEAT


class TestSleep:
    """Automations 1698790293237 and 1698790358170: bedtime."""

    def test_everyone_asleep_shuts_it_down(self) -> None:
        plan = decide(
            house(),
            world(
                outdoor=5.0,
                living=20.0,
                modes={LIVING: MODE_HEAT},
                residents={"danny": asleep(), "nancy": asleep()},
            ),
        )
        assert all(mode == MODE_OFF for mode in modes_of(plan).values())

    def test_one_person_still_up_keeps_it_running(self) -> None:
        plan = decide(
            house(),
            world(
                outdoor=5.0,
                living=20.0,
                residents={"danny": asleep(), "nancy": awake()},
            ),
        )
        assert modes_of(plan)[LIVING] == MODE_HEAT

    def test_getting_up_starts_it_again(self) -> None:
        """Automations 1740085543756 and 1740085635715."""
        plan = decide(
            house(),
            world(outdoor=5.0, living=20.0, residents={"danny": awake(), "nancy": asleep()}),
        )
        assert modes_of(plan)[LIVING] == MODE_HEAT


class TestBackDoor:
    """Automations 1698779803062 and 1670602446395: the door interrupt."""

    def test_open_long_enough_suspends_everything(self) -> None:
        plan = decide(
            house(),
            world(
                outdoor=5.0,
                living=20.0,
                modes={LIVING: MODE_HEAT},
                now=at(12, 1),
                openings={BACK_DOOR: OpeningState(open=True, changed_at=at(12, 0))},
            ),
        )
        assert all(mode == MODE_OFF for mode in modes_of(plan).values())

    def test_briefly_open_changes_nothing(self) -> None:
        plan = decide(
            house(),
            world(
                outdoor=5.0,
                living=20.0,
                modes={LIVING: MODE_HEAT},
                now=at(12, 0) + timedelta(seconds=10),
                openings={BACK_DOOR: OpeningState(open=True, changed_at=at(12, 0))},
            ),
        )
        assert modes_of(plan)[LIVING] == MODE_HEAT

    def test_closing_the_door_restores_the_right_duty_without_any_helper(self) -> None:
        """No mirror booleans and no snapshot scene: the conditions decide again.

        Automation 1702928278931 existed only to remember which mode the living
        room had been in. That whole mechanism disappears here.
        """
        plan = decide(
            house(),
            world(
                outdoor=28.0,
                living=26.0,
                season=Season.SUMMER,
                now=at(12, 5),
                openings={BACK_DOOR: OpeningState(open=False, changed_at=at(12, 4))},
            ),
        )
        assert modes_of(plan)[LIVING] == MODE_COOL


class TestManualOverride:
    """Automation 1702988832917: the manual off button."""

    def test_an_override_stops_the_director_touching_that_zone(self) -> None:
        plan = decide(
            house(),
            world(
                outdoor=5.0,
                living=20.0,
                modes={LIVING: MODE_HEAT},
                zone_overrides={"woonkamer": True},
            ),
        )
        decision = plan.decision_for("woonkamer")
        assert decision is not None
        assert decision.reason is Reason.MANUAL_OVERRIDE

    def test_other_zones_carry_on(self) -> None:
        plan = decide(
            house(),
            world(outdoor=5.0, living=20.0, zone_overrides={"woonkamer": True}),
        )
        attic = plan.decision_for("zolder")
        assert attic is not None
        assert attic.reason is not Reason.MANUAL_OVERRIDE


class TestSafetyInterlock:
    """Automation 1764151296803 was a detector for a state that cannot occur.

    That automation switched everything off whenever the boiler and an air
    conditioner were found running at once. With one decision point, that state
    is not reachable at all - so the sweep below finds nothing to catch.
    """

    def test_the_forbidden_combination_never_appears(self) -> None:
        for outdoor in [-15.0, -1.0, 0.0, 2.5, 3.0, 4.0, 12.0, 18.0, 20.0, 25.0, 30.0]:
            for indoor in [16.0, 20.0, 22.0, 23.0, 24.0, 27.0]:
                for season in (Season.SUMMER, Season.WINTER):
                    plan = decide(house(), world(outdoor=outdoor, living=indoor, season=season))
                    modes = modes_of(plan)
                    boiler_on = modes[GAS] != MODE_OFF
                    pump_on = any(
                        modes[entity_id] != MODE_OFF for entity_id in (LIVING, ATTIC, BEDROOM)
                    )
                    assert not (boiler_on and pump_on), (outdoor, indoor, season)

    def test_one_duty_at_a_time_across_the_multi_split(self) -> None:
        for indoor in [16.0, 20.0, 23.0, 26.0, 30.0]:
            plan = decide(house(), world(outdoor=26.0, living=indoor, season=Season.SUMMER))
            modes = modes_of(plan)
            running = {
                modes[entity_id]
                for entity_id in (LIVING, ATTIC, BEDROOM)
                if modes[entity_id] != MODE_OFF
            }
            assert len(running) <= 1, indoor


class TestSeasonHelper:
    """Automation 1709468855509 maintained a summer/winter helper by date."""

    def test_the_season_is_an_input_rather_than_a_helper_to_maintain(self) -> None:
        hot = world(outdoor=28.0, living=26.0, season=Season.SUMMER)
        cold = world(outdoor=28.0, living=26.0, season=Season.WINTER)
        assert modes_of(decide(house(), hot))[LIVING] == MODE_COOL
        assert modes_of(decide(house(), cold))[LIVING] == MODE_OFF

    def test_an_unknown_season_still_allows_heating(self) -> None:
        """Heating carries no season restriction, so it survives a stale sensor."""
        plan = decide(house(), world(outdoor=5.0, living=20.0, season=Season.UNKNOWN))
        assert modes_of(plan)[LIVING] == MODE_HEAT
