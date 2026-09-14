"""Elke reparatiemelding verdwijnt bij het uitladen van de installatie.

Every repair notice disappears when the installation unloads.

R30-2: `problems.async_clear_bypassed_openings` bestond wel maar werd nergens
aangeroepen. Zes van de zeven per-installatie meldingen werden bij het uitladen
opgeruimd, deze niet - een overbruggingsmelding bleef dus staan nadat de entry
weg was. De functie ernaast was dode code die precies dat gat markeerde.

Deze test leest de **lijst van meldingsfabrieken uit `problems.py`** met een AST
in plaats van hem hier nog een keer over te typen, en eist voor élke
`async_report_*` dat `async_unload_entry` de bijbehorende `async_clear_*`
werkelijk aanroept. Zo kan een achtste melding niet opnieuw vergeten worden: de
test groeit mee met de bron.

R30-2: `problems.async_clear_bypassed_openings` existed but was never called.
Six of the seven per-installation notices were cleaned up on unload, this one
was not - so a bypass notice stayed behind after the entry was gone. The
function next to it was dead code marking exactly that gap.

This test reads the **list of notice factories from `problems.py`** with an AST
instead of re-typing it here, and demands that for every `async_report_*`,
`async_unload_entry` actually calls the matching `async_clear_*`. That way an
eighth notice cannot be forgotten again: the test grows along with the source.
"""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "custom_components" / "climate_director"
PROBLEMS = PACKAGE / "problems.py"
INIT = PACKAGE / "__init__.py"


def module_functions(path: Path) -> set[str]:
    """Return the names of every function defined at module level in a file.

    Return the names of every function defined at module level in a file.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }


def report_functions() -> list[str]:
    """Return every `async_report*` factory defined in `problems.py`."""
    return sorted(name for name in module_functions(PROBLEMS) if name.startswith("async_report"))


def cleared_at_unload() -> set[str]:
    """Return every `problems.async_clear_*` call inside `async_unload_entry`.

    Return every `problems.async_clear_*` call inside `async_unload_entry`.
    """
    tree = ast.parse(INIT.read_text(encoding="utf-8"))
    cleared: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.AsyncFunctionDef) and node.name == "async_unload_entry"):
            continue
        for call in ast.walk(node):
            if not isinstance(call, ast.Call):
                continue
            func = call.func
            if not isinstance(func, ast.Attribute) or not func.attr.startswith("async_clear"):
                continue
            if isinstance(func.value, ast.Name) and func.value.id == "problems":
                cleared.add(func.attr)
    return cleared


def clear_name_for(report: str) -> str:
    """Return the clear counterpart that belongs to a report factory.

    Return the clear counterpart that belongs to a report factory.
    """
    return report.replace("async_report", "async_clear", 1)


def test_every_report_factory_has_a_clear_counterpart() -> None:
    """Elke melding die je maakt, kun je ook opruimen.

    Every notice you raise, you can also clear.
    """
    functions = module_functions(PROBLEMS)
    reports = report_functions()

    assert reports, "geen enkele `async_report_*` gevonden; de AST leest het verkeerde bestand"

    for report in reports:
        clear = clear_name_for(report)
        assert clear in functions, (
            f"{report} heeft geen tegenhanger `{clear}` in problems.py; "
            f"een melding die je niet kunt opruimen blijft eeuwig staan"
        )


def test_every_report_is_cleared_when_the_entry_unloads() -> None:
    """Bij het uitladen verdwijnt élke melding van deze installatie, niet zes van de zeven.

    On unload every notice of this installation disappears, not six of the seven.
    """
    cleared = cleared_at_unload()
    reports = report_functions()

    assert reports, "geen enkele `async_report_*` gevonden; de AST leest het verkeerde bestand"

    missing: set[str] = set()
    for report in reports:
        clear = clear_name_for(report)
        if clear not in cleared:
            missing.add(clear)
    assert not missing, (
        "deze opruimers worden niet aangeroepen in `async_unload_entry`, dus hun "
        f"melding overleeft het uitladen: {', '.join(sorted(missing))}"
    )


def test_the_guard_reads_the_real_source() -> None:
    """De bewaking hangt aan de bron en niet aan een lijst hier.

    The guard hangs on the source, not on a list here.
    """
    reports = report_functions()
    assert "async_report_bypassed_openings" in reports
    assert clear_name_for("async_report_bypassed_openings") == "async_clear_bypassed_openings"
    assert clear_name_for("async_report") == "async_clear"
    assert cleared_at_unload() >= {clear_name_for(report) for report in reports}
