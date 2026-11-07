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

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.storage import Store
from homeassistant.loader import async_get_integration

from . import (
    binary_sensor as binary_sensor_platform,
)
from . import (
    button as button_platform,
)
from . import (
    number as number_platform,
)
from . import (
    problems,
    texts,
)
from . import (
    select as select_platform,
)
from . import (
    sensor as sensor_platform,
)
from . import (
    switch as switch_platform,
)
from .const import (
    DOMAIN,
    EVENT_AUTOMATION_RELOADED,
    PLATFORMS,
    STORAGE_VERSION,
)
from .coordinator import ClimateDirectorCoordinator, ClimateDirectorEntry, storage_key
from .engine import DirectorConfig
from .services import async_register_services

_LOGGER = logging.getLogger(__name__)

__all__ = ["DOMAIN", "async_remove_entry", "async_setup", "async_setup_entry", "async_unload_entry"]


async def async_setup(hass: HomeAssistant, _config: dict[str, object]) -> bool:
    """Register the domain's actions, also without a loaded installation.

    De acties horen bij het domein, niet bij een entry: ze bestaan zodra Home
    Assistant het domein opzet, zodat een aanroep zonder geladen installatie
    netjes botst met de installatie-fout in plaats van met "service not found".

    The actions belong to the domain rather than to an entry: they exist as soon
    as Home Assistant sets the domain up, so a call without a loaded installation
    hits the installation error instead of "service not found".
    """
    async_register_services(hass)
    return True


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

    async_register_services(hass)
    _async_remove_stale_entities(hass, entry)

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
    def _recheck(_event: Event | HomeAssistant | None = None) -> None:
        problems.async_check_watchers(hass)

    entry.async_on_unload(async_at_started(hass, _recheck))
    entry.async_on_unload(hass.bus.async_listen(EVENT_AUTOMATION_RELOADED, _recheck))


def _wanted_entity_keys(config: DirectorConfig) -> set[str]:
    """Return every unique-id key the platforms will create for `config`.

    Opgebouwd uit de platforms zelf, niet uit een lijstje achtervoegsels: komt
    er een entiteit bij of vervalt er een, dan verandert deze verzameling mee
    in plaats van stilletjes achter te lopen.

    Built from the platforms themselves rather than from a list of suffixes:
    when an entity is added or dropped this set moves with it instead of
    quietly falling behind.
    """
    keys: set[str] = set()
    for builder in (
        binary_sensor_platform.wanted_entity_keys,
        button_platform.wanted_entity_keys,
        number_platform.wanted_entity_keys,
        select_platform.wanted_entity_keys,
        sensor_platform.wanted_entity_keys,
        switch_platform.wanted_entity_keys,
    ):
        keys.update(builder(config))
    return keys


@callback
def _async_remove_stale_entities(hass: HomeAssistant, entry: ClimateDirectorEntry) -> None:
    """Remove entities of this entry whose key the platforms no longer create.

    Een verwijderde zone of een verwijderd apparaat verdwijnt uit de
    configuratie, maar zijn entiteiten blijven in het entiteitenregister staan
    als `unavailable`, en die komen nooit meer vanzelf weg. Ze hangen allemaal
    aan het ene apparaat van de installatie, dus
    `async_remove_config_entry_device` kan hier niets: opruimen op basis van de
    sleutel is de enige weg. Dit gebeurt bij het opzetten, zodat een herstart
    of herlaadbeurt ze opruimt voordat de platforms de entiteiten van nu
    opnieuw aanmaken.

    A removed zone or a removed appliance disappears from the configuration,
    but its entities stay in the entity registry as `unavailable`, and they
    never go away by themselves. They all hang off the installation's single
    device, so `async_remove_config_entry_device` cannot help here: cleaning by
    key is the only way. This runs at setup, so a restart or reload clears them
    before the platforms re-create today's entities.
    """
    registry = er.async_get(hass)
    wanted = _wanted_entity_keys(entry.runtime_data.config)
    prefix = f"{entry.entry_id}_"
    for entity in list(registry.entities.values()):
        if (
            entity.config_entry_id == entry.entry_id
            and entity.unique_id.startswith(prefix)
            and entity.unique_id[len(prefix) :] not in wanted
        ):
            registry.async_remove(entity.entity_id)


async def async_unload_entry(hass: HomeAssistant, entry: ClimateDirectorEntry) -> bool:
    """Tear one installation down."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    # De coordinator stopt altijd, ook als een platform weigerde uit te laden.
    # Zijn timers horen bij de coordinator en mogen niet doordraaien terwijl
    # de entry afgebroken wordt; dat zou een dode coordinator elke ronde
    # beslissingen laten nemen.
    #
    # The coordinator always stops, even when a platform refused to unload. Its
    # timers belong to the coordinator and must not keep running while the entry
    # is being torn down; that would leave a dead coordinator deciding round
    # after round.
    await entry.runtime_data.async_shutdown()
    if unloaded:
        problems.async_clear(hass, entry.entry_id)
        problems.async_clear_manual_sources(hass, entry.entry_id)
        problems.async_clear_unreadable(hass, entry.entry_id)
        problems.async_clear_unsupported_modes(hass, entry.entry_id)
        problems.async_clear_command_not_taking(hass, entry.entry_id)
        problems.async_clear_bypassed_openings(hass, entry.entry_id)
        problems.async_clear_season_override(hass, entry.entry_id)
        problems.async_clear_corrupt_storage(hass, entry.entry_id)
        # De luistermelding is er één voor de hele integratie, dus hij gaat pas
        # weg als de laatste installatie weg is.
        #
        # The listener notice is one for the whole integration, so it only goes
        # when the last installation does.
        if not hass.config_entries.async_loaded_entries(DOMAIN):
            problems.async_clear_watchers(hass)
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
