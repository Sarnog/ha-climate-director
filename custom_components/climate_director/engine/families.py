"""Modusfamilies: welke HVAC-standen claimen hetzelfde koelcircuit.

Mode families: which HVAC modes claim the same refrigerant circuit.

Een conflict op een multi-split ontstaat niet tussen `hvac_mode`s maar tussen
*compressorbedrijven*. Ontvochtigen (`dry`) is koelbedrijf en botst dus met
verwarmen; ventileren (`fan_only`) gebruikt de compressor niet en mag altijd.

A conflict on a multi-split does not arise between `hvac_mode`s but between
*compressor duties*. Drying (`dry`) is cooling duty and therefore clashes with
heating; fan-only does not use the compressor and is always allowed.
"""

from __future__ import annotations

from enum import StrEnum

# HVAC-standen als platte strings, zodat deze module - en daarmee de hele
# engine - los van Home Assistant te importeren en te testen is. De waarden
# komen exact overeen met homeassistant.components.climate.HVACMode.
#
# HVAC modes as plain strings, so this module - and with it the whole engine -
# can be imported and tested without Home Assistant. The values match
# homeassistant.components.climate.HVACMode exactly.
MODE_OFF = "off"
MODE_HEAT = "heat"
MODE_COOL = "cool"
MODE_DRY = "dry"
MODE_FAN_ONLY = "fan_only"
MODE_HEAT_COOL = "heat_cool"
MODE_AUTO = "auto"


class ModeFamily(StrEnum):
    """Compressor duty a mode claims on its refrigerant circuit."""

    NEUTRAL = "neutral"
    """No compressor claim: `off` and `fan_only`. Always allowed."""

    HEAT = "heat"
    """Heating duty: `heat`."""

    COOL = "cool"
    """Cooling duty: `cool` and `dry`."""

    AMBIGUOUS = "ambiguous"
    """The unit picks its own duty: `heat_cool` and `auto`.

    Unusable on a circuit that cannot do both at once, because the unit may
    switch duty on its own and knock another zone off its circuit. The engine
    resolves these into a concrete family before applying constraints.
    """


_FAMILY_BY_MODE: dict[str, ModeFamily] = {
    MODE_OFF: ModeFamily.NEUTRAL,
    MODE_FAN_ONLY: ModeFamily.NEUTRAL,
    MODE_HEAT: ModeFamily.HEAT,
    MODE_COOL: ModeFamily.COOL,
    MODE_DRY: ModeFamily.COOL,
    MODE_HEAT_COOL: ModeFamily.AMBIGUOUS,
    MODE_AUTO: ModeFamily.AMBIGUOUS,
}

#: Duties that actually claim the compressor, in the order the engine reports
#: them. `NEUTRAL` and `AMBIGUOUS` are deliberately absent.
ACTIVE_FAMILIES: tuple[ModeFamily, ...] = (ModeFamily.HEAT, ModeFamily.COOL)


def family_of(mode: str) -> ModeFamily:
    """Return the compressor duty `mode` claims.

    Unknown modes count as `AMBIGUOUS` rather than `NEUTRAL`: a mode this
    engine does not recognise may well run the compressor, and treating it as
    harmless is the more damaging way to be wrong.
    """
    return _FAMILY_BY_MODE.get(mode, ModeFamily.AMBIGUOUS)


def is_compatible(mode: str, family: ModeFamily) -> bool:
    """Return whether `mode` may run while its circuit is in `family`.

    A unit may always be `off` or `fan_only`. Beyond that it must match the
    circuit's active duty. While the circuit is idle (`NEUTRAL`) any concrete
    duty is free to start.
    """
    mode_family = family_of(mode)
    if mode_family is ModeFamily.NEUTRAL:
        return True
    if family is ModeFamily.NEUTRAL:
        return mode_family is not ModeFamily.AMBIGUOUS
    return mode_family is family


def idle_mode(allow_fan_only: bool) -> str:
    """Return the mode a unit takes when it may not run its own duty."""
    return MODE_FAN_ONLY if allow_fan_only else MODE_OFF


def preferred_mode(family: ModeFamily) -> str:
    """Return the concrete mode the engine commands for an active duty."""
    if family is ModeFamily.HEAT:
        return MODE_HEAT
    if family is ModeFamily.COOL:
        return MODE_COOL
    return MODE_OFF
