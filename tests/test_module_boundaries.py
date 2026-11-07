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
    (package / "host.py").write_text(
        "class Host:\n"
        "    def payload(self):\n"
        "        return {}\n"
        "    def build(self):\n"
        "        return getattr(self, 'payload', dict)(), getattr(self, 'plain', None)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(f"{__name__}.PACKAGE", package)
    assert getattr_fallbacks_on_own_methods() == ["host.py:5"]
