"""Apparaten die wegvallen, in elke denkbare combinatie.

Appliances dropping out, in every conceivable combination.

Een apparaat kan op drie manieren onbereikbaar zijn: het meldt `unavailable`,
het meldt `unknown`, of het bestaat helemaal niet meer omdat iemand het uit
Home Assistant heeft gegooid. Voor de engine zijn die drie hetzelfde, maar dat
mag niet toevallig zo zijn - de koppelingslaag moet ze alle drie op dezelfde
manier vertalen.

Deze module loopt daarom twee dingen af. Eerst elke combinatie van uitgevallen
apparaten in een huis met reservebronnen: welke bron neemt het over, wat meldt
de zone, en wat gebeurt er als er niets meer over is. Daarna dezelfde gevallen
in een draaiende Home Assistant, waar ook de sensoren, de aanwezigheid, het
raamcontact en het seizoen kunnen wegvallen.

An appliance can be unreachable in three ways: it reports `unavailable`, it
reports `unknown`, or it no longer exists at all because somebody threw it out
of Home Assistant. To the engine those three are the same, but that must not be
by accident - the binding layer has to translate all three the same way.

This module therefore walks two things. First every combination of failed
appliances in a house with reserve sources: which source takes over, what the
zone reports, and what happens once nothing is left. Then the same cases inside
a running Home Assistant, where the sensors, the presence, the door contact and
the season can drop out too.
"""

from __future__ import annotations

from itertools import combinations
from typing import Any

import pytest
from conftest import assert_plan_holds, climate, make_world
from harness_live import settings, source, start_house, stop_house, zone

from custom_components.climate_director.engine import (
    Circuit,
    DirectorConfig,
    Generator,
    ModeFamily,
    ModeSettings,
    OutdoorWindow,
    Reason,
    Season,
    Source,
    SourceRole,
    Zone,
    decide,
)

# -- de opstelling / the setup ----------------------------------------------

FIRST = "climate.woonkamer_airco"
SECOND = "climate.woonkamer_kachel"
THIRD = "climate.woonkamer_infrarood"
ATTIC = "climate.zolder_airco"
BOILER = "climate.ketel"

APPLIANCES = (FIRST, SECOND, THIRD, ATTIC, BOILER)

#: De drie manieren waarop een apparaat niet te lezen is. Voor de engine
#: hetzelfde, voor Home Assistant drie verschillende toestanden.
#:
#: The three ways an appliance cannot be read. The same to the engine, three
#: different states to Home Assistant.
UNREADABLE = ("unavailable", "unknown", "missing")


def house() -> DirectorConfig:
    """Return a living room with three sources, an attic with one, and a boiler."""
    living = Zone(
        zone_id="woonkamer",
        name="Woonkamer",
        indoor_sensor="sensor.woonkamer",
        sources=(
            Source("eerste", FIRST, role=SourceRole.HEAT_COOL, priority=0),
            Source("tweede", SECOND, role=SourceRole.HEAT_ONLY, priority=1),
            Source("derde", THIRD, role=SourceRole.HEAT_ONLY, priority=2),
        ),
        heat=ModeSettings(target=21.0, start_at=20.0, hysteresis=1.0),
        cool=ModeSettings(target=23.0, start_at=24.0, hysteresis=1.0),
    )
    attic = Zone(
        zone_id="zolder",
        name="Zolder",
        indoor_sensor="sensor.zolder",
        priority=1,
        sources=(Source("zolder", ATTIC, role=SourceRole.HEAT_COOL),),
        heat=ModeSettings(target=20.0, start_at=19.0, hysteresis=1.0),
    )
    return DirectorConfig(
        zones=(living, attic),
        circuits=(
            Circuit(
                circuit_id="multisplit",
                name="Multi-split",
                units=(FIRST, ATTIC),
                simultaneous_heat_cool=False,
            ),
        ),
        generators=(Generator("ketel", "Ketel", BOILER, zone_ids=("woonkamer",)),),
        outdoor_sensor="sensor.buiten",
    )


def world_with(down: frozenset[str], **extra: Any):
    """Return a cold world in which the named appliances cannot be reached."""
    return make_world(
        outdoor=3.0,
        indoor={"woonkamer": 17.0, "zolder": 16.0},
        climates={entity: climate("off", available=entity not in down) for entity in APPLIANCES},
        **extra,
    )


def _every_outage():
    """Yield every combination of appliances that can be out at once."""
    for count in range(len(APPLIANCES) + 1):
        for group in combinations(APPLIANCES, count):
            yield frozenset(group)


OUTAGES = list(_every_outage())


