"""Gas en airco mogen nooit tegelijk draaien in een centrale cv.

Gas and air conditioner may never run together in a central heating system.

Een ketel met `covers_zones` verwarmt zijn hele gebied. Houdt een kamer een airco
vast op de dode band van de buitentemperatuur (net onder het venster van de airco)
terwijl een andere kamer in datzelfde gebied - zonder vorige bron - de ketel kiest,
dan draaien gas en airco naast elkaar. Deze toets zet die situatie na: buiten zakt
van 1,5 naar 1,0 graden bij een venster vanaf 1,1 en een dode band van 0,5.

A boiler with `covers_zones` heats its whole area. If one room holds an air
conditioner on the outdoor dead band (just below the air conditioner's window)
while another room in that area - with no previous source - chooses the boiler,
gas and air conditioner run side by side. This test recreates that situation:
outdoors drops from 1.5 to 1.0 degrees with a window from 1.1 and a dead band of
0.5.
"""

from __future__ import annotations

from datetime import datetime

from conftest import awake, make_world

from custom_components.climate_director.engine import (
    DirectorConfig,
    ModeSettings,
    OutdoorWindow,
    Resident,
    Source,
    SourceRole,
    Zone,
    decide,
)

NOON = datetime(2026, 11, 9, 12, 0)
AIRCO = "climate.huiskamer"
GAS = "climate.ketel"
CUTOVER = 1.1


def _zone(zone_id: str, priority: int, *, airco_source: str, with_airco: bool = True) -> Zone:
    sources = [
        Source(
            f"{zone_id}_gas",
            GAS,
            role=SourceRole.HEAT_ONLY,
            priority=1,
            outdoor=OutdoorWindow(maximum=CUTOVER),
            covers_zones=("woonkamer", "slaapkamer") if zone_id == "woonkamer" else (),
        )
    ]
    if with_airco:
        sources.insert(
            0,
            Source(
                airco_source,
                AIRCO,
                role=SourceRole.HEAT_COOL,
                priority=0,
                outdoor=OutdoorWindow(minimum=CUTOVER),
            ),
        )
    return Zone(
        zone_id,
        zone_id,
        f"sensor.{zone_id}",
        priority=priority,
        sources=tuple(sources),
        heat=ModeSettings(21.0, 20.0, outdoor=OutdoorWindow(maximum=19.0)),
    )


def _config() -> DirectorConfig:
    return DirectorConfig(
        zones=(
            _zone("woonkamer", 0, airco_source="woonkamer_airco"),
            _zone("slaapkamer", 2, airco_source="", with_airco=False),
        ),
        residents=(Resident("danny", presence_entity="person.danny"),),
        outdoor_sensor="sensor.buiten",
        outdoor_hysteresis=0.5,
    )


def _plan(outdoor: float, previous=None, modes=None):
    world = make_world(
        now=NOON,
        outdoor=outdoor,
        indoor={"woonkamer": 15.0, "slaapkamer": 15.0},
        climates=modes or {AIRCO: "off", GAS: "off"},
        residents={"danny": awake()},
    )
    return decide(_config(), world, previous), world


def _running(plan) -> set[str]:
    return {c.entity_id for c in plan.commands if c.hvac_mode not in ("off", "fan_only")}


def test_gas_and_airco_never_both_run() -> None:
    # Buiten 1,5: de woonkamer start op de airco. Het weer zakt naar 1,0: de
    # airco blijft op de dode band, de slaapkamer pakt de ketel.
    first, _ = _plan(1.5)
    assert _running(first) == {AIRCO}
    second, _ = _plan(1.0, first, {AIRCO: "heat", GAS: "off"})
    assert not {AIRCO, GAS} <= _running(second)
