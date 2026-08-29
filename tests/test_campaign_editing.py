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
import voluptuous as vol
from harness_live import LiveHome, settings, source, start_bare_house, start_house, stop_house, zone
from homeassistant.util.unit_system import IMPERIAL_SYSTEM

from custom_components.climate_director.const import CONF_INSTALLATION, DOMAIN

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


def _optional_fields_by_step() -> dict[str, list[str]]:
    """Return the `vol.Optional` keys per `async_show_form` step, from the source.

    De lijst komt uit de bron van de héle integratie (AST over álle `*.py` onder
    `custom_components/climate_director/`), niet uit een met de hand bijgehouden
    kaart of uit `config_flow.py` alleen. Een nieuw optioneel veld — in welk
    bestand dan ook — doet zo automatisch mee in plaats van stilletjes te
    ontbreken; precies wat er met `house_wide_openings` op het
    openingenlijstscherm misging.

    The map comes from the source of the whole integration (AST over every
    `*.py` under `custom_components/climate_director/`), not from a hand-kept
    map or from `config_flow.py` alone. A new optional field — in whatever file —
    joins in automatically instead of quietly missing; exactly what went wrong
    with `house_wide_openings` on the openings screen.
    """
    import ast

    from conftest import async_show_form_calls

    found: dict[str, list[str]] = {}
    for _module, step_id, schema in async_show_form_calls():
        if step_id is None or schema is None:
            continue
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


def _optional_fields(screen: str) -> list[str]:
    """Return the `vol.Optional` keys of one form, failing on an unknown step."""
    found = _optional_fields_by_step()
    if screen not in found:
        raise AssertionError(f"geen async_show_form met step_id {screen!r} gevonden")
    return found[screen]


def _show_form_steps() -> set[str]:
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


class TestEveryFormInTheSourceIsWalkedTo:
    """M1: elk formulier in de bron heeft een expliciete doorloop.

    De tekenfixture in `conftest.py` bewaakt élk formulier dat de suite werkelijk
    tekent — foutherhalingen en tussenschermen inbegrepen — maar zijn dekking
    volgt wat de tests toevallig aandoen. Deze test bindt die dekking aan de
    bron: hij loopt de AST-inventarisatie van `async_show_form(step_id=...)` af
    en loopt élk scherm binnen via `open_screen`, dat hard faalt op een step_id
    waarvoor geen navigatie bestaat. Zo is een nieuw scherm zonder test
    zichtbaar rood in plaats van stilletjes onbewaakt; samen bewaken deze twee
    dus twee verschillende dingen.

    Het **bestaan** van een scherm werd al afgedwongen door drie bewakingen die
    niets met deze doorloop te maken hebben: `TestEveryFormField` (labels én
    uitleg, zeven talen),
    `TestEveryScreenCanBeLeft.test_each_one_offers_a_way_back` en
    `TestDiscardArrivesOnEveryScreen.test_the_example_values_cover_exactly_the_schema`.
    De **dekking** van álle formulieren ligt bij deze test zelf: hij leest zijn
    lijst uit de bron, niet uit een handkaart. Sinds ronde 19 is dit de **enige**
    bewaking op de formulierdekking; er stond er een tweede naast in
    `pytest_sessionfinish` (`conftest.py`), en die is geschrapt omdat hij dezelfde
    invariant bewaakte met een extra aanname over de runconditie.

    M1: every form in the source has an explicit walk.

    The draw fixture in `conftest.py` guards every form the suite actually
    draws — error re-displays and intermediate screens included — but its
    coverage follows whatever the tests happen to touch. This test binds that
    coverage to the source: it walks the AST inventory of
    `async_show_form(step_id=...)` and walks into every screen through
    `open_screen`, which hard-fails on a step id without navigation. A new
    screen without a test is thereby visibly red instead of silently
    unguarded; together the two guard two different things.

    A screen's **existence** was already forced by three guards unrelated to
    this walk: `TestEveryFormField` (labels and explanations, seven languages),
    `TestEveryScreenCanBeLeft.test_each_one_offers_a_way_back` and
    `TestDiscardArrivesOnEveryScreen.test_the_example_values_cover_exactly_the_schema`.
    The **coverage** of all forms lies with this test itself: it reads its list
    from the source, not from a hand-kept map. Since round 19 this is the **only**
    guard on the form coverage; a second one used to stand beside it in
    `pytest_sessionfinish` (`conftest.py`), and it was removed because it guarded
    the same invariant with an extra assumption about the run condition.
    """

    async def test_every_step_id_in_the_source_opens(self) -> None:
        """Elke step_id uit de bron is via `open_screen` werkelijk te openen.

        Every step id from the source can really be opened through `open_screen`.
        """
        steps = _show_form_steps()
        assert "user" in steps, "de AST-loop vindt het wizardscherm niet"
        assert "init" in steps, "de AST-loop vindt het reparatiescherm niet"
        home = await start_house(_installation_with_a_problem(), states=cold())
        try:
            for screen in sorted(steps - {"user", "init"}):
                _, result, _ = await open_screen(home, screen)
                assert result["step_id"] == screen, (
                    f"open_screen liep naar {result['step_id']!r} in plaats van {screen!r}"
                )

            # Het reparatiescherm hoort bij de oplosflow van de handbediend-melding,
            # niet bij de options flow; die heeft dus een losse flow nodig, net
            # zoals de wizard hieronder een huis zonder entry nodig heeft.
            #
            # The repair screen belongs to the fix flow of the hand-operated
            # notice, not to the options flow; it therefore needs its own flow,
            # just as the wizard below needs a house without an entry.
            from custom_components.climate_director.repairs import ManualSourcesFlow

            flow = ManualSourcesFlow()
            flow.hass = home.hass
            flow.handler = DOMAIN
            flow.issue_id = "manual_sources_live"
            flow.data = {"entry_id": home.entry.entry_id, "signature": "x"}
            result = await flow.async_step_init(None)
            assert result["type"] == "form"
            assert result["step_id"] == "init"
        finally:
            await stop_house(home)

        # De wizard hoort bij de config flow, niet bij de options flow; die heeft
        # dus een huis zonder entry nodig en zijn eigen, kleinere doorloop.
        #
        # The wizard belongs to the config flow, not the options flow; it needs
        # a house without an entry and its own, smaller walk.
        hass = await start_bare_house(states=cold())
        try:
            result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
            assert result["type"] == "form"
            assert result["step_id"] == "user"
        finally:
            await hass.async_stop()

        assert steps == {
            "user",
            "settings",
            "exclusives",
            "exclusive",
            "quiets",
            "quiet",
            "zones",
            "zone",
            "sources",
            "source",
            "circuits",
            "circuit",
            "circuit_priorities",
            "circuit_priority",
            "generators",
            "generator",
            "residents",
            "resident",
            "windows",
            "window",
            "openings",
            "opening",
            "save",
            "init",
        }, (
            f"de bron heeft {len(steps)} schermen; de doorloop hierboven hoort ze "
            f"allemaal te openen — {sorted(steps)}"
        )


