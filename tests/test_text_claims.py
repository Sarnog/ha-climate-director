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

De naald is een **zinsdeel**, geen hele zin: zonder hoofdletter en zonder
leesteken, en de vergelijking is hoofdletterongevoelig. Een hele zin als naald
mist dezelfde bewering in een andere zinsbouw - gemeten: "a holiday counts as a
Saturday for this time too" bleef groen naast de naald "A holiday counts as a
Saturday.". Naast elke naald staat daarom een letterlijke lijst **toegestane
contexten**: de zinsneden waarin dat zinsdeel wel mag staan, omdat ze het tegendeel
zeggen of over iets anders gaan. Een treffer telt alleen buiten zo'n context, en
elke toegestane context moet werkelijk in de teksten staan - een context die
nergens meer voorkomt is een verouderde vergunning en is rood.

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

The needle is a **phrase**, not a whole sentence: without a capital and without
punctuation, and the comparison is case-insensitive. A whole sentence as a needle
misses the same claim in another sentence shape - measured: "a holiday counts as a
Saturday for this time too" stayed green beside the needle "A holiday counts as a
Saturday.". Beside every needle therefore stands a literal list of **allowed
contexts**: the phrases in which that fragment may stand, because they say the
opposite or are about something else. A hit counts only outside such a context, and
every allowed context has to really stand in the texts - a context that occurs
nowhere any more is a stale permission and is red.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
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
    allowed: dict[str, tuple[str, ...]] = field(default_factory=dict)


#: Elke ingetrokken bewering, met per taal het zinsdeel dat niet meer mag
#: voorkomen en de letterlijke contexten waarin het wel mag. Alleen groter worden,
#: met een reden.
#:
#: Every retracted claim, with the fragment per language that may no longer occur
#: and the literal contexts in which it may. Only ever larger, with a reason.
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
            "nl": "telt als zaterdag",
            "en": "counts as a saturday",
            "strings": "counts as a saturday",
            "de": "zählt als samstag",
            "fr": "compte comme un samedi",
            "es": "cuenta como sábado",
            "ar": "يُحتسب يوم العطلة سبتًا",
        },
        allowed={
            "nl": ("elke dag telt als zaterdag",),
            "en": (
                "A holiday counts as a Saturday for the schedules",
                "Without one, a holiday counts as a Saturday",
            ),
            "strings": (
                "A holiday counts as a Saturday for the schedules",
                "Without one, a holiday counts as a Saturday",
            ),
            "de": ("Jeder Tag zählt als Samstag",),
            "fr": ("un jour de vacances compte comme un samedi",),
            "es": (
                "cuenta como sábado para los horarios",
                "no cuenta como sábado",
            ),
            "ar": (
                "يُحتسب يوم العطلة سبتًا في الجداول",
                "وبدونها يُحتسب يوم العطلة سبتًا",
            ),
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
            "nl": "ingestelde tijden",
            "en": "configured hours",
            "strings": "configured hours",
            "de": "eingestellten zeiten",
            "fr": "heures réglées",
            "es": "horas configuradas",
            "ar": "الأوقات المضبوطة",
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


def blanked(text: str, contexts: tuple[str, ...]) -> str:
    """Vervang elke toegestane context door evenveel nullen.

    Replace every allowed context with as many zero characters.

    Zo blijft de positie staan en kan een treffer niet over een grens heen
    ontstaan: een zinsdeel dat binnen een toegestane context valt telt niet mee,
    en een zinsdeel dat erbuiten valt wel.

    That keeps the position and a hit cannot arise across a boundary: a fragment
    inside an allowed context does not count, and one outside it does.
    """
    for context in contexts:
        while True:
            start = text.lower().find(context.lower())
            if start < 0:
                break
            text = text[:start] + chr(0) * len(context) + text[start + len(context) :]
    return text


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
    """Deze ingetrokken bewering staat in geen enkel bestand en in geen enkele gids.

    This retracted claim stands in no file and in no guide.

    Zoekt per taal het zinsdeel hoofdletterongevoelig in alle teksten, buiten de
    toegestane contexten van die taal. Een treffer noemt het bestand, de taal en
    het zinsdeel, plus de reden en het anker, zodat de volgende lezer weet waarom
    deze regel bestaat zonder in de geschiedenis te duiken. Een toegestane context
    die nergens meer staat is zelf een treffer: een vergunning zonder tekst is
    verouderd.

    Searches each language's phrase case-insensitively in every text, outside that
    language's allowed contexts. A hit names the file, the language and the
    phrase, plus the reason and the anchor, so the next reader knows why this rule
    exists without digging into history. An allowed context that no longer stands
    anywhere is itself a hit: a permission without a text is stale.
    """
    texts = corpus()
    found: list[str] = []
    for language, needle in claim.needles.items():
        contexts = claim.allowed.get(language, ())
        for context in contexts:
            if not any(context.lower() in text.lower() for text in texts.values()):
                found.append(f"toegestane context staat nergens meer: [{language}] {context!r}")
        for where, text in texts.items():
            if needle.lower() in blanked(text, contexts).lower():
                found.append(f"{where} [{language}]: {needle!r}")
    assert not found, (
        f"deze bewering is ingetrokken ({claim.reason}); hij hoort nergens meer te staan "
        f"({claim.anchor}):" + chr(10).join(["", *found])
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
