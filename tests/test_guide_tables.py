"""De gidsen gebruiken de woorden van het scherm: tabelrijen, uitzonderingen, knopcitaten.

Drie bewakingen op de handleidingen en de vertalingen samen:

1. elke **vette tabelrij** in Stap 3 t/m 11 van een gids is letterlijk een
   schermlabel van die taal - een `data`-label van een `config`/`options`-stap of
   een optielabel van de kiezer die de tabel beschrijft (bij het optielabel telt
   ook het deel vóór ` - ` of `: `, zoals *Prioriteit* uit *Prioriteit: het
   laagste nummer wint*);
2. elke sleutel in `EXCEPTIONS[taal]` van `tests/test_install_guides.py` valt in
   één van de vier categorieën waarin een uitzondering mag vallen: een
   `data.delete`, een sleutel met `when_done`, een `back_to_menu`, of een
   lijstkiezer van de vorm `options.step.<x>s.data.<x>` (met `es` voor het
   meervoud). Die uitzonderingenlijst is de lijst van labels die nog niet
   letterlijk in het proza staan; valt er een buiten deze vier, dan is dat een
   veldnaam die de lezer nergens terugziet;
3. elke waarde waarvan de Engelse tekst de verwerp-knop noemt (`\\bdiscard`)
   citeert het label van die knop in alle zes talen letterlijk tussen
   aanhalingstekens, zonder de pijl: *Kies je “Verwerpen en teruggaan”, …*. Voor
   het Engels wordt ook `strings.json` gelezen, de bron die Home Assistant zelf
   leest, en die twee horen dezelfde tekst te dragen.

Dekking: de zes vertaalbestanden, `strings.json` voor het Engels, de zes gidsen
en `EXCEPTIONS` uit `tests/test_install_guides.py`. Niet gedekt: of de rest van
een tabelrij klopt, of de uitzonderingenlijst zelf de juiste labels noemt (dat
doet `tests/test_install_guides.py`), of de gidsen de verwerp-knop ook citeren
waar ze hem noemen (alleen het Nederlands doet dat; dat staat als idee in
`ROADMAP.md`), en de vorm van de overige tabellen buiten Stap 3 t/m 11.

The guides use the words of the screen: table rows, exceptions, button quotes.

Three guards on the guides and the translations together:

1. every **bold table row** in Step 3 through 11 of a guide is literally a screen
   label of that language - a `data` label of a `config`/`options` step or an
   option label of the picker that the table describes (for an option label the
   part before ` - ` or `: ` counts too, such as *Precedence* out of *Precedence:
   the lowest number wins*);
2. every key in `EXCEPTIONS[language]` of `tests/test_install_guides.py` falls in
   one of the four categories an exception may fall in: a `data.delete`, a key
   with `when_done`, a `back_to_menu`, or a list picker of the form
   `options.step.<x>s.data.<x>` (with `es` for the plural). That exception list is
   the list of labels not yet standing literally in the prose; one falling outside
   these four is a field name the reader never sees back;
3. every value whose English text names the discard button (`\\bdiscard`) quotes
   that button's label in all six languages literally between quotation marks,
   without the arrow: *Choosing “Discard and go back”, …*. For English
   `strings.json` is read as well, the source Home Assistant itself reads, and the
   two should carry the same text.

Coverage: the six translation files, `strings.json` for English, the six guides
and `EXCEPTIONS` from `tests/test_install_guides.py`. Not covered: whether the
rest of a table row is right, whether the exception list itself names the right
labels (that is `tests/test_install_guides.py`), whether the guides quote the
discard button where they mention it (only Dutch does; that stands as an idea in
`ROADMAP.md`), and the shape of the other tables outside Step 3 through 11.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

COMPONENT = Path(__file__).parent.parent / "custom_components" / "climate_director"
TRANSLATIONS = COMPONENT / "translations"
STRINGS = COMPONENT / "strings.json"
INSTALL = Path(__file__).parent.parent / "docs" / "install"
GUIDES_TEST = Path(__file__).parent / "test_install_guides.py"

LANGUAGES = ("en", "nl", "de", "es", "fr", "ar")


def load(path: Path) -> dict:
    """Return one JSON file as a dict."""
    return json.loads(path.read_text(encoding="utf-8"))


def leaves(node: object, path: str = "") -> dict[str, str]:
    """Return every value of the file, keyed by its dotted path."""
    if not isinstance(node, dict):
        return {path: str(node)}
    found: dict[str, str] = {}
    for key, value in node.items():
        found |= leaves(value, f"{path}.{key}" if path else key)
    return found


def screen_labels(language: str) -> dict[str, str]:
    """Every screen label of one language, keyed by the literal text.

    Een schermlabel is een `data`-label van een `config`/`options`-stap of een
    optielabel van een kiezer. Van een optielabel telt ook het deel vóór ` - ` of
    `: ` mee, want zo staat het in de tabel.

    A screen label is a `data` label of a `config`/`options` step or an option
    label of a picker. Of an option label the part before ` - ` or `: ` counts
    too, because that is how it stands in the table.
    """
    labels: dict[str, str] = {}
    for key, value in leaves(load(TRANSLATIONS / f"{language}.json")).items():
        if not (
            re.fullmatch(r"(config|options)\.step\.\w+\.data\.\w+", key)
            or key.startswith("selector.")
        ):
            continue
        labels.setdefault(value, key)
        if key.startswith("selector."):
            labels.setdefault(re.split(r" - |: ", value, maxsplit=1)[0].rstrip(), key)
    return labels


def bold_rows(language: str) -> list[tuple[int, str]]:
    """Every bold table row in Step 3 through 11, with its line number."""
    rows: list[tuple[int, str]] = []
    step: int | None = None
    text = (INSTALL / f"{language}.md").read_text(encoding="utf-8")
    for number, line in enumerate(text.splitlines(), 1):
        if line.startswith("## "):
            heading = re.match(r"^## \S+ (\d+) ", line)
            step = int(heading.group(1)) if heading else None
        cell = re.match(r"\| \*\*(.+?)\*\*", line)
        if step is not None and 3 <= step <= 11 and cell:
            rows.append((number, cell.group(1)))
    return rows


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_table_row_names_a_screen_label(language: str) -> None:
    """Elke vette tabelrij in Stap 3 t/m 11 is een schermlabel van die taal.

    Every bold table row in Step 3 through 11 is a screen label of that language.
    """
    labels = screen_labels(language)
    wrong = [
        f"{language}.md:{number} **{cell}** staat niet in de interface"
        for number, cell in bold_rows(language)
        if cell not in labels
    ]
    assert not wrong, "een tabelrij noemt een eigen woord:\n" + "\n".join(wrong)


#: De vier categorieën waarin een uitzondering mag vallen. Dezelfde definitie als
#: in de T13-meter: een verwijderknop, een `when_done`, een `back_to_menu`, of een
#: lijstkiezer waarvan de stapnaam het meervoud van de veldnaam is.
#:
#: The four categories an exception may fall in. The same definition as in the T13
#: meter: a delete key, a `when_done`, a `back_to_menu`, or a list picker whose
#: step name is the plural of the field name.
def in_category(key: str) -> bool:
    """Return whether an exception key falls in one of the four categories."""
    if key.endswith(".data.delete") or "when_done" in key or key.endswith("back_to_menu"):
        return True
    match = re.fullmatch(r"options\.step\.(\w+)\.data\.(\w+)", key)
    return bool(match and match.group(1) in (match.group(2) + "s", match.group(2) + "es"))


def exceptions() -> dict[str, dict[str, str]]:
    """The exception list as `tests/test_install_guides.py` carries it.

    Die lijst wordt gegenereerd uit de gidsen (`script/_gen_guides_test.py`); deze
    bewaking leest hem daar en herschrijft niets.

    That list is generated from the guides (`script/_gen_guides_test.py`); this
    guard reads it there and rewrites nothing.
    """
    tree = ast.parse(GUIDES_TEST.read_text(encoding="utf-8"))
    for node in tree.body:
        target = (
            node.target
            if isinstance(node, ast.AnnAssign)
            else (node.targets[0] if isinstance(node, ast.Assign) else None)
        )
        if isinstance(target, ast.Name) and target.id == "EXCEPTIONS":
            return ast.literal_eval(node.value)
    raise AssertionError("EXCEPTIONS staat niet in tests/test_install_guides.py")


@pytest.mark.parametrize("language", LANGUAGES)
def test_exceptions_stay_in_their_four_categories(language: str) -> None:
    """Elke uitzondering valt in één van de vier categorieën.

    Every exception falls in one of the four categories.
    """
    outside = sorted(key for key in exceptions().get(language, {}) if not in_category(key))
    assert not outside, (
        f"{language}: deze uitzonderingen vallen buiten de vier categorieën: {outside}"
    )


def discard_label(language: str) -> str:
    """The text of the discard button of one language, without the arrow."""
    key = "selector.when_done.options.discard"
    return leaves(load(TRANSLATIONS / f"{language}.json"))[key].lstrip("← ").strip()


def cited_keys() -> list[str]:
    """Every key whose English text names the discard button."""
    return sorted(
        key
        for key, value in leaves(load(TRANSLATIONS / "en.json")).items()
        if re.search(r"\bdiscard", value, re.I)
    )


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_mention_of_the_discard_button_quotes_its_label(language: str) -> None:
    """Elke vermelding van de verwerp-knop citeert het label letterlijk.

    Every mention of the discard button quotes its label literally.
    """
    label = discard_label(language)
    quoted = re.compile("[\u201c\u201e\u00ab]\\s?" + re.escape(label) + "\\s?[\u201d\u201c\u00bb]")
    values = leaves(load(TRANSLATIONS / f"{language}.json"))
    source = leaves(load(STRINGS)) if language == "en" else {}
    missing = []
    for key in cited_keys():
        if key == "selector.when_done.options.discard":
            continue
        if not quoted.search(values.get(key, "")):
            missing.append(f"{language}.json:{key}")
        if source and source.get(key) != values.get(key):
            missing.append(f"strings.json:{key} wijkt af van translations/en.json")
    assert not missing, f"de verwerp-knop {label!r} wordt niet letterlijk geciteerd:\n" + "\n".join(
        missing
    )
