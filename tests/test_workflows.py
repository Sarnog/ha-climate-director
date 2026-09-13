"""Eén commit, één run: `push` draait alleen op `main`.

One commit, one run: `push` only runs on `main`.

R29-2: zonder branchfilter start `git push --tags` naast de gewone push nog een
keer élke baan op dezelfde commit - twee runs per release, en de tweede voegt
niets toe. De drie workflowbestanden dragen daarom `push: branches: [main]`;
`pull_request`, `schedule` en `workflow_dispatch` blijven gewoon staan. Deze test
pint die eigenschap vast: haalt iemand het filter uit één bestand, dan valt hier
een rood, en dat is precies de mutatie uit de acceptatie van ronde 29.

R29-2: without a branch filter `git push --tags` starts every job a second time
on the same commit - two runs per release, and the second one adds nothing. The
three workflow files therefore carry `push: branches: [main]`; `pull_request`,
`schedule` and `workflow_dispatch` simply stay. This test pins that property
down: remove the filter from one file and a red falls here, which is exactly the
mutation from round 29's acceptance.

Let op: PyYAML leest de `on:`-sleutel als de boolean `True` (YAML 1.1), dus de
triggers worden op beide sleutels opgezocht.

Note: PyYAML reads the `on:` key as the boolean `True` (YAML 1.1), so the
triggers are looked up under both keys.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"

# De drie banen die op een push draaien.
# The three jobs that run on a push.
FILES = ("tests.yaml", "hacs.yaml", "hassfest.yaml")

# Wat er per bestand naast `push` hoort te blijven draaien. Alleen aanwezigheid,
# niet de volledige verzameling: een nieuw event erbij is geen regressie.
# What should keep running per file besides `push`. Presence only, not the full
# set: adding a new event is not a regression.
REMAINING = {
    "tests.yaml": ("pull_request", "workflow_dispatch"),
    "hacs.yaml": ("pull_request", "schedule", "workflow_dispatch"),
    "hassfest.yaml": ("pull_request", "schedule"),
}


def triggers(name: str) -> dict:
    """Geef de `on:`-mapping van een workflowbestand terug.

    Return the `on:` mapping of a workflow file.
    """
    document = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    assert isinstance(document, dict), f"{name} hoort een mapping te zijn"
    on = document.get("on", document.get(True))
    assert isinstance(on, dict), f"{name} hoort een `on:`-mapping te hebben"
    return on


@pytest.mark.parametrize("name", FILES)
def test_a_push_only_runs_the_jobs_on_main(name: str) -> None:
    """`push` heeft een `branches`-filter met precies `main`, en de rest blijft.

    `push` carries a `branches` filter holding exactly `main`, and the rest stays.
    """
    on = triggers(name)

    push = on.get("push")
    assert isinstance(push, dict), f"{name}: `push` hoort een `branches`-filter te hebben"
    assert push.get("branches") == ["main"], (
        f"{name}: `push` hoort alleen op main te draaien, niet op tags of andere branches"
    )

    for event in REMAINING[name]:
        assert event in on, f"{name}: `{event}` hoort te blijven draaien"
