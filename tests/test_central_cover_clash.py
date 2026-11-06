"""Gas en airco mogen nooit tegelijk draaien in een centrale cv.

Gas and air conditioner may never run together in a central heating system.

Productie, 6 november 07:07: de woonkamer hield `climate.huiskamer` (airco) vast
op de dode band van de buitentemperatuur (1,0 graden, venster vanaf 1,1), terwijl
de slaapkamer - zonder vorige bron - de gasketel koos. De ketel verwarmt het hele
huis (`covers_zones`), dus draaiden gas en airco naast elkaar tot de
veiligheidsautomatisering alles uitzette.

Production, 6 November 07:07: the living room held `climate.huiskamer` (air
conditioner) on the outdoor dead band (1.0 degrees, window from 1.1), while the
bedroom - with no previous source - chose the boiler. The boiler heats the whole
house (`covers_zones`), so gas and air conditioner ran side by side until the
safety automation switched everything off.
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
