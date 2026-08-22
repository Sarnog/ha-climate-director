"""Een commando dat nooit aankomt hoort zichzelf te melden.

A command that never arrives should report itself.

`diff.changes()` biedt hetzelfde verschil elke ronde opnieuw aan zolang het
apparaat niet meebeweegt. Een apparaat dat de aanroep aanneemt maar niets doet -
of zichzelf meteen terugzet - levert daarmee met de vangnetklok van zestig
seconden ruim veertienhonderd mislukte aanroepen per dag op, zonder dat er ook
maar iets van te zien is. Na een aantal gelijke rondes is dat geen toeval meer.

`diff.changes()` offers the same difference again every round for as long as the
appliance does not move with it. An appliance that accepts the call but does
nothing - or puts itself straight back - therefore racks up well over fourteen
hundred failed calls a day on the sixty-second safety-net clock, without a trace
of it showing anywhere. After a number of identical rounds that is no longer
chance.

In schaduwmodus telt dit nooit: daar wordt niets uitgevoerd, dus de
verschillenlijst is per definitie permanent gevuld en zou de melding bij iedereen
die netjes met schaduw begint op dag één afgaan.

In shadow mode this never counts: nothing is executed there, so the difference
list is by definition permanently filled and the notice would go off on day one
for everyone who starts out properly in shadow.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from harness_live import LiveHome, settings, source, start_house, stop_house, zone
from homeassistant.core import ServiceCall
from homeassistant.helpers import issue_registry as ir

from custom_components.climate_director.const import DOMAIN

LIVING = "climate.woonkamer"


def installation() -> dict[str, Any]:
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
    }


def world() -> dict[str, tuple[str, dict[str, Any]]]:
    """Return a house that is warm enough, so nothing is asked of the boiler yet.

    Het opzetten van de installatie beslist meteen een keer. Begint het huis
    koud, dan gaat de ketel op dat moment netjes aan en valt er daarna niets
    meer te melden; begint het warm, dan kan het apparaat eerst doof worden
    gemaakt en pas daarna iets gevraagd krijgen.

    Setting the installation up decides once straight away. Start the house
    cold and the boiler duly comes on at that moment, leaving nothing to report
    afterwards; start it warm and the appliance can be made deaf first and only
    then be asked for something.
    """
    return {
        "sensor.woonkamer": ("22.0", {}),
        "sensor.buiten": ("4.0", {}),
        LIVING: ("off", {"hvac_modes": ["heat", "off"]}),
    }


def go_deaf(live: LiveHome) -> None:
    """Let the appliance accept every call and carry out none of them.

    Het harnas schrijft de toestand normaal terug, zoals een apparaat dat doet
    dat luistert. Dit vervangt die twee acties door aannemen-en-vergeten: precies
    het apparaat waar deze melding over gaat. Daarna koelt het huis af, zodat er
    ook echt iets gevraagd wordt.

    The harness normally writes the state back, the way an appliance that
    listens does. This replaces those two actions with accept-and-forget:
    exactly the appliance this notice is about. The house then cools down, so
    that something really is asked of it.
    """

    async def _swallow(call: ServiceCall) -> None:
        live.calls.append((call.service, dict(call.data)))

    live.hass.services.async_register("climate", "set_hvac_mode", _swallow)
    live.hass.services.async_register("climate", "set_temperature", _swallow)
    live.set("sensor.woonkamer", "18.0")


def issue_for(live: LiveHome):
    """Return the command-not-taking notice for this installation, if it stands."""
    registry = ir.async_get(live.hass)
    return registry.async_get_issue(DOMAIN, f"command_not_taking_{live.entry.entry_id}")


async def rounds(live: LiveHome, count: int, *, minutes: float = 1.0) -> None:
    """Decide `count` more times, each one `minutes` later than the last.

    De vangnetklok beslist elke minuut opnieuw, ook als er niets beweegt. Dit
    bootst precies dat na: dezelfde wereld, een minuut verder.

    The safety-net clock decides again every minute, even when nothing moves.
    This mimics exactly that: the same world, a minute further on.
    """
    from homeassistant.util import dt as dt_util

    from custom_components.climate_director import coordinator as module

    start = dt_util.now()
    for step in range(1, count + 1):
        moved = start + timedelta(minutes=minutes * step)
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(module.dt_util, "now", lambda moved=moved: moved)
            await live.evaluate()


@pytest.fixture
async def home():
    live = await start_house(installation(), states=world())
    go_deaf(live)
    try:
        yield live
    finally:
        await stop_house(live)


class TestAnApplianceThatNeverTakesItsCommand:
    async def test_the_command_really_is_offered_again_every_round(self, home: LiveHome) -> None:
        home.clear_calls()
        await rounds(home, 3)
        assert len(home.climate_calls()) == 3

    async def test_a_few_rounds_report_nothing_yet(self, home: LiveHome) -> None:
        await rounds(home, 3)
        assert issue_for(home) is None

    async def test_ten_rounds_of_the_same_difference_are_reported(self, home: LiveHome) -> None:
        await rounds(home, 12)
        issue = issue_for(home)
        assert issue is not None
        assert issue.translation_key == "command_not_taking"

    async def test_the_notice_names_the_appliance_and_the_wanted_mode(self, home: LiveHome) -> None:
        await rounds(home, 12)
        issue = issue_for(home)
        assert issue is not None
        placeholders = issue.translation_placeholders or {}
        assert LIVING in placeholders["entities"]
        assert "heat" in placeholders["entities"]
        assert placeholders["count"] == "1"

    async def test_it_clears_once_the_appliance_takes_the_command(self, home: LiveHome) -> None:
        await rounds(home, 12)
        assert issue_for(home) is not None

        home.set(LIVING, "heat", hvac_modes=["heat", "off"], temperature=21.0)
        await rounds(home, 1)
        assert issue_for(home) is None

    async def test_a_burst_of_rounds_within_a_minute_is_not_enough(self, home: LiveHome) -> None:
        # De ontdubbelaar wacht maar een seconde, dus twintig toestandswijzigingen
        # achter elkaar zijn zo voorbij. Dat is geen dove ketel, dat is druk.
        #
        # The debouncer waits only a second, so twenty state changes in a row are
        # over in no time. That is not a deaf boiler, that is a busy house.
        await rounds(home, 20, minutes=0.05)
        assert issue_for(home) is None


class TestShadowMode:
    async def test_shadow_never_reports_it(self) -> None:
        live = await start_house(installation(), states=world(), shadow=True, entry_id="schaduw")
        go_deaf(live)
        try:
            await rounds(live, 100)
            assert issue_for(live) is None
        finally:
            await stop_house(live)


class TestTearingDown:
    async def test_unloading_takes_the_notice_with_it(self) -> None:
        live = await start_house(installation(), states=world(), entry_id="afbreken")
        go_deaf(live)
        await rounds(live, 12)
        assert issue_for(live) is not None

        await live.hass.config_entries.async_unload(live.entry.entry_id)
        await live.hass.async_block_till_done()
        assert issue_for(live) is None
        await stop_house(live)
