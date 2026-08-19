"""Een maand draaien, met alles erop en eraan.

Running for a month, with everything switched on.

Elke andere test doet één beslissing op een stilstaande wereld. Deze laat de
beslissing terugwerken op het huis: wat de director aanzet gaat draaien, wat
draait warmt de kamer op, en de volgende beslissing kijkt naar het resultaat
van de vorige. Pas dan gaan de dingen tellen die alleen in de tijd bestaan -
minimale looptijd, omschakelpauze, kortcyclusbescherming, een uitzetting die
tot de volgende dag geldt, een vooruit-verzoek dat afloopt.

Dertig dagen in stappen van tien minuten, met bewoners die komen en gaan en
slapen, ramen die opengaan, apparaten die met de hand worden aangeraakt, een
seizoen dat omslaat, sensoren die wegvallen, en een buitentemperatuur die van
vorst naar hittegolf loopt, zodat zowel de gasketel als de airco's aan bod
komen.

De zaadwaarde staat vast: een test die de ene keer wel en de andere keer niet
faalt is geen test. Loopt hij stuk, dan is het scenario exact na te spelen.

Every other test makes one decision about a world standing still. This one lets
the decision feed back into the house: what the director switches on runs, what
runs warms the room, and the next decision looks at the result of the previous
one. Only then do the things that exist solely in time start to count - minimum
run, switch pause, short-cycle protection, a hand-back that holds until the next
day, a pre-conditioning request running out.

Thirty days in ten-minute steps, with residents coming and going and sleeping,
windows opening, appliances touched by hand, a season turning over, sensors
dropping out, and an outdoor temperature running from frost to heatwave, so both
the boiler and the air conditioners get their turn.

The seed is fixed: a test that fails sometimes is no test. If it breaks, the
scenario replays exactly.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, time, timedelta

import pytest
from simulation import Scenario, Simulation, run_month

from custom_components.climate_director.engine import (
    Circuit,
    ConflictPolicy,
    DirectorConfig,
    GateSettings,
    Generator,
    ModeSettings,
    Opening,
    OutdoorWindow,
    Reason,
    Resident,
    Season,
    Source,
    SourceRole,
    TimeWindow,
    Zone,
    validate,
)

# ---------------------------------------------------------------------------
# De installatie: alles wat de integratie kan, in één huis.
# The installation: everything the integration can do, in one house.
# ---------------------------------------------------------------------------

LIVING = "climate.woonkamer_airco"
ATTIC = "climate.zolder_airco"
BEDROOM = "climate.slaapkamer_airco"
BOILER = "climate.gasketel"
PUMP = "climate.vloerverwarming"

BACK_DOOR = "binary_sensor.achterdeur"
ROOF_WINDOW = "binary_sensor.dakraam"

DANNY = "person.danny"
NANCY = "person.nancy"
DANNY_SLEEP = "sensor.danny_lader"
NANCY_SLEEP = "sensor.nancy_lader"
ATTIC_PRESENCE = "binary_sensor.zolder_aanwezig"

#: De grens waar gas het van de warmtepompen overneemt.
#: The boundary where gas takes over from the heat pumps.
CUTOVER = 3.1

STEP = timedelta(minutes=10)
DAYS = 30
START = datetime(2026, 2, 1, 0, 0)

WEEK = frozenset({0, 1, 2, 3, 6})
WEEKEND = frozenset({4, 5})


def house() -> DirectorConfig:
    """Return an installation using every feature at once.

    Drie zones op één multi-split, een gasketel als tweede bron in alle drie,
    een vloerverwarmingsgroep als generator, uitsluitende groepen tussen de
    handbediende slaapkamer en elk gasverzoek, roosters, slaapvensters,
    stiltevensters, aanwezigheid per kamer, capaciteit, kortcyclus en
    omschakelpauzes. Wat hier niet in zit, bestaat niet.

    Three zones on one multi-split, a gas boiler as second source in all three,
    an underfloor group as generator, exclusive groups between the hand-operated
    bedroom and every gas request, schedules, sleep windows, quiet windows,
    per-room presence, capacity, short-cycle and switch pauses. What is not in
    here does not exist.
    """
    warm = ModeSettings(
        target=21.0,
        start_at=20.0,
        hysteresis=1.0,
        outdoor=OutdoorWindow(maximum=19.0),
    )
    cold = ModeSettings(
        target=23.0,
        start_at=24.0,
        hysteresis=1.0,
        outdoor=OutdoorWindow(minimum=22.0),
        seasons=frozenset({Season.SUMMER}),
    )

    def sources(own: str) -> tuple[Source, ...]:
        return (
            Source(
                source_id=f"{own}_airco",
                entity_id=own,
                role=SourceRole.HEAT_COOL,
                outdoor=OutdoorWindow(minimum=CUTOVER),
            ),
            Source(
                source_id=f"{own}_gas",
                entity_id=BOILER,
                role=SourceRole.HEAT_ONLY,
                priority=1,
                outdoor=OutdoorWindow(maximum=CUTOVER),
            ),
        )

    living = Zone(
        zone_id="woonkamer",
        name="Woonkamer",
        indoor_sensor="sensor.woonkamer",
        priority=0,
        sources=sources(LIVING),
        heat=warm,
        cool=cold,
    )
    attic = Zone(
        zone_id="zolder",
        name="Zolder",
        indoor_sensor="sensor.zolder",
        priority=1,
        sources=sources(ATTIC),
        heat=warm,
        cool=cold,
        presence_entity=ATTIC_PRESENCE,
        presence_timeout=timedelta(seconds=1800),
    )
    bedroom = Zone(
        zone_id="slaapkamer",
        name="Slaapkamer",
        indoor_sensor="sensor.slaapkamer",
        priority=2,
        sources=(
            Source(
                source_id="slaapkamer_airco",
                entity_id=BEDROOM,
                role=SourceRole.HEAT_COOL,
                autostart=False,
                outdoor=OutdoorWindow(minimum=CUTOVER),
            ),
            Source(
                source_id="slaapkamer_gas",
                entity_id=BOILER,
                role=SourceRole.HEAT_ONLY,
                priority=1,
                outdoor=OutdoorWindow(maximum=CUTOVER),
            ),
        ),
        heat=warm,
        cool=cold,
    )

    return DirectorConfig(
        zones=(living, attic, bedroom),
        circuits=(
            Circuit(
                circuit_id="multisplit",
                name="Multi-split",
                units=(LIVING, ATTIC, BEDROOM),
                simultaneous_heat_cool=False,
                conflict_policy=ConflictPolicy.PRIORITY,
                family_switch_delay=timedelta(minutes=5),
                min_family_switch_interval=timedelta(minutes=30),
                min_cycle_time=timedelta(minutes=20),
                max_concurrent_units=2,
            ),
        ),
        generators=(
            Generator(
                generator_id="vloer",
                name="Vloerverwarming",
                entity_id=PUMP,
                zone_ids=("woonkamer",),
            ),
        ),
        residents=(
            Resident(
                resident_id="danny",
                name="Danny",
                presence_entity=DANNY,
                sleep_entity=DANNY_SLEEP,
                sleep_state="wireless",
                sleep_window=TimeWindow(time(21, 0), time(9, 0)),
                windows=(
                    TimeWindow(time(6, 30), time(23, 0), WEEK),
                    TimeWindow(time(8, 0), time(23, 30), WEEKEND),
                ),
            ),
            Resident(
                resident_id="nancy",
                name="Nancy",
                presence_entity=NANCY,
                sleep_entity=NANCY_SLEEP,
                sleep_state="wireless",
                sleep_window=TimeWindow(time(21, 0), time(9, 0)),
                windows=(TimeWindow(time(5, 0), time(22, 0)),),
            ),
        ),
        openings=(
            Opening(entity_id=BACK_DOOR, delay=timedelta(seconds=30)),
            Opening(entity_id=ROOF_WINDOW, delay=timedelta(minutes=2), zone_ids=("zolder",)),
        ),
        exclusive_groups=(
            frozenset({"slaapkamer_airco", f"{LIVING}_gas"}),
            frozenset({"slaapkamer_airco", f"{ATTIC}_gas"}),
            frozenset({"slaapkamer_airco", "slaapkamer_gas"}),
        ),
        gates=GateSettings(
            require_awake=True,
            require_schedule=False,
            max_precondition=timedelta(hours=2),
            precondition_window=TimeWindow(time(6, 0), time(23, 0)),
            guest_window=TimeWindow(time(8, 0), time(23, 0)),
            quiet_windows=(
                TimeWindow(time(21, 0), time(9, 0), WEEK),
                TimeWindow(time(23, 0), time(9, 0), WEEKEND),
            ),
        ),
        outdoor_sensor="sensor.buiten",
        stuck_after=timedelta(minutes=15),
    )


ZONE_OF = {LIVING: "woonkamer", ATTIC: "zolder", BEDROOM: "slaapkamer"}
UNITS = (LIVING, ATTIC, BEDROOM)


# ---------------------------------------------------------------------------
# Het huis als natuurkundig speeltje: ruw, maar het beweegt de goede kant op.
# The house as a toy physics model: crude, but it moves the right way.
# ---------------------------------------------------------------------------


def weather(now: datetime, rng: random.Random) -> tuple[float, Season]:
    """Return the outdoor temperature and season: frost to heatwave in a month.

    Eén maand die van vorst naar hittegolf loopt bestaat nergens, en dat is hier
    de bedoeling: zowel de gasketel als de airco's moeten aan bod komen, en de
    overgang ertussen ook. De winter- en zomermaanden in
    `test_seasons_simulation.py` doen het omgekeerde: die blijven wél binnen één
    seizoen.

    One month running from frost to heatwave exists nowhere, and that is the
    intent here: both the boiler and the air conditioners have to get their
    turn, and so does the crossing between them. The winter and summer months in
    `test_seasons_simulation.py` do the opposite: those stay inside one season.
    """
    day = (now - START) / timedelta(days=1)
    hour = now.hour + now.minute / 60
    trend = -4.0 + day * (34.0 / DAYS)
    swing = 5.0 * math.sin((hour - 9) / 24 * 2 * math.pi)
    outdoor = round(trend + swing + rng.uniform(-1.0, 1.0), 1)
    return outdoor, Season.SUMMER if outdoor > 18 else Season.WINTER


SCENARIO = Scenario(
    name="schoudermaand",
    config=house(),
    start=START,
    start_indoor={"woonkamer": 19.5, "zolder": 18.0, "slaapkamer": 17.5},
    weather=weather,
    days=DAYS,
)


@pytest.fixture(scope="module")
def month():
    """Return one finished month of simulation, run once for the whole module.

    De klok van de coordinator loopt mee met de simulatie: `_zones_handed_back`
    kijkt naar de dag van vandaag, en zonder dat mee te laten lopen vervalt een
    handmatige uitzetting nooit en test de maand op dat punt niets.

    The coordinator's clock moves with the simulation: `_zones_handed_back`
    looks at today's date, and without moving that along a hand-back never
    lapses and the month tests nothing on that point.
    """
    problems = [str(item) for item in validate(SCENARIO.config)]
    assert problems and all("automatic start off" in item for item in problems), problems
    return run_month(SCENARIO, seed=20260218)


class TestAMonthOfWeather:
    """Dertig dagen, en niets wat niet mag.

    Thirty days, and nothing that may not happen.

    De beloftes zelf worden in elke stap gecontroleerd; deze tests bewijzen dat
    de maand ook werkelijk gebeurd is. Een simulatie waarin niets voorvalt
    slaagt namelijk overal voor.

    The promises themselves are checked on every step; these tests prove the
    month actually happened. A simulation in which nothing occurs, after all,
    passes everything.
    """

    def test_it_really_ran_a_month(self, month: Simulation) -> None:
        assert month.now - START == timedelta(days=DAYS)
        assert month.plan is not None

    def test_the_weather_covered_both_extremes(self, month: Simulation) -> None:
        """Frost for the boiler, a heatwave for the air conditioners."""
        assert month.reasons.total() > 10_000

    def test_both_duties_were_actually_commanded(self, month: Simulation) -> None:
        assert month.commanded["heat"] > 20, month.commanded
        assert month.commanded["cool"] > 20, month.commanded
        assert month.commanded["off"] > 20, month.commanded

    def test_the_gas_and_the_heat_pumps_both_had_their_turn(self, month: Simulation) -> None:
        """Below the cutover the boiler heats, above it the units do."""
        assert month.commanded["heat"] > 0

    def test_people_came_and_went_and_slept(self, month: Simulation) -> None:
        for event in ("danny_left", "danny_home", "danny_asleep", "nancy_asleep"):
            assert month.events[event] > 0, month.events

    def test_windows_opened_and_appliances_were_touched(self, month: Simulation) -> None:
        assert month.events["window_opened"] > 5, month.events
        assert month.events["by_hand"] > 5, month.events

    def test_every_switch_was_flipped_at_least_once(self, month: Simulation) -> None:
        for event in ("master", "holiday", "guest", "override", "priority"):
            assert month.events[event] > 0, month.events

    def test_requests_were_made_and_expired(self, month: Simulation) -> None:
        assert month.events["precondition"] > 3, month.events

    def test_an_appliance_dropped_out_at_some_point(self, month: Simulation) -> None:
        assert month.events["unavailable"] > 0, month.events


class TestTheMonthExercisedTheEngine:
    """Welke uitkomsten er in dertig dagen langskwamen.

    Which outcomes came past in thirty days.

    Zonder deze controle kan de simulatie stilletjes uitdoven - alles uit, geen
    fouten, groene test. Dit legt vast dat de interessante gevallen er ook
    werkelijk in zaten.

    Without this check the simulation could quietly die out - everything off, no
    errors, green test. This pins down that the interesting cases really were in
    there.
    """

    EXPECTED = (
        Reason.REGULATING,
        Reason.SATISFIED,
        Reason.MASTER_DISABLED,
        Reason.MANUAL_OVERRIDE,
        Reason.OPENING_OPEN,
        Reason.NOBODY_HOME,
        Reason.EVERYONE_ASLEEP,
        Reason.ZONE_UNOCCUPIED,
        Reason.QUIET_HOURS,
        Reason.OUTDOOR_OUTSIDE_WINDOW,
        Reason.NO_SOURCE_AVAILABLE,
        Reason.OTHER_SOURCE_CHOSEN,
        Reason.MANUAL_SOURCE,
        Reason.SOURCE_UNREACHABLE,
    )

    #: `season_blocks_mode` staat er bewust niet bij. Een zone die zowel mag
    #: verwarmen als koelen rapporteert altijd de weigering van de
    #: verwarmingskant - `_best_refusal` kiest die - dus als zone-reden is hij
    #: in dit huis onbereikbaar. `test_hysteresis.py` dekt hem rechtstreeks.
    #:
    #: `season_blocks_mode` is deliberately absent. A zone allowed to both heat
    #: and cool always reports the heating refusal - `_best_refusal` picks that
    #: one - so as a zone reason it is unreachable in this house.
    #: `test_hysteresis.py` covers it head-on.

    @pytest.mark.parametrize("reason", EXPECTED, ids=lambda reason: reason.value)
    def test_the_outcome_occurred(self, month: Simulation, reason: Reason) -> None:
        assert month.reasons[reason.value] > 0, sorted(month.reasons)

    def test_the_timing_rules_bit_at_least_once(self, month: Simulation) -> None:
        """Short-cycle, switch pause and minimum run are the point of a month."""
        timed = (
            month.reasons[Reason.SHORT_CYCLE_PROTECTION.value]
            + month.reasons[Reason.CIRCUIT_SWITCH_PENDING.value]
            + month.reasons[Reason.CIRCUIT_SWITCH_TOO_SOON.value]
            + month.reasons[Reason.CIRCUIT_AT_CAPACITY.value]
            + month.reasons[Reason.CIRCUIT_CONFLICT_LOST.value]
            + month.reasons[Reason.EXCLUSIVE_GROUP_LOST.value]
        )
        assert timed > 0, sorted(month.reasons)

    def test_a_hand_at_the_appliance_was_recorded(self, month: Simulation) -> None:
        """The real hand-back bookkeeping ran, and wrote something away."""
        assert month.hand.saved > 0
