"""De beslismelding die de blueprint standaard toont.

Het event `climate_director_decision` draagt sinds T6-8 vier velden waarmee een
automatisering zonder sjablonen een leesbare melding kan maken: `reason_text`,
`action_text`, `source_name` en `message`. Dit bestand bewaakt twee dingen:
dat de zinnen in alle zeven bestanden staan en nergens jargon of een identifier
bevatten (de statische helft), en dat een echt draaiend huis die zin ook
werkelijk zo opbouwt (de live helft).

De identifiers blijven het contract: `reason` is en blijft de stabiele waarde om
op te filteren. Wie dat doet merkt van dit alles niets.

The decision message the blueprint shows by default.

Since T6-8 the `climate_director_decision` event carries four fields that let an
automation build a readable message without templates: `reason_text`,
`action_text`, `source_name` and `message`. This file guards two things: that the
sentences exist in all seven files and never contain jargon or an identifier
(the static half), and that a really running house builds that sentence exactly
so (the live half).

The identifiers stay the contract: `reason` is and remains the stable value to
filter on. Whoever does that notices nothing of any of this.
"""

from __future__ import annotations

import json
import pathlib
import re
from datetime import timedelta
from typing import Any

import pytest
from harness_live import settings, source, start_house, stop_house, zone
from homeassistant.util import dt as dt_util

from custom_components.climate_director.engine import Reason

ROOT = pathlib.Path(__file__).resolve().parents[1]
TRANSLATIONS = ROOT / "custom_components" / "climate_director" / "translations"

#: De zes vertaalbestanden plus het Engels dat `strings.json` zelf draagt.
LANGUAGES = ("nl", "en", "de", "fr", "es", "ar")

REASONS = tuple(item.value for item in Reason)

ACTIONS = ("heat", "cool", "off", "left_alone", "stays_off")

SHAPES = ("plain", "target", "appliance", "appliance_target")

#: Woorden die een gebruiker niet kent en die dus niet in zijn melding horen.
#:
#: De lijst staat hier letterlijk per taal, en niet afgeleid uit de code: een
#: bewaking die zijn eigen woordenlijst uit de te bewaken bestanden haalt,
#: keurt alles goed. `circuit` en `hysterese` zijn de vaktaal van de engine;
#: `entiteit`/`entity` en `familie`/`family` zijn de interne begrippen; een
#: `_`-woord of een `domein.object`-vorm verraadt een identifier, en dat is wat
#: `AGENTS.md` verbiedt in tekst die een gebruiker leest.
#:
#: Words a user does not know and that therefore do not belong in their
#: message. The list stands here literally per language rather than being
#: derived from the code: a guard that takes its own word list from the files it
#: guards approves of everything. `circuit` and `hysterese` are the engine's
#: jargon; `entiteit`/`entity` and `familie`/`family` are the internal notions; a
#: `_` word or a `domain.object` shape betrays an identifier, and that is what
#: `AGENTS.md` forbids in text a user reads.
JARGON: dict[str, tuple[str, ...]] = {
    "nl": (
        "circuit",
        "dode band",
        "hysterese",
        "familie",
        "deferral",
        "uitsluitende groep",
        "entiteit",
    ),
    "en": (
        "circuit",
        "dead band",
        "deadband",
        "hysteresis",
        "family",
        "deferral",
        "exclusive group",
        "entity",
    ),
    "de": ("kreis", "totband", "hysterese", "familie", "aufschub", "exklusive gruppe", "entität"),
    "fr": (
        "circuit",
        "bande morte",
        "hystérésis",
        "famille",
        "report",
        "groupe exclusif",
        "entité",
    ),
    "es": (
        "circuito",
        "banda muerta",
        "histéresis",
        "familia",
        "aplazamiento",
        "grupo exclusivo",
        "entidad",
    ),
    "ar": ("دائرة", "نطاق ميت", "تباطؤ", "عائلة", "تأجيل", "مجموعة حصرية", "كيان"),
}


def _entity(language: str) -> dict[str, Any]:
    return json.loads((TRANSLATIONS / f"{language}.json").read_text(encoding="utf-8"))["entity"]


def reason_sentences(language: str) -> dict[str, str]:
    """Return every reason's sentence in one language."""
    return _entity(language)["sensor"]["zone_source"]["state_attributes"]["reason"]["state"]


