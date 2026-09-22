"""Uren waarin de director uit zichzelf niets begint.

Hours in which the director starts nothing of its own accord.

Thuiskomen om elf uur 's avonds terwijl je zo naar bed gaat, hoeft het huis niet
te laten opstoken. Maar het is een rem op beginnen, niet op doorgaan: wat al
draait blijft gewoon geregeld, en zet iemand zelf iets aan, dan wordt dat
opgepakt. Zou de rem ook het doorgaan raken, dan was het een tweede rooster - en
dan zou je 's avonds niets meer met de hand kunnen aanzetten.

Een venster remt alleen wie er **ná het begin van dat venster** thuiskomt. Wie er
al zat toen het venster inging, zit er wakker bij en houdt het huis aan de gang;
komt er in een leeg huis iemand thuis ná het begin, dan blijft het stil tot het
venster afloopt. Zonder bekend thuiskomstmoment (`home_since`) remt het venster
zoals altijd: stilte is de veilige kant om fout te zitten.

Coming home at eleven at night when you are about to turn in need not fire the
boiler. But it is a brake on starting, not on continuing: whatever already runs
stays regulated, and switching something on yourself is picked up. Were the brake
to touch continuing as well it would be a second schedule - and then you could no
longer switch anything on by hand in the evening.

A window brakes only whoever comes home **after that window began**. Whoever was
already sitting there when it began keeps the house going; when somebody comes
home to an empty house after the beginning, it stays quiet until the window
lapses. Without a known homecoming moment (`home_since`) the window brakes as it
always did: quiet is the safe side to be wrong on.
"""

from __future__ import annotations

from datetime import datetime, time

import pytest
from conftest import asleep, awake, away, gate_verdict, make_world

from custom_components.climate_director.engine import (
    DirectorConfig,
    GateSettings,
    ModeSettings,
    Reason,
    Resident,
    Source,
    TimeWindow,
    Zone,
)
from custom_components.climate_director.engine.serialise import config_from_dict, config_to_dict
from custom_components.climate_director.engine.world import PresenceState, ResidentState

LIVING = "climate.huiskamer"

#: 17 augustus 2026 is een maandag, 21 augustus een vrijdag.
#: 17 August 2026 is a Monday, 21 August a Friday.
MONDAY = 17
FRIDAY = 21

WEEK = frozenset({0, 1, 2, 3, 6})
WEEKEND = frozenset({4, 5})

#: Zijn eigen vensters, omgekeerd: de uren waarin er niets mag beginnen.
#: His own windows, inverted: the hours in which nothing may start.
HIS = (
    TimeWindow(time(21, 0), time(9, 0), WEEK),
    TimeWindow(time(23, 0), time(9, 0), WEEKEND),
)


def house(*windows: TimeWindow) -> DirectorConfig:
    return DirectorConfig(
        zones=(
            Zone(
                "woonkamer",
                "Woonkamer",
                "sensor.woonkamer",
                sources=(Source("w", LIVING),),
                heat=ModeSettings(23.0, 22.0),
            ),
        ),
        residents=(Resident("danny", "Danny", presence_entity="person.danny"),),
        gates=GateSettings(quiet_windows=windows),
    )


def verdict(
    config: DirectorConfig, hour: int, running: str, *, day: int = MONDAY, holiday: bool = False
):
    return verdict_at(
        config,
        datetime(2026, 8, day, hour, 0),
        running,
        holiday=holiday,
    )


def verdict_at(
    config: DirectorConfig,
    moment: datetime,
    running: str,
    *,
    home_since: datetime | None = None,
    holiday: bool = False,
    guest_mode: bool = False,
    residents=None,
):
    """Return the gate verdict for one moment of one installation.

    `home_since` is het thuiskomstmoment van anker 13; laat je het weg, dan is het
    onbekend en remt een stiltevenster zoals het altijd deed.
    """
    zone = config.zone("woonkamer")
    assert zone is not None
    world = make_world(
        now=moment,
        indoor={"woonkamer": 18.0},
        climates={LIVING: running},
        residents={"danny": awake(home_since=home_since)} if residents is None else residents,
        presence={"woonkamer": PresenceState(occupied=True)},
        holiday_mode=holiday,
        guest_mode=guest_mode,
    )
    return gate_verdict(config, world, zone)


