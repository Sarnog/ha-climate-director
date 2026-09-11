"""Anker 8: een overbrugde opening bestaat niet voor de director.

Anchor 8: a bypassed opening does not exist for the director.
"""

from __future__ import annotations

from conftest import BACK_DOOR, at, everyone_up, gate_verdict, house, make_world

from custom_components.climate_director.engine import (
    DirectorConfig,
    Opening,
    OpeningState,
    Reason,
)
from custom_components.climate_director.engine.gates import (
    house_wide_blocked,
    opening_bypassed_and_open,
    opening_standing,
)
from custom_components.climate_director.engine.serialise import (
    config_from_dict,
    config_to_dict,
)


def config_with(bypassable: Opening) -> DirectorConfig:
    """Return the standard house, with `bypassable` as its only opening."""
    base = house()
    return DirectorConfig(
        zones=base.zones,
        circuits=base.circuits,
        residents=base.residents,
        openings=(bypassable,),
        gates=base.gates,
        outdoor_sensor=base.outdoor_sensor,
    )


def world_open(bypassed: bool = False) -> object:
    """Return a world in which the back door has stood open long enough."""
    return make_world(
        now=at(12, 1),
        residents=everyone_up(),
        openings={BACK_DOOR: OpeningState(open=True, changed_at=at(12, 0))},
        opening_bypasses=frozenset({"achterdeur"}) if bypassed else frozenset(),
    )


def test_a_bypassed_opening_does_not_suspend_its_own_zones() -> None:
    config = config_with(Opening(entity_id=BACK_DOOR, opening_id="achterdeur", name="Achterdeur"))
    living = config.zone("woonkamer")
    assert living is not None

    assert gate_verdict(config, world_open(), living).reason is Reason.OPENING_OPEN
    assert gate_verdict(config, world_open(bypassed=True), living).allowed


def test_a_bypassed_opening_does_not_trigger_the_house_wide_stop() -> None:
    config = config_with(Opening(entity_id=BACK_DOOR, opening_id="achterdeur", name="Achterdeur"))
    config = DirectorConfig(
        zones=config.zones,
        circuits=config.circuits,
        residents=config.residents,
        openings=config.openings,
        gates=config.gates,
        outdoor_sensor=config.outdoor_sensor,
        house_wide_openings=("climate.gas",),
    )

    assert house_wide_blocked(config, world_open()) == frozenset({"climate.gas"})
    assert house_wide_blocked(config, world_open(bypassed=True)) == frozenset()


def test_opening_standing_skips_a_bypassed_opening() -> None:
    opening = Opening(entity_id=BACK_DOOR, opening_id="achterdeur", name="Achterdeur")
    assert opening_standing(opening, world_open()) is True
    assert opening_standing(opening, world_open(bypassed=True)) is False


def test_opening_bypassed_and_open_only_holds_for_a_bypassed_open_opening() -> None:
    opening = Opening(entity_id=BACK_DOOR, opening_id="achterdeur", name="Achterdeur")
    assert opening_bypassed_and_open(opening, world_open()) is False
    assert opening_bypassed_and_open(opening, world_open(bypassed=True)) is True


def test_a_closed_bypassed_opening_does_not_report() -> None:
    opening = Opening(entity_id=BACK_DOOR, opening_id="achterdeur", name="Achterdeur")
    world = make_world(
        now=at(12, 1),
        residents=everyone_up(),
        openings={BACK_DOOR: OpeningState(open=False, changed_at=at(12, 0))},
        opening_bypasses=frozenset({"achterdeur"}),
    )
    assert opening_bypassed_and_open(opening, world) is False


def test_legacy_openings_get_their_identity_from_the_entity() -> None:
    """Oude opslag zonder opening_id/naam krijgt de entity_id als identiteit.

    Old storage without an opening id or name gets the entity id as identity.
    """
    raw = {
        "zones": [],
        "openings": [
            {
                "entity_id": "binary_sensor.achterdeur",
                "zone_ids": ["woonkamer"],
                "open_state": "on",
                "delay": 30,
            }
        ],
    }
    config = config_from_dict(raw)
    opening = config.openings[0]
    assert opening.opening_id == "binary_sensor.achterdeur"
    assert opening.name == "binary_sensor.achterdeur"
    # En de tweede passage is stabiel: de identiteit wordt opgeslagen.
    # And the second pass is stable: the identity is stored.
    assert config_from_dict(config_to_dict(config)) == config
