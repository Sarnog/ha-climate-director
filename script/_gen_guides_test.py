"""Generate tests/test_install_guides.py for a given docs state and guard set."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(".")
TRANS = ROOT / "custom_components" / "climate_director" / "translations"
BUTTON_SELECTORS = ("when_done",)
LANGUAGES = ("en", "nl", "de", "es", "fr", "ar")

#: De regelbreedte van `pyproject.toml`. De uitzonderingenlijst hieronder moet
#: `ruff format --check` doorstaan, en dat kapt een lange regel op deze breedte
#: af; daarom rekent de generator dezelfde grens uit.
#:
#: The line width from `pyproject.toml`. The exception list below has to pass
#: `ruff format --check`, and that splits a long line at this width; so the
#: generator works out the same bound.
LINE_LENGTH = 100

#: De kop van de woordenlijst per taal. Deze generator knipt die sectie uit de
#: handleiding voordat hij de uitzonderingen meet, en de gegenereerde test doet
#: hetzelfde met dezelfde koppen - daarom staat de lijst hier en niet daar.
#:
#: The glossary heading per language. This generator cuts that section out of
#: the guide before measuring the exceptions, and the generated test does the
#: same with the same headings - which is why the list lives here and not there.
GLOSSARY = {
    "en": "Interface glossary",
    "nl": "Woordenlijst van de interface",
    "de": "Wörterliste der Oberfläche",
    "es": "Glosario de la interfaz",
    "fr": "Glossaire de l'interface",
    "ar": "قائمة كلمات الواجهة",
}


def without_glossary(text: str, language: str) -> str:
    """Return `text` without the interface glossary section.

    De woordenlijst staat in de handleiding voor de lezer, niet voor de ratel:
    die meet of het **proza** de woorden van de interface gebruikt. Zonder deze
    knip telt elk label mee dat ergens in een tabel staat, en dan is de bewaking
    groen zonder dat er iets bewezen is - dan keurt de lijst ontbrekende tekst
    goed in plaats van hem aan te wijzen.

    The glossary is in the guide for the reader, not for the ratchet: it
    measures whether the **prose** uses the interface's words. Without this cut
    every label in any table counts, and then the guard is green without
    anything being proven - the list then approves missing text instead of
    pointing at it.
    """
    lines = text.splitlines(keepends=True)
    keep: list[str] = []
    skipping = False
    for line in lines:
        if line.strip() == f"## {GLOSSARY[language]}":
            skipping = True
            continue
        if skipping and line.startswith("## "):
            skipping = False
        if not skipping:
            keep.append(line)
    return "".join(keep)


def glossary_code() -> str:
    """Return the glossary headings as Python source for the generated test."""
    lines = [
        "#: De kop van de woordenlijst per taal. Deze test knipt die sectie uit de",
        "#: handleiding voordat hij meet, en die koppen moeten dus letterlijk met de",
        "#: zes bestanden overeenkomen - anders knipt hij niets weg en telt de tabel",
        "#: mee. Deze lijst wordt gegenereerd uit `script/_gen_guides_test.py`, waar",
        "#: dezelfde koppen de uitzonderingen meten.",
        "#:",
        "#: The glossary heading per language. This test cuts that section out of the",
        "#: guide before measuring, so the headings have to match the six files",
        "#: literally - otherwise it cuts nothing away and the table counts along.",
        "#: This list is generated from `script/_gen_guides_test.py`, where the same",
        "#: headings measure the exceptions.",
        "GLOSSARY: dict[str, str] = {",
    ]
    lines += [
        f"    {json.dumps(lang, ensure_ascii=False)}: {json.dumps(heading, ensure_ascii=False)},"
        for lang, heading in GLOSSARY.items()
    ]
    lines.append("}")
    return "\n".join(lines)


def interface_labels(lang: str) -> dict[str, str]:
    with open(TRANS / f"{lang}.json", encoding="utf-8") as f:
        data = json.load(f)
    labels: dict[str, str] = {}
    for step, stepd in data.get("options", {}).get("step", {}).items():
        if not isinstance(stepd, dict):
            continue
        d = stepd.get("data")
        if isinstance(d, dict):
            for k, v in d.items():
                if isinstance(v, str):
                    labels[f"options.step.{step}.data.{k}"] = v
    sel = data.get("selector", {})
    for selname in BUTTON_SELECTORS:
        opts = sel.get(selname, {}).get("options", {})
        for k, v in opts.items():
            if isinstance(v, str):
                labels[f"selector.{selname}.options.{k}"] = v
    return labels


def build(docs: Path, *, entity_guard: bool, slugify_import: bool = False) -> str:
    exceptions: dict[str, dict[str, str]] = {}
    for lang in LANGUAGES:
        doc = (docs / f"{lang}.md").read_text(encoding="utf-8")
        prose = without_glossary(doc, lang)
        exceptions[lang] = {k: v for k, v in interface_labels(lang).items() if v not in prose}

    glossary_literal = glossary_code()

    lines = []
    for lang in LANGUAGES:
        lines.append(f'    "{lang}": {{')
        for k, v in sorted(exceptions[lang].items()):
            key = json.dumps(k, ensure_ascii=False)
            value = json.dumps(v, ensure_ascii=False)
            one_line = f"        {key}: ({value}),"
            if len(one_line) <= LINE_LENGTH:
                lines.append(one_line)
            else:
                lines.append(f"        {key}: (")
                lines.append(f"            {value}")
                lines.append("        ),")
        lines.append("    },")
    exceptions_literal = "\n".join(lines)

    slugify_import_line = "from homeassistant.util import slugify\n" if slugify_import else ""
    entity_guard_code = ""
    if entity_guard:
        entity_guard_code = '''

def entity_names(language: str) -> dict[tuple[str, str], str]:
    """Elke vertaalde entiteitsnaam, per domein en translation_key.

    Every translated entity name, per domain and translation key.
    """
    data = load(TRANSLATIONS / f"{language}.json")
    names: dict[tuple[str, str], str] = {}
    for domain, keys in data.get("entity", {}).items():
        if not isinstance(keys, dict):
            continue
        for key, info in keys.items():
            if isinstance(info, dict) and isinstance(info.get("name"), str):
                names[(domain, key)] = info["name"]
    return names


def test_every_guide_names_its_own_entity_ids() -> None:
    """Elke handleiding noemt de entiteit-ID's die HA van die taal afleidt.

    Home Assistant leidt de entiteit-ID af van de vertaalde naam: op een Duitse
    HA heet de mismatchesensor `sensor.*_abweichungen`, niet
    `sensor.*_mismatch`. Deze bewaking rekent per taal de verwachte ID-patronen
    uit met dezelfde `slugify` die HA gebruikt en eist dat elk patroon letterlijk
    in de handleiding staat. Placeholders als `{zone}` verschijnen in de
    handleiding als `<zone>`, dus die vorm wordt in het patroon teruggezet.

    Every guide names the entity ids HA derives from that language. Home
    Assistant derives the entity id from the translated name: on a German HA
    the mismatch sensor is called `sensor.*_abweichungen`, not
    `sensor.*_mismatch`. This guard computes each language's expected id
    patterns with the same `slugify` HA uses and requires every pattern to
    stand literally in the guide. Placeholders such as `{zone}` appear in the
    guide as `<zone>`, so that form is put back into the pattern.
    """
    problems: list[str] = []
    for language in LANGUAGES:
        text = guide_text(language)
        for (domain, key), name in sorted(entity_names(language).items()):
            pattern = slugify(name)
            for placeholder in re.findall(r"\\{[a-z_]+\\}", name):
                pattern = pattern.replace(slugify(placeholder), f"<{placeholder[1:-1]}>")
            needle = f"{domain}.*_{pattern}"
            if needle not in text:
                problems.append(
                    f"{language}: entiteit {domain}.{key} = {name!r} hoort als "
                    f"`{needle}` in docs/install/{language}.md te staan"
                )
    assert not problems, "de entiteit-ID's drijven weg van de interface:\\n" + "\\n".join(problems)
'''

    source = f'''"""De zes handleidingen gebruiken de woorden van de interface.

