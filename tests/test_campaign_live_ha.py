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
from datetime import timedelta
from typing import Any

import pytest
from harness_live import LiveHome, settings, source, start_house, stop_house, zone

LIVING = "climate.woonkamer"
SPARE = "climate.woonkamer_reserve"
ATTIC = "climate.zolder"
BOILER = "climate.ketel"


def installation(**extra: Any) -> dict[str, Any]:
    """Return a two-zone house: a room with a stand-in, and an attic.

    Het vooruit-venster staat op de hele dag. Standaard is dat 06:00-23:00, en
    de klok van deze testopstelling is UTC: tussen 23:00 en 06:00 UTC vielen
    zeven tests over een verzoek dan om, zonder dat er iets aan de code
    veranderd was. Een test die van het uur afhangt zegt niets over de code.

    The pre-conditioning window is set to the whole day. The default is
    06:00-23:00 and this harness's clock is UTC: between 23:00 and 06:00 UTC
    seven tests about a request fell over, with nothing in the code changed. A
    test depending on the hour says nothing about the code.
    """
    found: dict[str, Any] = {
        "gates": {"precondition_window": None},
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


@pytest.fixture(params=["obedient", "stubborn"], autouse=True)
def appliance(request, monkeypatch):
    """Run every test against both appliance kinds the harness knows."""
    import harness_live

    monkeypatch.setattr(harness_live, "DEFAULT_APPLIANCE", request.param)


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


class TestTheActionsAndTheirLifetime:
    """De acties horen bij de integratie, dus ze gaan met de laatste mee.

    The actions belong to the integration, so they go with the last one.

    Ze stonden er na het afbreken nog, en dan gebeurt er bij een aanroep niets:
    de handler loopt over de geladen installaties, en dat zijn er nul. Een actie
    die er is en niets doet is erger dan een actie die er niet is - dan zegt
    Home Assistant tenminste dat hij niet bestaat.

    They stood there after tearing down, and then a call does nothing: the
    handler walks the loaded installations, and there are none. An action that
    exists and does nothing is worse than an action that does not exist - at
    least then Home Assistant says so.
    """

    async def test_the_actions_stand_while_an_installation_is_loaded(self, home: LiveHome) -> None:
        for name in ("evaluate", "precondition", "cancel_precondition"):
            assert home.hass.services.has_service("climate_director", name), name

    async def test_the_last_installation_takes_the_actions_with_it(self) -> None:
        live = await start_house(installation(), states=cold_world(), entry_id="acties")
        try:
            await live.hass.config_entries.async_unload(live.entry.entry_id)
            await live.hass.async_block_till_done()
            for name in ("evaluate", "precondition", "cancel_precondition"):
                assert not live.hass.services.has_service("climate_director", name), name
        finally:
            await stop_house(live)

    async def test_setting_up_again_brings_them_back(self) -> None:
        live = await start_house(installation(), states=cold_world(), entry_id="opnieuw")
        try:
            await live.hass.config_entries.async_unload(live.entry.entry_id)
            await live.hass.async_block_till_done()
            await live.hass.config_entries.async_setup(live.entry.entry_id)
            await live.hass.async_block_till_done()
            assert live.hass.services.has_service("climate_director", "evaluate")
        finally:
            await stop_house(live)


class TestUnloadingDuringARunningRound:
    """Afsluiten wacht de lopende ronde uit, zodat er niets meer achteraan komt.

    Unloading waits out the running round, so nothing comes after it.
    """

    @staticmethod
    def _warm_house() -> dict[str, tuple[str, dict[str, Any]]]:
        """Alles draait al zoals de director het wil: de eerste ronde is stil.

        Everything already runs the way the director wants it: the first round
        is silent.
        """
        return {
            "sensor.woonkamer": ("18.0", {}),
            "sensor.zolder": ("17.0", {}),
            "sensor.buiten": ("4.0", {}),
            LIVING: ("heat", {"temperature": 21.0}),
            SPARE: ("off", {"temperature": 19.0}),
            ATTIC: ("heat", {"temperature": 20.0}),
            "person.danny": ("home", {}),
            "sensor.danny_lader": ("none", {}),
            "binary_sensor.achterdeur": ("off", {}),
        }

    async def test_no_service_call_lands_after_the_unload(self) -> None:
        import contextlib

        live = await start_house(installation(), states=self._warm_house())
        started = asyncio.Event()
        proceed = asyncio.Event()

        async def slow_set_mode(call):
            started.set()
            await proceed.wait()
            live.calls.append(("set_hvac_mode", dict(call.data)))
            live.hass.states.async_set(call.data["entity_id"], call.data["hvac_mode"])

        live.hass.services.async_register("climate", "set_hvac_mode", slow_set_mode)
        try:
            assert live.climate_calls() == [], "de eerste ronde hoort niets te sturen"

            # De woonkamer wordt te warm; de director wil de airco uitzetten.
            # The living room turns too warm; the director wants the unit off.
            live.set("sensor.woonkamer", "23.0")
            round_task = asyncio.create_task(live.coordinator._async_evaluate())
            await asyncio.wait_for(started.wait(), timeout=5)

            unload_task = asyncio.create_task(
                live.hass.config_entries.async_unload(live.entry.entry_id)
            )
            await asyncio.sleep(0)
            await live.hass.async_block_till_done()

            assert not unload_task.done(), "de unload hoort op de lopende ronde te wachten"

            proceed.set()
            await round_task
            await unload_task
            await live.hass.async_block_till_done()

            calls_during = live.climate_calls()
            assert calls_during == [("set_hvac_mode", {"entity_id": LIVING, "hvac_mode": "off"})]

            await asyncio.sleep(0)
            await live.hass.async_block_till_done()
            assert live.climate_calls() == calls_during, "ná de unload mag er niets meer bijkomen"
        finally:
            proceed.set()
            with contextlib.suppress(Exception):
                await stop_house(live)

    async def test_reload_does_not_let_the_old_plan_land_after_the_new_one(self) -> None:
        import contextlib

        live = await start_house(installation(), states=self._warm_house())
        started = asyncio.Event()
        proceed = asyncio.Event()

        async def slow_set_mode(call):
            started.set()
            await proceed.wait()
            live.calls.append(("set_hvac_mode", dict(call.data)))
            live.hass.states.async_set(call.data["entity_id"], call.data["hvac_mode"])

        live.hass.services.async_register("climate", "set_hvac_mode", slow_set_mode)
        try:
            assert live.climate_calls() == [], "de eerste ronde hoort niets te sturen"

            live.set("sensor.woonkamer", "23.0")
            round_task = asyncio.create_task(live.coordinator._async_evaluate())
            await asyncio.wait_for(started.wait(), timeout=5)

            reload_task = asyncio.create_task(
                live.hass.config_entries.async_reload(live.entry.entry_id)
            )
            await asyncio.sleep(0)
            await live.hass.async_block_till_done()

            assert not reload_task.done(), "de reload hoort op de lopende ronde te wachten"

            proceed.set()
            await round_task
            await reload_task
            await live.hass.async_block_till_done()

            # Eén commando, en dat is het commando van vóór de reload. Het oude
            # plan mag niet nog eens landen nadat de nieuwe installatie er staat.
            # One command, and it is the one from before the reload. The old plan
            # may not land again once the new installation stands.
            assert live.climate_calls() == [
                ("set_hvac_mode", {"entity_id": LIVING, "hvac_mode": "off"})
            ]
        finally:
            proceed.set()
            with contextlib.suppress(Exception):
                await stop_house(live)


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

    async def test_calling_with_zero_minutes_is_refused_by_the_schema(self, home: LiveHome) -> None:
        """Nul minuten is een typefout, en die hoort te botsen, niet te verdwijnen.

        Zero minutes is a typo, and a typo should hit something rather than
        vanish.

        Het scherm staat het al niet toe (`min: 1` in services.yaml), dus een
        nul komt uit een met de hand geschreven aanroep. Die stil laten mislukken
        is precies verkeerd: je drukt op de knop, er gebeurt niets, en er is geen
        spoor van waarom.

        The screen already disallows it (`min: 1` in services.yaml), so a zero
        comes from a hand-written call. Failing that silently is exactly wrong:
        you press the button, nothing happens, and there is no trace of why.
        """
        import voluptuous as vol

        home.set("person.danny", "not_home")
        await home.evaluate()
        assert home.state(LIVING) == "off"

        with pytest.raises(vol.Invalid):
            await home.call(
                "climate_director", "precondition", {"zone_ids": ["woonkamer"], "minutes": 0}
            )
        assert home.coordinator._live_preconditions() == {}

    async def test_zero_minutes_still_grants_nothing_straight_at_the_coordinator(
        self, home: LiveHome
    ) -> None:
        """Ook zonder het schema ertussen blijft nul minuten geen verzoek.

        Without the schema in between, zero minutes still is not a request.
        """
        assert home.coordinator.async_precondition(["woonkamer"], 0) == {}
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


class TestTheAlarmUnderAPreConditioningRequest:
    """Een afgelopen verzoek mag de wekker van een lopend verzoek niet doven.

    A request that has run out must not put out the alarm of a running one.

    Er staat altijd maar een wekker, op het eerstvolgende verzoek dat afloopt.
    Werd die gezet op de ruwe lijst, dan koos hij een verzoek dat al voorbij was,
    zag "dat moment ligt achter ons" en zette helemaal niets. Het lopende verzoek
    liep daarna af zonder dat iemand het merkte, en op een stille middag stookt
    een leeg huis dan door tot er toevallig iets anders verandert.

    There is only ever one alarm, set on the first request to run out. Set from
    the raw list, it picked a request that was already over, saw "that moment is
    behind us" and set nothing at all. The running request then ran out with
    nobody noticing, and on a quiet afternoon an empty house keeps burning until
    something else happens to change.
    """

    async def test_a_stale_request_does_not_swallow_the_alarm(
        self, home: LiveHome, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from homeassistant.util import dt as dt_util

        from custom_components.climate_director import coordinator as module

        home.coordinator.async_precondition(["woonkamer"], 30)
        assert home.coordinator._cancel_precondition_wake is not None

        # Een uur verder is dat eerste verzoek allang voorbij, maar niemand
        # heeft het gelezen, dus het staat er nog.
        #
        # An hour on that first request is long over, but nobody has read it, so
        # it is still there.
        later = dt_util.now() + timedelta(hours=1)
        monkeypatch.setattr(module.dt_util, "now", lambda: later)
        home.coordinator._cancel_pending_precondition_wake()

        home.coordinator.async_precondition(["zolder"], 60)
        assert home.coordinator._cancel_precondition_wake is not None, (
            "het lopende verzoek hoort zijn eigen wekker te krijgen"
        )


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

    async def test_the_command_sensor_is_an_enum_over_every_state_it_can_take(
        self, home: LiveHome
    ) -> None:
        """De standen zijn een vaste lijst, dus Home Assistant mag ze vertalen.

        The states are a fixed list, so Home Assistant may translate them.

        Bij een `enum` logt Home Assistant een fout zodra er een waarde langskomt
        die niet in `options` staat. De lijst wordt daarom afgeleid uit
        `preferred_mode`, niet met de hand opgeschreven: wie daar ooit een stand
        aan toevoegt, hoeft deze lijst niet te onthouden.

        On an `enum` Home Assistant logs an error the moment a value appears that
        is not in `options`. The list is therefore derived from `preferred_mode`
        rather than written out by hand: whoever adds a mode there need not
        remember this list too.
        """
        from custom_components.climate_director.engine.families import (
            MODE_FAN_ONLY,
            MODE_OFF,
            ModeFamily,
            preferred_mode,
        )
        from custom_components.climate_director.sensor import (
            STATE_LEFT_ALONE,
            STATE_UNREACHABLE,
        )

        attributes = home.values(f"command_{LIVING}")
        assert attributes["device_class"] == "enum"
        options = set(attributes["options"])

        reachable = {preferred_mode(family) for family in ModeFamily}
        reachable |= {MODE_OFF, MODE_FAN_ONLY, STATE_LEFT_ALONE, STATE_UNREACHABLE}
        assert reachable <= options, sorted(reachable - options)
        assert home.value(f"command_{LIVING}") in options

    async def test_every_command_state_is_translated(self) -> None:
        """Een stand zonder tekst laat Home Assistant de kale sleutel tonen.

        A state without wording makes Home Assistant show the bare key.
        """
        import json
        from pathlib import Path

        from custom_components.climate_director.sensor import COMMAND_STATES

        component = Path(__file__).resolve().parents[1] / "custom_components" / "climate_director"
        files = [component / "strings.json", *sorted((component / "translations").glob("*.json"))]
        for path in files:
            data = json.loads(path.read_text(encoding="utf-8"))
            states = data["entity"]["sensor"]["would_command"]["state"]
            assert sorted(states) == sorted(COMMAND_STATES), path.name

    async def test_the_mismatch_sensor_carries_no_unit(self, home: LiveHome) -> None:
        """Een telling is geen meting met een eenheid.

        A count is not a measurement with a unit.

        Er stond `appliances` als eenheid, onvertaald en in het Engels, achter
        een getal dat gewoon een aantal is. Home Assistant zet dat er letterlijk
        achter, dus in het Nederlands stond er "2 appliances".

        The unit read `appliances`, untranslated and in English, behind a number
        that is simply a count. Home Assistant prints that verbatim, so in Dutch
        it said "2 appliances".
        """
        assert "unit_of_measurement" not in home.values("mismatch")

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
            assert "Nog open" in message, message
            assert "120 minuten" in message, message
        finally:
            await stop_house(home)
