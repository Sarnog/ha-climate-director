"""De handstart in een echte Home Assistant: herkenning, knop, opslag en verval.

The hand start inside a real Home Assistant: recognition, button, storage and expiry.

De engine-toetsen leggen vast welke drie remmen een handstart passeert. Dit
bestand legt de koppelingslaag vast: iemand die zelf een apparaat aanzet, de knop
per zone, een gedeeld apparaat dat elke zone start, de late melding van onze eigen
aanzet, een bron met automatisch aanzetten uit, de opslag over een herstart en het
verval bij slapen, een leeg huis, de volgende dag en het einde van het wachten.
De klok staat stil op een nagebouwde week in augustus 2026; de tijdstempels van
de entiteiten blijven echt.

The engine tests pin down which three brakes a hand start passes. This file pins
down the binding layer: somebody switching an appliance on themselves, the
per-zone button, a shared appliance starting every zone it serves, the late
report of our own switch-on, a source with automatic starting off, the store
across a restart, and expiry on sleep, an empty house, the next day and the end
of the waiting. The clock stands still on a rebuilt week in August 2026; the
entities' timestamps stay real.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
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
from homeassistant.util import dt as dt_util

from custom_components.climate_director import coordinator as coordinator_module
from custom_components.climate_director.diagnostics import async_get_config_entry_diagnostics

LIVING = "climate.woonkamer"
ATTIC = "climate.zolder"
BEDROOM = "climate.slaapkamer"
BOILER = "climate.ketel"
LIVING_SENSOR = "sensor.woonkamer"
ATTIC_SENSOR = "sensor.zolder"
BEDROOM_SENSOR = "sensor.slaapkamer"
OUTDOOR = "sensor.buiten"
OCCUPANCY = "binary_sensor.zolder_bezet"

DANNY = ("person.danny", "sensor.danny_lader")
NANCY = ("person.nancy", "sensor.nancy_lader")


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch):
    """Return a handle that sets the integration's clock to an August 2026 moment."""
    real = dt_util.now
    shift = {"by": timedelta()}

    def _now() -> datetime:
        return real() + shift["by"]

    monkeypatch.setattr(coordinator_module.dt_util, "now", _now)

    class Handle:
        def at(self, day: int, hour: int, minute: int = 0) -> datetime:
            """Put the clock at that day and time, local time."""
            base = real()
            target = datetime(2026, 8, day, hour, minute, tzinfo=base.tzinfo)
            shift["by"] = target - base
            return target

    return Handle()


def resident(
    *,
    deadline: bool = True,
    rise_brake: bool = False,
) -> list[dict[str, Any]]:
    """Return two residents with a night window and the wanted morning rules."""
    found: list[dict[str, Any]] = []
    for resident_id, (person, charger) in (("danny", DANNY), ("nancy", NANCY)):
        item: dict[str, Any] = {
            "resident_id": resident_id,
            "name": resident_id.title(),
            "presence_entity": person,
            "sleep_entity": charger,
            "sleep_state": "wireless",
            "sleep_window": {"start": "21:00:00", "end": "08:00:00", "weekdays": None},
            "sleep_in": {"until": "13:00:00", "weekdays": [5, 6], "holiday": True},
        }
        if deadline:
            item["wake_deadline"] = {
                "at": "11:00:00",
                "weekdays": [5, 6],
                "holiday": True,
            }
        if rise_brake:
            item["rise_brake"] = {"at": "09:00:00", "weekdays": [1]}
        found.append(item)
    return found


def installation(
    *,
    deadline: bool = True,
    rise_brake: bool = False,
    presence_timeout: float = 0.0,
    autostart: bool = True,
    quiet: bool = False,
) -> dict[str, Any]:
    """Return one cold living room with a single air conditioner."""
    extra: dict[str, Any] = {}
    if presence_timeout:
        extra = {
            "presence_entity": OCCUPANCY,
            "presence_state": "on",
            "presence_timeout": presence_timeout,
        }
    gates: dict[str, Any] = {}
    if quiet:
        gates["quiet_windows"] = [
            {"start": "07:00:00", "end": "09:00:00", "weekdays": None, "holiday": False}
        ]
    return {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("woonkamer_airco", LIVING, autostart=autostart)],
                indoor_sensor=LIVING_SENSOR,
                heat=settings(23.0, 22.0),
                **extra,
            )
        ],
        "outdoor_sensor": OUTDOOR,
        "residents": resident(deadline=deadline, rise_brake=rise_brake),
        **({"gates": gates} if gates else {}),
    }


