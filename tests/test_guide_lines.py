"""Geen regel in een gids langer dan 120 tekens.

Een handleiding die je op een scherm leest hoort niet zijwaarts te scrollen, en
een gewijzigde regel hoort in een diff leesbaar te blijven. Lange alinea's zijn dus
afgebroken op een breedte van hoogstens 120 tekens, met de opening-id-alinea van
Stap 11 als strengere afspraak (hoogstens 80 tekens per regel), zodat de lezer de
draad niet kwijtraakt.

Wat hier vastligt: elke prozaregel in de zes gidsen is hoogstens 120 tekens. Niet
meegeteld: **tabelregels** (een tabel is per definitie breed en de kolommen zijn
de opmaak), **codeblokken** (inhoud die niet af te breken valt) en **regels met
een URL** (een adres mag niet in tweeën). Elf tekens aan het begin van een regel is
nergens anders mee te meten dan op de tekst zelf, dus de bewaking leest de bron.
Geen uitzonderingenlijst: de grens geldt voor alle zes de gidsen, en een nieuwe
lange regel is rood met de taal, het regelnummer en de lengte erbij.

Waarom een eigen bestand naast `test_guide_markdown.py`: dat bestand gaat over een
opsommingsteken dat per ongeluk een lijst opent, en deze bewaking over de breedte
van de regel. Twee verschillende eigenschappen, twee docstrings; ze in één bestand
zetten zou één van de twee onwaar maken.

Dekking: de zes gidsen, op regelbreedte, met tabellen, codeblokken en URL-regels
uitgezonderd. Niet gedekt: de breedte van een tabelkolom, de opmaak binnen een
codeblok, en of een afgebroken regel op een goede plek is afgebroken - dat leest de
proeflezing.

Coverage: the six guides, on line width, with tables, code blocks and URL lines
excluded. Not covered: the width of a table column, the shape inside a code block,
and whether a broken line broke in a good place - the proofreading reads that.
"""

from __future__ import annotations

from pathlib import Path

import pytest

INSTALL = Path(__file__).parent.parent / "docs" / "install"

LANGUAGES = ("en", "nl", "de", "es", "fr", "ar")

#: De breedte waarop een gids afbreekt.
#:
#: The width a guide breaks at.
MAXIMUM = 120


def long_lines(language: str) -> list[tuple[int, int]]:
    """Elke prozaregel langer dan `MAXIMUM`, met regelnummer en lengte.

    Every prose line longer than `MAXIMUM`, with its line number and length.
    """
    found: list[tuple[int, int]] = []
    fence = False
    text = (INSTALL / f"{language}.md").read_text(encoding="utf-8")
    for number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            fence = not fence
            continue
        if fence or line.lstrip().startswith("|") or "http" in line:
            continue
        if len(line) > MAXIMUM:
            found.append((number, len(line)))
    return found


@pytest.mark.parametrize("language", LANGUAGES)
def test_no_guide_line_runs_past_120_characters(language: str) -> None:
    """Geen prozaregel in een gids langer dan 120 tekens.

    No prose line in a guide runs past 120 characters.
    """
    over = long_lines(language)
    assert not over, "een gidsregel loopt te ver door:\n" + "\n".join(
        f"{language}.md:{number} is {length} tekens" for number, length in over
    )
