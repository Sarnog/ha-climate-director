"""De beslismelding die de blueprint standaard toont.

Het event `climate_director_decision` draagt vier velden waarmee een
automatisering zonder sjablonen een leesbare melding kan maken: `reason_text`,
`action_text`, `source_name` en `message`. Dit bestand bewaakt twee dingen:
dat de zinnen in alle zeven bestanden staan en nergens jargon of een identifier
bevatten (de statische helft), en dat een echt draaiend huis die zin ook
werkelijk zo opbouwt (de live helft).

De identifiers blijven het contract: `reason` is en blijft de stabiele waarde om
op te filteren. Wie dat doet merkt van dit alles niets.

The decision message the blueprint shows by default.

The `climate_director_decision` event carries four fields that let an
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
GUIDES = ROOT / "docs" / "install"

#: De zes vertaalbestanden plus het Engels dat `strings.json` zelf draagt.
LANGUAGES = ("nl", "en", "de", "fr", "es", "ar")

#: De stukken van het voorbeeld dat elke gids toont, in de woorden van die gids.
GUIDE_EXAMPLES: dict[str, tuple[str, str]] = {
    "nl": ("Woonkamer", "Cv-ketel"),
    "en": ("Living room", "Boiler"),
    "de": ("Wohnzimmer", "Heizkessel"),
    "fr": ("Salon", "Chaudière"),
    "es": ("Salón", "Caldera"),
    "ar": ("غرفة المعيشة", "الغلاية"),
}

REASONS = tuple(item.value for item in Reason)

ACTIONS = ("heat", "cool", "off", "left_alone", "stays_off")

CONNECTORS = ("after_zone", "before_appliance", "before_target")

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


def connectors(language: str) -> dict[str, str]:
    """Return the two connecting words in one language."""
    return _entity(language)["sensor"]["zone_source"]["state_attributes"]["message"]["state"]


def render(
    language: str,
    *,
    zone: str,
    action: str,
    reason: str,
    source: str | None = None,
    target: str | None = None,
) -> str:
    """Build the sentence exactly as `texts.decision_message` builds it.

    Dezelfde opbouw als in de integratie: kamer, actie, dan het apparaat en het
    setpoint met hun verbindingswoord, en de reden achter het streepje. Deze
    helper staat hier zodat een test de zin kan nabouwen zonder de tekst over te
    typen.

    The same composition as in the integration: room, action, then the appliance
    and the setpoint with their connecting word, and the reason after the dash.
    This helper stands here so a test can rebuild the sentence without retyping
    the text.
    """
    words = connectors(language)
    parts = [f"{zone}{words['after_zone']} {action}"]
    if source:
        parts.append(f"{words['before_appliance']} {source}")
    if target:
        parts.append(f"{words['before_target']} {target}")
    return f"{' '.join(parts)} — {reason}."


def _identified(sentence: str) -> bool:
    """Return whether a sentence carries an identifier rather than a word."""
    return "_" in sentence or re.search(r"[a-z]\.[a-z]", sentence) is not None


@pytest.mark.parametrize("language", LANGUAGES)
class TestEveryLanguageCarriesTheSameSet:
    def test_every_reason_has_a_sentence(self, language: str) -> None:
        assert set(reason_sentences(language)) == set(REASONS)

    def test_every_action_has_words(self, language: str) -> None:
        assert set(action_sentences(language)) == set(ACTIONS)

    def test_every_connecting_word_exists(self, language: str) -> None:
        assert set(connectors(language)) == set(CONNECTORS)


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


#: Werkwoorden die een richting kiezen - verwarmen of koelen. De redenzin
#: `opening_open_elsewhere` geldt zowel voor een verwarmend als voor een koelend
#: huisbreed apparaat, en in die tak noemt de directeur geen apparaat; de zin mag
#: dus geen van beide richtingen uitspreken. Per taal letterlijk, met stam, want
#: er is geen runtime-object dat "richting" meet.
#:
#: Verbs that pick a direction - heating or cooling. The reason sentence
#: `opening_open_elsewhere` holds for a heating as well as for a cooling
#: house-wide appliance, and in that branch the director names no appliance; the
#: sentence may therefore not speak either direction. Literal per language, as a
#: stem, because no runtime object measures "direction".
DIRECTION_WORDS: dict[str, tuple[str, ...]] = {
    "nl": ("verwarm", "koel"),
    "en": ("heat", "cool"),
    "de": ("heiz", "kühl"),
    "fr": ("chauff", "refroid"),
    "es": ("calient", "enfrí"),
    "ar": ("يدفّئ", "يبرّد"),
}


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_elsewhere_sentence_names_no_direction(language: str) -> None:
    """De huisbrede-openingszin kiest geen richting.

    `opening_open_elsewhere` valt ook wanneer het huisbrede apparaat koelt: de
    directeur noemt het apparaat in die tak niet, dus een werkwoord dat
    verwarmen of koelen zegt liegt tegen de helft van de gevallen. Daarom draagt
    de zin geen van beide richtingen.

    The elsewhere sentence names no direction. `opening_open_elsewhere` also
    falls when the house-wide appliance cools: the director names no appliance in
    that branch, so a verb that says heating or cooling lies to half the cases.
    The sentence therefore carries neither direction.
    """
    sentence = reason_sentences(language)["opening_open_elsewhere"].lower()
    for word in DIRECTION_WORDS[language]:
        assert word not in sentence, f"{language}: {sentence}"


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_action_words_carry_no_identifiers(language: str) -> None:
    for action, words in action_sentences(language).items():
        assert words and words == words.strip(), f"{language}/{action}: {words!r}"
        assert not _identified(words), f"{language}/{action}: {words!r}"
        lowered = words.lower()
        for word in JARGON[language]:
            assert word not in lowered, f"{language}/{action} gebruikt jargon ({word}): {words}"


#: Waaraan een actiewoord zijn geslacht verraadt, per taal. De kamernaam die de
#: gebruiker zelf koos is het onderwerp van de zin en de integratie kent zijn
#: geslacht niet, dus het actiewoord moet onveranderlijk zijn. Alleen de talen
#: die hier buigen hebben een regel; het Nederlands, Engels en Duits laten het
#: werkwoord in deze vorm ongemoeid.
#:
#: Wat deze toets dekt: de uitgangen waarmee een voltooid deelwoord in het Frans
#: (-é/-i/-u met hun geslachts- en meervoudsuitgangen) en het Spaans (-ado/-ido)
#: meebuigt, plus de onregelmatige familie van *éteindre* bij naam, en in het
#: Arabisch het mannelijke werkwoordsvoorvoegsel ي/س. Wat zij bewust niet dekt:
#: andere onregelmatige Franse deelwoorden (*mis*, *ouvert*, *épris*),
#: bijvoeglijke naamwoorden van de -eux/-ive-familie, en een Arabische vorm die
#: verbogen is zonder met ي of س te beginnen.
#:
#: What an action word betrays about gender, per language. The room name the
#: user chose is the subject of the sentence and the integration does not know
#: its gender, so the action word has to be invariable. Only the languages that
#: bend here carry a rule; Dutch, English and German leave the verb alone in
#: this form.
#:
#: What this guard covers: the endings a past participle bends with in French
#: (-é/-i/-u with their gender and plural endings) and Spanish (-ado/-ido), plus
#: the irregular *éteindre* family by name, and in Arabic the masculine verb
#: prefix ي/س. What it deliberately leaves uncovered: other irregular French
#: participles (*mis*, *ouvert*, *épris*), adjectives of the -eux/-ive family,
#: and an Arabic form that bends without starting with ي or س.
AGREEMENT_ENDINGS: dict[str, tuple[str, ...]] = {
    "nl": (),
    "en": (),
    "de": (),
    "fr": ("é", "ée", "és", "ées", "i", "ie", "is", "ies", "u", "ue", "us", "ues"),
    "es": ("ado", "ada", "ados", "adas", "ido", "ida", "idos", "idas"),
    "ar": (),
}

#: Onregelmatige deelwoorden die geen uitgang uit `AGREEMENT_ENDINGS` dragen maar
#: evengoed meebuigen. Alleen de familie die deze integratie zelf gebruikte staat
#: er; de rest is een leesfout, geen meetfout.
#:
#: Irregular participles that carry none of the endings in `AGREEMENT_ENDINGS`
#: but bend all the same. Only the family this integration used itself is here;
#: the rest is a reading matter, not a measuring matter.
IRREGULAR_PARTICIPLES: dict[str, tuple[str, ...]] = {
    "fr": ("éteint", "éteinte", "éteints", "éteintes"),
}

#: Het mannelijke werkwoordsvoorvoegsel in het Arabisch; de vrouwelijke vorm
#: begint met ت/ست en is dus niet verboden.
#:
#: The masculine verb prefix in Arabic; the feminine form starts with ت/ست and is
#: therefore not forbidden.
MALE_VERB_PREFIXES: dict[str, tuple[str, ...]] = {
    "ar": ("ي", "س"),
}

#: Witruimte en leestekens die aan een woord kunnen kleven.
#:
#: Whitespace and punctuation that can stick to a word.
_TRIM = ".,;:!?«»\"'()[]—–"


def _action_word_tokens(words: str) -> list[str]:
    """Return the action words without surrounding punctuation."""
    return [token for token in (part.strip(_TRIM) for part in words.split()) if token]


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_action_word_does_not_bend_with_the_room(language: str) -> None:
    """Het actiewoord is onveranderlijk, want de kamernaam is het onderwerp.

    `texts.decision_message` bouwt `f"{zone}{after_zone} {action}"`, dus de
    kamernaam die de gebruiker zelf koos is het onderwerp van de zin. Die naam
    kan van alles zijn en de integratie kent zijn geslacht niet; een actiewoord
    dat daarmee meebuigt, zegt dus in de helft van de gevallen het verkeerde.
    Daarom mag geen enkel actiewoord een verbogen voltooid deelwoord dragen en
    in het Arabisch geen mannelijk werkwoordsvoorvoegsel. De dekking en de
    bewust ongedekte randen staan bij de lijsten hierboven.

    The action word is invariable, because the room name is the subject.
    `texts.decision_message` builds `f"{zone}{after_zone} {action}"`, so the room
    name the user chose is the subject of the sentence. That name can be
    anything and the integration does not know its gender; an action word that
    bends with it therefore says the wrong thing half the time. So no action
    word may carry a bent past participle and, in Arabic, no masculine verb
    prefix. The coverage and the deliberately uncovered edges stand with the
    lists above.
    """
    for action, words in action_sentences(language).items():
        for token in _action_word_tokens(words):
            lowered = token.lower()
            assert not lowered.endswith(AGREEMENT_ENDINGS[language]), (
                f"{language}/{action} buigt mee met de kamernaam: {words!r}"
            )
            assert lowered not in IRREGULAR_PARTICIPLES.get(language, ()), (
                f"{language}/{action} buigt mee met de kamernaam: {words!r}"
            )
            for prefix in MALE_VERB_PREFIXES.get(language, ()):
                assert not token.startswith(prefix), (
                    f"{language}/{action} buigt mee met de kamernaam: {words!r}"
                )


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_connecting_words_are_words_and_not_templates(language: str) -> None:
    """De verbindingswoorden zijn woorden: geen placeholder, geen id.

    Hassfest weigert een plaatsaanduiding in een vertaalwaarde, en dat is de
    reden dat de zin hier opgebouwd wordt en niet in het tekstbestand staat.
    Deze test houdt die grens vast: een woord van een paar letters, zonder
    accolade erin en zonder identifier. Het scheidingsteken tussen kamer en
    actie mag de spatie dragen die de taal daar wil - het Frans zet er een vóór
    de dubbele punt - dus dat ene woord mag randwitruimte hebben; de andere twee
    zijn kaal.

    The connecting words are words: no placeholder, no id. Hassfest refuses a
    placeholder inside a translation value, and that is why the sentence is
    composed here rather than standing in the text file. This test holds that
    boundary: a word of a few letters, without a brace in it and without an
    identifier. The separator between room and action may carry the space the
    language wants there - French puts one before the colon - so that one word
    may have surrounding whitespace; the other two are bare.
    """
    for which, word in connectors(language).items():
        assert word, f"{language}/{which}: {word!r}"
        assert "{" not in word and "}" not in word, f"{language}/{which}: {word}"
        assert word == word.strip() or which == "after_zone", f"{language}/{which}: {word!r}"
        assert len(word.split()) == 1, f"{language}/{which}: {word}"
        assert not _identified(word), f"{language}/{which}: {word}"
        lowered = word.lower()
        for jargon in JARGON[language]:
            assert jargon not in lowered, f"{language}/{which} gebruikt jargon ({jargon}): {word}"


#: Het zelfstandig naamwoord waarmee het schermlabel van `require_schedule` de
#: bewoner noemt, en het woord waarmee een zone naar zijn eigen kamer verwijst.
#: De redenzin `outside_schedule` hoort het eerste te noemen en het tweede te
#: vermijden: het rooster dat die reden tegenhoudt is het rooster van de
#: bewoners (het scherm onder Stap 10) en niet van de zone (Stap 4), en een zone
#: heeft geen roosterveld - wie de zin leest hoort naar de bewoners te kijken.
#: De vergelijking is hoofdletterongevoelig, want `Bewohner` en `الساكنين` staan
#: met een hoofdletter of een lidwoord in het label en zonder in de zin.
#:
#: The noun with which the screen label of `require_schedule` names the resident,
#: and the word with which a zone refers to its own room. The reason sentence
#: `outside_schedule` has to name the first and avoid the second: the schedule
#: that reason holds back is the residents' schedule (the screen under step 10)
#: and not the zone's (step 4), and a zone has no schedule field at all - whoever
#: reads the sentence has to look at the residents. The comparison is
#: case-insensitive, because `Bewohner` and `الساكنين` carry a capital or an
#: article in the label and stand bare in the sentence.
SCHEDULE_NOUN: dict[str, str] = {
    "nl": "bewoner",
    "en": "resident",
    "de": "bewohner",
    "fr": "occupant",
    "es": "residente",
    "ar": "ساكن",
}

ROOM_NOUN: dict[str, str] = {
    "nl": "kamer",
    "en": "room",
    "de": "raum",
    "fr": "pièce",
    "es": "habitación",
    "ar": "غرفة",
}


def require_schedule_label(language: str) -> str:
    """Return the screen label of the schedule switch in one language."""
    bestand = json.loads((TRANSLATIONS / f"{language}.json").read_text(encoding="utf-8"))
    return bestand["options"]["step"]["settings"]["data"]["require_schedule"]


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_schedule_noun_is_the_one_the_screen_uses(language: str) -> None:
    """De woordenlijst hierboven hangt aan het scherm en niet aan zichzelf.

    Een letterlijke lijst is de enige vorm die werkt voor "welk woord noemt deze
    taal voor een bewoner", maar zo'n lijst veroudert stil. Daarom wordt elk
    woord uit de lijst hier tegen het echte schermlabel gehouden: verandert
    iemand het label, dan valt deze test om en moet de lijst mee - en dus ook de
    zin die de gebruiker leest.

    The word list above hangs on the screen and not on itself. A literal list is
    the only shape that works for "which word does this language use for a
    resident", but such a list ages quietly. That is why every word from the list
    is held against the real screen label here: change the label and this test
    falls over, so the list has to come along - and with it the sentence the user
    reads.
    """
    label = require_schedule_label(language).lower()
    assert SCHEDULE_NOUN[language] in label, f"{language}: {label}"


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_schedule_sentence_names_a_resident_and_not_a_room(language: str) -> None:
    """De redenzin noemt het ding dat op het scherm staat.

    `outside_schedule` betekent "de roosters van de bewoners laten het nu niet
    toe". De oude zin wees naar een rooster van de kamer, en dat bestaat niet:
    `Zone` draagt geen roosterveld en het scherm waar de gebruiker het instelt
    staat bij de bewoners. Wie de zin leest wordt naar het verkeerde scherm
    gestuurd, dus de zin noemt het bewonerswoord van deze taal en niet het
    kamerwoord van deze taal.

    The reason sentence names the thing that stands on the screen.
    `outside_schedule` means "the residents' schedules do not allow it now". The
    old sentence pointed at a room's schedule, and that does not exist: `Zone`
    carries no schedule field and the screen where the user sets it lives under
    the residents. Whoever reads the sentence is sent to the wrong screen, so the
    sentence names this language's resident word and not its room word.
    """
    sentence = reason_sentences(language)["outside_schedule"].lower()
    assert SCHEDULE_NOUN[language] in sentence, f"{language}: {sentence}"
    assert ROOM_NOUN[language] not in sentence, f"{language}: {sentence}"


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
    sentence = lambda **pieces: render("nl", **pieces)  # noqa: E731

    assert (
        sentence(
            zone="Woonkamer",
            action=actions["heat"],
            reason=reasons["regulating"],
            source="Cv-ketel",
            target="23.0 °C",
        )
        == "Woonkamer: gaat verwarmen met Cv-ketel op 23.0 °C — de kamer vraagt erom."
    )
    assert (
        sentence(
            zone="Zolder",
            action=actions["stays_off"],
            reason=reasons["circuit_conflict_lost"],
        )
        == "Zolder: blijft uit — de buitenunit doet al het tegenovergestelde voor een andere kamer."
    )
    assert (
        sentence(
            zone="Slaapkamer",
            action=actions["left_alone"],
            reason=reasons["manual_override"],
        )
        == "Slaapkamer: wordt met rust gelaten — deze kamer is aan jou overgedragen."
    )


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_guide_shows_an_example_the_template_really_gives(language: str) -> None:
    """Het voorbeeld in elke gids is geen losse belofte.

    De zes gidsen tonen elk één melding in hun eigen woorden. Die staat hier
    niet als zes lossen strings die kunnen afdrijven: de test bouwt hem uit het
    sjabloon van die taal en eist dat hij letterlijk in de gids staat. Verandert
    een verbindingswoord, dan valt de gids om en niet pas de gebruiker.

    The example in every guide is not a loose promise. The six guides each show
    one message in their own words. It does not stand here as six loose strings
    that can drift: the test builds it from that language's template and demands
    it stands literally in the guide. Change a connecting word and the guide
    falls over, not the user.
    """
    room, appliance = GUIDE_EXAMPLES[language]
    expected = render(
        language,
        zone=room,
        action=action_sentences(language)["heat"],
        reason=reason_sentences(language)["regulating"],
        source=appliance,
        target="23.0 °C",
    )
    guide = (GUIDES / f"{language}.md").read_text(encoding="utf-8")
    # De gidsen zijn op tachtig kolommen afgebroken, dus de zin loopt daar over
    # twee regels; vergelijken op de woorden in volgorde maakt dat onverschillig
    # zonder de eis los te laten.
    #
    # The guides wrap at eighty columns, so the sentence runs over two lines
    # there; comparing on the words in order makes that indifferent without
    # letting the demand go.
    wrapped = " ".join(expected.split())
    assert f"*{wrapped}*" in " ".join(guide.split()), expected


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_guide_names_the_four_fields_of_the_event(language: str) -> None:
    """Elke gids noemt de vier velden waarmee een automatisering leest.

    Het event `climate_director_decision` draagt vier velden die een
    automatisering zonder sjablonen nodig heeft: `reason_text`, `action_text`,
    `source_name` en `message`. Wie ze niet in de gids zet, laat de lezer zelf
    uitzoeken hoe het event heet en welke velden erin zitten, en dat is precies
    wat een handleiding hoort te zeggen. De vier moeten in één alinea staan - de
    alinea die over de melding gaat - samen met `reason`, want dat blijft het
    filterwoord; een veldnaam die los ergens anders in de gids opduikt telt niet
    mee.

    Every guide names the four fields an automation reads. The
    `climate_director_decision` event carries four fields an automation needs
    without templates: `reason_text`, `action_text`, `source_name` and `message`.
    Whoever leaves them out of the guide makes the reader find out the event's
    name and its fields alone, and that is exactly what a manual should say. The
    four must stand in one paragraph - the one about the message - together with
    `reason`, because that stays the filter word; a field name that turns up
    loose somewhere else does not count.
    """
    guide = (GUIDES / f"{language}.md").read_text(encoding="utf-8")
    fields = ("reason_text", "action_text", "source_name", "message")
    for paragraph in re.split(r"\n\s*\n", guide):
        flat = " ".join(paragraph.split())
        missing = [field for field in fields if f"`{field}`" not in flat]
        if not missing and "`reason`" in flat:
            return
    raise AssertionError(f"{language}: geen alinea met alle vier de velden en `reason`")


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
    return render(
        "en",
        zone=event["zone_name"],
        action=event["action_text"],
        reason=event["reason_text"],
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


class TestTheFrenchExampleOnALiveHouse:
    """Het Frans zet een spatie vóór de dubbele punt, het Nederlands niet.

    De zin wordt door de integratie opgebouwd, dus het scheidingsteken tussen de
    kamer en de actie is een vertaalwaarde geworden in plaats van een vaste
    dubbele punt. Deze test haalt de Franse melding uit een draaiend huis en eist
    die spatie; de Nederlandse voorbeelden hierboven eisen dat hij er niet staat.

    French puts a space before the colon, Dutch does not. The sentence is built by
    the integration, so the separator between the room and the action became a
    translation value instead of a fixed colon. This test takes the French message
    from a running house and demands that space; the Dutch examples above demand
    it is absent.
    """

    async def test_the_french_message_puts_a_space_before_the_colon(self) -> None:
        live = await start_house(
            installation(heat_target=23.0),
            states=world(),
            appliance="obedient",
            language="fr",
        )
        try:
            await live.evaluate()
            events = live.fired("climate_director_decision")
            assert events, "geen decision-event gevuurd"
            message = events[-1]["message"]
            assert "Woonkamer : va chauffer" in message, message
        finally:
            await stop_house(live)
