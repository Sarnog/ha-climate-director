"""Bereikbare takken van een gebiedsovername.

Reachable branches of an area takeover."""

from __future__ import annotations

from typing import Any

from conftest import climate, make_world

from custom_components.climate_director.engine import serialise
from custom_components.climate_director.engine.models import ModeFamily


def _takeover_house(*, extra_source: bool = False) -> Any:
    """Return two rooms where one appliance also covers the other's room."""
    sources: list[dict[str, Any]] = [
        {"source_id": "airco", "entity_id": "climate.a", "covers_zones": ["zolder"]}
    ]
    if extra_source:
        sources.append({"source_id": "kachel", "entity_id": "climate.c"})
    return serialise.config_from_dict(
        {
            "zones": [
                {
                    "zone_id": "woonkamer",
                    "name": "Woonkamer",
                    "indoor_sensor": "sensor.woonkamer",
                    "sources": sources,
                },
                {
                    "zone_id": "zolder",
                    "name": "Zolder",
                    "indoor_sensor": "sensor.zolder",
                    "sources": [{"source_id": "ketel", "entity_id": "climate.b"}],
                },
            ]
        }
    )


def test_an_area_whose_appliance_is_unreachable_does_not_take_over() -> None:
    """Een onbereikbaar apparaat neemt niets over, al staat zijn gebied er wel."""
    from custom_components.climate_director.engine import takeover

    config = _takeover_house()
    world = make_world(climates={"climate.a": climate("off", available=False)})
    assert takeover.in_force(config, world) == ()


def test_a_taken_area_without_anything_around_keeps_its_commands() -> None:
    """Draait de overnemer alleen, dan valt er niets stil te leggen."""
    from custom_components.climate_director.engine import takeover
    from custom_components.climate_director.engine.plan import UnitCommand
    from custom_components.climate_director.engine.takeover import Takeover

    config = _takeover_house()
    world = make_world()
    takeovers = (
        Takeover("climate.a", frozenset({"woonkamer"}), frozenset({ModeFamily.HEAT})),
        Takeover("climate.b", frozenset({"zolder"}), frozenset({ModeFamily.HEAT})),
    )
    commands = [UnitCommand(entity_id="climate.a", hvac_mode="heat", temperature=21.0)]
    assert takeover.stop_others(config, world, takeovers, commands, []) == commands


def test_a_hand_operated_appliance_in_a_taken_area_is_stood_down() -> None:
    """Een handbediend apparaat in het gebied gaat uit; een onbereikbaar niet."""
    from custom_components.climate_director.engine import Reason, UntouchedSource, takeover
    from custom_components.climate_director.engine.plan import UnitCommand
    from custom_components.climate_director.engine.takeover import Takeover

    config = _takeover_house(extra_source=True)
    world = make_world()
    takeovers = (Takeover("climate.a", frozenset({"woonkamer"}), frozenset({ModeFamily.HEAT})),)
    commands = [UnitCommand(entity_id="climate.a", hvac_mode="heat", temperature=21.0)]
    untouched = [
        UntouchedSource("climate.c", "woonkamer", Reason.MANUAL_SOURCE),
        UntouchedSource("climate.d", "woonkamer", Reason.MANUAL_SOURCE),
    ]
    # `climate.c` is bereikbaar maar staat uit, `climate.d` valt buiten het
    # gebied: geen van beide levert een commando op.
    assert takeover.stop_others(config, world, takeovers, commands, untouched) == commands
