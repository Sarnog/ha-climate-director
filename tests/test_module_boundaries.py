"""De grenzen tussen de modules van het pakket worden bewaakt, niet alleen beloofd.

ARCHITECTURE.md ("Code-indeling", "Grenzen") zegt: een module importeert alleen
naar beneden, en een eigen methode wordt gewoon aangeroepen. Deze bewakingen
lopen met `ast` over élk bestand van het pakket, zodat een nieuwe terugval of een
nieuwe privé import over een modulegrens meteen een rode test geeft.

The borders between the package's modules are guarded, not just promised.
ARCHITECTURE.md ("Code layout", "Borders") says: a module imports only
downwards, and an own method is simply called. These guards walk every file of
the package with `ast`, so a new fallback or a new private import across a
module border turns a test red at once.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "custom_components" / "climate_director"


def package_files() -> list[Path]:
    """Every Python file of the package; an empty scan is an error."""
    files = sorted(PACKAGE.rglob("*.py"))
    assert files, "geen enkel pakketbestand gevonden / no package file found"
    return files


def method_names() -> set[str]:
    """The names of all methods defined in a class anywhere in the package."""
    names: set[str] = set()
    for path in package_files():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ClassDef):
                names.update(
                    item.name
                    for item in node.body
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                )
    return names


def getattr_fallbacks_on_self() -> list[str]:
    """`getattr(self, "<name>", ...)` calls: a fallback on a member of our own.

    Two shapes count: a name with a default (an attribute or a method that may be
    missing) and a name that is a method of a class in the package, with or without
    a default.
    """
    methods = method_names()
    found: list[str] = []
    for path in package_files():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "getattr"
                and len(node.args) >= 2
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id == "self"
                and isinstance(node.args[1], ast.Constant)
                and (len(node.args) >= 3 or node.args[1].value in methods)
            ):
                found.append(f"{path.relative_to(PACKAGE).as_posix()}:{node.lineno}")
    return found


def test_no_own_member_is_reached_through_a_getattr_fallback() -> None:
    """Een eigen attribuut of methode wordt gelezen, niet via `getattr(self, naam, terugval)`.

    Een terugval op een lid dat de klasse zelf (of een mixin of het protocol)
    draagt verbergt dat een stand-in het lid mist: de stand-in hoort het lid te
    krijgen.

    An own attribute or method is read, not reached through
    `getattr(self, name, fallback)`. A fallback on a member the class itself (or a
    mixin or the protocol) carries hides that a stand-in lacks the member: the
    stand-in should get the member.
    """
    found = getattr_fallbacks_on_self()
    assert not found, (
        "getattr-terugval op een eigen lid / getattr fallback on an own member: " + ", ".join(found)
    )


def test_the_getattr_guard_sees_a_fallback_on_an_own_member(tmp_path: Path, monkeypatch) -> None:
    """De bewaking merkt een verzonnen terugval echt op, ook in een async def.

    Een vreemd object, of een naam zonder terugval die geen methode is, blijft
    ongemoeid.

    The guard really notices an invented fallback, an async def included. A
    foreign object, or a name without a fallback that is no method, is left alone.
    """
    package = tmp_path / "package"
    package.mkdir()
    (package / "a_first.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "host.py").write_text(
        "class Host:\n"
        "    def payload(self):\n"
        "        return {}\n"
        "    def build(self):\n"
        "        first = getattr(self, 'payload', dict)()\n"
        "        second = getattr(self, 'plain', None)\n"
        "        third = getattr(other, 'payload', dict)()\n"
        "        fourth = getattr(self, 'payload')\n"
        "        fifth = getattr(self, 'plain')\n"
        "        return first, second, third, fourth, fifth\n",
        encoding="utf-8",
    )
    (package / "later.py").write_text(
        "class Later:\n"
        "    async def run(self):\n"
        "        def inner():\n"
        "            return getattr(self, '_closing', False)\n"
        "        return inner()\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(f"{__name__}.PACKAGE", package)
    found = sorted(getattr_fallbacks_on_self())
    assert found == ["host.py:5", "host.py:6", "host.py:8", "later.py:4"]


def private_imports_across_modules() -> list[str]:
    """Imports of a name with a leading underscore from another module of the package."""
    found: list[str] = []
    for path in package_files():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.ImportFrom):
                continue
            inside_package = node.level > 0 or (node.module or "").startswith(
                "custom_components.climate_director"
            )
            if not inside_package:
                continue
            for alias in node.names:
                if alias.name.startswith("_") and not alias.name.startswith("__"):
                    found.append(
                        f"{path.relative_to(PACKAGE).as_posix()}:{node.lineno}: {alias.name}"
                    )
    return found


def test_no_name_with_a_leading_underscore_crosses_a_module_border() -> None:
    """Over een modulegrens staat geen naam met een leidende onderstreping.

    Een naam die een andere module nodig heeft is niet privé: hij krijgt een
    publieke naam in het bestand waar hij woont.

    No name with a leading underscore crosses a module border. A name another
    module needs is not private: it gets a public name in the file where it lives.
    """
    found = private_imports_across_modules()
    assert not found, (
        "privé naam over een modulegrens / private name across a module border: " + ", ".join(found)
    )


def test_the_private_import_guard_sees_a_private_name_and_leaves_a_public_one(
    tmp_path: Path, monkeypatch
) -> None:
    """De bewaking merkt een verzonnen privé import en laat een publieke staan.

    The guard notices an invented private import and leaves a public one alone.
    """
    package = tmp_path / "package"
    package.mkdir()
    (package / "a_first.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "user.py").write_text(
        "from .owner import shown, _hidden\nfrom os import _exit\n", encoding="utf-8"
    )
    monkeypatch.setattr(f"{__name__}.PACKAGE", package)
    assert private_imports_across_modules() == ["user.py:1: _hidden"]


def lazy_imports() -> list[str]:
    """Imports inside a function body: the usual detour around a cycle."""
    found: list[str] = []
    for path in package_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for function in ast.walk(tree):
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(function):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    found.append(f"{path.relative_to(PACKAGE).as_posix()}:{node.lineno}")
    return found


def test_no_import_hides_inside_a_function() -> None:
    """Een import staat bovenaan het bestand, niet in een functie.

    Een luie import is de omweg rond een kring tussen twee modules; de kring zelf
    hoort verdwenen te zijn.

    An import stands at the top of the file, not inside a function. A lazy import
    is the detour around a cycle between two modules; the cycle itself should be
    gone.
    """
    found = lazy_imports()
    assert not found, "import in een functie / import inside a function: " + ", ".join(found)


def test_the_lazy_import_guard_sees_an_import_in_a_function(tmp_path: Path, monkeypatch) -> None:
    """De bewaking merkt een import in een functie en laat een gewone staan.

    The guard notices an import inside a function and leaves an ordinary one alone.
    """
    package = tmp_path / "package"
    package.mkdir()
    (package / "a_first.py").write_text("import os\n", encoding="utf-8")
    (package / "late.py").write_text(
        "import json\n\n\ndef load():\n    from .other import thing\n    return thing\n\n\n"
        "async def later():\n    import os\n    return os\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(f"{__name__}.PACKAGE", package)
    assert lazy_imports() == ["late.py:5", "late.py:10"]


def late_import_exemptions() -> list[str]:
    """Comments that silence ruff's "import not at the top" (`E402`), read with `tokenize`.

    Every spelling of the rule code in a `# noqa` comment counts, among other
    codes and in any case; a string that merely contains the text does not.
    """
    found: list[str] = []
    for path in package_files():
        with io.StringIO(path.read_text(encoding="utf-8")) as source:
            for token in tokenize.generate_tokens(source.readline):
                if token.type == tokenize.COMMENT and re.search(
                    r"noqa\s*:[^#]*\bE402\b", token.string, re.IGNORECASE
                ):
                    found.append(f"{path.relative_to(PACKAGE).as_posix()}:{token.start[0]}")
    return found


def test_no_import_is_exempted_from_standing_at_the_top() -> None:
    """Geen `# noqa: E402` in het pakket: een import staat bovenaan, zonder uitzondering.

    Een import onderaan een bestand is de omweg rond een kring tussen twee modules,
    en de kring zelf hoort verdwenen te zijn.

    No `# noqa: E402` in the package: an import stands at the top, without
    exemption. An import at the bottom of a file is the detour around a cycle between
    two modules, and the cycle itself should be gone.
    """
    found = late_import_exemptions()
    assert found == [], "E402 buiten de regel gezet / E402 exempted: " + ", ".join(found)


def test_the_exemption_guard_sees_every_spelling_and_no_string(tmp_path: Path, monkeypatch) -> None:
    """De bewaking merkt elke schrijfwijze van de uitzondering en slaat een tekst over.

    The guard notices every spelling of the exemption and skips a string.
    """
    package = tmp_path / "package"
    package.mkdir()
    (package / "a_first.py").write_text("import os  # noqa: E402\nimport sys\n", encoding="utf-8")
    (package / "second.py").write_text(
        "import json  #noqa:E402, I001\n"
        "import re  # NOQA: I001,E402\n"
        "import abc  # noqa: e402\n"
        "TEXT = 'import io  # noqa: E402'\n"
        "import ast  # noqa: I001\n"
        "import csv  # E402 is the code, but no exemption\n"
        "import cgi  # noqa: E4020\n"
        "import zlib  # noqa: I001  # E402 is named after the exemption\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(f"{__name__}.PACKAGE", package)
    assert late_import_exemptions() == ["a_first.py:1", "second.py:1", "second.py:2", "second.py:3"]


def private_attributes_of_the_coordinator() -> list[str]:
    """`coordinator._name` outside `coordinator.py`: a part reaching into the host's privates."""
    found: list[str] = []
    for path in package_files():
        if path.name == "coordinator.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "coordinator"
                and node.attr.startswith("_")
                and not node.attr.startswith("__")
            ):
                found.append(f"{path.relative_to(PACKAGE).as_posix()}:{node.lineno}: {node.attr}")
    return found


