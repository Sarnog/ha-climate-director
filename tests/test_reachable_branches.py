"""De bereikbare takken die de suite nog niet aanraakte (ronde 30, fase 3b).

The reachable branches the suite had not touched yet (round 30, phase 3b).

De dekkingsmeting van 2026-09-14 wees 107 gemiste statements aan. Deze module
dekt de takken die **bereikbaar** zijn: de terugkeer naar het hoofdmenu, het
verwijderen en bewerken van een item, de foutherhalingen van de formulieren, en
de kleine engine- en opslagtakken. Die meting telde ook regels die met
`# pragma: no cover` waren afgevangen; ronde 32 (R32-1) heeft de laatste zes
daarvan alsnog gemeten, en sindsdien draagt het pakket **geen enkele** pragma
meer (`tests/test_reachable_branches_deep.py` houdt dat vast).

The coverage run of 2026-09-14 pointed at 107 missed statements. This module
covers the branches that are **reachable**: returning to the main menu, deleting
and editing an item, the forms' error repeats, and the small engine and storage
branches. That measurement also counted lines caught with `# pragma: no cover`;
round 32 (R32-1) measured the last six of those after all, and the package has
carried **no** pragma since (`tests/test_reachable_branches_deep.py` holds that
down).
"""

from __future__ import annotations

from typing import Any

import pytest
from harness_live import LiveHome, start_house, stop_house
from test_campaign_editing import ATTIC, LIVING, cold, menu, save, two_rooms

from custom_components.climate_director.config_flow import (
    ClimateDirectorOptionsFlow,
    _name_errors,
)

CIRCUIT_FIELDS: dict[str, Any] = {
    "name": "Buitenunit",
    "units": [LIVING, ATTIC],
    "simultaneous_heat_cool": False,
    "conflict_policy": "priority",
    "allow_fan_only_during_conflict": False,
    "family_switch_delay": 0,
    "min_family_switch_interval": 0,
    "min_cycle_time": 180,
    "when_done": "keep",
}


# -- de options flow, zonder Home Assistant -----------------------------------
# -- the options flow, without Home Assistant ---------------------------------


def bare_flow(installation: dict[str, Any] | None = None) -> ClimateDirectorOptionsFlow:
    """Return a flow with just enough state to reach a helper.

    Return a flow with just enough state to reach a helper.
    """
    flow = ClimateDirectorOptionsFlow()
    flow._installation = installation if installation is not None else {}
    flow._shadow_mode = False
    return flow


def test_dropping_no_source_references_is_a_no_op() -> None:
    """Een lege verzameling bron-ID's raakt de groepen niet aan."""
    flow = bare_flow({"exclusive_groups": [["a", "b"]]})
    flow._drop_source_references(set())
    assert flow._installation["exclusive_groups"] == [["a", "b"]]


def test_priority_clash_skips_a_circuit_without_the_zone() -> None:
    """Een circuit zonder deze zone doet niet mee aan de voorrangscontrole."""
    flow = bare_flow(
        {
            "circuits": [
                {"circuit_id": "a", "units": [LIVING]},
                {"circuit_id": "b", "units": ["climate.elders"]},
            ],
            "zones": [
                {
                    "zone_id": "woonkamer",
                    "priority": 0,
                    "sources": [{"entity_id": LIVING}],
                }
            ],
        }
    )
    assert flow._priority_clash("woonkamer", 0) is False


def test_a_stale_resident_cursor_yields_no_resident() -> None:
    """Een cursor die nergens meer heen wijst levert geen bewoner op."""
    flow = bare_flow({"residents": [{"resident_id": "a"}]})
    assert flow._current_resident() is None


def test_a_zone_without_a_name_is_refused() -> None:
    """Een naam die niets om te sluggen oplevert wordt geweigerd."""
    assert _name_errors({"name": ""}) == {"name": "required"}
    assert _name_errors({"name": "Woonkamer"}) == {}


async def test_the_source_screen_returns_to_the_menu_without_a_zone() -> None:
    """Zonder zone gaat het bronnenscherm terug naar het hoofdmenu."""
    flow = bare_flow({"zones": []})
    result = await flow.async_step_sources()
    assert result["type"] == "menu"
    assert result["step_id"] == "init"


async def test_the_source_form_returns_to_the_menu_without_a_zone() -> None:
    """Zonder zone gaat ook het bronformulier terug naar het hoofdmenu."""
    flow = bare_flow({"zones": []})
    result = await flow.async_step_source()
    assert result["type"] == "menu"
    assert result["step_id"] == "init"


