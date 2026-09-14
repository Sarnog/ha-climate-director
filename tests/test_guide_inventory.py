"""De zichtbare inventaris uit de bron staat in alle zes de gidsen.

The visible inventory from the source stands in all six guides.

Een nieuwe entiteit, een nieuwe actie of een nieuwe reparatiemelding hoort niet
stilletjes buiten de handleidingen te blijven. Deze test leest de inventaris
daarom uit de **bron** — `icons.json` voor de entiteiten, `services.yaml` voor de
acties, en `problems.py` via een AST voor de meldingen — en eist per gids dat
elk item er met de interfacewoorden in staat: de entiteit onder de id die Home
Assistant uit zijn vertaalde naam afleidt, de actie onder
`climate_director.<naam>`, en de melding onder de titel die de gebruiker in
*Reparaties* ziet (met de plaatshouders als `<naam>`).

De velden van de options-flowschermen worden al op dezelfde manier bewaakt door
`tests/test_install_guides.py`, dat zijn veldenkaart uit de schema's leest en per
label eist dat het in de tekst staat. Dat werk wordt hier niet overgedaan.

A new entity, a new action or a new repair notice should not quietly stay out of
the manuals. This test therefore reads the inventory from the **source** —
`icons.json` for the entities, `services.yaml` for the actions, and `problems.py`
through an AST for the notices — and demands per guide that every item stands
there in the interface's own words: the entity under the id Home Assistant
derives from its translated name, the action under `climate_director.<name>`, and
the notice under the title the user sees in *Repairs* (with its placeholders as
`<name>`).

The options-flow screens' fields are already guarded the same way by
`tests/test_install_guides.py`, which reads its field map from the schemas and
demands per label that it stands in the text. That work is not redone here.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

import pytest
from homeassistant.util import slugify

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "custom_components" / "climate_director"
TRANSLATIONS = PACKAGE / "translations"
INSTALL = ROOT / "docs" / "install"
LANGUAGES = ("en", "nl", "de", "es", "fr", "ar")

MARKER = re.compile(r"\{[a-z_]+\}")
BRAND = re.compile(r"^Climate Director\s*:\s*")
ACTION_LINE = re.compile(r"^([a-z_]+):$")


def _json(path: Path) -> Any:
    """Return the parsed JSON of `path`."""
    return json.loads(path.read_text(encoding="utf-8"))


def _translation(language: str) -> dict[str, Any]:
    """Return one language's translations."""
    return _json(TRANSLATIONS / f"{language}.json")


def entity_keys() -> dict[str, list[str]]:
    """Return every entity key per domain, out of `icons.json`."""
    return {
        domain: sorted(keys) for domain, keys in _json(PACKAGE / "icons.json")["entity"].items()
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
    tree = ast.parse((PACKAGE / "problems.py").read_text(encoding="utf-8"))
    constants = {
        node.targets[0].id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    keys: set[str] = set()
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "async_create_issue"
        ):
            continue
        for keyword in node.keywords:
            if keyword.arg != "translation_key":
                continue
            if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                keys.add(keyword.value.value)
            elif isinstance(keyword.value, ast.Name):
                keys.add(constants[keyword.value.id])
    assert keys, "geen enkele reparatiemelding gevonden in problems.py"
    return sorted(keys)


def _entity_pattern(language: str, domain: str, key: str) -> str:
    """Return the entity id pattern the guide should name."""
    name = _translation(language)["entity"][domain][key]["name"]
    pattern = slugify(name)
    for marker in MARKER.findall(name):
        pattern = pattern.replace(slugify(marker), f"<{marker[1:-1]}>")
    return f"{domain}.*_{pattern}"


def _notice_title(language: str, key: str) -> str:
    """Return the notice title as the user sees it, with `<naam>` for markers."""
    title = _translation(language)["issues"][key]["title"]
    return MARKER.sub(lambda match: f"<{match.group(0)[1:-1]}>", BRAND.sub("", title))


def _missing(language: str) -> list[str]:
    """Return every inventory item this guide does not name."""
    text = (INSTALL / f"{language}.md").read_text(encoding="utf-8")
    missing: list[str] = []

    for domain, keys in entity_keys().items():
        for key in keys:
            needle = _entity_pattern(language, domain, key)
            if needle not in text:
                missing.append(f"entiteit {domain}.{key}: {needle!r} ontbreekt")

    for action in action_keys():
        if f"climate_director.{action}" not in text:
            missing.append(f"actie climate_director.{action} ontbreekt")

    for key in notice_keys():
        needle = _notice_title(language, key)
        if needle not in text:
            missing.append(f"melding {key}: {needle!r} ontbreekt")

    return missing


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_visible_feature_stands_in_every_guide(language: str) -> None:
    """Elke entiteit, actie en melding staat met de interfacewoorden in de gids."""
    assert not _missing(language)