class TestItBrakesStarting:
    @pytest.mark.parametrize("hour", [21, 23, 3, 8])
    def test_nothing_starts_inside_the_window(self, hour: int) -> None:
        """Zonder bekend thuiskomstmoment remt het venster: de stille kant.

        Zonder `home_since` valt er niets te vergelijken en is stilte de veilige
        kant om fout te zitten; deze test legt dat gedrag vast (was: elke bewoner
        die thuis en wakker was, hield het huis tegen).
        """
        assert verdict(house(*HIS), hour, "off").reason is Reason.QUIET_HOURS

    @pytest.mark.parametrize("hour", [9, 12, 17, 20])
    def test_outside_it_everything_is_normal(self, hour: int) -> None:
        assert verdict(house(*HIS), hour, "off").allowed

    def test_the_weekday_matters(self) -> None:
        """At 22:00 the week is quiet; Friday runs until eleven."""
        assert verdict(house(*HIS), 22, "off", day=MONDAY).reason is Reason.QUIET_HOURS
        assert verdict(house(*HIS), 22, "off", day=FRIDAY).allowed


class TestOnlyHomecomersAreBraked:
    """Anker 13: een venster remt wie er ná zijn begin thuiskwam, niet wie er al was.

    Het venster loopt van 21:00 tot 09:00, dus het begint op de dag zelf en, in de
    nacht erna, op de dag ervoor. `home_since` vóór dat begin laat de zones gewoon
    regelen; op het begin of daarna - en een onbekend moment - remt het venster.

    Anchor 13: a window brakes whoever came home after it began, not whoever was
    already there. The window runs from 21:00 to 09:00, so it begins on the day
    itself and, in the night after, on the day before. A `home_since` before that
    beginning lets the zones regulate; on the beginning or after it - and an
    unknown moment - the window brakes.

    Bovendien: het venster in de nacht erna is hetzelfde venster, dus het begin
    ligt op de dag ervoor en niet om 21:00 van de nacht zelf.
    """

    #: Het venster begon maandag 21:00 (maandag 17 augustus 2026).
    EVENING = datetime(2026, 8, MONDAY, 21, 10)
    #: De nacht erna: dinsdag 02:00, met het begin nog steeds maandag 21:00.
    NIGHT = datetime(2026, 8, 18, 2, 0)
    HOME_EARLY = datetime(2026, 8, MONDAY, 18, 0)
    JUST_BEFORE = datetime(2026, 8, MONDAY, 20, 59, 59)
    ON_THE_HOUR = datetime(2026, 8, MONDAY, 21, 0, 0)
    LATE = datetime(2026, 8, MONDAY, 21, 30)

    @pytest.mark.parametrize(
        ("home_since", "expected"),
        [
            pytest.param(HOME_EARLY, "allowed", id="18:00"),
            pytest.param(JUST_BEFORE, "allowed", id="20:59:59"),
            pytest.param(ON_THE_HOUR, "quiet", id="21:00:00-precies"),
            pytest.param(LATE, "quiet", id="21:30"),
            pytest.param(None, "quiet", id="onbekend"),
        ],
    )
    @pytest.mark.parametrize("moment", [EVENING, NIGHT], ids=["21:10", "02:00-nacht-erna"])
    def test_who_was_home_before_the_window_began_regulates_on(
        self, moment: datetime, home_since: datetime | None, expected: str
    ) -> None:
        found = verdict_at(house(*HIS), moment, "off", home_since=home_since)
        if expected == "allowed":
            assert found.allowed
        else:
            assert found.reason is Reason.QUIET_HOURS

    def test_a_window_that_has_not_started_returns_no_beginning(self) -> None:
        """Buiten het venster is er geen lopende voorkomst, dus geen begintijd.

        Deze tak bestaat echt: de lezer vraagt het alleen voor een venster dat
        openstaat, en juist daarom mag "geen begintijd" geen stilte opleveren.
        """
        window = TimeWindow(time(21, 0), time(9, 0), WEEK)
        assert window.started_at(datetime(2026, 8, MONDAY, 12, 0)) is None

    def test_a_daytime_window_begins_today(self) -> None:
        """Een gewoon venster (einde ná begin) begint vandaag, niet gisteren."""
        window = TimeWindow(time(8, 0), time(18, 0))
        assert window.started_at(datetime(2026, 8, MONDAY, 12, 0)) == datetime(
            2026, 8, MONDAY, 8, 0
        )

    def test_an_evening_window_begins_today(self) -> None:
        """Vóór middernacht begint een nachtvenster vandaag om zijn starttijd."""
        window = TimeWindow(time(21, 0), time(9, 0), WEEK)
        assert window.started_at(datetime(2026, 8, MONDAY, 22, 0)) == datetime(
            2026, 8, MONDAY, 21, 0
        )

    def test_an_after_midnight_window_begins_yesterday(self) -> None:
        """Ná middernacht begint het op de startdag: maandag 21:00, niet 00:00."""
        window = TimeWindow(time(21, 0), time(9, 0), WEEK)
        assert window.started_at(datetime(2026, 8, 18, 2, 0)) == datetime(2026, 8, MONDAY, 21, 0)

    def test_the_start_day_skips_the_days_this_window_does_not_apply(self) -> None:
        """Een vrijdagvenster dat op zondag nog loopt begon op vrijdag.

        Het venster 23:00-09:00 van vrijdag loopt tot zaterdag 09:00, en op
        zaterdag 02:00 is de lopende voorkomst dus die van vrijdag - niet die van
        de dag ervoor op dezelfde kloktijd.
        """
        window = TimeWindow(time(23, 0), time(9, 0), WEEKEND)
        assert window.started_at(datetime(2026, 8, 22, 2, 0)) == datetime(2026, 8, FRIDAY, 23, 0)

    def test_a_resident_who_left_and_came_back_is_a_homecomer(self) -> None:
        """Vertrek wist het moment, terugkomst zet het opnieuw (anker 13).

        Om 21:30 was hij weg - zijn moment is vervallen - en om 23:00 komt hij
        terug met een vers moment, dus ná het begin van 21:00: stil.
        """
        found = verdict_at(
            house(*HIS),
            datetime(2026, 8, MONDAY, 23, 0),
            "off",
            residents={"danny": away()},
        )
        assert found.reason is Reason.QUIET_HOURS

        again = verdict_at(
            house(*HIS),
            datetime(2026, 8, MONDAY, 23, 0),
            "off",
            home_since=datetime(2026, 8, MONDAY, 23, 0),
        )
        assert again.reason is Reason.QUIET_HOURS

    def test_the_awake_sleeper_need_not_be_the_one_who_was_home(self) -> None:
        """Twee losse voorwaarden, twee verschillende bewoners (besluit 2).

        Nancy was al thuis sinds 18:00 en ligt in bed; Danny komt om 22:00 thuis
        en is wakker. De stilte valt weg door Nancy, de slaappoort laat het door
        omdat Danny op is.
        """
        config = DirectorConfig(
            zones=(
                Zone(
                    "woonkamer",
                    "Woonkamer",
                    "sensor.woonkamer",
                    sources=(Source("w", LIVING),),
                    heat=ModeSettings(23.0, 22.0),
                ),
            ),
            residents=(
                Resident("nancy", "Nancy", presence_entity="person.nancy"),
                Resident("danny", "Danny", presence_entity="person.danny"),
            ),
            gates=GateSettings(quiet_windows=HIS),
        )
        residents = {
            "nancy": asleep(home_since=datetime(2026, 8, MONDAY, 18, 0)),
            "danny": awake(home_since=datetime(2026, 8, MONDAY, 22, 0)),
        }
        allowed = verdict_at(config, self.NIGHT, "off", residents=residents)
        assert allowed.allowed

    def test_an_early_sleeper_alone_leaves_the_sleep_gate_in_charge(self) -> None:
        """Nancy sinds 18:00 en asleep, Danny weg: de slaappoort, niet de stilte.

        De stilte remt niet - Nancy was er al - maar de slaappoort doet het
        wél, en die noemt zichzelf: `EVERYONE_ASLEEP`, niet `QUIET_HOURS`.
        """
        config = DirectorConfig(
            zones=(
                Zone(
                    "woonkamer",
                    "Woonkamer",
                    "sensor.woonkamer",
                    sources=(Source("w", LIVING),),
                    heat=ModeSettings(23.0, 22.0),
                ),
            ),
            residents=(
                Resident("nancy", "Nancy", presence_entity="person.nancy"),
                Resident("danny", "Danny", presence_entity="person.danny"),
            ),
            gates=GateSettings(quiet_windows=HIS, require_awake=True),
        )
        residents = {
            "nancy": asleep(home_since=datetime(2026, 8, MONDAY, 18, 0)),
            "danny": away(),
        }
        found = verdict_at(config, self.NIGHT, "off", residents=residents)
        assert found.reason is Reason.EVERYONE_ASLEEP


