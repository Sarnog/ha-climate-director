"""De opslagkant van een veldtabel, aan de kant van de engine.

The storage side of a field table, on the engine's side.

`engine/fields.py` zegt wélke velden een scherm draagt en waar ze in de
opgeslagen installatie staan; deze module vertaalt dat in beide richtingen. Eén
rij wordt één blad (`parse_leaf` / `write_leaf`), en een puntpad
(`outdoor.minimum`) wordt de geneste dataclass eronder (`values_from` /
`dict_from`). Zonder deze wandeling zou elke tabelrij alsnog een eigen regel in
`engine/serialise.py` kosten, en dan is de ketting niet korter geworden.

`engine/fields.py` says which fields a screen carries and where they live in the
stored installation; this module translates that both ways. One row becomes one
leaf (`parse_leaf` / `write_leaf`), and a dotted path (`outdoor.minimum`)
becomes the nested dataclass underneath (`values_from` / `dict_from`). Without
this walk every table row would still cost a line of its own in
`engine/serialise.py`, and then the chain has not become shorter.

Het lezen is net zo vergevingsgezind als de rest van `serialise.py`: de helpers
uit `storage_helpers.py` doen dat werk, en deze module kiest alleen wélke helper
bij welk veldtype hoort. Home Assistant komt hier niet voor — de tabel bevat
geen selectors en deze module geen enkele import erbuiten.

Reading is as forgiving as the rest of `serialise.py`: the helpers in
`storage_helpers.py` do that work, and this module only chooses which helper
belongs to which field kind. Home Assistant does not appear here — the table
holds no selectors and this module no import outside the engine.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import time
from typing import Any, Union, get_args, get_origin, get_type_hints

from .fields import FieldSpec
from .storage_helpers import (
    _bool,
    _enum,
    _float,
    _int,
    _optional_float,
    _seconds,
    _strings,
    _text,
    _time,
    _weekdays,
)


def _unwrap(annotation: Any) -> Any:
    """Return `X` for `X | None`, and the annotation itself otherwise."""
    if get_origin(annotation) is Union or type(annotation).__name__ == "UnionType":
        parts = [part for part in get_args(annotation) if part is not type(None)]
        if len(parts) == 1:
            return parts[0]
    return annotation


def parse_leaf(field: FieldSpec, stored: Any, annotation: Any = None) -> Any:
    """Return one table field as the value its dataclass expects.

    De vergevingsgezindheid zit in de bestaande helpers, niet hier. Voor een
    keuzeveld is `annotation` het enum-type waar de opgeslagen waarde bij hoort;
    dat komt uit de dataclass en niet uit de tabel, zodat er geen tweede kopie
    van dat type in de tabel hoeft te staan.

    The forgivingness sits in the existing helpers, not here. For a choice field
    `annotation` is the enum type the stored value belongs to; that comes from
    the dataclass rather than from the table, so no second copy of that type has
    to sit in the table.
    """
    if field.kind == "bool":
        return _bool(stored, field.default)
    if field.kind in ("text", "entity"):
        return tuple(_strings(stored)) if field.multiple else _text(stored)
    if field.kind == "zones":
        # Een lijst zone-id's. Leeg is hier een echte waarde: "alleen de eigen
        # zone". / A list of zone ids. Empty is a real value here: "this zone
        # only".
        return tuple(_strings(stored))
    if field.kind == "choice":
        enum_type = _unwrap(annotation)
        return _enum(enum_type, stored, enum_type(field.default))
    if field.kind == "time":
        return _time(stored, time(0, 0))
    if field.kind == "weekdays":
        return _weekdays(stored)
    if field.kind == "number":
        if field.unit in ("minutes", "minutes_or_off"):
            return _seconds(stored, field.default)
        if field.unit == "temperature":
            return _optional_float(stored)
        if field.unit == "rank":
            return _int(stored, field.default)
        if field.unit == "seconds":
            # Leeg betekent "geen eigen rem", en dat is iets anders dan nul.
            # Empty means "no brake of its own", which is not the same as zero.
            return None if stored in (None, "") else _seconds(stored)
        return _float(stored, field.default)
    raise AssertionError(f"onbekend veldtype {field.kind!r} voor {field.key}")


def write_leaf(field: FieldSpec, value: Any) -> Any:
    """Return one dataclass value as the plain data the entry stores."""
    if field.kind == "bool":
        return value
    if field.kind in ("text", "entity"):
        return list(value) if field.multiple else value
    if field.kind == "zones":
        return list(value)
    if field.kind == "choice":
        return value.value
    if field.kind == "time":
        return value.isoformat()
    if field.kind == "weekdays":
        return None if value is None else sorted(value)
    if field.kind == "number":
        if field.unit in ("minutes", "minutes_or_off"):
            return int(value.total_seconds())
        if field.unit == "seconds":
            return None if value is None else value.total_seconds()
        return value
    raise AssertionError(f"onbekend veldtype {field.kind!r} voor {field.key}")


def _split(
    fields: tuple[FieldSpec, ...],
) -> tuple[dict[str, FieldSpec], dict[str, list[FieldSpec]]]:
    """Split a table into its own leaves and the tables one level deeper."""
    leaves: dict[str, FieldSpec] = {}
    branches: dict[str, list[FieldSpec]] = {}
    for field in fields:
        assert field.target is not None, f"veld {field.key} heeft geen doel in de installatie"
        head, _, rest = field.target.partition(".")
        if rest:
            branches.setdefault(head, []).append(replace(field, target=rest))
        else:
            leaves[head] = field
    return leaves, branches


def values_from(fields: tuple[FieldSpec, ...], raw: Any, model: type) -> dict[str, Any]:
    """Return the keyword arguments `model` needs, read from stored data.

    Een puntpad wordt de geneste dataclass eronder: `outdoor.minimum` en
    `outdoor.maximum` worden samen één `OutdoorWindow`. Welk type dat is komt uit
    de dataclass zelf, dus de tabel hoeft alleen het pad te kennen.

    A dotted path becomes the nested dataclass underneath: `outdoor.minimum` and
    `outdoor.maximum` together become one `OutdoorWindow`. Which type that is
    comes from the dataclass itself, so the table only has to know the path.
    """
    hints = get_type_hints(model)
    leaves, branches = _split(fields)
    source = raw if isinstance(raw, Mapping) else {}
    values: dict[str, Any] = {
        name: parse_leaf(field, source.get(name), hints.get(name)) for name, field in leaves.items()
    }
    for name, nested in branches.items():
        nested_model = _unwrap(hints[name])
        values[name] = nested_model(**values_from(tuple(nested), source.get(name), nested_model))
    return values


def dict_from(fields: tuple[FieldSpec, ...], instance: Any) -> dict[str, Any]:
    """Return the stored data a table describes, read off a dataclass."""
    leaves, branches = _split(fields)
    stored: dict[str, Any] = {
        name: write_leaf(field, getattr(instance, name)) for name, field in leaves.items()
    }
    for name, nested in branches.items():
        stored[name] = dict_from(tuple(nested), getattr(instance, name))
    return stored