def action_sentences(language: str) -> dict[str, str]:
    """Return every action's words in one language."""
    return _entity(language)["sensor"]["would_command"]["state_attributes"]["action"]["state"]


def message_templates(language: str) -> dict[str, str]:
    """Return the four message shapes in one language."""
    return _entity(language)["sensor"]["zone_source"]["state_attributes"]["message"]["state"]


def _identified(sentence: str) -> bool:
    """Return whether a sentence carries an identifier rather than a word."""
    return "_" in sentence or re.search(r"[a-z]\.[a-z]", sentence) is not None


@pytest.mark.parametrize("language", LANGUAGES)
class TestEveryLanguageCarriesTheSameSet:
    def test_every_reason_has_a_sentence(self, language: str) -> None:
        assert set(reason_sentences(language)) == set(REASONS)

    def test_every_action_has_words(self, language: str) -> None:
        assert set(action_sentences(language)) == set(ACTIONS)

    def test_every_message_shape_exists(self, language: str) -> None:
        assert set(message_templates(language)) == set(SHAPES)


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("reason", REASONS)
def test_the_reason_is_a_sentence_without_identifiers_or_jargon(language: str, reason: str) -> None:
    """Eén gewone zin per reden, in de woorden van dat scherm.

    De zin moet waar zijn voor elk geval waarin die reden valt, dus hij noemt
    het ding dat de gebruiker ziet (het raam, de buitentemperatuur, wie thuis
    is) en niet de toestandsvariabele erachter. Daarom staat de verboden
    woordenlijst hierboven per taal letterlijk in de test: een zin met
    `circuit_conflict_lost` erin als tekst zou anders stil goedgekeurd worden.

    One ordinary sentence per reason, in the words of that screen. The sentence
    has to be true for every case that reason falls in, so it names the thing
    the user sees (the window, the outdoor temperature, who is home) and not the
    state variable behind it. That is why the forbidden word list above stands
    literally in the test per language: a sentence with `circuit_conflict_lost`
    in it as text would otherwise be silently approved of.
    """
    sentence = reason_sentences(language)[reason]
    assert sentence, f"{language}/{reason} heeft geen zin"
    assert sentence == sentence.strip(), f"{language}/{reason} heeft witruimte"
    assert not _identified(sentence), f"{language}/{reason} draagt een identifier: {sentence}"
    lowered = sentence.lower()
    for word in JARGON[language]:
        assert word not in lowered, f"{language}/{reason} gebruikt jargon ({word}): {sentence}"


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_action_words_carry_no_identifiers(language: str) -> None:
    for action, words in action_sentences(language).items():
        assert words and words == words.strip(), f"{language}/{action}: {words!r}"
        assert not _identified(words), f"{language}/{action}: {words!r}"
        lowered = words.lower()
        for word in JARGON[language]:
            assert word not in lowered, f"{language}/{action} gebruikt jargon ({word}): {words}"


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_templates_ask_for_the_three_pieces(language: str) -> None:
    """Elk sjabloon vult de kamer, de actie en de reden zelf in.

    Een sjabloon zonder `{reason}` zou de reden weglaten, en een sjabloon met
    een identifier erin zou precies terugbrengen wat deze ronde weghaalt.

    Every template fills in the room, the action and the reason itself. A
    template without `{reason}` would drop the reason, and one holding an
    identifier would bring back exactly what this round removes.
    """
    for shape, template in message_templates(language).items():
        assert "{zone}" in template, f"{language}/{shape}: {template}"
        assert "{action}" in template, f"{language}/{shape}: {template}"
        assert "{reason}" in template, f"{language}/{shape}: {template}"
        assert not _identified(template), f"{language}/{shape}: {template}"
        assert "{" in template and template.count("{") == template.count("}"), template