class TestGuestsLiftTheQuiet:
    """Besluit 5: gastenmodus heft de stilte op, maar alleen binnen zijn venster."""

    #: Gastenvenster 08:00-23:00, zoals in productie.
    GUEST = TimeWindow(time(8, 0), time(23, 0))

    def _house(self, guest_window: TimeWindow | None) -> DirectorConfig:
        base = house(*HIS)
        return DirectorConfig(
            zones=base.zones,
            residents=base.residents,
            gates=GateSettings(quiet_windows=base.gates.quiet_windows, guest_window=guest_window),
        )

    def test_inside_the_guest_window_the_quiet_is_lifted(self) -> None:
        """22:00 valt binnen het gastenvenster: er is iemand, dus geen stilte."""
        found = verdict_at(
            self._house(self.GUEST),
            datetime(2026, 8, MONDAY, 22, 0),
            "off",
            guest_mode=True,
        )
        assert found.allowed

    def test_outside_the_guest_window_the_ordinary_rules_return(self) -> None:
        """01:00 valt buiten het gastenvenster: de gewone stilte geldt weer."""
        found = verdict_at(
            self._house(self.GUEST),
            datetime(2026, 8, 18, 1, 0),
            "off",
            guest_mode=True,
        )
        assert found.reason is Reason.QUIET_HOURS

    def test_without_a_guest_window_the_guests_carry_the_whole_night(self) -> None:
        """Geen gastenvenster betekent de hele dag, dus ook om 01:00."""
        found = verdict_at(
            self._house(None),
            datetime(2026, 8, 18, 1, 0),
            "off",
            guest_mode=True,
        )
        assert found.allowed

    @pytest.mark.parametrize("hour", [9, 12, 17, 20])
    def test_outside_it_everything_is_normal(self, hour: int) -> None:
        assert verdict(house(*HIS), hour, "off").allowed

    def test_the_weekday_matters(self) -> None:
        """At 22:00 the week is quiet; Friday runs until eleven."""
        assert verdict(house(*HIS), 22, "off", day=MONDAY).reason is Reason.QUIET_HOURS
        assert verdict(house(*HIS), 22, "off", day=FRIDAY).allowed


