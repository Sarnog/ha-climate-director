"""Kleine, bereikbare takken van de beslissing en de bronkeuze.

Small, reachable branches of the decision and source selection."""

from __future__ import annotations

import dataclasses

from conftest import climate, house, make_world

import custom_components.climate_director.engine.sources as source_picker
from custom_components.climate_director.engine import diff, validation
from custom_components.climate_director.engine.decide import _group_holder, clamped_target
from custom_components.climate_director.engine.models import ModeFamily


def test_a_command_without_a_setpoint_is_never_measured_against_one() -> None:
    """Een stand-commando zonder setpoint is nooit 'te ver' van iets."""
    assert diff._close(None, None) is True
    assert diff._close(20.0, None) is True


def test_clamping_a_command_without_a_setpoint_gives_nothing() -> None:
    """Zonder setpoint valt er niets af te kappen."""
    assert clamped_target(None, climate("heat")) is None


def test_a_group_holder_ignores_a_member_that_is_no_source() -> None:
    """Een apparaat dat in geen enkele bron voorkomt bezet de groep niet."""
    assert _group_holder(house(), make_world(), frozenset({"climate.geen_bron"})) is None


def test_a_dead_band_without_a_serving_source_holds_nothing() -> None:
    """Zonder geleverde bron, of met een bron die niet meer bestaat, houdt de band niets."""
    zone = house().zones[0]
    world = make_world()
    assert source_picker._held(zone, ModeFamily.HEAT, world, None, 2.0, []) is None
    assert source_picker._held(zone, ModeFamily.HEAT, world, "bestaat_niet", 2.0, []) is None


def test_a_dead_band_lets_go_outside_its_takeover_or_when_blocked() -> None:
    """Buiten de overname, of huisbreed stilgezet, houdt de band de bron niet vast."""
    zone = house().zones[0]
    world = make_world()
    source = zone.sources[0]
    outside = source_picker._held(
        zone, ModeFamily.HEAT, world, source.source_id, 2.0, [], only=frozenset({"climate.anders"})
    )
    assert outside is None
    blocked = source_picker._held(
        zone,
        ModeFamily.HEAT,
        world,
        source.source_id,
        2.0,
        [],
        blocked=frozenset({source.entity_id}),
    )
    assert blocked is None


def test_a_source_covering_an_unknown_zone_is_reported() -> None:
    """Een bron die een onbekende zone in zijn gebied noemt wordt gemeld."""
    base = house()
    zone = base.zones[0]
    source = dataclasses.replace(zone.sources[0], covers_zones=("bestaat_niet",))
    zone = dataclasses.replace(zone, sources=(source, *zone.sources[1:]))
    config = dataclasses.replace(base, zones=(zone, *base.zones[1:]))

    found = [problem.code for problem in validation._rule_source_covered_zones(config)]
    assert found == ["source_unknown_covered_zone"]
