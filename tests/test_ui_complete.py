"""Elk stukje UI dat een gebruiker ziet, in elke taal.

Every piece of UI a user sees, in every language.

Een veld zonder vertaling valt niet om: Home Assistant zet er gewoon de sleutel
neer. Je krijgt dan `precondition_start` op je scherm in plaats van "Vooruit
verwarmen vanaf", en niets in de code merkt daar iets van. Dat is precies het
soort fout dat pas opvalt als iemand het scherm openslaat - dus lezen we het
formulier uit de broncode en leggen we het naast elk vertaalbestand.

A field without a translation does not break anything: Home Assistant simply
prints the key. You get `precondition_start` on screen instead of
"Pre-conditioning from", and nothing in the code notices. That is exactly the
kind of fault that only shows when somebody opens the screen - so we read the
form out of the source and lay it beside every translation file.
"""

from __future__ import annotations

import ast
import json
import pathlib
import re

import pytest
import yaml

COMPONENT = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "climate_director"

#: Velden waarvan de naam uit een constante komt in plaats van uit een letterlijke.
#: Fields whose name comes from a constant rather than from a literal.
CONSTANTS = {"CONF_NAME": "name", "CONF_SHADOW_MODE": "shadow_mode", "_CANCEL": "discard"}


def translation_files() -> list[pathlib.Path]:
    return [COMPONENT / "strings.json", *sorted((COMPONENT / "translations").glob("*.json"))]


def load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def fields_per_step() -> dict[str, set[str]]:
    """Return every field the flow asks for, per step, read from the source.

    Uit de broncode en niet uit een lijstje: een lijstje raakt achter zodra
    iemand een veld toevoegt, en dan bewijst deze test niets meer.

    From the source rather than from a list: a list falls behind the moment
    somebody adds a field, and then this test proves nothing.
    """
    tree = ast.parse((COMPONENT / "config_flow.py").read_text(encoding="utf-8"))
    found: dict[str, set[str]] = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or getattr(node.func, "attr", "") != "async_show_form":
            continue
        step = next((kw.value.value for kw in node.keywords if kw.arg == "step_id"), None)
        if not isinstance(step, str):
            continue

        keys: set[str] = set()
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            if getattr(inner.func, "attr", "") not in {"Required", "Optional"} or not inner.args:
                continue
            arg = inner.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                keys.add(arg.value)
            elif isinstance(arg, ast.Name):
                keys.add(CONSTANTS.get(arg.id, arg.id))
        found.setdefault(step, set()).update(keys)

    return found


def step_block(data: dict, step: str) -> dict | None:
    for section in ("options", "config"):
        block = data.get(section, {}).get("step", {}).get(step)
        if block:
            return block
    return None


STEPS = fields_per_step()
FILES = translation_files()
IDS = [path.name for path in FILES]


class TestEveryFormField:
    """Nineteen screens, eighty-six fields, seven files."""

    def test_the_source_yields_steps_at_all(self) -> None:
        """Guards the reader itself: an empty sweep would pass everything below."""
        assert len(STEPS) >= 15
        assert sum(len(keys) for keys in STEPS.values()) >= 80

    @pytest.mark.parametrize("path", FILES, ids=IDS)
    def test_every_step_exists(self, path: pathlib.Path) -> None:
        data = load(path)
        missing = [step for step in STEPS if step_block(data, step) is None]
        assert not missing, missing

    @pytest.mark.parametrize("path", FILES, ids=IDS)
    def test_every_field_has_a_label(self, path: pathlib.Path) -> None:
        data = load(path)
        missing = [
            f"{step}.{key}"
            for step, keys in STEPS.items()
            for key in keys
            if key not in (step_block(data, step) or {}).get("data", {})
        ]
        assert not missing, missing

    @pytest.mark.parametrize("path", FILES, ids=IDS)
    def test_every_field_has_an_explanation(self, path: pathlib.Path) -> None:
        """The grey line under the input is the only place a setting can explain itself."""
        data = load(path)
        missing = [
            f"{step}.{key}"
            for step, keys in STEPS.items()
            for key in keys
            if key not in (step_block(data, step) or {}).get("data_description", {})
        ]
        assert not missing, missing

    @pytest.mark.parametrize("path", FILES, ids=IDS)
    def test_no_label_is_a_bare_key(self, path: pathlib.Path) -> None:
        """A label that reads like a key is a translation somebody forgot to write."""
        data = load(path)
        suspects = []
        for step in STEPS:
            for key, label in (step_block(data, step) or {}).get("data", {}).items():
                if label == key or re.fullmatch(r"[a-z0-9]+(_[a-z0-9]+)+", label):
                    suspects.append(f"{step}.{key} = {label}")
        assert not suspects, suspects


