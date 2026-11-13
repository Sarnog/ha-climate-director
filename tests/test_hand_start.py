"""De handstartpoort in de engine: welke drie remmen hij opzij zet.

The hand start gate in the engine: which three brakes it sets aside.

Een handstart is geen hand: hij zet een zone aan, niet uit. Daarom passeert hij
uitsluitend `WAITING_FOR_SLEEPER`, `EARLY_RISER` en `QUIET_HOURS`. De
hoofdschakelaar, een open raam, een leeg huis en de slaappoort blijven gelden.
Dezelfde module beantwoordt wanneer de handstart niets meer doet en dus mag
vervallen.

A hand start is not a hand: it switches a zone on, not off. It therefore passes
only `WAITING_FOR_SLEEPER`, `EARLY_RISER` and `QUIET_HOURS`. The master switch,
an open window, an empty house and the sleep gate keep applying. The same module
answers when the hand start no longer does anything and may lapse.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import time

import pytest
from conftest import (
    BACK_DOOR,
    asleep,
    at,
    awake,
    everyone_up,
    house,
    make_world,
)
from conftest import (
    LIVING as LIVING_SOURCE,
)

from custom_components.climate_director.engine import (
    DirectorConfig,
    GateSettings,
    OpeningState,
    Reason,
    RiseBrake,
    TimeWindow,
    WakeDeadline,
    Zone,
    gates,
    hand_start,
)
from custom_components.climate_director.engine.world import WorldState

LIVING = "woonkamer"


def living(config: DirectorConfig) -> Zone:
    """Return the living room, whose zone id every test here uses."""
    zone = config.zone(LIVING)
    assert zone is not None
    return zone


def with_hand_start(world: WorldState, *zone_ids: str) -> WorldState:
    """Return the same world with hand starts for the named zones."""
    return replace(world, zone_hand_starts=frozenset(zone_ids))


def no_reading(world: WorldState, kind: str, subject: str = "") -> WorldState:
    """Return the same world with one brake input marked unreadable."""
    from custom_components.climate_director.engine.world import (
        ReadableInput,
        UnreadableInput,
    )

    missing = UnreadableInput(ReadableInput(kind), subject)
    return replace(world, unreadable=world.unreadable | {missing})


def weekend_house() -> DirectorConfig:
    """Return the house with a weekend wake deadline for both residents."""
    base = house()
    eleven = WakeDeadline(at=time(11, 0), weekdays=frozenset({5, 6}))
    return replace(
        base,
        residents=tuple(replace(resident, wake_deadline=eleven) for resident in base.residents),
    )


def after_a_slept_night(world: WorldState) -> WorldState:
    """Return the world as a morning after a night the house slept."""
    return replace(world, asleep_since=world.now.replace(hour=1, minute=0))


class TestWaitingForSleeper:
    def test_it_passes_the_wait_for_the_last_sleeper(self) -> None:
        """Een handstart laat de zone door terwijl de ander nog in bed ligt."""
        config = weekend_house()
        world = after_a_slept_night(
            make_world(now=at(10, 0, day=15), residents={"danny": awake(), "nancy": asleep()})
        )
        waiting = gate(config, world)
        assert waiting == (Reason.WAITING_FOR_SLEEPER,)

        assert gate(config, with_hand_start(world, LIVING)) == ()

    def test_it_does_not_pass_everyone_asleep(self) -> None:
        """De slaappoort is geen ochtendwacht en blijft dicht."""
        config = weekend_house()
        world = with_hand_start(
            make_world(
                now=at(23, 0, day=14),
                residents={"danny": asleep(), "nancy": asleep()},
            ),
            LIVING,
        )
        assert gate(config, world) == (Reason.EVERYONE_ASLEEP,)


class TestEarlyRiser:
    def test_it_passes_the_rise_brake(self) -> None:
        """Een handstart laat de zone door vóór de opsta-rem voorbij is."""
        base = house()
        brake = RiseBrake(at=time(9, 0), weekdays=frozenset({0}))
        config = replace(
            base,
            residents=tuple(replace(resident, rise_brake=brake) for resident in base.residents),
        )
        world = make_world(now=at(8, 0), residents=everyone_up())
        assert gate(config, world) == (Reason.EARLY_RISER,)
        assert gate(config, with_hand_start(world, LIVING)) == ()

    def test_it_does_not_pass_the_master_switch(self) -> None:
        """De hoofdschakelaar gaat vóór elke handstart."""
        config = house()
        world = with_hand_start(make_world(residents=everyone_up(), master_enabled=False), LIVING)
        assert gate(config, world) == (Reason.MASTER_DISABLED,)


class TestQuietHours:
    def quiet_house(self) -> DirectorConfig:
        """Return the house with a quiet window around the test moment."""
        return replace(
            house(),
            gates=GateSettings(
                require_awake=True,
                quiet_windows=(TimeWindow(time(11, 0), time(13, 0)),),
            ),
        )

    def test_it_passes_the_quiet_window(self) -> None:
        """Een handstart laat de zone in het stiltevenster beginnen."""
        config = self.quiet_house()
        world = make_world(now=at(12, 0), residents=everyone_up())
        assert gate(config, world) == (Reason.QUIET_HOURS,)
        assert gate(config, with_hand_start(world, LIVING)) == ()

    def test_a_running_zone_still_waits_for_the_end_of_the_window(self) -> None:
        """Een draaiende zone passeert het venster, maar de handstart blijft tot het einde.

        Na de eerste stop moet de zone in hetzelfde venster weer kunnen
        starten; daarom telt een draaiend eigen apparaat hier als uit.

        A running zone passes the window, but the hand start stays until the end.
        After the first stop the zone must be able to start again inside the same
        window; that is why a running appliance of its own counts as off here.
        """
        config = self.quiet_house()
        world = with_hand_start(
            make_world(now=at(12, 0), residents=everyone_up(), climates={LIVING_SOURCE: "heat"}),
            LIVING,
        )
        assert gate(config, world) == ()
        assert gates.brakes_remaining(config, world, living(config), None) == frozenset(
            {Reason.QUIET_HOURS}
        )

    def test_it_does_not_pass_an_open_window(self) -> None:
        """Een open raam blijft de zone tegenhouden."""
        config = self.quiet_house()
        world = with_hand_start(
            make_world(
                now=at(12, 1),
                residents=everyone_up(),
                openings={BACK_DOOR: OpeningState(open=True, changed_at=at(12, 0))},
            ),
            LIVING,
        )
        assert gate(config, world) == (Reason.OPENING_OPEN,)


class TestWhenTheHandStartStopsDoingSomething:
    def test_brakes_remain_while_the_sleeper_waits(self) -> None:
        """Zolang de slaper wacht, blijft de handstart nodig."""
        config = weekend_house()
        world = with_hand_start(
            after_a_slept_night(
                make_world(
                    now=at(10, 0, day=15),
                    residents={"danny": awake(), "nancy": asleep()},
                )
            ),
            LIVING,
        )
        assert gates.brakes_remaining(config, world, living(config), None) == frozenset(
            {Reason.WAITING_FOR_SLEEPER}
        )

    def test_no_brake_remains_after_the_deadline(self) -> None:
        """Na de uiterste tijd doet de handstart niets meer."""
        config = weekend_house()
        world = with_hand_start(
            after_a_slept_night(
                make_world(
                    now=at(11, 0, day=15),
                    residents={"danny": awake(), "nancy": asleep()},
                )
            ),
            LIVING,
        )
        assert gates.brakes_remaining(config, world, living(config), None) == frozenset()

    def test_it_passes_only_the_three_waiting_reasons(self) -> None:
        """Geen enkele andere reden gaat door de handstartpoort."""
        world = with_hand_start(make_world(), LIVING)
        for reason in Reason:
            assert hand_start.passes(world, LIVING, reason) is (
                reason in hand_start.HAND_START_BRAKES
            )

    def test_a_hand_start_on_another_zone_does_not_help(self) -> None:
        """De handstart hangt aan de zone, niet aan het huis."""
        config = weekend_house()
        world = with_hand_start(
            after_a_slept_night(
                make_world(
                    now=at(10, 0, day=15),
                    residents={"danny": awake(), "nancy": asleep()},
                )
            ),
            "zolder",
        )
        assert gate(config, world) == (Reason.WAITING_FOR_SLEEPER,)

    def test_a_zone_without_a_waiting_reason_keeps_its_hand_start_harmless(self) -> None:
        """Een handstart zonder wachtreden doet niets en vervalt meteen."""
        config = house()
        world = with_hand_start(make_world(residents=everyone_up()), LIVING)
        assert gate(config, world) == ()
        assert gates.brakes_remaining(config, world, living(config), None) == frozenset()


class TestUnreadableInputs:
    def test_a_reading_on_every_sensor_allows_the_recheck(self) -> None:
        """Met een lezing op elke sensor mogen de remmen gewoon hertoetst worden."""
        config = weekend_house()
        world = with_hand_start(
            after_a_slept_night(
                make_world(
                    now=at(10, 0, day=15),
                    residents={"danny": awake(), "nancy": asleep()},
                )
            ),
            LIVING,
        )
        assert hand_start.brakes_readable(config, world) is True
        assert gates.brakes_remaining(config, world, living(config), None) == frozenset(
            {Reason.WAITING_FOR_SLEEPER}
        )

    def test_an_unreadable_sleep_sensor_blocks_the_recheck(self) -> None:
        """Een onleesbare slaapsensor laat de rem verdwijnen maar blokkeert het verval."""
        config = weekend_house()
        world = with_hand_start(
            no_reading(
                after_a_slept_night(
                    make_world(
                        now=at(10, 0, day=15),
                        residents={
                            "danny": awake(),
                            "nancy": replace(asleep(), asleep=False),
                        },
                    )
                ),
                "sleep",
                "nancy",
            ),
            LIVING,
        )
        assert gate(config, world) == ()
        assert gates.brakes_remaining(config, world, living(config), None) == frozenset()
        assert hand_start.brakes_readable(config, world) is False

    def test_an_unreadable_presence_entity_blocks_the_recheck(self) -> None:
        """Een onleesbare aanwezigheid laat de rem verdwijnen maar blokkeert het verval."""
        config = weekend_house()
        world = with_hand_start(
            no_reading(
                after_a_slept_night(
                    make_world(
                        now=at(10, 0, day=15),
                        residents={
                            "danny": awake(),
                            "nancy": replace(asleep(), home=False),
                        },
                    )
                ),
                "presence",
                "nancy",
            ),
            LIVING,
        )
        assert gate(config, world) == ()
        assert gates.brakes_remaining(config, world, living(config), None) == frozenset()
        assert hand_start.brakes_readable(config, world) is False

    def test_a_sensor_the_installation_does_not_use_does_not_block(self) -> None:
        """Een sensor die deze installatie niet gebruikt is geen ontbrekende lezing."""
        base = weekend_house()
        config = replace(
            base,
            residents=tuple(replace(resident, sleep_entity="") for resident in base.residents),
        )
        world = no_reading(
            after_a_slept_night(
                make_world(
                    now=at(10, 0, day=15),
                    residents={
                        "danny": awake(),
                        "nancy": replace(asleep(), asleep=False),
                    },
                )
            ),
            "sleep",
            "nancy",
        )
        assert hand_start.brakes_readable(config, world) is True

    def test_a_presence_sensor_the_installation_does_not_use_does_not_block(self) -> None:
        """Een aanwezigheidssensor die niet meedoet is geen ontbrekende lezing."""
        base = weekend_house()
        config = replace(
            base,
            residents=tuple(replace(resident, presence_entity="") for resident in base.residents),
        )
        world = no_reading(
            after_a_slept_night(
                make_world(
                    now=at(10, 0, day=15),
                    residents={
                        "danny": awake(),
                        "nancy": replace(asleep(), home=False),
                    },
                )
            ),
            "presence",
            "nancy",
        )
        assert hand_start.brakes_readable(config, world) is True

    @pytest.mark.parametrize("who", ["danny", "nancy"])
    @pytest.mark.parametrize("kind", ["presence", "sleep"])
    def test_every_resident_and_every_sensor_blocks_the_recheck(self, who: str, kind: str) -> None:
        """Elke bewoner en elke sensor telt mee, niet alleen de tweede bewoner.

        Every resident and every sensor counts, not only the second resident.
        """
        config = weekend_house()
        residents = {"danny": awake(), "nancy": asleep()}
        world = after_a_slept_night(make_world(now=at(10, 0, day=15), residents=residents))
        assert hand_start.brakes_readable(config, no_reading(world, kind, who)) is False

    @pytest.mark.parametrize("unused", ["sleep_entity", "presence_entity"])
    def test_a_missing_resident_blocks_with_either_sensor_alone(self, unused: str) -> None:
        """Een bewoner die mist telt als onleesbaar, ook als maar één sensor meedoet.

        A resident who is missing counts as unreadable, even when only one sensor
        takes part.
        """
        base = weekend_house()
        config = replace(
            base,
            residents=tuple(replace(resident, **{unused: ""}) for resident in base.residents),
        )
        world = after_a_slept_night(make_world(now=at(10, 0, day=15), residents={"danny": awake()}))
        assert hand_start.brakes_readable(config, world) is False

    def test_a_missing_resident_with_a_sensor_blocks_the_recheck(self) -> None:
        """Een bewoner die helemaal uit de wereld mist telt als onleesbaar."""
        config = weekend_house()
        world = after_a_slept_night(make_world(now=at(10, 0, day=15), residents={"danny": awake()}))
        assert hand_start.brakes_readable(config, world) is False


class TestTheReadabilityModel:
    """Alle invoeren van de drie remmen staan in één model.

    Every input of the three brakes sits in one model.
    """

    @staticmethod
    def with_reading(kind: str, subject: str = "") -> WorldState:
        """Return a slept-night world whose named input gave no reading."""
        from custom_components.climate_director.engine.world import (
            ReadableInput,
            UnreadableInput,
        )

        world = after_a_slept_night(
            make_world(
                now=at(10, 0, day=15),
                residents={"danny": awake(), "nancy": asleep()},
            )
        )
        return replace(
            world,
            unreadable=frozenset({UnreadableInput(ReadableInput(kind), subject)}),
        )

    @pytest.mark.parametrize(
        ("kind", "subject"),
        [
            ("presence", "danny"),
            ("presence", "nancy"),
            ("sleep", "danny"),
            ("sleep", "nancy"),
            ("holiday", ""),
        ],
    )
    def test_every_input_of_the_brakes_counts(self, kind: str, subject: str) -> None:
        """Aanwezigheid, slaap en de feestdagenagenda tellen alle drie mee."""
        base = weekend_house()
        config = replace(
            base,
            holiday_calendars=("calendar.feestdagen",),
            holiday_keyword="vakantie",
        )
        world = self.with_reading(kind, subject)
        assert hand_start.brakes_readable(config, world) is False

    def test_a_keyword_without_a_calendar_does_not_count(self) -> None:
        """Een trefwoord zonder agenda voedt de remmen niet."""
        config = replace(weekend_house(), holiday_calendars=(), holiday_keyword="vakantie")
        world = self.with_reading("holiday")
        assert hand_start.brakes_readable(config, world) is True

    def test_a_calendar_without_a_keyword_does_not_count(self) -> None:
        """Zonder trefwoord voedt de agenda de remmen niet."""
        config = replace(
            weekend_house(),
            holiday_calendars=("calendar.feestdagen",),
            holiday_keyword="",
        )
        world = self.with_reading("holiday")
        assert hand_start.brakes_readable(config, world) is True

    #: Velden die de drie wachtrema's lezen via een entiteit die kan wegvallen, met de
    #: soorten invoer (`ReadableInput`) die ze dragen. Een nieuw veld dat een rem
    #: voedt hoort hier, met zijn soort.
    #:
    #: Fields the three waiting brakes read through an entity that can drop out, with
    #: the kinds of input (`ReadableInput`) they carry. A new field feeding a brake
    #: belongs here, with its kind.
    BRAKE_INPUT_FIELDS = {
        "residents": {"presence", "sleep"},
        "holiday_mode": {"holiday"},
    }

    #: Overige velden uit een entiteit, een schakelaar of een dienst die de remmen niet
    #: via een onleesbare entiteit voeden.
    #:
    #: Other fields from an entity, a switch or a service that do not feed the brakes
    #: through an unreadable entity.
    EXTERNAL_WORLD_FIELDS = {
        "outdoor_temperature",
        "season",
        "indoor_temperatures",
        "climates",
        "unreadable",
        "openings",
        "presence",
        "circuit_family_since",
        "master_enabled",
        "precondition_bypass",
        "precondition_until",
        "guest_mode",
        "precipitation",
        "zone_overrides",
        "zone_hand_starts",
        "zone_hands",
        "zone_priorities",
        "opening_bypasses",
        "heat_pick",
        "heat_picks",
    }

    #: Velden die de engine zelf uit de klok of uit de andere velden afleidt.
    #:
    #: Fields the engine derives from the clock or from the other fields.
    INTERNAL_WORLD_FIELDS = {"now", "asleep_since"}

    def test_every_world_field_is_classified(self) -> None:
        """Een nieuw veld in de wereld staat in precies één van de drie klassen."""
        from dataclasses import fields

        classes = [
            set(self.BRAKE_INPUT_FIELDS),
            self.EXTERNAL_WORLD_FIELDS,
            self.INTERNAL_WORLD_FIELDS,
        ]
        found = {field.name for field in fields(WorldState)}
        assert found == classes[0] | classes[1] | classes[2]
        assert sum(len(item) for item in classes) == len(found)

    def test_every_readable_input_belongs_to_a_field(self) -> None:
        """Elke soort onleesbare invoer hoort bij een veld dat de remmen voedt."""
        from custom_components.climate_director.engine.world import ReadableInput

        carried = [kind for kinds in self.BRAKE_INPUT_FIELDS.values() for kind in kinds]
        assert sorted(carried) == sorted(str(kind) for kind in ReadableInput)


def gate(config: DirectorConfig, world: WorldState) -> tuple[Reason, ...]:
    """Return every gate still shut for the living room."""
    return gates.closed(config, world, living(config))
