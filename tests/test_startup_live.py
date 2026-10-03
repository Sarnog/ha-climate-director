"""Het opstarten van Home Assistant: de eerste beslissing wacht op het herstel.

Deciding on the startup of Home Assistant: the first decision waits for the restore.

Bij het opzetten van de config entry zijn de entiteiten er al, maar Home Assistant
is nog bezig: herstelde standen, automatiseringen en andere integraties komen pas
daarna. Wat er dan wél al gebeurt is een toestandswijziging van een gevolgde
entiteit - een sensor die binnenkomt terwijl de integraties laden. Die wekt de
debouncer, en zonder een poort besloot de director een seconde later op een half
herstelde wereld: een apparaat dat iemand eerder die dag met de hand uitzette stond dan
al weer aan, en bleef de rest van de dag aan. `tests/test_startup.py` legt de
poort in de coordinator vast; dit bestand meet hem in een echte Home Assistant,
met het harnas in `CoreState.starting` in plaats van meteen op `running`.

When the config entry is set up the entities exist, but Home Assistant is still
busy: restored states, automations and other integrations come only afterwards.
What does already happen is a state change of a tracked entity - a sensor arriving
while the integrations load. That wakes the debouncer, and without a gate the
director decided a second later on a half-restored world: an appliance somebody
switched off by hand earlier that day stood on again and stayed on for the rest of the
day. `tests/test_startup.py` pins the gate down in the coordinator; this file
measures it inside a real Home Assistant, with the harness in `CoreState.starting`
rather than on `running` at once.

Wat er in die seconden aan een override of een vooruit-verzoek gebeurt, wint van
het herstel: de schakelaar, `set_override`, `clear_override` en de keuze
`ignore_openings` zijn jonger dan het bestand, dus het herstel slaat zo'n zone
over (en `bypass` wordt samengevoegd in plaats van vervangen). Alleen een echte
overgang van de schakelaar telt: het herstellen van zijn eigen stand
(`RestoreEntity`) is geen handeling van de gebruiker.

What happens in those seconds to an override or a pre-conditioning request wins
over the restore: the switch, `set_override`, `clear_override` and the
`ignore_openings` choice are younger than the file, so the restore skips such a
zone (and `bypass` is merged rather than replaced). Only a real transition of the
switch counts: restoring its own position (`RestoreEntity`) is no action by the
user.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import timedelta
from typing import Any

from harness_live import (
    LiveHome,
    new_config_dir,
    settings,
    source,
    start_house,
    stop_house,
    zone,
)
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState
from homeassistant.util import dt as dt_util

from custom_components.climate_director.const import WHEN_DONE_LEAVE, WHEN_DONE_TURN_OFF

LIVING = "climate.woonkamer"
SENSOR = "sensor.woonkamer"
OUTDOOR = "sensor.buiten"
ATTIC = "climate.zolder"
ATTIC_SENSOR = "sensor.zolder"
PERSON = "person.danny"
MODES = {"hvac_modes": ["off", "heat", "cool"], "current_temperature": 18.5}

#: De sleutel waaronder de coordinator zijn stand bewaart, met de entry-id van
#: dit harnas (`live`).
#: The key the coordinator stores its state under, with this harness's entry id
#: (`live`).
STORE_KEY = "climate_director.live.precondition"


def store_path(config_dir: str) -> str:
    """Return the path of the file a previous run leaves its state in."""
    return os.path.join(config_dir, ".storage", STORE_KEY)


def write_store(config_dir: str, data: dict[str, Any]) -> None:
    """Write a state file exactly as a previous run left it behind.

    Hetzelfde bestand dat de opslag van de integratie zelf schrijft; een test die
    een herstart nabouwt hoeft de integratie daarvoor niet eerst te laten
    wegschrijven.

    The same file the integration's own store writes; a test rebuilding a restart
    need not have the integration write it out first.
    """
    os.makedirs(os.path.dirname(store_path(config_dir)), exist_ok=True)
    payload = {
        "version": 1,
        "minor_version": 1,
        "key": STORE_KEY,
        "data": data,
    }
    with open(store_path(config_dir), "w", encoding="utf-8") as handle:
        json.dump(payload, handle)


def read_store(config_dir: str) -> dict[str, Any]:
    """Return the data in the state file, as a later reader would see it."""
    with open(store_path(config_dir), encoding="utf-8") as handle:
        return json.load(handle)["data"]


def installation() -> dict[str, Any]:
    """Return a cold single-zone house with one boiler."""
    return {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("woonkamer_ketel", LIVING)],
                heat=settings(21.0, 20.0),
            )
        ],
        "outdoor_sensor": OUTDOOR,
    }


def cold_world() -> dict[str, tuple[str, dict[str, Any]]]:
    """Return a world in which the living room wants heat and the boiler is off."""
    return {
        SENSOR: ("18.5", {"unit_of_measurement": "°C"}),
        OUTDOOR: ("4.0", {}),
        LIVING: ("off", {"hvac_modes": ["off", "heat"], "temperature": 19.0}),
    }


async def settle_the_debouncer(home: LiveHome) -> None:
    """Let the debouncer's second pass and everything behind it finish."""
    await asyncio.sleep(1.5)
    await home.settle()


