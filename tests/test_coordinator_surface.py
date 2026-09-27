"""Het protocol van de coördinator noemt precies wat de mixins gebruiken.

`CoordinatorSurface` bestaat alleen voor mypy: de vier mixins (`overrides.py`,
`preconditions.py`, `state_store.py`, `world_builder.py`) erven er onder
`TYPE_CHECKING` van, zodat hun `self` elk lid van de coördinator kent. Buiten de
typecontrole bestaat het protocol niet, en dus controleerde niets of de
coördinator die leden ook werkelijk draagt, of een lid er nog toe doet, of dat een
mixin iets gebruikt wat er niet in staat. Deze toetsen doen dat, zonder handlijst:
de leden komen uit `CoordinatorSurface.__annotations__` plus de methodes en
properties in de klasse zelf.

Dekking: (1) elk lid wordt door minstens één mixin gebruikt, als `self.<lid>` of
als letterlijke naam in `getattr(self, …)` / `hasattr(self, …)`; (2) elke
`self.<naam>` in een mixinbestand is een lid van het protocol of iets wat die
mixin zelf definieert (een methode of een klasse-attribuut) - dat is precies wat
mypy via het protocol laat passeren; (3) de echte coördinator, opgestart met
`start_house`, heeft elk lid; (4) elke stand-in in `tests/` die een methode van
`ClimateDirectorCoordinator` leent (`naam = ClimateDirectorCoordinator.<methode>`
in de klassebody) draagt zelf elk protocollid dat die methodes als `self.<lid>`
aanraken: in de klassebody, of als `self.<lid> = …` in een eigen methode. Niet
gedekt: een naam die via `getattr(self, …)` met een standaardwaarde gelezen wordt
telt bij (2) en (4) niet, want die mag ontbreken; een methode die een stand-in op
een andere manier leent (via een basisklasse, of `item.x = …` van buitenaf), en
leden buiten het protocol die een geleende methode aanraakt.

The coordinator's protocol names exactly what the mixins use.

`CoordinatorSurface` exists only for mypy: the four mixins (`overrides.py`,
`preconditions.py`, `state_store.py`, `world_builder.py`) inherit from it under
`TYPE_CHECKING`, so their `self` knows every member of the coordinator. Outside
the type check the protocol does not exist, so nothing checked whether the
coordinator really carries those members, whether a member still matters, or
whether a mixin uses something that is not in it. These tests do, without a
hand-written list: the members come from `CoordinatorSurface.__annotations__`
plus the methods and properties in the class itself.

Coverage: (1) every member is used by at least one mixin, as `self.<member>` or
as a literal name in `getattr(self, …)` / `hasattr(self, …)`; (2) every
`self.<name>` in a mixin file is a member of the protocol or something that mixin
defines itself (a method or a class attribute) - exactly what mypy lets through
by way of the protocol; (3) the real coordinator, started with `start_house`,
has every member; (4) every stand-in in `tests/` that borrows a method of
`ClimateDirectorCoordinator` (`name = ClimateDirectorCoordinator.<method>` in the
class body) carries every protocol member those methods touch as
`self.<member>` itself: in the class body, or as `self.<member> = …` in a method
of its own. Not covered: a name read through `getattr(self, …)` with a default
does not count for (2) and (4), since it may be missing; a method a stand-in
borrows another way (through a base class, or `item.x = …` from outside), and
members outside the protocol that a borrowed method touches.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path

from harness_live import settings, source, start_house, stop_house, zone

from custom_components.climate_director import coordinator as coordinator_module
from custom_components.climate_director.coordinator import (
    ClimateDirectorCoordinator,
    CoordinatorSurface,
)

PACKAGE = Path(coordinator_module.__file__).parent
TESTS = Path(__file__).parent

#: De vier mixins die van het protocol erven; de coördinator erft van hen.
#:
#: The four mixins inheriting from the protocol; the coordinator inherits from them.
MIXIN_FILES = ("overrides.py", "preconditions.py", "state_store.py", "world_builder.py")


def protocol_members() -> set[str]:
    """Return every member of `CoordinatorSurface`: its fields, methods and properties."""
    fields = set(CoordinatorSurface.__annotations__)
    methods = {
        name
        for name, value in vars(CoordinatorSurface).items()
        if not name.startswith("__") and (callable(value) or isinstance(value, property))
    }
    return fields | methods


def _is_self(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "self"


def self_attributes(tree: ast.AST) -> set[str]:
    """Return every name reached as `self.<name>` in this tree."""
    return {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and _is_self(node.value)
    }


def self_names_by_string(tree: ast.AST) -> set[str]:
    """Return every literal name in `getattr(self, …)` or `hasattr(self, …)`."""
    return {
        node.args[1].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"getattr", "hasattr"}
        and len(node.args) >= 2
        and _is_self(node.args[0])
        and isinstance(node.args[1], ast.Constant)
        and isinstance(node.args[1].value, str)
    }


def class_body_names(cls: ast.ClassDef) -> set[str]:
    """Return every name a class body defines: methods, assignments, annotations."""
    names: set[str] = set()
    for statement in cls.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(statement.name)
        elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            names.add(statement.target.id)
        elif isinstance(statement, ast.Assign):
            names |= {target.id for target in statement.targets if isinstance(target, ast.Name)}
    return names


def test_the_protocol_lists_what_the_mixins_use() -> None:
    """Every member is used by a mixin, and every mixin reaches only members or its own names."""
    members = protocol_members()
    used: set[str] = set()
    unlisted: list[str] = []
    for name in MIXIN_FILES:
        tree = ast.parse((PACKAGE / name).read_text(encoding="utf-8"))
        own = set().union(
            *(class_body_names(node) for node in tree.body if isinstance(node, ast.ClassDef))
        )
        reached = self_attributes(tree)
        used |= reached | self_names_by_string(tree)
        unlisted += [f"{name}: self.{attribute}" for attribute in sorted(reached - own - members)]
    unused = sorted(members - used)
    assert not unlisted, "een mixin gebruikt wat niet in CoordinatorSurface staat:\n" + "\n".join(
        unlisted
    )
    assert not unused, "CoordinatorSurface noemt wat geen mixin gebruikt: " + ", ".join(unused)


async def test_the_real_coordinator_carries_every_member_of_its_protocol() -> None:
    """A member the protocol promises but the coordinator never sets only fails at run time."""
    installation = {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("woonkamer_ketel", "climate.woonkamer")],
                indoor_sensor="sensor.woonkamer",
                heat=settings(21.0, 20.0),
            )
        ],
        "outdoor_sensor": "sensor.buiten",
    }
    states = {
        "sensor.woonkamer": ("21.0", {}),
        "sensor.buiten": ("4.0", {}),
        "climate.woonkamer": ("off", {"hvac_modes": ["heat", "off"]}),
    }
    live = await start_house(installation, states=states)
    try:
        missing = sorted(
            member for member in protocol_members() if not hasattr(live.coordinator, member)
        )
    finally:
        await stop_house(live)
    assert not missing, "de coördinator mist: " + ", ".join(missing)


def touched_members(method_name: str, members: set[str]) -> set[str]:
    """Return the protocol members a coordinator method reaches as `self.<member>`."""
    method = getattr(ClimateDirectorCoordinator, method_name)
    method = getattr(method, "fget", method)
    tree = ast.parse(textwrap.dedent(inspect.getsource(method)))
    return self_attributes(tree) & members


def carried_names(cls: ast.ClassDef) -> set[str]:
    """Return what a stand-in carries itself: its body plus every `self.<name> = …`."""
    names = class_body_names(cls)
    for node in ast.walk(cls):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = [node.target]
        else:
            continue
        names |= {
            target.attr
            for target in targets
            if isinstance(target, ast.Attribute) and _is_self(target.value)
        }
    return names


def borrowed_methods(cls: ast.ClassDef) -> list[str]:
    """Return what a class body borrows as `name = ClimateDirectorCoordinator.<method>`."""
    return [
        statement.value.attr
        for statement in cls.body
        if isinstance(statement, ast.Assign)
        and isinstance(statement.value, ast.Attribute)
        and isinstance(statement.value.value, ast.Name)
        and statement.value.value.id == "ClimateDirectorCoordinator"
    ]


def test_every_stand_in_carries_what_its_borrowed_methods_touch() -> None:
    """A stand-in missing a member fails only on the branch that reaches it; say it up front."""
    members = protocol_members()
    problems: list[str] = []
    stand_ins = 0
    for path in sorted(TESTS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for cls in (node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)):
            borrowed = borrowed_methods(cls)
            if not borrowed:
                continue
            stand_ins += 1
            needed = set().union(*(touched_members(name, members) for name in borrowed))
            missing = sorted(needed - carried_names(cls))
            if missing:
                where = f"{path.name}::{cls.name} (regel {cls.lineno})"
                problems.append(f"{where}: {', '.join(missing)}")
    assert stand_ins, "geen enkele stand-in gevonden; leest de toets nog de goede vorm?"
    assert not problems, "een stand-in mist een protocollid:\n" + "\n".join(problems)