def _installation_with_a_problem() -> dict[str, Any]:
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

    async def test_the_house_wide_stops_are_written_from_the_openings_screen(self) -> None:
        """De lijst hangt aan het apparaat, dus hij staat op het lijstscherm."""
        home = await start_house(two_rooms(), states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await menu(home, "openings")

            result = await flow.async_configure(
                result["flow_id"],
                {"opening": "back_to_menu", "house_wide_openings": [LIVING]},
            )
            stored = await save(home, result["flow_id"])

            assert stored["house_wide_openings"] == [LIVING]
        finally:
            await stop_house(home)

    async def test_the_house_wide_stops_survive_walking_into_an_opening(self) -> None:
        """Doorklikken naar een opening mag de zojuist gemaakte keuze niet wissen."""
        home = await start_house(two_rooms(), states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await menu(home, "openings")

            result = await flow.async_configure(
                result["flow_id"],
                {"opening": "add_new", "house_wide_openings": [LIVING]},
            )
            assert result["step_id"] == "opening"

            result = await flow.async_configure(
                result["flow_id"],
                {
                    "entity_id": "binary_sensor.achterdeur",
                    "zone_ids": ["woonkamer"],
                    "delete": False,
                    "when_done": "keep",
                },
            )
            stored = await save(home, result["flow_id"])

            assert stored["house_wide_openings"] == [LIVING]
            assert stored["openings"][0]["entity_id"] == "binary_sensor.achterdeur"
        finally:
            await stop_house(home)

    async def test_the_house_wide_stops_can_be_cleared_again(self) -> None:
        installation = two_rooms()
        installation["house_wide_openings"] = [LIVING]
        home = await start_house(installation, states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await menu(home, "openings")

            result = await flow.async_configure(
                result["flow_id"], {"opening": "back_to_menu", "house_wide_openings": []}
            )
            stored = await save(home, result["flow_id"])

            assert stored["house_wide_openings"] == []
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

    async def test_deleting_a_source_cleans_its_exclusive_group(self) -> None:
        """M2: een verwijderde bron laat geen verweesd bron-ID achter."""
        installation = {
            "zones": [
                zone(
                    "woonkamer",
                    sources=[
                        source("woonkamer_airco", LIVING, role="heat_cool"),
                        source("woonkamer_ketel", "climate.gas", role="heat_only", priority=1),
                    ],
                    heat=settings(21.0, 20.0),
                )
            ],
            "exclusive_groups": [["woonkamer_airco", "woonkamer_ketel"]],
        }
        states = {
            "sensor.woonkamer": ("18.0", {}),
            LIVING: ("off", {}),
            "climate.gas": ("off", {}),
        }
        home = await start_house(installation, states=states)
        try:
            flow = home.hass.config_entries.options
            result = await menu(home, "zones")
            result = await flow.async_configure(result["flow_id"], {"zone": "0"})
            assert result["step_id"] == "zone"
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
                    "heat_target": 21.0,
                    "heat_start_at": 20.0,
                    "heat_hysteresis": 1.0,
                    "enable_cool": False,
                    "cool_target": 23.0,
                    "cool_start_at": 24.0,
                    "cool_hysteresis": 1.0,
                    "cool_summer_only": False,
                    "delete": False,
                    "when_done": "keep",
                },
            )
            assert result["step_id"] == "sources"

            result = await flow.async_configure(result["flow_id"], {"source": "1"})
            assert result["step_id"] == "source"
            result = await flow.async_configure(
                result["flow_id"],
                {
                    "entity_id": "climate.gas",
                    "role": "heat_only",
                    "autostart": True,
                    "priority": 1,
                    "delete": True,
                    "when_done": "keep",
                },
            )
            assert result["step_id"] == "sources"
            result = await flow.async_configure(result["flow_id"], {"source": "back_to_menu"})
            stored = await save(home, result["flow_id"])

            dangling = [
                source_id
                for group in stored.get("exclusive_groups") or []
                for source_id in group
                if source_id == "woonkamer_ketel"
            ]
            assert not dangling, f"verweesde groep bleef staan: {stored.get('exclusive_groups')}"
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

    async def test_the_house_wide_stop_list_loses_a_removed_appliance(self) -> None:
        """Een verwijzing die niets meer aanwijst hoort niet te blijven staan."""
        installation = {
            **two_rooms(),
            "openings": [{"entity_id": "binary_sensor.raam"}],
            "house_wide_openings": [LIVING, ATTIC],
        }
        home = await start_house(installation, states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await menu(home, "zones")
            result = await flow.async_configure(result["flow_id"], {"zone": "0"})
            result = await flow.async_configure(
                result["flow_id"], {"delete": True, "when_done": "keep"}
            )

            stored = await save(home, result["flow_id"])
            assert stored["house_wide_openings"] == [ATTIC]
        finally:
            await stop_house(home)

    async def test_the_openings_screen_shows_no_stale_house_wide_value(self) -> None:
        """Een scherm dat je binnenkomt, moet je ook weer kunnen verlaten.

        A screen you can enter, you must be able to leave again.
        """
        installation = {
            **two_rooms(),
            "openings": [{"entity_id": "binary_sensor.raam"}],
            "house_wide_openings": [LIVING],
        }
        home = await start_house(installation, states=cold())
        try:
            flow = home.hass.config_entries.options
            result = await menu(home, "zones")
            result = await flow.async_configure(result["flow_id"], {"zone": "0"})
            result = await flow.async_configure(
                result["flow_id"], {"delete": True, "when_done": "keep"}
            )
            assert result["type"] == "menu"

            result = await flow.async_configure(result["flow_id"], {"next_step_id": "openings"})
            assert result["step_id"] == "openings"
            field = next(
                key for key in result["data_schema"].schema if str(key) == "house_wide_openings"
            )
            assert field.description["suggested_value"] is None

            result = await flow.async_configure(
                result["flow_id"], {"opening": "back_to_menu", "house_wide_openings": []}
            )
            stored = await save(home, result["flow_id"])
            assert stored["house_wide_openings"] == []
        finally:
            await stop_house(home)

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
    als `None` of `""` (die aanname kostte 7.2.1 de interface; de fixture
    `every_drawn_form_must_serialize` in `conftest.py` bewaakt dat elk scherm
    tekenbaar blijft). Deze test laat daarom op elk bewerkingsscherm álle
    optionele velden weg en eist dat "verwerpen en teruggaan" aankomt op de lijst
    erboven; daarna vult hij dezelfde velden met geldige voorbeeldwaarden en eist
    hetzelfde.

    H8/K1: "discard and go back" arrives on every screen, even with cleared fields.

    Home Assistant validates the form before the step runs. The frontend sends a
    cleared optional field as a **missing key** — not as `None` or `""` (that
    assumption cost 7.2.1 its interface; the `every_drawn_form_must_serialize`
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
            "entity_id": "climate.gas",
            "outdoor_min": -5.0,
            "outdoor_max": 20.0,
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
        all_steps = _optional_fields_by_step()
        with_fields = {screen for screen, keys in all_steps.items() if keys}
        uncovered = with_fields - set(self._VALUES)
        assert not uncovered, f"schermen zonder voorbeeldkaart: {sorted(uncovered)}"
        for screen, values in self._VALUES.items():
            assert set(values) == set(_optional_fields(screen)), (
                f"scheef voor {screen}: waarden {sorted(values)}, "
                f"schema {sorted(_optional_fields(screen))}"
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
