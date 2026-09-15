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
import re
from typing import Any

import voluptuous as vol
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
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
    ATTR_ENTRY_ID,
    ATTR_HVAC_MODE,
    ATTR_IGNORE_OPENINGS,
    ATTR_MINUTES,
    ATTR_TEMPERATURE,
    ATTR_WHEN_DONE,
    ATTR_ZONE_ID,
    ATTR_ZONE_IDS,
    DOMAIN,
    EVENT_AUTOMATION_RELOADED,
    PLATFORMS,
    SERVICE_CANCEL_PRECONDITION,
    SERVICE_CLEAR_OVERRIDE,
    SERVICE_EVALUATE,
    SERVICE_PRECONDITION,
    SERVICE_SET_OVERRIDE,
    STORAGE_VERSION,
    WHEN_DONE_LEAVE,
    WHEN_DONE_TURN_OFF,
)
from .coordinator import ClimateDirectorCoordinator, ClimateDirectorEntry, storage_key
from .engine import DirectorConfig
from .units import temperature_unit_of, to_celsius

_LOGGER = logging.getLogger(__name__)

__all__ = ["DOMAIN", "async_remove_entry", "async_setup", "async_setup_entry", "async_unload_entry"]

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

_OVERRIDE_WHEN_DONE = vol.In([WHEN_DONE_TURN_OFF, WHEN_DONE_LEAVE])

#: De twee unique-id-vormen die als override-doel tellen: de schakelaar van een
#: zone en de eindtijdsensor van diezelfde zone. Al het andere is geen doel.
#:
#: The two unique-id shapes that count as an override target: a zone's switch
#: and that same zone's end-time sensor. Anything else is not a target.
_OVERRIDE_TARGET = re.compile(r"^zone_(?P<zone>.+)_override(?P<sensor>_ends)?$")

_SET_OVERRIDE_FIELDS: dict[Any, Any] = {
    **_ENTRIES,
    vol.Optional(ATTR_ENTITY_ID): cv.entity_ids,
    vol.Optional(ATTR_ZONE_ID): cv.string,
    vol.Required(ATTR_HVAC_MODE): cv.string,
    vol.Optional(ATTR_TEMPERATURE): vol.All(vol.Coerce(float)),
    vol.Optional(ATTR_MINUTES): vol.All(vol.Coerce(float), vol.Range(min=1)),
    vol.Optional(ATTR_WHEN_DONE, default=WHEN_DONE_TURN_OFF): _OVERRIDE_WHEN_DONE,
}
_SET_OVERRIDE_SCHEMA = vol.Schema(_SET_OVERRIDE_FIELDS)

_CLEAR_OVERRIDE_FIELDS: dict[Any, Any] = {
    **_ENTRIES,
    vol.Optional(ATTR_ENTITY_ID): cv.entity_ids,
    vol.Optional(ATTR_ZONE_ID): cv.string,
}
_CLEAR_OVERRIDE_SCHEMA = vol.Schema(_CLEAR_OVERRIDE_FIELDS)


async def async_setup(hass: HomeAssistant, _config: dict[str, object]) -> bool:
    """Register the domain's actions, also without a loaded installation.

    De acties horen bij het domein, niet bij een entry: ze bestaan zodra Home
    Assistant het domein opzet, zodat een aanroep zonder geladen installatie
    netjes botst met de installatie-fout in plaats van met "service not found".

    The actions belong to the domain rather than to an entry: they exist as soon
    as Home Assistant sets the domain up, so a call without a loaded installation
    hits the installation error instead of "service not found".
    """
    _async_register_services(hass)
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

    _async_register_services(hass)
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


def _chosen_entries(hass: HomeAssistant, call: ServiceCall) -> list[ClimateDirectorEntry]:
    """Return the installations a call wants, or all loaded ones."""
    wanted = set(call.data.get(ATTR_ENTRY_ID) or ())
    return [
        entry
        for entry in hass.config_entries.async_loaded_entries(DOMAIN)
        if not wanted or entry.entry_id in wanted
    ]