def test_the_three_examples_are_exactly_this() -> None:
    """De drie meldingen zoals de blueprint ze toont, in het Nederlands.

    Deze drie staan letterlijk in het afrondingsbericht van deze ronde, dus ze
    worden hier vastgelegd in plaats van overgetypt uit een scherm. Het
    setpoint verschijnt als `23.0 °C` en niet als `23 °C`: dat is de bestaande
    weergave van de integratie, met één decimaal, zodat elke plek waar een
    gebruiker een temperatuur leest hetzelfde getal toont.

    The three messages as the blueprint shows them, in Dutch. They stand
    literally in this round's closing report, so they are pinned down here
    rather than copied off a screen. The setpoint shows as `23.0 °C` and not as
    `23 °C`: that is the integration's existing display, with one decimal, so
    every place a user reads a temperature shows the same number.
    """
    reasons = reason_sentences("nl")
    actions = action_sentences("nl")
    templates = message_templates("nl")

    def render(shape: str, **pieces: str) -> str:
        return templates[shape].format(
            zone=pieces["zone"],
            action=pieces["action"],
            reason=pieces["reason"],
            source=pieces.get("source", ""),
            target=pieces.get("target", ""),
        )

    assert (
        render(
            "appliance_target",
            zone="Woonkamer",
            action=actions["heat"],
            reason=reasons["regulating"],
            source="Cv-ketel",
            target="23.0 °C",
        )
        == "Woonkamer: gaat verwarmen met Cv-ketel op 23.0 °C — de kamer vraagt erom."
    )
    assert (
        render(
            "plain",
            zone="Zolder",
            action=actions["stays_off"],
            reason=reasons["circuit_conflict_lost"],
        )
        == "Zolder: blijft uit — de buitenunit doet al het tegenovergestelde voor een andere kamer."
    )
    assert (
        render(
            "plain",
            zone="Slaapkamer",
            action=actions["left_alone"],
            reason=reasons["manual_override"],
        )
        == "Slaapkamer: wordt met rust gelaten — deze kamer is aan jou overgedragen."
    )


# -- de live helft / the live half -------------------------------------------

LIVING = "climate.woonkamer"
PERSON = "person.danny"
DOOR = "binary_sensor.achterdeur"


def installation(
    *, quiet_window: dict[str, Any] | None = None, heat_target: float = 21.0
) -> dict[str, Any]:
    """Return a cold single-zone house with a named boiler and one resident."""
    found: dict[str, Any] = {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("woonkamer_ketel", LIVING, name="Cv-ketel")],
                heat=settings(heat_target, 20.0),
            )
        ],
        "outdoor_sensor": "sensor.buiten",
        "residents": [
            {
                "resident_id": "danny",
                "name": "Danny",
                "presence_entity": PERSON,
                "sleep_entity": "sensor.danny_lader",
                "sleep_state": "wireless",
            }
        ],
        "openings": [{"entity_id": DOOR, "delay": 0}],
    }
    if quiet_window is not None:
        found["gates"] = {"quiet_windows": [quiet_window]}
    return found


def world(
    *, indoor: str = "18.0", home: bool = True, door: str = "off"
) -> dict[str, tuple[str, dict[str, Any]]]:
    """Return a world in which the living room wants heat."""
    return {
        "sensor.woonkamer": (indoor, {}),
        "sensor.buiten": ("4.0", {}),
        LIVING: ("off", {"temperature": 19.0}),
        PERSON: ("home" if home else "not_home", {}),
        "sensor.danny_lader": ("none", {}),
        DOOR: (door, {}),
    }