class TestEveryDropdown:
    """A select without translated options shows its stored values instead."""

    _flow = (COMPONENT / "config_flow.py").read_text(encoding="utf-8")
    #: Twee vormen: rechtstreeks op de selector, en via `_choices`.
    #: Two shapes: straight on the selector, and by way of `_choices`.
    keys = set(re.findall(r'translation_key="(\w+)"', _flow)) | set(
        re.findall(r'_choices\([^"]*"(\w+)"\)', _flow)
    )

    def test_the_flow_uses_translation_keys(self) -> None:
        assert len(self.keys) >= 10

    @pytest.mark.parametrize("path", FILES, ids=IDS)
    def test_every_key_is_translated(self, path: pathlib.Path) -> None:
        present = set(load(path).get("selector", {}))
        assert not (self.keys - present), sorted(self.keys - present)

    @pytest.mark.parametrize("path", FILES, ids=IDS)
    def test_option_names_are_valid_keys(self, path: pathlib.Path) -> None:
        """Hassfest rejects a key that starts or ends with an underscore."""
        pattern = re.compile(r"^[a-z0-9]([a-z0-9_-]*[a-z0-9])?$")
        bad = [
            f"{key}.{option}"
            for key, block in load(path).get("selector", {}).items()
            for option in block.get("options", {})
            if not pattern.fullmatch(option)
        ]
        assert not bad, bad


class TestEveryAction:
    """Actions show up in the UI too, fields and all."""

    actions = yaml.safe_load((COMPONENT / "services.yaml").read_text(encoding="utf-8"))

    @pytest.mark.parametrize("path", FILES, ids=IDS)
    def test_each_one_is_named_and_described(self, path: pathlib.Path) -> None:
        services = load(path).get("services", {})
        missing = [
            f"{name}.{part}"
            for name in self.actions
            for part in ("name", "description")
            if part not in services.get(name, {})
        ]
        assert not missing, missing

    @pytest.mark.parametrize("path", FILES, ids=IDS)
    def test_each_field_is_named_and_described(self, path: pathlib.Path) -> None:
        services = load(path).get("services", {})
        missing = [
            f"{name}.{field}.{part}"
            for name, block in self.actions.items()
            for field in (block or {}).get("fields", {})
            for part in ("name", "description")
            if part not in services.get(name, {}).get("fields", {}).get(field, {})
        ]
        assert not missing, missing


class TestEveryEntity:
    """Every entity the integration creates needs a name in each language."""

    keys = {
        key
        for path in COMPONENT.glob("*.py")
        for key in re.findall(r'_attr_translation_key = "(\w+)"', path.read_text(encoding="utf-8"))
    }

    def test_there_are_entities_to_check(self) -> None:
        assert len(self.keys) >= 5

    @pytest.mark.parametrize("path", FILES, ids=IDS)
    def test_each_one_is_named(self, path: pathlib.Path) -> None:
        named = {key for domain in load(path).get("entity", {}).values() for key in domain}
        assert not (self.keys - named), sorted(self.keys - named)


class TestTheLanguagesAgree:
    """Same shape everywhere, so no language quietly falls behind."""

    def _shape(self, value, path: str = "") -> set[str]:
        if isinstance(value, dict):
            return {
                item for key, inner in value.items() for item in self._shape(inner, f"{path}.{key}")
            } | {path}
        return {path}

    @pytest.mark.parametrize("path", FILES, ids=IDS)
    def test_it_matches_the_english(self, path: pathlib.Path) -> None:
        english = self._shape(load(COMPONENT / "translations" / "en.json"))
        theirs = self._shape(load(path))
        assert not (english - theirs), sorted(english - theirs)

    @pytest.mark.parametrize("path", FILES, ids=IDS)
    def test_nothing_is_left_empty(self, path: pathlib.Path) -> None:
        def walk(value, trail: str = "") -> list[str]:
            if isinstance(value, dict):
                return [
                    item for key, inner in value.items() for item in walk(inner, f"{trail}.{key}")
                ]
            return [] if str(value).strip() else [trail]

        assert not walk(load(path)), walk(load(path))