# ---------------------------------------------------------------------------
# Elke combinatie, door de engine heen.
# Every combination, through the engine.
# ---------------------------------------------------------------------------


class TestEveryCombinationOfOutages:
    """Twee-en-dertig uitvalspatronen, elk met dezelfde beloftes.

    Thirty-two failure patterns, each with the same promises.
    """

    @pytest.mark.parametrize("down", OUTAGES, ids=lambda item: "+".join(sorted(item)) or "geen")
    def test_the_promises_hold_whatever_is_down(self, down: frozenset[str]) -> None:
        config, world = house(), world_with(down)
        plan = decide(config, world)
        assert_plan_holds(config, world, plan, where=f"uitval {sorted(down)}")

    @pytest.mark.parametrize("down", OUTAGES, ids=lambda item: "+".join(sorted(item)) or "geen")
    def test_nothing_is_ever_ordered_at_an_appliance_that_is_gone(
        self, down: frozenset[str]
    ) -> None:
        plan = decide(house(), world_with(down))
        for entity_id in down:
            assert plan.command_for(entity_id) is None, f"{entity_id} kreeg toch een opdracht"

    @pytest.mark.parametrize("down", OUTAGES, ids=lambda item: "+".join(sorted(item)) or "geen")
    def test_every_missing_appliance_is_reported_as_unreachable(self, down: frozenset[str]) -> None:
        plan = decide(house(), world_with(down))
        for entity_id in down & {FIRST, SECOND, THIRD, ATTIC}:
            left = plan.untouched_for(entity_id)
            assert left is not None, f"{entity_id} staat in geen van beide lijsten"
            assert left.reason is Reason.SOURCE_UNREACHABLE

    @pytest.mark.parametrize("down", OUTAGES, ids=lambda item: "+".join(sorted(item)) or "geen")
    def test_the_best_reachable_source_takes_over(self, down: frozenset[str]) -> None:
        """De voorkeursvolgorde blijft staan; alleen wat weg is valt eruit.

        The order of preference stands; only what is gone falls out of it.
        """
        plan = decide(house(), world_with(down))
        decision = plan.decision_for("woonkamer")
        assert decision is not None

        expected = next(
            (
                source_id
                for source_id, entity_id in (
                    ("eerste", FIRST),
                    ("tweede", SECOND),
                    ("derde", THIRD),
                )
                if entity_id not in down
            ),
            None,
        )
        if expected is None:
            assert decision.granted is ModeFamily.NEUTRAL
            assert decision.reason is Reason.NO_SOURCE_AVAILABLE
        else:
            assert decision.source_id == expected
            assert (
                plan.command_for(dict(eerste=FIRST, tweede=SECOND, derde=THIRD)[expected]).hvac_mode
                == "heat"
            )

    @pytest.mark.parametrize("down", OUTAGES, ids=lambda item: "+".join(sorted(item)) or "geen")
    def test_the_skipped_favourites_are_named(self, down: frozenset[str]) -> None:
        """Een kamer die op een tweede keus draait zegt welke eerste keus wegviel.

        A room running on a second choice says which first choice fell away.
        """
        plan = decide(house(), world_with(down))
        decision = plan.decision_for("woonkamer")
        assert decision is not None
        if decision.source_id is None:
            assert decision.passed_over == ()
            return

        order = ["eerste", "tweede", "derde"]
        entities = {"eerste": FIRST, "tweede": SECOND, "derde": THIRD}
        ahead = order[: order.index(decision.source_id)]
        assert list(decision.passed_over) == [item for item in ahead if entities[item] in down]
        assert decision.on_fallback == bool(decision.passed_over)

    @pytest.mark.parametrize("down", OUTAGES, ids=lambda item: "+".join(sorted(item)) or "geen")
    def test_the_boiler_only_runs_while_a_room_it_serves_is_heated(
        self, down: frozenset[str]
    ) -> None:
        plan = decide(house(), world_with(down))
        command = plan.command_for(BOILER)
        if BOILER in down:
            assert command is None
            return
        assert command is not None
        living = plan.decision_for("woonkamer")
        assert living is not None
        wanted = living.granted is ModeFamily.HEAT
        assert (command.hvac_mode == "heat") is wanted


