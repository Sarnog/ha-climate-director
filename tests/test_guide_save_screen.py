"""Stap 12 van elke gids noemt het scherm, het veld en de twee keuzes die er echt zijn.

De gids beschreef hier knoppen die niet bestaan: *Toch opslaan* en *Terug om iets
aan te passen*. Het bewaarscherm heet anders in elke taal, het veld erop ook, en
de twee keuzes zijn de opties van `selector.when_done` in die taal. Wie de gids
leest en die woorden in Home Assistant zoekt, hoort ze ook te vinden.

Deze bewaking leest de sectie die met *Stap 12* begint (het kopje met het cijfer
12 erin, in welke taal dan ook) en eist dat de titel van het scherm, de naam van
het veld en beide `when_done`-keuzes er letterlijk in staan. De woorden komen uit
het vertaalbestand van die taal, niet uit een lijstje hier: verandert de interface
van woord, dan verandert deze eis mee.

Step 12 of every guide names the screen, the field and the two choices that really
exist.

The guide used to describe buttons that do not exist: *Save anyway* and *Back to
change something*. The save screen has a different name in every language, so does
the field on it, and the two choices are the options of `selector.when_done` in
that language. Whoever reads the guide and looks for those words in Home Assistant
should find them.

This guard reads the section starting with *Step 12* (the heading carrying the
number 12, whatever the language) and demands that the screen's title, the field's
name and both `when_done` choices stand in it literally. The words come from that
language's translation file, not from a list here: change the interface wording and
this demand changes with it.

Dekking: stap 12 van de zes gidsen tegen het scherm, het veld en de twee
`when_done`-keuzes uit dat taals vertaalbestand. Niet gedekt: de andere stappen
(`tests/test_install_guides.py`), de inhoudsopgave (`tests/test_guide_toc.py`) en
de schermen van de flow zelf - die staan in de live campagnes, niet in een tekst.

Coverage: step 12 of the six guides against the screen, the field and the two
`when_done` choices from that language's translation file. Not covered: the other
steps (`tests/test_install_guides.py`), the table of contents
(`tests/test_guide_toc.py`) and the flow's own screens - those live in the live
campaigns, not in a text.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "docs" / "install"
TRANSLATIONS = ROOT / "custom_components" / "climate_director" / "translations"

LANGUAGES = ("en", "nl", "de", "es", "fr", "ar")

#: Het kopje van Stap 12, in welke taal dan ook: een `## `-kopje met het getal 12.
#:
#: The Step 12 heading, in whatever language: a `## ` heading with the number 12.
STEP_TWELVE = re.compile(r"^## .*\b12\b.*$", re.MULTILINE)


def guide_text(language: str) -> str:
    """De volledige tekst van de gids van die taal.

    The full text of that language's guide.
    """
    return (INSTALL / f"{language}.md").read_text(encoding="utf-8")


def translation(language: str) -> dict:
    """Het vertaalbestand van die taal.

    That language's translation file.
    """
    return json.loads((TRANSLATIONS / f"{language}.json").read_text(encoding="utf-8"))


def step_twelve(language: str) -> str:
    """De sectie van Stap 12, van het kopje tot het volgende kopje.

    The Step 12 section, from the heading up to the next heading.
    """
    text = guide_text(language)
    matches = list(STEP_TWELVE.finditer(text))
    assert len(matches) == 1, (
        f"{language}.md: verwacht precies één kopje met het getal 12, gevonden "
        f"{[match.group(0) for match in matches]}"
    )
    start = matches[0].start()
    end = text.find("\n## ", start + 1)
    return text[start : end if end != -1 else len(text)]


def test_the_step_twelve_heading_is_found_in_every_guide() -> None:
    """De bewaking vindt het kopje in alle zes de talen.

    The guard finds the heading in all six languages.
    """
    for language in LANGUAGES:
        section = step_twelve(language)
        assert len(section) > 200, f"{language}.md: Stap 12 lijkt leeg"


@pytest.mark.parametrize("language", LANGUAGES)
def test_step_twelve_names_the_screen_the_field_and_the_choices(language: str) -> None:
    """Stap 12 noemt het scherm, het veld en beide keuzes letterlijk.

    Step 12 names the screen, the field and both choices literally.
    """
    data = translation(language)
    screen = data["options"]["step"]["save"]["title"]
    field = data["options"]["step"]["save"]["data"]["when_done"]
    choices = list(data["selector"]["when_done"]["options"].values())
    assert len(choices) == 2, f"{language}: verwacht twee when_done-keuzes, vond {choices}"

    section = step_twelve(language)
    missing = [word for word in (screen, field, *choices) if word not in section]
    assert not missing, (
        f"{language}.md: Stap 12 noemt {missing} niet, terwijl Home Assistant die woorden "
        f"wel gebruikt"
    )
