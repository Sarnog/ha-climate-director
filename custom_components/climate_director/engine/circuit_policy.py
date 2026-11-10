"""De taakkeuze op een circuit.

The duty choice on a circuit.

Welke taak (`heat` of `cool`) een circuit draait, welke taken apparaten buiten de
greep van de director al afdwingen, en welke taak wint als zones iets anders
vragen. De regel die alles stuurt staat in `constraints.py`.

Which duty (`heat` or `cool`) a circuit runs, which duties appliances outside the
director's control already force, and which duty wins when zones ask for
different things. The rule that drives everything stands in `constraints.py`.
"""

from __future__ import annotations

from .circuit_requests import Request
from .families import ModeFamily, claims_compressor
from .models import Circuit, ConflictPolicy, DirectorConfig, Season
from .plan import Reason
from .world import WorldState


def active_family(world: WorldState, circuit: Circuit) -> ModeFamily:
    """Return the duty a circuit is running right now.

    Reads every entity on the circuit, including indoor units the director does
    not manage: an unmanaged unit still claims the compressor. A mode that
    claims the compressor without naming its duty (`heat_cool`, `auto`, or an
    unknown mode) is reported as `AMBIGUOUS` - it locks the circuit against a
    duty the director would put beside it, even though it cannot be used as a
    concrete label. On the contradictory reading of two claiming units, the
    first in configured order wins, so the answer stays deterministic.
    """
    for entity_id in circuit.units:
        family = world.climate(entity_id).family
        if claims_compressor(family):
            return family
    return ModeFamily.NEUTRAL


def forced_families(
    config: DirectorConfig,
    world: WorldState,
    circuit: Circuit,
    standing: frozenset[str] = frozenset(),
) -> frozenset[ModeFamily]:
    """Return the duties forced on a circuit by units the director cannot steer.

    Twee soorten dwingen: een unit die in geen enkele zone staat, en een unit
    die deze ronde met opzet niets krijgt en gewoon doordraait. Die tweede werd
    hier niet meegeteld, en daardoor kon de director de tegengestelde taak op
    dezelfde buitenunit zetten terwijl er nog een unit in de eerste taak stond
    te draaien - precies de toestand die hier onbereikbaar hoort te zijn.

    Alle taken worden teruggegeven en niet alleen de eerste. Een mens kan met
    een afstandsbediening en een override twee taken tegelijk op een circuit
    zetten; wie dan alleen naar de eerste keek, zag de tweede over het hoofd en
    kon er een derde unit bij aanzetten. `AMBIGUOUS` telt net zo hard mee als
    een concrete taak: wie op `auto` draait claimt de compressor, en zolang de
    director die taak niet kan lezen zet hij er niets naast.

    Two kinds compel: a unit sitting in no zone at all, and a unit that
    deliberately gets nothing this round and simply keeps running. That second
    one was left out here, which let the director put the opposing duty on the
    same outdoor unit while a unit still ran the first - exactly the state this
    is meant to make unreachable.

    Every duty is returned rather than only the first. A person can put two
    duties on one circuit at once with a remote and an override; looking at the
    first alone missed the second and allowed a third unit to be started beside
    them. `AMBIGUOUS` counts just as hard as a concrete duty: a unit running
    `auto` claims the compressor, and as long as the director cannot read that
    duty it puts nothing beside it.

    De hele D1-eigenschap hangt aan de filter `claims_compressor(family)`
    hieronder; haal die regel nooit als "opruiming" weg. De twee andere
    D1-bewerkingen (`active_family` en de `AMBIGUOUS`-tak van `choose_family`)
    zijn aantoonbaar equivalent.

    The whole D1 property hangs on the `claims_compressor(family)` filter below;
    never remove that line as a cleanup. The two other D1 edits (`active_family`
    and the `AMBIGUOUS` branch of `choose_family`) are provably equivalent.
    """
    managed = {source.entity_id for _, source in config.sources_on(circuit)}
    # Een generator die in dit circuit staat is óók beheerd: de director stuurt
    # hem via `_generator_commands` net zo goed uit als een gewone bron. Hem als
    # "onbeheerd" meetellen zette het circuit op zijn taak vast, terwijl de
    # director hem juist kán uitzetten.
    #
    # A generator sitting on this circuit is managed too: the director stands it
    # down through `_generator_commands` just like an ordinary source. Counting
    # it as "unmanaged" pinned the circuit to its duty even though the director
    # can switch it off.
    managed |= {
        generator.entity_id
        for generator in config.generators
        if generator.entity_id in circuit.units
    }
    return frozenset(
        family
        for entity_id in circuit.units
        if entity_id not in managed or entity_id in standing
        for family in (world.climate(entity_id).family,)
        if claims_compressor(family)
    )