def _override_setpoint(temperature: float | None, unit: str) -> float | None:
    """Return the override's setpoint in Celsius.

    Alleen de eenheidsomrekening. Het klemmen naar `min_temp`/`max_temp` van het
    apparaat gebeurt in de beslisronde waarin het commando werkelijk de deur uit
    gaat (R28-2): daar is de wereld al in de hand, en tussen de aanroep en die
    ronde kan het bereik van het apparaat veranderen - een cloud-drop-out laat
    `min_temp` even verdwijnen, of een apparaat meldt zijn bereik pas later.
    Beide paden gebruiken daar dezelfde `engine.clamped_target`.

    Only the unit conversion. Pressing the setpoint into the appliance's
    `min_temp`/`max_temp` happens in the decision round that really puts the
    command on the wire (R28-2): the world is already in hand there, and between
    the call and that round the appliance's range can change - a cloud drop-out
    makes `min_temp` disappear for a while, or an appliance only reports its
    range later. Both paths use the same `engine.clamped_target` there.
    """
    if temperature is None:
        return None
    return to_celsius(temperature, unit)


def _refuse_unknown_zones(
    zone_ids: list[str] | None,
    entries: list[ClimateDirectorEntry],
    wanted_entry_id: list[str] | str | None,
) -> None:
    """Raise when a requested zone does not exist, instead of only logging.

    Een typefout in `zone_ids` verdween tot nu toe met alleen een logregel:
    je drukt op de knop, er gebeurt niets, en nergens staat waarom. Een
    service die de zone niet kent hoort te botsen, precies zoals een
    onbekende entiteit dat doet. Een onbekende `entry_id` is hetzelfde
    verhaal één niveau hoger: dan bestaat de installatie niet en hoort de
    fout dat te zeggen, in plaats van elke zone als onbekend af te
    schilderen.

    A typo in `zone_ids` used to vanish with only a log line: you press the
    button, nothing happens, and nowhere does it say why. A service that does
    not know the zone should collide, exactly like an unknown entity does. An
    unknown `entry_id` is the same story one level up: the installation does
    not exist then, and the error should say so instead of painting every zone
    as unknown.
    """
    if not entries:
        if wanted_entry_id:
            wanted = (
                ", ".join(wanted_entry_id)
                if isinstance(wanted_entry_id, list)
                else str(wanted_entry_id)
            )
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_installation",
                translation_placeholders={"installation": wanted},
            )
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="no_installation_configured",
        )
    if not zone_ids:
        return
    known = {zone.zone_id for entry in entries for zone in entry.runtime_data.config.zones}
    unknown = sorted(set(zone_ids) - known)
    if unknown:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="unknown_zones",
            translation_placeholders={"zones": ", ".join(unknown)},
        )


@callback
def _override_entity_target(
    hass: HomeAssistant,
    entity_id: str,
    wanted_entry_id: list[str] | None,
) -> tuple[ClimateDirectorEntry, str]:
    """Return the installation and zone one override entity points at.

    De kaart `simple-timer-card` stuurt bij een timestamp-sensor geen `data` mee:
    hij zet de sensor zelf als `target.entity_id` in de aanroep. Home Assistant
    plakt dat doel vóór de schemavalidatie aan de data, dus de actie krijgt
    `entity_id` binnen en moet daar de zone en de installatie uit halen. Dat gaat
    via het entiteitenregister, en alleen de twee entiteiten die deze integratie
    voor een override maakt tellen mee: de overrideschakelaar van een zone en de
    eindtijdsensor van diezelfde zone. Al het andere is een typefout en hoort te
    botsen in plaats van stil niets te doen.

    The `simple-timer-card` card sends no `data` for a timestamp sensor: it puts
    the sensor itself in the call as `target.entity_id`. Home Assistant merges
    that target into the data before schema validation, so the action receives
    `entity_id` and has to derive the zone and the installation from it. That
    goes through the entity registry, and only the two entities this integration
    creates for an override count: a zone's override switch and that same zone's
    end-time sensor. Anything else is a typo and should collide instead of
    quietly doing nothing.
    """
    registry = er.async_get(hass)
    registered = registry.async_get(entity_id)
    entry_id = registered.config_entry_id if registered is not None else None
    match: re.Match[str] | None = None
    if registered is not None and entry_id is not None:
        match = _OVERRIDE_TARGET.fullmatch(registered.unique_id.removeprefix(f"{entry_id}_"))
    if match is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="not_an_override_entity",
            translation_placeholders={"entity": entity_id},
        )
    entry = next(
        (
            item
            for item in hass.config_entries.async_loaded_entries(DOMAIN)
            if item.entry_id == entry_id
        ),
        None,
    )
    if entry is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="unknown_installation",
            translation_placeholders={"installation": str(entry_id)},
        )
    if wanted_entry_id and entry_id not in wanted_entry_id:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="unknown_installation",
            translation_placeholders={"installation": ", ".join(wanted_entry_id)},
        )
    return entry, match.group("zone")


