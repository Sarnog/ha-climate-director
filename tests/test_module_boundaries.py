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


def getattr_fallbacks_on_own_methods() -> list[str]:
    """`getattr(self, "<own method>", ...)` calls: a fallback on a method of our own."""
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
                and node.args[1].value in methods
            ):
                found.append(f"{path.relative_to(PACKAGE).as_posix()}:{node.lineno}")
    return found


def test_no_own_method_is_reached_through_a_getattr_fallback() -> None:
    """Een eigen methode wordt aangeroepen, niet via `getattr(self, naam, terugval)`.

    Een terugval op een methode die de klasse zelf (of een mixin) definieert
    verbergt dat een stand-in het lid mist: de stand-in hoort het lid te krijgen.

    An own method is called, not reached through `getattr(self, name, fallback)`.
    A fallback on a method the class itself (or a mixin) defines hides that a
    stand-in lacks the member: the stand-in should get the member.
    """
    found = getattr_fallbacks_on_own_methods()
    assert not found, (
        "getattr-terugval op een eigen methode / getattr fallback on an own method: "
        + ", ".join(found)
    )


def test_the_getattr_guard_sees_a_fallback_on_an_own_method(tmp_path: Path, monkeypatch) -> None:
    """De bewaking merkt een verzonnen terugval echt op, en een gewoon attribuut niet.

    The guard really notices an invented fallback, and not a plain attribute.
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
        "        return first, second, third\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(f"{__name__}.PACKAGE", package)
    assert getattr_fallbacks_on_own_methods() == ["host.py:5"]


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
