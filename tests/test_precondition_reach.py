"""Hoe ver een vooruit-verzoek reikt, en waar het ophoudt.

How far a pre-conditioning request reaches, and where it stops.

Een verzoek is met de hand gegeven en het is het enige dat een leeg huis mag
laten draaien. Het mag daarom meer dan de gewone regeling - maar niet alles, en
juist die grens moet vastliggen.

A request is given by hand and is the only thing allowed to run an empty house.
It may therefore do more than ordinary regulation - but not everything, and it
is exactly that boundary that has to be pinned down.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from conftest import MONDAY_NOON, awake, climate, make_world

from custom_components.climate_director.engine import (
    MODE_COOL,
    MODE_HEAT,
    DirectorConfig,
    ModeSettings,
    Opening,
    OutdoorWindow,
    Reason,
    Season,
    Source,
    SourceRole,
    Zone,
    decide,
)
from custom_components.climate_director.engine.world import OpeningState

AIRCO = "climate.airco"
GAS = "climate.gas"
WINDOW = "binary_sensor.raam"

#: Verwarmen mag tot 19 buiten, koelen vanaf 24. Daartussen doet de gewone
#: regeling niets - dat is het gat dat een verzoek moet kunnen overbruggen.
HEAT = ModeSettings(target=21.0, start_at=20.0, hysteresis=1.0, outdoor=OutdoorWindow(maximum=19.0))
COOL = ModeSettings(
    target=23.0,
    start_at=24.0,
    hysteresis=1.0,
    outdoor=OutdoorWindow(minimum=24.0),
    seasons=(Season.SUMMER,),
)

CONFIG = DirectorConfig(
    zones=(
        Zone(
            zone_id="woonkamer",
            name="Woonkamer",
            indoor_sensor="sensor.wk",
            sources=(
                Source(source_id="airco", entity_id=AIRCO, outdoor=OutdoorWindow(minimum=3.1)),
                Source(
                    source_id="gas",
                    entity_id=GAS,
                    role=SourceRole.HEAT_ONLY,
                    priority=1,
                    outdoor=OutdoorWindow(maximum=3.1),
                ),
            ),
            heat=HEAT,
            cool=COOL,
        ),
    ),
    openings=(Opening(entity_id=WINDOW, zone_ids=("woonkamer",)),),
)


def world(*, indoor, outdoor, asking=False, bypass=False, window_open=False, season=Season.SUMMER):
    """Return a world with nobody home, and optionally a request running."""
    return make_world(
        now=MONDAY_NOON,
        indoor={"woonkamer": indoor},
        outdoor=outdoor,
        season=season,
        climates={AIRCO: climate("off"), GAS: climate("off")},
        residents={"danny": awake(home=False)},
        openings={
            WINDOW: OpeningState(open=window_open, changed_at=MONDAY_NOON - timedelta(hours=1))
        },
        precondition_until={"woonkamer": MONDAY_NOON + timedelta(hours=1)} if asking else {},
        precondition_bypass=frozenset({"woonkamer"}) if bypass else frozenset(),
    )


def outcome(**kwargs):
    """Return the commanded mode per entity, plus the zone's reason."""
    plan = decide(CONFIG, world(**kwargs))
    return (
        {command.entity_id: command.hvac_mode for command in plan.commands},
        plan.zones[0].reason,
    )


class TestTheGapBetweenTheWindows:
    """Verwarmen mag tot 19, koelen vanaf 24 - en daartussen gebeurde niets."""

    def test_ordinary_regulation_does_nothing_in_the_gap(self) -> None:
        """Nobody home and no request: the zone stays out of it entirely."""
        _, reason = outcome(indoor=18.0, outdoor=21.0)
        assert reason is not Reason.REGULATING

    def test_a_request_reaches_into_the_gap(self) -> None:
        """21 C outside is too warm to heat by the rules, but the room is cold."""
        commands, reason = outcome(indoor=18.0, outdoor=21.0, asking=True)
        assert commands[AIRCO] == MODE_HEAT
        assert reason is Reason.REGULATING

    def test_it_reaches_the_other_way_too(self) -> None:
        """Warm room, mild outside: cooling was not allowed below 24 C."""
        commands, _ = outcome(indoor=26.0, outdoor=21.0, asking=True)
        assert commands[AIRCO] == MODE_COOL

    @pytest.mark.parametrize("outdoor", [-10.0, 0.0, 3.0])
    def test_the_source_window_still_picks_the_appliance(self, outdoor: float) -> None:
        """The zone's window lapses; the one per source does not."""
        commands, _ = outcome(indoor=18.0, outdoor=outdoor, asking=True, season=Season.WINTER)
        assert commands[GAS] == MODE_HEAT, "onder 3,1 hoort het gas te draaien"
        assert commands.get(AIRCO) != MODE_HEAT


