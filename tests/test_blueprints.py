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

import jinja2
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

    def test_the_default_message_is_the_readable_sentence(self) -> None:
        """De standaardmelding is het veld dat de integratie zelf opbouwt.

        Een sjabloon dat zelf velden aaneenplakt zou de vertaling omzeilen en
        weer identifiers tonen (`zone_id`, `granted`, `reason`). Wie zijn eigen
        tekst wil houdt dat veld; wie het met rust laat hoort de zin te zien die
        de integratie meelevert, in de taal van de interface.

        Een blueprint van `main` kan naast een oudere integratie draaien, en dat
        event draagt geen `message`. Dan mag er geen sjabloonfout ontstaan - dat
        is precies wat de gebruiker zag: een lege melding en een fout in de
        tracering. De standaard valt daarom terug op velden die elk event al
        draagt, en die terugval wordt hier met de echte sjabloonmachine gerenderd.

        The default message is the field the integration builds itself. A
        template stitching fields together itself would bypass the translation
        and show identifiers again (`zone_id`, `granted`, `reason`). Whoever wants
        their own text keeps that field; whoever leaves it alone should see the
        sentence the integration hands along, in the interface's language.
        A blueprint from `main` can run next to an older integration, and that
        event carries no `message`. No template error may arise then - exactly
        what the user saw: an empty notification and an error in the trace. The
        default therefore falls back to fields every event already carries, and
        that fallback is rendered here with the real template engine.
        """
        data = load(FOLDER / "decisions.yaml")
        default = data["blueprint"]["input"]["message"]["default"]
        assert "trigger.event.data.message" in default
        assert "default(" in default, default
        source = (self.COMPONENT / "coordinator.py").read_text(encoding="utf-8")
        block = source[source.index("def _event_data") :]
        known = set(re.findall(r'^\s{8}"(\w+)":', block, re.MULTILINE))
        used = set(re.findall(r"trigger\.event\.data\.(\w+)", default))
        assert used <= known, sorted(used - known)
        # HA rendert automatiseringensjablonen met een strikte undefined: een
        # ontbrekend veld wordt een fout in de tracering in plaats van een lege
        # regel. Deze test gebruikt daarom dezelfde strikte omgeving.
        #
        # HA renders automation templates with a strict undefined: a missing
        # field becomes a trace error instead of an empty line. This test
        # therefore uses the same strict environment.
        engine = jinja2.Environment(undefined=jinja2.StrictUndefined)
        ready = engine.from_string(default).render(
            trigger={
                "event": {
                    "data": {
                        "message": "kant-en-klaar",
                        "zone_name": "Woonkamer",
                        "granted": "heat",
                        "reason": "regulating",
                    }
                }
            }
        )
        older = engine.from_string(default).render(
            trigger={
                "event": {
                    "data": {
                        "zone_name": "Woonkamer",
                        "granted": "heat",
                        "reason": "regulating",
                    }
                }
            }
        )
        assert ready == "kant-en-klaar"
        assert "Woonkamer" in older and "regulating" in older, older

    def test_the_fallback_puts_no_punctuation_that_is_wrong_somewhere(self) -> None:
        """De terugval van het bericht zet geen dubbele punt.

        Deze test leest de **bron** (het blueprintbestand) en niet een
        runtimeobject, want de standaardtekst van een automatisering bestaat
        alleen als tekst in dat YAML-bestand.

        Wat hij **dekt**: een dubbele punt (`:`) waar dan ook in wat de terugval
        oplevert, met of zonder spatie erna - dus zowel `kamer: stand` als
        `kamer:stand`, en ook een dubbele punt midden in de zin. Wat hij **niet**
        dekt: andere leestekens die in één taal ongebruikelijk zijn, de
        spatieregels rond de em-dash, en een gebruiker die in zijn eigen sjabloon
        zelf een dubbele punt zet - dat is zijn eigen zin. De structurele
        afspraak erbij staat in `AGENTS.md`.

        Waarom: de Franse zinsbouw zet een **spatie vóór** de dubbele punt
        (`Woonkamer : ...`) en een blueprint kan niet vertalen. Het
        scheidingsteken dat de integratie zelf gebruikt is de em-dash met spaties
        eromheen, en dat teken is in alle zeven talen goed.

        The fallback puts no colon: French puts a space **before** the colon and
        a blueprint cannot translate. The separator the integration itself uses
        is the em dash with spaces around it, which is right in all seven
        languages.
        """
        data = load(FOLDER / "decisions.yaml")
        default = data["blueprint"]["input"]["message"]["default"]
        engine = jinja2.Environment(undefined=jinja2.StrictUndefined)
        older = engine.from_string(default).render(
            trigger={
                "event": {
                    "data": {
                        "zone_name": "Woonkamer",
                        "granted": "heat",
                        "reason": "regulating",
                    }
                }
            }
        )
        assert ":" not in older, older
        assert "Woonkamer" in older and "heat" in older and "regulating" in older, older

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

    def test_the_filter_stays_on_the_identifier(self) -> None:
        """Het filter van de blueprint blijft op `reason` staan.

        `reason` is de stabiele identifier en het contract: automatiseringen
        filteren erop en die belofte staat in de blueprint. `reason_text` is
        dezelfde reden als gewone zin - presentatie, geen contract, en hij kan per
        taal veranderen. Wie het filter op de zin zet, breekt bij de eerste
        tekstwijziging. Daarom leest deze test het conditietemplate van
        `decisions.yaml` en eist dat het `reason` noemt en `reason_text` niet, en
        rendert hij het met de echte sjabloonmachine.

        The blueprint's filter stays on `reason`. `reason` is the stable identifier
        and the contract: automations filter on it and that promise stands in the
        blueprint. `reason_text` is that same reason as an ordinary sentence -
        presentation, not a contract, and it can change per language. Whoever puts
        the filter on the sentence breaks on the first text change. This test
        therefore reads the condition template of `decisions.yaml` and requires it
        to name `reason` and not `reason_text`, and renders it with the real
        template engine.
        """
        data = load(FOLDER / "decisions.yaml")
        template = data["conditions"][0]["value_template"]
        assert "trigger.event.data.reason" in template, template
        assert "trigger.event.data.reason_text" not in template, template
        engine = jinja2.Environment(undefined=jinja2.StrictUndefined)
        condition = engine.from_string(template)

        def kept(reason: str, only: list[str]) -> bool:
            rendered = condition.render(
                trigger={"event": {"data": {"reason": reason, "zone_id": "woonkamer"}}},
                only_reasons=only,
                only_zones=[],
            )
            return "True" in rendered

        assert kept("regulating", [])
        assert kept("regulating", ["regulating"])
        assert not kept("regulating", ["satisfied"])
