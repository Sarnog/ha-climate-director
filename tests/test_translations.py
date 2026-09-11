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
    """Ronde 21: het Duits trekt alle formele vormen naar `du`; C3 verbreedt dat.

    De bewaking keek eerst alleen naar het losse woord `Sie`. Het Duits kent
    zijn formele aanspreekvorm net zo goed in `Ihr`, `Ihre` en `Ihnen`, dus wie
    alleen op `Sie` let, laat die drie erlangs glippen. Daarom hier het hele
    rijtje, als parametrisatie.

    Round 21: the German pulls every formal form towards `du`; C3 broadens that.
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
    """Ronde 25 (D3): de Duitse handleiding spreekt `du`, net als de interface.

    De aanspreekvorm-bewaking hierboven keek alleen naar `de.json`; de
    handleiding viel op twee regels terug in de Sie-vorm en een paar
    hoofdletter-`Sie`-vormen die als "zij" bedoeld waren. Nu geldt dezelfde
    eis voor `docs/install/de.md`, zodat de handleiding niet stilletjes kan
    terugvallen. Bewuste prijs: de tekst vermijdt ook de hoofdletter `Sie` als
    verwijzing naar een zelfstandig naamwoord, en noemt dat naamwoord gewoon.

    Round 25 (D3): the German guide speaks `du`, exactly like the interface.
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
    """Ronde 25 (D3): de Franse handleiding spreekt `vous`, net als de interface.

    De sectie *Limites connues* viel terug in tutoiement (`laisse`, `juge`,
    `règle-le`) midden in een vous-tekst. Hier dezelfde eis als bij het Duits:
    geen tu-voornaamwoorden en geen tu-gebiedende wijs, zodat de handleiding
    niet stilletjes terugvalt. De bewaking is bewust een letterlijke lijst van
    de tu-vormen die kunnen terugkomen; een derde-persoons-`laisse`
    ("une installation qui laisse") hoort er niet onder.

    Round 25 (D3): the French guide speaks `vous`, exactly like the interface.
    The *Known limitations* section fell back into tutoiement (`laisse`,
    `juge`, `règle-le`) in the middle of a vous-text. The same demand as for
    German: no tu-pronouns and no tu-imperative, so the guide cannot silently
    relapse. The guard is deliberately a literal list of the tu-forms that can
    come back; a third-person `laisse` ("une installation qui laisse") does
    not belong under it.
    """
    text = (Path(__file__).parent.parent / "docs" / "install" / "fr.md").read_text(encoding="utf-8")
    for tu_form in (r"\btu\b", r"\bton\b", r"\bta\b", r"\btes\b", r"\btoi\b"):
        assert not re.search(tu_form, text), f"fr.md bevat {tu_form}"
    for phrase in ("laisse le directeur", "juge chaque tour", "règle-le"):
        assert phrase not in text, f"fr.md bevat {phrase!r}"
    assert re.search(r"\bvous\b", text), "fr.md spreekt de lezer niet meer met vous aan"


def test_french_names_the_product_one_way() -> None:
    """Ronde 21: `directeur` overal, rechte apostroffen, geen `préchauffage`."""
    texts = leaves(load(TRANSLATIONS / "fr.json"))
    for key, text in texts.items():
        assert not re.search(r"\bdirector\b", text), key
        assert "\u2019" not in text, key
        assert "préchauff" not in text, key


def test_every_language_names_the_shared_heat_source_in_unreadable_entities() -> None:
    """Ronde 21: na B1 noemt de reparatiemelding ook de gedeelde warmtebron."""
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
