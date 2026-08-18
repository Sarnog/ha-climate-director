"""Een half jaar gesimuleerde tijd aan één stuk, van nazomer tot en met de winter.

Half a year of simulated time in one go, from late summer through the winter.

Gesimuleerd, en dus geen draaitijd: een nagebouwd huis met een nagebouwde klok,
doorlopen in seconden.

Simulated, and therefore not running time: a rebuilt house with a rebuilt clock,
walked in seconds.

De maanden in de andere simulaties blijven binnen één seizoen of springen er in
dertig dagen doorheen. Deze loopt een half jaar aan één stuk: eerst koelen in de
nazomer, dan de overgang waarin geen van beide mag, en dan een winter lang
stoken. Juist die overgang is waar een klimaatregelaar in de war raakt - het
seizoen slaat om, de buitengrenzen wisselen van kant, en de dode band moet
voorkomen dat er twee keer per dag van taak gewisseld wordt.

Het huis heeft bovendien echte reservebronnen: elke kamer heeft een tweede
apparaat dat hetzelfde kan. Apparaten vallen hier vaker en langer weg dan in de
andere simulaties, zodat het vangnet ook werkelijk in werking treedt - en dat is
het geval waar de "op reserve"-melder voor bestaat: de kamer wordt gewoon warm,
alleen anders dan bedoeld.

The months in the other simulations stay inside one season or jump through them
in thirty days. This one runs half a year in one go: cooling in the late summer
first, then the crossing where neither is allowed, and then a winter of heating.
That crossing is exactly where a climate controller gets confused - the season
turns over, the outdoor bounds swap sides, and the dead band has to keep it from
switching duty twice a day.

The house also has real reserve sources: every room has a second appliance that
can do the same thing. Appliances drop out more often and for longer here than
in the other simulations, so the safety net really does engage - and that is the
case the "on stand-in" sensor exists for: the room simply gets warm, only
differently than intended.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, time, timedelta

import pytest
from simulation import Profile, Scenario, run_month

from custom_components.climate_director.engine import (
    Circuit,
    DirectorConfig,
    GateSettings,
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
    validate,
)
from custom_components.climate_director.engine.models import SeasonSettings

LIVING = "climate.woonkamer_airco"
LIVING_SPARE = "climate.woonkamer_reserve"
ATTIC = "climate.zolder_airco"
ATTIC_SPARE = "climate.zolder_reserve"
BEDROOM = "climate.slaapkamer_airco"

BACK_DOOR = "binary_sensor.achterdeur"

START = datetime(2026, 9, 1, 0, 0)
DAYS = 182

#: Grenzen die de twee helften van het jaar uit elkaar houden.
#: Bounds that keep the two halves of the year apart.
HEAT_UNTIL = 17.0
COOL_FROM = 20.0


def warm(start_at: float) -> ModeSettings:
    return ModeSettings(
        target=start_at + 1.0,
        start_at=start_at,
        hysteresis=1.0,
        outdoor=OutdoorWindow(maximum=HEAT_UNTIL),
    )


def cold(start_at: float) -> ModeSettings:
    return ModeSettings(
        target=start_at - 1.0,
        start_at=start_at,
        hysteresis=1.0,
        outdoor=OutdoorWindow(minimum=COOL_FROM),
        seasons=frozenset({Season.SUMMER}),
    )


def zone(name: str, first: str, spare: str | None, start_at: float, priority: int) -> Zone:
    """Return a room with a first choice and, if given, a stand-in that can do the same."""
    sources = [
        Source(source_id=f"{name}_eerste", entity_id=first, role=SourceRole.HEAT_COOL),
    ]
    if spare is not None:
        sources.append(
            Source(
                source_id=f"{name}_reserve",
                entity_id=spare,
                role=SourceRole.HEAT_COOL,
                priority=1,
            )
        )
    return Zone(
        zone_id=name,
        name=name.title(),
        indoor_sensor=f"sensor.{name}",
        priority=priority,
        sources=tuple(sources),
        heat=warm(start_at),
        cool=cold(start_at + 4.0),
    )


def house() -> DirectorConfig:
    """Return a house where two rooms have a stand-in and one has none.

    De reservebronnen hebben géén eigen buitengrens: ze mogen precies wanneer de
    eerste keus mag. Anders zou het vangnet niet het vangnet zijn maar een
    tweede regel.

    The reserve sources carry no outdoor bound of their own: they may exactly
    when the first choice may. Otherwise the safety net would not be a safety
    net but a second rule.
    """
    return DirectorConfig(
        zones=(
            zone("woonkamer", LIVING, LIVING_SPARE, 19.5, 0),
            zone("zolder", ATTIC, ATTIC_SPARE, 19.0, 1),
            zone("slaapkamer", BEDROOM, None, 17.0, 2),
        ),
        circuits=(
            Circuit(
                circuit_id="buiten",
                name="Buitenunit",
                units=(LIVING, ATTIC, BEDROOM),
                simultaneous_heat_cool=False,
                family_switch_delay=timedelta(minutes=5),
                min_family_switch_interval=timedelta(hours=1),
                min_cycle_time=timedelta(minutes=15),
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
            ),
        ),
        openings=(Opening(entity_id=BACK_DOOR, delay=timedelta(minutes=2)),),
        gates=GateSettings(
            require_awake=True,
            max_precondition=timedelta(hours=2),
            precondition_window=TimeWindow(time(6, 0), time(23, 0)),
            quiet_windows=(TimeWindow(time(23, 0), time(6, 0)),),
        ),
        seasons=SeasonSettings(),
        outdoor_sensor="sensor.buiten",
        stuck_after=timedelta(minutes=30),
    )


def half_a_year(now: datetime, rng: random.Random) -> tuple[float, Season]:
    """Return a September-to-February climate, with the season read as the integration does.

    De jaarcurve is een sinus met zijn top begin augustus en zijn dal begin
    februari; de dagcurve zit daar bovenop. Het seizoen komt uit dezelfde
    maandtabel die de integratie op `AUTO` gebruikt, zodat de simulatie en de
    configuratie het niet oneens kunnen zijn.

    The yearly curve is a sine peaking in early August and bottoming in early
    February; the daily curve sits on top of it. The season comes from the same
    month table the integration uses on `AUTO`, so the simulation and the
    configuration cannot disagree.
    """
    day_of_year = now.timetuple().tm_yday
    yearly = 10.5 + 12.0 * math.sin((day_of_year - 115) / 365 * 2 * math.pi)

    # Een nazomer bovenop de jaarcurve. Zonder die eerste warme weken begint dit
    # half jaar al in de overgang, en dan komt de koelkant er nooit aan te pas -
    # terwijl juist de omslag van koelen naar stoken het punt van deze test is.
    #
    # An Indian summer on top of the yearly curve. Without those first warm
    # weeks this half year starts in the crossing already, and then the cooling
    # side never gets a turn - while the swing from cooling to heating is
    # exactly this test's point.
    indian_summer = 6.0 if (now - START) < timedelta(days=18) else 0.0

    hour = now.hour + now.minute / 60
    daily = 4.0 * math.sin((hour - 15) / 24 * 2 * math.pi)
    outdoor = round(yearly + indian_summer + daily + rng.uniform(-1.5, 1.5), 1)
    return outdoor, SeasonSettings().for_month(now.month)


def _the_stand_in_is_never_worse(config, world, plan, where: str) -> None:
    """Assert a room on its stand-in is still being served properly.

    Uitwijken mag de kamer niet stilzetten en mag de streeftemperatuur niet
    veranderen: het is een ander apparaat, niet een andere bedoeling.

    Falling back may not silence the room and may not change the target: it is a
    different appliance, not a different intention.
    """
    for decision in plan.zones:
        if not decision.on_fallback:
            continue
        assert decision.granted is not ModeFamily.NEUTRAL or decision.reason is not None, (
            f"{where}: {decision.zone_id} wijkt uit maar krijgt niets"
        )
        for entity_id in decision.passed_over:
            source = next(
                (
                    item
                    for zone_item in config.zones
                    for item in zone_item.sources
                    if item.source_id == entity_id
                ),
                None,
            )
            if source is None:
                continue
            assert not world.climate(source.entity_id).available, (
                f"{where}: {entity_id} werd overgeslagen terwijl hij gewoon te bereiken was"
            )

    # Een apparaat dat niet te bereiken is, krijgt nooit een opdracht.
    # An appliance that cannot be reached never gets a command.
    for command in plan.commands:
        assert world.climate(command.entity_id).available, (
            f"{where}: {command.entity_id} kreeg een opdracht terwijl hij weg was"
        )


SCENARIO = Scenario(
    name="halfjaar",
    config=house(),
    start=START,
    start_indoor={"woonkamer": 22.0, "zolder": 23.0, "slaapkamer": 21.0},
    weather=half_a_year,
    days=DAYS,
    extra_check=_the_stand_in_is_never_worse,
    # Apparaten vallen hier vaker en langer weg, zodat het vangnet echt gaat werken.
    # Appliances drop out more often and for longer here, so the safety net really works.
    profile=Profile(drops_out=0.004, comes_back=0.04),
    duty_rate=0.4,
    leak_rate=0.015,
)


@pytest.fixture(scope="module")
def half_year():
    """Return one uninterrupted half year."""
    assert not validate(SCENARIO.config), validate(SCENARIO.config)
    return run_month(SCENARIO, seed=20260901)


class TestItReallyRanHalfAYear:
    def test_the_clock_advanced(self, half_year) -> None:
        assert half_year.now - START == timedelta(days=DAYS)

    def test_it_took_tens_of_thousands_of_decisions(self, half_year) -> None:
        assert half_year.reasons.total() > 100_000, half_year.reasons.total()


class TestTheSeasonsCameAndWent:
    """Koelen in september, stoken in januari, en de overgang ertussen.

    Cooling in September, heating in January, and the crossing between them.
    """

    def test_both_duties_were_commanded(self, half_year) -> None:
        assert half_year.commanded["cool"] > 20, half_year.commanded
        assert half_year.commanded["heat"] > 100, half_year.commanded

    def test_cooling_belongs_to_the_first_half(self, half_year) -> None:
        """Koelen staat op zomer, dus na september hoort het te stoppen."""
        cooled = {month for (month, mode) in half_year.duty_by_month if mode == "cool"}
        assert cooled <= {9, 10}, sorted(cooled)

    def test_heating_belongs_to_the_second_half(self, half_year) -> None:
        heated = {month for (month, mode) in half_year.duty_by_month if mode == "heat"}
        assert 12 in heated or 1 in heated, sorted(heated)

    def test_the_outdoor_bounds_shut_things_down_in_between(self, half_year) -> None:
        """Tussen de twee grenzen mag geen van beide, en dat hoort gemeld te worden."""
        assert half_year.reasons[Reason.OUTDOOR_OUTSIDE_WINDOW.value] > 0, half_year.reasons

    def test_the_minimum_run_held_the_duty_during_the_crossing(self, half_year) -> None:
        """De overgang is waar een regelaar gaat pendelen tussen koelen en stoken.

        Een warme middag en een koude nacht in dezelfde week is normaal; twee
        keer per uur van taak wisselen is dat niet. De minimale looptijd voor
        een taakwissel houdt de buitenunit dan vast, en dat die regel in dit
        half jaar werkelijk gebeten heeft, is het bewijs dat de overgang
        doorlopen is.

        The crossing is where a controller starts swinging between cooling and
        heating. A warm afternoon and a cold night in the same week is normal;
        swapping duty twice an hour is not. The minimum run before a switch then
        holds the outdoor unit, and that this rule really bit during this half
        year is the proof that the crossing was walked.
        """
        assert half_year.reasons[Reason.CIRCUIT_SWITCH_TOO_SOON.value] > 0, half_year.reasons

    def test_both_duties_happened_in_the_same_month(self, half_year) -> None:
        """September koelt overdag en stookt 's nachts - dat is de overgang zelf."""
        months_with_both = {
            month
            for (month, mode) in half_year.duty_by_month
            if mode == "heat" and (month, "cool") in half_year.duty_by_month
        }
        assert months_with_both, sorted(half_year.duty_by_month)


