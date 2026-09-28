"""Het moment waarop het huis ging slapen, vastgelegd en hersteld in een draaiende Home Assistant.

The moment the house went to sleep, recorded and restored in a running Home Assistant.

`tests/test_the_night.py` legt de regel vast in de engine. Dit bestand legt vast dat
de koppelingslaag het moment werkelijk vastlegt zodra iedereen die thuis is slaapt,
en niet eerder (N9); dat het een herstart overleeft, ook als die midden in de nacht
of in de ochtend valt (N8); en dat een herstart terwijl iemand op was geen moment
verzint, zodat er niet gewacht wordt (N7).

De klok van de integratie wordt op een vaste nacht gezet (vrijdag 14 op zaterdag 15
augustus 2026); de tijdstempels van de entiteiten blijven echt. Het slaapvenster
(21:00–08:00) en de uiterste tijd (11:00 op zaterdag) worden tegen die klok gelezen.

`tests/test_the_night.py` pins the rule down in the engine. This file pins down that
the binding layer really records the moment as soon as everybody at home is asleep,
and not before (N9); that it survives a restart, also one in the middle of the night
or in the morning (N8); and that a restart while somebody was up invents no moment,
so nobody is waited for (N7).

The integration's clock is set to a fixed night (Friday 14 to Saturday 15 August
2026); the entities' timestamps stay real. The sleep window (21:00–08:00) and the
deadline (11:00 on Saturday) are read against that clock.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest
from harness_live import LiveHome, new_config_dir, settings, source, start_house, stop_house, zone

from custom_components.climate_director import coordinator as coordinator_module

LIVING = "climate.woonkamer"
PEOPLE = {
    "danny": ("person.danny", "sensor.danny_lader"),
    "nancy": ("person.nancy", "sensor.nancy_lader"),
}


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch):
    """Return a handle that sets the integration's clock to a moment in that night."""
    from homeassistant.util import dt as dt_util

    real = dt_util.now
    shift = {"by": timedelta()}

    def _now() -> datetime:
        return real() + shift["by"]

    monkeypatch.setattr(coordinator_module.dt_util, "now", _now)

    class Handle:
        def at(self, day: int, hour: int, minute: int = 0) -> datetime:
            """Put the clock at that day and time in August 2026, local time."""
            base = real()
            target = datetime(2026, 8, day, hour, minute, tzinfo=base.tzinfo)
            shift["by"] = target - base
            return target

    return Handle()


def installation() -> dict[str, Any]:
    """Return a cold single-zone house with two residents, set up like a real one."""
    return {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("woonkamer_ketel", LIVING)],
                indoor_sensor="sensor.woonkamer",
                heat=settings(21.0, 20.0),
            )
        ],
        "outdoor_sensor": "sensor.buiten",
        "residents": [
            {
                "resident_id": resident_id,
                "name": resident_id.title(),
                "presence_entity": person,
                "sleep_entity": charger,
                "sleep_state": "wireless",
                "sleep_window": {"start": "21:00:00", "end": "08:00:00", "weekdays": None},
                "sleep_in": {"until": "13:00:00", "weekdays": [5, 6], "holiday": True},
                "wake_deadline": {"at": "11:00:00", "weekdays": [5, 6], "holiday": True},
            }
            for resident_id, (person, charger) in PEOPLE.items()
        ],
    }


def world(*, danny: bool, nancy: bool) -> dict[str, tuple[str, dict[str, Any]]]:
    """Return a cold house with both residents home, each asleep or up.

    De aanwezigheid staat vóór de laders, zodat een slaapmelding niet ouder is dan de
    thuiskomst. Presence comes before the chargers, so no sleep reading is older than
    the homecoming.
    """
    found: dict[str, tuple[str, dict[str, Any]]] = {
        "sensor.woonkamer": ("18.0", {}),
        "sensor.buiten": ("4.0", {}),
        LIVING: ("off", {"temperature": 19.0}),
    }
    for _, (person, _charger) in PEOPLE.items():
        found[person] = ("home", {})
    for resident_id, asleep in (("danny", danny), ("nancy", nancy)):
        found[PEOPLE[resident_id][1]] = ("wireless" if asleep else "none", {})
    return found


def reason(home: LiveHome) -> str:
    """Return the living room's reason in the last decision."""
    decision = home.coordinator.data.decision_for("woonkamer")
    assert decision is not None
    return decision.reason.value


