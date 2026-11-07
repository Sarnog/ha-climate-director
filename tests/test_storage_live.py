"""Een beschadigd opslagbestand mag het opstarten nooit verhinderen.

A broken storage file must never stop the startup."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from harness_live import (
    new_config_dir,
    start_house,
    stop_house,
)
from homeassistant.util import dt as dt_util
from live_helpers import (
    IMPOSSIBLE,
    IMPOSSIBLE_DATE,
    LIVING,
    NAIVE,
    cold_one_room,
    house_with_two_residents,
    simple_installation,
    two_residents,
    write_store,
)

pytest_plugins = ["live_fixtures"]
pytestmark = pytest.mark.usefixtures("appliance")


class TestAStartupWithBrokenStorage:
    """Het bewaarde werk van een herstart mag nooit het opstarten verhinderen.

    The saved work from a restart must never stop the startup.
    """

    async def test_a_wrong_shaped_stored_state_is_skipped_not_fatal(self) -> None:
        """Velden met een onleesbare vorm worden overgeslagen, de rest draait.

        Fields with an unreadable shape are skipped, the rest just runs.
        """
        config_dir = new_config_dir()
        path = write_store(
            config_dir,
            "vorm",
            {
                "until": ["geen", "dict"],
                "bypass": 42,
                "handed_back": ["ook", "geen", "dict"],
            },
        )
        home = await start_house(
            simple_installation(), states=cold_one_room(), config_dir=config_dir, entry_id="vorm"
        )
        try:
            assert home.state(LIVING) == "heat", "de director hoort gewoon te beslissen"
            assert home.coordinator._clock_reeval_unsub is not None, "de klok hoort te staan"
            assert path.exists(), "een leesbaar bestand met vreemde velden hoort te blijven staan"
        finally:
            await stop_house(home)

    async def test_an_unreadable_stored_state_is_quarantined_and_director_decides(self) -> None:
        """Een bestand dat nergens op lijkt gaat opzij, met melding, en de director draait.

        A file shaped like nothing goes aside, with a notice, and the director runs.
        """
        config_dir = new_config_dir()
        path = write_store(config_dir, "kapot", [1, 2, 3])
        home = await start_house(
            simple_installation(), states=cold_one_room(), config_dir=config_dir, entry_id="kapot"
        )
        try:
            assert home.state(LIVING) == "heat", "de director hoort met een lege staat te beginnen"
            assert home.coordinator._clock_reeval_unsub is not None, "de klok hoort te staan"
            assert not path.exists(), "het onleesbare bestand hoort opzij gezet te zijn"
            assert list(path.parent.glob(path.name + ".corrupt*")), (
                "er hoort een .corrupt-bestand te staan"
            )

            from homeassistant.helpers import issue_registry as ir

            registry = ir.async_get(home.hass)
            assert ("climate_director", "corrupt_storage_kapot") in registry.issues
        finally:
            await stop_house(home)

    async def test_an_impossible_precondition_time_counts_as_unknown(self) -> None:
        """Een onmogelijke tijd bij `until` laat de eerste beslissing gewoon doorgaan.

        `dt_util.parse_datetime` gooit een `ValueError` bij iets dat op een datum lijkt maar
        er geen is. Zo'n waarde hoort als afwezig te tellen, net als onzin en een verkeerde
        vorm - anders valt de eerste beslissing om en blijft de kamer koud tot de volgende
        herstart.

        An impossible time at `until` lets the first decision simply go through.
        """
        config_dir = new_config_dir()
        write_store(config_dir, "tot", {"until": {"woonkamer": IMPOSSIBLE}})
        home = await start_house(
            house_with_two_residents(),
            states=two_residents(),
            config_dir=config_dir,
            entry_id="tot",
        )
        try:
            assert home.state(LIVING) == "heat", "de eerste beslissing hoort te draaien"
            assert home.coordinator._precondition == {}, "het onmogelijke tijdstip telt als afwezig"
        finally:
            await stop_house(home)

    async def test_an_impossible_homecoming_counts_as_unknown(self) -> None:
        """Een onmogelijke tijd bij `home_since` telt als een onbekende thuiskomst.

        De bewoner is weg, dus er valt ook niets terug te zetten; waar het hier om gaat is
        dat het lezen van dat tijdstip de rest van het bestand niet tegenhoudt.

        An impossible time at `home_since` counts as an unknown homecoming.
        """
        config_dir = new_config_dir()
        write_store(config_dir, "thuis", {"home_since": {"nancy": IMPOSSIBLE}})
        home = await start_house(
            house_with_two_residents(),
            states=two_residents(nancy="away"),
            config_dir=config_dir,
            entry_id="thuis",
        )
        try:
            assert home.state(LIVING) == "heat", "de eerste beslissing hoort te draaien"
            assert "nancy" not in home.coordinator._home_since
        finally:
            await stop_house(home)

    async def test_an_impossible_sleep_moment_counts_as_unknown(self) -> None:
        """Een onmogelijk slaapmoment wacht op niemand; een leesbaar moment wel.

        De eerste start is de tegenproef: met een leesbaar moment in de opslag houdt de
        bewoner in bed het huis tegen (`waiting_for_sleeper`). Met het onmogelijke moment
        telt dat moment als afwezig, dus wacht het huis op niemand en start de kamer.

        An impossible sleep moment waits for nobody; a readable one does.
        """
        config_dir = new_config_dir()
        readable = (dt_util.now() - timedelta(hours=1)).isoformat()
        home_since = (dt_util.now() - timedelta(hours=2)).isoformat()
        write_store(
            config_dir,
            "nacht",
            {
                "asleep_since": readable,
                "home_since": {"danny": home_since, "nancy": home_since},
            },
        )
        home = await start_house(
            house_with_two_residents(),
            states=two_residents(danny="bed"),
            config_dir=config_dir,
            entry_id="nacht",
        )
        try:
            decision = home.coordinator.data.decision_for("woonkamer")
            assert decision is not None
            assert decision.reason.value == "waiting_for_sleeper"
            assert home.state(LIVING) == "off"
        finally:
            await stop_house(home)
        write_store(config_dir, "nacht", {"asleep_since": IMPOSSIBLE})
        again = await start_house(
            house_with_two_residents(),
            states=two_residents(danny="bed"),
            config_dir=config_dir,
            entry_id="nacht",
        )
        try:
            assert again.coordinator._asleep_since is None
            decision = again.coordinator.data.decision_for("woonkamer")
            assert decision is not None
            assert decision.reason.value != "waiting_for_sleeper"
            assert again.state(LIVING) == "heat"
        finally:
            await stop_house(again)

    async def test_a_naive_precondition_time_counts_as_unknown(self) -> None:
        """Een tijd zonder tijdzone bij `until` telt als afwezig.

        De waarde leest wel, maar vergelijken met de klok van de integratie kan niet. De
        eerste beslissing hoort gewoon te draaien en het verzoek hoort niet terug te komen.

        A time without a time zone at `until` counts as absent.
        """
        config_dir = new_config_dir()
        write_store(config_dir, "tot", {"until": {"woonkamer": NAIVE}})
        home = await start_house(
            house_with_two_residents(),
            states=two_residents(),
            config_dir=config_dir,
            entry_id="tot",
        )
        try:
            assert home.coordinator.data is not None, "de eerste beslissing hoort te draaien"
            assert home.coordinator._precondition == {}, "de naïeve tijd telt als afwezig"
        finally:
            await stop_house(home)

    async def test_a_naive_homecoming_counts_as_unknown(self) -> None:
        """Een tijd zonder tijdzone bij `home_since` telt als een onbekende thuiskomst.

        De bewoner is thuis, dus zonder opvang zou dit moment blijven staan - en dan valt
        elke vergelijking met de klok erop om. De eerste beslissing hoort gewoon te draaien
        en er hoort geen tijd zonder tijdzone in de thuiskomstmomenten te staan.

        A time without a time zone at `home_since` counts as an unknown homecoming.
        """
        config_dir = new_config_dir()
        write_store(config_dir, "thuis", {"home_since": {"nancy": NAIVE}})
        home = await start_house(
            house_with_two_residents(),
            states=two_residents(),
            config_dir=config_dir,
            entry_id="thuis",
        )
        try:
            assert home.coordinator.data is not None, "de eerste beslissing hoort te draaien"
            assert all(
                moment.tzinfo is not None for moment in home.coordinator._home_since.values()
            ), "een tijd zonder tijdzone hoort hier niet te staan"
        finally:
            await stop_house(home)

    async def test_a_naive_sleep_moment_counts_as_unknown_and_the_next_round_decides(self) -> None:
        """Een naïef slaapmoment wacht op niemand, en ook de ronde daarna wordt er beslist.

        Van de opgeslagen tijdstippen is dit de enige die elke ronde opnieuw gelezen wordt:
        blijft hij staan, dan valt niet alleen de eerste beslissing om maar elke volgende
        ook. Daarom loopt deze toets een tweede ronde.

        A naive sleep moment waits for nobody, and the round after it decides too.
        """
        config_dir = new_config_dir()
        write_store(config_dir, "nacht", {"asleep_since": NAIVE})
        home = await start_house(
            house_with_two_residents(),
            states=two_residents(danny="bed"),
            config_dir=config_dir,
            entry_id="nacht",
        )
        try:
            assert home.coordinator._asleep_since is None
            assert home.state(LIVING) == "heat", "de eerste beslissing hoort te draaien"
            await home.evaluate()
            decision = home.coordinator.data.decision_for("woonkamer")
            assert decision is not None, "de tweede ronde hoort ook te beslissen"
            assert decision.reason.value != "waiting_for_sleeper"
        finally:
            await stop_house(home)

    @pytest.mark.parametrize("value", [NAIVE, IMPOSSIBLE])
    @pytest.mark.parametrize("key", ["override_until", "override_started"])
    async def test_a_stored_override_time_counts_as_unknown(self, key: str, value: str) -> None:
        """Een looptijd of starttijd van een override die niet te lezen is telt als afwezig.

        Een onmogelijke waarde gooit een `ValueError` en een tijd zonder tijdzone een
        `TypeError`; allebei horen ze de eerste beslissing niet te laten vallen.

        An override's duration or start time that cannot be read counts as absent.
        """
        config_dir = new_config_dir()
        stored: dict[str, Any] = {key: {"woonkamer": value}}
        if key == "override_started":
            # De starttijd hoort alleen bij een looptijd die er is; die zetten we er dus
            # leesbaar bij, zodat deze toets echt de starttijd meet.
            #
            # The start time only belongs to a duration that is there; it is therefore set
            # readably alongside, so this test really measures the start time.
            stored["override_until"] = {
                "woonkamer": (dt_util.now() + timedelta(hours=2)).isoformat()
            }
        write_store(config_dir, "override", stored)
        home = await start_house(
            simple_installation(),
            states=cold_one_room(),
            config_dir=config_dir,
            entry_id="override",
        )
        try:
            assert home.coordinator.data is not None, "de eerste beslissing hoort te draaien"
            if key == "override_until":
                assert "woonkamer" not in home.coordinator.zone_overrides
            else:
                assert "woonkamer" in home.coordinator.zone_override_until, "de looptijd las wel"
                assert "woonkamer" not in home.coordinator.zone_override_started
        finally:
            await stop_house(home)

    @pytest.mark.parametrize("value", [NAIVE, IMPOSSIBLE_DATE])
    async def test_a_stored_handed_back_day_counts_as_unknown(self, value: str) -> None:
        """Een handmatige uitzetting van een dag die niet te lezen is komt niet terug.

        `handed_back` leest met de datumvariant van dezelfde lezer: een tijd zonder tijdzone,
        een onmogelijke dag en onzin vallen er allemaal buiten, en de eerste beslissing
        draait gewoon.

        A hand-back on a day that cannot be read does not come back.
        """
        config_dir = new_config_dir()
        write_store(config_dir, "terug", {"handed_back": {"woonkamer": value}})
        home = await start_house(
            simple_installation(), states=cold_one_room(), config_dir=config_dir, entry_id="terug"
        )
        try:
            assert home.coordinator.data is not None, "de eerste beslissing hoort te draaien"
            assert home.coordinator._handed_back == {}
        finally:
            await stop_house(home)

    async def test_a_readable_handed_back_day_does_come_back(self) -> None:
        """De tegenproef: een uitzetting van vandaag komt wel terug.

        Zonder deze toets zou de toets hierboven ook groen zijn als er nooit iets hersteld
        werd.

        The counter-proof: a hand-back from today does come back.
        """
        config_dir = new_config_dir()
        today = dt_util.now().date()
        write_store(config_dir, "vandaag", {"handed_back": {"woonkamer": today.isoformat()}})
        home = await start_house(
            simple_installation(), states=cold_one_room(), config_dir=config_dir, entry_id="vandaag"
        )
        try:
            assert home.coordinator._handed_back.get("woonkamer") == today
        finally:
            await stop_house(home)
