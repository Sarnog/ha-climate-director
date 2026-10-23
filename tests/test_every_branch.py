"""Elke tak van het pakket loopt in beide richtingen.

Every branch of the package runs in both directions.

De dekking eist geen enkele gemiste regel én geen enkele halve tak: van elke `if`,
elke lus en elke kortsluiting is ook de andere kant gemeten. Deze module dekt de
kanten die de rest van de suite niet nam - meestal de onschuldige kant van een
verdedigende toets (een opening of bewoner zonder entiteit, een lus die zonder
treffer doorloopt, een standaardwaarde die er al stond). Waar het echte gedrag
niet bij die kant komt, krijgt de toets verzonnen invoer, net als in
`tests/test_reachable_branches.py`; een `pragma: no cover` bestaat in dit pakket
niet.

Coverage demands not a single missed line and not a single half branch: of every
`if`, every loop and every short circuit the other side is measured as well. This
module covers the sides the rest of the suite did not take - mostly the harmless
side of a defensive check (an opening or resident without an entity, a loop that
runs on without a hit, a default value that was already there). Where real
behaviour does not reach that side, the test gets made-up input, just like
`tests/test_reachable_branches.py`; a `pragma: no cover` does not exist in this
package.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from conftest import GAS, LIVING, awake, climate, house, make_world
from test_ha_layer import NOW, FakeState, coordinator

from custom_components.climate_director import schema_fields, schemas, texts
from custom_components.climate_director.config_flow import ClimateDirectorOptionsFlow
from custom_components.climate_director.coordinator import ClimateDirectorCoordinator
from custom_components.climate_director.engine import (
    Circuit,
    DirectorConfig,
    Opening,
    Resident,
    Source,
    SourceRole,
    Zone,
    decide,
)
from custom_components.climate_director.engine.fields import FieldSpec
from custom_components.climate_director.engine.models import _rule_source_covered_zones
from custom_components.climate_director.engine.table_storage import _unwrap

# `engine.decide` is ook de naam van de functie; de module zelf staat in sys.modules.
# `engine.decide` is the function's name too; the module itself is in sys.modules.
decide_module = sys.modules["custom_components.climate_director.engine.decide"]

# -- de options flow ----------------------------------------------------------
# -- the options flow ---------------------------------------------------------


async def test_saving_without_a_visit_to_the_menu_keeps_the_stored_shadow_mode() -> None:
    """Zonder bezoek aan het menu staat er geen schaduwstand; de opslag houdt de zijne."""
    flow = ClimateDirectorOptionsFlow()
    flow.hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_get_known_entry=lambda _entry_id: SimpleNamespace(options={"shadow_mode": True})
        )
    )
    flow.handler = "abc"
    flow._installation = {}
    result = await flow.async_step_save({})
    assert result["type"] == "create_entry"
    assert result["data"] == {"shadow_mode": True, "installation": {}}


def test_dropping_an_item_without_a_zone_id_leaves_the_openings_alone() -> None:
    """Een item zonder zone-id raakt de openingen en generatoren niet aan."""
    flow = ClimateDirectorOptionsFlow()
    flow._installation = {
        "openings": [{"zone_ids": ["woonkamer"]}],
        "generators": [{"zone_ids": ["woonkamer"]}],
    }
    flow._drop_zone_references({})
    assert flow._installation["openings"] == [{"zone_ids": ["woonkamer"]}]
    assert flow._installation["generators"] == [{"zone_ids": ["woonkamer"]}]


# -- de schermen --------------------------------------------------------------
# -- the screens --------------------------------------------------------------


def test_a_choice_without_a_translation_key_shows_its_values() -> None:
    chosen = schema_fields._choices(["a", "b"])
    assert "translation_key" not in chosen.config


def test_a_number_with_a_measure_the_table_does_not_know_is_refused() -> None:
    unknown = FieldSpec(key="x", kind="number", unit="onbekend")
    with pytest.raises(AssertionError, match="onbekend veldtype"):
        schema_fields._selector_for(unknown, SimpleNamespace(hass=None))


def test_a_screen_without_a_footer_carries_only_its_table() -> None:
    field = FieldSpec(key="naam", kind="text")
    schema = schema_fields._table_schema((field,), SimpleNamespace(hass=None), values={})
    assert [str(key) for key in schema.schema] == ["naam"]


def test_a_source_or_generator_without_an_entity_steers_nothing() -> None:
    installation = {
        "zones": [{"sources": [{}, {"entity_id": "climate.a"}]}],
        "generators": [{}, {"entity_id": "climate.b"}],
    }
    assert schemas._managed_entities(installation) == ["climate.a", "climate.b"]


def test_a_registry_entry_without_a_name_falls_back_to_the_source_name() -> None:
    """Een registerinvoer zonder naam laat de naam uit de configuratie staan."""
    config = replace(
        house(),
        zones=(
            replace(
                house().zones[0],
                sources=(replace(house().zones[0].sources[0], name="Airco beneden"),),
            ),
        ),
    )
    registry = SimpleNamespace(
        async_get=lambda _entity_id: SimpleNamespace(name=None, original_name=None)
    )
    hass = SimpleNamespace(data={texts.DATA_REGISTRY: registry})
    assert texts._source_display_name(hass, config, LIVING) == "Airco beneden"


# -- de engine ----------------------------------------------------------------
# -- the engine ---------------------------------------------------------------


def test_a_covered_zone_that_exists_is_no_complaint() -> None:
    config = replace(
        house(),
        zones=(
            replace(
                house().zones[0],
                sources=(
                    replace(house().zones[0].sources[1], covers_zones=("woonkamer", "zolder")),
                ),
            ),
            *house().zones[1:],
        ),
    )
    assert list(_rule_source_covered_zones(config)) == []


def test_a_union_of_two_real_types_stays_as_it_is() -> None:
    assert _unwrap(int | str) == int | str


def test_the_weaker_hand_operated_holder_does_not_take_the_group() -> None:
    """Twee handbediende units draaien in de groep; de sterkste zone houdt hem."""
    strong = Zone(
        zone_id="sterk",
        name="Sterk",
        indoor_sensor="sensor.sterk",
        priority=0,
        sources=(Source(source_id="s", entity_id="climate.s", autostart=False),),
    )
    weak = Zone(
        zone_id="zwak",
        name="Zwak",
        indoor_sensor="sensor.zwak",
        priority=1,
        sources=(Source(source_id="z", entity_id="climate.z", autostart=False),),
    )
    config = DirectorConfig(zones=(strong, weak))
    world = make_world(climates={"climate.s": "heat", "climate.z": "heat"})
    holder = decide_module._group_holder(config, world, frozenset({"climate.s", "climate.z"}))
    assert holder == ("climate.s", (0, "sterk"))


def _unit_zone(zone_id: str, priority: int, *entities: str) -> Zone:
    return replace(
        house().zones[1],
        zone_id=zone_id,
        name=zone_id,
        indoor_sensor=f"sensor.{zone_id}",
        priority=priority,
        sources=tuple(
            Source(source_id=f"{zone_id}_{index}", entity_id=entity, role=SourceRole.HEAT_COOL)
            for index, entity in enumerate(entities)
        ),
    )


def test_every_fallback_round_can_move_a_zone_on() -> None:
    """Elke ronde schuift een zone door; de lus houdt op bij het maximum aantal rondes.

    A neemt de enige plek op circuit 1, dus B schuift door naar circuit 2. Daar
    verdringt B met meer voorrang C, en C schuift in de tweede - en laatste - ronde
    door naar zijn eigen losse unit.
    """
    a = _unit_zone("a", 0, "climate.x")
    b = _unit_zone("b", 1, "climate.y", "climate.w2")
    c = _unit_zone("c", 2, "climate.w1", "climate.v")
    config = replace(
        house(),
        zones=(a, b, c),
        circuits=(
            Circuit(
                circuit_id="een",
                name="Een",
                units=("climate.x", "climate.y"),
                max_concurrent_units=1,
            ),
            Circuit(
                circuit_id="twee",
                name="Twee",
                units=("climate.w1", "climate.w2"),
                max_concurrent_units=1,
            ),
        ),
        openings=(),
    )
    units = ("climate.x", "climate.y", "climate.w1", "climate.w2", "climate.v")
    world = make_world(
        outdoor=10.0,
        indoor=dict.fromkeys(("a", "b", "c"), 15.0),
        residents={"danny": awake(), "nancy": awake()},
        climates=dict.fromkeys(units, "off"),
    )
    plan = decide(config, world)
    chosen = {zone: plan.decision_for(zone).source_id for zone in ("a", "b", "c")}
    assert chosen == {"a": "a_0", "b": "b_1", "c": "c_1"}
    # Dat C na zijn laatste doorschuiving ook echt zijn losse unit krijgt, staat als
    # idee in ROADMAP.md ("Een doorschuiving in de laatste ronde wordt nog
    # opgelost"); deze toets houdt alleen de lus zelf vast.
    # That C really gets its loose unit after its last move on stands as an idea in
    # ROADMAP.md ("A move in the last round still gets resolved"); this test only
    # holds the loop itself.


# -- de koppeling -------------------------------------------------------------
# -- the binding ---------------------------------------------------------------


def test_an_opening_or_resident_without_an_entity_is_not_tracked() -> None:
    config = replace(
        house(),
        openings=(Opening(entity_id=""),),
        residents=(Resident(resident_id="gast", name="Gast"),),
    )
    item = coordinator(config=config)
    tracked = item.tracked_entities()
    assert "" not in tracked


def _presence_event(entity_id: str, old: str, new: str) -> SimpleNamespace:
    return SimpleNamespace(
        data={
            "entity_id": entity_id,
            "old_state": FakeState(old),
            "new_state": FakeState(new, last_changed=NOW + timedelta(minutes=5)),
        }
    )


def test_a_home_resident_whose_state_repeats_keeps_the_moment() -> None:
    """Thuis blijft thuis (bijvoorbeeld een nieuwe gps-positie): geen nieuw moment."""
    item = coordinator()
    item._home_since = {"danny": NOW}
    ClimateDirectorCoordinator._notice_home(item, _presence_event("person.danny", "home", "home"))
    assert item._home_since == {"danny": NOW}


def test_an_away_resident_without_a_moment_stays_without_one() -> None:
    item = coordinator()
    ClimateDirectorCoordinator._notice_home(
        item, _presence_event("person.danny", "not_home", "not_home")
    )
    assert item._home_since == {}


def test_an_occupied_room_that_stays_occupied_has_no_moment() -> None:
    item = coordinator()
    item._notice_room_empty(_presence_event("binary_sensor.zolder", "on", "on"))
    assert item._empty_since == {}


def test_without_a_world_no_opening_is_reported_as_bypassed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reported: list[Any] = []
    monkeypatch.setattr(
        "custom_components.climate_director.problems.async_report_bypassed_openings",
        lambda *args: reported.append(args[-1]),
    )
    item = coordinator()
    ClimateDirectorCoordinator._report_bypassed_openings(item)
    assert reported == [{}]


def test_a_refusal_for_an_unknown_zone_names_no_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Een zone die niet (meer) bestaat heeft geen doeltemperatuur in de zin."""
    monkeypatch.setattr(texts, "lookup", lambda _hass, _code: None)
    item = coordinator()
    item.world = make_world(climates={GAS: climate("off")})
    item._precondition = {"onbekend": NOW}
    data = item._refusal_data("onbekend", None)
    assert data["zone"] == "onbekend"
    assert data["target_temperature"] is None