class TestWhenEverythingIsGone:
    """Een huis zonder één bereikbaar apparaat doet niets, en zegt waarom.

    A house without a single reachable appliance does nothing, and says why.
    """

    def test_the_plan_is_empty_but_complete(self) -> None:
        config = house()
        world = world_with(frozenset(APPLIANCES))
        plan = decide(config, world)

        assert plan.commands == ()
        assert len(plan.zones) == len(config.zones)
        assert {item.entity_id for item in plan.untouched} == {
            FIRST,
            SECOND,
            THIRD,
            ATTIC,
        }
        assert all(item.reason is Reason.SOURCE_UNREACHABLE for item in plan.untouched)

    def test_every_zone_says_it_has_nothing_to_work_with(self) -> None:
        plan = decide(house(), world_with(frozenset(APPLIANCES)))
        for decision in plan.zones:
            assert decision.granted is ModeFamily.NEUTRAL
            assert decision.reason is Reason.NO_SOURCE_AVAILABLE


class TestAnOutageWhileRunning:
    """Wegvallen terwijl het apparaat draait: de reserve neemt het over.

    Dropping out while running: the reserve takes over.
    """

    def test_the_reserve_starts_while_the_first_hangs(self) -> None:
        config = house()
        world = make_world(
            outdoor=3.0,
            indoor={"woonkamer": 17.0, "zolder": 21.0},
            climates={
                FIRST: climate("heat", available=False),
                SECOND: climate("off"),
                THIRD: climate("off"),
                ATTIC: climate("off"),
                BOILER: climate("off"),
            },
        )
        plan = decide(config, world)

        assert plan.command_for(SECOND).hvac_mode == "heat"
        assert plan.untouched_for(FIRST).reason is Reason.SOURCE_UNREACHABLE
        assert plan.decision_for("woonkamer").passed_over == ("eerste",)
        assert_plan_holds(config, world, plan)

    def test_the_circuit_is_not_claimed_by_a_unit_nobody_can_read(self) -> None:
        """Een unavailable unit die 'heat' meldde telt niet meer als taak.

        Wat je niet kunt uitlezen kun je ook niet aan een taak houden. De
        zolder moet dus gewoon kunnen koelen zodra de woonkamerunit wegvalt.

        An unavailable unit that reported `heat` no longer counts as a duty.
        What you cannot read you cannot hold to a duty either. The attic must
        therefore simply be able to cool once the living-room unit drops out.
        """
        config = house()
        world = make_world(
            season=Season.SUMMER,
            outdoor=28.0,
            indoor={"woonkamer": 26.0, "zolder": 16.0},
            climates={
                FIRST: climate("cool", available=False),
                SECOND: climate("off"),
                THIRD: climate("off"),
                ATTIC: climate("off"),
                BOILER: climate("off"),
            },
        )
        plan = decide(config, world)
        assert plan.command_for(ATTIC).hvac_mode == "heat"
        assert_plan_holds(config, world, plan)

    def test_coming_back_puts_the_favourite_in_charge_again(self) -> None:
        config = house()
        world = make_world(
            outdoor=3.0,
            indoor={"woonkamer": 17.0, "zolder": 21.0},
            climates={
                FIRST: climate("off"),
                SECOND: climate("heat"),
                THIRD: climate("off"),
                ATTIC: climate("off"),
                BOILER: climate("off"),
            },
        )
        plan = decide(config, world)
        assert plan.command_for(FIRST).hvac_mode == "heat"
        assert plan.command_for(SECOND).hvac_mode == "off"
        assert plan.decision_for("woonkamer").passed_over == ()


class TestOutdoorWindowsAndOutages:
    """De buitengrens kiest het apparaat; uitval mag die keuze niet omzeilen.

    The outdoor window picks the appliance; an outage must not sidestep it.
    """

    def _split(self) -> DirectorConfig:
        """Return a boiler below three degrees and a heat pump above it."""
        living = Zone(
            zone_id="woonkamer",
            name="Woonkamer",
            indoor_sensor="sensor.woonkamer",
            sources=(
                Source("warmtepomp", FIRST, outdoor=OutdoorWindow(minimum=3.0)),
                Source(
                    "gasketel",
                    SECOND,
                    role=SourceRole.HEAT_ONLY,
                    outdoor=OutdoorWindow(maximum=3.0),
                ),
            ),
            heat=ModeSettings(target=21.0, start_at=20.0, hysteresis=1.0),
        )
        return DirectorConfig(zones=(living,), outdoor_sensor="sensor.buiten")

    def test_the_boiler_carries_the_cold_and_is_not_replaced_by_the_heat_pump(self) -> None:
        config = self._split()
        world = make_world(
            outdoor=-5.0,
            indoor={"woonkamer": 17.0},
            climates={FIRST: climate("off"), SECOND: climate("off", available=False)},
        )
        plan = decide(config, world)
        decision = plan.decision_for("woonkamer")
        assert decision.granted is ModeFamily.NEUTRAL
        assert decision.reason is Reason.NO_SOURCE_AVAILABLE
        assert plan.command_for(FIRST).hvac_mode == "off", (
            "de warmtepomp hoort bij vijf graden vorst niet in te vallen"
        )

    def test_an_unknown_outdoor_temperature_shuts_every_bounded_source_out(self) -> None:
        config = self._split()
        world = make_world(
            outdoor=None,
            indoor={"woonkamer": 17.0},
            climates={FIRST: climate("off"), SECOND: climate("off")},
        )
        plan = decide(config, world)
        assert plan.decision_for("woonkamer").reason is Reason.NO_SOURCE_AVAILABLE


