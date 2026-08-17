"""De beslisfunctie: van momentopname naar plan.

The decision function: from snapshot to plan.

`decide()` is de enige ingang van de engine en het enige punt waar besloten
wordt. Daardoor is een toestand als "gas en airco draaien tegelijk" niet iets
dat achteraf gedetecteerd moet worden - hij komt er simpelweg nooit uit.

`decide()` is the engine's only entry point and the only place a decision is
made. A state such as "boiler and heat pump both running" therefore needs no
detection after the fact - it simply never comes out.
"""

from __future__ import annotations

from . import constraints, gates, hysteresis, sources
from .families import MODE_FAN_ONLY, MODE_HEAT, MODE_OFF, ModeFamily, family_of, preferred_mode
from .models import Circuit, DirectorConfig, Source, Zone
from .plan import CircuitDecision, Deferral, Plan, Reason, UnitCommand, ZoneDecision
from .world import WorldState

#: Solo circuit standing in for a source with an outdoor unit to itself.
_SOLO = Circuit(circuit_id="", name="", units=(), simultaneous_heat_cool=True)


def decide(config: DirectorConfig, world: WorldState) -> Plan:
    """Return the complete, consistent end state the installation should be in."""
    wishes, refusals = _collect_wishes(config, world)
    wishes, dropped = _apply_exclusive_groups(config, wishes)

    grants, circuit_decisions, deferrals = _resolve_circuits(config, world, wishes)
    reasons = _zone_reasons(config, grants, dropped, refusals)

    return Plan(
        commands=_build_commands(config, world, grants, reasons, wishes),
        zones=_build_zone_decisions(config, wishes, dropped, grants, refusals),
        circuits=circuit_decisions,
        deferrals=deferrals,
    )


def _collect_wishes(
    config: DirectorConfig, world: WorldState
) -> tuple[dict[str, constraints.Request], dict[str, Reason]]:
    """Return each zone's request, plus the refusal reason for zones with none."""
    wishes: dict[str, constraints.Request] = {}
    refusals: dict[str, Reason] = {}

    for zone in config.zones:
        verdict = gates.evaluate(config, world, zone)
        if not verdict.allowed:
            refusals[zone.zone_id] = verdict.reason or Reason.MASTER_DISABLED
            continue

        demand = hysteresis.evaluate(zone, world, _running_family(zone, world))
        if demand.family is ModeFamily.NEUTRAL:
            refusals[zone.zone_id] = demand.reason
            continue

        source = sources.select(zone, demand.family, world)
        if source is None:
            refusals[zone.zone_id] = Reason.NO_SOURCE_AVAILABLE
            continue

        wishes[zone.zone_id] = constraints.Request(
            zone=zone,
            source=source,
            family=demand.family,
            deviation=demand.deviation,
            priority=world.priority_for(zone.zone_id, zone.priority),
        )

    return wishes, refusals


def _apply_exclusive_groups(
    config: DirectorConfig, wishes: dict[str, constraints.Request]
) -> tuple[dict[str, constraints.Request], dict[str, constraints.Request]]:
    """Split the requests into those that keep a shared appliance and those that lose it.

    Zones keep their own mutual exclusion for free - a zone only ever picks one
    source - so this covers only appliances shared across zones. Losers are
    returned rather than discarded, so the plan can still report what they
    wanted and why they did not get it.
    """
    if not config.exclusive_groups:
        return wishes, {}

    kept = dict(wishes)
    dropped: dict[str, constraints.Request] = {}
    for group in config.exclusive_groups:
        contenders = sorted(
            (request for request in kept.values() if request.source.source_id in group),
            key=lambda request: request.rank,
        )
        for loser in contenders[1:]:
            dropped[loser.zone.zone_id] = kept.pop(loser.zone.zone_id)
    return kept, dropped