class TestItDoesNotBrakeContinuing:
    @pytest.mark.parametrize("running", ["heat", "cool", "dry"])
    def test_something_already_running_stays_regulated(self, running: str) -> None:
        assert verdict(house(*HIS), 23, running).allowed

    def test_switching_it_on_yourself_is_picked_up(self) -> None:
        """The whole point: you may still decide to stay up."""
        assert verdict(house(*HIS), 2, "heat").allowed

    def test_fan_only_does_not_count_as_running(self) -> None:
        """Circulating air is not climate control, so it may not start either."""
        assert verdict(house(*HIS), 23, "fan_only").reason is Reason.QUIET_HOURS


class TestASecondAppliance:
    """Een kamer met twee apparaten telt ze allebei, niet alleen de eerste.

    Wie alleen naar het eerste apparaat kijkt, zet de rem terug op een kamer
    waar de tweede unit gewoon staat te draaien - en dan gaat die uit terwijl
    iemand hem net met de hand aanzette.

    A room with two appliances counts both, not just the first. Looking only at
    the first puts the brake back on a room whose second unit is running - and
    then that one goes off just after somebody switched it on by hand.
    """

    SECOND = "climate.bijzetkachel"

    def _house(self) -> DirectorConfig:
        return DirectorConfig(
            zones=(
                Zone(
                    "woonkamer",
                    "Woonkamer",
                    "sensor.woonkamer",
                    sources=(Source("w", LIVING), Source("b", self.SECOND)),
                    heat=ModeSettings(23.0, 22.0),
                ),
            ),
            residents=(Resident("danny", "Danny", presence_entity="person.danny"),),
            gates=GateSettings(quiet_windows=HIS),
        )

    def _verdict(self, first: str, second: str):
        config = self._house()
        zone = config.zone("woonkamer")
        assert zone is not None
        world = make_world(
            now=datetime(2026, 8, MONDAY, 23, 0),
            indoor={"woonkamer": 18.0},
            climates={LIVING: first, self.SECOND: second},
            residents={"danny": awake()},
            presence={"woonkamer": PresenceState(occupied=True)},
        )
        return gate_verdict(config, world, zone)

    def test_the_second_appliance_lifts_the_brake_too(self) -> None:
        assert self._verdict("off", "heat").allowed

    def test_with_both_of_them_off_the_brake_holds(self) -> None:
        assert self._verdict("off", "off").reason is Reason.QUIET_HOURS


