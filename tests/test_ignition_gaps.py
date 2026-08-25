"""De ontstekingsgrens meet het gat tussen twee ontstekingen, niet het aantal.

The ignition boundary measures the gap between two ignitions, not the count.

De opgetilde invariant uit `a972579` telde ontstekingen per uur; met een
tijdstap van tien minuten kan die telling de grens voor een apparaat zonder
circuit (twintig per uur) nooit bereiken, en twee ontstekingen twee minuten na
elkaar telt hij sowieso niet. Deze simulatie draait daarom op een tijdstap van
één minuut - fijn genoeg om een gat van twee minuten te kúnnen zien - en pint
vast dat de ontstekingsgrens daarmee écht kan falen.

The lifted invariant from `a972579` counted ignitions per hour; with a
ten-minute time step that count can never reach the boundary for an appliance
without a circuit (twenty per hour), and two ignitions two minutes apart are not
counted anyway. This simulation therefore runs on a one-minute time step - fine
enough to be able to see a two-minute gap - and pins down that the ignition
boundary can then really fail.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

import pytest
from simulation import Profile, Scenario, Simulation

from custom_components.climate_director.engine import (
    Circuit,
    DirectorConfig,
    Generator,
    ModeSettings,
    Opening,
    Season,
    Source,
    SourceRole,
    Zone,
)
from custom_components.climate_director.engine.gates import OPENING_MIN_REST

GAS = "climate.cv_ketel"
CV = "climate.cv"
UNIT_A = "climate.unit_a"
UNIT_B = "climate.unit_b"
DOOR = "binary_sensor.deur"
START = datetime(2026, 1, 12, 6, 0)
FINE_STEP = timedelta(minutes=1)


def fine_house() -> DirectorConfig:
    """Return one room heated by a circuit-less boiler behind one door."""
    heat = ModeSettings(target=21.0, start_at=20.0, hysteresis=1.0)
    return DirectorConfig(
        zones=(
            Zone(
                zone_id="woonkamer",
                name="Woonkamer",
                indoor_sensor="sensor.woonkamer",
                sources=(Source(source_id="ketel", entity_id=GAS, role=SourceRole.HEAT_ONLY),),
                heat=heat,
            ),
        ),
        openings=(Opening(entity_id=DOOR),),
        outdoor_sensor="sensor.buiten",
    )


def fine_weather(now: datetime, rng: random.Random) -> tuple[float, Season]:
    """Return a steady frost: the boiler is the only candidate all along."""
    return 2.0, Season.WINTER


#: Elke willekeurige gebeurtenis uit, zodat de deur hieronder met de hand
#: bestuurd kan worden en de simulatie volledig deterministisch is.
#:
#: Every random event switched off, so the door below can be driven by hand and
#: the simulation is fully deterministic.
STILL = Profile(
    leaving=0.0,
    returning=0.0,
    turning_in=0.0,
    getting_up=0.0,
    window_opens=0.0,
    window_closes=0.0,
    presence_flips=0.0,
    master=0.0,
    master_back=0.0,
    holiday=0.0,
    holiday_back=0.0,
    guest=0.0,
    guest_back=0.0,
    override=0.0,
    override_back=0.0,
    priority=0.0,
    drops_out=0.0,
    comes_back=0.0,
    by_hand=0.0,
    requests=0.0,
    cancels=0.0,
)

FINE_SCENARIO = Scenario(
    name="fijne-ontstekingsstap",
    config=fine_house(),
    start=START,
    start_indoor={"woonkamer": 18.0},
    weather=fine_weather,
    profile=STILL,
    days=1,
    step=FINE_STEP,
    check_ignition_brakes=True,
)


class TestTheFineSimulationChecksIgnitionGaps:
    """De grens die het moet bewaken, is met deze tijdstap ook werkelijk te overschrijden.

    The boundary it has to guard can really be exceeded with this time step.
    """

    def test_the_step_can_observe_the_opening_rest(self) -> None:
        if FINE_SCENARIO.step * 2 >= OPENING_MIN_REST:
            pytest.fail(
                f"een tijdstap van {FINE_SCENARIO.step} kan een rust van "
                f"{OPENING_MIN_REST} niet waarnemen: de ontstekingsgrens zou loos zijn"
            )

    def test_a_flapping_door_holds_the_gap_between_ignitions(self) -> None:
        simulation = Simulation(FINE_SCENARIO, seed=20260824)
        for minute in range(12):
            # De deur klappert: om en om open en dicht, elke minuut.
            # The door flaps: open and shut in turn, every minute.
            door_open = minute % 2 == 1
            simulation.open[DOOR] = door_open
            simulation.opened_at[DOOR] = simulation.now
            simulation.step()

        starts = simulation.starts[GAS]
        assert len(starts) >= 2, (
            f"de fijne simulatie ontstak de ketel {len(starts)} keer; "
            "zonder twee ontstekingen vergelijkt de grens niets"
        )
        for first, second in zip(starts, starts[1:], strict=False):
            assert second - first >= OPENING_MIN_REST, (
                f"de ketel ontsteekt {second - first} na de vorige start, "
                f"terwijl {OPENING_MIN_REST} rust moet"
            )


def fine_generator_house(satisfied: str, cold: str) -> DirectorConfig:
    """Return two rooms on one multi-split, plus a shared heat source.

    R14 zat uitsluitend in het generatorpad: één kamer op temperatuur, de deur
    bij de koude kamer, en een gedeelde warmtebron die beide kamers bedient. De
    fijne simulatie hierboven kent geen generator, dus zij zag dat pad niet.

    R14 lived solely in the generator path: one room at temperature, the door at
    the cold room, and a shared heat source serving both rooms. The fine
    simulation above has no generator, so it could not see that path.
    """

    def room(zone_id: str, unit: str, priority: int) -> Zone:
        return Zone(
            zone_id=zone_id,
            name=zone_id,
            indoor_sensor=f"sensor.{zone_id}",
            priority=priority,
            sources=(
                Source(
                    source_id=f"{zone_id}_unit",
                    entity_id=unit,
                    role=SourceRole.HEAT_COOL,
                ),
            ),
            heat=ModeSettings(target=21.0, start_at=20.0, hysteresis=1.0),
        )

    return DirectorConfig(
        zones=(room("woonkamer", UNIT_A, 0), room("zolder", UNIT_B, 1)),
        circuits=(
            Circuit(
                circuit_id="multi",
                name="Multi",
                units=(UNIT_A, UNIT_B),
                min_cycle_time=timedelta(0),
            ),
        ),
        generators=(Generator(generator_id="cv", name="CV", entity_id=CV),),
        openings=(Opening(entity_id=DOOR, zone_ids=(cold,)),),
        outdoor_sensor="sensor.buiten",
    )


class TestTheFineSimulationSeesTheGeneratorsOpeningRest:
    """De fijne ontstekingsstap bewaakt ook de gedeelde warmtebron.

    R14 is op het generatorpad gerepareerd, maar `fine_house()` heeft geen
    generator: de fijne stap bewaakte precies het bronpad dat al dicht was. Dit
    scenario zet dezelfde fijne stap naast een generator met één kamer op
    temperatuur en de deur bij de koude kamer - het scenario waar R14 in zat.

    The fine ignition step also guards the shared heat source.

    R14 was repaired on the generator path, but `fine_house()` has no generator:
    the fine step guarded exactly the source path that was already closed. This
    scenario puts the same fine step next to a generator with one room at
    temperature and the door at the cold room - the scenario R14 lived in.
    """

    @pytest.mark.parametrize(
        ("satisfied", "cold"),
        [("woonkamer", "zolder"), ("zolder", "woonkamer")],
        ids=["woonkamer_tevreden", "zolder_tevreden"],
    )
    def test_a_flapping_door_holds_the_generators_gap(self, satisfied: str, cold: str) -> None:
        scenario = Scenario(
            name=f"fijne-ontstekingsstap-generator-{satisfied}-tevreden",
            config=fine_generator_house(satisfied=satisfied, cold=cold),
            start=START,
            start_indoor={satisfied: 21.5, cold: 18.5},
            weather=fine_weather,
            profile=STILL,
            days=1,
            step=FINE_STEP,
            check_ignition_brakes=True,
        )
        simulation = Simulation(scenario, seed=20260825)
        for minute in range(20):
            # De deur klappert: om en om open en dicht, elke minuut.
            # The door flaps: open and shut in turn, every minute.
            door_open = minute % 2 == 1
            simulation.open[DOOR] = door_open
            simulation.opened_at[DOOR] = simulation.now
            simulation.step()

        starts = simulation.starts[CV]
        assert len(starts) >= 2, (
            f"de fijne simulatie ontstak de gedeelde warmtebron {len(starts)} keer; "
            "zonder twee ontstekingen vergelijkt de grens niets"
        )
        for first, second in zip(starts, starts[1:], strict=False):
            assert second - first >= OPENING_MIN_REST, (
                f"de gedeelde warmtebron ontsteekt {second - first} na de vorige start, "
                f"terwijl {OPENING_MIN_REST} rust moet"
            )
