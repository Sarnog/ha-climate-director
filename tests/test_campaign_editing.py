"""De bewerkingskant van de options flow, scherm voor scherm.

The editing side of the options flow, screen by screen.

De wizard bouwt een installatie op; deze schermen veranderen er daarna iets aan.
Dat is de kant waar een gebruiker het vaakst komt en waar het minst getest was:
circuits, prioriteiten op een circuit, openingen, stiltevensters, gedeelde
warmtebronnen, uitsluitende groepen en de roosters van een bewoner. Alles gaat
hier door de echte flow-machinerie heen, dus ook de schema's, de foutmeldingen
en het opslaan.

The wizard builds an installation; these screens change it afterwards. That is
the side a user visits most often and the one that was tested least: circuits,
priorities on a circuit, openings, quiet windows, shared heat sources, exclusive
groups and a resident's schedules. Everything here goes through the real flow
machinery, so the schemas, the error messages and the saving as well.
"""

from __future__ import annotations

from typing import Any

import pytest
from harness_live import LiveHome, settings, source, start_house, stop_house, zone

from custom_components.climate_director.const import CONF_INSTALLATION

LIVING = "climate.woonkamer"
ATTIC = "climate.zolder"


def two_rooms() -> dict[str, Any]:
    """Return two rooms, each with its own appliance, ready to be edited."""
    return {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("woonkamer_airco", LIVING, role="heat_cool")],
                heat=settings(21.0, 20.0),
                priority=0,
            ),
            zone(
                "zolder",
                sources=[source("zolder_airco", ATTIC, role="heat_cool")],
                heat=settings(20.0, 19.0),
                priority=1,
            ),
        ]
    }


def cold() -> dict[str, tuple[str, dict[str, Any]]]:
    return {
        "sensor.woonkamer": ("18.0", {}),
        "sensor.zolder": ("18.0", {}),
        LIVING: ("off", {}),
        ATTIC: ("off", {}),
    }


async def menu(home: LiveHome, step: str) -> Any:
    """Open the options flow and walk into one menu entry."""
    flow = home.hass.config_entries.options
    result = await flow.async_init(home.entry.entry_id)
    return await flow.async_configure(result["flow_id"], {"next_step_id": step})


async def save(home: LiveHome, flow_id: str) -> dict[str, Any]:
    """Save and hand back the installation as it was stored.

    Ziet de controle iets, dan komt er eerst een waarschuwingsscherm; hier
    wordt dat weggeklikt met "toch opslaan", want deze tests gaan over wat er
    opgeslagen wordt en niet over de controle zelf.

    If the check spots something a warning screen comes first; here it is
    clicked away with "save anyway", since these tests are about what gets
    stored and not about the check itself.
    """
    flow = home.hass.config_entries.options
    result = await flow.async_configure(flow_id, {"next_step_id": "save"})
    if result["type"] == "form":
        assert result["step_id"] == "save"
        result = await flow.async_configure(flow_id, {"when_done": "keep"})
    await home.hass.async_block_till_done()
    assert result["type"] == "create_entry"
    return home.entry.options[CONF_INSTALLATION]


