"""Kleine, bereikbare takken van de opslag en de veldtabel.

Small, reachable branches of storage and the field table."""

from __future__ import annotations

import pytest

from custom_components.climate_director.engine import serialise, table_storage
from custom_components.climate_director.engine.fields import FieldSpec
from custom_components.climate_director.schema_fields import _summer_months


def test_an_optional_type_is_unwrapped() -> None:
    """`X | None` leest als `X`; een gewoon type blijft zichzelf."""
    assert table_storage._unwrap(int | None) is int
    assert table_storage._unwrap(int) is int


def test_a_number_without_a_known_unit_reads_as_a_float() -> None:
    """Een getalveld met een onbekende maat leest als gewoon getal."""
    field = FieldSpec(key="x", kind="number", unit="onbekend", default=0.0)
    assert table_storage.parse_leaf(field, 3.5) == 3.5


def test_an_unknown_field_type_is_refused() -> None:
    """Een veldtype dat de tabel niet kent is een fout in de tabel, geen datafout."""
    field = FieldSpec(key="x", kind="onbekend")
    with pytest.raises(AssertionError, match="onbekend veldtype"):
        table_storage.parse_leaf(field, 1)
    with pytest.raises(AssertionError, match="onbekend veldtype"):
        table_storage.write_leaf(field, 1)


def test_a_broken_stored_month_list_falls_back_on_the_default() -> None:
    """Een bewaarde zomermaandenlijst met onbruikbare waarden telt als geen lijst."""
    assert _summer_months("north", ["geen getal"]) == _summer_months("north", [])


def test_a_guest_window_without_a_start_is_dropped() -> None:
    """Een gastenvenster zonder begin- of eindtijd bestaat niet."""
    assert serialise._guest_window({}) is None
    assert serialise._guest_window({"start": "09:00:00"}) is None
