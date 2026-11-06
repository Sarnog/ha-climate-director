"""Algemene installatievelden van en naar de opgeslagen vorm.

General installation fields to and from the stored shape.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import time
from typing import Any

from .fields import GATES_FLAT_FIELDS, GUEST_WINDOW_FIELDS, target_key
from .models import (
    GateSettings,
    HeatingLayout,
    PrecipitationSettings,
    SeasonSettings,
    SeasonSource,
    SourceRole,
    TimeWindow,
)
from .storage_values import (
    bool_or,
    choice,
    int_or,
    is_number,
    seconds_or,
    sequence,
    strings,
    text,
    time_or,
    weekdays,
)
from .table_storage import parse_leaf, write_leaf


def time_window(raw: Mapping[str, Any]) -> TimeWindow:
    return TimeWindow(
        holiday=bool_or(raw.get("holiday"), False),
        start=time_or(raw.get("start"), time(0, 0)),
        end=time_or(raw.get("end"), time(0, 0)),
        weekdays=weekdays(raw.get("weekdays")),
    )


def gates(raw: Any) -> GateSettings:
    """Return the gate settings, built from the field table.

    De sleutels van `GATES_FLAT_FIELDS` zijn de namen van de dataclass: een
    nieuwe poort is één tabelrij plus één attribuut op `GateSettings`.

    The keys of `GATES_FLAT_FIELDS` are the dataclass's names: a new gate is one
    table row plus one attribute on `GateSettings`.
    """
    if not isinstance(raw, Mapping):
        return GateSettings()
    flat = {
        target_key(field): parse_leaf(field, raw.get(target_key(field)))
        for field in GATES_FLAT_FIELDS
    }
    guest_raw = raw.get("guest_window")
    guest: dict[str, Any] = guest_raw if isinstance(guest_raw, dict) else {}
    return GateSettings(
        quiet_windows=tuple(
            time_window(item)
            for item in sequence(raw.get("quiet_windows"))
            if isinstance(item, dict)
        ),
        guest_window=guest_window(guest),
        guest_window_incomplete=bool(guest.get("start")) != bool(guest.get("end")),
        **flat,
    )


def guest_window(raw: dict[str, Any]) -> TimeWindow | None:
    """Return the guest window, or `None` when it is not both-ends filled in.

    Half een venster is geen venster: dan geldt de gastenmodus de hele dag.
    Half a window is no window: guest mode then applies all day.

    De bladeren (start, eind en dagen) komen uit de veldtabel, zodat een nieuw
    gastenvensterveld één rij is in `engine/fields.py`, niet een wijziging hier.

    The leaves (start, end and days) come from the field table, so a new guest
    window field is one row in `engine/fields.py`, not a change here and in the form.
    """
    if not isinstance(raw, Mapping):
        return None
    leaves = {target_key(field): raw.get(target_key(field)) for field in GUEST_WINDOW_FIELDS}
    start, end = leaves.get("start"), leaves.get("end")
    if not start or not end:
        return None
    values = {
        target_key(field): parse_leaf(field, leaves[target_key(field)])
        for field in GUEST_WINDOW_FIELDS
    }
    return TimeWindow(
        start=values["start"],
        end=values["end"],
        weekdays=values.get("weekdays"),
    )


def sleep_window(raw: dict[str, Any]) -> TimeWindow | None:
    """Return the sleep window, days and all.

    Het gastenvenster en het vooruit-venster gelden voor het hele huis en
    kennen geen dagen; een slaapvenster hangt aan één bewoner, en die heeft in
    het weekend een ander ritme dan doordeweeks.

    The guest window and the pre-conditioning window apply to the whole house
    and know no days; a sleep window belongs to one resident, and a resident
    keeps a different rhythm at the weekend than on a working day.
    """
    window = guest_window(raw)
    if window is None:
        return None
    return TimeWindow(start=window.start, end=window.end, weekdays=weekdays(raw.get("weekdays")))


def seasons(raw: Any) -> SeasonSettings:
    if not isinstance(raw, Mapping):
        return SeasonSettings()
    months = raw.get("summer_months")
    return SeasonSettings(
        source=choice(SeasonSource, raw.get("source"), SeasonSource.AUTO),
        entity_id=text(raw.get("entity_id")),
        summer_months=(
            SeasonSettings().summer_months
            if months is None
            # Via `sequence`, want een opgeslagen waarde die geen lijst blijkt
            # - een getal, een tekst - werd hier gewoon doorlopen. Bij een tekst
            # levert dat losse letters op en bij een getal een `TypeError` die
            # de hele installatie niet meer laat laden.
            #
            # Through `sequence`, since a stored value that turns out not to be
            # a list - a number, a string - used to be iterated all the same. On
            # a string that yields loose letters and on a number a `TypeError`
            # that stops the whole installation from loading.
            else frozenset(int_or(month, 0) for month in sequence(months) if is_number(month))
        ),
    )


def precipitation(raw: Any) -> PrecipitationSettings:
    """Return the precipitation settings, defaulting to the engine's own."""
    if not isinstance(raw, Mapping):
        return PrecipitationSettings()
    states = raw.get("states")
    if states is None:
        chosen = PrecipitationSettings().states
    else:
        chosen = frozenset(item for item in strings(states) if item.strip())
        # Het instellingenscherm schrijft een leeg tekstveld als `[]`. Dat is
        # iets anders dan een opzet die neerslag nooit telt: wie het veld
        # leeghaalt bedoelt "doe maar gewoon", niet "zet de regenuitzondering
        # stilletjes uit terwijl de bron nog ingevuld staat".
        #
        # The settings screen writes an empty text field as `[]`. That is
        # different from a setup that should never count precipitation: clearing
        # the field means "just the usual", not "silently disable the rain
        # exception while the source still stands filled in".
        if not chosen:
            chosen = PrecipitationSettings().states
    return PrecipitationSettings(
        source=text(raw.get("source")),
        states=chosen,
        grace=seconds_or(raw.get("grace"), 900.0),
    )


