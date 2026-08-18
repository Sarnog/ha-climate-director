"""Prioriteit per zone, als entiteit in plaats van als configuratie.

Priority per zone, as an entity rather than as configuration.

Welke ruimte voorgaat op een gedeelde buitenunit is niets vasts. Overdag mag de
woonkamer de baas zijn en 's avonds de slaapkamer; wie thuiswerkt wil dat de
zolder wint zodra daar iemand zit. Dat hoort dus bedienbaar te zijn vanuit een
automatisering, en niet in een config entry te staan die bij elke wijziging de
hele installatie herlaadt.

Which room outranks which on a shared outdoor unit is nothing fixed. By day the
living room may rule and by evening the bedroom; somebody working from home
wants the attic to win the moment they sit down in it. So it belongs somewhere
an automation can reach, not in a config entry that reloads the whole
installation on every change.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DEFAULT_PRECONDITION_MINUTES,
    MAX_PRECONDITION_MINUTES,
    MIN_PRECONDITION_MINUTES,
)
from .coordinator import ClimateDirectorCoordinator, ClimateDirectorEntry
from .entity import ClimateDirectorEntity

#: Bewaard naast de stand, zodat een latere wijziging in de configuratie te
#: onderscheiden is van een waarde die een automatisering heeft gezet.
#:
#: Stored alongside the value, so a later change in the configuration can be
#: told apart from a value an automation set.
ATTR_CONFIGURED = "configured_priority"


def resolve_initial(configured: int, last_value: int | None, last_configured: int | None) -> int:
    """Return the priority to start from after a restart or a reload.

    The restored value normally wins: it is what an automation last set, and
    losing that on every restart would make the whole entity pointless. But when
    the configured priority has changed since, the user has just said something
    newer in the options flow, and that wins instead.
    """
    if last_value is None:
        return configured
    if last_configured != configured:
        return configured
    return last_value


def resolve_minutes(restored: str | float | None) -> float:
    """Return the duration to start from after a restart.

    Een bewaarde waarde van buiten het bereik komt uit een oudere versie of uit
    een met de hand bewerkt bestand. Hem binnen de grenzen trekken is beter dan
    hem weggooien: de bedoeling was duidelijk, alleen het getal niet. Is er
    niets bewaard, of iets onleesbaars zoals `unavailable`, dan begint hij op
    de standaardduur.

    A stored value outside the range comes from an older version or a
    hand-edited file. Pulling it inside the bounds beats discarding it: the
    intent was clear, only the number was not. With nothing stored, or
    something unreadable such as `unavailable`, it starts on the default.
    """
    try:
        value = float(restored)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return float(DEFAULT_PRECONDITION_MINUTES)
    return float(min(max(value, MIN_PRECONDITION_MINUTES), MAX_PRECONDITION_MINUTES))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ClimateDirectorEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one priority entity per zone, plus the shared pre-conditioning duration."""
    coordinator = entry.runtime_data
    entities: list[NumberEntity] = [
        ZonePriorityNumber(coordinator, zone.zone_id) for zone in coordinator.config.zones
    ]
    entities.append(PreconditionMinutesNumber(coordinator))
    async_add_entities(entities)


class ZonePriorityNumber(ClimateDirectorEntity, NumberEntity, RestoreEntity):
    """How strongly one zone claims a shared outdoor unit. Lower wins."""

    _attr_translation_key = "zone_priority"
    _attr_icon = "mdi:sort-numeric-ascending"
    _attr_native_min_value = 0
    _attr_native_max_value = 99
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: ClimateDirectorCoordinator, zone_id: str) -> None:
        """Set up the priority entity for one zone."""
        super().__init__(coordinator, f"zone_{zone_id}_priority")
        self._zone_id = zone_id
        zone = coordinator.config.zone(zone_id)
        self._configured = zone.priority if zone else 0
        self._value = self._configured
        self._attr_translation_placeholders = {"zone": zone.name if zone else zone_id}

    async def async_added_to_hass(self) -> None:
        """Restore the last value before the first decision is made."""
        await super().async_added_to_hass()

        last = await self.async_get_last_state()
        last_value: int | None = None
        last_configured: int | None = None
        if last is not None:
            try:
                last_value = int(float(last.state))
            except (TypeError, ValueError):
                last_value = None
            raw = last.attributes.get(ATTR_CONFIGURED)
            last_configured = int(raw) if isinstance(raw, int | float) else None

        self._value = resolve_initial(self._configured, last_value, last_configured)
        self._push()

    @property
    def native_value(self) -> float:
        """Return the priority in force."""
        return self._value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the configured priority this entity started from."""
        return {ATTR_CONFIGURED: self._configured}

    async def async_set_native_value(self, value: float) -> None:
        """Set a new priority and decide again straight away."""
        self._value = int(value)
        self._push()
        self.async_write_ha_state()
        self.coordinator.async_request_evaluation()

    def _push(self) -> None:
        """Write this priority into the coordinator."""
        self.coordinator.zone_priorities[self._zone_id] = self._value

    def _handle_coordinator_update(self) -> None:
        """Ignore coordinator updates: this entity is an input, not an output."""


class PreconditionMinutesNumber(ClimateDirectorEntity, NumberEntity, RestoreEntity):
    """How long one press of a pre-conditioning button lasts.

    Een knop heeft geen velden, dus de duur staat ernaast. Dat is meteen de
    prettigste vorm: je zet hem één keer op wat bij je huis past en drukt
    daarna alleen nog op de knop.

    Het is geen tweede maximum. Het ingestelde maximum van de installatie kort
    een te lang verzoek alsnog in, dus deze staat er nooit overheen.

    A button has no fields, so the duration sits beside it. Which is the nicer
    shape anyway: set it once to what suits your house and after that you only
    press the button.

    It is not a second ceiling. The installation's own maximum still shortens a
    request that runs too long, so this can never overrule it.
    """

    _attr_translation_key = "precondition_minutes"
    _attr_icon = "mdi:timer-outline"
    _attr_native_min_value = MIN_PRECONDITION_MINUTES
    _attr_native_max_value = MAX_PRECONDITION_MINUTES
    _attr_native_step = 5
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: ClimateDirectorCoordinator) -> None:
        """Set up the shared duration entity."""
        super().__init__(coordinator, "precondition_minutes")
        self._value: float = DEFAULT_PRECONDITION_MINUTES

    async def async_added_to_hass(self) -> None:
        """Restore the duration that was set before the restart."""
        await super().async_added_to_hass()

        last = await self.async_get_last_state()
        self._value = resolve_minutes(last.state if last is not None else None)
        self._push()

    @property
    def native_value(self) -> float:
        """Return the duration in force."""
        return self._value

    async def async_set_native_value(self, value: float) -> None:
        """Set a new duration for the next press."""
        self._value = value
        self._push()
        self.async_write_ha_state()

    def _push(self) -> None:
        """Write this duration into the coordinator."""
        self.coordinator.precondition_minutes = self._value

    def _handle_coordinator_update(self) -> None:
        """Ignore coordinator updates: this entity is an input, not an output."""
