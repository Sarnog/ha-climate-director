"""Elke entiteit die de integratie aanmaakt moet een eigen unieke ID hebben.

Every entity the integration creates must have a unique id of its own.

Home Assistant gooit een tweede entiteit met dezelfde unieke ID weg en zet er
een fout bij in het logboek. Dat is stil genoeg om maanden onopgemerkt te
blijven: je mist gewoon een sensor die je nooit gezocht hebt.

Sinds een apparaat onder meerdere zones mag staan - zo ziet een centrale
verwarming eruit - is dat geen theoretisch geval meer.

Home Assistant discards a second entity with the same unique id and logs an
error. That is quiet enough to go unnoticed for months: you simply miss a sensor
you never went looking for.

Since an appliance may sit under several zones - which is what central heating
looks like - that is no longer a theoretical case.
"""

from __future__ import annotations

from custom_components.climate_director.engine import (
    DirectorConfig,
    ModeSettings,
    Source,
    SourceRole,
    Zone,
)

BOILER = "climate.central_boiler"
HEAT = ModeSettings(target=21.0, start_at=20.0, hysteresis=1.0)


def _shared_house() -> DirectorConfig:
    """Return three rooms that all lean on the same boiler, plus their own units."""
    return DirectorConfig(
        zones=tuple(
            Zone(
                zone_id=name,
                name=name.title(),
                indoor_sensor=f"sensor.{name}",
                sources=(
                    Source(source_id=f"{name}_own", entity_id=f"climate.{name}"),
                    Source(
                        source_id=f"{name}_boiler",
                        entity_id=BOILER,
                        role=SourceRole.HEAT_ONLY,
                        priority=1,
                    ),
                ),
                heat=HEAT,
            )
            for name in ("living_room", "attic", "bedroom")
        )
    )


class TestOneSensorPerAppliance:
    """The shared boiler must yield one command sensor, not three."""

    def test_the_appliances_are_counted_once(self) -> None:
        config = _shared_house()
        entities = list(
            dict.fromkeys(source.entity_id for _, source in config.sources() if source.entity_id)
        )
        assert entities.count(BOILER) == 1
        assert len(entities) == 4, entities

    def test_the_source_list_really_does_repeat_it(self) -> None:
        """Guards the test itself: without repetition it proves nothing."""
        config = _shared_house()
        raw = [source.entity_id for _, source in config.sources()]
        assert raw.count(BOILER) == 3

    def test_every_zone_keeps_its_own_sensors(self) -> None:
        """De-duplication must not swallow a room's own appliance."""
        config = _shared_house()
        entities = {source.entity_id for _, source in config.sources()}
        for name in ("living_room", "attic", "bedroom"):
            assert f"climate.{name}" in entities
