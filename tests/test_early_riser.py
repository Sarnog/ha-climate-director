"""*Opstaan zet het huis pas aan vanaf*: vroeg opstaan remt het huis, per bewoner.

*Getting up only starts the house from*: getting up early brakes the house, per resident.

Wie op een werkdag om kwart voor zes opstaat en om half zeven de deur uit gaat, hoeft
het huis niet aan te zetten - ook niet als de ander niet thuis is. Staat de ander op,
dan gaat het huis wel aan. Op een vakantiedag geldt de rem nooit; slaapt de ander dan
nog, dan wacht het huis zoals op zaterdag (*Wacht op deze slaper tot*). Het is een rem
op beginnen, niet op doorgaan, en het stiltevenster blijft precies zoals het was.

De instellingen zijn die van een echt huis: Danny heeft de rem tot 07:00 op maandag
tot en met vrijdag, Nancy niet; beiden wachten tot 11:00 op zaterdag, zondag en
vakantiedagen; het slaapvenster is 21:00–08:00 en de stiltevensters zijn 21:00–09:00
(ma–do, zo) en 23:00–09:00 (vr, za). Elke toets loopt de nacht ronde na ronde, zoals de
koppelingslaag dat doet: `night.house_asleep_since` geeft het moment voor de volgende
ronde. Met een vast moment zou een geval groen kunnen zijn terwijl de koppelingslaag dat
moment in die ronde allang vergeten was - en dan meet de toets niet wat een gebruiker
meemaakt. De gevallen staan bij hun nummer in de toets-id's (wens2-1 tot en met wens2-12).

Whoever gets up at a quarter to six on a working day and leaves at half past six need
not start the house - not even when the other resident is away. When the other gets
up, the house does start. On a holiday the brake never applies; when the other is
still asleep then, the house waits as on a Saturday (*Wait for this sleeper until*).
It is a brake on starting, not on continuing, and the quiet window stays exactly as
it was.

The settings are those of a real house: Danny has the brake until 07:00 Monday to
Friday, Nancy does not; both wait until 11:00 on Saturday, Sunday and holidays; the
sleep window is 21:00–08:00 and the quiet windows are 21:00–09:00 (Mon–Thu, Sun) and
23:00–09:00 (Fri, Sat). Every test walks the night round by round, the way the binding
layer does: `night.house_asleep_since` hands the moment to the next round. With a fixed
moment a case could be green while the binding layer had long forgotten that moment in
that round - and then the test does not measure what a user goes through. The cases
stand by their number in the test ids (wens2-1 through wens2-12).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, time, timedelta

import pytest
from conftest import ATTIC, BEDROOM, GAS, LIVING, asleep, at, awake, away, house, make_world

from custom_components.climate_director.engine import (
    DirectorConfig,
    Reason,
    ResidentState,
    RiseBrake,
    SleepIn,
    TimeWindow,
    WakeDeadline,
    WorldState,
    Zone,
    gates,
    night,
)
from custom_components.climate_director.engine.serialise import config_from_dict, config_to_dict

MON, TUE, FRI, SAT = 10, 11, 14, 15
WORKDAYS = frozenset({0, 1, 2, 3, 4})

Step = tuple[datetime, ResidentState, ResidentState]


def with_brakes(config: DirectorConfig, **brakes: RiseBrake | None) -> DirectorConfig:
    """Return the house with a rise brake per resident."""
    return replace(
        config,
        residents=tuple(
            replace(resident, rise_brake=brakes.get(resident.resident_id))
            for resident in config.residents
        ),
    )


def live_house(*, danny: bool = True, nancy: bool = False) -> DirectorConfig:
    """Return the standard house with the settings of a real one, brakes as asked."""
    config = house()
    weekend = frozenset({5, 6})
    config = replace(
        config,
        residents=tuple(
            replace(
                resident,
                sleep_window=TimeWindow(start=time(21, 0), end=time(8, 0)),
                sleep_in=SleepIn(until=time(13, 0), weekdays=weekend, holiday=True),
                wake_deadline=WakeDeadline(at=time(11, 0), weekdays=weekend, holiday=True),
            )
            for resident in config.residents
        ),
        gates=replace(
            config.gates,
            quiet_windows=(
                TimeWindow(time(21, 0), time(9, 0), weekdays=frozenset({0, 1, 2, 3, 6})),
                TimeWindow(time(23, 0), time(9, 0), weekdays=frozenset({4, 5})),
            ),
        ),
    )
    seven = RiseBrake(at=time(7, 0), weekdays=WORKDAYS)
    return with_brakes(config, danny=seven if danny else None, nancy=seven if nancy else None)


def evening(day: int) -> datetime:
    """Return the evening before `day` at 18:00: everybody was home by then."""
    return at(18, 0, day=day) - timedelta(days=1)


def up(day: int) -> ResidentState:
    """Return a resident who is up, home since the evening before."""
    return awake(home_since=evening(day))


def bed(day: int) -> ResidentState:
    """Return a resident who is in bed, home since the evening before."""
    return asleep(home_since=evening(day))


def person(how: str, day: int) -> ResidentState:
    """Return one resident's state: `bed`, `up` or `away`."""
    if how == "bed":
        return bed(day)
    if how == "away":
        return away()
    return up(day)


