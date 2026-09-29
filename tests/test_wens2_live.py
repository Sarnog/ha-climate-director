"""De opsta-rem in een draaiende Home Assistant: wie alleen thuis opstaat wordt geremd.

The rise brake inside a running Home Assistant: whoever gets up alone at home is braked.

Wens 2 van `na-T13-wensen.md` zegt het met zoveel woorden: *Opstaan zet het huis pas
aan vanaf* geldt ook als de bewoner met de rem de enige is die thuis opstaat, en dan
blijft het huis uit. In de engine hing dat aan `night.house_asleep_since`: die gaf `None`
zodra er niemand thuis meer sliep, en dat is precies de ronde waarin die bewoner opstaat.
Het moment was dan weg, `night.rise_braked` eist het, en de rem remde niets meer.

Wish 2 of `na-T13-wensen.md` says it in so many words: *Getting up only starts the house
from* also applies when the resident with the brake is the only one getting up at home,
and then the house stays off. In the engine that hung on `night.house_asleep_since`: it
returned `None` as soon as nobody at home was asleep any more, which is exactly the round
in which that resident gets up. The moment was gone then, `night.rise_braked` demands it,
and the brake no longer braked anything.

De engine-kant staat in `tests/test_early_riser.py` (de twaalf gevallen, nacht ronde na
ronde) en in `tests/test_the_night.py` (het moment zelf); hier gaat het door de
koppelingslaag heen, met een echte nacht van maandag 23:30 op dinsdag, en met een
herstart om 06:00 waarna het bewaarde moment terugkomt. De klok van de integratie wordt op
die nacht gezet; de tijdstempels van de entiteiten blijven echt.

The engine side stands in `tests/test_early_riser.py` (the twelve cases, night round by
round) and in `tests/test_the_night.py` (the moment itself); here it goes through the
binding layer, with a real night from Monday 23:30 into Tuesday, and with a restart at
06:00 after which the stored moment comes back. The integration's clock is set to that
night; the entities' timestamps stay real.

Eén reeks gaat over hetzelfde huis zonder slaapvenster: daar telt de slaapsensor de klok
rond, remt de rem wie op de remdagen vóór de remtijd op is ook als het moment van het
huis onbekend is, en is er dus geen moment dat een herstart kan overleven. De aanvaarde
prijs staat er met de andere kant naast: om half één nog op terwijl het huis uit staat
remt zonder venster wel, met venster niet.

One series goes over the same house without a sleep window: there the sleep sensor counts
around the clock, the brake brakes whoever is up before the brake time on the brake's days
even when the house's moment is unknown, and so there is no moment a restart could carry
over. The accepted price stands there with the other side beside it: still up at half past
midnight with the house off is braked without a window, not with one.
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


def brake_for(resident_id: str, *, danny: bool, nancy: bool) -> dict[str, Any] | None:
    """Return the rise brake of this resident, or nothing when he has none."""
    if (resident_id == "danny" and danny) or (resident_id == "nancy" and nancy):
        return {"at": "07:00:00", "weekdays": [0, 1, 2, 3, 4]}
    return None


def installation(
    *,
    danny_brake: bool = True,
    nancy_brake: bool = False,
    sleep_window: bool = True,
) -> dict[str, Any]:
    """Return a cold single-zone house of two residents, with the brake as asked.

    Zonder slaapvenster (`sleep_window=False`) telt de slaapsensor de klok rond en is er
    geen nacht om het moment van het huis aan af te lezen.

    Without a sleep window (`sleep_window=False`) the sleep sensor counts around the clock
    and there is no night to read the house's moment against.
    """
    night = {"start": "21:00:00", "end": "08:00:00", "weekdays": None} if sleep_window else None
    sleep_in = {"until": "13:00:00", "weekdays": [5, 6], "holiday": True} if sleep_window else None
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
                "sleep_window": night,
                "sleep_in": sleep_in,
                "wake_deadline": {"at": "11:00:00", "weekdays": [5, 6], "holiday": True},
                "rise_brake": brake_for(resident_id, danny=danny_brake, nancy=nancy_brake),
            }
            for resident_id, (person, charger) in PEOPLE.items()
        ],
    }


def world(*, danny: str, nancy: str) -> dict[str, tuple[str, dict[str, Any]]]:
    """Return a cold house with each resident in bed, up or away.

    `danny` and `nancy` are `bed`, `up` or `away`. De aanwezigheid staat vóór de
    laders, zodat een slaapmelding niet ouder is dan de thuiskomst; wie weg is
    heeft geen lader en geen aanwezigheid.

    The presence comes before the chargers, so no sleep reading is older than the
    homecoming; whoever is away has no charger and no presence.
    """
    found: dict[str, tuple[str, dict[str, Any]]] = {
        "sensor.woonkamer": ("18.0", {}),
        "sensor.buiten": ("4.0", {}),
        LIVING: ("off", {"temperature": 19.0}),
    }
    for resident_id, how in (("danny", danny), ("nancy", nancy)):
        person, charger = PEOPLE[resident_id]
        found[person] = ("not_home" if how == "away" else "home", {})
        found[charger] = ("wireless" if how == "bed" else "none", {})
    return found


def reason(home: LiveHome) -> str:
    """Return the living room's reason in the last decision."""
    decision = home.coordinator.data.decision_for("woonkamer")
    assert decision is not None
    return decision.reason.value


