"""Climate Director - orkestreert bestaande climate-entiteiten.

Climate Director - orchestrates existing climate entities.

Deze integratie is opgebouwd in twee helften. `engine/` bevat de volledige
besliskunde als pure Python zonder Home Assistant-imports; de rest van dit
pakket koppelt die engine aan Home Assistant. Op dit moment bestaat alleen de
engine - de koppelingslaag (config flow, coordinator, entiteiten) volgt.

This integration is built in two halves. `engine/` holds all decision logic as
pure Python without Home Assistant imports; the rest of this package binds that
engine to Home Assistant. Only the engine exists at this point - the binding
layer (config flow, coordinator, entities) follows.
"""

from __future__ import annotations

from typing import Any

from .const import DOMAIN

__all__ = ["DOMAIN", "async_setup"]


async def async_setup(hass: Any, config: dict[str, Any]) -> bool:
    """Set up the integration; the binding layer is not built yet."""
    return True
