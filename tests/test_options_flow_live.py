"""De wizard en het opslaan van dezelfde invoer, in een echte Home Assistant.

The wizard and saving the same input twice, in a real Home Assistant."""

from __future__ import annotations

from typing import Any

import pytest
from harness_live import (
    start_bare_house,
    start_house,
    stop_house,
)
from live_helpers import (
    ATTIC,
    LIVING,
    cold_one_room,
    simple_installation,
)

from custom_components.climate_director.const import CONF_INSTALLATION, DOMAIN

pytest_plugins = ["live_fixtures"]
pytestmark = pytest.mark.usefixtures("appliance")


class TestBuildingAnInstallationInTheWizard:
    """Van een leeg formulier naar een draaiende installatie.

    From an empty form to a running installation.
    """

    async def test_the_config_flow_creates_an_empty_installation(self) -> None:
        hass = await start_bare_house(states=cold_one_room())
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
        home = await start_house(simple_installation(), states=cold_one_room())
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
        home = await start_bare_house(states=cold_one_room())
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
        home = await start_bare_house(states=cold_one_room())
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
        home = await start_house({"zones": []}, states=cold_one_room())
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
        home = await start_house(simple_installation(), states=cold_one_room())
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
        home = await start_house(simple_installation(), states=cold_one_room())
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
                    "sleep_entity": "sensor.nancy_lader",
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
        home = await start_house({"zones": []}, states=cold_one_room())
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
        home = await start_house(installation, states=cold_one_room())
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
        home = await start_house(simple_installation(), states=cold_one_room())
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
        home = await start_house(simple_installation(), states=cold_one_room())
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

    async def test_the_settings_step_refuses_a_season_entity_source_without_an_entity(self) -> None:
        """Het scherm weigert een seizoen dat nooit te lezen valt (M2).

        De herkomst op *entiteit* zonder gekozen entiteit laat het seizoen
        onbekend, en dan doet elke taak met een seizoensbeperking niets. Dit
        scherm is de enige plek waar de gebruiker dat recht kan zetten, dus het
        hoort te weigeren in plaats van het stil op te slaan.

        The screen refuses a season that can never be read (M2). The source on
        *entity* with no entity chosen leaves the season unknown, and then every
        duty with a season restriction does nothing. This screen is the only
        place the user can put it right, so it should refuse rather than store it
        quietly.
        """
        home = await start_house(simple_installation(), states=cold_one_room())
        try:
            flow = home.hass.config_entries.options
            result = await flow.async_init(home.entry.entry_id)
            result = await flow.async_configure(result["flow_id"], {"next_step_id": "settings"})
            assert result["step_id"] == "settings"

            fields = {str(key): key for key in result["data_schema"].schema}
            filled: dict[str, Any] = {}
            # `season_entity` bewust niet ingevuld: het schema weigert een lege
            # string al ("geen geldige entiteit"), dus de gebruiker die niets
            # kiest stuurt het veld helemaal niet mee - en juist die weg moet dit
            # scherm zelf afvangen.
            #
            # `season_entity` deliberately left unfilled: the schema already
            # refuses an empty string ("not a valid entity"), so a user who picks
            # nothing does not send the field at all - and that is the route this
            # screen has to catch itself.
            for name in fields:
                if name == "season_source":
                    filled[name] = "entity"
                elif name == "season_entity":
                    continue
                elif name == "when_done":
                    filled[name] = "keep"

            result = await flow.async_configure(result["flow_id"], filled)
            assert result["step_id"] == "settings", "het scherm hoort terug te komen"
            assert result["errors"] == {"season_entity": "season_entity_missing"}
            stored = home.entry.options["installation"].get("seasons", {})
            assert stored.get("source") != "entity", "er is niets opgeslagen"
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
        home = await start_house(installation, states=cold_one_room())
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
                "name": "Raam",
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