def turning_in(day: int, *, danny: str = "bed", nancy: str = "bed") -> Step:
    """Return the round in which both residents turn in, at 23:30 on evening `day`."""
    return (at(23, 30, day=day), person(danny, day), person(nancy, day))


def getting_up(
    day: int, hour: int, minute: int = 0, *, danny: str = "up", nancy: str = "bed"
) -> Step:
    """Return the round in which the residents get up, or leave, that morning."""
    return (at(hour, minute, day=day), person(danny, day), person(nancy, day))


def night_world(
    *,
    now: datetime,
    danny: ResidentState,
    nancy: ResidentState,
    holiday: bool = False,
    running: bool = False,
    slept: datetime | None = None,
    **extra: object,
) -> WorldState:
    """Return one world, with the moment the house went to sleep as given."""
    return make_world(
        now=now,
        outdoor=10.0,
        indoor={"woonkamer": 18.0, "zolder": 18.0, "slaapkamer": 18.0},
        climates={LIVING: "heat" if running else "off", GAS: "off", ATTIC: "off", BEDROOM: "off"},
        residents={"danny": danny, "nancy": nancy},
        holiday_mode=holiday,
        asleep_since=slept,
        **extra,  # type: ignore[arg-type]
    )


def walk(
    config: DirectorConfig,
    steps: list[Step],
    *,
    holiday: bool = False,
    running: bool = False,
    slept: datetime | None = None,
    **extra: object,
) -> WorldState:
    """Walk the night round by round, carrying the moment the way the binding layer does.

    Elke ronde geeft `night.house_asleep_since` het moment voor de volgende ronde, precies
    zoals `world_builder._note_house_asleep` dat in een draaiende Home Assistant doet. De
    uitkomst is de laatste wereld: daar kijken de poorten naar.

    Every round hands `night.house_asleep_since`'s outcome to the next one, exactly as
    `world_builder._note_house_asleep` does in a running Home Assistant. The outcome is the
    last world: that is the one the gates look at.
    """
    worlds: list[WorldState] = []
    for now, danny, nancy in steps:
        world = night_world(
            now=now,
            danny=danny,
            nancy=nancy,
            holiday=holiday,
            running=running,
            slept=slept,
            **extra,
        )
        slept = night.house_asleep_since(config, world)
        worlds.append(replace(world, asleep_since=slept))
    return worlds[-1]


def shut(config: DirectorConfig, world: WorldState) -> tuple[Reason, ...]:
    """Return every gate shut on the living room."""
    zone = config.zone("woonkamer")
    assert isinstance(zone, Zone)
    return gates.closed(config, world, zone)


#: De nacht van maandag op dinsdag waarin beiden thuis naar bed gaan.
#: The night from Monday into Tuesday in which both residents turn in at home.
SLEPT: list[Step] = [turning_in(MON)]

#: Diezelfde nacht, maar Nancy is de deur uit: Danny is de enige die thuis slaapt.
#: That same night, but Nancy is away: Danny is the only one asleep at home.
ALONE: list[Step] = [turning_in(MON, nancy="away")]

#: De nacht van vrijdag op zaterdag, waarin beiden thuis naar bed gaan.
#: The night from Friday into Saturday, in which both turn in at home.
FRIDAY: list[Step] = [turning_in(FRI)]


