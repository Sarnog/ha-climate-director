"""Vraagbepaling: welke taak heeft deze zone nodig.

Demand: which duty this zone needs.

Aan- en uitschakelen gebeurt op twee verschillende temperaturen. De breedte
daartussen is de dode band. Met een band van nul valt het aan- en uitpunt samen
en gaat een zone pendelen op precies die waarde - een fout die met de hand
geschreven automatiseringen vrijwel altijd ergens maken.

Switching on and switching off happen at two different temperatures. The width
between them is the dead band. With a band of zero the on and off points
coincide and a zone chatters on exactly that value - a mistake hand-written
automations nearly always make somewhere.
"""

from __future__ import annotations

from dataclasses import dataclass

from .families import ModeFamily
from .models import ModeSettings, Zone
from .plan import Reason
from .world import WorldState


@dataclass(frozen=True, slots=True)
class Demand:
    """The duty a zone needs, with the cause when it needs none."""

    family: ModeFamily
    reason: Reason
    deviation: float = 0.0
    """How far the indoor temperature sits past the switch-on point."""


def evaluate(zone: Zone, world: WorldState, running: ModeFamily) -> Demand:
    """Return the duty `zone` needs, given the duty it is `running` now.

    `running` is what makes the dead band work: a duty already under way keeps
    going until the far edge of the band, while a duty not running yet has to
    reach the near edge before it may start.
    """
    indoor = world.indoor(zone.zone_id)
    if indoor is None:
        return Demand(ModeFamily.NEUTRAL, Reason.NO_INDOOR_TEMPERATURE)

    heat = _candidate(zone, world, ModeFamily.HEAT, indoor, running)
    cool = _candidate(zone, world, ModeFamily.COOL, indoor, running)

    wanted = [demand for demand in (heat, cool) if demand.family is not ModeFamily.NEUTRAL]
    if not wanted:
        # Both duties declined. Report the more informative refusal rather than
        # a fixed one, so "the season forbids cooling" does not get hidden
        # behind "heating is not configured".
        return _best_refusal(heat, cool)
    if len(wanted) == 1:
        return wanted[0]

    # Heating and cooling both asking at once means the two switch-on points
    # overlap - a misconfiguration. Keeping whatever already runs stops the
    # zone from oscillating between them; otherwise the larger deviation wins.
    for demand in wanted:
        if demand.family is running:
            return demand
    return max(wanted, key=lambda demand: demand.deviation)


def _candidate(
    zone: Zone,
    world: WorldState,
    family: ModeFamily,
    indoor: float,
    running: ModeFamily,
) -> Demand:
    """Return whether `family` wants to run in this zone, and why not if it does not."""
    settings = zone.settings_for(family)
    if settings is None:
        return Demand(ModeFamily.NEUTRAL, Reason.MODE_NOT_CONFIGURED)
    if not settings.allowed_in(world.season):
        return Demand(ModeFamily.NEUTRAL, Reason.SEASON_BLOCKS_MODE)
    if not settings.outdoor.contains(world.outdoor_temperature):
        return Demand(ModeFamily.NEUTRAL, Reason.OUTDOOR_OUTSIDE_WINDOW)

    running_now = running is family
    threshold = _threshold(settings, family, running_now)

    # The switch-on point counts as reached, the switch-off point as passed. If
    # both were inclusive, a zero-width band would never let a duty stop at all.
    if family is ModeFamily.HEAT:
        needed = indoor < threshold if running_now else indoor <= threshold
        deviation = threshold - indoor
    else:
        needed = indoor > threshold if running_now else indoor >= threshold
        deviation = indoor - threshold

    if not needed:
        return Demand(ModeFamily.NEUTRAL, Reason.SATISFIED)
    return Demand(family, Reason.REGULATING, max(deviation, 0.0))


def _threshold(settings: ModeSettings, family: ModeFamily, running: bool) -> float:
    """Return the temperature this duty switches on or off at.

    While the duty runs the far edge of the dead band applies, so it keeps
    going past its switch-on point instead of stopping the moment it reaches it.
    """
    if not running:
        return settings.start_at
    band = abs(settings.hysteresis)
    return settings.start_at + band if family is ModeFamily.HEAT else settings.start_at - band


def _best_refusal(heat: Demand, cool: Demand) -> Demand:
    """Return the more specific of two refusals.

    `MODE_NOT_CONFIGURED` says nothing a user can act on, so any other cause
    outranks it; between two real causes the heating one is reported, since a
    cold house is the complaint people chase first.
    """
    if heat.reason is Reason.MODE_NOT_CONFIGURED:
        return cool
    if cool.reason is Reason.MODE_NOT_CONFIGURED:
        return heat
    return heat