def shared_installation() -> dict[str, Any]:
    """Return three rooms on one boiler thermostat."""
    return {
        "zones": [
            zone(
                "woonkamer",
                sources=[
                    source(
                        "woonkamer_ketel",
                        BOILER,
                        covers_zones=["zolder", "slaapkamer"],
                    )
                ],
                indoor_sensor=LIVING_SENSOR,
                heat=settings(21.0, 20.0),
            ),
            zone(
                "zolder",
                sources=[source("zolder_ketel", BOILER, covers_zones=["woonkamer", "slaapkamer"])],
                indoor_sensor=ATTIC_SENSOR,
                heat=settings(21.0, 20.0),
            ),
            zone(
                "slaapkamer",
                sources=[source("slaapkamer_ketel", BOILER, covers_zones=["woonkamer", "zolder"])],
                indoor_sensor=BEDROOM_SENSOR,
                heat=settings(21.0, 20.0),
            ),
        ],
        "outdoor_sensor": OUTDOOR,
        "residents": resident(),
    }


def world(*, danny_asleep: bool, nancy_asleep: bool, ac: str = "off") -> dict[str, Any]:
    """Return a cold house with both residents home, each awake or asleep."""
    found: dict[str, Any] = {
        LIVING_SENSOR: ("18.0", {}),
        OUTDOOR: ("4.0", {}),
        LIVING: (ac, {"temperature": 21.0}),
    }
    for person, _charger in (DANNY, NANCY):
        found[person] = ("home", {})
    found[DANNY[1]] = ("wireless" if danny_asleep else "none", {})
    found[NANCY[1]] = ("wireless" if nancy_asleep else "none", {})
    return found


def shared_world(*, nancy_asleep: bool) -> dict[str, Any]:
    """Return three cold rooms, both residents home and asleep at the start."""
    found = world(danny_asleep=True, nancy_asleep=nancy_asleep, ac="off")
    found[ATTIC_SENSOR] = ("18.0", {})
    found[BEDROOM_SENSOR] = ("18.0", {})
    found[BOILER] = ("off", {"temperature": 19.0})
    return found


def reason(home: LiveHome, zone_id: str = "woonkamer") -> str:
    """Return one zone's reason in the last decision."""
    decision = home.coordinator.data.decision_for(zone_id)
    assert decision is not None, f"geen beslissing voor {zone_id}"
    return decision.reason.value


async def decide(home: LiveHome) -> None:
    """Let the debouncer and every queued task finish, then decide once."""
    await asyncio.sleep(1.5)
    await home.settle()
    await home.evaluate()


async def a_slept_night(home: LiveHome, clock: Any, *, monday: bool = False) -> None:
    """Start at 23:30, let the house sleep, and wake Danny in the morning."""
    day = 10 if monday else 7
    clock.at(day, 23, 30)
    await decide(home)
    assert home.coordinator._asleep_since is not None, "het huis ging niet slapen"
    clock.at(day + 1, 7 if monday else 8, 0 if monday else 30)
    home.set(DANNY[1], "none")
    await decide(home)


async def prepare_sleeping_house(
    installation_data: dict[str, Any], states: dict[str, Any]
) -> LiveHome:
    """Start the house with these states and return it."""
    return await start_house(installation_data, states=states)