def _resolve_circuits(
    config: DirectorConfig, world: WorldState, wishes: dict[str, constraints.Request]
) -> tuple[dict[str, constraints.Grant], tuple[CircuitDecision, ...], tuple[Deferral, ...]]:
    """Run every circuit's constraints and collect the grants they produce."""
    by_circuit: dict[str, list[constraints.Request]] = {}
    solo: list[constraints.Request] = []

    for request in wishes.values():
        circuit = config.circuit_for_entity(request.source.entity_id)
        if circuit is None:
            solo.append(request)
        else:
            by_circuit.setdefault(circuit.circuit_id, []).append(request)

    grants: dict[str, constraints.Grant] = {}
    decisions: list[CircuitDecision] = []
    deferrals: list[Deferral] = []

    # Every configured circuit is resolved, including the ones nobody asked
    # anything of: a circuit whose requests all dropped away still has to be
    # reported as idle rather than silently omitted.
    for circuit in config.circuits:
        outcome = constraints.resolve(
            config, world, circuit, tuple(by_circuit.get(circuit.circuit_id, ()))
        )
        decisions.append(outcome.decision)
        deferrals.extend(outcome.deferrals)
        for grant in outcome.grants:
            grants[grant.zone_id] = grant

    for request in solo:
        outcome = constraints.resolve(config, world, _SOLO, (request,))
        deferrals.extend(outcome.deferrals)
        for grant in outcome.grants:
            grants[grant.zone_id] = grant

    return grants, tuple(decisions), tuple(deferrals)


def _zone_reasons(
    config: DirectorConfig,
    grants: dict[str, constraints.Grant],
    dropped: dict[str, constraints.Request],
    refusals: dict[str, Reason],
) -> dict[str, Reason]:
    """Return the single reason that explains each zone's outcome.

    Every zone gets one, so a unit being switched off can always say why rather
    than falling back on a generic "nothing to do".
    """
    reasons: dict[str, Reason] = {}
    for zone in config.zones:
        grant = grants.get(zone.zone_id)
        if grant is not None:
            reasons[zone.zone_id] = grant.reason
        elif zone.zone_id in dropped:
            reasons[zone.zone_id] = Reason.EXCLUSIVE_GROUP_LOST
        else:
            reasons[zone.zone_id] = refusals.get(zone.zone_id, Reason.SATISFIED)
    return reasons


def _manual_conflict(
    config: DirectorConfig,
    world: WorldState,
    zone: Zone,
    source: Source,
    wishes: dict[str, constraints.Request],
) -> UnitCommand | None:
    """Return the command standing a manual source down, or `None` to leave it.

    Gekeken wordt naar wat de andere kamers *vragen*, niet naar wat ze *kregen*.
    Dat scheelt een klem: zolang deze unit draait houdt hij het circuit op zijn
    taak, dus de ander krijgt niets toegekend - en zou hij daarop wachten, dan
    wachtten ze allebei tot Sint-Juttemis. Wie in de weg staat gaat opzij, ook
    als de omschakeling nog een pauze te gaan heeft.

    What the other rooms *ask for* is what counts, not what they *got*. That
    avoids a deadlock: while this unit runs it holds the circuit to its duty, so
    the other is granted nothing - and were this to wait on that, both would
    wait forever. Whoever is in the way steps aside, even when the changeover
    still has a pause to sit out.
    """
    running = family_of(world.climate(source.entity_id).hvac_mode)
    if running is ModeFamily.NEUTRAL:
        return None

    # Een exclusieve groep gaat over apparaten die elkaar uitsluiten, niet over
    # taken die botsen: staat er een ander lid op het punt te draaien, dan moet
    # deze uit, ook al doen ze hetzelfde en delen ze geen buitenunit. Zonder dit
    # zou een handbediend apparaat de groep straffeloos negeren, want het doet
    # zelf nooit een aanvraag - en dan is de hele groep een papieren regel.
    #
    # An exclusive group is about appliances ruling each other out, not about
    # duties clashing: if another member is about to run, this one goes off even
    # when they do the same thing and share no outdoor unit. Without this a
    # hand-operated appliance would ignore the group with impunity, since it
    # never files a request of its own - leaving the group a rule on paper.
    if _exclusive_rival(config, zone, source, wishes):
        return _stand_down(config, zone, source, Reason.EXCLUSIVE_GROUP_LOST)

    circuit = config.circuit_for_entity(source.entity_id)
    if circuit is None or circuit.simultaneous_heat_cool:
        return None

    wanted = {
        request.family
        for zone_id, request in wishes.items()
        if zone_id != zone.zone_id
        and request.family is not ModeFamily.NEUTRAL
        and _on_circuit(config, circuit, zone_id)
    }
    if not wanted or running in wanted:
        return None

    return _stand_down(config, zone, source, Reason.CIRCUIT_CONFLICT_LOST)