Er leest vandaag geen enkele test of CI-baan `docs/install/*.md`; daardoor zijn
de handleidingen van de interface weggedreven. Deze test maakt ze weer vast:
voor elke taal wordt elke interfacelabel uit `translations/<taal>.json` —
de veldnamen van `options.step.*.data.*` plus de knopteksten `discard`/`keep`
van de actiekeuze — letterlijk in `docs/install/<taal>.md` gezocht.

De uitzonderingenlijst hieronder is letterlijk de stand van dit moment: het
label hoort in de handleiding thuis maar staat er nog niet letterlijk in.
Wordt een label in de vertaling hernoemd, dan is deze test rood; wordt het in
de handleiding gerepareerd, dan is hij óók rood, met de melding "haal deze van
de lijst". Zo kan de lijst alleen korter worden en is hij nooit stiekem
verouderd. De zes bestanden moeten bovendien een gelijk aantal `## `-koppen
houden, zodat geen taal een sectie kwijtraakt zonder dat iemand het merkt.

Gemeten wordt het **proza**: de sectie "Woordenlijst van de interface" wordt er
eerst uit geknipt. Anders telt een label mee zodra het ergens in een tabel
staat, en dan is deze test groen zonder dat er iets bewezen is - dan keurt de
lijst ontbrekende tekst goed in plaats van hem aan te wijzen. De koppentelling
leest het hele bestand, juist zodat de woordenlijst niet stil kan verdwijnen.

