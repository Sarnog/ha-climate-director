"""Per zone of hij tegengehouden wordt, en of er ergens iets vastloopt.

Per zone whether it is held back, and whether anything is stuck.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ClimateDirectorCoordinator, ClimateDirectorEntry
from .entity import ClimateDirectorEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ClimateDirectorEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the per-zone sensors, and one stuck sensor for the whole."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = []
    for zone in coordinator.config.zones:
        entities.append(ZoneBlockedSensor(coordinator, zone.zone_id))
        entities.append(ZoneFallbackSensor(coordinator, zone.zone_id))
    entities.append(StuckSensor(coordinator))
    async_add_entities(entities)


class ZoneBlockedSensor(ClimateDirectorEntity, BinarySensorEntity):
    """On when a zone is held back from regulating.

    Twee manieren: het vroeg meer dan het kreeg (bijvoorbeeld een circuitconflict),
    of een dichte poort houdt een zone tegen die wél had willen regelen. Dat
    tweede kijkt naar de dode band: een open raam in een kamer die toch al op
    temperatuur is, is geen blokkade om te melden. De hoofdschakelaar en de
    override tellen nooit als blokkade: dat zijn bewuste ingrepen.

    Two ways: it asked for more than it got (a circuit conflict, say), or a
    shut gate holds back a zone that did want to regulate. That second one
    honours the dead band: an open window in a room that is comfortable anyway
    is no blockage to report. The master switch and the override never count
    as a blockage: those are deliberate acts.
    """

    _attr_translation_key = "zone_blocked"
    _attr_icon = "mdi:hand-back-left"

    def __init__(self, coordinator: ClimateDirectorCoordinator, zone_id: str) -> None:
        """Set up the sensor for one zone."""
        super().__init__(coordinator, f"zone_{zone_id}_blocked")
        self._zone_id = zone_id
        zone = coordinator.config.zone(zone_id)
        self._attr_translation_placeholders = {"zone": zone.name if zone else zone_id}

    @property
    def is_on(self) -> bool | None:
        """Return whether this zone is being held back from regulating."""
        plan = self.coordinator.data
        if plan is None:
            return None
        decision = plan.decision_for(self._zone_id)
        if decision is None:
            return None
        return decision.blocked or decision.held_back

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the cause, the wish, and every gate shut on this zone.

        `reason` is de eerste hindernis; `closed_gates` zijn ze allemaal, en
        `would_want` is wat de temperatuurregeling gewild zou hebben als die
        poorten open stonden. Bij het inrichten scheelt dat een ronde per
        poort: je zet het raam dicht, kijkt weer, en vindt dan pas dat er ook
        niemand thuis is.

        `reason` is the first obstacle; `closed_gates` are all of them, and
        `would_want` is what the temperature regulation would have wanted had
        those gates stood open. While setting up that saves a round per gate:
        you close the window, look again, and only then find that nobody is
        home either.
        """
        plan = self.coordinator.data
        if plan is None:
            return {}
        decision = plan.decision_for(self._zone_id)
        if decision is None:
            return {}
        return {
            "reason": decision.reason.value,
            "closed_gates": [reason.value for reason in decision.closed_gates],
            "would_want": decision.would_want.value,
        }


class ZoneFallbackSensor(ClimateDirectorEntity, BinarySensorEntity):
    """On when a zone runs on a stand-in because its own appliance is unreachable.

    Valt de thermostaat van de gasverwarming weg, dan schuift de director door
    naar de airco: de kamer wordt gewoon warm. Precies daarom is dit nodig. Een
    vangnet dat werkt is een vangnet dat je niet voelt, en dus wekenlang kan
    blijven hangen zonder dat iemand de kapotte thermostaat repareert - je merkt
    het pas op de energierekening.

    Deze sensor maakt het zichtbaar, zodat een eigen automatisering er een
    melding aan kan hangen. Hij zegt niets over of het warm wordt; hij zegt dat
    het anders warm wordt dan bedoeld.

    If the gas thermostat drops out, the director moves on to the air
    conditioner: the room simply gets warm. That is exactly why this is needed.
    A safety net that works is a safety net you do not feel, and so it can stay
    in place for weeks without anybody fixing the broken thermostat - you notice
    on the energy bill.

    This sensor makes it visible, so an automation of your own can hang a
    notification on it. It says nothing about whether the room gets warm; it
    says the room gets warm differently than intended.
    """

    _attr_translation_key = "zone_fallback"
    _attr_icon = "mdi:swap-horizontal"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: ClimateDirectorCoordinator, zone_id: str) -> None:
        """Set up the sensor for one zone."""
        super().__init__(coordinator, f"zone_{zone_id}_fallback")
        self._zone_id = zone_id
        zone = coordinator.config.zone(zone_id)
        self._attr_translation_placeholders = {"zone": zone.name if zone else zone_id}

    @property
    def is_on(self) -> bool | None:
        """Return whether a preferred appliance had to be skipped."""
        plan = self.coordinator.data
        if plan is None:
            return None
        decision = plan.decision_for(self._zone_id)
        return decision.on_fallback if decision else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return which appliance was skipped and which one stepped in."""
        plan = self.coordinator.data
        if plan is None:
            return {}
        decision = plan.decision_for(self._zone_id)
        if decision is None:
            return {}
        return {
            "unreachable": list(decision.passed_over),
            "serving": decision.source_id,
            "zone": self._zone_id,
        }


class StuckSensor(ClimateDirectorEntity, BinarySensorEntity):
    """On when a zone keeps waiting for something that is not coming.

    De andere melders zeggen wat er nu is; deze zegt dat er iets niet meer
    verandert. Een pauze bij het wisselen van taak hoort seconden te duren, dus
    een zone die er een kwartier op staat wacht niet meer - die zit vast. Zo'n
    klem is van buiten niet te onderscheiden van "de director besluit niets",
    en dat is de stilste manier waarop deze integratie kan falen.

    The other sensors say what is; this one says that something has stopped
    changing. A pause when switching duty should last seconds, so a zone sitting
    on one for a quarter of an hour is no longer waiting - it is stuck. From the
    outside such a deadlock is indistinguishable from "the director decides
    nothing", which is the quietest way this integration can fail.
    """

    _attr_translation_key = "stuck"
    _attr_icon = "mdi:progress-alert"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ClimateDirectorCoordinator) -> None:
        """Set up the installation-wide stuck sensor."""
        super().__init__(coordinator, "stuck")

    @property
    def is_on(self) -> bool | None:
        """Return whether anything is stuck or unreadable."""
        if self.coordinator.data is None:
            return None
        return bool(self.coordinator.stuck_zones() or self.coordinator.unusable_entities())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return which zones are stuck, on what, and for how long."""
        stuck = self.coordinator.stuck_zones()
        return {
            "unusable_entities": self.coordinator.unusable_entities(),
            "zones": sorted(stuck),
            "reasons": {zone_id: reason.value for zone_id, reason in sorted(stuck.items())},
            "waiting_seconds": {
                zone_id: round(seconds)
                for zone_id, seconds in sorted(self.coordinator.waiting_seconds().items())
            },
        }
