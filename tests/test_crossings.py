"""De kruispunten waar de bugs van de review zaten.

The crossings where the review's bugs sat.

Geen van de zes bewezen bugs zat in een functie die het verkeerd deed. Alle zes
zaten op het kruispunt van twee dingen die apart precies werkten: een gedeeld
apparaat en een stiltevenster, een aanwezigheidssensor en een handmatige
uitzetting, een gedeelde bron en een voorrang die tijdens het draaien verandert.
Elk van die onderdelen had zijn eigen tests, en die stonden allemaal op groen.

None of the six proven bugs sat in a function doing something wrong. All six sat
at the crossing of two things that each worked exactly right on their own: a
shared appliance and a quiet window, a presence sensor and a hand-operated
stand-down, a shared source and a priority that changes while running. Each of
those parts had tests of its own, and every one of them was green.

Dit bestand loopt die kruispunten na in een echt draaiende Home Assistant, met
een echte herstart waar dat uitmaakt - want twee van de zes waren pas te zien
nadat de installatie opnieuw geladen was. De reparaties hebben elk hun eigen
test bij hun eigen module; deze staan er als kruispunt, zodat de volgende lezer
het patroon ziet en niet alleen de losse gevallen.

This file walks those crossings in a really running Home Assistant, with a real
restart where that matters - since two of the six only showed after the
installation had been loaded afresh. The repairs each carry a test of their own
next to their own module; these stand here as crossings, so the next reader sees
the pattern rather than only the separate cases.
"""

from __future__ import annotations

from typing import Any

import pytest
from harness_live import LiveHome, settings, source, start_house, stop_house, zone

BOILER = "climate.ketel"
ATTIC_AIRCO = "climate.zolder_airco"

ALWAYS_QUIET = {"quiet_windows": [{"start": "00:00:00", "end": "23:59:00"}]}


def two_zones_on_one_boiler(**extra: Any) -> dict[str, Any]:
    """Return two rooms whose only source is the same boiler thermostat."""
    return {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("ketel_woonkamer", BOILER)],
                indoor_sensor="sensor.woonkamer",
                heat=settings(21.0, 20.0),
                priority=0,
            ),
            zone(
                "zolder",
                sources=[source("ketel_zolder", BOILER)],
                indoor_sensor="sensor.zolder",
                heat=settings(20.0, 19.0),
                priority=1,
            ),
        ],
        "outdoor_sensor": "sensor.buiten",
        **extra,
    }


def cold_with_the_boiler_on() -> dict[str, tuple[str, dict[str, Any]]]:
    """Return two cold rooms and a boiler that is already burning."""
    return {
        "sensor.woonkamer": ("18.0", {}),
        "sensor.zolder": ("17.0", {}),
        "sensor.buiten": ("2.0", {}),
        BOILER: ("heat", {"temperature": 21.0, "hvac_modes": ["heat", "off"]}),
    }


class TestASharedApplianceInsideTheQuietWindow:
    """Stiltevenster x gedeeld apparaat x herstart: een rem, geen slot.

    Quiet window x shared appliance x restart: a brake, not a lock.

    Het stiltevenster houdt een start tegen en laat draaien met rust. Bij een
    gedeeld apparaat werd dat een slot: na een herstart binnen het venster wist
    de director niet meer dat hij die ketel zelf had aangezet, telde hem voor
    geen enkele zone mee, en zette de brandende verwarming uit. Met de hand weer
    aanzetten hielp niet - de volgende ronde deed het weer.

    The quiet window holds a start back and leaves running alone. On a shared
    appliance that turned into a lock: after a restart inside the window the
    director no longer knew it had switched that boiler on itself, counted it for
    no zone at all, and shut the burning heating down. Switching it back on by
    hand did not help - the next round did it again.
    """

    async def test_a_burning_boiler_survives_a_restart_in_the_quiet_window(self) -> None:
        live = await start_house(
            two_zones_on_one_boiler(gates=ALWAYS_QUIET),
            states=cold_with_the_boiler_on(),
            entry_id="kruispunt_stilte",
        )
        config_dir = live.config_dir
        try:
            await live.evaluate()
            assert live.state(BOILER) == "heat", "een brandende ketel gaat niet uit van een rem"
        finally:
            await stop_house(live)

        again = await start_house(
            two_zones_on_one_boiler(gates=ALWAYS_QUIET),
            states=cold_with_the_boiler_on(),
            entry_id="kruispunt_stilte",
            config_dir=config_dir,
        )
        try:
            await again.evaluate()
            assert again.state(BOILER) == "heat", (
                "na een herstart binnen het stiltevenster blijft de ketel branden"
            )
        finally:
            await stop_house(again)


