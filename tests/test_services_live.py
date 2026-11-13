"""De acties, hun levensduur en het vooruit-verzoek in een echte Home Assistant.

The actions, their lifetime and the pre-conditioning request in a real house."""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from harness_live import (
    LiveHome,
    start_bare_house,
    start_house,
    stop_house,
)
from homeassistant.util import dt as dt_util
from live_helpers import (
    ATTIC,
    LIVING,
    cold_two_rooms,
    two_zone_installation,
)

pytest_plugins = ["live_fixtures"]
pytestmark = pytest.mark.usefixtures("appliance")


class TestTheActionsAndTheirLifetime:
    """De acties horen bij de integratie, dus ze gaan met de laatste mee.

    The actions belong to the integration, so they go with the last one.

    Ze stonden er na het afbreken nog, en dan gebeurt er bij een aanroep niets:
    de handler loopt over de geladen installaties, en dat zijn er nul. Een actie
    die er is en niets doet is erger dan een actie die er niet is - dan zegt
    Home Assistant tenminste dat hij niet bestaat.

    They stood there after tearing down, and then a call does nothing: the
    handler walks the loaded installations, and there are none. An action that
    exists and does nothing is worse than an action that does not exist - at
    least then Home Assistant says so.
    """

    async def test_the_actions_stand_while_an_installation_is_loaded(self, home: LiveHome) -> None:
        for name in (
            "evaluate",
            "precondition",
            "cancel_precondition",
            "set_override",
            "clear_override",
        ):
            assert home.hass.services.has_service("climate_director", name), name

    async def test_the_last_installation_leaves_the_actions_standing(self) -> None:
        """Ook zonder installatie bestaan de acties; een aanroep botst netjes.

        Even without an installation the actions exist; a call hits the proper
        error instead of "service not found".
        """
        from homeassistant.exceptions import ServiceValidationError

        live = await start_house(
            two_zone_installation(), states=cold_two_rooms(), entry_id="acties"
        )
        try:
            await live.hass.config_entries.async_unload(live.entry.entry_id)
            await live.hass.async_block_till_done()
            for name in (
                "evaluate",
                "precondition",
                "cancel_precondition",
                "set_override",
                "clear_override",
            ):
                assert live.hass.services.has_service("climate_director", name), name
            with pytest.raises(ServiceValidationError, match="installation"):
                await live.hass.services.async_call(
                    "climate_director",
                    "precondition",
                    {"zone_ids": ["woonkamer"], "minutes": 30},
                    blocking=True,
                )
        finally:
            await stop_house(live)

    async def test_setting_up_again_brings_them_back(self) -> None:
        live = await start_house(
            two_zone_installation(), states=cold_two_rooms(), entry_id="opnieuw"
        )
        try:
            await live.hass.config_entries.async_unload(live.entry.entry_id)
            await live.hass.async_block_till_done()
            await live.hass.config_entries.async_setup(live.entry.entry_id)
            await live.hass.async_block_till_done()
            assert live.hass.services.has_service("climate_director", "evaluate")
        finally:
            await stop_house(live)


