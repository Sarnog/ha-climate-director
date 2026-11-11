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

Dekking: deze toetsen lezen geen gids; de paden onder `docs/install/` en
`translations/` zijn namen op een verzonnen kaart. Alleen de mutatielijst leest de
echte bronbestanden die ze noemt, waaronder een vertaling. Wel gedekt: de regels van de
selectie, het ontleden van `git diff --name-status`, de eis aan de kaart in de CI
en het bijwerken ervan lokaal, en welke paden de recorder bewaart. Niet gedekt: de
echte kaart zelf, behalve dat hij alleen bestaande toetsbestanden noemt - die
vergelijkt elke run met wat hij meet.

Coverage: these tests read no guide; the paths under `docs/install/` and
`translations/` are names on a made-up map. Only the mutation list reads the real
source files it names, a translation among them. Covered: the rules
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
probe = _load("mutation_probe")
review = _load("mutation_review")

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

    def test_a_new_test_runs_everything(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(sel, "ROOT", _fake_root(tmp_path, {"tests/test_new.py": []}))
        assert sel.select({"tests/test_new.py": "A"}, {}) == sel.ALL

    def test_a_new_package_file_runs_everything(self) -> None:
        changed = {"custom_components/climate_director/engine/new.py": "A"}
        assert sel.select(changed, IMPACT) == sel.ALL

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

    def test_the_oldest_home_assistant_follows_the_package_only(self) -> None:
        """Een tekst of een toets die een tekst leest, raakt de oudste versie niet."""
        assert sel.needs_oldest(["custom_components/climate_director/translations/de.json"])
        assert sel.needs_oldest(["requirements_test.txt"])
        assert not sel.needs_oldest(["ROADMAP.md", "docs/install/nl.md", "tests/test_x.py"])

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

    def test_a_new_test_enters_the_map_without_a_missing_input(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("CI", "true")
        target = tmp_path / "impact_map.json"
        target.write_text(json.dumps(IMPACT))
        monkeypatch.setattr(runner.sel, "MAP", target)
        artifact = tmp_path / "artifact.json"
        monkeypatch.setenv("CD_IMPACT_ARTIFACT", str(artifact))
        recorded = _recorded({"tests/test_new.py": {"README.md"}})
        assert (
            runner.compare_and_keep(
                recorded, full=False, new_tests=frozenset({"tests/test_new.py"})
            )
            == 0
        )
        assert json.loads(artifact.read_text())["tests/test_new.py"] == ["README.md"]

    def test_locally_the_map_is_brought_up_to_date(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("CI", raising=False)
        root = _fake_root(tmp_path / "repo", {"tests/test_guide.py": []})
        (root / "docs" / "install").mkdir(parents=True)
        for name in ("nl", "de"):
            (root / "docs" / "install" / f"{name}.md").write_text("", encoding="utf-8")
        target = tmp_path / "impact_map.json"
        target.write_text(json.dumps({"tests/test_guide.py": ["docs/install/nl.md"]}))
        monkeypatch.setattr(runner, "ROOT", root)
        monkeypatch.setattr(runner.sel, "MAP", target)
        recorded = _recorded({"tests/test_guide.py": {"docs/install/de.md"}})
        assert runner.compare_and_keep(recorded, full=False) == 0
        assert json.loads(target.read_text()) == {
            "tests/test_guide.py": ["docs/install/de.md", "docs/install/nl.md"]
        }

    def test_a_full_run_keeps_a_line_it_did_not_see(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Een lokale run ziet `script/` niet en laat de regel toch staan.

        A local run does not see `script/` and still leaves the line standing.
        """
        monkeypatch.delenv("CI", raising=False)
        root = _fake_root(tmp_path / "repo", {"tests/test_controls.py": []})
        (root / "script").mkdir()
        (root / "README.md").write_text("", encoding="utf-8")
        target = tmp_path / "impact_map.json"
        target.write_text(json.dumps({"tests/test_controls.py": ["script/", "README.md"]}))
        monkeypatch.setattr(runner, "ROOT", root)
        monkeypatch.setattr(runner.sel, "MAP", target)
        recorded = _recorded({"tests/test_controls.py": {"README.md"}})
        assert runner.compare_and_keep(recorded, full=True) == 0
        assert json.loads(target.read_text()) == {
            "tests/test_controls.py": ["README.md", "script/"]
        }

    def test_a_full_run_drops_only_what_no_longer_exists(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Een bestand, een map en een toetsbestand die weg zijn, vallen van de kaart.

        A file, a directory and a test file that are gone drop off the map.
        """
        monkeypatch.delenv("CI", raising=False)
        root = _fake_root(tmp_path / "repo", {"tests/test_kept.py": []})
        (root / "README.md").write_text("", encoding="utf-8")
        (root / "docs").mkdir()
        (root / "docs" / "kept.md").write_text("", encoding="utf-8")
        (root / "docs" / "notdir").write_text("", encoding="utf-8")
        target = tmp_path / "impact_map.json"
        target.write_text(
            json.dumps(
                {
                    "tests/test_kept.py": [
                        "README.md",
                        "tox.ini",
                        "docs/kept.md",
                        "docs/gone.md",
                        "docs/gone/",
                        "docs/notdir/",
                    ],
                    "tests/test_gone.py": ["README.md"],
                }
            )
        )
        monkeypatch.setattr(runner, "ROOT", root)
        monkeypatch.setattr(runner.sel, "MAP", target)
        recorded = _recorded({"tests/test_kept.py": {"README.md"}})
        assert runner.compare_and_keep(recorded, full=True) == 0
        assert json.loads(target.read_text()) == {
            "tests/test_kept.py": ["README.md", "docs/kept.md", "tox.ini"]
        }

    def test_ci_accepts_a_map_with_an_extra_line_and_rejects_a_missing_one(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """De CI keurt een kaart met een ontbrekende regel af, niet een met een extra regel.

        CI rejects a map with a missing line, not one with an extra line.
        """
        monkeypatch.setenv("CI", "true")
        root = _fake_root(tmp_path / "repo", {"tests/test_one.py": []})
        for name in ("a.md", "b.md", "extra.md"):
            (root / name).write_text("", encoding="utf-8")
        target = tmp_path / "impact_map.json"
        monkeypatch.setattr(runner, "ROOT", root)
        monkeypatch.setattr(runner.sel, "MAP", target)
        monkeypatch.setenv("CD_IMPACT_ARTIFACT", str(tmp_path / "artifact.json"))
        recorded = _recorded({"tests/test_one.py": {"a.md", "b.md"}})
        target.write_text(json.dumps({"tests/test_one.py": ["a.md", "b.md", "extra.md"]}))
        assert runner.compare_and_keep(recorded, full=True) == 0
        target.write_text(json.dumps({"tests/test_one.py": ["a.md", "extra.md"]}))
        assert runner.compare_and_keep(recorded, full=True) == 1

    def test_a_changed_recording_reports_instead_of_failing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Verandert de opname zelf, dan is een verschil een nieuwe kaart, geen fout."""
        monkeypatch.setenv("CI", "true")
        target = tmp_path / "impact_map.json"
        target.write_text(json.dumps({"tests/test_guide.py": ["docs/install/nl.md"]}))
        monkeypatch.setattr(runner.sel, "MAP", target)
        monkeypatch.setenv("CD_IMPACT_ARTIFACT", str(tmp_path / "artifact.json"))
        recorded = _recorded({"tests/test_guide.py": {"docs/install/", "docs/install/nl.md"}})
        assert runner.compare_and_keep(recorded, full=True, machinery=True) == 0
        assert runner.compare_and_keep(recorded, full=True, machinery=False) == 1
        assert json.loads((tmp_path / "artifact.json").read_text()) == {
            "tests/test_guide.py": ["docs/install/"]
        }
        assert "tests/impact_recorder.py" in sel.RECORDING

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
            (ROOT / ".venv", None),
            (ROOT / ".git" / "HEAD", None),
            (ROOT / "tests" / "__pycache__" / "x.pyc", None),
            (ROOT.parent / "elsewhere.txt", None),
            (3, None),
        ],
    )
    def test_a_path_is_kept_only_inside_the_repository(self, target, expected) -> None:
        assert impact_recorder._relative(target) == expected

    def test_a_directory_walked_by_rglob_is_noted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`Path.rglob` loopt via een eigen `scandir`; ook die map telt."""
        monkeypatch.setattr(impact_recorder, "_current", "tests/test_x.py")
        monkeypatch.setattr(impact_recorder, "_reads", {})
        monkeypatch.setattr(impact_recorder, "_originals", {})
        # Binnen een opnamerun mag deze toets de coverage-context niet verzetten.
        # Inside a recording run this test must not move the coverage context.
        monkeypatch.setattr(impact_recorder, "switch", lambda _test_file: None)
        impact_recorder.start()
        try:
            list((ROOT / "brand").rglob("*.png"))
        finally:
            impact_recorder.stop()
        assert "brand/" in impact_recorder._reads["tests/test_x.py"]

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


class TestTheMutationProbe:
    """Een mutatie draait alleen haar eigen toetsen, en alleen als haar deel veranderde.

    A mutation runs only its own tests, and only when its part changed.
    """

    MUTATION = {"name": "m", "file": "custom_components/climate_director/engine/gates.py"}

    def test_a_mutation_runs_only_the_tests_that_touch_its_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(sel, "ROOT", _fake_root(tmp_path, IMPACT))
        assert probe.tests_for(self.MUTATION, IMPACT) == ["tests/test_engine.py"]

    def test_without_a_map_a_mutation_runs_the_full_suite(self) -> None:
        assert probe.tests_for(self.MUTATION, None) == []

    @pytest.mark.parametrize(
        ("changed", "runs"),
        [
            (None, True),
            ({"custom_components/climate_director/engine/gates.py": "M"}, True),
            ({"tests/test_engine.py": "M"}, True),
            ({"script/mutation_probe.py": "M"}, True),
            ({"tests/conftest.py": "M"}, True),
            ({"ROADMAP.md": "M", "tests/test_guide.py": "M"}, False),
        ],
    )
    def test_a_mutation_runs_only_when_its_part_changed(self, changed, runs: bool) -> None:
        assert probe.relevant(self.MUTATION, ["tests/test_engine.py"], changed) is runs

    def test_a_mutation_on_the_full_suite_always_runs(self) -> None:
        assert probe.relevant(self.MUTATION, [], {"ROADMAP.md": "M"}) is True


class TestTheMutationsStillApply:
    """Elke mutatie van de probe vindt haar patroon nog in de broncode.

    Every mutation of the probe still finds its pattern in the source.

    Een hernoemde functie of verplaatste regel laat een patroon verdwijnen, en de
    probe stopt dan bij die mutatie: alle mutaties erna draaien niet meer, terwijl
    de baan als geslaagd telt. Deze toets laat de CI vallen voordat dat gebeurt.

    A renamed function or a moved line makes a pattern vanish, and the probe then
    stops at that mutation: every mutation after it no longer runs, while the job
    counts as passed. This test drops the CI before that happens.
    """

    @pytest.mark.parametrize("mutation", probe.MUTATIONS, ids=lambda item: item["name"])
    def test_the_pattern_stands_in_its_file(self, mutation: dict) -> None:
        text = (ROOT / mutation["file"]).read_text(encoding="utf-8")
        assert mutation["old"] in text, f"{mutation['name']}: patroon niet gevonden"


class TestTheReviewListStillApplies:
    """De mutatielijst van de controle veroudert niet stilletjes.

    The review's mutation list does not go stale silently.

    Elk patroon staat nog precies één keer in zijn bestand en elke toets die een
    mutatie noemt bestaat. Een verhuizing laat anders een mutatie "geen patroon
    gevonden" melden in plaats van een eigenschap te meten, en een gat blijft dan
    onzichtbaar. De zes mutaties op `area_clash` die de CI-baan draait staan ook in
    deze lijst, zodat de twee niet uit elkaar lopen.

    Every pattern still stands exactly once in its file and every test a mutation names
    exists. Otherwise a move makes a mutation report "no pattern found" instead of
    measuring a property, and a hole stays invisible. The six mutations on `area_clash`
    that the CI lane runs also stand in this list, so the two cannot drift apart.
    """

    @pytest.mark.parametrize("mutation", review.REVIEW_MUTATIONS, ids=lambda item: item["name"])
    def test_the_pattern_stands_exactly_once(self, mutation: dict) -> None:
        text = (ROOT / mutation["file"]).read_text(encoding="utf-8")
        assert text.count(mutation["old"]) == 1, f"{mutation['name']}: patroon niet precies 1x"

    @pytest.mark.parametrize("mutation", review.REVIEW_MUTATIONS, ids=lambda item: item["name"])
    def test_every_test_it_names_exists(self, mutation: dict) -> None:
        missing = [name for name in mutation["tests"] if not (ROOT / name).is_file()]
        assert not missing, f"{mutation['name']}: toetsbestand ontbreekt: {missing}"

    def test_the_area_mutations_of_the_lane_stand_in_the_list(self) -> None:
        listed = {(m["file"], m["old"], m["new"]) for m in review.REVIEW_MUTATIONS}
        in_the_lane = [m for m in probe.MUTATIONS if m["name"].startswith("gebiedsconflict-")]
        assert len(in_the_lane) >= 6
        for mutation in in_the_lane:
            key = (mutation["file"], mutation["old"], mutation["new"])
            assert key in listed, f"{mutation['name']} staat niet in de controlelijst"

    def test_the_names_are_unique(self) -> None:
        names = [m["name"] for m in review.REVIEW_MUTATIONS]
        assert len(names) == len(set(names))


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
