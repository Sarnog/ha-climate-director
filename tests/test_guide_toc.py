"""De inhoudsopgave van elke gids noemt elk kopje, en elke link wijst ergens heen.

Wie in de gids een hoofdstuk zoekt, klikt in de inhoudsopgave. Ontbreekt daar een
kopje, dan bestaat dat hoofdstuk voor de lezer niet; staat er een link in die
nergens heen wijst, dan lijkt de gids stuk. De gidsentest hiernaast telt de kopjes
en de woorden, maar niet of de inhoudsopgave compleet en kloppend is.

De anketteksten rekent deze test zelf uit met de regels die GitHub gebruikt, zodat
er geen handlijstje met ankers nodig is dat stil kan verouderen:

1. zet het kopje om naar kleine letters;
2. laat letters, cijfers, underscores, koppeltekens en spaties staan, en haal al
   het andere leesteken weg - dus ook de em-dash `—` en de apostrof `'`;
3. vervang elke spatie door een koppelteken.

Een em-dash tussen twee spaties laat daardoor twee koppeltekens achter
(`Stap 1 — Installeren` wordt `stap-1--installeren`), een apostrof verdwijnt
zonder spoor (`Gebruiksscenario's` wordt `gebruiksscenarios`) en Arabische letters
blijven staan (`متابعة تجاوز بمدة على لوحة التحكم` wordt
`متابعة-تجاوز-بمدة-على-لوحة-التحكم`). Die drie gevallen staan hieronder letterlijk
in de test, zodat een wijziging in de slugregels opvalt.

Every guide's table of contents names every heading, and every link points
somewhere.

A reader looking for a chapter clicks in the table of contents. If a heading is
missing there, that chapter does not exist for the reader; if a link points
nowhere, the guide looks broken. The guide test beside this one counts the headings
and the words, but not whether the table of contents is complete and correct.

This test computes the anchor texts itself with the rules GitHub uses, so no
hand-written list of anchors is needed that can quietly go stale:

1. turn the heading into lower case;
2. keep letters, digits, underscores, hyphens and spaces, and drop every other
   punctuation mark - including the em dash `—` and the apostrophe `'`;
3. replace every space with a hyphen.

An em dash between two spaces therefore leaves two hyphens behind (`Stap 1 —
Installeren` becomes `stap-1--installeren`), an apostrophe vanishes without a
trace (`Gebruiksscenario's` becomes `gebruiksscenarios`) and Arabic letters stay
(`متابعة تجاوز بمدة على لوحة التحكم` becomes `متابعة-تجاوز-بمدة-على-لوحة-التحكم`).
Those three cases stand literally in the test below, so a change in the slug rules
stands out.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "docs" / "install"

LANGUAGES = ("en", "nl", "de", "es", "fr", "ar")

HEADING = re.compile(r"^## (.+)$", flags=re.MULTILINE)
LINK = re.compile(r"^- \[(.+?)\]\(#(.+?)\)$", flags=re.MULTILINE)

#: Drie kopjes waar de slugregels iets doen dat je niet raadt, met de gids waarin
#: ze staan en het anker dat GitHub ervan maakt. Letterlijk, zodat de regels
#: meetbaar blijven in plaats van aangenomen.
#:
#: Three headings where the slug rules do something you would not guess, with the
#: guide they stand in and the anchor GitHub makes of them. Literal, so the rules
#: stay measurable instead of assumed.
SLUG_CASES = (
    ("nl", "Stap 1 — Installeren", "stap-1--installeren"),
    ("nl", "Gebruiksscenario's", "gebruiksscenarios"),
    ("fr", "Cas d'utilisation", "cas-dutilisation"),
    ("ar", "متابعة تجاوز بمدة على لوحة التحكم", "متابعة-تجاوز-بمدة-على-لوحة-التحكم"),
)


def slug(heading: str) -> str:
    """De ankettekst die GitHub van een kopje maakt.

    The anchor text GitHub makes of a heading.
    """
    text = re.sub(r"[^\w\- ]", "", heading.strip().lower(), flags=re.UNICODE)
    return text.replace(" ", "-")


def guide_text(language: str) -> str:
    """De volledige tekst van de gids van die taal.

    The full text of that language's guide.
    """
    return (INSTALL / f"{language}.md").read_text(encoding="utf-8")


def headings(language: str) -> list[str]:
    """Elk `## `-kopje van die gids, in bestandsorde.

    Every `## ` heading of that guide, in file order.
    """
    return HEADING.findall(guide_text(language))


def toc_section(language: str) -> str:
    """Het stuk van het inhoudskopje tot het volgende kopje.

    The part from the contents heading up to the next heading.
    """
    text = guide_text(language)
    start = text.index(f"## {headings(language)[0]}")
    end = text.index("\n## ", start + 1)
    return text[start:end]


def toc_links(language: str) -> list[tuple[str, str]]:
    """De links in de inhoudsopgave, als (label, anker).

    The links in the table of contents, as (label, anchor).
    """
    return LINK.findall(toc_section(language))


def test_the_slug_rules_are_the_github_ones() -> None:
    """De uitgerekende anketteksten kloppen met de gidsen zelf.

    The computed anchor texts match the guides themselves.
    """
    for language, heading, anchor in SLUG_CASES:
        assert slug(heading) == anchor, f"{heading!r} horen we als {anchor!r} te zien"
        assert heading in headings(language), f"{language}.md heeft het kopje {heading!r} niet"
        assert (heading, anchor) in toc_links(language), (
            f"{language}.md linkt {heading!r} niet naar #{anchor}"
        )


def test_every_guide_has_a_table_of_contents_first() -> None:
    """Het eerste kopje van elke gids is de inhoudsopgave zelf.

    The first heading of every guide is the table of contents itself.
    """
    for language in LANGUAGES:
        found = headings(language)
        assert found, f"{language}.md heeft geen kopjes"
        assert len(toc_links(language)) >= 20, (
            f"{language}.md: de inhoudsopgave lijkt leeg ({len(toc_links(language))} links)"
        )


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_heading_stands_in_the_table_of_contents(language: str) -> None:
    """Elk kopje behalve de inhoudsopgave zelf heeft precies één link erin.

    Every heading except the table of contents itself has exactly one link in it.
    """
    found = headings(language)
    toc_heading = found[0]
    links = toc_links(language)
    labels = [label for label, _ in links]
    problems: list[str] = []
    for heading in found:
        if heading == toc_heading:
            continue
        if labels.count(heading) != 1:
            problems.append(f"{heading!r} staat {labels.count(heading)}x in de inhoudsopgave")
    for label, anchor in links:
        if label not in found:
            problems.append(f"de link {label!r} hoort bij geen enkel kopje")
        elif slug(label) != anchor:
            problems.append(f"de link {label!r} wijst naar #{anchor} en hoort naar #{slug(label)}")
    assert not problems, f"{language}.md: de inhoudsopgave klopt niet met de kopjes:\n" + "\n".join(
        problems
    )
