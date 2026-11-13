"""Wat een kWh warmte kost: gas tegenover een elektrische bron.

What a kWh of heat costs: gas against an electric source.

Alleen rekenwerk, zonder Home Assistant en zonder toestand. De bronkeuze leest
deze module niet zelf: `energy.py` en `heat_pick.py` maken er een voorkeur van,
en die komt als `WorldState.heat_pick` bij `sources.py`.

Pure arithmetic, with no Home Assistant and no state. The source selection does
not read this module itself: `energy.py` and `heat_pick.py` turn it into a
preference, which reaches `sources.py` as `WorldState.heat_pick`.

Alles wat onleesbaar of onbruikbaar is geeft `None`, geen uitzondering en geen
gok: een caller die geen kosten heeft, houdt de huidige bronvolgorde.

Anything unreadable or unusable gives `None`, no exception and no guess: a caller
without a cost keeps the current source order.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class PricePoint:
    """One price valid over `[start, end)`, in currency per kWh."""

    start: datetime
    end: datetime
    value: float


@dataclass(frozen=True, slots=True)
class CopCurve:
    """The COP of an electric source as a function of the outdoor temperature.

    Punten van `(buitentemperatuur in °C, COP)`. Tussen twee punten loopt de
    curve recht; buiten het eerste en het laatste punt blijft hij vlak op de
    waarde van dat punt, want een curve die verder omlaag of omhoog doorloopt
    is een gok.

    Points of `(outdoor temperature in °C, COP)`. The curve runs straight
    between two points; beyond the first and the last point it stays flat at
    that point's value, since a curve that carries on further down or up is a
    guess.
    """

    points: tuple[tuple[float, float], ...]

    def cop_at(self, outdoor: float | None) -> float | None:
        """Return the COP at this outdoor temperature, or `None` when unusable."""
        usable = sorted(point for point in self.points if point[1] > 0)
        if outdoor is None or not usable:
            return None
        if outdoor <= usable[0][0]:
            return usable[0][1]
        for (low_t, low_cop), (high_t, high_cop) in zip(usable, usable[1:], strict=False):
            if outdoor <= high_t:
                share = (outdoor - low_t) / (high_t - low_t)
                return low_cop + share * (high_cop - low_cop)
        return usable[-1][1]

    def first_temperature_with(self, cop: float) -> float | None:
        """Return the lowest outdoor temperature at which the COP reaches `cop`.

        Loopt de curve al op of boven `cop` bij het koudste punt, of haalt hij
        het nergens, dan is er geen kruising en geeft dit `None`. Bij een curve
        die niet stijgt telt de eerste kruising van onder naar boven.

        If the curve already sits at or above `cop` at its coldest point, or
        never reaches it, there is no crossing and this gives `None`. On a curve
        that does not rise, the first crossing from below counts.
        """
        usable = sorted(point for point in self.points if point[1] > 0)
        if not usable or usable[0][1] >= cop:
            return None
        for (low_t, low_cop), (high_t, high_cop) in zip(usable, usable[1:], strict=False):
            if high_cop >= cop > low_cop:
                share = (cop - low_cop) / (high_cop - low_cop)
                return low_t + share * (high_t - low_t)
        return None


def gas_cost(price_per_m3: float | None, kwh_per_m3: float, efficiency: float) -> float | None:
    """Return the cost of one kWh of heat from gas.

    `price_per_m3` is de gasprijs per m³, `kwh_per_m3` de calorische waarde en
    `efficiency` het rendement van de ketel (0 tot 1). Een prijs onder nul, een
    waarde of rendement van nul of lager, en een rendement boven 1,2 zijn geen
    bruikbare invoer.

    `price_per_m3` is the gas price per m³, `kwh_per_m3` the calorific value and
    `efficiency` the boiler's efficiency (0 to 1). A price below zero, a value or
    efficiency of zero or less, and an efficiency above 1.2 are not usable input.
    """
    if price_per_m3 is None or price_per_m3 < 0 or kwh_per_m3 <= 0:
        return None
    if efficiency <= 0 or efficiency > MAX_EFFICIENCY:
        return None
    return price_per_m3 / (kwh_per_m3 * efficiency)


MAX_EFFICIENCY = 1.2
"""Upper bound for a boiler efficiency; a condensing boiler is rated up to about 1.1."""


def electric_cost(price_per_kwh: float | None, cop: float | None) -> float | None:
    """Return the cost of one kWh of heat from an electric source with this COP."""
    if price_per_kwh is None or cop is None or cop <= 0:
        return None
    return price_per_kwh / cop


def surplus_price(
    grid_price: float | None,
    feed_in_price: float | None,
    surplus_kw: float | None,
) -> float | None:
    """Return the price of the electricity one more kWh of heat would use.

    Bij een overschot aan zonnestroom kost een extra kWh wat het teruglevert
    zou opbrengen (`feed_in_price`): zelf opgewekte stroom is niet gratis, de
    waarde is wat je misloopt. Zonder overschot kost hij de netprijs. Een
    onbekend overschot telt als geen overschot.

    With a surplus of solar power one more kWh costs what feeding it back would
    earn (`feed_in_price`): self-generated power is not free, its value is what
    you give up. Without a surplus it costs the grid price. An unknown surplus
    counts as none.
    """
    if surplus_kw is not None and surplus_kw > 0 and feed_in_price is not None:
        return feed_in_price
    return grid_price


def window_average(
    prices: Sequence[PricePoint],
    start: datetime,
    horizon: timedelta,
) -> float | None:
    """Return the time-weighted average price over `[start, start + horizon)`.

    Alleen het deel van de periode dat de lijst dekt telt mee. Dekt de lijst het
    venster niet geheel, dan is het gemiddelde alleen over het gedekte deel
    bekend en geeft de functie `None`: een gat in de prijslijst is een reden om
    terug te vallen, niet om te gokken. Prijzen die elkaar overlappen tellen
    dubbel en geven ook `None`.

    Only the part of the period the list covers counts. If the list does not
    cover the whole window the average is only known over the covered part, and
    the function returns `None`: a gap in the price list is a reason to fall
    back, not to guess. Prices that overlap would count twice and also give
    `None`.
    """
    end = start + horizon
    if horizon <= timedelta(0):
        return None
    inside = sorted(
        (point for point in prices if min(point.end, end) > max(point.start, start)),
        key=lambda point: point.start,
    )
    total = 0.0
    covered = timedelta(0)
    reached: datetime | None = None
    for point in inside:
        # Overlappende prijzen tellen dubbel en zijn dus geen betrouwbare lijst.
        # Overlapping prices would count twice, so the list is not reliable.
        if reached is not None and point.start < reached:
            return None
        overlap = min(point.end, end) - max(point.start, start)
        total += point.value * overlap.total_seconds()
        covered += overlap
        reached = point.end
    if covered < horizon:
        return None
    return total / horizon.total_seconds()


def cheapest(
    costs: dict[str, float | None],
    holding: str | None = None,
    margin: float = 0.0,
) -> str | None:
    """Return the id of the source to use, or `None` when no cost is known.

    `holding` is de bron die nu levert. Die houdt de keus tenzij een andere bron
    minstens `margin` (een fractie, 0,15 is 15%) goedkoper is: zonder die rem
    wisselt een keus rond het omslagpunt elk uur. De marge is een fractie van de
    grootte van de kosten van de huidige bron, ook als die negatief zijn. Bij gelijke kosten wint de
    kleinste id, zodat de uitkomst vastligt.

    `holding` is the source that delivers now. It keeps the choice unless
    another source is at least `margin` (a fraction, 0.15 is 15%) cheaper:
    without that brake a choice around the changeover swaps every hour. The
    margin is a fraction of the size of the holder's cost, also when negative. At equal
    cost the smallest id wins, so the outcome is fixed.
    """
    known = {source: cost for source, cost in costs.items() if cost is not None}
    if not known:
        return None
    best = min(known, key=lambda source: (known[source], source))
    held = known.get(holding) if holding is not None else None
    # Een gelijke prijs is geen reden om te wisselen, ook niet zonder marge. De marge
    # rekent met de grootte van de kosten, zodat ze ook bij negatieve kosten remt.
    if held is not None and (known[best] >= held or known[best] > held - margin * abs(held)):
        return holding
    return best
