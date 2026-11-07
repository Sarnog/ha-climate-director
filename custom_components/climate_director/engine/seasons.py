"""Seizoenen, hun bron en de neerslaginstellingen.

Seasons, their source and the precipitation settings.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum

QUIET_ROOM_MINUTES = 15

HOLIDAY_WEEKDAY = 5


class Season(StrEnum):
    """Coarse season used to gate whole modes on and off."""

    SUMMER = "summer"
    WINTER = "winter"
    UNKNOWN = "unknown"


class SeasonSource(StrEnum):
    """Where the coarse season comes from."""

    AUTO = "auto"
    """Derived from the month."""

    ENTITY = "entity"
    """Read from an entity, so an existing helper keeps working."""

    SUMMER = "summer"
    WINTER = "winter"
    """Pinned by hand."""


@dataclass(frozen=True, slots=True)
class SeasonSettings:
    """How to resolve the season the zones are gated on."""

    source: SeasonSource = SeasonSource.AUTO
    entity_id: str = ""
    summer_months: frozenset[int] = frozenset({4, 5, 6, 7, 8, 9})
    """Month numbers counting as summer when `source` is `AUTO`."""

    def for_month(self, month: int) -> Season:
        """Return the season `AUTO` would pick for this month."""
        return Season.SUMMER if month in self.summer_months else Season.WINTER


@dataclass(frozen=True, slots=True)
class PrecipitationSettings:
    """Which source counts as precipitation, and how long it keeps counting.

    De buitengrens per zone is een zuinigheidsregel die ervan uitgaat dat je
    bij mooi weer beter een raam openzet dan de airco aan. Valt er neerslag,
    dan gaat die aanname niet op — en zolang een neerslagbron neerslag meldt,
    slaat de engine de buitengrens per zone over, precies zoals een
    vooruit-verzoek dat al doet.

    The per-zone outdoor bound is a thrift rule that assumes you are better off
    opening a window than switching the air conditioner on in nice weather.
    When precipitation falls that assumption does not hold — and as long as a
    precipitation source reports precipitation, the engine skips the per-zone
    outdoor bound, exactly as a pre-conditioning request already does.
    """

    source: str = ""
    """Entity carrying the reading. Empty switches the whole feature off."""

    states: frozenset[str] = frozenset({"rainy", "pouring", "snowy", "hail", "lightning-rainy"})
    """States of that entity that count as precipitation.

    Voor een `weather`-entiteit zijn dit zijn condities; voor een sensor zijn
    het zijn standen.

    For a `weather` entity these are its conditions; for a sensor its states.
    """

    grace: timedelta = timedelta(minutes=15)
    """How long a reading keeps counting after it stops.

    Een bui van vijf minuten hoort de regeling niet te laten stuiteren.

    A five-minute shower should not make the regulation bounce.
    """

    @property
    def enabled(self) -> bool:
        """Return whether a source is configured at all."""
        return bool(self.source)
