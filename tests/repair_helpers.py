"""Hulpjes voor de reparatiemeldingen: de bron lezen en de ids volgen.

Helpers for the repair notices: reading the source and following the ids."""

from __future__ import annotations

import ast
from pathlib import Path

from _ast_helpers import ISSUE_CALLS, ISSUE_MODULE, issue_call_names, issue_calls

PACKAGE = Path(__file__).resolve().parents[1] / "custom_components" / "climate_director"

ISSUE_ID_ARGUMENT = 2

ISSUE_ID_KEYWORD = "issue_id"


def _modules(root: Path = PACKAGE) -> list[Path]:
    """Elk Python-bestand van het pakket.

    Every Python file of the package.
    """
    return sorted(root.rglob("*.py"))


def _parse(root: Path = PACKAGE) -> list[tuple[Path, ast.Module]]:
    """De AST van elk pakketbestand, met het bestand erbij.

    The AST of every package file, with the file next to it.
    """
    return [(path, ast.parse(path.read_text(encoding="utf-8"))) for path in _modules(root)]


def _issue_id_argument(call: ast.Call) -> ast.expr | None:
    """Het issue-id-argument van een `async_create_issue`/`async_delete_issue`."""

    if len(call.args) > ISSUE_ID_ARGUMENT:
        return call.args[ISSUE_ID_ARGUMENT]
    for keyword in call.keywords:
        if keyword.arg == ISSUE_ID_KEYWORD:
            return keyword.value
    return None


def _string_constants(tree: ast.Module) -> set[str]:
    """Namen die op moduleniveau een letterlijke string krijgen.

    Alleen die zijn te volgen: een variabele binnen een functie kan van alles
    zijn.

    Names that get a literal string at module level. Only those can be followed:
    a variable inside a function can be anything.
    """
    names: set[str] = set()
    for node in tree.body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        if value is None:
            continue
        if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
            continue
        names.update(target.id for target in targets if isinstance(target, ast.Name))
    return names


def _issue_id_key(argument: ast.expr | None, constants: set[str]) -> str | None:
    """De sleutel waaronder een issue-id telt: het hulpje, de constante of de tekst.

    The key an issue id counts under: the helper, the constant or the literal. A
    call such as `_issue_id(entry_id)` and a module constant such as
    `UNWATCHED_ISSUE` both become a string; a literal string stays itself.
    Anything else is **not** an issue id we can follow, and the caller reports
    that instead of skipping it.
    """
    if isinstance(argument, ast.Call):
        func = argument.func
        if isinstance(func, ast.Attribute):
            return func.attr
        if isinstance(func, ast.Name):
            return func.id
        return None
    if isinstance(argument, ast.Name):
        return argument.id if argument.id in constants else None
    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
        return argument.value
    return None


def unfollowable_issue_ids(root: Path = PACKAGE) -> list[str]:
    """Elke issue-id die de bewaking niet kan volgen, met bestand en regelnummer.

    Every issue id the guard cannot follow, with file and line number.
    """
    offenders: list[str] = []
    for path, tree in _parse(root):
        constants = _string_constants(tree)
        names = issue_call_names(tree)
        for attribute in ISSUE_CALLS:
            for call in issue_calls(tree, attribute, names):
                argument = _issue_id_argument(call)
                if _issue_id_key(argument, constants) is not None:
                    continue
                shown = "<geen id>" if argument is None else ast.unparse(argument)
                offenders.append(f"{path.name}:{call.lineno}: {attribute}({shown})")
    return offenders


def _refuse_unfollowable(root: Path = PACKAGE) -> None:
    """Meld een onvolgbaar issue-id in plaats van het over te slaan.

    Report an unfollowable issue id instead of skipping it.
    """
    offenders = unfollowable_issue_ids(root)
    assert not offenders, (
        "deze issue-id's zijn geen hulpje, moduleconstante of letterlijke tekst, dus de "
        "bewaking kan ze niet volgen en die meldingen vallen stil uit de "
        "unload-controle: " + "; ".join(offenders)
    )


