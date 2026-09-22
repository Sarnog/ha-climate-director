"""Eén schrijfwijze voor de fatḥatān in het Arabisch.

One spelling for the fatḥatān in Arabic.

Het Arabisch schrijft de fatḥatān (het `-an`-achtervoegsel van een onbepaald
accusatief) op twee manieren: de norm in deze twee bestanden is fatḥatān
**gevolgd door** de alif (`ـًا`), maar de buurvorm met de alif **vóór** de
fatḥatān (`ـاً`) komt ook voor. Beide zijn leesbaar, maar in één bestand hoort
het er één te zijn: de lezer ziet anders in dezelfde alinea twee spellingen
door elkaar, en de vertaler die één van de twee intikt weet niet welke de
afspraak is. Op het moment dat deze bewaking geschreven is staat de norm
**267×** in `ar.md` en **220×** in `ar.json`, tegen nul van de buurvorm.

De eigenschap is letterlijk "deze reeks komt in dit bestand niet voor", en dat
is alleen op de tekst zelf te meten — er is geen object of gereedschap dat hem
kan weerspreken. Daarom staat de reeks hier letterlijk en is dit een
tekstbewaking, net als de geslachtsbewaking in `test_grammar_agreement.py`.

Wat deze bewaking **wel** dekt: de reeks alif gevolgd door fatḥatān
(U+0627 U+064B) in het proza van `ar.md` en in élke waarde van `ar.json`, buiten
code-spans (`` `…` ``), afgebakende codeblokken (```` ```…``` ````) en URL's. Die
drie zijn uitgezonderd omdat ze externe, niet-geredigeerde tekst kunnen dragen.

Wat hij **bewust niet** dekt: de goede vorm (die is de norm, niet verboden); de
fatḥatān op een hamza (`أً`) of op een andere drager, die een eigen tekenreeks
is; de fatḥatān zonder alif (die komt in het standaardbeeld niet voor); en de
reeks binnen een code-span of URL — wie daar een Arabische tekst in zet,
vertaalt hem niet. Ook andere diakritische tekens (sukūn, šadda, ḍamma) vallen
buiten deze regel.

English: the property is literally "this sequence does not occur in this file",
measurable only on the text itself, so the sequence stands literally here. The
guard covers the sequence alif followed by fatḥatān (U+0627 U+064B) in the prose
of `ar.md` and in every value of `ar.json`, outside code spans, fenced code
blocks and URLs. It deliberately does not cover the normal form (fatḥatān
followed by alif), the fatḥatān on a hamza (`أً`), the fatḥatān without an alif,
or a sequence inside a code span or URL.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
AR_MD = ROOT / "docs" / "install" / "ar.md"
AR_JSON = ROOT / "custom_components" / "climate_director" / "translations" / "ar.json"

ALIF = "\u0627"
FATHATAN = "\u064b"
#: De buurvorm: alif, dan de fatḥatān.
#:
#: The neighbouring form: alif, then the fatḥatān.
BURENVORM = ALIF + FATHATAN
#: De norm in deze twee bestanden: de fatḥatān, dan de alif.
#:
#: The norm in these two files: the fatḥatān, then the alif.
NORM = FATHATAN + ALIF


def leaves(node: object, path: str = "") -> dict[str, str]:
    """Elke tekst in een vertaalbestand, op zijn puntpad.

    Every text in a translation file, keyed by its dotted path.
    """
    if not isinstance(node, dict):
        return {path: str(node)}
    found: dict[str, str] = {}
    for key, value in node.items():
        found |= leaves(value, f"{path}.{key}" if path else key)
    return found


def strip_code(text: str) -> str:
    """Haal code-spans, codeblokken en URL's weg, met behoud van regelstructuur.

    Remove code spans, code blocks and URLs, keeping the line structure.

    Elke ontdubbelde regel wordt door evenveel spaties vervangen, zodat een
    treffer niet over een grens heen kan ontstaan en een regelnummer blijft
    kloppen.
    """
    text = re.sub(r"```.*?```", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.DOTALL)
    text = re.sub(r"`[^`\n]*`", lambda m: " " * len(m.group(0)), text)
    text = re.sub(r"https?://\S+", lambda m: " " * len(m.group(0)), text)
    return text


def _lines_with_burenvorm(text: str) -> list[int]:
    """De regelnummers (1-based) waar de buurvorm in staat."""
    return [number for number, line in enumerate(text.splitlines(), start=1) if BURENVORM in line]


def _keys_with_burenvorm(text: str) -> list[str]:
    """De sleutelpaden waarvan de waarde de buurvorm draagt."""
    return [
        key for key, value in leaves(json.loads(text)).items() if BURENVORM in strip_code(value)
    ]


@pytest.mark.parametrize("source", ["ar.md", "ar.json"])
def test_the_arabic_uses_one_fathatan_spelling(source: str) -> None:
    """De buurvorm alif + fatḥatān staat niet in `ar.md` en niet in `ar.json`.

    The neighbouring form alif + fatḥatān stands neither in `ar.md` nor in
    `ar.json`.

    Waarom: één schrijfwijze per bestand, en de norm is fatḥatān + alif (267
    tegen 0 in `ar.md`, 220 tegen 0 in `ar.json`). De melding noemt per plek het
    regelnummer (`ar.md`) of het sleutelpad (`ar.json`), zodat de reparateur
    niet hoeft te zoeken.

    English: one spelling per file, the norm being fatḥatān + alif. The message
    names the line number (`ar.md`) or the dotted key (`ar.json`).
    """
    if source == "ar.md":
        raw = AR_MD.read_text(encoding="utf-8")
        assert NORM in raw, "de norm staat niet in ar.md: leest deze bewaking het echte bestand?"
        found = [f"ar.md:{number}" for number in _lines_with_burenvorm(strip_code(raw))]
        assert not found, (
            "de buurvorm van de fatḥatān (alif vóór de fatḥatān) hoort hier niet te staan; "
            "gebruik de norm (fatḥatān vóór de alif):" + "\n" + "\n".join(found)
        )
    else:
        raw = AR_JSON.read_text(encoding="utf-8")
        assert NORM in raw, "de norm staat niet in ar.json: leest deze bewaking het echte bestand?"
        found = [f"ar.json:{key}" for key in _keys_with_burenvorm(raw)]
        assert not found, (
            "de buurvorm van de fatḥatān (alif vóór de fatḥatān) hoort hier niet te staan; "
            "gebruik de norm (fatḥatān vóór de alif):" + "\n" + "\n".join(found)
        )
