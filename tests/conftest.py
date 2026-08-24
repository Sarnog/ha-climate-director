"""Gedeelde bouwstenen voor de engine-tests.

Shared building blocks for the engine tests.

De engine importeert geen Home Assistant, dus hier is geen `hass`-fixture
nodig: elk scenario is een gewoon dataobject.

The engine imports no Home Assistant, so no `hass` fixture is needed here:
every scenario is a plain data object.
"""

from __future__ import annotations

from dataclasses import dataclass
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
    PresenceState,
    Resident,
    ResidentState,
    Season,
    Source,
    SourceRole,
    TimeWindow,
    WorldState,
    Zone,
    gates,
)
from custom_components.climate_director.engine.plan import Reason

# Entiteiten uit de bestaande opstelling, zodat scenario's herkenbaar blijven.
# Entities from the existing setup, so scenarios stay recognisable.
GAS = "climate.smart_thermostat_x"
LIVING = "climate.huiskamer"
ATTIC = "climate.zolder"
BEDROOM = "climate.master_bedroom"
BACK_DOOR = "binary_sensor.achterdeur_mc_contact"

MONDAY_NOON = datetime(2026, 8, 10, 12, 0)


@dataclass(frozen=True, slots=True)
class Verdict:
    """Mag deze zone geregeld worden, en zo niet: welke poort noem je dan.

    May this zone be regulated, and if not: which gate do you name.

    Testgereedschap, geen engine. De engine geeft de hele lijst dichte poorten
    terug, want bij het inrichten wil je ze allemaal zien; deze samenvatting is
    wat de tests hieronder prettig leest. Hij stond ooit in de engine zelf en
    werd daar door niets gebruikt.

    Test tooling, not engine. The engine returns the whole list of shut gates,
    since while setting things up you want to see them all; this summary is what
    reads pleasantly in the tests below. It used to live in the engine itself,
    where nothing used it.
    """

    allowed: bool
    reason: Reason | None = None


def gate_verdict(config, world, zone, previous=None) -> Verdict:
    """Return whether `zone` may run, naming the gate a user would name first."""
    reason = next(iter(gates.closed(config, world, zone, previous)), None)
    return Verdict(reason is None, reason)


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
    presence: dict[str, PresenceState] | None = None,
    circuit_family_since: dict[str, datetime | None] | None = None,
    master_enabled: bool = True,
    holiday_mode: bool = False,
    guest_mode: bool = False,
    precondition_until: dict[str, datetime] | None = None,
    precondition_bypass: frozenset[str] = frozenset(),
    zone_overrides: dict[str, bool] | None = None,
    zone_priorities: dict[str, int] | None = None,
    precipitation: bool = False,
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
        presence=dict(presence or {}),
        circuit_family_since=dict(circuit_family_since or {}),
        master_enabled=master_enabled,
        holiday_mode=holiday_mode,
        guest_mode=guest_mode,
        precondition_until=dict(precondition_until or {}),
        precondition_bypass=precondition_bypass,
        zone_overrides=dict(zone_overrides or {}),
        zone_priorities=dict(zone_priorities or {}),
        precipitation=precipitation,
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
            # De entiteiten waar de koppelingslaag ze mee uitleest. De engine
            # raakt ze nooit aan, maar zonder aanwezigheidsentiteit kan een
            # bewoner nooit thuis zijn, en daar klaagt `validate()` terecht over.
            #
            # The entities the binding layer reads them with. The engine never
            # touches them, but without a presence entity a resident can never
            # be home, which `validate()` rightly complains about.
            Resident(
                resident_id="danny",
                name="Danny",
                presence_entity="person.danny",
                sleep_entity="sensor.danny_charger_type",
                sleep_state="wireless",
            ),
            Resident(
                resident_id="nancy",
                name="Nancy",
                presence_entity="person.nancy",
                sleep_entity="sensor.nancy_charger_type",
                sleep_state="wireless",
            ),
        ),
        openings=(Opening(entity_id=BACK_DOOR, delay=timedelta(seconds=30)),),
        gates=GateSettings(require_awake=True),
        # De engine leest deze entiteit nooit zelf - de koppelingslaag doet dat
        # en zet het resultaat in `WorldState`. Hij hoort hier omdat elk
        # begrensd buitenvenster in deze opstelling zonder buitentemperatuur
        # nooit voldaan kan worden, en `validate()` daar terecht over klaagt.
        #
        # The engine never reads this entity itself - the binding layer does and
        # puts the result in `WorldState`. It belongs here because every bounded
        # outdoor window in this setup can never be satisfied without an outdoor
        # temperature, which `validate()` rightly complains about.
        outdoor_sensor="sensor.buienradar_temperature",
    )


@pytest.fixture
def config() -> DirectorConfig:
    """Return the existing installation as a fixture."""
    return house()


def office_hours() -> tuple:
    """Return a weekday 08:00-18:00 schedule window."""

    return (TimeWindow(time(8, 0), time(18, 0), frozenset({0, 1, 2, 3, 4})),)


