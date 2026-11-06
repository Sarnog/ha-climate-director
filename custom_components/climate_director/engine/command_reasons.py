"""Waarom een apparaat niets krijgt. / Why an appliance gets nothing."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from . import gates
from .families import (
    MODE_FAN_ONLY,
    MODE_OFF,
    ModeFamily,
)
from .models import DirectorConfig
from .plan import (
    Deferral,
    Plan,
    Reason,
)
from .world import WorldState


def was_running(world: WorldState, previous: Plan | None, entity_id: str) -> bool:
    """Return whether the appliance really was running when the stop came.

    Anker 5: alleen een apparaat dat werkelijk draaide toen de stop kwam hoeft
    te rusten. De wereld zegt het direct; het vorige plan is het vangnet voor
    een harnas of apparaat dat zijn stand nog niet teruggemeld heeft - stond er
    vorige ronde een actief commando, dan telt het apparaat als draaiend.

    Anchor 5: only an appliance that really was running when the stop came has
    to rest. The world says so directly; the previous plan is the safety net
    for a harness or appliance that has not reported its mode back yet - with
    an active command last round, the appliance counts as running.
    """
    if world.climate(entity_id).running:
        return True
    if previous is None:
        return False
    command = previous.command_for(entity_id)
    return command is not None and command.hvac_mode not in (MODE_OFF, MODE_FAN_ONLY)


def received_heat(previous: Plan | None, zone_id: str) -> bool:
    """Return whether this zone really received heat last round.

    Beslissing 1 bij R14: een openingsstop telt alleen voor een zone die de
    vórige ronde werkelijk warmte kreeg. Zo blijft een stop waarbij de vraag
    écht wegviel `SATISFIED` heten, ook als er toevallig ergens een raam
    openstond.

    Decision 1 at R14: an opening stop only counts for a zone that really
    received heat last round. That keeps a stop whose demand really fell away
    named `SATISFIED`, even with a window standing open somewhere.
    """
    if previous is None:
        return False
    decision = previous.decision_for(zone_id)
    return decision is not None and decision.granted is ModeFamily.HEAT


def unreadable_reason(refusals: Mapping[str, Reason], served: Iterable[str]) -> Reason | None:
    """Return the unreadable-temperature reason for the served zones, if any.

    Anker 2: zonder leesbare binnen- of buitentemperatuur valt er niets te
    beslissen, en dan is uitzetten de enige fout die je kunt maken. Zijn er
    meerdere bediende zones, dan gaat de buitentemperatuur vóór de
    binnentemperatuur, zodat de uitkomst niet van de zonevolgorde afhangt.

    Anchor 2: without a readable indoor or outdoor temperature there is
    nothing to decide, and switching off is then the only mistake to make.
    With several served zones the outdoor temperature outranks the indoor one,
    so the outcome does not depend on zone order.
    """
    if any(refusals.get(zone_id) is Reason.NO_OUTDOOR_TEMPERATURE for zone_id in served):
        return Reason.NO_OUTDOOR_TEMPERATURE
    if any(refusals.get(zone_id) is Reason.NO_INDOOR_TEMPERATURE for zone_id in served):
        return Reason.NO_INDOOR_TEMPERATURE
    return None


def untouched_reason(
    world: WorldState,
    *,
    entity_id: str,
    blind: Reason | None,
) -> Reason | None:
    """Return why this appliance is left alone, or `None` when it gets a command.

    De gedeelde untouched-vragen van een zone-bron en een gedeelde warmtebron.
    Onbereikbaar en hoofdschakelaar uit zijn op beide paden letterlijk gelijk;
    de onleesbare-temperatuurtak is anker 2: een draaiend apparaat wordt met
    rust gelaten, wie uit staat krijgt gewoon zijn commando ("elke beheerde
    bron krijgt een commando"). De override zit hier bewust niet in: die
    triggert per pad anders.

    The shared untouched questions of a zone source and a shared heat source.
    Unreachable and master-off are verbatim the same on both paths; the
    unreadable-temperature branch is anchor 2: a running appliance is left
    alone, one that is off simply gets its command ("every managed source gets
    a command"). The override is deliberately absent: it triggers differently
    per path.
    """
    if not world.climate(entity_id).available:
        return Reason.SOURCE_UNREACHABLE
    if not world.master_enabled:
        return Reason.MASTER_DISABLED
    if blind is not None and world.climate(entity_id).running:
        return blind
    return None


def opening_stop_reason(
    world: WorldState,
    previous: Plan | None,
    entity_id: str,
    served: Iterable[str],
    refusals: Mapping[str, Reason],
    *,
    requires_received_heat: bool,
) -> Reason | None:
    """Return the opening reason when this stop counts as an opening stop.

    Anker 5: de rust geldt voor een apparaat dat werkelijk draaide toen de stop
    kwam (`was_running`). Een gedeelde warmtebron eist daarnaast dat een
    bediende zone die vórige ronde werkelijk warmte kreeg nu door een opening
    geweigerd wordt (`received_heat`); een zone-bron vaart op de wereld alleen.
    Het gedeelde lichaam is de keuze tussen `OPENING_OPEN` en
    `OPENING_OPEN_ELSEWHERE`, over alle bediende zones.

    Anchor 5: the rest covers an appliance that really was running when the
    stop came (`was_running`). A shared heat source additionally requires a
    served zone that really received heat last round to be refused by an
    opening (`received_heat`); a zone source goes on the world alone. The
    shared body is the choice between `OPENING_OPEN` and
    `OPENING_OPEN_ELSEWHERE`, taken over all served zones.
    """
    if not was_running(world, previous, entity_id):
        return None
    if not any(
        refusals.get(zone_id) in (Reason.OPENING_OPEN, Reason.OPENING_OPEN_ELSEWHERE)
        for zone_id in served
    ):
        return None
    if requires_received_heat and not any(
        refusals.get(zone_id) in (Reason.OPENING_OPEN, Reason.OPENING_OPEN_ELSEWHERE)
        and received_heat(previous, zone_id)
        for zone_id in served
    ):
        return None
    if any(refusals.get(zone_id) is Reason.OPENING_OPEN for zone_id in served):
        return Reason.OPENING_OPEN
    return Reason.OPENING_OPEN_ELSEWHERE


def opening_rest_hold(
    config: DirectorConfig,
    world: WorldState,
    previous: Plan | None,
    entity_id: str,
    *,
    ignores_openings: bool,
    deferrals: list[Deferral],
) -> bool:
    """Add the opening-rest deferral when the appliance may not start again yet.

    De gedeelde rekensom van de herstart-rem: lees de rusttijd, sla hem over
    voor een "toch doen"-verzoek, en ligt de eindtijd nog in de toekomst, voeg
    dan één `SHORT_CYCLE_PROTECTION`-deferral toe (ontdubbeld). Wat de aanroeper
    daarna doet — de zone weigeren, of de generator uitzetten — blijft per pad.

    The shared arithmetic of the restart brake: read the rest deadline, skip it
    for a "do it anyway" request, and when the deadline still lies ahead add
    one `SHORT_CYCLE_PROTECTION` deferral (deduplicated). What the caller does
    next — refuse the zone, or command the generator off — stays per path.
    """
    if ignores_openings:
        return False
    rest_until = gates.opening_rest_until(config, world, previous, entity_id)
    if rest_until is None or world.now >= rest_until:
        return False
    deferral = Deferral(entity_id, rest_until, Reason.SHORT_CYCLE_PROTECTION)
    if deferral not in deferrals:
        deferrals.append(deferral)
    return True


def idle_mode(config: DirectorConfig, world: WorldState, entity_id: str, reason: Reason) -> str:
    """Return how an appliance stands down: off, or circulating air.

    Fan-only is only ever offered to a zone that lost its circuit to another
    zone. A zone that is simply warm enough has nothing to circulate for, and
    leaving its fan running would read as a fault. And fan-only is only offered
    when the unit reports it can run that mode; a unit that knows just heat,
    cool and off would refuse the command, so it falls back on off.
    """
    if reason is not Reason.CIRCUIT_CONFLICT_LOST:
        return MODE_OFF
    circuit = config.circuit_for_entity(entity_id)
    if (
        circuit is not None
        and circuit.allow_fan_only_during_conflict
        and world.climate(entity_id).supports(MODE_FAN_ONLY)
    ):
        return MODE_FAN_ONLY
    return MODE_OFF
