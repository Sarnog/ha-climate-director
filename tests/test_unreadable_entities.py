"""Een entiteit die niet te lezen is, hoort onder Reparaties te komen.

An entity that cannot be read belongs under Repairs.

Een verkeerd getikte entiteit bestaat niet, en een sensor die wegvalt leest als
niets. In beide gevallen valt er niets om: de poort die erop leunt gaat dicht,
de zone doet niets, en van buiten is dat niet te onderscheiden van een zone die
niets hoeft te doen. Tot nu toe stond dat alleen in een attribuut van de
vastloopmelder - je moest er dus al naar zoeken om het te vinden.

Juist bij een onleesbare binnentemperatuur laat de director een draaiend
apparaat met rust, en dan houdt dat apparaat zijn circuit bezet. Dat is precies
het moment waarop een gebruiker het hoort te weten.

Er zit een wachttijd op. Een entiteit die bij een herstart een minuut wegvalt is
geen storing, en een melding die aan en uit knippert leert je hem te negeren.

A mistyped entity does not exist, and a sensor that drops out reads as nothing.
Neither breaks anything: the gate leaning on it closes, the zone does nothing,
and from the outside that is indistinguishable from a zone with nothing to do.
Until now that only lived in an attribute of the stuck sensor - so you had to be
looking for it already to find it.

With an unreadable indoor temperature in particular the director leaves a
running appliance alone, and that appliance then holds its circuit. Which is
exactly the moment a user should be told.

There is a settling time. An entity that drops out for a minute during a restart
is no fault, and a notice that blinks on and off teaches you to ignore it.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from harness_live import LiveHome, settings, source, start_house, stop_house, zone
from homeassistant.helpers import issue_registry as ir

from custom_components.climate_director.const import DOMAIN

LIVING = "climate.woonkamer"


def installation() -> dict[str, Any]:
    return {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("woonkamer_airco", LIVING, role="heat_cool")],
                indoor_sensor="sensor.woonkamer",
                heat=settings(21.0, 20.0),
            )
        ],
        "outdoor_sensor": "sensor.buiten",
    }


def world() -> dict[str, tuple[str, dict[str, Any]]]:
    return {
        "sensor.woonkamer": ("18.0", {}),
        "sensor.buiten": ("4.0", {}),
        LIVING: ("off", {}),
    }


@pytest.fixture
async def home():
    live = await start_house(installation(), states=world())
    try:
        yield live
    finally:
        await stop_house(live)


def issue_for(live: LiveHome):
    """Return the unreadable-entity notice for this installation, if it stands."""
    registry = ir.async_get(live.hass)
    return registry.async_get_issue(DOMAIN, f"unreadable_entities_{live.entry.entry_id}")


async def age(live: LiveHome, minutes: float) -> None:
    """Let the coordinator believe that much time has passed, and decide again."""
    from homeassistant.util import dt as dt_util

    from custom_components.climate_director import coordinator as module

    moved = dt_util.now() + timedelta(minutes=minutes)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(module.dt_util, "now", lambda: moved)
        await live.evaluate()


class TestASoundInstallationStaysQuiet:
    async def test_nothing_is_reported(self, home: LiveHome) -> None:
        await home.evaluate()
        assert issue_for(home) is None


class TestASensorThatDropsOut:
    async def test_a_short_outage_reports_nothing_yet(self, home: LiveHome) -> None:
        home.set("sensor.woonkamer", "unavailable")
        await home.evaluate()
        assert issue_for(home) is None

    async def test_a_lasting_outage_is_reported(self, home: LiveHome) -> None:
        home.set("sensor.woonkamer", "unavailable")
        await home.evaluate()
        await age(home, 10)
        issue = issue_for(home)
        assert issue is not None
        assert issue.translation_key == "unreadable_entities"

    async def test_the_notice_names_the_entity(self, home: LiveHome) -> None:
        home.set("sensor.woonkamer", "unavailable")
        await home.evaluate()
        await age(home, 10)
        issue = issue_for(home)
        assert issue is not None
        placeholders = issue.translation_placeholders or {}
        assert "sensor.woonkamer" in placeholders["entities"]
        assert placeholders["count"] == "1"

    async def test_unknown_counts_the_same(self, home: LiveHome) -> None:
        home.set("sensor.woonkamer", "unknown")
        await home.evaluate()
        await age(home, 10)
        assert issue_for(home) is not None

    async def test_a_reading_without_a_number_counts_too(self, home: LiveHome) -> None:
        home.set("sensor.woonkamer", "kapot")
        await home.evaluate()
        await age(home, 10)
        assert issue_for(home) is not None

    async def test_it_clears_once_the_sensor_returns(self, home: LiveHome) -> None:
        home.set("sensor.woonkamer", "unavailable")
        await home.evaluate()
        await age(home, 10)
        assert issue_for(home) is not None

        home.set("sensor.woonkamer", "18.0")
        await home.evaluate()
        assert issue_for(home) is None

    async def test_the_clock_restarts_after_a_return(self, home: LiveHome) -> None:
        """Wie terugkomt en weer wegvalt, krijgt opnieuw de volle wachttijd."""
        home.set("sensor.woonkamer", "unavailable")
        await home.evaluate()
        await age(home, 10)
        home.set("sensor.woonkamer", "18.0")
        await home.evaluate()

        home.set("sensor.woonkamer", "unavailable")
        await home.evaluate()
        assert issue_for(home) is None


class TestAnEntityThatWasNeverThere:
    async def test_a_mistyped_entity_is_reported(self) -> None:
        broken = installation()
        broken["zones"][0]["indoor_sensor"] = "sensor.tikfout"
        live = await start_house(broken, states=world(), entry_id="tikfout")
        try:
            await live.evaluate()
            await age(live, 10)
            issue = issue_for(live)
            assert issue is not None
            assert "sensor.tikfout" in (issue.translation_placeholders or {})["entities"]
        finally:
            await stop_house(live)


class TestTearingDown:
    async def test_unloading_takes_the_notice_with_it(self) -> None:
        live = await start_house(installation(), states=world(), entry_id="afbreken")
        live.set("sensor.woonkamer", "unavailable")
        await live.evaluate()
        await age(live, 10)
        assert issue_for(live) is not None

        await live.hass.config_entries.async_unload(live.entry.entry_id)
        await live.hass.async_block_till_done()
        assert issue_for(live) is None
        await stop_house(live)
