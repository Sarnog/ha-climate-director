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


def running_family(zone: Zone, world: WorldState) -> ModeFamily:
    """Return the duty this zone is running now, for the dead band to build on."""
    for source in zone.sources:
        family = world.climate(source.entity_id).family
        if family in (ModeFamily.HEAT, ModeFamily.COOL):
            return family
    return ModeFamily.NEUTRAL


def wanted_target(zone: Zone, world: WorldState) -> tuple[Demand, float | None]:
    """Return what this room needs and the temperature it would aim for.

    Los van de poorten, en dat is precies waarvoor het bedoeld is: bij een
    geweigerd vooruit-verzoek wil je in het bericht kunnen zetten waar de kamer
    naartoe zou gaan als de poort openging.

    De reden komt mee en niet alleen de taak, want zonder streeftemperatuur zijn
    er twee heel verschillende antwoorden: de kamer ligt al goed (`SATISFIED`),
    of er valt hier niets te doen omdat het seizoen of de configuratie het
    verbiedt. Alleen het eerste mag je een gebruiker vertellen als "het is al
    goed".

    Independent of the gates, which is exactly what it is for: on a refused
    pre-conditioning request you want to be able to put in the message where the
    room would head if the gate opened.

    The reason comes along rather than just the duty, since without a target
    there are two very different answers: the room is already right
    (`SATISFIED`), or there is nothing to do here because the season or the
    configuration forbids it. Only the first may be told to a user as "it is
    already right".
    """
    demand = evaluate(zone, world, running_family(zone, world))
    settings = zone.settings_for(demand.family)
    return demand, settings.target if settings else None


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
    # De buitengrens van een zone beantwoordt de vraag "mag er bij dit weer
    # uberhaupt geregeld worden" - een zuinigheidsregel die ervan uitgaat dat
    # er iemand thuis is. Vraagt iemand met de hand om vooruit verwarmen, dan
    # is dat antwoord al gegeven: hij wil het, en hij komt eraan. Zonder deze
    # uitzondering valt er een gat tussen de twee grenzen, waar verwarmen niet
    # meer mag en koelen nog niet - en daar doet een verzoek dan niets.
    #
    # De grens per BRON blijft wel gelden; die kiest het apparaat. Net als het
    # seizoen, de dode band en alles daarna.
    #
    # A zone's outdoor window answers "may anything be regulated in this
    # weather at all" - a thrift rule that assumes somebody is home. If
    # somebody asks for pre-conditioning by hand, that answer is already given:
    # they want it, and they are on their way. Without this exception a gap
    # opens between the two windows, where heating is no longer allowed and
    # cooling not yet - and a request does nothing there.
    #
    # The window per SOURCE does still apply; that one picks the appliance. As
    # do the season, the dead band and everything after them.
    if not world.preconditioning(zone.zone_id) and not settings.outdoor.contains(
        world.outdoor_temperature
    ):
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
