"""De controles op bronnen en generatoren.

The checks on sources and generators.

Dubbele bron-id's, het buitenvenster en de gebieden van een bron, de families, de
generatoren en de exclusieve groepen.

Doubled source ids, the outdoor window and the areas of a source, the families, the
generators and the exclusive groups.
"""

from __future__ import annotations

import math
from collections.abc import Iterator

from .candidates import group_entities
from .families import ModeFamily
from .models import DirectorConfig, ModeSettings, Source, Zone
from .problem import Problem
from .takeover import areas
from .validation_shared import duplicates


def rule_duplicate_source_ids(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for every source id that occurs more than once.

    Een bron-id is de sleutel waarmee uitsluitende groepen naar bronnen
    verwijzen; een dubbel id maakt die verwijzing dubbelzinnig.

    A source id is the key exclusive groups use to point at sources; a doubled
    id makes that reference ambiguous.
    """
    for source_id in duplicates([source.source_id for _, source in config.sources()]):
        yield Problem("duplicate_source_id", f"duplicate source id: {source_id}", source=source_id)


def rule_source_outdoor_window(source: Source, outdoor_known: bool) -> Iterator[Problem]:
    """Yield a complaint when a source's outdoor window can never be met.

    Een leeg venster laat de bron nooit draaien; een begrensd venster zonder
    buitensensor kan nooit voldaan worden. Beide zijn van buiten niet te
    onderscheiden van "de director doet niets".

    An empty window never lets the source run; a bounded window without an
    outdoor sensor can never be satisfied. Both look like "the director does
    nothing" from the outside.
    """
    if source.outdoor.empty:
        yield Problem(
            "source_window_admits_nothing",
            f"source {source.source_id} has an outdoor window that admits nothing",
            source=source.source_id,
        )
    elif not outdoor_known and not source.outdoor.unbounded:
        yield Problem(
            "source_outdoor_without_sensor",
            f"source {source.source_id} is limited by outdoor temperature, "
            "but no outdoor sensor is set",
            source=source.source_id,
        )


def rule_source_covered_zones(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint when a source's area names a zone that does not exist.

    Anker 12: `covers_zones` noemt zones, en een zone die niet bestaat kan dit
    apparaat nooit meebedienen. Stil overslaan zou de overname kleiner maken dan
    de gebruiker denkt en dat is precies het soort verschil dat je nergens ziet -
    dezelfde klacht die een gedeelde warmtebron met een onbekende zone al krijgt.

    Anchor 12: `covers_zones` names zones, and a zone that does not exist can
    never be served along by this appliance. Skipping it quietly would make the
    takeover smaller than the user thinks, and that is exactly the kind of
    difference you never see - the same complaint a shared heat source naming an
    unknown zone already gets.
    """
    known = {zone.zone_id for zone in config.zones}
    for _, source in config.sources():
        for zone_id in source.covers_zones:
            if zone_id not in known:
                yield Problem(
                    "source_unknown_covered_zone",
                    f"source {source.source_id} names unknown zone {zone_id} in its area",
                    source=source.source_id,
                    zone=zone_id,
                )


def rule_family_hysteresis(
    zone: Zone, family: ModeFamily, settings: ModeSettings
) -> Iterator[Problem]:
    """Yield a complaint when a duty's hysteresis is not a usable number.

    Een niet-eindige hysterese glipt langs de `< 0`-controle, en een negatieve
    is een dode band de verkeerde kant op; beide maken het gedrag van de zone
    onvoorspelbaar.

    A non-finite hysteresis slips past the `< 0` check, and a negative one is
    a dead band the wrong way round; both make the zone's behaviour
    unpredictable.
    """
    if not math.isfinite(settings.hysteresis):
        yield Problem(
            "nonfinite_hysteresis",
            f"zone {zone.zone_id} has a non-finite {family.value} hysteresis",
            zone=zone.zone_id,
            mode=family.value,
        )
    elif settings.hysteresis < 0:
        yield Problem(
            "zone_negative_hysteresis",
            f"zone {zone.zone_id} has a negative {family.value} hysteresis",
            zone=zone.zone_id,
            mode=family.value,
        )


def rule_family_outdoor_window(
    zone: Zone, family: ModeFamily, settings: ModeSettings, outdoor_known: bool
) -> Iterator[Problem]:
    """Yield a complaint when a duty's outdoor window can never be met.

    Een leeg venster laat de taak nooit draaien; een begrensd venster zonder
    buitensensor kan nooit voldaan worden. Beide zijn het stille niets waar
    deze hele controlelijst voor bestaat.

    An empty window never lets the duty run; a bounded window without an
    outdoor sensor can never be satisfied. Both are the silent nothing this
    whole problem list exists for.
    """
    if settings.outdoor.empty:
        yield Problem(
            "zone_window_admits_nothing",
            f"zone {zone.zone_id} has a {family.value} outdoor window that admits nothing",
            zone=zone.zone_id,
            mode=family.value,
        )
    elif not outdoor_known and not settings.outdoor.unbounded:
        yield Problem(
            "zone_outdoor_without_sensor",
            f"zone {zone.zone_id} limits {family.value} by outdoor temperature, "
            "but no outdoor sensor is set",
            zone=zone.zone_id,
            mode=family.value,
        )


def rule_generators(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for every generator that doubles or names wrongly.

    Een gedeelde warmtebron die ook als zone-bron bestaat krijgt twee
    opdrachtgevers; een generator die een onbekende zone noemt kan die zone
    nooit bedienen.

    A shared heat source that also exists as a zone source gets two masters; a
    generator naming an unknown zone can never serve that zone.
    """
    zone_ids = [zone.zone_id for zone in config.zones]
    source_entities = {source.entity_id for _, source in config.sources()}
    for generator in config.generators:
        if generator.entity_id in source_entities:
            yield Problem(
                "generator_also_a_source",
                f"generator {generator.generator_id} uses climate entity "
                f"{generator.entity_id}, which is already a zone's source",
                generator=generator.generator_id,
                entity=generator.entity_id,
            )
        for zone_id in generator.zone_ids:
            if zone_id not in set(zone_ids):
                yield Problem(
                    "generator_unknown_zone",
                    f"generator {generator.generator_id} names unknown zone {zone_id}",
                    generator=generator.generator_id,
                    zone=zone_id,
                )


def rule_exclusive_groups(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for every exclusive group naming an unknown source.

    Een groep die naar een onbekende bron wijst kan zijn uitsluiting nooit
    toepassen; de instelling staat er dan wel, maar doet niets.

    A group pointing at an unknown source can never apply its exclusion; the
    setting is there, but does nothing.
    """
    known_sources = {source.source_id for _, source in config.sources()}
    for group in config.exclusive_groups:
        for source_id in sorted(group - known_sources):
            yield Problem(
                "exclusive_group_unknown_source",
                f"exclusive group names unknown source {source_id}",
                source=source_id,
            )


def rule_area_source_without_group(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for a hand-operated source in a boiler's area that no group holds.

    `area_clash()` kijkt naar verzoeken van de director, en een bron waarvan
    `autostart` uit staat vraagt nooit iets: hij wordt alleen door een
    uitsluitende groep of door een handbediend-conflict in bedwang gehouden. Staat
    zo'n bron in het gebied van een apparaat (`covers_zones`) en in geen enkele
    uitsluitende groep met dat apparaat, dan kan hij naast de ketel blijven draaien
    zonder dat de director ingrijpt. De controle meldt dat, zodat de gebruiker de
    twee in één groep zet; het gedrag van de engine verandert er niet door.

    `area_clash()` looks at requests of the director, and a source whose
    `autostart` is off never asks for anything: it is held in check only by an
    exclusive group or by the hand-operated conflict. If such a source stands in
    the area of an appliance (`covers_zones`) and in no exclusive group with that
    appliance, it can keep running beside the boiler without the director stepping
    in. This check reports that, so the user puts the two in one group; the
    engine's behaviour does not change because of it.
    """
    for boiler, area in sorted(areas(config).items()):
        if len(area) < 2:
            continue
        grouped = frozenset().union(
            *(
                members
                for members in (group_entities(config, group) for group in config.exclusive_groups)
                if boiler in members
            )
        )
        for zone, source in config.sources():
            if (
                source.autostart
                or source.entity_id == boiler
                or zone.zone_id not in area
                or source.entity_id in grouped
            ):
                continue
            yield Problem(
                "area_source_without_group",
                f"source {source.source_id} does not start automatically and stands in the "
                f"area of {boiler}, but in no exclusive group with it",
                source=source.source_id,
                boiler=boiler,
            )