class TestHandStartAtTheAppliance:
    async def test_waiting_for_the_sleeper_yields_to_a_hand_start(self, clock) -> None:
        """W1: de handstart laat de airco regelen en daarna uit en weer aan gaan."""
        home = await prepare_sleeping_house(
            installation(), world(danny_asleep=True, nancy_asleep=True)
        )
        try:
            await a_slept_night(home, clock)
            assert reason(home) == "waiting_for_sleeper"
            home.clear_calls()

            home.climate(LIVING, "heat", current=18.5)
            await decide(home)
            assert home.coordinator._hand_starts.keys() == {"woonkamer"}
            assert reason(home) == "regulating"
            assert home.state(LIVING) == "heat"

            home.set(LIVING_SENSOR, "23.5")
            await decide(home)
            assert home.state(LIVING) == "off"
            assert "woonkamer" in home.coordinator._hand_starts

            home.set(LIVING_SENSOR, "21.5")
            await decide(home)
            assert home.state(LIVING) == "heat"
        finally:
            await stop_house(home)

    async def test_the_rise_brake_yields_through_the_first_stop(self, clock) -> None:
        """D1: de opsta-rem houdt de zone niet meer tegen na de eerste stop."""
        home = await start_house(
            installation(rise_brake=True),
            states=world(danny_asleep=True, nancy_asleep=True),
        )
        try:
            await a_slept_night(home, clock, monday=True)
            assert reason(home) == "early_riser"
            home.clear_calls()

            home.climate(LIVING, "heat", current=18.5)
            await decide(home)
            assert "woonkamer" in home.coordinator._hand_starts
            assert reason(home) == "regulating"

            home.set(LIVING_SENSOR, "23.5")
            await decide(home)
            assert home.state(LIVING) == "off"
            assert "woonkamer" in home.coordinator._hand_starts

            home.set(LIVING_SENSOR, "21.5")
            await decide(home)
            assert home.state(LIVING) == "heat"
        finally:
            await stop_house(home)

    async def test_a_source_with_automatic_start_off_is_no_hand_start(self, clock) -> None:
        """Een bron met automatisch aanzetten uit blijft een handbediend apparaat."""
        home = await start_house(
            installation(autostart=False),
            states=world(danny_asleep=True, nancy_asleep=True),
        )
        try:
            await a_slept_night(home, clock)
            home.climate(LIVING, "heat", current=18.5)
            await decide(home)
            assert home.coordinator._hand_starts == {}
        finally:
            await stop_house(home)

    async def test_our_own_late_switch_on_is_no_hand_start(self) -> None:
        """Een late melding van onze eigen aanzet wordt geen handstart."""
        installation_data = installation(deadline=False)
        home = await start_house(
            installation_data,
            states=world(danny_asleep=False, nancy_asleep=False),
            appliance="late_reporter",
        )
        try:
            await decide(home)
            home.clear_calls()
            await home.evaluate()
            await home.settle()
            assert home.coordinator._hand_starts == {}
        finally:
            await stop_house(home)

    async def test_a_shadow_run_notes_no_hand_start(self, clock) -> None:
        """In schaduwmodus wordt een hand aan het apparaat niet overgenomen."""
        home = await start_house(installation(), states=world(danny_asleep=True, nancy_asleep=True))
        try:
            await a_slept_night(home, clock)
            assert reason(home) == "waiting_for_sleeper"
            home.coordinator.shadow = True
            home.climate(LIVING, "heat", current=18.5)
            await decide(home)
            assert home.coordinator._hand_starts == {}
        finally:
            await stop_house(home)

    async def test_an_empty_state_change_notes_no_hand_start(self) -> None:
        """Een gebeurtenis zonder oude of nieuwe toestand doet niets."""
        home = await start_house(
            installation(deadline=False), states=world(danny_asleep=False, nancy_asleep=False)
        )
        try:
            coordinator = home.coordinator
            coordinator._notice_hand_start(  # type: ignore[arg-type]
                SimpleNamespace(data={"new_state": None, "old_state": None})
            )
            coordinator._notice_hand_start(  # type: ignore[arg-type]
                SimpleNamespace(
                    data={
                        "new_state": SimpleNamespace(state="heat"),
                        "old_state": None,
                    }
                )
            )
            assert coordinator._hand_starts == {}
        finally:
            await stop_house(home)

    async def test_a_wanted_switch_on_is_no_hand_start_while_a_zone_waits(self) -> None:
        """Onze eigen aanzet blijft geen handstart, ook niet tijdens het wachten."""
        home = await start_house(
            installation(deadline=False), states=world(danny_asleep=False, nancy_asleep=False)
        )
        try:
            coordinator = home.coordinator
            coordinator._we_wanted_it_on = lambda *_: True
            coordinator._waiting_on_a_brake = lambda *_: True
            coordinator._notice_hand_start(  # type: ignore[arg-type]
                SimpleNamespace(
                    data={
                        "entity_id": LIVING,
                        "old_state": SimpleNamespace(state="off"),
                        "new_state": SimpleNamespace(state="heat"),
                    }
                )
            )
            assert coordinator._hand_starts == {}
        finally:
            await stop_house(home)


