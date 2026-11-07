"""De service-API van Climate Director.

Climate Director's service API.
"""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol
from homeassistant.components.climate.const import ATTR_HVAC_MODE
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .const import (
    ATTR_ENTRY_ID,
    ATTR_IGNORE_OPENINGS,
    ATTR_MINUTES,
    ATTR_WHEN_DONE,
    ATTR_ZONE_ID,
    ATTR_ZONE_IDS,
    DOMAIN,
    SERVICE_CANCEL_PRECONDITION,
    SERVICE_CLEAR_OVERRIDE,
    SERVICE_EVALUATE,
    SERVICE_PRECONDITION,
    SERVICE_SET_OVERRIDE,
    WHEN_DONE_LEAVE,
    WHEN_DONE_TURN_OFF,
)
from .coordinator import ClimateDirectorEntry
from .units import temperature_unit_of, to_celsius

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

_OVERRIDE_TARGET = re.compile(r"^zone_(?P<zone>.+)_override(?P<sensor>_ends)?$")
_OVERRIDE_DOMAINS = ("sensor", "switch")


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
    gaat: daar is de wereld al in de hand, en tussen de aanroep en die
    ronde kan het bereik van het apparaat veranderen - een cloud-drop-out laat
    `min_temp` even verdwijnen, of een apparaat meldt zijn bereik pas later.
    Beide paden gebruiken daar dezelfde `engine.clamped_target`.

    Only the unit conversion. Pressing the setpoint into the appliance's
    `min_temp`/`max_temp` happens in the decision round that really puts the
    command on the wire: the world is already in hand there, and between
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

    Die toets is volledig: entry, platform, domein én
    prefix moeten alle vier kloppen voordat de `unique_id` op het patroon mag
    passen. Zie anker 11 in ARCHITECTURE.md voor waarom.

    The `simple-timer-card` card sends no `data` for a timestamp sensor: it puts
    the sensor itself in the call as `target.entity_id`. Home Assistant merges
    that target into the data before schema validation, so the action receives
    `entity_id` and has to derive the zone and the installation from it. That
    goes through the entity registry, and only the two entities this integration
    creates for an override count: a zone's override switch and that same zone's
    end-time sensor. Anything else is a typo and should collide instead of
    quietly doing nothing.

    That check is complete: entry, platform, domain
    and prefix all have to hold before the `unique_id` may fit the pattern. See
    anchor 11 in ARCHITECTURE.md for why.
    """
    registry = er.async_get(hass)
    registered = registry.async_get(entity_id)
    entry_id = registered.config_entry_id if registered is not None else None
    entry = hass.config_entries.async_get_entry(entry_id) if entry_id else None
    prefix = f"{entry_id}_"
    match: re.Match[str] | None = None
    if (
        registered is not None
        and entry is not None
        and entry.domain == DOMAIN
        and registered.platform == DOMAIN
        and registered.domain in _OVERRIDE_DOMAINS
        and registered.unique_id.startswith(prefix)
    ):
        match = _OVERRIDE_TARGET.fullmatch(registered.unique_id[len(prefix) :])
    if match is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="not_an_override_entity",
            translation_placeholders={"entity": entity_id},
        )
    loaded = next(
        (
            item
            for item in hass.config_entries.async_loaded_entries(DOMAIN)
            if item.entry_id == entry_id
        ),
        None,
    )
    if loaded is None:
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
    return loaded, match.group("zone")


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


def async_register_services(hass: HomeAssistant) -> None:
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
            if entry.runtime_data.override_source(zone_id, hvac_mode) is None:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="zone_no_source_for_mode",
                    translation_placeholders={"zone": zone_id, "mode": hvac_mode},
                )
        for entry, zone_id in targets:
            entry.runtime_data.async_set_override(
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
