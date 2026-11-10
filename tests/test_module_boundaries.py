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
