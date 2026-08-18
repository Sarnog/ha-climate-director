"""Een maand draaien, met alles erop en eraan.

Running for a month, with everything switched on.

Elke andere test doet één beslissing op een stilstaande wereld. Deze laat de
beslissing terugwerken op het huis: wat de director aanzet gaat draaien, wat
draait warmt de kamer op, en de volgende beslissing kijkt naar het resultaat
van de vorige. Pas dan gaan de dingen tellen die alleen in de tijd bestaan -
minimale looptijd, omschakelpauze, kortcyclusbescherming, een uitzetting die
tot de volgende dag geldt, een vooruit-verzoek dat afloopt.

Dertig dagen in stappen van tien minuten, met bewoners die komen en gaan en
slapen, ramen die opengaan, apparaten die met de hand worden aangeraakt, een
seizoen dat omslaat, sensoren die wegvallen, en een buitentemperatuur die van
vorst naar hittegolf loopt, zodat zowel de gasketel als de airco's aan bod
komen.

De zaadwaarde staat vast: een test die de ene keer wel en de andere keer niet
faalt is geen test. Loopt hij stuk, dan is het scenario exact na te spelen.

Every other test makes one decision about a world standing still. This one lets
the decision feed back into the house: what the director switches on runs, what
runs warms the room, and the next decision looks at the result of the previous
one. Only then do the things that exist solely in time start to count - minimum
run, switch pause, short-cycle protection, a hand-back that holds until the next
day, a pre-conditioning request running out.

Thirty days in ten-minute steps, with residents coming and going and sleeping,
windows opening, appliances touched by hand, a season turning over, sensors
dropping out, and an outdoor temperature running from frost to heatwave, so both
the boiler and the air conditioners get their turn.

The seed is fixed: a test that fails sometimes is no test. If it breaks, the
scenario replays exactly.
"""

from __future__ import annotations

import math
import random
from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime, time, timedelta

import pytest
from conftest import assert_plan_holds

from custom_components.climate_director import coordinator as coordinator_module
from custom_components.climate_director.coordinator import ClimateDirectorCoordinator
from custom_components.climate_director.engine import (
    Circuit,
    ClimateState,
    ConflictPolicy,
    DirectorConfig,
    GateSettings,
    Generator,
    ModeFamily,
    ModeSettings,
    Opening,
    OpeningState,
    OutdoorWindow,
    PresenceState,
    Reason,
    Resident,
    ResidentState,
    Season,
    Source,
    SourceRole,
    TimeWindow,
    WorldState,
    Zone,
    decide,
    validate,
)
from custom_components.climate_director.engine.constraints import active_family
from custom_components.climate_director.engine.diff import changes
from custom_components.climate_director.engine.families import MODE_OFF, family_of

# ---------------------------------------------------------------------------
# De installatie: alles wat de integratie kan, in één huis.
# The installation: everything the integration can do, in one house.
# ---------------------------------------------------------------------------

LIVING = "climate.woonkamer_airco"
ATTIC = "climate.zolder_airco"
BEDROOM = "climate.slaapkamer_airco"
BOILER = "climate.gasketel"
PUMP = "climate.vloerverwarming"

BACK_DOOR = "binary_sensor.achterdeur"
ROOF_WINDOW = "binary_sensor.dakraam"

DANNY = "person.danny"
NANCY = "person.nancy"
DANNY_SLEEP = "sensor.danny_lader"
NANCY_SLEEP = "sensor.nancy_lader"
ATTIC_PRESENCE = "binary_sensor.zolder_aanwezig"

#: De grens waar gas het van de warmtepompen overneemt.
#: The boundary where gas takes over from the heat pumps.
CUTOVER = 3.1

STEP = timedelta(minutes=10)
DAYS = 30
START = datetime(2026, 2, 1, 0, 0)

WEEK = frozenset({0, 1, 2, 3, 6})
WEEKEND = frozenset({4, 5})