async def start_up(home: LiveHome) -> None:
    """Let Home Assistant report that it has started, and settle."""
    home.hass.set_state(CoreState.running)
    home.hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await home.hass.async_block_till_done()
    await settle_the_debouncer(home)


def watch_worlds(home: LiveHome) -> list[Any]:
    """Return a list that every world the director builds is appended to.

    Een beslissing bouwt haar wereld één keer, in `_async_evaluate`; de lijst
    liegt er dus niet over of er beslist is. Dat is precies wat "de eerste
    beslissing ziet het" meetbaar maakt: op het moment van de beslissing zelf, in
    plaats van achteraf uit een stand die later alsnog hersteld wordt.

    A decision builds its world once, in `_async_evaluate`; the list therefore
    does not lie about whether a decision was taken. That is exactly what makes
    "the first decision sees it" measurable: at the moment of the decision
    itself, rather than afterwards from a state that gets restored later on
    anyway.
    """
    built: list[Any] = []
    original = home.coordinator.build_world

    def spy() -> Any:
        found = original()
        built.append(found)
        return found

    home.coordinator.build_world = spy  # type: ignore[method-assign]
    return built


def reason_of(home: LiveHome, zone_id: str = "woonkamer") -> str:
    """Return the reason of one zone's last decision."""
    decision = home.coordinator.data.decision_for(zone_id)
    assert decision is not None, f"geen beslissing voor {zone_id}"
    return decision.reason.value


class TestAHandFromBeforeTheRestart:
    """Een hand-uitzetting van vandaag overleeft het opstarten.

    A hand-back from today survives the startup.
    """

    async def test_the_appliance_stays_off_through_the_startup(self) -> None:
        config_dir = new_config_dir()
        write_store(config_dir, {"handed_back": {"woonkamer": dt_util.now().date().isoformat()}})

        home = await start_house(
            installation(),
            config_dir=config_dir,
            core_state=CoreState.starting,
            states=cold_world(),
        )
        try:
            built = watch_worlds(home)
            home.clear_calls()

            # Tijdens het opstarten komt er een nieuwe sensormeting binnen.
            home.hass.states.async_set(SENSOR, "18.4", {"unit_of_measurement": "°C"})
            await settle_the_debouncer(home)

            assert built == [], "er is beslist vóór het herstel van de opslag"
            assert home.climate_calls() == [], "de director stuurde tijdens het opstarten"
            assert home.state(LIVING) == "off"

            await start_up(home)

            assert reason_of(home) == "manual_override"
            assert home.state(LIVING) == "off", "het apparaat hoort uit te blijven"
        finally:
            await stop_house(home)


