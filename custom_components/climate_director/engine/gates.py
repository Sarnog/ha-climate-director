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

    # Een configuratie zonder bewoners beschrijft een pand waar niemand gevolgd
    # wordt - een kantoor, een vakantiehuis, een serverruimte. De poorten die
    # over bewoners gaan slaan we daar over, want die kunnen nooit slagen. De
    # kamerpoort hieronder blijft wél gelden: die gaat over de ruimte, niet over
    # wie er in het huis is.
    #
    # A configuration without residents describes a building nobody is tracked
    # in - an office, a holiday home, a server room. The gates about residents
    # are skipped there, since they could never pass. The room gate below still
    # applies: that one is about the room, not about who is in the house.
    gates = config.gates

    # Gastenmodus neemt de poorten over die over afwezigheid gaan. Er logeert
    # iemand die niet gevolgd wordt, dus een leeg lijkend huis zegt niets en
    # hoort niet uit te gaan. Slaap blijft wél tellen: zodra een bewoner thuis
    # is en naar bed gaat, is de dag voorbij en is het huis weer van hen.
    #
    # Guest mode takes over the gates that are about absence. Somebody untracked
    # is staying, so a house that looks empty says nothing and should not shut
    # down. Sleep still counts: once a resident is home and turns in, the day is
    # over and the house is theirs again.
    if config.residents:
        if _guests_carry_the_house(config, world):
            # Afwezigheid en rooster zeggen niets meer, slaap wel: zodra iemand
            # thuis is en naar bed gaat, is het huis weer van de bewoners.
            #
            # Absence and schedule no longer say anything, sleep still does: the
            # moment somebody is home and turns in, the house is the residents'
            # again.
            at_home = [
                resident
                for resident in config.residents
                if world.resident(resident.resident_id).home
            ]
            if (
                at_home
                and gates.require_awake
                and not any(
                    world.resident(resident.resident_id).present_and_awake for resident in at_home
                )
            ):
                return GateVerdict.block(Reason.EVERYONE_ASLEEP)
        else:
            if not any(world.resident(resident.resident_id).home for resident in config.residents):
                return GateVerdict.block(Reason.NOBODY_HOME)

            if gates.require_awake and not any(
                world.resident(resident.resident_id).present_and_awake
                for resident in config.residents
            ):
                return GateVerdict.block(Reason.EVERYONE_ASLEEP)

            if gates.require_schedule and not _schedule_open(config, world):
                return GateVerdict.block(Reason.OUTSIDE_SCHEDULE)

    # Het smalst van allemaal, en daarom als laatste: iemand thuis zegt niets
    # over of er iemand op zolder zit.
    #
    # The narrowest of the lot, and therefore last: somebody being home says
    # nothing about whether anybody is in the attic.
    if not _room_occupied(world, zone):
        return GateVerdict.block(Reason.ZONE_UNOCCUPIED)

    return GateVerdict.allow()


def _guests_carry_the_house(config: DirectorConfig, world: WorldState) -> bool:
    """Return whether guest mode is standing in for the residents right now.

    Alleen overdag, of preciezer: binnen het ingestelde gastenvenster. Buiten
    dat venster nemen de gewone poorten het weer over, zodat een schakelaar die
    iemand vergeet uit te zetten het huis niet de hele nacht laat doordraaien.

    Only during the day, or more precisely: inside the configured guest window.
    Outside it the ordinary gates take over again, so a switch somebody forgets
    to turn off does not keep the house running all night.
    """
    if not world.guest_mode:
        return False
    window = config.gates.guest_window
    if window is None:
        return True
    return window.contains(world.now.time(), world.now.weekday())


def _room_occupied(world: WorldState, zone: Zone) -> bool:
    """Return whether this room counts as occupied right now.

    A zone without a presence entity is never held back on this: not measuring
    a room is not the same as knowing it is empty.
    """
    if not zone.presence_entity:
        return True

    state = world.presence_of(zone.zone_id)
    if state.occupied:
        return True
    if not zone.presence_timeout:
        return False

    # Zonder tijdstempel valt niet aan te tonen dat de kamer nog binnen de
    # nalooptijd valt, en dan telt hij als leeg. Een lege kamer met rust laten
    # is de onschadelijke kant om fout te zitten.
    #
    # Without a timestamp there is no showing the room is still inside the
    # grace period, so it counts as empty. Leaving an empty room alone is the
    # harmless side to be wrong on.
    if state.changed_at is None:
        return False
    return world.now - state.changed_at < zone.presence_timeout


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
    """Return whether the household's schedules allow regulating right now.

    Only residents who actually have a schedule take part. Someone without one
    neither opens the gate nor holds it shut: they have said nothing about when
    they want the house to join in, and silence is not a vote either way.

    A participant does two things. Awake, with their window open, they open the
    gate. At home and asleep, with their window not yet open, they hold it shut
    - which is what makes the house wait for the last sleeper on a weekend
    morning instead of starting the moment the first person is up. Once their
    own window opens, their sleeping stops counting: the schedule said they
    meant to be up by then.
    """
    moment = world.now.time()
    weekday = world.now.weekday()
    holiday = world.holiday_mode

    participants = [
        resident for resident in config.residents if resident.takes_part(holiday=holiday)
    ]
    if not participants:
        return False

    for resident in participants:
        state = world.resident(resident.resident_id)
        if (
            state.home
            and state.asleep
            and not resident.wants_climate_at(moment, weekday, holiday=holiday)
        ):
            return False

    return any(
        resident.wants_climate_at(moment, weekday, holiday=holiday)
        for resident in participants
        if _counts_towards_schedule(config, world, resident.resident_id)
    )


def _counts_towards_schedule(config: DirectorConfig, world: WorldState, resident_id: str) -> bool:
    """Return whether a resident's own schedule may open the schedule gate.

    Being home is required outright: a schedule says when somebody wants the
    house warm, not that it should be warm without them. Sleep mirrors the
    sleep gate instead of being hard-coded, so with `require_awake` off a
    schedule still counts while its owner sleeps.
    """
    state = world.resident(resident_id)
    if not state.home:
        return False
    return not (config.gates.require_awake and state.asleep)