# ---------------------------------------------------------------------------
# Dezelfde uitval, maar dan in een draaiende Home Assistant.
# The same outages, but inside a running Home Assistant.
# ---------------------------------------------------------------------------


LIVE_FIRST = "climate.eerste"
LIVE_SECOND = "climate.tweede"


def live_installation() -> dict[str, Any]:
    """Return a one-room installation with a first choice and a stand-in."""
    return {
        "zones": [
            zone(
                "woonkamer",
                sources=[
                    source("eerste", LIVE_FIRST, role="heat_cool"),
                    source("tweede", LIVE_SECOND, role="heat_only", priority=1),
                ],
                heat=settings(21.0, 20.0),
            )
        ],
        "outdoor_sensor": "sensor.buiten",
        "seasons": {"source": "entity", "entity_id": "sensor.seizoen"},
    }


def live_world() -> dict[str, tuple[str, dict[str, Any]]]:
    """Return a cold world in which the first choice can serve the room."""
    return {
        "sensor.woonkamer": ("18.0", {}),
        "sensor.buiten": ("4.0", {}),
        "sensor.seizoen": ("winter", {}),
        LIVE_FIRST: ("off", {}),
        LIVE_SECOND: ("off", {}),
    }


@pytest.mark.parametrize("how", UNREADABLE)
async def test_a_broken_appliance_hands_over_to_the_stand_in(how: str) -> None:
    """`unavailable`, `unknown` en helemaal weg horen hetzelfde te doen.

    `unavailable`, `unknown` and gone altogether should all do the same.
    """
    states = live_world()
    if how == "missing":
        states.pop(LIVE_FIRST)
    else:
        states[LIVE_FIRST] = (how, {})

    home = await start_house(live_installation(), states=states)
    try:
        assert home.state(LIVE_SECOND) == "heat", f"de reserve viel niet in bij {how}"
        assert home.value("zone_woonkamer_fallback") == "on"
        assert home.values("zone_woonkamer_fallback")["unreachable"] == ["eerste"]
        assert home.value(f"command_{LIVE_FIRST}") == "unreachable"
        assert home.value("zone_woonkamer_source") == "tweede"
    finally:
        await stop_house(home)


@pytest.mark.parametrize("how", UNREADABLE)
async def test_a_room_without_a_reading_simply_stops(how: str) -> None:
    """Zonder kamertemperatuur valt er niets te regelen, en dat wordt gemeld.

    Without a room temperature there is nothing to regulate, and it is reported.
    """
    states = live_world()
    if how == "missing":
        states.pop("sensor.woonkamer")
    else:
        states["sensor.woonkamer"] = (how, {})

    home = await start_house(live_installation(), states=states)
    try:
        assert home.state(LIVE_FIRST) == "off"
        assert home.values("zone_woonkamer_source")["reason"] == "no_indoor_temperature"
        assert "sensor.woonkamer" in home.values("stuck")["unusable_entities"] or (how == "missing")
    finally:
        await stop_house(home)


@pytest.mark.parametrize("how", UNREADABLE)
async def test_the_unusable_list_names_whatever_cannot_be_read(how: str) -> None:
    states = live_world()
    if how == "missing":
        states.pop("sensor.buiten")
    else:
        states["sensor.buiten"] = (how, {})

    home = await start_house(live_installation(), states=states)
    try:
        unusable = home.coordinator.unusable_entities()
        assert unusable.get("sensor.buiten") == ("missing" if how == "missing" else how)
        # Opvallen doet hij onder Reparaties (na vijf minuten, zie
        # test_unreadable_entities.py) en in dit attribuut - niet meer via de
        # vastloopmelder, die weer alleen over wachtende zones gaat.
        #
        # Standing out happens under Repairs (after five minutes, see
        # test_unreadable_entities.py) and in this attribute - no longer through
        # the stuck sensor, which is once again only about waiting zones.
        assert "sensor.buiten" in home.values("stuck")["unusable_entities"]
    finally:
        await stop_house(home)


