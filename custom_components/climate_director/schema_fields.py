"""Selectors en de veldtabel-vertaling voor de formulieren.

Selectors and the field-table translation for the forms.

De bouwstenen die `schemas.py` voor élk scherm gebruikt, plus de functie die
een declaratieve veldtabel uit `engine/fields.py` omzet naar een `vol.Schema`.
De veldtabel zelf woont in `engine/` en bevat geen selectors; die vertaling
staat hier, in de Home Assistant-helft van het pakket.

The building blocks `schemas.py` uses for every screen, plus the function that
turns a declarative field table from `engine/fields.py` into a `vol.Schema`.
The field table itself lives in `engine/` and contains no selectors; that
translation lives here, in the Home Assistant half of the package.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers import selector

from . import texts
from .const import CONF_SHADOW_MODE, DEFAULT_SHADOW_MODE
from .engine.fields import FieldSpec
from .engine.models import PrecipitationSettings, SeasonSettings
from .units import rounded_delta_from_celsius, temperature_unit_of

#: Zomermaanden per halfrond, als maandnummers 1-12. De engine telt
#: april-september als zomer; wie op het zuidelijk halfrond woont, krijgt
#: oktober-maart. De noordelijke standaard komt uit de engine, zodat hij hier
#: niet stilletjes uit de pas kan lopen.
#:
#: Summer months per hemisphere, as month numbers 1-12. The engine counts
#: April-September as summer; the southern hemisphere gets October-March. The
#: northern default comes from the engine, so it cannot drift apart here.
_SUMMER_NORTH = SeasonSettings().summer_months
_SUMMER_SOUTH = frozenset({1, 2, 3, 10, 11, 12})


def _hemisphere(months: Any) -> str:
    """Return which hemisphere a stored summer-months set describes.

    Alles wat niet precies het zuidelijke rijtje is, telt als noordelijk. Dat is
    de veilige kant: een handmatig bewerkte of half geschreven waarde valt
    terug op de standaard in plaats van de wizard te laten struikelen.

    Anything that is not exactly the southern row counts as northern. That is
    the safe side: a hand-edited or half-written value falls back on the
    default rather than tripping the wizard up.
    """
    try:
        return "south" if frozenset(int(month) for month in months) == _SUMMER_SOUTH else "north"
    except (TypeError, ValueError):
        return "north"


def _temperature(unit: str) -> selector.NumberSelector:
    """Return a temperature selector in the user's unit.

    De engine bewaart alles in graden Celsius; het formulier toont de eenheid
    van Home Assistant. In Fahrenheit is hetzelfde zinnige bereik -20..40 °C
    precies -4..104 °F.

    The engine stores everything in degrees Celsius; the form shows Home
    Assistant's unit. In Fahrenheit the same sensible -20..40 °C range is
    exactly -4..104 °F.
    """
    if unit == UnitOfTemperature.FAHRENHEIT:
        return selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=-4,
                max=104,
                step=1,
                unit_of_measurement="°F",
                mode=selector.NumberSelectorMode.BOX,
            )
        )
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=-20,
            max=40,
            step=0.5,
            unit_of_measurement="°C",
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _band(unit: str) -> selector.NumberSelector:
    """Return a temperature-band selector in the user's unit.

    Een band is een verschil, dus in Fahrenheit telt alleen de schaalfactor:
    0..10 °C is 0..18 °F.

    A band is a difference, so in Fahrenheit only the scale factor counts:
    0..10 °C is 0..18 °F.
    """
    if unit == UnitOfTemperature.FAHRENHEIT:
        return selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0,
                max=18,
                step=0.2,
                unit_of_measurement="°F",
                mode=selector.NumberSelectorMode.BOX,
            )
        )
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0,
            max=10,
            step=0.1,
            unit_of_measurement="°C",
            mode=selector.NumberSelectorMode.BOX,
        )
    )


_MINUTES_OR_OFF = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=0, max=240, step=1, unit_of_measurement="min", mode=selector.NumberSelectorMode.BOX
    )
)

_MINUTES = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=1, max=480, step=1, unit_of_measurement="min", mode=selector.NumberSelectorMode.BOX
    )
)

_SECONDS = selector.NumberSelector(
    selector.NumberSelectorConfig(min=0, max=3600, step=1, mode=selector.NumberSelectorMode.BOX)
)
_RANK = selector.NumberSelector(
    selector.NumberSelectorConfig(min=0, max=99, step=1, mode=selector.NumberSelectorMode.BOX)
)
_CLIMATE = selector.EntitySelector(selector.EntitySelectorConfig(domain="climate"))
_CLIMATE_MULTI = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="climate", multiple=True)
)
_TEXT = selector.TextSelector()
_TIME = selector.TimeSelector()


def _choices(values: list[str], key: str = "") -> selector.SelectSelector:
    """Return a dropdown over plain string values.

    Met een vertaalsleutel toont Home Assistant de vertaalde namen in plaats van
    de opgeslagen waarden. Zonder sleutel blijft het bij de waarde zelf, wat voor
    een lijst die al leesbaar is genoeg is.

    With a translation key Home Assistant shows translated names instead of the
    stored values. Without one the value itself shows, which is enough for a list
    that reads well already.
    """
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=values,
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key=key or None,
        )
    )


def _target_value(installation: dict[str, Any], target: str | None) -> Any:
    """Read a dotted path from the installation, `None` at the first gap."""
    if not target:
        return None
    current: Any = installation
    for part in target.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _weekday_selector() -> selector.SelectSelector:
    """Return the weekday picker, the same shape every window uses."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                selector.SelectOptionDict(value=str(number), label=label)
                for number, label in enumerate(texts.WEEKDAYS)
            ],
            multiple=True,
            mode=selector.SelectSelectorMode.LIST,
            translation_key="weekday",
        )
    )