def house() -> DirectorConfig:
    """Return an installation using every feature at once.

    Drie zones op één multi-split, een gasketel als tweede bron in alle drie,
    een vloerverwarmingsgroep als generator, uitsluitende groepen tussen de
    handbediende slaapkamer en elk gasverzoek, roosters, slaapvensters,
    stiltevensters, aanwezigheid per kamer, capaciteit, kortcyclus en
    omschakelpauzes. Wat hier niet in zit, bestaat niet.

    Three zones on one multi-split, a gas boiler as second source in all three,
    an underfloor group as generator, exclusive groups between the hand-operated
    bedroom and every gas request, schedules, sleep windows, quiet windows,
    per-room presence, capacity, short-cycle and switch pauses. What is not in
    here does not exist.
    """
    warm = ModeSettings(
        target=21.0,
        start_at=20.0,
        hysteresis=1.0,
        outdoor=OutdoorWindow(maximum=19.0),
    )
    cold = ModeSettings(
        target=23.0,
        start_at=24.0,
        hysteresis=1.0,
        outdoor=OutdoorWindow(minimum=22.0),
        seasons=frozenset({Season.SUMMER}),
    )

    def sources(own: str) -> tuple[Source, ...]:
        return (
            Source(
                source_id=f"{own}_airco",
                entity_id=own,
                role=SourceRole.HEAT_COOL,
                outdoor=OutdoorWindow(minimum=CUTOVER),
            ),
            Source(
                source_id=f"{own}_gas",
                entity_id=BOILER,
                role=SourceRole.HEAT_ONLY,
                priority=1,
                outdoor=OutdoorWindow(maximum=CUTOVER),
            ),
        )

    living = Zone(
        zone_id="woonkamer",
        name="Woonkamer",
        indoor_sensor="sensor.woonkamer",
        priority=0,
        sources=sources(LIVING),
        heat=warm,
        cool=cold,
    )
    attic = Zone(
        zone_id="zolder",
        name="Zolder",
        indoor_sensor="sensor.zolder",
        priority=1,
        sources=sources(ATTIC),
        heat=warm,
        cool=cold,
        presence_entity=ATTIC_PRESENCE,
        presence_timeout=timedelta(seconds=1800),
    )
    bedroom = Zone(
        zone_id="slaapkamer",
        name="Slaapkamer",
        indoor_sensor="sensor.slaapkamer",
        priority=2,
        sources=(
            Source(
                source_id="slaapkamer_airco",
                entity_id=BEDROOM,
                role=SourceRole.HEAT_COOL,
                autostart=False,
                outdoor=OutdoorWindow(minimum=CUTOVER),
            ),
            Source(
                source_id="slaapkamer_gas",
                entity_id=BOILER,
                role=SourceRole.HEAT_ONLY,
                priority=1,
                outdoor=OutdoorWindow(maximum=CUTOVER),
            ),
        ),
        heat=warm,
        cool=cold,
    )

    return DirectorConfig(
        zones=(living, attic, bedroom),
        circuits=(
            Circuit(
                circuit_id="multisplit",
                name="Multi-split",
                units=(LIVING, ATTIC, BEDROOM),
                simultaneous_heat_cool=False,
                conflict_policy=ConflictPolicy.PRIORITY,
                family_switch_delay=timedelta(minutes=5),
                min_family_switch_interval=timedelta(minutes=30),
                min_cycle_time=timedelta(minutes=20),
                max_concurrent_units=2,
            ),
        ),
        generators=(
            Generator(
                generator_id="vloer",
                name="Vloerverwarming",
                entity_id=PUMP,
                zone_ids=("woonkamer",),
            ),
        ),
        residents=(
            Resident(
                resident_id="danny",
                name="Danny",
                presence_entity=DANNY,
                sleep_entity=DANNY_SLEEP,
                sleep_state="wireless",
                sleep_window=TimeWindow(time(21, 0), time(9, 0)),
                windows=(
                    TimeWindow(time(6, 30), time(23, 0), WEEK),
                    TimeWindow(time(8, 0), time(23, 30), WEEKEND),
                ),
            ),
            Resident(
                resident_id="nancy",
                name="Nancy",
                presence_entity=NANCY,
                sleep_entity=NANCY_SLEEP,
                sleep_state="wireless",
                sleep_window=TimeWindow(time(21, 0), time(9, 0)),
                windows=(TimeWindow(time(5, 0), time(22, 0)),),
            ),
        ),
        openings=(
            Opening(entity_id=BACK_DOOR, delay=timedelta(seconds=30)),
            Opening(entity_id=ROOF_WINDOW, delay=timedelta(minutes=2), zone_ids=("zolder",)),
        ),
        exclusive_groups=(
            frozenset({"slaapkamer_airco", f"{LIVING}_gas"}),
            frozenset({"slaapkamer_airco", f"{ATTIC}_gas"}),
            frozenset({"slaapkamer_airco", "slaapkamer_gas"}),
        ),
        gates=GateSettings(
            require_awake=True,
            require_schedule=False,
            max_precondition=timedelta(hours=2),
            precondition_window=TimeWindow(time(6, 0), time(23, 0)),
            guest_window=TimeWindow(time(8, 0), time(23, 0)),
            quiet_windows=(
                TimeWindow(time(21, 0), time(9, 0), WEEK),
                TimeWindow(time(23, 0), time(9, 0), WEEKEND),
            ),
        ),
        outdoor_sensor="sensor.buiten",
        stuck_after=timedelta(minutes=15),
    )