class TestTheCases:
    """De twaalf gevallen, elk met het gewenste gedrag. The twelve cases."""

    def test_wens2_1_danny_up_early_nancy_asleep(self) -> None:
        """1: di 05:50, werkdag, Danny op, Nancy slaapt: het huis start niet."""
        world = walk(live_house(), [*SLEPT, getting_up(TUE, 5, 50)])
        found = shut(live_house(), world)
        assert found and found[0] is Reason.EARLY_RISER

    def test_wens2_2_danny_up_early_nancy_away(self) -> None:
        """2: di 05:50, werkdag, Danny op en de enige thuis, Nancy weg: `early_riser`.

        Dit is het geval dat niet remde zolang het moment verviel zodra er niemand thuis
        meer sliep: de bewoner met de rem stond op, en daarmee was het slaapmoment van het
        huis weg. Wie alleen thuis opstaat na een nacht slapen hoort geremd te worden.

        This is the case that did not brake as long as the moment lapsed the once nobody at
        home was asleep: the resident with the brake got up, and with that the house's sleep
        moment was gone. Whoever gets up alone at home after a night's sleep should be braked.
        """
        world = walk(live_house(), [*ALONE, getting_up(TUE, 5, 50, nancy="away")])
        found = shut(live_house(), world)
        assert found and found[0] is Reason.EARLY_RISER

    def test_wens2_3_nancy_gets_up_too(self) -> None:
        """3: di 06:10, werkdag, Danny op en Nancy staat op: het huis start."""
        world = walk(live_house(), [*SLEPT, getting_up(TUE, 6, 10, nancy="up")])
        assert shut(live_house(), world) == ()

    def test_wens2_4_the_brake_is_over(self) -> None:
        """4: di 07:05, werkdag, Danny nog thuis, Nancy weg: het huis start."""
        world = walk(live_house(), [*ALONE, getting_up(TUE, 7, 5, nancy="away")])
        assert shut(live_house(), world) == ()

    def test_wens2_5_holiday_nancy_away(self) -> None:
        """5: di 05:50, vakantie, Danny op, Nancy niet thuis: het huis start."""
        world = walk(live_house(), [*ALONE, getting_up(TUE, 5, 50, nancy="away")], holiday=True)
        assert shut(live_house(), world) == ()

    def test_wens2_6_holiday_nancy_asleep(self) -> None:
        """6: di 05:50, vakantie, Danny op, Nancy slaapt: `waiting_for_sleeper`."""
        world = walk(live_house(), [*SLEPT, getting_up(TUE, 5, 50)], holiday=True)
        found = shut(live_house(), world)
        assert found and found[0] is Reason.WAITING_FOR_SLEEPER

    def test_wens2_7_holiday_eleven(self) -> None:
        """7: di 11:00, vakantie, Danny op, Nancy slaapt nog: het huis start."""
        world = walk(live_house(), [*SLEPT, getting_up(TUE, 11, 0)], holiday=True)
        assert shut(live_house(), world) == ()

    def test_wens2_8_saturday_nancy_asleep(self) -> None:
        """8: za 05:50, geen vakantie, Danny op, Nancy slaapt: wachten tot 11:00."""
        world = walk(live_house(), [*FRIDAY, getting_up(SAT, 5, 50)])
        found = shut(live_house(), world)
        assert found and found[0] is Reason.WAITING_FOR_SLEEPER

    def test_wens2_9_saturday_nancy_away(self) -> None:
        """9: za 05:50, geen vakantie, Danny op, Nancy weg: de rem geldt alleen ma-vr."""
        world = walk(live_house(), [*FRIDAY, getting_up(SAT, 5, 50, nancy="away")])
        assert shut(live_house(), world) == ()

    def test_wens2_10_a_running_zone_keeps_running(self) -> None:
        """10: di 06:15, de zone draait al (Nancy was op en is weg), Danny op."""
        world = walk(live_house(), [*ALONE, getting_up(TUE, 6, 15, nancy="away")], running=True)
        assert shut(live_house(), world) == ()

    def test_wens2_11_the_quiet_window_is_unchanged(self) -> None:
        """11: di 22:00, thuiskomst na het begin van het stiltevenster: geremd door de stilte."""
        homecoming = awake(home_since=at(21, 30, day=TUE))
        world = walk(live_house(), [(at(22, 0, day=TUE), homecoming, away())])
        found = shut(live_house(), world)
        assert found and found[0] is Reason.QUIET_HOURS

    def test_wens2_12_the_roles_reversed(self) -> None:
        """12: als 2, met de rollen omgedraaid: Nancy heeft de rem, Danny is weg."""
        config = live_house(danny=False, nancy=True)
        world = walk(
            config,
            [turning_in(MON, nancy="away"), getting_up(TUE, 5, 50, danny="away", nancy="up")],
        )
        found = shut(config, world)
        assert found and found[0] is Reason.EARLY_RISER


