"""Hulpjes voor de schermtoetsen: een huis, een koude wereld en de weg naar elk scherm.

Helpers for the screen tests: a house, a cold world and the way to every screen."""

from __future__ import annotations

from typing import Any

from harness_live import LiveHome, settings, source, zone

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


async def open_screen(home: LiveHome, screen: str) -> tuple[str, dict[str, Any], str | None]:
    """Walk into `screen`; return `(flow_id, its form result, parent)`.

    `parent` is de step_id van de lijst waar het scherm bij "verwerpen" naar
    terugkeert, of `None` wanneer verwerpen op het hoofdmenu landt (`settings`,
    `openings`, de lijstschermen en `save`). De navigatie staat hier zodat elke
    test die de flow doorloopt dezelfde paden gebruikt en de schermen niet
    tussen tests uit de pas kunnen lopen. `TestEveryFormInTheSourceIsWalkedTo`
    loopt de broninventarisatie af tegen precies deze functie; een step_id die
    hier geen tak heeft, maakt die test rood.

    `parent` is the step id of the list the screen returns to when discarded, or
    `None` when discarding lands back on the main menu (`settings`, `openings`,
    the list screens and `save`). The navigation lives here so every test that
    walks the flow uses the same paths, and the screens cannot drift apart
    between tests. `TestEveryFormInTheSourceIsWalkedTo` walks the source
    inventory against exactly this function; a step id without a branch here
    turns that test red.
    """
    flow = home.hass.config_entries.options

    async def into(step: str) -> dict[str, Any]:
        """Walk into a main-menu entry and return its form result."""
        result = await menu(home, step)
        assert result["step_id"] == step
        return result

    async def into_zone(choice: str) -> dict[str, Any]:
        """Walk into the zone form, choosing an existing room or the add-row."""
        result = await menu(home, "zones")
        result = await flow.async_configure(result["flow_id"], {"zone": choice})
        assert result["step_id"] == "zone"
        return result

    async def into_sources() -> dict[str, Any]:
        """Walk through room zero into its list of sources."""
        result = await into_zone("0")
        result = await flow.async_configure(
            result["flow_id"],
            {"name": "Woonkamer", "indoor_sensor": "sensor.woonkamer", "when_done": "keep"},
        )
        assert result["step_id"] == "sources"
        return result

    async def into_circuit_priorities() -> dict[str, Any]:
        """Create a priority-based circuit and land on its per-room priorities."""
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
                "when_done": "keep",
            },
        )
        assert result["step_id"] == "circuit_priorities"
        return result

    async def into_windows() -> dict[str, Any]:
        """Create a resident and land on its list of schedules."""
        result = await menu(home, "residents")
        result = await flow.async_configure(result["flow_id"], {"resident": "add_new"})
        result = await flow.async_configure(
            result["flow_id"],
            {"name": "Danny", "presence_entity": "person.danny", "when_done": "keep"},
        )
        assert result["step_id"] == "windows"
        return result

    if screen in (
        "settings",
        "energy",
        "openings",
        "zones",
        "circuits",
        "generators",
        "residents",
        "quiets",
        "exclusives",
        "save",
    ):
        result = await into(screen)
        return result["flow_id"], result, None
    if screen in ("zone", "zone_existing"):
        choice = "add_new" if screen == "zone" else "0"
        result = await into_zone(choice)
        return result["flow_id"], result, "zones"
    if screen == "sources":
        result = await into_sources()
        return result["flow_id"], result, None
    if screen == "source":
        result = await into_sources()
        result = await flow.async_configure(result["flow_id"], {"source": "add_new"})
        assert result["step_id"] == "source"
        return result["flow_id"], result, "sources"
    if screen == "circuit":
        result = await menu(home, "circuits")
        result = await flow.async_configure(result["flow_id"], {"circuit": "add_new"})
        assert result["step_id"] == "circuit"
        return result["flow_id"], result, "circuits"
    if screen == "circuit_priorities":
        result = await into_circuit_priorities()
        return result["flow_id"], result, None
    if screen == "circuit_priority":
        result = await into_circuit_priorities()
        result = await flow.async_configure(result["flow_id"], {"zone": "woonkamer"})
        assert result["step_id"] == "circuit_priority"
        return result["flow_id"], result, "circuit_priorities"
    if screen == "generator":
        result = await menu(home, "generators")
        result = await flow.async_configure(result["flow_id"], {"generator": "add_new"})
        assert result["step_id"] == "generator"
        return result["flow_id"], result, "generators"
    if screen == "resident":
        result = await menu(home, "residents")
        result = await flow.async_configure(result["flow_id"], {"resident": "add_new"})
        assert result["step_id"] == "resident"
        return result["flow_id"], result, "residents"
    if screen == "windows":
        result = await into_windows()
        return result["flow_id"], result, None
    if screen == "window":
        result = await into_windows()
        result = await flow.async_configure(result["flow_id"], {"window": "add_new"})
        assert result["step_id"] == "window"
        return result["flow_id"], result, "windows"
    if screen == "opening":
        result = await menu(home, "openings")
        result = await flow.async_configure(result["flow_id"], {"opening": "add_new"})
        assert result["step_id"] == "opening"
        return result["flow_id"], result, "openings"
    if screen == "quiet":
        result = await menu(home, "quiets")
        result = await flow.async_configure(result["flow_id"], {"quiet": "add_new"})
        assert result["step_id"] == "quiet"
        return result["flow_id"], result, "quiets"
    if screen == "exclusive":
        result = await menu(home, "exclusives")
        result = await flow.async_configure(result["flow_id"], {"group": "add_new"})
        assert result["step_id"] == "exclusive"
        return result["flow_id"], result, "exclusives"
    raise AssertionError(f"unknown screen {screen}")