# ---------------------------------------------------------------------------
# De beloftes die elk plan moet houden, welke installatie er ook onder ligt.
# The promises every plan must keep, whatever installation lies under it.
# ---------------------------------------------------------------------------


def assert_plan_holds(config, world, plan, where: str = "") -> None:
    """Assert what may never come out of `decide()`, for any configuration.

    Bedoeld voor de brede tests die duizenden willekeurige installaties en een
    hele maand doorlopen: die kunnen niet per geval een verwachting opschrijven,
    dus leggen ze vast wat er nooit uit mag komen. Wat hier stukloopt, loopt bij
    een gebruiker stuk terwijl het huis koud staat.

    Meant for the broad tests that walk thousands of random installations and a
    whole month: those cannot write down an expectation per case, so they pin
    down what may never come out. What breaks here breaks for a user while the
    house sits cold.
    """
    from custom_components.climate_director.engine import ModeFamily
    from custom_components.climate_director.engine.families import family_of

    mark = f"{where}: " if where else ""

    steered = [command.entity_id for command in plan.commands]
    assert len(steered) == len(set(steered)), f"{mark}twee opdrachten voor een apparaat"

    known = {source.entity_id for _, source in config.sources() if source.entity_id}
    known |= {item.entity_id for item in config.generators if item.entity_id}
    assert set(steered) <= known, f"{mark}opdracht naar een onbekend apparaat"

    assert len(plan.zones) == len(config.zones), f"{mark}niet elke zone kreeg een besluit"
    assert len({zone.zone_id for zone in plan.zones}) == len(plan.zones), (
        f"{mark}een zone kreeg twee besluiten"
    )

    left = {item.entity_id for item in plan.untouched}
    assert not left & set(steered), f"{mark}apparaat in beide lijsten"

    # Een zone die is overgedragen krijgt niets, ook geen uit - tenzij het
    # apparaat gedeeld wordt met een zone die wel meedoet.
    #
    # A zone handed over gets nothing, an off included - unless the appliance is
    # shared with a zone that does take part.
    for zone in config.zones:
        if not world.overridden(zone.zone_id):
            continue
        for source in zone.sources:
            shared = any(
                other.zone_id != zone.zone_id
                and not world.overridden(other.zone_id)
                and any(item.entity_id == source.entity_id for item in other.sources)
                for other in config.zones
            )
            if not shared:
                assert plan.command_for(source.entity_id) is None, (
                    f"{mark}{zone.zone_id} is overgedragen en kreeg toch een opdracht"
                )

    # Een bron die overal handbediend is, wordt nooit gestart.
    # A source that is hand-operated everywhere is never started.
    owners: dict[str, list] = {}
    for _, source in config.sources():
        owners.setdefault(source.entity_id, []).append(source)
    for entity_id, sources in owners.items():
        if any(source.autostart for source in sources):
            continue
        command = plan.command_for(entity_id)
        if command is not None:
            assert family_of(command.hvac_mode) is ModeFamily.NEUTRAL, (
                f"{mark}handbediende {entity_id} werd gestart"
            )

    # Een zone met een dichte poort draait nooit.
    # A zone with a shut gate never runs.
    for decision in plan.zones:
        if decision.closed_gates:
            assert decision.granted is ModeFamily.NEUTRAL, (
                f"{mark}{decision.zone_id} draait terwijl {decision.closed_gates} dicht staat"
            )

    for circuit in config.circuits:
        if circuit.simultaneous_heat_cool:
            continue

        ordered = {
            family_of(command.hvac_mode)
            for command in plan.commands
            if command.entity_id in circuit.units
        } & {ModeFamily.HEAT, ModeFamily.COOL}
        assert len(ordered) <= 1, f"{mark}{circuit.circuit_id} krijgt {ordered} tegelijk"

        if circuit.max_concurrent_units is None:
            continue

        # De grens gaat over wat de director erbij zet. Staan er al meer units
        # te draaien dan de buitenunit aankan, dan heeft een mens dat gedaan -
        # met een afstandsbediening, een override of een handbediend apparaat -
        # en daar mag de director niets meer bovenop doen. Hij mag er dan ook
        # niet dwars voor gaan liggen: een override uitzetten is precies wat een
        # override niet is.
        #
        # The limit is about what the director adds. If more units already run
        # than the outdoor unit can take, a person did that - with a remote, an
        # override or a hand-operated appliance - and the director may add
        # nothing on top. Nor may it get in the way: switching an override off
        # is exactly what an override is not.
        put_to_work = {
            command.entity_id
            for command in plan.commands
            if command.entity_id in circuit.units
            and family_of(command.hvac_mode) in (ModeFamily.HEAT, ModeFamily.COOL)
        }
        left_running = {
            entity_id
            for entity_id in circuit.units
            if entity_id not in {command.entity_id for command in plan.commands}
            and world.climate(entity_id).running
        }
        assert not put_to_work or len(put_to_work | left_running) <= circuit.max_concurrent_units, (
            f"{mark}director zet {sorted(put_to_work)} aan terwijl {sorted(left_running)} al "
            f"draait op een circuit voor {circuit.max_concurrent_units}"
        )
