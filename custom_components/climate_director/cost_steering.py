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
from .engine import DirectorConfig, ModeFamily, SourceEnergy, WorldState
from .engine.energy import EnergySettings, HeatCosts, heat_costs
from .engine.heat_pick import OFF, HeatPick, pick_heat_source


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
    costs = costs_now(coordinator.hass, settings, world.outdoor_temperature)
    hysteresis = coordinator.config.outdoor_hysteresis

    def pick_for(limit_settings: EnergySettings, holding: HeatPick | None) -> HeatPick:
        return pick_heat_source(
            limit_settings, costs, world.outdoor_temperature, holding, hysteresis, world.season
        )

    pick = pick_for(settings, coordinator.round.heat_pick)
    coordinator.round.heat_pick = pick
    # Per zone alleen waar het afwijkt: een zone die de kostenregeling niet
    # volgt, of een eigen koudegrens heeft. / Per zone only where it differs: a
    # zone that does not follow the cost control, or has a cold limit of its own.
    own: dict[str, HeatPick] = {}
    for zone in coordinator.config.zones:
        if not zone.cost_control:
            own[zone.zone_id] = HeatPick(None, OFF)
        elif zone.cold_limit is not None:
            holding = coordinator.round.zone_heat_picks.get(zone.zone_id)
            own[zone.zone_id] = pick_for(replace(settings, cold_limit=zone.cold_limit), holding)
    coordinator.round.zone_heat_picks = own
    return replace(
        world,
        heat_pick=pick.preferred,
        heat_picks={zone_id: item.preferred for zone_id, item in own.items()},
    )


def heating_kinds(hass: HomeAssistant, config: DirectorConfig) -> frozenset[str]:
    """Return the energy kinds that are really heating at this moment.

    Een bron telt als verwarmend als het apparaat `hvac_action` `heating` meldt;
    meldt het apparaat geen `hvac_action`, dan telt de stand `heat`. Een airco die
    op `heat` staat maar stilstaat telt dus niet mee. Zo komen de uren overeen met
    het verbruik van gas en stroom, en niet met wat er alleen ingesteld staat.

    A source counts as heating when the appliance reports `hvac_action` `heating`;
    when it reports no `hvac_action`, the mode `heat` counts. An air conditioner
    that is in `heat` but idle therefore does not count. That way the hours match
    the use of gas and power, not just what is set.
    """
    kinds: set[str] = set()
    for _, source in config.sources():
        if source.energy is SourceEnergy.NONE or not source.supports(ModeFamily.HEAT):
            continue
        state = hass.states.get(source.entity_id)
        if state is None:
            continue
        action = state.attributes.get("hvac_action")
        if (action == "heating") if action is not None else (state.state == "heat"):
            kinds.add(source.energy.value)
    return frozenset(kinds)


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
