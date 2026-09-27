"""Commentaar, docstrings en documenten zijn tijdloos.

Een verwijzing naar het moment waarop iets gebouwd of gemeten is (een datum, een
ronde, een tag uit een controleronde, een versienummer, een commithash) veroudert
op de dag dat hij geschreven wordt, en daarna leest de tekst als geschiedenis. Die
hoort in de release notes. De inhoud blijft staan; alleen de verwijzing naar het
moment gaat eruit.

Dekking: `ROADMAP.md` en `ARCHITECTURE.md` op een ISO-datum, een ronde met een
getal erachter (*ronde*, *round*, *Runde*, *ronda*, *tour*), een tag (een `R`, `T`
of `H` met cijfers, eventueel met streepje en volgnummer), een versienummer met
drie delen en een commithash tussen backticks; de zes gidsen in `docs/install/` op
een datum, een ronde, een versienummer en een hash; en van elk `.py`-bestand onder
`tests/`, `script/` en `custom_components/climate_director/` het `#`-commentaar
(gelezen met `tokenize`) en de docstrings van module, klasse en functie (gelezen
met `ast`) op een datum, een ronde, een `R`- of `T`-tag met streepje en
volgnummer, een versienummer en een hash. Een ronde telt alleen met een woordgrens
ervoor, dus *hieronder*, *around* en *Entscheidungsrunde* tellen niet. Niet
gedekt: stringliteralen, want dat is data (een ISO-datum in een assert); een losse
string na een toekenning (een attribuutdocstring); een hash zonder backticks; een
`H`-tag in code, waar die het eigen label van een toets kan zijn; en de andere
bestanden van de repo, zoals `README.md` en de blauwdrukken.

Comments, docstrings and documents are timeless.

A reference to the moment something was built or measured (a date, a round, a
tag from a review round, a version number, a commit hash) goes stale the day it is
written, and from then on the text reads as history. That belongs in the release
notes. The content stays; only the reference to the moment goes.

Coverage: `ROADMAP.md` and `ARCHITECTURE.md` for an ISO date, a round with a
number after it (*ronde*, *round*, *Runde*, *ronda*, *tour*), a tag (an `R`, `T`
or `H` with digits, optionally with a dash and a sequence number), a three-part
version number and a commit hash between backticks; the six guides in
`docs/install/` for a date, a round, a version number and a hash; and for every
`.py` file under `tests/`, `script/` and `custom_components/climate_director/` the
`#` comments (read with `tokenize`) and the docstrings of module, class and
function (read with `ast`) for a date, a round, an `R` or `T` tag with a dash and
a sequence number, a version number and a hash. A round only counts with a word
boundary before it, so *hieronder*, *around* and *Entscheidungsrunde* do not
count. Not covered: string literals, since that is data (an ISO date in an
assert); a bare string after an assignment (an attribute docstring); a hash
without backticks; an `H` tag in code, where it can be a test's own label; and the
other files of the repo, such as `README.md` and the blueprints.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent

DATE = re.compile(r"\b20\d\d-\d\d-\d\d\b")
ROUND = re.compile(r"\b(ronde|round|runde|ronda|tour)\s+\d+", re.IGNORECASE)
TAG = re.compile(r"\b[RTH]\d+(-\d+)?\b")
CODE_TAG = re.compile(r"\b[RT]\d+-\d+\b")
VERSION = re.compile(r"\b\d+\.\d+\.\d+\b")
HASH = re.compile(r"`[0-9a-f]{7,40}`")

#: Per soort document de patronen die er niet in mogen staan.
#:
#: Per kind of document the patterns that may not appear in it.
DOCUMENTS: dict[str, tuple[re.Pattern[str], ...]] = {
    "ROADMAP.md": (DATE, ROUND, TAG, VERSION, HASH),
    "ARCHITECTURE.md": (DATE, ROUND, TAG, VERSION, HASH),
    **{
        f"docs/install/{language}.md": (DATE, ROUND, VERSION, HASH)
        for language in ("nl", "en", "de", "fr", "es", "ar")
    },
}
CODE_PATTERNS = (DATE, ROUND, CODE_TAG, VERSION, HASH)
CODE_FOLDERS = ("tests", "script", "custom_components/climate_director")


def moments(text: str, patterns: tuple[re.Pattern[str], ...]) -> list[str]:
    """Return every reference to a moment in this text, with its line."""
    return [
        f"{number}: {match.group(0)!r}"
        for number, line in enumerate(text.splitlines(), 1)
        for pattern in patterns
        for match in pattern.finditer(line)
    ]


@pytest.mark.parametrize("name", sorted(DOCUMENTS))
def test_the_documents_are_timeless(name: str) -> None:
    """A document describes what is, not when it came to be."""
    found = moments((ROOT / name).read_text(encoding="utf-8"), DOCUMENTS[name])
    assert not found, f"{name}:\n" + "\n".join(found)


def code_files() -> list[str]:
    """Return every Python file under the three code folders, relative to the repo."""
    return sorted(
        path.relative_to(ROOT).as_posix()
        for folder in CODE_FOLDERS
        for path in (ROOT / folder).rglob("*.py")
        if "__pycache__" not in path.parts
    )


@pytest.mark.parametrize("name", code_files())
def test_comments_and_docstrings_are_timeless(name: str) -> None:
    """A comment or docstring explains the code as it is, not its history."""
    source = (ROOT / name).read_text(encoding="utf-8")
    found = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            found += [
                f"commentaar r. {token.start[0]}: {moment.split(': ', 1)[1]}"
                for moment in moments(token.string, CODE_PATTERNS)
            ]
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            docstring = ast.get_docstring(node, clean=False)
            if docstring:
                start = node.body[0].lineno
                found += [
                    f"docstring r. {start + int(moment.split(':', 1)[0]) - 1}: "
                    f"{moment.split(': ', 1)[1]}"
                    for moment in moments(docstring, CODE_PATTERNS)
                ]
    assert not found, f"{name}:\n" + "\n".join(found)
