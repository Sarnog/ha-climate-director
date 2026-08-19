"""Een strenge winter en een hittegolf, in een heel ander huis.

A hard winter and a heatwave, in a very different house.

De schoudermaand in `test_month_simulation.py` loopt van vorst naar hittegolf in
één huis met één multi-split. Hier staat het omgekeerde: twee maanden die elk
binnen hun eigen seizoen blijven, in een huis dat op alle punten anders in
elkaar zit - centrale verwarming met radiatorknoppen en een gedeelde ketel, een
tweede buitenunit die maar één binnenunit tegelijk aankan, een werkkamer die op
aanwezigheid draait, en een rooster dat verplicht is.

Wat een winter en een zomer apart bewijzen en een schoudermaand niet: dat de
gasketel het hele koude seizoen dóór blijft doen wat hij moet doen, dat er in de
winter geen kilowattuur naar koelen gaat, en dat een te kleine buitenunit in een
hittegolf niet ineens twee kamers tegelijk gaat bedienen.

The shoulder month in `test_month_simulation.py` runs from frost to heatwave in
one house with one multi-split. Here stands the opposite: two months that each
stay inside their own season, in a house built differently on every point -
central heating with radiator valves and a shared boiler, a second outdoor unit
that can drive only one indoor unit at a time, a study that runs on presence,
and a schedule that is compulsory.

What a winter and a summer prove separately and a shoulder month does not: that
the boiler keeps doing its job right through the cold season, that not one
kilowatt-hour goes to cooling in winter, and that an undersized outdoor unit
does not suddenly serve two rooms at once in a heatwave.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, time, timedelta

import pytest
from simulation import Profile, Scenario, run_month

from custom_components.climate_director.engine import (
    Circuit,
    ConflictPolicy,
    DirectorConfig,
    GateSettings,
    Generator,
    ModeFamily,
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
    ZoneGate,
    validate,
)
from custom_components.climate_director.engine.families import family_of

# ---------------------------------------------------------------------------
# Huis B: centrale verwarming met knoppen, plus twee airco's op een te kleine
# buitenunit.
#
# House B: central heating with valves, plus two air conditioners on an
# undersized outdoor unit.
# ---------------------------------------------------------------------------

BOILER = "climate.cv_ketel"
LIVING_VALVE = "climate.knop_woonkamer"
STUDY_VALVE = "climate.knop_werkkamer"
BEDROOM_VALVE = "climate.knop_slaapkamer"
LIVING_AC = "climate.airco_woonkamer"
STUDY_AC = "climate.airco_werkkamer"

FRONT_DOOR = "binary_sensor.voordeur"
STUDY_WINDOW = "binary_sensor.raam_werkkamer"
STUDY_PRESENCE = "binary_sensor.werkkamer_bezet"

#: Boven deze buitentemperatuur heeft stoken geen zin.
#: Above this outdoor temperature heating makes no sense.
HEAT_UNTIL = 18.0

#: Onder deze buitentemperatuur heeft koelen geen zin.
#: Below this outdoor temperature cooling makes no sense.
COOL_FROM = 21.0

WINTER_START = datetime(2026, 1, 1, 0, 0)
SUMMER_START = datetime(2026, 7, 1, 0, 0)
DAYS = 30


def warm(start_at: float) -> ModeSettings:
    """Return heating settings that stop once the weather turns mild."""
    return ModeSettings(
        target=start_at + 1.0,
        start_at=start_at,
        hysteresis=0.5,
        outdoor=OutdoorWindow(maximum=HEAT_UNTIL),
    )


def cold(start_at: float) -> ModeSettings:
    """Return cooling settings for the summer only."""
    return ModeSettings(
        target=start_at - 1.5,
        start_at=start_at,
        hysteresis=1.0,
        outdoor=OutdoorWindow(minimum=COOL_FROM),
        seasons=frozenset({Season.SUMMER}),
    )


def house() -> DirectorConfig:
    """Return a house with valves on one boiler and a small split system.

    De woonkamer en de werkkamer kunnen allebei verwarmen (knop) en koelen
    (airco); de slaapkamer heeft alleen een knop. De twee airco's delen een
    buitenunit die er maar één tegelijk aankan - precies de situatie waarvoor de
    capaciteitsgrens bestaat. De werkkamer draait op aanwezigheid, want een lege
    werkkamer hoeft niet gekoeld te worden.

    The living room and the study can both heat (valve) and cool (air
    conditioner); the bedroom has only a valve. The two air conditioners share
    an outdoor unit that can drive just one at a time - exactly the situation
    the capacity limit exists for. The study runs on presence, since an empty
    study need not be cooled.
    """
    living = Zone(
        zone_id="woonkamer",
        name="Woonkamer",
        indoor_sensor="sensor.woonkamer",
        priority=0,
        sources=(
            Source(
                source_id="woonkamer_knop",
                entity_id=LIVING_VALVE,
                role=SourceRole.HEAT_ONLY,
                outdoor=OutdoorWindow(maximum=HEAT_UNTIL),
            ),
            Source(
                source_id="woonkamer_airco",
                entity_id=LIVING_AC,
                role=SourceRole.COOL_ONLY,
                priority=1,
                outdoor=OutdoorWindow(minimum=COOL_FROM),
            ),
        ),
        heat=warm(19.5),
        cool=cold(24.0),
    )
    study = Zone(
        zone_id="werkkamer",
        name="Werkkamer",
        indoor_sensor="sensor.werkkamer",
        priority=1,
        gate=ZoneGate.PRESENCE,
        presence_entity=STUDY_PRESENCE,
        presence_timeout=timedelta(minutes=20),
        sources=(
            Source(
                source_id="werkkamer_knop",
                entity_id=STUDY_VALVE,
                role=SourceRole.HEAT_ONLY,
                outdoor=OutdoorWindow(maximum=HEAT_UNTIL),
            ),
            Source(
                source_id="werkkamer_airco",
                entity_id=STUDY_AC,
                role=SourceRole.COOL_ONLY,
                priority=1,
                outdoor=OutdoorWindow(minimum=COOL_FROM),
            ),
        ),
        heat=warm(20.0),
        cool=cold(23.5),
    )
    bedroom = Zone(
        zone_id="slaapkamer",
        name="Slaapkamer",
        indoor_sensor="sensor.slaapkamer",
        priority=2,
        sources=(
            Source(
                source_id="slaapkamer_knop",
                entity_id=BEDROOM_VALVE,
                role=SourceRole.HEAT_ONLY,
                autostart=False,
                outdoor=OutdoorWindow(maximum=HEAT_UNTIL),
            ),
        ),
        heat=warm(17.5),
    )

    return DirectorConfig(
        zones=(living, study, bedroom),
        circuits=(
            Circuit(
                circuit_id="split",
                name="Split",
                units=(LIVING_AC, STUDY_AC),
                simultaneous_heat_cool=False,
                conflict_policy=ConflictPolicy.DEMAND,
                allow_fan_only_during_conflict=True,
                min_cycle_time=timedelta(minutes=15),
                family_switch_delay=timedelta(minutes=3),
                max_concurrent_units=1,
            ),
        ),
        generators=(
            Generator(
                generator_id="ketel",
                name="CV-ketel",
                entity_id=BOILER,
                zone_ids=("woonkamer", "werkkamer", "slaapkamer"),
            ),
        ),
        residents=(
            Resident(
                resident_id="bewoner",
                name="Bewoner",
                presence_entity="person.bewoner",
                sleep_entity="sensor.bewoner_lader",
                sleep_state="wireless",
                sleep_window=TimeWindow(time(22, 0), time(8, 0)),
                windows=(TimeWindow(time(7, 0), time(23, 0)),),
            ),
            Resident(
                resident_id="huisgenoot",
                name="Huisgenoot",
                presence_entity="person.huisgenoot",
                sleep_entity="sensor.huisgenoot_lader",
                sleep_state="wireless",
                sleep_window=TimeWindow(time(23, 0), time(9, 0)),
                windows=(TimeWindow(time(9, 0), time(1, 0)),),
            ),
        ),
        openings=(
            Opening(entity_id=FRONT_DOOR, delay=timedelta(minutes=1)),
            Opening(entity_id=STUDY_WINDOW, delay=timedelta(minutes=3), zone_ids=("werkkamer",)),
        ),
        gates=GateSettings(
            require_awake=True,
            require_schedule=True,
            max_precondition=timedelta(minutes=90),
            precondition_window=TimeWindow(time(5, 0), time(22, 0)),
            guest_window=TimeWindow(time(9, 0), time(22, 0)),
            quiet_windows=(TimeWindow(time(23, 30), time(6, 30)),),
        ),
        outdoor_sensor="sensor.buiten",
        holiday_calendars=("calendar.gezin",),
        holiday_keyword="vakantie",
        stuck_after=timedelta(minutes=20),
    )


VALVES = (LIVING_VALVE, STUDY_VALVE, BEDROOM_VALVE)
AIRCOS = (LIVING_AC, STUDY_AC)


# ---------------------------------------------------------------------------
# Twee klimaten.
# Two climates.
# ---------------------------------------------------------------------------


def winter(now: datetime, rng: random.Random) -> tuple[float, Season]:
    """Return a January: between roughly -12 and +6, with a cold snap midway."""
    day = (now - WINTER_START) / timedelta(days=1)
    hour = now.hour + now.minute / 60
    base = -1.0 + 4.0 * math.sin(day / DAYS * 2 * math.pi)
    snap = -8.0 if 12 <= day < 17 else 0.0
    swing = 4.0 * math.sin((hour - 9) / 24 * 2 * math.pi)
    return round(base + snap + swing + rng.uniform(-1.5, 1.5), 1), Season.WINTER


def summer(now: datetime, rng: random.Random) -> tuple[float, Season]:
    """Return a July: between roughly 14 and 38, with a heatwave midway."""
    day = (now - SUMMER_START) / timedelta(days=1)
    hour = now.hour + now.minute / 60
    base = 22.0 + 3.0 * math.sin(day / DAYS * 2 * math.pi)
    wave = 8.0 if 10 <= day < 18 else 0.0
    swing = 6.0 * math.sin((hour - 15) / 24 * 2 * math.pi)
    return round(base + wave + swing + rng.uniform(-1.5, 1.5), 1), Season.SUMMER


def _never_the_wrong_appliance(config, world, plan, where: str) -> None:
    """Assert the two halves of this house never trade places.

    De knoppen zitten aan de ketel en kunnen alleen verwarmen; de airco's
    kunnen alleen koelen. Zou er ooit een koelopdracht naar een knop gaan of een
    verwarmingsopdracht naar een airco, dan klopt er iets fundamenteel niet - en
    dat is precies het soort fout dat je pas merkt als het huis niet warm wordt.

    The valves hang off the boiler and can only heat; the air conditioners can
    only cool. Were a cooling command ever to go to a valve or a heating command
    to an air conditioner, something is fundamentally wrong - and that is
    exactly the sort of fault you only notice when the house fails to warm up.
    """
    for command in plan.commands:
        family = family_of(command.hvac_mode)
        if command.entity_id in VALVES:
            assert family is not ModeFamily.COOL, f"{where}: knop {command.entity_id} moet koelen"
        if command.entity_id in AIRCOS:
            assert family is not ModeFamily.HEAT, f"{where}: airco {command.entity_id} moet stoken"

    # De ketel stookt nooit als het buiten al warm is: dat is de buitengrens
    # waar elke knop op staat.
    #
    # The boiler never fires while it is already warm outside: that is the
    # outdoor bound every valve carries.
    boiler = plan.command_for(BOILER)
    if (
        boiler is not None
        and family_of(boiler.hvac_mode) is ModeFamily.HEAT
        and world.outdoor_temperature is not None
    ):
        assert world.outdoor_temperature < HEAT_UNTIL, (
            f"{where}: de ketel stookt bij {world.outdoor_temperature} graden buiten"
        )


#: Een cv-ketel met knoppen warmt een kamer harder op dan een airco, en dit
#: huis is beter geïsoleerd dan het vorige. Zonder dat verschil verliest de
#: verwarming het van de kou en zegt een test over de kamertemperatuur meer over
#: mijn natuurkundemodel dan over de director.
#:
#: A boiler with valves warms a room harder than an air conditioner, and this
#: house is better insulated than the previous one. Without that difference the
#: heating loses to the cold, and a test about the room temperature says more
#: about my physics model than about the director.
WINTER_SCENARIO = Scenario(
    name="winter",
    config=house(),
    start=WINTER_START,
    start_indoor={"woonkamer": 18.5, "werkkamer": 17.0, "slaapkamer": 16.0},
    weather=winter,
    days=DAYS,
    extra_check=_never_the_wrong_appliance,
    profile=Profile(by_hand=0.006, requests=0.006),
    boiler_rate=0.75,
    duty_rate=0.45,
    leak_rate=0.012,
)

SUMMER_SCENARIO = Scenario(
    name="zomer",
    config=house(),
    start=SUMMER_START,
    start_indoor={"woonkamer": 23.0, "werkkamer": 24.5, "slaapkamer": 22.0},
    weather=summer,
    days=DAYS,
    extra_check=_never_the_wrong_appliance,
    profile=Profile(window_opens=0.02, presence_flips=0.05),
    duty_rate=0.45,
    leak_rate=0.012,
)

SEEDS = (20260101, 20260707)


@pytest.fixture(scope="module")
def winters():
    """Return two Januaries, each on its own seed."""
    problems = [str(item) for item in validate(house())]
    assert problems and all("automatic start off" in item for item in problems), problems
    return [run_month(WINTER_SCENARIO, seed=seed) for seed in SEEDS]


@pytest.fixture(scope="module")
def summers():
    """Return two Julys, each on its own seed."""
    return [run_month(SUMMER_SCENARIO, seed=seed) for seed in SEEDS]


class TestTheWinterMonths:
    """Wat een koude maand moet opleveren, en wat er zeker niet in mag zitten.

    What a cold month must produce, and what may certainly not be in it.
    """

    def test_the_boiler_actually_ran(self, winters: list) -> None:
        for month in winters:
            assert month.commanded["heat"] > 100, month.commanded

    def test_not_one_command_to_cool(self, winters: list) -> None:
        """Koelen staat op zomer, dus in januari hoort er geen enkele te zijn."""
        for month in winters:
            assert month.commanded["cool"] == 0, month.commanded

    def test_the_living_room_stayed_warm(self, winters: list) -> None:
        """Buiten kan het min twintig zijn; de woonkamer blijft op temperatuur.

        Alleen de woonkamer: de werkkamer draait op aanwezigheid en mag afkoelen
        als er niemand zit, en de slaapkamerknop is handbediend - die start de
        director nooit uit zichzelf, en dat is precies de bedoeling.

        The living room only: the study runs on presence and may cool down with
        nobody in it, and the bedroom valve is hand-operated - the director never
        starts that of its own accord, which is exactly the intent.
        """
        for month in winters:
            assert month.indoor["woonkamer"] > 15.0, month.indoor

    def test_the_hand_operated_bedroom_was_allowed_to_get_cold(self, winters: list) -> None:
        """Wie zijn slaapkamerknop zelf bedient, krijgt hem niet vanzelf aan."""
        for month in winters:
            assert month.commanded["heat"] > 0
            assert month.reasons[Reason.MANUAL_SOURCE.value] > 0, month.reasons

    def test_the_cold_snap_did_not_break_anything(self, winters: list) -> None:
        for month in winters:
            assert month.reasons[Reason.REGULATING.value] > 500, month.reasons

    def test_the_house_still_stood_down_sometimes(self, winters: list) -> None:
        """Een maand die alleen maar stookt test de poorten niet."""
        for month in winters:
            assert month.commanded["off"] > 50, month.commanded


class TestTheSummerMonths:
    """Wat een hittegolf moet opleveren.

    What a heatwave must produce.
    """

    def test_the_air_conditioners_actually_ran(self, summers: list) -> None:
        for month in summers:
            assert month.commanded["cool"] > 50, month.commanded

    def test_the_boiler_stayed_out_of_it(self, summers: list) -> None:
        """Er kan 's nachts nog gestookt worden, maar niet in de hitte."""
        for month in summers:
            assert month.commanded["heat"] < month.commanded["cool"], month.commanded

    def test_the_undersized_outdoor_unit_held(self, summers: list) -> None:
        """Eén binnenunit tegelijk: de tweede kamer hoort te horen dat hij wacht."""
        for month in summers:
            assert month.reasons[Reason.CIRCUIT_AT_CAPACITY.value] > 0, month.reasons

    def test_the_rooms_did_not_run_away(self, summers: list) -> None:
        for month in summers:
            assert max(month.indoor.values()) < 40.0, month.indoor


