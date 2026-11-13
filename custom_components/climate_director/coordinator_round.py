"""Eén beslisronde en haar klok. / One decision round and its clock."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime

from homeassistant.core import callback
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from .applier import apply
from .const import (
    CLOCK_REEVAL_SECONDS,
    MIN_DEFERRAL_SECONDS,
)
from .coordinator_surface import CoordinatorSurface
from .engine import (
    ModeFamily,
    Plan,
    WorldState,
    decide,
)
from .engine.circuit_policy import active_family
from .engine.diff import changes
from .preconditions import still_running

_LOGGER = logging.getLogger(__name__)
_COMMAND_NOT_TAKING_ROUNDS = 10


def remember_families(coordinator: CoordinatorSurface, world: WorldState) -> None:
    """Record when each circuit last took on the duty it is running.

    Read from the observed states rather than from the previous plan: a
    unit switched by remote changes a circuit's duty just as effectively as
    the director does, and the minimum-run timer has to respect that.
    """
    for circuit in coordinator.config.circuits:
        current = active_family(world, circuit)
        if coordinator.round.family_seen.get(circuit.circuit_id) != current:
            coordinator.round.family_seen[circuit.circuit_id] = current
            coordinator.round.family_since[circuit.circuit_id] = (
                world.now if current in (ModeFamily.HEAT, ModeFamily.COOL) else None
            )


def with_family_history(coordinator: CoordinatorSurface, world: WorldState) -> WorldState:
    """Return the snapshot with the recorded duty-change times filled in.

    Eén veld vervangen, de rest overnemen zoals hij is. Dat gebeurde ooit
    door de momentopname met de hand opnieuw op te bouwen, en toen viel er
    stilletjes een veld uit: `precondition_bypass` bleef leeg, waardoor
    "toch doen" bij een openstaand raam nooit werkte in een draaiende Home
    Assistant - terwijl elke engine-test hem wél doorgaf. Een veld dat er
    later bij komt kan zo niet meer vergeten worden.

    Replace one field and carry the rest across as it stands. This once
    rebuilt the snapshot by hand, and a field quietly fell out of it:
    `precondition_bypass` stayed empty, so "do it anyway" on an open window
    never worked inside a running Home Assistant - while every engine test
    did pass it along. A field added later can no longer be forgotten this
    way.
    """
    return replace(world, circuit_family_since=dict(coordinator.round.family_since))


def schedule_deferral(coordinator: CoordinatorSurface, plan: Plan) -> None:
    """Re-evaluate when a timer in the plan expires.

    Without this, a plan held back by short-cycle protection would wait for
    an unrelated state change to resume - which on a quiet night may never
    come.
    """
    coordinator.cancel_pending_deferral()

    deferral = plan.next_deferral
    if deferral is None:
        return

    delay = max((deferral.until - dt_util.now()).total_seconds(), MIN_DEFERRAL_SECONDS)

    @callback
    def _resume(_now: datetime) -> None:
        coordinator.round.cancel_deferral = None
        coordinator.async_request_evaluation()

    coordinator.round.cancel_deferral = async_call_later(coordinator.hass, delay, _resume)


def cancel_pending_deferral(coordinator: CoordinatorSurface) -> None:
    """Drop the scheduled re-evaluation, if there is one."""
    if coordinator.round.cancel_deferral is not None:
        coordinator.round.cancel_deferral()
        coordinator.round.cancel_deferral = None


def cancel_clock_reeval(coordinator: CoordinatorSurface) -> None:
    """Drop the scheduled safety-net tick, if there is one."""
    if coordinator.round.clock_reeval_unsub is not None:
        coordinator.round.clock_reeval_unsub()
        coordinator.round.clock_reeval_unsub = None


def schedule_clock_reeval(coordinator: CoordinatorSurface) -> None:
    """Arm the periodic safety-net evaluation, replacing any earlier one.

    Het vangnet voor tijdregels die vanzelf verlopen: een raamvertraging,
    een aanwezigheids-nalooptijd, de neerslag-grace, de eerstvolgende
    vensterrand en middernacht. Zonder deze klok hangt zo'n omslagpunt op
    toeval - er moet toevallig iets anders veranderen voordat er opnieuw
    besloten wordt. Een ronde zonder verschil kost geen service call, dus
    elke minuut is goedkoop.

    The safety net for time rules that lapse by themselves: a window delay,
    a presence grace period, the precipitation grace, the next window edge
    and midnight. Without this clock such a turning point depends on chance
    - something else must happen to change before another decision is made.
    A round without a difference costs no service call, so every minute is
    cheap.
    """
    coordinator.cancel_clock_reeval()
    coordinator.round.clock_reeval_unsub = async_call_later(
        coordinator.hass, CLOCK_REEVAL_SECONDS, coordinator.on_clock_reeval
    )


def on_clock_reeval(coordinator: CoordinatorSurface, _now: datetime) -> None:
    """Re-evaluate on the clock, and arm the next tick."""
    coordinator.round.clock_reeval_unsub = None
    coordinator.async_request_evaluation()
    coordinator.schedule_clock_reeval()


def live_preconditions(coordinator: CoordinatorSurface) -> dict[str, datetime]:
    """Return the requests that have not run out, dropping the rest.

    Pruned on reading rather than on a timer: an expired request is over
    whether or not anything got round to noticing.
    """
    coordinator.precondition_until = still_running(coordinator.precondition_until, dt_util.now())
    coordinator.precondition_bypass &= set(coordinator.precondition_until)
    return dict(coordinator.precondition_until)


async def async_evaluate(coordinator: CoordinatorSurface) -> None:
    """Read the world, decide, apply, and report."""
    # `restored` is de opstartpoort en `closing` de afbraakpoort; zie `__init__`.
    if coordinator.lifecycle.closing or not coordinator.lifecycle.restored:
        return
    async with coordinator.round.lock:
        coordinator.drop_lapsed_override_timers()
        world = coordinator.note_house_asleep(coordinator.build_world())
        coordinator.remember_families(world)
        world = coordinator.with_heat_pick(coordinator.with_family_history(world))
        world = coordinator.settle_hand_starts(world)

        plan = decide(coordinator.config, world, coordinator.data)
        coordinator.world = world
        coordinator.round.issued = plan

        # De verschillenlijst wordt hier bewaard, niet wat de applier
        # ervan uitgevoerd kreeg. In schaduwmodus is dit precies "wat de
        # director gedaan zou hebben terwijl iets anders het huis stuurt" -
        # het getal waar de hele meeloopfase om draait.
        #
        # The difference list is kept here, not what the applier managed to
        # execute. In shadow mode this is exactly "what the director would
        # have done while something else steers the house" - the number the
        # whole shadow phase is about.
        #
        # De afloopkeuze (anker 11) komt vóór de gewone verschillen: het
        # plan is nog met de override berekend, dus het geeft die zone geen
        # commando, en de afloopkeuze is zo precies het enige commando op
        # dat moment. Daarna beslist de director gewoon weer.
        #
        # The expiry choice (anchor 11) comes before the ordinary
        # differences: the plan was still computed with the override, so it
        # commands that zone nothing, and the expiry choice is thus exactly
        # the one command at that moment. After that the director simply
        # decides again.
        expiry_changes = coordinator.consume_expired_overrides(world.now)
        pending_changes = coordinator.consume_pending_override_changes(world)
        sent = coordinator.round.sent_setpoints
        coordinator.last_changes = changes(plan, world, sent) + expiry_changes + pending_changes
        coordinator.last_applied = ()

        try:
            coordinator.last_applied = await apply(
                coordinator.hass, coordinator.last_changes, shadow=coordinator.shadow
            )
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Applying the climate plan failed")
        coordinator.note_commanded_off(coordinator.last_applied)
        coordinator.note_commanded_on(coordinator.last_applied)
        for change in coordinator.last_applied:
            if change.set_temperature and change.command.temperature is not None:
                sent[change.entity_id] = (change.command.hvac_mode, change.command.temperature)

        if coordinator.lifecycle.closing:
            return
        # Het publiceren van het plan hoort altijd te gebeuren, ook als een
        # van de meldingen eromheen een uitzondering gooit. Gebeurde dat
        # niet, dan bleef elke entiteit ronde na ronde op het vorige plan
        # staan terwijl de lus gewoon doordraaide - de stilste manier om
        # een huis te bevriezen.
        #
        # Publishing the plan must always happen, even when one of the
        # notices around it raises. Otherwise every entity stayed on the
        # previous plan round after round while the loop kept running - the
        # quietest way to freeze a house.
        try:
            coordinator.fire_events(plan)
            coordinator.fire_refusals(plan)
            coordinator.note_waiting(plan)
            coordinator.report_unreadable()
            coordinator.report_unsupported_modes()
            coordinator.report_command_not_taking()
            coordinator.report_season_override()
            coordinator.report_bypassed_openings()
            coordinator.schedule_deferral(plan)
        finally:
            coordinator.async_set_updated_data(plan)