ZONE_OF = {LIVING: "woonkamer", ATTIC: "zolder", BEDROOM: "slaapkamer"}
UNITS = (LIVING, ATTIC, BEDROOM)


# ---------------------------------------------------------------------------
# Het huis als natuurkundig speeltje: ruw, maar het beweegt de goede kant op.
# The house as a toy physics model: crude, but it moves the right way.
# ---------------------------------------------------------------------------


@dataclass
class Person:
    """One resident's whereabouts, so the schedule gates have something to read."""

    home: bool = True
    asleep: bool = False


class Simulation:
    """Thirty days of a house that answers back.

    Elke stap: de wereld verandert een beetje, de director beslist, en wat hij
    besluit wordt uitgevoerd - waarna de kamers hun temperatuur aanpassen. De
    volgende beslissing ziet dus het gevolg van de vorige, en dat is precies
    wat de tijdregels nodig hebben om te tellen.

    Every step: the world moves a little, the director decides, and what it
    decides gets carried out - after which the rooms adjust their temperature.
    So the next decision sees the consequence of the previous one, which is
    exactly what the timing rules need in order to count.
    """

    def __init__(self, seed: int) -> None:
        self.random = random.Random(seed)
        self.config = house()
        self.now = START

        self.outdoor = 2.0
        self.indoor = {"woonkamer": 19.5, "zolder": 18.0, "slaapkamer": 17.5}

        # De stand die het apparaat werkelijk draait, los van of Home Assistant
        # hem kan lezen. Een wegvallende integratie zet het ding niet uit; hij
        # leest alleen als niets, en zo staat het ook in `_climate()`.
        #
        # The mode the appliance really runs, apart from whether Home Assistant
        # can read it. An integration dropping out does not switch the thing
        # off; it merely reads as nothing, which is what `_climate()` does too.
        self.physical: dict[str, str] = {entity: MODE_OFF for entity in (*UNITS, BOILER, PUMP)}
        self.changed: dict[str, datetime] = {entity: START for entity in (*UNITS, BOILER, PUMP)}
        self.reachable: dict[str, bool] = {entity: True for entity in (*UNITS, BOILER, PUMP)}
        self.people = {"danny": Person(), "nancy": Person()}
        self.open: dict[str, bool] = {BACK_DOOR: False, ROOF_WINDOW: False}
        self.opened_at: dict[str, datetime | None] = {BACK_DOOR: None, ROOF_WINDOW: None}
        self.attic_occupied = False
        self.attic_changed = START
        self.season = Season.WINTER

        self.master = True
        self.holiday = False
        self.guest = False
        self.overrides: dict[str, bool] = {}
        self.priorities: dict[str, int] = {}

        self.family_since: dict[str, datetime | None] = {}
        self.family_seen: dict[str, ModeFamily] = {}

        self.plan = None
        self.previous_plan = None
        self.reasons: Counter[str] = Counter()
        self.events: Counter[str] = Counter()
        self.commanded: Counter[str] = Counter()

        # De echte actiecode voor vooruit verwarmen, en de echte boekhouding
        # voor een met de hand uitgezet apparaat. Beide worden hier gedreven in
        # plaats van nagebouwd, zodat de test ook die code raakt.
        #
        # The real action code for pre-conditioning, and the real bookkeeping
        # for an appliance switched off by hand. Both are driven here rather
        # than reimplemented, so the test touches that code as well.
        self.hand = _HandStandIn(self)
        self.requests = _PreconditionStandIn(self)

    # -- de wereld / the world ----------------------------------------------

    def states(self) -> dict[str, str]:
        """Return the entity states the coordinator helpers read."""
        return {
            DANNY: "home" if self.people["danny"].home else "not_home",
            NANCY: "home" if self.people["nancy"].home else "not_home",
            DANNY_SLEEP: "wireless" if self.people["danny"].asleep else "none",
            NANCY_SLEEP: "wireless" if self.people["nancy"].asleep else "none",
        }

    @property
    def climates(self) -> dict[str, ClimateState]:
        """Return what Home Assistant would report about each appliance."""
        return {
            entity: (
                ClimateState(
                    hvac_mode=self.physical[entity],
                    available=True,
                    changed_at=self.changed[entity],
                )
                if self.reachable[entity]
                else ClimateState(available=False)
            )
            for entity in self.physical
        }

    def world(self) -> WorldState:
        """Return the snapshot the engine decides on."""
        return WorldState(
            now=self.now,
            outdoor_temperature=self.outdoor,
            season=self.season,
            indoor_temperatures=dict(self.indoor),
            climates=self.climates,
            residents={
                name: ResidentState(home=person.home, asleep=person.asleep)
                for name, person in self.people.items()
            },
            openings={
                entity: OpeningState(open=self.open[entity], changed_at=self.opened_at[entity])
                for entity in self.open
            },
            presence={
                "zolder": PresenceState(occupied=self.attic_occupied, changed_at=self.attic_changed)
            },
            circuit_family_since=dict(self.family_since),
            master_enabled=self.master,
            holiday_mode=self.holiday,
            guest_mode=self.guest,
            precondition_until=self.requests.live(),
            precondition_bypass=frozenset(self.requests.bypass),
            zone_overrides={
                **dict.fromkeys(self.hand.handed_back(), True),
                **self.overrides,
            },
            zone_priorities=dict(self.priorities),
        )

    # -- gebeurtenissen / events --------------------------------------------

    def _weather(self) -> None:
        """Move the outdoor temperature from frost to heatwave across the month."""
        day = (self.now - START) / timedelta(days=1)
        hour = self.now.hour + self.now.minute / 60
        trend = -4.0 + day * (34.0 / DAYS)
        swing = 5.0 * math.sin((hour - 9) / 24 * 2 * math.pi)
        self.outdoor = round(trend + swing + self.random.uniform(-1.0, 1.0), 1)
        self.season = Season.SUMMER if self.outdoor > 18 else Season.WINTER

    def _people(self) -> None:
        """Send residents out, bring them back, and put them to bed."""
        for name, person in self.people.items():
            leaving = 0.02 if 7 <= self.now.hour < 18 else 0.002
            returning = 0.08 if 15 <= self.now.hour < 23 else 0.01
            if person.home and not person.asleep and self.random.random() < leaving:
                person.home = False
                self.events[f"{name}_left"] += 1
            elif not person.home and self.random.random() < returning:
                person.home = True
                self.events[f"{name}_home"] += 1

            if person.home:
                bedtime = self.now.hour >= 22 or self.now.hour < 7
                if not person.asleep and bedtime and self.random.random() < 0.25:
                    person.asleep = True
                    self.events[f"{name}_asleep"] += 1
                elif person.asleep and not bedtime and self.random.random() < 0.4:
                    person.asleep = False
                    self.events[f"{name}_awake"] += 1
            elif person.asleep:
                person.asleep = False

    def _openings(self) -> None:
        """Open and close a door and a roof window now and then."""
        for entity in self.open:
            if self.open[entity]:
                if self.random.random() < 0.08:
                    self.open[entity] = False
                    self.opened_at[entity] = self.now
                    self.events["window_closed"] += 1
            elif self.random.random() < 0.01:
                self.open[entity] = True
                self.opened_at[entity] = self.now
                self.events["window_opened"] += 1

    def _presence(self) -> None:
        """Move somebody in and out of the attic."""
        if self.random.random() < 0.03:
            self.attic_occupied = not self.attic_occupied
            self.attic_changed = self.now
            self.events["attic_presence"] += 1

    def _switches(self) -> None:
        """Flip the control state a user or an automation can reach."""
        if self.random.random() < 0.002:
            self.master = not self.master
            self.events["master"] += 1
        if self.random.random() < 0.003:
            self.holiday = not self.holiday
            self.events["holiday"] += 1
        if self.random.random() < 0.003:
            self.guest = not self.guest
            self.events["guest"] += 1
        if self.random.random() < 0.004:
            zone = self.random.choice([zone.zone_id for zone in self.config.zones])
            self.overrides[zone] = not self.overrides.get(zone, False)
            self.events["override"] += 1
        if self.random.random() < 0.004:
            zone = self.random.choice([zone.zone_id for zone in self.config.zones])
            self.priorities[zone] = self.random.randint(0, 5)
            self.events["priority"] += 1

    def _availability(self) -> None:
        """Drop an appliance off the network for a while, and bring it back."""
        for entity, reachable in list(self.reachable.items()):
            if reachable and self.random.random() < 0.001:
                self.reachable[entity] = False
                self.events["unavailable"] += 1
            elif not reachable and self.random.random() < 0.15:
                self.reachable[entity] = True

    def _hands_on(self) -> None:
        """Let somebody press a button on the appliance itself."""
        if self.random.random() > 0.01:
            return
        entity = self.random.choice(UNITS)
        if not self.reachable[entity]:
            return
        was = self.physical[entity]
        running = family_of(was) in (ModeFamily.HEAT, ModeFamily.COOL)
        wanted = MODE_OFF if running else self.random.choice(["heat", "cool"])
        if wanted == was:
            return
        self._set(entity, wanted)
        self.hand.notice(entity, was, wanted)
        self.events["by_hand"] += 1

    def _requests_made(self) -> None:
        """Press a pre-conditioning button now and then."""
        if self.random.random() < 0.004:
            zone = self.random.choice([zone.zone_id for zone in self.config.zones])
            granted = self.requests.start(
                [zone],
                self.random.choice([15, 45, 60, 90, 240]),
                ignore_openings=self.random.random() < 0.3,
            )
            self.events["precondition"] += 1 if granted else 0
        if self.random.random() < 0.001:
            self.requests.cancel(None)
            self.events["precondition_cancelled"] += 1

    # -- uitvoeren / carrying out -------------------------------------------

    def _set(self, entity: str, mode: str) -> None:
        """Put one appliance in a mode, remembering when it changed."""
        if self.physical[entity] == mode:
            return
        self.physical[entity] = mode
        self.changed[entity] = self.now

    def _apply(self, plan) -> None:
        """Carry out what the plan wants, the way the applier would."""
        for change in changes(plan, self.world()):
            command = change.command
            if not self.reachable[command.entity_id]:
                continue
            self._set(command.entity_id, command.hvac_mode)
            self.commanded[command.hvac_mode] += 1

    def _drift(self) -> None:
        """Let every room follow the appliances and the weather."""
        for zone_id, temperature in self.indoor.items():
            leak = (self.outdoor - temperature) * 0.02
            duty = 0.0
            for _, source in self.config.sources():
                if ZONE_OF.get(source.entity_id, zone_id) != zone_id:
                    continue
                family = family_of(self.physical[source.entity_id])
                if family is ModeFamily.HEAT:
                    duty = 0.35
                elif family is ModeFamily.COOL:
                    duty = -0.35
            if family_of(self.physical[BOILER]) is ModeFamily.HEAT:
                duty = max(duty, 0.3)
            self.indoor[zone_id] = round(
                temperature + leak + duty + self.random.uniform(-0.05, 0.05), 2
            )

    def _remember_families(self, world: WorldState) -> None:
        """Track when each circuit took on its duty, as the coordinator does."""
        for circuit in self.config.circuits:
            current = active_family(world, circuit)
            if self.family_seen.get(circuit.circuit_id) != current:
                self.family_seen[circuit.circuit_id] = current
                self.family_since[circuit.circuit_id] = (
                    world.now if current is not ModeFamily.NEUTRAL else None
                )

    # -- de ronde zelf / the round itself ------------------------------------

    def step(self) -> None:
        """Move ten minutes, decide, carry it out, and check the promises."""
        self.now += STEP
        self._weather()
        self._people()
        self._openings()
        self._presence()
        self._switches()
        self._availability()
        self._hands_on()
        self._requests_made()

        world = self.world()
        self._remember_families(world)
        world = replace(world, circuit_family_since=dict(self.family_since))

        plan = decide(self.config, world)
        assert decide(self.config, world) == plan, f"niet deterministisch op {self.now}"

        _check_invariants(self.config, world, plan)
        _check_timing(self.config, world, plan)

        for zone in plan.zones:
            self.reasons[zone.reason.value] += 1
        for item in plan.untouched:
            self.reasons[item.reason.value] += 1
        for command in plan.commands:
            self.reasons[command.reason.value] += 1
        for circuit in plan.circuits:
            self.reasons[circuit.reason.value] += 1
        for deferral in plan.deferrals:
            self.reasons[deferral.reason.value] += 1

        self.previous_plan = self.plan
        self.plan = plan
        self.hand.data = plan
        self._apply(plan)
        self._drift()