async def test_a_priority_screen_without_its_zone_returns_to_the_menu() -> None:
    """Een prioriteitenscherm zonder zijn zone of circuit gaat terug."""
    flow = bare_flow({"zones": [], "circuits": []})
    flow._priority_zone_id = "bestaat_niet"
    result = await flow.async_step_circuit_priority()
    assert result["type"] == "menu"
    assert result["step_id"] == "init"


async def test_the_window_screens_return_to_the_menu_without_a_resident() -> None:
    """Zonder bewoner gaan beide roosterschermen terug naar het hoofdmenu."""
    flow = bare_flow({"residents": []})
    listed = await flow.async_step_windows()
    assert listed["step_id"] == "init"
    form = await flow.async_step_window()
    assert form["step_id"] == "init"


# -- de options flow, met Home Assistant --------------------------------------
# -- the options flow, with Home Assistant ------------------------------------


@pytest.fixture
async def home() -> LiveHome:
    """A two-room house that can be edited.

    A two-room house that can be edited.
    """
    live = await start_house(two_rooms(), states=cold())
    try:
        yield live
    finally:
        await stop_house(live)


@pytest.mark.parametrize(
    ("screen", "field"),
    [
        ("zones", "zone"),
        ("circuits", "circuit"),
        ("generators", "generator"),
        ("residents", "resident"),
        ("quiets", "quiet"),
        ("exclusives", "group"),
        ("openings", "opening"),
        ("sources", "source"),
        ("windows", "window"),
        ("circuit_priorities", "zone"),
    ],
)
async def test_the_back_row_of_every_list_returns_to_the_menu(
    home: LiveHome, screen: str, field: str
) -> None:
    """De terugkeerregel van elk lijstscherm landt op het hoofdmenu."""
    from test_campaign_editing import open_screen

    flow_id, _result, _parent = await open_screen(home, screen)
    flow = home.hass.config_entries.options
    result = await flow.async_configure(flow_id, {field: "back_to_menu"})
    assert result["type"] == "menu"
    assert result["step_id"] == "init"


async def test_a_circuit_can_be_deleted_and_returns_to_the_menu(home: LiveHome) -> None:
    """Een circuit verwijderen ruimt zijn cursor op en gaat naar het menu."""
    flow = home.hass.config_entries.options
    result = await menu(home, "circuits")
    flow_id = result["flow_id"]
    result = await flow.async_configure(flow_id, {"circuit": "add_new"})
    result = await flow.async_configure(flow_id, CIRCUIT_FIELDS)
    assert result["step_id"] == "circuit_priorities"
    result = await flow.async_configure(flow_id, {"zone": "back_to_menu"})
    assert result["step_id"] == "init"
    result = await flow.async_configure(flow_id, {"next_step_id": "circuits"})
    result = await flow.async_configure(flow_id, {"circuit": "0"})
    assert result["step_id"] == "circuit"
    result = await flow.async_configure(flow_id, {"delete": True, "when_done": "keep"})
    assert result["type"] == "menu"
    assert result["step_id"] == "init"


async def test_an_existing_exclusive_group_keeps_its_place(home: LiveHome) -> None:
    """Een bestaande groep bewerken vervangt hem op zijn eigen plek."""
    flow = home.hass.config_entries.options
    result = await menu(home, "exclusives")
    flow_id = result["flow_id"]
    result = await flow.async_configure(flow_id, {"group": "add_new"})
    result = await flow.async_configure(
        flow_id, {"sources": ["woonkamer_airco", "zolder_airco"], "when_done": "keep"}
    )
    assert result["step_id"] == "exclusives"
    result = await flow.async_configure(flow_id, {"group": "0"})
    assert result["step_id"] == "exclusive"
    result = await flow.async_configure(
        flow_id, {"sources": ["zolder_airco", "woonkamer_airco"], "when_done": "keep"}
    )
    assert result["step_id"] == "exclusives"
    result = await flow.async_configure(flow_id, {"group": "back_to_menu"})
    stored = await save(home, flow_id)
    assert stored["exclusive_groups"] == [["zolder_airco", "woonkamer_airco"]]


