"""Een echte Home Assistant om de integratie heen, in het geheugen.

A real Home Assistant around the integration, in memory.

`tests/test_ha_layer.py` bouwt de stukjes Home Assistant na die de koppelingslaag
aanraakt. Dat dekt het uitlezen en het schrijven, maar niet wat Home Assistant
zelf doet: een config entry opzetten, de platforms omhoog brengen, entiteiten
aanmaken, acties registreren, en dat alles weer afbreken. Precies daar zit de
laag die bij een gebruiker thuis stukloopt en nergens anders.

Deze module zet daarom een echte `HomeAssistant` op met de integratie als custom
component erin. De klimaatapparaten zijn nagebouwd - `climate.set_hvac_mode` en
`climate.set_temperature` schrijven gewoon de toestand terug - waardoor de lus
rond is: de director stuurt, de apparaten veranderen, en dat leidt tot een
volgende beslissing.

`tests/test_ha_layer.py` rebuilds the pieces of Home Assistant the binding layer
touches. That covers the reading and the writing, but not what Home Assistant
itself does: setting up a config entry, bringing the platforms up, creating
entities, registering actions, and tearing all of it down again. That is exactly
the layer that breaks in somebody's home and nowhere else.

This module therefore stands up a real `HomeAssistant` with the integration in it
as a custom component. The climate appliances are stand-ins -
`climate.set_hvac_mode` and `climate.set_temperature` simply write the state back
- which closes the loop: the director steers, the appliances change, and that
leads to the next decision.
"""

from __future__ import annotations

import asyncio
import atexit
import contextlib
import os
import shutil
import tempfile
from datetime import datetime
from typing import Any

from homeassistant import loader
from homeassistant.config_entries import ConfigEntries, ConfigEntry
from homeassistant.core import CoreState, HomeAssistant, ServiceCall
from homeassistant.helpers import (
    area_registry,
    device_registry,
    entity_registry,
    issue_registry,
    restore_state,
)
from homeassistant.setup import async_setup_component