De woordenlijst zelf wordt ook bewaakt: de eerste kolom is precies de
uitzonderingenlijst hieronder, niet meer en niet minder, en elke rij noemt een
label dat werkelijk in de vertaling van die taal staat. Die vergelijking staat
in `script/_gen_guides_test.py`, waar de uitzonderingenlijst ook vandaan komt -
één plek, zodat tabel en lijst alleen samen kunnen veranderen.

The six installation guides use the words of the interface.

No test or CI job reads `docs/install/*.md` today; the guides have therefore
drifted away from the interface. This test ties them back: for each language
every interface label from `translations/<language>.json` — the field names of
`options.step.*.data.*` plus the `discard`/`keep` button texts of the action
picker — is looked up literally in `docs/install/<language>.md`.

The exception list below is literally the state of this moment: the label
belongs in the guide but does not yet stand in it literally. When a label is
renamed in the translation this test is red; when the guide is repaired it is
red too, with the message "remove it from the list". That way the list can only
get shorter and is never silently outdated. The six files must also keep an
equal number of `## ` headers, so no language loses a section unnoticed.

What is measured is the **prose**: the "Interface glossary" section is cut out
first. Otherwise a label counts as soon as it stands in any table, and then this
test is green without anything being proven - the list then approves missing
text instead of pointing at it. The header count reads the whole file, exactly
so the glossary cannot disappear quietly.

The glossary itself is guarded too: its first column is exactly the exception
list below, no more and no less, and every row names a label that really stands
in that language's translation. That comparison lives in
`script/_gen_guides_test.py`, where the exception list comes from as well - one
place, so table and list can only change together.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
{slugify_import_line}
COMPONENT = Path(__file__).parent.parent / "custom_components" / "climate_director"
TRANSLATIONS = COMPONENT / "translations"
INSTALL = Path(__file__).parent.parent / "docs" / "install"

LANGUAGES = ("en", "nl", "de", "es", "fr", "ar")
BUTTON_SELECTORS = ("when_done",)

{glossary_literal}

EXCEPTIONS: dict[str, dict[str, str]] = {{
{exceptions_literal}
}}


def load(path: Path) -> dict:
    """Return one JSON file as a dict."""
    return json.loads(path.read_text(encoding="utf-8"))


def interface_labels(language: str) -> dict[str, str]:
    """Every label of the options flow, keyed by its dotted path.

    De veldnamen van `options.step.*.data.*` zijn wat de gebruiker naast elk
    formulierveld leest; de actiekeuze (`when_done`) draagt de knopteksten
    waaronder `discard` en `keep`.
    """
    data = load(TRANSLATIONS / f"{{language}}.json")
    labels: dict[str, str] = {{}}
    for step, step_data in data.get("options", {{}}).get("step", {{}}).items():
        if not isinstance(step_data, dict):
            continue
        fields = step_data.get("data")
        if isinstance(fields, dict):
            for key, value in fields.items():
                if isinstance(value, str):
                    labels[f"options.step.{{step}}.data.{{key}}"] = value
    for selector_name in BUTTON_SELECTORS:
        options = data.get("selector", {{}}).get(selector_name, {{}}).get("options", {{}})
        for key, value in options.items():
            if isinstance(value, str):
                labels[f"selector.{{selector_name}}.options.{{key}}"] = value
    return labels


def guide_raw(language: str) -> str:
    """The whole installation guide of one language, glossary included."""
    return (INSTALL / f"{{language}}.md").read_text(encoding="utf-8")


