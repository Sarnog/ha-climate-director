"""De grenzen van `takeover.area_clash`: wie wint in het gebied van een ketel, en wie niet.

The borders of `takeover.area_clash`: who wins in a boiler's area, and who does not.

`area_clash` laat per gebied (`covers_zones`) één kant over: het verzoek om de
ketel of de verzoeken van andere apparaten. Deze toetsen leggen elke grens
apart vast, op de functie zelf, zodat een verzonnen wijziging van één vergelijking
of één voorwaarde een eigen rode toets geeft.

`area_clash` leaves one side per area (`covers_zones`): the request for the boiler
or the requests of other appliances. These tests pin down each border on its own,
on the function itself, so that an invented change to one comparison or one
condition turns its own test red.
"""

from __future__ import annotations

from custom_components.climate_director.engine import (
    DirectorConfig,
    ModeFamily,
    ModeSettings,
    Source,
    SourceRole,
    Zone,
)
from custom_components.climate_director.engine import takeover as takeover_module
from custom_components.climate_director.engine.constraints import Request

BOILER = "climate.ketel"
AIRCO_ONE = "climate.airco_een"
AIRCO_TWO = "climate.airco_twee"
HEAT = ModeSettings(21.0, 20.0)


def _zone(zone_id: str, *sources: Source, priority: int = 0) -> Zone:
    return Zone(
        zone_id, zone_id, f"sensor.{zone_id}", priority=priority, sources=sources, heat=HEAT
    )


def _boiler(source_id: str, covers: tuple[str, ...] = ()) -> Source:
    return Source(source_id, BOILER, role=SourceRole.HEAT_ONLY, priority=1, covers_zones=covers)


def _airco(source_id: str, entity_id: str = AIRCO_ONE) -> Source:
    return Source(source_id, entity_id, role=SourceRole.HEAT_COOL, priority=0)


def _house(boiler_covers: tuple[str, ...] = ("a", "b", "c")) -> DirectorConfig:
    """Zone a, b and c; the boiler stands under all three, the airco under b and c."""
    return DirectorConfig(
        zones=(
            _zone("a", _boiler("a_boiler", boiler_covers)),
            _zone("b", _airco("b_airco"), _boiler("b_boiler")),
            _zone("c", _airco("c_airco", AIRCO_TWO), _boiler("c_boiler")),
        )
    )


def _ask(config: DirectorConfig, zone_id: str, source_id: str, priority: int) -> Request:
    zone = config.zone(zone_id)
    source = next(item for item in zone.sources if item.source_id == source_id)
    return Request(zone, source, ModeFamily.HEAT, priority=priority)


def _wishes(*requests: Request) -> dict[str, Request]:
    return {request.zone.zone_id: request for request in requests}


def test_the_boiler_wins_by_priority_and_the_other_appliances_in_the_area_lapse() -> None:
    config = _house()
    boiler = _ask(config, "a", "a_boiler", 0)
    airco = _ask(config, "b", "b_airco", 1)
    other = _ask(config, "c", "c_airco", 2)
    kept, dropped = takeover_module.area_clash(config, _wishes(boiler, airco, other))
    assert kept == {"a": boiler}
    assert dropped == {"b": airco, "c": other}


def test_another_appliance_wins_by_priority_and_every_request_for_the_boiler_lapses() -> None:
    config = _house()
    airco = _ask(config, "b", "b_airco", 0)
    first = _ask(config, "a", "a_boiler", 1)
    second = _ask(config, "c", "c_boiler", 2)
    kept, dropped = takeover_module.area_clash(config, _wishes(airco, first, second))
    assert kept == {"b": airco}
    assert dropped == {"a": first, "c": second}


def test_the_best_owner_is_set_against_the_best_rival_not_the_first() -> None:
    config = _house()
    weak_boiler = _ask(config, "a", "a_boiler", 5)
    airco = _ask(config, "b", "b_airco", 3)
    strong_boiler = _ask(config, "c", "c_boiler", 1)
    kept, dropped = takeover_module.area_clash(config, _wishes(weak_boiler, airco, strong_boiler))
    assert kept == {"a": weak_boiler, "c": strong_boiler}
    assert dropped == {"b": airco}


