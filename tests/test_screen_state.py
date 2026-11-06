"""Wat een scherm onthoudt naast zijn buur, na een fout en na afronding.

What a screen keeps beside its neighbour, after an error and after rounding."""

from __future__ import annotations

from typing import Any

import pytest
import voluptuous as vol
from flow_helpers import (
    ATTIC,
    LIVING,
    cold,
    installation_with_a_problem,
    menu,
    open_screen,
    optional_fields,
    optional_fields_by_step,
    save,
    two_rooms,
)
from harness_live import settings, source, start_house, stop_house
from homeassistant.util.unit_system import IMPERIAL_SYSTEM


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

    async def test_a_hand_picked_summer_list_survives_a_settings_save(self) -> None:
        """Een handmatige zomermaandenlijst overleeft het instellingenscherm.

        A hand-picked summer-months list survives the settings screen.
        """
        data = two_rooms()
        data["seasons"] = {"source": "auto", "summer_months": [4, 5, 6, 7, 8, 9, 10]}
        home = await start_house(data, states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await menu(home, "settings")
            assert result["step_id"] == "settings"

            result = await flow.async_configure(result["flow_id"], {"when_done": "keep"})
            stored = await save(home, result["flow_id"])

            assert stored["seasons"]["summer_months"] == [4, 5, 6, 7, 8, 9, 10]
        finally:
            await stop_house(home)

    async def test_a_zone_error_keeps_the_typed_temperatures(self) -> None:
        """Bij een fout toont het zoneformulier de ingetypte temperaturen, niet de oude.

        On an error the zone form keeps the temperatures just typed, not the
        stored ones.
        """
        home = await start_house(two_rooms(), states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await menu(home, "zones")
            result = await flow.async_configure(result["flow_id"], {"zone": "0"})
            assert result["step_id"] == "zone"

            result = await flow.async_configure(
                result["flow_id"],
                {
                    "name": "Woonkamer X",
                    "priority": 0,
                    "gate": "household",
                    "presence_state": "on",
                    "enable_heat": True,
                    "heat_target": 24.0,
                    "heat_start_at": 23.0,
                    "heat_hysteresis": 2.0,
                    "enable_cool": False,
                    "cool_target": 23.0,
                    "cool_start_at": 24.0,
                    "cool_hysteresis": 1.0,
                    "cool_summer_only": False,
                    "delete": False,
                    "when_done": "keep",
                },
            )
            assert result["step_id"] == "zone"
            assert result["errors"] == {"indoor_sensor": "required"}

            result = await flow.async_configure(
                result["flow_id"], {"indoor_sensor": "sensor.woonkamer", "when_done": "keep"}
            )
            assert result["step_id"] == "sources"
            result = await flow.async_configure(result["flow_id"], {"source": "back_to_menu"})
            stored = await save(home, result["flow_id"])

            woonkamer = next(item for item in stored["zones"] if item["zone_id"] == "woonkamer")
            assert woonkamer["name"] == "Woonkamer X"
            assert woonkamer["heat"]["target"] == 24.0
            assert woonkamer["heat"]["start_at"] == 23.0
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
                "sleep_in_until": "13:00:00",
                "sleep_in_days": ["5", "6"],
                "sleep_in_holiday": True,
                "wake_by": "11:00:00",
                "wake_days": ["5", "6"],
                "wake_holiday": True,
                "rise_from": "07:00:00",
                "rise_days": ["0", "1", "2", "3", "4"],
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
        assert stored["residents"][0]["sleep_in"] == {
            "until": "13:00:00",
            "weekdays": [5, 6],
            "holiday": True,
        }
        assert stored["residents"][0]["wake_deadline"] == {
            "at": "11:00:00",
            "weekdays": [5, 6],
            "holiday": True,
        }
        assert stored["residents"][0]["rise_brake"] == {
            "at": "07:00:00",
            "weekdays": [0, 1, 2, 3, 4],
        }

    async def _fill_opening(self, flow: Any, flow_id: str) -> dict[str, Any]:
        result = await flow.async_configure(flow_id, {"opening": "add_new"})
        assert result["step_id"] == "opening"
        result = await flow.async_configure(
            result["flow_id"],
            {
                "name": "Dakraam",
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
                "opening_id": "dakraam",
                "name": "Dakraam",
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


class TestTheFormShowsRoundedValues:
    """G4: het formulier toont afgeronde waarden, de opslag blijft ongeafgerond.

    G4: the form shows rounded values, storage stays unrounded.
    """

    def _installation(self) -> dict[str, Any]:
        return {
            **two_rooms(),
            "outdoor_hysteresis": 0.1,
        }

    def _imperial_world(self) -> dict[str, tuple[str, dict[str, Any]]]:
        return {
            "sensor.woonkamer": ("61.0", {"unit_of_measurement": "°F"}),
            "sensor.zolder": ("61.0", {"unit_of_measurement": "°F"}),
            LIVING: ("off", {}),
            ATTIC: ("off", {}),
        }

    @staticmethod
    def _default(schema: Any, key_name: str) -> float | None:
        field = next(key for key in schema.schema if str(key) == key_name)
        default = field.default
        return default() if callable(default) else default

    async def test_temperature_defaults_are_rounded(self) -> None:
        """16,1 °C is 60,980000000000004 °F; het veld hoort 61.0 te tonen."""
        installation = self._installation()
        installation["zones"][0]["heat"] = settings(16.1, 15.1, hysteresis=0.1)
        home = await start_house(
            installation,
            states=self._imperial_world(),
            unit_system=IMPERIAL_SYSTEM,
        )
        try:
            flow = home.hass.config_entries.options
            result = await menu(home, "zones")
            result = await flow.async_configure(result["flow_id"], {"zone": "0"})
            assert result["step_id"] == "zone"
            schema = result["data_schema"]
            assert self._default(schema, "heat_target") == 61.0
            assert self._default(schema, "heat_hysteresis") == 0.2
        finally:
            await stop_house(home)

    async def test_the_dead_band_default_is_rounded(self) -> None:
        """0,1 °C is 0,18000000000000002 °F; de dode band hoort 0.2 te tonen."""
        home = await start_house(
            self._installation(),
            states=self._imperial_world(),
            unit_system=IMPERIAL_SYSTEM,
        )
        try:
            result = await menu(home, "settings")
            assert result["step_id"] == "settings"
            assert self._default(result["data_schema"], "outdoor_hysteresis") == 0.2
        finally:
            await stop_house(home)

    async def test_saving_keeps_storage_unrounded(self) -> None:
        """De opslag gaat ongeafgerond door `to_celsius`; anders kruipt de
        configuratie bij elke bewerking weg.

        Storage passes through `to_celsius` unrounded; otherwise the
        configuration creeps away on every edit.
        """
        installation = self._installation()
        installation["zones"][0]["heat"] = settings(16.1, 15.1)
        home = await start_house(
            installation,
            states=self._imperial_world(),
            unit_system=IMPERIAL_SYSTEM,
        )
        try:
            flow = home.hass.config_entries.options
            result = await menu(home, "zones")
            result = await flow.async_configure(result["flow_id"], {"zone": "0"})
            result = await flow.async_configure(
                result["flow_id"],
                {
                    "name": "Woonkamer",
                    "indoor_sensor": "sensor.woonkamer",
                    "priority": 0,
                    "gate": "household",
                    "presence_state": "on",
                    "ignore_precipitation": False,
                    "enable_heat": True,
                    "heat_target": 61.0,
                    "heat_start_at": 59.0,
                    "heat_hysteresis": 1.8,
                    "enable_cool": False,
                    "cool_target": 73.0,
                    "cool_start_at": 75.0,
                    "cool_hysteresis": 1.8,
                    "cool_summer_only": False,
                    "delete": False,
                    "when_done": "keep",
                },
            )
            result = await flow.async_configure(result["flow_id"], {"source": "back_to_menu"})
            stored = await save(home, result["flow_id"])
            heat = stored["zones"][0]["heat"]
            assert heat["target"] == pytest.approx(16.11111111111111)
            assert heat["hysteresis"] == pytest.approx(1.0)
        finally:
            await stop_house(home)


class TestDiscardArrivesOnEveryScreen:
    """H8/K1: "verwerpen en teruggaan" komt op elk scherm aan, ook met leeggemaakte velden.

    Home Assistant valideert het formulier vóórdat de stap draait. De interface
    stuurt een leeggemaakt optioneel veld als **ontbrekende sleutel** door — niet
    als `None` of `""` (die aanname maakt de interface onbruikbaar; de fixture
    `every_drawn_form_must_serialize` in `conftest.py` bewaakt dat elk scherm
    tekenbaar blijft). Deze test laat daarom op elk bewerkingsscherm álle
    optionele velden weg en eist dat "verwerpen en teruggaan" aankomt op de lijst
    erboven; daarna vult hij dezelfde velden met geldige voorbeeldwaarden en eist
    hetzelfde.

    H8/K1: "discard and go back" arrives on every screen, even with cleared fields.

    Home Assistant validates the form before the step runs. The frontend sends a
    cleared optional field as a **missing key** — not as `None` or `""` (that
    assumption makes the interface unusable; the `every_drawn_form_must_serialize`
    fixture in `conftest.py` guards that every screen stays drawable). This test
    therefore omits every optional field on every edit screen and requires
    "discard and go back" to arrive on the list above; then it fills those same
    fields with valid example values and requires the same.
    """

    _VALUES: dict[str, dict[str, Any]] = {
        "zone": {
            "indoor_sensor": "sensor.woonkamer",
            "presence_entity": "sensor.aanwezig",
            "presence_timeout": 60,
            "heat_outdoor_max": 25.0,
            "cool_outdoor_min": 15.0,
        },
        "source": {
            "name": "Gasketel",
            "entity_id": "climate.gas",
            "outdoor_min": -5.0,
            "outdoor_max": 20.0,
            "min_cycle_time": 180,
            "covers_zones": ["woonkamer"],
        },
        "circuit": {"units": [LIVING, ATTIC], "max_concurrent_units": 2},
        "circuit_priority": {},
        "generator": {
            "entity_id": "climate.gas",
            "zone_ids": ["woonkamer"],
            "setpoint": 21.5,
        },
        "resident": {
            "presence_entity": "person.danny",
            "sleep_entity": "binary_sensor.slaap",
            "sleep_from": "22:00:00",
            "sleep_until": "07:00:00",
            "sleep_days": ["0", "1"],
            "sleep_in_until": "13:00:00",
            "sleep_in_days": ["5", "6"],
            "wake_by": "11:00:00",
            "wake_days": ["5", "6"],
            "rise_from": "07:00:00",
            "rise_days": ["0", "1", "2", "3", "4"],
        },
        "window": {"weekdays": ["0", "1"]},
        "opening": {
            "entity_id": "binary_sensor.achterdeur",
            "open_state": "open",
            "zone_ids": ["woonkamer"],
            "delay": 60,
        },
        "quiet": {"weekdays": ["0", "1"]},
        "exclusive": {"sources": ["woonkamer_airco", "zolder_airco"]},
        "settings": {
            "outdoor_sensor": "sensor.buiten",
            "season_entity": "sensor.seizoen",
            "holiday_calendars": ["calendar.danny"],
            "holiday_keyword": "vakantie",
            "guest_start": "08:00:00",
            "guest_end": "23:00:00",
            "guest_days": ["5", "6"],
            "precipitation_source": "sensor.regen",
        },
        "openings": {"house_wide_openings": [LIVING]},
    }

    @staticmethod
    def _discard(screen: str) -> dict[str, Any]:
        """Return the payload that leaves `screen` without saving anything.

        `openings` kent geen "when_done"-regel; de uitgang daar is de
        "terug"-keuze in de openingenlijst zelf.

        `openings` has no "when_done" row; its exit is the "back" choice in the
        opening list itself.
        """
        if screen == "openings":
            return {"opening": "back_to_menu"}
        return {"when_done": "discard"}

    @pytest.mark.parametrize(
        ("screen", "variant"),
        [
            (screen, variant)
            for screen in [
                "zone",
                "source",
                "circuit",
                "circuit_priority",
                "generator",
                "resident",
                "window",
                "opening",
                "quiet",
                "exclusive",
                "settings",
                "openings",
            ]
            for variant in ["omitted", "filled"]
        ],
    )
    async def test_discard_arrives(self, screen: str, variant: str) -> None:
        """Elk scherm, elke variant: verwerpen en teruggaan komt aan.

        Every screen, every variant: discard and go back arrives.
        """
        home = await start_house(two_rooms(), states=cold())
        try:
            flow_id, _, parent = await open_screen(home, screen)
            payload = self._discard(screen)
            if variant == "filled":
                payload.update(self._VALUES[screen])
            result = await home.hass.config_entries.options.async_configure(flow_id, payload)
            if parent is None:
                assert result["type"] == "menu"
            else:
                assert result["step_id"] == parent
        finally:
            await stop_house(home)

    def test_the_example_values_cover_exactly_the_schema(self) -> None:
        """J2: elke voorbeeldwaarde dekt precies de optionele velden van zijn scherm.

        De veldenlijst komt uit de bron; deze test eist dat de voorbeeldkaart
        niet uit de pas loopt — geen ontbrekend veld en geen overbodige waarde.
        Zo groeit de doorloop vanzelf mee met een nieuw veld in plaats van het
        stilletjes over te slaan.

        J2: every example value covers exactly its screen's optional fields.

        The field list comes from the source; this test requires the example map
        not to drift — no missing field, no superfluous value, and no screen
        with optional fields left uncovered. That way the walk grows along with
        a new field instead of silently skipping it.
        """
        all_steps = optional_fields_by_step()
        with_fields = {screen for screen, keys in all_steps.items() if keys}
        uncovered = with_fields - set(self._VALUES)
        assert not uncovered, f"schermen zonder voorbeeldkaart: {sorted(uncovered)}"
        for screen, values in self._VALUES.items():
            assert set(values) == set(optional_fields(screen)), (
                f"scheef voor {screen}: waarden {sorted(values)}, "
                f"schema {sorted(optional_fields(screen))}"
            )

    async def test_an_invalid_filled_value_is_still_refused(self) -> None:
        """Een ingevuld veld gaat nog steeds door de selector: 500 °C wordt geweigerd.

        A filled-in value still goes through the selector: 500 °C is refused.
        """
        home = await start_house(two_rooms(), states=cold())
        try:
            flow_id, _, _ = await open_screen(home, "generator")
            with pytest.raises(vol.Invalid):
                await home.hass.config_entries.options.async_configure(
                    flow_id,
                    {
                        "name": "Ketel",
                        "entity_id": "climate.gas",
                        "setpoint": 500,
                        "when_done": "discard",
                    },
                )
        finally:
            await stop_house(home)


class TestAnEditRoundStoresNoEmptyStrings:
    """J4: een bewerkronde met leeggemaakte velden laat geen `""` achter in de opslag.

    De test maakt alle optionele getalvelden leeg (de interface levert ze als
    ontbrekende sleutel aan), slaat op, en loopt daarna de hele opgeslagen boom
    af: nergens mag `""` staan op een plek waar een getal of een entiteit hoort.
    Alleen de velden waar `""` de afgesproken betekenis "niet ingesteld" heeft
    mogen het zijn. Deze test bewaakt de **opslagvorm**, niet de helper
    `_blank_to_none`: die is op elk bereikbaar pad een no-op, want de selectors
    ervóór weigeren een lege string al.

    J4: an edit round with cleared fields leaves no `""` behind in storage.

    The test clears every optional numeric field (the frontend delivers them as
    missing keys), saves, and then walks the whole stored tree: nowhere may `""`
    stand where a number or an entity belongs. Only the fields where `""` means
    "not set" by convention may have it. This test guards the **storage shape**,
    not the `_blank_to_none` helper: that one is a no-op on every reachable
    path, since the selectors in front of it already refuse an empty string.
    """

    _STRING_EMPTY_KEYS = {
        # Een lege eigen naam betekent "noem het apparaat zelf", net zoals een
        # leeg vakantietrefwoord "geen trefwoord" betekent. Dat is een geldige
        # tekstwaarde, geen lege string op de plek van een getal of entiteit.
        #
        # An empty name of one's own means "name the appliance itself", just as
        # an empty holiday keyword means "no keyword". That is a valid text
        # value, not an empty string where a number or an entity belongs.
        "name",
        "presence_entity",
        "outdoor_sensor",
        "season_entity",
        "sleep_entity",
        "holiday_keyword",
        "precipitation_source",
        "guest_start",
        "guest_end",
        "sleep_from",
        "sleep_until",
    }

    @staticmethod
    def _empty_string_keys(value: Any) -> list[str]:
        """Return the key under which every `""` value sits, list parents included."""
        found: list[str] = []

        def walk(item: Any, key: str) -> None:
            if isinstance(item, dict):
                for name, child in item.items():
                    walk(child, name)
            elif isinstance(item, list):
                for child in item:
                    walk(child, key)
            elif item == "":
                found.append(key)

        walk(value, "$")
        return found

    async def test_cleared_optional_fields_land_as_none(self) -> None:
        installation = two_rooms()
        installation["zones"][0]["heat"] = settings(21.0, 20.0, outdoor={"maximum": 25.0})
        installation["zones"][0]["sources"][0] = source(
            "woonkamer_airco",
            LIVING,
            role="heat_cool",
            outdoor={"minimum": 5.0, "maximum": 25.0},
        )
        installation["circuits"] = [
            {
                "circuit_id": "buitenunit",
                "name": "Buitenunit",
                "units": [LIVING, ATTIC],
                "simultaneous_heat_cool": False,
                "conflict_policy": "priority",
                "allow_fan_only_during_conflict": False,
                "family_switch_delay": 0,
                "min_family_switch_interval": 0,
                "min_cycle_time": 180,
                "max_concurrent_units": 2,
            }
        ]
        installation["generators"] = [
            {
                "generator_id": "ketel",
                "name": "Ketel",
                "entity_id": "climate.gas",
                "zone_ids": ["woonkamer"],
                "setpoint": 21.5,
            }
        ]
        installation["house_wide_openings"] = [LIVING]
        home = await start_house(installation, states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await menu(home, "zones")
            flow_id = result["flow_id"]

            # Zone bewerken: beide buitengrenzen leegmaken (ontbrekende sleutels).
            # Edit the zone: clear both outdoor bounds (missing keys).
            result = await flow.async_configure(flow_id, {"zone": "0"})
            result = await flow.async_configure(
                flow_id,
                {
                    "name": "Woonkamer",
                    "indoor_sensor": "sensor.woonkamer",
                    "enable_heat": True,
                    "enable_cool": True,
                    "when_done": "keep",
                },
            )
            assert result["step_id"] == "sources"

            # Bron bewerken: beide buitengrenzen leegmaken.
            # Edit the source: clear both outdoor bounds.
            result = await flow.async_configure(flow_id, {"source": "0"})
            result = await flow.async_configure(
                flow_id,
                {
                    "entity_id": LIVING,
                    "role": "heat_cool",
                    "autostart": True,
                    "priority": 0,
                    "when_done": "keep",
                },
            )
            assert result["step_id"] == "sources"
            result = await flow.async_configure(flow_id, {"source": "back_to_menu"})
            assert result["type"] == "menu"

            # Circuit bewerken: de capaciteitsgrens leegmaken.
            # Edit the circuit: clear the capacity limit.
            result = await flow.async_configure(flow_id, {"next_step_id": "circuits"})
            result = await flow.async_configure(flow_id, {"circuit": "0"})
            result = await flow.async_configure(
                flow_id,
                {
                    "name": "Buitenunit",
                    "units": [LIVING, ATTIC],
                    "simultaneous_heat_cool": False,
                    "conflict_policy": "priority",
                    "allow_fan_only_during_conflict": False,
                    "family_switch_delay": 0,
                    "min_family_switch_interval": 0,
                    "min_cycle_time": 180,
                    "when_done": "keep",
                },
            )
            assert result["step_id"] == "circuit_priorities"
            result = await flow.async_configure(flow_id, {"zone": "back_to_menu"})
            assert result["type"] == "menu"

            # Gedeelde warmtebron bewerken: het setpoint leegmaken.
            # Edit the shared heat source: clear the setpoint.
            result = await flow.async_configure(flow_id, {"next_step_id": "generators"})
            result = await flow.async_configure(flow_id, {"generator": "0"})
            result = await flow.async_configure(
                flow_id,
                {
                    "name": "Ketel",
                    "entity_id": "climate.gas",
                    "zone_ids": ["woonkamer"],
                    "when_done": "keep",
                },
            )
            assert result["type"] == "menu"

            # Openingen bevestigen zonder huisbrede lijst.
            # Confirm the openings screen without the house-wide list.
            result = await flow.async_configure(flow_id, {"next_step_id": "openings"})
            result = await flow.async_configure(flow_id, {"opening": "back_to_menu"})
            assert result["type"] == "menu"

            stored = await save(home, flow_id)

            zone_0 = stored["zones"][0]
            assert zone_0["heat"]["outdoor"]["maximum"] is None
            assert zone_0["cool"]["outdoor"]["minimum"] is None
            assert zone_0["sources"][0]["outdoor"]["minimum"] is None
            assert zone_0["sources"][0]["outdoor"]["maximum"] is None
            assert stored["circuits"][0]["max_concurrent_units"] is None
            assert stored["generators"][0]["setpoint"] is None
            assert stored["house_wide_openings"] == []

            offenders = [
                key for key in self._empty_string_keys(stored) if key not in self._STRING_EMPTY_KEYS
            ]
            assert not offenders, f"lege strings op onverwachte plekken: {offenders}"
        finally:
            await stop_house(home)


class TestEveryDayFieldSpeaksTheUsersLanguage:
    """De dagen van de week staan in de taal van de interface, niet in het Engels.

    Een keuzeveld dat zijn labels als letterlijke tekst meegeeft, toont die tekst
    onvertaald: Home Assistant heeft dan niets om op te zoeken. De vertaling
    hangt aan `translation_key`, en die eigenschap pinnen we hier vast op het
    **getekende** formulier - niet op hoe het in de bron geschreven staat.

    The days of the week appear in the language of the interface, not in English.
    A picker handing its labels as literal text shows that text untranslated:
    Home Assistant then has nothing to look up. The translation hangs on
    `translation_key`, and that property is pinned here against the **drawn**
    form - not against how it reads in the source.
    """

    @staticmethod
    def _day_fields(schema: Any) -> list[Any]:
        """Return every selector in `schema` that offers the seven weekdays."""
        found = []
        for validator in schema.schema.values():
            config = getattr(validator, "config", None)
            if config is None:
                continue
            options = config.get("options") or ()
            values = [option["value"] for option in options if isinstance(option, dict)]
            if values == [str(day) for day in range(7)]:
                found.append(config)
        return found

    @pytest.mark.parametrize(("screen", "fields"), [("resident", 4), ("window", 1), ("quiet", 1)])
    async def test_the_day_pickers_carry_a_translation_key(self, screen: str, fields: int) -> None:
        home = await start_house(installation_with_a_problem(), states=cold())
        try:
            _, result, _ = await open_screen(home, screen)
            found = self._day_fields(result["data_schema"])
            assert len(found) == fields, f"{screen} heeft {len(found)} dagenvelden"
            for config in found:
                assert config.get("translation_key") == "weekday"
        finally:
            await stop_house(home)

    def test_the_list_line_uses_the_translated_days(self) -> None:
        from custom_components.climate_director.schemas import _window_label

        dutch = {
            "component.climate_director.selector.weekday_short.options.5": "za",
            "component.climate_director.selector.weekday_short.options.6": "zo",
            "component.climate_director.selector.weekday_summary.options.every_day": "elke dag",
        }
        window = {"start": "08:00:00", "end": "15:00:00", "weekdays": [5, 6]}
        assert _window_label(window, dutch) == "08:00 - 15:00, za, zo"
        assert _window_label({**window, "weekdays": None}, dutch) == "08:00 - 15:00, elke dag"

    def test_it_falls_back_on_english_without_a_translation(self) -> None:
        from custom_components.climate_director.schemas import _window_label

        window = {"start": "08:00:00", "end": "15:00:00", "weekdays": [5, 6]}
        assert _window_label(window, {}) == "08:00 - 15:00, Sat, Sun"