def test_no_part_reaches_into_the_privates_of_the_coordinator() -> None:
    """Buiten `coordinator.py` leest of zet niemand `coordinator._naam`.

    Een onderdeel (`coordinator_*.py`) krijgt de coördinator als eerste argument; wat
    het nodig heeft staat in `CoordinatorSurface` onder een publieke naam, of in zijn
    eigen staatsklasse in `coordinator_state.py`.

    Outside `coordinator.py` nobody reads or sets `coordinator._name`. A part
    (`coordinator_*.py`) receives the coordinator as its first argument; whatever it
    needs stands in `CoordinatorSurface` under a public name, or in its own state
    class in `coordinator_state.py`.
    """
    found = private_attributes_of_the_coordinator()
    assert not found, (
        "privé attribuut van de coördinator / private attribute of the coordinator: "
        + ", ".join(found)
    )


def private_names_of_a_sibling_module() -> list[str]:
    """`module._name` where `module` came in through `from . import module`."""
    found: list[str] = []
    for path in package_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        aliases = {
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is None
            for alias in node.names
        }
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in aliases
                and node.attr.startswith("_")
                and not node.attr.startswith("__")
            ):
                found.append(
                    f"{path.relative_to(PACKAGE).as_posix()}:{node.lineno}: "
                    f"{node.value.id}.{node.attr}"
                )
    return found


