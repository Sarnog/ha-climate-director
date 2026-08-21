"""Bedieningsschakelaars: hoofdschakelaar, vakantiemodus en overrides.

Control switches: master, holiday mode, guest mode and per-zone overrides.

Deze schakelaars zijn de bedieningstoestand van de installatie, geen
configuratie. Ze herstellen zichzelf na een herstart en schrijven hun stand
terug naar de coordinator, die ze in de volgende momentopname meeneemt.

These switches are the installation's control state, not its configuration.
They restore themselves after a restart and write their state back to the
coordinator, which carries it into the next snapshot.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .coordinator import ClimateDirectorCoordinator, ClimateDirectorEntry
from .entity import ClimateDirectorEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ClimateDirectorEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the master, holiday and guest switches, and one override per zone."""
    coordinator = entry.runtime_data
    entities: list[SwitchEntity] = [
        MasterSwitch(coordinator),
        HolidaySwitch(coordinator),
        GuestSwitch(coordinator),
    ]
    entities.extend(
        ZoneOverrideSwitch(coordinator, zone.zone_id) for zone in coordinator.config.zones
    )
    async_add_entities(entities)


class _DirectorSwitch(ClimateDirectorEntity, SwitchEntity, RestoreEntity):
    """A switch whose state lives in the coordinator and survives a restart."""

    _default_on = False

    def __init__(self, coordinator: ClimateDirectorCoordinator, key: str) -> None:
        """Set up the switch."""
        super().__init__(coordinator, key)
        self._is_on = self._default_on

    async def async_added_to_hass(self) -> None:
        """Restore the saved state before the first decision is made."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in ("on", "off"):
            self._is_on = last.state == "on"
        self._push()

    @property
    def is_on(self) -> bool:
        """Return the switch state."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on and decide again."""
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off and decide again."""
        await self._set(False)

    async def _set(self, value: bool) -> None:
        self._is_on = value
        self._push()
        self.async_write_ha_state()
        self.coordinator.async_request_evaluation()

    def _push(self) -> None:
        """Write this switch's state into the coordinator."""
        raise NotImplementedError

    def _handle_coordinator_update(self) -> None:
        """Ignore coordinator updates: this switch is an input, not an output."""


class MasterSwitch(_DirectorSwitch):
    """Turns the whole director on and off."""

    _attr_translation_key = "master"
    _attr_icon = "mdi:home-thermometer"
    _default_on = True

    def __init__(self, coordinator: ClimateDirectorCoordinator) -> None:
        """Set up the master switch."""
        super().__init__(coordinator, "master")

    def _push(self) -> None:
        self.coordinator.master_enabled = self._is_on


class HolidaySwitch(_DirectorSwitch):
    """Holiday mode: every day counts as a Saturday, or as its own schedule."""

    _attr_translation_key = "holiday"
    _attr_icon = "mdi:palm-tree"

    def __init__(self, coordinator: ClimateDirectorCoordinator) -> None:
        """Set up the holiday switch."""
        super().__init__(coordinator, "holiday")

    def _push(self) -> None:
        self.coordinator.holiday_mode = self._is_on


class GuestSwitch(_DirectorSwitch):
    """Guest mode: keeps the house running while the residents are away."""

    _attr_translation_key = "guest"
    _attr_icon = "mdi:account-multiple-plus"

    def __init__(self, coordinator: ClimateDirectorCoordinator) -> None:
        """Set up the guest switch."""
        super().__init__(coordinator, "guest")

    def _push(self) -> None:
        self.coordinator.guest_mode = self._is_on


class ZoneOverrideSwitch(_DirectorSwitch):
    """Hands one zone back to the user until it is turned off again."""

    _attr_translation_key = "zone_override"
    _attr_icon = "mdi:hand-back-right"

    def __init__(self, coordinator: ClimateDirectorCoordinator, zone_id: str) -> None:
        """Set up the override switch for one zone."""
        self._zone_id = zone_id
        super().__init__(coordinator, f"zone_{zone_id}_override")
        zone = coordinator.config.zone(zone_id)
        self._attr_translation_placeholders = {"zone": zone.name if zone else zone_id}

    def _push(self) -> None:
        self.coordinator.zone_overrides[self._zone_id] = self._is_on

    def _handle_coordinator_update(self) -> None:
        """Follow the coordinator, and write the lapse away when it lets go.

        De noodknop vervalt bij bedtijd en bij een leeg huis: de coordinator
        gooit `zone_overrides` dan leeg. Zou de schakelaar haar eigen stand
        houden, dan stond ze aan terwijl de zone allang weer meedraait - en erger:
        een herstart herstelt die `on` terug de coordinator in, zodat de
        overgedragen zone herleeft. Daarom wordt de stand hier bijgewerkt én
        weggeschreven.

        The emergency handle lapses at bedtime and on an empty house: the
        coordinator then empties `zone_overrides`. Were the switch to keep its
        own state it would read on while the zone has long since rejoined - and
        worse: a restart restores that `on` back into the coordinator, so the
        handed-over zone revives. Hence the state is both updated and written
        away here.
        """
        self._is_on = self.coordinator.zone_overrides.get(self._zone_id, False)
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return the switch state, following the coordinator when it lets go."""
        return self.coordinator.zone_overrides.get(self._zone_id, False)
