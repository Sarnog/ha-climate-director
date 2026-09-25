"""Een opsommingsteken midden in een alinea is geen lijstitem.

Markdown maakt van elke regel die met `- ` of `* ` begint een lijstitem, ook
midden in een alinea. Valt een gedachtestreepje op de regelgrens, dan verandert
de lopende tekst stil in een opsomming: de lezer ziet opeens een bolletje waar
een gedachtestreepje hoorde. Precies dat gebeurde in de Franse en de Spaanse gids
(`fr.md` en `es.md`, Stap 10), en aan de brontekst is het niet te zien.

Wat hier vastligt: een regel die met `- ` of `* ` begint is alleen een lijstitem
als hij ergens bij hoort - de regel erboven is leeg, de regel erboven is zelf een
item, of tussen de twee staat niets dan de ingesprongen uitloop van een item.
Anders is het proza dat per ongeluk als opsomming rendert, en dat is rood met de
taal en het regelnummer erbij.

De bewaking dekt beide opsommingstekens (`- ` en `* `), op elke inspringing, in
de zes gidsen; codeblokken en tabelregels tellen niet mee, want in een codeblok is
`- ` gewone inhoud en een tabelregel begint met `|`. Elf tekens aan het begin van
een regel is nergens anders mee te meten dan op de tekst zelf, dus de bewaking
leest de bron; wat hij dekt staat hier opgesomd en de eis eronder is de
structurele kant: elke regel die een item opent moet aansluiten op wat erboven
staat.

Waarom een eigen bestand naast `test_guide_toc.py`: dat bestand bewaakt de
inhoudsopgave (elk kopje een link, elke link een kopje) en deze bewaking gaat over
de opbouw van de tekst zelf. Twee verschillende eigenschappen, twee docstrings;
ze in één bestand zetten zou één van de twee onwaar maken.

A list marker in the middle of a paragraph is not a list item.

Markdown turns every line starting with `- ` or `* ` into a list item, even in
the middle of a paragraph. When a thought dash falls on a line boundary the
running text quietly turns into a list: the reader suddenly sees a bullet where a
dash belonged. Exactly that happened in the French and Spanish guides (`fr.md`
and `es.md`, Step 10), and it cannot be seen in the source text.

What this pins down: a line starting with `- ` or `* ` is a list item only when
it belongs somewhere - the line above is empty, the line above is itself an item,
or between the two there is nothing but an item's indented tail. Otherwise it is
prose that accidentally renders as a list, and that is red with the language and
the line number alongside.

The guard covers both markers (`- ` and `* `), at any indentation, in the six
guides; code blocks and table rows do not count, because inside a code block `- `
is ordinary content and a table row starts with `|`. Eleven characters at the
start of a line can be measured nowhere but on the text itself, so the guard reads
the source; what it covers is listed here and the demand beside it is the
structural side: every line that opens an item has to connect to what stands
above it.

Why a file of its own beside `test_guide_toc.py`: that file guards the table of
contents (every heading a link, every link a heading) while this guard is about
the structure of the text itself. Two different properties, two docstrings;
putting them in one file would make one of the two untrue.

Dekking: elke regel die met `- ` of `* ` begint in de zes gidsen, buiten
codeblokken en tabelregels. Niet gedekt: de `+ `-marker, de opmaak binnen
codeblokken en de tabelopmaak.

Coverage: every line starting with `- ` or `* ` in the six guides, outside code
blocks and table rows. Not covered: the `+ ` marker, the markup inside code blocks
and the table markup.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "docs" / "install"

LANGUAGES = ("en", "nl", "de", "es", "fr", "ar")

#: De twee tekens die Markdown aan het begin van een regel als opsomming leest.
#:
#: The two characters Markdown reads as a list at the start of a line.
MARKERS = ("- ", "* ")


def guide_lines(language: str) -> list[str]:
    """De regels van één gids, zonder regeleinde eraan.

    The lines of one guide, without their line ending.
    """
    return (INSTALL / f"{language}.md").read_text(encoding="utf-8").split("\n")


def opens_an_item(line: str) -> bool:
    """Opent deze regel zelf een lijstitem, ingesprongen of niet?

    Does this line itself open a list item, indented or not?
    """
    return line.lstrip().startswith(MARKERS)


def is_an_item_tail(line: str) -> bool:
    """Is dit de ingesprongen uitloop van een item (geen eigen regel)?

    Is this the indented tail of an item (not a line of its own)?
    """
    return line.startswith((" ", "\t")) and line.strip() != ""


def dangling_markers(language: str) -> list[tuple[int, str]]:
    """Elke regel die met een opsommingsteken begint en geen item is.

    Loopt van boven naar beneden en houdt de codeblokken bij. Een item mag op een
    lege regel volgen, op een ander item, of op de ingesprongen uitloop van een
    item; al het andere is proza dat als opsomming rendert.

    Every line that opens with a list marker and is not an item. Walks from top
    to bottom, tracking the code fences. An item may follow an empty line,
    another item, or the indented tail of an item; anything else is prose that
    renders as a list.
    """
    lines = guide_lines(language)
    problems: list[tuple[int, str]] = []
    in_code = False
    for index, line in enumerate(lines):
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not line.startswith(MARKERS):
            continue
        above = index - 1
        while above >= 0 and is_an_item_tail(lines[above]):
            above -= 1
        if above < 0:
            continue
        previous = lines[above]
        if previous.strip() == "" or opens_an_item(previous):
            continue
        problems.append((index + 1, line))
    return problems


@pytest.mark.parametrize("language", LANGUAGES)
def test_no_prose_line_opens_with_a_list_marker(language: str) -> None:
    """Geen enkele prozaregel in een gids begint met `- ` of `* `.

    No prose line in a guide opens with `- ` or `* `.
    """
    problems = dangling_markers(language)
    assert not problems, (
        f"{language}.md: deze regels openen met een opsommingsteken terwijl ze proza zijn; "
        "zet het streepje aan het eind van de regel erboven:\n"
        + "\n".join(f"  regel {line}: {text}" for line, text in problems)
    )
