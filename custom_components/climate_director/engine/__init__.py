"""Pure beslislaag van Climate Director - geen Home Assistant-imports.

Climate Director's pure decision layer - no Home Assistant imports.

Alles in dit pakket is gewone Python: geen `hass`, geen entiteiten, geen I/O.
Dat is bewust de belangrijkste scheidslijn van het project - elk denkbaar
klimaatscenario is hier als dataobject na te bouwen en in milliseconden te
testen, zonder draaiende Home Assistant.

Everything in this package is plain Python: no `hass`, no entities, no I/O.
That is deliberately the project's most important dividing line - every
conceivable climate scenario can be reproduced here as a data object and tested
in milliseconds, without a running Home Assistant.
"""

from __future__ import annotations

from .decide import decide
from .families import (
    ACTIVE_FAMILIES,
    MODE_COOL,
    MODE_DRY,
    MODE_FAN_ONLY,
    MODE_HEAT,
    MODE_HEAT_COOL,
    MODE_OFF,
    ModeFamily,
    family_of,
    is_compatible,
)
from .models import (
    Circuit,
    ConflictPolicy,
    DirectorConfig,
    GateSettings,
    ModeSettings,
    Opening,
    OutdoorWindow,
    Resident,
    Season,
    Source,
    SourceRole,
    TimeWindow,
    Zone,
    validate,
)
from .plan import CircuitDecision, Deferral, Plan, Reason, UnitCommand, ZoneDecision
from .world import ClimateState, OpeningState, PresenceState, ResidentState, WorldState

__all__ = [
    "ACTIVE_FAMILIES",
    "MODE_COOL",
    "MODE_DRY",
    "MODE_FAN_ONLY",
    "MODE_HEAT",
    "MODE_HEAT_COOL",
    "MODE_OFF",
    "Circuit",
    "CircuitDecision",
    "ClimateState",
    "ConflictPolicy",
    "Deferral",
    "DirectorConfig",
    "GateSettings",
    "ModeFamily",
    "ModeSettings",
    "Opening",
    "OpeningState",
    "PresenceState",
    "OutdoorWindow",
    "Plan",
    "Reason",
    "Resident",
    "ResidentState",
    "Season",
    "Source",
    "SourceRole",
    "TimeWindow",
    "UnitCommand",
    "WorldState",
    "Zone",
    "ZoneDecision",
    "decide",
    "family_of",
    "is_compatible",
    "validate",
]
