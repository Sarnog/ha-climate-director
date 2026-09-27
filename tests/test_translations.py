"""Tests voor de vertaalbestanden.

Tests for the translation files.

Home Assistant kiest zelf het bestand dat bij de taal van de gebruiker hoort en
valt terug op Engels voor wat daarin ontbreekt. Die terugval is stil: een
vergeten sleutel levert geen fout op, maar een half Engelse dialoog. Daarom
wordt hier afgedwongen dat elk bestand exact dezelfde sleutels draagt als
`strings.json`.

Home Assistant picks the file matching the user's language itself and falls
back to English for whatever is missing from it. That fallback is silent: a
forgotten key produces no error, just a half-English dialog. Hence the check
here that every file carries exactly the same keys as `strings.json`.

Dekking: de sleutels van de zeven bestanden tegen `strings.json`, de
plaatshouders in elke waarde, de sleutel die binnen één object twee keer staat,
de aanspreekvorm in de Duitse en de Franse gids, en de terminologielijst
`TERMINOLOGY` die één woord per begrip eist. Die lijst dekt **alle zes** talen, met
ruim vijftig naalden; van elke taal leest deze test het hele vertaalbestand én de
hele gids, en voor `en` ook `strings.json`, want dat is de bron die Home Assistant
zelf leest. Niet gedekt: de schermlabels en de
formuliervelden (`tests/test_ui_complete.py`), de sleutels zonder producent
(`tests/test_text_producers.py`), de gidsen van `nl`, `en`, `es` en `ar` op
aanspreekvorm, en de rest van elke gids buiten de terminologienaalden.

Coverage: the keys of the seven files against `strings.json`, the placeholders in
every value, the key standing twice inside one object, the form of address in the
German and French guides, and the `TERMINOLOGY` list demanding one word per
concept. That list covers **all six** languages, with well over fifty needles; for
every language it reads the whole translation file and the whole guide, and for
`en` also `strings.json`, because that is the source Home Assistant itself reads.
Not covered: the screen labels and form fields
(`tests/test_ui_complete.py`), the keys without a producer
(`tests/test_text_producers.py`), the guides of `nl`, `en`, `es` and `ar` for
their form of address, and the rest of each guide outside the terminology
needles.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

COMPONENT = Path(__file__).parent.parent / "custom_components" / "climate_director"
STRINGS = COMPONENT / "strings.json"
TRANSLATIONS = COMPONENT / "translations"

#: Wordt door Home Assistant zelf ingevuld; verdwijnt er een uit een vertaling,
#: dan staat er straks een lege plek in de zin.
#:
#: Filled in by Home Assistant itself; drop one from a translation and the
#: sentence ends up with a hole in it.
PLACEHOLDER = re.compile(r"\{[a-z_]+\}")


def load(path: Path) -> dict:
    """Return one translation file as a dict."""
    return json.loads(path.read_text(encoding="utf-8"))


def leaves(node: object, path: str = "") -> dict[str, str]:
    """Return every text in the file, keyed by its dotted path."""
    if not isinstance(node, dict):
        return {path: str(node)}
    found: dict[str, str] = {}
    for key, value in node.items():
        found |= leaves(value, f"{path}.{key}" if path else key)
    return found


def language_files() -> list[Path]:
    """Return every shipped translation."""
    return sorted(TRANSLATIONS.glob("*.json"))


def test_the_languages_we_promise_are_all_shipped() -> None:
    """English is required as Home Assistant's fallback, on top of the rest."""
    shipped = {path.stem for path in language_files()}
    assert {"en", "nl", "de", "fr", "es", "ar"} <= shipped


class _Object(list):
    """Een JSON-object, bewaard als zijn sleutel-waardeparen.

    `json` roept de `object_pairs_hook` voor elk object aan met de paren in
    bestandsorde. Door die paren te bewaren in plaats van er een dict van te
    maken blijft een sleutel die twee keer voorkomt zichtbaar; een gewone dict
    laat stil de laatste winnen.

    A JSON object, kept as its key-value pairs. `json` calls the
    `object_pairs_hook` for every object with the pairs in file order. Keeping
    those pairs instead of turning them into a dict leaves a key that stands
    twice visible; a plain dict quietly lets the last one win.
    """


def duplicate_key_paths(node: object, path: str = "") -> list[str]:
    """Geef het pad van elke sleutel die binnen hetzelfde object twee keer staat.

    Return the path of every key that stands twice inside the same object.

    `node` is wat `json.loads(..., object_pairs_hook=_Object)` teruggeeft: elk
    object is een `_Object` (een lijst paren), elke array een gewone lijst. Een
    dubbele sleutel levert hier het pad van het object waarin hij staat plus de
    sleutel zelf, en telt per voorkomen — dus drie keer hetzelfde betekent twee
    meldingen.

    `node` is what `json.loads(..., object_pairs_hook=_Object)` returns: every
    object is an `_Object` (a list of pairs), every array a plain list. A
    duplicate key yields the path of the object it stands in plus the key
    itself, once per extra occurrence — so three times the same key means two
    findings.
    """
    found: list[str] = []
    if isinstance(node, _Object):
        seen: set[str] = set()
        for key, value in node:
            here = f"{path}.{key}" if path else key
            if key in seen:
                found.append(here)
            seen.add(key)
            found += duplicate_key_paths(value, here)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found += duplicate_key_paths(value, f"{path}[{index}]")
    return found


