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

    Een lege entiteit of een gasprijs van nul betekent: niet ingesteld. Een
    installatie zonder gasprijs of zonder netprijs heeft geen vergelijking, en
    de sensor ervoor wordt dan niet aangemaakt.

    An empty entity or a gas price of zero means: not set. An installation
    without a gas price or without a grid price has no comparison, and the
    sensor for it is then not created.
    """

    grid_price_sensor: str = ""
    """Entiteit met de stroomprijs per kWh nu. / Entity with the power price per kWh now."""

    feed_in_sensor: str = ""
    """Entiteit met de terugleverprijs per kWh nu; leeg gebruikt altijd de netprijs.

    Entity with the feed-in price per kWh now; empty always uses the grid price.
    """

    surplus_sensor: str = ""
    """Entiteit met het zonne-overschot in kW (positief is overschot); leeg is geen.

    Entity with the solar surplus in kW (positive is surplus); empty is none.
    """

    gas_price: float = 0.0
    """Gasprijs per m³; nul is niet ingesteld. / Gas price per m³; zero is not set."""

    kwh_per_m3: float = 9.77
    """Calorische waarde in kWh per m³. / Calorific value in kWh per m³."""

    boiler_efficiency: float = 0.9
    """Rendement van de ketel, 0 tot 1,2. / The boiler's efficiency, 0 to 1.2."""

    cop_curve: str = ""
    """De COP-curve als tekst `buitentemperatuur:COP`; zie `parse_cop_curve`.

    The COP curve as text `outdoor temperature:COP`; see `parse_cop_curve`.
    """

    @property
    def configured(self) -> bool:
        """Return whether there is enough here to compare at all."""
        return self.gas_price > 0 and bool(self.grid_price_sensor) and bool(self.cop_curve.strip())

    def entities(self) -> tuple[str, ...]:
        """Return the entities this comparison reads, without empty ones."""
        return tuple(
            entity
            for entity in (self.grid_price_sensor, self.feed_in_sensor, self.surplus_sensor)
            if entity
        )


def parse_cop_curve(text: str) -> CopCurve | None:
    """Return the curve a text such as `-5:2.8, 7:3.8, 15:4.5` describes.

    Elk punt is `buitentemperatuur:COP`; komma's of puntkomma's scheiden de
    punten. Een tekst met een punt dat niet leest, met een COP van nul of lager,
    met twee keer dezelfde temperatuur of zonder punten geeft `None`: een curve
    waar je half op kunt rekenen is er geen.

    Each point is `outdoor temperature:COP`; commas or semicolons separate the
    points. A text with a point that does not read, with a COP of zero or less,
    with the same temperature twice or without points gives `None`: a curve you
    can only half count on is none.
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
        if cop <= 0:
            return None
        points.append((outdoor, cop))
    if not points or len({outdoor for outdoor, _ in points}) != len(points):
        return None
    return CopCurve(points=tuple(sorted(points)))


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
) -> HeatCosts:
    """Return the cost of a kWh of heat from gas and from electricity now.

    De stroomprijs is de netprijs, of de terugleverprijs bij een zonneoverschot.
    Wat niet te lezen is, geeft `None` voor die bron, en is er geen enkele bron
    met kosten dan is er ook geen goedkoopste.

    The power price is the grid price, or the feed-in price during a solar
    surplus. What cannot be read gives `None` for that source, and with no
    source that has a cost there is no cheapest either.
    """
    price = surplus_price(grid_price, feed_in_price, surplus_kw)
    curve = parse_cop_curve(settings.cop_curve)
    cop = curve.cop_at(outdoor) if curve is not None else None
    gas = gas_cost(settings.gas_price or None, settings.kwh_per_m3, settings.boiler_efficiency)
    electric = electric_cost(price, cop)
    return HeatCosts(
        gas=gas,
        electric=electric,
        cop=cop,
        electricity_price=price,
        cheapest=cheapest({GAS: gas, ELECTRIC: electric}),
    )
