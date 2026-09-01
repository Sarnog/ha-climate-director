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


def test_german_no_longer_mixes_sie_and_du() -> None:
    """Ronde 21: het Duits trekt alle `Sie`-vormen naar `du`."""
    texts = leaves(load(TRANSLATIONS / "de.json"))
    for key, text in texts.items():
        assert not re.search(r"\bSie\b", text), key
    assert sum(len(re.findall(r"\bdu\b", text)) for text in texts.values()) > 0


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
