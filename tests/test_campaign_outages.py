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

from dataclasses import replace
from datetime import datetime
from itertools import combinations
from typing import Any

import pytest
from conftest import assert_plan_holds, awake, climate, make_world
from harness_live import settings, source, start_house, stop_house, zone

from custom_components.climate_director.engine import (
    Circuit,
    DirectorConfig,
    GateSettings,
    Generator,
    ModeFamily,
    ModeSettings,
    Opening,
    OpeningState,
    OutdoorWindow,
    Reason,
    Resident,
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
        # Ook de onbereikbare ketel hoort in `untouched`: "elk apparaat komt in
        # precies één van de twee lijsten" geldt voor generatoren net zo goed.
        # The unreachable boiler belongs in `untouched` too: "every appliance
        # lands in exactly one of the two lists" holds for generators as well.
        assert {item.entity_id for item in plan.untouched} == set(APPLIANCES)
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
        decision = plan.decision_for("woonkamer")
        assert decision is not None
        assert decision.granted is ModeFamily.NEUTRAL
        assert decision.reason is Reason.NO_OUTDOOR_TEMPERATURE
        # "Elke beheerde bron krijgt een commando": wie uitstaat krijgt off.
        # "Every managed source gets a command": one that is off gets its off.
        assert plan.command_for(FIRST).hvac_mode == "off"
        assert plan.command_for(SECOND).hvac_mode == "off"


class TestAnUnreadableOutdoorSensorNeverStopsARunningAppliance:
    """Zonder buitentemperatuur gaat er nooit een uit-commando naar een draaiend
    apparaat, ongeacht wáár de buitengrens staat.

    Without an outdoor temperature no off command ever goes to a running
    appliance, wherever the outdoor bound sits.
    """

    @pytest.mark.parametrize(
        "placement",
        ["zone_heat", "zone_cool", "source", "source_and_zone"],
    )
    def test_a_running_appliance_is_left_alone(self, placement: str) -> None:
        config, running, other, duty = _bounded_placement(placement)
        indoor = {"woonkamer": 26.0} if duty == "cool" else {"woonkamer": 17.0}
        climates = {running: climate(duty)}
        if other != running:
            climates[other] = climate("off")
        world = make_world(
            outdoor=None,
            season=Season.SUMMER if duty == "cool" else Season.WINTER,
            indoor=indoor,
            climates=climates,
        )
        plan = decide(config, world)
        assert plan.command_for(running) is None, (
            f"{placement}: draaiend apparaat kreeg een opdracht"
        )
        left = plan.untouched_for(running)
        assert left is not None, f"{placement}: draaiend apparaat staat in geen van beide lijsten"
        assert left.reason is Reason.NO_OUTDOOR_TEMPERATURE


def _bounded_placement(placement: str) -> tuple[DirectorConfig, str, str, str]:
    """Return (config, running appliance, other appliance, duty) per placement.

    De vier plekken waar een buitengrens kan staan:
    (a) zone-heat, (b) zone-cool, (c) de bron, (d) bron én zone.

    The four places an outdoor bound can sit:
    (a) zone heat, (b) zone cool, (c) the source, (d) source and zone.
    """
    gas = "climate.gasketel"
    airco = "climate.airco"

    if placement == "zone_heat":
        zone_ = Zone(
            "woonkamer",
            "Woonkamer",
            "sensor.woonkamer",
            sources=(Source("gas", gas, role=SourceRole.HEAT_ONLY),),
            heat=ModeSettings(21.0, 20.0, outdoor=OutdoorWindow(maximum=19.0)),
        )
        return DirectorConfig(zones=(zone_,), outdoor_sensor="sensor.buiten"), gas, gas, "heat"

    if placement == "zone_cool":
        zone_ = Zone(
            "woonkamer",
            "Woonkamer",
            "sensor.woonkamer",
            sources=(Source("airco", airco, role=SourceRole.HEAT_COOL),),
            cool=ModeSettings(23.0, 24.0, outdoor=OutdoorWindow(minimum=24.0)),
        )
        return DirectorConfig(zones=(zone_,), outdoor_sensor="sensor.buiten"), airco, airco, "cool"

    if placement == "source":
        zone_ = Zone(
            "woonkamer",
            "Woonkamer",
            "sensor.woonkamer",
            sources=(
                Source(
                    "gas",
                    gas,
                    role=SourceRole.HEAT_ONLY,
                    priority=1,
                    outdoor=OutdoorWindow(maximum=3.1),
                ),
                Source(
                    "airco",
                    airco,
                    role=SourceRole.HEAT_COOL,
                    priority=0,
                    outdoor=OutdoorWindow(minimum=3.1),
                ),
            ),
            heat=ModeSettings(21.0, 20.0),
        )
        return DirectorConfig(zones=(zone_,), outdoor_sensor="sensor.buiten"), gas, airco, "heat"

    zone_ = Zone(
        "woonkamer",
        "Woonkamer",
        "sensor.woonkamer",
        sources=(
            Source(
                "gas",
                gas,
                role=SourceRole.HEAT_ONLY,
                priority=1,
                outdoor=OutdoorWindow(maximum=3.1),
            ),
            Source(
                "airco",
                airco,
                role=SourceRole.HEAT_COOL,
                priority=0,
                outdoor=OutdoorWindow(minimum=3.1),
            ),
        ),
        heat=ModeSettings(21.0, 20.0, outdoor=OutdoorWindow(maximum=19.0)),
    )
    return DirectorConfig(zones=(zone_,), outdoor_sensor="sensor.buiten"), gas, airco, "heat"


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


# ---------------------------------------------------------------------------
# Een onleesbare buitensensor, met de grens op elke denkbare plek.
# An unreadable outdoor sensor, with the bound on every conceivable place.
# ---------------------------------------------------------------------------

OUTDOOR_UNREADABLE = ("unavailable", "unknown", "NaN", "missing")
OUTDOOR_PLACEMENTS = ("zone_heat", "zone_cool", "source", "source_and_zone")


def _live_bounded_placement(placement: str) -> tuple[dict[str, Any], str, str, str, float]:
    """Return (installation, running appliance, other appliance, duty, indoor)."""
    gas = "climate.gasketel"
    airco = "climate.airco"

    if placement == "zone_heat":
        return (
            {
                "zones": [
                    zone(
                        "woonkamer",
                        sources=[source("gas", gas, role="heat_only")],
                        indoor_sensor="sensor.woonkamer",
                        heat=settings(21.0, 20.0, outdoor={"minimum": None, "maximum": 19.0}),
                    )
                ],
                "outdoor_sensor": "sensor.buiten",
            },
            gas,
            gas,
            "heat",
            18.0,
        )

    if placement == "zone_cool":
        return (
            {
                "zones": [
                    zone(
                        "woonkamer",
                        sources=[source("airco", airco, role="heat_cool")],
                        indoor_sensor="sensor.woonkamer",
                        cool=settings(23.0, 24.0, outdoor={"minimum": 24.0, "maximum": None}),
                    )
                ],
                "outdoor_sensor": "sensor.buiten",
            },
            airco,
            airco,
            "cool",
            26.0,
        )

    sources = [
        source(
            "gas",
            gas,
            role="heat_only",
            priority=1,
            outdoor={"minimum": None, "maximum": 3.1},
        ),
        source(
            "airco",
            airco,
            role="heat_cool",
            priority=0,
            outdoor={"minimum": 3.1, "maximum": None},
        ),
    ]
    heat = (
        settings(21.0, 20.0, outdoor={"minimum": None, "maximum": 19.0})
        if placement == "source_and_zone"
        else settings(21.0, 20.0)
    )
    return (
        {
            "zones": [
                zone(
                    "woonkamer",
                    sources=sources,
                    indoor_sensor="sensor.woonkamer",
                    heat=heat,
                )
            ],
            "outdoor_sensor": "sensor.buiten",
        },
        gas,
        airco,
        "heat",
        18.0,
    )


@pytest.mark.parametrize("placement", OUTDOOR_PLACEMENTS)
@pytest.mark.parametrize("how", OUTDOOR_UNREADABLE)
async def test_an_unreadable_outdoor_sensor_leaves_a_running_appliance_alone(
    placement: str, how: str
) -> None:
    """Vier plekken voor de grens, vier manieren onleesbaar: nooit iets uitzetten.

    Four places for the bound, four ways to be unreadable: never switch
    anything off.
    """
    installation, running, other, duty, indoor = _live_bounded_placement(placement)
    states: dict[str, tuple[str, dict[str, Any]]] = {
        "sensor.woonkamer": (str(indoor), {}),
        running: (duty, {"hvac_modes": ["heat", "cool", "off"]}),
    }
    if other != running:
        states[other] = ("off", {"hvac_modes": ["heat", "cool", "off"]})
    if how == "missing":
        states.pop("sensor.buiten", None)
    else:
        states["sensor.buiten"] = (how, {})

    home = await start_house(installation, states=states)
    try:
        assert home.state(running) == duty, f"{placement}/{how}: draaiend apparaat ging uit"
        reason = home.values("zone_woonkamer_source").get("reason")
        assert reason == "no_outdoor_temperature", f"{placement}/{how}: reden is {reason}"
    finally:
        await stop_house(home)


# ---------------------------------------------------------------------------
# Een dode thermometer en een gedeelde warmtebron.
# A dead thermometer and a shared heat source.
# ---------------------------------------------------------------------------

BLIND_BOILER = ("binnen", "buiten")
VALVE = "climate.badkamer_kraan"


def _blind_boiler_house() -> DirectorConfig:
    """Eén kamer met een radiatorkraan en een gedeelde ketel eronder."""
    zone = Zone(
        zone_id="badkamer",
        name="Badkamer",
        indoor_sensor="sensor.badkamer",
        sources=(Source("kraan", VALVE, role=SourceRole.HEAT_ONLY),),
        heat=ModeSettings(
            target=22.0,
            start_at=21.0,
            hysteresis=1.0,
            outdoor=OutdoorWindow(maximum=19.0),
        ),
    )
    return DirectorConfig(
        zones=(zone,),
        generators=(Generator("cv", "CV", BOILER, zone_ids=("badkamer",)),),
        residents=(Resident("danny", "Danny", presence_entity="person.danny"),),
        gates=GateSettings(require_awake=True),
        outdoor_sensor="sensor.buiten",
    )


def _blind_boiler_world(*, which: str, running: bool):
    indoor = None if which == "binnen" else 17.0
    outdoor = None if which == "buiten" else -5.0
    boiler = "heat" if running else "off"
    return make_world(
        now=datetime(2026, 1, 12, 10, 0),
        outdoor=outdoor,
        indoor={"badkamer": indoor},
        climates={
            VALVE: climate("heat", changed_at=datetime(2026, 1, 12, 9, 0)),
            BOILER: climate(boiler, changed_at=datetime(2026, 1, 12, 9, 0)),
        },
        residents={"danny": awake()},
    )


@pytest.mark.parametrize("which", BLIND_BOILER)
@pytest.mark.parametrize("running", (True, False), ids=("draait", "stond_uit"))
def test_a_blind_shared_boiler_is_left_alone(which: str, running: bool) -> None:
    """Zonder leesbare temperatuur gaat er nooit een brandende ketel uit.

    Anker 2 geldt voor élk apparaat dat de director aanstuurt: een draaiende
    gedeelde warmtebron hoort bij een dode binnen- of buitensensor in
    `untouched` met de reden van die weigering, niet uit. Wie al uit stond
    krijgt gewoon zijn uit-commando, want "elke beheerde bron krijgt een
    commando" blijft gelden.

    Anchor 2 covers every appliance the director steers: with a dead indoor or
    outdoor sensor a running shared heat source belongs in `untouched` with
    that refusal's reason, not off. One that was already off simply gets its
    off command, since "every managed source gets a command" still holds.
    """
    config = _blind_boiler_house()
    world = _blind_boiler_world(which=which, running=running)
    plan = decide(config, world)

    expected = Reason.NO_OUTDOOR_TEMPERATURE if which == "buiten" else Reason.NO_INDOOR_TEMPERATURE

    if running:
        left = plan.untouched_for(BOILER)
        assert left is not None, f"{which}: de ketel verdween uit beeld"
        assert left.reason is expected, f"{which}: ketelreden is {left.reason}"
        assert plan.command_for(BOILER) is None, f"{which}: de ketel kreeg toch een commando"
        valve = plan.untouched_for(VALVE)
        assert valve is not None and valve.reason is expected, f"{which}: de kraan meldt {valve}"
    else:
        command = plan.command_for(BOILER)
        assert command is not None, f"{which}: een stilstaande ketel kreeg geen commando"
        assert command.hvac_mode == "off", f"{which}: stilstaande ketel kreeg {command.hvac_mode}"
        assert command.reason is Reason.SATISFIED, (
            f"{which}: stilstaande ketel meldt {command.reason}"
        )
        valve = plan.untouched_for(VALVE)
        assert valve is not None and valve.reason is expected, f"{which}: de kraan meldt {valve}"


def test_the_house_wide_stop_outranks_a_blind_shared_boiler() -> None:
    """De huisbrede stop wint van een dode thermometer, niet andersom.

    Zonder deze volgorde zou een brandende ketel op de huisbrede stoplijst bij
    een kapotte buitensensor tóch blijven draaien, terwijl een open deur hem
    hoort stil te zetten. De openingsstop en de huisbrede stop noemen hun eigen
    reden; de blind-reden is pas daarna aan de beurt.

    The house-wide stop outranks a dead thermometer, not the other way round.
    Without this order a burning boiler on the house-wide stop list would keep
    running on a broken outdoor sensor while an open door should stop it. The
    opening stop and the house-wide stop name their own reason; the blind reason
    only gets a turn after them.
    """
    config = _blind_boiler_house()
    attic = Zone(
        zone_id="zolder",
        name="Zolder",
        indoor_sensor="sensor.zolder",
        sources=(Source("kachel", "climate.zolder_kachel", role=SourceRole.HEAT_ONLY),),
        heat=ModeSettings(target=20.0, start_at=19.0, hysteresis=1.0),
    )
    config = replace(
        config,
        zones=(config.zones[0], attic),
        openings=(Opening("binary_sensor.achterdeur", zone_ids=("zolder",)),),
        house_wide_openings=(BOILER,),
    )
    world = make_world(
        now=datetime(2026, 1, 12, 10, 0),
        outdoor=None,
        indoor={"badkamer": 17.0, "zolder": 17.0},
        climates={
            VALVE: climate("heat", changed_at=datetime(2026, 1, 12, 9, 0)),
            BOILER: climate("heat", changed_at=datetime(2026, 1, 12, 9, 0)),
            "climate.zolder_kachel": climate("off", changed_at=datetime(2026, 1, 12, 9, 0)),
        },
        residents={"danny": awake()},
        openings={
            "binary_sensor.achterdeur": OpeningState(
                open=True, changed_at=datetime(2026, 1, 12, 9, 30)
            )
        },
    )
    plan = decide(config, world)
    command = plan.command_for(BOILER)
    assert command is not None, "de ketel verdween uit beeld"
    assert command.hvac_mode == "off", f"de ketel kreeg {command.hvac_mode}"
    assert command.reason is Reason.OPENING_OPEN_ELSEWHERE, f"ketelreden is {command.reason}"
    assert plan.untouched_for(BOILER) is None, "de ketel werd met rust gelaten"
