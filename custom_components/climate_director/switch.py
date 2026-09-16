"""Bedieningsschakelaars: hoofdschakelaar, vakantiemodus en overrides.

Control switches: master, holiday mode, guest mode and per-zone overrides.

Deze schakelaars zijn de bedieningstoestand van de installatie, geen
configuratie. Ze herstellen zichzelf na een herstart en schrijven hun stand
terug naar de coordinator, die ze in de volgende momentopname meeneemt.

These switches are the installation's control state, not its configuration.
They restore themselves after a restart and write their state back to the
coordinator, which carries it into the next snapshot.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .coordinator import ClimateDirectorCoordinator, ClimateDirectorEntry
from .engine import DirectorConfig
from .entity import ClimateDirectorEntity

#: Alles komt uit één coordinator; er valt niets te serialiseren.
#: Everything comes from one coordinator; there is nothing to serialise.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: ClimateDirectorEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the master, holiday and guest switches, and one override per zone."""
    coordinator = entry.runtime_data
    entities: list[SwitchEntity] = [
        MasterSwitch(coordinator),
        HolidaySwitch(coordinator),
        GuestSwitch(coordinator),
    ]
    entities.extend(
        ZoneOverrideSwitch(coordinator, zone.zone_id) for zone in coordinator.config.zones
    )
    entities.extend(
        OpeningBypassSwitch(coordinator, opening.opening_id)
        for opening in coordinator.config.openings
        if opening.opening_id
    )
    async_add_entities(entities)


def wanted_entity_keys(config: DirectorConfig) -> set[str]:
    """Return every unique-id key this platform will create for `config`."""
    return {
        "master",
        "holiday",
        "guest",
        *(f"zone_{zone.zone_id}_override" for zone in config.zones),
        *(
            f"opening_{opening.opening_id}_bypass"
            for opening in config.openings
            if opening.opening_id
        ),
    }


class _DirectorSwitch(ClimateDirectorEntity, SwitchEntity, RestoreEntity):
    """A switch whose state lives in the coordinator and survives a restart."""

    _default_on = False

    def __init__(self, coordinator: ClimateDirectorCoordinator, key: str) -> None:
        """Set up the switch."""
        super().__init__(coordinator, key)
        self._is_on = self._default_on

    async def async_added_to_hass(self) -> None:
        """Restore the saved state before the first decision is made."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in ("on", "off"):
            self._is_on = last.state == "on"
        self._push()

    @property
    def is_on(self) -> bool:
        """Return the switch state."""
        return self._is_on

    async def async_turn_on(self, **_kwargs: Any) -> None:
        """Turn the switch on and decide again."""
        await self._set(True)

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Turn the switch off and decide again."""
        await self._set(False)

    async def _set(self, value: bool) -> None:
        self._is_on = value
        self._push()
        self.async_write_ha_state()
        self.coordinator.async_request_evaluation()

    def _push(self) -> None:
        """Write this switch's state into the coordinator."""
        raise NotImplementedError

    def _handle_coordinator_update(self) -> None:
        """Ignore coordinator updates: this switch is an input, not an output."""


class MasterSwitch(_DirectorSwitch):
    """Turns the whole director on and off."""

    _attr_translation_key = "master"
    _attr_entity_category = None
    _attr_icon = "mdi:home-thermometer"
    _default_on = True

    def __init__(self, coordinator: ClimateDirectorCoordinator) -> None:
        """Set up the master switch."""
        super().__init__(coordinator, "master")

    def _push(self) -> None:
        self.coordinator.master_enabled = self._is_on


class HolidaySwitch(_DirectorSwitch):
    """Holiday mode: every day counts as a Saturday, or as its own schedule."""

    _attr_translation_key = "holiday"
    _attr_entity_category = None
    _attr_icon = "mdi:palm-tree"

    def __init__(self, coordinator: ClimateDirectorCoordinator) -> None:
        """Set up the holiday switch."""
        super().__init__(coordinator, "holiday")

    def _push(self) -> None:
        self.coordinator.holiday_mode = self._is_on


class GuestSwitch(_DirectorSwitch):
    """Guest mode: keeps the house running while the residents are away."""

    _attr_translation_key = "guest"
    _attr_entity_category = None
    _attr_icon = "mdi:account-multiple-plus"

    def __init__(self, coordinator: ClimateDirectorCoordinator) -> None:
        """Set up the guest switch."""
        super().__init__(coordinator, "guest")

    def _push(self) -> None:
        self.coordinator.guest_mode = self._is_on


