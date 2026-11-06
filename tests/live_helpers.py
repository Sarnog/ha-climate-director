"""Bouwstenen voor de toetsen in een echte Home Assistant: huizen, werelden en opslag.

Building blocks for the tests in a real Home Assistant: houses, worlds and storage."""

from __future__ import annotations

import json
import pathlib
from typing import Any

from harness_live import settings, source, zone

from custom_components.climate_director import coordinator as coordinator_module
from custom_components.climate_director.coordinator import storage_key

LIVING = "climate.woonkamer"


ATTIC = "climate.zolder"


SPARE = "climate.woonkamer_reserve"


BOILER = "climate.ketel"


VALVE = "climate.keuken_kraan"


def simple_installation() -> dict[str, Any]:
    """Return a one-room installation that wants heat."""
    return {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("airco", LIVING, role="heat_cool")],
                heat=settings(21.0, 20.0),
            )
        ]
    }


def cold_one_room() -> dict[str, tuple[str, dict[str, Any]]]:
    """Return a cold room and an idle appliance."""
    return {"sensor.woonkamer": ("18.0", {}), LIVING: ("off", {})}


PEOPLE = {
    "danny": ("person.danny", "sensor.danny_lader"),
    "nancy": ("person.nancy", "sensor.nancy_lader"),
}


def write_store(config_dir: str, entry_id: str, data: Any) -> pathlib.Path:
    """Write one store file the way Home Assistant's `Store` would."""
    key = storage_key(entry_id)
    store_dir = pathlib.Path(config_dir) / ".storage"
    store_dir.mkdir(parents=True, exist_ok=True)
    path = store_dir / key
    path.write_text(
        json.dumps({"version": 1, "minor_version": 1, "key": key, "data": data}),
        encoding="utf-8",
    )
    return path


IMPOSSIBLE = "2026-13-45T10:00:00+00:00"


NAIVE = "2026-08-15T01:00:00"


IMPOSSIBLE_DATE = "2026-13-45"


def resident(resident_id: str) -> dict[str, Any]:
    """Return one resident in stored form, with a deadline late enough for any test run.

    Zonder slaapvenster telt de lader de klok rond, zodat een bewoner in bed ook echt als
    slapend geldt op het moment dat deze toets draait - dat is wat het slaapmoment hier
    meetbaar maakt.

    Without a sleep window the charger counts around the clock, so a resident in bed really
    counts as asleep at the moment this test runs - that is what makes the sleep moment
    measurable here.
    """
    person, charger = PEOPLE[resident_id]
    return {
        "resident_id": resident_id,
        "name": resident_id.title(),
        "presence_entity": person,
        "sleep_entity": charger,
        "sleep_state": "wireless",
        "wake_deadline": {"at": "23:59:59"},
    }


def house_with_two_residents() -> dict[str, Any]:
    """Return the cold one-room house with two residents whose moments come from the store."""
    installation = simple_installation()
    installation["residents"] = [resident("danny"), resident("nancy")]
    return installation


def two_residents(*, danny: str = "up", nancy: str = "up") -> dict[str, tuple[str, dict[str, Any]]]:
    """Return the cold room with each resident at home in bed (`bed`), up or `away`."""
    found = cold_one_room()
    for resident_id, how in (("danny", danny), ("nancy", nancy)):
        person, charger = PEOPLE[resident_id]
        found[person] = ("not_home" if how == "away" else "home", {})
        found[charger] = ("wireless" if how == "bed" else "none", {})
    return found


def two_zone_installation(**extra: Any) -> dict[str, Any]:
    """Return a two-zone house: a room with a stand-in, and an attic.

    Er is geen vooruit-venster meer, dus deze tests hangen niet van het uur af:
    een verzoek geldt op elk moment van de dag. De klok van deze testopstelling
    is UTC; een test die van het uur afhangt zegt niets over de code.

    There is no pre-conditioning window anymore, so these tests do not depend
    on the hour: a request counts at any moment of the day. This harness's
    clock is UTC; a test depending on the hour says nothing about the code.
    """
    found: dict[str, Any] = {
        "zones": [
            zone(
                "woonkamer",
                sources=[
                    source("woonkamer_airco", LIVING, role="heat_cool"),
                    source("woonkamer_reserve", SPARE, role="heat_only", priority=1),
                ],
                heat=settings(21.0, 20.0),
                cool=settings(23.0, 24.0),
            ),
            zone(
                "zolder",
                sources=[source("zolder_airco", ATTIC, role="heat_cool")],
                heat=settings(20.0, 19.0),
                priority=1,
            ),
        ],
        "outdoor_sensor": "sensor.buiten",
        "residents": [
            {
                "resident_id": "danny",
                "name": "Danny",
                "presence_entity": "person.danny",
                "sleep_entity": "sensor.danny_lader",
                "sleep_state": "wireless",
            }
        ],
        "openings": [{"entity_id": "binary_sensor.achterdeur", "delay": 0}],
    }
    found.update(extra)
    return found