def test_no_module_reaches_into_the_privates_of_a_sibling() -> None:
    """Een privé naam van een zusterbestand wordt ook niet via `module._naam` gelezen.

    De bewaking op `from .x import _naam` ziet alleen de import; een module die als
    `from . import x` binnenkomt en daarna `x._naam` gebruikt, omzeilt hem.

    A private name of a sibling file is not read through `module._name` either. The
    guard on `from .x import _name` only sees the import; a module imported as
    `from . import x` and then used as `x._name` slips past it.
    """
    found = private_names_of_a_sibling_module()
    assert not found, "privé naam van een zusterbestand / private name of a sibling: " + ", ".join(
        found
    )


def test_the_private_attribute_guards_see_invented_cases(tmp_path: Path, monkeypatch) -> None:
    """De twee bewakingen merken verzonnen gevallen op, ook in een async def.

    Het toegestane blijft staan.

    The two guards notice invented cases, an async def included, and leave the allowed alone.
    """
    package = tmp_path / "package"
    package.mkdir()
    (package / "coordinator.py").write_text(
        "def build(coordinator):\n    return coordinator._allowed_here\n", encoding="utf-8"
    )
    (package / "part_one.py").write_text(
        "from . import helper as aid, other\n"
        "from .other import Thing\n"
        "def run(coordinator):\n"
        "    a = coordinator._hidden\n"
        "    b = coordinator.shown\n"
        "    c = coordinator.__class__\n"
        "    d = aid._secret\n"
        "    e = other.public\n"
        "    f = unrelated._thing\n"
        "    g = Thing._internal\n"
        "    return a, b, c, d, e, f, g\n",
        encoding="utf-8",
    )
    (package / "part_two.py").write_text(
        "from . import helper\n"
        "async def later(coordinator):\n"
        "    await coordinator._also_hidden()\n"
        "    return helper._LOGGER, helper.__name__\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(f"{__name__}.PACKAGE", package)
    assert sorted(private_attributes_of_the_coordinator()) == [
        "part_one.py:4: _hidden",
        "part_two.py:3: _also_hidden",
    ]
    assert sorted(private_names_of_a_sibling_module()) == [
        "part_one.py:7: aid._secret",
        "part_two.py:4: helper._LOGGER",
    ]
