"""De integratie in een echt draaiende Home Assistant.

The integration inside a really running Home Assistant.

Alles hier gaat door de echte opzetweg: `async_setup_entry`, de platforms, de
entiteitenregistratie, de actiedefinities en het afbreken. De klimaatapparaten
zijn nagebouwd maar de rest niet, dus wat hier stukloopt, loopt bij een
gebruiker ook stuk.

Everything here goes through the real setup path: `async_setup_entry`, the
platforms, the entity registry, the action definitions and the teardown. The
climate appliances are stand-ins but the rest is not, so what breaks here breaks
for a user too.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from harness_live import LiveHome, settings, source, start_house, stop_house, zone

LIVING = "climate.woonkamer"
SPARE = "climate.woonkamer_reserve"
ATTIC = "climate.zolder"
BOILER = "climate.ketel"


def installation(**extra: Any) -> dict[str, Any]:
    """Return a two-zone house: a room with a stand-in, and an attic."""
    found: dict[str, Any] = {
        "zones": [
            zone(
                "woonkamer",
                sources=[
                    source("woonkamer_airco", LIVING, role="heat_cool"),
                    source("woonkamer_reserve", SPARE, role="heat_only", priority=1),
                ],
                heat=settings(21.0, 20.0),
                cool=settings(23.0, 24.0),
            ),
            zone(
                "zolder",
                sources=[source("zolder_airco", ATTIC, role="heat_cool")],
                heat=settings(20.0, 19.0),
                priority=1,
            ),
        ],
        "outdoor_sensor": "sensor.buiten",
        "residents": [
            {
                "resident_id": "danny",
                "name": "Danny",
                "presence_entity": "person.danny",
                "sleep_entity": "sensor.danny_lader",
                "sleep_state": "wireless",
            }
        ],
        "openings": [{"entity_id": "binary_sensor.achterdeur", "delay": 0}],
    }
    found.update(extra)
    return found


def cold_world() -> dict[str, tuple[str, dict[str, Any]]]:
    """Return a world where both rooms want heat and somebody is home."""
    return {
        "sensor.woonkamer": ("18.0", {}),
        "sensor.zolder": ("17.0", {}),
        "sensor.buiten": ("4.0", {}),
        LIVING: ("off", {"temperature": 19.0}),
        SPARE: ("off", {"temperature": 19.0}),
        ATTIC: ("off", {"temperature": 19.0}),
        "person.danny": ("home", {}),
        "sensor.danny_lader": ("none", {}),
        "binary_sensor.achterdeur": ("off", {}),
    }


@pytest.fixture
async def home():
    """Return a running house that wants heat, torn down afterwards."""
    live = await start_house(installation(), states=cold_world())
    try:
        yield live
    finally:
        await stop_house(live)


# ---------------------------------------------------------------------------
# Opzetten en afbreken.
# Setting up and tearing down.
# ---------------------------------------------------------------------------


class TestSettingUp:
    """Wat er op tafel staat zodra de installatie geladen is.

    What stands on the table once the installation is loaded.
    """

    async def test_the_entry_loads(self, home: LiveHome) -> None:
        from homeassistant.config_entries import ConfigEntryState

        assert home.entry.state is ConfigEntryState.LOADED

    async def test_every_platform_delivered_its_entities(self, home: LiveHome) -> None:
        keys = set(home.registered())
        assert "last_decision" in keys
        assert "mismatch" in keys
        assert "master" in keys
        assert "holiday" in keys
        assert "guest" in keys
        assert "stuck" in keys
        assert {"zone_woonkamer_override", "zone_zolder_override"} <= keys
        assert {"zone_woonkamer_priority", "zone_zolder_priority"} <= keys
        assert "precondition_minutes" in keys
        assert {f"command_{LIVING}", f"command_{SPARE}", f"command_{ATTIC}"} <= keys

    async def test_a_generator_gets_a_command_sensor(self) -> None:
        """Een gedeelde warmtebron krijgt een commando, dus ook een sensor.

        A shared heat source gets a command, so it also gets a sensor.
        """
        live = await start_house(
            installation(generators=[{"generator_id": "cv", "name": "CV", "entity_id": BOILER}]),
            states={**cold_world(), BOILER: ("off", {"temperature": 19.0})},
        )
        try:
            assert f"command_{BOILER}" in live.registered()
        finally:
            await stop_house(live)

    async def test_no_two_entities_share_a_unique_id(self, home: LiveHome) -> None:
        registered = home.registered()
        assert len(registered) == len(set(registered.values()))

    async def test_the_actions_are_registered(self, home: LiveHome) -> None:
        available = home.hass.services.async_services().get("climate_director", {})
        assert set(available) == {"evaluate", "precondition", "cancel_precondition"}

    async def test_the_device_carries_the_installed_version(self, home: LiveHome) -> None:
        from homeassistant.helpers import device_registry

        registry = device_registry.async_get(home.hass)
        devices = [
            item for item in registry.devices.values() if home.entry.entry_id in item.config_entries
        ]
        assert len(devices) == 1
        assert devices[0].sw_version
        assert devices[0].manufacturer == "Sarnog"

    async def test_unloading_takes_the_entities_away(self, home: LiveHome) -> None:
        entity_id = home.by_key("last_decision")
        assert home.state(entity_id) is not None
        assert await home.hass.config_entries.async_unload(home.entry.entry_id)
        await home.hass.async_block_till_done()
        assert home.state(entity_id) in (None, "unavailable")

    async def test_reloading_keeps_the_house_working(self, home: LiveHome) -> None:
        assert await home.hass.config_entries.async_reload(home.entry.entry_id)
        await home.hass.async_block_till_done()
        assert home.value("last_decision") == "2/2"


class TestStartupWithHalfLoadedState:
    """Opstarten met een half geladen wereld mag niets uitzetten.

    Starting up with a half-loaded world must not switch anything off.
    """

    async def test_an_unreadable_sensor_leaves_the_running_appliance_alone(self) -> None:
        """De sensor ontbreekt nog, het apparaat draait: geen `set_hvac_mode`.

        The sensor is still missing and the appliance runs: no `set_hvac_mode`.
        """
        states = cold_world()
        del states["sensor.woonkamer"]
        states[LIVING] = ("heat", {"temperature": 21.0})

        home = await start_house(installation(), states=states)
        try:
            calls = home.climate_calls()
            assert not [call for call in calls if call[1].get("entity_id") == LIVING]
        finally:
            await stop_house(home)


# ---------------------------------------------------------------------------
# Van beslissing naar service call.
# From decision to service call.
# ---------------------------------------------------------------------------


class TestSteeringForReal:
    """De opdrachten komen als echte acties bij de apparaten aan.

    The commands arrive at the appliances as real actions.
    """

    async def test_both_rooms_were_started(self, home: LiveHome) -> None:
        assert home.state(LIVING) == "heat"
        assert home.state(ATTIC) == "heat"
        assert home.attributes(LIVING)["temperature"] == 21.0

    async def test_the_stand_in_was_not_started(self, home: LiveHome) -> None:
        assert home.state(SPARE) == "off"

    async def test_deciding_again_changes_nothing(self, home: LiveHome) -> None:
        home.clear_calls()
        await home.evaluate()
        assert home.climate_calls() == []

    async def test_a_warm_room_is_switched_off_again(self, home: LiveHome) -> None:
        home.set("sensor.woonkamer", "23.0")
        await home.evaluate()
        assert home.state(LIVING) == "off"

    async def test_the_dead_band_keeps_it_running(self, home: LiveHome) -> None:
        # Aan bij 20, uit pas bij 21: 20,5 hoort door te draaien.
        # On at 20, off only at 21: 20.5 should keep running.
        home.set("sensor.woonkamer", "20.5")
        await home.evaluate()
        assert home.state(LIVING) == "heat"

    async def test_an_open_door_stops_the_house(self, home: LiveHome) -> None:
        home.set("binary_sensor.achterdeur", "on")
        await home.evaluate()
        assert home.state(LIVING) == "off"
        assert home.state(ATTIC) == "off"

    async def test_the_debouncer_carries_a_state_change_through(self, home: LiveHome) -> None:
        """Zonder aanroep van buiten: alleen een sensor die verandert.

        Without a call from outside: only a sensor that changes.
        """
        home.set("sensor.woonkamer", "22.0")
        await asyncio.sleep(1.4)
        await home.hass.async_block_till_done()
        assert home.state(LIVING) == "off"


class TestPrecipitation:
    """Regen zet de 'zet een raam open'-grens opzij, met nalooptijd."""

    def _installation(self, grace: int) -> dict[str, Any]:
        found = installation()
        found["zones"][0]["heat"] = {
            **found["zones"][0]["heat"],
            "outdoor": {"minimum": None, "maximum": 25.0},
        }
        found["precipitation"] = {
            "source": "weather.buienradar",
            "states": ["rainy", "pouring"],
            "grace": grace,
        }
        return found

    def _states(self) -> dict[str, tuple[str, dict[str, Any]]]:
        return {
            **cold_world(),
            "sensor.buiten": ("26.0", {}),
            "weather.buienradar": ("rainy", {}),
        }

    async def test_rain_lifts_the_zone_bound_and_stopping_rain_drops_it(self) -> None:
        """Buiten 26 graden is boven de verwarmgrens; regen zet die opzij."""
        live = await start_house(self._installation(grace=0), states=self._states())
        try:
            assert live.state(LIVING) == "heat"
            live.set("weather.buienradar", "cloudy")
            await live.evaluate()
            assert live.state(LIVING) == "off"
        finally:
            await stop_house(live)

    async def test_rain_keeps_counting_for_the_grace_period(self) -> None:
        """Een bui van vijf minuten hoort de regeling niet te laten stuiteren."""
        live = await start_house(self._installation(grace=900), states=self._states())
        try:
            assert live.state(LIVING) == "heat"
            live.set("weather.buienradar", "cloudy")
            await live.evaluate()
            assert live.state(LIVING) == "heat", "de nalooptijd hoort regen te laten meetellen"
        finally:
            await stop_house(live)


class TestShadowMode:
    """In schaduwmodus gebeurt er niets, en wordt alles wel opgeschreven.

    In shadow mode nothing happens, and everything is written down.
    """

    async def test_nothing_is_steered_but_it_is_reported(self) -> None:
        live = await start_house(installation(), states=cold_world(), shadow=True)
        try:
            assert live.climate_calls() == []
            assert live.state(LIVING) == "off"
            would = live.values("last_decision")["would_change"]
            assert LIVING in would
            assert ATTIC in would
            assert live.values("last_decision")["shadow_mode"] is True
        finally:
            await stop_house(live)


# ---------------------------------------------------------------------------
# De acties.
# The actions.
# ---------------------------------------------------------------------------


class TestTheActions:
    """De drie acties, met hun velden en hun grenzen.

    The three actions, with their fields and their limits.
    """

    async def test_evaluate_decides_again(self, home: LiveHome) -> None:
        home.set("sensor.woonkamer", "22.0")
        await home.call("climate_director", "evaluate", {})
        await asyncio.sleep(1.4)
        await home.hass.async_block_till_done()
        assert home.state(LIVING) == "off"

    async def test_evaluate_accepts_a_single_entry_id(self, home: LiveHome) -> None:
        await home.call("climate_director", "evaluate", {"entry_id": home.entry.entry_id})
        await home.settle()

    async def test_evaluate_ignores_an_unknown_entry_id(self, home: LiveHome) -> None:
        await home.call("climate_director", "evaluate", {"entry_id": "geen-installatie"})
        await home.settle()

    async def test_preconditioning_runs_an_empty_house(self, home: LiveHome) -> None:
        home.set("person.danny", "not_home")
        await home.evaluate()
        assert home.state(LIVING) == "off"

        await home.call(
            "climate_director", "precondition", {"zone_ids": ["woonkamer"], "minutes": 45}
        )
        await asyncio.sleep(1.4)
        await home.hass.async_block_till_done()
        assert home.state(LIVING) == "heat"
        assert home.state(ATTIC) == "off", "alleen de gevraagde zone hoort te draaien"

    @pytest.mark.parametrize("minutes", ["45", "45.0"])
    async def test_a_duration_may_arrive_as_text(self, home: LiveHome, minutes: str) -> None:
        """YAML levert getallen vaak als tekst aan; het schema hoort dat om te zetten.

        YAML often hands numbers over as text; the schema should coerce that.
        """
        home.set("person.danny", "not_home")
        await home.evaluate()
        assert home.state(LIVING) == "off"

        await home.call(
            "climate_director", "precondition", {"zone_ids": ["woonkamer"], "minutes": minutes}
        )
        await asyncio.sleep(1.4)
        await home.hass.async_block_till_done()
        assert home.state(LIVING) == "heat"

    async def test_a_request_is_capped_at_the_installation_maximum(self, home: LiveHome) -> None:
        home.coordinator.async_precondition(["woonkamer"], 6000)
        granted = home.coordinator._live_preconditions()["woonkamer"]
        from homeassistant.util import dt as dt_util

        assert (granted - dt_util.now()).total_seconds() <= 7200 + 5

    async def test_calling_without_minutes_grants_the_installation_maximum(
        self, home: LiveHome
    ) -> None:
        """De blueprint laat `minutes` weg; dat hoort het maximum te geven.

        The blueprint omits `minutes`; that should grant the installation maximum.
        """
        home.set("person.danny", "not_home")
        await home.call("climate_director", "precondition", {"zone_ids": ["woonkamer"]})
        granted = home.coordinator._live_preconditions()["woonkamer"]
        from homeassistant.util import dt as dt_util

        assert (granted - dt_util.now()).total_seconds() > 7200 - 5

    async def test_calling_with_zero_minutes_does_nothing(self, home: LiveHome) -> None:
        """Nul minuten is een typefout, geen vrijbrief voor het maximum.

        Zero minutes is a typo, not a licence for the maximum.
        """
        home.set("person.danny", "not_home")
        await home.evaluate()
        assert home.state(LIVING) == "off"

        await home.call(
            "climate_director", "precondition", {"zone_ids": ["woonkamer"], "minutes": 0}
        )
        await asyncio.sleep(1.4)
        await home.hass.async_block_till_done()
        assert home.state(LIVING) == "off"
        assert home.coordinator._live_preconditions() == {}

    async def test_cancelling_stops_it_again(self, home: LiveHome) -> None:
        home.set("person.danny", "not_home")
        await home.call("climate_director", "precondition", {"minutes": 60})
        await asyncio.sleep(1.4)
        await home.hass.async_block_till_done()
        assert home.state(LIVING) == "heat"

        await home.call("climate_director", "cancel_precondition", {})
        await asyncio.sleep(1.4)
        await home.hass.async_block_till_done()
        assert home.state(LIVING) == "off"

    async def test_an_unknown_zone_is_simply_dropped(self, home: LiveHome) -> None:
        granted = home.coordinator.async_precondition(["kelder", "woonkamer"], 30)
        assert set(granted) == {"woonkamer"}

    async def test_a_negative_duration_is_refused_by_the_schema(self, home: LiveHome) -> None:
        import voluptuous as vol

        with pytest.raises(vol.Invalid):
            await home.call("climate_director", "precondition", {"minutes": -5})

    async def test_ignore_openings_is_accepted_and_carried(self, home: LiveHome) -> None:
        home.set("person.danny", "not_home")
        home.set("binary_sensor.achterdeur", "on")
        await home.evaluate()

        await home.call(
            "climate_director",
            "precondition",
            {"zone_ids": ["woonkamer"], "minutes": 30, "ignore_openings": True},
        )
        await asyncio.sleep(1.4)
        await home.hass.async_block_till_done()
        assert home.state(LIVING) == "heat", "een uitdrukkelijk 'toch doen' hoort door te gaan"


# ---------------------------------------------------------------------------
# De bedieningsentiteiten.
# The control entities.
# ---------------------------------------------------------------------------


class TestTheControls:
    """Schakelaars, getallen en knoppen, aangeroepen zoals een gebruiker het doet.

    Switches, numbers and buttons, called the way a user does.
    """

    async def test_the_master_switch_stops_everything(self, home: LiveHome) -> None:
        await home.call("switch", "turn_off", {"entity_id": home.by_key("master")})
        await asyncio.sleep(1.4)
        await home.hass.async_block_till_done()
        assert home.state(LIVING) == "off"
        assert home.state(ATTIC) == "off"

        await home.call("switch", "turn_on", {"entity_id": home.by_key("master")})
        await asyncio.sleep(1.4)
        await home.hass.async_block_till_done()
        assert home.state(LIVING) == "heat"

    async def test_the_override_hands_a_zone_over(self, home: LiveHome) -> None:
        await home.call("switch", "turn_on", {"entity_id": home.by_key("zone_woonkamer_override")})
        await asyncio.sleep(1.4)
        await home.hass.async_block_till_done()

        home.set("sensor.woonkamer", "26.0")
        home.clear_calls()
        await home.evaluate()
        steered = [data["entity_id"] for _name, data in home.climate_calls()]
        assert LIVING not in steered, "een overgedragen zone hoort niets te krijgen"

    async def test_the_guest_switch_carries_an_empty_house(self, home: LiveHome) -> None:
        home.set("person.danny", "not_home")
        await home.evaluate()
        assert home.state(LIVING) == "off"

        await home.call("switch", "turn_on", {"entity_id": home.by_key("guest")})
        await asyncio.sleep(1.4)
        await home.hass.async_block_till_done()
        assert home.state(LIVING) == "heat"

    async def test_the_holiday_switch_is_accepted(self, home: LiveHome) -> None:
        await home.call("switch", "turn_on", {"entity_id": home.by_key("holiday")})
        await home.settle()
        assert home.state(home.by_key("holiday")) == "on"
        assert home.coordinator.holiday_mode is True

    async def test_priority_can_be_set_from_an_automation(self, home: LiveHome) -> None:
        await home.call(
            "number",
            "set_value",
            {"entity_id": home.by_key("zone_zolder_priority"), "value": 0},
        )
        await home.settle()
        assert home.coordinator.zone_priorities["zolder"] == 0

    async def test_the_duration_number_holds_its_bounds(self, home: LiveHome) -> None:
        entity_id = home.by_key("precondition_minutes")
        attributes = home.attributes(entity_id)
        assert attributes["min"] == 15
        assert attributes["max"] == 120

        await home.call("number", "set_value", {"entity_id": entity_id, "value": 90})
        await home.settle()
        assert home.coordinator.precondition_minutes == 90

        from homeassistant.exceptions import ServiceValidationError

        with pytest.raises(ServiceValidationError):
            await home.call("number", "set_value", {"entity_id": entity_id, "value": 500})

    async def test_the_button_starts_a_request_for_its_own_zone(self, home: LiveHome) -> None:
        home.set("person.danny", "not_home")
        await home.evaluate()
        assert home.state(LIVING) == "off"

        await home.call(
            "button", "press", {"entity_id": home.by_key("zone_woonkamer_precondition")}
        )
        await asyncio.sleep(1.4)
        await home.hass.async_block_till_done()
        assert home.state(LIVING) == "heat"
        assert home.state(ATTIC) == "off"


# ---------------------------------------------------------------------------
# Wat de sensoren laten zien.
# What the sensors show.
# ---------------------------------------------------------------------------


class TestTheReporting:
    """De uitkomst zoals een gebruiker hem op zijn dashboard ziet.

    The outcome as a user sees it on their dashboard.
    """

    async def test_the_summary_counts_the_served_rooms(self, home: LiveHome) -> None:
        assert home.value("last_decision") == "2/2"
        home.set("sensor.zolder", "25.0")
        await home.evaluate()
        assert home.value("last_decision") == "1/2"

    async def test_the_command_sensor_names_the_mode(self, home: LiveHome) -> None:
        assert home.value(f"command_{LIVING}") == "heat"
        assert home.values(f"command_{LIVING}")["temperature"] == 21.0
        assert home.values(f"command_{LIVING}")["reason"] == "regulating"

    async def test_an_unreachable_appliance_says_so(self, home: LiveHome) -> None:
        home.set(ATTIC, "unavailable")
        await home.evaluate()
        assert home.value(f"command_{ATTIC}") == "unreachable"
        assert home.values(f"command_{ATTIC}")["reason"] == "source_unreachable"

    async def test_the_zone_sensor_names_the_source(self, home: LiveHome) -> None:
        assert home.value("zone_woonkamer_source") == "woonkamer_airco"

    async def test_the_blocked_sensor_names_the_gate_that_held_the_zone_back(
        self, home: LiveHome
    ) -> None:
        """De melder gaat nu ook aan bij een dichte poort, en noemt hem.

        Een zone met een dichte poort vraagt niets en kreeg dus niets te
        weinig; de melder keek alleen daarnaar en bleef uit terwijl de kamer
        wél iets nodig had. Nu telt ook "poort dicht terwijl de kamer buiten
        zijn dode band ligt". De attributen noemen de poort en wat de kamer
        gewild zou hebben.

        The sensor now also comes on for a shut gate, and names it. A zone
        with a shut gate asks for nothing and was therefore short-changed
        nothing; the sensor only looked at that and stayed off while the room
        did need something. Now "gate shut while the room sits outside its
        dead band" counts too. The attributes name the gate and what the room
        would have wanted.
        """
        assert home.value("zone_woonkamer_blocked") == "off"
        assert home.values("zone_woonkamer_blocked")["closed_gates"] == []
        home.set("binary_sensor.achterdeur", "on")
        await home.evaluate()
        assert home.value("zone_woonkamer_blocked") == "on"
        attributes = home.values("zone_woonkamer_blocked")
        assert attributes["reason"] == "opening_open"
        assert attributes["closed_gates"] == ["opening_open"]
        assert attributes["would_want"] == "heat"

    async def test_a_shut_gate_in_a_comfortable_room_does_not_light_the_sensor(
        self, home: LiveHome
    ) -> None:
        """Een open raam in een kamer die al op temperatuur is, blokkeert niets."""
        home.set("binary_sensor.achterdeur", "on")
        home.set("sensor.woonkamer", "22.0")
        await home.evaluate()
        assert home.value("zone_woonkamer_blocked") == "off"

    async def test_an_override_is_not_a_blockage(self, home: LiveHome) -> None:
        """Wie een zone overdraagt wil geen 'geblokkeerd'-melder zien branden."""
        home.set("binary_sensor.achterdeur", "on")
        await home.evaluate()
        assert home.value("zone_woonkamer_blocked") == "on"
        home.coordinator.zone_overrides["woonkamer"] = True
        await home.evaluate()
        assert home.value("zone_woonkamer_blocked") == "off"

    async def test_the_stand_in_sensor_lights_up_when_it_takes_over(self, home: LiveHome) -> None:
        assert home.value("zone_woonkamer_fallback") == "off"
        home.set(LIVING, "unavailable")
        await home.evaluate()
        assert home.state(SPARE) == "heat"
        assert home.value("zone_woonkamer_fallback") == "on"

    async def test_the_mismatch_sensor_counts_what_did_not_land(self, home: LiveHome) -> None:
        # De eerste ronde wilde twee apparaten zetten; die zijn daarna gezet,
        # dus de ronde erna valt er niets meer te verschillen.
        #
        # The first round wanted to set two appliances; those have since been
        # set, so the round after there is nothing left to differ.
        assert home.value("mismatch") == "2"
        await home.evaluate()
        assert home.value("mismatch") == "0"
        assert home.values("mismatch")["differences"] == []

    async def test_the_decision_event_carries_the_outcome(self, home: LiveHome) -> None:
        fired = home.fired("climate_director_decision")
        assert fired, "er hoort na de eerste beslissing een event te zijn"
        living = [item for item in fired if item["zone_id"] == "woonkamer"][-1]
        assert living["granted"] == "heat"
        assert living["entity_id"] == LIVING
        assert living["temperature"] == 21.0

    async def test_no_event_is_fired_when_nothing_changed(self, home: LiveHome) -> None:
        before = len(home.fired("climate_director_decision"))
        await home.evaluate()
        assert len(home.fired("climate_director_decision")) == before


# ---------------------------------------------------------------------------
# Wat er over een herstart heen hoort te komen.
# What should survive a restart.
# ---------------------------------------------------------------------------


class TestAcrossARestart:
    """Een verzoek en een handmatige uitzetting overleven een herstart.

    A request and a hand-operated stand-down survive a restart.
    """

    async def test_a_running_request_comes_back(self) -> None:
        live = await start_house(installation(), states=cold_world(), entry_id="restart_probe")
        config_dir = live.config_dir
        try:
            live.set("person.danny", "not_home")
            await live.evaluate()
            live.coordinator.async_precondition(["woonkamer"], 90)
            await live.evaluate()
            assert live.state(LIVING) == "heat"
        finally:
            await stop_house(live)

        again = await start_house(
            installation(),
            states={**cold_world(), "person.danny": ("not_home", {})},
            entry_id="restart_probe",
            config_dir=config_dir,
        )
        try:
            assert again.coordinator._live_preconditions(), (
                "het verzoek hoort de herstart te overleven"
            )
            assert again.state(LIVING) == "heat"
        finally:
            await stop_house(again)


# ---------------------------------------------------------------------------
# De vertalingen, geladen zoals een draaiende Home Assistant dat zelf doet.
# The translations, loaded the way a running Home Assistant loads them itself.
# ---------------------------------------------------------------------------


class TestTheTranslationsLive:
    """Elke taal wordt echt geladen en ingevuld, niet alleen op vorm gecontroleerd.

    Each language is really loaded and filled in, not just checked for shape.
    """

    LANGUAGES = ("en", "nl", "de", "fr", "es", "ar")

    @pytest.mark.parametrize("language", LANGUAGES)
    async def test_every_language_loads_and_fills_its_sentences(self, language: str) -> None:
        home = await start_house(installation(), states=cold_world())
        try:
            home.hass.config.language = language
            from custom_components.climate_director import texts

            await texts.async_prepare(home.hass)
            message = texts.translated(
                home.hass,
                "precondition_refused",
                "fallback {zone} {openings} {minutes}",
                zone="Woonkamer",
                openings="Achterdeur",
                minutes=120,
            )

            assert "{" not in message, f"{language}: {message}"
            assert "Woonkamer" in message, f"{language}: {message}"
            assert "Achterdeur" in message, f"{language}: {message}"
            if language == "nl":
                assert "kon niet vooruit beginnen" in message
            elif language == "en":
                assert "could not start pre-conditioning" in message
        finally:
            await stop_house(home)

    async def test_the_refusal_event_speaks_dutch_in_a_dutch_interface(self) -> None:
        """De gebeurtenis draagt de zin in de taal van de interface.

        The event carries the sentence in the language of the interface.
        """
        home = await start_house(installation(), states=cold_world())
        try:
            home.hass.config.language = "nl"
            from custom_components.climate_director import texts

            await texts.async_prepare(home.hass)

            home.set("person.danny", "not_home")
            home.set("binary_sensor.achterdeur", "on")
            home.coordinator.async_precondition(["woonkamer"], 30)
            await home.evaluate()

            refused = home.fired("climate_director_precondition_refused")
            assert refused, "een geweigerd verzoek hoort zichzelf te melden"
            message = refused[-1]["message"]
            assert "kon niet vooruit beginnen" in message, message
            assert "Staat nog open" in message, message
            assert "120 minuten" in message, message
        finally:
            await stop_house(home)