def _exclusive_rival(
    config: DirectorConfig,
    zone: Zone,
    source: Source,
    wishes: dict[str, constraints.Request],
) -> bool:
    """Return whether another member of this source's exclusive group wants to run."""
    for group in config.exclusive_groups:
        if source.source_id not in group:
            continue
        for zone_id, request in wishes.items():
            if zone_id != zone.zone_id and request.source.source_id in group:
                return True
    return False


def _stand_down(config: DirectorConfig, zone: Zone, source: Source, reason: Reason) -> UnitCommand:
    """Return the command putting one source back to standing still."""
    return UnitCommand(
        entity_id=source.entity_id,
        hvac_mode=_idle_mode(config, source, reason),
        temperature=None,
        zone_id=zone.zone_id,
        source_id=source.source_id,
        reason=reason,
    )


def _on_circuit(config: DirectorConfig, circuit: Circuit, zone_id: str) -> bool:
    """Return whether any of that zone's sources hangs on this circuit."""
    zone = config.zone(zone_id)
    if zone is None:
        return False
    return any(source.entity_id in circuit.units for source in zone.sources)


def _build_commands(
    config: DirectorConfig,
    world: WorldState,
    grants: dict[str, constraints.Grant],
    reasons: dict[str, Reason],
    wishes: dict[str, constraints.Request],
) -> tuple[UnitCommand, ...]:
    """Return the end state for every managed climate entity.

    Sources that were not chosen are commanded off explicitly rather than left
    alone. That is what makes two appliances running against each other
    unreachable instead of merely unlikely.
    """
    commands: list[UnitCommand] = []

    for zone, source in config.sources():
        if not world.climate(source.entity_id).available:
            continue

        grant = grants.get(zone.zone_id)
        chosen = grant is not None and grant.granted and grant.source_id == source.source_id

        # Een handbediende bron wordt niet aangestuurd tenzij hij in de weg
        # staat. Hem "voor de zekerheid" uitzetten zou precies het apparaat
        # uitschakelen dat iemand net met de hand heeft aangezet.
        #
        # A manual source is left alone unless it is in the way. Switching it
        # off "to be safe" would turn off exactly the appliance somebody just
        # switched on by hand.
        if not source.autostart:
            standing_down = _manual_conflict(config, world, zone, source, wishes)
            if standing_down is not None:
                commands.append(standing_down)
            continue

        if chosen and grant is not None:
            settings = zone.settings_for(grant.family)
            commands.append(
                UnitCommand(
                    entity_id=source.entity_id,
                    hvac_mode=preferred_mode(grant.family),
                    temperature=settings.target if settings else None,
                    zone_id=zone.zone_id,
                    source_id=source.source_id,
                    reason=Reason.REGULATING,
                )
            )
            continue

        # A zone that is being served has its other sources stood down for that
        # reason, not for whatever kept the chosen source waiting.
        served = grant is not None and grant.granted
        reason = (
            Reason.OTHER_SOURCE_CHOSEN if served else reasons.get(zone.zone_id, Reason.SATISFIED)
        )
        commands.append(
            UnitCommand(
                entity_id=source.entity_id,
                hvac_mode=_idle_mode(config, source, reason),
                temperature=None,
                zone_id=zone.zone_id,
                source_id=source.source_id,
                reason=reason,
            )
        )

    commands.extend(_generator_commands(config, world, grants))

    # Stops before starts. On a circuit that has to swap duty, starting the new
    # one before the old has let go would put two duties on one compressor for
    # as long as the calls take to land.
    return tuple(sorted(commands, key=lambda command: _command_order(config, command)))