class TestASharedApplianceAndAPriorityThatChanges:
    """Gedeeld apparaat x voorrang die tijdens het draaien verandert.

    Shared appliance x a priority that changes while running.

    Twee zones op een ketel leveren twee commando's voor hetzelfde apparaat, en
    daar wint er een. Wie die keuze op de ingestelde voorrang baseert, negeert
    de schuif waarmee de gebruiker de voorrang net verzet heeft.

    Two zones on one boiler produce two commands for the same appliance, and one
    of them wins. Basing that choice on the configured priority ignores the
    slider with which the user has just moved the priority.
    """

    async def test_the_live_priority_decides_which_zone_the_boiler_follows(self) -> None:
        live = await start_house(
            two_zones_on_one_boiler(),
            states=cold_with_the_boiler_on(),
            entry_id="kruispunt_voorrang",
        )
        try:
            await live.evaluate()
            assert live.attributes(BOILER)["temperature"] == 21.0, "de woonkamer heeft voorrang"

            # De zolder krijgt met de schuif de hoogste voorrang.
            # The attic is given top priority with the slider.
            live.coordinator.zone_priorities["zolder"] = -1
            await live.evaluate()
            assert live.attributes(BOILER)["temperature"] == 20.0, (
                "de ketel hoort de voorrang te volgen die nu geldt"
            )
        finally:
            await stop_house(live)


class TestPresenceOnSomethingOtherThanAPerson:
    """Aanwezigheid op een binary_sensor x een hand aan het apparaat.

    Presence on a binary sensor x a hand at the appliance.

    Het formulier biedt elke entiteit aan die aanwezigheid kan melden, en een
    `binary_sensor` zegt `on` waar een `person` `home` zegt. Wie alleen op
    `home` vergelijkt, leest zo'n huis altijd als leeg - en een leeg huis gooit
    elke ronde de handmatige uitzetting weg die de bewoner net gaf.

    The form offers every entity that can report presence, and a `binary_sensor`
    says `on` where a `person` says `home`. Comparing against `home` alone reads
    such a house as empty every time - and an empty house throws away the
    hand-operated stand-down its occupant just gave, every round.
    """

    @staticmethod
    def _installation() -> dict[str, Any]:
        return {
            "zones": [
                zone(
                    "woonkamer",
                    sources=[source("airco", ATTIC_AIRCO)],
                    indoor_sensor="sensor.woonkamer",
                    heat=settings(21.0, 20.0),
                )
            ],
            "residents": [
                {
                    "resident_id": "danny",
                    "presence_entity": "binary_sensor.iemand_thuis",
                    "sleep_entity": "sensor.danny_lader",
                    "sleep_state": "wireless",
                }
            ],
            "outdoor_sensor": "sensor.buiten",
        }

    @staticmethod
    def _world() -> dict[str, tuple[str, dict[str, Any]]]:
        return {
            "sensor.woonkamer": ("18.0", {}),
            "sensor.buiten": ("2.0", {}),
            "binary_sensor.iemand_thuis": ("on", {}),
            "sensor.danny_lader": ("none", {}),
            ATTIC_AIRCO: ("off", {"hvac_modes": ["heat", "off"]}),
        }

    async def test_a_hand_at_the_appliance_holds_with_a_binary_sensor_at_home(self) -> None:
        live = await start_house(
            self._installation(), states=self._world(), entry_id="kruispunt_aanwezig"
        )
        try:
            await live.evaluate()
            assert live.state(ATTIC_AIRCO) == "heat"

            # Iemand drukt op het apparaat zelf op uit. Eerst uitlopen: de
            # coordinator merkt de hand op in een luisteraar bij de
            # toestandswijziging, en die draait pas als de lus aan de beurt
            # komt. Meteen doorbeslissen is een race die op de ene machine wél
            # en op de andere niet goed valt - deze test viel daardoor lokaal
            # groen en in de CI rood.
            #
            # Somebody presses off on the appliance itself. Let it run out
            # first: the coordinator notices the hand in a listener on the state
            # change, and that only runs once the loop gets round to it.
            # Deciding straight away is a race that lands one way on one machine
            # and another way elsewhere - this test was green locally and red in
            # CI because of it.
            live.set(ATTIC_AIRCO, "off", hvac_modes=["heat", "off"])
            await live.settle()
            await live.evaluate()
            assert live.state(ATTIC_AIRCO) == "off", "de hand houdt tot de volgende dag"

            await live.evaluate()
            assert live.state(ATTIC_AIRCO) == "off", (
                "een thuiszijnde bewoner op een binary_sensor maakt het huis niet leeg"
            )
        finally:
            await stop_house(live)


