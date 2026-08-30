"""De bewakingen van de testset worden zelf bewaakt.

The guards of the test suite are themselves guarded.

Ronde 19, beslissing 2: we bewaken één niveau en niet het niveau daarboven.
Acht rondes lang is elke bewaking alleen met losse mutatieruns gevalideerd;
die toetsen staan nergens in de suite, dus ze verroten en de volgende ronde
vindt een nieuwe rand. Dit bestand pint elke bewaking vast op **verzonnen**
invoer — niet op de echte boom, want dan test je opnieuw de toestand van
vandaag in plaats van de eigenschap.

Round 19, decision 2: we guard one level, and not the level above it. For
eight rounds every guard was validated only with ad-hoc mutation runs; those
checks live nowhere in the suite, so they rot and the next round finds a new
edge. This file pins every guard on **invented** input — not on the real tree,
because that would again test today's state instead of the property.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import (
    async_show_form_calls,
    fix_flow_steps,
    fixable_issue_keys,
    notice_fixable_kind_error,
    notice_key_pair_error,
    notice_title_error,
)

REPO = Path(__file__).resolve().parents[1]


def _write_package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    package: str,
    files: dict[str, str],
) -> Path:
    """Schrijf een verzonnen pakket in `tmp_path` en maak het importeerbaar.

    Write an invented package into `tmp_path` and make it importable.
    """
    root = tmp_path / package
    root.mkdir()
    (root / "__init__.py").write_text("", encoding="utf-8")
    for name, text in files.items():
        (root / name).write_text(text, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    return root


class TestFixFlowSteps:
    """`fix_flow_steps()` hangt aan de klasse, niet aan hoe je hem opschrijft."""

    def test_it_sees_a_flow_written_as_plain_repairs_flow(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        root = _write_package(
            monkeypatch,
            tmp_path,
            "guardpkg_plain",
            {
                "flow.py": (
                    "import voluptuous as vol\n"
                    "from homeassistant.components.repairs.models import RepairsFlow\n"
                    "\n"
                    "\n"
                    "class Flow(RepairsFlow):\n"
                    "    async def async_step_init(self, user_input=None):\n"
                    '        return self.async_show_form(step_id="plain",'
                    " data_schema=vol.Schema({}))\n"
                ),
            },
        )
        assert fix_flow_steps(root=root, package="guardpkg_plain") == {"plain"}

    def test_it_sees_a_flow_written_as_repairs_models_attribute(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        root = _write_package(
            monkeypatch,
            tmp_path,
            "guardpkg_models",
            {
                "flow.py": (
                    "import voluptuous as vol\n"
                    "from homeassistant.components.repairs import models as repairs_models\n"
                    "\n"
                    "\n"
                    "class Flow(repairs_models.RepairsFlow):\n"
                    "    async def async_step_init(self, user_input=None):\n"
                    '        return self.async_show_form(step_id="repairs_models",'
                    " data_schema=vol.Schema({}))\n"
                ),
            },
        )
        assert fix_flow_steps(root=root, package="guardpkg_models") == {"repairs_models"}

    def test_it_sees_a_flow_written_as_models_attribute(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        root = _write_package(
            monkeypatch,
            tmp_path,
            "guardpkg_models2",
            {
                "flow.py": (
                    "import voluptuous as vol\n"
                    "from homeassistant.components.repairs import models\n"
                    "\n"
                    "\n"
                    "class Flow(models.RepairsFlow):\n"
                    "    async def async_step_init(self, user_input=None):\n"
                    '        return self.async_show_form(step_id="models",'
                    " data_schema=vol.Schema({}))\n"
                ),
            },
        )
        assert fix_flow_steps(root=root, package="guardpkg_models2") == {"models"}

    def test_it_sees_a_subclass_of_a_fix_flow(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        root = _write_package(
            monkeypatch,
            tmp_path,
            "guardpkg_child",
            {
                "manual.py": (
                    "import voluptuous as vol\n"
                    "from homeassistant.components.repairs.models import RepairsFlow\n"
                    "\n"
                    "\n"
                    "class ManualFlow(RepairsFlow):\n"
                    "    async def async_step_init(self, user_input=None):\n"
                    '        return self.async_show_form(step_id="manual",'
                    " data_schema=vol.Schema({}))\n"
                ),
                "child.py": (
                    "import voluptuous as vol\n"
                    "from .manual import ManualFlow\n"
                    "\n"
                    "\n"
                    "class ChildFlow(ManualFlow):\n"
                    "    async def async_step_child(self, user_input=None):\n"
                    '        return self.async_show_form(step_id="child",'
                    " data_schema=vol.Schema({}))\n"
                ),
            },
        )
        assert fix_flow_steps(root=root, package="guardpkg_child") == {"manual", "child"}

    def test_it_ignores_async_show_form_outside_a_fix_flow(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        root = _write_package(
            monkeypatch,
            tmp_path,
            "guardpkg_outside",
            {
                "flow.py": (
                    "import voluptuous as vol\n"
                    "from homeassistant.components.repairs.models import RepairsFlow\n"
                    "\n"
                    "\n"
                    "class NotAFlow:\n"
                    "    async def async_step(self, user_input=None):\n"
                    '        return self.async_show_form(step_id="outside",'
                    " data_schema=vol.Schema({}))\n"
                    "\n"
                    "\n"
                    "class Flow(RepairsFlow):\n"
                    "    async def async_step_init(self, user_input=None):\n"
                    '        return self.async_show_form(step_id="inside",'
                    " data_schema=vol.Schema({}))\n"
                ),
            },
        )
        assert fix_flow_steps(root=root, package="guardpkg_outside") == {"inside"}

    def test_it_sees_a_flow_that_is_not_at_module_level(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Een fix-flow die in een functie staat hoort ook mee te tellen.

        Ronde 20, B2: de loop ging over `tree.body` en zag daardoor alleen
        klassen op modulehoogte; een fabrieksfunctie die een `RepairsFlow`
        teruggeeft viel er stil uit.

        A fix flow defined inside a function must count too. Round 20, B2: the
        loop walked `tree.body` and therefore saw only module-level classes; a
        factory function returning a `RepairsFlow` silently dropped out.
        """
        root = _write_package(
            monkeypatch,
            tmp_path,
            "guardpkg_nested",
            {
                "flow.py": (
                    "import voluptuous as vol\n"
                    "from homeassistant.components.repairs.models import RepairsFlow\n"
                    "\n"
                    "\n"
                    "def maak_flow():\n"
                    "    class NestedFlow(RepairsFlow):\n"
                    "        async def async_step_init(self, user_input=None):\n"
                    '            return self.async_show_form(step_id="nested",'
                    " data_schema=vol.Schema({}))\n"
                    "\n"
                    "    return NestedFlow\n"
                ),
            },
        )
        assert fix_flow_steps(root=root, package="guardpkg_nested") == {"nested"}

    def test_it_sees_a_nested_flow_that_is_never_bound_to_a_module_name(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Ook zonder modulenaam blijft de tweede, zwakkere weg over.

        `getattr(module, ...)` vindt deze klasse niet, dus hier telt de basis
        uit de AST. Dat is bewust zwakker — zie de docstring van
        `fix_flow_steps()`.

        Without a module-level name the second, weaker route remains.
        `getattr(module, ...)` cannot find this class, so here the AST base
        counts. That is deliberately weaker — see `fix_flow_steps()`.
        """
        root = _write_package(
            monkeypatch,
            tmp_path,
            "guardpkg_unbound",
            {
                "flow.py": (
                    "import voluptuous as vol\n"
                    "from homeassistant.components.repairs import models\n"
                    "\n"
                    "\n"
                    "def registreer(register):\n"
                    "    class Verborgen(models.RepairsFlow):\n"
                    "        async def async_step_init(self, user_input=None):\n"
                    '            return self.async_show_form(step_id="verborgen",'
                    " data_schema=vol.Schema({}))\n"
                    "\n"
                    "    register.append(Verborgen)\n"
                ),
            },
        )
        assert fix_flow_steps(root=root, package="guardpkg_unbound") == {"verborgen"}

    def test_it_sees_a_flow_in_a_file_that_did_not_exist_yesterday(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        root = _write_package(
            monkeypatch,
            tmp_path,
            "guardpkg_new",
            {
                "first.py": (
                    "import voluptuous as vol\n"
                    "from homeassistant.components.repairs.models import RepairsFlow\n"
                    "\n"
                    "\n"
                    "class FirstFlow(RepairsFlow):\n"
                    "    async def async_step_init(self, user_input=None):\n"
                    '        return self.async_show_form(step_id="first",'
                    " data_schema=vol.Schema({}))\n"
                ),
            },
        )
        assert fix_flow_steps(root=root, package="guardpkg_new") == {"first"}

        (root / "second.py").write_text(
            "import voluptuous as vol\n"
            "from homeassistant.components.repairs.models import RepairsFlow\n"
            "\n"
            "\n"
            "class SecondFlow(RepairsFlow):\n"
            "    async def async_step_init(self, user_input=None):\n"
            '        return self.async_show_form(step_id="second",'
            " data_schema=vol.Schema({}))\n",
            encoding="utf-8",
        )
        assert fix_flow_steps(root=root, package="guardpkg_new") == {"first", "second"}


class TestFixableIssueKeys:
    """`fixable_issue_keys()` leest de sleutels uit de bron en gooit op een berekende."""

    def test_it_finds_a_literal_key_for_is_fixable_true(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        root = _write_package(
            monkeypatch,
            tmp_path,
            "guardpkg_fixable",
            {
                "problems.py": (
                    "async def report(hass, domain):\n"
                    '    await ir.async_create_issue(hass, domain, "manual_sources",'
                    ' is_fixable=True, translation_key="manual_sources")\n'
                ),
            },
        )
        assert fixable_issue_keys(root=root) == {"manual_sources"}

    def test_it_skips_is_fixable_false(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        root = _write_package(
            monkeypatch,
            tmp_path,
            "guardpkg_not_fixable",
            {
                "problems.py": (
                    "async def report(hass, domain):\n"
                    '    await ir.async_create_issue(hass, domain, "unreadable",'
                    ' is_fixable=False, translation_key="unreadable_entities")\n'
                ),
            },
        )
        assert fixable_issue_keys(root=root) == set()

    def test_it_raises_with_file_and_line_on_a_computed_translation_key(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        root = _write_package(
            monkeypatch,
            tmp_path,
            "guardpkg_computed",
            {
                "problems.py": (
                    'UNWATCHED = "unwatched"\n'
                    "\n"
                    "\n"
                    "async def report(hass, domain):\n"
                    '    await ir.async_create_issue(hass, domain, "computed",'
                    " is_fixable=True, translation_key=UNWATCHED)\n"
                ),
            },
        )
        with pytest.raises(AssertionError, match=r"problems\.py:\d+: is_fixable=True"):
            fixable_issue_keys(root=root)


class TestAsyncShowFormCalls:
    """`async_show_form_calls()` vindt élk formulier, in elke schrijfwijze."""

    def test_it_finds_forms_with_and_without_data_schema_and_any_binding(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        root = _write_package(
            monkeypatch,
            tmp_path,
            "guardpkg_forms",
            {
                "forms.py": (
                    "import voluptuous as vol\n"
                    "\n"
                    "\n"
                    "class Flow:\n"
                    "    def draw(self):\n"
                    '        return self.async_show_form(step_id="met_schema",'
                    " data_schema=vol.Schema({}))\n"
                    "\n"
                    "    async def draw_bare(self):\n"
                    '        return self.async_show_form(step_id="zonder_schema")\n'
                    "\n"
                    "\n"
                    "async def free_function():\n"
                    '    return Flow().async_show_form(step_id="los")\n'
                    "\n"
                    "\n"
                    "def not_bound():\n"
                    '    return iets.async_show_form(step_id="niet_self")\n'
                ),
            },
        )
        found = async_show_form_calls(root=root)
        steps = {step_id for _module, step_id, _schema in found}
        assert steps == {"met_schema", "zonder_schema", "los", "niet_self"}
        by_step = {step_id: schema for _module, step_id, schema in found}
        assert by_step["met_schema"] is not None
        assert by_step["zonder_schema"] is None

    def test_it_keeps_a_non_literal_step_id_as_none(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        root = _write_package(
            monkeypatch,
            tmp_path,
            "guardpkg_nonliteral",
            {
                "forms.py": (
                    'NAME = "berekend"\n'
                    "\n"
                    "\n"
                    "async def free_function():\n"
                    "    return self.async_show_form(step_id=NAME)\n"
                ),
            },
        )
        found = async_show_form_calls(root=root)
        assert found, "een niet-letterlijke step_id hoort niet stil te verdwijnen"
        assert all(step_id is None for _module, step_id, _schema in found)


class TestTheHassfestKeyPairRule:
    """De hassfest-regel uit M3, op verzonnen meldingsblokken."""

    def test_only_description_passes(self) -> None:
        assert notice_key_pair_error("bestand", "melding", {"description": "uitleg"}) is None

    def test_only_fix_flow_passes(self) -> None:
        assert notice_key_pair_error("bestand", "melding", {"fix_flow": {}}) is None

    def test_both_is_an_error(self) -> None:
        error = notice_key_pair_error(
            "bestand", "melding", {"description": "uitleg", "fix_flow": {}}
        )
        assert error is not None and "precies één" in error

    def test_neither_is_an_error(self) -> None:
        error = notice_key_pair_error("bestand", "melding", {})
        assert error is not None and "precies één" in error

    def test_a_notice_with_a_title_passes(self) -> None:
        assert notice_title_error("bestand", "melding", {"title": "Iets"}) is None

    def test_a_missing_title_is_an_error(self) -> None:
        error = notice_title_error("bestand", "melding", {"description": "uitleg"})
        assert error is not None and "title te hebben" in error

    @pytest.mark.parametrize("title", ["", "   ", None, 3])
    def test_a_title_that_says_nothing_is_an_error(self, title: object) -> None:
        error = notice_title_error("bestand", "melding", {"title": title})
        assert error is not None and "niet leeg" in error

    def test_the_fixable_cross_check_holds_both_ways(self) -> None:
        fixable = {"fixbare"}
        assert notice_fixable_kind_error("bestand", "fixbare", {"fix_flow": {}}, fixable) is None
        assert (
            notice_fixable_kind_error("bestand", "losse", {"description": "uitleg"}, fixable)
            is None
        )
        error = notice_fixable_kind_error("bestand", "fixbare", {"description": "uitleg"}, fixable)
        assert error is not None and "fix_flow" in error
        error = notice_fixable_kind_error("bestand", "losse", {"fix_flow": {}}, fixable)
        assert error is not None and "description" in error


class _DummyHome:
    """Genoeg huis voor `open_screen` om bij de `unknown screen`-tak te komen."""

    class hass:
        class config_entries:
            options = None


class TestTheWalkGuard:
    """`TestEveryFormInTheSourceIsWalkedTo` faalt hard op een onbekende stap."""

    async def test_an_unknown_step_really_raises_unknown_screen(self) -> None:
        from test_campaign_editing import open_screen

        with pytest.raises(AssertionError, match="unknown screen verzonnen_scherm"):
            await open_screen(_DummyHome(), "verzonnen_scherm")

    def test_the_walk_compares_the_returned_step_id(self) -> None:
        source = (REPO / "tests" / "test_campaign_editing.py").read_text(encoding="utf-8")
        assert 'assert result["step_id"] == step' in source, (
            "open_screen hoort elke menu-stap tegen de gevraagde step_id te houden"
        )
        assert 'assert result["step_id"] == screen' in source, (
            "de doorlooptest hoort de teruggekregen step_id te vergelijken, "
            "niet alleen te kijken of er iets terugkomt"
        )
        assert 'raise AssertionError(f"unknown screen {screen}")' in source, (
            "een step_id zonder tak in open_screen hoort 'unknown screen ...' te geven"
        )