class TestWithoutWindows:
    @pytest.mark.parametrize("hour", [0, 3, 12, 23])
    def test_the_brake_is_off(self, hour: int) -> None:
        assert verdict(house(), hour, "off").allowed


class TestAHolidayWindow:
    """Een vakantievenster geldt alleen op vakantiedagen, en dan elke dag.

    A holiday window applies only on holidays, and then on any weekday.
    """

    def test_it_does_not_bite_on_an_ordinary_day(self) -> None:
        window = TimeWindow(time(21, 0), time(9, 0), holiday=True)
        assert verdict(house(window), 22, "off").allowed

    def test_it_bites_on_a_holiday(self) -> None:
        window = TimeWindow(time(21, 0), time(9, 0), holiday=True)
        assert verdict(house(window), 22, "off", holiday=True).reason is Reason.QUIET_HOURS

    def test_on_a_holiday_it_ignores_its_weekdays(self) -> None:
        """Een vakantie is geen dag van de week, dus ook op zaterdag geldt hij.

        A holiday is not a day of the week, so it applies on a Saturday too.
        """
        window = TimeWindow(time(21, 0), time(9, 0), WEEK, holiday=True)
        assert verdict(house(window), 22, "off", day=22, holiday=True).reason is Reason.QUIET_HOURS

    def test_ordinary_windows_fall_back_to_saturday_on_a_holiday(self) -> None:
        """Zonder vakantievenster telt een vakantie als zaterdag.

        Without a holiday window a holiday counts as a Saturday.
        """
        window = TimeWindow(time(21, 0), time(9, 0), WEEKEND)
        assert verdict(house(window), 22, "off", day=18).allowed
        assert verdict(house(window), 22, "off", day=18, holiday=True).reason is Reason.QUIET_HOURS

    def test_a_weekday_window_stops_applying_on_a_holiday(self) -> None:
        """Een doordeweeks venster is geen zaterdagvenster.

        A weekday window is not a Saturday window.
        """
        window = TimeWindow(time(21, 0), time(9, 0), WEEK)
        assert verdict(house(window), 22, "off", day=18).reason is Reason.QUIET_HOURS
        assert verdict(house(window), 22, "off", day=18, holiday=True).allowed

    def test_a_holiday_window_replaces_the_ordinary_ones(self) -> None:
        """Op een vakantie neemt het vakantievenster het over.

        On a holiday the holiday window takes over from the ordinary ones.
        """
        config = house(
            TimeWindow(time(21, 0), time(9, 0)),
            TimeWindow(time(23, 0), time(9, 0), holiday=True),
        )
        assert verdict(config, 22, "off", holiday=True).allowed
        assert verdict(config, 23, "off", holiday=True).reason is Reason.QUIET_HOURS


