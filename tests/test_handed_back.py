"""Wie bij het apparaat zelf op uit drukt, krijgt die kamer terug.

Whoever presses off on the appliance itself gets that room back.

Het ergste wat deze integratie kan doen is iemand overstemmen die net met de
hand iets heeft uitgezet. Dan staat er twee seconden later weer een airco te
blazen die je expres stil had gezet, en is de conclusie terecht dat het ding
niet deugt. Dus: die zone valt stil tot dezelfde hand hem weer aanzet, of tot de
volgende dag - want een besluit van gisteravond hoort vanochtend niet te gelden.

The worst thing this integration can do is overrule somebody who just switched
something off by hand. Two seconds later an air conditioner you deliberately
silenced is blowing again, and the fair conclusion is that the thing is no good.
So: that zone falls silent until the same hand switches it back on, or until the
next day - since last night's decision should not still hold this morning.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from custom_components.climate_director.coordinator import ClimateDirectorCoordinator
from custom_components.climate_director.engine import (
    DirectorConfig,
    ModeSettings,
    Source,
    Zone,
)
from custom_components.climate_director.engine.plan import Plan, Reason, UnitCommand

LIVING = "climate.huiskamer"
BEDROOM = "climate.master_bedroom"


def config() -> DirectorConfig:
    return DirectorConfig(
        zones=(
            Zone(
                "woonkamer",
                "Woonkamer",
                "sensor.woonkamer",
                sources=(Source("w", LIVING),),
                heat=ModeSettings(21.0, 20.0),
            ),
            Zone(
                "slaapkamer",
                "Slaapkamer",
                "sensor.slaapkamer",
                sources=(Source("s", BEDROOM),),
                heat=ModeSettings(21.0, 20.0),
            ),
        )
    )


class _State:
    def __init__(self, state: str) -> None:
        self.state = state


class _Event:
    """A state change, shaped the way Home Assistant hands one over."""

    def __init__(self, entity_id: str, old: str | None, new: str | None) -> None:
        self.data = {
            "entity_id": entity_id,
            "old_state": None if old is None else _State(old),
            "new_state": None if new is None else _State(new),
        }


def coordinator(plan: Plan | None = None):
    """Return a stand-in carrying only what the notice methods touch."""

    class StandIn:
        def __init__(self) -> None:
            self.config = config()
            self.zone_overrides: dict[str, bool] = {}
            self._handed_back: dict[str, date] = {}
            self.data = plan

        _notice_hand = ClimateDirectorCoordinator._notice_hand
        _zone_of = ClimateDirectorCoordinator._zone_of
        _we_wanted_it_off = ClimateDirectorCoordinator._we_wanted_it_off
        _zones_handed_back = ClimateDirectorCoordinator._zones_handed_back

    return StandIn()


def running_plan(entity_id: str = BEDROOM) -> Plan:
    """Return a plan in which that appliance is meant to be heating."""
    return Plan(commands=(UnitCommand(entity_id=entity_id, hvac_mode="heat"),))


def idle_plan(entity_id: str = BEDROOM) -> Plan:
    """Return a plan in which the director itself stood that appliance down."""
    return Plan(
        commands=(UnitCommand(entity_id=entity_id, hvac_mode="off", reason=Reason.SATISFIED),)
    )


class TestAHandSwitchingItOff:
    def test_the_zone_is_handed_back(self) -> None:
        item = coordinator(running_plan())
        item._notice_hand(_Event(BEDROOM, "heat", "off"))
        assert item._zones_handed_back() == {"slaapkamer"}

    def test_the_other_zones_carry_on(self) -> None:
        item = coordinator(running_plan())
        item._notice_hand(_Event(BEDROOM, "heat", "off"))
        assert "woonkamer" not in item._zones_handed_back()

    @pytest.mark.parametrize("was", ["heat", "cool", "dry", "auto", "heat_cool"])
    def test_from_any_running_mode(self, was: str) -> None:
        item = coordinator(running_plan())
        item._notice_hand(_Event(BEDROOM, was, "off"))
        assert item._zones_handed_back() == {"slaapkamer"}

    @pytest.mark.parametrize("now", ["off", "fan_only"])
    def test_to_any_idle_mode(self, now: str) -> None:
        """Fan only is not climate control either, whatever the appliance calls it."""
        item = coordinator(running_plan())
        item._notice_hand(_Event(BEDROOM, "heat", now))
        assert item._zones_handed_back() == {"slaapkamer"}


class TestWhatDoesNotCount:
    def test_our_own_command_is_not_a_hand(self) -> None:
        """Otherwise the director would silence every zone it ever switches off."""
        item = coordinator(idle_plan())
        item._notice_hand(_Event(BEDROOM, "heat", "off"))
        assert item._zones_handed_back() == set()

    def test_an_appliance_the_director_does_not_drive(self) -> None:
        item = coordinator(running_plan())
        item._notice_hand(_Event("climate.iets_anders", "heat", "off"))
        assert item._zones_handed_back() == set()

    def test_a_change_within_the_same_family(self) -> None:
        """Turning the setpoint up is not switching the thing off."""
        item = coordinator(running_plan())
        item._notice_hand(_Event(BEDROOM, "heat", "heat"))
        assert item._zones_handed_back() == set()

    @pytest.mark.parametrize("old", ["off", "fan_only"])
    def test_it_was_already_idle(self, old: str) -> None:
        item = coordinator(running_plan())
        item._notice_hand(_Event(BEDROOM, old, "off"))
        assert item._zones_handed_back() == set()

    def test_a_missing_state_is_survivable(self) -> None:
        """Entities come and go on a restart; none of that is a hand."""
        item = coordinator(running_plan())
        item._notice_hand(_Event(BEDROOM, None, "off"))
        item._notice_hand(_Event(BEDROOM, "heat", None))
        assert item._zones_handed_back() == set()

    def test_without_a_plan_yet(self) -> None:
        """Before the first decision there is nothing to compare against."""
        item = coordinator(None)
        item._notice_hand(_Event(BEDROOM, "heat", "off"))
        assert item._zones_handed_back() == {"slaapkamer"}


class TestGettingItBack:
    def test_switching_it_on_again_by_hand(self) -> None:
        item = coordinator(running_plan())
        item._notice_hand(_Event(BEDROOM, "heat", "off"))
        item._notice_hand(_Event(BEDROOM, "off", "heat"))
        assert item._zones_handed_back() == set()

    @pytest.mark.parametrize("mode", ["heat", "cool", "dry", "heat_cool"])
    def test_in_any_running_mode(self, mode: str) -> None:
        item = coordinator(running_plan())
        item._notice_hand(_Event(BEDROOM, "heat", "off"))
        item._notice_hand(_Event(BEDROOM, "off", mode))
        assert item._zones_handed_back() == set()

    def test_the_next_day(self) -> None:
        """Yesterday's decision should not still be holding this morning."""
        item = coordinator(running_plan())
        item._handed_back = {"slaapkamer": date.today() - timedelta(days=1)}
        assert item._zones_handed_back() == set()

    def test_today_it_still_holds(self) -> None:
        item = coordinator(running_plan())
        item._handed_back = {"slaapkamer": date.today()}
        assert item._zones_handed_back() == {"slaapkamer"}

    def test_a_day_older_still_counts_as_over(self) -> None:
        item = coordinator(running_plan())
        item._handed_back = {"slaapkamer": date.today() - timedelta(days=30)}
        assert item._zones_handed_back() == set()


class TestItReachesTheGates:
    """The whole point is that the zone stops being regulated, so check that."""

    def test_a_handed_back_zone_is_overridden(self) -> None:
        from conftest import make_world

        from custom_components.climate_director.engine import Reason as GateReason
        from custom_components.climate_director.engine import gates

        item = coordinator(running_plan())
        item._notice_hand(_Event(BEDROOM, "heat", "off"))

        overrides = {
            **dict.fromkeys(item._zones_handed_back(), True),
            **item.zone_overrides,
        }
        world = make_world(zone_overrides=overrides)
        bedroom = item.config.zone("slaapkamer")
        living = item.config.zone("woonkamer")
        assert bedroom is not None and living is not None
        assert gates.evaluate(item.config, world, bedroom).reason is GateReason.MANUAL_OVERRIDE
        assert gates.evaluate(item.config, world, living).allowed

    def test_the_switch_still_wins(self) -> None:
        """A user switching the override on outranks anything worked out here."""
        item = coordinator(running_plan())
        item.zone_overrides["woonkamer"] = True
        overrides = {
            **dict.fromkeys(item._zones_handed_back(), True),
            **item.zone_overrides,
        }
        assert overrides["woonkamer"] is True
