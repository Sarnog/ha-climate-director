"""De wizard, de herstart en de meldingen, in een echte Home Assistant.

The wizard, the restart and the notices, inside a real Home Assistant.

Dit is het stuk dat een gebruiker als eerste tegenkomt en dat het lastigst na te
bouwen is: het scherm waarin de installatie gebouwd wordt, de standen die een
herstart moeten overleven, en de reparatiemelding die vertelt dat er iets niet
klopt. Hier gaat alles door de echte flow-machinerie van Home Assistant heen -
dus ook de schema's, de menu's en het opnieuw laden van de entry.

This is the part a user meets first and that is hardest to rebuild: the screen
the installation is built in, the states that have to survive a restart, and the
repair notice saying something is wrong. Everything here goes through Home
Assistant's real flow machinery - so the schemas, the menus and the reloading of
the entry as well.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest
from harness_live import (
    LiveHome,
    new_config_dir,
    settings,
    source,
    start_bare_house,
    start_house,
    stop_house,
    zone,
)
from homeassistant.helpers.storage import Store

from custom_components.climate_director.const import CONF_INSTALLATION, DOMAIN, STORAGE_VERSION
from custom_components.climate_director.coordinator import storage_key

LIVING = "climate.woonkamer"
ATTIC = "climate.zolder"


def simple_installation() -> dict[str, Any]:
    """Return a one-room installation that wants heat."""
    return {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("airco", LIVING, role="heat_cool")],
                heat=settings(21.0, 20.0),
            )
        ]
    }


def cold() -> dict[str, tuple[str, dict[str, Any]]]:
    """Return a cold room and an idle appliance."""
    return {"sensor.woonkamer": ("18.0", {}), LIVING: ("off", {})}


@pytest.fixture(params=["obedient", "stubborn"], autouse=True)
def appliance(request, monkeypatch):
    """Run every test against both appliance kinds the harness knows."""
    import harness_live

    monkeypatch.setattr(harness_live, "DEFAULT_APPLIANCE", request.param)


# ---------------------------------------------------------------------------
# De wizard.
# The wizard.
# ---------------------------------------------------------------------------


class TestBuildingAnInstallationInTheWizard:
    """Van een leeg formulier naar een draaiende installatie.

    From an empty form to a running installation.
    """

    async def test_the_config_flow_creates_an_empty_installation(self) -> None:
        hass = await start_bare_house(states=cold())
        try:
            result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
            assert result["type"] == "form"
            assert result["step_id"] == "user"

            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {"name": "Tweede huis", "shadow_mode": True}
            )
            await hass.async_block_till_done()

            assert result["type"] == "create_entry"
            assert result["title"] == "Tweede huis"
            assert result["options"][CONF_INSTALLATION] == {}
            assert result["options"]["shadow_mode"] is True
        finally:
            await hass.async_stop()

    async def test_a_second_installation_is_refused(self) -> None:
        """Eén installatie per huis: een tweede aanmelding wordt geweigerd.

        Twee installaties op dezelfde apparaten zouden elke ronde allebei een
        commando aan hetzelfde apparaat geven - precies de toestand waarvan het
        ontwerp zegt dat hij nooit voorkomt. Het manifest zegt daarom
        `single_config_entry`, en Home Assistant weigert de tweede.

        One installation per house: a second sign-up is refused. Two
        installations on the same appliances would both command the same
        appliance every round - exactly the state the design says never occurs.
        The manifest therefore says `single_config_entry`, and Home Assistant
        refuses the second.
        """
        home = await start_house(simple_installation(), states=cold())
        try:
            result = await home.hass.config_entries.flow.async_init(
                DOMAIN, context={"source": "user"}
            )
            assert result["type"] == "abort"
            assert result["reason"] == "single_instance_allowed"
        finally:
            await stop_house(home)

    async def test_an_empty_name_is_refused(self) -> None:
        """Een installatie zonder naam maakt naamloze entiteiten.

        An installation without a name makes nameless entities.

        `vol.Required` eist alleen dat het veld er is, niet dat er iets in staat.
        Een lege naam werd dus gewoon de titel, en die titel staat voor de naam
        van elke entiteit die deze integratie aanmaakt.

        `vol.Required` only demands the field is there, not that it holds
        anything. An empty name simply became the title, and that title precedes
        the name of every entity this integration creates.
        """
        home = await start_bare_house(states=cold())
        try:
            result = await home.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
            result = await home.config_entries.flow.async_configure(
                result["flow_id"], {"name": "   ", "shadow_mode": True}
            )
            assert result["type"] == "form"
            assert result["errors"] == {"name": "required"}
        finally:
            await home.async_stop()

    async def test_the_name_is_stored_without_its_stray_spaces(self) -> None:
        home = await start_bare_house(states=cold())
        try:
            result = await home.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
            result = await home.config_entries.flow.async_configure(
                result["flow_id"], {"name": "  Tweede huis  ", "shadow_mode": False}
            )
            await home.async_block_till_done()
            assert result["title"] == "Tweede huis"
        finally:
            await home.async_stop()

    async def test_the_options_flow_builds_a_zone_and_the_entry_reloads(self) -> None:
        """Een kamer met een apparaat erbij zetten, opslaan, en er staan entiteiten.

        Adding a room with an appliance, saving, and there stand the entities.
        """
        home = await start_house({"zones": []}, states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await flow.async_init(home.entry.entry_id)
            assert result["type"] == "menu"
            assert "zones" in result["menu_options"]

            result = await flow.async_configure(result["flow_id"], {"next_step_id": "zones"})
            assert result["step_id"] == "zones"

            # "add" is de standaardkeuze in de lijst.
            # "add" is the default choice in the list.
            result = await flow.async_configure(result["flow_id"], {"zone": "add_new"})
            assert result["step_id"] == "zone"

            result = await flow.async_configure(
                result["flow_id"],
                {
                    "name": "Woonkamer",
                    "indoor_sensor": "sensor.woonkamer",
                    "priority": 0,
                    "gate": "household",
                    "presence_state": "on",
                    "enable_heat": True,
                    "heat_target": 21.0,
                    "heat_start_at": 20.0,
                    "heat_hysteresis": 1.0,
                    "enable_cool": False,
                    "cool_target": 23.0,
                    "cool_start_at": 24.0,
                    "cool_hysteresis": 1.0,
                    "cool_summer_only": True,
                    "delete": False,
                    "when_done": "keep",
                },
            )
            assert result["step_id"] == "sources"

            result = await flow.async_configure(result["flow_id"], {"source": "add_new"})
            assert result["step_id"] == "source"

            result = await flow.async_configure(
                result["flow_id"],
                {
                    "entity_id": LIVING,
                    "role": "heat_cool",
                    "autostart": True,
                    "priority": 0,
                    "delete": False,
                    "when_done": "keep",
                },
            )
            assert result["step_id"] == "sources"

            result = await flow.async_configure(result["flow_id"], {"source": "back_to_menu"})
            assert result["type"] == "menu"

            result = await flow.async_configure(result["flow_id"], {"next_step_id": "save"})
            await home.hass.async_block_till_done()
            assert result["type"] == "create_entry"

            stored = home.entry.options[CONF_INSTALLATION]
            assert [item["zone_id"] for item in stored["zones"]] == ["woonkamer"]
            assert stored["zones"][0]["sources"][0]["entity_id"] == LIVING

            # En de installatie draait meteen: de kamer is koud.
            # And the installation runs at once: the room is cold.
            assert home.state(LIVING) == "heat"
            assert "zone_woonkamer_source" in home.registered()
        finally:
            await stop_house(home)

    async def test_a_resident_keeps_the_days_of_their_sleep_window(self) -> None:
        """Een weekendritme: de slaapsensor telt alleen op vrijdag en zaterdag.

        Het venster kon al dagen dragen en de poort leest ze uit, maar het
        formulier vroeg er niet naar - dus stond er nooit iets in.

        A weekend rhythm: the sleep sensor only counts on Friday and Saturday.
        The window could already carry days and the gate reads them, but the
        form never asked for any - so nothing was ever in there.
        """
        home = await start_house(simple_installation(), states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await flow.async_init(home.entry.entry_id)
            result = await flow.async_configure(result["flow_id"], {"next_step_id": "residents"})
            assert result["step_id"] == "residents"

            result = await flow.async_configure(result["flow_id"], {"resident": "add_new"})
            assert result["step_id"] == "resident"

            result = await flow.async_configure(
                result["flow_id"],
                {
                    "name": "Danny",
                    "presence_entity": "person.danny",
                    "sleep_entity": "binary_sensor.danny_slaapt",
                    "sleep_state": "on",
                    "sleep_from": "23:00:00",
                    "sleep_until": "09:00:00",
                    "sleep_days": ["4", "5"],
                    "delete": False,
                    "when_done": "keep",
                },
            )
            assert result["step_id"] == "windows"

            result = await flow.async_configure(result["flow_id"], {"window": "back_to_menu"})
            result = await flow.async_configure(result["flow_id"], {"next_step_id": "save"})
            await home.hass.async_block_till_done()
            assert result["type"] == "create_entry"

            stored = home.entry.options[CONF_INSTALLATION]["residents"][0]
            assert stored["sleep_window"] == {
                "start": "23:00:00",
                "end": "09:00:00",
                "weekdays": [4, 5],
            }
        finally:
            await stop_house(home)

    async def test_a_sleep_window_without_days_stays_every_day(self) -> None:
        """Niets aangevinkt betekent elke dag, niet nooit."""
        home = await start_house(simple_installation(), states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await flow.async_init(home.entry.entry_id)
            result = await flow.async_configure(result["flow_id"], {"next_step_id": "residents"})
            result = await flow.async_configure(result["flow_id"], {"resident": "add_new"})
            result = await flow.async_configure(
                result["flow_id"],
                {
                    "name": "Nancy",
                    "presence_entity": "person.nancy",
                    "sleep_state": "on",
                    "sleep_from": "22:00:00",
                    "sleep_until": "08:00:00",
                    "delete": False,
                    "when_done": "keep",
                },
            )
            result = await flow.async_configure(result["flow_id"], {"window": "back_to_menu"})
            result = await flow.async_configure(result["flow_id"], {"next_step_id": "save"})
            await home.hass.async_block_till_done()

            stored = home.entry.options[CONF_INSTALLATION]["residents"][0]
            assert stored["sleep_window"]["weekdays"] is None
        finally:
            await stop_house(home)

    async def test_a_zone_without_a_sensor_is_refused_at_the_screen(self) -> None:
        home = await start_house({"zones": []}, states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await flow.async_init(home.entry.entry_id)
            result = await flow.async_configure(result["flow_id"], {"next_step_id": "zones"})
            result = await flow.async_configure(result["flow_id"], {"zone": "add_new"})
            result = await flow.async_configure(
                result["flow_id"],
                {
                    "name": "Zolder",
                    "priority": 0,
                    "gate": "household",
                    "presence_state": "on",
                    "enable_heat": True,
                    "heat_target": 21.0,
                    "heat_start_at": 20.0,
                    "heat_hysteresis": 1.0,
                    "enable_cool": False,
                    "cool_target": 23.0,
                    "cool_start_at": 24.0,
                    "cool_hysteresis": 1.0,
                    "cool_summer_only": True,
                    "delete": False,
                    "when_done": "keep",
                },
            )
            assert result["step_id"] == "zone"
            assert result["errors"], "zonder kamersensor hoort het scherm te klagen"
        finally:
            await stop_house(home)

    async def test_the_quiet_window_screen_keeps_the_holiday_flag(self) -> None:
        """Een stiltevenster met vakantievlag verliest hem niet in het scherm.

        A quiet window with the holiday flag does not lose it in the screen.
        """
        installation = {
            **simple_installation(),
            "gates": {
                "quiet_windows": [
                    {"start": "22:00:00", "end": "07:00:00", "weekdays": None, "holiday": True}
                ]
            },
        }
        home = await start_house(installation, states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await flow.async_init(home.entry.entry_id)
            result = await flow.async_configure(result["flow_id"], {"next_step_id": "quiets"})
            assert result["step_id"] == "quiets"
            result = await flow.async_configure(result["flow_id"], {"quiet": "0"})
            assert result["step_id"] == "quiet"
            result = await flow.async_configure(
                result["flow_id"],
                {
                    "start": "22:00:00",
                    "end": "07:00:00",
                    "holiday": True,
                    "delete": False,
                    "when_done": "keep",
                },
            )
            assert result["step_id"] == "quiets"
            result = await flow.async_configure(result["flow_id"], {"quiet": "back_to_menu"})
            result = await flow.async_configure(result["flow_id"], {"next_step_id": "save"})
            if result["type"] == "form":
                result = await flow.async_configure(result["flow_id"], {"when_done": "keep"})
            assert result["type"] == "create_entry"
            await home.hass.async_block_till_done()
            stored = home.entry.options[CONF_INSTALLATION]
            assert stored["gates"]["quiet_windows"][0]["holiday"] is True
        finally:
            await stop_house(home)

    async def test_the_settings_step_writes_the_shadow_mode_through(self) -> None:
        home = await start_house(simple_installation(), states=cold())
        try:
            assert home.coordinator.shadow is False
            flow = home.hass.config_entries.options
            result = await flow.async_init(home.entry.entry_id)
            result = await flow.async_configure(result["flow_id"], {"next_step_id": "settings"})
            assert result["step_id"] == "settings"

            fields = {str(key): key for key in result["data_schema"].schema}
            filled: dict[str, Any] = {}
            for name in fields:
                if name == "shadow_mode":
                    filled[name] = True
                elif name == "when_done":
                    filled[name] = "keep"

            result = await flow.async_configure(result["flow_id"], filled)
            result = await flow.async_configure(result["flow_id"], {"next_step_id": "save"})
            await home.hass.async_block_till_done()

            assert home.entry.options["shadow_mode"] is True
            assert home.coordinator.shadow is True, "de herlaadbeurt hoort de stand mee te nemen"
        finally:
            await stop_house(home)

    async def test_the_settings_step_writes_the_hemisphere_through(self) -> None:
        home = await start_house(simple_installation(), states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await flow.async_init(home.entry.entry_id)
            result = await flow.async_configure(result["flow_id"], {"next_step_id": "settings"})
            assert result["step_id"] == "settings"

            fields = {str(key): key for key in result["data_schema"].schema}
            filled: dict[str, Any] = {}
            for name in fields:
                if name == "hemisphere":
                    filled[name] = "south"
                elif name == "when_done":
                    filled[name] = "keep"

            result = await flow.async_configure(result["flow_id"], filled)
            result = await flow.async_configure(result["flow_id"], {"next_step_id": "save"})
            await home.hass.async_block_till_done()

            stored = home.entry.options["installation"]["seasons"]
            assert stored["summer_months"] == [1, 2, 3, 10, 11, 12]
        finally:
            await stop_house(home)

    async def test_a_full_settings_save_keeps_optional_fields(self) -> None:
        """De echte interface stuurt voorgevulde selectors mee; die horen te overleven.

        The real frontend submits pre-filled selectors; those should survive.
        """
        installation = {
            **simple_installation(),
            "outdoor_sensor": "sensor.buiten",
            "precipitation": {
                "source": "weather.buienradar",
                "states": ["rainy", "pouring"],
                "grace": 900,
            },
        }
        home = await start_house(installation, states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await flow.async_init(home.entry.entry_id)
            result = await flow.async_configure(result["flow_id"], {"next_step_id": "settings"})

            # Zoals de echte frontend: de voorgevulde optionele selectors worden
            # meegestuurd, de rest blijft op zijn standaard.
            #
            # As the real frontend does: the pre-filled optional selectors are
            # submitted, the rest stays on its default.
            result = await flow.async_configure(
                result["flow_id"],
                {
                    "shadow_mode": True,
                    "when_done": "keep",
                    "outdoor_sensor": "sensor.buiten",
                    "precipitation_source": "weather.buienradar",
                },
            )
            result = await flow.async_configure(result["flow_id"], {"next_step_id": "save"})
            await home.hass.async_block_till_done()

            stored = home.entry.options["installation"]
            assert stored["outdoor_sensor"] == "sensor.buiten"
            assert stored["precipitation"] == {
                "source": "weather.buienradar",
                "states": ["pouring", "rainy"],
                "grace": 900,
            }
        finally:
            await stop_house(home)


# ---------------------------------------------------------------------------
# Elk scherm twee keer met identieke invoer.
# Every screen twice with identical input.
# ---------------------------------------------------------------------------


class TestSavingTheSameInputTwice:
    """De spiegel van de kruistest: scherm A twee keer in plaats van A naast B.

    The mirror of the cross test: screen A twice instead of A next to B.
    """

    async def _add_zone(self, flow, entry_id: str, name: str, sensor: str, entity_id: str) -> None:
        result = await flow.async_init(entry_id)
        result = await flow.async_configure(result["flow_id"], {"next_step_id": "zones"})
        result = await flow.async_configure(result["flow_id"], {"zone": "add_new"})
        result = await flow.async_configure(
            result["flow_id"],
            {
                "name": name,
                "indoor_sensor": sensor,
                "priority": 0,
                "gate": "household",
                "presence_state": "on",
                "enable_heat": True,
                "heat_target": 21.0,
                "heat_start_at": 20.0,
                "heat_hysteresis": 1.0,
                "enable_cool": False,
                "cool_target": 23.0,
                "cool_start_at": 24.0,
                "cool_hysteresis": 1.0,
                "cool_summer_only": True,
                "delete": False,
                "when_done": "keep",
            },
        )
        assert result["step_id"] == "sources"
        result = await flow.async_configure(result["flow_id"], {"source": "add_new"})
        result = await flow.async_configure(
            result["flow_id"],
            {
                "entity_id": entity_id,
                "role": "heat_only",
                "autostart": True,
                "priority": 0,
                "delete": False,
                "when_done": "keep",
            },
        )
        result = await flow.async_configure(result["flow_id"], {"source": "back_to_menu"})
        result = await flow.async_configure(result["flow_id"], {"next_step_id": "save"})
        if result["type"] == "form":
            result = await flow.async_configure(result["flow_id"], {"when_done": "keep"})
        assert result["type"] == "create_entry"

    async def _add_circuit(self, flow, entry_id: str, name: str, units: list[str]) -> None:
        result = await flow.async_init(entry_id)
        result = await flow.async_configure(result["flow_id"], {"next_step_id": "circuits"})
        result = await flow.async_configure(result["flow_id"], {"circuit": "add_new"})
        result = await flow.async_configure(
            result["flow_id"],
            {
                "name": name,
                "units": units,
                "simultaneous_heat_cool": False,
                "conflict_policy": "priority",
                "allow_fan_only_during_conflict": False,
                "family_switch_delay": 0,
                "min_family_switch_interval": 0,
                "min_cycle_time": 180,
                "delete": False,
                "when_done": "keep",
            },
        )
        assert result["step_id"] == "circuit_priorities"
        result = await flow.async_configure(result["flow_id"], {"zone": "back_to_menu"})
        result = await flow.async_configure(result["flow_id"], {"next_step_id": "save"})
        if result["type"] == "form":
            result = await flow.async_configure(result["flow_id"], {"when_done": "keep"})
        assert result["type"] == "create_entry"

    async def _add_resident(self, flow, entry_id: str, name: str, presence: str) -> None:
        result = await flow.async_init(entry_id)
        result = await flow.async_configure(result["flow_id"], {"next_step_id": "residents"})
        result = await flow.async_configure(result["flow_id"], {"resident": "add_new"})
        result = await flow.async_configure(
            result["flow_id"],
            {
                "name": name,
                "presence_entity": presence,
                "sleep_entity": "binary_sensor.slaapt",
                "sleep_state": "on",
                "sleep_from": "23:00:00",
                "sleep_until": "09:00:00",
                "delete": False,
                "when_done": "keep",
            },
        )
        assert result["step_id"] == "windows"
        result = await flow.async_configure(result["flow_id"], {"window": "back_to_menu"})
        result = await flow.async_configure(result["flow_id"], {"next_step_id": "save"})
        if result["type"] == "form":
            result = await flow.async_configure(result["flow_id"], {"when_done": "keep"})
        assert result["type"] == "create_entry"

    async def _add_quiet(self, flow, entry_id: str) -> None:
        result = await flow.async_init(entry_id)
        result = await flow.async_configure(result["flow_id"], {"next_step_id": "quiets"})
        result = await flow.async_configure(result["flow_id"], {"quiet": "add_new"})
        result = await flow.async_configure(
            result["flow_id"],
            {"start": "22:00:00", "end": "07:00:00", "delete": False, "when_done": "keep"},
        )
        assert result["step_id"] == "quiets"
        result = await flow.async_configure(result["flow_id"], {"quiet": "back_to_menu"})
        result = await flow.async_configure(result["flow_id"], {"next_step_id": "save"})
        if result["type"] == "form":
            result = await flow.async_configure(result["flow_id"], {"when_done": "keep"})
        assert result["type"] == "create_entry"

    async def _add_opening(self, flow, entry_id: str) -> None:
        result = await flow.async_init(entry_id)
        result = await flow.async_configure(result["flow_id"], {"next_step_id": "openings"})
        result = await flow.async_configure(result["flow_id"], {"opening": "add_new"})
        result = await flow.async_configure(
            result["flow_id"],
            {
                "entity_id": "binary_sensor.raam",
                "open_state": "on",
                "delay": 0,
                "delete": False,
                "when_done": "keep",
            },
        )
        assert result["type"] == "menu"
        result = await flow.async_configure(result["flow_id"], {"next_step_id": "save"})
        if result["type"] == "form":
            result = await flow.async_configure(result["flow_id"], {"when_done": "keep"})
        assert result["type"] == "create_entry"

    async def test_no_screen_makes_a_duplicate_id_or_entity(self, caplog) -> None:
        """Twee keer dezelfde invoer: geen dubbel ID, geen dubbel entiteitenlog.

        The same input twice: no duplicate id, no duplicate-entity log line.
        """
        states = {
            "sensor.badkamer_boven": ("18.0", {}),
            "sensor.badkamer_beneden": ("18.0", {}),
            LIVING: ("off", {"hvac_modes": ["heat", "off"]}),
            ATTIC: ("off", {"hvac_modes": ["heat", "off"]}),
            "person.danny": ("home", {}),
            "person.nancy": ("home", {}),
        }
        home = await start_house({"zones": []}, states=states)
        try:
            flow = home.hass.config_entries.options
            entry_id = home.entry.entry_id

            await self._add_zone(flow, entry_id, "Badkamer", "sensor.badkamer_boven", LIVING)
            await self._add_zone(flow, entry_id, "Badkamer", "sensor.badkamer_beneden", ATTIC)

            await self._add_circuit(flow, entry_id, "Multi-split", [LIVING])
            await self._add_circuit(flow, entry_id, "Multi-split", [ATTIC])

            await self._add_resident(flow, entry_id, "Bewoner", "person.danny")
            await self._add_resident(flow, entry_id, "Bewoner", "person.nancy")

            await self._add_quiet(flow, entry_id)
            await self._add_quiet(flow, entry_id)

            await self._add_opening(flow, entry_id)
            await self._add_opening(flow, entry_id)

            await home.hass.async_block_till_done()
            stored = home.entry.options[CONF_INSTALLATION]

            zone_ids = [item["zone_id"] for item in stored["zones"]]
            assert len(zone_ids) == len(set(zone_ids)) == 2, zone_ids
            circuit_ids = [item["circuit_id"] for item in stored["circuits"]]
            assert len(circuit_ids) == len(set(circuit_ids)) == 2, circuit_ids
            resident_ids = [item["resident_id"] for item in stored["residents"]]
            assert len(resident_ids) == len(set(resident_ids)) == 2, resident_ids
            assert len(stored["gates"]["quiet_windows"]) == 2
            assert len(stored["openings"]) == 2

            entity_ids = [item.entity_id for item in home.hass.states.async_all()]
            assert len(entity_ids) == len(set(entity_ids))
            assert "does not generate unique IDs" not in caplog.text
        finally:
            await stop_house(home)


# ---------------------------------------------------------------------------
# De reparatiemelding.
# The repair notice.
# ---------------------------------------------------------------------------


class TestTheRepairNotice:
    """Een configuratie die niet klopt hoort in Home Assistant zelf op te vallen.

    A configuration that does not add up should stand out in Home Assistant
    itself.
    """

    def _issues(self, home: LiveHome) -> dict:
        from homeassistant.helpers import issue_registry as ir

        registry = ir.async_get(home.hass)
        return {key: item for key, item in registry.issues.items() if key[0] == DOMAIN}

    async def test_a_sound_installation_raises_nothing(self) -> None:
        home = await start_house(simple_installation(), states=cold())
        try:
            assert self._issues(home) == {}
        finally:
            await stop_house(home)

    async def test_a_zone_without_a_source_is_reported(self) -> None:
        broken = {
            "zones": [
                {
                    "zone_id": "woonkamer",
                    "name": "Woonkamer",
                    "indoor_sensor": "sensor.woonkamer",
                    "sources": [],
                    "heat": settings(21.0, 20.0),
                }
            ]
        }
        home = await start_house(broken, states=cold())
        try:
            issues = self._issues(home)
            assert issues, "hier hoort een reparatiemelding te staan"
            issue = next(iter(issues.values()))
            assert issue.severity == "warning"
            assert issue.translation_key == "invalid_config"
        finally:
            await stop_house(home)

    async def test_the_notice_disappears_once_it_is_fixed(self) -> None:
        broken = {
            "zones": [
                {
                    "zone_id": "woonkamer",
                    "name": "Woonkamer",
                    "indoor_sensor": "",
                    "sources": [source("airco", LIVING)],
                    "heat": settings(21.0, 20.0),
                }
            ]
        }
        home = await start_house(broken, states=cold())
        try:
            assert self._issues(home)

            home.hass.config_entries.async_update_entry(
                home.entry, options={**home.entry.options, CONF_INSTALLATION: simple_installation()}
            )
            await home.hass.async_block_till_done()
            assert self._issues(home) == {}
        finally:
            await stop_house(home)


# ---------------------------------------------------------------------------
# Wat een herstart moet overleven.
# What has to survive a restart.
# ---------------------------------------------------------------------------


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
        home = await start_house(simple_installation(), states=cold())
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


class TestAcrossARestart:
    """Standen die een gebruiker zette horen na een herstart nog te staan.

    States a user set should still stand after a restart.
    """

    async def test_the_master_switch_stays_off(self) -> None:
        config_dir = new_config_dir()
        home = await start_house(
            simple_installation(), states=cold(), entry_id="herstart", config_dir=config_dir
        )
        try:
            assert home.state(LIVING) == "heat"
            await home.call("switch", "turn_off", {"entity_id": home.by_key("master")})
            await home.evaluate()
            # Noodknop: de director stuurt niets, dus de airco blijft draaien.
            # Emergency stop: the director sends nothing, so the airco keeps running.
            assert home.state(LIVING) == "heat"
        finally:
            await stop_house(home)

        again = await start_house(
            simple_installation(), states=cold(), entry_id="herstart", config_dir=config_dir
        )
        try:
            assert again.value("master") == "off", "de hoofdschakelaar hoort uit te blijven"
            # Ook na een herstart stuurt de noodknop niets: het apparaat blijft
            # zoals het opgestart is.
            # After a restart too the emergency stop sends nothing: the appliance
            # stays as it started up.
            assert again.state(LIVING) == "off"
            assert not again.climate_calls(), "een uitgezette noodknop hoort niets te sturen"
        finally:
            await stop_house(again)

    async def test_a_priority_set_by_an_automation_comes_back(self) -> None:
        config_dir = new_config_dir()
        installation = {
            "zones": [
                zone(
                    "woonkamer",
                    sources=[source("airco", LIVING, role="heat_cool")],
                    heat=settings(21.0, 20.0),
                    priority=0,
                ),
                zone(
                    "zolder",
                    sources=[source("airco2", ATTIC, role="heat_cool")],
                    heat=settings(21.0, 20.0),
                    priority=1,
                ),
            ]
        }
        states = {**cold(), "sensor.zolder": ("18.0", {}), ATTIC: ("off", {})}

        home = await start_house(
            installation, states=states, entry_id="voorrang", config_dir=config_dir
        )
        try:
            await home.call(
                "number",
                "set_value",
                {"entity_id": home.by_key("zone_zolder_priority"), "value": 4},
            )
            await home.settle()
            assert home.coordinator.zone_priorities["zolder"] == 4
        finally:
            await stop_house(home)

        again = await start_house(
            installation, states=states, entry_id="voorrang", config_dir=config_dir
        )
        try:
            assert again.coordinator.zone_priorities["zolder"] == 4, (
                "wat een automatisering zette hoort een herstart te overleven"
            )
        finally:
            await stop_house(again)

    async def test_a_changed_configuration_wins_from_the_restored_priority(self) -> None:
        """Wie in de wizard iets nieuws zegt, overstemt de bewaarde waarde.

        Whoever says something new in the wizard overrules the stored value.
        """
        from custom_components.climate_director.number import resolve_initial

        assert resolve_initial(configured=2, last_value=4, last_configured=2) == 4
        assert resolve_initial(configured=3, last_value=4, last_configured=2) == 3
        assert resolve_initial(configured=3, last_value=None, last_configured=None) == 3


# ---------------------------------------------------------------------------
# Een kapot opslagbestand mag de director niet stilleggen.
# A broken storage file must not silence the director.
# ---------------------------------------------------------------------------


def _write_store(config_dir: str, entry_id: str, data: Any) -> pathlib.Path:
    """Write one store file the way Home Assistant's `Store` would."""
    key = storage_key(entry_id)
    store_dir = pathlib.Path(config_dir) / ".storage"
    store_dir.mkdir(parents=True, exist_ok=True)
    path = store_dir / key
    path.write_text(
        json.dumps({"version": 1, "minor_version": 1, "key": key, "data": data}),
        encoding="utf-8",
    )
    return path


