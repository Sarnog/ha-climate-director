"""De melding dat er niemand naar een geweigerd vooruit-verzoek luistert.

The notice that nobody is listening for a refused pre-conditioning request.

Een verzoek dat strandt op een openstaand raam meldt zichzelf op de bus en
verder nergens. Luistert daar niemand naar, dan is dat van buiten niet te
onderscheiden van een knop die niets doet - en dan is de knop stuk, ook al
werkt hij precies zoals bedoeld. Daarom staat de melding er meteen, en niet pas
nadat er een verzoek geweigerd is: een halve functie is geen functie.

A request stranding on an open window reports itself on the bus and nowhere
else. If nobody listens, that is indistinguishable from a button that does
nothing - and then the button is broken, however exactly it works as intended.
Hence the notice stands from the start rather than only after a request has been
refused: half a feature is no feature.
"""

from __future__ import annotations

import ast
import json
import pathlib
import re

import pytest
from conftest import fix_flow_steps, fixable_issue_keys

from custom_components.climate_director import problems
from custom_components.climate_director.const import (
    CONF_MANUAL_SOURCES_SEEN,
    DOMAIN,
    EVENT_PRECONDITION_REFUSED,
)
from custom_components.climate_director.engine import (
    DirectorConfig,
    ModeSettings,
    Source,
    Zone,
    manual_only_problems,
)
from custom_components.climate_director.repairs import ManualSourcesFlow

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "climate_director"


class Registry:
    """Stand-in for the issue registry, remembering what it was told."""

    class IssueSeverity:
        WARNING = "warning"

    def __init__(self) -> None:
        self.created: list[tuple[str, dict]] = []
        self.deleted: list[str] = []

    def async_create_issue(self, hass, domain, issue_id, **kwargs):
        self.created.append((issue_id, kwargs))

    def async_delete_issue(self, hass, domain, issue_id):
        self.deleted.append(issue_id)


def hass_with(listeners: int):
    class Bus:
        def async_listeners(self):
            return {EVENT_PRECONDITION_REFUSED: listeners} if listeners else {"other_event": 3}

    class Hass:
        bus = Bus()

    return Hass()


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> Registry:
    fake = Registry()
    monkeypatch.setattr(problems, "ir", fake)
    return fake


class TestNobodyListening:
    def test_it_raises_the_notice(self, registry: Registry) -> None:
        assert problems.async_check_watchers(hass_with(0)) is False
        assert [issue for issue, _ in registry.created] == [problems.UNWATCHED_ISSUE]

    def test_it_is_a_warning_that_cannot_be_clicked_away(self, registry: Registry) -> None:
        """Nothing to fix from a dialog: the user has to build the automation."""
        problems.async_check_watchers(hass_with(0))
        _, kwargs = registry.created[0]
        assert kwargs["severity"] is Registry.IssueSeverity.WARNING
        assert kwargs["is_fixable"] is False

    def test_it_points_at_the_chapter_that_explains_it(self, registry: Registry) -> None:
        problems.async_check_watchers(hass_with(0))
        _, kwargs = registry.created[0]
        assert kwargs["learn_more_url"] == problems.BLUEPRINTS_URL

    def test_it_carries_its_own_translation(self, registry: Registry) -> None:
        problems.async_check_watchers(hass_with(0))
        _, kwargs = registry.created[0]
        assert kwargs["translation_key"] == problems.UNWATCHED_ISSUE


class TestSomebodyListening:
    def test_the_notice_goes_away(self, registry: Registry) -> None:
        assert problems.async_check_watchers(hass_with(1)) is True
        assert registry.deleted == [problems.UNWATCHED_ISSUE]
        assert not registry.created

    def test_several_listeners_are_just_as_good(self, registry: Registry) -> None:
        assert problems.async_check_watchers(hass_with(4)) is True

    def test_the_last_installation_leaving_clears_it(self, registry: Registry) -> None:
        problems.async_clear_watchers(hass_with(0))
        assert registry.deleted == [problems.UNWATCHED_ISSUE]