def guide_text(language: str) -> str:
    """The guide's prose, without the interface glossary section.

    De woordenlijst staat in de handleiding voor de lezer, niet voor deze ratel:
    die meet of het **proza** de woorden van de interface gebruikt. Zonder deze
    knip telt elk label mee dat ergens in een tabel staat, en dan is de bewaking
    groen zonder dat er iets bewezen is. Dan keurt de lijst ontbrekende tekst
    goed in plaats van hem aan te wijzen.

    The glossary is in the guide for the reader, not for this ratchet: it
    measures whether the **prose** uses the interface's words. Without this cut
    every label in any table counts, and then the guard is green without
    anything being proven - the list then approves missing text instead of
    pointing at it.
    """
    lines = guide_raw(language).splitlines(keepends=True)
    keep: list[str] = []
    skipping = False
    for line in lines:
        if line.strip() == f"## {{GLOSSARY[language]}}":
            skipping = True
            continue
        if skipping and line.startswith("## "):
            skipping = False
        if not skipping:
            keep.append(line)
    return "".join(keep)


def test_every_guide_uses_the_words_of_its_interface() -> None:
    """Elk interfacelabel staat letterlijk in de handleiding van die taal.

    Every interface label stands literally in that language's guide.
    """
    problems: list[str] = []
    for language in LANGUAGES:
        labels = interface_labels(language)
        text = guide_text(language)
        exceptions = EXCEPTIONS.get(language, {{}})
        for key, value in sorted(labels.items()):
            if value in text:
                continue
            noted = exceptions.get(key)
            if noted is None:
                problems.append(
                    f"{{language}}: label {{key}} = {{value!r}} komt niet letterlijk "
                    f"voor in docs/install/{{language}}.md"
                )
            elif noted != value:
                problems.append(
                    f"{{language}}: label {{key}} is veranderd van {{noted!r}} naar "
                    f"{{value!r}}; pas de uitzondering aan"
                )
        for key, noted in sorted(exceptions.items()):
            if key not in labels:
                problems.append(
                    f"{{language}}: uitzondering {{key}} bestaat niet meer in "
                    f"translations/{{language}}.json; haal deze van de lijst"
                )
                continue
            value = labels[key]
            if noted != value:
                if value in text:
                    problems.append(
                        f"{{language}}: label {{key}} is veranderd en staat nu wél "
                        f"in de handleiding; haal deze van de lijst"
                    )
            elif value in text:
                problems.append(
                    f"{{language}}: label {{key}} = {{noted!r}} staat nu wél in de "
                    f"handleiding; haal deze van de lijst"
                )
    assert not problems, "de handleidingen drijven weg van de interface:\\n" + "\\n".join(problems)
{entity_guard_code}

@pytest.mark.parametrize("language", LANGUAGES)
def test_every_guide_has_the_same_number_of_headers(language: str) -> None:
    """Zes bestanden, een gelijk aantal `## `-koppen.

    Deze telt het hele bestand (`guide_raw`), dus de woordenlijst-sectie telt
    mee: die is van de lezer en mag in geen enkele taal ontbreken.

    This one counts the whole file (`guide_raw`), so the glossary section counts
    along: it is the reader's and may be missing from no language.
    """
    counts = {{
        lang: len(re.findall(r"^## ", guide_raw(lang), flags=re.MULTILINE)) for lang in LANGUAGES
    }}
    assert len(set(counts.values())) == 1, f"ongelijke koppentelling: {{counts}}"
    assert counts[language] > 0, f"{{language}}: geen enkele `## `-kop"


def glossary_cells(language: str) -> list[list[str]]:
    """Elke rij van de woordenlijst-sectie als lijst cellen, in bestandsorde.

    De kopregel en de scheidingsregel (`|---|---|`) tellen niet mee; alles wat
    daarna in de sectie met een `|` begint is een rij van de lezer.

    Every row of the interface glossary section as a list of cells, in file
    order. The header row and the separator row (`|---|---|`) do not count;
    everything after that inside the section, starting with `|`, is a row for the
    reader.
    """
    rows: list[list[str]] = []
    inside = False
    separator_seen = False
    for line in guide_raw(language).splitlines():
        stripped = line.strip()
        if stripped == f"## {{GLOSSARY[language]}}":
            inside = True
            continue
        if inside and line.startswith("## "):
            break
        if not inside or not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 2:
            continue
        if set(cells[0]) <= set("-: "):
            separator_seen = True
            continue
        if not separator_seen:
            continue
        rows.append(cells)
    return rows


