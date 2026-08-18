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

import json
import pathlib
import re

import pytest

from custom_components.climate_director import problems
from custom_components.climate_director.const import EVENT_PRECONDITION_REFUSED

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
