"""De beschrijving en de gids zeggen wat een bewoner zonder slaapsensor met het wachten doet.

The description and the guide say what a resident without a sleep sensor does to the waiting.

Het huis gaat pas slapen als iedereen die thuis is slaapt, en wie geen slaapsensor heeft
slaapt nooit (`engine/night.py::asleep_at`). Woont er zo iemand thuis, dan gaat dat huis
nooit slapen en wacht het 's ochtends op niemand, wat een ander ook bij *Wacht op deze
slaper tot* invult: dat veld doet dan niets. Dat gevolg hoort de gebruiker te lezen op de
plek waar hij het veld instelt - de beschrijving van dat veld - en in de handleiding, en
het staat er in elke taal. Deze bewaking eist dat: één naald per taal, in de beschrijving
en in de alinea over het wachten in de gids.

The house only goes to sleep once everybody at home is asleep, and whoever has no sleep
sensor never sleeps (`engine/night.py::asleep_at`). With such a resident at home that
house never goes to sleep and waits for nobody in the morning, whatever somebody else
fills in at *Wait for this sleeper until*: that field then does nothing. The user should
read that consequence where he sets the field - the description of that field - and in
the manual, and it stands there in every language. This guard demands that: one needle per
language, in the description and in the guide's paragraph about the waiting.

Dekking: de beschrijving van `options.step.resident.data_description.wake_by` in
`strings.json` en in de zes vertaalbestanden, en de alinea onder de kop van het wachten in
de zes gidsen, elk tegen één naald per taal - de zin dat een bewoner zonder slaapsensor
nooit slaapt en dat een huis met zo iemand dus nooit gaat slapen en 's ochtends op niemand
wacht. De naald stopt vóór de naam van de rem, zodat de vetgedrukte naam in de gids en de
geciteerde naam in de beschrijving er allebei buiten vallen, en in de gids wordt de alinea
eerst witruimte-genormaliseerd, zodat een afgebroken regel de naald niet mist. Niet gedekt:
of de rest van de beschrijving en van de alinea klopt, of de zin ergens anders in dat
bestand staat en niet in de alinea zelf (de gids wordt per alinea gelezen, de beschrijving
per sleutel), en of het gedrag zelf klopt - dat meten `tests/test_the_night.py` en
`tests/test_early_riser.py`.

Coverage: the description of `options.step.resident.data_description.wake_by` in
`strings.json` and in the six translation files, and the paragraph under the waiting
heading in the six guides, each against one needle per language - the sentence that a
resident without a sleep sensor never sleeps and that a house with such a resident
therefore never goes to sleep and waits for nobody in the morning. The needle stops before
the brake's name, so the bold name in the guide and the quoted name in the description both
fall outside it, and in the guide the paragraph is whitespace-normalised first, so a broken
line does not make the needle miss. Not covered: whether the rest of the description and of
the paragraph is right, whether the sentence stands elsewhere in that file rather than in
the paragraph itself (the guide is read per paragraph, the description per key), and
whether the behaviour itself is right - `tests/test_the_night.py` and
`tests/test_early_riser.py` measure that.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "climate_director"
TRANSLATIONS = COMPONENT / "translations"
STRINGS = COMPONENT / "strings.json"
INSTALL = ROOT / "docs" / "install"

LANGUAGES = ("en", "nl", "de", "es", "fr", "ar")

#: Per taal de naald: de zin dat een bewoner zonder slaapsensor nooit slaapt, en dat een
#: huis met zo iemand dus nooit gaat slapen en 's ochtends op niemand wacht. De naald stopt
#: vóór de naam van de rem, want die staat in de gids vet en in de beschrijving tussen
#: aanhalingstekens.
#:
#: Per language the needle: the sentence that a resident without a sleep sensor never
#: sleeps, and that a house with such a resident therefore never goes to sleep and waits for
#: nobody in the morning. The needle stops before the brake's name, since that stands in
#: bold in the guide and between quotation marks in the description.
NEEDLES: dict[str, str] = {
    "en": (
        "A resident at home without a sleep sensor never sleeps, and a house with one never "
        "goes to sleep: it waits for nobody in the morning"
    ),
    "nl": (
        "Een bewoner die thuis is zonder slaapsensor slaapt nooit, en een huis met zo iemand "
        "gaat nooit slapen: het wacht 's ochtends op niemand"
    ),
    "de": (
        "Wer zu Hause keinen Schlafsensor hat, schläft nie, und ein Haus mit so jemandem geht "
        "nie schlafen: es wartet morgens auf niemanden"
    ),
    "es": (
        "Un residente en casa sin sensor de sueño nunca duerme, y una casa con alguien así "
        "nunca se duerme: por la mañana no espera a nadie"
    ),
    "fr": (
        "Un occupant à la maison sans capteur de sommeil ne dort jamais, et une maison avec un "
        "tel occupant ne s'endort jamais : elle n'attend personne le matin"
    ),
    "ar": (
        "والساكن في المنزل بلا مستشعر نوم لا ينام أبدًا، ومنزل فيه شخص كهذا لا ينام أبدًا: "
        "فلا ينتظر أحدًا في الصباح"
    ),
}

#: De kop boven de alinea over het wachten, per taal; daar zoekt de gidsnaald in.
#:
#: The heading above the paragraph about the waiting, per language; the guide needle is
#: looked for there.
HEADINGS: dict[str, str] = {
    "en": "### Waiting for the last sleeper",
    "nl": "### Wachten op de laatste slaper",
    "de": "### Auf den letzten Schläfer warten",
    "es": "### Esperar al último que duerme",
    "fr": "### Attendre le dernier dormeur",
    "ar": "### انتظار آخر النائمين",
}


def flattened(text: str) -> str:
    """Return the text with every run of whitespace as one space."""
    return re.sub(r"\s+", " ", text)


def descriptions(language: str) -> dict[str, str]:
    """Return the description of *Wait for this sleeper until* per text file of that language.

    Voor het Engels worden twee bestanden gelezen: `strings.json` is de bron die Home
    Assistant zelf leest, en `translations/en.json` is wat de gebruiker in de lijst ziet.

    For English two files are read: `strings.json` is the source Home Assistant itself
    reads, and `translations/en.json` is what the user sees in the list.
    """
    files: dict[str, Path] = {}
    if language == "en":
        files["strings.json"] = STRINGS
    files[f"translations/{language}.json"] = TRANSLATIONS / f"{language}.json"
    found: dict[str, str] = {}
    for name, path in files.items():
        data = json.loads(path.read_text(encoding="utf-8"))
        found[name] = data["options"]["step"]["resident"]["data_description"]["wake_by"]
    return found


def waiting_paragraph(language: str) -> str:
    """Return the guide's paragraph about the waiting, from its heading to the next one."""
    lines = (INSTALL / f"{language}.md").read_text(encoding="utf-8").splitlines()
    heading = HEADINGS[language]
    assert heading in lines, f"{language}.md heeft de kop {heading!r} niet"
    start = lines.index(heading) + 1
    following = next(
        (number for number, line in enumerate(lines[start:], start) if line.startswith("### ")),
        len(lines),
    )
    return flattened(" ".join(lines[start:following]))


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_description_names_the_sleep_sensor(language: str) -> None:
    """De beschrijving van *Wacht op deze slaper tot* noemt het gevolg van geen slaapsensor.

    Every description of *Wait for this sleeper until* names the consequence of a resident
    without a sleep sensor.
    """
    needle = NEEDLES[language]
    for name, value in descriptions(language).items():
        assert needle in flattened(value), (
            f"{name}: de beschrijving van *Wacht op deze slaper tot* mist de zin over de "
            f"bewoner zonder slaapsensor: {needle!r}"
        )


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_guide_names_the_sleep_sensor(language: str) -> None:
    """De alinea over het wachten in de gids noemt hetzelfde gevolg.

    The guide's paragraph about the waiting names the same consequence.
    """
    needle = NEEDLES[language]
    assert needle in waiting_paragraph(language), (
        f"docs/install/{language}.md: de alinea over het wachten mist de zin over de bewoner "
        f"zonder slaapsensor: {needle!r}"
    )