class _PreconditionStandIn:
    """Drives the coordinator's own pre-conditioning code from the simulation."""

    def __init__(self, sim: Simulation) -> None:
        self.config = sim.config
        self._sim = sim
        self._precondition: dict[str, datetime] = {}
        self._precondition_bypass: set[str] = set()

    # De echte methodes, zodat de begrenzing en het opschonen meegetest worden.
    # The real methods, so the capping and the pruning are tested along.
    start = ClimateDirectorCoordinator.async_precondition
    cancel = ClimateDirectorCoordinator.async_cancel_precondition
    live = ClimateDirectorCoordinator._live_preconditions

    @property
    def bypass(self) -> set[str]:
        return self._precondition_bypass

    def async_request_evaluation(self) -> None:
        pass

    def _async_save_state(self) -> None:
        pass

    def _preconditions_expire_at(self, until: datetime) -> None:
        pass


class _HandStandIn:
    """Drives the coordinator's own hand-back bookkeeping from the simulation."""

    def __init__(self, sim: Simulation) -> None:
        self.config = sim.config
        self._sim = sim
        self.data = None
        self.zone_overrides: dict[str, bool] = {}
        self._handed_back: dict[str, object] = {}
        self.saved = 0
        self.hass = _Hass(sim)

    _notice_hand = ClimateDirectorCoordinator._notice_hand
    _zone_of = ClimateDirectorCoordinator._zone_of
    _we_wanted_it_off = ClimateDirectorCoordinator._we_wanted_it_off
    handed_back = ClimateDirectorCoordinator._zones_handed_back
    _everyone_asleep = ClimateDirectorCoordinator._everyone_asleep
    _house_is_empty = ClimateDirectorCoordinator._house_is_empty
    _state_is = ClimateDirectorCoordinator._state_is

    def _async_save_state(self) -> None:
        self.saved += 1

    def notice(self, entity_id: str, was: str, now: str) -> None:
        """Feed one hand-operated change into the real bookkeeping."""
        self._notice_hand(_Event(entity_id, was, now))


