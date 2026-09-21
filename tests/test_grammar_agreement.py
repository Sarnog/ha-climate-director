"""Grammatica-afspraken in de teksten die de gebruiker ziet.

Grammar agreements in the texts the user sees.

Een bewaking op spelling is hier de juiste vorm: of een lidwoord bij zijn
zelfstandig naamwoord past is een afspraak over de tekst zelf en valt nergens aan
een object of een echte tool af te meten. Daarom staat de lijst hieronder
letterlijk, met per woord zijn geslacht, en zegt deze docstring exact welke
vormen hij toetst:

- het bepaald lidwoord, het onbepaald lidwoord en het aanwijzend voornaamwoord
  **direct vóór** het schermwoord: Frans *le/la*, *un/une*, *ce/cette*; Spaans
  *el/la*, *un/una*, *este/esta*; Nederlands *de/het*, *deze/dit*;
- het wederkerend voornaamwoord *lui-même* / *elle-même* (Frans) en *sí mismo* /
  *sí misma* (Spaans) **in dezelfde zin**, en alleen wanneer daar precies één
  schermwoord uit de lijst in staat. Met twee schermwoorden in één zin kan de
  bewaking niet zien waar het voornaamwoord naar wijst en zwijgt hij liever dan
  te gokken — dat is de bewuste, smalle kant van deze regel;
- het **voltooid deelwoord** na een hulpwerkwoord van zijn, maar alleen wanneer
  het schermwoord met zijn eigen lidwoord **direct vóór** dat hulpwerkwoord
  staat: *la dérogation a été posée*, *la zone est activée*, *le contournement
  est activé*. Frans toetst de uitgangen `-é`/`-és` (mannelijk) tegen `-ée`/
  `-ées` (vrouwelijk), Spaans `-ado`/`-ados`/`-ido`/`-idos` tegen `-ada`/
  `-adas`/`-ida`/`-idas`. De bewaking eist die vaste volgorde — lidwoord,
  schermwoord, hulpwerkwoord, deelwoord — en dat is de smalle kant: een
  deelwoord verderop in dezelfde zin wordt **niet** getoetst, want daar beslist
  zijn eigen onderwerp. Dat is geen zuinigheid maar gemeten: in *rien ne s'est
  passé* naast de tabelrij *Préparation refusée*, in *{openings} est ignoré*
  naast *{zone}* en in *La porte de planning est activée* is het deelwoord goed
  en het schermwoord toevallig mede-aanwezig. Een bijvoeglijk naamwoord dat
  los achter het zelfstandig naamwoord staat (*une zone actif*) valt er ook
  buiten, om dezelfde reden.

De vergelijking is hoofdletterongevoelig, zodat een kop die met het schermwoord
begint niet langs de bewaking glipt. Meervouden staan er niet bij waar het
lidwoord geen geslacht meer draagt: Frans *les/des/ces* en Nederlands *de* zijn
voor beide geslachten hetzelfde, dus daar valt geen fout te meten; het Spaans
draagt zijn geslacht in het meervoud wél (*las* tegenover *los*) en dat staat er
daarom bij. Duits doet niet mee, en dat is met opzet: door de naamvallen is *der
Übersteuerung* in de datief correct, dus een lidwoordtoets zonder zinsontleding
geeft daar valse positieven. Wie een schermwoord toevoegt, schrijft zijn geslacht
erbij op; een woord dat hier niet staat wordt nergens getoetst.

A spelling guard is the right shape here: whether a determiner fits its noun is
an agreement about the text itself and cannot be measured on an object or with a
real tool. The list below is literal, with each word's gender, and this docstring
states exactly which forms it checks: the determiner directly before the screen
word (French *le/la*, *un/une*, *ce/cette*; Spanish *el/la*, *un/una*,
*este/esta*; Dutch *de/het*, *deze/dit*) and the reflexive pronoun
*lui-même*/*elle-même* (French) and *sí mismo*/*sí misma* (Spanish) in the same
sentence, and only when exactly one screen word from the list stands in it. With
two screen words in one sentence the guard cannot tell what the pronoun points
at and prefers to stay silent rather than guess — that is the deliberate, narrow
side of this rule. The **past participle** after an auxiliary of *être* is
checked too, but only when the screen word with its own determiner stands
**directly before** that auxiliary: *la dérogation a été posée*, *la zone est
activée*, *le contournement est activé*. French checks the endings
`-é`/`-és` (masculine) against `-ée`/`-ées` (feminine), Spanish
`-ado`/`-ados`/`-ido`/`-idos` against `-ada`/`-adas`/`-ida`/`-idas`. That fixed
order — determiner, screen word, auxiliary, participle — is the narrow side: a
participle further along in the same sentence is **not** checked, because there
its own subject decides. That is measured, not thrift: in *rien ne s'est passé*
next to the table row *Préparation refusée*, in *{openings} est ignoré* next to
*{zone}*, and in *La porte de planning est activée* the participle is right and
the screen word merely happens to be nearby. An adjective standing loose behind
the noun (*une zone actif*) stays outside for the same reason. The comparison is
case-insensitive, plurals are listed only where the determiner still carries a
gender (Spanish *las* against *los*), and German does not take part because its
cases make *der Übersteuerung* correct in the dative.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

COMPONENT = Path(__file__).parent.parent / "custom_components" / "climate_director"
GUIDES = Path(__file__).parent.parent / "docs" / "install"
TRANSLATIONS = COMPONENT / "translations"

#: De canonieke schermwoorden per taal, met hun geslacht: `v` vrouwelijk, `m`
#: mannelijk, `de`/`het` de Nederlandse lidwoordgroep. Alleen deze woorden worden
#: getoetst; een woord dat hier niet staat blijft buiten de bewaking.
#:
#: The canonical screen words per language, with their gender. Only these words
#: are checked; a word that does not stand here stays outside the guard.
SCREEN_NOUNS: dict[str, tuple[tuple[str, str], ...]] = {
    "fr": (
        ("dérogation", "v"),
        ("dérogations", "v"),
        ("contournement", "m"),
        ("contournements", "m"),
        ("planning", "m"),
        ("plannings", "m"),
        ("préparation", "v"),
        ("préparations", "v"),
        ("zone", "v"),
        ("zones", "v"),
        ("source", "v"),
        ("sources", "v"),
    ),
    "es": (
        ("anulación", "v"),
        ("anulaciones", "v"),
        ("zona", "v"),
        ("zonas", "v"),
        ("fuente", "v"),
        ("fuentes", "v"),
    ),
    "nl": (
        ("override", "de"),
        ("overrides", "de"),
        ("overbrugging", "de"),
        ("overbruggingen", "de"),
        ("planning", "de"),
        ("planningen", "de"),
        ("zone", "de"),
        ("zones", "de"),
        ("bron", "de"),
        ("bronnen", "de"),
    ),
}

#: Het lidwoord, het onbepaald lidwoord en het aanwijzend voornaamwoord dat bij
#: elk geslacht hoort. Alles wat in dezelfde taal bij een ander geslacht hoort is
#: fout vóór dit woord.
#:
#: The article, indefinite article and demonstrative that belong to each gender.
#: Anything in the same language that belongs to another gender is wrong before
#: this word.
DETERMINERS: dict[str, dict[str, tuple[str, ...]]] = {
    "fr": {"v": ("la", "une", "cette"), "m": ("le", "un", "ce")},
    "es": {
        "v": ("la", "una", "esta", "las", "unas", "estas"),
        "m": ("el", "un", "este", "los", "unos", "estos"),
    },
    "nl": {"de": ("de", "deze"), "het": ("het", "dit")},
}

#: Het wederkerend voornaamwoord per taal, met per vorm het geslacht waarnaar het
#: verwijst.
#:
#: The reflexive pronoun per language, with the gender each form points at.
REFLEXIVES: dict[str, tuple[str, dict[str, str]]] = {
    "fr": (r"\b(lui|elle)-même\b", {"lui": "m", "elle": "v"}),
    "es": (r"\bsí\s+(mismo|misma)\b", {"mismo": "m", "misma": "v"}),
}

#: Waar een zin eindigt. Een puntkomma telt mee: het voornaamwoord wijst naar een
#: antecedent binnen zijn eigen zin, en losse zinsdelen in een tabelrij zijn geen
#: zinnen. Zonder die grens zou een tabelrij als *un nom pour cette source ; le
#: sélecteur nomme l'appareil lui-même* een verwijzing naar het verkeerde woord
#: lijken.
#:
#: Where a sentence ends. A semicolon counts: the pronoun points at an antecedent
#: inside its own clause, and loose fragments in a table row are not sentences.
CLAUSE_END = re.compile(r"[.;!?\u2026\n]")

#: Het voltooid deelwoord bij het schermwoord: het hulpwerkwoord van zijn en de
#: uitgangen die geslacht dragen. Alleen de `-é`-familie (Frans) en de
#: `-ado`/`-ido`-familie (Spaans) staan erin; de uitgangen `-i`/`-u` van de
#: onregelmatige deelwoorden blijven erbuiten omdat woorden als *ainsi*, *ici* en
#: *aussi* dan valse positieven geven. De volgorde waarin de bewaking zoekt staat
#: in de docstring boven deze lijsten.
#:
#: The past participle with the screen word: the auxiliary of *être* and the
#: endings that carry a gender. Only the `-é` family (French) and the
#: `-ado`/`-ido` family (Spanish) are in it; the `-i`/`-u` endings of the
#: irregular participles stay out because words like *ainsi*, *ici* and *aussi*
#: would then give false positives.
PARTICIPLES: dict[str, tuple[str, dict[str, str]]] = {
    "fr": (
        r"(?:a été|ont été|est|sont|reste|restent)",
        {"é": "m", "és": "m", "ée": "v", "ées": "v"},
    ),
    "es": (
        r"(?:ha sido|han sido|está|están|fue|fueron|estaba|estaban)",
        {
            "ado": "m",
            "ados": "m",
            "ada": "v",
            "adas": "v",
            "ido": "m",
            "idos": "m",
            "ida": "v",
            "idas": "v",
        },
    ),
}


def leaves(node: object, path: str = "") -> dict[str, str]:
    """Return every text in the file, keyed by its dotted path."""
    if not isinstance(node, dict):
        return {path: str(node)}
    found: dict[str, str] = {}
    for key, value in node.items():
        found |= leaves(value, f"{path}.{key}" if path else key)
    return found


def texts_of(language: str) -> dict[str, list[str]]:
    """De teksten van één taal: de gids en het vertaalbestand.

    The texts of one language: the guide and the translation file.
    """
    translated = json.loads((TRANSLATIONS / f"{language}.json").read_text(encoding="utf-8"))
    return {
        f"docs/install/{language}.md": [(GUIDES / f"{language}.md").read_text(encoding="utf-8")],
        f"translations/{language}.json": list(leaves(translated).values()),
    }


def wrong_determiners(language: str, text: str, word: str, gender: str) -> list[str]:
    """Elk lidwoord of voornaamwoord dat niet bij dit woord past.

    Every determiner or pronoun that does not fit this word.
    """
    allowed = DETERMINERS[language][gender]
    everything = {form for forms in DETERMINERS[language].values() for form in forms}
    wrong = []
    for form in sorted(everything - set(allowed)):
        for match in re.finditer(rf"\b{form}\s+{re.escape(word)}\b", text, re.IGNORECASE):
            wrong.append(match.group(0))
    return wrong


def wrong_reflexives(language: str, text: str) -> list[str]:
    """Elk wederkerend voornaamwoord dat niet bij zijn schermwoord past.

    Every reflexive pronoun that does not fit its screen word.
    """
    if language not in REFLEXIVES:
        return []
    pattern, genders = REFLEXIVES[language]
    nouns = SCREEN_NOUNS[language]
    wrong = []
    for match in re.finditer(pattern, text, re.IGNORECASE):
        clause_start = 0
        for end in CLAUSE_END.finditer(text, 0, match.start()):
            clause_start = end.end()
        clause = text[clause_start : match.end()]
        present = [
            (word, gender)
            for word, gender in nouns
            if re.search(rf"\b{re.escape(word)}\b", clause, re.IGNORECASE)
        ]
        if len(present) != 1:
            continue
        word, gender = present[0]
        if genders[match.group(1).lower()] != gender:
            wrong.append(f"{word}: {match.group(0)}")
    return wrong


def wrong_participles(language: str, text: str) -> list[str]:
    """Elk voltooid deelwoord dat niet bij zijn schermwoord past.

    Alleen de vaste volgorde *lidwoord - schermwoord - hulpwerkwoord -
    deelwoord* telt; een deelwoord verderop in dezelfde zin blijft ongetoetst,
    want daar beslist zijn eigen onderwerp. Zie de docstring boven de lijsten.

    Every past participle that does not fit its screen word.

    Only the fixed order *determiner - screen word - auxiliary - participle*
    counts; a participle further along in the same sentence stays unchecked,
    because there its own subject decides. See the docstring above the lists.
    """
    if language not in PARTICIPLES:
        return []
    auxiliary, endings = PARTICIPLES[language]
    longest_first = sorted(endings, key=len, reverse=True)
    wrong = []
    for word, gender in SCREEN_NOUNS[language]:
        for determiner in DETERMINERS[language][gender]:
            pattern = re.compile(
                rf"\b{determiner}\s+{re.escape(word)}\s+{auxiliary}\s+([a-zà-ÿ]+)\b",
                re.IGNORECASE,
            )
            for match in pattern.finditer(text):
                form = match.group(1).lower()
                ending = next((e for e in longest_first if form.endswith(e)), None)
                if ending is not None and endings[ending] != gender:
                    wrong.append(f"{word}: {match.group(0)}")
    return wrong


@pytest.mark.parametrize("language", sorted(SCREEN_NOUNS))
def test_screen_nouns_keep_their_gender(language: str) -> None:
    """Een schermwoord houdt zijn geslacht, in de gids én in het vertaalbestand.

    Zie de docstring boven de lijsten: getoetst worden het lidwoord, het
    onbepaald lidwoord en het aanwijzend voornaamwoord direct vóór het woord, het
    wederkerend voornaamwoord in dezelfde zin wanneer daar precies één
    schermwoord in staat, en het voltooid deelwoord wanneer het schermwoord met
    zijn eigen lidwoord direct vóór het hulpwerkwoord staat. De zes gidsen en de
    zeven vertaalbestanden zijn de teksten die een gebruiker leest; een fout
    geslacht staat daar letterlijk op het scherm.

    A screen word keeps its gender, in the guide and in the translation file.
    See the docstring above the lists: what is checked is the determiner directly
    before the word, the reflexive pronoun in the same sentence when exactly
    one screen word stands in it, and the past participle when the screen word
    with its own determiner stands directly before the auxiliary.
    """
    problems: list[str] = []
    for where, texts in texts_of(language).items():
        for text in texts:
            for word, gender in SCREEN_NOUNS[language]:
                for found in wrong_determiners(language, text, word, gender):
                    problems.append(f"{where}: {found!r} — {word!r} is {gender}")
            for found in wrong_reflexives(language, text):
                problems.append(f"{where}: {found}")
            for found in wrong_participles(language, text):
                problems.append(f"{where}: {found}")
    assert not problems, "een schermwoord houdt zijn geslacht:\n" + "\n".join(problems)