from custom_components.climate_director.const import (
    CONF_INSTALLATION,
    CONF_SHADOW_MODE,
    DOMAIN,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_own_config_dirs: list[str] = []


def new_config_dir() -> str:
    """Return a fresh Home Assistant config directory with the integration in it.

    Elk huis krijgt zijn eigen map, want `.storage` blijft anders tussen twee
    tests staan en dan bestaat een config entry al voordat hij aangemaakt wordt.
    Wie een herstart wil nabootsen geeft dezelfde map twee keer mee - dan is dat
    juist de bedoeling.

    Every house gets its own directory, since `.storage` would otherwise linger
    between two tests and a config entry would already exist before it was
    created. Whoever wants to mimic a restart passes the same directory twice -
    there that is exactly the point.
    """
    target = tempfile.mkdtemp(prefix="climate_director_live_")
    shutil.copytree(
        os.path.join(REPO, "custom_components"),
        os.path.join(target, "custom_components"),
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    _own_config_dirs.append(target)
    return target


def _remove_own_config_dirs() -> None:
    """Ruim aan het eind van de testrun elke zelfgemaakte map weer op.

    Elk huis kopieert de integratie naar zijn eigen map van ongeveer een
    megabyte, en de suite zet er duizenden op. Zonder deze stap blijven die
    allemaal in de tijdelijke map van het systeem staan - na twee dagen testen
    stonden er 3668, samen ruim drie gigabyte. Opruimen gebeurt pas als het
    proces eindigt, want een test die een herstart nabootst geeft dezelfde map
    een tweede keer mee en heeft hem tot dat moment nodig. Een map die de
    aanroeper zelf meegeeft, blijft staan: die is niet van ons.

    Clean up every self-made directory when the test run ends.

    Every house copies the integration into its own directory of about a
    megabyte, and the suite stands up thousands of them. Without this step they
    all stay behind in the system's temporary directory - after two days of
    testing there were 3668, over three gigabytes together. The cleanup only
    happens once the process ends, since a test mimicking a restart passes the
    same directory a second time and needs it until then. A directory the caller
    supplies itself stays: that one is not ours.
    """
    while _own_config_dirs:
        shutil.rmtree(_own_config_dirs.pop(), ignore_errors=True)


atexit.register(_remove_own_config_dirs)


class LiveHome:
    """One running Home Assistant with one installation set up in it."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Bind the harness to a running instance."""
        self.hass = hass
        self.entry = entry
        self.config_dir = hass.config.config_dir
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.events: list[tuple[str, dict[str, Any]]] = []

    # -- de wereld zetten / setting the world --------------------------------

    def set(self, entity_id: str, state: str, **attributes: Any) -> None:
        """Put one entity in a state, the way a device or a helper would."""
        self.hass.states.async_set(entity_id, state, attributes or None)

    def climate(
        self,
        entity_id: str,
        mode: str = "off",
        *,
        temperature: float | None = None,
        current: float | None = None,
    ) -> None:
        """Put one climate entity in a mode, with its setpoint and reading."""
        attributes: dict[str, Any] = {}
        if temperature is not None:
            attributes["temperature"] = temperature
        if current is not None:
            attributes["current_temperature"] = current
        self.hass.states.async_set(entity_id, mode, attributes)

    def state(self, entity_id: str) -> str | None:
        """Return an entity's state, or `None` when it does not exist."""
        found = self.hass.states.get(entity_id)
        return None if found is None else found.state

    def attributes(self, entity_id: str) -> dict[str, Any]:
        """Return an entity's attributes, or an empty mapping."""
        found = self.hass.states.get(entity_id)
        return {} if found is None else dict(found.attributes)

    def registered(self) -> dict[str, str]:
        """Return this installation's entities, keyed by the key in their unique id.

        De unieke ID is `<entry_id>_<sleutel>`, en die sleutel is wat de code
        zelf kiest. Daarop zoeken is steviger dan op een entity id, want dat
        laatste hangt aan de naam van de installatie en aan de vertaling.

        The unique id is `<entry_id>_<key>`, and that key is what the code
        itself picks. Looking things up on it is sturdier than on an entity id,
        since the latter hangs on the installation's name and on the
        translation.
        """
        registry = entity_registry.async_get(self.hass)
        prefix = f"{self.entry.entry_id}_"
        return {
            item.unique_id.removeprefix(prefix): item.entity_id
            for item in registry.entities.values()
            if item.config_entry_id == self.entry.entry_id and item.unique_id.startswith(prefix)
        }

    def by_key(self, key: str) -> str:
        """Return the entity id of the entity carrying this key."""
        found = self.registered()
        assert key in found, f"geen entiteit met sleutel {key}; wel: {sorted(found)}"
        return found[key]

    def value(self, key: str) -> str | None:
        """Return the state of the entity carrying this key."""
        return self.state(self.by_key(key))

    def values(self, key: str) -> dict[str, Any]:
        """Return the attributes of the entity carrying this key."""
        return self.attributes(self.by_key(key))

    # -- de integratie aan het werk zetten / putting the integration to work --

    @property
    def coordinator(self):
        """Return the live coordinator of this installation."""
        return self.entry.runtime_data

    async def evaluate(self) -> None:
        """Decide once, right now, without waiting for the debouncer."""
        await self.coordinator._async_evaluate()
        await self.hass.async_block_till_done()

    async def settle(self) -> None:
        """Let every queued task finish, the debouncer included."""
        await asyncio.sleep(0)
        await self.hass.async_block_till_done()

    async def call(self, domain: str, service: str, data: dict[str, Any] | None = None) -> None:
        """Call one action and wait for it to be done."""
        await self.hass.services.async_call(domain, service, data or {}, blocking=True)
        await self.hass.async_block_till_done()

    def climate_calls(self) -> list[tuple[str, dict[str, Any]]]:
        """Return every climate action the applier issued so far."""
        return list(self.calls)

    def clear_calls(self) -> None:
        """Forget the climate actions issued so far."""
        self.calls.clear()

    def fired(self, event_type: str) -> list[dict[str, Any]]:
        """Return the payloads of one event type fired so far."""
        return [data for name, data in self.events if name == event_type]


async def start_house(
    installation: dict[str, Any],
    *,
    shadow: bool = False,
    states: dict[str, tuple[str, dict[str, Any]]] | None = None,
    title: str = "Climate Director",
    entry_id: str = "live",
    config_dir: str | None = None,
) -> LiveHome:
    """Return a running Home Assistant with this installation loaded.

    De toestanden worden gezet vóórdat de entry opgezet wordt, zodat de eerste
    beslissing een volledige wereld ziet - net als bij een herstart van een huis
    dat al draait.

    States are set before the entry is set up, so the first decision sees a full
    world - just as on a restart of a house already running.
    """
    hass = HomeAssistant(config_dir or new_config_dir())
    loader.async_setup(hass)
    hass.config_entries = ConfigEntries(hass, {})
    await hass.config_entries.async_initialize()
    # Het apparaatregister moet sinds Home Assistant 2026.3 eerst opgezet
    # worden; daarvoor maakte het zichzelf aan bij het eerste gebruik. De
    # testset draait tegen allebei - de CI installeert een oudere versie dan
    # deze ontwikkelmachine - dus wordt de nieuwe stap alleen gezet als hij
    # bestaat.
    #
    # Since Home Assistant 2026.3 the device registry has to be set up first;
    # before that it created itself on first use. The test set runs against
    # both - CI installs an older version than this development machine - so
    # the newer step is only taken when it exists.
    prepare = getattr(device_registry, "async_setup", None)
    if prepare is not None:
        prepare(hass)

    for module in (area_registry, device_registry, entity_registry, issue_registry, restore_state):
        await module.async_load(hass)
    await async_setup_component(hass, "homeassistant", {})

    # De integratie hangt haar eerste beslissing aan `async_at_started`, en dat
    # kijkt naar `hass.state`. In een echte Home Assistant staat die op
    # `running` zodra de entry opgezet wordt; dit harnas roept `async_start()`
    # nooit aan, dus wordt die stand hier gezet zodat `async_at_started` meteen
    # vuurt - precies zoals een draaiende Home Assistant dat zou doen.
    #
    # The integration hangs its first decision off `async_at_started`, which
    # looks at `hass.state`. In a real Home Assistant that reads `running` by
    # the time the entry is set up; this harness never calls `async_start()`,
    # so the state is set here to make `async_at_started` fire at once - exactly
    # as a running Home Assistant would.
    hass.set_state(CoreState.running)

    # Een bewaarde entry betekent dat dit een herstart is: dan hoort hij
    # opgezet te worden zoals hij bewaard staat, niet opnieuw aangemaakt.
    #
    # A stored entry means this is a restart: it should then be set up as it
    # stands stored, rather than created afresh.
    stored = hass.config_entries.async_get_entry(entry_id)
    entry = stored or ConfigEntry(
        data={CONF_INSTALLATION: installation},
        options={CONF_SHADOW_MODE: shadow},
        domain=DOMAIN,
        minor_version=1,
        version=1,
        source="user",
        title=title,
        unique_id=None,
        discovery_keys={},  # type: ignore[arg-type]
        subentries_data=None,
        entry_id=entry_id,
    )

    home = LiveHome(hass, entry)
    _register_climate(home)
    _watch_events(home)

    for entity_id, (state, attributes) in (states or {}).items():
        hass.states.async_set(entity_id, state, attributes)

    if stored is None:
        await hass.config_entries.async_add(entry)
    else:
        await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return home


async def stop_house(home: LiveHome) -> None:
    """Write the restorable states away, unload, and stop Home Assistant again.

    De standen wegschrijven hoort bij het afsluiten: Home Assistant doet dat bij
    het stoppen, en zonder die stap zou een herstart in deze tests altijd met
    een schone lei beginnen - waarmee elke test over "dit hoort een herstart te
    overleven" niets zou zeggen.

    Writing the restorable states away is part of shutting down: Home Assistant
    does that when it stops, and without that step a restart in these tests
    would always begin with a clean slate - which would leave every test about
    "this should survive a restart" saying nothing.
    """
    with contextlib.suppress(Exception):  # het afbreken mag hier nooit op stuklopen
        await restore_state.async_get(home.hass).async_dump_states()
    try:
        if home.entry.entry_id in home.hass.config_entries._entries:
            await home.hass.config_entries.async_unload(home.entry.entry_id)
        await home.hass.async_block_till_done()
    finally:
        await home.hass.async_stop(force=True)


def _register_climate(home: LiveHome) -> None:
    """Register stand-in climate actions that write the state back.

    Zonder deze twee bestaat `climate.set_hvac_mode` niet en gooit Home
    Assistant een `ServiceNotFound` - precies wat er bij een gebruiker gebeurt
    als een apparaat verdwenen is, maar niet wat we hier willen meten. Ze
    schrijven de toestand terug, zodat de volgende ronde ziet wat er gebeurd is.

    Without these two `climate.set_hvac_mode` does not exist and Home Assistant
    raises a `ServiceNotFound` - exactly what happens to a user when an appliance
    has gone, but not what we want to measure here. They write the state back, so
    the next round sees what happened.
    """

    async def _set_mode(call: ServiceCall) -> None:
        home.calls.append(("set_hvac_mode", dict(call.data)))
        _write(home, call.data["entity_id"], call.data["hvac_mode"])

    async def _set_temperature(call: ServiceCall) -> None:
        home.calls.append(("set_temperature", dict(call.data)))
        _write(
            home,
            call.data["entity_id"],
            call.data.get("hvac_mode"),
            call.data.get("temperature"),
        )

    home.hass.services.async_register("climate", "set_hvac_mode", _set_mode)
    home.hass.services.async_register("climate", "set_temperature", _set_temperature)


def _write(
    home: LiveHome, entity_id: str, mode: str | None, temperature: float | None = None
) -> None:
    """Write one appliance's new state, keeping what the call did not name."""
    current = home.hass.states.get(entity_id)
    attributes = dict(current.attributes) if current else {}
    if temperature is not None:
        attributes["temperature"] = temperature
    state = mode if mode is not None else (current.state if current else "off")
    home.hass.states.async_set(entity_id, state, attributes)


def _watch_events(home: LiveHome) -> None:
    """Record the integration's own events as they are fired."""
    from custom_components.climate_director.const import (
        EVENT_DECISION,
        EVENT_PRECONDITION_REFUSED,
    )

    for event_type in (EVENT_DECISION, EVENT_PRECONDITION_REFUSED):

        def _record(event, name=event_type):
            home.events.append((name, dict(event.data)))

        home.hass.bus.async_listen(event_type, _record)


# ---------------------------------------------------------------------------
# Installaties als opslagvorm, want dat is wat een config entry bevat.
# Installations in stored form, since that is what a config entry holds.
# ---------------------------------------------------------------------------


def zone(
    zone_id: str,
    *,
    sources: list[dict[str, Any]],
    indoor_sensor: str | None = None,
    heat: dict[str, Any] | None = None,
    cool: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Return one zone in stored form, with sensible defaults."""
    found: dict[str, Any] = {
        "zone_id": zone_id,
        "name": zone_id.replace("_", " ").title(),
        "indoor_sensor": indoor_sensor or f"sensor.{zone_id}",
        "sources": sources,
    }
    if heat is not None:
        found["heat"] = heat
    if cool is not None:
        found["cool"] = cool
    found.update(extra)
    return found


def source(source_id: str, entity_id: str, **extra: Any) -> dict[str, Any]:
    """Return one source in stored form."""
    return {"source_id": source_id, "entity_id": entity_id, **extra}


def settings(target: float, start_at: float, hysteresis: float = 1.0, **extra: Any) -> dict:
    """Return one duty's settings in stored form."""
    return {"target": target, "start_at": start_at, "hysteresis": hysteresis, **extra}


def moment(hour: int = 12, minute: int = 0, *, day: int = 10, month: int = 8) -> datetime:
    """Return a moment in 2026; 10 August is a Monday."""
    return datetime(2026, month, day, hour, minute)
