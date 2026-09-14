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
["main"]` en breder dan een handlijst van bestanden: **géén bestand onder
`.github/workflows/` heeft een `push`-trigger die op een tag-ref kan afgaan.**
De bestanden komen daarom uit een glob en niet uit een lijst hier; een vierde
workflow valt er vanzelf onder, en een bestand zonder `push` (zoals
`mutation.yaml`) valt er vanzelf buiten. De regel van GitHub zelf, gemeten aan
de hand van de documentatie en de mutatiemetingen van ronde 30:

  * `push:` met alleen een `branches`-filter  -> **geen** tag-events;
  * `push:` met `branches` én `tags`          -> **allebei**, dus de tag-push
    start de banen opnieuw (precies de dubbele run die R29-2 weghaalde);
  * `push:` zonder enig filter                -> alle branches én alle tags;
  * `push:` met een `tags-ignore` naast `branches` -> onschadelijk.

Daarom eist deze test, voor elk bestand mét een `push`-trigger: `push` is een
mapping, draagt géén `tags`-sleutel, en heeft een `branches`-filter met precies
`main`. Dat is strenger dan de tag-eigenschap alleen: `branches-ignore` zou
tag-veilig zijn maar zakt op de werkregel "alleen main", en `[main, dev]` blijft
om dezelfde reden geweigerd. De `tags`-assertie staat bewust vóór de
`branches`-assertie, zodat een toegevoegde `tags`-sleutel rood valt mét de
bestandsnaam én het woord `tags` in de melding. De `REMAINING`-controle geldt
alleen voor bestanden die werkelijk een `push` hebben.

The property this test pins down is broader than the spelling `branches ==
["main"]` and broader than a hand-written list of files: **no file under
`.github/workflows/` has a `push` trigger that can fire on a tag ref.** The
files therefore come from a glob rather than from a list here; a fourth workflow
falls under it by itself, and a file without `push` (such as `mutation.yaml`)
falls outside it by itself. GitHub's own rule, measured against the
documentation and round 30's mutation runs:

  * `push:` with only a `branches` filter  -> **no** tag events;
  * `push:` with `branches` and `tags`     -> **both**, so the tag push starts
    the jobs again (exactly the double run R29-2 removed);
  * `push:` without any filter             -> all branches and all tags;
  * `push:` with `tags-ignore` next to `branches` -> harmless.

For every file **with** a `push` trigger this test therefore demands: `push` is
a mapping, carries no `tags` key, and has a `branches` filter with exactly
`main`. That is stricter than the tag property alone: `branches-ignore` would be
tag-safe, but it trips over the working rule "main only", so it is refused too -
the same reason `[main, dev]` is refused. The `tags` assertion deliberately
precedes the `branches` assertion, so an added `tags` key falls red with the
file name and the word `tags` in the message. The `REMAINING` check applies only
to files that actually have a `push`.

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

# Alle bestanden die GitHub als workflow leest. `.yml` hoort erbij: een bestand
# met die extensie draait net zo goed, en zou in een `*.yaml`-glob stil buiten
# de bewaking vallen.
#
# Every file GitHub reads as a workflow. `.yml` belongs here too: a file with
# that extension runs just as well and would silently fall outside a `*.yaml`
# glob.
WORKFLOW_FILES = tuple(sorted({*WORKFLOWS.glob("*.yaml"), *WORKFLOWS.glob("*.yml")}))
WORKFLOW_NAMES = tuple(path.name for path in WORKFLOW_FILES)

# De bestanden die er vandaag zijn. Deze lijst bewaakt de **glob**, niet de
# eigenschap: raakt de map of de extensie zoek, dan valt de eigenschap hierboven
# stil uit en zou die test groen blijven zonder iets te meten. Een nieuw bestand
# erbij is geen probleem - de bewaking groeit mee.
#
# The files present today. This list guards the **glob**, not the property: if
# the directory or the extension goes missing, the property above silently stops
# applying and that test would stay green measuring nothing. An extra file is no
# problem - the guard grows along with it.
DISCOVERED_TODAY = ("tests.yaml", "hacs.yaml", "hassfest.yaml", "mutation.yaml")

# Wat er per bestand naast `push` hoort te blijven draaien. Alleen aanwezigheid,
# niet de volledige verzameling: een nieuw event erbij is geen regressie. Geldt
# alleen voor bestanden die werkelijk een `push` hebben.
#
# What should keep running per file besides `push`. Presence only, not the full
# set: adding a new event is not a regression. Applies only to files that really
# have a `push`.
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


def test_the_glob_reads_the_real_workflow_directory() -> None:
    """De bewaking leest de echte map, niet een lege of verkeerde.

    The guard reads the real directory, not an empty or wrong one.
    """
    names = {path.name for path in WORKFLOW_FILES}
    missing = [name for name in DISCOVERED_TODAY if name not in names]
    assert not missing, (
        "de glob over `.github/workflows/` ziet deze bestanden niet: "
        + ", ".join(missing)
        + " - dan valt de tag-bewaking stil"
    )


@pytest.mark.parametrize("name", WORKFLOW_NAMES)
def test_no_push_trigger_can_fire_on_a_tag(name: str) -> None:
    """Elke `push`-trigger draait alleen op `main` en kan nooit op een tag afgaan.

    Every `push` trigger runs on `main` only and can never fire on a tag.
    """
    on = triggers(name)

    push = on.get("push")
    if push is None:
        # Geen push-trigger: een tag-push kan deze baan niet starten.
        # No push trigger: a tag push cannot start this job.
        return

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

    for event in REMAINING.get(name, ()):
        assert event in on, f"{name}: `{event}` hoort te blijven draaien"