def optional_fields_by_step() -> dict[str, list[str]]:
    """Return the `vol.Optional` keys per `async_show_form` step, from the source.

    De lijst komt uit de bron van de héle integratie (AST over álle `*.py` onder
    `custom_components/climate_director/`), niet uit een met de hand bijgehouden
    kaart of uit `config_flow.py` alleen. Een nieuw optioneel veld — in welk
    bestand dan ook — doet zo automatisch mee in plaats van stilletjes te
    ontbreken; precies wat er met `house_wide_openings` op het
    openingenlijstscherm misging. Sinds S5 staan de schema's in `schemas.py`;
    `conftest.form_field_nodes()` lost `data_schema=schemas.<naam>(...)` op
    naar de functie in dat bestand, zodat de velden hier evengoed gelezen
    worden.

    The map comes from the source of the whole integration (AST over every
    `*.py` under `custom_components/climate_director/`), not from a hand-kept
    map or from `config_flow.py` alone. A new optional field — in whatever file —
    joins in automatically instead of quietly missing; exactly what went wrong
    with `house_wide_openings` on the openings screen. Since S5 the schemas live
    in `schemas.py`; `conftest.form_field_nodes()` resolves
    `data_schema=schemas.<name>(...)` to the function in that file, so the
    fields are read here just the same.
    """
    import ast

    from conftest import form_field_nodes

    found: dict[str, list[str]] = {}
    for _module, step_id, schema in form_field_nodes():
        found[step_id] = [
            sub.args[0].value
            for sub in ast.walk(schema)
            if isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and sub.func.attr == "Optional"
            and sub.args
            and isinstance(sub.args[0], ast.Constant)
            and isinstance(sub.args[0].value, str)
        ]
    return found


def optional_fields(screen: str) -> list[str]:
    """Return the `vol.Optional` keys of one form, failing on an unknown step."""
    found = optional_fields_by_step()
    if screen not in found:
        raise AssertionError(f"geen async_show_form met step_id {screen!r} gevonden")
    return found[screen]


def show_form_steps() -> set[str]:
    """Return every `async_show_form(step_id=...)` in the source, from the AST.

    Een eigen loop, los van de veldenkaart: een scherm zonder `data_schema`
    (een kale bevestiging) hoort evengoed een doorloopplicht te hebben. De
    inventarisatie loopt over de héle integratie, niet over `config_flow.py`
    alleen; het reparatiescherm (`init` in `repairs.py`) hoort er dus bij.

    Its own loop, separate from the field map: a screen without a `data_schema`
    (a bare confirmation) deserves a walk duty just the same. The inventory
    walks the whole integration, not `config_flow.py` alone; the repair screen
    (`init` in `repairs.py`) therefore belongs to it.
    """
    from conftest import async_show_form_calls

    return {step_id for _module, step_id, _schema in async_show_form_calls() if step_id is not None}


def installation_with_a_problem() -> dict[str, Any]:
    """Return two rooms plus one deliberate validation problem.

    Het bewaarscherm (`save`) toont zich alleen als formulier wanneer
    `validate()` iets vindt; een huisbrede stop zonder openingen is zo'n
    melding en laat alle andere schermen gewoon openen.

    The save screen only shows itself as a form when `validate()` finds
    something; a house-wide stop without openings is such a problem and leaves
    every other screen openable.
    """
    installation = two_rooms()
    installation["house_wide_openings"] = [LIVING]
    return installation


async def walk_screens(home, screens: set[str]) -> None:
    """Open every screen and demand that the flow lands on the requested one."""
    for screen in sorted(screens):
        _, result, _ = await open_screen(home, screen)
        assert result["step_id"] == screen, (
            f"open_screen liep naar {result['step_id']!r} in plaats van {screen!r}"
        )