class TestARequestFromBeforeTheRestart:
    """Een vooruit-verzoek van vóór de herstart zit in de eerste beslissing.

    A pre-conditioning request from before the restart is in the first decision.
    """

    async def test_the_first_decision_sees_the_request(self) -> None:
        config_dir = new_config_dir()
        until = dt_util.now() + timedelta(minutes=30)
        write_store(config_dir, {"until": {"woonkamer": until.isoformat()}})

        home = await start_house(
            installation(),
            config_dir=config_dir,
            core_state=CoreState.starting,
            states=cold_world(),
        )
        try:
            built = watch_worlds(home)
            home.clear_calls()

            home.hass.states.async_set(SENSOR, "18.4", {"unit_of_measurement": "°C"})
            await settle_the_debouncer(home)

            assert built == [], "er is beslist vóór het herstel van de opslag"
            assert home.climate_calls() == []

            await start_up(home)

            assert built, "de eerste beslissing is nooit gevallen"
            assert built[0].preconditioning("woonkamer"), (
                "de eerste beslissing kent het bewaarde vooruit-verzoek niet"
            )
            assert reason_of(home) == "regulating"
            assert home.state(LIVING) == "heat"
        finally:
            await stop_house(home)


class TestWithoutAnythingToRestore:
    """De poort legt de integratie niet stil: zonder herstel doet hij gewoon zijn werk.

    The gate does not silence the integration: without anything to restore it
    simply does its work.
    """

    async def test_the_zone_is_regulated_after_the_startup(self) -> None:
        home = await start_house(
            installation(),
            core_state=CoreState.starting,
            states=cold_world(),
        )
        try:
            built = watch_worlds(home)
            home.clear_calls()

            home.hass.states.async_set(SENSOR, "18.4", {"unit_of_measurement": "°C"})
            await settle_the_debouncer(home)

            assert built == [], "er is beslist vóór het herstel van de opslag"

            await start_up(home)

            assert reason_of(home) == "regulating"
            assert home.state(LIVING) == "heat"
            assert [call[0] for call in home.climate_calls()], "de ketel is nooit aangestuurd"
        finally:
            await stop_house(home)


def two_rooms() -> dict[str, Any]:
    """Return two rooms with an appliance of their own, and one resident.

    Twee zones met elk een eigen apparaat, zodat een hand in de ene zone niets
    over de andere zegt; de bewoner houdt het huis bewoond, zodat een hand niet om
    die reden vervalt.

    Two zones with an appliance of their own, so that a hand in one zone says
    nothing about the other; the resident keeps the house occupied, so a hand does
    not lapse for that reason.
    """
    return {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("w_living", LIVING, role="heat_cool")],
                heat=settings(21.0, 20.0),
            ),
            zone(
                "zolder",
                sources=[source("z_attic", ATTIC, role="heat_cool")],
                heat=settings(21.0, 20.0),
            ),
        ],
        "residents": [{"resident_id": "danny", "presence_entity": PERSON}],
    }


def two_room_world(
    *, living: str = "off", attic: str = "off", person: str = "home"
) -> dict[str, tuple[str, dict[str, Any]]]:
    """Return a cold two-room world with the resident at home, or away."""
    return {
        SENSOR: ("18.5", {"unit_of_measurement": "°C"}),
        ATTIC_SENSOR: ("18.5", {"unit_of_measurement": "°C"}),
        LIVING: (living, dict(MODES)),
        ATTIC: (attic, dict(MODES)),
        PERSON: (person, {}),
    }


class TestASaveDuringTheStartupLeavesTheStoreAlone:
    """Wat tijdens het opstarten genoteerd wordt wist de opslag niet.

    What is noted during the startup does not wipe the store.

    Een bewoner die tijdens het opstarten thuiskomt, laat de coordinator bewaren -
    en zonder de poort schreef die schrijfactie het bestand vóór het herstel vol
    met de half opgebouwde staat van dit moment. Dan was de hand van de gebruiker
    weg en stond het apparaat na de start weer aan.
    """

    async def test_the_stored_hand_survives_a_homecoming_during_the_startup(self) -> None:
        config_dir = new_config_dir()
        today = dt_util.now().date().isoformat()
        write_store(config_dir, {"handed_back": {"woonkamer": today}})

        home = await start_house(
            two_rooms(),
            config_dir=config_dir,
            core_state=CoreState.starting,
            states=two_room_world(person="not_home"),
        )
        try:
            home.clear_calls()
            home.hass.states.async_set(PERSON, "home", {})
            await settle_the_debouncer(home)

            assert read_store(config_dir)["handed_back"] == {"woonkamer": today}, (
                "er is vóór het herstel in de opslag geschreven"
            )

            await start_up(home)

            assert home.state(LIVING) == "off", "het apparaat hoort uit te blijven"
            assert reason_of(home) == "manual_override"
        finally:
            await stop_house(home)


