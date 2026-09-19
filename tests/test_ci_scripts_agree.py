"""`script/test` en `script/lint` draaien precies wat de CI draait.

De scripts zijn er zodat lokaal en CI niet uit elkaar lopen: een stap erbij in
`tests.yaml` hoort niet stil achter te blijven. De eigenschap hangt aan de
**bron** en niet aan een handlijst van stapnamen: elk commando van elke baan in
`tests.yaml` moet, met dezelfde tool en dezelfde argumenten, in `script/test` of
`script/lint` staan. Een `run:`-regel wordt daarom eerst in losse commando's
geknipt - op `shlex`, en verder op `&&`, `||` en `;` - want een regel die de
opstap aan een tweede commando plakt hoort niet in zijn geheel overgeslagen te
worden, en een regel zonder interpreter ervoor (`pytest ...`, `ruff ...`) is net
zo goed een stap. De opstapstappen (`python -m pip install ...`) horen niet in
een script thuis - die staan in `script/setup` - dus die worden overgeslagen, en
wel op het **eerste** commando van de regel. De omgekeerde richting wordt ook
bewaakt: een commando dat alleen in een script staat, hoort ergens in
`tests.yaml` te staan. Daarnaast eist een tweede test de **vorm**: elke
niet-opstapregel van elke niet-uitgezonderde baan begint met `python -m` of
`python script/`. Eén vorm, dan bestaat de rand niet: geen `python3`, geen kale
tool, geen `"$PYTHON"` in de CI.

`oldest-supported` is de uitzondering en staat letterlijk in dit bestand met zijn
reden: die baan pint een Home Assistant-versie en draait daarna dezelfde pytest,
dus het is een variatie op de CI-omgeving en geen commando van zijn eigen.

`script/test` and `script/lint` run exactly what CI runs.

The scripts exist so that local and CI do not drift apart: an extra step in
`tests.yaml` must not stay behind silently. The property hangs on the **source**,
not on a hand-written list of step names: every `run:` line of every job in
`tests.yaml` must appear, with the same tool and the same arguments, in
`script/test` or `script/lint`. A `run:` line is therefore split into separate
commands first - on `shlex`, and further on `&&`, `||` and `;` - because a line
that glues the setup to a second command must not be skipped as a whole, and a
line without an interpreter in front (`pytest ...`, `ruff ...`) is a step just
the same. The setup steps (`python -m pip install ...`) do not belong in a script
- they live in `script/setup` - so they are skipped, and skipped on the **first**
command of the line. The reverse direction is guarded too: a command that only
lives in a script belongs somewhere in `tests.yaml`. On top of that a second test
demands the **form**: every non-setup line of every non-exempt job starts with
`python -m` or `python script/`. One form, so the edge does not exist: no
`python3`, no bare tool, no `"$PYTHON"` in CI.

`oldest-supported` is the exception and stands literally in this file with its
reason: that job pins a Home Assistant version and then runs the very same
pytest, so it is a variation on the CI environment rather than a command of its
own.
"""

from __future__ import annotations

import shlex
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

#: De interpreters die de CI voor een stap mag zetten. Ze worden van het commando
#: afgehaald; wat overblijft is de tool met zijn argumenten. Staat er iets anders
#: voor, dan blijft de regel zoals hij is, en dan meldt de bewaking hem.
#:
#: The interpreters CI may put in front of a step. They are stripped off the
#: command; what remains is the tool with its arguments. Anything else in front
#: leaves the line as it is, and then the guard reports it.
CI_INTERPRETERS = ("python", "python3")

#: De twee vormen die een niet-opstapregel in `tests.yaml` mag hebben. Eén vorm,
#: dan bestaat de rand niet: geen `python3`, geen kale tool, geen `"$PYTHON"`, en
#: geen stap waar de bewaking naar moest raden.
#:
#: The two shapes a non-setup line in `tests.yaml` may have. One form, so the
#: edge does not exist: no `python3`, no bare tool, no `"$PYTHON"`, and no step
#: the guard had to guess about.
CI_PREFIXES = ("python -m ", "python script/")