class TestTheEdges:
    """Waar de rem niet hoort te komen. Where the brake should not reach."""

    def test_guest_mode_inside_its_window_lifts_the_brake(self) -> None:
        """Binnen het gastenvenster logeert er iemand: de rem geldt niet."""
        world = walk(live_house(), [*ALONE, getting_up(TUE, 5, 50, nancy="away")], guest_mode=True)
        assert Reason.EARLY_RISER not in shut(live_house(), world)

    def test_a_request_by_hand_always_starts_the_house(self) -> None:
        """Een vooruit-verzoek gaat voor alles wat over mensen gaat, ook voor de rem."""
        now = at(5, 50, day=TUE)
        world = walk(
            live_house(),
            [*ALONE, getting_up(TUE, 5, 50, nancy="away")],
            precondition_until={"woonkamer": now + timedelta(hours=1)},
        )
        assert shut(live_house(), world) == ()

    def test_somebody_still_up_from_the_evening_is_no_early_riser(self) -> None:
        """Di 00:30, Danny is nog op van de avond ervoor: het moment is van gisteren.

        De rem eist een moment uit de lopende nacht: wie om half één nog op is, staat niet
        op, ook al staat er een moment in de opslag.

        The brake demands a moment from the running night: whoever is still up at half past
        midnight is not getting up, even with a moment in the storage.
        """
        world = night_world(
            now=at(0, 30, day=TUE),
            danny=up(TUE),
            nancy=away(),
            slept=at(1, 0, day=MON),
        )
        assert Reason.EARLY_RISER not in shut(live_house(), world)

    def test_an_unknown_moment_brakes_nobody(self) -> None:
        """Na een herstart zonder bekend slaapmoment remt de rem niemand."""
        config = live_house()
        world = night_world(now=at(5, 50, day=TUE), danny=up(TUE), nancy=away())
        assert Reason.EARLY_RISER not in shut(config, world)

    def test_an_empty_time_brakes_nobody(self) -> None:
        """Zonder tijd is er geen rem: het gedrag van vóór deze instelling."""
        config = live_house(danny=False)
        world = night_world(
            now=at(5, 50, day=TUE),
            danny=up(TUE),
            nancy=away(),
            slept=at(1, 0, day=TUE),
        )
        assert shut(config, world) == ()

    def test_every_day_when_no_days_are_ticked(self) -> None:
        """Zonder dagen geldt de rem elke dag, ook op zaterdag."""
        config = with_brakes(live_house(), danny=RiseBrake(at=time(7, 0)))
        world = walk(config, [turning_in(FRI, nancy="away"), getting_up(SAT, 5, 50, nancy="away")])
        found = shut(config, world)
        assert found and found[0] is Reason.EARLY_RISER


class TestStorage:
    def test_the_brake_round_trips(self) -> None:
        """De rem komt ongeschonden terug uit de opslag, en zonder tijd is er geen rem."""
        config = live_house()
        again = config_from_dict(config_to_dict(config))
        assert again.residents[0].rise_brake == RiseBrake(at=time(7, 0), weekdays=WORKDAYS)
        assert again.residents[1].rise_brake is None
        stored = config_to_dict(config)
        stored["residents"][0]["rise_brake"] = {"at": "", "weekdays": [0, 1]}
        assert config_from_dict(stored).residents[0].rise_brake is None

    @pytest.mark.parametrize("stored", [None, {}, "x"])
    def test_an_old_store_without_the_brake_loads(self, stored: object) -> None:
        raw = config_to_dict(house())
        for resident in raw["residents"]:
            resident.pop("rise_brake", None)
            if stored is not None:
                resident["rise_brake"] = stored
        assert all(resident.rise_brake is None for resident in config_from_dict(raw).residents)
