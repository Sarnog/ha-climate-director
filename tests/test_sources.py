"""Tests voor de bronkeuze.

Tests for source selection.
"""

from __future__ import annotations

from conftest import GAS, GAS_CUTOVER, LIVING, climate, house, make_world

from custom_components.climate_director.engine import (
    ModeFamily,
    OutdoorWindow,
    Source,
    SourceRole,
    Zone,
    sources,
)


def living_room() -> Zone:
    zone = house().zone("woonkamer")
    assert zone is not None
    return zone


def available_house(outdoor: float):
    return make_world(
        outdoor=outdoor,
        climates={GAS: climate("off"), LIVING: climate("off")},
    )


class TestOutdoorCutover:
    def test_boiler_below_the_cutover(self) -> None:
        chosen = sources.select(living_room(), ModeFamily.HEAT, available_house(2.9))
        assert chosen is not None
        assert chosen.entity_id == GAS

    def test_heat_pump_at_the_cutover(self) -> None:
        """The cutover value itself belongs to the upper window."""
        chosen = sources.select(living_room(), ModeFamily.HEAT, available_house(GAS_CUTOVER))
        assert chosen is not None
        assert chosen.entity_id == LIVING

    def test_only_the_heat_pump_can_cool(self) -> None:
        chosen = sources.select(living_room(), ModeFamily.COOL, available_house(28.0))
        assert chosen is not None
        assert chosen.entity_id == LIVING

    def test_boiler_is_never_offered_for_cooling(self) -> None:
        assert sources.select(living_room(), ModeFamily.COOL, available_house(1.0)) is None


class TestAvailability:
    def test_unavailable_source_is_skipped(self) -> None:
        world = make_world(outdoor=10.0, climates={LIVING: climate("off", available=False)})
        assert sources.select(living_room(), ModeFamily.HEAT, world) is None

    def test_missing_entity_counts_as_unavailable(self) -> None:
        assert sources.select(living_room(), ModeFamily.HEAT, make_world(outdoor=10.0)) is None


class TestPreference:
    zone = Zone(
        zone_id="z",
        name="Z",
        indoor_sensor="sensor.t",
        sources=(
            Source("expensive", "climate.b", priority=5),
            Source("cheap", "climate.a", priority=1),
        ),
    )

    def test_lowest_priority_number_wins(self) -> None:
        world = make_world(climates={"climate.a": climate(), "climate.b": climate()})
        chosen = sources.select(self.zone, ModeFamily.HEAT, world)
        assert chosen is not None
        assert chosen.source_id == "cheap"

    def test_falls_back_when_the_preferred_source_is_gone(self) -> None:
        world = make_world(climates={"climate.a": climate(available=False), "climate.b": climate()})
        chosen = sources.select(self.zone, ModeFamily.HEAT, world)
        assert chosen is not None
        assert chosen.source_id == "expensive"

    def test_equal_priorities_resolve_on_source_id(self) -> None:
        zone = Zone(
            zone_id="z",
            name="Z",
            indoor_sensor="sensor.t",
            sources=(Source("b", "climate.b"), Source("a", "climate.a")),
        )
        world = make_world(climates={"climate.a": climate(), "climate.b": climate()})
        chosen = sources.select(zone, ModeFamily.HEAT, world)
        assert chosen is not None
        assert chosen.source_id == "a"

    def test_candidates_are_returned_most_preferred_first(self) -> None:
        world = make_world(climates={"climate.a": climate(), "climate.b": climate()})
        ordered = sources.candidates(self.zone, ModeFamily.HEAT, world)
        assert [source.source_id for source in ordered] == ["cheap", "expensive"]


def test_role_limits_the_offer() -> None:
    zone = Zone(
        zone_id="z",
        name="Z",
        indoor_sensor="sensor.t",
        sources=(
            Source("stove", "climate.stove", role=SourceRole.HEAT_ONLY),
            Source("fridge", "climate.fridge", role=SourceRole.COOL_ONLY),
        ),
    )
    world = make_world(climates={"climate.stove": climate(), "climate.fridge": climate()})
    heat = sources.select(zone, ModeFamily.HEAT, world)
    cool = sources.select(zone, ModeFamily.COOL, world)
    assert heat is not None and heat.source_id == "stove"
    assert cool is not None and cool.source_id == "fridge"


def test_window_on_a_source_narrows_it_further() -> None:
    zone = Zone(
        zone_id="z",
        name="Z",
        indoor_sensor="sensor.t",
        sources=(Source("s", "climate.x", outdoor=OutdoorWindow(minimum=-5.0)),),
    )
    world = make_world(outdoor=-10.0, climates={"climate.x": climate()})
    assert sources.select(zone, ModeFamily.HEAT, world) is None


class TestModesTheApplianceReports:
    """De rol zegt wat de installatie wil; het apparaat zegt wat het kan.

    The role says what the installation wants; the appliance says what it can.
    """

    def _zone(self) -> Zone:
        return Zone(
            zone_id="z",
            name="Z",
            indoor_sensor="sensor.t",
            sources=(Source("unit", "climate.unit", role=SourceRole.HEAT_COOL),),
        )

    def test_a_source_that_cannot_cool_is_not_offered_for_cooling(self) -> None:
        from custom_components.climate_director.engine import ClimateState

        world = make_world(
            outdoor=28.0,
            climates={
                "climate.unit": ClimateState(hvac_mode="off", hvac_modes=frozenset({"heat", "off"}))
            },
        )
        assert sources.select(self._zone(), ModeFamily.COOL, world) is None

    def test_a_source_without_a_listing_gets_the_benefit_of_the_doubt(self) -> None:
        """Geen opgave betekent onbekend, en dan wordt het commando gewoon gestuurd.

        No listing means unknown, and then the command is simply sent.
        """
        from custom_components.climate_director.engine import ClimateState

        world = make_world(
            outdoor=28.0,
            climates={"climate.unit": ClimateState(hvac_mode="off", hvac_modes=None)},
        )
        chosen = sources.select(self._zone(), ModeFamily.COOL, world)
        assert chosen is not None
        assert chosen.source_id == "unit"
