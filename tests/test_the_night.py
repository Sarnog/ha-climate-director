"""*Wacht op deze slaper* pas als iedereen die thuis is naar bed is geweest.

*Wait for this sleeper* only once everybody at home has been to bed.

Gaat de één om elf uur naar bed terwijl de ander nog op is, dan is het na middernacht
al "vandaag, vóór de uiterste tijd". Zonder nachtbegrip stopte het huis dan, terwijl
er nog iemand zat. De regel: het huis wacht 's ochtends alleen op een slaper als het
deze nacht geslapen heeft, dus als iedereen die thuis was naar bed is geweest
(`engine/night.py`).

Elke toets hier loopt de nacht af zoals de koppelingslaag dat doet: ronde na ronde
`night.house_asleep_since`, met de uitkomst als moment voor de volgende ronde. De
instellingen zijn die van een echt huis: slaapvenster 21:00–08:00 elke dag,
uitslapen tot 13:00 op zaterdag en zondag en op vakantiedagen, wachten tot 11:00 op
zaterdag en zondag en op vakantiedagen, en de stiltevensters 21:00–09:00 (ma–do, zo)
en 23:00–09:00 (vr, za). De gevallen N1–N12 staan bij naam in de toets-id's; het
vastleggen en herstellen in een draaiende Home Assistant staat in
`tests/test_the_night_live.py`.

When one resident turns in at eleven while the other is still up, it is already
"today, before the deadline" after midnight. Without a notion of night the house
then stopped, while somebody was still sitting there. The rule: in the morning the
house only waits for a sleeper when it has slept this night, so when everybody who
was home has been to bed (`engine/night.py`).

Every test here walks the night the way the binding layer does: round after round
`night.house_asleep_since`, with the outcome as the moment for the next round. The
settings are those of a real house: sleep window 21:00–08:00 every day, sleeping in
until 13:00 on Saturday and Sunday and on holidays, waiting until 11:00 on Saturday
and Sunday and on holidays, and the quiet windows 21:00–09:00 (Mon–Thu, Sun) and
23:00–09:00 (Fri, Sat). The cases N1–N12 stand by name in the test ids; the recording
and restoring inside a running Home Assistant is in `tests/test_the_night_live.py`.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, time

import pytest
from conftest import ATTIC, BEDROOM, GAS, LIVING, asleep, at, awake, away, house, make_world

from custom_components.climate_director.engine import (
    DirectorConfig,
    ModeFamily,
    Reason,
    ResidentState,
    SleepIn,
    TimeWindow,
    WakeDeadline,
    WorldState,
    Zone,
    decide,
    gates,
    night,
)

MON, TUE, WED, FRI, SAT, SUN = 10, 11, 12, 14, 15, 16

#: Iedereen was al thuis vóór de stiltevensters van die avond begonnen.
#: Everybody was home before that evening's quiet windows began.
HOME = at(18, 0, day=FRI)


def live_house() -> DirectorConfig:
    """Return the standard house with the sleep and quiet settings of a real one."""
    config = house()
    weekend = frozenset({5, 6})
    return replace(
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


def up(home_since: datetime = HOME) -> ResidentState:
    return awake(home_since=home_since)


def bed(home_since: datetime = HOME) -> ResidentState:
    return asleep(home_since=home_since)


Step = tuple[datetime, ResidentState, ResidentState]


def walk(
    config: DirectorConfig,
    steps: list[Step],
    *,
    running: bool = False,
    holiday: bool = False,
    since: datetime | None = None,
) -> list[WorldState]:
    """Walk the night round by round, carrying the moment the way the binding layer does."""
    worlds = []
    for now, danny, nancy in steps:
        world = make_world(
            now=now,
            outdoor=10.0,
            indoor={"woonkamer": 18.0, "zolder": 18.0, "slaapkamer": 18.0},
            climates={
                LIVING: "heat" if running else "off",
                GAS: "off",
                ATTIC: "off",
                BEDROOM: "off",
            },
            residents={"danny": danny, "nancy": nancy},
            holiday_mode=holiday,
            asleep_since=since,
        )
        since = night.house_asleep_since(config, world)
        worlds.append(replace(world, asleep_since=since))
    return worlds


def shut(config: DirectorConfig, world: WorldState) -> tuple[Reason, ...]:
    """Return every gate shut on the living room."""
    zone = config.zone("woonkamer")
    assert isinstance(zone, Zone)
    return gates.closed(config, world, zone)


#: Vrijdagavond: Nancy gaat om 22:00 naar bed, Danny blijft op.
#: Friday evening: Nancy turns in at 22:00, Danny stays up.
EVENING: list[Step] = [
    (at(21, 30, day=FRI), up(), up()),
    (at(22, 0, day=FRI), up(), bed()),
    (at(23, 30, day=FRI), up(), bed()),
    (at(0, 30, day=SAT), up(), bed()),
]

#: En daarna gaat Danny om 01:30 ook naar bed. And then Danny turns in too at 01:30.
BOTH_IN_BED: list[Step] = [*EVENING, (at(1, 30, day=SAT), bed(), bed())]


class TestTheNight:
    def test_n1_a_running_zone_keeps_running_while_somebody_is_up(self) -> None:
        """N1: za 00:30, Nancy in bed, Danny op, de zone draait: ze blijft draaien."""
        worlds = walk(live_house(), EVENING, running=True)
        assert shut(live_house(), worlds[-1]) == ()

    def test_n2_the_house_starts_for_whoever_is_still_up(self) -> None:
        """N2: za 00:30, de zone staat uit en het is te koud: het huis start.

        Danny was vóór het stiltevenster van 23:00 thuis, dus die remt niet (anker
        13), en Nancy houdt niemand tegen: het huis heeft nog niet geslapen.

        Danny was home before the 23:00 quiet window, so that does not brake (anchor
        13), and Nancy holds nobody back: the house has not slept yet.
        """
        config = live_house()
        world = walk(config, EVENING)[-1]
        assert world.asleep_since is None
        assert shut(config, world) == ()
        decision = decide(config, world, None).decision_for("woonkamer")
        assert decision is not None and decision.granted is ModeFamily.HEAT

    def test_n3_when_the_last_one_turns_in_the_house_goes_off(self) -> None:
        """N3: za 01:30, Danny gaat ook naar bed: `everyone_asleep`, zoals altijd."""
        world = walk(live_house(), BOTH_IN_BED)[-1]
        assert world.asleep_since == at(1, 30, day=SAT)
        assert shut(live_house(), world)[0] is Reason.EVERYONE_ASLEEP

    def test_n4_in_the_morning_the_house_waits_for_the_last_sleeper(self) -> None:
        """N4: za 07:00, Danny op, Nancy slaapt: wachten tot Nancy op is of tot 11:00."""
        steps = [*BOTH_IN_BED, (at(7, 0, day=SAT), up(), bed())]
        assert shut(live_house(), walk(live_house(), steps)[-1])[0] is (Reason.WAITING_FOR_SLEEPER)

    def test_n5_the_deadline_releases_the_house(self) -> None:
        """N5: za 11:00, Nancy slaapt nog (uitslapen tot 13:00): het huis start."""
        steps = [*BOTH_IN_BED, (at(7, 0, day=SAT), up(), bed()), (at(11, 0, day=SAT), up(), bed())]
        world = walk(live_house(), steps)[-1]
        assert world.asleep_since == at(1, 30, day=SAT)
        assert shut(live_house(), world) == ()

    @pytest.mark.parametrize(
        ("first", "holiday"),
        [pytest.param(FRI, False, id="N6"), pytest.param(TUE, True, id="N6-vakantie")],
    )
    def test_n6_somebody_up_all_night_is_never_held_back(self, first: int, holiday: bool) -> None:
        """N6: Danny blijft de hele nacht op; Nancy houdt het huis nooit tegen.

        Ook in een vakantienacht midden in de week (de probe: wo 00:30, vakantie),
        waar het wachten tot 11:00 anders al na middernacht gold.

        Also on a holiday night in the middle of the week (the probe: Wed 00:30,
        holiday), where waiting until 11:00 otherwise applied from midnight.
        """
        config = live_house()
        steps: list[Step] = [(at(22, 0, day=first), up(), bed())]
        steps += [(at(23, 0, day=first), up(), bed())]
        steps += [(at(hour, 0, day=first + 1), up(), bed()) for hour in range(11)]
        for world in walk(config, steps, holiday=holiday):
            assert world.asleep_since is None, world.now
            assert Reason.WAITING_FOR_SLEEPER not in shut(config, world), world.now

    def test_n9_a_late_second_sleeper_still_starts_the_night(self) -> None:
        """N9: Nancy om 22:00 naar bed, Danny om 00:30; 's ochtends wordt er gewacht."""
        config = live_house()
        steps = [
            (at(22, 0, day=FRI), up(), bed()),
            (at(0, 15, day=SAT), up(), bed()),
            (at(0, 30, day=SAT), bed(), bed()),
            (at(7, 0, day=SAT), up(), bed()),
        ]
        worlds = walk(config, steps)
        assert Reason.WAITING_FOR_SLEEPER not in shut(config, worlds[1])
        assert worlds[-1].asleep_since == at(0, 30, day=SAT)
        assert shut(config, worlds[-1])[0] is Reason.WAITING_FOR_SLEEPER

    def test_n10_last_nights_moment_does_not_count_tonight(self) -> None:
        """N10: het moment van vrijdagnacht telt zaterdagnacht niet mee.

        Het moment blijft staan zolang er iemand thuis op is - dat is het bijhouden
        - maar het valt vóór het begin van Nancy's lopende nacht (za 21:00), dus
        wordt er niet op gewacht.

        The moment stays while somebody at home is up - that is the bookkeeping -
        but it falls before the beginning of Nancy's current night (Sat 21:00), so
        nobody waits on it.
        """
        config = live_house()
        friday_night = at(1, 30, day=SAT)
        world = walk(config, [(at(0, 30, day=SUN), up(), bed())], since=friday_night)[-1]
        assert world.asleep_since == friday_night
        assert Reason.WAITING_FOR_SLEEPER not in shut(config, world)

    def test_n11_getting_up_briefly_at_night_does_not_start_the_house(self) -> None:
        """N11: Danny staat om 03:00 even op, Nancy slaapt: het huis start niet."""
        steps = [*BOTH_IN_BED, (at(3, 0, day=SAT), up(), bed())]
        world = walk(live_house(), steps)[-1]
        assert world.asleep_since == at(1, 30, day=SAT)
        assert shut(live_house(), world)[0] is Reason.WAITING_FOR_SLEEPER

    def test_n12_a_weekday_without_a_deadline_is_unchanged(self) -> None:
        """N12: doordeweeks, zonder uiterste tijd: wie op is zet het huis aan."""
        steps = [
            (at(22, 0, day=MON), up(home_since=at(18, 0, day=MON)), bed(at(18, 0, day=MON))),
            (at(23, 0, day=MON), bed(at(18, 0, day=MON)), bed(at(18, 0, day=MON))),
            (at(7, 0, day=TUE), up(at(18, 0, day=MON)), bed(at(18, 0, day=MON))),
        ]
        world = walk(live_house(), steps)[-1]
        assert world.asleep_since == at(23, 0, day=MON)
        assert shut(live_house(), world) == ()


