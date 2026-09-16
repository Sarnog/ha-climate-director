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

import ast
from pathlib import Path

import pytest
from _ast_helpers import issue_calls
from conftest import (
    async_show_form_calls,
    fix_flow_steps,
    fixable_issue_keys,
    notice_fixable_kind_error,
    notice_key_pair_error,
    notice_title_error,
)
from coverage import Coverage
from coverage.data import CoverageData
from test_repair_notices import (
    created_issue_ids,
    deleted_ids_by_function,
    issue_registry_form_problems,
    unfollowable_issue_ids,
)
from test_the_border import border_offenders

import script.coverage_gate as coverage_gate


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


def _assert_multiline_hint(out: str) -> None:
    """De hint van de vijfde weigering gaat over echte regels (R35-6).

    Een hint met een letterlijke `\\n` erin is één lange regel met zichtbare
    `\\n`; deze helper eist dat er geen letterlijke `\\n` meer in staat en dat de
    uitvoer over meerdere regels valt. Draait in de twee weigertests van
    `TestTheCoverageGate`; de constante zelf wordt apart gemeten.

    The fifth refusal's hint spans real lines (R35-6). A hint with a literal `\\n`
    in it is one long line with visible `\\n`; this helper demands that no literal
    `\\n` stands in it and that the output falls over several lines. It runs in
    the two refusal tests of `TestTheCoverageGate`; the constant itself is
    measured separately.
    """
    assert "\\n" not in out, f"de hint drukt een letterlijke \\n af: {out!r}"
    assert len([line for line in out.splitlines() if line.strip()]) >= 5, (
        f"de hint hoort over meerdere regels te gaan: {out!r}"
    )


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

    async def test_the_walk_fails_when_the_navigation_lands_on_another_screen(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Een leugenachtige `open_screen` hoort de doorlooptest rood te maken.

        Dit is de eigenschap waar het schrappen van de dekkingsbewaking (ronde
        19, V1) op leunt: de doorloop vergelijkt de **teruggekregen** step_id
        met de gevraagde, en kijkt niet alleen of er íets terugkomt. Hier wordt
        dat met een gedraaide meting vastgepind in plaats van met een zoekactie
        in de brontekst — die laatste vorm ging rood zodra iemand dezelfde
        assertie anders opschreef (ronde 20, B3).

        A lying `open_screen` must turn the walk test red. This is the property
        the removal of the coverage guard (round 19, V1) leans on: the walk
        compares the **returned** step id with the requested one, and does not
        merely check that something came back. It is pinned here with a real
        measurement instead of a search through the source text — that earlier
        form went red as soon as anyone wrote the same assertion differently
        (round 20, B3).
        """
        import test_campaign_editing as walk

        async def lying_open_screen(_home: object, _screen: str):
            return "flow", {"type": "form", "step_id": "een_ander_scherm"}, None

        monkeypatch.setattr(walk, "open_screen", lying_open_screen)

        with pytest.raises(AssertionError, match="open_screen liep naar"):
            await walk.TestEveryFormInTheSourceIsWalkedTo().test_every_step_id_in_the_source_opens()


class TestTheBorderGuard:
    """`border_offenders()` bewaakt de engine-grens, op verzonnen invoer.

    `border_offenders()` guards the engine border, on invented input.
    """

    def test_it_sees_a_plain_homeassistant_import(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        root = _write_package(
            monkeypatch,
            tmp_path,
            "guardpkg_border_plain",
            {"gates.py": "import homeassistant\n"},
        )
        assert border_offenders(root=root) == ["gates.py:1: import homeassistant"]

    def test_it_sees_a_homeassistant_submodule_import(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        root = _write_package(
            monkeypatch,
            tmp_path,
            "guardpkg_border_submodule",
            {"gates.py": "import homeassistant.util.dt\n"},
        )
        assert border_offenders(root=root) == ["gates.py:1: import homeassistant.util.dt"]

    def test_it_sees_a_from_homeassistant_import(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        root = _write_package(
            monkeypatch,
            tmp_path,
            "guardpkg_border_from",
            {"gates.py": "from homeassistant.const import X\n"},
        )
        assert border_offenders(root=root) == ["gates.py:1: from homeassistant.const import ..."]

    def test_it_sees_imports_inside_a_function_and_under_type_checking(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """De ast.walk-kant: een import die niet op modulehoogte staat telt ook.

        The ast.walk side: an import that is not at module level counts too.
        """
        root = _write_package(
            monkeypatch,
            tmp_path,
            "guardpkg_border_nested",
            {
                "func.py": "def laad():\n    from homeassistant import const\n",
                "typing.py": (
                    "from typing import TYPE_CHECKING\n"
                    "if TYPE_CHECKING:\n"
                    "    from homeassistant import const\n"
                ),
            },
        )
        assert border_offenders(root=root) == [
            "func.py:2: from homeassistant import ...",
            "typing.py:3: from homeassistant import ...",
        ]

    def test_it_sees_a_file_that_did_not_exist_yesterday_and_one_in_a_submap(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """De scan leest de schijf per aanroep, en vindt ook submappen.

        The scan reads the disk per call, and finds subdirectories too.
        """
        root = _write_package(monkeypatch, tmp_path, "guardpkg_border_grow", {})
        assert border_offenders(root=root) == []
        (root / "later.py").write_text("from homeassistant import const\n", encoding="utf-8")
        sub = root / "sub"
        sub.mkdir()
        (sub / "gates.py").write_text("from homeassistant import const\n", encoding="utf-8")
        assert border_offenders(root=root) == [
            "later.py:1: from homeassistant import ...",
            "sub/gates.py:1: from homeassistant import ...",
        ]

    def test_it_reports_no_false_positive_on_lookalike_imports(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        root = _write_package(
            monkeypatch,
            tmp_path,
            "guardpkg_border_lookalike",
            {
                "look.py": "import homeassistantx\n",
                "helper.py": "from homeassistant_helper import y\n",
            },
        )
        assert border_offenders(root=root) == []

    def test_an_empty_or_unfindable_tree_is_an_error(self, tmp_path: Path) -> None:
        """Een lege scan is een fout, geen groene test — dat is R1.

        An empty scan is an error, not a green test — that is R1.
        """
        empty = tmp_path / "lege_map"
        empty.mkdir()
        with pytest.raises(AssertionError, match="geen bestanden gevonden"):
            border_offenders(root=empty)
        with pytest.raises(AssertionError, match="geen bestanden gevonden"):
            border_offenders(root=tmp_path / "bestaat_niet")


class TestTheCoverageGate:
    """De dekkingspoort keurt geen lege of halve meting goed (ronde 32, R32-4).

    The coverage gate approves no empty or half measurement (round 32, R32-4).

    Alle invoer hier is verzonnen: een pakketje in `tmp_path` met één of twee
    bestanden, en een gegevensbestand dat die bestanden wel of niet noemt. Zo
    meet de test de eigenschap en niet de toestand van vandaag. Het vierde geval
    is de scherpste: een module die nooit geïmporteerd wordt staat in geen enkele
    meting, en zonder die eis zou zijn dekking stilzwijgend 100% zijn.

    All input here is invented: a small package in `tmp_path` with one or two
    files, and a data file that does or does not name those files. That way the
    test measures the property and not today's state. The fourth case is the
    sharpest: a module that is never imported appears in no measurement, and
    without that demand its coverage would silently be 100%.
    """

    def _package(self, tmp_path: Path, files: dict[str, str]) -> Path:
        """Een verzonnen pakket met alleen de gegeven bestanden.

        An invented package with only the given files.
        """
        root = tmp_path / "pkg"
        root.mkdir()
        for name, text in files.items():
            (root / name).write_text(text, encoding="utf-8")
        return root

    def _measurement(self, path: Path, measured: dict[str, set[int]]) -> Path:
        """Een coverage-gegevensbestand met precies de gegeven metingen.

        A coverage data file with exactly the given measurements.
        """
        data = CoverageData(basename=str(path))
        data.add_lines(measured)
        data.write()
        return path

    def _run(self, data: Path, package: Path) -> int:
        return coverage_gate.main(["--data-file", str(data), "--package", str(package)])

    def test_a_missing_data_file_is_refused(self, tmp_path: Path, capsys) -> None:
        """Zonder gegevensbestand valt er niets goed te keuren."""
        data = tmp_path / "bestaat_niet"
        assert self._run(data, tmp_path) == 1
        assert str(data) in capsys.readouterr().out

    def test_an_empty_measurement_is_refused(self, tmp_path: Path, capsys) -> None:
        """Een meting zonder één bestand is geen goedkeuring waard."""
        package = self._package(tmp_path, {"a.py": "x = 1\n"})
        data = self._measurement(tmp_path / "meting.data", {})
        assert self._run(data, package) == 1
        assert "is leeg" in capsys.readouterr().out

    def test_a_measurement_without_the_package_is_refused(self, tmp_path: Path, capsys) -> None:
        """Een meting over een andere map gaat niet over dit pakket."""
        package = self._package(tmp_path, {"a.py": "x = 1\n"})
        elsewhere = tmp_path / "elders.py"
        elsewhere.write_text("y = 1\n", encoding="utf-8")
        data = self._measurement(tmp_path / "elders.data", {str(elsewhere): {1}})
        assert self._run(data, package) == 1
        assert "geen enkel gemeten bestand" in capsys.readouterr().out

    def test_a_measurement_missing_a_module_is_refused(self, tmp_path: Path, capsys) -> None:
        """Een module die nooit geïmporteerd wordt moet opvallen."""
        package = self._package(tmp_path, {"a.py": "x = 1\n", "b.py": "y = 1\n"})
        data = self._measurement(tmp_path / "half.data", {str(package / "a.py"): {1}})
        assert self._run(data, package) == 1
        out = capsys.readouterr().out
        assert "b.py" in out and "a.py" not in out

    def test_a_complete_measurement_is_accepted(self, tmp_path: Path, capsys) -> None:
        """Een volledige meting zonder gemiste regel komt er doorheen."""
        package = self._package(tmp_path, {"a.py": "x = 1\n"})
        data = self._measurement(tmp_path / "heel.data", {str(package / "a.py"): {1}})
        assert self._run(data, package) == 0
        assert "OK" in capsys.readouterr().out

    def test_a_missed_line_is_reported_with_its_file_and_line(self, tmp_path: Path, capsys) -> None:
        """Een gemiste regel valt om, met het bestand en de regel erbij."""
        package = self._package(tmp_path, {"a.py": "x = 1\nif x:\n    y = 2\n"})
        data = self._measurement(tmp_path / "gemist.data", {str(package / "a.py"): {1}})
        assert self._run(data, package) == 1
        out = capsys.readouterr().out
        assert "a.py" in out and "2" in out and "3" in out

    def test_a_line_the_patterns_hide_must_be_named(self, tmp_path: Path, capsys) -> None:
        """Een regel die coverage overslaat hoort een naam te hebben (R34-2).

        Coverage houdt een `...`-stub buiten de telling op een patroon, en zonder
        whitelist zou die regel stil uit "nul gemiste regels" verdwijnen: de poort
        zou groen staan over een regel die hij nooit gezien heeft. Hier is de
        stub niet genoemd, dus valt de poort om en noemt hij de regel zelf.

        A line coverage skips has to have a name (R34-2). Coverage keeps a `...`
        stub out of the count on a pattern, and without the whitelist that line
        would quietly disappear from "zero missed lines": the gate would stand
        green about a line it never saw. Here the stub is unnamed, so the gate
        drops and names the line itself.
        """
        package = self._package(
            tmp_path, {"a.py": "x = 1\n\n\nclass P:\n    def een(self) -> None: ...\n"}
        )
        data = self._measurement(tmp_path / "stub.data", {str(package / "a.py"): {1, 4}})
        assert self._run(data, package) == 1
        out = capsys.readouterr().out
        assert "zonder naam" in out
        assert "a.py:5" in out and "def een(self) -> None: ..." in out
        _assert_multiline_hint(out)

    def test_a_named_line_the_patterns_hide_is_accepted(
        self, tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Met een naam erbij is precies diezelfde meting wel goed (R34-2).

        De whitelist wordt hier verzonnen in plaats van gelezen, want hij hoort
        bij dit pakket en niet bij een pakketje in `tmp_path`.

        With a name alongside, that very measurement is fine (R34-2). The
        whitelist is invented here rather than read, since it belongs to this
        package and not to a small package in `tmp_path`.
        """
        monkeypatch.setattr(
            coverage_gate,
            "NAMED_EXCLUSIONS",
            {"a.py": ("def een(self) -> None: ...",)},
        )
        package = self._package(
            tmp_path, {"a.py": "x = 1\n\n\nclass P:\n    def een(self) -> None: ...\n"}
        )
        data = self._measurement(tmp_path / "stub.data", {str(package / "a.py"): {1, 4}})
        assert self._run(data, package) == 0
        assert "regels buiten de meting: 1" in capsys.readouterr().out

    def test_a_name_that_hides_nothing_is_refused(
        self, tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Een whitelist die niets meer verbergt is verouderd, geen goedkeuring (R34-2).

        Een naam zonder regel wekt de indruk dat er iets afgesproken is terwijl de
        meting die regel gewoon meet; dan hoort de naam eruit in plaats van te
        blijven staan.

        A whitelist that hides nothing anymore is stale, not an approval (R34-2).
        A name without a line suggests something was agreed while the measurement
        simply measures that line; then the name belongs out instead of staying.
        """
        monkeypatch.setattr(coverage_gate, "NAMED_EXCLUSIONS", {"a.py": ("iets_anders",)})
        package = self._package(tmp_path, {"a.py": "if 1:\n    x = 1\n"})
        data = self._measurement(tmp_path / "gewoon.data", {str(package / "a.py"): {1, 2}})
        assert self._run(data, package) == 1
        out = capsys.readouterr().out
        assert "noemt een regel die de meting niet meer overslaat" in out
        assert "iets_anders" in out
        _assert_multiline_hint(out)

    def test_a_comment_behind_a_stub_is_not_a_line_without_a_name(
        self, tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Een commentaarregel achter een stub vraagt geen naam (R35-5).

        Coverage sluit de hele regio van een `...`-stub mee uit — de decorator
        erboven, een commentaarregel ertussen, de vervolgregels van een
        meerregelige `def` — maar zo'n regel kan zonder de uitsluiting nooit
        gemeten worden. De whitelist hoort hem dus niet te noemen; anders hing de
        poort aan de letterlijke tekst van een commentaar.

        A comment line behind a stub asks for no name (R35-5). Coverage excludes
        the whole region of a `...` stub — the decorator above it, a comment line
        in between, the continuation lines of a multi-line `def` — but such a line
        could never be measured without the exclusion. The whitelist should
        therefore not name it; otherwise the gate hung on the literal text of a
        comment.
        """
        monkeypatch.setattr(
            coverage_gate,
            "NAMED_EXCLUSIONS",
            {
                "a.py": (
                    "def een(self) -> None: ...",
                    "def twee(self) -> None: ...",
                )
            },
        )
        package = self._package(
            tmp_path,
            {
                "a.py": (
                    "x = 1\n"
                    "\n"
                    "\n"
                    "class P:\n"
                    "    def een(self) -> None: ...\n"
                    "    # een commentaar\n"
                    "    def twee(self) -> None: ...\n"
                )
            },
        )
        data = self._measurement(tmp_path / "comment.data", {str(package / "a.py"): {1, 4}})
        assert self._run(data, package) == 0
        assert "regels buiten de meting: 2" in capsys.readouterr().out

    def test_the_exclusion_hint_breaks_its_lines(self) -> None:
        """De hint van de vijfde weigering breekt zijn regels echt af (R35-6).

        Ronde 34 schreef de hint met `"\\\\n"` in plaats van `"\\n"`, dus drukte hij
        één lange regel met zichtbare `\\n` af. Deze test meet de constante zelf, en
        de twee weigertests hierboven (`_assert_multiline_hint`) meten de uitvoer.

        The fifth refusal's hint really breaks its lines (R35-6). Round 34 wrote
        the hint with `"\\\\n"` instead of `"\\n"`, so it printed one long line with
        visible `\\n`. This test measures the constant itself, and the two refusal
        tests above (`_assert_multiline_hint`) measure the output.
        """
        hint = coverage_gate.EXCLUSION_HINT
        assert "\\n" not in hint
        assert "\n" in hint
        assert len([line for line in hint.splitlines() if line.strip()]) >= 5
        assert "NAMED_EXCLUSIONS" in hint


class TestTheMeasurementNextToATestStaysUntouched:
    """Een test raakt de dekkingsmeting naast zich niet aan (ronde 36, R36-4).

    `test_reachable_branches_deep.py::test_every_line_outside_the_measurement_has_a_name`
    bouwde een `Coverage()` zonder `data_file`, en dat wijst naar het
    standaardbestand `.coverage`. `hidden_lines()` roept `analysis2()` aan, en
    gemeten liet dat het bestaande `.coverage` leeg achter: 39 → 0 gemeten
    bestanden, waarna `coverage report` "No data to report" zei en de poort "de
    meting is leeg". `Coverage` beschrijft `data_file=None` zelf als "geen
    gegevensbestand"; dan wordt er niets gelezen en niets geschreven.

    Deze test verzet de map naar `tmp_path`, maakt daar een echt meetbestand
    onder de standaardnaam `.coverage`, en eist dat zowel de functie onder
    bewaking als de bewaringstest zelf dat bestand ongemoeid laten — grootte én
    `measured_files()` vóór en ná gelijk. Wie de test terugzet op `Coverage()`
    maakt deze test rood, en dat is precies de bedoeling: de meting waar een test
    naast staat hoort hij niet aan te raken.

    A test does not touch the coverage measurement next to it (round 36, R36-4).
    `test_reachable_branches_deep.py::test_every_line_outside_the_measurement_has_a_name`
    built a `Coverage()` without `data_file`, which points at the default
    `.coverage`. `hidden_lines()` calls `analysis2()`, and measured, that left the
    existing `.coverage` empty: 39 → 0 measured files, after which
    `coverage report` said "No data to report" and the gate "the measurement is
    empty". `Coverage` itself describes `data_file=None` as "no data file at
    all"; then nothing is read and nothing is written.

    This test moves the working directory to `tmp_path`, creates a real
    measurement there under the default name `.coverage`, and demands that both
    the function under guard and the guard test itself leave that file alone —
    size and `measured_files()` equal before and after. Reverting the test to
    `Coverage()` turns this test red, which is exactly the point: a test should
    not touch the measurement it stands next to.
    """

    @staticmethod
    def _measurement(path: Path, measured: dict[str, set[int]]) -> Path:
        """Schrijf een echt meetbestand op `path`.

        Write a real measurement file at `path`.
        """
        data = CoverageData(basename=str(path))
        data.add_lines(measured)
        data.write()
        return path

    @staticmethod
    def _fingerprint(path: Path) -> tuple[int, set[str]]:
        """Grootte en gemeten bestanden van een meetbestand, alleen-lezen.

        Size and measured files of a measurement file, read-only.
        """
        data = CoverageData(basename=str(path))
        data.read()
        return path.stat().st_size, set(data.measured_files())

    def test_a_fabricated_measurement_survives_the_whitelist_guard(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        measured = tmp_path / "measured.py"
        measured.write_text("x = 1\n", encoding="utf-8")
        # Het standaarddatabestand heet in de map waarin je staat `.coverage`, dus
        # verzetten we de map: dan is dit verzonnen bestand precies degene die
        # `Coverage()` zou aanraken.
        #
        # The default data file is called `.coverage` in the directory you stand
        # in, so we move there: this invented file is then exactly the one
        # `Coverage()` would touch.
        monkeypatch.chdir(tmp_path)
        data_path = self._measurement(tmp_path / ".coverage", {str(measured): {1}})
        before = self._fingerprint(data_path)
        assert before[1] == {str(measured)}, "het verzonnen meetbestand is niet gevuld"

        coverage_gate.hidden_lines(Coverage(data_file=None), coverage_gate.PACKAGE)
        assert self._fingerprint(data_path) == before, (
            "de functie onder bewaking raakt de meting naast zich aan"
        )

        from test_reachable_branches_deep import (
            test_every_line_outside_the_measurement_has_a_name,
        )

        test_every_line_outside_the_measurement_has_a_name()
        assert self._fingerprint(data_path) == before, (
            "de bewaringstest zelf raakt de meting naast zich aan"
        )


class TestTheRepairNoticeGuard:
    """Een onvolgbaar issue-id meldt zich in plaats van stil over te slaan.

    An unfollowable issue id reports itself instead of being skipped silently.

    Ronde 32 (R32-6): `_issue_id_key` gaf `None` voor een f-string, een
    samenvoeging of een variabele, en de verzamelfunctie sloeg die melding
    vervolgens over. Daarmee viel ze uit de unload-controle zonder één woord.
    Volgbaar is een hulpje, een moduleconstante met een letterlijke string, of de
    letterlijke string zelf — de rest is een fout met bestand en regelnummer.

    Round 32 (R32-6): `_issue_id_key` returned `None` for an f-string, a
    concatenation or a variable, and the collector then skipped that notice. That
    took it out of the unload check without a word. Followable is a helper, a
    module constant holding a literal string, or the literal string itself — the
    rest is an error with file and line number.
    """

    def _package(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        name: str,
        body: str,
    ) -> Path:
        return _write_package(monkeypatch, tmp_path, name, {"problems.py": body})

    def test_a_literal_id_is_followed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        root = self._package(
            monkeypatch,
            tmp_path,
            "noticepkg_literal",
            'async def report(hass, domain):\n    ir.async_create_issue(hass, domain, "probe")\n',
        )
        assert created_issue_ids(root=root) == {"probe"}

    def test_a_helper_id_is_followed(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        root = self._package(
            monkeypatch,
            tmp_path,
            "noticepkg_helper",
            "def _probe_issue_id(entry_id):\n"
            '    return f"probe_{entry_id}"\n'
            "\n"
            "\n"
            "async def report(hass, domain, entry_id):\n"
            "    ir.async_create_issue(hass, domain, _probe_issue_id(entry_id))\n",
        )
        assert created_issue_ids(root=root) == {"_probe_issue_id"}

    def test_a_module_constant_is_followed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        root = self._package(
            monkeypatch,
            tmp_path,
            "noticepkg_constant",
            'PROBE_ISSUE = "probe"\n'
            "\n"
            "\n"
            "async def report(hass, domain):\n"
            "    ir.async_create_issue(hass, domain, PROBE_ISSUE)\n",
        )
        assert created_issue_ids(root=root) == {"PROBE_ISSUE"}

    @pytest.mark.parametrize(
        "argument",
        ['f"probe_{entry_id}"', '"probe_" + entry_id', "issue_id"],
    )
    def test_an_id_it_cannot_follow_is_refused(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        argument: str,
    ) -> None:
        """De f-string, de samenvoeging en de variabele melden zich alle drie."""
        root = self._package(
            monkeypatch,
            tmp_path,
            "noticepkg_unfollowable",
            "async def report(hass, domain, entry_id):\n"
            "    issue_id = entry_id\n"
            f"    ir.async_create_issue(hass, domain, {argument})\n",
        )
        offenders = unfollowable_issue_ids(root=root)
        assert len(offenders) == 1 and offenders[0].startswith("problems.py:3:")
        with pytest.raises(AssertionError, match=r"problems\.py:3:"):
            created_issue_ids(root=root)

    def test_an_unfollowable_delete_is_refused_too(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Dezelfde eis geldt voor de `async_delete_issue`-kant."""
        root = self._package(
            monkeypatch,
            tmp_path,
            "noticepkg_delete",
            "async def clear(hass, domain, entry_id):\n"
            '    ir.async_delete_issue(hass, domain, f"probe_{entry_id}")\n',
        )
        with pytest.raises(AssertionError, match=r"problems\.py:2: async_delete_issue"):
            deleted_ids_by_function(root=root)


class TestTheNoticeCallMatch:
    """Elke meldingsaanroep telt mee, hoe hij ook geïmporteerd is (ronde 35, R35-1).

    Vier lezers in de testset liepen elk hun eigen AST af en matchten alleen
    `ast.Attribute` — `ir.async_create_issue(...)`. Een kale naam of een
    `from … import … as x`-alias glipte er langs, en daarmee hing de hele
    meldingsbewaking (wissen bij het uitladen, de fixable-inventarisatie, de
    gidsen en de placeholders) aan één schrijfwijze. De match woont sinds ronde
    35 in `tests/_ast_helpers.py`; deze tests pinnen hem op verzonnen invoer
    vast: beide spellingen tellen, een naam zonder de juiste import niet.

    Every notice call counts, however it was imported (round 35, R35-1). Four
    readers in the suite each walked their own AST and matched only
    `ast.Attribute` — `ir.async_create_issue(...)`. A bare name or a
    `from … import … as x` alias slipped past it, and with that the whole notice
    guard (clearing on unload, the fixable inventory, the guides and the
    placeholders) hung on one spelling. The match lives in
    `tests/_ast_helpers.py` since round 35; these tests pin it on invented input:
    both spellings count, a name without the right import does not.
    """

    @staticmethod
    def _count(body: str, attribute: str = "async_create_issue") -> int:
        """Aantal aanroepen van `attribute` in een verzonnen bestand.

        The number of calls of `attribute` in an invented file.
        """
        return len(issue_calls(ast.parse(body), attribute))

    def test_an_attribute_call_counts(self) -> None:
        """`ir.async_create_issue(...)` blijft tellen, ook zonder import ernaast."""
        assert self._count('ir.async_create_issue(hass, domain, "probe")\n') == 1

    def test_a_bare_imported_name_counts(self) -> None:
        """Een kale naam na de import telt mee — dat was het gat."""
        assert (
            self._count(
                "from homeassistant.helpers.issue_registry import async_create_issue\n"
                'async_create_issue(hass, domain, "probe")\n'
            )
            == 1
        )

    def test_an_aliased_imported_name_counts(self) -> None:
        """`from … import … as x` wordt opgelost, hoe de alias ook heet."""
        assert (
            self._count(
                "from homeassistant.helpers.issue_registry import async_create_issue as note\n"
                'note(hass, domain, "probe")\n'
            )
            == 1
        )

    def test_a_lookalike_without_the_import_does_not_count(self) -> None:
        """Een kale naam zonder de juiste import is geen melding."""
        assert self._count('async_create_issue(hass, domain, "probe")\n') == 0

    def test_a_like_named_function_from_elsewhere_does_not_count(self) -> None:
        """Een gelijknamige functie uit een ander pakket telt niet mee."""
        assert (
            self._count(
                "from other.package import async_create_issue\n"
                'async_create_issue(hass, domain, "probe")\n'
            )
            == 0
        )

    def test_the_delete_side_is_matched_too(self) -> None:
        """Dezelfde regel geldt voor `async_delete_issue`."""
        assert (
            self._count(
                "from homeassistant.helpers import issue_registry as x\n"
                'x.async_delete_issue(hass, domain, "probe")\n',
                "async_delete_issue",
            )
            == 1
        )

    def test_a_bare_name_with_a_helper_id_reaches_the_unload_guard(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """De hele keten: een kale naam met een helper-id wordt gezien."""
        root = _write_package(
            monkeypatch,
            tmp_path,
            "noticepkg_barename",
            {
                "problems.py": (
                    "from homeassistant.helpers.issue_registry import async_create_issue\n"
                    "\n"
                    "\n"
                    "def _probe_issue_id(entry_id):\n"
                    '    return f"probe_{entry_id}"\n'
                    "\n"
                    "\n"
                    "async def report(hass, domain, entry_id):\n"
                    "    async_create_issue(hass, domain, _probe_issue_id(entry_id))\n"
                )
            },
        )
        assert created_issue_ids(root=root) == {"_probe_issue_id"}


class TestTheIssueRegistryForm:
    """De enige bestaande vorm van de registry is de enige die de bewaking dekt.

    The only existing shape of the registry is the only one the guard covers.

    De meldingsbewaking leest de bron; een aanroep onder een eigen naam
    (`_create = ir.async_create_issue`), via `getattr` of in een
    `functools.partial` glipt er langs (ronde 35, R35-1). In plaats van een derde
    spelling aan `_ast_helpers` toe te voegen legt `issue_registry_form_problems`
    vast dat zulke vormen niet bestaan. Deze tests pinnen die afspraak op
    **verzonnen** invoer vast: elke verboden vorm meldt zich, de toegestane vorm
    niet.

    The notice guard reads the source; a call under its own name
    (`_create = ir.async_create_issue`), through `getattr` or inside a
    `functools.partial` slips past it (round 35, R35-1). Instead of adding a third
    spelling to `_ast_helpers`, `issue_registry_form_problems` pins down that such
    shapes do not exist. These tests pin that agreement on **invented** input:
    every forbidden shape reports itself, the allowed one does not.
    """

    @staticmethod
    def _problems(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path, body: str, name: str = "regpkg"
    ) -> list[str]:
        root = _write_package(monkeypatch, tmp_path, name, {"problems.py": body})
        return issue_registry_form_problems(root=root)

    def test_the_canonical_form_is_allowed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """`from … import issue_registry as ir` plus een directe aanroep is goed."""
        assert (
            self._problems(
                monkeypatch,
                tmp_path,
                "from homeassistant.helpers import issue_registry as ir\n"
                "\n"
                "\n"
                "async def report(hass, domain):\n"
                '    ir.async_create_issue(hass, domain, "probe")\n'
                '    ir.async_delete_issue(hass, domain, "probe")\n',
            )
            == []
        )

    def test_a_direct_function_import_is_refused(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """De functie rechtstreeks importeren haalt de aanroep uit de vorm."""
        problems = self._problems(
            monkeypatch,
            tmp_path,
            "from homeassistant.helpers.issue_registry import async_create_issue\n",
        )
        assert problems and "rechtstreeks" in problems[0]

    def test_another_alias_for_the_module_is_refused(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """De module onder een andere naam importeren mag niet."""
        problems = self._problems(
            monkeypatch,
            tmp_path,
            "from homeassistant.helpers import issue_registry as x\n",
        )
        assert problems and "als `x`" in problems[0]

    def test_a_module_level_alias_is_refused(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """`_create = ir.async_create_issue` is precies het gat van ronde 35."""
        problems = self._problems(
            monkeypatch,
            tmp_path,
            "from homeassistant.helpers import issue_registry as ir\n"
            "\n"
            "_create = ir.async_create_issue\n",
        )
        assert problems and "aan een naam gegeven" in problems[0]

    def test_a_partial_is_refused(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Een `functools.partial` rond de meldingsfunctie mag niet."""
        problems = self._problems(
            monkeypatch,
            tmp_path,
            "import functools\n"
            "from homeassistant.helpers import issue_registry as ir\n"
            "\n"
            "_create = functools.partial(ir.async_create_issue, None, None)\n",
        )
        assert any("als argument doorgegeven" in problem for problem in problems)

    def test_a_getattr_is_refused(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """`getattr(ir, "async_create_issue")` mag niet."""
        problems = self._problems(
            monkeypatch,
            tmp_path,
            "from homeassistant.helpers import issue_registry as ir\n"
            "\n"
            "\n"
            "async def report(hass, domain):\n"
            '    getattr(ir, "async_create_issue")(hass, domain, "probe")\n',
        )
        assert any("via `getattr`" in problem for problem in problems)