def near(found: datetime | None, expected: datetime) -> bool:
    """Return whether a recorded moment is that moment, give or take the evaluation."""
    return found is not None and abs(found - expected) < timedelta(minutes=1)


async def wakes(home: LiveHome, resident_id: str) -> None:
    """Put one resident's charger to `none` - he gets up - and decide once."""
    home.set(PEOPLE[resident_id][1], "none")
    await home.settle()
    await home.evaluate()


class TestTheRiseBrakeInARunningHouse:
    """Wens 2, de twaalf gevallen waarvan hier de vier die door de koppelingslaag gingen.

    Wish 2, the twelve cases, of which the four that went through the binding layer.
    """

    async def test_wens2_1_live_danny_up_early_nancy_asleep(self, clock) -> None:
        """1 live: di 05:50, Danny op, Nancy slaapt: de rem houdt het huis tegen."""
        clock.at(10, 23, 30)
        home = await start_house(installation(), states=world(danny="bed", nancy="bed"))
        try:
            clock.at(11, 5, 50)
            await wakes(home, "danny")
            assert reason(home) == "early_riser"
            assert home.state(LIVING) == "off"
            assert home.coordinator._asleep_since is not None
        finally:
            await stop_house(home)

    async def test_wens2_2_live_danny_alone_gets_up_early(self, clock) -> None:
        """2 live: di 05:50, Danny alleen thuis, stond op na een nacht slapen: `early_riser`.

        Dit is het geval dat niet remde: het moment waarop het huis ging slapen viel weg
        in dezelfde ronde waarin Danny opstond, want er sliep niemand meer thuis.

        This is the case that did not brake: the moment the house went to sleep fell away
        in the same round in which Danny got up, since nobody at home was asleep any more.
        """
        bedtime = clock.at(10, 23, 30)
        home = await start_house(installation(), states=world(danny="bed", nancy="away"))
        try:
            assert near(home.coordinator._asleep_since, bedtime)
            clock.at(11, 5, 50)
            await wakes(home, "danny")
            assert near(home.coordinator._asleep_since, bedtime)
            assert reason(home) == "early_riser"
            assert home.state(LIVING) == "off"
        finally:
            await stop_house(home)

    async def test_wens2_4_live_after_seven_the_house_starts(self, clock) -> None:
        """4 live: di 07:05, dezelfde nacht en dezelfde lege kamer, maar de rem is over."""
        clock.at(10, 23, 30)
        home = await start_house(installation(), states=world(danny="bed", nancy="away"))
        try:
            clock.at(11, 7, 5)
            await wakes(home, "danny")
            assert reason(home) != "early_riser"
            assert home.state(LIVING) == "heat"
        finally:
            await stop_house(home)

    async def test_wens2_12_live_nancy_has_the_brake_and_danny_is_away(self, clock) -> None:
        """12 live: de rollen omgedraaid - Nancy heeft de rem, Danny is weg, Nancy staat op."""
        clock.at(10, 23, 30)
        home = await start_house(
            installation(danny_brake=False, nancy_brake=True),
            states=world(danny="away", nancy="bed"),
        )
        try:
            clock.at(11, 5, 50)
            await wakes(home, "nancy")
            assert reason(home) == "early_riser"
            assert home.state(LIVING) == "off"
            assert home.coordinator._asleep_since is not None
        finally:
            await stop_house(home)

    async def test_the_moment_comes_back_from_a_restart_while_the_riser_is_up(self, clock) -> None:
        """Een herstart om 06:00, terwijl de bewoner met de rem al op is: de rem blijft.

        Zonder het bewaarde moment zou het huis na die herstart gewoon starten: er is dan
        niets meer om aan af te lezen dat deze bewoner na een nacht slapen opstond.

        A restart at 06:00, while the resident with the brake is already up: the brake
        stays. Without the stored moment the house would simply start after that restart:
        there is nothing left to read that this resident got up after a night's sleep.
        """
        config_dir = new_config_dir()
        bedtime = clock.at(10, 23, 30)
        home = await start_house(
            installation(), states=world(danny="bed", nancy="away"), config_dir=config_dir
        )
        try:
            clock.at(11, 5, 50)
            await wakes(home, "danny")
            assert reason(home) == "early_riser"
            assert home.coordinator._store_payload()["asleep_since"]
        finally:
            await stop_house(home)
        clock.at(11, 6, 0)
        again = await start_house(
            installation(), states=world(danny="up", nancy="away"), config_dir=config_dir
        )
        try:
            assert near(again.coordinator._asleep_since, bedtime)
            assert reason(again) == "early_riser"
            assert again.state(LIVING) == "off"
        finally:
            await stop_house(again)


