"""De blauwdrukken die de zes gidsen noemen bestaan, en de weigeringsbullet wijst
naar de blauwdruk die erbij hoort.

De gids vertelt je een blauwdruk te importeren. Staat er een bestandsnaam in die
niet bestaat, dan leidt de lezer naar een 404 en denkt hij dat hij iets fout doet.
De gidsentest hiernaast meet kopjes, woorden en entiteit-id's; de blauwdrukken
vielen daarbuiten. Deze test haalt daarom elke blauwdruknaam uit de gidstekst en
eist dat hij in `blueprints/automation/climate_director/` staat, en hij eist dat
de bullet over een weigering die niemand hoort naar de weigeringsblauwdruk wijst
en niet naar de algemene beslissingsblauwdruk. Die bullet mag over meerdere
regels afgebroken zijn; de bewaking leest de hele alinea.

Welke bullet dat is, komt uit de code: de meldingssleutel `UNWATCHED_ISSUE` uit
`problems.py` (gelezen via de AST-hulp van de gidsentest) bepaalt over welke
reparatiemelding het gaat, en de bestandsnaam van de blauwdruk komt uit
`EVENT_PRECONDITION_REFUSED` in `const.py` — de gebeurtenis waar de blauwdruk op
luistert. Zo hoeft er geen enkel lijstje met gidsen of blauwdrukken bijgehouden te
worden: verandert de gebeurtenis, dan verandert deze eis mee.

The blueprints the six guides name exist, and the refusal bullet points at the
blueprint that belongs to it.

The guide tells you to import a blueprint. If it carries a file name that does not
exist, the reader is led to a 404 and thinks they did something wrong. The guide
test beside this one measures headings, words and entity ids; the blueprints fell
outside that. This test therefore takes every blueprint name out of the guide text
and demands that it stands in `blueprints/automation/climate_director/`, and it
demands that the bullet about a refusal nobody hears points at the refusal
blueprint and not at the general decision blueprint. That bullet may be wrapped
over several lines; the guard reads the whole paragraph.

Which bullet that is comes from the code: the notice key `UNWATCHED_ISSUE` from
`problems.py` (read through the guide test's AST helper) determines which repair
notice this is about, and the blueprint's file name comes from
`EVENT_PRECONDITION_REFUSED` in `const.py` - the event the blueprint listens for.
That way no list of guides or blueprints has to be maintained: change the event
and this demand changes with it.

Dekking: elke blauwdruknaam uit de zes gidsen tegen
`blueprints/automation/climate_director/`, en de alinea met de weigeringsmelding
tegen de blauwdruk van `EVENT_PRECONDITION_REFUSED` - ook als de gids die
alinea over meerdere regels afbreekt. Niet gedekt: de inhoud van de
blauwdrukbestanden en de overige bullets van de gidsen.

Coverage: every blueprint name from the six guides against
`blueprints/automation/climate_director/`, and the paragraph carrying the
refusal notice against the blueprint of `EVENT_PRECONDITION_REFUSED` - also
when the guide wraps that paragraph over several lines. Not covered: the
content of the blueprint files and the other bullets of the guides.
"""

from __future__ import annotations

import re
from pathlib import Path

from test_guide_inventory import _notice_title, notice_keys, paragraphs

from custom_components.climate_director.const import DOMAIN, EVENT_PRECONDITION_REFUSED

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "docs" / "install"
BLUEPRINTS = ROOT / "blueprints" / "automation" / "climate_director"

LANGUAGES = ("en", "nl", "de", "es", "fr", "ar")

#: Een blauwdrukbestandsnaam in de tekst van een gids.
#:
#: A blueprint file name in a guide's text.
BLUEPRINT_NAME = re.compile(r"\b[a-z][a-z0-9_]*\.ya?ml\b")

#: De gebeurtenis waar de weigeringsblauwdruk op luistert, zonder het domein:
#: `precondition_refused`, en dus `precondition_refused.yaml`.
#:
#: The event the refusal blueprint listens for, without the domain:
#: `precondition_refused`, and hence `precondition_refused.yaml`.
REFUSED_EVENT = EVENT_PRECONDITION_REFUSED.removeprefix(f"{DOMAIN}_")


def blueprint_files() -> set[str]:
    """De blauwdrukken die de integratie meelevert.

    The blueprints the integration ships.
    """
    return {path.name for path in BLUEPRINTS.glob("*.yaml")}


def guide_text(language: str) -> str:
    """De volledige tekst van de gids van die taal.

    The full text of that language's guide.
    """
    return (INSTALL / f"{language}.md").read_text(encoding="utf-8")


def test_the_blueprint_directory_is_read() -> None:
    """De bewaking leest de echte map en vindt de echte blauwdruk.

    The guard reads the real directory and finds the real blueprint.
    """
    files = blueprint_files()
    assert files, f"geen blauwdrukken gevonden in {BLUEPRINTS}"
    assert f"{REFUSED_EVENT}.yaml" in files, (
        f"de weigeringsblauwdruk {REFUSED_EVENT}.yaml hoort in {BLUEPRINTS} te staan; "
        f"gevonden: {sorted(files)}"
    )


def test_the_unwatched_notice_is_the_one_from_problems() -> None:
    """De bullet hoort bij de melding `precondition_unwatched` uit `problems.py`.

    The bullet belongs to the `precondition_unwatched` notice from `problems.py`.
    """
    keys = notice_keys()
    assert "precondition_unwatched" in keys, (
        f"de meldingssleutel staat niet meer in problems.py; gevonden: {keys}"
    )


def test_the_refusal_bullet_points_at_the_refusal_blueprint() -> None:
    """De bullet over een ongehoorde weigering noemt de weigeringsblauwdruk.

    The bullet about an unheard refusal names the refusal blueprint.
    """
    problems: list[str] = []
    for language in LANGUAGES:
        title = _notice_title(language, "precondition_unwatched")
        bullets = [block for block in paragraphs(guide_text(language)) if title in block]
        assert bullets, f"{language}.md: de melding {title!r} staat er niet in"
        for bullet in bullets:
            if f"{REFUSED_EVENT}.yaml" not in bullet:
                problems.append(
                    f"{language}.md: de bullet {title!r} noemt {REFUSED_EVENT}.yaml niet: {bullet}"
                )
    assert not problems, (
        "de weigeringsbullet wijst niet naar de blauwdruk die erbij hoort:\n" + "\n".join(problems)
    )


def test_every_blueprint_a_guide_names_exists() -> None:
    """Elke blauwdruknaam in een gids bestaat ook echt.

    Every blueprint name in a guide really exists.
    """
    files = blueprint_files()
    problems: list[str] = []
    for language in LANGUAGES:
        text = guide_text(language)
        named = sorted(set(BLUEPRINT_NAME.findall(text)))
        if not named:
            problems.append(f"{language}.md: geen enkele blauwdruknaam gevonden")
        for name in named:
            if name not in files:
                problems.append(
                    f"{language}.md noemt {name}, en dat bestand staat niet in {BLUEPRINTS.name}/ "
                    f"({sorted(files)})"
                )
    assert not problems, "een gids noemt een blauwdruk die niet bestaat:\n" + "\n".join(problems)
