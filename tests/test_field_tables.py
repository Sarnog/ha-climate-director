"""Elk veld in een veldtabel wijst naar een plek die bestaat.

Every field in a field table points to a place that exists.

Een `target` in `engine/fields.py` is een puntpad naar de opgeslagen installatie
en naar de dataclass eronder. Een typefout in dat pad is **stil**: het formulier
leest niets, toont daarom de standaard, en `config_flow.py` schrijft die
standaard bij het eerstvolgende opslaan over de echte waarde heen. Gemeten in
ronde 24: `stuck_after` -> `stuk_after` liet de volledige suite groen (2508
passed) terwijl het scherm 15 minuten toonde in plaats van de opgeslagen 30.

A `target` in `engine/fields.py` is a dotted path into the stored installation
and into the dataclass underneath. A typo in that path is **silent**: the form
reads nothing, therefore shows the default, and `config_flow.py` writes that
default over the real value on the next save. Measured in round 24:
`stuck_after` -> `stuk_after` left the whole suite green (2508 passed) while the
screen showed 15 minutes instead of the stored 30.

Deze bewaking loopt over **élke** veldtabel in `engine/fields.py` — ze worden
gevonden, niet opgesomd — zodat een derde tabel vanzelf meedoet. Welk model bij
welke tabel hoort staat in `fields.TABLE_ROOTS`; ontbreekt daar een regel, dan
is dát de fout, want anders zou een nieuwe tabel stilzwijgend buiten de bewaking
vallen.

This guard walks **every** field table in `engine/fields.py` — they are
discovered, not listed — so a third table joins in by itself. Which model
belongs to which table lives in `fields.TABLE_ROOTS`; a missing row there is
itself the failure, since a new table would otherwise quietly fall outside the
guard.

Er wordt getoetst op het **bestaan van de sleutel**, niet op "de waarde is niet
None". Een leeg optioneel veld — een lege buitensensor, een gastenvenster zonder
dagen — is een geldige waarde en mag deze bewaking niet rood maken.

The test is on the **existence of the key**, not on "the value is not None". An
empty optional field — a blank outdoor sensor, a guest window without days — is
a valid value and must not make this guard red.
"""

from __future__ import annotations

import dataclasses
import enum
from datetime import time, timedelta
from typing import Any, Union, get_args, get_origin, get_type_hints

import pytest

from custom_components.climate_director.engine import fields as engine_fields
from custom_components.climate_director.engine import models as engine_models
from custom_components.climate_director.engine import serialise as engine_serialise
from custom_components.climate_director.engine.fields import FieldSpec

_SKIP = object()


def field_tables() -> list[tuple[str, tuple[FieldSpec, ...]]]:
    """Return every field table in `engine/fields.py`, found rather than listed."""
    found = []
    for name, value in vars(engine_fields).items():
        if not isinstance(value, tuple) or not value:
            continue
        if all(isinstance(item, FieldSpec) for item in value):
            found.append((name, value))
    return sorted(found)


TABLES = field_tables()
TABLE_IDS = [name for name, _ in TABLES]


def _unwrap(annotation: Any) -> Any:
    """Return `X` for `X | None`, and the annotation itself otherwise."""
    if get_origin(annotation) is Union or type(annotation).__name__ == "UnionType":
        parts = [part for part in get_args(annotation) if part is not type(None)]
        if len(parts) == 1:
            return parts[0]
    return annotation


def _placeholder(annotation: Any) -> Any:
    """Return a stand-in value for one dataclass field, or `_SKIP`.

    Genoeg om een model te bouwen waarin élk optioneel onderdeel gevuld is,
    zodat de opgeslagen dict ook de bladeren onder een optioneel venster draagt.
    Containers houden hun eigen standaard: daar lopen geen `target`-paden
    doorheen.

    Enough to build a model in which every optional part is filled, so the
    stored dict carries the leaves under an optional window too. Containers keep
    their own default: no `target` path runs through them.
    """
    annotation = _unwrap(annotation)
    if get_origin(annotation) in (tuple, list, set, frozenset, dict):
        return _SKIP
    if isinstance(annotation, type):
        if dataclasses.is_dataclass(annotation):
            return build_sample(annotation)
        if issubclass(annotation, enum.Enum):
            return next(iter(annotation))
        if annotation is bool:
            return False
        if annotation is int:
            return 0
        if annotation is float:
            return 0.0
        if annotation is str:
            return ""
        if annotation is time:
            return time(0, 0)
        if annotation is timedelta:
            return timedelta(0)
    return _SKIP


def build_sample(model: type) -> Any:
    """Return an instance of `model` with every optional part filled in."""
    hints = get_type_hints(model)
    kwargs: dict[str, Any] = {}
    for field in dataclasses.fields(model):
        value = _placeholder(hints[field.name])
        if value is not _SKIP:
            kwargs[field.name] = value
    return model(**kwargs)


def dataclass_path_exists(model: type, path: str) -> bool:
    """Return whether a dotted path names real attributes, type by type."""
    current: Any = model
    for part in path.split("."):
        if not (isinstance(current, type) and dataclasses.is_dataclass(current)):
            return False
        hints = get_type_hints(current)
        if part not in hints:
            return False
        current = _unwrap(hints[part])
    return True


def stored_path_exists(stored: Any, path: str) -> bool:
    """Return whether a dotted path names keys that are present in stored data."""
    current: Any = stored
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return True


@pytest.mark.parametrize(("name", "table"), TABLES, ids=TABLE_IDS)
class TestEveryTargetPointsSomewhere:
    """Elke tabelrij wijst naar de opslag én naar de dataclass eronder."""

    def test_the_table_names_its_model(self, name: str, table: tuple[FieldSpec, ...]) -> None:
        """A table without a row in `TABLE_ROOTS` would fall outside this guard."""
        assert name in engine_fields.TABLE_ROOTS, (
            f"veldtabel {name} staat niet in fields.TABLE_ROOTS, "
            "dus zijn targets worden nergens getoetst"
        )

    def test_every_target_exists_on_the_dataclass(
        self, name: str, table: tuple[FieldSpec, ...]
    ) -> None:
        model_name, _ = engine_fields.TABLE_ROOTS[name]
        model = getattr(engine_models, model_name)
        missing = [
            f"{field.key} -> {field.target}"
            for field in table
            if field.target and not dataclass_path_exists(model, field.target)
        ]
        assert not missing, f"{name}: geen attribuut op {model_name} voor {missing}"

    def test_every_target_exists_in_the_stored_installation(
        self, name: str, table: tuple[FieldSpec, ...]
    ) -> None:
        model_name, writer_name = engine_fields.TABLE_ROOTS[name]
        model = getattr(engine_models, model_name)
        writer = getattr(engine_serialise, writer_name)
        stored = writer(build_sample(model))
        missing = [
            f"{field.key} -> {field.target}"
            for field in table
            if field.target and not stored_path_exists(stored, field.target)
        ]
        assert not missing, f"{name}: geen sleutel in de opgeslagen data voor {missing}"


def test_the_sweep_finds_the_tables_at_all() -> None:
    """Guards the reader: an empty sweep would pass everything above."""
    assert sorted(engine_fields.TABLE_ROOTS) == TABLE_IDS
