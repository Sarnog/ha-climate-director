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
every `run:` line of every job in `tests.yaml` must appear, with the same tool and
the same arguments, in `script/test` or `script/lint`. The setup steps
(`python -m pip install …`) do not belong there — they live in `script/setup` —
so they are skipped on their tool. One job is the exception and it stands
literally in this file with its reason: `oldest-supported` pins a Home Assistant
version and then runs the very same pytest, so it is a variation on the CI
environment rather than a command of its own. The reverse direction is guarded
too: a command that only lives in a script belongs somewhere in `tests.yaml`.

Ronde 35 (R35-2): de heenrichting las alleen de baan `tests`. Gemeten in ronde
34: een extra stap `python -m mypy tests/test_gates.py` in de baan `mypy` bleef
stil achter (2775 groen) terwijl `script/lint` belooft precies de CI-lint te
draaien. De bewaking loopt daarom over élke baan.

Round 35 (R35-2): the forward direction read only the `tests` job. Measured in
round 34: an extra step `python -m mypy tests/test_gates.py` in the `mypy` job
stayed behind silently (2775 green) while `script/lint` promises to run exactly
the CI lint. The guard therefore covers every job.
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

#: De enige baan waarvan de eigen stap níét in een script hoort te staan, met de
#: reden erbij. Deze baan pint een Home Assistant-versie (`homeassistant==2025.3.*`)
#: en draait daarna precies dezelfde pytest; dat is een variatie op de
#: CI-omgeving en geen eigen commando, dus er hoort geen scriptregel bij. De test
#: hieronder eist dat deze uitzondering exact is en dat hij echt nodig blijft.
#:
#: The only job whose own step should not stand in a script, with its reason.
#: This job pins a Home Assistant version (`homeassistant==2025.3.*`) and then
#: runs the very same pytest; that is a variation on the CI environment rather
#: than a command of its own, so no script line belongs with it. The test below
#: demands that this exception is exact and that it stays really needed.
EXEMPT_JOBS: dict[str, str] = {
    "oldest-supported": (
        "pint een Home Assistant-versie en draait daarna hetzelfde pytest; dat is "
        "een CI-variatie op de omgeving, geen eigen commando"
    ),
}


def workflow() -> dict:
    """De `tests.yaml` als mapping.

    `tests.yaml` as a mapping.
    """
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(document, dict), "tests.yaml hoort een mapping te zijn"
    return document


def ci_jobs() -> list[str]:
    """Elke baan uit `tests.yaml`, in de volgorde van het bestand.

    Every job in `tests.yaml`, in the order of the file.
    """
    jobs = workflow()["jobs"]
    assert isinstance(jobs, dict) and jobs, "tests.yaml hoort banen te hebben"
    return list(jobs)


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


def test_every_ci_step_of_every_job_is_in_a_script() -> None:
    """Elke test- en lintstap van élke CI-baan staat in `script/test` of `script/lint`.

    Every test and lint step of every CI job lives in `script/test` or `script/lint`.
    """
    scripts = {command for name in SCRIPTS for command in script_commands(name)}

    missing = []
    for job in ci_jobs():
        if job in EXEMPT_JOBS:
            continue
        for step, line in ci_commands(job):
            if SETUP in line or not line.startswith(f"{CI_INTERPRETER} "):
                continue
            command = without_interpreter(line, CI_INTERPRETER)
            if command not in scripts:
                missing.append(f"{job}: {step} ({command})")

    assert not missing, (
        "deze stappen draait geen enkel script, dus lokaal en in de CI lopen uit "
        "elkaar: " + "; ".join(missing)
    )


def test_the_only_exempt_job_pins_a_version_and_stays_needed() -> None:
    """De uitzondering staat letterlijk in de test, met de reden erbij.

    The exception stands literally in the test, with its reason.

    Twee kanten, allebei even hard: de uitzondering is exact (`oldest-supported`,
    geen tweede baan die stilletjes meelift), en ze blijft nodig — de eigen stap
    van die baan staat in géén enkel script. Zou iemand die stap alsnog in
    `script/test` zetten, dan hoort de uitzondering te verdwijnen in plaats van
    te blijven staan.

    Two sides, equally hard: the exception is exact (`oldest-supported`, no
    second job quietly riding along), and it stays needed — that job's own step
    stands in no script at all. Should someone add that step to `script/test`
    after all, the exception belongs out instead of staying.
    """
    jobs = ci_jobs()
    assert set(EXEMPT_JOBS) == {"oldest-supported"}, (
        "de uitzondering is precies de baan die een HA-versie pint: "
        + ", ".join(sorted(EXEMPT_JOBS))
    )
    assert set(EXEMPT_JOBS) <= set(jobs), "de uitgezonderde baan bestaat niet meer in tests.yaml"
    for reason in EXEMPT_JOBS.values():
        assert reason.strip(), "een uitzondering zonder reden is geen uitzondering"

    scripts = {command for name in SCRIPTS for command in script_commands(name)}
    own = [
        line
        for _step, line in ci_commands("oldest-supported")
        if line.startswith(f"{CI_INTERPRETER} ") and SETUP not in line
    ]
    assert own, "de uitgezonderde baan draait geen eigen stap meer, dus de uitzondering kan weg"
    for line in own:
        assert without_interpreter(line, CI_INTERPRETER) not in scripts, (
            "de stap van de uitgezonderde baan staat nu wél in een script, dus haal "
            f"de uitzondering weg: {line}"
        )


def test_every_script_command_is_a_ci_step() -> None:
    """Een commando dat alleen in een script staat, hoort daar niet.

    A command that lives only in a script does not belong there.
    """
    known = set()
    for job in ci_jobs():
        for step in workflow()["jobs"][job]["steps"]:
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
    jobs = ci_jobs()
    assert "tests" in jobs and "mypy" in jobs, f"de verwachte banen staan er niet: {jobs}"
    for job in jobs:
        assert ci_commands(job), f"geen enkele `run:`-regel gevonden in de baan {job}"
    for name in SCRIPTS:
        assert (ROOT / name).exists(), f"{name} niet gevonden"
        assert script_commands(name), f"{name} roept geen enkel commando aan met $PYTHON"


def test_the_setup_step_is_recognised() -> None:
    """De opstapstap wordt herkend, zodat hij niet stil buiten de bewaking valt.

    The setup step is recognised, so it does not silently fall outside the guard.
    """
    setup = [line for _step, line in ci_commands() if SETUP in line]
    assert len(setup) == 2, f"verwachte twee opstapregels, vond {setup}"