async def test_an_unreadable_season_entity_falls_back_to_no_season() -> None:
    """Een kapotte seizoenshelper mag geen taak stilletjes uitzetten.

    Het seizoen wordt dan onbekend, en alleen wat aan een seizoen gebonden is
    valt weg - de rest regelt gewoon door.

    A broken season helper must not quietly switch a duty off. The season
    becomes unknown, and only what is bound to a season falls away - the rest
    simply carries on.
    """
    states = live_world()
    states["sensor.seizoen"] = ("unavailable", {})
    home = await start_house(live_installation(), states=states)
    try:
        assert home.coordinator.world.season is Season.UNKNOWN
        assert home.state(LIVE_FIRST) == "heat", "verwarmen zonder seizoenseis loopt door"
    finally:
        await stop_house(home)


async def test_an_unrecognised_season_state_is_reported() -> None:
    """Een leesbare maar onherkenbare seizoensstaat hoort op te vallen.

    De entiteit bestaat en is leesbaar, dus de gewone onbruikbaarheidscontrole
    pakt hem niet - terwijl het seizoen wél UNKNOWN wordt en alles wat eraan
    hangt stilletjes wegvalt.

    A readable but unrecognised season state should stand out. The entity
    exists and reads fine, so the ordinary unusable check does not catch it -
    while the season does become UNKNOWN and everything hanging off it quietly
    falls away.
    """
    states = live_world()
    states["sensor.seizoen"] = ("droog", {})
    home = await start_house(live_installation(), states=states)
    try:
        unusable = home.coordinator.unusable_entities()
        assert unusable.get("sensor.seizoen") == "unrecognized season: droog"
        assert "sensor.seizoen" in home.values("stuck")["unusable_entities"]
    finally:
        await stop_house(home)


async def test_a_recognised_season_state_is_not_reported() -> None:
    states = live_world()
    states["sensor.seizoen"] = ("Zomer", {})
    home = await start_house(live_installation(), states=states)
    try:
        assert "sensor.seizoen" not in home.coordinator.unusable_entities()
    finally:
        await stop_house(home)


async def test_a_readable_sensor_without_a_number_is_reported() -> None:
    """Een sensor die bestaat en leesbaar is, maar geen getal geeft.

    De zone leest NO_INDOOR_TEMPERATURE en doet niets; de sensor hoort daarom
    in de onbruikbaarheidslijst te staan, waar de reparatiemelding hem oppikt.

    A sensor that exists and reads fine, but yields no number. The zone reads
    NO_INDOOR_TEMPERATURE and does nothing; the sensor therefore belongs in the
    unusable list, from where the repair notice picks it up.
    """
    states = live_world()
    states["sensor.woonkamer"] = ("warm", {})
    home = await start_house(live_installation(), states=states)
    try:
        unusable = home.coordinator.unusable_entities()
        assert unusable.get("sensor.woonkamer") == "no number"
        assert "sensor.woonkamer" in home.values("stuck")["unusable_entities"]
    finally:
        await stop_house(home)


async def test_a_sensor_with_a_number_is_not_reported() -> None:
    states = live_world()
    home = await start_house(live_installation(), states=states)
    try:
        assert "sensor.woonkamer" not in home.coordinator.unusable_entities()
    finally:
        await stop_house(home)


async def test_a_missing_climate_entity_never_gets_a_service_call() -> None:
    """Er wordt niets gestuurd naar een apparaat dat er niet is.

    Nothing is sent to an appliance that is not there.
    """
    states = live_world()
    states.pop(LIVE_FIRST)
    states.pop(LIVE_SECOND)
    home = await start_house(live_installation(), states=states)
    try:
        assert home.climate_calls() == []
        assert home.value("zone_woonkamer_source") == "none"
        assert home.values("zone_woonkamer_source")["reason"] == "no_source_available"
    finally:
        await stop_house(home)


async def test_an_appliance_that_comes_back_is_picked_up_again() -> None:
    """Terug in de lucht betekent: weer de eerste keus.

    Back online means: the first choice again.
    """
    states = live_world()
    states[LIVE_FIRST] = ("unavailable", {})
    home = await start_house(live_installation(), states=states)
    try:
        assert home.state(LIVE_SECOND) == "heat"
        home.climate(LIVE_FIRST, "off")
        await home.evaluate()
        assert home.state(LIVE_FIRST) == "heat"
        assert home.state(LIVE_SECOND) == "off"
        assert home.value("zone_woonkamer_fallback") == "off"
    finally:
        await stop_house(home)