class TestAddingThroughEveryScreen:
    """Alles wat je erbij kunt zetten, komt er ook echt bij te staan.

    Everything that can be added really does end up stored.
    """

    async def test_a_circuit_is_added_with_its_timings(self) -> None:
        home = await start_house(two_rooms(), states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await menu(home, "circuits")
            assert result["step_id"] == "circuits"

            result = await flow.async_configure(result["flow_id"], {"circuit": "add_new"})
            assert result["step_id"] == "circuit"

            result = await flow.async_configure(
                result["flow_id"],
                {
                    "name": "Buitenunit",
                    "units": [LIVING, ATTIC],
                    "simultaneous_heat_cool": False,
                    "conflict_policy": "priority",
                    "allow_fan_only_during_conflict": True,
                    "family_switch_delay": 60,
                    "min_family_switch_interval": 900,
                    "min_cycle_time": 300,
                    "max_concurrent_units": 2,
                    "delete": False,
                    "when_done": "keep",
                },
            )
            # Na een circuit vraagt de flow meteen om de voorrang per kamer.
            # After a circuit the flow asks straight away about per-room priority.
            assert result["step_id"] == "circuit_priorities"

            result = await flow.async_configure(result["flow_id"], {"zone": "back_to_menu"})
            stored = await save(home, result["flow_id"])

            assert len(stored["circuits"]) == 1
            circuit = stored["circuits"][0]
            assert circuit["circuit_id"] == "buitenunit"
            assert circuit["units"] == [LIVING, ATTIC]
            assert circuit["min_cycle_time"] == 300
            assert circuit["max_concurrent_units"] == 2
            assert circuit["allow_fan_only_during_conflict"] is True
        finally:
            await stop_house(home)

    async def test_a_priority_set_from_the_circuit_lands_on_the_zone(self) -> None:
        """De voorrang hoort bij de kamer, maar is ook vanaf het circuit te zetten."""
        home = await start_house(two_rooms(), states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await menu(home, "circuits")
            result = await flow.async_configure(result["flow_id"], {"circuit": "add_new"})
            result = await flow.async_configure(
                result["flow_id"],
                {
                    "name": "Buitenunit",
                    "units": [LIVING, ATTIC],
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

            result = await flow.async_configure(result["flow_id"], {"zone": "zolder"})
            assert result["step_id"] == "circuit_priority"

            result = await flow.async_configure(
                result["flow_id"], {"priority": 3, "when_done": "keep"}
            )
            assert result["step_id"] == "circuit_priorities"

            result = await flow.async_configure(result["flow_id"], {"zone": "back_to_menu"})
            stored = await save(home, result["flow_id"])

            attic = next(item for item in stored["zones"] if item["zone_id"] == "zolder")
            assert attic["priority"] == 3
        finally:
            await stop_house(home)

    async def test_an_opening_is_added_with_its_own_open_state(self) -> None:
        home = await start_house(two_rooms(), states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await menu(home, "openings")
            assert result["step_id"] == "openings"

            result = await flow.async_configure(result["flow_id"], {"opening": "add_new"})
            assert result["step_id"] == "opening"

            result = await flow.async_configure(
                result["flow_id"],
                {
                    "entity_id": "cover.dakraam",
                    "open_state": "open",
                    "zone_ids": ["zolder"],
                    "delay": 120,
                    "delete": False,
                    "when_done": "keep",
                },
            )
            stored = await save(home, result["flow_id"])

            assert stored["openings"] == [
                {
                    "entity_id": "cover.dakraam",
                    "zone_ids": ["zolder"],
                    "open_state": "open",
                    "delay": 120,
                }
            ]
        finally:
            await stop_house(home)

    async def test_a_quiet_window_is_added_with_its_days(self) -> None:
        home = await start_house(two_rooms(), states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await menu(home, "quiets")
            assert result["step_id"] == "quiets"

            result = await flow.async_configure(result["flow_id"], {"quiet": "add_new"})
            assert result["step_id"] == "quiet"

            result = await flow.async_configure(
                result["flow_id"],
                {
                    "start": "21:00:00",
                    "end": "09:00:00",
                    "weekdays": ["0", "1", "2", "3", "6"],
                    "delete": False,
                    "when_done": "keep",
                },
            )
            assert result["step_id"] == "quiets"

            result = await flow.async_configure(result["flow_id"], {"quiet": "back_to_menu"})
            stored = await save(home, result["flow_id"])

            assert stored["gates"]["quiet_windows"] == [
                {
                    "start": "21:00:00",
                    "end": "09:00:00",
                    "weekdays": [0, 1, 2, 3, 6],
                    "holiday": False,
                }
            ]
        finally:
            await stop_house(home)

    async def test_a_shared_heat_source_is_added(self) -> None:
        home = await start_house(two_rooms(), states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await menu(home, "generators")
            assert result["step_id"] == "generators"

            result = await flow.async_configure(result["flow_id"], {"generator": "add_new"})
            assert result["step_id"] == "generator"

            result = await flow.async_configure(
                result["flow_id"],
                {
                    "name": "Ketel",
                    "entity_id": "climate.gas",
                    "zone_ids": ["woonkamer", "zolder"],
                    "setpoint": 21.5,
                    "delete": False,
                    "when_done": "keep",
                },
            )
            stored = await save(home, result["flow_id"])

            assert stored["generators"] == [
                {
                    "generator_id": "ketel",
                    "name": "Ketel",
                    "entity_id": "climate.gas",
                    "zone_ids": ["woonkamer", "zolder"],
                    "setpoint": 21.5,
                }
            ]
        finally:
            await stop_house(home)

    async def test_an_exclusive_group_is_added(self) -> None:
        home = await start_house(two_rooms(), states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await menu(home, "exclusives")
            assert result["step_id"] == "exclusives"

            result = await flow.async_configure(result["flow_id"], {"group": "add_new"})
            assert result["step_id"] == "exclusive"

            result = await flow.async_configure(
                result["flow_id"],
                {
                    "sources": ["woonkamer_airco", "zolder_airco"],
                    "delete": False,
                    "when_done": "keep",
                },
            )
            assert result["step_id"] == "exclusives"

            result = await flow.async_configure(result["flow_id"], {"group": "back_to_menu"})
            stored = await save(home, result["flow_id"])

            assert stored["exclusive_groups"] == [["woonkamer_airco", "zolder_airco"]]
        finally:
            await stop_house(home)

    async def test_a_schedule_window_is_added_to_a_resident(self) -> None:
        home = await start_house(two_rooms(), states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await menu(home, "residents")
            result = await flow.async_configure(result["flow_id"], {"resident": "add_new"})
            result = await flow.async_configure(
                result["flow_id"],
                {
                    "name": "Danny",
                    "presence_entity": "person.danny",
                    "sleep_state": "on",
                    "delete": False,
                    "when_done": "keep",
                },
            )
            assert result["step_id"] == "windows"

            result = await flow.async_configure(result["flow_id"], {"window": "add_new"})
            assert result["step_id"] == "window"

            result = await flow.async_configure(
                result["flow_id"],
                {
                    "start": "06:00:00",
                    "end": "09:00:00",
                    "weekdays": ["0", "1", "2", "3", "4"],
                    "holiday": False,
                    "delete": False,
                    "when_done": "keep",
                },
            )
            assert result["step_id"] == "windows"

            result = await flow.async_configure(result["flow_id"], {"window": "back_to_menu"})
            stored = await save(home, result["flow_id"])

            assert stored["residents"][0]["windows"] == [
                {
                    "start": "06:00:00",
                    "end": "09:00:00",
                    "weekdays": [0, 1, 2, 3, 4],
                    "holiday": False,
                }
            ]
        finally:
            await stop_house(home)


class TestTheScreenSaysNo:
    """Een scherm dat een fout ziet, hoort niets op te slaan.

    A screen that spots a mistake must store nothing.
    """

    async def test_an_exclusive_group_of_one_is_refused(self) -> None:
        """Een groep van één sluit niets uit."""
        home = await start_house(two_rooms(), states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await menu(home, "exclusives")
            result = await flow.async_configure(result["flow_id"], {"group": "add_new"})
            result = await flow.async_configure(
                result["flow_id"],
                {"sources": ["woonkamer_airco"], "delete": False, "when_done": "keep"},
            )

            assert result["step_id"] == "exclusive"
            assert result["errors"] == {"sources": "too_few"}
        finally:
            await stop_house(home)

    async def test_a_circuit_without_units_is_refused(self) -> None:
        home = await start_house(two_rooms(), states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await menu(home, "circuits")
            result = await flow.async_configure(result["flow_id"], {"circuit": "add_new"})
            result = await flow.async_configure(
                result["flow_id"],
                {
                    "name": "Buitenunit",
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

            assert result["step_id"] == "circuit"
            assert result["errors"] == {"units": "required"}
        finally:
            await stop_house(home)

    async def test_an_opening_without_an_entity_is_refused(self) -> None:
        home = await start_house(two_rooms(), states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await menu(home, "openings")
            result = await flow.async_configure(result["flow_id"], {"opening": "add_new"})
            result = await flow.async_configure(
                result["flow_id"], {"zone_ids": ["zolder"], "delete": False, "when_done": "keep"}
            )

            assert result["step_id"] == "opening"
            assert result["errors"] == {"entity_id": "required"}
        finally:
            await stop_house(home)

    async def test_two_rooms_may_not_share_one_priority(self) -> None:
        """Gelijke voorrang op één circuit maakt de uitkomst willekeurig."""
        home = await start_house(two_rooms(), states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await menu(home, "circuits")
            result = await flow.async_configure(result["flow_id"], {"circuit": "add_new"})
            result = await flow.async_configure(
                result["flow_id"],
                {
                    "name": "Buitenunit",
                    "units": [LIVING, ATTIC],
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
            result = await flow.async_configure(result["flow_id"], {"zone": "zolder"})
            result = await flow.async_configure(
                result["flow_id"], {"priority": 0, "when_done": "keep"}
            )

            assert result["step_id"] == "circuit_priority"
            assert result["errors"] == {"priority": "duplicate_priority"}
        finally:
            await stop_house(home)


class TestTheCheckBeforeSaving:
    """Opslaan waarschuwt eerst, en luistert naar het antwoord.

    Saving warns first, and listens to the answer.
    """

    async def test_a_problem_is_shown_before_saving(self) -> None:
        installation = two_rooms()
        # Een groep die een bron noemt die niet bestaat: die kan nooit iets
        # uitsluiten, en dat meldt de controle.
        installation["exclusive_groups"] = [["woonkamer_airco", "bestaatniet"]]
        home = await start_house(installation, states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await flow.async_init(home.entry.entry_id)
            result = await flow.async_configure(result["flow_id"], {"next_step_id": "save"})

            assert result["type"] == "form"
            assert result["step_id"] == "save"
            assert "unknown source" in result["description_placeholders"]["problems"]
        finally:
            await stop_house(home)

    async def test_discarding_at_the_warning_goes_back_to_the_menu(self) -> None:
        """Wie schrikt van de melding, hoort terug te kunnen naar de instellingen."""
        installation = two_rooms()
        installation["exclusive_groups"] = [["woonkamer_airco", "bestaatniet"]]
        home = await start_house(installation, states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await flow.async_init(home.entry.entry_id)
            result = await flow.async_configure(result["flow_id"], {"next_step_id": "save"})
            result = await flow.async_configure(result["flow_id"], {"when_done": "discard"})

            assert result["type"] == "menu"
        finally:
            await stop_house(home)


class TestDiscardingAndDeleting:
    """Weggooien en verwijderen zijn twee verschillende dingen, en allebei echt.

    Discarding and deleting are two different things, and both are real.
    """

    async def test_discarding_a_screen_writes_nothing(self) -> None:
        home = await start_house(two_rooms(), states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await menu(home, "openings")
            result = await flow.async_configure(result["flow_id"], {"opening": "add_new"})
            result = await flow.async_configure(
                result["flow_id"],
                {
                    "entity_id": "binary_sensor.achterdeur",
                    "zone_ids": ["woonkamer"],
                    "delete": False,
                    "when_done": "discard",
                },
            )
            assert result["step_id"] == "openings"

            result = await flow.async_configure(result["flow_id"], {"opening": "back_to_menu"})
            stored = await save(home, result["flow_id"])

            assert stored.get("openings", []) == []
        finally:
            await stop_house(home)

    async def test_an_opening_can_be_deleted_again(self) -> None:
        installation = two_rooms()
        installation["openings"] = [
            {"entity_id": "binary_sensor.achterdeur", "zone_ids": ["woonkamer"], "delay": 0}
        ]
        home = await start_house(installation, states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await menu(home, "openings")
            result = await flow.async_configure(result["flow_id"], {"opening": "0"})
            assert result["step_id"] == "opening"

            result = await flow.async_configure(
                result["flow_id"],
                {
                    "entity_id": "binary_sensor.achterdeur",
                    "delete": True,
                    "when_done": "keep",
                },
            )
            stored = await save(home, result["flow_id"])

            assert stored["openings"] == []
        finally:
            await stop_house(home)

    async def test_a_quiet_window_can_be_deleted_again(self) -> None:
        installation = two_rooms()
        installation["gates"] = {"quiet_windows": [{"start": "21:00:00", "end": "09:00:00"}]}
        home = await start_house(installation, states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await menu(home, "quiets")
            result = await flow.async_configure(result["flow_id"], {"quiet": "0"})
            result = await flow.async_configure(
                result["flow_id"],
                {"start": "21:00:00", "end": "09:00:00", "delete": True, "when_done": "keep"},
            )
            assert result["step_id"] == "quiets"

            result = await flow.async_configure(result["flow_id"], {"quiet": "back_to_menu"})
            stored = await save(home, result["flow_id"])

            assert stored["gates"]["quiet_windows"] == []
        finally:
            await stop_house(home)

    async def test_an_exclusive_group_can_be_deleted_again(self) -> None:
        installation = two_rooms()
        installation["exclusive_groups"] = [["woonkamer_airco", "zolder_airco"]]
        home = await start_house(installation, states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await menu(home, "exclusives")
            result = await flow.async_configure(result["flow_id"], {"group": "0"})
            result = await flow.async_configure(
                result["flow_id"], {"delete": True, "when_done": "keep"}
            )
            assert result["step_id"] == "exclusives"

            result = await flow.async_configure(result["flow_id"], {"group": "back_to_menu"})
            stored = await save(home, result["flow_id"])

            assert stored["exclusive_groups"] == []
        finally:
            await stop_house(home)

    async def test_a_shared_heat_source_can_be_deleted_again(self) -> None:
        installation = two_rooms()
        installation["generators"] = [
            {
                "generator_id": "ketel",
                "name": "Ketel",
                "entity_id": "climate.gas",
                "zone_ids": [],
                "setpoint": None,
            }
        ]
        home = await start_house(installation, states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await menu(home, "generators")
            result = await flow.async_configure(result["flow_id"], {"generator": "0"})
            result = await flow.async_configure(
                result["flow_id"],
                {"name": "Ketel", "entity_id": "climate.gas", "delete": True, "when_done": "keep"},
            )
            stored = await save(home, result["flow_id"])

            assert stored["generators"] == []
        finally:
            await stop_house(home)


class TestEveryScreenSurvivesItsNeighbour:
    """Schermen die in dezelfde sleutel schrijven horen elkaar te laten staan.

    Screens that write into the same key must leave each other alone.
    """

    async def test_a_quiet_window_survives_a_settings_save(self) -> None:
        """Een stiltevenster zetten, daarna de instellingen bewaren: het venster blijft.

        Het instellingenscherm bouwt `gates` opnieuw op en wist daarmee de
        stiltevensters die het aparte stiltevensterscherm in diezelfde sleutel
        heeft gezet. Wie niets aan de instellingen verandert, mag dus niets
        kwijtraken.

        The settings screen rebuilds `gates` and thereby erases the quiet
        windows the separate quiet-window screen put into that same key. Saving
        the settings unchanged therefore must not lose anything.
        """
        home = await start_house(two_rooms(), states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await menu(home, "quiets")
            assert result["step_id"] == "quiets"

            result = await flow.async_configure(result["flow_id"], {"quiet": "add_new"})
            assert result["step_id"] == "quiet"

            result = await flow.async_configure(
                result["flow_id"],
                {
                    "start": "21:00:00",
                    "end": "09:00:00",
                    "weekdays": ["0", "1", "2", "3", "4"],
                    "delete": False,
                    "when_done": "keep",
                },
            )
            assert result["step_id"] == "quiets"
            result = await flow.async_configure(result["flow_id"], {"quiet": "back_to_menu"})
            assert result["type"] == "menu"

            result = await flow.async_configure(result["flow_id"], {"next_step_id": "settings"})
            assert result["step_id"] == "settings"

            # Niets veranderen, alleen bewaren; de defaults vullen de rest in.
            # Change nothing, only save; the defaults fill in the rest.
            result = await flow.async_configure(result["flow_id"], {"when_done": "keep"})
            stored = await save(home, result["flow_id"])

            assert stored["gates"]["quiet_windows"] == [
                {
                    "start": "21:00:00",
                    "end": "09:00:00",
                    "weekdays": [0, 1, 2, 3, 4],
                    "holiday": False,
                }
            ]
        finally:
            await stop_house(home)

    async def _fill_zone(self, flow: Any, flow_id: str) -> dict[str, Any]:
        result = await flow.async_configure(flow_id, {"zone": "add_new"})
        assert result["step_id"] == "zone"
        result = await flow.async_configure(
            result["flow_id"],
            {
                "name": "Keuken",
                "indoor_sensor": "sensor.keuken",
                "priority": 2,
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
        result = await flow.async_configure(result["flow_id"], {"source": "back_to_menu"})
        assert result["type"] == "menu"
        return result

    @staticmethod
    def _check_zone(stored: dict[str, Any]) -> None:
        keuken = next(item for item in stored["zones"] if item["zone_id"] == "keuken")
        assert keuken["name"] == "Keuken"
        assert keuken["heat"]["target"] == 21.0

    async def _fill_circuit(self, flow: Any, flow_id: str) -> dict[str, Any]:
        result = await flow.async_configure(flow_id, {"circuit": "add_new"})
        assert result["step_id"] == "circuit"
        result = await flow.async_configure(
            result["flow_id"],
            {
                "name": "Buitenunit",
                "units": [LIVING, ATTIC],
                "simultaneous_heat_cool": False,
                "conflict_policy": "priority",
                "allow_fan_only_during_conflict": True,
                "family_switch_delay": 60,
                "min_family_switch_interval": 900,
                "min_cycle_time": 300,
                "max_concurrent_units": 2,
                "delete": False,
                "when_done": "keep",
            },
        )
        assert result["step_id"] == "circuit_priorities"
        result = await flow.async_configure(result["flow_id"], {"zone": "back_to_menu"})
        assert result["type"] == "menu"
        return result

    @staticmethod
    def _check_circuit(stored: dict[str, Any]) -> None:
        assert stored["circuits"][0]["name"] == "Buitenunit"
        assert stored["circuits"][0]["min_cycle_time"] == 300

    async def _fill_generator(self, flow: Any, flow_id: str) -> dict[str, Any]:
        result = await flow.async_configure(flow_id, {"generator": "add_new"})
        assert result["step_id"] == "generator"
        result = await flow.async_configure(
            result["flow_id"],
            {
                "name": "Ketel",
                "entity_id": "climate.gas",
                "zone_ids": ["woonkamer", "zolder"],
                "setpoint": 21.5,
                "delete": False,
                "when_done": "keep",
            },
        )
        assert result["type"] == "menu"
        return result

    @staticmethod
    def _check_generator(stored: dict[str, Any]) -> None:
        assert stored["generators"][0]["generator_id"] == "ketel"
        assert stored["generators"][0]["entity_id"] == "climate.gas"

    async def _fill_exclusive(self, flow: Any, flow_id: str) -> dict[str, Any]:
        result = await flow.async_configure(flow_id, {"group": "add_new"})
        assert result["step_id"] == "exclusive"
        result = await flow.async_configure(
            result["flow_id"],
            {"sources": ["woonkamer_airco", "zolder_airco"], "delete": False, "when_done": "keep"},
        )
        assert result["step_id"] == "exclusives"
        result = await flow.async_configure(result["flow_id"], {"group": "back_to_menu"})
        assert result["type"] == "menu"
        return result

    @staticmethod
    def _check_exclusive(stored: dict[str, Any]) -> None:
        assert stored["exclusive_groups"] == [["woonkamer_airco", "zolder_airco"]]

    async def _fill_quiet(self, flow: Any, flow_id: str) -> dict[str, Any]:
        result = await flow.async_configure(flow_id, {"quiet": "add_new"})
        assert result["step_id"] == "quiet"
        result = await flow.async_configure(
            result["flow_id"],
            {
                "start": "21:00:00",
                "end": "09:00:00",
                "weekdays": ["0", "1", "2", "3", "4"],
                "delete": False,
                "when_done": "keep",
            },
        )
        assert result["step_id"] == "quiets"
        result = await flow.async_configure(result["flow_id"], {"quiet": "back_to_menu"})
        assert result["type"] == "menu"
        return result

    @staticmethod
    def _check_quiet(stored: dict[str, Any]) -> None:
        assert stored["gates"]["quiet_windows"] == [
            {"start": "21:00:00", "end": "09:00:00", "weekdays": [0, 1, 2, 3, 4], "holiday": False}
        ]

    async def _fill_resident(self, flow: Any, flow_id: str) -> dict[str, Any]:
        result = await flow.async_configure(flow_id, {"resident": "add_new"})
        assert result["step_id"] == "resident"
        result = await flow.async_configure(
            result["flow_id"],
            {
                "name": "Danny",
                "presence_entity": "person.danny",
                "sleep_state": "on",
                "delete": False,
                "when_done": "keep",
            },
        )
        assert result["step_id"] == "windows"
        result = await flow.async_configure(result["flow_id"], {"window": "back_to_menu"})
        assert result["type"] == "menu"
        return result

    @staticmethod
    def _check_resident(stored: dict[str, Any]) -> None:
        assert stored["residents"][0]["name"] == "Danny"

    async def _fill_opening(self, flow: Any, flow_id: str) -> dict[str, Any]:
        result = await flow.async_configure(flow_id, {"opening": "add_new"})
        assert result["step_id"] == "opening"
        result = await flow.async_configure(
            result["flow_id"],
            {
                "entity_id": "cover.dakraam",
                "open_state": "open",
                "zone_ids": ["zolder"],
                "delay": 120,
                "delete": False,
                "when_done": "keep",
            },
        )
        assert result["type"] == "menu"
        return result

    @staticmethod
    def _check_opening(stored: dict[str, Any]) -> None:
        assert stored["openings"] == [
            {
                "entity_id": "cover.dakraam",
                "zone_ids": ["zolder"],
                "open_state": "open",
                "delay": 120,
            }
        ]

    @pytest.mark.parametrize(
        "screen",
        ["zone", "circuit", "generator", "exclusive", "quiet", "resident", "opening"],
    )
    async def test_every_screen_keeps_its_work_after_a_settings_save(self, screen: str) -> None:
        """Elk scherm bewaart zijn werk als daarna de instellingen bewaard worden.

        Het instellingenscherm is het enige dat complete dicts in de installatie
        vervangt; de andere schermen muteren of bewaren elkaars velden. Deze test
        laat elk scherm iets toevoegen en gaat er daarna met een onveranderde
        instellingensave overheen - het werk van het eerste scherm hoort te
        blijven staan. Dit is de test die de stiltevenster-bug gevonden zou
        hebben en die er niet was.

        Every screen keeps its work when the settings are saved afterwards. The
        settings screen is the only one that replaces complete dicts in the
        installation; the other screens mutate or preserve each other's fields.
        This test has every screen add something and then runs an unchanged
        settings save over it - the first screen's work must remain. This is the
        test that would have caught the quiet-window bug and that did not exist.
        """
        home = await start_house(two_rooms(), states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await menu(home, f"{screen}s")
            result = await getattr(self, f"_fill_{screen}")(flow, result["flow_id"])
            assert result["type"] == "menu"

            result = await flow.async_configure(result["flow_id"], {"next_step_id": "settings"})
            assert result["step_id"] == "settings"

            # Niets veranderen, alleen bewaren; de defaults vullen de rest in.
            # Change nothing, only save; the defaults fill in the rest.
            result = await flow.async_configure(result["flow_id"], {"when_done": "keep"})
            stored = await save(home, result["flow_id"])

            getattr(self, f"_check_{screen}")(stored)
        finally:
            await stop_house(home)

    async def test_the_settings_screen_survives_the_quiet_window_screen(self) -> None:
        """Andersom: wat de instellingen bewaarden, mag het stiltevensterscherm niet raken.

        The reverse direction: the quiet-window screen must not touch what the
        settings screen saved.
        """
        home = await start_house(two_rooms(), states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await menu(home, "settings")
            assert result["step_id"] == "settings"
            result = await flow.async_configure(
                result["flow_id"], {"outdoor_hysteresis": 1.5, "when_done": "keep"}
            )
            assert result["type"] == "menu"

            result = await flow.async_configure(result["flow_id"], {"next_step_id": "quiets"})
            result = await self._fill_quiet(flow, result["flow_id"])

            stored = await save(home, result["flow_id"])

            assert stored["outdoor_hysteresis"] == 1.5
            self._check_quiet(stored)
        finally:
            await stop_house(home)


class TestDeletingAZoneCleansItsReferences:
    """Een verwijderde zone hoort nergens meer in voor te komen.

    A deleted zone should no longer appear anywhere.
    """

    async def test_openings_generators_and_groups_are_cleaned(self) -> None:
        installation = {
            **two_rooms(),
            "openings": [{"entity_id": "binary_sensor.raam", "zone_ids": ["woonkamer", "zolder"]}],
            "generators": [
                {
                    "generator_id": "cv",
                    "name": "CV",
                    "entity_id": "climate.ketel",
                    "zone_ids": ["woonkamer", "zolder"],
                }
            ],
            "exclusive_groups": [["woonkamer_airco", "zolder_airco"]],
        }
        home = await start_house(installation, states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await menu(home, "zones")
            assert result["step_id"] == "zones"

            result = await flow.async_configure(result["flow_id"], {"zone": "0"})
            assert result["step_id"] == "zone"
            result = await flow.async_configure(
                result["flow_id"], {"delete": True, "when_done": "keep"}
            )
            assert result["type"] == "menu"

            stored = await save(home, result["flow_id"])
            assert stored["openings"][0]["zone_ids"] == ["zolder"]
            assert stored["generators"][0]["zone_ids"] == ["zolder"]
            assert all("woonkamer_airco" not in group for group in stored["exclusive_groups"])
        finally:
            await stop_house(home)