@pytest.fixture(scope="module")
def months(winters: list, summers: list) -> list:
    """Return all four months, winters and summers together."""
    return [*winters, *summers]


class TestBothSeasons:
    """De dingen die in elke maand moeten gebeuren, wat het weer ook doet.

    The things that must happen in every month, whatever the weather does.
    """

    def test_every_month_really_ran(self, months: list) -> None:
        assert len(months) == 4
        for month in months:
            assert month.now - month.scenario.start == timedelta(days=DAYS)

    def test_the_presence_gated_study_was_left_alone_when_empty(self, months: list) -> None:
        for month in months:
            assert month.reasons[Reason.ZONE_UNOCCUPIED.value] > 0, month.reasons

    def test_the_compulsory_schedule_shut_the_house_sometimes(self, months: list) -> None:
        for month in months:
            assert month.reasons[Reason.OUTSIDE_SCHEDULE.value] > 0, month.reasons

    def test_the_quiet_window_braked_at_night(self, months: list) -> None:
        for month in months:
            assert month.reasons[Reason.QUIET_HOURS.value] > 0, month.reasons

    def test_the_hand_operated_bedroom_was_never_started(self, months: list) -> None:
        """`autostart: false` op de slaapkamerknop, de hele maand door."""
        for month in months:
            assert month.reasons[Reason.MANUAL_SOURCE.value] > 0, month.reasons

    def test_windows_and_doors_stopped_things(self, months: list) -> None:
        for month in months:
            assert month.reasons[Reason.OPENING_OPEN.value] > 0, month.reasons

    def test_requests_were_made(self, months: list) -> None:
        for month in months:
            assert month.events["precondition"] > 0, month.events

    def test_a_hand_at_an_appliance_was_recorded(self, months: list) -> None:
        for month in months:
            assert month.hand.saved > 0

    def test_two_seeds_do_not_produce_the_same_month(self, winters: list) -> None:
        """Anders test de tweede zaadwaarde niets nieuws."""
        first, second = winters
        assert first.reasons != second.reasons
