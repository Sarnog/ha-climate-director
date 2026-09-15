"""`script/test` en `script/lint` draaien precies wat de CI draait.

`script/test` and `script/lint` run exactly what CI runs.

C13 van ronde 22: de scripts zijn er zodat lokaal en CI niet uit elkaar lopen.
Ronde 31 zette een nieuwe stap in de CI ("Coverage gate") en vergat hem in
`script/test`, terwijl de kop van dat script belooft "precies wat de CI aan tests
draait, lokaal". Dat is de vorm die deze bewaking moet stoppen: een stap erbij in
`tests.yaml` blijft niet stil achter.

De eigenschap hangt aan de **bron** en niet aan een handlijst van stapnamen: elke
`run:`-regel van de baan `tests` in `tests.yaml` moet, met dezelfde tool en
dezelfde argumenten, in `script/test` of `script/lint` staan. De opstapstappen
(`python -m pip install …`) horen daar niet bij — die staan in `script/setup` —
dus die worden overgeslagen op hun tool. De omgekeerde richting wordt ook
bewaakt: een commando dat alleen in een script staat, hoort ergens in
`tests.yaml` te staan.

C13 of round 22: the scripts exist so that local and CI do not drift apart.
Round 31 added a new CI step ("Coverage gate") and forgot it in `script/test`,
while that script's header promises "exactly what CI runs for tests, locally".
That is the shape this guard has to stop: an extra step in `tests.yaml` must not
stay behind silently.

The property hangs on the **source**, not on a hand-written list of step names:
every `run:` line of the `tests` job in `tests.yaml` must appear, with the same
tool and the same arguments, in `script/test` or `script/lint`. The setup steps
(`python -m pip install …`) do not belong there — they live in `script/setup` —
so they are skipped on their tool. The reverse direction is guarded too: a
command that only lives in a script belongs somewhere in `tests.yaml`.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "tests.yaml"

#: De twee scripts die de test- en lintstappen van de CI spiegelen.
#:
#: The two scripts that mirror the CI's test and lint steps.
SCRIPTS = ("script/test", "script/lint")

#: Waarmee een script zijn commando's aanroept; de CI schrijft gewoon `python`.
#:
#: What a script calls its commands with; CI simply writes `python`.
INTERPRETER = '"$PYTHON"'
CI_INTERPRETER = "python"

#: De opstapstap van de CI; die hoort in `script/setup`, niet in een testscript.
#:
#: The CI's setup step; that belongs in `script/setup`, not in a test script.
SETUP = "-m pip"


def workflow() -> dict:
    """De `tests.yaml` als mapping.

    `tests.yaml` as a mapping.
    """
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(document, dict), "tests.yaml hoort een mapping te zijn"
    return document


def ci_commands(job: str = "tests") -> list[tuple[str, str]]:
    """Geef (stapnaam, commando) van elke `run:`-regel in een baan.

    Geeft de opstapregels mee: de aanroeper beslist wat hij ermee doet.

    Return (step name, command) of every `run:` line in a job. The setup lines
    are included; the caller decides what to do with them.
    """
    steps: list[tuple[str, str]] = []
    for step in workflow()["jobs"][job]["steps"]:
        run = step.get("run")
        if not isinstance(run, str):
            continue
        for line in run.splitlines():
            stripped = line.strip()
            if stripped:
                steps.append((step.get("name", "?"), stripped))
    return steps


def without_interpreter(command: str, interpreter: str) -> str:
    """Haal de interpreter van een commando af, zodat alleen de tool overblijft.

    Strip the interpreter off a command, so only the tool remains.
    """
    prefix = f"{interpreter} "
    assert command.startswith(prefix), f"geen commando: {command!r}"
    return command[len(prefix) :].strip()


def script_commands(name: str) -> list[str]:
    """Elk commando van een script, zonder de interpreter.

    Every command of a script, without the interpreter.
    """
    lines = (ROOT / name).read_text(encoding="utf-8").splitlines()
    calls = [line.strip() for line in lines if line.strip().startswith(INTERPRETER)]
    return [without_interpreter(line, INTERPRETER) for line in calls]


def test_every_ci_step_of_the_tests_job_is_in_a_script() -> None:
    """Elke test- en lintstap van de CI staat in `script/test` of `script/lint`.

    Every test and lint step of the CI lives in `script/test` or `script/lint`.
    """
    scripts = {command for name in SCRIPTS for command in script_commands(name)}

    missing = []
    for step, line in ci_commands():
        if SETUP in line or not line.startswith(f"{CI_INTERPRETER} "):
            continue
        command = without_interpreter(line, CI_INTERPRETER)
        if command not in scripts:
            missing.append(f"{step} ({command})")

    assert not missing, (
        "deze stappen van de baan `tests` draait geen enkel script, dus lokaal en "
        "in de CI lopen uit elkaar: " + "; ".join(missing)
    )


def test_every_script_command_is_a_ci_step() -> None:
    """Een commando dat alleen in een script staat, hoort daar niet.

    A command that lives only in a script does not belong there.
    """
    known = set()
    for job in workflow()["jobs"].values():
        for step in job["steps"]:
            run = step.get("run")
            if not isinstance(run, str):
                continue
            for line in run.splitlines():
                stripped = line.strip()
                if stripped.startswith(f"{CI_INTERPRETER} ") and SETUP not in stripped:
                    known.add(without_interpreter(stripped, CI_INTERPRETER))

    extra = [
        f"{name} ({command})"
        for name in SCRIPTS
        for command in script_commands(name)
        if command not in known
    ]

    assert not extra, (
        "deze commando's staan in een script maar in geen enkele CI-baan, dus "
        "lokaal en in de CI lopen uit elkaar: " + "; ".join(extra)
    )


def test_the_guard_reads_the_real_files() -> None:
    """De bewaking leest de echte bestanden, niet een lege of verkeerde.

    The guard reads the real files, not an empty or wrong one.
    """
    assert WORKFLOW.exists(), "tests.yaml niet gevonden"
    assert "tests" in workflow()["jobs"], "de baan `tests` niet gevonden"
    assert ci_commands(), "geen enkele `run:`-regel gevonden in de baan `tests`"
    for name in SCRIPTS:
        assert (ROOT / name).exists(), f"{name} niet gevonden"
        assert script_commands(name), f"{name} roept geen enkel commando aan met $PYTHON"


def test_the_setup_step_is_recognised() -> None:
    """De opstapstap wordt herkend, zodat hij niet stil buiten de bewaking valt.

    The setup step is recognised, so it does not silently fall outside the guard.
    """
    setup = [line for _step, line in ci_commands() if SETUP in line]
    assert len(setup) == 2, f"verwachte twee opstapregels, vond {setup}"