class TestTheStandInTookOver:
    """Het vangnet, over een half jaar aan uitvallende apparaten.

    The safety net, across half a year of appliances dropping out.
    """

    def test_appliances_really_dropped_out(self, half_year) -> None:
        assert half_year.events["unavailable"] > 20, half_year.events

    def test_an_unreachable_appliance_was_reported_as_such(self, half_year) -> None:
        assert half_year.reasons[Reason.SOURCE_UNREACHABLE.value] > 0, half_year.reasons

    def test_the_reserve_actually_served_a_room(self, half_year) -> None:
        """Zonder dit bewijst de hele opstelling niets over het vangnet."""
        assert half_year.fallbacks > 0, half_year.fallbacks

    def test_a_room_without_a_reserve_simply_stops(self, half_year) -> None:
        assert half_year.reasons[Reason.NO_SOURCE_AVAILABLE.value] > 0, half_year.reasons


class TestTheHouseStayedLiveable:
    """Een half jaar lang, met alles wat er tussendoor kwam.

    Half a year long, with everything that came past in between.
    """

    def test_the_rooms_never_ran_away(self, half_year) -> None:
        for zone_id, temperature in half_year.indoor.items():
            assert -10.0 < temperature < 45.0, (zone_id, temperature)

    def test_the_quiet_window_braked_at_night(self, half_year) -> None:
        assert half_year.reasons[Reason.QUIET_HOURS.value] > 0, half_year.reasons

    def test_requests_were_made_and_ran_out(self, half_year) -> None:
        assert half_year.events["precondition"] > 5, half_year.events

    def test_hands_at_appliances_were_recorded(self, half_year) -> None:
        assert half_year.hand.saved > 0

    def test_the_timing_rules_bit(self, half_year) -> None:
        timed = (
            half_year.reasons[Reason.SHORT_CYCLE_PROTECTION.value]
            + half_year.reasons[Reason.CIRCUIT_SWITCH_PENDING.value]
            + half_year.reasons[Reason.CIRCUIT_SWITCH_TOO_SOON.value]
        )
        assert timed > 0, half_year.reasons