class TestItSurvivesStorage:
    def test_it_round_trips(self) -> None:
        config = house(*HIS)
        assert config_from_dict(config_to_dict(config)) == config

    def test_a_holiday_window_keeps_its_flag(self) -> None:
        """De schrijver vergat deze vlag, dus een vakantievenster werd bij het
        terugschrijven stilletjes een gewoon venster - en de diagnose gaf
        daarmee een ander huis terug dan er draaide.

        The writer forgot this flag, so a holiday window quietly became an
        ordinary one on the way back - and the diagnostics then handed back a
        different house than the one running.
        """
        config = house(TimeWindow(time(21, 0), time(9, 0), holiday=True))
        assert config_to_dict(config)["gates"]["quiet_windows"][0]["holiday"] is True
        assert config_from_dict(config_to_dict(config)).gates.quiet_windows[0].holiday is True

    def test_older_options_have_no_windows(self) -> None:
        assert config_from_dict({}).gates.quiet_windows == ()

    def test_rubbish_is_ignored(self) -> None:
        stored = config_from_dict({"gates": {"quiet_windows": ["nonsense", None, 42]}})
        assert stored.gates.quiet_windows == ()


class TestAnOpenScheduleWins:
    """Het rooster beschrijft juist het vroege uur; de stilte mag dat niet knijpen.

    De stilte is bedoeld voor thuiskomen op een uur waarop je zo naar bed gaat.
    Wie om vijf uur 's ochtends begint heeft dat in zijn rooster gezet omdat het
    vroeg is - dan zou een stiltevenster van 21:00 tot 09:00 precies het ritme
    afknijpen dat het rooster beschrijft.

    The quiet is meant for coming home at an hour when you are about to turn in.
    Whoever starts at five in the morning put that in their schedule because it
    is early - a quiet window from 21:00 to 09:00 would then pinch off the very
    rhythm the schedule describes.
    """

    #: Nancy staat op dinsdag en donderdag vroeg op.
    #: Nancy is up early on Tuesdays and Thursdays.
    nancy = Resident(
        "nancy",
        "Nancy",
        windows=(TimeWindow(time(5, 0), time(8, 0), frozenset({1, 3})),),
        presence_entity="person.nancy",
    )

    def _config(self) -> DirectorConfig:
        base = house(*HIS)
        return DirectorConfig(zones=base.zones, residents=(self.nancy,), gates=base.gates)

    def _verdict(self, hour: int, *, day: int, home: bool = True):
        from conftest import away

        config = self._config()
        zone = config.zone("woonkamer")
        assert zone is not None
        world = make_world(
            now=datetime(2026, 8, day, hour, 0),
            indoor={"woonkamer": 18.0},
            climates={LIVING: "off"},
            residents={"nancy": awake() if home else away()},
            presence={"woonkamer": PresenceState(occupied=True)},
        )
        return gate_verdict(config, world, zone)

    def test_her_early_window_beats_the_quiet(self) -> None:
        """Tuesday 06:00: inside the quiet window, but her schedule is open."""
        assert self._verdict(6, day=18).allowed

    def test_outside_her_window_the_quiet_holds(self) -> None:
        """Tuesday 04:00: too early even for her."""
        assert self._verdict(4, day=18).reason is Reason.QUIET_HOURS

    def test_on_a_day_without_a_window_the_quiet_holds(self) -> None:
        """Wednesday 06:00: her window is Tuesday and Thursday only."""
        assert self._verdict(6, day=19).reason is Reason.QUIET_HOURS

    def test_the_evening_stays_quiet(self) -> None:
        """Tuesday 23:00: nobody's window is open, so coming home starts nothing."""
        assert self._verdict(23, day=18).reason is Reason.QUIET_HOURS

    def test_a_window_of_somebody_away_does_not_count(self) -> None:
        """Her schedule need not set the house going while she is out."""
        assert self._verdict(6, day=18, home=False).reason is Reason.QUIET_HOURS