class TestTheActions:
    """De drie acties, met hun velden en hun grenzen.

    The three actions, with their fields and their limits.
    """

    async def test_evaluate_decides_again(self, home: LiveHome) -> None:
        home.set("sensor.woonkamer", "22.0")
        await home.call("climate_director", "evaluate", {})
        await asyncio.sleep(1.4)
        await home.hass.async_block_till_done()
        assert home.state(LIVING) == "off"

    async def test_evaluate_accepts_a_single_entry_id(self, home: LiveHome) -> None:
        await home.call("climate_director", "evaluate", {"entry_id": home.entry.entry_id})
        await home.settle()

    async def test_evaluate_ignores_an_unknown_entry_id(self, home: LiveHome) -> None:
        await home.call("climate_director", "evaluate", {"entry_id": "geen-installatie"})
        await home.settle()

    async def test_actions_exist_without_a_loaded_entry(self) -> None:
        """Zonder geladen installatie bestaan de acties, en botsen ze netjes.

        Without a loaded entry the actions exist, and they hit the proper error.
        """
        from homeassistant.exceptions import ServiceValidationError

        hass = await start_bare_house()
        try:
            assert hass.services.has_service("climate_director", "precondition")
            assert hass.services.has_service("climate_director", "cancel_precondition")
            assert hass.services.has_service("climate_director", "evaluate")
            with pytest.raises(ServiceValidationError, match="installation"):
                await hass.services.async_call(
                    "climate_director",
                    "precondition",
                    {"zone_ids": ["woonkamer"], "minutes": 30},
                    blocking=True,
                )
            with pytest.raises(ServiceValidationError, match="installation"):
                await hass.services.async_call(
                    "climate_director",
                    "cancel_precondition",
                    {"zone_ids": ["woonkamer"]},
                    blocking=True,
                )
        finally:
            await hass.async_stop(force=True)

    async def test_preconditioning_runs_an_empty_house(self, home: LiveHome) -> None:
        home.set("person.danny", "not_home")
        await home.evaluate()
        assert home.state(LIVING) == "off"

        await home.call(
            "climate_director", "precondition", {"zone_ids": ["woonkamer"], "minutes": 45}
        )
        await asyncio.sleep(1.4)
        await home.hass.async_block_till_done()
        assert home.state(LIVING) == "heat"
        assert home.state(ATTIC) == "off", "alleen de gevraagde zone hoort te draaien"

    @pytest.mark.parametrize("minutes", ["45", "45.0"])
    async def test_a_duration_may_arrive_as_text(self, home: LiveHome, minutes: str) -> None:
        """YAML levert getallen vaak als tekst aan; het schema hoort dat om te zetten.

        YAML often hands numbers over as text; the schema should coerce that.
        """
        home.set("person.danny", "not_home")
        await home.evaluate()
        assert home.state(LIVING) == "off"

        await home.call(
            "climate_director", "precondition", {"zone_ids": ["woonkamer"], "minutes": minutes}
        )
        await asyncio.sleep(1.4)
        await home.hass.async_block_till_done()
        assert home.state(LIVING) == "heat"

    async def test_a_request_is_capped_at_the_installation_maximum(self, home: LiveHome) -> None:
        home.coordinator.async_precondition(["woonkamer"], 6000)
        granted = home.coordinator._live_preconditions()["woonkamer"]

        assert (granted - dt_util.now()).total_seconds() <= 7200 + 5

    async def test_calling_without_minutes_grants_the_installation_maximum(
        self, home: LiveHome
    ) -> None:
        """De blueprint laat `minutes` weg; dat hoort het maximum te geven.

        The blueprint omits `minutes`; that should grant the installation maximum.
        """
        home.set("person.danny", "not_home")
        await home.call("climate_director", "precondition", {"zone_ids": ["woonkamer"]})
        granted = home.coordinator._live_preconditions()["woonkamer"]

        assert (granted - dt_util.now()).total_seconds() > 7200 - 5

    async def test_calling_with_zero_minutes_is_refused_by_the_schema(self, home: LiveHome) -> None:
        """Nul minuten is een typefout, en die hoort te botsen, niet te verdwijnen.

        Zero minutes is a typo, and a typo should hit something rather than
        vanish.

        Het scherm staat het al niet toe (`min: 1` in services.yaml), dus een
        nul komt uit een met de hand geschreven aanroep. Die stil laten mislukken
        is precies verkeerd: je drukt op de knop, er gebeurt niets, en er is geen
        spoor van waarom.

        The screen already disallows it (`min: 1` in services.yaml), so a zero
        comes from a hand-written call. Failing that silently is exactly wrong:
        you press the button, nothing happens, and there is no trace of why.
        """
        import voluptuous as vol

        home.set("person.danny", "not_home")
        await home.evaluate()
        assert home.state(LIVING) == "off"

        with pytest.raises(vol.Invalid):
            await home.call(
                "climate_director", "precondition", {"zone_ids": ["woonkamer"], "minutes": 0}
            )
        assert home.coordinator._live_preconditions() == {}

    async def test_an_unknown_zone_is_refused_with_an_error(self, home: LiveHome) -> None:
        """Een typefout in `zone_ids` hoort te botsen, niet alleen te loggen.

        A typo in `zone_ids` should hit something, not just log a warning.
        """
        from homeassistant.exceptions import ServiceValidationError

        with pytest.raises(ServiceValidationError):
            await home.call(
                "climate_director", "precondition", {"zone_ids": ["woonkamr"], "minutes": 30}
            )
        with pytest.raises(ServiceValidationError):
            await home.call("climate_director", "cancel_precondition", {"zone_ids": ["woonkamr"]})

    async def test_an_empty_zone_list_means_no_zones(self, home: LiveHome) -> None:
        """Een lege lijst is geen enkele zone; weglaten is nog steeds het hele huis.

        An empty list means no zones; leaving the field away still means the
        whole house.
        """
        home.set("person.danny", "not_home")
        await home.evaluate()
        assert home.state(LIVING) == "off"

        await home.call("climate_director", "precondition", {"zone_ids": [], "minutes": 30})
        await home.settle()
        assert home.coordinator._live_preconditions() == {}

        await home.call("climate_director", "precondition", {"minutes": 30})
        await home.settle()
        assert set(home.coordinator._live_preconditions()) == {"woonkamer", "zolder"}

        await home.call("climate_director", "cancel_precondition", {"zone_ids": []})
        await home.settle()
        assert set(home.coordinator._live_preconditions()) == {"woonkamer", "zolder"}

    async def test_an_unknown_entry_id_is_reported_as_such(self, home: LiveHome) -> None:
        """Een onbekende installatie hoort zo te heten, niet "onbekende zone".

        An unknown installation should be called that, not "unknown zone".
        """
        from homeassistant.exceptions import ServiceValidationError

        with pytest.raises(ServiceValidationError, match="installation"):
            await home.call(
                "climate_director",
                "precondition",
                {"entry_id": "bestaat_niet", "zone_ids": ["woonkamer"], "minutes": 30},
            )
        with pytest.raises(ServiceValidationError, match="installation"):
            await home.call("climate_director", "cancel_precondition", {"entry_id": "bestaat_niet"})

    async def test_zero_minutes_still_grants_nothing_straight_at_the_coordinator(
        self, home: LiveHome
    ) -> None:
        """Ook zonder het schema ertussen blijft nul minuten geen verzoek.

        Without the schema in between, zero minutes still is not a request.
        """
        assert home.coordinator.async_precondition(["woonkamer"], 0) == {}
        assert home.coordinator._live_preconditions() == {}

    async def test_cancelling_stops_it_again(self, home: LiveHome) -> None:
        home.set("person.danny", "not_home")
        await home.call("climate_director", "precondition", {"minutes": 60})
        await asyncio.sleep(1.4)
        await home.hass.async_block_till_done()
        assert home.state(LIVING) == "heat"

        await home.call("climate_director", "cancel_precondition", {})
        await asyncio.sleep(1.4)
        await home.hass.async_block_till_done()
        assert home.state(LIVING) == "off"

    async def test_an_unknown_zone_is_simply_dropped(self, home: LiveHome) -> None:
        granted = home.coordinator.async_precondition(["kelder", "woonkamer"], 30)
        assert set(granted) == {"woonkamer"}

    async def test_a_negative_duration_is_refused_by_the_schema(self, home: LiveHome) -> None:
        import voluptuous as vol

        with pytest.raises(vol.Invalid):
            await home.call("climate_director", "precondition", {"minutes": -5})

    async def test_ignore_openings_is_accepted_and_carried(self, home: LiveHome) -> None:
        home.set("person.danny", "not_home")
        home.set("binary_sensor.achterdeur", "on")
        await home.evaluate()

        await home.call(
            "climate_director",
            "precondition",
            {"zone_ids": ["woonkamer"], "minutes": 30, "ignore_openings": True},
        )
        await asyncio.sleep(1.4)
        await home.hass.async_block_till_done()
        assert home.state(LIVING) == "heat", "een uitdrukkelijk 'toch doen' hoort door te gaan"