async def test_a_zone_form_comes_back_with_what_you_typed(home: LiveHome) -> None:
    """Een fout op het zoneformulier toont wat je ingevuld had, niet de oude waarde."""
    flow = home.hass.config_entries.options
    result = await menu(home, "zones")
    flow_id = result["flow_id"]
    result = await flow.async_configure(flow_id, {"zone": "0"})
    assert result["step_id"] == "zone"
    result = await flow.async_configure(
        flow_id, {"name": "", "indoor_sensor": "sensor.woonkamer", "when_done": "keep"}
    )
    assert result["type"] == "form"
    assert result["errors"] == {"name": "required"}


async def test_a_generator_form_comes_back_with_what_you_typed(home: LiveHome) -> None:
    """Een fout op het bronscherm herhaalt het formulier met je invoer."""
    flow = home.hass.config_entries.options
    result = await menu(home, "generators")
    flow_id = result["flow_id"]
    result = await flow.async_configure(flow_id, {"generator": "add_new"})
    assert result["step_id"] == "generator"
    # `entity_id` is optioneel in het schema maar verplicht voor de stap: de
    # stap meldt het zelf, en dat is de foutherhaling die de invoer bewaart.
    #
    # `entity_id` is optional in the schema but required by the step: the step
    # reports it itself, and that is the error repeat that keeps the input.
    result = await flow.async_configure(flow_id, {"name": "CV"})
    assert result["type"] == "form"
    assert result["step_id"] == "generator"


async def test_discarding_a_window_goes_back_to_the_list(home: LiveHome) -> None:
    """Verwerpen op het roosterformulier gaat terug naar de roosterlijst."""
    flow = home.hass.config_entries.options
    result = await menu(home, "residents")
    flow_id = result["flow_id"]
    result = await flow.async_configure(flow_id, {"resident": "add_new"})
    result = await flow.async_configure(
        flow_id, {"name": "Danny", "presence_entity": "person.danny", "when_done": "keep"}
    )
    assert result["step_id"] == "windows"
    result = await flow.async_configure(flow_id, {"window": "add_new"})
    assert result["step_id"] == "window"
    result = await flow.async_configure(flow_id, {"when_done": "discard"})
    assert result["step_id"] == "windows"


async def test_a_resident_can_be_deleted_and_returns_to_the_menu(home: LiveHome) -> None:
    """Een bewoner verwijderen ruimt zijn cursor op en gaat naar het menu."""
    flow = home.hass.config_entries.options
    result = await menu(home, "residents")
    flow_id = result["flow_id"]
    result = await flow.async_configure(flow_id, {"resident": "add_new"})
    result = await flow.async_configure(
        flow_id, {"name": "Danny", "presence_entity": "person.danny", "when_done": "keep"}
    )
    result = await flow.async_configure(flow_id, {"window": "back_to_menu"})
    assert result["step_id"] == "init"
    result = await flow.async_configure(flow_id, {"next_step_id": "residents"})
    result = await flow.async_configure(flow_id, {"resident": "0"})
    assert result["step_id"] == "resident"
    result = await flow.async_configure(flow_id, {"delete": True})
    assert result["type"] == "menu"
    assert result["step_id"] == "init"


async def test_a_resident_can_be_edited(home: LiveHome) -> None:
    """Een bestaande bewoner bewerken houdt zijn plek en zijn id."""
    flow = home.hass.config_entries.options
    result = await menu(home, "residents")
    flow_id = result["flow_id"]
    result = await flow.async_configure(flow_id, {"resident": "add_new"})
    result = await flow.async_configure(
        flow_id, {"name": "Danny", "presence_entity": "person.danny", "when_done": "keep"}
    )
    result = await flow.async_configure(flow_id, {"window": "back_to_menu"})
    assert result["step_id"] == "init"
    result = await flow.async_configure(flow_id, {"next_step_id": "residents"})
    result = await flow.async_configure(flow_id, {"resident": "0"})
    result = await flow.async_configure(
        flow_id, {"name": "Danny", "presence_entity": "person.danny", "when_done": "keep"}
    )
    assert result["step_id"] == "windows"
    result = await flow.async_configure(flow_id, {"window": "back_to_menu"})
    stored = await save(home, flow_id)
    assert len(stored["residents"]) == 1