def _selector_for(field: FieldSpec, flow: Any) -> Any:
    """Return the selector a table field describes, without `vol` around it."""
    unit = temperature_unit_of(flow.hass)
    if field.kind == "text" or field.kind == "states_text":
        return _TEXT
    if field.kind == "bool":
        return bool
    if field.kind == "time":
        return _TIME
    if field.kind == "entity":
        return selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain=(list(field.domain) if isinstance(field.domain, tuple) else field.domain),
                multiple=field.multiple,
            )
        )
    if field.kind == "choice" or field.kind == "hemisphere":
        return _choices(list(field.options), field.translation_key or "")
    if field.kind == "weekdays":
        return _weekday_selector()
    if field.kind == "number":
        if field.unit == "temperature":
            return _temperature(unit)
        if field.unit == "delta_celsius":
            return _band(unit)
        if field.unit == "minutes":
            return _MINUTES
        if field.unit == "minutes_or_off":
            return _MINUTES_OR_OFF
        if field.unit == "seconds":
            return _SECONDS
        if field.unit == "rank":
            return _RANK
    raise AssertionError(f"onbekend veldtype {field.kind!r} voor {field.key}")


def _settings_value(flow: Any, field: FieldSpec) -> Any:
    """Return the form-level default or suggestion for one settings field."""
    unit = temperature_unit_of(flow.hass)
    if field.kind == "number":
        stored = _target_value(flow._installation, field.target)
        if field.unit in ("minutes", "minutes_or_off"):
            return int(stored if stored is not None else field.default) // 60
        if field.unit == "delta_celsius":
            return rounded_delta_from_celsius(
                float(stored if stored is not None else field.default), unit
            )
        return stored if stored is not None else field.default
    if field.kind == "hemisphere":
        return _hemisphere(_target_value(flow._installation, field.target))
    if field.kind == "weekdays":
        stored = _target_value(flow._installation, field.target)
        return None if stored is None else [str(day) for day in sorted(stored)]
    if field.kind == "states_text":
        stored = _target_value(flow._installation, field.target)
        return ", ".join(stored if stored else sorted(PrecipitationSettings().states))
    stored = _target_value(flow._installation, field.target)
    if not field.required:
        return stored or None
    if stored is not None:
        return stored
    if field.kind == "bool" and field.key == CONF_SHADOW_MODE:
        return flow._shadow_mode if flow._shadow_mode is not None else DEFAULT_SHADOW_MODE
    return field.default


def _table_schema(
    fields: tuple[FieldSpec, ...],
    flow: Any,
    *,
    footer: dict[Any, Any] | None = None,
) -> vol.Schema:
    """Build a screen schema from a field table.

    De tabel zegt wélke velden een scherm draagt en wat ze betekenen; deze
    functie vertaalt elke rij naar de `vol.Required`/`vol.Optional`-vorm die
    Home Assistant tekent. De afsluitregel (`when_done`) hoort niet in de tabel
    thuis — die is voor elk scherm hetzelfde — en komt als `footer` mee.

    The table says which fields a screen carries and what they mean; this
    function turns each row into the `vol.Required`/`vol.Optional` shape Home
    Assistant draws. The exit row (`when_done`) does not belong in the table —
    it is the same for every screen — and comes along as `footer`.
    """
    schema: dict[Any, Any] = {}
    for field in fields:
        value = _settings_value(flow, field)
        if field.required:
            schema[vol.Required(field.key, default=value)] = _selector_for(field, flow)
        else:
            schema[vol.Optional(field.key, description={"suggested_value": value})] = _selector_for(
                field, flow
            )
    if footer:
        schema.update(footer)
    return vol.Schema(schema)
