"""De events naar buiten. / The events going out."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant

from . import texts
from .const import (
    EVENT_DECISION,
    EVENT_PRECONDITION_REFUSED,
)
from .engine import (
    DirectorConfig,
    Plan,
    Reason,
    WorldState,
    ZoneDecision,
)
from .engine.diff import Change
from .engine.gates import house_wide_blocked, opening_standing
from .engine.hysteresis import wanted_target
from .units import (
    display_temperature,
    from_celsius,
    unit_of_coordinator,
)

if TYPE_CHECKING:
    from .coordinator import ClimateDirectorCoordinator

_LOGGER = logging.getLogger(__name__)
_COMMAND_NOT_TAKING_ROUNDS = 10


def _fire_events(coordinator: ClimateDirectorCoordinator, plan: Plan) -> None:
    """Fire one event per zone whose outcome changed.

    Only on change: a decision is recomputed on every state change of every
    tracked entity, and firing each time would drown any automation
    listening for it.
    """
    previous = {zone.zone_id: zone for zone in (coordinator.data.zones if coordinator.data else ())}

    for decision in plan.zones:
        if previous.get(decision.zone_id) == decision:
            continue
        coordinator.hass.bus.async_fire(
            EVENT_DECISION,
            _event_data(
                coordinator.hass,
                coordinator.config,
                coordinator.world,
                plan,
                decision,
                unit_of_coordinator(coordinator),
            ),
        )


def _fire_refusals(coordinator: ClimateDirectorCoordinator, plan: Plan) -> None:
    """Say so when a pre-conditioning request strands on an open window.

    Zonder dit verdwijnt het verzoek in stilte: de zone meldt `opening_open`,
    maar dat ziet er van buiten hetzelfde uit als een raam dat gewoon
    openstaat terwijl niemand iets vroeg. Wie op een knop drukte hoort te
    horen waarom er niets gebeurt, en welk raam het is.

    Alleen bij een wisseling, niet bij elke beoordeling - anders verzuipt
    elke automatisering die meeluistert.

    Without this the request vanishes silently: the zone reports
    `opening_open`, but from the outside that looks the same as a window
    simply standing open while nobody asked for anything. Whoever pressed a
    button deserves to hear why nothing happens, and which window it is.

    Only on a change, not on every evaluation - otherwise any automation
    listening drowns.
    """
    refused: set[str] = set()
    for decision in plan.zones:
        if decision.reason not in (Reason.OPENING_OPEN, Reason.OPENING_OPEN_ELSEWHERE):
            continue
        if not coordinator._precondition.get(decision.zone_id):
            continue
        refused.add(decision.zone_id)

        if decision.zone_id in coordinator._refused:
            continue
        coordinator.hass.bus.async_fire(
            EVENT_PRECONDITION_REFUSED, coordinator._refusal_data(decision.zone_id, plan)
        )

    coordinator._refused = refused


def _refusal_data(
    coordinator: ClimateDirectorCoordinator, zone_id: str, plan: Plan | None
) -> dict[str, Any]:
    """Return the payload of one refusal, the sentences included.

    De zinnen worden hier al gemaakt, in de taal van de interface. Een
    blueprint kan niet vertalen en een gebruiker die zijn huis in het
    Nederlands bedient wil geen Engelse melding op zijn telefoon. Waar de
    melding heen gaat blijft aan de gebruiker; alleen de tekst komt hier
    vandaan.

    Er zitten twee zinnen in: de weigering, en wat er te melden valt zodra
    iemand op "toch doen" drukt. Die tweede staat er nu al in omdat hij
    precies dan nodig is, en dan is de gebeurtenis allang geweest.

    The sentences are made here, in the language of the interface. A
    blueprint cannot translate, and somebody running their house in Dutch
    does not want an English notice on their phone. Where the notice goes
    stays the user's business; only the text comes from here.

    Two sentences go in: the refusal, and what there is to report the
    moment somebody presses "do it anyway". The second is in here already
    because that is exactly when it is needed, and by then the event is
    long past.
    """
    zone = coordinator.config.zone(zone_id)
    name = zone.name if zone else zone_id
    decision = plan.decision_for(zone_id) if plan is not None else None
    held_elsewhere = decision is not None and (
        decision.reason is Reason.OPENING_OPEN_ELSEWHERE
        or Reason.OPENING_OPEN_ELSEWHERE in decision.closed_gates
    )
    house_wide = held_elsewhere or (
        zone is not None
        and any(
            source.entity_id in coordinator.config.house_wide_openings for source in zone.sources
        )
        and coordinator.world is not None
        and bool(house_wide_blocked(coordinator.config, coordinator.world))
    )
    openings = coordinator._open_openings(zone_id, house_wide=house_wide)
    listed = ", ".join(coordinator._friendly(entity_id) for entity_id in openings) or "-"
    minutes = round(coordinator.config.gates.max_precondition.total_seconds() / 60)

    indoor = coordinator.world.indoor(zone_id) if coordinator.world is not None else None
    target: float | None = None
    settled = False
    if zone is not None and coordinator.world is not None:
        demand, target = wanted_target(coordinator.config, zone, coordinator.world, plan)
        settled = demand.reason in (Reason.SATISFIED, Reason.WITHIN_DEADBAND)

    # De engine-wereld rekent in Celsius; de zin op de telefoon hoort de
    # eenheid van de gebruiker te noemen, afgerond — geen kale engine-float.
    #
    # The engine world counts in Celsius; the sentence on the phone should
    # name the user's unit, rounded — not the bare engine float.
    unit = unit_of_coordinator(coordinator)
    if indoor is None:
        code = "precondition_confirmed_unknown"
        fallback = (
            "{zone} is going ahead, ignoring {openings}. The room temperature cannot be "
            "read, so nothing will happen until it can."
        )
    elif target is not None:
        code = "precondition_confirmed"
        fallback = "{zone} is going ahead, ignoring {openings}. Now {indoor}, aiming for {target}."
    elif settled:
        code = "precondition_confirmed_satisfied"
        fallback = (
            "{zone} is going ahead, ignoring {openings}. Now {indoor} - the room is "
            "already right, so nothing happens for the moment."
        )
    else:
        # Geen streeftemperatuur en niet tevreden: het seizoen of de
        # configuratie laat hier niets toe. "De kamer ligt al goed" zou dan
        # een leugen zijn tegen iemand die op vijftien graden zit.
        #
        # No target and not satisfied: the season or the configuration
        # allows nothing here. "The room is already right" would then be a
        # lie to somebody sitting at fifteen degrees.
        code = "precondition_confirmed_idle"
        fallback = (
            "{zone} is going ahead, ignoring {openings}. Now {indoor} - there is "
            "nothing this room may do at the moment, so nothing happens."
        )

    filling = {
        "zone": name,
        "openings": listed,
        "indoor": display_temperature(from_celsius(indoor, unit), unit),
        "target": display_temperature(from_celsius(target, unit), unit),
        "minutes": minutes,
    }
    return {
        "entry_id": coordinator.entry.entry_id,
        "zone_id": zone_id,
        "zone": name,
        "openings": openings,
        "opening_names": [coordinator._friendly(entity_id) for entity_id in openings],
        "until": coordinator._precondition[zone_id].isoformat(),
        "indoor_temperature": indoor,
        "target_temperature": target,
        "override_minutes": minutes,
        "title": texts.translated(
            coordinator.hass, "precondition_refused_title", "Pre-conditioning refused", **filling
        ),
        "message": texts.translated(
            coordinator.hass,
            "precondition_refused",
            "{zone} could not start pre-conditioning. Still open: {openings}. Close what is "
            "open, or let the request run anyway for {minutes} minutes.",
            **filling,
        ),
        "confirmed_title": texts.translated(
            coordinator.hass,
            "precondition_confirmed_title",
            "Pre-conditioning is running",
            **filling,
        ),
        "confirmed_message": texts.translated(coordinator.hass, code, fallback, **filling),
        "confirm_label": texts.translated(
            coordinator.hass, "precondition_confirm_label", "Do it anyway", **filling
        ),
    }


def _friendly(coordinator: ClimateDirectorCoordinator, entity_id: str) -> str:
    """Return the name somebody would recognise, or the entity id."""
    state = coordinator.hass.states.get(entity_id)
    return state.name if state is not None else entity_id


def _open_openings(
    coordinator: ClimateDirectorCoordinator, zone_id: str, *, house_wide: bool = False
) -> list[str]:
    """Return the entity ids standing open, so the notice can name them.

    Met `house_wide` telt élke openstaande opening mee in plaats van alleen
    die van de zone. De deur die een huisbreed stilgezet apparaat stopt hoort
    per definitie bij een andere kamer, dus de gewone zonefilter zou een
    gerepareerd event alsnog `openings: "-"` laten melden.

    With `house_wide` every opening standing open counts rather than only the
    zone's own. The door stopping a house-wide stopped appliance belongs to
    another room by definition, so the ordinary zone filter would still have a
    repaired event report `openings: "-"`.
    """
    if coordinator.world is None:
        return []
    if house_wide:
        return sorted(
            opening.entity_id
            for opening in coordinator.config.openings
            if opening_standing(opening, coordinator.world)
        )
    return sorted(
        opening.entity_id
        for opening in coordinator.config.openings
        if (not opening.zone_ids or zone_id in opening.zone_ids)
        and opening_standing(opening, coordinator.world)
    )


def _event_data(
    hass: HomeAssistant,
    config: DirectorConfig,
    world: WorldState | None,
    plan: Plan,
    decision: ZoneDecision,
    unit: str,
) -> dict[str, Any]:
    """Return the payload of one `climate_director_decision` event.

    `temperature` wordt gepubliceerd in de eenheid van de gebruiker, afgerond op
    één decimaal, met `temperature_unit` ernaast, zodat een automatisering die
    op het getal templatet weet waarin ze rekent.

    De vier leesbare velden - `reason_text`, `action_text`, `source_name` en `message` - komen
    uit `texts.decision_fields`; de identifiers, `action` erbij, blijven staan en blijven het
    contract. Wie op `reason` of `action` filtert, merkt niets van die vier.

    `temperature` is published in the user's unit, rounded to one decimal, with
    `temperature_unit` alongside it, so an automation templating on the number
    knows what it is counting in.

    The four readable fields - `reason_text`, `action_text`, `source_name` and `message` - come
    from `texts.decision_fields`; the identifiers, `action` among them, stay and remain the
    contract. Whoever filters on `reason` or `action` notices nothing of those four.
    """
    zone = config.zone(decision.zone_id)
    reading = texts.decision_fields(
        hass, config=config, world=world, plan=plan, decision=decision, unit=unit
    )
    return {
        "zone_id": decision.zone_id,
        "zone_name": zone.name if zone else decision.zone_id,
        "wanted": decision.wanted.value,
        "granted": decision.granted.value,
        "source_id": decision.source_id,
        "entity_id": reading["entity_id"],
        "hvac_mode": reading["hvac_mode"],
        "temperature": reading["temperature"],
        "temperature_unit": unit,
        "reason": decision.reason.value,
        "reason_text": reading["reason_text"],
        "action": reading["action"],
        "action_text": reading["action_text"],
        "source_name": reading["source_name"],
        "message": reading["message"],
    }


def wanted(change: Change, unit: str) -> str:
    """Return what a change asks for, short enough to read in a notice.

    De stand is er altijd; het setpoint alleen als het meegestuurd wordt. Een
    apparaat dat uitgezet moet worden krijgt geen temperatuur mee, en die dan
    toch noemen zou een lezer op het verkeerde been zetten. Het setpoint wordt
    in de eenheid van de gebruiker getoond, afgerond - geen kale `°C` en geen
    onafgeronde engine-float.

    The mode is always there; the setpoint only when it is sent along. An
    appliance that has to be switched off gets no temperature with it, and
    naming one anyway would put a reader on the wrong foot. The setpoint is
    shown in the user's unit, rounded - no bare `°C` and no unrounded engine
    float.
    """
    if change.set_temperature and change.command.temperature is not None:
        return (
            f"{change.command.hvac_mode}, "
            f"{display_temperature(from_celsius(change.command.temperature, unit), unit)}"
        )
    return change.command.hvac_mode
