"""De controles op circuits.

The checks on circuits.

Dubbele circuit-id's, een eenheid op twee circuits, de circuitregels, de indeling van
de verwarming en de wisseltijden.

Doubled circuit ids, a unit on two circuits, the circuit rules, the heating layout
and the switch times.
"""

from __future__ import annotations

from collections.abc import Iterator

from .families import ModeFamily
from .models import DirectorConfig, HeatingLayout, Source
from .problem import Problem
from .validation_shared import duplicates


def rule_duplicate_circuit_ids(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for every circuit id that occurs more than once.

    Een circuit-id is de sleutel van de circuittoestand; twee circuits met
    dezelfde id zijn van buiten niet meer uit elkaar te houden.

    A circuit id is the key of circuit state; two circuits sharing one can no
    longer be told apart from the outside.
    """
    for circuit_id in duplicates([circuit.circuit_id for circuit in config.circuits]):
        yield Problem(
            "duplicate_circuit_id", f"duplicate circuit id: {circuit_id}", circuit=circuit_id
        )


def rule_unit_on_two_circuits(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for every unit sitting on more than one circuit.

    Een unit kan maar op één buitenunit hangen; staat hij op twee circuits,
    dan is de configuratie met de hand bewerkt of verkeerd overgenomen en
    weet de engine niet welk circuit hij moet geloven.

    A unit can hang on only one outdoor unit; sitting on two circuits means
    the configuration was hand-edited or copied wrongly, and the engine does
    not know which circuit to believe.
    """
    seen_units: dict[str, str] = {}
    for circuit in config.circuits:
        for unit in circuit.units:
            if unit in seen_units:
                yield Problem(
                    "unit_on_two_circuits",
                    f"unit {unit} sits on both circuit {seen_units[unit]} "
                    f"and circuit {circuit.circuit_id}",
                    unit=unit,
                    first=seen_units[unit],
                    second=circuit.circuit_id,
                )
            else:
                seen_units[unit] = circuit.circuit_id


def rule_circuits(config: DirectorConfig) -> Iterator[Problem]:
    """Yield every circuit complaint: shared priority, capacity, timing.

    Twee zones op één buitenunit met hetzelfde nummer laten de uitkomst
    afhangen van hun zone-id, dus alfabetisch. Dat crasht niets en beschadigt
    niets - de tie-break is deterministisch en het circuit houdt zich aan zijn
    ene taak - maar welke kamer wint is dan onzichtbaar en willekeurig.

    Two zones on one outdoor unit sharing a number leave the outcome hanging
    on their zone id, so alphabetical. That crashes nothing and damages
    nothing - the tie-break is deterministic and the circuit still keeps to
    its one duty - but which room wins becomes invisible and arbitrary.
    """
    for circuit in config.circuits:
        seen: dict[int, str] = {}
        for zone, _ in config.sources_on(circuit):
            if zone.priority in seen and seen[zone.priority] != zone.zone_id:
                yield Problem(
                    "shared_priority",
                    f"zones {seen[zone.priority]} and {zone.zone_id} share priority "
                    f"{zone.priority} on circuit {circuit.circuit_id}",
                    first=seen[zone.priority],
                    second=zone.zone_id,
                    priority=zone.priority,
                    circuit=circuit.circuit_id,
                )
            else:
                seen[zone.priority] = zone.zone_id

        if circuit.max_concurrent_units is not None and circuit.max_concurrent_units < 1:
            yield Problem(
                "circuit_allows_no_unit",
                f"circuit {circuit.circuit_id} allows no unit to run at all",
                circuit=circuit.circuit_id,
            )
        for label, span in (
            ("family switch delay", circuit.family_switch_delay),
            ("minimum switch interval", circuit.min_family_switch_interval),
            ("minimum cycle time", circuit.min_cycle_time),
        ):
            if span.total_seconds() < 0:
                yield Problem(
                    "circuit_negative_timing",
                    f"circuit {circuit.circuit_id} has a negative {label}",
                    circuit=circuit.circuit_id,
                    label=label,
                )


def layout_problems(config: DirectorConfig) -> list[str]:
    """Return the complaints about a heating layout that does not match the wiring.

    Waarschuwingen, geen blokkade. De director regelt gewoon door; dit zegt
    alleen dat de installatie er anders uitziet dan wat je koos, en dat is bijna
    altijd een vergissing die je pas merkt als het huis op de verkeerde plek
    warm wordt.

    Warnings, not a block. The director carries on regulating; this only says
    the installation looks different from what you picked, which is nearly
    always a mistake you notice when the wrong part of the house gets warm.
    """
    if len(config.zones) < 2:
        return []

    def heats(source: Source) -> bool:
        return bool(source.entity_id) and source.supports(ModeFamily.HEAT)

    # Welke zones leunen op welk verwarmingsapparaat.
    # Which zones lean on which heating appliance.
    shared: dict[str, list[str]] = {}
    for zone in config.zones:
        for entity_id in {source.entity_id for source in zone.sources if heats(source)}:
            shared.setdefault(entity_id, []).append(zone.zone_id)
    spanning = {entity_id: zones for entity_id, zones in shared.items() if len(zones) > 1}

    if config.heating_layout is HeatingLayout.PER_ZONE:
        # Een gedeeld apparaat is op zichzelf geen bewijs van een gesloten
        # systeem. Een gezoneerde cv werkt juist met EEN ketel en kleppen per
        # zone, en een kamer met een eigen airco plus de gasverwarming als
        # reserve is ook gewoon gezoneerd - die kan zichzelf verwarmen.
        #
        # Het gaat mis wanneer kamers uitsluitend op hetzelfde apparaat
        # aangewezen zijn: dan is er niets meer om per kamer te regelen, en
        # verwarmt aanzetten voor de een de ander mee.
        #
        # A shared appliance is no proof of a closed system by itself. A zoned
        # boiler system works precisely with ONE boiler and valves per zone, and
        # a room with its own air conditioner plus the gas heating as a stand-in
        # is zoned too - it can heat itself.
        #
        # It goes wrong when rooms depend on the same appliance and nothing
        # else: then there is nothing left to settle per room, and switching it
        # on for one warms the other along with it.
        for entity_id, zone_ids in sorted(spanning.items()):
            stranded = sorted(
                zone_id
                for zone_id in zone_ids
                if (candidate := config.zone(zone_id)) is not None
                and not [
                    source
                    for source in candidate.sources
                    if heats(source) and source.entity_id != entity_id
                ]
            )
            if len(stranded) > 1:
                return [
                    Problem(
                        "layout_zoned_with_shared_source",
                        (
                            f"heating is set to per zone, but {entity_id} is the only "
                            f"heat source of {len(stranded)} zones"
                        ),
                        entity=entity_id,
                        count=str(len(stranded)),
                        zones=", ".join(stranded),
                    )
                ]
        return []

    if config.heating_layout is HeatingLayout.CENTRAL and not spanning:
        return [
            Problem(
                "layout_central_without_shared_source",
                "heating is set to central, but no heat source is shared between zones",
                count=str(len(config.zones)),
            )
        ]

    return []


def timing_problems(config: DirectorConfig) -> list[Problem]:
    """Return a complaint about switch timings on a circuit that never switches.

    Een buitenunit die verwarmen en koelen tegelijk aankan wisselt nooit van
    taak, dus een omschakelpauze en een minimale looptijd voor die wissel doen
    daar niets. Ze staan er dan wel, en dan ga je ervan uit dat ze werken.

    De kortcyclustijd en de capaciteitsgrens blijven wél gelden; die gaan over
    losse units en niet over de taak van het circuit.

    An outdoor unit that can heat and cool at once never switches duty, so a
    switch pause and a minimum run before that switch do nothing there. They
    still sit in the settings, and then you assume they work.

    The short-cycle time and the capacity limit do still apply; those are about
    individual units rather than about the circuit's duty.
    """
    return [
        Problem(
            "switch_timings_without_a_switch",
            f"circuit {circuit.circuit_id} can run both duties at once, so its switch pause "
            "and minimum run before switching never apply",
            circuit=circuit.name or circuit.circuit_id,
        )
        for circuit in config.circuits
        if circuit.simultaneous_heat_cool
        and (circuit.family_switch_delay or circuit.min_family_switch_interval)
    ]