class TestAHandDuringTheStartupJoinsTheStoredOne:
    """Een hand van tijdens het opstarten komt naast de bewaarde hand te staan.

    A hand from during the startup stands beside the stored hand.

    De opslag houdt de woonkamer stil en iemand zet tijdens het opstarten de zolder
    uit. Het herstel voegt samen in plaats van te vervangen, en wat tijdens het
    opstarten bleef liggen wordt ná het herstel één keer weggeschreven - dus staan
    beide zones in het bestand en krijgt geen van beide apparaten een commando.
    """

    async def test_both_hands_end_up_in_the_store(self) -> None:
        config_dir = new_config_dir()
        today = dt_util.now().date().isoformat()
        write_store(config_dir, {"handed_back": {"woonkamer": today}})

        home = await start_house(
            two_rooms(),
            config_dir=config_dir,
            core_state=CoreState.starting,
            states=two_room_world(attic="heat"),
        )
        try:
            home.clear_calls()
            home.hass.states.async_set(ATTIC, "off", dict(MODES))
            await settle_the_debouncer(home)

            await start_up(home)

            assert set(home.coordinator._handed_back) == {"woonkamer", "zolder"}, (
                "het herstel en de hand van tijdens het opstarten zijn niet samengevoegd"
            )
            assert home.climate_calls() == [], (
                "geen van beide apparaten hoort een commando te krijgen"
            )
            assert set(read_store(config_dir)["handed_back"]) == {"woonkamer", "zolder"}, (
                "wat tijdens het opstarten bleef liggen is nooit weggeschreven"
            )
        finally:
            await stop_house(home)


class TestAPreconditionDuringTheStartupJoinsTheStoredOne:
    """Een vooruit-verzoek van tijdens het opstarten komt naast het bewaarde.

    A pre-conditioning request from during the startup stands beside the stored one.

    De opslag draagt een verzoek voor de woonkamer; tijdens het opstarten vraagt
    iemand vooruit voor de zolder. Beide horen in de eerste beslissing te zitten,
    en de zolder hoort er na de start ook warm van te worden.
    """

    async def test_both_requests_stand_in_the_first_round(self) -> None:
        config_dir = new_config_dir()
        until = dt_util.now() + timedelta(minutes=40)
        write_store(config_dir, {"until": {"woonkamer": until.isoformat()}})

        home = await start_house(
            two_rooms(),
            config_dir=config_dir,
            core_state=CoreState.starting,
            states=two_room_world(),
        )
        try:
            home.clear_calls()
            await home.call(
                "climate_director", "precondition", {"zone_ids": ["zolder"], "minutes": 30}
            )
            await settle_the_debouncer(home)

            await start_up(home)

            assert set(home.coordinator._precondition) == {"woonkamer", "zolder"}, (
                "het herstel en het verzoek van tijdens het opstarten zijn niet samengevoegd"
            )
            assert home.state(LIVING) == "heat"
            assert home.state(ATTIC) == "heat"
        finally:
            await stop_house(home)