def manual_house(*, autostart: bool = False) -> DirectorConfig:
    """Return a house whose only bedroom source is hand-operated."""
    return DirectorConfig(
        zones=(
            Zone(
                "woonkamer",
                "Woonkamer",
                "sensor.woonkamer",
                sources=(Source("w", "climate.huiskamer"),),
                heat=ModeSettings(21.0, 20.0),
            ),
            Zone(
                "slaapkamer",
                "Slaapkamer",
                "sensor.slaapkamer",
                sources=(Source("s", "climate.master_bedroom", autostart=autostart),),
                heat=ModeSettings(21.0, 20.0),
                cool=ModeSettings(23.0, 24.0),
            ),
        ),
    )


class TestTheHandOperatedNotice:
    """De eenmalige melding voor taken die alleen handbediend kunnen.

    Deze stand-in-tests bewaken de **logica** van de melding; de **keten** — de
    échte `issue_registry`, het formulier, de bevestiging en de herstart — wordt
    bewaakt door `tests/test_manual_sources_live.py`.

    The one-time notice for duties that can only be delivered by hand.

    These stand-in tests guard the **logic** of the notice; the **chain** — the
    real `issue_registry`, the form, the confirmation and the restart — is
    guarded by `tests/test_manual_sources_live.py`.
    """

    @pytest.fixture(autouse=True)
    def _no_translations(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Fall back to the English problem text; the notice text is not tested here."""
        monkeypatch.setattr(problems.texts, "lookup", lambda hass, code: None)

    def test_it_raises_the_notice(self, registry: Registry) -> None:
        config = manual_house()
        problems.async_report_manual_sources(None, "entry", "Climate Director", {}, config)
        issue_id, kwargs = registry.created[0]
        assert issue_id == "manual_sources_entry"
        assert kwargs["is_fixable"] is True
        assert kwargs["translation_key"] == "manual_sources"
        assert kwargs["data"]["entry_id"] == "entry"
        assert kwargs["data"]["signature"] == problems._manual_signature(
            manual_only_problems(config)
        )

    def test_a_matching_acknowledgement_stays_quiet(self, registry: Registry) -> None:
        config = manual_house()
        signature = problems._manual_signature(manual_only_problems(config))
        problems.async_report_manual_sources(
            None, "entry", "Climate Director", {CONF_MANUAL_SOURCES_SEEN: signature}, config
        )
        assert not registry.created
        assert registry.deleted == ["manual_sources_entry"]

    def test_a_changed_situation_is_a_new_notice(self, registry: Registry) -> None:
        config = manual_house()
        problems.async_report_manual_sources(
            None, "entry", "Climate Director", {CONF_MANUAL_SOURCES_SEEN: "slaapkamer:heat"}, config
        )
        assert registry.created

    def test_no_hand_operated_duties_clears_the_notice(self, registry: Registry) -> None:
        config = manual_house(autostart=True)
        problems.async_report_manual_sources(None, "entry", "Climate Director", {}, config)
        assert not registry.created
        assert registry.deleted == ["manual_sources_entry"]


class TestTheHandOperatedFixFlow:
    """De bevestiging die de melding voorgoed oplost.

    The confirmation that resolves the notice for good.
    """

    def _hass(self):
        class Entries:
            def __init__(self) -> None:
                self.entry = None
                self.updated = None

            def async_get_entry(self, entry_id: str):
                return self.entry

            def async_update_entry(self, entry, options=None):
                entry.options = dict(options)
                self.updated = dict(entry.options)

        entries = Entries()
        entries.entry = type("Entry", (), {"options": {"existing": True}})()

        class Hass:
            config_entries = entries

        return entries, Hass()

    def _fake_issue_registry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Let the form branch run without a real issue registry."""
        import custom_components.climate_director.repairs as repairs_module

        class FakeIssueRegistry:
            def async_get_issue(self, handler: str, issue_id: str) -> None:
                return None

        monkeypatch.setattr(repairs_module.ir, "async_get", lambda hass: FakeIssueRegistry())

    async def test_confirming_stores_the_fingerprint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._fake_issue_registry(monkeypatch)
        entries, hass = self._hass()
        flow = ManualSourcesFlow()
        flow.hass = hass
        flow.handler = DOMAIN
        flow.issue_id = "manual_sources_abc"
        flow.data = {"entry_id": "abc", "signature": "slaapkamer:cool,slaapkamer:heat"}
        assert (await flow.async_step_init(user_input=None))["type"] == "form"
        result = await flow.async_step_init(user_input={})
        assert result["type"] == "create_entry"
        assert entries.updated == {
            "existing": True,
            CONF_MANUAL_SOURCES_SEEN: "slaapkamer:cool,slaapkamer:heat",
        }

    async def test_an_unknown_entry_still_finishes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._fake_issue_registry(monkeypatch)
        entries, hass = self._hass()
        entries.entry = None
        flow = ManualSourcesFlow()
        flow.hass = hass
        flow.handler = DOMAIN
        flow.issue_id = "manual_sources_missing"
        flow.data = {"entry_id": "missing", "signature": "x"}
        assert (await flow.async_step_init(user_input=None))["type"] == "form"
        result = await flow.async_step_init(user_input={})
        assert result["type"] == "create_entry"
        assert entries.updated is None


class TestTheManualSignatureIsAStorageFormat:
    """De handtekening is een opslagformaat, geen toevallige string.

    Hij belandt in `entry.options[manual_sources_seen]` en overleeft herstarts;
    een reformat van `_manual_signature` maakt elke opgeslagen bevestiging
    ongeldig en geeft iedereen die de melding ooit heeft weggeklikt hem opnieuw.
    Daarom wordt het formaat hier letterlijk vastgepind — niet met de functie
    zelf, want dan vergelijkt de test de functie met zichzelf.

    The signature is a storage format, not an incidental string.

    It lands in `entry.options[manual_sources_seen]` and survives restarts; a
    reformat of `_manual_signature` invalidates every stored confirmation and
    gives everyone who ever dismissed the notice a new one. Hence the format is
    pinned literally here — not against the function itself, since then the
    test compares the function with itself.
    """

    def test_a_known_installation_has_the_literal_signature(self) -> None:
        config = manual_house()
        assert problems._manual_signature(manual_only_problems(config)) == (
            "slaapkamer:cool,slaapkamer:heat"
        )


class TestTheNoticeIsUsable:
    """Een melding die niet zegt wat je moet doen is een melding die blijft staan.

    A notice that does not say what to do is a notice that stays.
    """

    def _issue(self, language: str) -> dict:
        path = (
            COMPONENT / "strings.json"
            if language == "en"
            else COMPONENT / "translations" / f"{language}.json"
        )
        return json.loads(path.read_text(encoding="utf-8"))["issues"]["precondition_unwatched"]

    @pytest.mark.parametrize("language", ["en", "nl", "de", "fr", "es", "ar"])
    def test_every_language_has_a_title_and_a_way_out(self, language: str) -> None:
        issue = self._issue(language)
        assert issue["title"].strip()
        assert EVENT_PRECONDITION_REFUSED in issue["description"]

    @pytest.mark.parametrize("language", ["en", "nl"])
    def test_it_says_the_blueprint_must_also_be_set_up(self, language: str) -> None:
        """Importing alone listens to nothing, and that is the trap to name."""
        description = self._issue(language)["description"]
        wording = "set it up" if language == "en" else "stel"
        assert wording in description

    def test_the_link_lands_on_a_heading_that_exists(self) -> None:
        """A learn-more link into thin air is worse than no link."""
        anchor = problems.BLUEPRINTS_URL.split("#", 1)[1]
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        headings = re.findall(r"^#{2,4} (.+)$", readme, re.M)
        slugs = {
            re.sub(r"[^a-z0-9 -]", "", heading.lower()).replace(" ", "-") for heading in headings
        }
        assert anchor in slugs


class TestTheFixFlowHasTextInEveryLanguage:
    """L1: het reparatiedialoog van de handbediend-melding heeft in elke taal tekst.

    De bewaking pint de eigenschap vast, niet een naam: hij leest met een AST
    uit `problems.py` welke meldingen `is_fixable=True` zijn, uit de héle
    integratieboom welke stappen de fix-flows kennen (gefilterd op klassen die
    van `RepairsFlow` erven, niet op een bestandsnaam), en eist dan dat elke
    combinatie in alle zeven bestanden een `fix_flow.step.<step>`-blok heeft met
    een niet-lege titel én beschrijving. De placeholders in die beschrijving
    moeten een deelverzameling zijn van wat de code werkelijk meegeeft, zodat
    een `{typefout}` niet stil doorglipt. En een `is_fixable=True` met een
    niet-letterlijke `translation_key` is een duidelijke fout, geen melding die
    stilletjes uit de inventarisatie valt.

    L1: the hand-operated notice's repair dialog has text in every language.

    The guard pins the property, not a name: it reads with an AST from
    `problems.py` which notices are `is_fixable=True`, from the whole
    integration tree which steps the fix flows know (filtered on classes
    inheriting `RepairsFlow`, not on a filename), and then requires every
    combination to have a `fix_flow.step.<step>` block with a non-empty title
    and description in all seven files. The placeholders in that description
    must be a subset of what the code really passes, so a `{typo}` does not
    slip through silently. And an `is_fixable=True` with a non-literal
    `translation_key` is a clear error, not a notice that silently drops out of
    the inventory.
    """

    def _translation_files(self) -> list[pathlib.Path]:
        return [COMPONENT / "strings.json", *sorted((COMPONENT / "translations").glob("*.json"))]

    def _fixable_keys(self) -> set[str]:
        """Return every `translation_key` whose `async_create_issue` is fixable."""
        return fixable_issue_keys()

    def _fix_flow_steps(self) -> set[str]:
        """Return every `step_id` a repairs fix-flow can draw, from the whole tree."""
        return fix_flow_steps()

    def _placeholders_passed(self, key: str) -> set[str]:
        """Return the placeholder names the code really passes for `key`."""
        source = (COMPONENT / "problems.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr != "async_create_issue":
                continue
            keywords = {keyword.arg: keyword.value for keyword in node.keywords}
            key_node = keywords.get("translation_key")
            if not (isinstance(key_node, ast.Constant) and key_node.value == key):
                continue
            placeholders = keywords.get("translation_placeholders")
            if not isinstance(placeholders, ast.Dict):
                continue
            return {
                item.value
                for item in placeholders.keys
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            }
        return set()

    def test_every_fixable_notice_has_a_dialog_in_every_language(self) -> None:
        fixable = self._fixable_keys()
        steps = self._fix_flow_steps()
        assert fixable == {"manual_sources"}, f"verwachte fixable meldingen: {sorted(fixable)}"
        assert steps == {"init"}, f"verwachte fix-flow-stappen: {sorted(steps)}"

        for key in fixable:
            passed = self._placeholders_passed(key)
            assert passed, f"de code geeft geen placeholders mee voor {key}"
            for path in self._translation_files():
                for step in steps:
                    block = (
                        json.loads(path.read_text(encoding="utf-8"))
                        .get("issues", {})
                        .get(key, {})
                        .get("fix_flow", {})
                        .get("step", {})
                        .get(step)
                    )
                    assert block, f"{path.name}: geen fix_flow.step.{step} voor {key}"
                    title = block.get("title", "")
                    description = block.get("description", "")
                    assert title.strip(), f"{path.name}: lege fix_flow-titel voor {key}.{step}"
                    assert description.strip(), (
                        f"{path.name}: lege fix_flow-beschrijving voor {key}.{step}"
                    )
                    used = set(re.findall(r"{(\w+)}", title)) | set(
                        re.findall(r"{(\w+)}", description)
                    )
                    assert used <= passed, (
                        f"{path.name}: {sorted(used - passed)} worden niet meegegeven "
                        f"door de code voor {key}.{step}"
                    )