@pytest.mark.parametrize("path", [STRINGS, *language_files()], ids=lambda path: path.stem)
def test_no_key_stands_twice_inside_one_object(path: Path) -> None:
    """Geen enkel vertaalbestand draagt twee keer dezelfde sleutel.

    Wat hier vastligt: binnen één object komt geen sleutel twee keer voor. Dat
    is de eigenschap die een mens niet ziet en die een vertaling stil onbruikbaar
    maakt — JSON laat de laatste winnen, dus de eerste zin is onbereikbaar en er
    klaagt niets. De zeven bestanden zijn `strings.json` plus de zes
    vertalingen; de bron is de tekst van het bestand, gelezen met `json` zelf
    (`object_pairs_hook`), niet met een eigen parser ernaast. Die haak ziet
    élke dubbele sleutel, op elk niveau en in elke schrijfwijze — vandaag is dat
    de enige manier om dit te meten, want een dict is het bewijs al kwijt.

    What this pins down: inside one object no key occurs twice. That is the
    property a human does not see and that quietly makes a translation unusable
    — JSON lets the last one win, so the first sentence is unreachable and
    nothing complains. The seven files are `strings.json` plus the six
    translations; the source is the file's text, read with `json` itself
    (`object_pairs_hook`), not with a parser of its own beside it. That hook sees
    every duplicate key, at every level and in every spelling — today that is the
    only way to measure this, because a dict has already lost the evidence.
    """
    data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_Object)
    found = duplicate_key_paths(data)
    assert not found, (
        f"{path.name}: dezelfde sleutel staat twee keer in hetzelfde object, en JSON "
        f"laat stil de laatste winnen: {found}"
    )


@pytest.mark.parametrize("path", language_files(), ids=lambda path: path.stem)
class TestEveryLanguage:
    def test_it_is_valid_json(self, path: Path) -> None:
        assert isinstance(load(path), dict)

    def test_it_carries_exactly_the_english_keys(self, path: Path) -> None:
        expected = set(leaves(load(STRINGS)))
        actual = set(leaves(load(path)))
        assert not expected - actual, f"{path.stem} is missing {sorted(expected - actual)}"
        assert not actual - expected, f"{path.stem} has extra {sorted(actual - expected)}"

    def test_it_keeps_every_placeholder(self, path: Path) -> None:
        """A dropped `{zone}` leaves a sentence with a hole where a name goes."""
        source = leaves(load(STRINGS))
        for key, text in leaves(load(path)).items():
            assert set(PLACEHOLDER.findall(text)) == set(PLACEHOLDER.findall(source[key])), key

    def test_nothing_was_left_untranslated_by_accident(self, path: Path) -> None:
        """Every language should differ from English somewhere, or it is a copy."""
        if path.stem == "en":
            return
        source = leaves(load(STRINGS))
        translated = leaves(load(path))
        differing = sum(1 for key in source if translated[key] != source[key])
        assert differing > len(source) // 2, f"{path.stem} looks largely untranslated"

    def test_no_text_is_empty(self, path: Path) -> None:
        for key, text in leaves(load(path)).items():
            assert text.strip(), key


@pytest.mark.parametrize("formal", ["Sie", "Ihr", "Ihre", "Ihnen"])
def test_german_no_longer_mixes_formal_and_du(formal: str) -> None:
    """Het Duits trekt alle formele vormen naar `du`, niet alleen `Sie`.

    De bewaking keek eerst alleen naar het losse woord `Sie`. Het Duits kent
    zijn formele aanspreekvorm net zo goed in `Ihr`, `Ihre` en `Ihnen`, dus wie
    alleen op `Sie` let, laat die drie erlangs glippen. Daarom hier het hele
    rijtje, als parametrisatie.

    The German pulls every formal form towards `du`, not only `Sie`.
    The guard first looked only at the word `Sie`. German knows its formal
    address just as well in `Ihr`, `Ihre` and `Ihnen`, so a guard that only
    watches `Sie` lets those three slip through. Hence the whole row here, as a
    parametrisation.
    """
    texts = leaves(load(TRANSLATIONS / "de.json"))
    for key, text in texts.items():
        assert not re.search(rf"\b{formal}\b", text), key
    assert sum(len(re.findall(r"\bdu\b", text)) for text in texts.values()) > 0


@pytest.mark.parametrize("formal", ["Sie", "Ihr", "Ihre", "Ihnen"])
def test_german_guide_no_longer_mixes_formal_and_du(formal: str) -> None:
    """De Duitse handleiding spreekt `du`, net als de interface.

    De aanspreekvorm-bewaking hierboven keek alleen naar `de.json`; de
    handleiding viel op twee regels terug in de Sie-vorm en een paar
    hoofdletter-`Sie`-vormen die als "zij" bedoeld waren. Nu geldt dezelfde
    eis voor `docs/install/de.md`, zodat de handleiding niet stilletjes kan
    terugvallen. Bewuste prijs: de tekst vermijdt ook de hoofdletter `Sie` als
    verwijzing naar een zelfstandig naamwoord, en noemt dat naamwoord gewoon.

    The German guide speaks `du`, exactly like the interface.
    The address guard above only looked at `de.json`; the guide fell back into
    the Sie-form on two lines, with a few capital-`Sie` forms meant as "she".
    The same demand now applies to `docs/install/de.md`, so the guide cannot
    silently relapse. Deliberate price: the text also avoids capital `Sie`
    referring to a noun, and simply names that noun.
    """
    text = (Path(__file__).parent.parent / "docs" / "install" / "de.md").read_text(encoding="utf-8")
    assert not re.search(rf"\b{formal}\b", text), f"de.md bevat {formal}"
    assert re.search(r"\bdu\b", text), "de.md spreekt de lezer niet meer met du aan"


