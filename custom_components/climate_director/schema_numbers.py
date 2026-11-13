"""De getalkiezers voor prijzen en rendementen.

The number pickers for prices and efficiencies.
"""

from __future__ import annotations

from typing import Literal

from homeassistant.helpers import selector


def decimal(low: float, high: float, step: float | Literal["any"]) -> selector.NumberSelector:
    """Return a plain decimal number box, for prices and efficiencies."""
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=low, max=high, step=step, mode=selector.NumberSelectorMode.BOX
        )
    )


#: De energievelden: een prijs, een calorische waarde en een rendement.
#: The energy fields: a price, a calorific value and an efficiency.
DECIMALS: dict[str, selector.NumberSelector] = {
    "price": decimal(0, 100, "any"),
    "kwh_per_m3": decimal(1, 20, 0.01),
    "efficiency": decimal(0.1, 1.2, 0.01),
    "percent": decimal(0, 50, 1),
}