class TestTheAlarmUnderAPreConditioningRequest:
    """Een afgelopen verzoek mag de wekker van een lopend verzoek niet doven.

    A request that has run out must not put out the alarm of a running one.

    Er staat altijd maar een wekker, op het eerstvolgende verzoek dat afloopt.
    Werd die gezet op de ruwe lijst, dan koos hij een verzoek dat al voorbij was,
    zag "dat moment ligt achter ons" en zette helemaal niets. Het lopende verzoek
    liep daarna af zonder dat iemand het merkte, en op een stille middag stookt
    een leeg huis dan door tot er toevallig iets anders verandert.

    There is only ever one alarm, set on the first request to run out. Set from
    the raw list, it picked a request that was already over, saw "that moment is
    behind us" and set nothing at all. The running request then ran out with
    nobody noticing, and on a quiet afternoon an empty house keeps burning until
    something else happens to change.
    """

    async def test_a_stale_request_does_not_swallow_the_alarm(
        self, home: LiveHome, monkeypatch: pytest.MonkeyPatch
    ) -> None:

        from custom_components.climate_director import coordinator as module

        home.coordinator.async_precondition(["woonkamer"], 30)
        assert home.coordinator._cancel_precondition_wake is not None

        # Een uur verder is dat eerste verzoek allang voorbij, maar niemand
        # heeft het gelezen, dus het staat er nog.
        #
        # An hour on that first request is long over, but nobody has read it, so
        # it is still there.
        later = dt_util.now() + timedelta(hours=1)
        monkeypatch.setattr(module.dt_util, "now", lambda: later)
        home.coordinator.cancel_pending_precondition_wake()

        home.coordinator.async_precondition(["zolder"], 60)
        assert home.coordinator._cancel_precondition_wake is not None, (
            "het lopende verzoek hoort zijn eigen wekker te krijgen"
        )
