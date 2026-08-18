"""Tests voor modusfamilies.

Tests for mode families.
"""

from __future__ import annotations

import pytest

from custom_components.climate_director.engine.families import (
    MODE_AUTO,
    MODE_COOL,
    MODE_DRY,
    MODE_FAN_ONLY,
    MODE_HEAT,
    MODE_HEAT_COOL,
    MODE_OFF,
    ModeFamily,
    family_of,
    is_compatible,
    preferred_mode,
)


@pytest.mark.parametrize(
    ("mode", "family"),
    [
        (MODE_OFF, ModeFamily.NEUTRAL),
        (MODE_FAN_ONLY, ModeFamily.NEUTRAL),
        (MODE_HEAT, ModeFamily.HEAT),
        (MODE_COOL, ModeFamily.COOL),
        (MODE_DRY, ModeFamily.COOL),
        (MODE_HEAT_COOL, ModeFamily.AMBIGUOUS),
        (MODE_AUTO, ModeFamily.AMBIGUOUS),
    ],
)
def test_family_of(mode: str, family: ModeFamily) -> None:
    assert family_of(mode) is family


def test_dry_is_cooling_duty() -> None:
    """Drying runs the compressor in cooling duty, so it clashes with heating."""
    assert not is_compatible(MODE_DRY, ModeFamily.HEAT)
    assert is_compatible(MODE_DRY, ModeFamily.COOL)


def test_unknown_mode_is_ambiguous_not_neutral() -> None:
    """An unrecognised mode may well run the compressor; assume it does."""
    assert family_of("turbo_boost") is ModeFamily.AMBIGUOUS
    assert not is_compatible("turbo_boost", ModeFamily.HEAT)


def test_off_and_fan_only_are_always_allowed() -> None:
    for family in ModeFamily:
        assert is_compatible(MODE_OFF, family)
        assert is_compatible(MODE_FAN_ONLY, family)


def test_idle_circuit_accepts_any_concrete_duty() -> None:
    assert is_compatible(MODE_HEAT, ModeFamily.NEUTRAL)
    assert is_compatible(MODE_COOL, ModeFamily.NEUTRAL)


def test_idle_circuit_still_rejects_ambiguous_modes() -> None:
    """`heat_cool` picks its own duty, which a shared circuit cannot allow."""
    assert not is_compatible(MODE_HEAT_COOL, ModeFamily.NEUTRAL)


def test_preferred_mode_names_the_concrete_mode() -> None:
    """Hoe een unit stilstaat hangt af van het circuit en de reden, en wordt
    daarom in `decide.py` bepaald; `test_circuits.py` dekt dat met een echt
    circuit erbij.

    How a unit stands still depends on the circuit and the reason, so that is
    decided in `decide.py`; `test_circuits.py` covers it with a real circuit.
    """
    assert preferred_mode(ModeFamily.HEAT) == MODE_HEAT
    assert preferred_mode(ModeFamily.COOL) == MODE_COOL
    assert preferred_mode(ModeFamily.NEUTRAL) == MODE_OFF
