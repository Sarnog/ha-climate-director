"""De knop die een kamer vooruit laat verwarmen of koelen.

The button that warms or cools one room ahead of time.

Vooruit verwarmen bestond al als actie, en dat is precies het probleem: een
actie vind je alleen als je weet dat hij bestaat. Er was nergens iets om op te
drukken. Een knop per zone, met één duur ernaast, maakt er iets van dat je
gewoon op een dashboard zet.

De actie blijft bestaan en kan meer: meerdere zones tegelijk, en een raam
overbruggen. Dat past niet op een knop - een knop heeft geen velden - en het
zijn allebei dingen die je bewust doet, niet in het voorbijgaan.

Pre-conditioning already existed as an action, and that is exactly the problem:
you only find an action if you know it is there. There was nothing to press. One
button per zone, with a single duration beside it, turns it into something you
simply put on a dashboard.

The action stays and can do more: several zones at once, and overriding an open
window. Neither fits on a button - a button has no fields - and both are things
you do deliberately rather than in passing.
"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ClimateDirectorCoordinator, ClimateDirectorEntry
from .entity import ClimateDirectorEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ClimateDirectorEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one pre-conditioning button per zone."""
    coordinator = entry.runtime_data
    async_add_entities(
        ZonePreconditionButton(coordinator, zone.zone_id) for zone in coordinator.config.zones
    )


class ZonePreconditionButton(ClimateDirectorEntity, ButtonEntity):
    """Warms one zone up for somebody on their way home."""

    _attr_translation_key = "zone_precondition"
    _attr_icon = "mdi:home-clock"

    def __init__(self, coordinator: ClimateDirectorCoordinator, zone_id: str) -> None:
        """Set up the button for one zone."""
        super().__init__(coordinator, f"zone_{zone_id}_precondition")
        self._zone_id = zone_id
        zone = coordinator.config.zone(zone_id)
        self._attr_translation_placeholders = {"zone": zone.name if zone else zone_id}

    async def async_press(self) -> None:
        """Start a request for this zone, for the duration standing beside it.

        Er wordt niets bewaard over hoe lang: dat staat in de duurentiteit, en
        die is met de hand of vanuit een automatisering te zetten. Twee plekken
        die hetzelfde getal bijhouden zouden alleen maar uit elkaar lopen.

        Vragen om langer dan de installatie toestaat kort het verzoek in; het
        weigert niet. De bedoeling was duidelijk, alleen het getal klopte niet.

        Nothing is kept here about how long: that lives in the duration entity,
        which can be set by hand or from an automation. Two places holding the
        same number would only drift apart.

        Asking for longer than the installation allows shortens the request
        rather than refusing it. The intent was clear, only the number was
        wrong.
        """
        self.coordinator.async_precondition([self._zone_id], self.coordinator.precondition_minutes)

    def _handle_coordinator_update(self) -> None:
        """Ignore coordinator updates: this button is an input, not an output."""
