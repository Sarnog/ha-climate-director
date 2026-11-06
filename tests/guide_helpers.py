"""Hulpjes die de gidsen uit de bron lezen: de inventaris, de titels en de alinea's.

Helpers that read the guides from the source: the inventory, the titles and the paragraphs."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

from _ast_helpers import issue_calls
from homeassistant.util import slugify

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "custom_components" / "climate_director"
TRANSLATIONS = PACKAGE / "translations"
INSTALL = ROOT / "docs" / "install"
LANGUAGES = ("en", "nl", "de", "es", "fr", "ar")

MARKER = re.compile(r"\{[a-z_]+\}")
BRAND = re.compile(r"^Climate Director\s*:\s*")
ACTION_LINE = re.compile(r"^([a-z_]+):$")


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "custom_components" / "climate_director"
TRANSLATIONS = PACKAGE / "translations"
INSTALL = ROOT / "docs" / "install"
LANGUAGES = ("en", "nl", "de", "es", "fr", "ar")

MARKER = re.compile(r"\{[a-z_]+\}")
BRAND = re.compile(r"^Climate Director\s*:\s*")
ACTION_LINE = re.compile(r"^([a-z_]+):$")


def json_file(path: Path) -> Any:
    """Return the parsed JSON of `path`."""
    return json.loads(path.read_text(encoding="utf-8"))


def translation(language: str) -> dict[str, Any]:
    """Return one language's translations."""
    return json_file(TRANSLATIONS / f"{language}.json")


def entity_keys() -> dict[str, list[str]]:
    """Return every entity key per domain, out of `icons.json`."""
    return {
        domain: sorted(keys) for domain, keys in json_file(PACKAGE / "icons.json")["entity"].items()
    }


def action_keys() -> list[str]:
    """Return every action out of `services.yaml`."""
    found: list[str] = []
    for line in (PACKAGE / "services.yaml").read_text(encoding="utf-8").splitlines():
        match = ACTION_LINE.match(line)
        if match:
            found.append(match.group(1))
    return found


