"""Gedeelde bouwstenen voor de engine-tests.

Shared building blocks for the engine tests.

De engine importeert geen Home Assistant, dus hier is geen `hass`-fixture
nodig: elk scenario is een gewoon dataobject.

The engine imports no Home Assistant, so no `hass` fixture is needed here:
every scenario is a plain data object.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest

from custom_components.climate_director.engine import (
    Circuit,
    ClimateState,
    DirectorConfig,
    GateSettings,
    ModeSettings,
    Opening,
    OpeningState,
    OutdoorWindow,
    Resident,
    ResidentState,
    Season,
    Source,
    SourceRole,
    WorldState,
    Zone,
)

# Entiteiten uit de bestaande opstelling, zodat scenario's herkenbaar blijven.
# Entities from the existing setup, so scenarios stay recognisable.
GAS = "climate.smart_thermostat_x"
LIVING = "climate.huiskamer"
ATTIC = "climate.zolder"
BEDROOM = "climate.master_bedroom"
BACK_DOOR = "binary_sensor.achterdeur_mc_contact"

MONDAY_NOON = datetime(2026, 8, 10, 12, 0)


def at(hour: int = 12, minute: int = 0, *, day: int = 10) -> datetime:
    """Return a moment in August 2026; the 10th is a Monday."""
    return datetime(2026, 8, day, hour, minute)


def climate(
    mode: str = "off",
    *,
    available: bool = True,
    changed_at: datetime | None = None,
    target: float | None = None,
) -> ClimateState:
    """Return a climate entity state without spelling out every field."""
    return ClimateState(
        hvac_mode=mode,
        available=available,
        changed_at=changed_at,
        target_temperature=target,
    )


def make_world(
    *,
    now: datetime | None = None,
    outdoor: float | None = None,
    season: Season = Season.UNKNOWN,
    indoor: dict[str, float | None] | None = None,
    climates: dict[str, ClimateState | str] | None = None,
    residents: dict[str, ResidentState] | None = None,
    openings: dict[str, OpeningState] | None = None,
    circuit_family_since: dict[str, datetime | None] | None = None,
    master_enabled: bool = True,
    holiday_mode: bool = False,
    zone_overrides: dict[str, bool] | None = None,
) -> WorldState:
    """Return a `WorldState`, accepting bare mode strings for climate entities."""
    resolved = {
        entity_id: climate(state) if isinstance(state, str) else state
        for entity_id, state in (climates or {}).items()
    }
    return WorldState(
        now=now or MONDAY_NOON,
        outdoor_temperature=outdoor,
        season=season,
        indoor_temperatures=dict(indoor or {}),
        climates=resolved,
        residents=dict(residents or {}),
        openings=dict(openings or {}),
        circuit_family_since=dict(circuit_family_since or {}),
        master_enabled=master_enabled,
        holiday_mode=holiday_mode,
        zone_overrides=dict(zone_overrides or {}),
    )


def awake(home: bool = True) -> ResidentState:
    """Return a resident who is up."""
    return ResidentState(home=home, asleep=False)


def asleep(home: bool = True) -> ResidentState:
    """Return a resident who is in bed."""
    return ResidentState(home=home, asleep=True)


def away() -> ResidentState:
    """Return a resident who is out."""
    return ResidentState(home=False, asleep=False)


def everyone_up() -> dict[str, ResidentState]:
    """Return both residents home and awake."""
    return {"danny": awake(), "nancy": awake()}


# ---------------------------------------------------------------------------
# De bestaande opstelling: systeem A uit de ontwerpgesprekken.
# The existing setup: system A from the design discussions.
# ---------------------------------------------------------------------------

#: Drempel waarboven de warmtepomp de gasketel vervangt (input_number.gasverwarming_aan).
GAS_CUTOVER = 3.0

#: Buiten warmer dan dit en verwarmen heeft geen zin
#: (input_number.maximum_buiten_temperatuur_verwarmen_airco).
HEAT_OUTDOOR_MAX = 19.0

#: Buiten kouder dan dit en koelen heeft geen zin
#: (input_number.minimum_buiten_temperatuur_koelen_airco).
COOL_OUTDOOR_MIN = 24.0


def living_room_heat() -> ModeSettings:
    """Return the living room's heating settings.

    `start_at` 22 with a 1.0 band reproduces the summer branch of the original
    automations exactly (on at 22 or below, off at 23 or above) and gives the
    winter branch the dead band it was missing - there, on and off both sat at
    23 and the zone could chatter on that single value.
    """
    return ModeSettings(
        target=23.0,
        start_at=22.0,
        hysteresis=1.0,
        outdoor=OutdoorWindow(maximum=HEAT_OUTDOOR_MAX),
    )


def living_room_cool() -> ModeSettings:
    """Return the living room's cooling settings, summer only."""
    return ModeSettings(
        target=23.0,
        start_at=24.0,
        hysteresis=1.0,
        outdoor=OutdoorWindow(minimum=COOL_OUTDOOR_MIN),
        seasons=frozenset({Season.SUMMER}),
    )


