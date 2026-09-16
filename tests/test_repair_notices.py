"""Elke reparatiemelding verdwijnt bij het uitladen van de installatie.

Every repair notice disappears when the installation unloads.

R30-2: `problems.async_clear_bypassed_openings` bestond wel maar werd nergens
aangeroepen. Zes van de zeven per-installatie meldingen werden bij het uitladen
opgeruimd, deze niet - een overbruggingsmelding bleef dus staan nadat de entry
weg was. De functie ernaast was dode code die precies dat gat markeerde.

De vorige bewaking hing aan de **naam** van de fabriek (`async_report_*` in
`problems.py`). Gemeten in ronde 31: een melding die je onder een andere naam
opzet (`async_note_probe`, of dezelfde aanroep in `state_store.py`) glipte er
langs - de unload-bewaking bleef groen. Daarom loopt deze test nu met een AST
over **álle** `ir.async_create_issue`-aanroepen in het hele pakket, haalt het
issue-id-hulpje eruit (`_issue_id(entry_id)`, of een moduleconstante zoals
`UNWATCHED_ISSUE`), en eist dat `async_unload_entry` - direct of via een functie
die het aanroept - een `ir.async_delete_issue` op **datzelfde** hulpje bereikt.
Zo hangt de bewaking aan de eigenschap en niet aan hoe een melding heet of in
welk bestand hij woont.

Ronde 32 (R32-6) dichtte het laatste gat: een id dat de bewaking niet kán volgen
- een f-string, een samenvoeging, een variabele - werd **stil overgeslagen**, en
zo'n melding viel dus zonder één woord uit de controle. Dat is nu een fout met
bestand en regelnummer (`_refuse_unfollowable`), dezelfde regel als ronde 19 voor
een berekende `translation_key`. Volgbaar is: een hulpje (`_issue_id(entry_id)`),
een moduleconstante die op moduleniveau een letterlijke string krijgt
(`UNWATCHED_ISSUE`), of een letterlijke string. Al het andere meldt zich.

`UNWATCHED_ISSUE` is de bewuste uitzondering: dat is één melding voor de hele
integratie in plaats van één per installatie, dus hij gaat pas weg als de laatste
installatie verdwijnt (`async_clear_watchers`, en die is wel vanuit
`async_unload_entry` bereikbaar). De bewaking eist daarom ook van die melding dat
er een bereikbare delete is, maar niet dat hij bij élke unload verdwijnt.

R30-2: `problems.async_clear_bypassed_openings` existed but was never called.
Six of the seven per-installation notices were cleaned up on unload, this one
was not - so a bypass notice stayed behind after the entry was gone. The
function next to it was dead code marking exactly that gap.

The previous guard hung on the **name** of the factory (`async_report_*` in
`problems.py`). Measured in round 31: a notice set up under another name
(`async_note_probe`, or the same call in `state_store.py`) slipped past it - the
unload guard stayed green. This test therefore walks **every**
`ir.async_create_issue` call in the whole package with an AST, pulls the issue-id
helper out of it (`_issue_id(entry_id)`, or a module constant such as
`UNWATCHED_ISSUE`), and demands that `async_unload_entry` - directly or through a
function it calls - reaches an `ir.async_delete_issue` on **that same** helper.
That way the guard hangs on the property, not on what a notice is called or which
file it lives in.

Round 32 (R32-6) closed the last gap: an id the guard **cannot** follow - an
f-string, a concatenation, a variable - was **silently skipped**, so such a
notice dropped out of the check without a word. That is now an error with file
and line number (`_refuse_unfollowable`), the same rule as round 19 for a
computed `translation_key`. Followable is: a helper (`_issue_id(entry_id)`), a
module constant that gets a literal string at module level (`UNWATCHED_ISSUE`),
or a literal string. Anything else reports itself.

`UNWATCHED_ISSUE` is the deliberate exception: it is one notice for the whole
integration rather than one per installation, so it only goes when the last
installation does (`async_clear_watchers`, which is reachable from
`async_unload_entry`). The guard therefore demands a reachable delete for it too,
but not that it disappears on every unload.

Ronde 35 (R35-1): de match zelf woont nu in `tests/_ast_helpers.py`. Vier lezers
in de testset gebruiken daar dezelfde definitie — attribuut én kale naam, met
opgeloste import-aliassen — in plaats van vier keer hun eigen
`ast.Attribute`-variant.

Round 35 (R35-1): the match itself now lives in `tests/_ast_helpers.py`. Four
readers in the suite use the same definition there — attribute and bare name,
with resolved import aliases — instead of four of their own `ast.Attribute`
variants.
"""

