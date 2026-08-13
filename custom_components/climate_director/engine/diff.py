"""Verschil tussen het plan en de werkelijkheid.

The difference between the plan and reality.

Het plan beschrijft gewenste eindtoestanden. Deze module bepaalt welke daarvan
nog niet kloppen. Dat is bewust een pure functie: of een service call nodig is
hangt alleen af van twee dataobjecten, niet van Home Assistant.

The plan describes desired end states. This module works out which of them do
not hold yet. That is deliberately a pure function: whether a service call is
needed depends on two data objects alone, not on Home Assistant.
"""

from __future__ import annotations

from dataclasses import dataclass

from .families import MODE_OFF
from .plan import Plan, UnitCommand
from .world import WorldState

#: Hoe dicht een setpoint mag zitten voordat het als gelijk telt.
#: How close a setpoint may sit before it counts as equal.
TEMPERATURE_TOLERANCE = 0.05


@dataclass(frozen=True, slots=True)
class Change:
    """One climate entity that is not where the plan wants it."""

    command: UnitCommand
    set_mode: bool
    set_temperature: bool

    @property
    def entity_id(self) -> str:
        """Return the entity this change targets."""
        return self.command.entity_id


def changes(plan: Plan, world: WorldState) -> tuple[Change, ...]:
    """Return the commands that would actually alter something.

    A command matching reality produces nothing, so deciding again without
    anything having moved is free. That is what keeps the director from
    re-issuing the same call on every state change of every tracked entity.
    """
    result: list[Change] = []

    for command in plan.commands:
        state = world.climate(command.entity_id)
        if not state.available:
            continue

        set_mode = state.hvac_mode != command.hvac_mode

        # A unit being switched off keeps whatever setpoint it had; pushing a
        # temperature at it would be a call that changes nothing a user sees.
        wants_temperature = command.temperature is not None and command.hvac_mode != MODE_OFF
        set_temperature = wants_temperature and not _close(
            state.target_temperature, command.temperature
        )

        if set_mode or set_temperature:
            result.append(Change(command, set_mode, set_temperature))

    return tuple(result)


def _close(current: float | None, wanted: float | None) -> bool:
    """Return whether two setpoints are near enough to count as equal."""
    if wanted is None:
        return True
    if current is None:
        return False
    return abs(current - wanted) <= TEMPERATURE_TOLERANCE