def test_french_guide_speaks_vous_not_tu() -> None:
    """De Franse handleiding spreekt `vous`, net als de interface.

    De sectie *Limites connues* viel terug in tutoiement (`laisse`, `juge`,
    `règle-le`) midden in een vous-tekst. Hier dezelfde eis als bij het Duits:
    geen tu-voornaamwoorden en geen tu-gebiedende wijs, zodat de handleiding
    niet stilletjes terugvalt. De bewaking is bewust een letterlijke lijst van
    de tu-vormen die kunnen terugkomen; een derde-persoons-`laisse`
    ("une installation qui laisse") hoort er niet onder.

    The French guide speaks `vous`, exactly like the interface.
    The *Known limitations* section fell back into tutoiement (`laisse`,
    `juge`, `règle-le`) in the middle of a vous-text. The same demand as for
    German: no tu-pronouns and no tu-imperative, so the guide cannot silently
    relapse. The guard is deliberately a literal list of the tu-forms that can
    come back; a third-person `laisse` ("une installation qui laisse") does
    not belong under it.
    """
    text = (Path(__file__).parent.parent / "docs" / "install" / "fr.md").read_text(encoding="utf-8")
    # Hoofdletterongevoelig: een zin die met "Tu …" begint is net zo goed een
    # terugval in tutoiement als een "tu" midden in de zin.
    #
    # Case-insensitive: a sentence starting with "Tu …" is just as much a
    # relapse into tutoiement as a "tu" in the middle of a sentence.
    for tu_form in (r"\btu\b", r"\bton\b", r"\bta\b", r"\btes\b", r"\btoi\b"):
        assert not re.search(tu_form, text, flags=re.IGNORECASE), f"fr.md bevat {tu_form}"
    for phrase in ("laisse le directeur", "juge chaque tour", "règle-le"):
        assert phrase not in text, f"fr.md bevat {phrase!r}"
    assert re.search(r"\bvous\b", text), "fr.md spreekt de lezer niet meer met vous aan"


def test_french_names_the_product_one_way() -> None:
    """`directeur` overal, rechte apostroffen, geen `préchauffage`."""
    texts = leaves(load(TRANSLATIONS / "fr.json"))
    for key, text in texts.items():
        assert not re.search(r"\bdirector\b", text), key
        assert "\u2019" not in text, key
        assert "préchauff" not in text, key


def test_the_override_and_the_bypass_do_not_share_one_word() -> None:
    """De override van een zone en de overbrugging van één opening zijn twee dingen.

    Wie "Anulación" bij een zone leest en "Anulación" bij een opening, kan niet
    zien welk van de twee hij voor zich heeft; in het Arabisch is het net zo met
    `تجاوز`. De twee schakelaars staan naast elkaar in hetzelfde scherm, dus ze
    moeten twee woorden hebben: de gebruiker zoekt op het woord, niet op de
    plaatsaanduiding erachter.

    Deze test leest de **bron** (de vertaalbestanden) en niet een runtimeobject,
    want de weergavenaam van een schakelaar wordt nergens in de code opgebouwd -
    hij komt rechtstreeks uit de vertaling. Daarom staat de structurele afspraak
    erbij in `AGENTS.md` (taalregel: twee verschillende dingen krijgen twee
    woorden), en noemt deze docstring de dekking en de bewust ongedekte randen.

    Wat hij **dekt**: `entity.switch.zone_override.name` tegenover
    `entity.switch.opening_bypass.name` in alle zeven talen, met de
    plaatsaanduiding eruit gehaald (`{zone}` / `{opening}`), vergeleken als tekst
    na het strippen van spaties. Wat hij **niet** dekt: een taal die hetzelfde
    begrip met een ander lidwoord of een verbogen vorm alsnog hetzelfde noemt,
    een derde schakelaar die toevallig hetzelfde woord draagt, en de rest van het
    scherm - deze test kijkt naar precies deze twee sleutels.

    The zone override and the opening bypass are two different things. Whoever
    reads "Anulación" on a zone and "Anulación" on an opening cannot tell which
    of the two they are looking at, and Arabic has the same problem with
    `تجاوز`. The two switches stand side by side on one screen, so they need two
    words. This test reads the **source** (the translation files) rather than a
    runtime object, because the display name of a switch is never built in code.
    Hence the structural agreement in `AGENTS.md`, and the coverage named above
    with its deliberate edges.
    """
    for language in ("nl", "en", "de", "fr", "es", "ar"):
        texts = leaves(load(TRANSLATIONS / f"{language}.json"))
        override = texts["entity.switch.zone_override.name"].replace("{zone}", "").strip()
        bypass = texts["entity.switch.opening_bypass.name"].replace("{opening}", "").strip()
        assert override, language
        assert bypass, language
        assert override != bypass, f"{language}: de twee schakelaars delen één woord: {override!r}"


