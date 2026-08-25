"""De blueprints in de repo, gecontroleerd zoals Home Assistant ze inleest.

The blueprints in the repo, checked the way Home Assistant reads them.

Een blueprint is het enige stuk van dit project dat niemand kan draaien zonder
hem eerst te importeren. Een typefout merkt de gebruiker dus, en niet wij - en
dat is precies de verkeerde volgorde. Daarom worden ze hier ingelezen met de
loader van Home Assistant zelf, langs het echte schema gehaald, en nagelopen op
de dingen die een schema niet ziet: een `!input` die nergens gedefinieerd is,
een invoerveld dat nergens gebruikt wordt, en een `source_url` die niet naar het
bestand zelf wijst - want dan werkt bijwerken niet.

A blueprint is the one part of this project nobody can run without importing it
first. So a typo is found by the user rather than by us - exactly the wrong
order. Hence they are read here with Home Assistant's own loader, put through
the real schema, and checked for what a schema does not see: an `!input` that is
defined nowhere, an input nobody uses, and a `source_url` not pointing at the
file itself - since then updating does not work.
"""

from __future__ import annotations

import pathlib
import re

import pytest
from homeassistant.components.blueprint.models import Blueprint
from homeassistant.components.blueprint.schemas import BLUEPRINT_SCHEMA
from homeassistant.util import yaml as yaml_util

ROOT = pathlib.Path(__file__).resolve().parents[1]
FOLDER = ROOT / "blueprints" / "automation" / "climate_director"

REPOSITORY = "https://github.com/Sarnog/ha-climate-director/blob/main"


def blueprint_files() -> list[pathlib.Path]:
    return sorted(FOLDER.glob("*.yaml"))


FILES = blueprint_files()
IDS = [path.name for path in FILES]


def load(path: pathlib.Path) -> dict:
    """Return one blueprint as Home Assistant loads it, `!input` and all."""
    return yaml_util.load_yaml(str(path))


def test_the_blueprints_are_there() -> None:
    """Guards the sweep itself: an empty folder would pass everything below."""
    assert len(FILES) == 3


@pytest.mark.parametrize("path", FILES, ids=IDS)
class TestEveryBlueprint:
    def test_it_is_valid_yaml(self, path: pathlib.Path) -> None:
        assert isinstance(load(path), dict)

    def test_home_assistant_accepts_it(self, path: pathlib.Path) -> None:
        """The real schema, and the real check on undefined inputs."""
        blueprint = Blueprint(
            load(path), path=str(path), expected_domain="automation", schema=BLUEPRINT_SCHEMA
        )
        assert blueprint.name

    def test_every_input_is_used(self, path: pathlib.Path) -> None:
        """An input nobody reads is a question you ask for nothing."""
        blueprint = Blueprint(
            load(path), path=str(path), expected_domain="automation", schema=BLUEPRINT_SCHEMA
        )
        used = yaml_util.extract_inputs(blueprint.data)
        assert not set(blueprint.inputs) - used

    def test_it_points_back_at_itself(self, path: pathlib.Path) -> None:
        """Without a matching `source_url` an imported blueprint cannot be updated."""
        metadata = load(path)["blueprint"]
        expected = f"{REPOSITORY}/blueprints/automation/climate_director/{path.name}"
        assert metadata["source_url"] == expected

    def test_it_says_who_wrote_it_and_what_it_needs(self, path: pathlib.Path) -> None:
        metadata = load(path)["blueprint"]
        assert metadata["author"] == "Sarnog"
        assert metadata["homeassistant"]["min_version"]

    def test_it_asks_the_same_version_as_the_integration(self, path: pathlib.Path) -> None:
        """Deze blueprints horen bij deze integratie, dus bij dezelfde ondergrens.

        These blueprints belong to this integration, so to the same lower bound.

        Ze stonden lager dan de integratie zelf. Wie ze importeerde op een
        Home Assistant die de integratie niet kan draaien, kreeg een blueprint
        die netjes laadde en daarna nergens naar kon luisteren.

        They stood lower than the integration itself. Importing them on a Home
        Assistant that cannot run the integration got you a blueprint that
        loaded neatly and then had nothing to listen to.
        """
        import json

        wanted = json.loads((ROOT / "hacs.json").read_text(encoding="utf-8"))["homeassistant"]
        assert load(path)["blueprint"]["homeassistant"]["min_version"] == wanted

    def test_it_explains_itself_in_both_languages(self, path: pathlib.Path) -> None:
        """A blueprint cannot be translated, so both languages stand in the text."""
        description = load(path)["blueprint"]["description"]
        assert "NL - " in description
        assert "EN - " in description

    def test_every_input_carries_both_languages(self, path: pathlib.Path) -> None:
        blueprint = Blueprint(
            load(path), path=str(path), expected_domain="automation", schema=BLUEPRINT_SCHEMA
        )
        for key, field in blueprint.inputs.items():
            assert field and field.get("name"), key
            description = (field or {}).get("description")
            if description is None:
                continue
            assert "NL - " in description and "EN - " in description, key

    def test_it_uses_the_modern_syntax(self, path: pathlib.Path) -> None:
        """`triggers`/`actions` rather than the pre-2024.10 singular keys."""
        data = load(path)
        assert "triggers" in data
        assert "actions" in data
        assert "trigger" not in data
        assert "action" not in data


