"""De opbouw van een installatie door elk scherm heen.

Building an installation through every screen."""

from __future__ import annotations

from flow_helpers import (
    ATTIC,
    LIVING,
    cold,
    installation_with_a_problem,
    menu,
    save,
    show_form_steps,
    two_rooms,
    walk_screens,
)
from harness_live import settings, source, start_bare_house, start_house, stop_house, zone

from custom_components.climate_director.const import DOMAIN


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
    lijst uit de bron, niet uit een handkaart. Dit is de **enige**
    bewaking op de formulierdekking; een tweede in `pytest_sessionfinish`
    (`conftest.py`) zou dezelfde invariant bewaken met een extra aanname over de
    runconditie.

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
    from the source, not from a hand-kept map. This is the **only** guard on the
    form coverage; a second one in `pytest_sessionfinish` (`conftest.py`) would
    guard the same invariant with an extra assumption about the run condition.
    """

    async def test_every_step_id_in_the_source_opens(self) -> None:
        """Elke step_id uit de bron is via `open_screen` werkelijk te openen.

        Every step id from the source can really be opened through `open_screen`.
        """
        steps = show_form_steps()
        assert "user" in steps, "de AST-loop vindt het wizardscherm niet"
        assert "init" in steps, "de AST-loop vindt het reparatiescherm niet"
        home = await start_house(installation_with_a_problem(), states=cold())
        try:
            await walk_screens(home, steps - {"user", "init"})

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
                    "name": "Dakraam",
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
                    "opening_id": "dakraam",
                    "name": "Dakraam",
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
                    "name": "Achterdeur",
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
            assert result["errors"] == {"name": "required", "entity_id": "required"}
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
