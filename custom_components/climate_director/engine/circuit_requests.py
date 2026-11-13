"""Wat een zone aan een circuit vraagt en krijgt.

What a zone asks of a circuit and gets.

`Request` is het verzoek van één zone, `Grant` wat die zone werkelijk kreeg en
`Outcome` het volledige resultaat van één circuit. Ze staan hier en niet in
`constraints.py`, omdat de taakkeuze (`circuit_policy.py`), de capaciteit
(`capacity.py`) en het oplossen zelf (`constraints.py`) ze alle drie nodig hebben.

`Request` is one zone's request, `Grant` what that zone really got and `Outcome`
the full result of one circuit. They live here and not in `constraints.py`,
because the duty choice (`circuit_policy.py`), the capacity (`capacity.py`) and
the resolving itself (`constraints.py`) all three need them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .families import ModeFamily
from .models import Source, Zone
from .plan import CircuitDecision, Deferral, Reason


@dataclass(frozen=True, slots=True)
class Request:
    """One zone asking a circuit for a duty."""

    zone: Zone
    source: Source
    family: ModeFamily
    deviation: float = 0.0

    priority: int = 0
    """The priority in force, which may be a live value rather than the configured one."""

    @property
    def rank(self) -> tuple[int, str]:
        """Return the tie-break key: priority first, then zone id."""
        return (self.priority, self.zone.zone_id)


@dataclass(frozen=True, slots=True)
class Grant:
    """What a zone actually got."""

    zone_id: str
    source_id: str
    family: ModeFamily
    reason: Reason

    @property
    def granted(self) -> bool:
        """Return whether the zone may run its duty."""
        return self.family is not ModeFamily.NEUTRAL


@dataclass(frozen=True, slots=True)
class Outcome:
    """The full result of resolving one circuit."""

    decision: CircuitDecision
    grants: tuple[Grant, ...] = ()
    deferrals: tuple[Deferral, ...] = field(default_factory=tuple)
