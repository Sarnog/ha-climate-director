"""Gedeelde controles en hulpjes van de configuratiecontrole.

Shared checks and helpers of the configuration check.

De seizoensnamen, de dubbelenzoeker, de vensterlijst en de controle op het seizoen:
wat meer dan één onderwerpmodule nodig heeft, of wat bij de hele installatie hoort.

The season names, the duplicate finder, the window list and the check on the
season: whatever more than one subject module needs, or whatever belongs to the
installation as a whole.
"""

from __future__ import annotations

from collections.abc import Iterator

from .models import DirectorConfig, Season, SeasonSettings, SeasonSource, TimeWindow
from .problem import Problem


def pinned_season(seasons: SeasonSettings) -> Season | None:
    """Return the season `seasons` pins the installation to, if any."""
    if seasons.source is SeasonSource.SUMMER:
        return Season.SUMMER
    if seasons.source is SeasonSource.WINTER:
        return Season.WINTER
    return None


def season_names(seasons: frozenset[Season] | None) -> str:
    """Return the human-readable names of the seasons a duty is allowed in."""
    return ", ".join(sorted(season.value for season in seasons or ()))


def duplicates(values: list[str]) -> list[str]:
    """Return the values occurring more than once, in first-seen order."""
    seen: set[str] = set()
    duplicated: list[str] = []
    for value in values:
        if value in seen and value not in duplicated:
            duplicated.append(value)
        seen.add(value)
    return duplicated


def windows(config: DirectorConfig) -> Iterator[tuple[str, TimeWindow]]:
    """Yield every configured window with a readable label."""
    for window in config.gates.quiet_windows:
        yield "quiet window", window
    guest = config.gates.guest_window
    if guest is not None:
        yield "guest window", guest
    for resident in config.residents:
        if resident.sleep_window is not None:
            yield f"sleep window of {resident.name or resident.resident_id}", resident.sleep_window
        for window in resident.windows:
            yield f"schedule of {resident.name or resident.resident_id}", window


def outdoor_is_known(config: DirectorConfig) -> bool:
    """Return whether the installation has an outdoor temperature to read.

    Gedeeld door de bron- en taakvenstercontrole in `rule_zones`: één
    definitie, één berekening per `validate()`-aanroep.

    Shared by the source- and duty-window checks in `rule_zones`: one
    definition, one computation per `validate()` call.
    """
    return bool(config.outdoor_sensor)


def rule_seasons(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint when the season can never be read.

    Staat de herkomst van het seizoen op *entiteit* zonder dat er een gekozen is,
    dan blijft het seizoen onbekend en doet elke taak met een seizoensbeperking
    niets. Dat is het stille niets waarvoor `unreadable_entities` bestaat, maar
    dan zonder dat er iets te herlezen valt: de entiteit die ontbreekt is er niet
    een die even wegvalt, maar een die nooit gekozen is.

    With the season source on *entity* and none chosen, the season stays unknown
    and every duty with a season restriction does nothing. That is the silent
    nothing `unreadable_entities` exists for, but with nothing to re-read: the
    entity that is missing is not one that dropped out for a moment, but one that
    was never chosen.
    """
    if config.seasons.source is SeasonSource.ENTITY and not config.seasons.entity_id:
        yield Problem(
            "season_entity_missing",
            "the season source is an entity, but none is chosen",
        )
