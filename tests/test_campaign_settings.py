"""Elke instelling die een gebruiker kan zetten, in een draaiende Home Assistant.

Every setting a user can pick, inside a running Home Assistant.

De engine-tests laten zien dat een instelling het juiste besluit oplevert. Deze
module laat zien dat de instelling ook werkelijk bij de engine aankomt: hij komt
uit een opgeslagen config entry, gaat door de lezer, door de coordinator en pas
daarna door de engine. Precies in die keten kan een veld stilletjes wegvallen.

De tijd wordt hier verzet in plaats van afgewacht: een raamvertraging, een
nalooptijd, een kortcycluspauze en de vastloopmelder hangen allemaal aan de
klok, en een test die er echt op wacht duurt een kwartier.

The engine tests show that a setting yields the right decision. This module
shows the setting really reaches the engine: it comes out of a stored config
entry, goes through the reader, through the coordinator and only then through
the engine. That chain is exactly where a field can quietly fall away.

Time is moved rather than waited out here: an opening delay, a presence grace
period, a short-cycle pause and the stuck detector all hang on the clock, and a
test that really waits for those takes a quarter of an hour.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from harness_live import settings, source, start_house, stop_house, zone

from custom_components.climate_director import coordinator as coordinator_module
from custom_components.climate_director.engine import Season

LIVING = "climate.woonkamer"
SPARE = "climate.woonkamer_reserve"
ATTIC = "climate.zolder"
BOILER = "climate.ketel"
VALVE = "climate.keuken_kraan"


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch):
    """Return a handle that moves the integration's clock forward.

    Alleen de klok van de integratie schuift op; de tijdstempels van de
    entiteiten blijven staan waar Home Assistant ze zette. Dat is precies wat
    verstrijken van tijd betekent voor de vertragingen in deze integratie.

    Only the integration's clock moves; the entities' timestamps stay where Home
    Assistant put them. That is exactly what elapsed time means for this
    integration's delays.
    """
    from homeassistant.util import dt as dt_util

    real = dt_util.now
    shift = {"by": timedelta()}

    def _now():
        return real() + shift["by"]

    monkeypatch.setattr(coordinator_module.dt_util, "now", _now)

    class Handle:
        def advance(self, **kwargs: Any) -> None:
            shift["by"] += timedelta(**kwargs)

    return Handle()


# ---------------------------------------------------------------------------
# Het seizoen: vier bronnen, elk met hun eigen gevolg.
# The season: four sources, each with its own consequence.
# ---------------------------------------------------------------------------


def summer_house(seasons: dict[str, Any]) -> dict[str, Any]:
    """Return a one-room house that may only cool in the summer."""
    return {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("airco", LIVING, role="heat_cool")],
                cool=settings(22.0, 24.0, seasons=["summer"]),
                heat=settings(21.0, 18.0),
            )
        ],
        "seasons": seasons,
    }


def hot_world() -> dict[str, tuple[str, dict[str, Any]]]:
    """Return a world in which the room is hot enough to want cooling."""
    return {"sensor.woonkamer": ("26.0", {}), LIVING: ("off", {})}


class TestTheSeasonSetting:
    """De vier manieren waarop het seizoen bepaald kan worden.

    The four ways the season can be settled.
    """

    async def test_pinned_to_summer_lets_the_room_cool(self) -> None:
        home = await start_house(summer_house({"source": "summer"}), states=hot_world())
        try:
            assert home.coordinator.world.season is Season.SUMMER
            assert home.state(LIVING) == "cool"
        finally:
            await stop_house(home)

    async def test_pinned_to_winter_refuses_to_cool(self) -> None:
        """Zesentwintig graden in de winter: de airco blijft uit.

        De gemelde reden is die van de verwarmkant (`satisfied`), niet die van
        de koelkant: een zone rapporteert één reden, en de verwarmkant gaat
        voor. Wat telt voor de veiligheid is dat er niet gekoeld wordt.

        Twenty-six degrees in winter: the air conditioner stays off. The
        reported reason is the heating side's (`satisfied`) rather than the
        cooling side's: a zone reports one reason, and heating comes first.
        What counts for safety is that no cooling happens.
        """
        home = await start_house(summer_house({"source": "winter"}), states=hot_world())
        try:
            assert home.state(LIVING) == "off"
            assert home.values("zone_woonkamer_source")["granted"] == "neutral"
        finally:
            await stop_house(home)

    @pytest.mark.parametrize(
        ("reported", "cools"),
        [
            ("summer", True),
            ("zomer", True),
            ("Zomer", True),
            ("été", True),
            ("winter", False),
            ("herfst", False),
            ("lente", False),
            ("onzin", False),
            ("unavailable", False),
        ],
    )
    async def test_an_entity_may_name_the_season_in_several_languages(
        self, reported: str, cools: bool
    ) -> None:
        home = await start_house(
            summer_house({"source": "entity", "entity_id": "sensor.seizoen"}),
            states={**hot_world(), "sensor.seizoen": (reported, {})},
        )
        try:
            assert (home.state(LIVING) == "cool") is cools
        finally:
            await stop_house(home)

    async def test_the_month_table_decides_on_automatic(self) -> None:
        """Augustus staat in de standaard zomermaanden, dus koelen mag.

        August is in the default summer months, so cooling is allowed.
        """
        home = await start_house(
            summer_house({"source": "auto", "summer_months": [8]}), states=hot_world()
        )
        try:
            expected = Season.SUMMER if home.coordinator.world.now.month == 8 else Season.WINTER
            assert home.coordinator.world.season is expected
        finally:
            await stop_house(home)

    async def test_the_select_overrides_the_season(self) -> None:
        """Eén draai aan de select zet winter opzij, en terug op auto weer niet.

        One turn of the select overrides winter, and back to auto it no longer
        does.
        """
        home = await start_house(summer_house({"source": "winter"}), states=hot_world())
        try:
            assert home.state(LIVING) == "off"
            await home.call(
                "select",
                "select_option",
                {"entity_id": home.by_key("season"), "option": "summer"},
            )
            await home.evaluate()
            assert home.coordinator.season_override is Season.SUMMER
            assert home.coordinator.world.season is Season.SUMMER
            assert home.state(LIVING) == "cool"

            await home.call(
                "select",
                "select_option",
                {"entity_id": home.by_key("season"), "option": "auto"},
            )
            await home.evaluate()
            assert home.coordinator.season_override is None
            assert home.coordinator.world.season is Season.WINTER
        finally:
            await stop_house(home)


# ---------------------------------------------------------------------------
# De poorten: rooster, stilte, gasten, vakantie-agenda.
# The gates: schedule, quiet, guests, holiday calendar.
# ---------------------------------------------------------------------------


def gated_house(**gates: Any) -> dict[str, Any]:
    """Return a house whose gates can be dialled in per test."""
    return {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("airco", LIVING, role="heat_cool")],
                heat=settings(21.0, 20.0),
            )
        ],
        "residents": [
            {
                "resident_id": "danny",
                "presence_entity": "person.danny",
                "sleep_entity": "sensor.danny_lader",
                "sleep_state": "wireless",
                "windows": [{"start": "07:00:00", "end": "23:00:00"}],
            }
        ],
        "gates": gates,
    }


def cold_at_home() -> dict[str, tuple[str, dict[str, Any]]]:
    """Return a cold room with somebody home and awake."""
    return {
        "sensor.woonkamer": ("18.0", {}),
        LIVING: ("off", {}),
        "person.danny": ("home", {}),
        "sensor.danny_lader": ("none", {}),
    }


class TestTheHouseholdGates:
    """Wie thuis is, wakker is en binnen zijn rooster valt.

    Who is home, awake and inside their schedule.
    """

    async def test_nobody_home_stops_the_house(self) -> None:
        home = await start_house(
            gated_house(), states={**cold_at_home(), "person.danny": ("not_home", {})}
        )
        try:
            assert home.state(LIVING) == "off"
            assert home.values("zone_woonkamer_source")["reason"] == "nobody_home"
        finally:
            await stop_house(home)

    async def test_asleep_stops_the_house_when_awake_is_required(self) -> None:
        home = await start_house(
            gated_house(require_awake=True),
            states={**cold_at_home(), "sensor.danny_lader": ("wireless", {})},
        )
        try:
            assert home.values("zone_woonkamer_source")["reason"] == "everyone_asleep"
        finally:
            await stop_house(home)

    async def test_switching_the_awake_requirement_off_lets_it_run(self) -> None:
        home = await start_house(
            gated_house(require_awake=False),
            states={**cold_at_home(), "sensor.danny_lader": ("wireless", {})},
        )
        try:
            assert home.state(LIVING) == "heat"
        finally:
            await stop_house(home)

    async def test_a_guest_carries_the_house_inside_the_guest_window(self) -> None:
        home = await start_house(
            gated_house(guest_window={"start": "00:00:00", "end": "23:59:00"}),
            states={**cold_at_home(), "person.danny": ("not_home", {})},
        )
        try:
            assert home.state(LIVING) == "off"
            await home.call("switch", "turn_on", {"entity_id": home.by_key("guest")})
            await home.evaluate()
            assert home.state(LIVING) == "heat"
        finally:
            await stop_house(home)

    async def test_a_guest_outside_the_guest_window_changes_nothing(self) -> None:
        """Een venster van een minuut waar we nu zeker niet in zitten.

        A one-minute window we are certainly not inside right now.
        """
        home = await start_house(
            gated_house(guest_window={"start": "03:00:00", "end": "03:01:00"}),
            states={**cold_at_home(), "person.danny": ("not_home", {})},
        )
        try:
            await home.call("switch", "turn_on", {"entity_id": home.by_key("guest")})
            await home.evaluate()
            hour = home.coordinator.world.now.hour
            expected = "heat" if hour == 3 else "off"
            assert home.state(LIVING) == expected
        finally:
            await stop_house(home)


class TestTheHolidayCalendar:
    """Een agenda mag het huis op vakantie zetten, maar alleen met trefwoord.

    A calendar may put the house on holiday, but only with a keyword.
    """

    def _house(self, keyword: str) -> dict[str, Any]:
        found = gated_house()
        found["holiday_calendars"] = ["calendar.familie"]
        found["holiday_keyword"] = keyword
        return found

    async def test_a_running_event_with_the_keyword_counts(self) -> None:
        home = await start_house(
            self._house("vakantie"),
            states={
                **cold_at_home(),
                "calendar.familie": ("on", {"message": "Zomervakantie Spanje"}),
            },
        )
        try:
            assert home.coordinator.world.holiday_mode is True
        finally:
            await stop_house(home)

    async def test_an_event_without_the_keyword_does_not(self) -> None:
        home = await start_house(
            self._house("vakantie"),
            states={**cold_at_home(), "calendar.familie": ("on", {"message": "Tandarts"})},
        )
        try:
            assert home.coordinator.world.holiday_mode is False
        finally:
            await stop_house(home)

    async def test_without_a_keyword_the_calendar_is_left_alone(self) -> None:
        home = await start_house(
            self._house(""),
            states={**cold_at_home(), "calendar.familie": ("on", {"message": "Vakantie"})},
        )
        try:
            assert home.coordinator.world.holiday_mode is False
        finally:
            await stop_house(home)

    async def test_an_event_that_is_not_running_does_not_count(self) -> None:
        home = await start_house(
            self._house("vakantie"),
            states={**cold_at_home(), "calendar.familie": ("off", {"message": "Vakantie"})},
        )
        try:
            assert home.coordinator.world.holiday_mode is False
        finally:
            await stop_house(home)


# ---------------------------------------------------------------------------
# Alles wat aan de klok hangt.
# Everything hanging on the clock.
# ---------------------------------------------------------------------------


class TestTheDelays:
    """Vertragingen, nalooptijden en pauzes, met de klok vooruit gezet.

    Delays, grace periods and pauses, with the clock moved forward.
    """

    async def test_an_opening_only_bites_after_its_delay(self, clock) -> None:
        installation = {
            "zones": [
                zone(
                    "woonkamer",
                    sources=[source("airco", LIVING, role="heat_cool")],
                    heat=settings(21.0, 20.0),
                )
            ],
            "openings": [{"entity_id": "binary_sensor.deur", "delay": 300}],
        }
        home = await start_house(
            installation,
            states={
                "sensor.woonkamer": ("18.0", {}),
                LIVING: ("off", {}),
                "binary_sensor.deur": ("off", {}),
            },
        )
        try:
            assert home.state(LIVING) == "heat"
            home.set("binary_sensor.deur", "on")
            await home.evaluate()
            assert home.state(LIVING) == "heat", "vijf minuten zijn nog niet om"

            clock.advance(minutes=6)
            await home.evaluate()
            assert home.state(LIVING) == "off"
        finally:
            await stop_house(home)

    async def test_a_room_stays_occupied_for_its_grace_period(self, clock) -> None:
        installation = {
            "zones": [
                zone(
                    "zolder",
                    sources=[source("airco", ATTIC, role="heat_cool")],
                    heat=settings(21.0, 20.0),
                    gate="presence",
                    presence_entity="binary_sensor.zolder_aanwezig",
                    presence_timeout=900,
                )
            ]
        }
        home = await start_house(
            installation,
            states={
                "sensor.zolder": ("18.0", {}),
                ATTIC: ("off", {}),
                "binary_sensor.zolder_aanwezig": ("on", {}),
            },
        )
        try:
            assert home.state(ATTIC) == "heat"
            home.set("binary_sensor.zolder_aanwezig", "off")
            await home.evaluate()
            assert home.state(ATTIC) == "heat", "de nalooptijd van een kwartier loopt nog"

            clock.advance(minutes=16)
            await home.evaluate()
            assert home.state(ATTIC) == "off"
            assert home.values("zone_zolder_source")["reason"] == "zone_unoccupied"
        finally:
            await stop_house(home)

    async def test_short_cycle_protection_holds_a_restart_back(self, clock) -> None:
        installation = {
            "zones": [
                zone(
                    "woonkamer",
                    sources=[source("airco", LIVING, role="heat_cool")],
                    heat=settings(21.0, 20.0),
                )
            ],
            "circuits": [
                {
                    "circuit_id": "buiten",
                    "name": "Buiten",
                    "units": [LIVING],
                    "simultaneous_heat_cool": False,
                    "min_cycle_time": 900,
                }
            ],
        }
        home = await start_house(
            installation,
            states={"sensor.woonkamer": ("23.0", {}), LIVING: ("off", {})},
        )
        try:
            assert home.state(LIVING) == "off"
            home.set("sensor.woonkamer", "18.0")
            await home.evaluate()
            assert home.state(LIVING) == "off", "de unit stopte net; starten mag nog niet"
            assert home.values("zone_woonkamer_source")["reason"] == "short_cycle_protection"
            assert home.values("last_decision")["deferrals"], "er hoort een herkansing te staan"

            clock.advance(minutes=16)
            await home.evaluate()
            assert home.state(LIVING) == "heat"
        finally:
            await stop_house(home)

    async def test_a_zone_that_keeps_waiting_is_reported_as_stuck(self, clock) -> None:
        installation = {
            "zones": [
                zone(
                    "woonkamer",
                    sources=[source("airco", LIVING, role="heat_cool")],
                    heat=settings(21.0, 20.0),
                )
            ],
            "circuits": [
                {
                    "circuit_id": "buiten",
                    "name": "Buiten",
                    "units": [LIVING],
                    "simultaneous_heat_cool": False,
                    "min_cycle_time": 36000,
                }
            ],
            "stuck_after": 900,
        }
        home = await start_house(
            installation,
            states={"sensor.woonkamer": ("18.0", {}), LIVING: ("off", {})},
        )
        try:
            await home.evaluate()
            assert home.coordinator.stuck_zones() == {}
            clock.advance(minutes=20)
            await home.evaluate()
            assert "woonkamer" in home.coordinator.stuck_zones()
            assert home.value("stuck") == "on"
            assert home.values("stuck")["zones"] == ["woonkamer"]
        finally:
            await stop_house(home)


# ---------------------------------------------------------------------------
# Het circuit: wie wint er, en hoeveel mag er tegelijk.
# The circuit: who wins, and how much may run at once.
# ---------------------------------------------------------------------------


def two_room_circuit(**circuit: Any) -> dict[str, Any]:
    """Return two rooms on one outdoor unit, with the circuit dialled in."""
    return {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("woonkamer_airco", LIVING, role="heat_cool")],
                heat=settings(21.0, 20.0),
                cool=settings(22.0, 24.0),
                priority=0,
            ),
            zone(
                "zolder",
                sources=[source("zolder_airco", ATTIC, role="heat_cool")],
                heat=settings(21.0, 20.0),
                cool=settings(22.0, 24.0),
                priority=1,
            ),
        ],
        "circuits": [
            {
                "circuit_id": "buiten",
                "name": "Buiten",
                "units": [LIVING, ATTIC],
                "simultaneous_heat_cool": False,
                **circuit,
            }
        ],
        "seasons": {"source": "summer"},
    }


def opposing_world() -> dict[str, tuple[str, dict[str, Any]]]:
    """Return a world where one room wants heat and the other wants cooling."""
    return {
        "sensor.woonkamer": ("26.0", {}),
        "sensor.zolder": ("18.0", {}),
        LIVING: ("off", {}),
        ATTIC: ("off", {}),
    }


class TestTheCircuitRules:
    """Wat er gebeurt als twee kamers het tegelijk anders willen.

    What happens when two rooms want opposite things at once.
    """

    async def test_priority_hands_the_circuit_to_the_first_room(self) -> None:
        home = await start_house(
            two_room_circuit(conflict_policy="priority"), states=opposing_world()
        )
        try:
            assert home.state(LIVING) == "cool"
            assert home.state(ATTIC) == "off"
            assert home.values("zone_zolder_source")["reason"] == "circuit_conflict_lost"
        finally:
            await stop_house(home)

    async def test_a_lost_room_may_keep_circulating_air_when_allowed(self) -> None:
        home = await start_house(
            two_room_circuit(conflict_policy="priority", allow_fan_only_during_conflict=True),
            states=opposing_world(),
        )
        try:
            assert home.state(ATTIC) == "fan_only"
        finally:
            await stop_house(home)

    async def test_demand_hands_it_to_the_room_that_needs_it_most(self) -> None:
        """De zolder wijkt drie graden af, de woonkamer twee.

        The attic deviates by three degrees, the living room by two.
        """
        home = await start_house(
            two_room_circuit(conflict_policy="demand"),
            states={**opposing_world(), "sensor.zolder": ("17.0", {})},
        )
        try:
            assert home.state(ATTIC) == "heat"
            assert home.state(LIVING) == "off"
        finally:
            await stop_house(home)

    async def test_the_season_lock_hands_it_to_the_summer_duty(self) -> None:
        home = await start_house(
            two_room_circuit(conflict_policy="season_lock"),
            states={**opposing_world(), "sensor.zolder": ("15.0", {})},
        )
        try:
            assert home.state(LIVING) == "cool", "de zomer kiest koelen, hoe groot de vraag ook is"
        finally:
            await stop_house(home)

    async def test_first_come_lets_the_running_duty_keep_the_circuit(self) -> None:
        home = await start_house(
            two_room_circuit(conflict_policy="first_come"),
            states={**opposing_world(), "sensor.zolder": ("15.0", {}), ATTIC: ("heat", {})},
        )
        try:
            assert home.state(ATTIC) == "heat"
            assert home.state(LIVING) == "off"
        finally:
            await stop_house(home)

    async def test_the_capacity_limit_keeps_the_second_room_out(self) -> None:
        home = await start_house(
            two_room_circuit(max_concurrent_units=1),
            states={
                "sensor.woonkamer": ("18.0", {}),
                "sensor.zolder": ("18.0", {}),
                LIVING: ("off", {}),
                ATTIC: ("off", {}),
            },
        )
        try:
            assert home.state(LIVING) == "heat"
            assert home.state(ATTIC) == "off"
            assert home.values("zone_zolder_source")["reason"] == "circuit_at_capacity"
        finally:
            await stop_house(home)

    async def test_a_duty_swap_stops_before_it_starts(self) -> None:
        """Met een omschakelpauze gebeurt het stoppen nu en het starten straks.

        With a switch pause the stopping happens now and the starting later.
        """
        home = await start_house(
            two_room_circuit(family_switch_delay=300),
            states={
                "sensor.woonkamer": ("26.0", {}),
                "sensor.zolder": ("26.0", {}),
                LIVING: ("heat", {}),
                ATTIC: ("off", {}),
            },
        )
        try:
            assert home.state(LIVING) == "off", "eerst loslaten"
            assert home.values("zone_woonkamer_source")["reason"] == "circuit_switch_pending"
            assert home.values("last_decision")["deferrals"]
            await home.evaluate()
            assert home.state(LIVING) == "cool", "en daarna pas de andere taak"
        finally:
            await stop_house(home)


# ---------------------------------------------------------------------------
# De gedeelde warmtebron.
# The shared heat source.
# ---------------------------------------------------------------------------


def boiler_house(**generator: Any) -> dict[str, Any]:
    """Return two rooms with valves and one shared boiler."""
    return {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("woonkamer_kraan", LIVING, role="heat_only")],
                heat=settings(21.0, 20.0),
            ),
            zone(
                "keuken",
                sources=[source("keuken_kraan", VALVE, role="heat_only")],
                heat=settings(19.0, 18.0),
                priority=1,
            ),
        ],
        "generators": [
            {
                "generator_id": "ketel",
                "name": "Ketel",
                "entity_id": BOILER,
                "zone_ids": ["woonkamer", "keuken"],
                **generator,
            }
        ],
    }


class TestTheSharedBoiler:
    """De ketel volgt de kranen, en start als laatste.

    The boiler follows the valves, and starts last.
    """

    async def test_the_boiler_follows_the_warmest_demand(self) -> None:
        home = await start_house(
            boiler_house(),
            states={
                "sensor.woonkamer": ("18.0", {}),
                "sensor.keuken": ("17.0", {}),
                LIVING: ("off", {}),
                VALVE: ("off", {}),
                BOILER: ("off", {}),
            },
        )
        try:
            assert home.state(BOILER) == "heat"
            assert home.attributes(BOILER)["temperature"] == 21.0, "de warmste vraag wint"
        finally:
            await stop_house(home)

    async def test_a_fixed_setpoint_overrules_the_rooms(self) -> None:
        home = await start_house(
            boiler_house(setpoint=55.0),
            states={
                "sensor.woonkamer": ("18.0", {}),
                "sensor.keuken": ("17.0", {}),
                LIVING: ("off", {}),
                VALVE: ("off", {}),
                BOILER: ("off", {}),
            },
        )
        try:
            assert home.attributes(BOILER)["temperature"] == 55.0
        finally:
            await stop_house(home)

    async def test_the_boiler_goes_off_once_every_room_is_warm(self) -> None:
        home = await start_house(
            boiler_house(),
            states={
                "sensor.woonkamer": ("23.0", {}),
                "sensor.keuken": ("23.0", {}),
                LIVING: ("off", {}),
                VALVE: ("off", {}),
                BOILER: ("heat", {}),
            },
        )
        try:
            assert home.state(BOILER) == "off"
        finally:
            await stop_house(home)

    async def test_the_valves_open_before_the_boiler_fires(self) -> None:
        home = await start_house(
            boiler_house(),
            states={
                "sensor.woonkamer": ("18.0", {}),
                "sensor.keuken": ("17.0", {}),
                LIVING: ("off", {}),
                VALVE: ("off", {}),
                BOILER: ("off", {}),
            },
        )
        try:
            ordered = [data["entity_id"] for _name, data in home.climate_calls()]
            assert ordered.index(BOILER) == len(ordered) - 1, (
                "de ketel hoort als laatste aan de beurt te zijn"
            )
        finally:
            await stop_house(home)


# ---------------------------------------------------------------------------
# Wie met de hand aan het apparaat komt.
# Whoever touches the appliance by hand.
# ---------------------------------------------------------------------------


class TestAHandOnTheAppliance:
    """Zelf uitzetten geeft de kamer terug tot de volgende dag.

    Switching off yourself hands the room back until the next day.
    """

    async def test_switching_it_off_by_hand_silences_the_zone(self) -> None:
        installation = {
            "zones": [
                zone(
                    "woonkamer",
                    sources=[source("airco", LIVING, role="heat_cool")],
                    heat=settings(21.0, 20.0),
                )
            ],
            "residents": [
                {
                    "resident_id": "danny",
                    "presence_entity": "person.danny",
                    "sleep_entity": "sensor.danny_lader",
                    "sleep_state": "wireless",
                }
            ],
        }
        home = await start_house(
            installation,
            states={
                "sensor.woonkamer": ("18.0", {}),
                LIVING: ("off", {}),
                "person.danny": ("home", {}),
                "sensor.danny_lader": ("none", {}),
            },
        )
        try:
            assert home.state(LIVING) == "heat"

            # Iemand drukt bij het apparaat zelf op uit.
            # Somebody presses off on the appliance itself.
            home.climate(LIVING, "off")
            await home.settle()
            await home.evaluate()

            assert home.state(LIVING) == "off", "de director hoort dat niet te overrulen"
            assert home.value(f"command_{LIVING}") == "left_alone"
            assert home.values(f"command_{LIVING}")["reason"] == "manual_override"

            # En weer aanzetten laat hem gewoon meedoen.
            # And switching it back on has it join in again.
            home.climate(LIVING, "heat")
            await home.settle()
            await home.evaluate()
            assert home.coordinator._zones_handed_back() == set()
        finally:
            await stop_house(home)

    @pytest.mark.parametrize("gone", ["unavailable", "unknown"])
    async def test_an_appliance_dropping_out_and_back_is_not_a_hand(self, gone: str) -> None:
        """Wegvallen en terugkomen mag geen zone stilleggen.

        Een apparaat dat terugkomt meldt eerst `off`, en dat lijkt sprekend op
        iemand die net op uit drukte. Bij een herstart van Home Assistant komt
        elk apparaat zo langs, dus dit hoort echt niet mee te tellen.

        Dropping out and coming back may not silence a zone. An appliance coming
        back reports `off` first, and that looks exactly like somebody having
        just pressed off. On a restart of Home Assistant every appliance passes
        through this, so it really must not count.
        """
        installation = {
            "zones": [
                zone(
                    "woonkamer",
                    sources=[source("airco", LIVING, role="heat_cool")],
                    heat=settings(21.0, 20.0),
                )
            ]
        }
        home = await start_house(
            installation, states={"sensor.woonkamer": ("18.0", {}), LIVING: ("off", {})}
        )
        try:
            assert home.state(LIVING) == "heat"

            home.set(LIVING, gone)
            await home.settle()
            assert home.coordinator._zones_handed_back() == set(), (
                "wegvallen is geen hand aan het apparaat"
            )

            home.climate(LIVING, "off")
            await home.settle()
            assert home.coordinator._zones_handed_back() == set(), "terugkomen is dat evenmin"

            await home.evaluate()
            assert home.state(LIVING) == "heat", "de kamer hoort gewoon weer geregeld te worden"
        finally:
            await stop_house(home)

    @pytest.mark.parametrize("gone", ["unavailable", "unknown"])
    async def test_dropping_out_does_not_lift_a_hand_back(self, gone: str) -> None:
        """Een zone die met de hand is stilgezet blijft dat, ook als het apparaat wegvalt.

        A zone silenced by hand stays that way, even when the appliance drops out.
        """
        installation = {
            "zones": [
                zone(
                    "woonkamer",
                    sources=[source("airco", LIVING, role="heat_cool")],
                    heat=settings(21.0, 20.0),
                )
            ]
        }
        home = await start_house(
            installation, states={"sensor.woonkamer": ("18.0", {}), LIVING: ("off", {})}
        )
        try:
            home.climate(LIVING, "off")
            await home.settle()
            assert home.coordinator._zones_handed_back() == {"woonkamer"}

            home.set(LIVING, gone)
            await home.settle()
            assert home.coordinator._zones_handed_back() == {"woonkamer"}
        finally:
            await stop_house(home)

    async def test_in_shadow_mode_nothing_counts_as_a_hand(self) -> None:
        """Meelopen mag het vergelijken niet stilleggen.

        In schaduwmodus stuurt de director niets en zetten de bestaande
        automatiseringen de apparaten aan en uit. Zou elke uitzetting als een
        hand tellen, dan is elke zone binnen een dag overgedragen en meldt de
        integratie niets meer - terwijl dat melden het enige is wat deze modus
        oplevert.

        Running along may not silence the comparison. In shadow mode the
        director steers nothing and the existing automations switch the
        appliances on and off. Were every switch-off to count as a hand, every
        zone would be handed over within a day and the integration would report
        nothing - while that reporting is all this mode yields.
        """
        installation = {
            "zones": [
                zone(
                    "woonkamer",
                    sources=[source("airco", LIVING, role="heat_cool")],
                    heat=settings(21.0, 20.0),
                )
            ]
        }
        home = await start_house(
            installation,
            states={"sensor.woonkamer": ("18.0", {}), LIVING: ("heat", {})},
            shadow=True,
        )
        try:
            assert home.coordinator.data.command_for(LIVING).hvac_mode == "heat"

            # Een bestaande automatisering zet het apparaat uit.
            # An existing automation switches the appliance off.
            home.climate(LIVING, "off")
            await home.settle()
            assert home.coordinator._zones_handed_back() == set()

            await home.evaluate()
            command = home.coordinator.data.command_for(LIVING)
            assert command is not None and command.hvac_mode == "heat", (
                "de director hoort te blijven melden wat hij gedaan zou hebben"
            )
            assert home.value("mismatch") == "1"
            assert home.climate_calls() == [], "en er mag nog steeds niets gestuurd worden"
        finally:
            await stop_house(home)

    async def test_our_own_switch_off_is_not_a_hand(self) -> None:
        installation = {
            "zones": [
                zone(
                    "woonkamer",
                    sources=[source("airco", LIVING, role="heat_cool")],
                    heat=settings(21.0, 20.0),
                )
            ],
            "residents": [
                {
                    "resident_id": "danny",
                    "presence_entity": "person.danny",
                    "sleep_entity": "sensor.danny_lader",
                    "sleep_state": "wireless",
                }
            ],
        }
        home = await start_house(
            installation,
            states={
                "sensor.woonkamer": ("18.0", {}),
                LIVING: ("off", {}),
                "person.danny": ("home", {}),
                "sensor.danny_lader": ("none", {}),
            },
        )
        try:
            assert home.state(LIVING) == "heat"
            home.set("sensor.woonkamer", "23.0")
            await home.evaluate()
            await home.settle()
            assert home.state(LIVING) == "off"
            assert home.coordinator._zones_handed_back() == set(), (
                "ons eigen uitzetten mag de zone niet stilleggen"
            )

            home.set("sensor.woonkamer", "18.0")
            await home.evaluate()
            assert home.state(LIVING) == "heat"
        finally:
            await stop_house(home)


# ---------------------------------------------------------------------------
# Twee installaties naast elkaar.
# Two installations side by side.
# ---------------------------------------------------------------------------


async def test_two_installations_keep_their_own_entities_and_actions() -> None:
    """Twee huizen in één Home Assistant mogen elkaar niet in de weg zitten.

    Two houses in one Home Assistant must not get in each other's way.
    """
    first_installation = {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("airco", LIVING, role="heat_cool")],
                heat=settings(21.0, 20.0),
            )
        ]
    }
    home = await start_house(
        first_installation,
        states={"sensor.woonkamer": ("18.0", {}), LIVING: ("off", {}), ATTIC: ("off", {})},
        entry_id="huis_een",
        title="Huis een",
    )
    try:
        from homeassistant.config_entries import ConfigEntry

        second = ConfigEntry(
            data={
                "installation": {
                    "zones": [
                        zone(
                            "zolder",
                            sources=[source("airco2", ATTIC, role="heat_cool")],
                            heat=settings(21.0, 20.0),
                        )
                    ]
                }
            },
            options={"shadow_mode": False},
            domain="climate_director",
            minor_version=1,
            version=1,
            source="user",
            title="Huis twee",
            unique_id=None,
            discovery_keys={},  # type: ignore[arg-type]
            subentries_data=None,
            entry_id="huis_twee",
        )
        home.set("sensor.zolder", "18.0")
        await home.hass.config_entries.async_add(second)
        await home.hass.async_block_till_done()

        assert home.state(LIVING) == "heat"
        assert home.state(ATTIC) == "heat"

        # De actie mag op één installatie gericht worden.
        # The action may be aimed at one installation.
        await home.call(
            "climate_director", "precondition", {"entry_id": "huis_twee", "minutes": 30}
        )
        await home.settle()
        assert home.coordinator._live_preconditions() == {}
        assert second.runtime_data._live_preconditions()

        # En elke installatie houdt zijn eigen entiteiten.
        # And every installation keeps its own entities.
        from homeassistant.helpers import entity_registry

        registry = entity_registry.async_get(home.hass)
        first_ids = {
            item.entity_id
            for item in registry.entities.values()
            if item.config_entry_id == "huis_een"
        }
        second_ids = {
            item.entity_id
            for item in registry.entities.values()
            if item.config_entry_id == "huis_twee"
        }
        assert first_ids and second_ids
        assert not (first_ids & second_ids)
    finally:
        await stop_house(home)


# ---------------------------------------------------------------------------
# De diagnose.
# The diagnostics.
# ---------------------------------------------------------------------------


async def test_the_diagnostics_describe_the_whole_installation() -> None:
    """Wat je downloadt bij een storingsmelding moet compleet en leesbaar zijn.

    What you download with a bug report has to be complete and readable.
    """
    import json

    from custom_components.climate_director.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    installation = {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("airco", LIVING, role="heat_cool")],
                heat=settings(21.0, 20.0),
            )
        ],
        "outdoor_sensor": "sensor.buiten",
    }
    home = await start_house(
        installation,
        states={
            "sensor.woonkamer": ("18.0", {}),
            "sensor.buiten": ("3.0", {}),
            LIVING: ("off", {}),
        },
    )
    try:
        found = await async_get_config_entry_diagnostics(home.hass, home.entry)
        assert json.dumps(found, default=str), "de diagnose moet als JSON weg kunnen"
        text = json.dumps(found, default=str)
        assert "woonkamer" in text
        assert LIVING in text
    finally:
        await stop_house(home)
