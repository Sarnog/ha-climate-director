"""Wat de coordinator meet en meldt. / What the coordinator measures and reports."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util

from . import repair_notices
from .const import (
    UNUSABLE_GRACE_SECONDS,
)
from .coordinator_events import wanted
from .engine import (
    WAITING_REASONS,
    ModeFamily,
    Plan,
    Reason,
    Season,
)
from .engine.families import MODE_OFF, preferred_mode
from .engine.gates import opening_bypassed_and_open
from .engine.models import SeasonSource
from .readability import unreadable
from .units import (
    display_temperature,
    from_celsius,
    to_celsius,
    unit_of_coordinator,
)
from .world_builder import (
    as_float,
    as_modes,
    season_from_state,
    temperature_from_state,
)

if TYPE_CHECKING:
    from .coordinator import ClimateDirectorCoordinator

_LOGGER = logging.getLogger(__name__)
_COMMAND_NOT_TAKING_ROUNDS = 10


def unusable_entities(coordinator: ClimateDirectorCoordinator) -> dict[str, str]:
    """Return the configured entities that cannot be read right now.

    Een verkeerd getikte entiteit bestaat gewoon niet, en een sensor die
    wegvalt leest als niets. In beide gevallen valt er niets om: de poort
    die erop leunt gaat dicht, de zone doet niets, en dat is van buiten niet
    te onderscheiden van een zone die niets hoeft te doen. Daarom staat het
    hier apart, in plaats van dat je het uit een stille zone moet afleiden.

    A mistyped entity simply does not exist, and a sensor that drops out
    reads as nothing. Neither breaks anything: the gate leaning on it closes,
    the zone does nothing, and from the outside that is indistinguishable
    from a zone with nothing to do. Hence this, rather than leaving you to
    infer it from a silent zone.
    """
    found: dict[str, str] = {}
    for entity_id in sorted(coordinator.tracked_entities()):
        state = coordinator.hass.states.get(entity_id)
        if state is None:
            found[entity_id] = "missing"
        elif unreadable(state.state):
            found[entity_id] = state.state

    # Een leesbare seizoensentiteit met een onherkenbare staat is net zo
    # stil kapot als een onleesbare: het seizoen wordt UNKNOWN en alles wat
    # eraan hangt - zomerkoeling bijvoorbeeld - valt weg zonder dat er iets
    # van te zien is. De entiteit bestaat en is leesbaar, dus de gewone
    # controle hierboven pakt hem niet.
    #
    # A readable season entity with an unrecognised state is just as
    # silently broken as an unreadable one: the season becomes UNKNOWN and
    # everything hanging off it - summer cooling, say - falls away with
    # nothing to show for it. The entity exists and reads fine, so the
    # ordinary check above does not catch it.
    if (
        coordinator.config.seasons.source is SeasonSource.ENTITY
        and coordinator.config.seasons.entity_id
    ):
        entity_id = coordinator.config.seasons.entity_id
        state = coordinator.hass.states.get(entity_id)
        if (
            state is not None
            and not unreadable(state.state)
            and season_from_state(state.state) is Season.UNKNOWN
        ):
            found[entity_id] = f"unrecognized season: {state.state}"

    # Een leesbare temperatuursensor die geen getal oplevert is net zo stil
    # kapot als een onleesbare: de zone leest NO_INDOOR_TEMPERATURE en doet
    # niets, zonder dat er iets van te zien is. De entiteit bestaat en is
    # leesbaar, dus de gewone controle hierboven pakt hem niet.
    #
    # A readable temperature sensor that yields no number is just as
    # silently broken as an unreadable one: the zone reads
    # NO_INDOOR_TEMPERATURE and does nothing, with nothing to show for it.
    # The entity exists and reads fine, so the ordinary check above does
    # not catch it.
    sensors: set[str] = set()
    if coordinator.config.outdoor_sensor:
        sensors.add(coordinator.config.outdoor_sensor)
    for zone in coordinator.config.zones:
        if zone.indoor_sensor:
            sensors.add(zone.indoor_sensor)
    for entity_id in sorted(sensors):
        if entity_id in found:
            continue
        state = coordinator.hass.states.get(entity_id)
        if state is None or unreadable(state.state):
            continue
        attributes = getattr(state, "attributes", {})
        if (
            temperature_from_state(
                entity_id, state.state, attributes, unit=unit_of_coordinator(coordinator)
            )
            is None
        ):
            found[entity_id] = "no number"

    return found


def _report_unreadable(coordinator: ClimateDirectorCoordinator) -> None:
    """Put the entities that stay unreadable under Repairs, or take them away."""
    repair_notices.async_report_unreadable(
        coordinator.hass,
        coordinator.entry.entry_id,
        coordinator.entry.title,
        coordinator._note_unusable(),
    )


def _note_unusable(coordinator: ClimateDirectorCoordinator) -> dict[str, str]:
    """Record since when each entity has been unreadable, and return the lasting ones.

    Geschreven op het beslispad en niet in de lezer: `unusable_entities()`
    geeft alleen een antwoord, en een lezer met een bijwerking is precies
    de fout die de neerslagnalooptijd ooit onzichtbaar maakte.

    De teller begint opnieuw zodra een entiteit terugkomt. Wie een minuut
    wegvalt bij een herstart is geen storing; wie een kwartier weg is wel.

    Written on the decision path rather than in the reader:
    `unusable_entities()` only gives an answer, and a reader with a side
    effect is exactly the mistake that once made the precipitation grace
    invisible.

    The clock restarts the moment an entity returns. Dropping out for a
    minute during a restart is no fault; being gone for a quarter of an hour
    is.
    """
    now = dt_util.now()
    found = coordinator.unusable_entities()
    coordinator._unusable_latest = found
    coordinator._unusable_since = {
        entity_id: coordinator._unusable_since.get(entity_id, now) for entity_id in found
    }
    grace = timedelta(seconds=UNUSABLE_GRACE_SECONDS)
    return {
        entity_id: state
        for entity_id, state in found.items()
        if now - coordinator._unusable_since[entity_id] >= grace
    }


def unsupported_modes(coordinator: ClimateDirectorCoordinator) -> dict[str, str]:
    """Return the sources whose role asks what the appliance cannot deliver.

    De rol zegt wat de installatie wil, het apparaat wat het kan. Een bron
    met rol HEAT_COOL op een apparaat dat alleen `heat` en `off` meldt,
    wordt door de engine voor koelen overgeslagen - en dat is van buiten
    niet te onderscheiden van een zone die niets hoeft. Hetzelfde geldt voor
    een setpoint buiten `min_temp`/`max_temp`: de engine klemt het dan naar
    de dichtstbijzijnde grens, maar de gevraagde temperatuur wordt nooit
    gehaald. Onleesbare apparaten blijven hier buiten: die hebben hun eigen
    melding.

    The role says what the installation wants, the appliance what it can. A
    source with role HEAT_COOL on an appliance reporting only `heat` and
    `off` is skipped for cooling by the engine - and from the outside that
    is indistinguishable from a zone with nothing to do. The same holds for
    a setpoint outside `min_temp`/`max_temp`: the engine clamps it to the
    nearest bound, but the asked temperature is never reached. Unreadable
    appliances are left out here: they have a notice of their own.
    """
    found: dict[str, set[str]] = {}
    for zone, source in coordinator.config.sources():
        state = coordinator.hass.states.get(source.entity_id)
        if state is None or unreadable(state.state):
            continue
        complaints: set[str] = set()
        # De rol hangt aan de bron, niet aan het apparaat. Hetzelfde apparaat
        # kan in kamer A HEAT_ONLY zijn en in kamer B HEAT_COOL; een wacht
        # op het apparaat sloeg de koelrol van kamer B dan over. De set
        # hieronder ontdubbelt toch al.
        #
        # The role hangs on the source, not on the appliance. The same
        # appliance can be HEAT_ONLY in room A and HEAT_COOL in room B; a
        # guard on the appliance then skipped room B's cool role. The set
        # below deduplicates anyway.
        modes = as_modes(state.attributes.get("hvac_modes"))
        if modes is not None:
            complaints.update(
                preferred_mode(family)
                for family in (ModeFamily.HEAT, ModeFamily.COOL)
                if source.supports(family) and preferred_mode(family) not in modes
            )
            # De director wil een apparaat ook kunnen uitzetten; meldt het
            # `off` niet, dan valt die aanroep elke ronde om. Het verschil
            # zelf wordt niet meer gestuurd (`engine.diff.changes`), maar
            # stilzwijgen zou de instelfout verbergen.
            #
            # The director also wants to be able to switch an appliance off;
            # if it does not report `off`, that call falls over every round.
            # The mode itself is no longer sent (`engine.diff.changes`), but
            # staying silent would hide the configuration mistake.
            if MODE_OFF not in modes:
                complaints.add(MODE_OFF)
        minimum = to_celsius(
            as_float(state.attributes.get("min_temp")), unit_of_coordinator(coordinator)
        )
        maximum = to_celsius(
            as_float(state.attributes.get("max_temp")), unit_of_coordinator(coordinator)
        )
        unit = unit_of_coordinator(coordinator)
        for family in (ModeFamily.HEAT, ModeFamily.COOL):
            if not source.supports(family):
                continue
            settings = zone.settings_for(family)
            if settings is None:
                continue
            target = from_celsius(settings.target, unit)
            if minimum is not None and settings.target < minimum:
                complaints.add(
                    f"{preferred_mode(family)} {display_temperature(target, unit)}"
                    f" < {display_temperature(from_celsius(minimum, unit), unit)}"
                )
            if maximum is not None and settings.target > maximum:
                complaints.add(
                    f"{preferred_mode(family)} {display_temperature(target, unit)}"
                    f" > {display_temperature(from_celsius(maximum, unit), unit)}"
                )
        if complaints:
            found.setdefault(source.entity_id, set()).update(complaints)
    return {entity_id: ", ".join(sorted(parts)) for entity_id, parts in found.items()}


def _note_unsupported(coordinator: ClimateDirectorCoordinator) -> dict[str, str]:
    """Record since when each source has asked an unsupported mode, with grace."""
    now = dt_util.now()
    found = coordinator.unsupported_modes()
    coordinator._unsupported_since = {
        entity_id: coordinator._unsupported_since.get(entity_id, now) for entity_id in found
    }
    grace = timedelta(seconds=UNUSABLE_GRACE_SECONDS)
    return {
        entity_id: modes
        for entity_id, modes in found.items()
        if now - coordinator._unsupported_since[entity_id] >= grace
    }


def _report_unsupported_modes(coordinator: ClimateDirectorCoordinator) -> None:
    """Put the roles asking impossible modes under Repairs, or take them away."""
    repair_notices.async_report_unsupported_modes(
        coordinator.hass,
        coordinator.entry.entry_id,
        coordinator.entry.title,
        coordinator._note_unsupported(),
    )


def _note_unapplied(coordinator: ClimateDirectorCoordinator) -> dict[str, str]:
    """Count how often each difference was offered without taking effect.

    Een apparaat dat de aanroep aanneemt maar niet uitvoert, of zichzelf
    terugzet, levert elke ronde hetzelfde verschil op. Na een aantal rondes
    is dat geen toeval meer en hoort er een melding te komen. In
    schaduwmodus wordt er niets uitgevoerd, dus daar telt dit nooit - de
    verschillenlijst is dan per definitie permanent gevuld.

    An appliance that accepts the call but does not carry it out, or resets
    itself, yields the same difference every round. After a number of rounds
    that is no longer chance and a notice should appear. In shadow mode
    nothing is executed, so this never counts there - the difference list is
    by definition permanently filled then.
    """
    if coordinator.shadow:
        coordinator._unapplied = {}
        return {}

    now = dt_util.now()
    offered = {change.entity_id for change in coordinator.last_changes}
    for entity_id in list(coordinator._unapplied):
        if entity_id not in offered:
            del coordinator._unapplied[entity_id]

    grace = timedelta(seconds=UNUSABLE_GRACE_SECONDS)
    found: dict[str, str] = {}
    for change in coordinator.last_changes:
        fingerprint = (
            change.command.hvac_mode,
            change.command.temperature,
            change.set_mode,
            change.set_temperature,
        )
        previous, count, since = coordinator._unapplied.get(change.entity_id, (None, 0, now))
        if previous == fingerprint:
            count += 1
        else:
            count, since = 1, now
        coordinator._unapplied[change.entity_id] = (fingerprint, count, since)
        if count >= _COMMAND_NOT_TAKING_ROUNDS and now - since >= grace:
            found[change.entity_id] = wanted(change, unit_of_coordinator(coordinator))
    return found


def _report_command_not_taking(coordinator: ClimateDirectorCoordinator) -> None:
    """Put appliances that never take their command under Repairs, or take them away."""
    repair_notices.async_report_command_not_taking(
        coordinator.hass,
        coordinator.entry.entry_id,
        coordinator.entry.title,
        coordinator._note_unapplied(),
    )


def _report_bypassed_openings(coordinator: ClimateDirectorCoordinator) -> None:
    """Put openings bypassed while really open under Repairs, or take them away."""
    found: dict[str, str] = {}
    if coordinator.world is not None:
        for opening in coordinator.config.openings:
            if opening_bypassed_and_open(opening, coordinator.world):
                found[opening.entity_id] = opening.name or opening.entity_id
    repair_notices.async_report_bypassed_openings(
        coordinator.hass,
        coordinator.entry.entry_id,
        coordinator.entry.title,
        found,
    )


def _season_override_problems(coordinator: ClimateDirectorCoordinator) -> dict[str, str]:
    """Return the duties the season select locks out, keyed by zone and duty.

    De engine meldt de vaste seizoensbron in `validate()`; de select is
    bedieningstoestand en leeft hier. Zet iemand de select op een seizoen
    waarin een ingestelde taak nooit mag draaien, dan kan die taak nooit
    draaien - hetzelfde stille niets, dus dezelfde melding als bij de vaste
    instelling.

    The engine reports the fixed season source in `validate()`; the select
    is control state and lives here. Put the select on a season an
    installed duty is never allowed in, and that duty can never run - the
    same silent nothing, so the same notice as for the fixed setting.
    """
    override = getattr(coordinator, "season_override", None)
    if override is None:
        return {}
    found: dict[str, str] = {}
    for zone in coordinator.config.zones:
        for family in (ModeFamily.HEAT, ModeFamily.COOL):
            settings = zone.settings_for(family)
            if settings is not None and not settings.allowed_in(override):
                found[f"{zone.zone_id}:{family.value}"] = (
                    f"{zone.name or zone.zone_id} ({family.value})"
                )
    return found


def _report_season_override(coordinator: ClimateDirectorCoordinator) -> None:
    """Put a season select that locks a duty out under Repairs, or take it away."""
    repair_notices.async_report_season_override(
        coordinator.hass,
        coordinator.entry.entry_id,
        coordinator.entry.title,
        coordinator._season_override_problems(),
    )


def _note_waiting(coordinator: ClimateDirectorCoordinator, plan: Plan) -> None:
    """Remember since when each zone has been on its current waiting reason.

    De tijdstempel verspringt zodra de reden verandert, want dan is er wel
    iets gebeurd. Blijft dezelfde reden staan, dan loopt de teller door.

    The timestamp moves the moment the reason changes, since something did
    happen then. While the reason stays the same, the clock keeps running.
    """
    now = dt_util.now()
    fresh: dict[str, tuple[Reason, datetime]] = {}
    for decision in plan.zones:
        if decision.reason not in WAITING_REASONS:
            continue
        since = coordinator._waiting.get(decision.zone_id)
        fresh[decision.zone_id] = (
            since if since and since[0] is decision.reason else (decision.reason, now)
        )
    coordinator._waiting = fresh


def waiting_seconds(coordinator: ClimateDirectorCoordinator) -> dict[str, float]:
    """Return how long each waiting zone has been on its reason."""
    now = dt_util.now()
    return {
        zone_id: (now - since).total_seconds()
        for zone_id, (_reason, since) in coordinator._waiting.items()
    }


def unusable_latest(coordinator: ClimateDirectorCoordinator) -> dict[str, str]:
    """Return the unreadable entities of the latest decision round.

    De entiteitenlaag hoort niet aan `_unusable_latest` te zitten: dat is
    een privéveld van de coordinator en de grens van wat hij naar buiten
    brengt verandert mee met hem. Dit is de publieke lezer.

    The entity layer should not touch `_unusable_latest`: that is a private
    coordinator field, and the boundary of what it exposes moves with it.
    This is the public reader.
    """
    return coordinator._unusable_latest


def stuck_zones(coordinator: ClimateDirectorCoordinator) -> dict[str, Reason]:
    """Return the zones that have waited longer than the installation allows.

    Een pauze bij het wisselen van taak hoort seconden te duren. Staat een
    zone er een kwartier op, dan wacht hij niet meer maar zit hij vast - en
    dat is van buiten niet te onderscheiden van niets doen.

    A pause when switching duty should last seconds. A zone sitting on one
    for a quarter of an hour is no longer waiting but stuck - and from the
    outside that is indistinguishable from doing nothing at all.
    """
    limit = coordinator.config.stuck_after.total_seconds()
    if limit <= 0:
        return {}
    now = dt_util.now()
    return {
        zone_id: reason
        for zone_id, (reason, since) in coordinator._waiting.items()
        if (now - since).total_seconds() >= limit
    }


def _note_precipitation_now(coordinator: ClimateDirectorCoordinator) -> None:
    """Remember rain that was already falling before this process started.

    De listener ziet alleen overgangen. Wie herstart terwijl het regent,
    heeft geen overgang gezien, en zonder deze stap zou de nalooptijd voor
    die bui verloren zijn - terwijl de lezer zelf nooit mag schrijven. Dit
    is naast de listener de enige plek die het moment vastlegt.

    The listener only sees transitions. Restarting while it rains means no
    transition was seen, and without this step the grace for that shower
    would be lost - while the reader itself must never write. Besides the
    listener this is the only place that records the moment.
    """
    settings = coordinator.config.precipitation
    if not settings.enabled:
        return
    state = coordinator.hass.states.get(settings.source)
    if state is not None and state.state in settings.states:
        coordinator._precipitation_seen_at = dt_util.now()
