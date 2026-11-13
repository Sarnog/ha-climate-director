"""De ingang van de opslag: een installatie van en naar een platte dict.

The entrance of storage: an installation to and from a plain dict.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .equipment_storage import (
    circuit,
    circuit_to_dict,
    generator,
    generator_to_dict,
    opening,
    opening_to_dict,
    zone,
    zone_to_dict,
)
from .installation_storage import (
    energy,
    energy_to_dict,
    gates,
    gates_flat_to_dict,
    guest_window_to_dict,
    layout,
    precipitation,
    seasons,
)
from .models import DirectorConfig
from .resident_storage import resident, resident_to_dict
from .storage_values import float_or, items, seconds_or, sequence, strings, text


def opening_ids(items: Iterable[Mapping[str, Any]]) -> list[str]:
    """Return the id of every opening, deriving a missing one from its sensor.

    Eén afleiding, op één plek, voor twee lezers: de opslaglezer hieronder en de
    options flow, die de ruwe opslag leest. Een ontbrekend `opening_id` komt uit
    de `entity_id` en niet uit de naam, want de entity_id is de identiteit en
    blijft dezelfde als iemand er later een naam aan hangt - anders wisselt de
    `unique_id` van de overbruggingsschakelaar en verdwijnt de entiteit met
    geschiedenis en dashboardverwijzingen erbij. Alleen oudere opslag
    heeft geen id; een tweede opening op dezelfde sensor krijgt `_<n>` erachter.
    Een opgeslagen id wordt nooit veranderd, ook een dubbele niet: dat is iets
    voor `validate()` om te melden, niet voor deze lezer om stil op te lossen.

    One derivation, in one place, for two readers: the storage reader below and
    the options flow, which reads the raw storage. A missing `opening_id` comes
    from the `entity_id` and not from the name, because the entity id is the
    identity and stays the same once somebody hangs a name on it - otherwise the
    bypass switch's `unique_id` changes and the entity disappears, history and
    dashboard references included. Only older storage has no id; a
    second opening on the same sensor gets `_<n>` appended. A stored id is never
    changed, not even a duplicate one: that is for `validate()` to report, not
    for this reader to solve quietly.
    """
    ids: list[str] = []
    taken: set[str] = set()
    for item in items:
        opening_id = text(item.get("opening_id"))
        if not opening_id:
            base = text(item.get("entity_id")) or "opening"
            opening_id, index = base, 1
            while opening_id in taken:
                index += 1
                opening_id = f"{base}_{index}"
        ids.append(opening_id)
        taken.add(opening_id)
    return ids


def config_from_dict(raw: Mapping[str, Any]) -> DirectorConfig:
    """Return the installation described by `raw`."""
    stored_openings = items(raw, "openings")
    openings = [
        opening(item, opening_id)
        for item, opening_id in zip(stored_openings, opening_ids(stored_openings), strict=True)
    ]
    return DirectorConfig(
        zones=tuple(zone(item) for item in items(raw, "zones")),
        circuits=tuple(circuit(item) for item in items(raw, "circuits")),
        residents=tuple(resident(item) for item in items(raw, "residents")),
        openings=tuple(openings),
        house_wide_openings=tuple(strings(raw.get("house_wide_openings"))),
        generators=tuple(generator(item) for item in items(raw, "generators")),
        exclusive_groups=tuple(
            frozenset(strings(group)) for group in sequence(raw.get("exclusive_groups"))
        ),
        gates=gates(raw.get("gates")),
        seasons=seasons(raw.get("seasons")),
        precipitation=precipitation(raw.get("precipitation")),
        energy=energy(raw.get("energy")),
        heating_layout=layout(raw),
        outdoor_sensor=text(raw.get("outdoor_sensor")),
        outdoor_hysteresis=float_or(raw.get("outdoor_hysteresis"), 0.5),
        stuck_after=seconds_or(raw.get("stuck_after"), 900.0),
        holiday_calendars=tuple(strings(raw.get("holiday_calendars"))),
        holiday_keyword=text(raw.get("holiday_keyword")),
    )


def config_to_dict(config: DirectorConfig) -> dict[str, Any]:
    """Return `config` as data a config entry can store.

    Round-trips through `config_from_dict` unchanged, which is what lets the
    options flow read the stored configuration, hand a modified copy back and
    trust that nothing was quietly dropped along the way.
    """
    return {
        "zones": [zone_to_dict(zone) for zone in config.zones],
        "circuits": [circuit_to_dict(circuit) for circuit in config.circuits],
        "residents": [resident_to_dict(resident) for resident in config.residents],
        "openings": [opening_to_dict(opening) for opening in config.openings],
        "house_wide_openings": list(config.house_wide_openings),
        "generators": [generator_to_dict(item) for item in config.generators],
        "exclusive_groups": [sorted(group) for group in config.exclusive_groups],
        "gates": {
            **gates_flat_to_dict(config.gates),
            "quiet_windows": [
                {
                    "start": window.start.isoformat(),
                    "end": window.end.isoformat(),
                    "weekdays": (None if window.weekdays is None else sorted(window.weekdays)),
                    # De lezer kent deze vlag al; hem hier vergeten maakte van
                    # een vakantievenster stilletjes een gewoon venster zodra de
                    # configuratie werd teruggeschreven.
                    #
                    # The reader already knows this flag; forgetting it here
                    # quietly turned a holiday window into an ordinary one the
                    # moment the configuration was written back.
                    "holiday": window.holiday,
                }
                for window in config.gates.quiet_windows
            ],
            "guest_window": guest_window_to_dict(config.gates.guest_window),
        },
        "seasons": {
            "source": config.seasons.source.value,
            "entity_id": config.seasons.entity_id,
            "summer_months": sorted(config.seasons.summer_months),
        },
        "precipitation": {
            "source": config.precipitation.source,
            "states": sorted(config.precipitation.states),
            "grace": int(config.precipitation.grace.total_seconds()),
        },
        "energy": energy_to_dict(config.energy),
        "heating_layout": config.heating_layout.value,
        "outdoor_sensor": config.outdoor_sensor,
        "outdoor_hysteresis": config.outdoor_hysteresis,
        "stuck_after": int(config.stuck_after.total_seconds()),
        "holiday_calendars": list(config.holiday_calendars),
        "holiday_keyword": config.holiday_keyword,
    }