class TestAFreshOverrideDuringTheStartupSurvivesAnExpiredOne:
    """Een verse overdracht van tijdens het opstarten overleeft een verlopen looptijd.

    A fresh handover from during the startup survives an expired duration.

    De opslag draagt een override die allang verlopen is; tijdens het opstarten zet
    iemand de zone met de actie `set_override` een uur op warm. Het herstel voegt
    samen: de verlopen looptijd komt niet terug, maar de verse overdracht mag er
    ook niet door worden gewist.
    """

    async def test_the_fresh_override_stays(self) -> None:
        config_dir = new_config_dir()
        past = (dt_util.now() - timedelta(hours=2)).isoformat()
        write_store(
            config_dir,
            {"override_until": {"woonkamer": past}, "override_started": {"woonkamer": past}},
        )

        home = await start_house(
            two_rooms(),
            config_dir=config_dir,
            core_state=CoreState.starting,
            states=two_room_world(),
        )
        try:
            await home.call(
                "climate_director",
                "set_override",
                {"zone_id": "woonkamer", "hvac_mode": "heat", "temperature": 23, "minutes": 60},
            )
            await settle_the_debouncer(home)

            await start_up(home)

            assert home.coordinator.zone_overrides.get("woonkamer") is True
            assert "woonkamer" in home.coordinator.zone_override_until
            assert reason_of(home) == "manual_override"
            assert home.state(LIVING) == "heat"
        finally:
            await stop_house(home)


class TestAnOverrideEndedDuringTheStartupWins:
    """`clear_override` van tijdens het opstarten wint van de opgeslagen looptijd.

    A `clear_override` from during the startup wins over the stored duration.

    De opslag draagt een lopende override; iemand beëindigt hem terwijl Home
    Assistant nog bezig is. Het herstel mag hem niet terugzetten: die handeling van
    de gebruiker is jonger dan het bestand, en anders staat de zone na de start
    stil terwijl de gebruiker hem net teruggaf.
    """

    async def test_the_stored_override_does_not_come_back(self) -> None:
        config_dir = new_config_dir()
        until = dt_util.now() + timedelta(hours=2)
        write_store(
            config_dir,
            {
                "override_until": {"woonkamer": until.isoformat()},
                "override_started": {"woonkamer": until.isoformat()},
                "override_when_done": {"woonkamer": WHEN_DONE_LEAVE},
                "override_entity": {"woonkamer": LIVING},
            },
        )

        home = await start_house(
            two_rooms(),
            config_dir=config_dir,
            core_state=CoreState.starting,
            states=two_room_world(),
        )
        try:
            home.clear_calls()
            await home.call("climate_director", "clear_override", {"zone_id": "woonkamer"})
            await settle_the_debouncer(home)

            await start_up(home)

            assert home.coordinator.zone_overrides.get("woonkamer") is not True, (
                "het herstel zette de override van vóór de herstart weer aan"
            )
            assert "woonkamer" not in home.coordinator.zone_override_until
            assert reason_of(home) == "regulating", "de woonkamer hoort weer mee te doen"
            assert "woonkamer" not in read_store(config_dir).get("override_until", {}), (
                "de opgeslagen looptijd staat nog in het bestand"
            )
        finally:
            await stop_house(home)


class TestAFreshOverrideDuringTheStartupKeepsNoDuration:
    """`set_override` zonder looptijd erft de opgeslagen eindtijd niet.

    A `set_override` without a duration does not inherit the stored end time.

    De opslag draagt een override met nog een half uur te gaan en de keuze
    *uitzetten bij afloop*; iemand zet de zone tijdens het opstarten zonder
    looptijd over. Dat is een onbeperkte overdracht: erfde hij de opgeslagen
    eindtijd, dan ging het apparaat een half uur later uit terwijl de gebruiker
    juist niets van een einde had gezegd.
    """

    async def test_the_fresh_override_stands_without_an_end_time(self) -> None:
        config_dir = new_config_dir()
        until = dt_util.now() + timedelta(minutes=30)
        write_store(
            config_dir,
            {
                "override_until": {"woonkamer": until.isoformat()},
                "override_when_done": {"woonkamer": WHEN_DONE_TURN_OFF},
                "override_entity": {"woonkamer": LIVING},
            },
        )

        home = await start_house(
            two_rooms(),
            config_dir=config_dir,
            core_state=CoreState.starting,
            states=two_room_world(),
        )
        try:
            await home.call(
                "climate_director",
                "set_override",
                {"zone_id": "woonkamer", "hvac_mode": "heat", "temperature": 23},
            )
            await settle_the_debouncer(home)

            await start_up(home)

            assert home.coordinator.zone_overrides.get("woonkamer") is True
            assert "woonkamer" not in home.coordinator.zone_override_until, (
                "de verse overdracht erfde de opgeslagen eindtijd"
            )
            assert "woonkamer" not in home.coordinator.zone_override_when_done
            assert reason_of(home) == "manual_override"
        finally:
            await stop_house(home)