class ZoneOverrideSwitch(_DirectorSwitch):
    """Hands one zone back to the user until it is turned off again."""

    _attr_translation_key = "zone_override"
    _attr_entity_category = None
    _attr_icon = "mdi:hand-back-right"

    def __init__(self, coordinator: ClimateDirectorCoordinator, zone_id: str) -> None:
        """Set up the override switch for one zone."""
        self._zone_id = zone_id
        super().__init__(coordinator, f"zone_{zone_id}_override")
        zone = coordinator.config.zone(zone_id)
        self._attr_translation_placeholders = {"zone": zone.name if zone else zone_id}

    def _push(self) -> None:
        """Zet de stand en laat de rest direct volgen (R34-7).

        De schakelaar schrijft alleen `zone_overrides`; de coordinator laat de
        looptijd van een handmatig uitgezette zone stil vervallen en werkt zijn
        luisteraars bij, zodat de eindtijdsensor meteen `unknown` toont in plaats
        van pas bij de volgende beslisronde (de debouncer wacht een seconde).

        The switch only writes `zone_overrides`; the coordinator lets the duration
        of a hand-switched-off zone lapse silently and updates its listeners, so
        the end-time sensor shows `unknown` at once instead of only at the next
        decision round (the debouncer waits a second).
        """
        self.coordinator.zone_overrides[self._zone_id] = self._is_on
        self.coordinator.async_publish_override_state()

    def _handle_coordinator_update(self) -> None:
        """Follow the coordinator, and write any lapse away when it lets go.

        De overdracht is van de gebruiker en blijft staan tot hij hem zelf
        uitzet; de coordinator gooit `zone_overrides` niet meer leeg. Deze
        koppeling blijft toch staan, want ze is de enige die klopt: zou de
        schakelaar haar eigen stand houden terwijl de coordinator er anders over
        denkt, dan stond ze aan terwijl de zone allang weer meedraait - en erger:
        een herstart herstelt die `on` terug de coordinator in, zodat een
        overdracht herleeft die er niet meer was.

        The handover belongs to the user and holds until they turn it off
        themselves; the coordinator no longer empties `zone_overrides`. This
        binding stays all the same, since it is the only one that is right: were
        the switch to keep its own state while the coordinator thought
        otherwise, it would read on while the zone has long since rejoined - and
        worse: a restart restores that `on` back into the coordinator, reviving a
        handover that was gone.

        Geschreven wordt er alleen bij een **echte** verandering (R34-7). Sinds de
        override zijn stand direct publiceert komt deze tak ook langs op het
        moment dat de schakelaar zelf net schreef, en dan is er niets veranderd:
        `async_write_ha_state` zou daar een `state_reported` van maken en geen
        `state_changed`, dus dat is ruis. Zo blijft er precies één schrijfactie
        per echte overgang over.

        This writes only on a **real** change (R34-7). Since the override
        publishes its state at once, this branch also comes past the moment the
        switch itself just wrote, and then nothing has changed: `async_write_ha_state`
        would make a `state_reported` of that and no `state_changed`, so it is
        noise. That leaves exactly one write per real transition.
        """
        enabled = self.coordinator.zone_overrides.get(self._zone_id, False)
        if enabled != self._is_on:
            self._is_on = enabled
            self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return the switch state, following the coordinator when it lets go."""
        return self.coordinator.zone_overrides.get(self._zone_id, False)


def _opening_label(coordinator: ClimateDirectorCoordinator, opening_id: str) -> str:
    """Return the readable label for one opening's bypass switch.

    Een legacy-opening heeft geen naam en heet in de opslag naar zijn
    `opening_id`, dat de `entity_id` van de sensor is. Dan leest de schakelaar
    als "Overbrugging binary_sensor.achterdeur". Valt er geen naam te kiezen,
    dan is de friendly name van de sensor zelf de eerstvolgende leesbare
    aanduiding - die verandert mee als iemand de sensor hernoemt, en dat is
    precies wat je wilt voor een opening zonder eigen naam.

    A legacy opening has no name and is called after its `opening_id` in
    storage, which is the sensor's `entity_id`. The switch then reads as
    "Bypass binary_sensor.achterdeur". When there is no name to pick, the
    sensor's own friendly name is the next readable label - it follows along
    when somebody renames the sensor, which is exactly what you want for an
    opening without a name of its own.
    """
    opening = next(
        (item for item in coordinator.config.openings if item.opening_id == opening_id),
        None,
    )
    if opening is None:
        return opening_id
    if opening.name != opening.opening_id:
        return opening.name
    state = coordinator.hass.states.get(opening.entity_id)
    return state.name if state is not None else opening.name


class OpeningBypassSwitch(_DirectorSwitch):
    """Bridges one opening: while on, that opening counts nowhere (anchor 8)."""

    _attr_translation_key = "opening_bypass"
    _attr_entity_category = None
    _attr_icon = "mdi:window-open-variant"

    def __init__(self, coordinator: ClimateDirectorCoordinator, opening_id: str) -> None:
        """Set up the bypass switch for one opening."""
        self._opening_id = opening_id
        super().__init__(coordinator, f"opening_{opening_id}_bypass")
        self._attr_translation_placeholders = {"opening": _opening_label(coordinator, opening_id)}

    def _push(self) -> None:
        self.coordinator.opening_bypasses[self._opening_id] = self._is_on

    def _handle_coordinator_update(self) -> None:
        """Follow the coordinator, the sensor's name, and the opening's state.

        De overbrugging blijft staan tot iemand hem zelf terugzet; de
        coordinator gooit `opening_bypasses` niet leeg. Deze koppeling staat er
        toch, om dezelfde reden als bij de overrideschakelaar: zou de
        schakelaar zijn eigen stand houden terwijl de coordinator er anders over
        denkt, dan stond hij aan terwijl de opening allang weer meetelt - en
        erger: een herstart herstelt die `on` terug de coordinator in.

        Sinds R28-1 ververst deze ronde ook de naam, want die werd eerder alleen
        bij het opzetten gelezen en bleef dan staan. In productie zijn de vijf
        openingen Zigbee-contacten die bij een herstart net zo goed ná de
        integratie kunnen verschijnen, en een sensor hernoemen komt ook voor;
        zonder deze verversing heette de schakelaar in beide gevallen naar de
        kale `entity_id`. Geen herlaad nodig: de coordinator geeft elke
        beslisronde een update, en een toestandswijziging van de sensor vraagt
        er zelf een aan.

        The bypass holds until someone turns it off themselves; the coordinator
        does not empty `opening_bypasses`. This binding stays all the same, for
        the same reason as the override switch: were the switch to keep its own
        state while the coordinator thought otherwise, it would read on while
        the opening has long since counted again - and worse: a restart restores
        that `on` back into the coordinator.

        Since R28-1 this round refreshes the name too, which used to be read at
        setup only and then stayed put. In production the five openings are
        Zigbee contacts that can just as well appear *after* the integration on
        a restart, and renaming a sensor happens too; without this refresh the
        switch read as the bare `entity_id` in both cases. No reload needed: the
        coordinator hands out an update every decision round, and a state change
        of the sensor asks for one itself.
        """
        self._is_on = self.coordinator.opening_bypasses.get(self._opening_id, False)
        self._refresh_label()
        self.async_write_ha_state()

    def _refresh_label(self) -> None:
        """Follow the sensor's friendly name without a reload (R28-1).

        Gemeten op deze Home Assistant-versie: `translation_placeholders` staat
        net als `name` wél in HA's `CACHED_PROPERTIES_WITH_ATTR_`, en de
        `_attr_`-setter maakt de cache van `translation_placeholders` ook
        ongeldig. Alleen: `name` is een eigen `cached_property` die de vertaling
        met de placeholders opmaakt en zijn uitkomst apart bewaart, dus die
        cache raakt de placeholder-setter niet. Een nieuwe placeholder alleen
        laat de oude naam dus staan, en daarom gooit de schakelaar de gecachte
        naam er zelf uit zodra het label werkelijk verandert - niet elke ronde,
        want dat zou de state onnodig opnieuw publiceren.

        Measured on this Home Assistant version: `translation_placeholders`
        sits in HA's `CACHED_PROPERTIES_WITH_ATTR_` just like `name`, and the
        `_attr_` setter does invalidate the cache of `translation_placeholders`.
        Only: `name` is a `cached_property` of its own that renders the
        translation with the placeholders and stores its result separately, so
        the placeholder setter does not touch that cache. A new placeholder
        alone therefore leaves the old name in place, and that is why the switch
        drops the cached name itself as soon as the label really changes - not
        every round, since that would publish the state again for nothing.
        """
        label = _opening_label(self.coordinator, self._opening_id)
        if self._attr_translation_placeholders.get("opening") == label:
            return
        self._attr_translation_placeholders = {"opening": label}
        self.__dict__.pop("name", None)

    @property
    def is_on(self) -> bool:
        """Return the switch state, following the coordinator when it lets go."""
        return self.coordinator.opening_bypasses.get(self._opening_id, False)
