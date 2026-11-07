"""Wat een zone uiteindelijk te horen krijgt. / What a zone finally hears."""

from __future__ import annotations

from . import constraints, hysteresis, sources, takeover
from .candidates import handed_over, serving
from .families import (
    MODE_FAN_ONLY,
    MODE_OFF,
    ModeFamily,
    family_of,
)
from .models import DirectorConfig
from .plan import (
    Plan,
    Reason,
    UnitCommand,
    ZoneDecision,
)
from .world import ClimateState, WorldState


def command_order(config: DirectorConfig, command: UnitCommand) -> tuple[int, str]:
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


def lost_to_another_zone(
    commands: tuple[UnitCommand, ...],
    request: constraints.Request,
    grant: constraints.Grant | None,
) -> Reason | None:
    """Return why this zone does not get its duty, or `None` when it does.

    `collapse_shared` houdt per apparaat één opdracht over. Vraagt de ene kamer
    warmte en de andere koelte, dan volgt dat apparaat de kamer met de meeste
    voorrang, en houdt de andere kamer een `grant` over die niet gebeurt. Deze
    functie geeft de reden die daarbij hoort, zodat de zonebeslissing niet blijft
    zeggen dat zij een taak krijgt die het apparaat niet uitvoert.

    Alleen een apparaat dat de tegenovergestelde taak draait telt hier mee: het
    apparaat volgt dan een andere kamer. Een stop van buitenaf komt hier niet,
    want die zet de zone haar verzoek al af - een openstaande deur of een
    gesloten rooster laat `collect_wishes` geen verzoek achter, dus er valt dan
    geen `grant` meer te verliezen.

    `collapse_shared` keeps one command per appliance. If one room asks for heat
    and another for cool, that appliance follows the room with the most claim,
    and the other room is left with a `grant` that does not happen. This function
    returns the reason that goes with it, so the zone decision stops claiming a
    duty the appliance does not carry out.

    Only an appliance running the opposite duty counts here: it is then following
    a different room. A stop from outside does not arrive here, because it
    already drops the zone's request - an open door or a closed schedule leaves
    `collect_wishes` without a request, so there is no `grant` left to lose.
    """
    if grant is None or grant.family is ModeFamily.NEUTRAL:
        return None
    surviving = next(
        (command for command in commands if command.entity_id == request.source.entity_id), None
    )
    if surviving is None or family_of(surviving.hvac_mode) is grant.family:
        return None
    return Reason.CIRCUIT_CONFLICT_LOST