def test_every_language_names_the_shared_heat_source_in_unreadable_entities() -> None:
    """De reparatiemelding noemt ook de gedeelde warmtebron."""
    needles = {
        "strings": "shared heat source",
        "nl": "gedeelde warmtebron",
        "en": "shared heat source",
        "de": "gemeinsame Wärmequelle",
        "fr": "source de chaleur partagée",
        "es": "fuente de calor compartida",
        "ar": "مصدر الحرارة المشترك",
    }
    for language, needle in needles.items():
        path = STRINGS if language == "strings" else TRANSLATIONS / f"{language}.json"
        text = leaves(load(path))["issues.unreadable_entities.description"]
        assert needle in text, language


#: Eén begrip, één woord. Per taal het verboden woord, het canonieke woord en de
#: reden erbij. De lijst groeit per tekstronde; er gaat niets af zonder reden. Hij
#: dekt **alle zes** talen en telt ruim vijftig naalden; voor het Engels wordt ook
#: `strings.json` gelezen, want dat is de bron die Home Assistant zelf leest.
#:
#: Een naald is een **stam** of een **patroon**, niet een heel woord: het
#: Arabisch plakt zijn lidwoord en zijn voorzetsels aan het woord vast (*ال*,
#: *لل*, *بال*, *وال*), dus een naald met het lidwoord eraan mist dezelfde stam
#: achter een ander voorzetsel. En een naald die *ال* op het tweede woord
#: meeschrijft mist de onbepaalde vorm van diezelfde stam. Wie een naald
#: opschrijft laat het lidwoord eraf, en waar dat niet kan schrijft hij een
#: patroon met het lidwoord optioneel, zodat elke vorm meetelt; de canonieke
#: vorm eronder draagt het lidwoord wél, want dat is wat de lezer op het scherm
#: hoort te zien. Daarom wordt een naald met `re` gelezen en niet als losse
#: tekst, en mag hij een **woordgrens** dragen waar een dienstnaam hetzelfde
#: woord bevat: `\boverrides?\b` telt het losse woord en niet `set_override`.
#: Een naald dekt **enkelvoud én meervoud**: `\boverrides?\b` telt *override* en
#: *overrides*, `emplois? du temps` telt *emploi du temps* en *emplois du
#: temps*, en `résident` telt *résident* en *résidents*. Zonder dat glipt de
#: buurschrijfwijze er langs en wordt die de volgende ronde.
#:
#: One concept, one word. Per language the forbidden word, the canonical word and
#: the reason alongside. The list grows per text round; nothing comes off without
#: a reason. It covers **all six** languages and counts well over fifty needles;
#: for English it is also measured against `strings.json`, that being the source
#: Home Assistant itself reads.
#:
#: A needle is a **stem** or a **pattern**, not a whole word: Arabic glues its
#: article and its prepositions onto the word (*ال*, *لل*, *بال*, *وال*), so a
#: needle carrying the article misses the same stem behind another preposition.
#: And a needle that also writes *ال* onto the second word misses the indefinite
#: form of that same stem. Whoever writes a needle leaves the article off, and
#: where that is impossible he writes a pattern with the article optional, so
#: every form counts; the canonical form below does carry the article, because
#: that is what the reader should see on screen. That is why a needle is read
#: with `re` and not as plain text, and why it may carry a **word boundary**
#: where a service name holds the same word: `\boverrides?\b` counts the loose
#: word and not `set_override`. A needle covers **singular and plural**:
#: `\boverrides?\b` counts *override* and *overrides*, `emplois? du temps`
#: counts *emploi du temps* and *emplois du temps*, and `résident` counts
#: *résident* and *résidents*. Without that the neighbouring spelling slips past
#: and becomes the next round.
TERMINOLOGY: dict[str, tuple[tuple[str, str, str], ...]] = {
    "nl": (
        (
            r"\bhysteresis\b",
            "hysterese",
            "het scherm noemt de band *Dode band* en de melding *een negatieve "
            "{mode}-hysterese*; *hysteresis* is de Engelse vorm en staat in geen enkele "
            "Nederlandse schermtekst",
        ),
        (
            "buitendode",
            "dode band op de buitentemperatuur",
            "het veld heet *Dode band buitentemperatuur* en de melding zegt *de dode band op "
            "de buitentemperatuur*; *buitendode* is een samenstelling die het scherm nergens "
            "gebruikt",
        ),
        (
            r"\buitsluitende?\b",
            "exclusieve",
            "het scherm noemt de groep *Exclusieve groepen* en het veld *Apparaten in deze "
            "groep*; *uitsluitende* is een eigen woord voor hetzelfde ding",
        ),
        (
            "koelcircuit",
            "airco-circuit",
            "het scherm noemt de stap *Airco-circuits* en de knop *+ Airco-circuit "
            "toevoegen*; *koelcircuit* staat in geen enkele Nederlandse schermtekst",
        ),
    ),
    "en": (
        (
            "leave the field away",
            "leave the field out",
            "het scherm zegt *Leave the field out for the whole house*; *away* laat de lezer "
            "denken dat het veld weg moet in plaats van leeg te blijven",
        ),
        (
            "serves along",
            "it also serves",
            "de melding zegt *the area it also serves*; *serves along* is geen Engels dat "
            "het scherm gebruikt",
        ),
        (
            r"along with it\b",
            "along with this one",
            "de gids zegt *warms the rest along with this one*, naar het apparaat van deze "
            "bron; *it* slaat op niets terug",
        ),
        (
            "while holiday schedule is on",
            "while the holiday schedule is on",
            "de schermtekst zegt *while the holiday schedule is on*; het lidwoord hoort erbij",
        ),
        (
            "leaving holiday schedule to",
            "leaving the holiday schedule to",
            "idem in *leaving the holiday schedule to the switch alone*",
        ),
        (
            "switch holiday schedule",
            "switch the holiday schedule",
            "idem in *switch the holiday schedule on*: het lidwoord hoort erbij",
        ),
        (
            "holds back starting",
            "holds back the start",
            "het optielabel zegt *the quiet window holds back the start*; *starting* is geen "
            "zelfstandig naamwoord dat het scherm gebruikt",
        ),
        (
            "asks a mode",
            "asks for a mode",
            "de melding zegt *asks for a mode that {count} appliance(s) cannot run*; *asks a "
            "mode* laat het voorzetsel weg en is geen Engels dat het scherm gebruikt",
        ),
    ),
    "de": (
        (
            "Feiertag",
            "Urlaubstag",
            "de interface noemt een vakantiedag een *Urlaubstag*; een *Feiertag* is een "
            "feestdag en dat verschil is precies wat de uitleg bij de uiterste opsta-tijd maakt",
        ),
        (
            "Kältekreis",
            "Klimakreis",
            "de kop en de stap heten *Klimakreise*; *Kältekreis* is een eigen woord voor "
            "hetzelfde ding",
        ),
        (
            r"\bKreislauf",
            "Kreis",
            "het scherm zegt *Kreis*; *Kreislauf* staat in geen enkele Duitse schermtekst",
        ),
        (
            "Kreisläufe",
            "Kreise",
            "idem in het meervoud: de stap heet *Klimakreise* en het veld noemt *Kreise*",
        ),
        (
            "Außeneinheit",
            "Außengerät",
            "het scherm noemt het apparaat *Außengerät*; *Außeneinheit* staat in geen enkele "
            "Duitse schermtekst",
        ),
        (
            "Gastmodus",
            "Gästemodus",
            "de stap heet *Gästemodus*; *Gastmodus* mist de umlaut en staat er nergens",
        ),
        (
            "Gastfenster",
            "Fenster des Gästemodus",
            "het veld heet *Fenster des Gästemodus*; *Gastfenster* is geen schermtekst",
        ),
        (
            r"\bAnfrage",
            "Anforderung",
            "het scherm noemt het verzoek *Anforderung*; *Anfrage* staat er nergens",
        ),
        (
            r"\bWunsch",
            "Anforderung",
            "idem: *Wunsch* is een eigen woord voor hetzelfde ding",
        ),
        (
            r"\boverrides?\b",
            "Übersteuerung",
            "het scherm noemt de schakelaar *Übersteuerung {zone}* en de diensten "
            "*Übersteuerung setzen* en *Übersteuerung beenden*; *Override* is Engels en staat "
            "in geen enkele Duitse schermtekst. De dienstnamen `set_override` en "
            "`clear_override` blijven Engels en vallen door de woordgrens buiten deze naald",
        ),
        (
            "Totband",
            "Totzone",
            "het scherm zegt *Totzone*; *Totband* staat in geen enkele Duitse schermtekst",
        ),
        (
            "Außentotzone",
            "Totzone der Außentemperatur",
            "het veld heet *Totzone der Außentemperatur*; *Außentotzone* is een eigen "
            "samenstelling",
        ),
    ),
    "fr": (
        (
            "jour férié",
            "jour de vacances",
            "de interface noemt een vakantiedag *un jour de vacances*; *un jour férié* is een "
            "feestdag",
        ),
        (
            "préchauff",
            "préparation",
            "het verzoek warmt niet voor maar bereidt voor, en het koelt evengoed: het scherm "
            "noemt de knop en de duur *Préparer* en *Durée de la préparation*, en "
            "*préchauffage* belooft verwarming die er niet is",
        ),
        (
            r"\boverrides?\b",
            "dérogation",
            "het scherm noemt de schakelaar *Dérogation {zone}* en de acties *Définir une "
            "dérogation* en *Terminer la dérogation*; *override* is Engels en staat in geen "
            "enkele Franse schermtekst, in het enkelvoud niet en in het meervoud niet. De "
            "dienstnamen `set_override` en `clear_override` blijven Engels en vallen door de "
            "woordgrens buiten deze naald",
        ),
        (
            r"emplois? du temps",
            "planning",
            "het scherm noemt het rooster en de poort *Planning* (*Le planning d'un occupant "
            "doit être ouvert*, *La barrière de planning*); *emploi du temps* staat in geen "
            "enkele Franse schermtekst, in het enkelvoud niet en in het meervoud niet",
        ),
        (
            "résident",
            "occupant",
            "het scherm noemt de bewoner *Occupant* (*Occupants*, *Un nom, pour distinguer les "
            "occupants*, *Supprime l'occupant ainsi que ses plannings*); *résident* staat in "
            "geen enkele Franse schermtekst, in het enkelvoud niet en in het meervoud niet",
        ),
        (
            "frigorifique",
            "de climatisation",
            "het scherm zegt *circuit de climatisation* en *Circuits de climatisation*; "
            "*circuit frigorifique* staat in geen enkele Franse schermtekst",
        ),
        (
            r"habitants?\b",
            "occupant",
            "het scherm noemt de bewoner *Occupant*; *habitant* staat er nergens, in het "
            "enkelvoud niet en in het meervoud niet",
        ),
        (
            r"horaires?\b",
            "planning",
            "het scherm noemt het rooster *Planning*; *horaire* staat er nergens, in het "
            "enkelvoud niet en in het meervoud niet",
        ),
        (
            "zone morte",
            "bande morte",
            "het scherm noemt de band *Bande morte*; *zone morte* is een eigen woord voor "
            "hetzelfde ding",
        ),
        (
            "Laisser les deux vides",
            "Laissez les deux vides",
            "de schermtekst staat in de gebiedende wijs (*Laissez les deux vides pour qu'il "
            "s'applique toute la journée*); de infinitief leest als een beschrijving in "
            "plaats van een opdracht",
        ),
        (
            r"\bportes?\s+(de|du|des)\s",
            "barrière",
            "de poort heet *barrière* (*la barrière de présence*, *de planning*, *du "
            "sommeil*, *de silence*); *porte* blijft voor de echte deur (*une fenêtre ou une "
            "porte est ouverte*)",
        ),
        (
            r"\bfenêtres?\s+(de\s+sommeil|de\s+vacances|du\s+mode\s+invités"
            r"|de\s+silence|silencieuse|extérieure|ordinaire)",
            "plage",
            "het tijdvenster heet *plage* (*plage de sommeil*, *plage de vacances*, *plage du "
            "mode invités*, *plages de silence*, *plage extérieure*); *fenêtre* blijft voor "
            "het echte raam",
        ),
    ),
    "es": (
        (
            "día festivo",
            "día de vacaciones",
            "de interface noemt een vakantiedag *un día de vacaciones*; *un día festivo* is "
            "een feestdag",
        ),
        (
            r"\boverrides?\b",
            "anulación",
            "het scherm noemt de schakelaar *Anulación {zone}*, de eindtijdsensor *Fin de la "
            "anulación {zone}* en de acties *Definir anulación* en *Terminar anulación*; "
            "*override* is Engels en staat in geen enkele Spaanse schermtekst, in het "
            "enkelvoud niet en in het meervoud niet. De dienstnamen `set_override` en "
            "`clear_override` blijven Engels en vallen door de woordgrens buiten deze naald",
        ),
        (
            r"\baperturas?\b",
            "abertura",
            "het scherm noemt de opening *Abertura* en de knop *+ Añadir abertura*; "
            "*apertura* staat in geen enkele Spaanse schermtekst",
        ),
        (
            "frigorífico",
            "de climatización",
            "het scherm zegt *circuito de climatización* en *Circuitos de climatización*; "
            "*frigorífico* staat in geen enkele Spaanse schermtekst",
        ),
        (
            r"\bpuertas?\s+(de|del)\s",
            "barrera",
            "de poort heet *barrera* (*la barrera de presencia*, *de horario*, *del sueño*); "
            "*puerta* blijft voor de echte deur (*el contacto de puerta, ventana o "
            "claraboya*)",
        ),
        (
            r"\bventanas?\s+(de\s+sueño|de\s+vacaciones|de\s+invitados|de\s+silencio"
            r"|silenciosa|exterior|ordinaria)",
            "franja",
            "het tijdvenster heet *franja* (*franja de sueño*, *de vacaciones*, *de "
            "invitados*, *de silencio*, *franja exterior*); *ventana* blijft voor het echte "
            "raam",
        ),
        (
            r"franjas?\s+silenciosas?",
            "franja de silencio",
            "het scherm heet *Franja de silencio*; *franja silenciosa* is een eigen vorm voor "
            "hetzelfde ding, in het enkelvoud en het meervoud, ook over een regelafbreking "
            "heen. *fallos silenciosos* (stille storingen) valt buiten deze naald",
        ),
        (
            "titil",
            "no conmute sin parar",
            "het scherm zegt *no conmute sin parar por una décima de grado*; *titile* is een "
            "eigen werkwoord voor hetzelfde verschijnsel",
        ),
        (
            "anticiclado",
            "de descanso",
            "het scherm zegt *tiempo de descanso*; *anticiclado* is een eigen woord voor "
            "hetzelfde ding",
        ),
    ),
    "ar": (
        (
            r"تدفئة\s+(ال)?مسبقة",
            "التهيئة المسبقة",
            "het verzoek warmt niet voor maar vraagt vooruit; dezelfde taakneutrale term als "
            "het Nederlands, Duits en Frans gebruiken",
        ),
        (
            "المخرج",
            "المدير",
            "het scherm noemt de integratie *المدير*; *المخرج* is een eigen woord voor "
            "hetzelfde ding",
        ),
        (
            "دوائر التبريد",
            "دوائر التكييف",
            "de stap heet *دوائر التكييف*; *التبريد* hoort bij de taak koelen en niet bij het "
            "circuit",
        ),
        (
            "منظوم",
            "المنشأة",
            "het scherm noemt de installatie *المنشأة*; *المنظومة* is een eigen woord voor "
            "hetzelfde ding. De stam vangt ook de vorm met een bezittelijk achtervoegsel "
            "(*منظومتك*), die *المنظومة* als naald liet passeren",
        ),
        (
            "موسم",
            "الفصل",
            "het scherm noemt het seizoen *الفصل* (*كيان الفصل*, *الفصل: الفصل يحدد المهمة*); "
            "*الموسم* is een eigen woord voor hetzelfde ding. De naald is de stam zonder "
            "lidwoord, zodat ook de onbepaalde vorm (*كيان موسم*) meetelt",
        ),
        (
            "حضور",
            "وجود",
            "het scherm noemt de sensor *مستشعر الوجود* en de melding zegt *بلا مستشعر وجود*; "
            "*حضور* is een eigen woord voor hetzelfde ding, met en zonder lidwoord",
        ),
        (
            r"المنظ[ّ]?م\b",
            "المدير",
            "het scherm noemt de integratie *المدير*; *المنظّم* is een eigen woord voor "
            "hetzelfde ding. De woordgrens laat *المنظمة* en *منظّم الحرارة* (de thermostaat, "
            "zonder lidwoord) buiten de naald",
        ),
        (
            r"المنس[ّ]?ق(?!$)",
            "المدير",
            "het scherm noemt de integratie *المدير*; *المنسّق* is een eigen woord voor "
            "hetzelfde ding. Alleen de entiteitsnaam van de hoofdschakelaar heet zo, en die "
            "blijft om haar id: een waarde die precies dat woord is, valt buiten de naald",
        ),
        (
            "التكاملة",
            "التكامل",
            "het scherm schrijft *التكامل*; de vorm met de taa-marbuta is een eigen spelling",
        ),
        (
            r"حس[ّ]?اس",
            "مستشعر",
            "het scherm noemt de sensor *مستشعر*; *حسّاس* staat in geen enkele Arabische "
            "schermtekst, met of zonder shadda",
        ),
        (
            "تثبيتك",
            "منشأتك",
            "het scherm zegt *منشأتك* voor jouw installatie; *تثبيتك* betekent het installeren "
            "zelf",
        ),
        (
            "المقيم",
            "الساكن",
            "het scherm noemt de bewoner *الساكن* (*حذف هذا الساكن*); *المقيم* is een eigen "
            "woord voor hetzelfde ding",
        ),
        (
            "لكل تثبيت",
            "لكل منشأة",
            "idem: *لكل منشأة* is per installatie; *لكل تثبيت* is per installatiehandeling",
        ),
        (
            r"التركيب(?!ة)",
            "المنشأة",
            "het scherm noemt de installatie *المنشأة*; *التركيب* is een eigen woord voor "
            "hetzelfde ding, terwijl de vorm *التركيبة* buiten deze naald blijft",
        ),
    ),
}

