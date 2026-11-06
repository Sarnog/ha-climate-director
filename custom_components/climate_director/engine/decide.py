"""De beslisfunctie: van momentopname naar plan.

The decision function: from snapshot to plan.

`decide()` is de enige ingang van de engine en het enige punt waar besloten
wordt. De stappen wonen in de modules ernaast.

`decide()` is the engine's only entry point and the only place a decision is
made. The steps live in the modules beside it.
"""

from __future__ import annotations

from . import gates, takeover
from .candidates import collect_wishes, standing_firm
from .command_stops import opening_rest_bookkeeping
from .commands import build_commands
from .grants import resolve_with_fallbacks, zone_reasons
from .models import DirectorConfig
from .plan import Plan
from .world import WorldState
from .zone_decisions import build_zone_decisions


def decide(config: DirectorConfig, world: WorldState, previous: Plan | None = None) -> Plan:
    """Return the complete, consistent end state the installation should be in.

    `previous` is het plan van de vorige ronde. De dode band en de stiltevensters
    moeten weten of deze zone zelf draait, en bij een gedeeld apparaat zegt de
    apparaattoestand dat niet: die telt alleen voor de zone die het commando
    kreeg.

    `previous` is the previous round's plan. The dead band and the quiet windows
    need to know whether this zone itself is running, and on a shared appliance
    the appliance state does not say that: it counts only for the zone that got
    the command.
    """
    blocked = gates.house_wide_blocked(config, world)
    # Anker 12: welke bron een gebied overneemt staat vóór de bronkeuze vast,
    # want het bepaalt wélke bron een kamer nog mag kiezen.
    #
    # Anchor 12: which source takes an area over is settled before source
    # selection, since it decides which source a room may still choose.
    takeovers = takeover.in_force(config, world)
    wishes, refusals, shut, demands, rest_deferrals = collect_wishes(
        config, world, previous, blocked, takeovers
    )

    standing = standing_firm(config, world, refusals)
    grants, circuit_decisions, deferrals, refused_by_circuit, dropped, wishes = (
        resolve_with_fallbacks(config, world, wishes, standing, blocked, previous, takeovers)
    )
    reasons = zone_reasons(config, grants, dropped, refusals)

    families = {decision.circuit_id: decision.family for decision in circuit_decisions}
    commands, untouched, generator_deferrals, stopped_now = build_commands(
        config, world, grants, reasons, wishes, refusals, families, blocked, previous, takeovers
    )
    opening_rest_until = opening_rest_bookkeeping(world, previous, commands, stopped_now)
    return Plan(
        commands=commands,
        zones=build_zone_decisions(
            config,
            world,
            wishes,
            dropped,
            grants,
            refusals,
            shut,
            demands,
            previous,
            blocked,
            refused_by_circuit,
            takeovers,
            commands,
        ),
        circuits=circuit_decisions,
        deferrals=(*deferrals, *rest_deferrals, *generator_deferrals),
        untouched=untouched,
        opening_rest_until=opening_rest_until,
        refused_by_circuit=refused_by_circuit,
    )