class TestTheHomecomerRuleOnAHoliday:
    """Anker 13 geldt onverkort op een vakantie, met en zonder vakantievenster.

    Anchor 13 holds on a holiday too, with and without a holiday window of its
    own.
    """

    def test_a_holiday_window_brakes_only_homecomers(self) -> None:
        window = TimeWindow(time(21, 0), time(9, 0), holiday=True)
        moment = datetime(2026, 8, MONDAY, 21, 10)
        early = verdict_at(
            house(window),
            moment,
            "off",
            home_since=datetime(2026, 8, MONDAY, 18, 0),
            holiday=True,
        )
        assert early.allowed
        for home_since in (datetime(2026, 8, MONDAY, 21, 30), None):
            found = verdict_at(house(window), moment, "off", home_since=home_since, holiday=True)
            assert found.reason is Reason.QUIET_HOURS

    def test_a_falling_back_window_is_read_as_the_day_it_counts_as(self) -> None:
        """Zonder vakantievenster leest een gewoon venster als zaterdag.

        Dan hoort de begintijd ook vanaf díe dag gerekend te worden: het venster
        21:00-09:00 van vrijdag en zaterdag loopt op dinsdag 02:00 (vakantie) nog,
        en begon maandag 21:00. Wie er om 22:00 aankwam is dus een thuiskomer -
        zonder de vakantiedag mee te wegen zou dit venster helemaal niet open
        lijken en viel de stilte weg.
        """
        window = TimeWindow(time(21, 0), time(9, 0), WEEKEND)
        moment = datetime(2026, 8, 18, 2, 0)
        early = verdict_at(
            house(window),
            moment,
            "off",
            home_since=datetime(2026, 8, MONDAY, 18, 0),
            holiday=True,
        )
        assert early.allowed
        late = verdict_at(
            house(window),
            moment,
            "off",
            home_since=datetime(2026, 8, MONDAY, 22, 0),
            holiday=True,
        )
        assert late.reason is Reason.QUIET_HOURS


