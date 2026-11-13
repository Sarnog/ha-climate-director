"""De energie-instellingen en wat een kWh warmte nu kost.

The energy settings and what a kWh of heat costs right now.

Dit is de schaduwkant van het kostenrekenwerk in `cost.py`: de instellingen van
de installatie en één functie die er, met de lezingen van dit moment, de kosten
van gas en van een elektrische bron uit haalt. Er hangt geen besluit aan: de
bronkeuze kent deze module niet, dus hij verandert niets aan wat de ketel en de
airco's doen. Hij voedt alleen een sensor waarop je kunt zien wat de goedkoopste
bron nu zou zijn.

This is the shadow side of the cost arithmetic in `cost.py`: the installation's
settings and one function that, with this moment's readings, works the cost of
gas and of an electric source out of them. No decision hangs on it: the source
selection does not know this module, so it changes nothing about what the boiler
and the air conditioners do. It only feeds a sensor on which you can see what
the cheapest source would be right now.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .cost import CopCurve, cheapest, electric_cost, gas_cost, surplus_price

GAS = "gas"
"""Sleutel van de gasketel in de vergelijking. / Key of the boiler in the comparison."""

ELECTRIC = "electric"
"""Sleutel van de elektrische bron in de vergelijking. / Key of the electric source."""


@dataclass(frozen=True, slots=True)
class EnergySettings:
    """Welke prijzen en rendementen de kostenvergelijking gebruikt.

    Which prices and efficiencies the cost comparison uses.

    Een lege entiteit of een prijs van nul betekent: niet ingesteld. Elke prijs is
    een vast getal of een entiteit; de entiteit wint zolang die een getal geeft,
    de vaste prijs is wat overblijft als dat niet zo is. Een installatie zonder
    gasprijs of zonder stroomprijs heeft geen vergelijking, en de sensor ervoor
    wordt dan niet aangemaakt.

    An empty entity or a price of zero means: not set. Every price can be a fixed
    number or an entity; the entity wins while it reads a number, the fixed price
    is what is left when it does not. An installation without a gas price or
    without a power price has no comparison, and the sensor for it is then not
    created.
    """

    grid_price_sensor: str = ""
    """Entiteit met de stroomprijs per kWh nu. / Entity with the power price per kWh now."""

    grid_price: float = 0.0
    """Vaste stroomprijs per kWh; telt als de sensor leeg is of niets geeft. Nul is niet ingesteld.

    Fixed power price per kWh; counts when the sensor is empty or reads nothing.
    Zero is not set.
    """

    feed_in_sensor: str = ""
    """Entiteit met de terugleverprijs per kWh nu; leeg gebruikt altijd de netprijs.

    Entity with the feed-in price per kWh now; empty always uses the grid price.
    """

    feed_in_price: float = 0.0
    """Vaste terugleverprijs per kWh, als er geen sensor is. Nul is niet ingesteld.

    Fixed feed-in price per kWh, for when there is no sensor. Zero is not set.
    """

    surplus_sensor: str = ""
    """Entiteit met het zonne-overschot in kW (positief is overschot); leeg is geen.

    Entity with the solar surplus in kW (positive is surplus); empty is none.
    """

    gas_price_sensor: str = ""
    """Entiteit met de gasprijs per m³ nu. / Entity with the gas price per m³ now."""

    gas_price: float = 0.0
    """Vaste gasprijs per m³; telt als de sensor leeg is of niets geeft. Nul is niet ingesteld.

    Fixed gas price per m³; counts when the sensor is empty or reads nothing. Zero is not set.
    """

    kwh_per_m3: float = 9.77
    """Calorische waarde in kWh per m³. / Calorific value in kWh per m³."""

    boiler_efficiency: float = 0.9
    """Rendement van de ketel, 0 tot 1,2. / The boiler's efficiency, 0 to 1.2."""

    cost_control: bool = False
    """Of de goedkoopste bron ook echt kiest welk apparaat verwarmt; uit is alleen kijken.

    Whether the cheapest source really picks which appliance heats; off is watching only.
    """

    season_lock: bool = False
    """In de zomer kiest hij altijd elektrisch; gas blijft alleen terugval.

    In summer it always picks electric; gas stays only as the fallback.
    """

    cold_limit: float | None = 2.0
    """Onder deze buitentemperatuur verwarmt altijd gas; leeg is geen koudegrens.

    Below this outdoor temperature gas always heats; empty is no cold limit.
    """

    switch_margin: float = 10.0
    """Hoeveel procent goedkoper de andere bron moet zijn om over te schakelen.

    How many percent cheaper the other source must be before the heating switches.
    """

    cop_curve: str = ""
    """De COP-curve als tekst `buitentemperatuur:COP`; zie `parse_cop_curve`.

    The COP curve as text `outdoor temperature:COP`; see `parse_cop_curve`.
    """

    @property
    def configured(self) -> bool:
        """Return whether there is enough here to compare at all."""
        has_gas = self.gas_price > 0 or bool(self.gas_price_sensor)
        has_grid = self.grid_price > 0 or bool(self.grid_price_sensor)
        return has_gas and has_grid and bool(self.cop_curve.strip())

    def entities(self) -> tuple[str, ...]:
        """Return the entities this comparison reads, without empty ones."""
        return tuple(
            entity
            for entity in (
                self.grid_price_sensor,
                self.feed_in_sensor,
                self.surplus_sensor,
                self.gas_price_sensor,
            )
            if entity
        )