#: De opstapstap van de CI; die hoort in `script/setup`, niet in een testscript.
#:
#: The CI's setup step; that belongs in `script/setup`, not in a test script.
SETUP = "-m pip"

#: De scheidingstekens waarmee één `run:`-regel meerdere commando's aan elkaar
#: plakt. Alle drie worden herkend: een regel die de opstap met `&&` aan een tweede
#: commando koppelt, viel anders in zijn geheel buiten de bewaking.
#:
#: The separators with which one `run:` line glues several commands together. All
#: three are recognised: a line gluing the setup to a second command with `&&`
#: otherwise fell outside the guard as a whole.
COMMAND_SEPARATORS = ("&&", "||", ";")

#: Waaraan een opstapcommando te herkennen is: `python -m pip`. Alleen het
#: **eerste** commando van een regel telt als opstap; staat de opstap achter `&&`,
#: dan is de rest van de regel een gewoon commando, en dat valt onder de bewaking.
#:
#: How a setup command is recognised: `python -m pip`. Only the **first** command
#: of a line counts as setup; with the setup behind `&&` the rest of the line is an
#: ordinary command, and that falls under the guard.
SETUP_COMMAND = ("python", "-m", "pip")

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


def commands_of(line: str) -> list[str]:
    """Knip één `run:`-regel in de losse commando's die erin staan.

    `shlex` knipt de regel in woorden en haalt de aanhalingstekens eraf; daarna
    splitst deze functie op `&&`, `||` en `;`. Zo blijft een regel die twee
    commando's aan elkaar plakt twee commando's, in plaats van één regel die aan
    geen enkele kant meer te vergelijken is.

    De vormen die dit dekt: een enkel commando, `a && b`, `a || b`, `a ; b`, en elke
    mengeling daarvan op één regel, met of zonder aanhalingstekens en met of zonder
    extra spaties.

    Split one `run:` line into the separate commands it holds.

    `shlex` cuts the line into words and takes the quotes off; after that this
    function splits on `&&`, `||` and `;`. That way a line gluing two commands
    together stays two commands, instead of one line that can no longer be compared
    at either end.

    The forms this covers: a single command, `a && b`, `a || b`, `a ; b`, and any
    mixture of those on one line, with or without quotes and with or without extra
    spaces.
    """
    commands: list[list[str]] = [[]]
    for token in words(line):
        if token in COMMAND_SEPARATORS:
            commands.append([])
        else:
            commands[-1].append(token)
    return [" ".join(command) for command in commands if command]


def is_setup(command: str) -> bool:
    """Is dit een opstapcommando? Dat is het als het met `python -m pip` begint.

    Elk commando van een regel komt hier langs, niet alleen het eerste:
    `ci_commands()` knipt een `run:`-regel in losse commando's en deze toets ziet
    ze allemaal. Dat is strenger dan "alleen de opstap vooraan" - een opstap achter
    een `&&` is ook een opstap, en de bewaking hiernaast laat hem dus niet als
    gewone stap door.

    Every command of a line passes through here, not just the first:
    `ci_commands()` splits a `run:` line into separate commands and this check
    sees them all. That is stricter than "only a leading setup" - a setup behind
    a `&&` is a setup too, and the guard beside this one therefore does not let it
    through as an ordinary step.
    """
    return tuple(words(command)[:3]) == SETUP_COMMAND


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
            if not stripped:
                continue
            for command in commands_of(stripped):
                steps.append((step.get("name", "?"), command))
    return steps


def words(line: str) -> list[str]:
    """De woorden van een commando, met `shlex` — aanhalingstekens eraf.

    De aanhalingstekens rond `"$PYTHON"` zijn voor de shell; voor de vergelijking
    is de naam zelf de interpreter. `shlex` doet dat precies zo.

    The words of a command, with `shlex` — quotes removed. The quotes around
    `"$PYTHON"` are for the shell; for the comparison the name itself is the
    interpreter. `shlex` does exactly that.
    """
    return shlex.split(line)


