"""Configuratie omzetten van en naar platte dicts.

Converting the configuration to and from plain dicts.

Een Home Assistant config entry bewaart JSON-achtige data: dicts, lijsten,
strings en getallen. Deze module is de enige plek waar dat formaat naar de
dataclasses van `models.py` vertaald wordt, en terug.

Het lezen is bewust vergevingsgezind: onbekende sleutels worden genegeerd en
ontbrekende sleutels vallen terug op de standaardwaarde. Een config entry
overleeft zo een versie waarin een veld bijkomt of verdwijnt, in plaats van bij
het opstarten om te vallen. Wat structureel niet klopt komt uit `validate()`,
niet uit een exception hier.

A Home Assistant config entry stores JSON-like data: dicts, lists, strings and
numbers. This module is the only place that format is translated into the
dataclasses of `models.py`, and back.

Reading is deliberately forgiving: unknown keys are ignored and missing keys
fall back to their default. A config entry therefore survives a version that
adds or drops a field, instead of falling over at startup. What is structurally
wrong comes out of `validate()`, not out of an exception here.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import time, timedelta
from typing import Any

from .models import (
    Circuit,
    ConflictPolicy,
    DirectorConfig,
    GateSettings,
    Generator,
    ModeSettings,
    Opening,
    OutdoorWindow,
    Resident,
    Season,
    SeasonSettings,
    SeasonSource,
    Source,
    SourceRole,
    TimeWindow,
    Zone,
)


def config_from_dict(raw: Mapping[str, Any]) -> DirectorConfig:
    """Return the installation described by `raw`."""
    return DirectorConfig(
        zones=tuple(_zone(item) for item in _items(raw, "zones")),
        circuits=tuple(_circuit(item) for item in _items(raw, "circuits")),
        residents=tuple(_resident(item) for item in _items(raw, "residents")),
        openings=tuple(_opening(item) for item in _items(raw, "openings")),
        generators=tuple(_generator(item) for item in _items(raw, "generators")),
        exclusive_groups=tuple(
            frozenset(_strings(group)) for group in raw.get("exclusive_groups") or ()
        ),
        gates=_gates(raw.get("gates")),
        seasons=_seasons(raw.get("seasons")),
        outdoor_sensor=_text(raw.get("outdoor_sensor")),
        holiday_calendars=tuple(_strings(raw.get("holiday_calendars"))),
        holiday_keyword=_text(raw.get("holiday_keyword")),
    )


def config_to_dict(config: DirectorConfig) -> dict[str, Any]:
    """Return `config` as data a config entry can store.

    Round-trips through `config_from_dict` unchanged, which is what lets the
    options flow read the stored configuration, hand a modified copy back and
    trust that nothing was quietly dropped along the way.
    """
    return {
        "zones": [_zone_to_dict(zone) for zone in config.zones],
        "circuits": [_circuit_to_dict(circuit) for circuit in config.circuits],
        "residents": [_resident_to_dict(resident) for resident in config.residents],
        "openings": [_opening_to_dict(opening) for opening in config.openings],
        "generators": [_generator_to_dict(item) for item in config.generators],
        "exclusive_groups": [sorted(group) for group in config.exclusive_groups],
        "gates": {
            "require_awake": config.gates.require_awake,
            "require_schedule": config.gates.require_schedule,
        },
        "seasons": {
            "source": config.seasons.source.value,
            "entity_id": config.seasons.entity_id,
            "summer_months": sorted(config.seasons.summer_months),
        },
        "outdoor_sensor": config.outdoor_sensor,
        "holiday_calendars": list(config.holiday_calendars),
        "holiday_keyword": config.holiday_keyword,
    }


# ---------------------------------------------------------------------------
# Lezen / reading
# ---------------------------------------------------------------------------


def _zone(raw: Mapping[str, Any]) -> Zone:
    return Zone(
        zone_id=_text(raw.get("zone_id")),
        name=_text(raw.get("name")),
        indoor_sensor=_text(raw.get("indoor_sensor")),
        sources=tuple(_source(item) for item in _items(raw, "sources")),
        priority=_int(raw.get("priority"), 0),
        heat=_mode(raw.get("heat")),
        cool=_mode(raw.get("cool")),
        presence_entity=_text(raw.get("presence_entity")),
        presence_state=_text(raw.get("presence_state")) or "on",
        presence_timeout=_seconds(raw.get("presence_timeout")),
    )


def _source(raw: Mapping[str, Any]) -> Source:
    return Source(
        source_id=_text(raw.get("source_id")),
        entity_id=_text(raw.get("entity_id")),
        role=_enum(SourceRole, raw.get("role"), SourceRole.HEAT_COOL),
        priority=_int(raw.get("priority"), 0),
        outdoor=_window(raw.get("outdoor")),
    )


def _mode(raw: Any) -> ModeSettings | None:
    """Return mode settings, or `None` when the zone does not offer this duty."""
    if not isinstance(raw, Mapping):
        return None
    seasons = raw.get("seasons")
    return ModeSettings(
        target=_float(raw.get("target"), 21.0),
        start_at=_float(raw.get("start_at"), 21.0),
        hysteresis=_float(raw.get("hysteresis"), 1.0),
        outdoor=_window(raw.get("outdoor")),
        seasons=(
            None
            if seasons is None
            else frozenset(_enum(Season, item, Season.UNKNOWN) for item in _strings(seasons))
        ),
    )


def _window(raw: Any) -> OutdoorWindow:
    if not isinstance(raw, Mapping):
        return OutdoorWindow()
    return OutdoorWindow(
        minimum=_optional_float(raw.get("minimum")),
        maximum=_optional_float(raw.get("maximum")),
    )


def _circuit(raw: Mapping[str, Any]) -> Circuit:
    return Circuit(
        circuit_id=_text(raw.get("circuit_id")),
        name=_text(raw.get("name")),
        units=tuple(_strings(raw.get("units"))),
        simultaneous_heat_cool=_bool(raw.get("simultaneous_heat_cool"), True),
        conflict_policy=_enum(ConflictPolicy, raw.get("conflict_policy"), ConflictPolicy.PRIORITY),
        allow_fan_only_during_conflict=_bool(raw.get("allow_fan_only_during_conflict"), False),
        family_switch_delay=_seconds(raw.get("family_switch_delay")),
        min_family_switch_interval=_seconds(raw.get("min_family_switch_interval")),
        min_cycle_time=_seconds(raw.get("min_cycle_time")),
        max_concurrent_units=_optional_int(raw.get("max_concurrent_units")),
    )


def _resident(raw: Mapping[str, Any]) -> Resident:
    return Resident(
        resident_id=_text(raw.get("resident_id")),
        name=_text(raw.get("name")),
        windows=tuple(_time_window(item) for item in _items(raw, "windows")),
        presence_entity=_text(raw.get("presence_entity")),
        sleep_entity=_text(raw.get("sleep_entity")),
        sleep_state=_text(raw.get("sleep_state")) or "on",
    )


def _time_window(raw: Mapping[str, Any]) -> TimeWindow:
    weekdays = raw.get("weekdays")
    return TimeWindow(
        holiday=_bool(raw.get("holiday"), False),
        start=_time(raw.get("start"), time(0, 0)),
        end=_time(raw.get("end"), time(0, 0)),
        weekdays=(
            None
            if weekdays is None
            else frozenset(_int(day, 0) for day in weekdays if _is_number(day))
        ),
    )


def _opening(raw: Mapping[str, Any]) -> Opening:
    return Opening(
        entity_id=_text(raw.get("entity_id")),
        zone_ids=tuple(_strings(raw.get("zone_ids"))),
        delay=_seconds(raw.get("delay")),
    )


def _generator(raw: Mapping[str, Any]) -> Generator:
    return Generator(
        generator_id=_text(raw.get("generator_id")),
        name=_text(raw.get("name")),
        entity_id=_text(raw.get("entity_id")),
        zone_ids=tuple(_strings(raw.get("zone_ids"))),
        setpoint=_optional_float(raw.get("setpoint")),
    )


def _gates(raw: Any) -> GateSettings:
    if not isinstance(raw, Mapping):
        return GateSettings()
    return GateSettings(
        require_awake=_bool(raw.get("require_awake"), True),
        require_schedule=_bool(raw.get("require_schedule"), False),
    )


def _seasons(raw: Any) -> SeasonSettings:
    if not isinstance(raw, Mapping):
        return SeasonSettings()
    months = raw.get("summer_months")
    return SeasonSettings(
        source=_enum(SeasonSource, raw.get("source"), SeasonSource.AUTO),
        entity_id=_text(raw.get("entity_id")),
        summer_months=(
            SeasonSettings().summer_months
            if months is None
            else frozenset(_int(month, 0) for month in months if _is_number(month))
        ),
    )


# ---------------------------------------------------------------------------
# Schrijven / writing
# ---------------------------------------------------------------------------


def _zone_to_dict(zone: Zone) -> dict[str, Any]:
    return {
        "zone_id": zone.zone_id,
        "name": zone.name,
        "indoor_sensor": zone.indoor_sensor,
        "priority": zone.priority,
        "sources": [_source_to_dict(source) for source in zone.sources],
        "heat": _mode_to_dict(zone.heat),
        "cool": _mode_to_dict(zone.cool),
        "presence_entity": zone.presence_entity,
        "presence_state": zone.presence_state,
        "presence_timeout": zone.presence_timeout.total_seconds(),
    }


def _source_to_dict(source: Source) -> dict[str, Any]:
    return {
        "source_id": source.source_id,
        "entity_id": source.entity_id,
        "role": source.role.value,
        "priority": source.priority,
        "outdoor": _window_to_dict(source.outdoor),
    }


def _mode_to_dict(settings: ModeSettings | None) -> dict[str, Any] | None:
    if settings is None:
        return None
    return {
        "target": settings.target,
        "start_at": settings.start_at,
        "hysteresis": settings.hysteresis,
        "outdoor": _window_to_dict(settings.outdoor),
        "seasons": (
            None
            if settings.seasons is None
            else sorted(season.value for season in settings.seasons)
        ),
    }


def _window_to_dict(window: OutdoorWindow) -> dict[str, Any]:
    return {"minimum": window.minimum, "maximum": window.maximum}


def _circuit_to_dict(circuit: Circuit) -> dict[str, Any]:
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


def _resident_to_dict(resident: Resident) -> dict[str, Any]:
    return {
        "resident_id": resident.resident_id,
        "name": resident.name,
        "presence_entity": resident.presence_entity,
        "sleep_entity": resident.sleep_entity,
        "sleep_state": resident.sleep_state,
        "windows": [
            {
                "start": window.start.strftime("%H:%M:%S"),
                "end": window.end.strftime("%H:%M:%S"),
                "weekdays": (None if window.weekdays is None else sorted(window.weekdays)),
                "holiday": window.holiday,
            }
            for window in resident.windows
        ],
    }


def _generator_to_dict(generator: Generator) -> dict[str, Any]:
    return {
        "generator_id": generator.generator_id,
        "name": generator.name,
        "entity_id": generator.entity_id,
        "zone_ids": list(generator.zone_ids),
        "setpoint": generator.setpoint,
    }


def _opening_to_dict(opening: Opening) -> dict[str, Any]:
    return {
        "entity_id": opening.entity_id,
        "zone_ids": list(opening.zone_ids),
        "delay": opening.delay.total_seconds(),
    }


# ---------------------------------------------------------------------------
# Kleine hulpjes / small helpers
# ---------------------------------------------------------------------------


def _items(raw: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    """Return the mappings stored under `key`, skipping anything else."""
    return [item for item in (raw.get(key) or ()) if isinstance(item, Mapping)]


def _strings(raw: Any) -> list[str]:
    if isinstance(raw, str) or not isinstance(raw, Iterable):
        return []
    return [item for item in raw if isinstance(item, str)]


def _text(raw: Any) -> str:
    return raw if isinstance(raw, str) else ""


def _is_number(raw: Any) -> bool:
    return isinstance(raw, int | float) and not isinstance(raw, bool)


def _float(raw: Any, default: float) -> float:
    return float(raw) if _is_number(raw) else default


def _optional_float(raw: Any) -> float | None:
    return float(raw) if _is_number(raw) else None


def _int(raw: Any, default: int) -> int:
    return int(raw) if _is_number(raw) else default


def _optional_int(raw: Any) -> int | None:
    return int(raw) if _is_number(raw) else None


def _bool(raw: Any, default: bool) -> bool:
    return raw if isinstance(raw, bool) else default


def _seconds(raw: Any, default: float = 0.0) -> timedelta:
    """Return a duration; stored as plain seconds so the entry stays JSON."""
    return timedelta(seconds=_float(raw, default))


def _time(raw: Any, default: time) -> time:
    """Return a time from `HH:MM` or `HH:MM:SS`, falling back on `default`.

    A single-digit hour is padded first: the options flow always writes a padded
    time, but a hand-edited entry may well say `8:00`, and reading that as
    midnight would move somebody's schedule by eight hours without a word.
    """
    if not isinstance(raw, str):
        return default
    text = raw.strip()
    if len(text) > 1 and text[1] == ":":
        text = f"0{text}"
    try:
        return time.fromisoformat(text)
    except ValueError:
        return default


def _enum[T: str](enum_type: type[T], raw: Any, default: T) -> T:
    """Return the enum member named by `raw`, or `default` when unrecognised."""
    if not isinstance(raw, str):
        return default
    try:
        return enum_type(raw)
    except ValueError:
        return default