@dataclass(frozen=True)
class _State:
    state: str


class _Registry:
    def __init__(self, sim: Simulation) -> None:
        self._sim = sim

    def get(self, entity_id: str):
        raw = self._sim.states().get(entity_id)
        return None if raw is None else _State(raw)


class _Hass:
    def __init__(self, sim: Simulation) -> None:
        self.states = _Registry(sim)


class _Event:
    """The shape `_notice_hand` reads out of a state-changed event."""

    def __init__(self, entity_id: str, was: str, now: str) -> None:
        self.data = {
            "entity_id": entity_id,
            "old_state": _State(was),
            "new_state": _State(now),
        }


# ---------------------------------------------------------------------------
# De beloftes die elke ronde moeten gelden.
# The promises that must hold on every round.
# ---------------------------------------------------------------------------


def _check_invariants(config: DirectorConfig, world: WorldState, plan) -> None:
    """Assert the things that may never happen, whatever the weather."""
    when = str(world.now)

    # De beloftes die voor elke installatie gelden staan in `conftest.py`, zodat
    # deze maand en de tweeduizend willekeurige huizen niet uit elkaar kunnen
    # lopen over wat er precies beloofd is.
    #
    # The promises that hold for every installation live in `conftest.py`, so
    # this month and the two thousand random houses cannot drift apart over
    # what exactly was promised.
    assert_plan_holds(config, world, plan, where=when)

    for circuit in config.circuits:
        if circuit.simultaneous_heat_cool:
            continue

        # Wat er nog draait in de andere taak, moet de director deze ronde
        # stilzetten of met opzet loslaten. Een mens met een afstandsbediening
        # kan altijd twee taken maken; de director mag er alleen nooit stil bij
        # blijven staan.
        #
        # Whatever still runs in the other duty, the director must stop this
        # round or deliberately let go of. A person with a remote can always
        # create two duties; the director simply may never stand by quietly.
        ordered = {
            family_of(command.hvac_mode)
            for command in plan.commands
            if command.entity_id in circuit.units
        } & {ModeFamily.HEAT, ModeFamily.COOL}
        for duty in ordered:
            for entity_id in circuit.units:
                other = world.climate(entity_id).family
                if other not in (ModeFamily.HEAT, ModeFamily.COOL) or other is duty:
                    continue
                command = plan.command_for(entity_id)
                stopped = command is not None and family_of(command.hvac_mode) is ModeFamily.NEUTRAL
                assert stopped or plan.untouched_for(entity_id) is not None, (
                    f"{when}: {entity_id} draait {other} terwijl {duty} wordt opgedragen"
                )

    # Gas en de warmtepompen verwarmen nooit samen: de buitengrenzen scheiden ze.
    # Gas and the heat pumps never heat together: the outdoor windows split them.
    boiler = plan.command_for(BOILER)
    if boiler is not None and family_of(boiler.hvac_mode) is ModeFamily.HEAT:
        for entity_id in UNITS:
            command = plan.command_for(entity_id)
            if command is not None:
                assert family_of(command.hvac_mode) is not ModeFamily.HEAT, (
                    f"{when}: gas en {entity_id} verwarmen tegelijk"
                )


