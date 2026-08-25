"""Eenheidsomrekening tussen de engine (Celsius) en de gebruiker.

Unit conversion between the engine (Celsius) and the user.

De engine rekent overal in graden Celsius en blijft dat doen; Home Assistant
geeft temperaturen door in het eenhedenstelsel van de gebruiker. Deze module is
de enige plek waar de twee stelsels elkaar raken.

The engine works in degrees Celsius throughout and keeps doing so; Home
Assistant hands temperatures over in the user's unit system. This module is the
one place where the two systems meet.
"""

from __future__ import annotations

from homeassistant.const import UnitOfTemperature


def to_celsius(value: float | None, unit: str) -> float | None:
    """Return `value`, read in `unit`, as degrees Celsius.

    `None` passes through, and a metric reading is already Celsius.
    """
    if value is None or unit != UnitOfTemperature.FAHRENHEIT:
        return value
    return (value - 32.0) * 5.0 / 9.0


def from_celsius(value: float | None, unit: str) -> float | None:
    """Return a Celsius `value` in the user's `unit`."""
    if value is None or unit != UnitOfTemperature.FAHRENHEIT:
        return value
    return value * 9.0 / 5.0 + 32.0


def temperature_unit_of(hass: object) -> str:
    """Return the user's temperature unit, Celsius when it cannot be read.

    De applier en het formulier lezen dit van `hass.config.units`; een
    nagebouwde Home Assistant in de testset heeft dat veld niet altijd.

    The applier and the form read this off `hass.config.units`; a stand-in Home
    Assistant in the test set does not always carry that field.
    """
    config = getattr(hass, "config", None)
    units = getattr(config, "units", None)
    return getattr(units, "temperature_unit", UnitOfTemperature.CELSIUS)


def display_temperature(value: float | None, unit: str) -> str:
    """Return a rounded temperature with its unit, in the user's system.

    De reparatiemeldingen zijn voor de gebruiker, dus daar staat geen kale
    `°` en geen onafgeronde float. Fahrenheit telt zonder decimalen - een
    omgerekende 21 °C is 69,8 °F en dat leest niemand als 69.8.

    The repair notices are for the user, so they carry no bare `°` and no
    unrounded float. Fahrenheit counts without decimals - a converted 21 °C is
    69.8 °F and nobody reads that as 69.8.
    """
    if value is None:
        return "?"
    decimals = 0 if unit == UnitOfTemperature.FAHRENHEIT else 1
    return f"{round(value, decimals)} {unit}"


def delta_to_celsius(value: float | None, unit: str) -> float | None:
    """Return a temperature *difference* read in `unit` as degrees Celsius.

    Een verschil kent geen nulpunt, dus alleen de schaalfactor telt: 1,8 °F is
    precies 1 °C.

    A difference has no zero point, so only the scale factor counts: 1.8 °F is
    exactly 1 °C.
    """
    if value is None or unit != UnitOfTemperature.FAHRENHEIT:
        return value
    return value * 5.0 / 9.0


def delta_from_celsius(value: float | None, unit: str) -> float | None:
    """Return a Celsius temperature *difference* in the user's `unit`."""
    if value is None or unit != UnitOfTemperature.FAHRENHEIT:
        return value
    return value * 9.0 / 5.0
