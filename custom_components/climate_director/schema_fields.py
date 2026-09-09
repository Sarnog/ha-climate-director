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

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers import selector

from . import texts
from .const import CONF_SHADOW_MODE, DEFAULT_SHADOW_MODE
from .engine.fields import FieldSpec
from .engine.models import PrecipitationSettings, SeasonSettings
from .units import (
    delta_to_celsius,
    rounded_delta_from_celsius,
    rounded_from_celsius,
    temperature_unit_of,
    to_celsius,
)

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


def _target_value(values: Mapping[str, Any], target: str | None) -> Any:
    """Read a dotted path from a value source, `None` at the first gap.

    De waardebron is de installatie voor het instellingenscherm en het item zelf
    voor een lijst-itemscherm; de tabel kent alleen het pad.

    The value source is the installation for the settings screen and the item
    itself for a list-item screen; the table only knows the path.
    """
    if not target:
        return None
    current: Any = values
    for part in target.split("."):
        if not isinstance(current, Mapping):
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


def _settings_value(flow: Any, field: FieldSpec, values: Mapping[str, Any]) -> Any:
    """Return the form-level default or suggestion for one table field.

    De waardebron komt van buiten mee in plaats van hard uit `flow._installation`
    te komen: het instellingenscherm leest de installatie, een lijst-itemscherm
    leest het item dat bewerkt wordt. Dat is het enige verschil tussen de twee,
    en daarom is het een parameter en geen tweede functie.

    The value source is handed in rather than coming hard-wired from
    `flow._installation`: the settings screen reads the installation, a list-item
    screen reads the item being edited. That is the only difference between the
    two, and hence a parameter rather than a second function.
    """
    unit = temperature_unit_of(flow.hass)
    if field.kind == "number":
        stored = _target_value(values, field.target)
        if field.unit in ("minutes", "minutes_or_off"):
            return int(stored if stored is not None else field.default) // 60
        if field.unit == "delta_celsius":
            return rounded_delta_from_celsius(
                float(stored if stored is not None else field.default), unit
            )
        if field.unit == "temperature":
            return rounded_from_celsius(stored, unit)
        if field.unit == "seconds" and not field.required:
            # Leeg blijft leeg: dat betekent "geen eigen rem", en nul betekent
            # iets anders. / Empty stays empty: that means "no brake of its
            # own", and zero means something else.
            return stored
        return stored if stored is not None else field.default
    if field.kind == "hemisphere":
        return _hemisphere(_target_value(values, field.target))
    if field.kind == "weekdays":
        stored = _target_value(values, field.target)
        return None if stored is None else [str(day) for day in sorted(stored)]
    if field.kind == "states_text":
        stored = _target_value(values, field.target)
        return ", ".join(stored if stored else sorted(PrecipitationSettings().states))
    stored = _target_value(values, field.target)
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
    values: Mapping[str, Any],
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

    De waardebron (`values`) staat er expliciet bij: de installatie voor het
    instellingenscherm, het item zelf voor een lijst-itemscherm.

    The value source (`values`) is explicit: the installation for the settings
    screen, the item itself for a list-item screen.
    """
    schema: dict[Any, Any] = {}
    for field in fields:
        value = _settings_value(flow, field, values)
        if field.required:
            schema[vol.Required(field.key, default=value)] = _selector_for(field, flow)
        else:
            schema[vol.Optional(field.key, description={"suggested_value": value})] = _selector_for(
                field, flow
            )
    if footer:
        schema.update(footer)
    return vol.Schema(schema)


def _blank(value: Any) -> bool:
    """Return whether a submitted optional value means "nothing filled in"."""
    return value is None or value == ""


def _write_target(destination: dict[str, Any], target: str, value: Any) -> None:
    """Put `value` at the dotted `target` path, making the way there as needed.

    Een pad met een punt erin (`outdoor.minimum`, `gates.guest_window.start`)
    maakt de tussenliggende dicts aan in plaats van erop te struikelen, en laat
    staan wat er al staat: het stiltevensterscherm schrijft in dezelfde
    `gates`-sleutel, en een compleet nieuw dict zou dat werk stilletjes wissen.

    A path with a dot in it (`outdoor.minimum`, `gates.guest_window.start`)
    creates the intermediate dicts rather than tripping over them, and leaves
    what is already there: the quiet-window screen writes into the same `gates`
    key, and a brand-new dict would silently erase that work.
    """
    parts = target.split(".")
    current = destination
    for part in parts[:-1]:
        nested = current.get(part)
        if not isinstance(nested, dict):
            nested = {}
            current[part] = nested
        current = nested
    current[parts[-1]] = value


def _stored_number(field: FieldSpec, form_value: Any, unit: str) -> Any:
    """Return one submitted number as the value the installation stores."""
    if field.unit in ("minutes", "minutes_or_off"):
        return int(form_value or 0) * 60
    if field.unit == "delta_celsius":
        return float(delta_to_celsius(form_value, unit) or 0)
    if field.unit == "temperature":
        return to_celsius(None if _blank(form_value) else form_value, unit)
    if field.unit == "seconds":
        return None if _blank(form_value) else form_value
    if field.unit == "rank":
        return int(form_value)
    raise AssertionError(f"onbekende maat {field.unit!r} voor {field.key}")


def _stored_value(
    field: FieldSpec,
    user_input: Mapping[str, Any],
    destination: Mapping[str, Any],
    unit: str,
) -> Any:
    """Return one submitted field as the value the installation stores."""
    form_value = user_input.get(field.key)
    if field.hook == "summer_months":
        return _summer_months(form_value, _target_value(destination, field.target))
    if field.hook == "states":
        return sorted({item.strip() for item in (form_value or "").split(",") if item.strip()})
    if field.hook == "trim":
        return (form_value or "").strip()
    if field.kind in ("bool", "choice"):
        return user_input[field.key]
    if field.kind == "text" or field.kind == "time":
        return form_value or ""
    if field.kind == "entity":
        return list(form_value or ()) if field.multiple else (form_value or "")
    if field.kind == "weekdays":
        return [int(day) for day in form_value or ()] or None
    if field.kind == "number":
        return _stored_number(field, form_value, unit)
    raise AssertionError(f"onbekend veldtype {field.kind!r} voor {field.key}")


def _summer_months(hemisphere: Any, stored: Any) -> list[int]:
    """Return the summer months a hemisphere choice describes.

    Een handmatige zomermaandenlijst is een bewuste keuze; het halfrond-veld is
    alleen de snelle manier om een van de twee standaardlijsten te kiezen. Wijkt
    de opgeslagen lijst af van beide standaarden, dan blijft hij staan.

    A hand-picked summer-months list is a deliberate choice; the hemisphere
    field is only the quick way to pick one of the two default lists. If the
    stored list differs from both defaults it stays.
    """
    try:
        kept = frozenset(int(month) for month in stored or ())
    except (TypeError, ValueError):
        kept = frozenset()
    if kept and kept not in (_SUMMER_NORTH, _SUMMER_SOUTH):
        return sorted(kept)
    return sorted(_SUMMER_SOUTH if hemisphere == "south" else _SUMMER_NORTH)


def write_table(
    fields: tuple[FieldSpec, ...],
    user_input: Mapping[str, Any],
    destination: dict[str, Any],
    *,
    flow: Any,
) -> None:
    """Write every row of a field table back to its place in `destination`.

    De tegenhanger van `_table_schema`: die leest een scherm uit een waardebron,
    deze schrijft het ingezonden formulier terug. Elke rij gaat naar haar
    `target`-pad, genest en met de eenheidsomrekening die haar maat voorschrijft.
    Een rij met een `hook` wijkt daar bewust van af, en een rij zonder `target`
    hoort in de bedieningstoestand in plaats van in de installatie.

    The counterpart of `_table_schema`: that one reads a screen from a value
    source, this one writes the submitted form back. Every row goes to its
    `target` path, nested and with the unit conversion its measure prescribes. A
    row with a `hook` deliberately differs, and a row without a `target` belongs
    in the control state rather than in the installation.
    """
    unit = temperature_unit_of(flow.hass)
    for field in fields:
        if field.hook == "control_state":
            flow._shadow_mode = user_input[field.key]
            continue
        assert field.target is not None, f"veld {field.key} heeft geen doel in de installatie"
        value = _stored_value(field, user_input, destination, unit)
        _write_target(destination, field.target, value)
