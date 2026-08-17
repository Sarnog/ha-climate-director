"""Centrale verwarming tegenover een gezoneerd systeem.

Central heating against a zoned system.

Bij een gesloten systeem staat dezelfde thermostaat als bron onder meerdere
zones. De opdrachten worden per zone opgebouwd, dus zo'n apparaat kreeg er een
van elke zone - en die spreken elkaar tegen zodra de ene kamer warmte vraagt en
de andere niets. Welke er won hing af van de sorteervolgorde: toeval, geen
ontwerp.

With a closed system the same thermostat sits as a source under several zones.
Commands are built per zone, so such an appliance got one from each - and they
contradict each other the moment one room asks for heat and the other does not.
Which one won depended on sort order: chance, not design.
"""

from __future__ import annotations

from conftest import climate, make_world

from custom_components.climate_director.engine import (
    MODE_HEAT,
    MODE_OFF,
    DirectorConfig,
    HeatingLayout,
    ModeSettings,
    Source,
    SourceRole,
    Zone,
    decide,
    validate,
)
from custom_components.climate_director.engine.serialise import (
    config_from_dict,
    config_to_dict,
)

HEAT = ModeSettings(target=21.0, start_at=20.0, hysteresis=1.0)
THERMOSTAT = "climate.thermostat"


def zone(zone_id: str, *sources: Source, priority: int = 0) -> Zone:
    """Return one room."""
    return Zone(
        zone_id=zone_id,
        name=zone_id,
        indoor_sensor=f"sensor.{zone_id}",
        priority=priority,
        sources=sources,
        heat=HEAT,
    )


def shared(source_id: str = "central") -> Source:
    """Return the one thermostat that heats the whole house."""
    return Source(source_id=source_id, entity_id=THERMOSTAT, role=SourceRole.HEAT_ONLY)


def house(**temperatures: float):
    """Return a world at the given indoor temperatures, cold outside."""
    return make_world(
        indoor=dict(temperatures),
        outdoor=5.0,
        climates={THERMOSTAT: climate("off")},
    )


class TestOneAppliance:
    """A shared source gets exactly one command, whatever the zones want."""

    config = DirectorConfig(
        zones=(
            zone("living_room", shared("central_lr"), priority=0),
            zone("bedroom", shared("central_br"), priority=1),
        ),
        heating_layout=HeatingLayout.CENTRAL,
    )

    def test_one_room_cold_the_other_warm(self) -> None:
        """The old behaviour sent both `off` and `heat` to the same entity."""
        plan = decide(self.config, house(living_room=18.0, bedroom=23.0))
        for_thermostat = [c for c in plan.commands if c.entity_id == THERMOSTAT]
        assert len(for_thermostat) == 1, for_thermostat
        assert for_thermostat[0].hvac_mode == MODE_HEAT

    def test_demand_beats_silence_whichever_room_asks(self) -> None:
        """A closed system cannot heat one room and not the other."""
        plan = decide(self.config, house(living_room=23.0, bedroom=18.0))
        for_thermostat = [c for c in plan.commands if c.entity_id == THERMOSTAT]
        assert len(for_thermostat) == 1
        assert for_thermostat[0].hvac_mode == MODE_HEAT

    def test_nobody_asking_switches_it_off(self) -> None:
        plan = decide(self.config, house(living_room=23.0, bedroom=23.0))
        for_thermostat = [c for c in plan.commands if c.entity_id == THERMOSTAT]
        assert len(for_thermostat) == 1
        assert for_thermostat[0].hvac_mode == MODE_OFF

    def test_the_leading_room_is_the_one_with_most_claim(self) -> None:
        """Two rooms asking at once: the appliance follows the ranking zone."""
        plan = decide(self.config, house(living_room=18.0, bedroom=18.0))
        command = next(c for c in plan.commands if c.entity_id == THERMOSTAT)
        assert command.zone_id == "living_room"


