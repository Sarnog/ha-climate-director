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

from typing import Any

import pytest
from harness_live import (
    LiveHome,
    new_config_dir,
    settings,
    source,
    start_house,
    stop_house,
    zone,
)

from custom_components.climate_director.const import CONF_INSTALLATION, DOMAIN

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


# ---------------------------------------------------------------------------
# De wizard.
# The wizard.
# ---------------------------------------------------------------------------


class TestBuildingAnInstallationInTheWizard:
    """Van een leeg formulier naar een draaiende installatie.

    From an empty form to a running installation.
    """

    async def test_the_config_flow_creates_an_empty_installation(self) -> None:
        home = await start_house(simple_installation(), states=cold())
        try:
            result = await home.hass.config_entries.flow.async_init(
                DOMAIN, context={"source": "user"}
            )
            assert result["type"] == "form"
            assert result["step_id"] == "user"

            result = await home.hass.config_entries.flow.async_configure(
                result["flow_id"], {"name": "Tweede huis", "shadow_mode": True}
            )
            await home.hass.async_block_till_done()

            assert result["type"] == "create_entry"
            assert result["title"] == "Tweede huis"
            assert result["options"][CONF_INSTALLATION] == {}
            assert result["options"]["shadow_mode"] is True
        finally:
            await stop_house(home)

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
            assert home.state(LIVING) == "off"
        finally:
            await stop_house(home)

        again = await start_house(
            simple_installation(), states=cold(), entry_id="herstart", config_dir=config_dir
        )
        try:
            assert again.value("master") == "off", "de hoofdschakelaar hoort uit te blijven"
            assert again.state(LIVING) == "off", "en het huis hoort dus niets te doen"
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