class TestARequestDuringTheStartupKeepsItsOwnEndTime:
    """Een vers vooruit-verzoek van tijdens het opstarten houdt zijn eigen eindtijd.

    A fresh pre-conditioning request from during the startup keeps its own end time.

    De opslag draagt een verzoek van negentig minuten; tijdens het opstarten vraagt
    iemand dertig minuten voor dezelfde kamer. Dat verse verzoek is jonger, dus
    geldt het - anders stookt het huis door op een oordeel van vóór de herstart.
    """

    async def test_the_fresh_request_wins(self) -> None:
        config_dir = new_config_dir()
        until = dt_util.now() + timedelta(minutes=90)
        write_store(config_dir, {"until": {"woonkamer": until.isoformat()}})

        home = await start_house(
            two_rooms(),
            config_dir=config_dir,
            core_state=CoreState.starting,
            states=two_room_world(),
        )
        try:
            await home.call(
                "climate_director", "precondition", {"zone_ids": ["woonkamer"], "minutes": 30}
            )
            await settle_the_debouncer(home)

            await start_up(home)

            stored = dt_util.parse_datetime(read_store(config_dir)["until"]["woonkamer"])
            assert stored is not None
            assert stored < until, "de opgeslagen eindtijd wint nog van het verse verzoek"
            assert home.coordinator._precondition["woonkamer"] < until
        finally:
            await stop_house(home)


class TestARequestDuringTheStartupKeepsItsIgnoreOpenings:
    """De keuze `ignore_openings` van een vers verzoek blijft naast de opslag staan.

    The `ignore_openings` choice of a fresh request stands beside the store.

    Het herstel van `bypass` voegde niet samen maar verving, dus een verzoek met
    *toch doen* van tijdens het opstarten verloor die keuze zodra er een opgeslagen
    verzoek in een andere kamer lag. Het opgeslagen verzoek hoort gewoon terug te
    komen; de verse keuze hoort te blijven.
    """

    async def test_the_fresh_request_keeps_its_choice(self) -> None:
        config_dir = new_config_dir()
        until = dt_util.now() + timedelta(minutes=40)
        # De opslag draagt een lege `bypass`-lijst: alleen dan loopt het herstel van
        # `bypass` langs deze regel, en alleen dan kan het de verse keuze vervangen.
        #
        # The store carries an empty `bypass` list: only then does the restore of
        # `bypass` come past this line, and only then can it replace the fresh choice.
        write_store(config_dir, {"until": {"woonkamer": until.isoformat()}, "bypass": []})

        home = await start_house(
            two_rooms(),
            config_dir=config_dir,
            core_state=CoreState.starting,
            states=two_room_world(),
        )
        try:
            await home.call(
                "climate_director",
                "precondition",
                {"zone_ids": ["zolder"], "minutes": 30, "ignore_openings": True},
            )
            await settle_the_debouncer(home)

            await start_up(home)

            assert set(home.coordinator._precondition) == {"woonkamer", "zolder"}
            assert home.coordinator._precondition_bypass == {"zolder"}, (
                "de verse keuze *toch doen* is door het herstel vervangen"
            )
            stored = read_store(config_dir)
            assert stored["bypass"] == ["zolder"]
            assert "woonkamer" in stored["until"]
        finally:
            await stop_house(home)