from __future__ import annotations

import ast
from pathlib import Path

from _ast_helpers import ISSUE_CALLS, issue_call_names, issue_calls

PACKAGE = Path(__file__).resolve().parents[1] / "custom_components" / "climate_director"

#: De twee naamvarianten waarmee een issue-id kan worden doorgegeven: als derde
#: positie (zoals overal in dit project) of als trefwoordargument.
#:
#: The two spellings an issue id can arrive in: as the third position (as
#: everywhere in this project) or as a keyword argument.
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
    """Meld een onvolgbaar issue-id in plaats van het over te slaan (R32-6).

    Report an unfollowable issue id instead of skipping it (R32-6).
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


def test_every_created_notice_is_cleared_when_the_entry_unloads() -> None:
    """Bij het uitladen verdwijnt élke melding van deze installatie.

    On unload every notice of this installation disappears.
    """
    created = created_issue_ids()
    cleared = cleared_at_unload()

    assert created, "geen enkele `async_create_issue` gevonden; de AST leest het verkeerde pakket"
    assert "async_unload_entry" in functions_called_by(), (
        "`async_unload_entry` niet gevonden; de AST leest `__init__.py` niet"
    )

    missing = sorted(created - cleared)
    origins = created_issue_origins()
    detail = ", ".join(f"{name} ({origins.get(name, '?')})" for name in missing)
    assert not missing, (
        "deze meldingen worden aangemaakt maar op het uitlaadpad van "
        "`async_unload_entry` niet meer gewist, dus ze overleven het uitladen: " + detail
    )


def test_the_guard_reads_the_real_source() -> None:
    """De bewaking hangt aan de bron en niet aan een lijst hier.

    The guard hangs on the source, not on a list here.
    """
    created = created_issue_ids()
    cleared = cleared_at_unload()

    # De meldingen van vandaag, in beide vormen: een hulpje per installatie en
    # de ene constante voor de hele integratie.
    #
    # Today's notices, in both forms: a per-installation helper and the single
    # whole-integration constant.
    assert "_bypassed_opening_issue_id" in created
    assert "UNWATCHED_ISSUE" in created

    # Elk gevonden hulpje wordt op het uitlaadpad ook werkelijk gewist.
    #
    # Every helper found is really cleared on the unload path.
    assert created <= cleared


def test_every_issue_id_can_be_followed() -> None:
    """Elke melding heeft een id dat de bewaking kan volgen (ronde 32, R32-6).

    Een id dat ze niet kan volgen werd tot ronde 32 **stil overgeslagen**, en dan
    valt zo'n melding zonder één woord uit de unload-controle. Deze test is de
    expliciete kant daarvan; de twee verzamelfuncties weigeren zo'n id ook zelf.

    Every notice has an id the guard can follow (round 32, R32-6). Until round 32
    an id it could not follow was **silently skipped**, and then such a notice
    dropped out of the unload check without a word. This test is the explicit
    side of that; the two collector functions refuse such an id themselves too.
    """
    offenders = unfollowable_issue_ids()
    assert not offenders, (
        "deze meldingen gebruiken een issue-id dat de bewaking niet kan volgen en "
        "vallen dus stil buiten de unload-controle: " + "; ".join(offenders)
    )
