"""De selectie draait precies de toetsen van het deel dat veranderde.

The selection runs exactly the tests of the part that changed.

`script/select_tests.py` kiest de toetsbestanden uit `tests/impact_map.json`, en
`script/run_tests.py` vergelijkt na elke run wat de toetsen echt uitvoerden en
openden met die kaart. Deze toetsen zetten de regels vast met een eigen kaart, los
van de echte: alles bij twijfel (geen kaart, een gedeeld bestand, een verdwenen
toets), anders alleen wie het gewijzigde bestand, zijn map of zijn pakketmodule
raakt; en een kaart die een uitgevoerde of geopende invoer mist, laat de CI vallen.

`script/select_tests.py` picks the test files from `tests/impact_map.json`, and
`script/run_tests.py` compares after every run what the tests really executed and
opened with that map. These tests pin the rules down with a map of their own,
apart from the real one: everything when in doubt (no map, a shared file, a
vanished test), otherwise only whoever touches the changed file, its directory or
its package module; and a map that misses an executed or opened input drops the CI.

Dekking: deze toetsen lezen geen gids of vertaling; de paden onder `docs/install/`
en `translations/` zijn namen op een verzonnen kaart. Wel gedekt: de regels van de
selectie, het ontleden van `git diff --name-status`, de eis aan de kaart in de CI
en het bijwerken ervan lokaal, en welke paden de recorder bewaart. Niet gedekt: de
echte kaart zelf, behalve dat hij alleen bestaande toetsbestanden noemt - die
vergelijkt elke run met wat hij meet.

Coverage: these tests read no guide and no translation; the paths under
`docs/install/` and `translations/` are names on a made-up map. Covered: the rules
of the selection, the parsing of `git diff --name-status`, the demand on the map in
CI and its update locally, and which paths the recorder keeps. Not covered: the
real map itself, except that it names only existing test files - every run
compares that with what it measures.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import impact_recorder
import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "script" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sel = _load("select_tests")
runner = _load("run_tests")

IMPACT = {
    "tests/test_guide.py": ["docs/install/", "docs/install/nl.md"],
    "tests/test_engine.py": ["custom_components/climate_director/engine/gates.py"],
    "tests/test_live.py": [
        "custom_components/climate_director/coordinator.py",
        "custom_components/climate_director/translations/nl.json",
    ],
}


class TestTheSelection:
    """Wat er draait bij welke wijziging. / What runs for which change."""

    def test_without_a_map_everything_runs(self) -> None:
        assert sel.select({"docs/install/nl.md": "M"}, None) == sel.ALL

    @pytest.mark.parametrize(
        "path",
        [
            "pyproject.toml",
            "requirements_test.txt",
            "script/select_tests.py",
            "script/run_tests.py",
            "script/coverage_gate.py",
            ".github/workflows/tests.yaml",
            "tests/conftest.py",
            "tests/harness_live.py",
            "tests/impact_recorder.py",
        ],
    )
    def test_a_shared_file_runs_everything(self, path: str) -> None:
        assert sel.select({path: "M"}, IMPACT) == sel.ALL

    def test_a_changed_test_runs_itself(self) -> None:
        assert sel.select({"tests/test_select_tests.py": "M"}, {}) == ["tests/test_select_tests.py"]

    def test_a_changed_test_also_runs_whoever_reads_the_tests(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        impact = dict(IMPACT, **{"tests/test_timeless.py": ["tests/"]})
        monkeypatch.setattr(sel, "ROOT", _fake_root(tmp_path, impact))
        assert sel.select({"tests/test_guide.py": "M"}, impact) == [
            "tests/test_guide.py",
            "tests/test_timeless.py",
        ]

    def test_a_vanished_test_runs_everything(self) -> None:
        assert sel.select({"tests/test_gone.py": "D"}, IMPACT) == sel.ALL

    def test_a_text_runs_its_readers_only(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(sel, "ROOT", _fake_root(tmp_path, IMPACT))
        assert sel.select({"docs/install/nl.md": "M"}, IMPACT) == ["tests/test_guide.py"]
        assert sel.select(
            {"custom_components/climate_director/translations/nl.json": "M"}, IMPACT
        ) == ["tests/test_live.py"]

    def test_a_new_file_runs_whoever_walks_its_directory(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(sel, "ROOT", _fake_root(tmp_path, IMPACT))
        assert sel.select({"docs/install/pt.md": "A"}, IMPACT) == ["tests/test_guide.py"]

    def test_package_code_runs_whoever_executes_it(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(sel, "ROOT", _fake_root(tmp_path, IMPACT))
        changed = {"custom_components/climate_director/engine/gates.py": "M"}
        assert sel.select(changed, IMPACT) == ["tests/test_engine.py"]

    def test_package_code_runs_whoever_imports_it(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        root = _fake_root(tmp_path, IMPACT)
        (root / "tests" / "test_guide.py").write_text(
            "from custom_components.climate_director.engine import gates\n", encoding="utf-8"
        )
        package = root / "custom_components" / "climate_director" / "engine"
        package.mkdir(parents=True)
        (package / "gates.py").write_text("", encoding="utf-8")
        monkeypatch.setattr(sel, "ROOT", root)
        changed = {"custom_components/climate_director/engine/gates.py": "M"}
        assert sel.select(changed, IMPACT) == ["tests/test_engine.py", "tests/test_guide.py"]

    def test_a_file_nobody_touches_runs_nothing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(sel, "ROOT", _fake_root(tmp_path, IMPACT))
        assert sel.select({"brand/icon.png": "M", "ROADMAP.md": "M"}, IMPACT) == []

    def test_mypy_and_ruff_follow_their_own_part(self) -> None:
        assert sel.needs_mypy(["custom_components/climate_director/sensor.py"])
        assert sel.needs_mypy(["pyproject.toml"])
        assert not sel.needs_mypy(["tests/test_x.py", "ROADMAP.md"])
        assert sel.needs_lint(["tests/test_x.py"])
        assert not sel.needs_lint(["ROADMAP.md"])

    def test_the_diff_reads_as_one_letter_per_path(self) -> None:
        output = "M\tREADME.md\nD\ttests/test_old.py\nA\ttests/test_new.py\n"
        assert sel.parse_name_status(output) == {
            "README.md": "M",
            "tests/test_old.py": "D",
            "tests/test_new.py": "A",
        }

    def test_an_unknown_base_runs_everything(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CD_BASE", "0000000000000000000000000000000000000000")
        assert sel.base_ref() is None
        assert sel.current_selection() == (sel.ALL, None)

    def test_the_real_map_names_real_test_files(self) -> None:
        impact = sel.load_map() or {}
        assert all(sel.is_test_file(name) for name in impact)
        assert all((ROOT / name).is_file() for name in impact)


class TestTheMapCheck:
    """Een kaart die iets mist laat de CI vallen. / A map that misses something drops CI."""

    def test_ci_drops_on_a_missing_input(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        recorded = _recorded({"tests/test_guide.py": {"docs/install/nl.md", "docs/install/de.md"}})
        assert self._judge(monkeypatch, tmp_path, recorded, full=False) == 1

    def test_ci_passes_when_the_map_carries_it(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        recorded = _recorded({"tests/test_guide.py": {"docs/install/nl.md"}})
        assert self._judge(monkeypatch, tmp_path, recorded, full=False) == 0

    def test_a_package_file_opened_as_text_is_no_demand(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        recorded = runner.Recorded()
        recorded.add("tests/test_guide.py", "docs/install/nl.md", required=True)
        recorded.add(
            "tests/test_guide.py", "custom_components/climate_director/sensor.py", required=False
        )
        assert self._judge(monkeypatch, tmp_path, recorded, full=False) == 0

    def test_a_full_run_drops_on_a_test_that_did_not_run(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        recorded = _recorded({"tests/test_guide.py": {"docs/install/nl.md"}})
        assert self._judge(monkeypatch, tmp_path, recorded, full=True) == 1

    def test_locally_the_map_is_brought_up_to_date(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("CI", raising=False)
        target = tmp_path / "impact_map.json"
        target.write_text(json.dumps({"tests/test_guide.py": ["docs/install/nl.md"]}))
        monkeypatch.setattr(runner.sel, "MAP", target)
        recorded = _recorded({"tests/test_guide.py": {"docs/install/de.md"}})
        assert runner.compare_and_keep(recorded, full=False) == 0
        assert json.loads(target.read_text()) == {
            "tests/test_guide.py": ["docs/install/de.md", "docs/install/nl.md"]
        }

    def test_a_file_in_a_walked_directory_needs_no_line_of_its_own(self) -> None:
        """Een bewaking die de hele map doorloopt, kiest een nieuw bestand daar al."""
        recorded = runner.Recorded()
        recorded.add("tests/test_timeless.py", "tests/", required=True)
        recorded.add("tests/test_timeless.py", "tests/test_new.py", required=False)
        recorded.add("tests/test_timeless.py", "docs/install/nl.md", required=True)
        recorded.collapse()
        assert recorded.inputs["tests/test_timeless.py"] == {"tests/", "docs/install/nl.md"}
        assert recorded.required["tests/test_timeless.py"] == {"tests/", "docs/install/nl.md"}

    def test_a_python_file_opened_as_text_is_no_demand(self, tmp_path: Path) -> None:
        """`linecache` opent een `.py` alleen voor de eerste die erom vraagt."""
        reads = tmp_path / "reads.json"
        reads.write_text(json.dumps({"tests/test_x.py": ["tests/test_y.py", "README.md"]}))
        recorded = runner.recorded_inputs(None, reads)
        assert recorded.inputs["tests/test_x.py"] == {"tests/test_y.py", "README.md"}
        assert recorded.required["tests/test_x.py"] == {"README.md"}

    @staticmethod
    def _judge(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, recorded, full: bool) -> int:
        monkeypatch.setenv("CI", "true")
        target = tmp_path / "impact_map.json"
        target.write_text(
            json.dumps(
                {key: value for key, value in IMPACT.items() if key == "tests/test_guide.py"}
            )
            if not full
            else json.dumps(IMPACT)
        )
        monkeypatch.setattr(runner.sel, "MAP", target)
        monkeypatch.setenv("CD_IMPACT_ARTIFACT", str(tmp_path / "artifact.json"))
        return runner.compare_and_keep(recorded, full=full)


class TestTheRecorder:
    """Alleen wat binnen de repo ligt telt. / Only what lies inside the repository counts."""

    @pytest.mark.parametrize(
        ("target", "expected"),
        [
            (ROOT / "docs" / "install" / "nl.md", "docs/install/nl.md"),
            (ROOT / "ARCHITECTURE.md", "ARCHITECTURE.md"),
            (ROOT / ".venv" / "Lib" / "x.py", None),
            (ROOT / ".git" / "HEAD", None),
            (ROOT / "tests" / "__pycache__" / "x.pyc", None),
            (ROOT.parent / "elsewhere.txt", None),
            (3, None),
        ],
    )
    def test_a_path_is_kept_only_inside_the_repository(self, target, expected) -> None:
        assert impact_recorder._relative(target) == expected

    @pytest.mark.parametrize(
        ("mode", "noted"),
        [("r", True), ("rb", True), ("w", False), ("a", False), ("x", False), ("r+", False)],
    )
    def test_only_reading_is_an_input(
        self, monkeypatch: pytest.MonkeyPatch, mode: str, noted: bool
    ) -> None:
        """Schrijven (de eigen cache van pytest bijvoorbeeld) is geen invoer."""
        monkeypatch.setattr(impact_recorder, "_current", "tests/test_x.py")
        monkeypatch.setattr(impact_recorder, "_reads", {})
        opened = impact_recorder._wrap_open(lambda _file, _mode: None)
        opened(ROOT / "README.md", mode)
        assert bool(impact_recorder._reads) is noted


def _recorded(inputs: dict[str, set[str]]):
    found = runner.Recorded()
    for test_file, paths in inputs.items():
        for path in paths:
            found.add(test_file, path, required=True)
    return found


def _fake_root(root: Path, impact: dict[str, list[str]]) -> Path:
    (root / "tests").mkdir(parents=True, exist_ok=True)
    for test_file in impact:
        (root / test_file).write_text("", encoding="utf-8")
    return root