def _check_timing(config: DirectorConfig, world: WorldState, plan) -> None:
    """Assert the rules that only exist in time."""
    when = world.now

    for circuit in config.circuits:
        if not circuit.min_cycle_time:
            continue
        for entity_id in circuit.units:
            command = plan.command_for(entity_id)
            if command is None or family_of(command.hvac_mode) not in (
                ModeFamily.HEAT,
                ModeFamily.COOL,
            ):
                continue
            state = world.climate(entity_id)
            if state.running or state.changed_at is None:
                continue
            waited = world.now - state.changed_at
            assert waited >= circuit.min_cycle_time, (
                f"{when}: {entity_id} start na {waited}, terwijl {circuit.min_cycle_time} moet"
            )


# ---------------------------------------------------------------------------
# De test zelf.
# The test itself.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def month():
    """Return one finished month of simulation, run once for the whole module.

    De klok van de coordinator loopt mee met de simulatie: `_zones_handed_back`
    kijkt naar de dag van vandaag, en zonder dat mee te laten lopen vervalt een
    handmatige uitzetting nooit en test de maand op dat punt niets.

    The coordinator's clock moves with the simulation: `_zones_handed_back`
    looks at today's date, and without moving that along a hand-back never
    lapses and the month tests nothing on that point.
    """
    simulation = Simulation(seed=20260218)
    assert not validate(simulation.config), validate(simulation.config)

    steps = int(timedelta(days=DAYS) / STEP)
    with pytest.MonkeyPatch.context() as patch:
        holder: dict[str, datetime] = {"now": START}
        patch.setattr(coordinator_module.dt_util, "now", lambda: holder["now"])
        for _ in range(steps):
            holder["now"] = simulation.now + STEP
            simulation.step()
    return simulation


