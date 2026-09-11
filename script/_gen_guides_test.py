"""Generate tests/test_install_guides.py for a given docs state and guard set."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(".")
TRANS = ROOT / "custom_components" / "climate_director" / "translations"
BUTTON_SELECTORS = ("when_done", "save_exit")
LANGUAGES = ("en", "nl", "de", "es", "fr", "ar")


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


def docs_from(ref: str, tmp: Path) -> Path:
    """Extract docs/install from a git ref into a temp dir."""
    out = tmp / "docs" / "install"
    out.mkdir(parents=True, exist_ok=True)
    for lang in LANGUAGES:
        data = subprocess.check_output(["git", "show", f"{ref}:docs/install/{lang}.md"], cwd=ROOT)
        (out / f"{lang}.md").write_bytes(data)
    return out


def build(docs: Path, *, entity_guard: bool, slugify_import: bool = False) -> str:
    exceptions: dict[str, dict[str, str]] = {}
    for lang in LANGUAGES:
        doc = (docs / f"{lang}.md").read_text(encoding="utf-8")
        exceptions[lang] = {k: v for k, v in interface_labels(lang).items() if v not in doc}

    lines = []
    for lang in LANGUAGES:
        lines.append(f'    "{lang}": {{')
        for k, v in sorted(exceptions[lang].items()):
            lines.append(f"        {k!r}: (")
            lines.append(f"            {v!r}")
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
                pattern = pattern.replace(
                    slugify(placeholder), f"<{placeholder[1:-1]}>"
                )
            needle = f"{domain}.*_{pattern}"
            if needle not in text:
                problems.append(
                    f"{language}: entiteit {domain}.{key} = {name!r} hoort als "
                    f"`{needle}` in docs/install/{language}.md te staan"
                )
    assert not problems, "de entiteit-ID's drijven weg van de interface:\\n" + "\\n".join(
        problems
    )
'''

    source = f'''"""De zes handleidingen gebruiken de woorden van de interface.

Er leest vandaag geen enkele test of CI-baan `docs/install/*.md`; daardoor zijn
de handleidingen van de interface weggedreven. Deze test maakt ze weer vast:
voor elke taal wordt elke interfacelabel uit `translations/<taal>.json` —
de veldnamen van `options.step.*.data.*` plus de knopteksten `discard`/`keep`
van de twee actiekeuzes — letterlijk in `docs/install/<taal>.md` gezocht.

De uitzonderingenlijst hieronder is letterlijk de stand van dit moment: het
label hoort in de handleiding thuis maar staat er nog niet letterlijk in.
Wordt een label in de vertaling hernoemd, dan is deze test rood; wordt het in
de handleiding gerepareerd, dan is hij óók rood, met de melding "haal deze van
de lijst". Zo kan de lijst alleen korter worden en is hij nooit stiekem
verouderd. De zes bestanden moeten bovendien een gelijk aantal `## `-koppen
houden, zodat geen taal een sectie kwijtraakt zonder dat iemand het merkt.

The six installation guides use the words of the interface.

No test or CI job reads `docs/install/*.md` today; the guides have therefore
drifted away from the interface. This test ties them back: for each language
every interface label from `translations/<language>.json` — the field names of
`options.step.*.data.*` plus the `discard`/`keep` button texts of the two
action pickers — is looked up literally in `docs/install/<language>.md`.

The exception list below is literally the state of this moment: the label
belongs in the guide but does not yet stand in it literally. When a label is
renamed in the translation this test is red; when the guide is repaired it is
red too, with the message "remove it from the list". That way the list can only
get shorter and is never silently outdated. The six files must also keep an
equal number of `## ` headers, so no language loses a section unnoticed.
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
BUTTON_SELECTORS = ("when_done", "save_exit")

EXCEPTIONS: dict[str, dict[str, str]] = {{
{exceptions_literal}
}}


def load(path: Path) -> dict:
    """Return one JSON file as a dict."""
    return json.loads(path.read_text(encoding="utf-8"))


def interface_labels(language: str) -> dict[str, str]:
    """Every label of the options flow, keyed by its dotted path.

    De veldnamen van `options.step.*.data.*` zijn wat de gebruiker naast elk
    formulierveld leest; de twee actiekeuzes (`when_done`, `save_exit`) dragen
    de knopteksten waaronder `discard` en `keep`.
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


def guide_text(language: str) -> str:
    """The full installation guide of one language."""
    return (INSTALL / f"{{language}}.md").read_text(encoding="utf-8")


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

    Six files, an equal number of `## ` headers.
    """
    counts = {{
        lang: len(re.findall(r"^## ", guide_text(lang), flags=re.MULTILINE)) for lang in LANGUAGES
    }}
    assert len(set(counts.values())) == 1, f"ongelijke koppentelling: {{counts}}"
    assert counts[language] > 0, f"{{language}}: geen enkele `## `-kop"
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
