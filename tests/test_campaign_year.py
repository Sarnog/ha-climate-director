"""Twee halve jaren gesimuleerde tijd in een groot huis, met alles tegelijk aan.

Two half-years of simulated time in a large house, with everything at once.

Gesimuleerd, en dus geen draaitijd: dit is een nagebouwd huis met een nagebouwde
klok, in seconden doorlopen. Het zegt wat de besliskunde doet als er een half jaar
aan gebeurtenissen overheen gaat - niet dat de integratie ergens een half jaar
gedraaid heeft.

Simulated, and therefore not running time: this is a rebuilt house with a rebuilt
clock, walked in seconds. It says what the decision logic does when half a year of
events passes over it - not that the integration has run anywhere for half a year.

De bestaande halfjaarsimulatie loopt van september tot februari in een huis met
één buitenunit. Deze twee lopen de andere helften - februari tot augustus en
november tot april - in een huis waar alles tegelijk speelt: twee buitenunits
met verschillende conflictregels, een gedeelde ketel met kranen, een groep
apparaten die elkaar uitsluiten, een kamer die op aanwezigheid draait, een
handbediende slaapkamerairco, een verplicht rooster met vakantievensters, en een
buitenunit die minder units aankan dan eraan hangen.

Samen met de bestaande simulaties komt zo elke maand van het jaar aan bod, met
alle vier de seizoenen erin. Apparaten vallen vaak en lang weg, zodat de
reservebronnen werkelijk moeten invallen.

The existing half-year simulation runs September to February in a house with one
outdoor unit. These two run the other halves - February to August and November to
April - in a house where everything happens at once: two outdoor units with
different conflict rules, a shared boiler with valves, a group of appliances
ruling each other out, a room running on presence, a hand-operated bedroom unit,
a compulsory schedule with holiday windows, and an outdoor unit that can take
fewer units than hang on it.

Together with the existing simulations every month of the year is covered, all
four seasons in it. Appliances drop out often and for long, so the reserve
sources really have to step in.
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
from custom_components.climate_director.engine.models import SeasonSettings

# -- de apparaten / the appliances ------------------------------------------

LIVING = "climate.woonkamer_airco"
LIVING_SPARE = "climate.woonkamer_reserve"
KITCHEN_VALVE = "climate.keuken_kraan"
STUDY = "climate.studeerkamer_airco"
STUDY_SPARE = "climate.studeerkamer_reserve"
BEDROOM = "climate.slaapkamer_airco"
ATTIC = "climate.zolder_airco"
BOILER = "climate.ketel"

BACK_DOOR = "binary_sensor.achterdeur"
BEDROOM_WINDOW = "binary_sensor.slaapkamerraam"

HEAT_UNTIL = 18.0
COOL_FROM = 21.0


def warm(start_at: float, target: float | None = None) -> ModeSettings:
    """Return heating settings that stop once it is mild outside."""
    return ModeSettings(
        target=target if target is not None else start_at + 1.0,
        start_at=start_at,
        hysteresis=1.0,
        outdoor=OutdoorWindow(maximum=HEAT_UNTIL),
    )


def cool(start_at: float) -> ModeSettings:
    """Return cooling settings for the summer only."""
    return ModeSettings(
        target=start_at - 1.0,
        start_at=start_at,
        hysteresis=1.0,
        outdoor=OutdoorWindow(minimum=COOL_FROM),
        seasons=frozenset({Season.SUMMER}),
    )


def villa(policy: ConflictPolicy) -> DirectorConfig:
    """Return the big house, with one conflict rule swapped in.

    De conflictregel is het enige dat per doorloop verschilt, zodat de twee
    halve jaren niet alleen ander weer maar ook een andere arbitrage aflopen.

    The conflict rule is the only thing that differs per run, so the two half
    years walk not only different weather but a different arbitration too.
    """
    living = Zone(
        zone_id="woonkamer",
        name="Woonkamer",
        indoor_sensor="sensor.woonkamer",
        priority=0,
        sources=(
            Source("woonkamer_airco", LIVING, role=SourceRole.HEAT_COOL),
            Source("woonkamer_reserve", LIVING_SPARE, role=SourceRole.HEAT_ONLY, priority=1),
        ),
        heat=warm(19.5),
        cool=cool(23.5),
    )
    kitchen = Zone(
        zone_id="keuken",
        name="Keuken",
        indoor_sensor="sensor.keuken",
        priority=3,
        sources=(Source("keuken_kraan", KITCHEN_VALVE, role=SourceRole.HEAT_ONLY),),
        heat=warm(19.0),
    )
    study = Zone(
        zone_id="studeerkamer",
        name="Studeerkamer",
        indoor_sensor="sensor.studeerkamer",
        priority=1,
        sources=(
            Source("studeerkamer_airco", STUDY, role=SourceRole.HEAT_COOL),
            Source("studeerkamer_reserve", STUDY_SPARE, role=SourceRole.HEAT_COOL, priority=1),
        ),
        heat=warm(19.5),
        cool=cool(23.0),
        gate=ZoneGate.PRESENCE,
        presence_entity="binary_sensor.studeerkamer_aanwezig",
        presence_timeout=timedelta(minutes=20),
    )
    bedroom = Zone(
        zone_id="slaapkamer",
        name="Slaapkamer",
        indoor_sensor="sensor.slaapkamer",
        priority=2,
        sources=(
            # Handbediend: de director start hem nooit uit zichzelf, en zet hem
            # alleen uit als hij een ander in de weg staat.
            #
            # Hand-operated: the director never starts it of its own accord, and
            # only switches it off when it stands in somebody's way.
            Source("slaapkamer_airco", BEDROOM, role=SourceRole.HEAT_COOL, autostart=False),
        ),
        heat=warm(17.5),
        cool=cool(24.5),
    )
    attic = Zone(
        zone_id="zolder",
        name="Zolder",
        indoor_sensor="sensor.zolder",
        priority=4,
        sources=(Source("zolder_airco", ATTIC, role=SourceRole.HEAT_COOL),),
        heat=warm(18.0),
        cool=cool(25.0),
    )

    return DirectorConfig(
        zones=(living, kitchen, study, bedroom, attic),
        circuits=(
            # De grote buitenunit kan maar twee binnenunits tegelijk aan, en
            # verwarmt of koelt - nooit allebei.
            #
            # The large outdoor unit can take only two indoor units at once, and
            # either heats or cools - never both.
            Circuit(
                circuit_id="groot",
                name="Grote buitenunit",
                units=(LIVING, BEDROOM, ATTIC),
                simultaneous_heat_cool=False,
                conflict_policy=policy,
                allow_fan_only_during_conflict=True,
                family_switch_delay=timedelta(minutes=5),
                min_family_switch_interval=timedelta(hours=1),
                min_cycle_time=timedelta(minutes=15),
                max_concurrent_units=2,
            ),
            # De studeerkamer hangt aan een eigen splitunit met zijn reserve:
            # die twee mogen dus wel tegelijk iets anders doen.
            #
            # The study hangs on its own split unit with its stand-in: those two
            # may therefore do different things at once.
            Circuit(
                circuit_id="klein",
                name="Kleine buitenunit",
                units=(STUDY, STUDY_SPARE),
                simultaneous_heat_cool=True,
                min_cycle_time=timedelta(minutes=10),
            ),
        ),
        generators=(
            Generator(
                generator_id="ketel",
                name="Ketel",
                entity_id=BOILER,
                zone_ids=("keuken",),
            ),
        ),
        # De woonkamerreserve en de keukenkraan hangen aan dezelfde meterkast:
        # er mag er maar een van draaien.
        #
        # The living-room stand-in and the kitchen valve hang on the same fuse:
        # only one of them may run.
        exclusive_groups=(frozenset({"woonkamer_reserve", "keuken_kraan"}),),
        residents=(
            Resident(
                resident_id="danny",
                name="Danny",
                presence_entity="person.danny",
                sleep_entity="sensor.danny_lader",
                sleep_state="wireless",
                sleep_window=TimeWindow(time(22, 0), time(8, 0)),
                windows=(
                    TimeWindow(time(6, 30), time(23, 0), frozenset({0, 1, 2, 3, 4})),
                    TimeWindow(time(8, 0), time(23, 30), frozenset({5, 6})),
                    TimeWindow(time(9, 0), time(23, 30), holiday=True),
                ),
            ),
            Resident(
                resident_id="nancy",
                name="Nancy",
                presence_entity="person.nancy",
                sleep_entity="sensor.nancy_lader",
                sleep_state="wireless",
                sleep_window=TimeWindow(time(23, 0), time(7, 30)),
                windows=(TimeWindow(time(7, 0), time(22, 30)),),
            ),
        ),
        openings=(
            Opening(entity_id=BACK_DOOR, delay=timedelta(minutes=2)),
            Opening(
                entity_id=BEDROOM_WINDOW,
                zone_ids=("slaapkamer",),
                delay=timedelta(seconds=30),
            ),
        ),
        gates=GateSettings(
            require_awake=True,
            require_schedule=True,
            quiet_windows=(TimeWindow(time(23, 30), time(6, 0)),),
            guest_window=TimeWindow(time(8, 0), time(23, 0)),
            precondition_window=TimeWindow(time(5, 0), time(23, 0)),
            max_precondition=timedelta(hours=2),
        ),
        seasons=SeasonSettings(),
        outdoor_sensor="sensor.buiten",
        stuck_after=timedelta(minutes=45),
        holiday_calendars=("calendar.vakantie",),
        holiday_keyword="vakantie",
    )


# -- het weer / the weather --------------------------------------------------


def _curve(now: datetime, rng: random.Random, *, swing: float, middle: float) -> float:
    """Return an outdoor temperature: a yearly sine, a daily sine and some noise."""
    day_of_year = now.timetuple().tm_yday
    yearly = middle + swing * math.sin((day_of_year - 115) / 365 * 2 * math.pi)
    hour = now.hour + now.minute / 60
    daily = 4.5 * math.sin((hour - 15) / 24 * 2 * math.pi)
    return round(yearly + daily + rng.uniform(-1.5, 1.5), 1)


def winter_into_summer(now: datetime, rng: random.Random) -> tuple[float, Season]:
    """Return February-to-August weather, with a heatwave in July.

    De hittegolf zit er met opzet in: pas boven de dertig graden gaat een
    buitenunit die maar twee kamers aankan werkelijk knellen.

    The heatwave is deliberate: only above thirty degrees does an outdoor unit
    that can take two rooms really start to pinch.
    """
    outdoor = _curve(now, rng, swing=12.5, middle=10.5)
    if now.month == 7 and 10 <= now.day <= 20:
        outdoor += 8.0
    return round(outdoor, 1), SeasonSettings().for_month(now.month)


def autumn_into_spring(now: datetime, rng: random.Random) -> tuple[float, Season]:
    """Return November-to-April weather, with a hard frost in January.

    Een vorstperiode is waar het stoken echt aan moet blijven, en waar de
    dodeband en de minimale looptijd het van elkaar moeten winnen.

    A frost is where the heating really has to stay on, and where the dead band
    and the minimum run have to beat each other.
    """
    outdoor = _curve(now, rng, swing=12.5, middle=10.5)
    if now.month == 1 and 5 <= now.day <= 18:
        outdoor -= 9.0
    return round(outdoor, 1), SeasonSettings().for_month(now.month)


def whole_year(now: datetime, rng: random.Random) -> tuple[float, Season]:
    """Return a full calendar year: frost in January, a heatwave in July.

    Eén doorlopend jaar is de proef die twee halve jaren niet kunnen zijn: er is
    geen kunstmatige knip, dus de overgangen van winter naar zomer én van zomer
    naar winter zitten er allebei in, met alle vier de seizoenen ertussen.

    One continuous year is the test two half-years cannot be: there is no
    artificial cut, so both the winter-to-summer and the summer-to-winter
    crossings are in it, with all four seasons in between.
    """
    outdoor = _curve(now, rng, swing=12.5, middle=10.5)
    if now.month == 1 and 5 <= now.day <= 18:
        outdoor -= 9.0
    if now.month == 7 and 10 <= now.day <= 20:
        outdoor += 8.0
    return round(outdoor, 1), SeasonSettings().for_month(now.month)


# -- extra beloftes voor dit huis / extra promises for this house -----------


def _the_big_house_holds(config: DirectorConfig, world, plan, where: str) -> None:
    """Assert what this particular installation must never do."""
    running = {
        command.entity_id: family_of(command.hvac_mode)
        for command in plan.commands
        if family_of(command.hvac_mode) in (ModeFamily.HEAT, ModeFamily.COOL)
    }

    # De uitsluitende groep: de director zet nooit twee leden tegelijk aan het
    # werk. Wat een mens laat doordraaien in een overgedragen zone telt hier
    # niet mee - daar stuurt de director niets naartoe, ook geen uit.
    #
    # The exclusive group: the director never puts two members to work at once.
    # What a person leaves running in a handed-over zone does not count here -
    # the director sends that nothing, an off included.
    together = [entity for entity in (LIVING_SPARE, KITCHEN_VALVE) if entity in running]
    assert len(together) <= 1, f"{where}: {together} kregen allebei een opdracht om te draaien"

    # De ketel stookt alleen als de keuken warmte krijgt, tenzij de keuken is
    # overgedragen - dan blijft de director van de warmte af.
    #
    # The boiler only fires while the kitchen is being heated, unless the
    # kitchen has been handed over - then the director keeps off the heat.
    command = plan.command_for(BOILER)
    kitchen = plan.decision_for("keuken")
    if command is not None and kitchen is not None and not world.overridden("keuken"):
        heating = family_of(command.hvac_mode) is ModeFamily.HEAT
        assert heating == (kitchen.granted is ModeFamily.HEAT), (
            f"{where}: ketel {command.hvac_mode} terwijl keuken {kitchen.granted}"
        )

    # Koelen mag alleen in de zomer, hoe warm het ook is.
    # Cooling is for the summer only, however warm it gets.
    if world.season is not Season.SUMMER:
        cooling = [entity for entity, family in running.items() if family is ModeFamily.COOL]
        assert not cooling, f"{where}: {cooling} koelt buiten de zomer"

    # Wat er ook gebeurt: de slaapkamerairco wordt nooit door de director
    # aangezet.
    #
    # Whatever happens: the bedroom unit is never started by the director.
    bedroom = plan.command_for(BEDROOM)
    if bedroom is not None:
        assert family_of(bedroom.hvac_mode) is ModeFamily.NEUTRAL, (
            f"{where}: de handbediende slaapkamer werd gestart"
        )


# -- de twee doorlopen / the two runs ----------------------------------------

FIRST_START = datetime(2026, 2, 1, 0, 0)
SECOND_START = datetime(2026, 11, 1, 0, 0)
YEAR_START = datetime(2026, 1, 1, 0, 0)
DAYS = 182
YEAR_DAYS = 365

BUSY = Profile(
    drops_out=0.005,
    comes_back=0.04,
    by_hand=0.02,
    requests=0.006,
    cancels=0.002,
    override=0.005,
    override_back=0.05,
    priority=0.006,
    guest=0.004,
    holiday=0.003,
    window_opens=0.015,
    presence_flips=0.05,
)


def _scenario(
    name: str,
    policy: ConflictPolicy,
    start: datetime,
    weather,
    *,
    days: int = DAYS,
) -> Scenario:
    """Return one scenario for the big house."""
    return Scenario(
        name=name,
        config=villa(policy),
        start=start,
        start_indoor={
            "woonkamer": 20.5,
            "keuken": 19.5,
            "studeerkamer": 20.0,
            "slaapkamer": 18.0,
            "zolder": 19.0,
        },
        weather=weather,
        days=days,
        profile=BUSY,
        extra_check=_the_big_house_holds,
        duty_rate=0.4,
        boiler_rate=0.3,
        leak_rate=0.02,
    )


def _real_problems(config: DirectorConfig) -> list[str]:
    """Return the problems this house has, which should be none at all.

    Hier stond ooit een filter: de controle waarschuwde dat de twee apparaten
    in de uitsluitende groep elkaar bij elk weer konden tegenkomen, terwijl dat
    hier juist de bedoeling was - ze delen een groep omdat ze aan dezelfde
    meterkast hangen, en de groep is er om die keuze te maken. Een
    waarschuwing die je in je eigen testset moet wegfilteren is geen
    waarschuwing meer, en die controle is dus weg.

    A filter used to stand here: the check warned that the two appliances in
    the exclusive group could meet in any weather, while that was exactly the
    point - they share a group because they hang on the same fuse, and the
    group exists to make that choice. A warning you have to filter out of your
    own test suite is no warning any more, and that check has gone.
    """
    return list(validate(config))


@pytest.fixture(scope="module")
def spring():
    """Return February through July, arbitrated on demand."""
    scenario = _scenario(
        "winter_naar_zomer", ConflictPolicy.DEMAND, FIRST_START, winter_into_summer
    )
    assert not _real_problems(scenario.config), _real_problems(scenario.config)
    return run_month(scenario, seed=20260201)


@pytest.fixture(scope="module")
def frost():
    """Return November through April, arbitrated on the season."""
    scenario = _scenario(
        "herfst_naar_lente", ConflictPolicy.SEASON_LOCK, SECOND_START, autumn_into_spring
    )
    assert not _real_problems(scenario.config), _real_problems(scenario.config)
    return run_month(scenario, seed=20261101)


@pytest.fixture(scope="module")
def year():
    """Return one uninterrupted calendar year, arbitrated first-come."""
    scenario = _scenario(
        "heel_jaar", ConflictPolicy.FIRST_COME, YEAR_START, whole_year, days=YEAR_DAYS
    )
    assert not _real_problems(scenario.config), _real_problems(scenario.config)
    return run_month(scenario, seed=20260101)


class TestTheHalfYearReallyRan:
    """Eerst: is er werkelijk een half jaar verstreken.

    First: did half a year really pass.
    """

    def test_the_clock_advanced_half_a_year(self, spring, frost) -> None:
        assert spring.now - FIRST_START == timedelta(days=DAYS)
        assert frost.now - SECOND_START == timedelta(days=DAYS)

    def test_tens_of_thousands_of_decisions_were_taken(self, spring, frost) -> None:
        for run in (spring, frost):
            assert sum(run.reasons.values()) > 100_000

    def test_every_month_of_the_year_was_touched(self, spring, frost) -> None:
        months = {month for month, _mode in spring.duty_by_month} | {
            month for month, _mode in frost.duty_by_month
        }
        assert len(months) >= 10, f"maar {sorted(months)} kwamen aan bod"


class TestBothDutiesInTheirSeason:
    """Stoken hoort bij de winter, koelen bij de zomer.

    Heating belongs to the winter, cooling to the summer.
    """

    def test_the_first_run_both_heated_and_cooled(self, spring) -> None:
        assert spring.commanded["heat"] > 100
        assert spring.commanded["cool"] > 10

    def test_cooling_only_happened_in_the_summer_months(self, spring) -> None:
        cooling = {month for (month, mode) in spring.duty_by_month if mode == "cool"}
        assert cooling
        assert cooling <= {4, 5, 6, 7, 8, 9}, f"koelen in {sorted(cooling)}"

    def test_the_frost_run_never_cooled(self, frost) -> None:
        assert frost.commanded["cool"] == 0
        assert frost.commanded["heat"] > 100

    def test_the_frost_run_heated_through_the_deep_winter(self, frost) -> None:
        heating = {month for (month, mode) in frost.duty_by_month if mode == "heat"}
        assert {12, 1} <= heating, f"december en januari ontbreken: {sorted(heating)}"


class TestTheRoomsStayedLiveable:
    """Een half jaar sturen mag geen kamer laten ontsporen.

    Half a year of steering may not let a room run away.
    """

    def test_no_room_ran_away(self, spring, frost) -> None:
        for run in (spring, frost):
            for zone_id, temperature in run.indoor.items():
                assert -10.0 < temperature < 45.0, f"{zone_id} eindigde op {temperature}"

    def test_the_living_room_did_not_freeze_over_the_winter(self, frost) -> None:
        assert frost.indoor["woonkamer"] > 10.0


class TestEverySafeguardWasExercised:
    """Elke rem, poort en beperking moet in een half jaar aan bod komen.

    Every brake, gate and limit has to come up over half a year.
    """

    def _reasons(self, spring, frost) -> dict[str, int]:
        found: dict[str, int] = {}
        for run in (spring, frost):
            for reason, count in run.reasons.items():
                found[reason] = found.get(reason, 0) + count
        return found

    def test_the_capacity_limit_bit(self, spring, frost) -> None:
        assert self._reasons(spring, frost).get(Reason.CIRCUIT_AT_CAPACITY.value, 0) > 0

    def test_the_short_cycle_protection_bit(self, spring, frost) -> None:
        assert self._reasons(spring, frost).get(Reason.SHORT_CYCLE_PROTECTION.value, 0) > 0

    def test_a_duty_swap_was_paused(self, spring) -> None:
        counts = self._reasons(spring, spring)
        assert (
            counts.get(Reason.CIRCUIT_SWITCH_PENDING.value, 0)
            + counts.get(Reason.CIRCUIT_SWITCH_TOO_SOON.value, 0)
            > 0
        )

    def test_the_exclusive_group_took_somebody_out(self, spring, frost) -> None:
        assert self._reasons(spring, frost).get(Reason.EXCLUSIVE_GROUP_LOST.value, 0) > 0

    def test_the_presence_gated_study_was_left_alone(self, spring, frost) -> None:
        assert self._reasons(spring, frost).get(Reason.ZONE_UNOCCUPIED.value, 0) > 0

    def test_the_schedule_and_the_sleep_gate_both_shut(self, spring, frost) -> None:
        counts = self._reasons(spring, frost)
        assert counts.get(Reason.OUTSIDE_SCHEDULE.value, 0) > 0
        assert counts.get(Reason.EVERYONE_ASLEEP.value, 0) > 0

    def test_the_quiet_window_braked_at_night(self, spring, frost) -> None:
        assert self._reasons(spring, frost).get(Reason.QUIET_HOURS.value, 0) > 0

    def test_an_open_door_stopped_things(self, spring, frost) -> None:
        assert self._reasons(spring, frost).get(Reason.OPENING_OPEN.value, 0) > 0

    def test_the_manual_bedroom_was_left_alone(self, spring, frost) -> None:
        assert self._reasons(spring, frost).get(Reason.MANUAL_SOURCE.value, 0) > 0

    def test_a_zone_was_handed_over_by_hand(self, spring, frost) -> None:
        assert self._reasons(spring, frost).get(Reason.MANUAL_OVERRIDE.value, 0) > 0

    def test_the_outdoor_bounds_shut_the_shoulder_season_down(self, spring, frost) -> None:
        assert self._reasons(spring, frost).get(Reason.OUTDOOR_OUTSIDE_WINDOW.value, 0) > 0

    def test_no_cooling_was_ever_ordered_outside_the_summer(self, spring, frost) -> None:
        """Het seizoen hield koelen buiten de zomer tegen.

        De reden `season_blocks_mode` komt hier niet in de tellingen voor, en
        dat hoort ook: elke kamer kan ook stoken, en dan is de weigering van de
        koelkant nooit het antwoord dat een zone rapporteert. Wat telt is dat er
        buiten de zomer geen enkele koelopdracht uitging.

        The season held cooling back outside the summer. The reason
        `season_blocks_mode` does not show up in these counts, and rightly so:
        every room can heat as well, so the cooling side's refusal is never the
        answer a zone reports. What counts is that not one cooling command went
        out outside the summer.
        """
        cooling = {
            month
            for run in (spring, frost)
            for (month, mode) in run.duty_by_month
            if mode == "cool"
        }
        assert cooling <= {4, 5, 6, 7, 8, 9}, f"koelen in {sorted(cooling)}"


class TestTheSafetyNetEngaged:
    """Apparaten vielen weg, en de reserve nam het werkelijk over.

    Appliances dropped out, and the reserve really did take over.
    """

    def test_appliances_really_dropped_out(self, spring, frost) -> None:
        assert spring.events["unavailable"] + frost.events["unavailable"] > 20

    def test_the_unreachable_ones_were_reported(self, spring, frost) -> None:
        counts = {
            reason: spring.reasons.get(reason, 0) + frost.reasons.get(reason, 0)
            for reason in (Reason.SOURCE_UNREACHABLE.value, Reason.NO_SOURCE_AVAILABLE.value)
        }
        assert counts[Reason.SOURCE_UNREACHABLE.value] > 0
        assert counts[Reason.NO_SOURCE_AVAILABLE.value] > 0

    def test_a_room_really_ran_on_its_stand_in(self, spring, frost) -> None:
        assert spring.fallbacks + frost.fallbacks > 0

    def test_hands_at_the_appliances_were_noticed(self, spring, frost) -> None:
        assert spring.events["by_hand"] + frost.events["by_hand"] > 10

    def test_requests_were_made_and_ran_out(self, spring, frost) -> None:
        assert spring.events["precondition"] + frost.events["precondition"] > 5


class TestTheWholeYear:
    """Eén doorlopend jaar, van januari tot en met december.

    One continuous year, from January through December.
    """

    def test_the_clock_advanced_a_whole_year(self, year) -> None:
        assert year.now - YEAR_START == timedelta(days=YEAR_DAYS)

    def test_hundreds_of_thousands_of_decisions_were_taken(self, year) -> None:
        assert sum(year.reasons.values()) > 200_000, sum(year.reasons.values())

    def test_every_season_was_touched(self, year) -> None:
        """Alle vier de seizoenen komen aan bod, niet alleen de uitersten.

        All four seasons get their turn, not just the extremes.
        """
        months = {month for month, _mode in year.duty_by_month}
        seasons = {
            "winter": {12, 1, 2},
            "lente": {3, 4, 5},
            "zomer": {6, 7, 8},
            "herfst": {9, 10, 11},
        }
        for name, span in seasons.items():
            assert months & span, f"{name} ontbreekt in {sorted(months)}"

    def test_both_duties_were_commanded(self, year) -> None:
        assert year.commanded["heat"] > 100, year.commanded
        assert year.commanded["cool"] > 20, year.commanded

    def test_cooling_only_happened_in_the_summer_months(self, year) -> None:
        cooling = {month for (month, mode) in year.duty_by_month if mode == "cool"}
        assert cooling
        assert cooling <= {4, 5, 6, 7, 8, 9}, f"koelen in {sorted(cooling)}"

    def test_the_house_stayed_liveable(self, year) -> None:
        for zone_id, temperature in year.indoor.items():
            assert -10.0 < temperature < 45.0, (zone_id, temperature)

    def test_appliances_dropped_out_and_the_stand_in_took_over(self, year) -> None:
        assert year.events["unavailable"] > 20, year.events
        assert year.fallbacks > 0
        assert year.reasons[Reason.SOURCE_UNREACHABLE.value] > 0
        assert year.reasons[Reason.NO_SOURCE_AVAILABLE.value] > 0

    def test_the_safeguards_were_exercised(self, year) -> None:
        for reason in (
            Reason.CIRCUIT_AT_CAPACITY.value,
            Reason.SHORT_CYCLE_PROTECTION.value,
            Reason.EXCLUSIVE_GROUP_LOST.value,
            Reason.ZONE_UNOCCUPIED.value,
            Reason.OUTSIDE_SCHEDULE.value,
            Reason.EVERYONE_ASLEEP.value,
            Reason.QUIET_HOURS.value,
            Reason.OPENING_OPEN.value,
            Reason.MANUAL_SOURCE.value,
            Reason.MANUAL_OVERRIDE.value,
            Reason.OUTDOOR_OUTSIDE_WINDOW.value,
        ):
            assert year.reasons[reason] > 0, reason
        assert (
            year.reasons[Reason.CIRCUIT_SWITCH_PENDING.value]
            + year.reasons[Reason.CIRCUIT_SWITCH_TOO_SOON.value]
            > 0
        )

    def test_requests_were_made_and_hands_were_noticed(self, year) -> None:
        assert year.events["precondition"] > 5, year.events
        assert year.events["by_hand"] > 10, year.events