class TestAStartupWithBrokenStorage:
    """Het bewaarde werk van een herstart mag nooit het opstarten verhinderen.

    The saved work from a restart must never stop the startup.
    """

    async def test_a_wrong_shaped_stored_state_is_skipped_not_fatal(self) -> None:
        """Velden met een onleesbare vorm worden overgeslagen, de rest draait.

        Fields with an unreadable shape are skipped, the rest just runs.
        """
        config_dir = new_config_dir()
        path = _write_store(
            config_dir,
            "vorm",
            {
                "until": ["geen", "dict"],
                "bypass": 42,
                "handed_back": ["ook", "geen", "dict"],
            },
        )
        home = await start_house(
            simple_installation(), states=cold(), config_dir=config_dir, entry_id="vorm"
        )
        try:
            assert home.state(LIVING) == "heat", "de director hoort gewoon te beslissen"
            assert home.coordinator._clock_reeval_unsub is not None, "de klok hoort te staan"
            assert path.exists(), "een leesbaar bestand met vreemde velden hoort te blijven staan"
        finally:
            await stop_house(home)

    async def test_an_unreadable_stored_state_is_quarantined_and_director_decides(self) -> None:
        """Een bestand dat nergens op lijkt gaat opzij, met melding, en de director draait.

        A file shaped like nothing goes aside, with a notice, and the director runs.
        """
        config_dir = new_config_dir()
        path = _write_store(config_dir, "kapot", [1, 2, 3])
        home = await start_house(
            simple_installation(), states=cold(), config_dir=config_dir, entry_id="kapot"
        )
        try:
            assert home.state(LIVING) == "heat", "de director hoort met een lege staat te beginnen"
            assert home.coordinator._clock_reeval_unsub is not None, "de klok hoort te staan"
            assert not path.exists(), "het onleesbare bestand hoort opzij gezet te zijn"
            assert list(path.parent.glob(path.name + ".corrupt*")), (
                "er hoort een .corrupt-bestand te staan"
            )

            from homeassistant.helpers import issue_registry as ir

            registry = ir.async_get(home.hass)
            assert ("climate_director", "corrupt_storage_kapot") in registry.issues
        finally:
            await stop_house(home)