def _override_targets(
    hass: HomeAssistant, call: ServiceCall
) -> list[tuple[ClimateDirectorEntry, str]]:
    """Resolve an override call into installation-and-zone pairs.

    Twee vormen. Met `entity_id` bepaalt de entiteit de installatie én de zone —
    dat is de vorm die de kaart stuurt. Met `zone_id` blijft het gedrag van vóór
    deze versie staan: elke gekozen installatie, of precies die uit `entry_id`.
    Minstens één van de twee is verplicht, en een `zone_id` die niet bij de
    opgegeven entiteit hoort is een tegenspraak in plaats van een keuze. Een zone
    hoeft op dit pad niet apart getoetst te worden: de entiteit is er een die
    deze integratie zelf voor díe zone maakte, en een zone die uit de
    configuratie verdwijnt laat zijn entiteiten bij de volgende opzet opruimen
    (`_async_remove_stale_entities`).

    Two shapes. With `entity_id` the entity settles the installation *and* the
    zone — that is the shape the card sends. With `zone_id` the behaviour from
    before this version stands: every chosen installation, or exactly the one
    from `entry_id`. At least one of the two is required, and a `zone_id` that
    does not belong to the given entity is a contradiction rather than a choice.
    A zone needs no separate check on this path: the entity is one this
    integration created for *that* zone itself, and a zone that leaves the
    configuration has its entities cleaned up at the next setup
    (`_async_remove_stale_entities`).
    """
    entity_ids = call.data.get(ATTR_ENTITY_ID)
    zone_id = call.data.get(ATTR_ZONE_ID)
    if entity_ids:
        targets = [
            _override_entity_target(hass, entity_id, call.data.get(ATTR_ENTRY_ID))
            for entity_id in entity_ids
        ]
        if zone_id is not None and any(resolved != zone_id for _, resolved in targets):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="override_target_conflict",
                translation_placeholders={"zone": zone_id},
            )
        return targets
    if zone_id is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="override_needs_a_target",
        )
    entries = _chosen_entries(hass, call)
    _refuse_unknown_zones([zone_id], entries, call.data.get(ATTR_ENTRY_ID))
    return [(entry, zone_id) for entry in entries]


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
        entries = _chosen_entries(hass, call)
        _refuse_unknown_zones(call.data.get(ATTR_ZONE_IDS), entries, call.data.get(ATTR_ENTRY_ID))
        for entry in entries:
            entry.runtime_data.async_precondition(
                call.data.get(ATTR_ZONE_IDS),
                call.data.get(ATTR_MINUTES),
                ignore_openings=call.data.get(ATTR_IGNORE_OPENINGS, False),
            )

    async def _async_cancel_precondition(call: ServiceCall) -> None:
        """Call a running pre-conditioning request off."""
        entries = _chosen_entries(hass, call)
        _refuse_unknown_zones(call.data.get(ATTR_ZONE_IDS), entries, call.data.get(ATTR_ENTRY_ID))
        for entry in entries:
            entry.runtime_data.async_cancel_precondition(call.data.get(ATTR_ZONE_IDS))

    async def _async_set_override(call: ServiceCall) -> None:
        """Hand a zone over for a duration, with the appliance already set."""
        targets = _override_targets(hass, call)
        hvac_mode = call.data[ATTR_HVAC_MODE]
        temperature = call.data.get(ATTR_TEMPERATURE)
        unit = temperature_unit_of(hass)
        minutes = call.data.get(ATTR_MINUTES)
        when_done = call.data.get(ATTR_WHEN_DONE, WHEN_DONE_TURN_OFF)
        for entry, zone_id in targets:
            runtime = entry.runtime_data
            source = runtime.override_source(zone_id, hvac_mode)
            if source is None:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="zone_no_source_for_mode",
                    translation_placeholders={"zone": zone_id, "mode": hvac_mode},
                )
            runtime.async_set_override(
                zone_id,
                hvac_mode,
                _override_setpoint(temperature, unit),
                minutes,
                when_done,
            )

    async def _async_clear_override(call: ServiceCall) -> None:
        """End the override the way a hand-off of the switch does: silently."""
        for entry, zone_id in _override_targets(hass, call):
            entry.runtime_data.async_clear_override(zone_id)

    hass.services.async_register(DOMAIN, SERVICE_EVALUATE, _async_evaluate, _EVALUATE_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_PRECONDITION, _async_precondition, _PRECONDITION_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CANCEL_PRECONDITION, _async_cancel_precondition, _CANCEL_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_OVERRIDE, _async_set_override, _SET_OVERRIDE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CLEAR_OVERRIDE, _async_clear_override, _CLEAR_OVERRIDE_SCHEMA
    )
