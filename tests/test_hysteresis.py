"""Tests voor de dode band: wanneer start en stopt een taak.

Tests for the dead band: when a duty starts and stops.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from conftest import at, house, living_room_cool, living_room_heat, make_world

from custom_components.climate_director.engine import (
    ModeFamily,
    ModeSettings,
    OutdoorWindow,
    Reason,
    Season,
    Source,
    SourceRole,
    Zone,
    hysteresis,
)


def zone_with(**kwargs: object) -> Zone:
    """Return a bare zone carrying only the settings under test."""
    return Zone(
        zone_id="z",
        name="Z",
        indoor_sensor="sensor.t",
        sources=(Source("s", "climate.x"),),
        **kwargs,  # type: ignore[arg-type]
    )


def evaluate(zone: Zone, indoor: float | None, running: ModeFamily, **world_kwargs: object):
    world = make_world(indoor={"z": indoor}, **world_kwargs)  # type: ignore[arg-type]
    return hysteresis.evaluate(zone, world, running)


class TestHeating:
    """Heating starts at `start_at` and stops at `start_at + hysteresis`."""

    zone = zone_with(heat=ModeSettings(target=21.0, start_at=20.0, hysteresis=1.0))

    def test_starts_at_or_below_the_switch_on_point(self) -> None:
        assert evaluate(self.zone, 20.0, ModeFamily.NEUTRAL).family is ModeFamily.HEAT
        assert evaluate(self.zone, 19.0, ModeFamily.NEUTRAL).family is ModeFamily.HEAT

    def test_does_not_start_inside_the_band(self) -> None:
        demand = evaluate(self.zone, 20.5, ModeFamily.NEUTRAL)
        assert demand.family is ModeFamily.NEUTRAL
        assert demand.reason is Reason.WITHIN_DEADBAND

    def test_keeps_running_inside_the_band(self) -> None:
        assert evaluate(self.zone, 20.5, ModeFamily.HEAT).family is ModeFamily.HEAT

    def test_stops_at_the_far_edge(self) -> None:
        assert evaluate(self.zone, 21.0, ModeFamily.HEAT).family is ModeFamily.NEUTRAL

    def test_deviation_measures_how_far_past_the_switch_on_point(self) -> None:
        assert evaluate(self.zone, 18.0, ModeFamily.NEUTRAL).deviation == pytest.approx(2.0)


class TestCooling:
    """Cooling starts at `start_at` and stops at `start_at - hysteresis`."""

    zone = zone_with(cool=ModeSettings(target=22.0, start_at=24.0, hysteresis=1.0))

    def test_starts_at_or_above_the_switch_on_point(self) -> None:
        assert evaluate(self.zone, 24.0, ModeFamily.NEUTRAL).family is ModeFamily.COOL
        assert evaluate(self.zone, 26.0, ModeFamily.NEUTRAL).family is ModeFamily.COOL

    def test_does_not_start_inside_the_band(self) -> None:
        assert evaluate(self.zone, 23.5, ModeFamily.NEUTRAL).family is ModeFamily.NEUTRAL

    def test_keeps_running_inside_the_band(self) -> None:
        assert evaluate(self.zone, 23.5, ModeFamily.COOL).family is ModeFamily.COOL

    def test_stops_at_the_far_edge(self) -> None:
        assert evaluate(self.zone, 23.0, ModeFamily.COOL).family is ModeFamily.NEUTRAL


class TestZeroBandChatters:
    """The failure mode the dead band exists to prevent, pinned down."""

    zone = zone_with(heat=ModeSettings(target=23.0, start_at=23.0, hysteresis=0.0))

    def test_on_and_off_collapse_onto_one_value(self) -> None:
        assert evaluate(self.zone, 23.0, ModeFamily.NEUTRAL).family is ModeFamily.HEAT
        assert evaluate(self.zone, 23.0, ModeFamily.HEAT).family is ModeFamily.NEUTRAL

    def test_a_band_separates_them(self) -> None:
        banded = zone_with(heat=ModeSettings(target=23.0, start_at=23.0, hysteresis=1.0))
        assert evaluate(banded, 23.0, ModeFamily.HEAT).family is ModeFamily.HEAT


class TestWhyNothingHappens:
    """Binnen de band of eroverheen: twee antwoorden, niet één.

    `satisfied` betekent "de kamer is er voorbij"; `within_deadband` betekent
    "de kamer ligt in de band en wacht tot het startpunt weer gehaald wordt".
    Zonder dat onderscheid ziet iemand met 20,5 graden en een startpunt van 20
    alleen "al goed" staan, terwijl de verwarming juist net gestopt is.

    Inside the band or past it: two answers, not one. `satisfied` means "the
    room is past it"; `within_deadband` means "the room sits inside the band,
    waiting for the switch-on point again". Without that distinction somebody
    at 20.5 degrees with a switch-on point of 20 only sees "already right",
    while the heating in fact just stopped.
    """

    heating = zone_with(heat=ModeSettings(target=21.0, start_at=20.0, hysteresis=1.0))
    cooling = zone_with(cool=ModeSettings(target=22.0, start_at=24.0, hysteresis=1.0))

    def test_heating_past_the_far_edge_is_satisfied(self) -> None:
        assert evaluate(self.heating, 21.5, ModeFamily.NEUTRAL).reason is Reason.SATISFIED
        assert evaluate(self.heating, 21.0, ModeFamily.NEUTRAL).reason is Reason.SATISFIED

    def test_heating_inside_the_band_says_so(self) -> None:
        assert evaluate(self.heating, 20.5, ModeFamily.NEUTRAL).reason is Reason.WITHIN_DEADBAND

    def test_cooling_inside_the_band_says_so(self) -> None:
        assert evaluate(self.cooling, 23.5, ModeFamily.NEUTRAL).reason is Reason.WITHIN_DEADBAND

    def test_cooling_past_the_far_edge_is_satisfied(self) -> None:
        assert evaluate(self.cooling, 22.5, ModeFamily.NEUTRAL).reason is Reason.SATISFIED

    def test_a_running_duty_that_stops_is_simply_satisfied(self) -> None:
        """Wie stopt, staat op de verre rand - niet erbinnen."""
        assert evaluate(self.heating, 21.0, ModeFamily.HEAT).reason is Reason.SATISFIED
        assert evaluate(self.cooling, 23.0, ModeFamily.COOL).reason is Reason.SATISFIED

    def test_without_a_band_there_is_nothing_to_sit_inside(self) -> None:
        zone = zone_with(heat=ModeSettings(target=21.0, start_at=20.0, hysteresis=0.0))
        assert evaluate(zone, 20.5, ModeFamily.NEUTRAL).reason is Reason.SATISFIED


class TestRefusals:
    def test_unknown_indoor_temperature(self) -> None:
        zone = zone_with(heat=ModeSettings(21.0, 20.0))
        demand = evaluate(zone, None, ModeFamily.NEUTRAL)
        assert demand.reason is Reason.NO_INDOOR_TEMPERATURE

    def test_season_blocks_the_mode(self) -> None:
        zone = zone_with(cool=living_room_cool())
        demand = evaluate(zone, 30.0, ModeFamily.NEUTRAL, outdoor=30.0, season=Season.WINTER)
        assert demand.reason is Reason.SEASON_BLOCKS_MODE

    def test_outdoor_window_blocks_the_mode(self) -> None:
        zone = zone_with(heat=living_room_heat())
        demand = evaluate(zone, 15.0, ModeFamily.NEUTRAL, outdoor=25.0)
        assert demand.reason is Reason.OUTDOOR_OUTSIDE_WINDOW

    def test_unconfigured_mode_is_the_least_useful_refusal(self) -> None:
        """A real cause outranks "you never set this up"."""
        zone = zone_with(cool=living_room_cool())
        demand = evaluate(zone, 30.0, ModeFamily.NEUTRAL, outdoor=30.0, season=Season.WINTER)
        assert demand.reason is not Reason.MODE_NOT_CONFIGURED

    def test_nothing_configured_at_all(self) -> None:
        demand = evaluate(zone_with(), 20.0, ModeFamily.NEUTRAL)
        assert demand.reason is Reason.MODE_NOT_CONFIGURED

    def test_bounded_window_needs_a_known_outdoor_temperature(self) -> None:
        zone = zone_with(heat=ModeSettings(21.0, 20.0, outdoor=OutdoorWindow(maximum=19.0)))
        demand = evaluate(zone, 15.0, ModeFamily.NEUTRAL, outdoor=None)
        assert demand.reason is Reason.NO_OUTDOOR_TEMPERATURE


class TestAnOutdoorBoundOnlyHoldsBackItsOwnDuty:
    """Een grens op koelen mag verwarmen niet stilleggen, en omgekeerd.

    An outdoor bound on cooling must not silence heating, and vice versa.
    """

    @staticmethod
    def zone_with_bound(bound_on: str) -> Zone:
        """Return a zone with a heat and a cool source, one of which carries a bound."""
        heat_outdoor = OutdoorWindow(maximum=19.0) if bound_on == "zone_heat" else OutdoorWindow()
        cool_outdoor = OutdoorWindow(maximum=19.0) if bound_on == "zone_cool" else OutdoorWindow()
        heat_source_outdoor = (
            OutdoorWindow(maximum=19.0) if bound_on == "heat_source" else OutdoorWindow()
        )
        cool_source_outdoor = (
            OutdoorWindow(maximum=19.0) if bound_on == "cool_source" else OutdoorWindow()
        )
        return Zone(
            zone_id="z",
            name="Z",
            indoor_sensor="sensor.t",
            sources=(
                Source(
                    "heat_s",
                    "climate.heat_s",
                    role=SourceRole.HEAT_ONLY,
                    outdoor=heat_source_outdoor,
                ),
                Source(
                    "cool_s",
                    "climate.cool_s",
                    role=SourceRole.COOL_ONLY,
                    outdoor=cool_source_outdoor,
                ),
            ),
            heat=ModeSettings(21.0, 20.0, outdoor=heat_outdoor),
            cool=ModeSettings(23.0, 24.0, outdoor=cool_outdoor),
        )

    @pytest.mark.parametrize(
        ("bound_on", "family", "indoor", "refused"),
        [
            ("zone_heat", ModeFamily.HEAT, 15.0, True),
            ("zone_heat", ModeFamily.COOL, 26.0, False),
            ("zone_cool", ModeFamily.HEAT, 15.0, False),
            ("zone_cool", ModeFamily.COOL, 26.0, True),
            ("heat_source", ModeFamily.HEAT, 15.0, True),
            ("heat_source", ModeFamily.COOL, 26.0, False),
            ("cool_source", ModeFamily.HEAT, 15.0, False),
            ("cool_source", ModeFamily.COOL, 26.0, True),
        ],
        ids=lambda value: value.value if isinstance(value, ModeFamily) else str(value),
    )
    def test_the_bound_only_refuses_its_own_duty(
        self, bound_on: str, family: ModeFamily, indoor: float, refused: bool
    ) -> None:
        zone = self.zone_with_bound(bound_on)
        world = make_world(indoor={"z": indoor}, outdoor=None)
        demand = hysteresis._candidate(zone, world, family, indoor, ModeFamily.NEUTRAL)
        if refused:
            assert demand.reason is Reason.NO_OUTDOOR_TEMPERATURE
        else:
            assert demand.reason is not Reason.NO_OUTDOOR_TEMPERATURE
            assert demand.family is family


class TestOverlappingSetpoints:
    """A misconfiguration where heating and cooling both want to run."""

    zone = zone_with(
        heat=ModeSettings(target=24.0, start_at=25.0, hysteresis=1.0),
        cool=ModeSettings(target=20.0, start_at=20.0, hysteresis=1.0),
    )

    def test_the_running_duty_keeps_the_zone(self) -> None:
        assert evaluate(self.zone, 22.0, ModeFamily.COOL).family is ModeFamily.COOL
        assert evaluate(self.zone, 22.0, ModeFamily.HEAT).family is ModeFamily.HEAT

    def test_otherwise_the_larger_deviation_wins(self) -> None:
        # 21 is 4 below the heating point and 1 above the cooling point.
        assert evaluate(self.zone, 21.0, ModeFamily.NEUTRAL).family is ModeFamily.HEAT


def test_living_room_settings_match_the_original_thresholds() -> None:
    """On at 22 or below, off at 23 or above - the summer branch, with a band."""
    config = house()
    zone = config.zone("woonkamer")
    assert zone is not None
    world = lambda indoor: make_world(  # noqa: E731
        indoor={"woonkamer": indoor}, outdoor=10.0, season=Season.WINTER
    )
    assert hysteresis.evaluate(zone, world(22.0), ModeFamily.NEUTRAL).family is ModeFamily.HEAT
    assert hysteresis.evaluate(zone, world(22.5), ModeFamily.NEUTRAL).family is ModeFamily.NEUTRAL
    assert hysteresis.evaluate(zone, world(22.5), ModeFamily.HEAT).family is ModeFamily.HEAT
    assert hysteresis.evaluate(zone, world(23.0), ModeFamily.HEAT).family is ModeFamily.NEUTRAL


class TestARequestSkipsTheOutdoorBoundAtEveryHour:
    """Geen venster meer: een verzoek slaat de buitengrens op elk uur over.

    No window anymore: a request skips the outdoor bound at every hour.
    """

    zone = zone_with(heat=ModeSettings(21.0, 20.0, outdoor=OutdoorWindow(maximum=19.0)))

    @pytest.mark.parametrize(("hour", "minute"), [(3, 0), (12, 0), (23, 30)])
    def test_the_bound_is_skipped(self, hour: int, minute: int) -> None:
        now = at(hour, minute)
        world = make_world(
            now=now,
            outdoor=25.0,
            indoor={"z": 15.0},
            precondition_until={"z": now + timedelta(minutes=30)},
        )
        demand = hysteresis.evaluate(self.zone, world, ModeFamily.NEUTRAL)
        assert demand.family is ModeFamily.HEAT