def _walk_functions(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Elke functie- en methodedefinitie in de boom, op elk niveau.

    Every function and method definition in the tree, at every level.
    """
    return [
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    ]


def _called_names(node: ast.AST) -> set[str]:
    """Elke naam die binnen `node` wordt aangeroepen.

    Every name called inside `node`.
    """
    names: set[str] = set()
    for call in ast.walk(node):
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        if isinstance(func, ast.Attribute):
            names.add(func.attr)
        elif isinstance(func, ast.Name):
            names.add(func.id)
    return names


def created_issue_origins(root: Path = PACKAGE) -> dict[str, str]:
    """Elke aangemaakte issue-id met de plek waar hij vandaan komt.

    Voor de melding van de uitlaadbewaking: zonder bestand en regelnummer moet
    wie een melding ziet die niet gewist wordt zelf gaan zoeken.

    Every created issue id with the place it comes from. For the unload guard's
    message: without file and line number, whoever sees a notice that is not
    cleared has to go looking themselves.
    """
    _refuse_unfollowable(root)
    found: dict[str, str] = {}
    for path, tree in _parse(root):
        constants = _string_constants(tree)
        names = issue_call_names(tree)
        for call in issue_calls(tree, "async_create_issue", names):
            key = _issue_id_key(_issue_id_argument(call), constants)
            if key is not None:
                found.setdefault(key, f"{path.name}:{call.lineno}")
    return found


def created_issue_ids(root: Path = PACKAGE) -> set[str]:
    """Elke issue-id waarop het pakket een melding aanmaakt.

    Every issue id on which the package raises a notice.
    """
    return set(created_issue_origins(root))


def deleted_ids_by_function(root: Path = PACKAGE) -> dict[str, set[str]]:
    """Per functie de issue-id's die hij met `async_delete_issue` opruimt.

    Per function the issue ids it clears with `async_delete_issue`.
    """
    _refuse_unfollowable(root)
    deleted: dict[str, set[str]] = {}
    for _path, tree in _parse(root):
        constants = _string_constants(tree)
        names = issue_call_names(tree)
        for function in _walk_functions(tree):
            for call in issue_calls(function, "async_delete_issue", names):
                key = _issue_id_key(_issue_id_argument(call), constants)
                if key is not None:
                    deleted.setdefault(function.name, set()).add(key)
    return deleted


def functions_called_by() -> dict[str, set[str]]:
    """Per functie de namen die hij aanroept.

    Per function the names it calls.
    """
    called: dict[str, set[str]] = {}
    for _path, tree in _parse():
        for function in _walk_functions(tree):
            called.setdefault(function.name, set()).update(_called_names(function))
    return called


def unload_reachable_functions() -> set[str]:
    """Elke functie die `async_unload_entry` bereikt, direct of via een andere.

    Every function `async_unload_entry` reaches, directly or through another.
    """
    called = functions_called_by()
    reachable: set[str] = set()
    queue = list(called.get("async_unload_entry", set()))
    while queue:
        name = queue.pop()
        if name in reachable or name not in called:
            continue
        reachable.add(name)
        queue.extend(called[name] - reachable)
    return reachable


def cleared_at_unload() -> set[str]:
    """Elke issue-id die een vanuit `async_unload_entry` bereikbare functie wist.

    Every issue id a function reachable from `async_unload_entry` clears.
    """
    deleted = deleted_ids_by_function()
    cleared: set[str] = set()
    for name in unload_reachable_functions():
        cleared |= deleted.get(name, set())
    return cleared


ISSUE_ALIAS = "ir"

ISSUE_PARENT = "homeassistant.helpers"


def _issue_aliases(tree: ast.Module) -> set[str]:
    """Elke naam die in dit bestand naar de issue-registry wijst.

    Every name in this file that points at the issue registry.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == ISSUE_PARENT:
            for alias in node.names:
                if alias.name == "issue_registry":
                    names.add(alias.asname or alias.name)
    return names


def issue_registry_form_problems(root: Path = PACKAGE) -> list[str]:
    """Elke schrijfwijze waarin de bewaking van hierboven een aanroep kan missen.

    Drie dingen zijn verboden, alle drie omdat ze de aanroep uit de vorm halen
    waarop `issue_calls` matcht:

    1. een andere import dan `from homeassistant.helpers import issue_registry as
       ir` — de functie rechtstreeks importeren (`from …issue_registry import
       async_create_issue`), de module onder een andere naam, of de module
       helemaal uitschrijven;
    2. `ir.async_create_issue` of `ir.async_delete_issue` ergens anders dan als
       het doel van een directe aanroep: aan een naam gegeven, in een
       `functools.partial` gestopt, als callback doorgegeven;
    3. dezelfde functie via `getattr(ir, "async_create_issue")` opgehaald.

    Elke andere vorm is te bewaken: `ir.async_create_issue(...)` en
    `ir.async_delete_issue(...)` staan letterlijk in de bron, en daar leest
    `issue_calls` ze. Een test die deze afspraak handhaaft laat de rand niet
    bestaan in plaats van hem te repareren.

    Every spelling in which the guard above can miss a call. Three things are
    forbidden, all three because they take the call out of the shape
    `issue_calls` matches: another import than `from homeassistant.helpers import
    issue_registry as ir`; `ir.async_create_issue` or `ir.async_delete_issue`
    anywhere other than as the target of a direct call; and the same function
    fetched through `getattr(ir, "async_create_issue")`. Every other shape can be
    guarded: the direct calls stand literally in the source, and that is where
    `issue_calls` reads them. A test enforcing this agreement makes the edge not
    exist instead of repairing it.
    """
    problems: list[str] = []
    for path, tree in _parse(root):
        parents = {
            child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)
        }
        aliases = _issue_aliases(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == ISSUE_MODULE:
                    problems.append(
                        f"{path.name}:{node.lineno}: `{ISSUE_MODULE}` wordt rechtstreeks "
                        f"geïmporteerd; alleen `from {ISSUE_PARENT} import issue_registry "
                        f"as {ISSUE_ALIAS}` is te bewaken"
                    )
                elif node.module == ISSUE_PARENT:
                    for alias in node.names:
                        if alias.name == "issue_registry" and alias.asname != ISSUE_ALIAS:
                            problems.append(
                                f"{path.name}:{node.lineno}: `issue_registry` wordt als "
                                f"`{alias.asname or alias.name}` geïmporteerd; alleen "
                                f"`as {ISSUE_ALIAS}` is te bewaken"
                            )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[-1] == "issue_registry":
                        problems.append(
                            f"{path.name}:{node.lineno}: `{alias.name}` wordt rechtstreeks "
                            f"geïmporteerd; alleen `from {ISSUE_PARENT} import issue_registry "
                            f"as {ISSUE_ALIAS}` is te bewaken"
                        )
            elif isinstance(node, ast.Attribute) and node.attr in ISSUE_CALLS:
                parent = parents.get(node)
                if isinstance(parent, ast.Call) and parent.func is node:
                    continue
                problems.append(
                    f"{path.name}:{node.lineno}: {ast.unparse(node)} wordt aan een naam "
                    f"gegeven of als argument doorgegeven; alleen een directe aanroep "
                    f"`{ISSUE_ALIAS}.{node.attr}(...)` is te bewaken"
                )
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "getattr"
                and len(node.args) >= 2
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id in aliases
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value in ISSUE_CALLS
            ):
                problems.append(
                    f"{path.name}:{node.lineno}: {ast.unparse(node)} haalt de aanroep via "
                    f"`getattr` op; alleen `{ISSUE_ALIAS}.{node.args[1].value}(...)` is te "
                    f"bewaken"
                )
    return problems