def layout(raw: Mapping[str, Any]) -> HeatingLayout:
    """Return the heating layout, inferred when it was never chosen.

    De instelling kwam er later bij. Een bestaande installatie zonder deze
    sleutel mag daar geen waarschuwing voor krijgen, dus leiden we hem af uit
    wat er al staat: deelt een warmtebron twee of meer zones, dan is het een
    gesloten systeem. Vanaf de eerste keer opslaan staat de keuze vast en
    raadt er niets meer.

    The setting arrived later. An existing installation without this key must
    not be warned about it, so we infer it from what is already there: if a heat
    source spans two or more zones, it is a closed system. From the first save
    onwards the choice is recorded and nothing guesses any more.
    """
    stored = raw.get("heating_layout")
    if isinstance(stored, str) and stored in {item.value for item in HeatingLayout}:
        return HeatingLayout(stored)

    seen: dict[str, int] = {}
    for zone in sequence(raw.get("zones")):
        if not isinstance(zone, dict):
            continue
        # Alleen bronnen die kunnen verwarmen tellen mee: het gaat hier om de
        # verwarmingsindeling. Een gedeelde airco die alleen koelt zegt niets
        # over hoe het huis verwarmd wordt, en meetellen maakte van zo'n
        # configuratie stilletjes een "centrale verwarming" waar de controle
        # daarna over klaagde.
        #
        # Only sources able to heat count: this is about the heating layout. A
        # shared cooler says nothing about how the house is heated, and counting
        # it quietly turned such a setup into "central heating", which the check
        # then complained about.
        entities = {
            text(source.get("entity_id"))
            for source in sequence(zone.get("sources"))
            if isinstance(source, dict) and source.get("role") != SourceRole.COOL_ONLY.value
        }
        for entity_id in entities - {""}:
            seen[entity_id] = seen.get(entity_id, 0) + 1
    return (
        HeatingLayout.CENTRAL
        if any(count > 1 for count in seen.values())
        else HeatingLayout.PER_ZONE
    )


def guest_window_to_dict(window: TimeWindow | None) -> dict[str, Any] | None:
    """Return the guest window as stored data, days included."""
    if window is None:
        return None
    return {
        target_key(field): write_leaf(field, getattr(window, target_key(field)))
        for field in GUEST_WINDOW_FIELDS
    }


def gates_flat_to_dict(gates: GateSettings) -> dict[str, Any]:
    """Return the flat gates fields as stored data, from the field table."""
    return {
        target_key(field): write_leaf(field, getattr(gates, target_key(field)))
        for field in GATES_FLAT_FIELDS
    }