class TestWithoutASleepWindow:
    """Wens 2 in een huis zonder slaapvenster: de slaapsensor telt de klok rond.

    Wish 2 in a house without a sleep window: the sleep sensor counts around the clock.
    """

    async def test_wens2_2_live_without_a_sleep_window_danny_alone_gets_up_early(
        self, clock
    ) -> None:
        """2 live: di 05:50, geen venster, Danny op en de enige thuis: `early_riser`, huis uit.

        Het moment van het huis is in deze ronde al weg - er slaapt niemand thuis - en toch
        remt de rem: zonder venster is er geen nacht om aan af te lezen.

        The house's moment is already gone in this round - nobody at home is asleep - and
        the brake still brakes: without a window there is no night to read.
        """
        bedtime = clock.at(10, 23, 30)
        home = await start_house(
            installation(sleep_window=False), states=world(danny="bed", nancy="away")
        )
        try:
            assert near(home.coordinator._asleep_since, bedtime)
            clock.at(11, 5, 50)
            await wakes(home, "danny")
            assert home.coordinator._asleep_since is None
            assert reason(home) == "early_riser"
            assert home.state(LIVING) == "off"
        finally:
            await stop_house(home)

    async def test_wens2_4_live_without_a_sleep_window_the_house_starts_at_seven(
        self, clock
    ) -> None:
        """4 live: di 07:05, geen venster, dezelfde lege kamer: de rem is over, huis aan."""
        clock.at(10, 23, 30)
        home = await start_house(
            installation(sleep_window=False), states=world(danny="bed", nancy="away")
        )
        try:
            clock.at(11, 7, 5)
            await wakes(home, "danny")
            assert reason(home) != "early_riser"
            assert home.state(LIVING) == "heat"
        finally:
            await stop_house(home)

    async def test_the_brake_stays_over_a_restart_without_a_sleep_window(self, clock) -> None:
        """Een herstart om 06:00 terwijl de bewoner met de rem al op is: de rem blijft.

        Zonder slaapvenster valt er geen moment te bewaren - dat is juist de prijs - en
        toch remt de rem na de herstart, want zonder venster eist ze geen nacht.

        A restart at 06:00 while the resident with the brake is already up: the brake
        stays. Without a sleep window there is no moment to keep - that is the price - and
        the brake still brakes after the restart, since without a window it demands no
        night.
        """
        config_dir = new_config_dir()
        clock.at(10, 23, 30)
        home = await start_house(
            installation(sleep_window=False),
            states=world(danny="bed", nancy="away"),
            config_dir=config_dir,
        )
        try:
            clock.at(11, 5, 50)
            await wakes(home, "danny")
            assert reason(home) == "early_riser"
            assert home.coordinator._store_payload()["asleep_since"] is None
        finally:
            await stop_house(home)
        clock.at(11, 6, 0)
        again = await start_house(
            installation(sleep_window=False),
            states=world(danny="up", nancy="away"),
            config_dir=config_dir,
        )
        try:
            assert reason(again) == "early_riser"
            assert again.state(LIVING) == "off"
        finally:
            await stop_house(again)

    async def test_the_accepted_price_whoever_is_up_after_midnight_is_braked(self, clock) -> None:
        """De prijs: zonder venster om 00:30 nog op terwijl het huis uit staat: `early_riser`."""
        clock.at(11, 0, 30)
        home = await start_house(
            installation(sleep_window=False), states=world(danny="up", nancy="away")
        )
        try:
            assert reason(home) == "early_riser"
            assert home.state(LIVING) == "off"
        finally:
            await stop_house(home)

    async def test_with_a_sleep_window_whoever_is_up_late_is_not_braked(self, clock) -> None:
        """De andere kant: mét venster is wie 's nachts nog op is geen opstaander.

        Het huis heeft deze nacht niet geslapen, dus valt er geen nacht te lezen en remt de
        rem niet: het huis start gewoon.

        The other side: with a window whoever is still up at night is no riser. The house
        has not slept this night, so there is no night to read and the brake does not
        brake: the house simply starts.
        """
        clock.at(11, 0, 30)
        home = await start_house(installation(), states=world(danny="up", nancy="away"))
        try:
            assert reason(home) != "early_riser"
            assert home.state(LIVING) == "heat"
        finally:
            await stop_house(home)