class TestHandStartAtTheButton:
    async def test_the_button_starts_a_waiting_zone(self, clock) -> None:
        """De knop per zone doet hetzelfde als de hand aan het apparaat."""
        home = await start_house(installation(), states=world(danny_asleep=True, nancy_asleep=True))
        try:
            await a_slept_night(home, clock)
            assert reason(home) == "waiting_for_sleeper"
            await home.call(
                "button",
                "press",
                {"entity_id": home.by_key("zone_woonkamer_hand_start")},
            )
            await decide(home)
            assert "woonkamer" in home.coordinator._hand_starts
            assert reason(home) == "regulating"

            fresh = dict(home.coordinator._hand_starts)
            await home.call(
                "button",
                "press",
                {"entity_id": home.by_key("zone_woonkamer_hand_start")},
            )
            home.coordinator.async_hand_start("onbekend")
            home.coordinator._remember_hand_starts(("woonkamer", "onbekend"))
            assert home.coordinator._hand_starts == fresh
        finally:
            await stop_house(home)

    async def test_the_button_does_nothing_in_a_zone_that_waits_on_nothing(self) -> None:
        """Een zone zonder wachtreden verandert niet en geeft geen fout."""
        home = await start_house(
            installation(deadline=False),
            states=world(danny_asleep=False, nancy_asleep=False),
        )
        try:
            await decide(home)
            home.coordinator.async_hand_start("woonkamer")
            assert home.coordinator._hand_starts == {}
            await home.call(
                "button",
                "press",
                {"entity_id": home.by_key("zone_woonkamer_hand_start")},
            )
            await decide(home)
            assert home.coordinator._hand_starts == {}
        finally:
            await stop_house(home)


class TestTheSharedAppliance:
    async def test_the_boiler_starts_every_zone_on_it(self, clock) -> None:
        """De cv met de hand aan start alle drie de zones die erop zitten."""
        home = await start_house(
            shared_installation(),
            states=shared_world(nancy_asleep=True),
        )
        try:
            await a_slept_night(home, clock)
            assert reason(home, "woonkamer") == "waiting_for_sleeper"
            home.climate(BOILER, "heat", current=17.0)
            await decide(home)
            assert set(home.coordinator._hand_starts) == {"woonkamer", "zolder", "slaapkamer"}
            for zone_id in ("woonkamer", "zolder", "slaapkamer"):
                assert reason(home, zone_id) != "waiting_for_sleeper"
        finally:
            await stop_house(home)

    async def test_one_source_row_covering_the_others_starts_them_too(self, clock) -> None:
        """Alleen de eerste zone heeft een bronrij; covers_zones doet de rest."""
        data = shared_installation()
        for zone_data in data["zones"][1:]:
            zone_data["sources"] = []
        home = await start_house(data, states=shared_world(nancy_asleep=True))
        try:
            await a_slept_night(home, clock)
            assert reason(home, "woonkamer") == "waiting_for_sleeper"
            home.climate(BOILER, "heat", current=17.0)
            await decide(home)
            assert set(home.coordinator._hand_starts) == {"woonkamer", "zolder", "slaapkamer"}
        finally:
            await stop_house(home)


