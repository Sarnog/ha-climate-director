"""Wat de sensoren en het beslisevent naar buiten vertellen.

What the sensors and the decision event tell the outside world.

Dekking: de samenvatting, de commando- en bronzensoren, het beslisevent en de
teksten die uit `strings.json` en de zes vertalingen komen, telkens in een echte
Home Assistant. Niet gedekt: de opmaak van het dashboard en de vraag of een
vertaling mooi leest.

Coverage: the summary, the command and source sensors, the decision event and
the texts that come from `strings.json` and the six translations, each inside a
real Home Assistant. Not covered: the dashboard's layout and whether a
translation reads well.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from harness_live import (
    LiveHome,
    start_house,
    stop_house,
)
from live_helpers import (
    ATTIC,
    LIVING,
    SPARE,
    cold_two_rooms,
    two_zone_installation,
)

pytest_plugins = ["live_fixtures"]
pytestmark = pytest.mark.usefixtures("appliance")


class TestTheReporting:
    """De uitkomst zoals een gebruiker hem op zijn dashboard ziet.

    The outcome as a user sees it on their dashboard.
    """

    async def test_the_summary_counts_the_served_rooms(self, home: LiveHome) -> None:
        assert home.value("last_decision") == "2/2"
        home.set("sensor.zolder", "25.0")
        await home.evaluate()
        assert home.value("last_decision") == "1/2"

    async def test_the_command_sensor_names_the_mode(self, home: LiveHome) -> None:
        assert home.value(f"command_{LIVING}") == "heat"
        assert home.values(f"command_{LIVING}")["temperature"] == 21.0
        assert home.values(f"command_{LIVING}")["reason"] == "regulating"

    async def test_an_unreachable_appliance_says_so(self, home: LiveHome) -> None:
        home.set(ATTIC, "unavailable")
        await home.evaluate()
        assert home.value(f"command_{ATTIC}") == "unreachable"
        assert home.values(f"command_{ATTIC}")["reason"] == "source_unreachable"

    async def test_the_zone_sensor_names_the_source(self, home: LiveHome) -> None:
        assert home.value("zone_woonkamer_source") == "woonkamer_airco"

    async def test_the_blocked_sensor_names_the_gate_that_held_the_zone_back(
        self, home: LiveHome
    ) -> None:
        """De melder gaat nu ook aan bij een dichte poort, en noemt hem.

        Een zone met een dichte poort vraagt niets en kreeg dus niets te
        weinig; de melder keek alleen daarnaar en bleef uit terwijl de kamer
        wél iets nodig had. Nu telt ook "poort dicht terwijl de kamer buiten
        zijn dode band ligt". De attributen noemen de poort en wat de kamer
        gewild zou hebben.

        The sensor now also comes on for a shut gate, and names it. A zone
        with a shut gate asks for nothing and was therefore short-changed
        nothing; the sensor only looked at that and stayed off while the room
        did need something. Now "gate shut while the room sits outside its
        dead band" counts too. The attributes name the gate and what the room
        would have wanted.
        """
        assert home.value("zone_woonkamer_blocked") == "off"
        assert home.values("zone_woonkamer_blocked")["closed_gates"] == []
        home.set("binary_sensor.achterdeur", "on")
        await home.evaluate()
        assert home.value("zone_woonkamer_blocked") == "on"
        attributes = home.values("zone_woonkamer_blocked")
        assert attributes["reason"] == "opening_open"
        assert attributes["closed_gates"] == ["opening_open"]
        assert attributes["would_want"] == "heat"

    async def test_a_shut_gate_in_a_comfortable_room_does_not_light_the_sensor(
        self, home: LiveHome
    ) -> None:
        """Een open raam in een kamer die al op temperatuur is, blokkeert niets."""
        home.set("binary_sensor.achterdeur", "on")
        home.set("sensor.woonkamer", "22.0")
        await home.evaluate()
        assert home.value("zone_woonkamer_blocked") == "off"

    async def test_an_override_is_not_a_blockage(self, home: LiveHome) -> None:
        """Wie een zone overdraagt wil geen 'geblokkeerd'-melder zien branden."""
        home.set("binary_sensor.achterdeur", "on")
        await home.evaluate()
        assert home.value("zone_woonkamer_blocked") == "on"
        home.coordinator.zone_overrides["woonkamer"] = True
        await home.evaluate()
        assert home.value("zone_woonkamer_blocked") == "off"

    async def test_the_stand_in_sensor_lights_up_when_it_takes_over(self, home: LiveHome) -> None:
        assert home.value("zone_woonkamer_fallback") == "off"
        home.set(LIVING, "unavailable")
        await home.evaluate()
        assert home.state(SPARE) == "heat"
        assert home.value("zone_woonkamer_fallback") == "on"

    async def test_the_mismatch_sensor_counts_what_did_not_land(self, home: LiveHome) -> None:
        # De eerste ronde wilde twee apparaten zetten; die zijn daarna gezet,
        # dus de ronde erna valt er niets meer te verschillen.
        #
        # The first round wanted to set two appliances; those have since been
        # set, so the round after there is nothing left to differ.
        assert home.value("mismatch") == "2"
        await home.evaluate()
        assert home.value("mismatch") == "0"
        assert home.values("mismatch")["differences"] == []

    async def test_the_command_sensor_is_an_enum_over_every_state_it_can_take(
        self, home: LiveHome
    ) -> None:
        """De standen zijn een vaste lijst, dus Home Assistant mag ze vertalen.

        The states are a fixed list, so Home Assistant may translate them.

        Bij een `enum` logt Home Assistant een fout zodra er een waarde langskomt
        die niet in `options` staat. De lijst wordt daarom afgeleid uit
        `preferred_mode`, niet met de hand opgeschreven: wie daar ooit een stand
        aan toevoegt, hoeft deze lijst niet te onthouden.

        On an `enum` Home Assistant logs an error the moment a value appears that
        is not in `options`. The list is therefore derived from `preferred_mode`
        rather than written out by hand: whoever adds a mode there need not
        remember this list too.
        """
        from custom_components.climate_director.engine.families import (
            MODE_FAN_ONLY,
            MODE_OFF,
            ModeFamily,
            preferred_mode,
        )
        from custom_components.climate_director.sensor import (
            STATE_LEFT_ALONE,
            STATE_UNREACHABLE,
        )

        attributes = home.values(f"command_{LIVING}")
        assert attributes["device_class"] == "enum"
        options = set(attributes["options"])

        reachable = {preferred_mode(family) for family in ModeFamily}
        reachable |= {MODE_OFF, MODE_FAN_ONLY, STATE_LEFT_ALONE, STATE_UNREACHABLE}
        assert reachable <= options, sorted(reachable - options)
        assert home.value(f"command_{LIVING}") in options

    async def test_every_command_state_is_translated(self) -> None:
        """Een stand zonder tekst laat Home Assistant de kale sleutel tonen.

        Deze bewaking leest de **bron**: `strings.json` en de zes
        vertaalbestanden. Wat hij dekt: de sleutels onder
        `entity.sensor.would_command.state` zijn in alle zeven bestanden precies
        dezelfde zes als `COMMAND_STATES` in `sensor.py` (*cool*, *fan_only*,
        *heat*, *left_alone*, *off*, *unreachable*) - geen ontbrekende en geen
        extra. Daarmee ligt de verzameling vast, niet de tekst erachter. Wat hij
        **niet** dekt: of die teksten van elkaar verschillen of leesbaar zijn, of
        de sleutel ook op een echt scherm terechtkomt, en de andere
        sensoreigenschappen. De structurele afspraak staat in `AGENTS.md`
        (projectspecifieke afspraken: welke bronbewakingen er zijn).

        A state without wording makes Home Assistant show the bare key.

        This guard reads the **source**: `strings.json` and the six translation
        files. What it covers: the keys under `entity.sensor.would_command.state`
        are exactly the same six in all seven files as `COMMAND_STATES` in
        `sensor.py` (*cool*, *fan_only*, *heat*, *left_alone*, *off*,
        *unreachable*) - none missing and none extra. That pins the set down, not
        the wording behind it. What it does **not** cover: whether those texts
        differ from each other or read well, whether the key reaches a real
        screen, and the other sensor attributes. The structural agreement stands
        in `AGENTS.md` (project-specific agreements: which source guards there
        are).
        """
        from pathlib import Path

        from custom_components.climate_director.sensor import COMMAND_STATES

        component = Path(__file__).resolve().parents[1] / "custom_components" / "climate_director"
        files = [component / "strings.json", *sorted((component / "translations").glob("*.json"))]
        for path in files:
            data = json.loads(path.read_text(encoding="utf-8"))
            states = data["entity"]["sensor"]["would_command"]["state"]
            assert sorted(states) == sorted(COMMAND_STATES), path.name

    async def test_the_mismatch_sensor_carries_no_unit(self, home: LiveHome) -> None:
        """Een telling is geen meting met een eenheid.

        A count is not a measurement with a unit.

        Er stond `appliances` als eenheid, onvertaald en in het Engels, achter
        een getal dat gewoon een aantal is. Home Assistant zet dat er letterlijk
        achter, dus in het Nederlands stond er "2 appliances".

        The unit read `appliances`, untranslated and in English, behind a number
        that is simply a count. Home Assistant prints that verbatim, so in Dutch
        it said "2 appliances".
        """
        assert "unit_of_measurement" not in home.values("mismatch")

    async def test_the_decision_event_carries_the_outcome(self, home: LiveHome) -> None:
        fired = home.fired("climate_director_decision")
        assert fired, "er hoort na de eerste beslissing een event te zijn"
        living = [item for item in fired if item["zone_id"] == "woonkamer"][-1]
        assert living["granted"] == "heat"
        assert living["entity_id"] == LIVING
        assert living["temperature"] == 21.0

    async def test_no_event_is_fired_when_nothing_changed(self, home: LiveHome) -> None:
        before = len(home.fired("climate_director_decision"))
        await home.evaluate()
        assert len(home.fired("climate_director_decision")) == before

    async def test_a_house_wide_stop_refuses_a_precondition_by_name(self) -> None:
        """De huisbrede weigering noemt de deur, ook als die in een andere zone staat.

        The house-wide refusal names the door, even when it stands in another zone.
        """
        live = await start_house(
            two_zone_installation(
                house_wide_openings=[LIVING],
                openings=[
                    {"entity_id": "binary_sensor.achterdeur", "delay": 0, "zone_ids": ["zolder"]}
                ],
            ),
            states=cold_two_rooms(),
        )
        try:
            live.set("binary_sensor.achterdeur", "on")
            await live.settle()
            await live.call(
                "climate_director", "precondition", {"zone_ids": ["woonkamer"], "minutes": 45}
            )
            await asyncio.sleep(1.4)
            await live.hass.async_block_till_done()

            fired = live.fired("climate_director_precondition_refused")
            assert fired, "de weigering is nooit gemeld"
            assert "achterdeur" in fired[-1]["opening_names"][0]
        finally:
            await stop_house(live)