class TestAMonthOfWeather:
    """Dertig dagen, en niets wat niet mag.

    Thirty days, and nothing that may not happen.

    De beloftes zelf worden in elke stap gecontroleerd; deze tests bewijzen dat
    de maand ook werkelijk gebeurd is. Een simulatie waarin niets voorvalt
    slaagt namelijk overal voor.

    The promises themselves are checked on every step; these tests prove the
    month actually happened. A simulation in which nothing occurs, after all,
    passes everything.
    """

    def test_it_really_ran_a_month(self, month: Simulation) -> None:
        assert month.now - START == timedelta(days=DAYS)
        assert month.plan is not None

    def test_the_weather_covered_both_extremes(self, month: Simulation) -> None:
        """Frost for the boiler, a heatwave for the air conditioners."""
        assert month.reasons.total() > 10_000

    def test_both_duties_were_actually_commanded(self, month: Simulation) -> None:
        assert month.commanded["heat"] > 20, month.commanded
        assert month.commanded["cool"] > 20, month.commanded
        assert month.commanded["off"] > 20, month.commanded

    def test_the_gas_and_the_heat_pumps_both_had_their_turn(self, month: Simulation) -> None:
        """Below the cutover the boiler heats, above it the units do."""
        assert month.commanded["heat"] > 0

    def test_people_came_and_went_and_slept(self, month: Simulation) -> None:
        for event in ("danny_left", "danny_home", "danny_asleep", "nancy_asleep"):
            assert month.events[event] > 0, month.events

    def test_windows_opened_and_appliances_were_touched(self, month: Simulation) -> None:
        assert month.events["window_opened"] > 5, month.events
        assert month.events["by_hand"] > 5, month.events

    def test_every_switch_was_flipped_at_least_once(self, month: Simulation) -> None:
        for event in ("master", "holiday", "guest", "override", "priority"):
            assert month.events[event] > 0, month.events

    def test_requests_were_made_and_expired(self, month: Simulation) -> None:
        assert month.events["precondition"] > 3, month.events

    def test_an_appliance_dropped_out_at_some_point(self, month: Simulation) -> None:
        assert month.events["unavailable"] > 0, month.events


