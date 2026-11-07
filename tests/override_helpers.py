"""Een stand-in met alleen de override-staat van de coördinator.

A stand-in carrying only the coordinator's override state.
"""

from __future__ import annotations

from typing import Any

from custom_components.climate_director.overrides import OverridesMixin


class OverrideHost(OverridesMixin):
    """A stand-in for the coordinator with just the override state on it.

    A stand-in for the coordinator with just the override state on it.
    """

    def __init__(self, config: Any) -> None:
        self.config = config
        self.zone_overrides: dict[str, bool] = {}
        self.zone_override_until: dict[str, Any] = {}
        self.zone_override_when_done: dict[str, str] = {}
        self._cancel_override_wake: Any = None
        self.evaluations = 0

    def async_request_evaluation(self) -> None:
        self.evaluations += 1