class TestTheyMatchTheIntegration:
    """Een blueprint die een veld noemt dat de integratie niet stuurt, meldt niets.

    A blueprint naming a field the integration does not send reports nothing.
    """

    COMPONENT = ROOT / "custom_components" / "climate_director"

    def _text(self, name: str) -> str:
        return (FOLDER / name).read_text(encoding="utf-8")

    def _refusal_keys(self) -> set[str]:
        source = (self.COMPONENT / "coordinator.py").read_text(encoding="utf-8")
        block = source[source.index("def _refusal_data") : source.index("def _friendly")]
        return set(re.findall(r'^\s{12}"(\w+)":', block, re.MULTILINE))

    def test_the_refusal_blueprint_reads_only_fields_that_exist(self) -> None:
        text = self._text("precondition_refused.yaml")
        used = set(re.findall(r"trigger\.event\.data\.(\w+)", text))
        assert used
        assert used <= self._refusal_keys(), sorted(used - self._refusal_keys())

    def test_the_decision_blueprint_reads_only_fields_that_exist(self) -> None:
        source = (self.COMPONENT / "coordinator.py").read_text(encoding="utf-8")
        block = source[source.index("def _event_data") :]
        known = set(re.findall(r'^\s{8}"(\w+)":', block, re.MULTILINE))
        used = set(re.findall(r"trigger\.event\.data\.(\w+)", self._text("decisions.yaml")))
        assert used
        assert used <= known, sorted(used - known)

    def test_the_reasons_it_lists_all_exist(self) -> None:
        """A list of reasons that has drifted sends people filtering on nothing."""
        from custom_components.climate_director.engine import Reason

        listed = set(re.findall(r"`(\w+)`", self._text("decisions.yaml")))
        reasons = {item.value for item in Reason}
        named = listed & reasons
        assert len(named) == len(reasons), sorted(reasons - named)

    def test_the_refusal_blueprint_leaves_the_duration_to_the_installation(self) -> None:
        """The notification names the configured maximum, so the request must use it."""
        text = self._text("precondition_refused.yaml")
        assert "ignore_openings: true" in text
        assert "minutes:" not in text.split("actions:")[-1]

    def test_the_monitoring_trigger_sees_problems_present_right_after_a_restart(self) -> None:
        """`unknown -> on` is de vorm van een probleem dat er na een herstart al is.

        `unknown -> on` is the shape of a problem already present after a restart.
        """
        data = load(FOLDER / "monitoring.yaml")
        problem = next(trigger for trigger in data["triggers"] if trigger.get("id") == "problem")
        assert problem["to"] == "on"
        starts = problem["from"] if isinstance(problem["from"], list) else [problem["from"]]
        assert {"off", "unknown", "unavailable"} <= set(starts)

    def test_the_recovery_trigger_keeps_requiring_a_reported_problem(self) -> None:
        """Herstel meldt alleen wat eerst als probleem gemeld is; anders knippert het
        bij elke start.

        Recovery reports only what was reported as a problem first; otherwise it
        blinks on every start-up.
        """
        data = load(FOLDER / "monitoring.yaml")
        recovered = next(
            trigger for trigger in data["triggers"] if trigger.get("id") == "recovered"
        )
        assert recovered["from"] == "on"
        assert recovered["to"] == "off"