GUIDES = Path(__file__).parent.parent / "docs" / "install"


def terminology_texts(language: str) -> dict[str, list[str]]:
    """De teksten van één taal: het vertaalbestand, de gids en de bron van Engels.

    `strings.json` is voor het Engels de bron die Home Assistant zelf leest; staat
    daar een woord dat de vertaling al kwijt is, dan leest de gebruiker het toch.

    The texts of one language: its translation file, its guide and the English
    source. For English `strings.json` is the source Home Assistant itself reads; a
    word lost there while the translation still has it is read by the user anyway.
    """
    texts = {
        f"translations/{language}.json": list(
            leaves(load(TRANSLATIONS / f"{language}.json")).values()
        ),
        f"docs/install/{language}.md": [(GUIDES / f"{language}.md").read_text(encoding="utf-8")],
    }
    if language == "en":
        texts["strings.json"] = list(leaves(load(STRINGS)).values())
    return texts


@pytest.mark.parametrize("language", sorted(TERMINOLOGY))
def test_one_concept_gets_one_word(language: str) -> None:
    """Eén begrip, één woord, in het vertaalbestand én in de gids van die taal.

    Dit is een **spellingsbewaking** en dat is hier de juiste vorm: "één woord per
    begrip" valt nergens aan een object of een echte tool af te meten, want het is
    een afspraak over de tekst zelf. De lijst is daarom letterlijk en noemt per
    regel het verboden woord, het canonieke woord en de reden; de docstring bij de
    lijst zegt welke spellingen hij dekt, en elke naald wordt als patroon gelezen
    (`re`) zodat een lidwoord optioneel kan zijn. De vergelijking is
    hoofdletterongevoelig, zodat een kop die met het verboden woord begint niet
    langs de bewaking glipt. Wie een woord toevoegt, schrijft de reden
    erbij op: waarom het ene woord het begrip dekt en het andere een ander begrip
    oproept.

    One concept, one word, in the translation file and in that language's guide.

    This is a **spelling guard** and that is the right shape here: "one word per
    concept" cannot be measured on an object or with a real tool, because it is an
    agreement about the text itself. The list is therefore literal and names the
    forbidden word, the canonical word and the reason per line; the docstring at
    the list says which spellings it covers. The comparison is case-insensitive,
    so a heading opening with the forbidden word does not slip past the guard.
    Whoever adds a word writes the reason
    down: why the one word covers the concept and the other calls up a different
    one.
    """
    problems: list[str] = []
    for where, texts in terminology_texts(language).items():
        for forbidden, canonical, reason in TERMINOLOGY[language]:
            for text in texts:
                if re.search(forbidden, text, re.IGNORECASE):
                    problems.append(
                        f"{where}: {forbidden!r} hoort {canonical!r} te zijn - {reason}"
                    )
    assert not problems, "één begrip, één woord:\n" + "\n".join(problems)


