"""Seizoenskeuze per hand, als entiteit in plaats van als configuratie.

Season choice by hand, as an entity rather than as configuration.

Het seizoen hangt normaal aan de maand, een entiteit of een vaste instelling.
Maar een uitzonderlijk warme oktober of een koude mei hoort iemand met één
draai aan een select te kunnen corrigeren, zonder de options flow in te duiken
die de hele installatie herlaadt. Deze entiteit is dus bedieningstoestand,
geen configuratie: hij herstelt zich na een herstart en schrijft zijn stand
terug naar de coordinator.

The season normally follows the month, an entity or a fixed setting. But an
unusually warm October or a cold May should be correctable with one turn of a
select, without diving into the options flow that reloads the whole
installation. So this entity is control state, not configuration: it restores
itself after a restart and writes its state back to the coordinator.
"""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .coordinator import ClimateDirectorCoordinator, ClimateDirectorEntry
from .engine import DirectorConfig, Season
from .entity import ClimateDirectorEntity

OPTIONS = ("auto", "summer", "winter")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ClimateDirectorEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the season select for one installation."""
    async_add_entities([SeasonSelect(entry.runtime_data)])


def wanted_entity_keys(config: DirectorConfig) -> set[str]:
    """Return every unique-id key this platform will create for `config`."""
    return {"season"}


class SeasonSelect(ClimateDirectorEntity, SelectEntity, RestoreEntity):
    """A select that overrides the season the director works with."""

    _attr_translation_key = "season"
    _attr_icon = "mdi:calendar-month"
    _attr_options = list(OPTIONS)

    def __init__(self, coordinator: ClimateDirectorCoordinator) -> None:
        """Set up the season select."""
        super().__init__(coordinator, "season")
        self._current = OPTIONS[0]

    async def async_added_to_hass(self) -> None:
        """Restore the saved choice before the first decision is made."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in OPTIONS:
            self._current = last.state
        self._push()

    @property
    def current_option(self) -> str | None:
        """Return the season the director currently works with."""
        return self._current

    async def async_select_option(self, option: str) -> None:
        """Set the season override and decide again."""
        self._current = option
        self._push()
        self.async_write_ha_state()
        self.coordinator.async_request_evaluation()

    def _push(self) -> None:
        """Write this select's choice into the coordinator."""
        self.coordinator.season_override = (
            None if self._current == OPTIONS[0] else Season(self._current)
        )

    def _handle_coordinator_update(self) -> None:
        """Ignore coordinator updates: this select is an input, not an output."""