class TestTheHandStartLapses:
    async def test_it_survives_a_restart(self, clock) -> None:
        """Een handstart tussen zijn begin en zijn einde komt terug na een herstart."""
        config_dir = new_config_dir()
        home = await start_house(
            installation(),
            states=world(danny_asleep=True, nancy_asleep=True),
            config_dir=config_dir,
        )
        try:
            await a_slept_night(home, clock)
            home.climate(LIVING, "heat", current=18.5)
            await decide(home)
            assert "woonkamer" in home.coordinator._hand_starts
            await asyncio.sleep(1.2)
        finally:
            await stop_house(home)

        again = await start_house(
            installation(),
            states=world(danny_asleep=False, nancy_asleep=True, ac="off"),
            config_dir=config_dir,
        )
        try:
            await decide(again)
            assert "woonkamer" in again.coordinator._hand_starts
            assert reason(again) == "regulating"
        finally:
            await stop_house(again)

    async def test_it_does_not_come_back_after_the_waiting_is_over(self, clock) -> None:
        """Na de uiterste tijd komt een opgeslagen handstart niet terug."""
        config_dir = new_config_dir()
        home = await start_house(
            installation(),
            states=world(danny_asleep=True, nancy_asleep=True),
            config_dir=config_dir,
        )
        try:
            await a_slept_night(home, clock)
            home.climate(LIVING, "heat", current=18.5)
            await decide(home)
            assert "woonkamer" in home.coordinator._hand_starts
            await asyncio.sleep(1.2)
        finally:
            await stop_house(home)

        clock.at(8, 11, 0)
        again = await start_house(
            installation(),
            states=world(danny_asleep=False, nancy_asleep=True, ac="off"),
            config_dir=config_dir,
        )
        try:
            await decide(again)
            assert again.coordinator._hand_starts == {}
        finally:
            await stop_house(again)

    async def test_a_missing_old_or_unknown_stored_note_is_harmless(self, clock) -> None:
        """Een ontbrekende, oude of onbekende notitie leest als geen handstart."""
        clock.at(8, 10, 0)
        home = await start_house(
            installation(), states=world(danny_asleep=False, nancy_asleep=True)
        )
        try:
            coordinator = home.coordinator
            coordinator._hand_starts.clear()
            now = dt_util.now()

            coordinator._restore_hand_starts({}, now)
            coordinator._restore_hand_starts({"hand_starts": ["geen tabel"]}, now)
            coordinator._restore_hand_starts(
                {
                    "hand_starts": {
                        "onbekend": now.isoformat(),
                        "woonkamer": "geen moment",
                    }
                },
                now,
            )
            assert coordinator._hand_starts == {}

            coordinator._restore_hand_starts(
                {"hand_starts": {"woonkamer": (now - timedelta(days=1)).isoformat()}}, now
            )
            assert coordinator._hand_starts == {}

            coordinator._restore_hand_starts({"hand_starts": {"woonkamer": now.isoformat()}}, now)
            fresh = coordinator._hand_starts["woonkamer"]
            coordinator._restore_hand_starts(
                {"hand_starts": {"woonkamer": (now - timedelta(minutes=1)).isoformat()}}, now
            )
            assert coordinator._hand_starts["woonkamer"] == fresh
        finally:
            await stop_house(home)

    async def test_an_unreadable_room_sensor_does_not_lift_the_hand_start(self, clock) -> None:
        """N9: een wegvallende aanwezigheidssensor laat de handstart staan."""
        home = await start_house(
            installation(presence_timeout=2.0),
            states={
                **world(danny_asleep=True, nancy_asleep=True),
                OCCUPANCY: ("on", {}),
            },
        )
        try:
            await a_slept_night(home, clock)
            home.climate(LIVING, "heat", current=18.5)
            await decide(home)
            assert "woonkamer" in home.coordinator._hand_starts

            home.set(OCCUPANCY, "unavailable")
            await decide(home)
            assert "woonkamer" in home.coordinator._hand_starts
        finally:
            await stop_house(home)