# ---------------------------------------------------------------------------
# Sensoren in alle vormen die Home Assistant kent.
# Sensors in every shape Home Assistant knows.
# ---------------------------------------------------------------------------


class TestReadingTemperaturesFromAnything:
    """Een kamertemperatuur mag uit een sensor, een weerbericht of een unit komen.

    A room temperature may come from a sensor, a weather forecast or a unit.
    """

    async def test_a_weather_entity_carries_the_outdoor_temperature(self) -> None:
        installation = {
            "zones": [
                zone(
                    "woonkamer",
                    sources=[
                        source(
                            "airco",
                            LIVING,
                            role="heat_cool",
                            outdoor={"maximum": 15.0},
                        )
                    ],
                    heat=settings(21.0, 20.0),
                )
            ],
            "outdoor_sensor": "weather.thuis",
        }
        home = await start_house(
            installation,
            states={**cold(), "weather.thuis": ("rainy", {"temperature": 4.0})},
        )
        try:
            assert home.coordinator.world.outdoor_temperature == 4.0
            assert home.state(LIVING) == "heat"
        finally:
            await stop_house(home)

    async def test_a_climate_entity_may_be_the_room_sensor(self) -> None:
        """Dan telt `current_temperature`, nooit het setpoint.

        Then `current_temperature` counts, never the setpoint.
        """
        installation = {
            "zones": [
                zone(
                    "woonkamer",
                    indoor_sensor=LIVING,
                    sources=[source("airco", LIVING, role="heat_cool")],
                    heat=settings(21.0, 20.0),
                )
            ]
        }
        home = await start_house(
            installation,
            states={LIVING: ("off", {"current_temperature": 17.0, "temperature": 25.0})},
        )
        try:
            assert home.coordinator.world.indoor("woonkamer") == 17.0
            assert home.state(LIVING) == "heat"
        finally:
            await stop_house(home)

    @pytest.mark.parametrize("reading", ["", "unknown", "unavailable", "kapot", "NaN"])
    async def test_an_unreadable_sensor_never_breaks_the_run(self, reading: str) -> None:
        home = await start_house(
            simple_installation(), states={**cold(), "sensor.woonkamer": (reading, {})}
        )
        try:
            assert home.coordinator.data is not None
            assert home.state(LIVING) == "off"
        finally:
            await stop_house(home)