def quiet_window_minutes(minutes: int = 60) -> dict[str, Any]:
    """Return a quiet window around the current clock."""
    now = dt_util.now()
    return {
        "start": (now - timedelta(minutes=minutes // 2)).strftime("%H:%M:%S"),
        "end": (now + timedelta(minutes=minutes // 2)).strftime("%H:%M:%S"),
        "weekdays": None,
        "holiday": False,
    }


def _plain_message(event: dict[str, Any]) -> str:
    """Return the sentence the plain shape should give for this event.

    De kale vorm is `<kamer>: <actie> — <reden>.`; deze helper bouwt hem uit het
    Engelse sjabloon en de stukken die het event zelf meedraagt, zodat een test
    kan eisen dat er géén apparaat in de zin staat zonder de woorden over te
    typen.

    The bare shape is `<room>: <action> — <reason>.`; this helper builds it from
    the English template and the pieces the event itself carries, so a test can
    demand that no appliance stands in the sentence without retyping the words.
    """
    return message_templates("en")["plain"].format(
        zone=event["zone_name"],
        action=event["action_text"],
        reason=event["reason_text"],
        source="",
        target="",
    )


def assert_readable(event: dict[str, Any], reason: str) -> None:
    """Demand that one event carries a message a stranger can read.

    De melding moet de kamer, de actie en de reden als gewone zin dragen, en
    geen enkele identifier: geen bron-id, geen entiteits-id, geen redencode en
    geen `_`-woord. Wie op `reason` filtert blijft dat gewoon kunnen.

    The message must carry the room, the action and the reason as an ordinary
    sentence, and no identifier at all: no source id, no entity id, no reason
    code and no `_` word. Whoever filters on `reason` can still do just that.
    """
    message = event["message"]
    assert event["reason"] == reason, event["reason"]
    assert event["reason_text"], "geen reason_text"
    assert event["action_text"], "geen action_text"
    assert message.startswith(event["zone_name"]), message
    assert event["action_text"] in message, message
    assert message.endswith(event["reason_text"] + "."), message
    assert reason not in message, message
    if event["source_id"]:
        assert event["source_id"] not in message, message
    if event["entity_id"]:
        assert event["entity_id"] not in message, message
    assert "_" not in message, message
    for word in JARGON["en"]:
        assert word not in message.lower(), (word, message)


class TestWhatALiveHouseShows:
    """Eén reden per test, op een huis dat echt draait.

    Per reden die dit harnas kan bereiken wordt het event opgevangen en de
    melding nagelopen. De redenen staan hier bij naam, zodat een hernoemde of
    verdwenen reden meteen opvalt in plaats van stil uit de lijst te vallen.

    One reason per test, on a house that really runs. For every reason this
    harness can reach, the event is caught and the message checked. The reasons
    are named here, so a renamed or vanished reason stands out immediately
    instead of quietly dropping out of the list.
    """

    async def _event(self, live) -> dict[str, Any]:
        await live.evaluate()
        events = live.fired("climate_director_decision")
        assert events, "geen decision-event gevuurd"
        return events[-1]

    async def test_a_room_that_asks_for_heat(self) -> None:
        """Met apparaat en setpoint: de vorm van het eerste voorbeeld."""
        live = await start_house(installation(), states=world(), appliance="obedient")
        try:
            event = await self._event(live)
            assert_readable(event, "regulating")
            assert "Cv-ketel" in event["message"], event["message"]
            assert "°C" in event["message"], event["message"]
            assert event["source_name"] == "Cv-ketel"
        finally:
            await stop_house(live)

    async def test_a_room_that_is_already_at_temperature(self) -> None:
        """Zonder apparaat: de vorm van het tweede voorbeeld.

        Het apparaat stond al uit en blijft uit, dus de zin noemt het niet en
        zegt "blijft uit" - niet "gaat uit", want er verandert niets.

        No appliance: the shape of the second example. The appliance already
        stood off and stays off, so the sentence does not name it and says
        "stays off" - not "goes off", since nothing changes.
        """
        live = await start_house(installation(), states=world(indoor="21.5"), appliance="obedient")
        try:
            event = await self._event(live)
            assert_readable(event, "satisfied")
            assert event["action_text"] == action_sentences("en")["stays_off"], event["action_text"]
            assert event["source_name"] is None, event["source_name"]
            assert event["message"] == _plain_message(event), event["message"]
        finally:
            await stop_house(live)

    async def test_a_room_with_an_open_door(self) -> None:
        live = await start_house(installation(), states=world(door="on"), appliance="obedient")
        try:
            assert_readable(await self._event(live), "opening_open")
        finally:
            await stop_house(live)

    async def test_a_house_with_nobody_home(self) -> None:
        live = await start_house(installation(), states=world(home=False), appliance="obedient")
        try:
            assert_readable(await self._event(live), "nobody_home")
        finally:
            await stop_house(live)

    async def test_a_running_appliance_is_switched_off(self) -> None:
        """ "Gaat uit" en "blijft uit" zijn niet hetzelfde.

        Een apparaat dat werkelijk draait en door een leeg huis wordt
        stopgezet, levert "gaat uit": de lezer ziet iets stoppen. Dezelfde
        reden op een apparaat dat al uit stond levert "blijft uit". Zonder dat
        onderscheid zou de melding zwijgen over een apparaat dat stopt.

        "Goes off" and "stays off" are not the same. An appliance that really
        runs and is stopped by an empty house yields "goes off": the reader
        watches something stop. The same reason on an appliance that already
        stood off yields "stays off". Without that distinction the message would
        stay silent about an appliance that stops.
        """
        running = world(home=False)
        running[LIVING] = ("heat", {"temperature": 19.0})
        live = await start_house(installation(), states=running, appliance="obedient")
        try:
            event = await self._event(live)
            assert_readable(event, "nobody_home")
            assert event["action_text"] == action_sentences("en")["off"], event["action_text"]
            assert event["message"] == _plain_message(event), event["message"]
        finally:
            await stop_house(live)

    async def test_a_house_in_the_quiet_window(self) -> None:
        live = await start_house(
            installation(quiet_window=quiet_window_minutes()),
            states=world(),
            appliance="obedient",
        )
        try:
            assert_readable(await self._event(live), "quiet_hours")
        finally:
            await stop_house(live)

    async def test_a_room_handed_over_to_you(self) -> None:
        """Zonder apparaat: de vorm van het derde voorbeeld."""
        live = await start_house(installation(), states=world(), appliance="obedient")
        try:
            live.coordinator.zone_overrides["woonkamer"] = True
            event = await self._event(live)
            assert_readable(event, "manual_override")
            assert event["action_text"] == action_sentences("en")["left_alone"], event[
                "action_text"
            ]
            assert event["source_name"] is None, event["source_name"]
            assert event["message"] == _plain_message(event), event["message"]
        finally:
            await stop_house(live)

    async def test_a_house_with_the_master_switch_off(self) -> None:
        live = await start_house(installation(), states=world(), appliance="obedient")
        try:
            live.coordinator.master_enabled = False
            assert_readable(await self._event(live), "master_disabled")
        finally:
            await stop_house(live)


class TestTheDutchExamplesOnALiveHouse:
    """De drie voorbeeldmeldingen, letterlijk uit een huis dat echt draait.

    De taal van de interface is hier Nederlands, dus wat het event meedraagt is
    precies de zin die een Nederlandse gebruiker op zijn telefoon leest. Deze
    drie staan letterlijk in het afrondingsbericht van deze ronde; ze worden hier
    uit een draaiend huis gehaald in plaats van uit een sjabloon nagerekend.

    The three example messages, literally from a house that really runs. The
    interface language is Dutch here, so what the event carries is exactly the
    sentence a Dutch user reads on their phone. These three stand literally in
    this round's closing report; they are taken from a running house here rather
    than recomputed from a template.
    """

    async def _event(self, live) -> dict[str, Any]:
        await live.evaluate()
        events = live.fired("climate_director_decision")
        assert events, "geen decision-event gevuurd"
        return events[-1]

    async def test_heat_names_the_appliance_and_the_setpoint(self) -> None:
        live = await start_house(
            installation(heat_target=23.0),
            states=world(),
            appliance="obedient",
            language="nl",
        )
        try:
            event = await self._event(live)
            assert event["reason"] == "regulating", event["reason"]
            assert (
                event["message"]
                == "Woonkamer: gaat verwarmen met Cv-ketel op 23.0 °C — de kamer vraagt erom."
            ), event["message"]
        finally:
            await stop_house(live)

    async def test_a_room_at_temperature_stays_off_without_an_appliance(self) -> None:
        live = await start_house(
            installation(), states=world(indoor="21.5"), appliance="obedient", language="nl"
        )
        try:
            event = await self._event(live)
            assert event["reason"] == "satisfied", event["reason"]
            assert event["message"] == "Woonkamer: blijft uit — de kamer is op temperatuur.", event[
                "message"
            ]
        finally:
            await stop_house(live)

    async def test_a_handed_over_room_is_left_alone(self) -> None:
        live = await start_house(
            installation(), states=world(), appliance="obedient", language="nl"
        )
        try:
            live.coordinator.zone_overrides["woonkamer"] = True
            event = await self._event(live)
            assert event["reason"] == "manual_override", event["reason"]
            assert (
                event["message"]
                == "Woonkamer: wordt met rust gelaten — deze kamer is aan jou overgedragen."
            ), event["message"]
        finally:
            await stop_house(live)