async def test_a_window_can_be_deleted_and_returns_to_windows(home: LiveHome) -> None:
    """Een rooster verwijderen ruimt zijn cursor op en gaat terug naar de lijst."""
    flow = home.hass.config_entries.options
    result = await menu(home, "residents")
    flow_id = result["flow_id"]
    result = await flow.async_configure(flow_id, {"resident": "add_new"})
    result = await flow.async_configure(
        flow_id, {"name": "Danny", "presence_entity": "person.danny", "when_done": "keep"}
    )
    result = await flow.async_configure(flow_id, {"window": "add_new"})
    result = await flow.async_configure(
        flow_id,
        {
            "start": "06:30:00",
            "end": "09:00:00",
            "weekdays": ["0", "1"],
            "when_done": "keep",
        },
    )
    assert result["step_id"] == "windows"
    result = await flow.async_configure(flow_id, {"window": "0"})
    assert result["step_id"] == "window"
    result = await flow.async_configure(flow_id, {"delete": True, "when_done": "keep"})
    assert result["step_id"] == "windows"


async def test_a_window_can_be_edited(home: LiveHome) -> None:
    """Een bestaand rooster bewerken houdt zijn plek."""
    flow = home.hass.config_entries.options
    result = await menu(home, "residents")
    flow_id = result["flow_id"]
    result = await flow.async_configure(flow_id, {"resident": "add_new"})
    result = await flow.async_configure(
        flow_id, {"name": "Danny", "presence_entity": "person.danny", "when_done": "keep"}
    )
    result = await flow.async_configure(flow_id, {"window": "add_new"})
    result = await flow.async_configure(
        flow_id,
        {
            "start": "06:30:00",
            "end": "09:00:00",
            "weekdays": ["0", "1"],
            "when_done": "keep",
        },
    )
    result = await flow.async_configure(flow_id, {"window": "0"})
    result = await flow.async_configure(
        flow_id,
        {
            "start": "07:00:00",
            "end": "10:00:00",
            "weekdays": ["0", "1"],
            "when_done": "keep",
        },
    )
    assert result["step_id"] == "windows"


async def test_a_duplicate_priority_on_one_circuit_is_refused() -> None:
    """Twee zones op één buitenunit mogen niet hetzelfde voorrangsnummer hebben."""
    installation = two_rooms()
    installation["circuits"] = [
        {
            "circuit_id": "buitenunit",
            "name": "Buitenunit",
            "units": [LIVING, ATTIC],
            "conflict_policy": "priority",
            "allow_fan_only_during_conflict": False,
            "simultaneous_heat_cool": False,
            "family_switch_delay": 0,
            "min_family_switch_interval": 0,
            "min_cycle_time": 180,
        }
    ]
    live = await start_house(installation, states=cold())
    try:
        flow = live.hass.config_entries.options
        result = await menu(live, "zones")
        flow_id = result["flow_id"]
        result = await flow.async_configure(flow_id, {"zone": "1"})
        assert result["step_id"] == "zone"
        result = await flow.async_configure(
            flow_id,
            {
                "name": "Zolder",
                "indoor_sensor": "sensor.zolder",
                "priority": 0,
                "when_done": "keep",
            },
        )
        assert result["type"] == "form"
        assert result["errors"] == {"priority": "duplicate_priority"}
    finally:
        await stop_house(live)


async def test_a_source_form_comes_back_with_what_you_typed(home: LiveHome) -> None:
    """Een bron zonder entiteit herhaalt het formulier met je invoer."""
    flow = home.hass.config_entries.options
    result = await menu(home, "zones")
    flow_id = result["flow_id"]
    result = await flow.async_configure(flow_id, {"zone": "0"})
    result = await flow.async_configure(
        flow_id,
        {"name": "Woonkamer", "indoor_sensor": "sensor.woonkamer", "when_done": "keep"},
    )
    assert result["step_id"] == "sources"
    result = await flow.async_configure(flow_id, {"source": "add_new"})
    assert result["step_id"] == "source"
    result = await flow.async_configure(flow_id, {"name": "Tweede"})
    assert result["type"] == "form"
    assert result["step_id"] == "source"


async def test_a_resident_form_comes_back_with_what_you_typed(home: LiveHome) -> None:
    """Een bewoner zonder aanwezigheidsentiteit herhaalt het formulier."""
    flow = home.hass.config_entries.options
    result = await menu(home, "residents")
    flow_id = result["flow_id"]
    result = await flow.async_configure(flow_id, {"resident": "add_new"})
    assert result["step_id"] == "resident"
    result = await flow.async_configure(flow_id, {"name": "Danny"})
    assert result["type"] == "form"
    assert result["step_id"] == "resident"
