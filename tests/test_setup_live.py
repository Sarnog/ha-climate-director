"""Opzetten en verwijderen van een installatie in een echte Home Assistant.

Setting up and removing an installation in a real Home Assistant."""

from __future__ import annotations

import pathlib
from typing import Any

import pytest
from harness_live import (
    LiveHome,
    settings,
    source,
    start_house,
    stop_house,
    zone,
)
from homeassistant.helpers.storage import Store
from live_helpers import (
    ATTIC,
    BOILER,
    LIVING,
    SPARE,
    cold_one_room,
    cold_two_rooms,
    simple_installation,
    two_zone_installation,
)

from custom_components.climate_director.const import CONF_INSTALLATION, STORAGE_VERSION
from custom_components.climate_director.coordinator import storage_key

pytest_plugins = ["live_fixtures"]
pytestmark = pytest.mark.usefixtures("appliance")


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
            two_zone_installation(
                generators=[{"generator_id": "cv", "name": "CV", "entity_id": BOILER}]
            ),
            states={**cold_two_rooms(), BOILER: ("off", {"temperature": 19.0})},
        )
        try:
            assert f"command_{BOILER}" in live.registered()
        finally:
            await stop_house(live)

    async def test_a_hand_at_a_shared_boiler_is_noticed(self) -> None:
        """Wie de ketel bij het toestel uitzet, wordt niet meteen overstemd.

        Whoever switches the boiler off at the appliance is not overruled at
        once.
        """
        live = await start_house(
            two_zone_installation(
                generators=[{"generator_id": "cv", "name": "CV", "entity_id": BOILER}]
            ),
            states={**cold_two_rooms(), BOILER: ("off", {"temperature": 19.0})},
        )
        try:
            assert live.state(BOILER) == "heat"
            live.set(BOILER, "off", hvac_modes=["heat", "off"])
            await live.settle()
            await live.evaluate()
            assert live.state(BOILER) == "off", "de director zet de ketel meteen weer aan"
            assert "woonkamer" in live.coordinator._handed_back
            assert "zolder" in live.coordinator._handed_back
        finally:
            await stop_house(live)

    async def test_no_two_entities_share_a_unique_id(self, home: LiveHome) -> None:
        registered = home.registered()
        assert len(registered) == len(set(registered.values()))

    @pytest.mark.parametrize("with_second_zone", [False, True], ids=["een_zone", "twee_zones"])
    @pytest.mark.parametrize(
        "with_generator", [False, True], ids=["zonder_generator", "met_generator"]
    )
    async def test_every_registered_key_is_a_wanted_key(
        self, with_second_zone: bool, with_generator: bool
    ) -> None:
        """De opruiming wist nooit een entiteit die een platform wél aanmaakt.

        `_async_remove_stale_entities` verwijdert elke sleutel die niet in
        `_wanted_entity_keys` staat. Vergeet iemand ooit één sleutel in die
        verzameling, dan wist de opruiming die entiteit bij élke start — met
        zijn bewaarde stand erbij. Deze test legt de verzameling daarom naast
        het echte entiteitenregister, over vier installaties.

        The cleanup never wipes an entity a platform actually creates.

        `_async_remove_stale_entities` removes every key not in
        `_wanted_entity_keys`. Were a key ever forgotten from that set, the
        cleanup would wipe that entity on every start — stored state included.
        This test therefore holds the set against the real entity registry,
        across four installations.
        """
        from custom_components.climate_director import _wanted_entity_keys

        if with_second_zone:
            house: dict[str, Any] = two_zone_installation()
        else:
            house = {
                "zones": [
                    zone(
                        "woonkamer",
                        sources=[source("kraan", "climate.kraan", role="heat_only")],
                        heat=settings(21.0, 20.0),
                    )
                ]
            }
        states: dict[str, tuple[str, dict[str, Any]]]
        if with_second_zone:
            states = cold_two_rooms()
        else:
            states = {
                "sensor.woonkamer": ("18.0", {}),
                "climate.kraan": ("off", {"temperature": 19.0}),
            }
        if with_generator:
            house["generators"] = [{"generator_id": "cv", "name": "CV", "entity_id": BOILER}]
            states = {**states, BOILER: ("off", {"temperature": 19.0})}

        live = await start_house(house, states=states)
        try:
            wanted = _wanted_entity_keys(live.entry.runtime_data.config)
            registered = set(live.registered())
            assert registered == wanted, (
                f"alleen in het register: {sorted(registered - wanted)}; "
                f"alleen gewenst: {sorted(wanted - registered)}"
            )
        finally:
            await stop_house(live)

    async def test_a_removed_zone_leaves_no_entities_behind(self, home: LiveHome) -> None:
        """Zes entiteiten per zone, en een verwijderde zone ruimt ze alle zes op.

        Six entities per zone, and a removed zone clears all six away.
        """
        from custom_components.climate_director.const import (
            CONF_SHADOW_MODE,
        )

        before = home.registered()
        assert {"zone_woonkamer_blocked", "zone_zolder_blocked"} <= set(before)

        single = two_zone_installation()
        single["zones"] = [single["zones"][0]]
        home.hass.config_entries.async_update_entry(
            home.entry,
            options={CONF_INSTALLATION: single, CONF_SHADOW_MODE: False},
        )
        assert await home.hass.config_entries.async_reload(home.entry.entry_id)
        await home.hass.async_block_till_done()

        after = home.registered()
        suffixes = ("_override", "_priority", "_precondition", "_source", "_blocked", "_fallback")
        for suffix in suffixes:
            assert f"zone_zolder{suffix}" not in after, suffix
        assert "zone_woonkamer_blocked" in after

    async def test_a_removed_appliance_leaves_no_command_sensor_behind(self) -> None:
        """Een verwijderde bron of gedeelde warmtebron ruimt zijn commando-sensor op.

        A removed source or shared heat source clears its command sensor away.
        """

        live = await start_house(
            two_zone_installation(
                generators=[{"generator_id": "cv", "name": "CV", "entity_id": BOILER}]
            ),
            states={**cold_two_rooms(), BOILER: ("off", {"temperature": 19.0})},
        )
        try:
            before = live.registered()
            assert f"command_{SPARE}" in before
            assert f"command_{BOILER}" in before

            options = dict(live.entry.options)
            data = dict(options[CONF_INSTALLATION])
            data["zones"] = [
                {**data["zones"][0], "sources": [data["zones"][0]["sources"][0]]},
                data["zones"][1],
            ]
            data["generators"] = []
            options[CONF_INSTALLATION] = data
            live.hass.config_entries.async_update_entry(live.entry, options=options)
            assert await live.hass.config_entries.async_reload(live.entry.entry_id)
            await live.hass.async_block_till_done()

            after = live.registered()
            assert f"command_{SPARE}" not in after
            assert f"command_{BOILER}" not in after
            assert f"command_{LIVING}" in after
        finally:
            await stop_house(live)

    async def test_a_refusing_platform_still_stops_the_coordinator(
        self, home: LiveHome, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Weigert een platform, dan stopt de coordinator tóch — anders blijft hij draaien.

        When a platform refuses, the coordinator still stops — otherwise it keeps running.
        """
        from custom_components.climate_director import async_unload_entry

        async def _refuse(*_args: object, **_kwargs: object) -> bool:
            return False

        monkeypatch.setattr(home.hass.config_entries, "async_unload_platforms", _refuse)
        assert await async_unload_entry(home.hass, home.entry) is False
        assert home.coordinator._closing is True

    async def test_the_stuck_sensor_reads_through_the_public_reader(
        self, home: LiveHome, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """De sensor hangt aan de publieke lezer, niet aan het privéveld.

        The sensor hangs off the public reader, not the private field.
        """
        monkeypatch.setattr(home.coordinator, "unusable_latest", lambda: {"sensor.via_reader": "x"})
        home.coordinator._unusable_latest = {"sensor.via_private": "y"}
        await home.evaluate()
        assert home.values("stuck")["unusable_entities"] == {"sensor.via_reader": "x"}

    async def test_a_throwing_notice_still_publishes_the_plan(
        self, home: LiveHome, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Gooit een melding, dan wordt het plan tóch gepubliceerd.

        When a notice raises, the plan is still published.
        """

        def _boom(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("kapot")

        monkeypatch.setattr(home.coordinator, "_fire_events", _boom)
        before = home.coordinator.data
        with pytest.raises(RuntimeError):
            await home.evaluate()
        assert home.coordinator.data is not None
        assert home.coordinator.data is not before

    async def test_the_actions_are_registered(self, home: LiveHome) -> None:
        available = home.hass.services.async_services().get("climate_director", {})
        assert set(available) == {
            "evaluate",
            "precondition",
            "cancel_precondition",
            "set_override",
            "clear_override",
        }

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


class TestRemovingAnInstallation:
    """Wie een installatie weggooit, laat niets achter.

    Removing an installation leaves nothing behind.
    """

    async def test_the_stored_state_goes_with_it(self) -> None:
        """Het opslagbestand hangt aan de entry en niets anders leest het.

        Bleef het staan, dan verzamelde `.storage` een bestand per verwijderde
        installatie dat nooit meer opengaat: een nieuwe installatie krijgt een
        nieuwe entry_id en pakt het dus niet op.

        The storage file belongs to the entry and nothing else reads it. Left
        behind, `.storage` collected a file per removed installation that never
        opens again: a new installation gets a new entry_id and so never picks
        it up.
        """
        home = await start_house(simple_installation(), states=cold_one_room())
        try:
            key = storage_key(home.entry.entry_id)
            await Store(home.hass, STORAGE_VERSION, key).async_save({"until": {}, "bypass": []})
            path = pathlib.Path(home.config_dir) / ".storage" / key
            assert path.exists()

            await home.hass.config_entries.async_remove(home.entry.entry_id)
            await home.hass.async_block_till_done()

            assert not path.exists()
        finally:
            await stop_house(home)
