"""Welke zone een huisbreed overgedragen apparaat met rust laat.

Which zone leaves a house-wide handed-over appliance alone.
"""

from __future__ import annotations

from .models import DirectorConfig
from .plan import Reason, UnitCommand, UntouchedSource
from .world import WorldState


def first_per_entity(
    config: DirectorConfig,
    world: WorldState,
    untouched: list[UntouchedSource],
    commands: list[UnitCommand],
) -> list[UntouchedSource]:
    """Return one entry per appliance, keeping the first zone that reported it.

    Bij een huisbreed overgedragen apparaat telt de zone met de override: die
    zegt waarom het apparaat met rust blijft. Zonder die voorkeur noemde de
    melding de eerste zone die het apparaat toevallig ook draagt.

    For a house-wide handed-over appliance the zone with the override counts:
    it says why the appliance is left alone. Without that preference the notice
    named the first zone that happened to carry the appliance too.
    """
    overridden = frozenset(zone.zone_id for zone in config.zones if world.overridden(zone.zone_id))
    commanded = {command.entity_id for command in commands}
    seen: dict[str, UntouchedSource] = {}
    for item in untouched:
        if item.entity_id not in seen or (
            item.reason is Reason.MANUAL_OVERRIDE and item.zone_id in overridden
        ):
            seen[item.entity_id] = item
    return [item for item in seen.values() if item.entity_id not in commanded]