class TestACancelledRequestDuringTheStartupStaysCancelled:
    """Een annulering van tijdens het opstarten laat het verzoek niet terugkomen.

    A cancellation from during the startup does not let the request come back.

    De gebruiker zegt *nee* tegen een verzoek dat in het bestand nog loopt. Kwam
    dat verzoek na de start alsnog terug, dan stookte het huis door op een oordeel
    waar de gebruiker net vanaf wilde.
    """

    async def test_the_stored_request_stays_away(self) -> None:
        config_dir = new_config_dir()
        until = dt_util.now() + timedelta(minutes=40)
        write_store(config_dir, {"until": {"woonkamer": until.isoformat()}})

        home = await start_house(
            two_rooms(),
            config_dir=config_dir,
            core_state=CoreState.starting,
            states=two_room_world(),
        )
        try:
            await home.call("climate_director", "cancel_precondition", {"zone_ids": ["woonkamer"]})
            await settle_the_debouncer(home)

            await start_up(home)

            assert "woonkamer" not in home.coordinator._precondition, (
                "het opgeslagen verzoek kwam terug nadat de gebruiker het annuleerde"
            )
            assert "woonkamer" not in read_store(config_dir).get("until", {})
        finally:
            await stop_house(home)


class TestASwitchDuringTheStartupWins:
    """De overrideschakelaar van tijdens het opstarten wint van de opgeslagen stand.

    The override switch from during the startup wins over the stored state.

    De schakelaar zelf herstelt zijn stand (`RestoreEntity`) en dat is geen
    handeling van de gebruiker; alleen een echte overgang telt. Aan en weer uit
    tijdens het opstarten laat dus geen override achter, en aan naast een verlopen
    opgeslagen looptijd geeft een onbeperkte overdracht.

    The switch restores its own position (`RestoreEntity`), and that is no action
    by the user; only a real transition counts. On and off again during the
    startup therefore leaves no override behind, and on beside an expired stored
    duration gives an unlimited handover.
    """

    async def test_switching_it_on_and_off_leaves_no_override(self) -> None:
        config_dir = new_config_dir()
        until = dt_util.now() + timedelta(hours=1)
        write_store(
            config_dir,
            {
                "override_until": {"woonkamer": until.isoformat()},
                "override_entity": {"woonkamer": LIVING},
            },
        )

        home = await start_house(
            two_rooms(),
            config_dir=config_dir,
            core_state=CoreState.starting,
            states=two_room_world(),
        )
        try:
            switch = home.by_key("zone_woonkamer_override")
            await home.call("switch", "turn_on", {"entity_id": switch})
            await settle_the_debouncer(home)
            await home.call("switch", "turn_off", {"entity_id": switch})
            await settle_the_debouncer(home)

            await start_up(home)

            assert home.coordinator.zone_overrides.get("woonkamer") is not True, (
                "de uit- en aan-stand van de schakelaar is door het herstel ongedaan gemaakt"
            )
            assert home.state(switch) == "off"
            assert reason_of(home) == "regulating"
        finally:
            await stop_house(home)

    async def test_switching_it_on_gives_an_unlimited_override(self) -> None:
        config_dir = new_config_dir()
        past = (dt_util.now() - timedelta(hours=2)).isoformat()
        write_store(
            config_dir,
            {
                "override_until": {"woonkamer": past},
                "override_when_done": {"woonkamer": WHEN_DONE_TURN_OFF},
                "override_entity": {"woonkamer": LIVING},
            },
        )

        home = await start_house(
            two_rooms(),
            config_dir=config_dir,
            core_state=CoreState.starting,
            states=two_room_world(),
        )
        try:
            switch = home.by_key("zone_woonkamer_override")
            await home.call("switch", "turn_on", {"entity_id": switch})
            await settle_the_debouncer(home)

            await start_up(home)

            assert home.coordinator.zone_overrides.get("woonkamer") is True
            assert "woonkamer" not in home.coordinator.zone_override_until, (
                "de verlopen opgeslagen looptijd hangt toch aan de verse overdracht"
            )
            assert home.state(switch) == "on"
            assert reason_of(home) == "manual_override"
        finally:
            await stop_house(home)