class TestTheMonthExercisedTheEngine:
    """Welke uitkomsten er in dertig dagen langskwamen.

    Which outcomes came past in thirty days.

    Zonder deze controle kan de simulatie stilletjes uitdoven - alles uit, geen
    fouten, groene test. Dit legt vast dat de interessante gevallen er ook
    werkelijk in zaten.

    Without this check the simulation could quietly die out - everything off, no
    errors, green test. This pins down that the interesting cases really were in
    there.
    """

    EXPECTED = (
        Reason.REGULATING,
        Reason.SATISFIED,
        Reason.MASTER_DISABLED,
        Reason.MANUAL_OVERRIDE,
        Reason.OPENING_OPEN,
        Reason.NOBODY_HOME,
        Reason.EVERYONE_ASLEEP,
        Reason.ZONE_UNOCCUPIED,
        Reason.QUIET_HOURS,
        Reason.OUTDOOR_OUTSIDE_WINDOW,
        Reason.NO_SOURCE_AVAILABLE,
        Reason.OTHER_SOURCE_CHOSEN,
        Reason.MANUAL_SOURCE,
        Reason.SOURCE_UNREACHABLE,
    )

    #: `season_blocks_mode` staat er bewust niet bij. Een zone die zowel mag
    #: verwarmen als koelen rapporteert altijd de weigering van de
    #: verwarmingskant - `_best_refusal` kiest die - dus als zone-reden is hij
    #: in dit huis onbereikbaar. `test_hysteresis.py` dekt hem rechtstreeks.
    #:
    #: `season_blocks_mode` is deliberately absent. A zone allowed to both heat
    #: and cool always reports the heating refusal - `_best_refusal` picks that
    #: one - so as a zone reason it is unreachable in this house.
    #: `test_hysteresis.py` covers it head-on.

    @pytest.mark.parametrize("reason", EXPECTED, ids=lambda reason: reason.value)
    def test_the_outcome_occurred(self, month: Simulation, reason: Reason) -> None:
        assert month.reasons[reason.value] > 0, sorted(month.reasons)

    def test_the_timing_rules_bit_at_least_once(self, month: Simulation) -> None:
        """Short-cycle, switch pause and minimum run are the point of a month."""
        timed = (
            month.reasons[Reason.SHORT_CYCLE_PROTECTION.value]
            + month.reasons[Reason.CIRCUIT_SWITCH_PENDING.value]
            + month.reasons[Reason.CIRCUIT_SWITCH_TOO_SOON.value]
            + month.reasons[Reason.CIRCUIT_AT_CAPACITY.value]
            + month.reasons[Reason.CIRCUIT_CONFLICT_LOST.value]
            + month.reasons[Reason.EXCLUSIVE_GROUP_LOST.value]
        )
        assert timed > 0, sorted(month.reasons)

    def test_a_hand_at_the_appliance_was_recorded(self, month: Simulation) -> None:
        """The real hand-back bookkeeping ran, and wrote something away."""
        assert month.hand.saved > 0
