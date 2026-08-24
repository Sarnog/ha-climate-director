"""Apparaten die stilvallen zodra ergens in huis een opening openstaat.

Appliances that stop the moment an opening anywhere in the house stands open.

Een opening werkt op zones. Bij een gedeelde ketel klopt dat niet: die staat als
bron onder alle zones, en zolang een andere zone warmte vraagt blijft hij
branden met de deur open, want vraag wint van stilte. Deze tests pinnen beide
kanten vast - het oude gedrag met een lege lijst, en het nieuwe zodra het
apparaat erin staat.

An opening acts on zones. For a shared boiler that is wrong: it sits as a source
under every zone, and as long as another zone asks for heat it keeps running
with the door open, because demand beats silence. These tests pin both sides
down - the old behaviour with an empty list, and the new one the moment the
appliance is listed.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from conftest import at, climate, everyone_up, make_world

from custom_components.climate_director.engine import (
    Circuit,
    DirectorConfig,
    Generator,
    ModeFamily,
    ModeSettings,
    Opening,
    OpeningState,
    OutdoorWindow,
    Reason,
    Source,
    SourceRole,
    Zone,
    decide,
    gates,
    serialise,
    validate,
)

GAS = "climate.cv_ketel"
LIVING_AIRCO = "climate.woonkamer_airco"
BACK_DOOR = "binary_sensor.achterdeur"
SKYLIGHT = "binary_sensor.dakraam"

#: Ruim voorbij de vertraging van elke opening hieronder.
#: Comfortably past the delay of every opening below.
OPENED_AT = at(11, 0)


def warmth() -> ModeSettings:
    """Return heating settings that want heat at 18 degrees indoors."""
    return ModeSettings(target=21.0, start_at=20.0, hysteresis=1.0)


def shared_boiler(**overrides: object) -> DirectorConfig:
    """Return two rooms on one boiler, with a skylight on the attic only.

    De opening raakt alleen de zolder. De woonkamer vraagt gewoon warmte, en dat
    is precies het geval waarin de ketel met het dakraam open bleef branden.

    The opening affects the attic only. The living room simply asks for heat,
    which is exactly the case in which the boiler kept burning with the skylight
    open.
    """
    living = Zone(
        zone_id="woonkamer",
        name="Woonkamer",
        indoor_sensor="sensor.woonkamer",
        priority=0,
        sources=(Source(source_id="ketel_woonkamer", entity_id=GAS, role=SourceRole.HEAT_ONLY),),
        heat=warmth(),
    )
    attic = Zone(
        zone_id="zolder",
        name="Zolder",
        indoor_sensor="sensor.zolder",
        priority=1,
        sources=(Source(source_id="ketel_zolder", entity_id=GAS, role=SourceRole.HEAT_ONLY),),
        heat=warmth(),
    )
    return DirectorConfig(
        zones=(living, attic),
        openings=(Opening(entity_id=SKYLIGHT, zone_ids=("zolder",), delay=timedelta(minutes=5)),),
        **overrides,  # type: ignore[arg-type]
    )


def cold_house(**overrides: object) -> object:
    """Return a world in which both rooms are cold and the skylight is open."""
    settings: dict[str, object] = {
        "now": at(12, 0),
        "outdoor": 5.0,
        "indoor": {"woonkamer": 18.0, "zolder": 18.0},
        "climates": {GAS: climate("heat"), LIVING_AIRCO: climate("off")},
        "residents": everyone_up(),
        "openings": {SKYLIGHT: OpeningState(open=True, changed_at=OPENED_AT)},
    }
    settings.update(overrides)
    return make_world(**settings)  # type: ignore[arg-type]


def command_for(plan, entity_id: str):
    """Return the command issued to `entity_id`, or None if there is none."""
    return next((item for item in plan.commands if item.entity_id == entity_id), None)


def decision_for(plan, zone_id: str):
    """Return the decision for `zone_id`."""
    decision = plan.decision_for(zone_id)
    assert decision is not None
    return decision


# ---------------------------------------------------------------------------
# Het gedrag dat dit oplost / the behaviour this settles
# ---------------------------------------------------------------------------


def test_a_shared_boiler_keeps_burning_without_the_setting() -> None:
    """Dit is het gedrag van vóór deze instelling, en het blijft zo."""
    plan = decide(shared_boiler(), cold_house())

    boiler = command_for(plan, GAS)
    assert boiler is not None
    assert boiler.hvac_mode == "heat"
    assert boiler.zone_id == "woonkamer"


def test_a_listed_boiler_stops_while_any_opening_stands_open() -> None:
    plan = decide(shared_boiler(house_wide_openings=(GAS,)), cold_house())

    boiler = command_for(plan, GAS)
    assert boiler is not None
    assert boiler.hvac_mode == "off"
    assert boiler.reason is Reason.OPENING_OPEN_ELSEWHERE


def test_the_room_says_why_instead_of_blaming_the_configuration() -> None:
    """`no_source_available` zou de gebruiker de configuratie in sturen."""
    plan = decide(shared_boiler(house_wide_openings=(GAS,)), cold_house())

    living = decision_for(plan, "woonkamer")
    assert living.reason is Reason.OPENING_OPEN_ELSEWHERE
    assert Reason.OPENING_OPEN_ELSEWHERE in living.closed_gates
    # De "geblokkeerd"-melder van die kamer hoort te branden: hij wilde warmte
    # en staat stil door een deur elders.
    assert living.held_back


def test_a_room_with_no_source_at_all_still_says_no_source_available() -> None:
    """De nieuwe reden mag de oude niet overnemen zodra hij eenmaal bestaat."""
    config = shared_boiler(house_wide_openings=(GAS,))
    world = cold_house(climates={GAS: climate("heat", available=False)})

    living = decision_for(decide(config, world), "woonkamer")
    assert living.reason is Reason.NO_SOURCE_AVAILABLE


def boiler_with_a_reserve() -> DirectorConfig:
    """Return the shared-boiler house with an airco reserve in the living room."""
    config = shared_boiler(house_wide_openings=(GAS,))
    living = config.zones[0]
    with_reserve = replace(
        living,
        sources=(
            Source(
                source_id="ketel_woonkamer",
                entity_id=GAS,
                role=SourceRole.HEAT_ONLY,
                priority=0,
            ),
            Source(
                source_id="woonkamer_airco",
                entity_id=LIVING_AIRCO,
                role=SourceRole.HEAT_COOL,
                priority=1,
            ),
        ),
    )
    return replace(config, zones=(with_reserve, config.zones[1]))


def test_a_blocked_first_choice_stops_the_zone_instead_of_using_the_reserve() -> None:
    """De instelling heet "apparaat valt stil", niet "kamer wijkt uit".

    The setting reads "appliance stops", not "room moves to another appliance".
    """
    plan = decide(boiler_with_a_reserve(), cold_house())

    boiler = command_for(plan, GAS)
    airco = command_for(plan, LIVING_AIRCO)
    assert boiler is not None and boiler.hvac_mode == "off"
    assert airco is not None
    assert airco.hvac_mode == "off"

    living = decision_for(plan, "woonkamer")
    assert living.reason is Reason.OPENING_OPEN_ELSEWHERE
    assert living.granted is ModeFamily.NEUTRAL
    assert living.source_id is None


def test_an_unreachable_first_choice_still_falls_back_visibly() -> None:
    """Alleen een écht onbereikbare eerste keus telt als uitwijking.

    Only a genuinely unreachable first choice counts as a fallback.
    """
    config = boiler_with_a_reserve()
    world = cold_house(
        climates={GAS: climate("off", available=False), LIVING_AIRCO: climate("off")}
    )

    plan = decide(config, world)

    airco = command_for(plan, LIVING_AIRCO)
    assert airco is not None and airco.hvac_mode == "heat"
    living = decision_for(plan, "woonkamer")
    assert living.on_fallback
    assert living.source_id == "woonkamer_airco"


def boiler_with_a_broken_reserve() -> DirectorConfig:
    """Return the blocked-first-choice house with a broken middle choice.

    De eerste keus is de huisbreed stilgezette ketel, de tweede een onbereikbare
    airco en de derde een gezonde reserve. Met een bypass-verzoek kiest het plan
    de ketel; de uitwijkmelder hoort dan niets te melden, want er is niets
    overgeslagen.

    The first choice is the house-wide stopped boiler, the second an unreachable
    air conditioner and the third a sound reserve. With a bypassing request the
    plan picks the boiler; the fallback reporter should then stay silent, since
    nothing was skipped.
    """
    config = boiler_with_a_reserve()
    living = config.zones[0]
    with_third = replace(
        living,
        sources=(
            Source(
                source_id="ketel_woonkamer",
                entity_id=GAS,
                role=SourceRole.HEAT_ONLY,
                priority=0,
            ),
            Source(
                source_id="kapotte_airco",
                entity_id=LIVING_AIRCO,
                role=SourceRole.HEAT_COOL,
                priority=1,
            ),
            Source(
                source_id="reserve",
                entity_id="climate.reserve",
                role=SourceRole.HEAT_ONLY,
                priority=2,
            ),
        ),
    )
    return replace(config, zones=(with_third, config.zones[1]))


def test_a_bypassed_request_reports_no_false_fallback() -> None:
    """R5: de uitwijkmelder rekent met dezelfde stop als het plan.

    R5: the fallback reporter reckons with the same stop as the plan.
    """
    config = boiler_with_a_broken_reserve()
    world = cold_house(
        climates={
            GAS: climate("heat"),
            LIVING_AIRCO: climate("off", available=False),
            "climate.reserve": climate("off"),
        },
        precondition_until={"woonkamer": at(14, 0)},
        precondition_bypass=frozenset({"woonkamer"}),
    )

    plan = decide(config, world)
    living = decision_for(plan, "woonkamer")
    assert living.source_id == "ketel_woonkamer"
    assert living.passed_over == ()


# ---------------------------------------------------------------------------
# De grenzen van de stop / the bounds of the stop
# ---------------------------------------------------------------------------


def test_an_empty_list_changes_nothing_at_all() -> None:
    """Een installatie die deze instelling niet gebruikt merkt er niets van."""
    world = cold_house()
    assert decide(shared_boiler(), world) == decide(shared_boiler(house_wide_openings=()), world)


def test_a_closed_house_leaves_the_listed_appliance_alone() -> None:
    plan = decide(shared_boiler(house_wide_openings=(GAS,)), cold_house(openings={}))

    boiler = command_for(plan, GAS)
    assert boiler is not None
    assert boiler.hvac_mode == "heat"


@pytest.mark.parametrize(
    ("minutes", "stopped"),
    [(1, False), (4, False), (5, True), (30, True)],
)
def test_the_openings_own_delay_applies(minutes: int, stopped: bool) -> None:
    """Vijf minuten vertraging op het dakraam geldt ook voor de huisbrede stop."""
    world = cold_house(
        openings={
            SKYLIGHT: OpeningState(open=True, changed_at=at(12, 0) - timedelta(minutes=minutes))
        }
    )

    boiler = command_for(decide(shared_boiler(house_wide_openings=(GAS,)), world), GAS)
    assert boiler is not None
    assert (boiler.hvac_mode == "off") is stopped


def test_an_opening_without_a_timestamp_counts_as_open_long_enough() -> None:
    """Gelijk aan de gewone raampoort: onbekende ouderdom telt als open."""
    world = cold_house(openings={SKYLIGHT: OpeningState(open=True, changed_at=None)})

    boiler = command_for(decide(shared_boiler(house_wide_openings=(GAS,)), world), GAS)
    assert boiler is not None
    assert boiler.hvac_mode == "off"


def test_every_opening_counts_whichever_zone_it_names() -> None:
    """Een achterdeur die aan geen enkele zone hangt telt net zo goed mee."""
    config = shared_boiler(house_wide_openings=(GAS,))
    config = replace(
        config,
        openings=(Opening(entity_id=BACK_DOOR, zone_ids=("woonkamer",), delay=timedelta(0)),),
    )
    world = cold_house(openings={BACK_DOOR: OpeningState(open=True, changed_at=OPENED_AT)})

    boiler = command_for(decide(config, world), GAS)
    assert boiler is not None
    assert boiler.hvac_mode == "off"


def test_an_appliance_not_on_the_list_is_untouched_by_it() -> None:
    config = shared_boiler(house_wide_openings=("climate.iets_anders",))

    boiler = command_for(decide(config, cold_house()), GAS)
    assert boiler is not None
    assert boiler.hvac_mode == "heat"


# ---------------------------------------------------------------------------
# Wat de director met rust laat, blijft met rust
# What the director leaves alone stays left alone
# ---------------------------------------------------------------------------


def test_an_override_still_wins_over_the_house_wide_stop() -> None:
    """De override is een hoofdsleutel; deze instelling gaat er niet overheen."""
    config = shared_boiler(house_wide_openings=(GAS,))
    world = cold_house(zone_overrides={"woonkamer": True, "zolder": True})

    plan = decide(config, world)
    assert command_for(plan, GAS) is None
    assert [item.reason for item in plan.untouched] == [Reason.MANUAL_OVERRIDE]


def test_a_hand_operated_source_is_left_alone_as_ever() -> None:
    """Precies zoals een openstaand raam een handbediende airco niet uitzet."""
    config = shared_boiler(house_wide_openings=(GAS,))
    manual = tuple(
        replace(zone, sources=tuple(replace(item, autostart=False) for item in zone.sources))
        for zone in config.zones
    )
    config = replace(config, zones=manual)

    plan = decide(config, cold_house())
    assert command_for(plan, GAS) is None
    assert [item.reason for item in plan.untouched] == [Reason.MANUAL_SOURCE]


def test_a_precondition_told_to_ignore_openings_passes_through() -> None:
    """Dezelfde uitzondering als op de gewone raampoort, op één plek geregeld."""
    config = shared_boiler(house_wide_openings=(GAS,))
    world = cold_house(
        precondition_until={"woonkamer": at(14, 0)},
        precondition_bypass=frozenset({"woonkamer"}),
    )

    boiler = command_for(decide(config, world), GAS)
    assert boiler is not None
    assert boiler.hvac_mode == "heat"


def test_a_precondition_without_that_bypass_does_not_pass_through() -> None:
    config = shared_boiler(house_wide_openings=(GAS,))
    world = cold_house(precondition_until={"woonkamer": at(14, 0)})

    boiler = command_for(decide(config, world), GAS)
    assert boiler is not None
    assert boiler.hvac_mode == "off"


# ---------------------------------------------------------------------------
# De gedeelde warmtebron / the shared heat source
# ---------------------------------------------------------------------------


def generator_house(**overrides: object) -> DirectorConfig:
    """Return two rooms with valves of their own and one boiler behind them."""
    config = shared_boiler(**overrides)
    valves = tuple(
        replace(
            zone,
            sources=(
                Source(
                    source_id=f"{zone.zone_id}_kraan",
                    entity_id=f"climate.{zone.zone_id}_kraan",
                    role=SourceRole.HEAT_ONLY,
                ),
            ),
        )
        for zone in config.zones
    )
    return replace(
        config,
        zones=valves,
        generators=(Generator(generator_id="cv", name="CV-ketel", entity_id=GAS),),
    )


def valve_world(**overrides: object) -> object:
    """Return the generator house cold, with both valves and the boiler off."""
    settings: dict[str, object] = {
        "climates": {
            GAS: climate("heat"),
            "climate.woonkamer_kraan": climate("off"),
            "climate.zolder_kraan": climate("off"),
        }
    }
    settings.update(overrides)
    return cold_house(**settings)


def test_a_generator_on_the_list_stops_too() -> None:
    """De generator loopt geen bronkeuze door; het vangnet moet hem pakken."""
    plan = decide(generator_house(house_wide_openings=(GAS,)), valve_world())

    boiler = command_for(plan, GAS)
    assert boiler is not None
    assert boiler.hvac_mode == "off"
    assert boiler.reason is Reason.OPENING_OPEN_ELSEWHERE


def test_a_generator_not_on_the_list_keeps_following_demand() -> None:
    boiler = command_for(decide(generator_house(), valve_world()), GAS)
    assert boiler is not None
    assert boiler.hvac_mode == "heat"


def test_a_generator_follows_a_precondition_that_ignores_openings() -> None:
    world = valve_world(
        precondition_until={"woonkamer": at(14, 0)},
        precondition_bypass=frozenset({"woonkamer"}),
    )

    boiler = command_for(decide(generator_house(house_wide_openings=(GAS,)), world), GAS)
    assert boiler is not None
    assert boiler.hvac_mode == "heat"


def wet_house(**overrides: object) -> DirectorConfig:
    """Return two valve rooms behind one boiler; the door touches both rooms.

    De deur heeft geen `zone_ids`, dus hij raakt beide kamers. De generator
    bedient beide kamers en hangt aan geen circuit: precies het apparaat dat
    zonder R1 nooit openingsrust kreeg. De kleppen hangen wél aan een circuit
    (zonder minimale looptijd), zodat hun eigen openingsrust het beeld niet
    maskeert: zodra de deur dicht is vragen zij meteen weer warmte.

    The door has no `zone_ids`, so it affects both rooms. The generator serves
    both rooms and hangs on no circuit: exactly the appliance that never got an
    opening rest before R1. The valves do sit on a circuit (with no minimum run
    time), so their own opening rest does not mask the picture: the moment the
    door closes they ask for heat again at once.
    """
    heat = ModeSettings(target=21.0, start_at=20.0, hysteresis=1.0)
    return DirectorConfig(
        zones=(
            Zone(
                zone_id="woonkamer",
                name="Woonkamer",
                indoor_sensor="sensor.woonkamer",
                priority=0,
                sources=(
                    Source(
                        source_id="woonkamer_kraan",
                        entity_id="climate.woonkamer_kraan",
                        role=SourceRole.HEAT_ONLY,
                    ),
                ),
                heat=heat,
            ),
            Zone(
                zone_id="slaapkamer",
                name="Slaapkamer",
                indoor_sensor="sensor.slaapkamer",
                priority=1,
                sources=(
                    Source(
                        source_id="slaapkamer_kraan",
                        entity_id="climate.slaapkamer_kraan",
                        role=SourceRole.HEAT_ONLY,
                    ),
                ),
                heat=heat,
            ),
        ),
        circuits=(
            Circuit(
                circuit_id="kleppen",
                name="Kleppen",
                units=("climate.woonkamer_kraan", "climate.slaapkamer_kraan"),
                min_cycle_time=timedelta(0),
            ),
        ),
        generators=(Generator(generator_id="cv", name="CV-ketel", entity_id=GAS),),
        openings=(Opening(entity_id=BACK_DOOR),),
        **overrides,  # type: ignore[arg-type]
    )


def wet_world(*, minute: int, door_open: bool, indoor: dict[str, float], boiler: str) -> object:
    """Return the valve house at 12:`minute` with both valves off and the door as given."""
    return make_world(
        now=at(12, minute),
        outdoor=2.0,
        indoor=indoor,
        climates={
            GAS: climate(boiler, changed_at=at(12, max(0, minute - 1))),
            "climate.woonkamer_kraan": climate("off"),
            "climate.slaapkamer_kraan": climate("off"),
        },
        openings={BACK_DOOR: OpeningState(open=door_open, changed_at=at(12, minute))},
    )


COLD = {"woonkamer": 18.0, "slaapkamer": 18.0}


class TestTheGeneratorTakesPartInTheOpeningRest:
    """R1: ook een gedeelde warmtebron rust na een openingsstop.

    R1: a shared heat source rests after an opening stop too.
    """

    @pytest.mark.parametrize(
        ("stop_door_open", "opening_zone_ids", "stop_indoor", "rests"),
        [
            (True, (), {"woonkamer": 18.0, "slaapkamer": 18.0}, True),
            (True, ("woonkamer",), {"woonkamer": 18.0, "slaapkamer": 23.0}, False),
            (False, ("woonkamer",), {"woonkamer": 23.0, "slaapkamer": 23.0}, False),
        ],
        ids=["elke_zone_geweigerd", "een_zone_tevreden", "alle_zones_tevreden"],
    )
    def test_only_a_stop_by_opening_rests_the_generator(
        self,
        stop_door_open: bool,
        opening_zone_ids: tuple[str, ...],
        stop_indoor: dict[str, float],
        rests: bool,
    ) -> None:
        config = wet_house()
        if opening_zone_ids:
            config = replace(
                config,
                openings=(Opening(entity_id=BACK_DOOR, zone_ids=opening_zone_ids),),
            )

        burning = decide(
            config,
            wet_world(minute=1, door_open=False, indoor=COLD, boiler="off"),
        )
        assert command_for(burning, GAS).hvac_mode == "heat"

        stopped = decide(
            config,
            wet_world(minute=2, door_open=stop_door_open, indoor=stop_indoor, boiler="heat"),
            burning,
        )
        stopped_command = command_for(stopped, GAS)
        assert stopped_command is not None
        assert stopped_command.hvac_mode == "off"
        if rests:
            assert stopped_command.reason is Reason.OPENING_OPEN
            assert GAS in stopped.stopped_by_opening
        else:
            assert GAS not in stopped.stopped_by_opening

        again = decide(
            config,
            wet_world(minute=3, door_open=False, indoor=COLD, boiler="off"),
            stopped,
        )
        again_command = command_for(again, GAS)
        assert again_command is not None
        if rests:
            assert again_command.hvac_mode == "off"
            assert again_command.reason is Reason.SHORT_CYCLE_PROTECTION
        else:
            assert again_command.hvac_mode == "heat"

    def test_a_house_wide_listed_generator_rests_too(self) -> None:
        config = wet_house(house_wide_openings=(GAS,))

        burning = decide(
            config,
            wet_world(minute=1, door_open=False, indoor=COLD, boiler="off"),
        )
        assert command_for(burning, GAS).hvac_mode == "heat"

        stopped = decide(
            config,
            wet_world(minute=2, door_open=True, indoor=COLD, boiler="heat"),
            burning,
        )
        stopped_command = command_for(stopped, GAS)
        assert stopped_command is not None
        assert stopped_command.hvac_mode == "off"
        assert stopped_command.reason is Reason.OPENING_OPEN_ELSEWHERE
        assert GAS in stopped.stopped_by_opening

        again = decide(
            config,
            wet_world(minute=3, door_open=False, indoor=COLD, boiler="off"),
            stopped,
        )
        again_command = command_for(again, GAS)
        assert again_command is not None
        assert again_command.hvac_mode == "off"
        assert again_command.reason is Reason.SHORT_CYCLE_PROTECTION

    def test_a_flapping_door_ignites_the_generator_at_most_once(self) -> None:
        config = wet_house()
        issued: list[str] = []
        previous = None
        boiler = "off"
        for minute, door_open in (
            (0, False),
            (1, True),
            (2, False),
            (3, True),
            (4, False),
            (5, True),
            (6, False),
            (7, True),
            (8, False),
            (9, True),
            (10, False),
        ):
            plan = decide(
                config,
                wet_world(minute=minute, door_open=door_open, indoor=COLD, boiler=boiler),
                previous,
            )
            command = command_for(plan, GAS)
            assert command is not None
            issued.append(command.hvac_mode)
            boiler = command.hvac_mode
            previous = plan

        starts = sum(
            1
            for before, after in zip(issued, issued[1:], strict=False)
            if before == "off" and after == "heat"
        )
        assert starts <= 1, f"de brander werd {starts} keer opnieuw ontstoken: {issued}"


# ---------------------------------------------------------------------------
# Opslag / storage
# ---------------------------------------------------------------------------


def test_the_list_survives_a_round_trip() -> None:
    config = shared_boiler(house_wide_openings=(GAS, LIVING_AIRCO))

    back = serialise.config_from_dict(serialise.config_to_dict(config))
    assert back.house_wide_openings == (GAS, LIVING_AIRCO)
    assert back == config


def test_an_installation_stored_before_this_setting_reads_as_empty() -> None:
    stored = serialise.config_to_dict(shared_boiler())
    del stored["house_wide_openings"]

    assert serialise.config_from_dict(stored).house_wide_openings == ()


def test_an_unreadable_list_reads_as_empty_rather_than_falling_over() -> None:
    stored = serialise.config_to_dict(shared_boiler())
    stored["house_wide_openings"] = "climate.cv_ketel"

    assert serialise.config_from_dict(stored).house_wide_openings == ()


# ---------------------------------------------------------------------------
# De controle / the check
# ---------------------------------------------------------------------------


def codes(config: DirectorConfig) -> set[str]:
    """Return the codes of everything `validate()` complains about."""
    return {item.code for item in validate(config) if hasattr(item, "code")}


def test_a_correct_setup_draws_no_complaint() -> None:
    assert "house_wide_without_openings" not in codes(shared_boiler(house_wide_openings=(GAS,)))
    assert "house_wide_unmanaged" not in codes(shared_boiler(house_wide_openings=(GAS,)))


def test_a_list_without_any_opening_is_reported() -> None:
    """Anders staat de instelling er en gebeurt er nooit iets."""
    config = replace(shared_boiler(house_wide_openings=(GAS,)), openings=())

    assert "house_wide_without_openings" in codes(config)


def test_an_appliance_nobody_steers_is_reported() -> None:
    config = shared_boiler(house_wide_openings=("climate.los_kacheltje",))

    assert "house_wide_unmanaged" in codes(config)


def test_a_generator_counts_as_steered() -> None:
    assert "house_wide_unmanaged" not in codes(generator_house(house_wide_openings=(GAS,)))


def test_the_outdoor_dead_band_does_not_hold_a_stopped_appliance() -> None:
    """De band houdt vast wat draait; wat stil moet staan mag niet doorlopen.

    Zonder deze grens hield de dode band op de buitentemperatuur de ketel vast:
    hij lag buiten zijn venster maar binnen de band, en dat is precies de greep
    die een draaiende bron laat doorlopen - ook een die stil hoorde te vallen.
    """
    boiler = Source(
        source_id="ketel_woonkamer",
        entity_id=GAS,
        role=SourceRole.HEAT_ONLY,
        outdoor=OutdoorWindow(maximum=3.0),
    )
    config = shared_boiler(house_wide_openings=(GAS,))
    config = replace(config, zones=(replace(config.zones[0], sources=(boiler,)), config.zones[1]))

    # Ronde 1: binnen het venster, deur dicht - de ketel levert deze zone.
    running = decide(config, cold_house(outdoor=2.0, openings={}))
    assert decision_for(running, "woonkamer").source_id == "ketel_woonkamer"

    # Ronde 2: buiten het venster maar binnen de dode band van 0,5, deur open.
    plan = decide(config, cold_house(outdoor=3.2), running)

    # Het commando is uit - maar dat zegt het vangnet ook zonder deze grens.
    # Waar het om gaat is dat het plan de ketel niet meer toewijst: anders
    # noemt `sensor.…_bron_<zone>` een apparaat dat vervolgens uitgaat.
    living = decision_for(plan, "woonkamer")
    assert living.source_id is None
    assert living.reason is Reason.OPENING_OPEN_ELSEWHERE

    command = command_for(plan, GAS)
    assert command is not None
    assert command.hvac_mode == "off"


# ---------------------------------------------------------------------------
# Kortcyclusbescherming op de huisbrede stop
# Short-cycle protection on the house-wide stop
# ---------------------------------------------------------------------------


def flapping_config() -> DirectorConfig:
    """Return the shared boiler house with a door that acts at once.

    `shared_boiler` geeft zijn dakraam vijf minuten vertraging; een klapperende
    deur heeft die niet, dus hier geldt de standaardvertraging van nul.

    `shared_boiler` gives its skylight a five-minute delay; a flapping door has
    none, so here the default delay of zero applies.
    """
    return replace(
        shared_boiler(house_wide_openings=(GAS,)),
        openings=(Opening(entity_id=SKYLIGHT, zone_ids=("zolder",)),),
    )


def flap_world(*, minute: int, door_open: bool, boiler: str = "off") -> object:
    """Return a world at 12:`minute` with the door as given and both rooms cold."""
    return make_world(
        now=at(12, minute),
        outdoor=2.0,
        indoor={"woonkamer": 18.0, "zolder": 18.0},
        climates={GAS: climate(boiler)},
        residents=everyone_up(),
        openings={SKYLIGHT: OpeningState(open=door_open, changed_at=at(12, minute))},
    )


def test_a_door_that_keeps_opening_and_closing_ignites_the_burner_at_most_once() -> None:
    """Tien keer open en dicht in tien minuten, hoogstens één ontsteking.

    The door flapping ten times in ten minutes must not ignite the burner twice.
    """
    config = flapping_config()
    issued: list[str] = []
    previous = None
    for minute, door_open in (
        (0, False),
        (1, True),
        (2, False),
        (3, True),
        (4, False),
        (5, True),
        (6, False),
        (7, True),
        (8, False),
        (9, True),
        (10, False),
    ):
        plan = decide(config, flap_world(minute=minute, door_open=door_open), previous)
        command = command_for(plan, GAS)
        assert command is not None
        issued.append(command.hvac_mode)
        previous = plan

    starts = sum(
        1
        for before, after in zip(issued, issued[1:], strict=False)
        if before == "off" and after == "heat"
    )
    assert starts <= 1, f"de brander werd {starts} keer opnieuw ontstoken: {issued}"


def test_a_door_that_stays_open_keeps_the_boiler_off() -> None:
    """De stop zelf wordt nooit uitgesteld, alleen de herstart."""
    config = flapping_config()
    world = flap_world(minute=1, door_open=True)

    plan = decide(config, world)
    assert command_for(plan, GAS).hvac_mode == "off"

    later = decide(config, flap_world(minute=20, door_open=True), plan)
    assert command_for(later, GAS).hvac_mode == "off"


def test_the_restart_waits_one_rest_time_after_closing() -> None:
    """De herstart wacht de rusttijd uit, en de deferral staat er ook echt."""
    config = flapping_config()

    stopped = decide(config, flap_world(minute=1, door_open=True, boiler="heat"))
    stopped_command = command_for(stopped, GAS)
    assert stopped_command is not None
    assert stopped_command.hvac_mode == "off"
    assert stopped_command.reason is Reason.OPENING_OPEN_ELSEWHERE

    waiting = decide(config, flap_world(minute=2, door_open=False), stopped)
    waiting_command = command_for(waiting, GAS)
    assert waiting_command is not None
    assert waiting_command.hvac_mode == "off"
    assert waiting_command.reason is Reason.SHORT_CYCLE_PROTECTION

    deferral = waiting.next_deferral
    assert deferral is not None
    assert deferral.subject == GAS
    assert deferral.reason is Reason.SHORT_CYCLE_PROTECTION
    assert deferral.until == at(12, 2) + gates.OPENING_MIN_REST

    resumed = decide(config, flap_world(minute=5, door_open=False), waiting)
    resumed_command = command_for(resumed, GAS)
    assert resumed_command is not None
    assert resumed_command.hvac_mode == "heat"


def own_boiler() -> DirectorConfig:
    """Return one room heated by a boiler that hangs on no circuit.

    De opening raakt de kamer zelf; de ketel staat niet op de huisbrede lijst.
    Vóór P3 kon deze ketel klapperen zodra zijn eigen deur openging, want de
    rusttijd gold alleen voor de huisbrede stop.

    The opening affects the room itself; the boiler is not on the house-wide
    list. Before P3 this boiler could flap once its own door opened, because the
    rest only applied to the house-wide stop.
    """
    room = Zone(
        zone_id="woonkamer",
        name="Woonkamer",
        indoor_sensor="sensor.woonkamer",
        priority=0,
        sources=(Source(source_id="ketel", entity_id=GAS, role=SourceRole.HEAT_ONLY),),
        heat=warmth(),
    )
    return DirectorConfig(
        zones=(room,),
        openings=(Opening(entity_id=BACK_DOOR, zone_ids=("woonkamer",)),),
        outdoor_sensor="sensor.buiten",
    )


def own_door_world(*, minute: int, door_open: bool, boiler: str = "off") -> object:
    """Return a world at 12:`minute` with the room cold and its own door as given."""
    return make_world(
        now=at(12, minute),
        outdoor=2.0,
        indoor={"woonkamer": 18.0},
        climates={GAS: climate(boiler)},
        openings={BACK_DOOR: OpeningState(open=door_open, changed_at=at(12, minute))},
    )


def test_a_zone_door_stop_rests_a_circuit_less_boiler_too() -> None:
    """De rusttijd geldt voor élke openingsstop van een apparaat zonder circuit.

    The rest applies to every opening stop of an appliance without a circuit.
    """
    config = own_boiler()

    stopped = decide(config, own_door_world(minute=1, door_open=True, boiler="heat"))
    stopped_command = command_for(stopped, GAS)
    assert stopped_command is not None
    assert stopped_command.hvac_mode == "off"
    assert stopped_command.reason is Reason.OPENING_OPEN

    waiting = decide(config, own_door_world(minute=2, door_open=False), stopped)
    waiting_command = command_for(waiting, GAS)
    assert waiting_command is not None
    assert waiting_command.hvac_mode == "off"
    assert waiting_command.reason is Reason.SHORT_CYCLE_PROTECTION

    deferral = waiting.next_deferral
    assert deferral is not None
    assert deferral.subject == GAS
    assert deferral.reason is Reason.SHORT_CYCLE_PROTECTION
    assert deferral.until == at(12, 2) + gates.OPENING_MIN_REST

    resumed = decide(config, own_door_world(minute=5, door_open=False), waiting)
    resumed_command = command_for(resumed, GAS)
    assert resumed_command is not None
    assert resumed_command.hvac_mode == "heat"


BEDROOM_WINDOW = "binary_sensor.slaapkamerraam"


def central_boiler(living_priority: int, bedroom_priority: int) -> DirectorConfig:
    """Return one boiler under two rooms; the window belongs to the bedroom only.

    De woonkamer ligt in de dode band, dus die levert `within_deadband`. Staat
    het slaapkamerraam open, dan levert de slaapkamer `opening_open`; de
    collapse kiest de reden van de zone met de meeste voorrang, en met de
    woonkamer op voorrang 0 overleeft `within_deadband` — precies waar H3 de
    openingsrust verliest.

    The living room sits inside its dead band, so it delivers `within_deadband`.
    With the bedroom window open, the bedroom delivers `opening_open`; the
    collapse keeps the reason of the highest-priority zone, and with the living
    room on priority 0 `within_deadband` survives — exactly where H3 loses the
    opening rest.
    """
    heat = ModeSettings(target=21.0, start_at=20.0, hysteresis=1.0)
    return DirectorConfig(
        zones=(
            Zone(
                zone_id="woonkamer",
                name="Woonkamer",
                indoor_sensor="sensor.woonkamer",
                priority=living_priority,
                sources=(Source(source_id="wk", entity_id=GAS, role=SourceRole.HEAT_ONLY),),
                heat=heat,
            ),
            Zone(
                zone_id="slaapkamer",
                name="Slaapkamer",
                indoor_sensor="sensor.slaapkamer",
                priority=bedroom_priority,
                sources=(Source(source_id="sk", entity_id=GAS, role=SourceRole.HEAT_ONLY),),
                heat=heat,
            ),
        ),
        openings=(Opening(entity_id=BEDROOM_WINDOW, zone_ids=("slaapkamer",)),),
    )


def central_world(*, minute: int, window_open: bool, boiler: str) -> object:
    """Return a world at 12:`minute`: living in the dead band, bedroom cold."""
    return make_world(
        now=at(12, minute),
        indoor={"woonkamer": 20.5, "slaapkamer": 16.0},
        climates={GAS: climate(boiler, changed_at=at(12, minute - 1))},
        openings={BEDROOM_WINDOW: OpeningState(open=window_open, changed_at=at(12, minute))},
    )


class TestTheOpeningRestBelongsToTheAppliance:
    """De openingsrust hangt aan het apparaat, niet aan de collapsewinnaar.

    The opening rest belongs to the appliance, not to the collapse winner.
    """

    @pytest.mark.parametrize(
        ("living_priority", "bedroom_priority"),
        [(0, 1), (1, 0)],
        ids=["deadband_wins", "opening_wins"],
    )
    def test_a_flapping_bedroom_window_does_not_re_ignite_the_shared_boiler(
        self, living_priority: int, bedroom_priority: int
    ) -> None:
        config = central_boiler(living_priority, bedroom_priority)

        burning = decide(config, central_world(minute=1, window_open=False, boiler="off"))
        assert command_for(burning, GAS).hvac_mode == "heat"

        stopped = decide(config, central_world(minute=2, window_open=True, boiler="heat"), burning)
        assert command_for(stopped, GAS).hvac_mode == "off"

        again = decide(config, central_world(minute=3, window_open=False, boiler="off"), stopped)
        again_command = command_for(again, GAS)
        assert again_command is not None
        assert again_command.hvac_mode != "heat", (
            f"de brander ontsteekt één minuut na de stop: {again_command}"
        )

        resumed = decide(config, central_world(minute=6, window_open=False, boiler="off"), again)
        resumed_command = command_for(resumed, GAS)
        assert resumed_command is not None
        assert resumed_command.hvac_mode == "heat"


def test_the_rest_survives_one_satisfied_round() -> None:
    """M3: één ronde met een andere uit-reden doet de openingsrust niet vergeten.

    The M3 property: one round with another off reason does not forget the
    opening rest.
    """
    config = own_boiler()

    stopped = decide(config, own_door_world(minute=0, door_open=True, boiler="heat"))
    stopped_command = command_for(stopped, GAS)
    assert stopped_command is not None
    assert stopped_command.reason is Reason.OPENING_OPEN

    settled = decide(
        config,
        make_world(
            now=at(12, 1),
            outdoor=2.0,
            indoor={"woonkamer": 25.0},
            climates={GAS: climate("off")},
            openings={BACK_DOOR: OpeningState(open=False, changed_at=at(12, 1))},
        ),
        stopped,
    )
    assert command_for(settled, GAS).hvac_mode == "off"

    resumed = decide(config, own_door_world(minute=2, door_open=False), settled)
    resumed_command = command_for(resumed, GAS)
    assert resumed_command is not None
    assert resumed_command.hvac_mode != "heat", (
        f"de ketel ontsteekt binnen de rusttijd: {resumed_command}"
    )


def rest_world(*, now: datetime, door_open: bool, door_since: datetime, boiler_mode: str) -> object:
    """Return the own-boiler world with the door and the boiler exactly as given."""
    return make_world(
        now=now,
        outdoor=2.0,
        indoor={"woonkamer": 18.0},
        climates={GAS: climate(boiler_mode, changed_at=at(1, 0))},
        openings={BACK_DOOR: OpeningState(open=door_open, changed_at=door_since)},
    )


class TestOnlyARunningApplianceRestsAfterAnOpening:
    """R3: alleen een apparaat dat werkelijk draaide hoeft na een opening te rusten.

    R3: only an appliance that really was running has to rest after an opening.
    """

    @pytest.mark.parametrize(
        ("door_since", "boiler_mode", "rests"),
        [
            (at(1, 0), "off", False),
            (at(6, 59), "off", False),
            (at(1, 0), "heat", True),
            (at(6, 59), "heat", True),
        ],
        ids=["uren_open_koud", "minuut_open_koud", "uren_open_draaiend", "minuut_open_draaiend"],
    )
    def test_the_rest_requires_a_running_appliance(
        self, door_since: datetime, boiler_mode: str, rests: bool
    ) -> None:
        config = own_boiler()

        stopped = decide(
            config,
            rest_world(
                now=at(7, 0), door_open=True, door_since=door_since, boiler_mode=boiler_mode
            ),
        )
        stopped_command = command_for(stopped, GAS)
        assert stopped_command is not None
        assert stopped_command.hvac_mode == "off"
        if rests:
            assert GAS in stopped.stopped_by_opening
        else:
            assert GAS not in stopped.stopped_by_opening

        resumed = decide(
            config,
            rest_world(now=at(7, 1), door_open=False, door_since=at(7, 1), boiler_mode="off"),
            stopped,
        )
        resumed_command = command_for(resumed, GAS)
        assert resumed_command is not None
        if rests:
            assert resumed_command.hvac_mode == "off"
            assert resumed_command.reason is Reason.SHORT_CYCLE_PROTECTION
        else:
            assert resumed_command.hvac_mode == "heat"
