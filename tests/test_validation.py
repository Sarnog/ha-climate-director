"""Tests voor alles wat een gebruiker verkeerd kan instellen.

Tests for everything a user can set up wrongly.

Elke controle hier bestaat omdat de fout die hij vangt van buiten niet te
onderscheiden is van "de director besluit niets". Dat is de stilste manier
waarop deze integratie kan falen, en daarom hoort elke instelfout een naam te
krijgen in plaats van een symptoom.

Every check here exists because the mistake it catches is, from the outside,
indistinguishable from "the director decides nothing". That is the quietest way
this integration can fail, so every configuration mistake should get a name
rather than a symptom.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from conftest import house

from custom_components.climate_director.engine import (
    Circuit,
    DirectorConfig,
    ModeSettings,
    Opening,
    Resident,
    Source,
    Zone,
    validate,
)


def problem(config: DirectorConfig, fragment: str) -> bool:
    """Return whether any reported problem mentions `fragment`."""
    return any(fragment in item for item in validate(config))


def zone(zone_id: str, **kwargs: object) -> Zone:
    """Return a workable zone, overridden by whatever the test cares about."""
    settings: dict[str, object] = {
        "indoor_sensor": f"sensor.{zone_id}",
        "sources": (Source(f"{zone_id}_s", f"climate.{zone_id}"),),
        "heat": ModeSettings(21.0, 20.0),
    }
    settings.update(kwargs)
    return Zone(zone_id, zone_id.title(), **settings)  # type: ignore[arg-type]


def test_the_existing_installation_is_still_sound() -> None:
    assert validate(house()) == ()


class TestSharedPriority:
    """Two rooms on one outdoor unit must not hold the same number."""

    def _config(self, first: int, second: int) -> DirectorConfig:
        return DirectorConfig(
            zones=(zone("woonkamer", priority=first), zone("zolder", priority=second)),
            circuits=(
                Circuit(
                    "c",
                    "C",
                    units=("climate.woonkamer", "climate.zolder"),
                    simultaneous_heat_cool=False,
                ),
            ),
        )

    def test_distinct_numbers_are_fine(self) -> None:
        assert not problem(self._config(0, 1), "share priority")

    def test_the_same_number_is_reported(self) -> None:
        assert problem(self._config(0, 0), "share priority")

    def test_rooms_on_separate_circuits_may_share_a_number(self) -> None:
        """They never compete, so making them differ would be a rule without a reason."""
        config = DirectorConfig(
            zones=(zone("woonkamer", priority=0), zone("zolder", priority=0)),
            circuits=(
                Circuit("a", "A", units=("climate.woonkamer",)),
                Circuit("b", "B", units=("climate.zolder",)),
            ),
        )
        assert not problem(config, "share priority")


class TestZonesThatCanNeverAct:
    def test_a_zone_without_an_indoor_sensor(self) -> None:
        assert problem(DirectorConfig(zones=(zone("a", indoor_sensor=""),)), "no indoor")

    def test_a_zone_that_may_neither_heat_nor_cool(self) -> None:
        assert problem(DirectorConfig(zones=(zone("a", heat=None),)), "neither heat nor cool")

    def test_overlapping_switch_on_points(self) -> None:
        """Heating and cooling would ask for the same room at the same moment."""
        config = DirectorConfig(
            zones=(zone("a", heat=ModeSettings(21.0, 22.0), cool=ModeSettings(20.0, 20.0)),)
        )
        assert problem(config, "starts cooling at or below")

    def test_sensible_switch_on_points_are_fine(self) -> None:
        config = DirectorConfig(
            zones=(zone("a", heat=ModeSettings(21.0, 20.0), cool=ModeSettings(23.0, 25.0)),)
        )
        assert not problem(config, "starts cooling")


class TestCircuitsThatCanNeverAct:
    def test_a_capacity_of_zero(self) -> None:
        config = DirectorConfig(
            zones=(zone("a"),),
            circuits=(Circuit("c", "C", units=("climate.a",), max_concurrent_units=0),),
        )
        assert problem(config, "no unit to run at all")

    @pytest.mark.parametrize(
        ("field", "fragment"),
        [
            ("family_switch_delay", "negative family switch delay"),
            ("min_family_switch_interval", "negative minimum switch interval"),
            ("min_cycle_time", "negative minimum cycle time"),
        ],
    )
    def test_a_negative_duration(self, field: str, fragment: str) -> None:
        config = DirectorConfig(
            zones=(zone("a"),),
            circuits=(Circuit("c", "C", units=("climate.a",), **{field: timedelta(seconds=-5)}),),  # type: ignore[arg-type]
        )
        assert problem(config, fragment)


class TestReferencesThatGoNowhere:
    def test_an_opening_naming_an_unknown_zone(self) -> None:
        config = DirectorConfig(
            zones=(zone("a"),),
            openings=(Opening("binary_sensor.door", zone_ids=("kelder",)),),
        )
        assert problem(config, "unknown zone kelder")

    def test_an_opening_naming_a_real_zone(self) -> None:
        config = DirectorConfig(
            zones=(zone("a"),), openings=(Opening("binary_sensor.door", zone_ids=("a",)),)
        )
        assert not problem(config, "unknown zone")

    def test_a_negative_opening_delay(self) -> None:
        config = DirectorConfig(
            zones=(zone("a"),),
            openings=(Opening("binary_sensor.door", delay=timedelta(seconds=-1)),),
        )
        assert problem(config, "negative delay")


class TestResidentsWhoCanNeverBeHome:
    def test_a_resident_without_a_presence_entity(self) -> None:
        """Being home is required outright, so an untracked resident is a mistake."""
        config = DirectorConfig(
            zones=(zone("a"),),
            residents=(Resident("danny", "Danny"),),
        )
        assert problem(config, "can never be home")

    def test_a_tracked_resident_is_fine(self) -> None:
        config = DirectorConfig(
            zones=(zone("a"),),
            residents=(Resident("danny", "Danny", presence_entity="person.danny"),),
        )
        assert not problem(config, "can never be home")


class TestNegativeTimeouts:
    def test_a_negative_presence_timeout(self) -> None:
        config = DirectorConfig(zones=(zone("a", presence_timeout=timedelta(seconds=-1)),))
        assert problem(config, "negative presence timeout")
