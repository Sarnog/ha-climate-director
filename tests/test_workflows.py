"""Eén commit, één run: geen `push`-trigger kan op een tag-ref afgaan.

One commit, one run: no `push` trigger can fire on a tag ref.

R29-2: zonder branchfilter start `git push --tags` naast de gewone push nog een
keer élke baan op dezelfde commit - twee runs per release, en de tweede voegt
niets toe. De drie workflowbestanden dragen daarom `push: branches: [main]`;
`pull_request`, `schedule` en `workflow_dispatch` blijven gewoon staan.

R29-2: without a branch filter `git push --tags` starts every job a second time
on the same commit - two runs per release, and the second one adds nothing. The
three workflow files therefore carry `push: branches: [main]`; `pull_request`,
`schedule` and `workflow_dispatch` simply stay.

De eigenschap die deze test vastpint is breder dan de schrijfwijze `branches ==
["main"]`: geen enkele `push`-trigger mag op een tag-ref kunnen afgaan. De regel
van GitHub zelf, gemeten aan de hand van de documentatie en de mutatiemetingen
van ronde 30:

  * `push:` met alleen een `branches`-filter  -> **geen** tag-events;
  * `push:` met `branches` én `tags`          -> **allebei**, dus de tag-push
    start de banen opnieuw (precies de dubbele run die R29-2 weghaalde);
  * `push:` zonder enig filter                -> alle branches én alle tags;
  * `push:` met een `tags-ignore` naast `branches` -> onschadelijk.

Daarom eist deze test: `push` heeft een `branches`-filter met precies `main` én
géén `tags`-sleutel. Dat is strenger dan de tag-eigenschap alleen:
`branches-ignore` zou tag-veilig zijn, maar zakt op de werkregel "alleen main",
en `[main, dev]` blijft om dezelfde reden geweigerd. De `tags`-assertie staat
bewust vóór de `branches`-assertie, zodat een toegevoegde `tags`-sleutel rood
valt mét de bestandsnaam én het woord `tags` in de melding.

The property this test pins down is broader than the spelling `branches ==
["main"]`: no `push` trigger may be able to fire on a tag ref. GitHub's own rule,
measured against the documentation and round 30's mutation runs:

  * `push:` with only a `branches` filter  -> **no** tag events;
  * `push:` with `branches` and `tags`     -> **both**, so the tag push starts
    the jobs again (exactly the double run R29-2 removed);
  * `push:` without any filter             -> all branches and all tags;
  * `push:` with `tags-ignore` next to `branches` -> harmless.

This test therefore demands: `push` carries a `branches` or `branches-ignore`
filter **and no `tags` key**. `branches-ignore` is allowed (stricter than
needed); `[main, dev]` stays refused, because the working rule is "main only".
The `tags` assertion deliberately precedes the `branches` assertion, so an added
`tags` key falls red with the file name and the word `tags` in the message.

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
    """`push` draait alleen op `main` en kan nooit op een tag-ref afgaan.

    `push` only runs on `main` and can never fire on a tag ref.
    """
    on = triggers(name)

    push = on.get("push")
    assert isinstance(push, dict), (
        f"{name}: `push` hoort een `branches`-filter te hebben; zonder filter draait "
        f"de baan ook op een tag-push"
    )

    # GitHub-regel: alleen `branches` = geen tag-events; `branches` én `tags` = allebei.
    # GitHub rule: `branches` alone = no tag events; `branches` and `tags` = both.
    assert "tags" not in push, (
        f"{name}: `push` heeft een `tags`-sleutel. Met een `tags`-filter naast "
        f"`branches` draait GitHub de baan ook op een tag-push, en dat is precies de "
        f"dubbele run die R29-2 weghaalde"
    )

    # Werkregel: alleen main; `branches-ignore` en `[main, dev]` zakken hierop.
    # Working rule: main only; `branches-ignore` and `[main, dev]` fail on it.
    assert push.get("branches") == ["main"], (
        f"{name}: `push` hoort alleen op main te draaien, niet op tags of andere branches"
    )

    for event in REMAINING[name]:
        assert event in on, f"{name}: `{event}` hoort te blijven draaien"