def glossary_rows(language: str) -> list[str]:
    """De eerste kolom van de woordenlijst-sectie, in bestandsorde.

    The first column of the interface glossary section, in file order.
    """
    return [cells[0] for cells in glossary_cells(language)]


def test_the_glossary_is_the_exception_list() -> None:
    """De woordenlijst is de uitzonderingenlijst van die taal, en niets anders.

    Wat hier vastligt: de eerste kolom van de woordenlijst-sectie komt exact
    overeen met `EXCEPTIONS[taal]` - elke rij staat op de lijst en elke regel van
    de lijst heeft een rij - en elke rij noemt een label dat werkelijk in
    `translations/<taal>.json` staat. Die tweede eis is de scherpe kant: een
    verdwenen interfaceknop laat een rij staan die nergens meer naar verwijst, en
    dat is precies hoe deze tabel eerder is weggelopen. Vergeleken wordt op de
    **tekst** van het label, niet op de sleutel: een label dat twee sleutels
    deelt (een `when_done`-knop die op elk scherm hetzelfde heet) hoort één rij
    te hebben, niet twee. Staat dezelfde rij twee keer in de sectie, dan is dat
    ook rood: een `set` zou de dubbele stil laten vallen.

    What this pins down: the glossary's first column matches `EXCEPTIONS[language]`
    exactly - every row stands on the list and every line of the list has a row -
    and every row names a label that really stands in `translations/<language>.json`.
    That second demand is the sharp side: a disappeared interface button leaves a
    row pointing at nothing, and that is exactly how this table drifted before.
    The comparison is on the **text** of the label, not on the key: a label two
    keys share (a `when_done` button that is called the same on every screen)
    belongs in one row, not two. A row standing twice in the section is red as
    well: a `set` would quietly let the duplicate fall.
    """
    problems: list[str] = []
    for language in LANGUAGES:
        rows = glossary_rows(language)
        expected = {{value for value in EXCEPTIONS.get(language, {{}}).values()}}
        labels = set(interface_labels(language).values())
        pairs = [tuple(cells[:2]) for cells in glossary_cells(language)]
        duplicates = sorted({{pair for pair in pairs if pairs.count(pair) > 1}})
        for pair in duplicates:
            note = f"{{language}}: rij {{pair[0]!r}} bij {{pair[1]!r}} staat er twee keer"
            problems.append(note)
        for row in sorted(set(rows) - expected):
            problems.append(
                f"{{language}}: de woordenlijst noemt {{row!r}}, en dat staat niet op de "
                f"uitzonderingenlijst; haal de rij weg"
            )
        for row in sorted(expected - set(rows)):
            problems.append(
                f"{{language}}: de uitzonderingenlijst noemt {{row!r}} en de woordenlijst "
                f"niet; zet de rij erin of haal de regel van de lijst"
            )
        for row in sorted(set(rows)):
            if row not in labels:
                problems.append(
                    f"{{language}}: de woordenlijst noemt {{row!r}}, en dat label bestaat "
                    f"niet in translations/{{language}}.json"
                )
    assert not problems, "de woordenlijst is de uitzonderingenlijst niet:\\n" + "\\n".join(problems)
'''
    return source


def main() -> None:
    worktree = "--worktree" in sys.argv
    entity_guard = "--entity" in sys.argv
    ref = next((arg for arg in sys.argv[1:] if not arg.startswith("--")), "HEAD")
    if worktree:
        docs = ROOT / "docs" / "install"
        source = build(docs, entity_guard=entity_guard, slugify_import=entity_guard)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            docs = tmp_path / "docs" / "install"
            docs.mkdir(parents=True)
            for lang in LANGUAGES:
                data = subprocess.check_output(
                    ["git", "show", f"{ref}:docs/install/{lang}.md"], cwd=ROOT
                )
                (docs / f"{lang}.md").write_bytes(data)
            source = build(docs, entity_guard=entity_guard, slugify_import=entity_guard)
    out = ROOT / "tests" / "test_install_guides.py"
    out.write_text(source, encoding="utf-8")
    print(f"wrote {out} ({'worktree' if worktree else ref}, entity_guard={entity_guard})")


if __name__ == "__main__":
    main()
