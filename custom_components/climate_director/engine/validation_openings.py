"""De controles op openingen.

The checks on openings.

Dubbele opening-id's, de openingen, de huisbrede stops, de open stand van een
afdekking en de vastzittijd onder de ingestelde rust.

Doubled opening ids, the openings, the house-wide stops, the open state of a cover
and the stuck time below the configured rest.
"""

from __future__ import annotations

from collections.abc import Iterator

from .models import DirectorConfig
from .problem import Problem
from .validation_shared import duplicates


def rule_duplicate_opening_ids(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for every opening id that occurs more than once.

    Anker 8: een opening draagt een eigen `opening_id`; twee openingen met
    dezelfde id delen de overbruggingsschakelaar, en dan verdwijnt er één stil
    uit het entiteitenregister. Oudere opslag kent die ids niet; ze
    worden bij het lezen afgeleid (`serialise.opening_ids`); een opgeslagen
    dubbel id laat die lezer staan, dus deze controle ziet hem.

    Anchor 8: an opening carries its own `opening_id`; two openings sharing one
    share the bypass switch, and then one disappears quietly from the entity
    registry. Older storage has no such ids; they are
    derived on read (`serialise.opening_ids`); a stored duplicate is left
    alone by that reader, so this check sees it.
    """
    ids = [opening.opening_id for opening in config.openings if opening.opening_id]
    for opening_id in duplicates(ids):
        yield Problem(
            "duplicate_opening_id", f"duplicate opening id: {opening_id}", opening=opening_id
        )


def rule_openings(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for every opening that names or times wrongly.

    Een opening die een onbekende zone noemt kan nooit iets stilzetten; een
    negatieve vertraging is een timer die al verstreken is vóór hij begint.

    An opening naming an unknown zone can never stop anything; a negative
    delay is a timer already expired before it starts.
    """
    known_zones = {zone.zone_id for zone in config.zones}
    for opening in config.openings:
        for zone_id in opening.zone_ids:
            if zone_id not in known_zones:
                yield Problem(
                    "opening_unknown_zone",
                    f"opening {opening.entity_id} names unknown zone {zone_id}",
                    opening=opening.entity_id,
                    zone=zone_id,
                )
        if opening.delay.total_seconds() < 0:
            yield Problem(
                "opening_negative_delay",
                f"opening {opening.entity_id} has a negative delay",
                opening=opening.entity_id,
            )


def rule_house_wide_stops(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for every house-wide stop that can never stop.

    Een apparaat dat huisbreed stil hoort te vallen terwijl er niets is dat
    het ooit stilzet, is een instelling die er staat en niets doet. Beide
    helften zijn los te vergeten: de openingen kunnen ontbreken, en het
    apparaat kan bij geen enkele zone of gedeelde warmtebron horen - dan
    stuurt de director er nooit iets heen en valt er dus ook niets stil te
    zetten.

    An appliance meant to stop house-wide while nothing can ever stop it is a
    setting that sits there doing nothing. Both halves can be forgotten
    separately: the openings may be missing, and the appliance may belong to
    no zone and no shared heat source - the director then never sends it
    anything, so there is nothing to stop either.
    """
    if config.house_wide_openings and not config.openings:
        for entity_id in config.house_wide_openings:
            yield Problem(
                "house_wide_without_openings",
                f"appliance {entity_id} is set to stop while an opening stands open, "
                "but the installation has no openings at all",
                entity=entity_id,
            )

    steered = {source.entity_id for _, source in config.sources()} | {
        generator.entity_id for generator in config.generators
    }
    for entity_id in config.house_wide_openings:
        if entity_id not in steered:
            yield Problem(
                "house_wide_unmanaged",
                f"appliance {entity_id} is set to stop while an opening stands open, but no "
                "zone and no shared heat source uses it, so the director never steers it",
                entity=entity_id,
            )


def rule_cover_open_state(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for a cover opening that never reports open.

    Een `cover` meldt `open`, geen `on`. Staat de openingsstand op `on`, dan
    telt het dakraam nooit als open en stookt de installatie er dwars doorheen.

    A `cover` reports `open`, not `on`. With the opening state on `on`, the
    skylight never counts as open and the installation heats straight through
    it.
    """
    for opening in config.openings:
        if opening.entity_id.startswith("cover.") and opening.open_state != "open":
            yield Problem(
                "cover_opening_without_open_state",
                f"opening {opening.entity_id} is a cover but its open state is "
                f"{opening.open_state!r}, so it never counts as open",
                opening=opening.name or opening.entity_id,
                open_state=opening.open_state,
            )


def rule_stuck_below_configured_rest(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint when the stuck time is shorter than a configured rest.

    De vastloopmelder staat op de wachtredenen, en een ingestelde circuit- of
    bronrust staat daar ook op. Is de vastlooptijd korter, dan meldt de sensor
    een apparaat als vastgelopen terwijl het netjes zijn rust neemt.

    The stuck notice sits on the waiting reasons, and a configured circuit or
    source rest sits there too. With a shorter stuck time the sensor reports an
    appliance as stuck while it is simply taking its rest.
    """
    stuck = config.stuck_after.total_seconds()
    if stuck <= 0:
        return
    for circuit in config.circuits:
        for label, rest in (
            ("minimum cycle time", circuit.min_cycle_time),
            ("minimum switch interval", circuit.min_family_switch_interval),
        ):
            if rest.total_seconds() > stuck:
                yield Problem(
                    "stuck_after_below_configured_rest",
                    f"the stuck-detection time is below the circuit's {label}",
                    subject=circuit.name or circuit.circuit_id,
                    label=label,
                    rest=str(int(rest.total_seconds())),
                    stuck_after=str(int(stuck)),
                )
    for _zone, source in config.sources():
        source_rest = source.min_cycle_time
        if source_rest is not None and source_rest.total_seconds() > stuck:
            yield Problem(
                "stuck_after_below_configured_rest",
                "the stuck-detection time is below the source's minimum cycle time",
                subject=source.name or source.entity_id,
                label="minimum cycle time",
                rest=str(int(source_rest.total_seconds())),
                stuck_after=str(int(stuck)),
            )
