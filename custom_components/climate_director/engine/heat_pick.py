"""Welke bron nu de zone mag verwarmen, op kosten: de voorkeur van de bronkeuze.

Which source may heat the zone now, on cost: the preference of the source
selection.

Alleen beslislogica, zonder Home Assistant. De koppelingslaag leest de prijzen,
rekent met `heat_costs` en geeft hier de uitkomst plus wat er vorige ronde gold;
terug komt één voorkeur voor het hele huis, die als `WorldState.heat_pick` bij
`sources.select()` aankomt. Elke twijfel geeft `None`: dan beslist het
buitenvenster van de bron, zoals het altijd deed.

Decision logic only, with no Home Assistant. The binding layer reads the prices,
works them out with `heat_costs` and hands the outcome here together with what
held last round; one preference for the whole house comes back, which reaches
`sources.select()` as `WorldState.heat_pick`. Any doubt gives `None`: the
source's outdoor window then decides, as it always did.
"""

from __future__ import annotations

from dataclasses import dataclass

from .cost import cheapest
from .energy import ELECTRIC, GAS, EnergySettings, HeatCosts

OFF = "off"
NO_OUTDOOR = "no_outdoor"
COLD_LIMIT = "cold_limit"
COST = "cost"
UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class HeatPick:
    """The preferred heating source for the house, and why."""

    preferred: str | None
    reason: str


def pick_heat_source(
    settings: EnergySettings,
    costs: HeatCosts,
    outdoor: float | None,
    holding: HeatPick | None = None,
    hysteresis: float = 0.0,
) -> HeatPick:
    """Return which source should heat now.

    Onder de koudegrens verwarmt altijd gas, wat de prijs ook is: daar is de COP
    van de airco niet te meten en niet te vertrouwen. Terug naar elektrisch kan
    pas als het één dode band boven de koudegrens is, anders klappert de keuze
    mee met elke trilling van de thermometer. Boven de koudegrens wint de
    goedkoopste bron, en de bron die nu draait houdt de zone tot de ander
    `switch_margin` procent goedkoper is. Een onbekende buitentemperatuur of
    onbekende kosten geven geen voorkeur.

    Below the cold limit gas always heats, whatever the price: there the air
    conditioner's COP can be neither measured nor trusted. Going back to
    electric has to wait until it is one dead band above the cold limit, or the
    choice rattles with every tremor of the thermometer. Above the cold limit
    the cheapest source wins, and the source that runs now keeps the zone until
    the other is `switch_margin` percent cheaper. An unknown outdoor temperature
    or unknown costs give no preference.
    """
    if not settings.cost_control:
        return HeatPick(None, OFF)
    if outdoor is None:
        return HeatPick(None, NO_OUTDOOR)
    limit = settings.cold_limit
    if limit is not None:
        held_by_cold = holding is not None and holding.reason == COLD_LIMIT
        if outdoor < limit + (hysteresis if held_by_cold else 0.0):
            return HeatPick(GAS, COLD_LIMIT)
    held = holding.preferred if holding is not None and holding.reason == COST else None
    winner = cheapest(
        {GAS: costs.gas, ELECTRIC: costs.electric},
        holding=held,
        margin=settings.switch_margin / 100,
    )
    if winner is None:
        return HeatPick(None, UNKNOWN)
    return HeatPick(winner, COST)
