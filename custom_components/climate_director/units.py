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


def rounded_from_celsius(value: float | None, unit: str) -> float | None:
    """Return a Celsius `value` in the user's `unit`, rounded to one decimal.

    De uitgaande kant - sensorattributen en het decision-event - rondt af op
    één decimaal, in beide stelsels, zodat drijvendekomma-ruis zoals 16,1 °C
    -> 60,980000000000004 °F de gebruiker nooit bereikt. De engine en de
    applier rekenen ongeafgerond verder; alleen de weergave rondt af.

    The outgoing side - sensor attributes and the decision event - rounds to
    one decimal in both systems, so floating-point noise like 16.1 °C ->
    60.980000000000004 °F never reaches the user. The engine and the applier
    keep computing unrounded; only the display rounds.
    """
    converted = from_celsius(value, unit)
    return None if converted is None else round(converted, 1)


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


def unit_of_coordinator(coordinator: object) -> str:
    """Return the unit this coordinator's Home Assistant reports in.

    De zes nagebouwde coordinators in de testset lenen losse methodes en kennen
    niet elk veld van de echte; wie hier rechtstreeks
    `coordinator.temperature_unit` leest breekt hen op afstand. Celsius is de
    veilige terugval.

    The six stand-in coordinators in the test set borrow individual methods and
    do not know every field of the real one; reading `coordinator.temperature_unit`
    directly here breaks them at a distance. Celsius is the safe fallback.
    """
    return getattr(coordinator, "temperature_unit", UnitOfTemperature.CELSIUS)


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


def rounded_delta_from_celsius(value: float | None, unit: str) -> float | None:
    """Return a Celsius temperature *difference* in the user's `unit`, rounded.

    Het formulier toont dode band en hysterese in de eenheid van de gebruiker;
    ook een verschil kan drijvendekomma-ruis dragen (0,1 °C is
    0,18000000000000002 °F) en past dan niet bij zijn eigen selectorstap.
    Alleen de weergave rondt af; de opslag gaat ongeafgerond door
    `delta_to_celsius`, anders kruipt de configuratie bij elke bewerking weg.

    The form shows dead band and hysteresis in the user's unit; a difference
    can carry floating-point noise too (0.1 °C is 0.18000000000000002 °F) and
    then does not fit its own selector step. Only the display rounds; storage
    passes unrounded through `delta_to_celsius`, otherwise the configuration
    creeps away on every edit.
    """
    converted = delta_from_celsius(value, unit)
    return None if converted is None else round(converted, 1)
