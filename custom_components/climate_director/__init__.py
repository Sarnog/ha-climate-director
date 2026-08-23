"""Climate Director - orkestreert bestaande climate-entiteiten.

Climate Director - orchestrates existing climate entities.

Deze integratie is opgebouwd in twee helften. `engine/` bevat de volledige
besliskunde als pure Python zonder Home Assistant-imports; de rest van dit
pakket koppelt die engine aan Home Assistant.

This integration is built in two halves. `engine/` holds all decision logic as
pure Python without Home Assistant imports; the rest of this package binds that
engine to Home Assistant.
"""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.storage import Store
from homeassistant.loader import async_get_integration

from . import problems, texts
from .const import (
    ATTR_ENTRY_ID,
    ATTR_IGNORE_OPENINGS,
    ATTR_MINUTES,
    ATTR_ZONE_IDS,
    DOMAIN,
    EVENT_AUTOMATION_RELOADED,
    PLATFORMS,
    SERVICE_CANCEL_PRECONDITION,
    SERVICE_EVALUATE,
    SERVICE_PRECONDITION,
    STORAGE_VERSION,
)
from .coordinator import ClimateDirectorCoordinator, ClimateDirectorEntry, storage_key

_LOGGER = logging.getLogger(__name__)

__all__ = ["DOMAIN", "async_remove_entry", "async_setup_entry", "async_unload_entry"]

_EVALUATE_SCHEMA = vol.Schema({vol.Optional(ATTR_ENTRY_ID): vol.All(cv.ensure_list, [cv.string])})

_ENTRIES = {vol.Optional(ATTR_ENTRY_ID): vol.All(cv.ensure_list, [cv.string])}
_ZONES = {vol.Optional(ATTR_ZONE_IDS): vol.All(cv.ensure_list, [cv.string])}

_PRECONDITION_SCHEMA = vol.Schema(
    {
        **_ENTRIES,
        **_ZONES,
        # Ondergrens 1, gelijk aan `min: 1` in services.yaml. Nul stond het
        # schema wel toe en werd daarna in stilte weggegooid: je drukt op de
        # knop, er gebeurt niets, en nergens staat waarom.
        #
        # Lower bound 1, matching `min: 1` in services.yaml. Zero passed the
        # schema and was then quietly thrown away: you press the button, nothing
        # happens, and nowhere does it say why.
        vol.Optional(ATTR_MINUTES): vol.All(vol.Coerce(float), vol.Range(min=1)),
        vol.Optional(ATTR_IGNORE_OPENINGS, default=False): cv.boolean,
    }
)

_CANCEL_SCHEMA = vol.Schema({**_ENTRIES, **_ZONES})


async def async_setup_entry(hass: HomeAssistant, entry: ClimateDirectorEntry) -> bool:
    """Set up one installation."""
    coordinator = ClimateDirectorCoordinator(hass, entry)
    coordinator.version = str((await async_get_integration(hass, DOMAIN)).version or "")
    entry.runtime_data = coordinator

    await texts.async_prepare(hass)
    found = problems.async_report(hass, entry.entry_id, entry.title, coordinator.config)
    if found:
        _LOGGER.warning(
            "%s has %d configuration problem(s): %s", entry.title, len(found), "; ".join(found)
        )
    problems.async_report_manual_sources(
        hass, entry.entry_id, entry.title, entry.options, coordinator.config
    )

    _async_register_services(hass)

    # De platforms gaan eerst omhoog, zodat de schakelaars hun bewaarde stand
    # al hersteld hebben voordat er voor het eerst besloten wordt. Anders zou
    # een uitgeschakelde hoofdschakelaar één ronde lang aan lijken te staan.
    #
    # Platforms come up first, so the switches have restored their saved state
    # before the first decision. Otherwise a master switch left off would look
    # on for one round.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await coordinator.async_start()

    _async_watch_for_listeners(hass, entry)

    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


@callback
def _async_watch_for_listeners(hass: HomeAssistant, entry: ClimateDirectorEntry) -> None:
    """Keep an eye on whether anybody hears a refused pre-conditioning request.

    Pas nadat Home Assistant klaar is met starten, want daarvoor zijn de
    automatiseringen er nog niet en zou de melding over iets klagen dat een
    seconde later gewoon goed staat. Daarna opnieuw bij elke herlaadbeurt van
    de automatiseringen - dat is ook wat er gebeurt als je er in de interface
    een aanmaakt.

    Only after Home Assistant has finished starting, since before that the
    automations are not there yet and the notice would complain about something
    that is fine a second later. After that, again on every automation reload -
    which is also what happens when you create one in the interface.
    """

    @callback
    def _recheck(_event: Event | None = None) -> None:
        problems.async_check_watchers(hass)

    entry.async_on_unload(async_at_started(hass, _recheck))
    entry.async_on_unload(hass.bus.async_listen(EVENT_AUTOMATION_RELOADED, _recheck))