#: De titels waarin `{count}` het onderwerp van de zin is: daar moet de
#: werkwoordsvorm het aantal kunnen dragen. Bij `unreadable_entities` en
#: `season_excludes_mode` is `{name}` het onderwerp en is het enkelvoud juist.
#:
#: The titles in which `{count}` is the subject of the sentence: there the verb
#: has to carry the number. In `unreadable_entities` and `season_excludes_mode`
#: `{name}` is the subject and the singular is right.
COUNT_SUBJECT_TITLES = ("command_not_taking", "bypassed_openings", "unsupported_modes")

#: Elke titel die `{count}` draagt, in elke taal. Een nieuwe titel met een aantal
#: erin laat deze bewaking rood worden, zodat hij niet ongemeten blijft.
#:
#: Every title carrying `{count}`, in every language. A new title with a count in
#: it turns this guard red, so it does not stay unmeasured.
COUNT_TITLES = frozenset({"unreadable_entities", "season_excludes_mode", *COUNT_SUBJECT_TITLES})

#: De enkelvoudige werkwoordsvormen die naast een `{count}` van 3 niet meer mogen
#: staan, per taal. Letterlijk, want "het werkwoord hoort bij het aantal" is een
#: afspraak over de tekst zelf en nergens aan een object te meten.
#:
#: The singular verb forms that may no longer stand beside a `{count}` of 3, per
#: language. Literal, because "the verb agrees with the count" is an agreement
#: about the text itself and cannot be measured on an object anywhere.
#:
#: Het Arabisch gebruikt bij een niet-menselijk meervoud de vrouwelijke
#: enkelvoudsvorm: *لا تنفّذ أمرها* hoort bij *أجهزة*, en de mannelijke
#: enkelvoudsvorm *ينفّذ* liegt zodra er drie staan. Voor *جهاز* alleen zou
#: *ينفّذ* juist zijn, maar een titel moet het met een vorm doen, en dan is de
#: vorm die bij drie niet liegt de enige keuze.
#:
#: Arabic uses the feminine singular for a non-human plural: *لا تنفّذ أمرها*
#: belongs with *أجهزة*, and the masculine singular *ينفّذ* lies as soon as three
#: stand there. For *جهاز* alone *ينفّذ* would be right, but a title has to make do
#: with one form, and then the form that does not lie at three is the only choice.
SINGULAR_VERBS: dict[str, tuple[str, ...]] = {
    "ar": ("ينفّذ",),
    "nl": ("voert", "is overbrugd", "kan"),
    "de": ("führt", "ist überbrückt", "kann"),
    "fr": ("n'exécute", "est contournée", "peut"),
    "es": ("no ejecuta", "está anulada", "puede"),
}


