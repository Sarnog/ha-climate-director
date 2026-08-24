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

from collections.abc import Mapping
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


def changes(
    plan: Plan,
    world: WorldState,
    already_sent: Mapping[str, tuple[str, float]] | None = None,
) -> tuple[Change, ...]:
    """Return the commands that would actually alter something.

    A command matching reality produces nothing, so deciding again without
    anything having moved is free. That is what keeps the director from
    re-issuing the same call on every state change of every tracked entity.

    `already_sent` is de boekhouding van wat de koppelingslaag werkelijk heeft
    uitgevoerd: per apparaat het laatst uitgevoerde `(hvac_mode, temperature)`.
    Een apparaat dat geen setpoint terugmeldt, kan zijn huidige setpoint niet
    laten zien; zonder deze boekhouding zou zo'n setpoint elke ronde opnieuw
    verstuurd worden. Met deze boekhouding telt het als ongewijzigd zodra
    ditzelfde setpoint écht is uitgevoerd. Een setpoint dat alleen in het plan
    stond maar waarvan de aanroep mislukte, staat er dus niet in: "al
    verstuurd" betekent uitgevoerd, niet gepland.

    `already_sent` is the binding layer's bookkeeping of what was really
    executed: per appliance the last executed `(hvac_mode, temperature)`. An
    appliance that reports no setpoint cannot show its current one; without
    this bookkeeping such a setpoint would be re-sent every round. With it the
    setpoint counts as unchanged once this same setpoint was really executed.
    A setpoint that only stood in the plan but whose call failed is therefore
    absent: "already sent" means executed, not planned.
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
            state.target_temperature,
            command.temperature,
            already_sent=_already_sent(already_sent, command),
        )

        if set_mode or set_temperature:
            result.append(Change(command, set_mode, set_temperature))

    return tuple(result)


def _already_sent(
    already_sent: Mapping[str, tuple[str, float]] | None, command: UnitCommand
) -> bool:
    """Return whether this exact state was really executed before."""
    if already_sent is None:
        return False
    sent = already_sent.get(command.entity_id)
    if sent is None:
        return False
    return sent[0] == command.hvac_mode and sent[1] == command.temperature


def _close(current: float | None, wanted: float | None, *, already_sent: bool = False) -> bool:
    """Return whether two setpoints are near enough to count as equal.

    Zonder meting tegenover het setpoint valt er niets te vergelijken. Is dit
    setpoint de vorige ronde al verstuurd, dan is het dus ongewijzigd; zo niet,
    dan wordt het één keer verstuurd.

    With no reading to hold against the setpoint there is nothing to compare.
    If this setpoint was already sent last round it is therefore unchanged; if
    not, it is sent once.
    """
    if wanted is None:
        return True
    if current is None:
        return already_sent
    return abs(current - wanted) <= TEMPERATURE_TOLERANCE
