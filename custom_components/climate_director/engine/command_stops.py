"""De stopboekhouding en het samenvouwen van gedeelde opdrachten.

The stop bookkeeping and collapsing shared commands.
"""

from __future__ import annotations

from datetime import datetime

from . import circuit_requests
from .families import MODE_FAN_ONLY, MODE_OFF
from .models import DirectorConfig
from .plan import OPENING_MIN_REST, Plan, Reason, UnitCommand
from .world import WorldState


def opening_rest_bookkeeping(
    world: WorldState,
    previous: Plan | None,
    commands: tuple[UnitCommand, ...],
    stopped_now: frozenset[str],
) -> dict[str, datetime]:
    """Return this plan's per-appliance opening-rest bookkeeping.

    De rust hangt aan het apparaat, niet aan de reden van het vorige commando.
    `opening_rest_until` draagt de eindtijd van elke rust, gerekend vanaf de
    stop zelf (anker 5): een verse openingsstop krijgt meteen
    `world.now + OPENING_MIN_REST`, en die eindtijd wordt ronde na ronde
    meegedragen zolang het apparaat niet draait.

    The rest hangs on the appliance, not on the previous command's reason.
    `opening_rest_until` carries each rest's deadline, counted from the stop
    itself (anchor 5): a fresh opening stop gets `world.now + OPENING_MIN_REST`
    at once, and that deadline is carried round after round while the appliance
    stays off.
    """
    if previous is None:
        return {entity: world.now + OPENING_MIN_REST for entity in stopped_now}

    commanded_running = {
        command.entity_id
        for command in commands
        if command.hvac_mode not in (MODE_OFF, MODE_FAN_ONLY)
    }
    commanded = {command.entity_id for command in commands}
    carried_until = dict(previous.opening_rest_until)
    dropped = {
        entity
        for entity in carried_until
        if entity in commanded_running
        or (entity not in commanded and world.climate(entity).running)
    }

    opening_rest_until = {
        entity: until for entity, until in carried_until.items() if entity not in dropped
    }
    opening_rest_until.update({entity: world.now + OPENING_MIN_REST for entity in stopped_now})
    return opening_rest_until


def stop_blocked(
    config: DirectorConfig,
    world: WorldState,
    grants: dict[str, circuit_requests.Grant],
    blocked: frozenset[str],
    commands: list[UnitCommand],
) -> list[UnitCommand]:
    """Return the commands with every house-wide stopped appliance forced off.

    De bronkeuze laat een stilgezet apparaat al vallen, dus in de gewone gang
    van zaken verandert dit niets. Het staat er voor de paden die buiten die
    keuze omgaan - een gedeelde ketel die zijn commando van een andere zone
    kreeg, en de generator, die helemaal geen bronkeuze doorloopt. Zo kan er
    langs geen enkele weg alsnog een `heat` uitkomen.

    Wat de director met rust laat blijft met rust: een overgedragen zone en een
    handbediende bron krijgen geen commando, en die staan hier dus ook niet in.
    Deze instelling stuurt wat de director stuurt; hij is geen uitknop die over
    een override heen gaat.

    Source selection already drops a stopped appliance, so in the ordinary run
    of things this changes nothing. It is here for the paths going round that
    choice - a shared boiler that got its command from another zone, and the
    generator, which never runs through source selection at all. That way no
    route can let a `heat` come out after all.

    Whatever the director leaves alone stays left alone: a zone handed over and
    a hand-operated source get no command, and are therefore absent here too.
    This setting steers what the director steers; it is no off switch reaching
    over an override.
    """
    if not blocked:
        return commands
    return [
        command
        if command.entity_id not in blocked
        or command.hvac_mode in (MODE_OFF, MODE_FAN_ONLY)
        or ignores_openings(config, world, grants, command)
        else UnitCommand(
            entity_id=command.entity_id,
            hvac_mode=MODE_OFF,
            temperature=None,
            zone_id=command.zone_id,
            source_id=command.source_id,
            reason=Reason.OPENING_OPEN_ELSEWHERE,
        )
        for command in commands
    ]


def ignores_openings(
    config: DirectorConfig,
    world: WorldState,
    grants: dict[str, circuit_requests.Grant],
    command: UnitCommand,
) -> bool:
    """Return whether this command carries a pre-conditioning "do it anyway".

    Een zonecommando draagt zijn eigen zone. Een generator hoort bij geen zone,
    dus daar telt of een van de zones die hij bedient dat verzoek draagt en op
    dit moment ook echt bediend wordt - anders zou een uitzondering in een kamer
    die niets krijgt de ketel alsnog laten branden.

    A zone command carries its own zone. A generator belongs to no zone, so
    there it counts whether one of the zones it serves carries that request and
    is actually being served right now - otherwise an exception in a room
    getting nothing would keep the boiler burning after all.
    """
    if command.zone_id:
        return world.precondition_ignores_openings(command.zone_id)
    return any(
        world.precondition_ignores_openings(zone.zone_id)
        and (grant := grants.get(zone.zone_id)) is not None
        and grant.granted
        for generator in config.generators
        if generator.entity_id == command.entity_id
        for zone in config.zones
        if generator.serves(zone.zone_id)
    )


def collapse_shared(
    config: DirectorConfig, world: WorldState, commands: list[UnitCommand]
) -> list[UnitCommand]:
    """Return one command per appliance, so a shared source never gets two.

    Bij een centrale verwarming staat dezelfde thermostaat als bron onder
    meerdere zones. De opdrachten worden per zone opgebouwd, dus zo'n apparaat
    kreeg er een van elke zone - en die spreken elkaar tegen zodra de ene kamer
    warmte vraagt en de andere niets. Twee tegengestelde opdrachten naar een
    apparaat is nooit goed; welke er wint hing af van de volgorde, en dat is
    geen ontwerp maar toeval.

    Vraag wint van stilte: een gesloten systeem heeft nu eenmaal geen manier om
    de ene kamer wel en de andere niet te verwarmen. Vragen er meer zones
    tegelijk, dan volgt het apparaat de zone met de meeste voorrang - net zoals
    een gewone thermostaat de leidende kamer volgt. Die voorrang is de live
    waarde, niet de ingestelde: een automatisering die `number.<zone>_prioriteit`
    verzet hoort de gedeelde ketel net zo goed te sturen als de rest.

    With central heating the same thermostat sits as a source under several
    zones. Commands are built per zone, so such an appliance got one from each -
    and they contradict each other the moment one room asks for heat and the
    other does not. Two opposing commands to one appliance is never right; which
    won depended on ordering, and that is chance rather than design.

    Demand beats silence: a closed system simply has no way to heat one room and
    not the other. If several zones ask at once, the appliance follows the zone
    with the most claim - just as an ordinary thermostat follows the leading
    room. That claim is the live priority, not the configured one: an automation
    moving `number.<zone>_priority` should steer the shared boiler just as much
    as the rest.
    """
    ranked: dict[str, UnitCommand] = {}
    for command in commands:
        sitting = ranked.get(command.entity_id)
        if sitting is None or claim(config, world, command) < claim(config, world, sitting):
            ranked[command.entity_id] = command
    return list(ranked.values())


def claim(config: DirectorConfig, world: WorldState, command: UnitCommand) -> tuple[int, int, str]:
    """Return how strong a command's claim on its appliance is; lower wins."""
    running = command.hvac_mode not in (MODE_OFF, MODE_FAN_ONLY)
    zone = config.zone(command.zone_id) if command.zone_id else None
    priority = world.priority_for(command.zone_id or "", zone.priority) if zone else 0
    return (0 if running else 1, priority, command.zone_id or "")
