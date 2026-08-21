"""Diagnostiek moet elke beslissing reproduceerbaar maken.

Diagnostics must make every decision reproducible.

Een diagnose die de helft van de wereld weglaat, kan een beslissing niet
naspelen - en dat is precies waar de download voor bestaat. Deze tests pinnen
vast dat de zes nog ontbrekende `WorldState`-velden, de bedieningstoestand en
de `untouched`-lijst in de uitvoer zitten.

A diagnostics download that omits half the world cannot replay a decision -
and replaying is exactly what the download exists for. These tests pin down
that the six still-missing `WorldState` fields, the control state and the
`untouched` list are in the output.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from custom_components.climate_director.diagnostics import _plan, _world
from custom_components.climate_director.engine import (
    MODE_OFF,
    Plan,
    Reason,
    Season,
    UnitCommand,
    UntouchedSource,
)
from custom_components.climate_director.engine.world import (
    ClimateState,
    OpeningState,
    PresenceState,
    ResidentState,
    WorldState,
)

NOW = datetime(2026, 8, 21, 12, 0)


def _full_world() -> WorldState:
    """Return a snapshot in which every field carries a recognisable value."""
    return WorldState(
        now=NOW,
        outdoor_temperature=12.5,
        season=Season.WINTER,
        indoor_temperatures={"woonkamer": 19.5},
        climates={
            "climate.huiskamer": ClimateState(
                hvac_mode="heat",
                current_temperature=19.5,
                target_temperature=21.0,
                available=True,
                changed_at=NOW - timedelta(minutes=3),
            )
        },
        residents={"danny": ResidentState(home=True, asleep=False)},
        openings={"binary_sensor.raam": OpeningState(open=False, changed_at=None)},
        presence={"woonkamer": PresenceState(occupied=True, changed_at=NOW - timedelta(minutes=5))},
        circuit_family_since={"c1": NOW - timedelta(minutes=10)},
        master_enabled=True,
        holiday_mode=False,
        precondition_until={"woonkamer": NOW + timedelta(minutes=30)},
        precondition_bypass=frozenset({"woonkamer"}),
        guest_mode=True,
        precipitation=True,
        zone_overrides={"zolder": True},
        zone_priorities={"woonkamer": 1},
    )


def _full_plan() -> Plan:
    """Return a plan that carries a command and one deliberately untouched appliance."""
    return Plan(
        commands=(
            UnitCommand(
                entity_id="climate.huiskamer",
                hvac_mode="heat",
                temperature=21.0,
                zone_id="woonkamer",
                source_id="w",
                reason=Reason.REGULATING,
            ),
        ),
        zones=(),
        circuits=(),
        deferrals=(),
        untouched=(
            UntouchedSource(
                entity_id="climate.zolder", zone_id="zolder", reason=Reason.MANUAL_SOURCE
            ),
        ),
    )


class TestTheWorldIsComplete:
    def test_all_six_previously_missing_fields_are_present(self) -> None:
        data = _world(_full_world())
        assert data is not None
        assert set(data) >= {
            "presence",
            "precondition_until",
            "precondition_bypass",
            "guest_mode",
            "precipitation",
            "zone_priorities",
        }

    def test_each_new_field_keeps_its_value(self) -> None:
        data = _world(_full_world())
        assert data is not None
        assert data["presence"]["woonkamer"]["occupied"] is True
        assert data["precondition_until"]["woonkamer"] == (NOW + timedelta(minutes=30)).isoformat()
        assert data["precondition_bypass"] == ["woonkamer"]
        assert data["guest_mode"] is True
        assert data["precipitation"] is True
        assert data["zone_priorities"] == {"woonkamer": 1}


class TestThePlanIsComplete:
    def test_untouched_appliances_are_named_with_their_reason(self) -> None:
        data = _plan(_full_plan())
        assert data is not None
        assert data["untouched"] == [
            {
                "entity_id": "climate.zolder",
                "zone_id": "zolder",
                "reason": Reason.MANUAL_SOURCE.value,
            }
        ]

    def test_a_plan_without_untouched_stays_empty(self) -> None:
        data = _plan(Plan(commands=(), zones=(), circuits=(), deferrals=(), untouched=()))
        assert data is not None
        assert data["untouched"] == []


class TestEmptyInputs:
    def test_a_missing_world_stays_none(self) -> None:
        assert _world(None) is None

    def test_a_missing_plan_stays_none(self) -> None:
        assert _plan(None) is None

    def test_an_off_command_survives_the_round_trip(self) -> None:
        plan = Plan(
            commands=(
                UnitCommand(
                    entity_id="climate.x",
                    hvac_mode=MODE_OFF,
                    reason=Reason.SATISFIED,
                ),
            ),
            zones=(),
            circuits=(),
            deferrals=(),
        )
        data = _plan(plan)
        assert data is not None
        assert data["commands"][0]["hvac_mode"] == MODE_OFF
