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

from .families import ModeFamily, preferred_mode
from .models import Source, Zone
from .world import WorldState


def select(
    zone: Zone,
    family: ModeFamily,
    world: WorldState,
    serving: str | None = None,
    margin: float = 0.0,
) -> Source | None:
    """Return the source that should deliver `family` in `zone`.

    Returns `None` when the zone has no source able to deliver that duty at
    this outdoor temperature, or when every candidate is unavailable.

    `serving` is de bron die deze zone vorige ronde werkelijk leverde, en
    `margin` de dode band op de buitentemperatuur. Ligt die bron net buiten zijn
    venster maar binnen de band, dan houdt hij de zone - anders trekt een
    buitentemperatuur die rond de omslag schommelt de ketel en de warmtepomp
    heen en weer. Ligt hij gewoon in zijn venster, dan telt de voorkeur weer als
    altijd: een uitwijking naar een tweede keus hoort terug te schuiven zodra de
    eerste keus er weer is.

    `serving` is the source that really delivered this zone last round, and
    `margin` the dead band on the outdoor temperature. If that source sits just
    outside its window but inside the band, it holds the zone - otherwise an
    outdoor temperature hovering around the changeover drags the boiler and the
    heat pump back and forth. If it sits plainly inside its window, preference
    counts as ever: a fallback to a second choice should move back the moment
    the first choice returns.
    """
    eligible = [source for source in zone.sources if _eligible(source, family, world)]
    held = _held(zone, family, world, serving, margin, eligible)
    if held is not None:
        return held
    if not eligible:
        return None
    return min(eligible, key=lambda source: (source.priority, source.source_id))


def _held(
    zone: Zone,
    family: ModeFamily,
    world: WorldState,
    serving: str | None,
    margin: float,
    eligible: list[Source],
) -> Source | None:
    """Return the running source the dead band keeps in place, if there is one.

    Alleen de bron die het vorige plan werkelijk leverde, alleen als hij buiten
    zijn venster ligt maar binnen de band, en alleen als hij verder gewoon kan.
    Staat hij binnen zijn venster, dan is er niets vast te houden en beslist de
    voorkeur.

    Only the source the previous plan really delivered, only when it sits
    outside its window but inside the band, and only when it can otherwise
    still run. Inside its window there is nothing to hold on to and preference
    decides.
    """
    if serving is None or not margin:
        return None
    source = next((item for item in zone.sources if item.source_id == serving), None)
    if source is None or source in eligible:
        return None
    if not _reachable(source, family, world):
        return None
    return source if source.outdoor.contains(world.outdoor_temperature, margin) else None


def passed_over(
    zone: Zone,
    family: ModeFamily,
    world: WorldState,
    serving: str | None = None,
    margin: float = 0.0,
) -> tuple[str, ...]:
    """Return the preferred sources this duty had to skip because they are unreachable.

    Valt de gasketel weg, dan neemt de airco het over - dat regelt `select()` al,
    want een onbereikbaar apparaat is geen kandidaat. Alleen: van buiten zie je
    dat niet. De kamer komt op temperatuur, alles lijkt goed, en pas op de
    energierekening merk je dat er wekenlang elektrisch verwarmd is.

    Deze functie noemt wat er overgeslagen is: bronnen die op geschiktheid en
    buitentemperatuur wél aan de beurt waren, maar niet te bereiken zijn, en die
    voorrang hebben op wat er nu draait. Wat niet gekozen werd omdat een ander
    apparaat gewoon beter past, staat er dus niet bij - dat is geen storing.

    If the gas boiler drops out the air conditioner takes over - `select()`
    already arranges that, since an unreachable appliance is no candidate. Only:
    from the outside you cannot see it. The room reaches temperature, all looks
    well, and you notice on the energy bill that it has been heating
    electrically for weeks.

    This function names what was skipped: sources that on suitability and
    outdoor temperature were up next, but cannot be reached, and that outrank
    what is running now. What was not chosen because another appliance simply
    fits better is therefore absent - that is no fault.
    """
    chosen = select(zone, family, world, serving, margin)
    if chosen is None:
        return ()
    rank = (chosen.priority, chosen.source_id)
    return tuple(
        source.source_id
        for source in sorted(zone.sources, key=lambda item: (item.priority, item.source_id))
        if (source.priority, source.source_id) < rank
        and _suitable(source, family, world)
        and not world.climate(source.entity_id).available
    )


def _suitable(source: Source, family: ModeFamily, world: WorldState) -> bool:
    """Return whether a source fits this duty, leaving reachability aside."""
    return (
        source.autostart
        and source.supports(family)
        and source.outdoor.contains(world.outdoor_temperature)
    )


def _reachable(source: Source, family: ModeFamily, world: WorldState) -> bool:
    """Return whether a source could serve this duty, leaving its window aside."""
    # Een handbediende bron is nooit een antwoord op een vraag. Hem hier toch
    # meetellen zou de zone een aanspraak op het circuit geven die hij nooit
    # verzilvert, en daarmee een kamer met minder voorrang laten winnen zonder
    # dat er iets gaat draaien.
    #
    # A manual source is never an answer to a demand. Counting it here would
    # give the zone a claim on the circuit it never cashes in, letting a room
    # with less claim win while nothing actually runs.
    if not source.autostart:
        return False
    if not source.supports(family):
        return False
    state = world.climate(source.entity_id)
    # De rol zegt wat de installatie wil, het apparaat wat het kan. Een bron
    # met rol HEAT_COOL op een apparaat dat alleen `heat` en `off` kent, krijgt
    # geen `cool`-commando - die call zou toch maar mislukken. Onbekend krijgt
    # het voordeel van de twijfel, precies zoals `ClimateState.supports` het
    # regelt.
    #
    # The role says what the installation wants, the appliance what it can. A
    # source with role HEAT_COOL on an appliance knowing only `heat` and `off`
    # gets no `cool` command - that call would fail anyway. Unknown gets the
    # benefit of the doubt, exactly as `ClimateState.supports` arranges it.
    return state.available and state.supports(preferred_mode(family))


def _eligible(source: Source, family: ModeFamily, world: WorldState) -> bool:
    """Return whether a source can serve this duty under current conditions."""
    if not _reachable(source, family, world):
        return False
    return source.outdoor.contains(world.outdoor_temperature)