def choose_family(
    world: WorldState,
    circuit: Circuit,
    requests: tuple[Request, ...],
    current: ModeFamily,
    forced: frozenset[ModeFamily],
) -> tuple[ModeFamily, Reason]:
    """Return the duty the circuit should run, and why."""
    if not requests:
        return ModeFamily.NEUTRAL, Reason.SATISFIED

    wanted = {request.family for request in requests}

    # Staan er al twee taken te draaien op apparaten waar de director niet aan
    # mag komen, dan is er geen taak die dit circuit veilig kan draaien. Zo'n
    # toestand kan hij niet zelf maken en niet rechtzetten - maar hij hoort er
    # dan zeker geen unit bij te zetten.
    #
    # With two duties already running on appliances the director may not touch,
    # there is no duty this circuit can safely run. It can neither create nor
    # put right such a state - but it certainly should not add a unit to it.
    if len(forced) > 1:
        return ModeFamily.NEUTRAL, Reason.CIRCUIT_CONFLICT_LOST

    # Een unit buiten de greep van de director heeft de compressor al geclaimd;
    # daar kan niets hier overheen. Een claim die de director niet kán lezen
    # (`auto`, `heat_cool`, onbekend) zet het circuit vast zonder een taak te
    # noemen: geen enkele concrete taak kan er veilig naast draaien, dus krijgt
    # geen enkele zone er een.
    #
    # A unit outside the director's control has already claimed the compressor;
    # nothing here can overrule that. A claim the director cannot read (`auto`,
    # `heat_cool`, unknown) locks the circuit without naming a duty: no concrete
    # duty can safely run beside it, so no zone gets one.
    if ModeFamily.AMBIGUOUS in forced:
        return ModeFamily.NEUTRAL, Reason.CIRCUIT_CONFLICT_LOST

    if forced:
        locked = next(iter(forced))
        settled = wanted == {locked}
        return locked, Reason.REGULATING if settled else Reason.CIRCUIT_CONFLICT_LOST

    if len(wanted) == 1:
        return next(iter(wanted)), Reason.REGULATING

    if circuit.conflict_policy is ConflictPolicy.FIRST_COME and current in wanted:
        return current, Reason.CIRCUIT_CONFLICT_LOST

    if circuit.conflict_policy is ConflictPolicy.DEMAND:
        winner = max(requests, key=lambda request: (request.deviation, -request.priority))
        return winner.family, Reason.CIRCUIT_CONFLICT_LOST

    if circuit.conflict_policy is ConflictPolicy.SEASON_LOCK:
        preferred = {
            Season.SUMMER: ModeFamily.COOL,
            Season.WINTER: ModeFamily.HEAT,
        }.get(world.season)
        if preferred in wanted:
            return preferred, Reason.CIRCUIT_CONFLICT_LOST

    # Priority, and the fallback for every policy that could not decide.
    return requests[0].family, Reason.CIRCUIT_CONFLICT_LOST


def any_managed_running(
    config: DirectorConfig, world: WorldState, circuit: Circuit, family: ModeFamily
) -> bool:
    """Return whether the director still has a unit running `family` here."""
    return any(
        world.climate(source.entity_id).family is family for _, source in config.sources_on(circuit)
    )
