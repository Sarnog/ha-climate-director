"""Apparaten en gebieden van en naar de opgeslagen vorm.

Appliances and areas to and from the stored shape.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .fields import SOURCE_FIELDS
from .models import (
    Circuit,
    ConflictPolicy,
    Generator,
    ModeSettings,
    Opening,
    OutdoorWindow,
    Season,
    Source,
    Zone,
    ZoneGate,
)
from .storage_values import (
    bool_or,
    choice,
    float_or,
    int_or,
    items,
    optional_float,
    optional_int,
    seconds_or,
    strings,
    text,
)
from .table_storage import dict_from, values_from


def zone(raw: Mapping[str, Any]) -> Zone:
    return Zone(
        zone_id=text(raw.get("zone_id")),
        name=text(raw.get("name")),
        indoor_sensor=text(raw.get("indoor_sensor")),
        sources=tuple(source(item) for item in items(raw, "sources")),
        priority=int_or(raw.get("priority"), 0),
        heat=mode(raw.get("heat")),
        cool=mode(raw.get("cool")),
        gate=choice(ZoneGate, raw.get("gate"), ZoneGate.HOUSEHOLD),
        presence_entity=text(raw.get("presence_entity")),
        presence_state=text(raw.get("presence_state")) or "on",
        presence_timeout=seconds_or(raw.get("presence_timeout")),
        ignore_precipitation=bool_or(raw.get("ignore_precipitation"), False),
    )


def source(raw: Mapping[str, Any]) -> Source:
    """Return one source, its fields read from `SOURCE_FIELDS`.

    Alleen `source_id` staat er niet in: dat is identiteit en geen veld van het
    scherm. / Only `source_id` is not in it: that is identity, not a field of
    the screen.
    """
    return Source(source_id=text(raw.get("source_id")), **values_from(SOURCE_FIELDS, raw, Source))


def mode(raw: Any) -> ModeSettings | None:
    """Return mode settings, or `None` when the zone does not offer this duty."""
    if not isinstance(raw, Mapping):
        return None
    seasons = raw.get("seasons")
    return ModeSettings(
        target=float_or(raw.get("target"), 21.0),
        start_at=float_or(raw.get("start_at"), 21.0),
        hysteresis=float_or(raw.get("hysteresis"), 1.0),
        outdoor=outdoor_window(raw.get("outdoor")),
        seasons=(
            None
            if seasons is None
            else frozenset(choice(Season, item, Season.UNKNOWN) for item in strings(seasons))
        ),
    )


def outdoor_window(raw: Any) -> OutdoorWindow:
    if not isinstance(raw, Mapping):
        return OutdoorWindow()
    return OutdoorWindow(
        minimum=optional_float(raw.get("minimum")),
        maximum=optional_float(raw.get("maximum")),
    )


def circuit(raw: Mapping[str, Any]) -> Circuit:
    return Circuit(
        circuit_id=text(raw.get("circuit_id")),
        name=text(raw.get("name")),
        units=tuple(strings(raw.get("units"))),
        simultaneous_heat_cool=bool_or(raw.get("simultaneous_heat_cool"), False),
        conflict_policy=choice(ConflictPolicy, raw.get("conflict_policy"), ConflictPolicy.PRIORITY),
        allow_fan_only_during_conflict=bool_or(raw.get("allow_fan_only_during_conflict"), False),
        family_switch_delay=seconds_or(raw.get("family_switch_delay")),
        min_family_switch_interval=seconds_or(raw.get("min_family_switch_interval")),
        min_cycle_time=seconds_or(raw.get("min_cycle_time")),
        max_concurrent_units=optional_int(raw.get("max_concurrent_units")),
    )


def opening(raw: Mapping[str, Any], opening_id: str) -> Opening:
    """Return one opening, with the id handed in by `opening_ids`."""
    entity_id = text(raw.get("entity_id"))
    return Opening(
        entity_id=entity_id,
        zone_ids=tuple(strings(raw.get("zone_ids"))),
        open_state=text(raw.get("open_state")) or "on",
        delay=seconds_or(raw.get("delay")),
        opening_id=opening_id,
        name=text(raw.get("name")) or entity_id,
    )


def generator(raw: Mapping[str, Any]) -> Generator:
    return Generator(
        generator_id=text(raw.get("generator_id")),
        name=text(raw.get("name")),
        entity_id=text(raw.get("entity_id")),
        zone_ids=tuple(strings(raw.get("zone_ids"))),
        setpoint=optional_float(raw.get("setpoint")),
    )


def zone_to_dict(zone: Zone) -> dict[str, Any]:
    return {
        "zone_id": zone.zone_id,
        "name": zone.name,
        "indoor_sensor": zone.indoor_sensor,
        "priority": zone.priority,
        "sources": [source_to_dict(source) for source in zone.sources],
        "heat": mode_to_dict(zone.heat),
        "cool": mode_to_dict(zone.cool),
        "gate": zone.gate.value,
        "presence_entity": zone.presence_entity,
        "presence_state": zone.presence_state,
        "presence_timeout": zone.presence_timeout.total_seconds(),
        "ignore_precipitation": zone.ignore_precipitation,
    }


def source_to_dict(source: Source) -> dict[str, Any]:
    """Return one source as stored data, its fields from `SOURCE_FIELDS`."""
    return {"source_id": source.source_id, **dict_from(SOURCE_FIELDS, source)}


def mode_to_dict(settings: ModeSettings | None) -> dict[str, Any] | None:
    if settings is None:
        return None
    return {
        "target": settings.target,
        "start_at": settings.start_at,
        "hysteresis": settings.hysteresis,
        "outdoor": outdoor_window_to_dict(settings.outdoor),
        "seasons": (
            None
            if settings.seasons is None
            else sorted(season.value for season in settings.seasons)
        ),
    }


def outdoor_window_to_dict(window: OutdoorWindow) -> dict[str, Any]:
    return {"minimum": window.minimum, "maximum": window.maximum}


def circuit_to_dict(circuit: Circuit) -> dict[str, Any]:
    return {
        "circuit_id": circuit.circuit_id,
        "name": circuit.name,
        "units": list(circuit.units),
        "simultaneous_heat_cool": circuit.simultaneous_heat_cool,
        "conflict_policy": circuit.conflict_policy.value,
        "allow_fan_only_during_conflict": circuit.allow_fan_only_during_conflict,
        "family_switch_delay": circuit.family_switch_delay.total_seconds(),
        "min_family_switch_interval": circuit.min_family_switch_interval.total_seconds(),
        "min_cycle_time": circuit.min_cycle_time.total_seconds(),
        "max_concurrent_units": circuit.max_concurrent_units,
    }


def generator_to_dict(generator: Generator) -> dict[str, Any]:
    return {
        "generator_id": generator.generator_id,
        "name": generator.name,
        "entity_id": generator.entity_id,
        "zone_ids": list(generator.zone_ids),
        "setpoint": generator.setpoint,
    }


def opening_to_dict(opening: Opening) -> dict[str, Any]:
    return {
        "opening_id": opening.opening_id,
        "name": opening.name,
        "entity_id": opening.entity_id,
        "zone_ids": list(opening.zone_ids),
        "open_state": opening.open_state,
        "delay": opening.delay.total_seconds(),
    }