def near(found: datetime | None, expected: datetime) -> bool:
    """Return whether a recorded moment is that moment, give or take the evaluation."""
    return found is not None and abs(found - expected) < timedelta(minutes=1)


async def wakes(home: LiveHome, resident_id: str, *, asleep: bool = False) -> None:
    """Put one resident's charger in a state and decide once."""
    home.set(PEOPLE[resident_id][1], "wireless" if asleep else "none")
    await home.settle()
    await home.evaluate()


class TestTheMomentInARunningHouse:
    async def test_n7_a_restart_while_somebody_is_up_waits_for_nobody(self, clock) -> None:
        """N7: een herstart om 00:45 terwijl Danny op is: er wordt niet gewacht.

        Het huis heeft vóór de herstart niet geslapen (Nancy lag in bed, Danny was op),
        dus er is geen moment om te bewaren, en de herstart verzint er geen.

        The house did not sleep before the restart (Nancy was in bed, Danny was up), so
        there is no moment to store, and the restart invents none.
        """
        config_dir = new_config_dir()
        clock.at(14, 23, 30)
        home = await start_house(
            installation(), states=world(danny=False, nancy=True), config_dir=config_dir
        )
        try:
            assert home.coordinator._asleep_since is None
        finally:
            await stop_house(home)
        clock.at(15, 0, 45)
        again = await start_house(
            installation(), states=world(danny=False, nancy=True), config_dir=config_dir
        )
        try:
            assert again.coordinator._asleep_since is None
            assert reason(again) != "waiting_for_sleeper"
            assert again.state(LIVING) == "heat"
        finally:
            await stop_house(again)

    async def test_n8_the_moment_survives_a_restart(self, clock) -> None:
        """N8: een herstart om 03:00 terwijl beiden slapen; 's ochtends wordt gewacht.

        Het moment van 01:30 komt terug uit de opslag, niet het herstartmoment van
        03:00. Daarna nog een herstart om 07:30, terwijl Danny al op is: zonder het
        bewaarde moment zou het huis dan niet meer wachten.

        The 01:30 moment comes back from storage, not the 03:00 restart moment. Then
        another restart at 07:30, with Danny already up: without the stored moment
        the house would no longer wait then.
        """
        config_dir = new_config_dir()
        first = clock.at(15, 1, 30)
        home = await start_house(
            installation(), states=world(danny=True, nancy=True), config_dir=config_dir
        )
        try:
            assert near(home.coordinator._asleep_since, first)
            assert home.coordinator._store_payload()["asleep_since"]
        finally:
            await stop_house(home)

        clock.at(15, 3, 0)
        again = await start_house(
            installation(), states=world(danny=True, nancy=True), config_dir=config_dir
        )
        try:
            assert near(again.coordinator._asleep_since, first)
            clock.at(15, 7, 0)
            await wakes(again, "danny")
            assert reason(again) == "waiting_for_sleeper"
        finally:
            await stop_house(again)

        clock.at(15, 7, 30)
        morning = await start_house(
            installation(), states=world(danny=False, nancy=True), config_dir=config_dir
        )
        try:
            assert near(morning.coordinator._asleep_since, first)
            assert reason(morning) == "waiting_for_sleeper"
        finally:
            await stop_house(morning)

    async def test_n9_the_moment_is_recorded_when_the_last_one_turns_in(self, clock) -> None:
        """N9: Nancy om 22:00 naar bed, Danny om 00:30; 's ochtends wordt gewacht.

        Het moment ontstaat pas als Danny ook slaapt, niet toen Nancy naar bed ging;
        tot dan houdt Danny het huis aan de gang.

        The moment only comes about once Danny sleeps too, not when Nancy turned in;
        until then Danny keeps the house going.
        """
        clock.at(14, 22, 0)
        home = await start_house(installation(), states=world(danny=False, nancy=True))
        try:
            assert home.coordinator._asleep_since is None
            clock.at(15, 0, 15)
            await home.evaluate()
            assert home.coordinator._asleep_since is None
            assert reason(home) != "waiting_for_sleeper"
            bedtime = clock.at(15, 0, 30)
            await wakes(home, "danny", asleep=True)
            assert near(home.coordinator._asleep_since, bedtime)
            assert home.coordinator._store_payload()["asleep_since"]
            clock.at(15, 7, 0)
            await wakes(home, "danny")
            assert reason(home) == "waiting_for_sleeper"
        finally:
            await stop_house(home)