class TestTheChoiceIsRecorded:
    """The setting survives a save, and an old installation is not guessed at twice."""

    def test_it_round_trips(self) -> None:
        for layout in HeatingLayout:
            config = DirectorConfig(zones=(zone("a", shared()),), heating_layout=layout)
            assert config_from_dict(config_to_dict(config)).heating_layout is layout

    def test_an_old_installation_with_a_shared_source_reads_as_central(self) -> None:
        """Inferred, so upgrading never raises a warning about a choice never made."""
        stored = {
            "zones": [
                {"zone_id": "a", "sources": [{"source_id": "s1", "entity_id": THERMOSTAT}]},
                {"zone_id": "b", "sources": [{"source_id": "s2", "entity_id": THERMOSTAT}]},
            ]
        }
        assert config_from_dict(stored).heating_layout is HeatingLayout.CENTRAL

    def test_an_old_installation_with_its_own_appliances_reads_as_zoned(self) -> None:
        stored = {
            "zones": [
                {"zone_id": "a", "sources": [{"source_id": "s1", "entity_id": "climate.a"}]},
                {"zone_id": "b", "sources": [{"source_id": "s2", "entity_id": "climate.b"}]},
            ]
        }
        assert config_from_dict(stored).heating_layout is HeatingLayout.PER_ZONE

    def test_a_stored_choice_beats_the_guess(self) -> None:
        """Once chosen, nothing infers over it."""
        stored = {
            "heating_layout": "per_zone",
            "zones": [
                {"zone_id": "a", "sources": [{"source_id": "s1", "entity_id": THERMOSTAT}]},
                {"zone_id": "b", "sources": [{"source_id": "s2", "entity_id": THERMOSTAT}]},
            ],
        }
        assert config_from_dict(stored).heating_layout is HeatingLayout.PER_ZONE

    def test_nonsense_falls_back_to_the_guess(self) -> None:
        assert config_from_dict({"heating_layout": 7}).heating_layout is HeatingLayout.PER_ZONE


class TestTheCheckWarns:
    """A warning, never a block: the director keeps regulating either way."""

    def test_zoned_but_wired_centrally(self) -> None:
        config = DirectorConfig(
            zones=(zone("a", shared("s1")), zone("b", shared("s2"))),
            heating_layout=HeatingLayout.PER_ZONE,
        )
        found = validate(config)
        assert any(getattr(item, "code", "") == "layout_zoned_with_shared_source" for item in found)

    def test_central_but_wired_per_room(self) -> None:
        config = DirectorConfig(
            zones=(
                zone("a", Source(source_id="s1", entity_id="climate.a")),
                zone("b", Source(source_id="s2", entity_id="climate.b")),
            ),
            heating_layout=HeatingLayout.CENTRAL,
        )
        found = validate(config)
        assert any(
            getattr(item, "code", "") == "layout_central_without_shared_source" for item in found
        )

    def test_a_matching_installation_is_quiet(self) -> None:
        for layout, sources in (
            (HeatingLayout.CENTRAL, (shared("s1"), shared("s2"))),
            (
                HeatingLayout.PER_ZONE,
                (
                    Source(source_id="s1", entity_id="climate.a"),
                    Source(source_id="s2", entity_id="climate.b"),
                ),
            ),
        ):
            config = DirectorConfig(
                zones=(zone("a", sources[0]), zone("b", sources[1])),
                heating_layout=layout,
            )
            codes = [getattr(item, "code", "") for item in validate(config)]
            assert not [code for code in codes if code.startswith("layout_")], (layout, codes)

    def test_one_zone_is_never_wrong(self) -> None:
        """With a single room the distinction has no meaning yet."""
        for layout in HeatingLayout:
            config = DirectorConfig(zones=(zone("a", shared()),), heating_layout=layout)
            codes = [getattr(item, "code", "") for item in validate(config)]
            assert not [code for code in codes if code.startswith("layout_")]

    def test_a_cooling_only_shared_appliance_does_not_count(self) -> None:
        """This is about heating; a shared cooler says nothing about the layout."""
        cooler = Source(source_id="chiller", entity_id="climate.chiller", role=SourceRole.COOL_ONLY)
        config = DirectorConfig(
            zones=(
                zone("a", Source(source_id="s1", entity_id="climate.a"), cooler),
                zone("b", Source(source_id="s2", entity_id="climate.b"), cooler),
            ),
            heating_layout=HeatingLayout.PER_ZONE,
        )
        codes = [getattr(item, "code", "") for item in validate(config)]
        assert "layout_zoned_with_shared_source" not in codes