def count_titles(language: str) -> dict[str, str]:
    """Elke `issues.*.title` met een `{count}` erin, per taal.

    Every `issues.*.title` with a `{count}` in it, per language.
    """
    path = STRINGS if language == "strings" else TRANSLATIONS / f"{language}.json"
    return {
        key: value.get("title", "")
        for key, value in load(path)["issues"].items()
        if "{count}" in value.get("title", "")
    }


@pytest.mark.parametrize(
    "language",
    ["strings", *sorted(path.stem for path in language_files())],
    ids=["strings", "en", "nl", "de", "fr", "es", "ar"],
)
def test_every_count_title_is_a_known_one(language: str) -> None:
    """Elke titel met `{count}` staat in de lijst hierboven.

    Every title with `{count}` stands in the list above.
    """
    found = set(count_titles(language))
    assert found == set(COUNT_TITLES), (
        f"{language}: titels met een {{count}} erin: {sorted(found)}; verwacht "
        f"{sorted(COUNT_TITLES)}. Een nieuwe titel met een aantal erin hoort hier "
        f"bij te staan en op zijn werkwoordsvorm nagekeken te worden."
    )


@pytest.mark.parametrize("language", sorted(SINGULAR_VERBS))
def test_the_count_titles_read_at_count_one_and_three(language: str) -> None:
    """De drie titels met `{count}` als onderwerp lezen goed bij 1 én bij 3.

    De bewaking rendert elke titel op `count=1` en `count=3` en eist dat er geen
    enkelvoudige werkwoordsvorm uit de letterlijke lijst in staat. Bij `1
    apparaat` hoort `voert`, bij `3 apparaten` hoort `voeren`; één titel moet het
    met één vorm doen, en dan is de meervoudsvorm de enige die bij 3 niet liegt.
    De andere twee titels met een `{count}` erin blijven buiten de lijst: daar is
    `{name}` het onderwerp, en daar is het enkelvoud juist.

    The three titles with `{count}` as their subject read well at both 1 and 3.

    The guard renders every title at `count=1` and `count=3` and demands that no
    singular verb form from the literal list stands in it. `1 apparaat` takes
    `voert`, `3 apparaten` takes `voeren`; one title has to make do with one form,
    and then the plural is the only one that does not lie at 3. The other two
    titles containing a `{count}` stay outside the list: `{name}` is the subject
    there, and the singular is right.
    """
    problems: list[str] = []
    for key in COUNT_SUBJECT_TITLES:
        title = count_titles(language)[key]
        for count in (1, 3):
            rendered = title.replace("{count}", str(count)).replace("{name}", "Woonkamer")
            for form in SINGULAR_VERBS[language]:
                if re.search(rf"\b{re.escape(form)}\b", rendered):
                    problems.append(
                        f"{key} op count={count}: {form!r} staat in {rendered!r}, en dat leest "
                        f"niet bij drie"
                    )
    assert not problems, "de titel liegt over het aantal:\n" + "\n".join(problems)
