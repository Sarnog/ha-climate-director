"""Bronkeuze: welk apparaat levert de gevraagde taak.

Source selection: which appliance delivers the requested duty.

Bronnen worden gekozen op geschiktheid, beschikbaarheid en voorkeur - in die
volgorde. Het buitentemperatuurvenster is wat een gasketel van een warmtepomp
scheidt: half-open vensters `(None, 3.0)` en `(3.0, None)` dekken samen de hele
schaal zonder gat of overlap.

Sources are chosen on suitability, availability and preference - in that order.
The outdoor-temperature window is what separates a gas boiler from a heat pump:
half-open windows `(None, 3.0)` and `(3.0, None)` together cover the whole
scale with neither a gap nor an overlap.
"""

from __future__ import annotations

from .families import ModeFamily
from .models import Source, Zone
from .world import WorldState


def select(zone: Zone, family: ModeFamily, world: WorldState) -> Source | None:
    """Return the source that should deliver `family` in `zone`.

    Returns `None` when the zone has no source able to deliver that duty at
    this outdoor temperature, or when every candidate is unavailable.
    """
    candidates = [source for source in zone.sources if _eligible(source, family, world)]
    if not candidates:
        return None
    return min(candidates, key=lambda source: (source.priority, source.source_id))


def candidates(zone: Zone, family: ModeFamily, world: WorldState) -> tuple[Source, ...]:
    """Return every eligible source for `family`, most preferred first."""
    eligible = [source for source in zone.sources if _eligible(source, family, world)]
    return tuple(sorted(eligible, key=lambda source: (source.priority, source.source_id)))


def _eligible(source: Source, family: ModeFamily, world: WorldState) -> bool:
    """Return whether a source can serve this duty under current conditions."""
    if not source.supports(family):
        return False
    if not source.outdoor.contains(world.outdoor_temperature):
        return False
    return world.climate(source.entity_id).available