def build_zone_decisions(
    config: DirectorConfig,
    world: WorldState,
    wishes: dict[str, constraints.Request],
    dropped: dict[str, constraints.Request],
    grants: dict[str, constraints.Grant],
    refusals: dict[str, Reason],
    shut: dict[str, tuple[Reason, ...]],
    demands: dict[str, hysteresis.Demand],
    previous: Plan | None = None,
    blocked: frozenset[str] = frozenset(),
    refused_by_circuit: dict[str, frozenset[str]] | None = None,
    takeovers: tuple[takeover.Takeover, ...] = (),
    commands: tuple[UnitCommand, ...] = (),
) -> tuple[ZoneDecision, ...]:
    """Return one decision per zone, saying what it asked for and what it got."""
    refused_by_circuit = refused_by_circuit or {}
    decisions: list[ZoneDecision] = []
    # Een huisbreed overgedragen apparaat is geen storing maar een overdracht:
    # het hoort dus niet als "op reserve" in `passed_over` (anker 11). Het valt
    # daarom alleen uit de keuze, via het eigen argument `handed_over_ids`, en niet in
    # de lijst zoals een geweigerd of onbereikbaar apparaat.
    # A house-wide handed-over appliance is no fault but a handover: it therefore
    # does not belong in `passed_over` as "on reserve" (anchor 11). It drops out of
    # the choice only, through its own `handed_over_ids` argument, and not into the list
    # like a refused or unreachable appliance.
    handed_over_ids = handed_over(config, world)

    for zone in config.zones:
        request = wishes.get(zone.zone_id)
        demand = demands.get(zone.zone_id)
        would = demand.family if demand else ModeFamily.NEUTRAL

        if request is None:
            # A zone that lost a shared appliance still had a wish; keep it, so
            # the decision reads "wanted heat, got nothing" rather than hiding
            # the request that was made.
            loser = dropped.get(zone.zone_id)
            refused = refusals.get(zone.zone_id, Reason.SATISFIED)
            reason = Reason.EXCLUSIVE_GROUP_LOST if loser else refused
            decisions.append(
                ZoneDecision(
                    zone_id=zone.zone_id,
                    wanted=loser.family if loser else ModeFamily.NEUTRAL,
                    granted=ModeFamily.NEUTRAL,
                    source_id=loser.source.source_id if loser else None,
                    reason=reason,
                    closed_gates=shut.get(zone.zone_id, ()),
                    would_want=would,
                    duty=demand.duty if demand and demand.reason is reason else ModeFamily.NEUTRAL,
                )
            )
            continue

        grant = grants.get(zone.zone_id)
        # De uitwijkmelder moet met dezelfde stop rekenen als het plan. Voor
        # een zone met een bypass-verzoek is de huisbrede stop overgeslagen in
        # `collect_wishes`; gaven we hem hier tóch mee, dan kon de melder een
        # andere bron als "gekozen" aannemen en een onbereikbare tweede keus
        # melden die helemaal niet aan de beurt was.
        #
        # The fallback reporter must reckon with the same stop as the plan.
        # For a zone with a bypassing request the house-wide stop was skipped
        # in `collect_wishes`; handing it over here anyway would let the
        # reporter assume another source was chosen and name an unreachable
        # second choice that never got its turn.
        zone_blocked = frozenset() if world.precondition_ignores_openings(zone.zone_id) else blocked
        only, unbounded = takeover.narrowing(takeovers, zone.zone_id, request.family)
        stood_down = next(
            (
                command
                for command in commands
                if command.zone_id == zone.zone_id
                and command.source_id == request.source.source_id
                and command.reason is Reason.SHARED_SOURCE_TOOK_OVER
            ),
            None,
        )
        if stood_down is not None:
            # Anker 1 vierde uitzondering / anker 12: een overgenomen gebied
            # verwarmt of koelt nooit tegelijk met de overnemer, ook niet op
            # een lopend vooruit-verzoek. Het commando staat al uit; de
            # zonebeslissing hoort datzelfde te zeggen in plaats van een
            # koelende airco te blijven tonen (A2).
            decisions.append(
                ZoneDecision(
                    zone_id=zone.zone_id,
                    wanted=request.family,
                    granted=ModeFamily.NEUTRAL,
                    source_id=request.source.source_id,
                    reason=Reason.SHARED_SOURCE_TOOK_OVER,
                    closed_gates=shut.get(zone.zone_id, ()),
                    would_want=would,
                )
            )
            continue
        lost = lost_to_another_zone(commands, request, grant)
        if lost is not None:
            decisions.append(
                ZoneDecision(
                    zone_id=zone.zone_id,
                    wanted=request.family,
                    granted=ModeFamily.NEUTRAL,
                    source_id=request.source.source_id,
                    reason=lost,
                    closed_gates=shut.get(zone.zone_id, ()),
                    would_want=would,
                )
            )
            continue
        decisions.append(
            ZoneDecision(
                zone_id=zone.zone_id,
                wanted=request.family,
                granted=grant.family if grant is not None else ModeFamily.NEUTRAL,
                source_id=request.source.source_id,
                reason=grant.reason if grant is not None else Reason.NO_SOURCE_AVAILABLE,
                closed_gates=shut.get(zone.zone_id, ()),
                passed_over=sources.passed_over(
                    zone,
                    request.family,
                    world,
                    serving(previous, zone.zone_id),
                    config.outdoor_hysteresis,
                    zone_blocked,
                    refused_by_circuit.get(zone.zone_id, frozenset()),
                    only,
                    unbounded,
                    handed_over=handed_over_ids,
                ),
                would_want=would,
            )
        )

    return tuple(decisions)


def clamped_target(target: float | None, state: ClimateState) -> float | None:
    """Clamp a setpoint to what the appliance says it accepts.

    Home Assistant weigert een setpoint buiten `min_temp`/`max_temp` met een
    `ServiceValidationError`, en de stand ging dan nooit meer mee. Beter: vraag
    het dichtstbijzijnde setpoint dat het apparaat wél aanneemt, zodat de stand
    gewoon landt. Geen opgave betekent onbekend, en onbekend wordt doorgelaten.

    Home Assistant refuses a setpoint outside `min_temp`/`max_temp` with a
    `ServiceValidationError`, and the mode then never went along. Better: ask
    for the nearest setpoint the appliance does accept, so the mode simply
    lands. No listing means unknown, and unknown is passed through.
    """
    if target is None:
        return None
    if state.min_temp is not None and target < state.min_temp:
        return state.min_temp
    if state.max_temp is not None and target > state.max_temp:
        return state.max_temp
    return target
