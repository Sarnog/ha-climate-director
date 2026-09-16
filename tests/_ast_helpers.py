"""Gedeelde AST-hulpjes voor de bewakingen op de reparatiemeldingen.

Shared AST helpers for the guards on the repair notices.

Ronde 35 (R35-1): vier lezers in de testset liepen elk hun eigen AST af en
matchten alleen `ast.Attribute` — `ir.async_create_issue(...)`. Daarmee hing de
hele meldingsbewaking (het wissen bij het uitladen, de fixable-inventarisatie,
de gidsen-inventarisatie en de placeholder-controle) aan één schrijfwijze: een
kale naam na `from homeassistant.helpers.issue_registry import async_create_issue`
glipte er langs, en dat was gemeten (ronde 34: 2775 groen). Deze module is de
enige plek waar die match woont; de vier lezers gebruiken hem.

De eigenschap die hier vastligt: élke aanroep van `async_create_issue` of
`async_delete_issue` telt mee, hoe hij ook geïmporteerd of gespeld is — als
attribuut (`ir.async_create_issue`), als kale naam (`async_create_issue`) of
onder een `from … import … as x`-alias (`x(...)`). De attribuutkant blijft
bewust ruim: elke `iets.async_create_issue` telt, ook als de module niet in het
bestand gedefinieerd is — dat is precies wat de verzonnen pakketjes van de
bewakingen zelf doen (`ir.async_create_issue` zonder import ernaast).

Round 35 (R35-1): four readers in the suite each walked their own AST and
matched only `ast.Attribute` — `ir.async_create_issue(...)`. That hung the whole
notice guard (clearing on unload, the fixable inventory, the guide inventory and
the placeholder check) on one spelling: a bare name after
`from homeassistant.helpers.issue_registry import async_create_issue` slipped
past it, and that was measured (round 34: 2775 green). This module is the only
place that match lives; the four readers use it.

The property pinned here: every call of `async_create_issue` or
`async_delete_issue` counts, however it was imported or spelled — as an
attribute (`ir.async_create_issue`), as a bare name (`async_create_issue`) or
under a `from … import … as x` alias (`x(...)`). The attribute side stays
deliberately loose: any `something.async_create_issue` counts, even when the
module is not defined in the file — which is exactly what the guards' own
invented packages do (`ir.async_create_issue` with no import beside it).
"""

from __future__ import annotations

import ast

#: De twee functies van de issue-registry die een melding aanmaken of wissen.
#:
#: The issue registry's two functions that create or clear a notice.
ISSUE_CALLS = ("async_create_issue", "async_delete_issue")

#: Het modulepad waar die twee functies wonen.
#:
#: The module path where those two functions live.
ISSUE_MODULE = "homeassistant.helpers.issue_registry"


def issue_call_names(tree: ast.Module) -> dict[str, str]:
    """Kale namen die naar een meldingsfunctie wijzen, met hun echte naam.

    Leest de `import`-regels van het bestand: `from … import async_create_issue`
    levert `{"async_create_issue": "async_create_issue"}`, en
    `from … import async_create_issue as note` levert
    `{"note": "async_create_issue"}`. Alleen de twee functies van de
    issue-registry tellen; een gelijknamige naam uit een ander pakket niet.

    Bare names that point at a notice function, with their real name. Reads the
    file's `import` statements: `from … import async_create_issue` yields
    `{"async_create_issue": "async_create_issue"}`, and
    `from … import async_create_issue as note` yields
    `{"note": "async_create_issue"}`. Only the issue registry's two functions
    count; a like-named name from another package does not.
    """
    names: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module != ISSUE_MODULE:
            continue
        for alias in node.names:
            if alias.name in ISSUE_CALLS:
                names[alias.asname or alias.name] = alias.name
    return names


def issue_calls(
    node: ast.AST,
    attribute: str,
    names: dict[str, str] | None = None,
) -> list[ast.Call]:
    """Elke aanroep van `attribute`, hoe hij ook gespeld is.

    `names` is de uitkomst van `issue_call_names`; zonder die door te geven
    worden kale namen niet herkend (een functie- of klassenknoop bevat de
    importregels van het bestand niet). Geef bij een deelboom dus de namen van
    het omringende modulebestand mee.

    Every call of `attribute`, however it is spelled. `names` is the result of
    `issue_call_names`; without it bare names are not recognised (a function or
    class node does not carry the file's import statements). For a subtree, pass
    the surrounding module file's names.
    """
    if names is None:
        names = issue_call_names(node) if isinstance(node, ast.Module) else {}
    found: list[ast.Call] = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if isinstance(func, ast.Attribute):
            if func.attr == attribute:
                found.append(child)
        elif isinstance(func, ast.Name) and names.get(func.id) == attribute:
            found.append(child)
    return found