def without_interpreter(line: str) -> str:
    """Haal een interpreter van een commando af; alleen `python` en `python3`.

    Staat er iets anders voor — een kale tool, een derde interpreter — dan blijft
    de regel zoals hij is. De aanroeper vergelijkt hem dan met de scripts en
    meldt hem als bevinding, in plaats van hem stil over te slaan.

    Strip an interpreter off a command; only `python` and `python3`. Anything else
    in front — a bare tool, a third interpreter — leaves the line as it is. The
    caller then compares it with the scripts and reports it as a finding, instead
    of skipping it silently.
    """
    found = words(line)
    if found and found[0] in CI_INTERPRETERS:
        found = found[1:]
    return " ".join(found)


def script_commands(name: str) -> list[str]:
    """Elk commando van een script, zonder de interpreter.

    Every command of a script, without the interpreter.
    """
    lines = (ROOT / name).read_text(encoding="utf-8").splitlines()
    return [" ".join(words(line)[1:]) for line in lines if line.strip().startswith(INTERPRETER)]


def test_every_ci_step_of_every_job_is_in_a_script() -> None:
    """Elke test- en lintstap van élke CI-baan staat in `script/test` of `script/lint`.

    Every test and lint step of every CI job lives in `script/test` or `script/lint`.
    """
    scripts = {command for name in SCRIPTS for command in script_commands(name)}

    missing = []
    for job in ci_jobs():
        if job in EXEMPT_JOBS:
            continue
        for step, command in ci_commands(job):
            if is_setup(command):
                continue
            command = without_interpreter(command)
            if command not in scripts:
                missing.append(f"{job}: {step} ({command})")

    assert not missing, (
        "deze stappen draait geen enkel script, dus lokaal en in de CI lopen uit "
        "elkaar: " + "; ".join(missing)
    )


def test_every_ci_step_keeps_the_one_allowed_form() -> None:
    """Elke niet-opstapregel in `tests.yaml` houdt de ene toegestane vorm.

    Twee vormen en niets anders: `python -m <module>` of `python script/<bestand>`.
    Eén vorm, dan bestaat de rand niet — geen `python3`, geen kale tool, geen
    `"$PYTHON"` in de CI. Zonder deze eis moet de bewaking hiernaast elke
    schrijfwijze kennen, en elke schrijfwijze die er dan bijkomt is een gat.

    Every non-setup line in `tests.yaml` keeps the one allowed form. Two shapes
    and nothing else: `python -m <module>` or `python script/<file>`. One
    form, so the edge does not exist — no `python3`, no bare tool, no `"$PYTHON"`
    in CI. Without this demand the guard beside it has to know every spelling, and
    every spelling that comes along after that is a hole.
    """
    offenders = [
        f"{job}: {step} ({command})"
        for job in ci_jobs()
        if job not in EXEMPT_JOBS
        for step, command in ci_commands(job)
        if not is_setup(command) and not command.startswith(CI_PREFIXES)
    ]
    assert not offenders, (
        "deze CI-stappen gebruiken een andere vorm dan `python -m` of "
        "`python script/`, en dan moet de bewaking hiernaast spellingen raden: "
        + "; ".join(offenders)
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
    own = [command for _step, command in ci_commands("oldest-supported") if not is_setup(command)]
    assert own, "de uitgezonderde baan draait geen eigen stap meer, dus de uitzondering kan weg"
    for line in own:
        assert without_interpreter(line) not in scripts, (
            "de stap van de uitgezonderde baan staat nu wél in een script, dus haal "
            f"de uitzondering weg: {line}"
        )


def test_every_script_command_is_a_ci_step() -> None:
    """Een commando dat alleen in een script staat, hoort daar niet.

    A command that lives only in a script does not belong there.
    """
    known = set()
    for job in ci_jobs():
        for _step, command in ci_commands(job):
            if not is_setup(command):
                known.add(without_interpreter(command))

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
    setup = [command for _step, command in ci_commands() if is_setup(command)]
    assert len(setup) == 2, f"verwachte twee opstapregels, vond {setup}"