class TestNothingToSaveCostsNoWrite:
    """Een herstart waarin niets te bewaren viel schrijft niets weg.

    A restart in which nothing needed saving writes nothing away.

    De tegenproef bij het geval met de thuiskomer: daar viel er wél iets te
    bewaren. Hier alleen een sensorwijziging, en dan hoort de flush geen
    schrijfactie te plannen - elke herstart zou anders het bestand opnieuw
    schrijven zonder dat er iets veranderde.
    """

    async def test_the_flush_plans_no_write(self, monkeypatch) -> None:
        home = await start_house(
            installation(),
            core_state=CoreState.starting,
            states=cold_world(),
        )
        try:
            scheduled: list[object] = []
            monkeypatch.setattr(
                home.coordinator._store,
                "async_delay_save",
                lambda writer, _delay: scheduled.append(writer),
            )

            home.hass.states.async_set(SENSOR, "18.4", {"unit_of_measurement": "°C"})
            await settle_the_debouncer(home)
            await start_up(home)

            assert scheduled == [], "er is weggeschreven zonder dat er iets te bewaren viel"
        finally:
            await stop_house(home)


class TestAnEntryRemovedDuringTheStartupLeavesNoFile:
    """Een installatie die tijdens het opstarten weer weggaat schrijft niets terug.

    An installation removed again during the startup writes nothing back.

    De poort staat nog dicht, dus het herstel draait nooit; de afbraakpoort
    (`_closing`) houdt de schrijfactie tegen, ook de uitgestelde. Zou die er toch
    komen, dan schrijft hij het bestand terug ná `async_remove_entry`.
    """

    async def test_no_state_file_is_left_behind(self) -> None:
        config_dir = new_config_dir()
        today = dt_util.now().date().isoformat()
        write_store(config_dir, {"handed_back": {"woonkamer": today}})

        home = await start_house(
            two_rooms(),
            config_dir=config_dir,
            core_state=CoreState.starting,
            states=two_room_world(attic="heat"),
        )
        try:
            home.hass.states.async_set(ATTIC, "off", dict(MODES))
            await settle_the_debouncer(home)

            await home.hass.config_entries.async_remove(home.entry.entry_id)
            await home.hass.async_block_till_done()
            await asyncio.sleep(1.5)
            await home.hass.async_block_till_done()

            assert not os.path.exists(store_path(config_dir)), (
                "een uitgestelde schrijfactie heeft het bestand teruggezet"
            )
        finally:
            await stop_house(home)


class TestABrokenRestoreStillWritesWhatWasNoted:
    """Ook na een kapotte lezing gaat wat tijdens het opstarten bleef liggen de deur uit.

    Even after a broken reading, what stayed behind during the startup goes out.

    Vóór het herstel schrijft `_async_save_state` niets; het onthoudt alleen dát er
    iets te bewaren viel. Valt het herstel zelf om, dan komt de schrijfstap in het
    `try`-blok nooit langs, en dan hoort de `finally` het alsnog weg te schrijven - ná
    de poort, anders blijft het weer liggen. Zonder die stap stond een thuiskomst van
    tijdens het opstarten alleen in het geheugen, tot er toevallig weer iets bewaard
    werd.

    Before the restore `_async_save_state` writes nothing; it only remembers *that*
    something needed saving. When the restore itself falls over, the write step in the
    `try` block never comes by, and then the `finally` should write it away all the
    same - after the gate, or it stays behind again. Without that step a homecoming
    from during the startup stood in memory only, until something happened to be saved
    again.
    """

    async def test_the_homecoming_reaches_the_store(self, monkeypatch) -> None:
        config_dir = new_config_dir()
        home = await start_house(
            two_rooms(),
            config_dir=config_dir,
            core_state=CoreState.starting,
            states=two_room_world(person="not_home"),
        )
        try:

            async def broken_restore() -> None:
                raise RuntimeError("kapotte opslag")

            monkeypatch.setattr(home.coordinator, "_async_restore_state", broken_restore)
            home.hass.states.async_set(PERSON, "home", {})
            await settle_the_debouncer(home)
            assert not os.path.exists(store_path(config_dir)), (
                "er is vóór het herstel in de opslag geschreven"
            )

            await start_up(home)

            assert os.path.exists(store_path(config_dir)), (
                "wat tijdens het opstarten bleef liggen is nooit weggeschreven"
            )
            assert "danny" in read_store(config_dir)["home_since"]
        finally:
            await stop_house(home)