def notice_keys() -> list[str]:
    """Return every repair notice out of `problems.py`, read through an AST.

    De sleutel staat soms letterlijk in de aanroep en soms in een constante
    erboven; beide worden opgezocht, zodat een nieuwe melding in welke vorm dan
    ook meetelt.

    The key sometimes stands literally in the call and sometimes in a constant
    above it; both are looked up, so a new notice counts in either form.
    """
    trees = [
        ast.parse((PACKAGE / name).read_text(encoding="utf-8"))
        for name in ("problems.py", "repair_notices.py")
    ]
    constants = {
        node.targets[0].id: node.value.value
        for tree in trees
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    keys: set[str] = set()
    for tree in trees:
        for node in issue_calls(tree, "async_create_issue"):
            for keyword in node.keywords:
                if keyword.arg != "translation_key":
                    continue
                if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                    keys.add(keyword.value.value)
                elif isinstance(keyword.value, ast.Name):
                    keys.add(constants[keyword.value.id])
    assert keys, "geen enkele reparatiemelding gevonden in problems.py"
    return sorted(keys)


def slug_pattern(language: str, domain: str, key: str) -> str:
    """Return the slug pattern of one entity, with `{zone}` turned into `<zone>`.

    Home Assistant derives an entity id from the translated name with `slugify`,
    so this is exactly what a guide has to name. The placeholder between angle
    brackets stands where the marker stood, so the comparison hits the translated
    slug and not the incidental name of a room.
    """
    name = translation(language)["entity"][domain][key]["name"]
    pattern = slugify(name)
    for marker in MARKER.findall(name):
        pattern = pattern.replace(slugify(marker), f"<{marker[1:-1]}>")
    return pattern


def entity_pattern(language: str, domain: str, key: str) -> str:
    """Return the entity id pattern the guide should name."""
    return f"{domain}.*_{slug_pattern(language, domain, key)}"


def notice_title(language: str, key: str) -> str:
    """Return the notice title as the user sees it, with `<naam>` for markers."""
    title = translation(language)["issues"][key]["title"]
    return MARKER.sub(lambda match: f"<{match.group(0)[1:-1]}>", BRAND.sub("", title))


#: Hoeveel tekens er ná de titel in dezelfde alinea moeten staan voordat het een
#: uitleg is en geen kale titelopsomming. De titel zelf is per taal 30-80 tekens;
#: de uitleg erachter is in elke taal ruim langer dan dit.
#:
#: How many characters must stand after the title in the same paragraph before
#: it counts as an explanation rather than a bare title list. The title itself
#: is 30-80 characters per language; the explanation behind it is comfortably
#: longer than this in every language.
MIN_EXPLANATION = 25

#: Tekens die geen uitleg zijn: de markdown-opmaak en het scheidingsteken.
#:
#: Characters that are not explanation: the markdown emphasis and the separator.
DECORATION = " \t*_—–-.:;،"

#: Wat een nieuwe alinea begint: een opsommingsteken of een genummerd punt, en
#: alles wat op zichzelf staat (een tabelrij of een kop).
#:
#: What starts a new paragraph: a bullet or a numbered item, and everything
#: that stands on its own (a table row or a heading).
ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")
OWN_LINE = re.compile(r"^\s*[|#]")


def paragraphs(text: str) -> list[str]:
    """Elke alinea van de tekst, met zijn vervolgregels eraan vast.

    Een opsomming die over meerdere regels loopt is één alinea: de gids breekt
    een lange bullet af op de regellengte, en dat mag de uitleg erachter niet
    laten verdwijnen. Een tabelrij en een kop staan elk op zichzelf.

    Every paragraph of the text, its continuation lines joined together. A
    bullet that runs over several lines is one paragraph: the guide breaks a
    long bullet on the line length, and that must not make the explanation
    behind it disappear. A table row and a heading each stand on their own.
    """
    blocks: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            blocks.append("\n".join(current))
            current.clear()

    for line in text.splitlines():
        if not line.strip():
            flush()
        elif ITEM.match(line) or OWN_LINE.match(line):
            flush()
            current.append(line)
        else:
            current.append(line)
    flush()
    return blocks


def explained(text: str, needle: str) -> bool:
    """Staat de titel ergens in een alinea mét uitleg erachter?

    Een kale opsomming van titels is geen handleiding: de lezer weet dan nog
    niet wat een melding betekent of wat hij eraan doet. Deze functie eist dat
    de titel in minstens één alinea staat met genoeg tekst erachter; de
    vervolgregels van die alinea tellen mee, want een lange bullet wordt op de
    regellengte afgebroken. Een losse regel met alleen de titel telt niet.

    Is the title somewhere in a paragraph with an explanation behind it? A bare
    list of titles is no manual: the reader still does not know what a notice
    means or what to do about it. This function demands that the title stands
    in at least one paragraph with enough text behind it; that paragraph's
    continuation lines count, because a long bullet is broken on the line
    length. A separate line carrying only the title does not count.
    """
    for block in paragraphs(text):
        if needle not in block:
            continue
        rest = " ".join(block.partition(needle)[2].split())
        if len(rest.strip(DECORATION)) >= MIN_EXPLANATION:
            return True
    return False


def missing(language: str) -> list[str]:
    """Return every inventory item this guide does not name."""
    text = (INSTALL / f"{language}.md").read_text(encoding="utf-8")
    missing: list[str] = []

    for domain, keys in entity_keys().items():
        for key in keys:
            needle = entity_pattern(language, domain, key)
            if needle not in text:
                missing.append(f"entiteit {domain}.{key}: {needle!r} ontbreekt")

    for action in action_keys():
        if f"climate_director.{action}" not in text:
            missing.append(f"actie climate_director.{action} ontbreekt")

    for key in notice_keys():
        needle = notice_title(language, key)
        if needle not in text:
            missing.append(f"melding {key}: {needle!r} ontbreekt")
        elif not explained(text, needle):
            missing.append(f"melding {key}: {needle!r} staat er zonder uitleg")

    return missing
