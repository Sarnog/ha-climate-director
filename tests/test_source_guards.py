"""Elke bronbewaking noemt zelf wat zij dekt, en wat zij bewust laat liggen.

Een test die een tekstbestand leest, hoort in zijn moduledocstring te zeggen
welke eigenschap hij toetst en welke randen hij bewust niet raakt. Zonder die
regel is van buiten niet te zien of een groene toets iets bewijst of alleen de
toevallige stand van vandaag vastpint - en dat is precies de vorm waarin dit
project eerder is vastgelopen. Deze bewaking leest daarom, met `ast`, elk
`tests/test_*.py` dat een pad onder `docs/` of `translations/` leest, of
`README.md`, `ROADMAP.md`, `ARCHITECTURE.md` of `strings.json`, en eist dat de
moduledocstring van dat bestand *Dekking* én *Coverage* draagt.

De bronnen worden gevonden via de stringliteralen in `Path`-samenstellingen, in
`read_text`/`read_bytes`/`open`/`glob`/`rglob`/`load`/`loads`-aanroepen en in
een tabel op moduleniveau (een dict, tuple, lijst of set die aan een naam wordt
toegekend, met de vaste delen van een f-string erin): een bestand telt mee zodra
het zo'n pad noemt. De melding noemt elk bestand dat zijn
alinea mist, met het woord dat ontbreekt.

Dekking: elk `tests/test_*.py` dat een pad onder `docs/` of `translations/`
leest, of `README.md`, `ROADMAP.md`, `ARCHITECTURE.md` of `strings.json`, tegen
de eis dat zijn moduledocstring *Dekking* én *Coverage* draagt. Niet gedekt: of
die dekking klopt - dat leest de controleronde -, bestanden die alleen code,
workflows, opslagbestanden of blueprint-YAML lezen, en een pad dat pas tijdens
het draaien uit losse namen wordt samengesteld zonder dat een van de drie vormen
hierboven het noemt.

Coverage: every `tests/test_*.py` that reads a path under `docs/` or
`translations/`, or `README.md`, `ROADMAP.md`, `ARCHITECTURE.md` or
`strings.json`, against the demand that its module docstring carries *Dekking*
and *Coverage*. The sources are found through the string literals in `Path`
compositions, in read calls and in a table at module level (a dict, tuple, list
or set assigned to a name, with the fixed parts of an f-string in it). Not
covered: whether that coverage is correct - the control round reads it -, files
that only read code, workflows, storage files or blueprint YAML, and a path that
is only put together at run time from loose names without any of those three
shapes naming it.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

TESTS = Path(__file__).resolve().parent

#: De functies die een test gebruikt om een tekstbestand te lezen. Een
#: stringliteraal telt alleen mee wanneer hij in een van deze aanroepen of in een
#: `Path`-samenstelling staat, zodat een bestand dat een bron alleen in zijn
#: docstring noemt niet meetelt.
#:
#: The functions a test uses to read a text file. A string literal only counts
#: when it stands in one of these calls or in a `Path` composition, so a file that
#: merely mentions a source in its docstring does not count.
READ_FUNCS = frozenset(
    {"open", "read_text", "read_bytes", "glob", "rglob", "load", "loads", "joinpath", "with_name"}
)

#: De vier losse bronbestanden die geen map delen.
#:
#: The four standalone source files that share no directory.
NAMED_SOURCE = re.compile(r"(^|[/\\])(README|ROADMAP|ARCHITECTURE)\.md$|(^|[/\\])strings\.json$")


def guarded_literals(tree: ast.AST) -> set[str]:
    """De stringliteralen die een test als pad of leesdoel gebruikt.

    Elke kant van een `/`-deling en elk tekstargument van een leesaanroep telt
    mee. Zo vindt deze functie ook een pad dat met losse stukken is opgebouwd
    (`ROOT / "docs" / "install"`), zonder de docstring van het bestand te lezen.

    Every side of a `/` division and every text argument of a read call counts.
    That way this function also finds a path built from loose pieces
    (`ROOT / "docs" / "install"`) without reading the file's docstring.
    """
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            for side in (node.left, node.right):
                if isinstance(side, ast.Constant) and isinstance(side.value, str):
                    found.add(side.value)
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            else:
                name = ""
            if name in READ_FUNCS:
                arguments = [*node.args, *(keyword.value for keyword in node.keywords)]
                for argument in arguments:
                    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                        found.add(argument.value)
    return found | table_literals(tree)


def table_literals(tree: ast.AST) -> set[str]:
    """De stringliteralen in een tabel op moduleniveau.

    Een bewaking die haar bronnen in een dict of tuple opsomt en ze daarna via een
    variabele leest (`ROOT / name`), noemt het pad nergens in een leesaanroep. De
    tabel zelf noemt het wel: elke string in de waarde van een toekenning op
    moduleniveau aan een dict, tuple, lijst of set telt mee, ook de vaste delen van
    een f-string daarin (`f"docs/install/{language}.md"`).

    The string literals in a table at module level. A guard that lists its sources
    in a dict or tuple and then reads them through a variable (`ROOT / name`)
    names the path in no read call. The table itself does: every string in the
    value of a module-level assignment of a dict, tuple, list or set counts, the
    fixed parts of an f-string in it too.
    """
    found: set[str] = set()
    for statement in getattr(tree, "body", []):
        if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
            continue
        if not isinstance(statement.value, (ast.Dict, ast.Tuple, ast.List, ast.Set)):
            continue
        for node in ast.walk(statement.value):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                found.add(node.value)
    return found


def reads_a_guarded_source(literals: set[str]) -> bool:
    """Of deze literalen samen een van de bewaakte bronnen aanwijzen.

    Whether these literals together point at one of the guarded sources.
    """
    docs = any(literal.rstrip("/\\") == "docs" or "docs/install" in literal for literal in literals)
    install = any(literal == "install" for literal in literals)
    translations = any(
        literal.rstrip("/\\") == "translations" or literal.rstrip("/\\").endswith("/translations")
        for literal in literals
    )
    named = any(NAMED_SOURCE.search(literal) for literal in literals)
    return (docs and install) or translations or named


def files_without_coverage(root: Path = TESTS) -> list[tuple[str, str]]:
    """Per bronbewaking de ontbrekende woorden uit zijn moduledocstring.

    Per source guard the words missing from its module docstring.
    """
    missing: list[tuple[str, str]] = []
    for path in sorted(root.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if not reads_a_guarded_source(guarded_literals(tree)):
            continue
        docstring = ast.get_docstring(tree) or ""
        absent = [word for word in ("Dekking", "Coverage") if word not in docstring]
        if absent:
            missing.append((path.name, ", ".join(absent)))
    return missing


def test_every_source_guard_names_its_coverage() -> None:
    """Elke bronbewaking draagt *Dekking* én *Coverage* in zijn moduledocstring.

    De melding noemt elk bestand dat zijn alinea mist, met het woord erbij dat
    ontbreekt. De alinea's zelf worden hier niet beoordeeld: of de dekking juist
    is, leest de controleronde, en dat is bewust buiten deze toets gehouden.

    Every source guard carries *Dekking* and *Coverage* in its module docstring.
    The message names each file that lacks its paragraph, with the missing word.
    The paragraphs themselves are not judged here: whether the coverage is
    correct is read by the control round, and that is deliberately kept outside
    this guard.
    """
    missing = files_without_coverage()
    assert not missing, "deze bronbewakingen noemen hun dekking niet:\n" + "\n".join(
        f"{name}: {words} ontbreekt" for name, words in missing
    )