def cold_two_rooms() -> dict[str, tuple[str, dict[str, Any]]]:
    """Return a world where both rooms want heat and somebody is home."""
    return {
        "sensor.woonkamer": ("18.0", {}),
        "sensor.zolder": ("17.0", {}),
        "sensor.buiten": ("4.0", {}),
        LIVING: ("off", {"temperature": 19.0}),
        SPARE: ("off", {"temperature": 19.0}),
        ATTIC: ("off", {"temperature": 19.0}),
        "person.danny": ("home", {}),
        "sensor.danny_lader": ("none", {}),
        "binary_sensor.achterdeur": ("off", {}),
    }


def handed_back(home) -> set[str]:
    """Return the zones handed back, through the coordinator's own reader.

    De coordinator leest bewoners één keer in `build_world` en geeft
    ze door aan `_zones_handed_back`. Deze helper doet hier hetzelfde, zodat de
    tests de methode niet met losse, onderling afwijkende argumenten aanroepen.

    The coordinator reads residents once in `build_world` and
    passes them to `_zones_handed_back`. This helper does the same here, so the
    tests do not call the method with loose, mutually inconsistent arguments.
    """
    coordinator = home.coordinator
    now = coordinator_module.dt_util.now()
    residents = {
        resident.resident_id: coordinator._resident(
            resident.resident_id,
            resident.presence_entity,
            resident.sleep_entity,
            resident.sleep_state,
        )
        for resident in coordinator.config.residents
    }
    return coordinator._zones_handed_back(now, residents)


def summer_house(seasons: dict[str, Any]) -> dict[str, Any]:
    """Return a one-room house that may only cool in the summer."""
    return {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("airco", LIVING, role="heat_cool")],
                cool=settings(22.0, 24.0, seasons=["summer"]),
                heat=settings(21.0, 18.0),
            )
        ],
        "seasons": seasons,
    }


def hot_world() -> dict[str, tuple[str, dict[str, Any]]]:
    """Return a world in which the room is hot enough to want cooling."""
    return {"sensor.woonkamer": ("26.0", {}), LIVING: ("off", {})}


def gated_house(**gates: Any) -> dict[str, Any]:
    """Return a house whose gates can be dialled in per test."""
    return {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("airco", LIVING, role="heat_cool")],
                heat=settings(21.0, 20.0),
            )
        ],
        "residents": [
            {
                "resident_id": "danny",
                "presence_entity": "person.danny",
                "sleep_entity": "sensor.danny_lader",
                "sleep_state": "wireless",
                "windows": [{"start": "07:00:00", "end": "23:00:00"}],
            }
        ],
        "gates": gates,
    }


def cold_at_home() -> dict[str, tuple[str, dict[str, Any]]]:
    """Return a cold room with somebody home and awake."""
    return {
        "sensor.woonkamer": ("18.0", {}),
        LIVING: ("off", {}),
        "person.danny": ("home", {}),
        "sensor.danny_lader": ("none", {}),
    }


def two_room_circuit(**circuit: Any) -> dict[str, Any]:
    """Return two rooms on one outdoor unit, with the circuit dialled in."""
    return {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("woonkamer_airco", LIVING, role="heat_cool")],
                heat=settings(21.0, 20.0),
                cool=settings(22.0, 24.0),
                priority=0,
            ),
            zone(
                "zolder",
                sources=[source("zolder_airco", ATTIC, role="heat_cool")],
                heat=settings(21.0, 20.0),
                cool=settings(22.0, 24.0),
                priority=1,
            ),
        ],
        "circuits": [
            {
                "circuit_id": "buiten",
                "name": "Buiten",
                "units": [LIVING, ATTIC],
                "simultaneous_heat_cool": False,
                **circuit,
            }
        ],
        "seasons": {"source": "summer"},
    }


def opposing_world() -> dict[str, tuple[str, dict[str, Any]]]:
    """Return a world where one room wants heat and the other wants cooling."""
    return {
        "sensor.woonkamer": ("26.0", {}),
        "sensor.zolder": ("18.0", {}),
        LIVING: ("off", {}),
        ATTIC: ("off", {}),
    }


def boiler_house(**generator: Any) -> dict[str, Any]:
    """Return two rooms with valves and one shared boiler."""
    return {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("woonkamer_kraan", LIVING, role="heat_only")],
                heat=settings(21.0, 20.0),
            ),
            zone(
                "keuken",
                sources=[source("keuken_kraan", VALVE, role="heat_only")],
                heat=settings(19.0, 18.0),
                priority=1,
            ),
        ],
        "generators": [
            {
                "generator_id": "ketel",
                "name": "Ketel",
                "entity_id": BOILER,
                "zone_ids": ["woonkamer", "keuken"],
                **generator,
            }
        ],
    }