def parse_cop_curve(text: str) -> CopCurve | None:
    """Return the curve a text such as `-5:2.8, 7:3.8, 15:4.5` describes.

    Elk punt is `buitentemperatuur:COP`; komma's of puntkomma's scheiden de
    punten. Een tekst geeft `None` bij een punt dat niet leest, een COP van nul
    of lager, een getal dat niet eindig is (`inf`, `nan`), tweemaal dezelfde
    temperatuur, of geen punten: een curve waar je half op kunt rekenen is er
    geen.

    Each point is `outdoor temperature:COP`; commas or semicolons separate the
    points. A text gives `None` for a point that does not read, a COP of zero or
    less, a number that is not finite (`inf`, `nan`), the same temperature
    twice, or no points: a curve you can only half count on is none.
    """
    points: list[tuple[float, float]] = []
    for part in text.replace(";", ",").split(","):
        if not part.strip():
            continue
        pieces = part.split(":")
        if len(pieces) != 2:
            return None
        try:
            outdoor = float(pieces[0].strip().replace("−", "-"))
            cop = float(pieces[1].strip())
        except ValueError:
            return None
        if not (math.isfinite(outdoor) and math.isfinite(cop)) or cop <= 0:
            return None
        points.append((outdoor, cop))
    if not points or len({outdoor for outdoor, _ in points}) != len(points):
        return None
    return CopCurve(points=tuple(sorted(points)))


def _entity_or_fixed(reading: float | None, fixed: float) -> float | None:
    """Return the entity's reading, else the fixed price, else `None` (zero is not set)."""
    if reading is not None:
        return reading
    return fixed if fixed > 0 else None


@dataclass(frozen=True, slots=True)
class HeatCosts:
    """What one kWh of heat costs now, per source, and which is cheapest."""

    gas: float | None
    electric: float | None
    cop: float | None
    electricity_price: float | None
    cheapest: str | None


