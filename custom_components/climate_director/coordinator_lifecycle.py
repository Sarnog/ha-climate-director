"""Levensduur en agenda van de coordinator. / The coordinator's lifetime and calendar."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .engine.models import SeasonSource

if TYPE_CHECKING:
    from .coordinator import ClimateDirectorCoordinator

_LOGGER = logging.getLogger(__name__)
_COMMAND_NOT_TAKING_ROUNDS = 10


def tracked_entities(coordinator: ClimateDirectorCoordinator) -> set[str]:
    """Return every entity whose change could alter a decision.

    Circuit units are included even when the director does not manage them:
    an indoor unit somebody switches on by remote still claims the
    compressor, and the plan has to be recomputed when it does.
    """
    entities: set[str] = set()

    if coordinator.config.outdoor_sensor:
        entities.add(coordinator.config.outdoor_sensor)
    if (
        coordinator.config.seasons.source is SeasonSource.ENTITY
        and coordinator.config.seasons.entity_id
    ):
        entities.add(coordinator.config.seasons.entity_id)
    if coordinator.config.precipitation.enabled:
        entities.add(coordinator.config.precipitation.source)

    for zone in coordinator.config.zones:
        if zone.indoor_sensor:
            entities.add(zone.indoor_sensor)
        if zone.presence_entity:
            entities.add(zone.presence_entity)
        entities.update(source.entity_id for source in zone.sources if source.entity_id)

    for circuit in coordinator.config.circuits:
        entities.update(unit for unit in circuit.units if unit)

    entities.update(item.entity_id for item in coordinator.config.generators if item.entity_id)

    for opening in coordinator.config.openings:
        if opening.entity_id:
            entities.add(opening.entity_id)

    entities.update(item for item in coordinator.config.holiday_calendars if item)

    for resident in coordinator.config.residents:
        if resident.presence_entity:
            entities.add(resident.presence_entity)
        if resident.sleep_entity:
            entities.add(resident.sleep_entity)

    return entities


def _calendar_says_holiday(coordinator: ClimateDirectorCoordinator) -> bool:
    """Return whether a configured calendar has a holiday running right now.

    Een agenda-item telt zodra het loopt en het trefwoord erin voorkomt.
    Zonder trefwoord blijven de agenda's buiten beschouwing: raden welk item
    vakantie bedoelde is niet aan de integratie.

    An event counts once it is running and carries the keyword. Without a
    keyword the calendars are left alone: guessing which event meant a
    holiday is not the integration's call to make.
    """
    keyword = coordinator.config.holiday_keyword.strip().casefold()
    if not keyword:
        return False

    for entity_id in coordinator.config.holiday_calendars:
        state = coordinator.hass.states.get(entity_id)
        if state is None or state.state != "on":
            continue
        haystack = " ".join(
            str(state.attributes.get(field) or "")
            for field in ("message", "summary", "description", "location")
        ).casefold()
        if keyword in haystack:
            return True

    return False


async def async_shutdown(coordinator: ClimateDirectorCoordinator) -> None:
    """Stop deciding and drop every pending timer.

    Eerst de lopende ronde laten uitlopen: die kan service calls hebben
    uitstaan en schrijft daarna nog naar buiten (meldingen, timers). Wie
    hier meteen doorging, zag na de unload nog een melding herleven of een
    timer ontstaan die nooit meer wordt opgeruimd. Een ronde die langer dan
    vijf seconden blijft hangen, wordt niet langer tegengehouden - dan is
    het gedrag hetzelfde als vóór deze wacht, en dat is de veilige kant.

    First let the running round finish: it may have service calls out and
    writes outwards afterwards (notices, timers). Going on immediately let a
    notice revive or a timer come into being after the unload, never to be
    cleaned up again. A round hanging around for more than five seconds is
    no longer held up - behaviour is then the same as before this wait, and
    that is the safe side.
    """
    coordinator._closing = True
    try:
        # Vijf seconden is genoeg voor een lopende ronde; langer wachten
        # bevriest de configuratiepagina tijdens een herlaadbeurt.
        #
        # Five seconds is enough for a running round; waiting longer freezes
        # the configuration page during a reload.
        async with asyncio.timeout(5), coordinator._lock:
            pass
    except TimeoutError:
        _LOGGER.warning("Een beslisronde liep nog bij het afsluiten van %s", coordinator.name)
    coordinator._cancel_pending_deferral()
    coordinator._cancel_clock_reeval()
    coordinator._cancel_pending_precondition_wake()
    coordinator._cancel_pending_override_wake()
    coordinator._debouncer.async_shutdown()
    # Een uitgestelde opslag kan nog uitstaan: de store schrijft één seconde
    # na de laatste wijziging. Bij een herlaadbeurt is dat geen bezwaar, maar
    # bij een verwijdering zou die schrijfactie het bestand terugschrijven ná
    # `async_remove_entry`. Daarom hier zelf wegschrijven; `async_save` ruimt
    # de uitgestelde schrijfactie zelf al op.
    #
    # A delayed store write may still be pending: the store writes one second
    # after the last change. On a reload that is fine, but on a removal that
    # write would resurrect the file after `async_remove_entry`. So write it
    # away here; `async_save` clears the delayed write itself.
    await coordinator._store.async_save(coordinator._store_payload())
    await DataUpdateCoordinator.async_shutdown(coordinator)


async def async_start(coordinator: ClimateDirectorCoordinator) -> None:
    """Begin tracking entities; the first decision waits for Home Assistant.

    De eerste beslissing hoort niet thuis in het opzetten van de entry. Op
    dat moment is Home Assistant nog aan het opstarten: herstelde standen,
    automatiseringen en andere integraties komen pas daarna. Wie dan al
    beslist, ziet een half geladen wereld en kan een apparaat uitzetten dat
    er gewoon hoort te draaien.

    The first decision does not belong in the entry setup. At that point
    Home Assistant is still starting: restored states, automations and other
    integrations come only later. Whoever decides then sees a half-loaded
    world and can switch off an appliance that should simply be running.
    """
    entities = coordinator.tracked_entities()
    if entities:
        coordinator.entry.async_on_unload(
            async_track_state_change_event(
                coordinator.hass, sorted(entities), coordinator._handle_change
            )
        )
    coordinator.entry.async_on_unload(coordinator._cancel_pending_deferral)
    coordinator.entry.async_on_unload(coordinator._cancel_clock_reeval)
    coordinator.entry.async_on_unload(
        async_at_started(coordinator.hass, coordinator._async_on_hass_started)
    )


async def _async_on_hass_started(
    coordinator: ClimateDirectorCoordinator, _hass: HomeAssistant
) -> None:
    """Restore what a restart left behind, decide once, and arm the clock.

    Herstellen, neerslag noteren en beslissen zijn drie stappen op één pad.
    Slaat er één om, dan is de schade het grootst als daardoor ook de
    vangnetklok nooit loopt: dan wacht elke tijdregel op een toevallige
    wijziging die nooit komt. De klok wordt daarom hoe dan ook gezet, en de
    uitzondering wordt gelogd in plaats van de integratie stil te leggen.

    Restoring, noting precipitation and deciding are three steps on one
    path. When one falls over the damage is greatest if the safety-net clock
    never starts either: every time rule then waits for a chance change that
    never comes. The clock is therefore armed no matter what, and the
    exception is logged rather than silencing the integration.

    De vlag `_restored` gaat hier omhoog en niet eerder: pas als de opslag
    gelezen is, mag `_async_evaluate` iets doen. Wat de listeners intussen
    genoteerd hebben blijft staan - het herstel voegt samen en vervangt niet.

    The `_restored` flag goes up here and not earlier: only once the store
    has been read may `_async_evaluate` do anything. What the listeners noted
    in the meantime stays put - the restore merges rather than replaces. It
    goes up in the `finally` as well: after one broken reading the director
    must not fall silent for good, which is worse than a world without the
    stored hand.

    Hier gaat ook één keer naar buiten wat tijdens het opstarten bleef liggen:
    `_async_save_state` schreef niet, want HA's `Store.async_load` leest een
    wachtende schrijfactie in plaats van het bestand. Dat schrijven staat
    daarom ná het herstel, en ook in de `finally`.

    One write also goes out here for what stayed behind during the startup:
    `_async_save_state` did not write, since HA's `Store.async_load` reads a
    pending write instead of the file. That write therefore stands after the
    restore, and in the `finally` as well.
    """
    try:
        await coordinator._async_restore_state()
        coordinator._note_precipitation_now()
        coordinator._note_home_now()
        coordinator._restored = True
        coordinator._note_room_presence_now()
        coordinator._async_save_pending_state()
        await coordinator._async_evaluate()
    except Exception:
        _LOGGER.exception("The first decision of %s failed", coordinator.name)
    finally:
        # Ook als het herstel omviel gaat de poort open: anders zou de
        # director na één kapotte lezing nooit meer beslissen, en dat is
        # erger dan een wereld zonder de bewaarde hand.
        #
        # Even when the restore fell over the gate opens: otherwise the
        # director would never decide again after one broken reading, and
        # that is worse than a world without the stored hand.
        coordinator._restored = True
        # Wat de gebruiker vóór het herstel zelf deed is nu verwerkt: de
        # notities gaan weg, zodat een handeling daarna gewoon een handeling is.
        #
        # What the user did before the restore has been handled now:
        # the notes go, so an action afterwards is simply an action.
        coordinator._override_before_restore.clear()
        coordinator._request_before_restore.clear()
        coordinator._async_save_pending_state()
        coordinator._schedule_clock_reeval()
