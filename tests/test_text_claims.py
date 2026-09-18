"""Ingetrokken beweringen: zinnen die de interface niet meer mag dragen.

Dit is een **ratel van afgeschafte mechanismen**. Elke regel hieronder is een zin
die ooit waar was en het niet meer is, met per taal de letterlijke zinsnede en
de reden erbij plus het anker dat die zin weerspreekt. De test eist dat geen van
de zeven tekstbestanden én geen van de zes handleidingen zo'n zinsnede nog
draagt: een bewering die na een gedragswijziging blijft staan, is precies wat een
gebruiker op het verkeerde been zet en wat hij niet kan narekenen.

De lijst mag daarom **alleen groeien met een reden**: wie er een regel bij zet,
schrijft op waarom de zin niet meer waar is en welk anker of welke meting hem
weerspreekt. Er gaat geen regel af omdat een tekst toevallig veranderd is — dan
is de zin blijkbaar nog ergens anders blijven staan.

Waarom dit een tekstbewaking is en geen eigenschapsmeting: de eigenschap is
letterlijk "deze zinsnede komt nergens meer voor". Die is alleen op de tekst zelf
te meten; er is geen runtime-object dat hem kan weerspreken. De bewaking zoekt in
de *waarden* van de zeven bestanden (via `json`, niet met een eigen parser) en in
de volledige tekst van de zes handleidingen, zodat een escape als `\\u00e9` er
niet langs glipt.

Retracted claims: sentences the interface may no longer carry.

This is a **ratchet of abolished mechanisms**. Every line below is a sentence
that was once true and no longer is, with the literal phrase per language, the
reason beside it and the anchor that contradicts it. The test demands that none
of the seven text files and none of the six guides still carry such a phrase: a
claim left standing after a behaviour change is exactly what puts a user on the
wrong foot, and what they cannot check for themselves.

The list may therefore **only grow with a reason**: whoever adds a line writes
down why the sentence is no longer true and which anchor or measurement
contradicts it. No line comes off because a text happened to change — then the
sentence is apparently still standing somewhere else.

Why this is a text guard and not a property measurement: the property is
literally "this phrase no longer occurs anywhere". That can only be measured on
the text itself; no runtime object can contradict it. The guard searches the
*values* of the seven files (through `json`, not with a parser of its own) and
the full text of the six guides, so an escape such as `\\u00e9` cannot slip past.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "climate_director"
INSTALL = ROOT / "docs" / "install"

LANGUAGES = ("en", "nl", "de", "es", "fr", "ar")

TEXT_FILES = {
    "strings": COMPONENT / "strings.json",
    **{language: COMPONENT / "translations" / f"{language}.json" for language in LANGUAGES},
}


@dataclass(frozen=True)
class Claim:
    """Eén ingetrokken bewering.

    One retracted claim.
    """

    name: str
    reason: str
    anchor: str
    needles: dict[str, str]


#: Elke ingetrokken bewering, met per taal de letterlijke zinsnede die niet meer
#: mag voorkomen. Alleen groter worden, met een reden.
#:
#: Every retracted claim, with the literal phrase per language that may no longer
#: occur. Only ever larger, with a reason.
RETRACTED: tuple[Claim, ...] = (
    Claim(
        name="vakantiedag is geen zaterdag",
        reason=(
            "een vakantiedag telt bij de uiterste opsta-tijd niet als zaterdag: anders houdt "
            "de schoolvakantie van de één het huis op terwijl de ander thuis werkt"
        ),
        anchor=(
            "`Resident.waits_until` in `engine/models.py` leest de echte weekdag; het "
            "vakantievenster van die tijd staat als aparte vlag in `WakeDeadline.holiday`"
        ),
        needles={
            "nl": "Een vakantiedag telt als zaterdag.",
            "en": "A holiday counts as a Saturday.",
            "strings": "A holiday counts as a Saturday.",
            "de": "Ein Feiertag zählt als Samstag.",
            "fr": "Un jour férié compte comme un samedi.",
            "es": "Un día festivo cuenta como sábado.",
            "ar": "كل يوم. يُحتسب يوم العطلة سبتًا.",
        },
    ),
    Claim(
        name="geen vooruit-venster",
        reason=(
            "er is geen vooruit-venster: een verzoek gaat op elk uur van de dag voor, en "
            "alleen de hoofdschakelaar, een override en een onbevestigde opening houden het tegen"
        ),
        anchor="anker 1 in `ARCHITECTURE.md` (het vooruit-verzoek kent geen tijdvenster)",
        needles={
            "nl": "telt alleen binnen de ingestelde tijden",
            "en": "only counts inside the configured hours",
            "strings": "only counts inside the configured hours",
            "de": "gilt nur in den eingestellten Zeiten",
            "fr": "ne compte que dans les heures réglées",
            "es": "solo cuenta dentro de las horas configuradas",
            "ar": "ولا يُحتسب إلا ضمن الأوقات المضبوطة",
        },
    ),
    Claim(
        name="de oude terugkeerknop",
        reason=(
            "deze knoppen bestaan niet meer sinds het bewaarscherm *Er valt iets op* heet; het "
            "oude scherm had een eigen terugkeer- en bewaarknop"
        ),
        anchor=(
            "`options.step.save.data.when_done` en `selector.when_done.options.*` in de "
            "zeven tekstbestanden"
        ),
        needles={
            "nl": "Terug naar het hoofdmenu om iets aan te passen",
            "en": "Back to the main menu to change something",
            "de": "Zurück zum Hauptmenü, um etwas zu ändern",
            "fr": "Retour au menu principal pour modifier quelque chose",
            "es": "Volver al menú principal para cambiar algo",
            "ar": "العودة إلى القائمة الرئيسية لتعديل شيء",
        },
    ),
    Claim(
        name="de oude bewaarknop",
        reason=(
            "het oude bewaarscherm had twee eigen knoppen *toch opslaan* en *terug om iets aan "
            "te passen*; die bestaan niet meer, het scherm heet *Er valt iets op* met het veld "
            "*Wat nu* en de when_done-keuzes"
        ),
        anchor=(
            "`options.step.save.title`, `options.step.save.data.when_done` en "
            "`selector.when_done.options.*` in de zeven tekstbestanden, en de sectie "
            "*Stap 12* van de zes gidsen"
        ),
        needles={
            "nl": "Toch opslaan",
            "en": "Save anyway",
            "de": "Trotzdem speichern",
            "fr": "Enregistrer quand même",
            "es": "Guardar igualmente",
            "ar": "احفظ رغم ذلك",
        },
    ),
    Claim(
        name="de oude terugkeerknop van het bewaarscherm",
        reason=(
            "het oude bewaarscherm had ook een eigen terugkeerknop; het scherm heet *Er valt iets "
            "op* en de terugkeer zit in de when_done-keuzes"
        ),
        anchor=(
            "`selector.when_done.options.discard` in de zeven tekstbestanden en de sectie "
            "*Stap 12* van de zes gidsen"
        ),
        needles={
            "nl": "Terug om iets aan te passen",
            "en": "Back to change something",
            "de": "Zurück, um etwas zu ändern",
            "fr": "Revenir pour modifier quelque chose",
            "es": "Volver para cambiar algo",
            "ar": "عُد لتغيير شيء",
        },
    ),
    Claim(
        name="de oude Spaanse bewaarknop",
        reason=(
            "de éérste versie van het bewaarscherm had een eigen bewaarknop die de wijziging "
            "toch wegschreef; die knop bestaat niet meer"
        ),
        anchor=(
            "`options.step.save.data.when_done` in de zeven tekstbestanden en de sectie "
            "*Stap 12* van de zes gidsen"
        ),
        needles={
            "es": "Guardar de todos modos",
        },
    ),
)


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


def corpus() -> dict[str, str]:
    """Alle tekst die een gebruiker kan lezen: zeven bestanden en zes gidsen.

    Every text a user can read: seven files and six guides.
    """
    found: dict[str, str] = {}
    for _name, path in TEXT_FILES.items():
        data = json.loads(path.read_text(encoding="utf-8"))
        for key, text in leaves(data).items():
            found[f"{path.name}:{key}"] = text
    for language in LANGUAGES:
        path = INSTALL / f"{language}.md"
        found[path.name] = path.read_text(encoding="utf-8")
    return found


@pytest.mark.parametrize("claim", RETRACTED, ids=lambda claim: claim.name)
def test_the_retracted_claim_is_nowhere(claim: Claim) -> None:
    """Deze ingetrokken zin staat in geen enkel bestand en in geen enkele gids.

    This retracted sentence stands in no file and in no guide.

    Zoekt per taal de letterlijke zinsnede in alle teksten. Een treffer noemt het
    bestand, de taal en de zinsnede, plus de reden en het anker, zodat de volgende
    lezer weet waarom deze regel bestaat zonder in de geschiedenis te duiken.

    Searches the literal phrase per language in every text. A hit names the file,
    the language and the phrase, plus the reason and the anchor, so the next
    reader knows why this rule exists without digging into history.
    """
    found: list[str] = []
    for where, text in corpus().items():
        for language, needle in claim.needles.items():
            if needle in text:
                found.append(f"{where} [{language}]: {needle!r}")
    assert not found, (
        f"deze zin is ingetrokken ({claim.reason}); hij hoort nergens meer te staan "
        f"({claim.anchor}):\n" + "\n".join(found)
    )


def test_the_guard_reads_seven_files_and_six_guides() -> None:
    """De bewaking leest de echte bestanden, niet een lege of verkeerde.

    The guard reads the real files, not an empty or wrong one.
    """
    texts = corpus()
    assert len(TEXT_FILES) == 7, f"verwachte zeven tekstbestanden, vond {len(TEXT_FILES)}"
    for name in TEXT_FILES:
        assert any(key.startswith(TEXT_FILES[name].name) for key in texts), f"{name} niet gelezen"
    for language in LANGUAGES:
        assert (INSTALL / f"{language}.md").exists(), f"{language}.md niet gevonden"
    assert len(RETRACTED) >= 4, "de ratel hoort de ingetrokken beweringen te dragen"