def test_an_equal_priority_is_decided_by_the_zone_id_and_never_tied() -> None:
    config = _house()
    # The boiler zone sorts first: the boiler wins the tie.
    boiler_zone_first = takeover_module.area_clash(
        config, _wishes(_ask(config, "a", "a_boiler", 0), _ask(config, "b", "b_airco", 0))
    )
    assert set(boiler_zone_first[0]) == {"a"}
    # The airco zone sorts first: the airco wins the tie.
    airco_zone_first = takeover_module.area_clash(
        config, _wishes(_ask(config, "b", "b_airco", 0), _ask(config, "c", "c_boiler", 0))
    )
    assert set(airco_zone_first[0]) == {"b"}
    # No two requests of different zones ever have the same rank.
    assert _ask(config, "a", "a_boiler", 0).rank != _ask(config, "b", "b_airco", 0).rank


def test_a_running_takeover_leaves_its_area_alone() -> None:
    config = _house()
    boiler = _ask(config, "a", "a_boiler", 2)
    airco = _ask(config, "b", "b_airco", 0)
    taking = (
        takeover_module.Takeover(BOILER, frozenset({"a", "b", "c"}), frozenset({ModeFamily.HEAT})),
    )
    kept, dropped = takeover_module.area_clash(config, _wishes(boiler, airco), taking)
    assert kept == {"a": boiler, "b": airco}
    assert dropped == {}


def test_an_area_of_one_zone_has_nothing_to_resolve() -> None:
    config = DirectorConfig(zones=(_zone("a", _boiler("a_boiler", ("a",)), _airco("a_airco")),))
    assert takeover_module.areas(config) == {BOILER: frozenset({"a"})}
    boiler = _ask(config, "a", "a_boiler", 0)
    kept, dropped = takeover_module.area_clash(config, _wishes(boiler))
    assert kept == {"a": boiler}
    assert dropped == {}


def test_without_an_area_nothing_is_resolved() -> None:
    config = DirectorConfig(
        zones=(
            _zone("a", _airco("a_airco")),
            _zone("b", _airco("b_airco", AIRCO_TWO), _boiler("b_boiler")),
        )
    )
    airco = _ask(config, "a", "a_airco", 0)
    boiler = _ask(config, "b", "b_boiler", 1)
    assert takeover_module.areas(config) == {}
    kept, dropped = takeover_module.area_clash(config, _wishes(airco, boiler))
    assert kept == {"a": airco, "b": boiler}
    assert dropped == {}


def test_requests_outside_the_area_are_left_alone() -> None:
    config = DirectorConfig(
        zones=(
            _zone("a", _boiler("a_boiler", ("a", "b"))),
            _zone("b", _airco("b_airco"), _boiler("b_boiler")),
            _zone("c", _airco("c_airco", AIRCO_TWO)),
        )
    )
    boiler = _ask(config, "a", "a_boiler", 0)
    inside = _ask(config, "b", "b_airco", 1)
    outside = _ask(config, "c", "c_airco", 2)
    kept, dropped = takeover_module.area_clash(config, _wishes(boiler, inside, outside))
    assert kept == {"a": boiler, "c": outside}
    assert dropped == {"b": inside}


def test_without_a_rival_or_without_an_owner_nothing_lapses() -> None:
    config = _house()
    only_boilers = _wishes(_ask(config, "a", "a_boiler", 0), _ask(config, "c", "c_boiler", 1))
    assert takeover_module.area_clash(config, only_boilers) == (only_boilers, {})
    only_aircos = _wishes(_ask(config, "b", "b_airco", 0), _ask(config, "c", "c_airco", 1))
    assert takeover_module.area_clash(config, only_aircos) == (only_aircos, {})


def test_the_losers_come_back_instead_of_vanishing_and_the_input_is_untouched() -> None:
    config = _house()
    boiler = _ask(config, "a", "a_boiler", 0)
    airco = _ask(config, "b", "b_airco", 1)
    wishes = _wishes(boiler, airco)
    kept, dropped = takeover_module.area_clash(config, wishes)
    assert dropped["b"] is airco
    assert kept is not wishes
    assert set(wishes) == {"a", "b"}


def test_the_boiler_between_two_rivals_loses_to_the_better_one() -> None:
    config = _house()
    better_airco = _ask(config, "b", "b_airco", 0)
    boiler = _ask(config, "a", "a_boiler", 1)
    worse_airco = _ask(config, "c", "c_airco", 2)
    kept, dropped = takeover_module.area_clash(config, _wishes(better_airco, boiler, worse_airco))
    assert kept == {"b": better_airco, "c": worse_airco}
    assert dropped == {"a": boiler}
