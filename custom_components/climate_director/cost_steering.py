"""De kostenvoorkeur: prijzen lezen en de voorkeur voor dit moment bepalen.

The cost preference: reading the prices and settling the preference for this
moment.

De koppelingslaag leest alleen de entiteiten; het rekenen en kiezen staat in
`engine/energy.py` en `engine/heat_pick.py`. Wat hier uitkomt landt als
`WorldState.heat_pick`, en `sources.select()` leest het daar. Staat kostenbesturing
uit, dan is de voorkeur `None` en doet de installatie precies wat ze zonder deze
module deed.

The binding layer only reads the entities; the arithmetic and the choosing live in
`engine/energy.py` and `engine/heat_pick.py`. What comes out lands as
`WorldState.heat_pick`, and `sources.select()` reads it there. With cost control
off the preference is `None` and the installation does exactly what it did
without this module.
"""

from __future__ import annotations

from dataclasses import replace

from homeassistant.core import HomeAssistant

from .coordinator_surface import CoordinatorSurface
from .engine import WorldState
from .engine.energy import EnergySettings, HeatCosts, heat_costs
from .engine.heat_pick import pick_heat_source


def read_number(hass: HomeAssistant, entity_id: str) -> float | None:
    """Return the number an entity reports, or `None` when it reports none."""
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None:
        return None
    try:
        value = float(state.state)
    except ValueError:
        return None
    # `nan` en `inf` lezen als getal maar zijn er geen. / `nan` and `inf` parse as
    # a number but are none.
    return value if value == value and abs(value) != float("inf") else None


def costs_now(hass: HomeAssistant, settings: EnergySettings, outdoor: float | None) -> HeatCosts:
    """Return the cost of a kWh of heat at this moment's readings."""
    return heat_costs(
        settings,
        read_number(hass, settings.grid_price_sensor),
        read_number(hass, settings.feed_in_sensor),
        read_number(hass, settings.surplus_sensor),
        outdoor,
        read_number(hass, settings.gas_price_sensor),
    )


def with_heat_pick(coordinator: CoordinatorSurface, world: WorldState) -> WorldState:
    """Return the snapshot with the cost preference filled in."""
    settings = coordinator.config.energy
    pick = pick_heat_source(
        settings,
        costs_now(coordinator.hass, settings, world.outdoor_temperature),
        world.outdoor_temperature,
        coordinator.round.heat_pick,
        coordinator.config.outdoor_hysteresis,
    )
    coordinator.round.heat_pick = pick
    return replace(world, heat_pick=pick.preferred)


def tracked_prices(coordinator: CoordinatorSurface) -> set[str]:
    """Return the price entities whose change should start a fresh round.

    Alleen met kostenbesturing aan: zonder die schakelaar beslist niets op een
    prijs, en elke prijsverandering van een dynamisch contract zou voor niets een
    ronde starten.

    Only with cost control on: without that switch nothing is decided on a price,
    and every price change of a dynamic contract would start a round for nothing.
    """
    settings = coordinator.config.energy
    return set(settings.entities()) if settings.cost_control else set()
