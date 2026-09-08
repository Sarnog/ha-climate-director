"""Elke entiteit en elke actie heeft een regel in icons.json.

Every entity and every action has a line in icons.json.

C9: een icoon hoort bij de entiteit die een gebruiker in zijn lijst ziet,
niet bij een apparaat van een externe dienst. Deze test loopt over de zes
platforms, raapt elke `_attr_translation_key` op en eist dat `icons.json`
daar een icoon voor heeft; de drie acties staan er als `services` in. Zo kan
er geen entiteit of actie bijkomen zonder icoon.

C9: an icon belongs to the entity a user sees in their list, not to an
external service's device. This test walks the six platforms, collects every
`_attr_translation_key` and requires `icons.json` to carry an icon for it;
the three actions sit in there as `services`. That way no entity or action
can arrive without an icon.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "custom_components" / "climate_director"
ICONS = PACKAGE / "icons.json"

SERVICES = ("evaluate", "precondition", "cancel_precondition")


def declared_translation_keys() -> set[str]:
    """Return every `_attr_translation_key` the six platforms declare."""
    found: set[str] = set()
    for path in sorted((PACKAGE).glob("*.py")):
        if path.name in ("__init__.py", "config_flow.py", "coordinator.py", "texts.py"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_attr_translation_key":
                    value = node.value
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        found.add(value.value)
    return found


def test_every_entity_has_an_icon() -> None:
    """Elke `_attr_translation_key` heeft een `default`-regel in `icons.json`."""
    document = json.loads(ICONS.read_text(encoding="utf-8"))
    entities = document.get("entity", {})
    covered = {
        key
        for platform, keys in entities.items()
        if isinstance(keys, dict)
        for key, value in keys.items()
        if isinstance(value, dict) and "default" in value
    }
    declared = declared_translation_keys()
    missing = sorted(declared - covered)
    assert not missing, f"entiteiten zonder icoon: {missing}"
    assert declared, "de platformscan vond geen enkele translation key"


def test_every_action_has_an_icon() -> None:
    """Elke actie heeft een `service`-regel in `icons.json`."""
    document = json.loads(ICONS.read_text(encoding="utf-8"))
    services = document.get("services", {})
    missing = sorted(set(SERVICES) - set(services))
    assert not missing, f"acties zonder icoon: {missing}"
    for service in SERVICES:
        assert "service" in services[service], service