class TestTheMoment:
    """Het bijhouden zelf, los van de poort. The bookkeeping itself, apart from the gate."""

    def test_nobody_asleep_at_home_keeps_the_moment_within_the_night(self) -> None:
        """Er slaapt niemand thuis, maar het moment valt nog in de lopende nacht.

        Wie opstaat maakt de nacht niet ongedaan: het moment waarop het huis ging slapen
        blijft staan zolang het in iemands lopende nacht valt. Daar hangt de opsta-rem aan
        (*Opstaan zet het huis pas aan vanaf*), ook als de bewoner met de rem de enige is
        die thuis opstaat; vervalt het bij het opstaan, dan remt die rem niets meer.

        Nobody at home is asleep, but the moment still falls inside the running night:
        getting up does not undo the night, and the rise brake hangs on that moment.
        """
        worlds = walk(
            live_house(),
            [(at(1, 30, day=SAT), bed(), bed()), (at(9, 0, day=SAT), up(), away())],
        )
        assert [world.asleep_since for world in worlds] == [
            at(1, 30, day=SAT),
            at(1, 30, day=SAT),
        ]

    def test_the_moment_lapses_when_the_next_night_begins(self) -> None:
        """Het moment blijft de hele dag staan en vervalt bij het begin van de volgende nacht.

        Om 21:00 's avonds begint de volgende nacht van de bewoners, en dan valt het moment
        van de nacht ervoor erbuiten: vanaf dat moment is het weg.

        The moment stays all day and lapses when the next night begins: from 21:00 in the
        evening the moment of the night before falls outside the running night.
        """
        worlds = walk(
            live_house(),
            [
                (at(1, 30, day=SAT), bed(), bed()),
                (at(9, 0, day=SAT), up(), up()),
                (at(20, 59, day=SAT), up(), up()),
                (at(21, 0, day=SAT), up(), up()),
            ],
        )
        assert [world.asleep_since for world in worlds] == [
            at(1, 30, day=SAT),
            at(1, 30, day=SAT),
            at(1, 30, day=SAT),
            None,
        ]

    def test_last_nights_moment_no_longer_counts_on_the_next_evening(self) -> None:
        """Het moment van vrijdagnacht telt op zaterdagavond niet meer mee."""
        config = live_house()
        world = walk(config, [(at(21, 30, day=SAT), up(), up())], since=at(1, 30, day=SAT))[-1]
        assert world.asleep_since is None
        assert not any(night.slept_tonight(resident, world) for resident in config.residents)

    def test_without_a_sleep_window_the_moment_lapses_at_getting_up(self) -> None:
        """Zonder slaapvenster is er geen nacht om het moment aan af te lezen: het vervalt.

        De bewoners van de standaardopstelling hebben geen slaapvenster; de grens tussen
        twee nachten is daar het moment zelf. Zodra er niemand thuis meer slaapt is er dus
        geen lopende nacht om het moment in te plaatsen en is het weg - met als prijs dat de
        opsta-rem in zo'n huis niets doet. Dat staat als idee in `ROADMAP.md`.

        Without a sleep window there is no night to read the moment against, so it lapses
        the moment nobody at home is asleep any more - at the price that the rise brake does
        nothing in such a house, which stands as an idea in `ROADMAP.md`.
        """
        config = house()
        worlds = walk(
            config,
            [(at(23, 0, day=MON), bed(), away()), (at(6, 0, day=TUE), up(), away())],
        )
        assert [world.asleep_since for world in worlds] == [at(23, 0, day=MON), None]

    def test_a_house_asleep_since_last_night_starts_a_new_night(self) -> None:
        """Slaapt iedereen, maar is het moment van gisternacht, dan is het nu."""
        world = walk(live_house(), [(at(23, 30, day=SAT), bed(), bed())], since=at(1, 30, day=SAT))[
            -1
        ]
        assert world.asleep_since == at(23, 30, day=SAT)

    def test_the_night_begins_at_the_latest_start_on_a_day_it_applies(self) -> None:
        resident = replace(
            house().residents[0],
            sleep_window=TimeWindow(time(23, 0), time(9, 0), weekdays=frozenset({4, 5})),
        )
        assert night.night_began(resident, at(7, 0, day=SAT)) == at(23, 0, day=FRI)
        assert night.night_began(resident, at(7, 0, day=MON)) == at(23, 0, day=8)
        assert night.night_began(replace(resident, sleep_window=None), at(7, 0, day=MON)) is None

    def test_without_a_sleep_window_any_known_moment_counts(self) -> None:
        """Zonder slaapvenster is de grens tussen twee nachten het vergeten van het moment."""
        config = house()
        world = make_world(
            now=at(10, 0, day=SAT),
            residents={"danny": awake(), "nancy": asleep()},
            asleep_since=at(1, 0, day=WED),
        )
        resident = config.residents[1]
        assert night.slept_tonight(resident, world)