class TestTheEndOfTheWaiting:
    async def test_the_hand_start_lapses_when_the_deadline_passes(self, clock) -> None:
        """Een handstart verdwijnt zodra de slaper niet meer tegenhoudt."""
        home = await prepare_sleeping_house(
            installation(), world(danny_asleep=True, nancy_asleep=True)
        )
        try:
            await a_slept_night(home, clock)
            home.climate(LIVING, "heat", current=18.5)
            await decide(home)
            assert "woonkamer" in home.coordinator._hand_starts

            clock.at(8, 11, 0)
            await decide(home)
            assert home.coordinator._hand_starts == {}
            assert reason(home) == "regulating"
        finally:
            await stop_house(home)

    async def test_after_the_deadline_the_house_regulates_without_a_hand_start(self, clock) -> None:
        """Tegenproef: na 11:00 regelt het huis zonder handstart gewoon."""
        home = await start_house(installation(), states=world(danny_asleep=True, nancy_asleep=True))
        try:
            await a_slept_night(home, clock)
            assert reason(home) == "waiting_for_sleeper"
            clock.at(8, 11, 0)
            await decide(home)
            assert home.coordinator._hand_starts == {}
            assert reason(home) == "regulating"
        finally:
            await stop_house(home)

    async def test_it_lapses_when_everybody_goes_to_sleep(self, clock) -> None:
        """Een handstart vervalt zodra iedereen die thuis is naar bed gaat."""
        data = installation(deadline=False)
        data["gates"] = {
            "quiet_windows": [
                {"start": "22:00:00", "end": "23:59:00", "weekdays": None, "holiday": False}
            ]
        }
        clock.at(10, 22, 0)
        home = await start_house(data, states=world(danny_asleep=False, nancy_asleep=False))
        try:
            clock.at(10, 22, 30)
            await decide(home)
            assert reason(home) == "quiet_hours"
            home.climate(LIVING, "heat", current=18.5)
            await decide(home)
            assert "woonkamer" in home.coordinator._hand_starts

            clock.at(10, 23, 30)
            home.set(DANNY[1], "wireless")
            home.set(NANCY[1], "wireless")
            await decide(home)
            assert home.coordinator._hand_starts == {}
        finally:
            await stop_house(home)

    async def test_it_lapses_when_the_house_is_empty(self, clock) -> None:
        """Een handstart vervalt wanneer niemand thuis is."""
        data = installation(deadline=False)
        data["gates"] = {
            "quiet_windows": [
                {"start": "22:00:00", "end": "23:59:00", "weekdays": None, "holiday": False}
            ]
        }
        clock.at(10, 22, 0)
        home = await start_house(data, states=world(danny_asleep=False, nancy_asleep=False))
        try:
            clock.at(10, 22, 30)
            await decide(home)
            home.climate(LIVING, "heat", current=18.5)
            await decide(home)
            assert "woonkamer" in home.coordinator._hand_starts

            home.set(DANNY[0], "not_home")
            home.set(NANCY[0], "not_home")
            await decide(home)
            assert home.coordinator._hand_starts == {}
        finally:
            await stop_house(home)

    async def test_it_lapses_on_the_next_day(self, clock) -> None:
        """Een handstart van gisteren doet vandaag niets meer."""
        data = installation(deadline=False)
        data["gates"] = {
            "quiet_windows": [
                {"start": "00:00:00", "end": "23:59:00", "weekdays": None, "holiday": False}
            ]
        }
        clock.at(10, 22, 0)
        home = await start_house(data, states=world(danny_asleep=False, nancy_asleep=False))
        try:
            clock.at(10, 22, 30)
            await decide(home)
            home.climate(LIVING, "heat", current=18.5)
            await decide(home)
            assert "woonkamer" in home.coordinator._hand_starts

            clock.at(11, 0, 30)
            await decide(home)
            assert home.coordinator._hand_starts == {}
        finally:
            await stop_house(home)


class TestVisibility:
    async def test_diagnostics_and_the_decision_sensor_name_the_hand_start(self, clock) -> None:
        """De diagnose en de beslissensor noemen de zone, niet haar bewoner."""
        home = await start_house(installation(), states=world(danny_asleep=True, nancy_asleep=True))
        try:
            await a_slept_night(home, clock)
            home.climate(LIVING, "heat", current=18.5)
            await decide(home)
            diagnostics = await async_get_config_entry_diagnostics(home.hass, home.entry)
            assert diagnostics["world"]["zone_hand_starts"] == ["woonkamer"]
            assert home.values("last_decision")["hand_starts"] == ["woonkamer"]
        finally:
            await stop_house(home)
