"""Willekeurige installaties helemaal door de keten heen.

Random installations all the way through the chain.

`test_serialise.py` bewaakt dat de lezer niet omvalt op wat er opgeslagen staat.
Dit gaat een stap verder: lezen, terugschrijven, controleren én beslissen, met
een wereld eromheen die net zo raar is. Wat hier stukloopt, loopt bij een
gebruiker stuk terwijl het huis koud staat.

`test_serialise.py` guards that the reader survives whatever is stored. This
goes one step further: read, write back, validate and decide, with a world
around it that is just as odd. What breaks here breaks for a user while the
house sits cold.
"""

from __future__ import annotations

import random

from conftest import climate, make_world

from custom_components.climate_director.engine import decide, validate
from custom_components.climate_director.engine.serialise import (
    config_from_dict,
    config_to_dict,
)

#: Waarden die een JSON-opslag kan bevatten, inclusief de randen.
#: Values a JSON store can hold, edges included.
ODD: tuple[object, ...] = (
    None,
    "",
    0,
    -1,
    3.5,
    True,
    False,
    [],
    {},
    "tekst",
    [1, 2],
    {"a": 1},
    1e400,
    -1e400,
    float("nan"),
    [9, -3, "x"],
    "central",
    "per_zone",
    "onzin",
    -273.15,
    1e12,
    "  ",
    "climate.x",
    ["climate.x"],
    0.0,
    [[]],
    [None],
)

MODES = ("off", "heat", "cool", "dry", "fan_only", "heat_cool", "auto", "", None, 5)


def _odd() -> object:
    return random.choice(ODD)


def _source(index: int) -> dict:
    return {
        "source_id": random.choice([f"s{index}", "", None, 1, _odd()]),
        "entity_id": random.choice(["climate.a", "climate.b", "", None, _odd()]),
        "role": random.choice(["heat_only", "cool_only", "heat_cool", "onzin", None, 3]),
        "priority": _odd(),
        "autostart": random.choice([True, False, None, "ja", 1]),
        "outdoor": random.choice([None, {}, {"minimum": _odd(), "maximum": _odd()}, _odd()]),
    }


def _zone(index: int) -> dict:
    settings = {"target": _odd(), "start_at": _odd(), "hysteresis": _odd()}
    return {
        "zone_id": random.choice([f"z{index}", "", None, 1, _odd()]),
        "name": _odd(),
        "indoor_sensor": random.choice([f"sensor.z{index}", "", None, _odd()]),
        "priority": _odd(),
        "gate": random.choice(["household", "presence", "onzin", None, 7]),
        "presence_timeout": _odd(),
        "sources": random.choice(
            [[_source(i) for i in range(random.randint(0, 3))], None, "x", 3, [_odd()]]
        ),
        "heat": random.choice([None, {}, settings, _odd()]),
        "cool": random.choice([None, {}, settings, _odd()]),
    }


def _stored() -> dict:
    raw = {
        "heating_layout": random.choice(["central", "per_zone", None, 7, "", "CENTRAL", _odd()]),
        "zones": random.choice([[_zone(i) for i in range(random.randint(0, 4))], None, 5, "x"]),
        "circuits": random.choice([None, [], [{"circuit_id": _odd(), "units": _odd()}], 9]),
        "generators": random.choice(
            [None, [], [{"generator_id": _odd(), "entity_id": _odd(), "zone_ids": _odd()}]]
        ),
        "residents": random.choice([None, [], [{"resident_id": _odd(), "windows": _odd()}]]),
        "openings": random.choice([None, [], [{"entity_id": _odd()}]]),
        "gates": random.choice(
            [None, {}, {"quiet_windows": _odd(), "max_precondition": _odd()}, 4]
        ),
        "seasons": random.choice([None, {}, {"source": _odd(), "entity_id": _odd()}]),
        "exclusive_groups": random.choice([None, [], [_odd()], 3]),
        "outdoor_sensor": _odd(),
        "holiday_calendars": _odd(),
        "holiday_keyword": _odd(),
        "stuck_after": _odd(),
    }
    return {key: value for key, value in raw.items() if random.random() < 0.85}


def _world(config):
    entities = {source.entity_id for _, source in config.sources() if source.entity_id}
    entities |= {item.entity_id for item in config.generators if item.entity_id}
    return make_world(
        indoor={
            zone.zone_id: random.choice([18.0, 23.0, 26.0, None, float("nan")])
            for zone in config.zones
        },
        outdoor=random.choice([None, -20.0, 3.0, 5.0, 30.0, float("nan"), 1e12]),
        climates={
            entity_id: climate(
                random.choice(MODES) or "off", available=random.choice([True, True, False])
            )
            for entity_id in entities
        },
        master_enabled=random.choice([True, False]),
        holiday_mode=random.choice([True, False]),
        guest_mode=random.choice([True, False]),
    )


class TestNoInstallationBreaksTheChain:
    """Whatever goes in, a plan comes out - and the plan holds its promises."""

    def test_three_thousand_installations(self) -> None:
        random.seed(4242)
        for _ in range(3_000):
            config = config_from_dict(_stored())
            config_to_dict(config)
            validate(config)
            plan = decide(config, _world(config))

            # Twee tegengestelde opdrachten naar een apparaat is nooit goed; dat
            # is precies de fout die bij een gedeelde thermostaat optrad.
            #
            # Two opposing commands to one appliance is never right; that is
            # exactly the fault a shared thermostat produced.
            steered = [command.entity_id for command in plan.commands]
            assert len(steered) == len(set(steered)), f"dubbele opdracht: {steered}"

            # Elke zone hoort een besluit te krijgen, ook een zone die niets mag.
            # Every zone gets a decision, including one that may do nothing.
            assert len(plan.zones) == len(config.zones)