class TestWhatARequestStillObeys:
    """Wat er wél blijft gelden, want een verzoek is geen vrijbrief."""

    def test_the_dead_band_still_holds(self) -> None:
        """A comfortable room needs nothing, however hard somebody asks."""
        commands, _ = outcome(indoor=22.0, outdoor=21.0, asking=True)
        assert commands.get(AIRCO) != MODE_HEAT
        assert commands.get(AIRCO) != MODE_COOL

    def test_the_season_still_holds(self) -> None:
        """Cooling is configured for summer only."""
        commands, _ = outcome(indoor=26.0, outdoor=21.0, asking=True, season=Season.WINTER)
        assert commands.get(AIRCO) != MODE_COOL


class TestAnOpenWindow:
    """Standaard weigeren, tenzij iemand uitdrukkelijk zegt: toch doen."""

    def test_it_refuses_by_default(self) -> None:
        commands, reason = outcome(indoor=18.0, outdoor=21.0, asking=True, window_open=True)
        assert reason is Reason.OPENING_OPEN
        assert commands.get(AIRCO) != MODE_HEAT

    def test_the_bypass_lets_it_through(self) -> None:
        commands, reason = outcome(
            indoor=18.0, outdoor=21.0, asking=True, window_open=True, bypass=True
        )
        assert reason is Reason.REGULATING
        assert commands[AIRCO] == MODE_HEAT

    def test_the_bypass_does_nothing_without_a_request(self) -> None:
        """A stale flag must never open the window gate on its own.

        De overbrugging hoort bij een verzoek. Blijft hij per ongeluk staan
        zonder verzoek, dan mag hij niets - anders is een raam voorgoed geen
        rem meer.

        The bypass belongs to a request. If it lingers by accident without one
        it must do nothing - otherwise a window stops being a brake for good.
        """
        _, reason = outcome(indoor=18.0, outdoor=15.0, window_open=True, bypass=True)
        assert reason is Reason.OPENING_OPEN

    def test_a_closed_window_needs_no_bypass(self) -> None:
        commands, _ = outcome(indoor=18.0, outdoor=21.0, asking=True, window_open=False)
        assert commands[AIRCO] == MODE_HEAT


class TestTheTargetMustSitInsideItsOwnBand:
    """Een streven aan de verkeerde kant van het aanpunt doet niets.

    De zone start keurig en zet het apparaat dan op een temperatuur waar het
    niets voor hoeft te doen. Van buiten lijkt dat op een apparaat dat weigert,
    en daar ga je een defect voor zoeken dat er niet is.

    The zone starts dutifully and then sets the appliance to a temperature it
    need do nothing for. From the outside that looks like an appliance
    refusing, and you go hunting a fault that is not there.
    """

    def _zone(self, **modes) -> DirectorConfig:
        return DirectorConfig(
            zones=(
                Zone(
                    zone_id="a",
                    name="A",
                    indoor_sensor="sensor.a",
                    sources=(Source(source_id="s", entity_id=AIRCO),),
                    **modes,
                ),
            )
        )

    def test_heating_aiming_below_its_switch_on_point(self) -> None:
        from custom_components.climate_director.engine import validate

        config = self._zone(heat=ModeSettings(target=19.0, start_at=22.0, hysteresis=1.0))
        assert any(getattr(item, "code", "") == "target_outside_band" for item in validate(config))

    def test_cooling_aiming_above_its_switch_on_point(self) -> None:
        from custom_components.climate_director.engine import validate

        config = self._zone(cool=ModeSettings(target=27.0, start_at=24.0, hysteresis=1.0))
        assert any(getattr(item, "code", "") == "target_outside_band" for item in validate(config))

    def test_a_sound_pair_is_quiet(self) -> None:
        """The user's own numbers: heat 22->23, cool 24->23."""
        from custom_components.climate_director.engine import validate

        config = self._zone(
            heat=ModeSettings(target=23.0, start_at=22.0, hysteresis=1.0),
            cool=ModeSettings(target=23.0, start_at=24.0, hysteresis=1.0),
        )
        codes = [getattr(item, "code", "") for item in validate(config)]
        assert "target_outside_band" not in codes

    def test_target_equal_to_the_switch_on_point_is_allowed(self) -> None:
        """A zero-width intent is odd but not contradictory."""
        from custom_components.climate_director.engine import validate

        config = self._zone(heat=ModeSettings(target=22.0, start_at=22.0, hysteresis=1.0))
        codes = [getattr(item, "code", "") for item in validate(config)]
        assert "target_outside_band" not in codes