async def async_unload_entry(hass: HomeAssistant, entry: ClimateDirectorEntry) -> bool:
    """Tear one installation down."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_shutdown()
        problems.async_clear(hass, entry.entry_id)
        problems.async_clear_manual_sources(hass, entry.entry_id)
        problems.async_clear_unreadable(hass, entry.entry_id)
        problems.async_clear_unsupported_modes(hass, entry.entry_id)
        problems.async_clear_command_not_taking(hass, entry.entry_id)
        problems.async_clear_corrupt_storage(hass, entry.entry_id)
        # De luistermelding is er één voor de hele integratie, dus hij gaat pas
        # weg als de laatste installatie weg is.
        #
        # The listener notice is one for the whole integration, so it only goes
        # when the last installation does.
        if not hass.config_entries.async_loaded_entries(DOMAIN):
            problems.async_clear_watchers(hass)
            _async_remove_services(hass)
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ClimateDirectorEntry) -> None:
    """Throw away what this installation kept by hand once it is deleted.

    Het opslagbestand hangt aan de entry en niets anders leest het. Blijft het
    staan, dan verzamelt `.storage` bij elke verwijderde installatie een bestand
    dat nooit meer opengaat - en een nieuwe installatie krijgt een nieuwe
    entry_id, dus hergebruikt wordt het ook niet.

    The storage file belongs to the entry and nothing else reads it. Left
    behind, `.storage` collects a file per deleted installation that never opens
    again - and a new installation gets a new entry_id, so it is not reused
    either.
    """
    await Store(hass, STORAGE_VERSION, storage_key(entry.entry_id)).async_remove()


async def _async_reload(hass: HomeAssistant, entry: ClimateDirectorEntry) -> None:
    """Reload after the options changed, since the whole layout may have."""
    await hass.config_entries.async_reload(entry.entry_id)


@callback
def _async_remove_services(hass: HomeAssistant) -> None:
    """Take the domain's actions away with the last installation.

    Ze horen bij de integratie, niet bij een entry, dus ze worden ook maar één
    keer aangemeld. Bleven ze na het afbreken staan, dan deed een aanroep in
    stilte niets: de handler loopt over de geladen installaties, en dat zijn er
    dan nul. Een actie die er is en niets doet is erger dan een actie die er
    niet is - dan zegt Home Assistant tenminste dat hij niet bestaat.

    They belong to the integration rather than to an entry, so they are
    registered only once. Left standing after tearing down, a call quietly did
    nothing: the handler walks the loaded installations, and there are none. An
    action that exists and does nothing is worse than an action that does not
    exist - at least then Home Assistant says so.
    """
    for service in (SERVICE_EVALUATE, SERVICE_PRECONDITION, SERVICE_CANCEL_PRECONDITION):
        hass.services.async_remove(DOMAIN, service)


@callback
def _async_register_services(hass: HomeAssistant) -> None:
    """Register the domain's actions once, however many installations there are.

    Actions belong to the domain rather than to an entry, so registering them
    per entry would have the second installation overwrite the first's handler.
    """
    if hass.services.has_service(DOMAIN, SERVICE_EVALUATE):
        return

    async def _async_evaluate(call: ServiceCall) -> None:
        """Ask one or every installation to decide again right now."""
        wanted = set(call.data.get(ATTR_ENTRY_ID) or ())
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            if wanted and entry.entry_id not in wanted:
                continue
            entry.runtime_data.async_request_evaluation()

    async def _async_precondition(call: ServiceCall) -> None:
        """Warm zones up for somebody on their way home."""
        entries = _chosen(call)
        _refuse_unknown_zones(call.data.get(ATTR_ZONE_IDS), entries)
        for entry in entries:
            entry.runtime_data.async_precondition(
                call.data.get(ATTR_ZONE_IDS),
                call.data.get(ATTR_MINUTES),
                ignore_openings=call.data.get(ATTR_IGNORE_OPENINGS, False),
            )

    async def _async_cancel_precondition(call: ServiceCall) -> None:
        """Call a running pre-conditioning request off."""
        entries = _chosen(call)
        _refuse_unknown_zones(call.data.get(ATTR_ZONE_IDS), entries)
        for entry in entries:
            entry.runtime_data.async_cancel_precondition(call.data.get(ATTR_ZONE_IDS))

    def _refuse_unknown_zones(zone_ids, entries) -> None:
        """Raise when a requested zone does not exist, instead of only logging.

        Een typefout in `zone_ids` verdween tot nu toe met alleen een
        logregel: je drukt op de knop, er gebeurt niets, en nergens staat
        waarom. Een service die de zone niet kent hoort te botsen, precies
        zoals een onbekende entiteit dat doet.

        A typo in `zone_ids` used to vanish with only a log line: you press the
        button, nothing happens, and nowhere does it say why. A service that
        does not know the zone should collide, exactly like an unknown entity
        does.
        """
        if not zone_ids:
            return
        known = {zone.zone_id for entry in entries for zone in entry.runtime_data.config.zones}
        unknown = sorted(set(zone_ids) - known)
        if unknown:
            raise ServiceValidationError(f"unknown zones: {', '.join(unknown)}")

    def _chosen(call: ServiceCall):
        wanted = set(call.data.get(ATTR_ENTRY_ID) or ())
        return [
            entry
            for entry in hass.config_entries.async_loaded_entries(DOMAIN)
            if not wanted or entry.entry_id in wanted
        ]

    hass.services.async_register(DOMAIN, SERVICE_EVALUATE, _async_evaluate, _EVALUATE_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_PRECONDITION, _async_precondition, _PRECONDITION_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CANCEL_PRECONDITION, _async_cancel_precondition, _CANCEL_SCHEMA
    )