class TestTheEdgesOfTheHomecomerRule:
    """De randen die de regel zelf niet noemt, maar wel moet dragen.

    The edges the rule itself does not mention but has to carry.

    Drie vragen die je alleen stelt als je de regel wantrouwt: telt een moment
    zonder aanwezigheid (E1)? wat doet een moment in de toekomst (E3)? en wat
    gebeurt er met twee vensters die tegelijk openstaan (E2)? De laatste is de
    strengste lezing: **elk** open venster moet zo iemand aanwijzen.

    Three questions you only ask when you distrust the rule: does a moment without
    presence count (E1)? what does a moment in the future do (E3)? and what happens
    with two windows standing open at once (E2)? That last one is the strictest
    reading: **every** open window has to point at such a resident.
    """

    MOMENT = datetime(2026, 8, MONDAY, 21, 10)
    EARLY = datetime(2026, 8, MONDAY, 18, 0)

    def test_a_leftover_moment_of_somebody_who_is_out_does_not_count(self) -> None:
        """Een achtergebleven moment telt niet: weg is weg (E1).

        Wie weg is kan geen "al thuis" zijn, ook niet als er nog een moment van hem
        in de wereld staat. De poort kijkt naar `home` én naar het moment.
        """
        leftover = ResidentState(home=False, asleep=False, home_since=self.EARLY)
        found = verdict_at(house(*HIS), self.MOMENT, "off", residents={"danny": leftover})
        assert found.reason is Reason.QUIET_HOURS

    def test_a_moment_in_the_future_does_not_lift_the_quiet(self) -> None:
        """Een moment ná nu is geen "al thuis": geen uitzondering en geen crash (E3).

        Dat kan gebeuren als de klok is teruggezet of als een bewaarde tijd uit een
        andere tijdzone komt. De vergelijking is dan gewoon onwaar, en dan remt het
        venster - de veilige kant.
        """
        ahead = datetime(2026, 8, MONDAY, 23, 0)
        found = verdict_at(house(*HIS), self.MOMENT, "off", home_since=ahead)
        assert found.reason is Reason.QUIET_HOURS

    @pytest.mark.parametrize(
        ("home_since", "expected"),
        [
            pytest.param(datetime(2026, 8, MONDAY, 19, 30), "allowed", id="voor-beide-beginnen"),
            pytest.param(datetime(2026, 8, MONDAY, 20, 30), "quiet", id="tussen-beide-beginnen"),
        ],
    )
    def test_two_windows_open_at_once_ask_for_the_strictest_reading(
        self, home_since: datetime, expected: str
    ) -> None:
        """Twee open vensters tegelijk: elk venster moet zo iemand aanwijzen (E2).

        Wie om 20:30 thuiskwam was vóór het begin van het venster van 21:00 maar ná
        dat van 20:00, en dan remt het venster - de strengste lezing, precies zoals
        de docstring van `_quiet_windows` opschrijft. Vóór beide beginnen regelt hij
        gewoon door.
        """
        windows = (TimeWindow(time(21, 0), time(9, 0)), TimeWindow(time(20, 0), time(9, 0)))
        found = verdict_at(house(*windows), self.MOMENT, "off", home_since=home_since)
        if expected == "allowed":
            assert found.allowed
        else:
            assert found.reason is Reason.QUIET_HOURS

    def test_a_holiday_window_takes_over_with_its_own_beginning(self) -> None:
        """Een vakantievenster neemt het over, met zijn eigen begin (E2, vakantie).

        Op een vakantie met een eigen vakantievenster tellen alleen die vensters -
        dat was al zo - en dus hangt de vraag aan het begin van dát venster: wie om
        20:30 thuiskwam is een thuiskomer voor het venster van 20:00, ook al begon
        het gewone venster pas om 21:00.
        """
        windows = (
            TimeWindow(time(21, 0), time(9, 0)),
            TimeWindow(time(20, 0), time(9, 0), holiday=True),
        )
        late = verdict_at(
            house(*windows),
            self.MOMENT,
            "off",
            home_since=datetime(2026, 8, MONDAY, 20, 30),
            holiday=True,
        )
        assert late.reason is Reason.QUIET_HOURS
        early = verdict_at(
            house(*windows),
            self.MOMENT,
            "off",
            home_since=datetime(2026, 8, MONDAY, 19, 30),
            holiday=True,
        )
        assert early.allowed