def _generator_commands(
    config: DirectorConfig, world: WorldState, grants: dict[str, constraints.Grant]
) -> list[UnitCommand]:
    """Return the command for each shared heat source.

    A generator runs while any zone it serves is being heated, and stops once
    none is. There is nothing to arbitrate here - radiator valves all only ever
    heat - so this is a plain follow-along, not a conflict to resolve.
    """
    commands: list[UnitCommand] = []

    for generator in config.generators:
        if not world.climate(generator.entity_id).available:
            continue

        asking = [
            zone
            for zone in config.zones
            if generator.serves(zone.zone_id)
            and (grant := grants.get(zone.zone_id)) is not None
            and grant.granted
            and grant.family is ModeFamily.HEAT
        ]

        if not asking:
            commands.append(
                UnitCommand(
                    entity_id=generator.entity_id,
                    hvac_mode=MODE_OFF,
                    source_id=generator.generator_id,
                    reason=Reason.SATISFIED,
                )
            )
            continue

        # Zonder vaste waarde volgt de bron de warmste vraag. Het koudste
        # setpoint nemen zou de kamer die het hardst om warmte vraagt nooit
        # laten halen wat hij vroeg.
        #
        # Without a fixed value the source follows the warmest demand. Taking
        # the coldest setpoint would leave the room asking hardest never
        # reaching what it asked for.
        setpoint = generator.setpoint
        if setpoint is None:
            targets = [zone.heat.target for zone in asking if zone.heat]
            setpoint = max(targets) if targets else None

        commands.append(
            UnitCommand(
                entity_id=generator.entity_id,
                hvac_mode=MODE_HEAT,
                temperature=setpoint,
                source_id=generator.generator_id,
                reason=Reason.REGULATING,
            )
        )

    return commands


def _idle_mode(config: DirectorConfig, source: Source, reason: Reason) -> str:
    """Return how a source stands down: off, or circulating air.

    Fan-only is only ever offered to a zone that lost its circuit to another
    zone. A zone that is simply warm enough has nothing to circulate for, and
    leaving its fan running would read as a fault.
    """
    if reason is not Reason.CIRCUIT_CONFLICT_LOST:
        return MODE_OFF
    circuit = config.circuit_for_entity(source.entity_id)
    if circuit is not None and circuit.allow_fan_only_during_conflict:
        return MODE_FAN_ONLY
    return MODE_OFF


def _command_order(config: DirectorConfig, command: UnitCommand) -> tuple[int, str]:
    """Return the ordering key that puts stops ahead of starts.

    A shared heat source starts last of all. Firing the boiler before the
    valves are open would have it heat water against closed radiators; the
    other way round the room is simply cold for a moment longer.
    """
    generators = {item.entity_id for item in config.generators}
    if command.hvac_mode == MODE_OFF:
        rank = 0
    elif command.hvac_mode == MODE_FAN_ONLY:
        rank = 1
    elif command.entity_id in generators:
        rank = 3
    else:
        rank = 2
    return (rank, command.entity_id)


def _build_zone_decisions(
    config: DirectorConfig,
    wishes: dict[str, constraints.Request],
    dropped: dict[str, constraints.Request],
    grants: dict[str, constraints.Grant],
    refusals: dict[str, Reason],
) -> tuple[ZoneDecision, ...]:
    """Return one decision per zone, saying what it asked for and what it got."""
    decisions: list[ZoneDecision] = []

    for zone in config.zones:
        request = wishes.get(zone.zone_id)

        if request is None:
            # A zone that lost a shared appliance still had a wish; keep it, so
            # the decision reads "wanted heat, got nothing" rather than hiding
            # the request that was made.
            loser = dropped.get(zone.zone_id)
            decisions.append(
                ZoneDecision(
                    zone_id=zone.zone_id,
                    wanted=loser.family if loser else ModeFamily.NEUTRAL,
                    granted=ModeFamily.NEUTRAL,
                    source_id=loser.source.source_id if loser else None,
                    reason=(
                        Reason.EXCLUSIVE_GROUP_LOST
                        if loser
                        else refusals.get(zone.zone_id, Reason.SATISFIED)
                    ),
                )
            )
            continue

        grant = grants.get(zone.zone_id)
        decisions.append(
            ZoneDecision(
                zone_id=zone.zone_id,
                wanted=request.family,
                granted=grant.family if grant is not None else ModeFamily.NEUTRAL,
                source_id=request.source.source_id,
                reason=grant.reason if grant is not None else Reason.NO_SOURCE_AVAILABLE,
            )
        )

    return tuple(decisions)


def _running_family(zone: Zone, world: WorldState) -> ModeFamily:
    """Return the duty this zone is running now, for the dead band to build on."""
    for source in zone.sources:
        family = world.climate(source.entity_id).family
        if family in (ModeFamily.HEAT, ModeFamily.COOL):
            return family
    return ModeFamily.NEUTRAL
