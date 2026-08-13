"""Poorten: mag er in deze zone überhaupt geregeld worden.

Gates: may this zone be regulated at all.

Poorten kijken alleen naar omstandigheden, nooit naar temperaturen. Ze
beantwoorden "mag het", niet "moet het" - dat tweede is aan `hysteresis.py`.

Gates look only at circumstances, never at temperatures. They answer "is this
allowed", not "is this needed" - the latter belongs to `hysteresis.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import DirectorConfig, Zone
from .plan import Reason
from .world import WorldState


@dataclass(frozen=True, slots=True)
class GateVerdict:
    """Whether a zone may be regulated, and why not when it may not."""

    allowed: bool
    reason: Reason | None = None

    @staticmethod
    def allow() -> GateVerdict:
        """Return a passing verdict."""
        return GateVerdict(True)

    @staticmethod
    def block(reason: Reason) -> GateVerdict:
        """Return a blocking verdict carrying its cause."""
        return GateVerdict(False, reason)


def evaluate(config: DirectorConfig, world: WorldState, zone: Zone) -> GateVerdict:
    """Return whether `zone` may be regulated right now.

    Checked from broadest to narrowest, so the reported cause is the one a user
    would name first: a disabled master switch outranks an open window, which
    outranks nobody being home.
    """
    if not world.master_enabled:
        return GateVerdict.block(Reason.MASTER_DISABLED)

    if world.overridden(zone.zone_id):
        return GateVerdict.block(Reason.MANUAL_OVERRIDE)

    if _any_opening_open(config, world, zone):
        return GateVerdict.block(Reason.OPENING_OPEN)

    # A configuration without residents describes a building nobody is tracked
    # in - an office, a holiday home, a server room. Blocking it forever on a
    # presence gate that can never pass would be useless, so presence-based
    # gates simply do not apply there.
    if not config.residents:
        return GateVerdict.allow()

    gates = config.gates

    if gates.require_occupancy and not any(
        world.resident(resident.resident_id).home for resident in config.residents
    ):
        return GateVerdict.block(Reason.NOBODY_HOME)

    if gates.require_awake and not any(
        world.resident(resident.resident_id).present_and_awake for resident in config.residents
    ):
        return GateVerdict.block(Reason.EVERYONE_ASLEEP)

    if gates.require_schedule and not _schedule_open(config, world):
        return GateVerdict.block(Reason.OUTSIDE_SCHEDULE)

    return GateVerdict.allow()


def _any_opening_open(config: DirectorConfig, world: WorldState, zone: Zone) -> bool:
    """Return whether an opening has suspended this zone long enough."""
    for opening in config.openings:
        if not opening.affects(zone.zone_id):
            continue
        state = world.opening(opening.entity_id)
        if not state.open:
            continue
        # An open sensor without a timestamp counts as open long enough:
        # suspending climate control is the harmless direction to be wrong in,
        # and refusing to act on an unknown age would keep heating an open room.
        if state.changed_at is None:
            return True
        if world.now - state.changed_at >= opening.delay:
            return True
    return False


def _schedule_open(config: DirectorConfig, world: WorldState) -> bool:
    """Return whether anyone the earlier gates kept in play wants heating now."""
    if world.holiday_mode and config.gates.holiday_bypasses_schedule:
        return True

    moment = world.now.time()
    weekday = world.now.weekday()
    return any(
        resident.wants_climate_at(moment, weekday)
        for resident in config.residents
        if _counts_towards_schedule(config, world, resident.resident_id)
    )


def _counts_towards_schedule(config: DirectorConfig, world: WorldState, resident_id: str) -> bool:
    """Return whether a resident's own schedule may open the schedule gate.

    Deliberately mirrors the presence and sleep gates rather than hard-coding
    "home and awake": with `require_occupancy` off, someone's schedule should
    still count while they are out, and with `require_awake` off it should
    still count while they sleep.
    """
    state = world.resident(resident_id)
    if config.gates.require_occupancy and not state.home:
        return False
    return not (config.gates.require_awake and state.asleep)