def heat_costs(
    settings: EnergySettings,
    grid_price: float | None,
    feed_in_price: float | None,
    surplus_kw: float | None,
    outdoor: float | None,
    gas_reading: float | None = None,
) -> HeatCosts:
    """Return the cost of a kWh of heat from gas and from electricity now.

    De stroomprijs is de netprijs, of de terugleverprijs bij een zonneoverschot.
    Wat niet te lezen is, geeft `None` voor die bron, en is er geen enkele bron
    met kosten dan is er ook geen goedkoopste.

    The power price is the grid price, or the feed-in price during a solar
    surplus. What cannot be read gives `None` for that source, and with no
    source that has a cost there is no cheapest either.
    """
    # Staat er een terugleversensor ingesteld maar geeft die niets terwijl er
    # overschot is, dan is de prijs van die stroom onbekend: de netprijs is dan
    # niet wat je misloopt. Alleen een lege instelling gebruikt altijd de netprijs.
    #
    # With a feed-in sensor set that gives nothing while there is a surplus, the
    # price of that power is unknown: the grid price is then not what you give up.
    # Only an empty setting always uses the grid price.
    grid_price = _entity_or_fixed(grid_price, settings.grid_price)
    feed_in_price = _entity_or_fixed(feed_in_price, settings.feed_in_price)
    surplus = surplus_kw is not None and surplus_kw > 0
    if surplus and (settings.feed_in_sensor or settings.feed_in_price) and feed_in_price is None:
        price = None
    else:
        price = surplus_price(grid_price, feed_in_price, surplus_kw)
    curve = parse_cop_curve(settings.cop_curve)
    cop = curve.cop_at(outdoor) if curve is not None else None
    gas = gas_cost(
        _entity_or_fixed(gas_reading, settings.gas_price),
        settings.kwh_per_m3,
        settings.boiler_efficiency,
    )
    electric = electric_cost(price, cop)
    return HeatCosts(
        gas=gas,
        electric=electric,
        cop=cop,
        electricity_price=price,
        cheapest=cheapest({GAS: gas, ELECTRIC: electric}),
    )


BREAK_EVEN = "crossover"
"""Gas en elektrisch wisselen bij een temperatuur. / Gas and electric swap at a temperature."""

ELECTRIC_ALWAYS = "electric_always"
"""Elektrisch is overal even goedkoop of goedkoper. / Electric is everywhere as cheap or cheaper."""

GAS_ALWAYS = "gas_always"
"""Gas is over de hele curve goedkoper. / Gas is cheaper across the curve."""


@dataclass(frozen=True, slots=True)
class BreakEven:
    """Below which outdoor temperature gas beats electricity at these prices."""

    verdict: str | None
    temperature: float | None


def break_even(
    settings: EnergySettings,
    electricity_price: float | None,
    gas_reading: float | None = None,
) -> BreakEven:
    """Return the outdoor temperature at which gas and electricity cost the same.

    Het is de omslagtemperatuur voor deze prijzen: eronder is gas goedkoper,
    erboven de airco. Bij vaste prijzen is dit één getal dat je zo kunt lezen;
    bij een dynamisch contract beweegt het mee met de prijs. Is een van de twee
    kosten onbekend, of de curve onleesbaar, dan is er geen antwoord (`None`).

    It is the changeover temperature for these prices: below it gas is cheaper,
    above it the air conditioner. With fixed prices this is one number you can
    read at once; with a dynamic contract it moves with the price. If either
    cost is unknown, or the curve unreadable, there is no answer (`None`).
    """
    curve = parse_cop_curve(settings.cop_curve)
    gas = gas_cost(
        _entity_or_fixed(gas_reading, settings.gas_price),
        settings.kwh_per_m3,
        settings.boiler_efficiency,
    )
    if curve is None or gas is None or gas <= 0 or electricity_price is None:
        return BreakEven(None, None)
    needed = electricity_price / gas
    if needed <= 0:
        return BreakEven(ELECTRIC_ALWAYS, None)
    cops = [cop for _, cop in curve.points]
    if min(cops) >= needed:
        return BreakEven(ELECTRIC_ALWAYS, None)
    if max(cops) < needed:
        return BreakEven(GAS_ALWAYS, None)
    return BreakEven(BREAK_EVEN, curve.first_temperature_with(needed))