class TestARoleThatAsksWhatTheApplianceCannotDo:
    """Rol x de standen die het apparaat meldt.

    Role x the modes the appliance reports.

    De rol zegt wat de installatie wil, het apparaat wat het kan. Vraagt de rol
    koelen van een unit die alleen `heat` en `off` kent, dan hoort de engine hem
    over te slaan in plaats van een commando te sturen dat nooit aankomt.

    The role says what the installation wants, the appliance what it can. If the
    role asks cooling of a unit knowing only `heat` and `off`, the engine should
    skip it rather than send a command that never lands.
    """

    async def test_a_unit_without_cool_is_not_commanded_to_cool(self) -> None:
        live = await start_house(
            {
                "zones": [
                    zone(
                        "woonkamer",
                        sources=[source("airco", ATTIC_AIRCO, role="heat_cool")],
                        indoor_sensor="sensor.woonkamer",
                        cool=settings(21.0, 24.0),
                    )
                ],
                "outdoor_sensor": "sensor.buiten",
            },
            states={
                "sensor.woonkamer": ("27.0", {}),
                "sensor.buiten": ("30.0", {}),
                ATTIC_AIRCO: ("off", {"hvac_modes": ["heat", "off"]}),
            },
            entry_id="kruispunt_standen",
        )
        try:
            await live.evaluate()
            assert live.state(ATTIC_AIRCO) == "off"
            assert not [
                call for call in live.climate_calls() if call[1].get("hvac_mode") == "cool"
            ], "een unit die niet kan koelen krijgt geen koelcommando"
        finally:
            await stop_house(live)


class TestTheLifecycle:
    """Opzetten, herladen, afbreken, verwijderen - in die volgorde, echt.

    Setting up, reloading, tearing down, removing - in that order, for real.

    De meeste tests kijken naar een installatie die stilstaat. De fouten die
    overblijven zitten juist in de overgangen: een actie die na het afbreken
    blijft staan, een melding die niet weggaat, een opslagbestand dat blijft
    liggen. Die overgangen staan hier bij elkaar.

    Most tests look at an installation standing still. The faults that remain sit
    in the transitions: an action left standing after tearing down, a notice that
    does not go, a storage file left behind. Those transitions stand here
    together.
    """

    @pytest.fixture
    async def live(self):
        home = await start_house(
            two_zones_on_one_boiler(),
            states=cold_with_the_boiler_on(),
            entry_id="levensloop",
        )
        try:
            yield home
        finally:
            await stop_house(home)

    async def test_setting_up_puts_entities_and_actions_on_the_table(self, live: LiveHome) -> None:
        assert live.registered(), "er horen entiteiten te staan"
        assert live.hass.services.has_service("climate_director", "evaluate")

    async def test_reloading_leaves_one_set_of_entities_behind(self, live: LiveHome) -> None:
        before = live.registered()
        await live.hass.config_entries.async_reload(live.entry.entry_id)
        await live.hass.async_block_till_done()
        assert live.registered() == before, "herladen mag geen dubbele entiteiten opleveren"
        assert live.hass.services.has_service("climate_director", "evaluate")

    async def test_tearing_down_and_setting_up_again_works(self, live: LiveHome) -> None:
        await live.hass.config_entries.async_unload(live.entry.entry_id)
        await live.hass.async_block_till_done()
        assert not live.hass.services.has_service("climate_director", "evaluate")

        await live.hass.config_entries.async_setup(live.entry.entry_id)
        await live.hass.async_block_till_done()
        assert live.hass.services.has_service("climate_director", "evaluate")
        assert live.registered()

    async def test_removing_takes_the_storage_file_with_it(self) -> None:
        from pathlib import Path

        from homeassistant.const import EVENT_HOMEASSISTANT_FINAL_WRITE

        from custom_components.climate_director.coordinator import storage_key

        home = await start_house(
            two_zones_on_one_boiler(),
            states=cold_with_the_boiler_on(),
            entry_id="opruimen",
        )
        try:
            home.coordinator.async_precondition(["woonkamer"], 30)
            # `async_delay_save` schrijft pas na een pauze. Home Assistant duwt
            # zijn opslag eruit bij het laatste schrijfmoment van het afsluiten;
            # dat moment wordt hier nagebootst, want de installatie moet blijven
            # staan om verwijderd te kunnen worden.
            #
            # `async_delay_save` only writes after a pause. Home Assistant
            # flushes its stores on the final write of a shutdown; that moment is
            # imitated here, since the installation has to stay standing in order
            # to be removed.
            home.hass.bus.async_fire(EVENT_HOMEASSISTANT_FINAL_WRITE)
            await home.hass.async_block_till_done()
            path = Path(home.config_dir) / ".storage" / storage_key(home.entry.entry_id)
            assert path.exists(), "er hoort iets bewaard te zijn om op te ruimen"

            await home.hass.config_entries.async_remove(home.entry.entry_id)
            await home.hass.async_block_till_done()
            assert not path.exists(), "een verwijderde installatie laat niets achter"
        finally:
            await home.hass.async_stop(force=True)