def house() -> DirectorConfig:
    """Return the existing installation: one multi-split plus a gas boiler.

    The boiler sits on no circuit, so it has an outdoor unit to itself by
    definition. The three indoor units share one, and therefore one duty.

    Every heat-pump source carries the same outdoor cutover as the living
    room's. That is what keeps the boiler and the heat pump apart house-wide:
    below the cutover no indoor unit is eligible at all, so the combination the
    old safety automation watched for cannot be assembled.
    """
    living = Zone(
        zone_id="woonkamer",
        name="Woonkamer",
        indoor_sensor="sensor.temperatuur_sensor_woonkamer_selectie",
        priority=0,
        sources=(
            Source(
                source_id="woonkamer_airco",
                entity_id=LIVING,
                role=SourceRole.HEAT_COOL,
                outdoor=OutdoorWindow(minimum=GAS_CUTOVER),
            ),
            Source(
                source_id="gasketel",
                entity_id=GAS,
                role=SourceRole.HEAT_ONLY,
                outdoor=OutdoorWindow(maximum=GAS_CUTOVER),
            ),
        ),
        heat=living_room_heat(),
        cool=living_room_cool(),
    )
    attic = Zone(
        zone_id="zolder",
        name="Zolder",
        indoor_sensor="sensor.zolder_temperatuur",
        priority=1,
        sources=(
            Source(
                source_id="zolder_airco",
                entity_id=ATTIC,
                outdoor=OutdoorWindow(minimum=GAS_CUTOVER),
            ),
        ),
        heat=living_room_heat(),
        cool=living_room_cool(),
    )
    bedroom = Zone(
        zone_id="slaapkamer",
        name="Slaapkamer",
        indoor_sensor="sensor.slaapkamer_temperatuur",
        priority=2,
        sources=(
            Source(
                source_id="slaapkamer_airco",
                entity_id=BEDROOM,
                outdoor=OutdoorWindow(minimum=GAS_CUTOVER),
            ),
        ),
        heat=living_room_heat(),
        cool=living_room_cool(),
    )
    return DirectorConfig(
        zones=(living, attic, bedroom),
        circuits=(
            Circuit(
                circuit_id="multisplit",
                name="Multi-split",
                units=(LIVING, ATTIC, BEDROOM),
                simultaneous_heat_cool=False,
                family_switch_delay=timedelta(seconds=5),
            ),
        ),
        residents=(
            Resident(resident_id="danny", name="Danny"),
            Resident(resident_id="nancy", name="Nancy"),
        ),
        openings=(Opening(entity_id=BACK_DOOR, delay=timedelta(seconds=30)),),
        gates=GateSettings(require_occupancy=True, require_awake=True),
    )


@pytest.fixture
def config() -> DirectorConfig:
    """Return the existing installation as a fixture."""
    return house()


def office_hours() -> tuple:
    """Return a weekday 08:00-18:00 schedule window."""
    from custom_components.climate_director.engine import TimeWindow

    return (TimeWindow(time(8, 0), time(18, 0), frozenset({0, 1, 2, 3, 4})),)
