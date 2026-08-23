"""Een huis dat terugpraat: de gedeelde motor onder de maandsimulaties.

A house that answers back: the shared engine under the month simulations.

Elke gewone test doet één beslissing op een stilstaande wereld. Hier werkt de
beslissing terug op het huis: wat de director aanzet gaat draaien, wat draait
warmt de kamer op, en de volgende ronde kijkt naar het resultaat van de vorige.
Pas dan tellen de regels die alleen in de tijd bestaan - minimale looptijd,
omschakelpauze, kortcyclusbescherming, een uitzetting die tot de volgende dag
geldt, een vooruit-verzoek dat afloopt.

Deze module is geen test maar het gereedschap eronder. Wat een scenario nog moet
aanleveren is de installatie, het weer en waar de kamers beginnen; al het
andere - welke apparaten er zijn, wie er woont, welke ramen er zijn - wordt uit
de configuratie zelf afgeleid, zodat er niets uit de pas kan gaan lopen.

Every ordinary test makes one decision about a world standing still. Here the
decision feeds back into the house: what the director switches on runs, what
runs warms the room, and the next round looks at the result of the previous one.
Only then do the rules that exist solely in time start to count - minimum run,
switch pause, short-cycle protection, a hand-back that holds until the next day,
a pre-conditioning request running out.

This module is not a test but the tooling under one. What a scenario still has
to supply is the installation, the weather and where the rooms start; everything
else - which appliances exist, who lives there, which windows there are - is
derived from the configuration itself, so nothing can drift apart.
"""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta

from conftest import assert_plan_holds

from custom_components.climate_director.coordinator import ClimateDirectorCoordinator
from custom_components.climate_director.engine import (
    ClimateState,
    DirectorConfig,
    ModeFamily,
    OpeningState,
    PresenceState,
    ResidentState,
    Season,
    WorldState,
    decide,
)
from custom_components.climate_director.engine.constraints import active_family
from custom_components.climate_director.engine.diff import changes
from custom_components.climate_director.engine.families import MODE_OFF, family_of

STEP = timedelta(minutes=10)


@dataclass(frozen=True)
class Profile:
    """How often the people and the house do something, per ten-minute step."""

    leaving: float = 0.02
    returning: float = 0.08
    turning_in: float = 0.25
    getting_up: float = 0.40
    window_opens: float = 0.01
    window_closes: float = 0.08
    presence_flips: float = 0.03
    #: Aan- en uitgaan hebben elk hun eigen kans, want een hoofdschakelaar die
    #: net zo vaak aan- als uitgaat staat de halve maand uit. Uitzonderingen
    #: horen kort te duren; een vakantie mag dagen duren.
    #:
    #: Switching on and off each have their own chance, since a master switch
    #: that goes on as often as off stands off half the month. Exceptions should
    #: be short; a holiday may last days.
    master: float = 0.002
    master_back: float = 0.12
    holiday: float = 0.002
    holiday_back: float = 0.004
    guest: float = 0.003
    guest_back: float = 0.01
    override: float = 0.004
    override_back: float = 0.06
    priority: float = 0.004
    drops_out: float = 0.001
    comes_back: float = 0.15
    by_hand: float = 0.01
    requests: float = 0.004
    cancels: float = 0.001


@dataclass(frozen=True)
class Scenario:
    """One house, one climate, one month."""

    name: str
    config: DirectorConfig
    start: datetime
    start_indoor: dict[str, float]
    weather: Callable[[datetime, random.Random], tuple[float, Season]]
    profile: Profile = field(default_factory=Profile)
    days: int = 30

    #: Een extra belofte die alleen voor dit huis geldt, elke ronde nagelopen.
    #: Denk aan "de ketel stookt nooit als het buiten warm is".
    #:
    #: An extra promise that holds for this house alone, checked every round.
    #: Think "the boiler never fires while it is warm outside".
    extra_check: Callable[[DirectorConfig, WorldState, object, str], None] | None = None

    #: Hoe hard een kamer opwarmt of afkoelt terwijl een apparaat draait, per
    #: stap van tien minuten. Een gedeelde ketel doet het wat rustiger aan.
    #:
    #: How fast a room warms or cools while an appliance runs, per ten-minute
    #: step. A shared boiler goes about it a little more gently.
    duty_rate: float = 0.35
    boiler_rate: float = 0.30
    leak_rate: float = 0.02


class Simulation:
    """One scenario, stepped ten minutes at a time, checking itself as it goes."""

    def __init__(self, scenario: Scenario, seed: int) -> None:
        """Set the house up on the first minute of its month."""
        self.scenario = scenario
        self.config = scenario.config
        self.random = random.Random(seed)
        self.now = scenario.start

        self.units = tuple(
            dict.fromkeys(
                source.entity_id for _, source in self.config.sources() if source.entity_id
            )
        )
        self.appliances = tuple(
            dict.fromkeys((*self.units, *(item.entity_id for item in self.config.generators)))
        )
        self.openings = tuple(opening.entity_id for opening in self.config.openings)
        self.presence_zones = tuple(
            zone.zone_id for zone in self.config.zones if zone.presence_entity
        )

        self.outdoor, self.season = scenario.weather(self.now, self.random)
        self.indoor = dict(scenario.start_indoor)

        self.physical = dict.fromkeys(self.appliances, MODE_OFF)
        self.changed = dict.fromkeys(self.appliances, self.now)
        self.reachable = dict.fromkeys(self.appliances, True)

        self.people = {resident.resident_id: [True, False] for resident in self.config.residents}
        self.open = dict.fromkeys(self.openings, False)
        self.opened_at: dict[str, datetime | None] = dict.fromkeys(self.openings, None)
        self.occupied = dict.fromkeys(self.presence_zones, False)
        self.occupied_at = dict.fromkeys(self.presence_zones, self.now)

        self.master = True
        self.holiday = False
        self.guest = False
        self.overrides: dict[str, bool] = {}
        self.priorities: dict[str, int] = {}

        self.family_since: dict[str, datetime | None] = {}
        self.family_seen: dict[str, ModeFamily] = {}

        self.plan = None
        self.reasons: Counter[str] = Counter()
        self.events: Counter[str] = Counter()
        self.commanded: Counter[str] = Counter()
        self.duty_by_month: Counter[tuple[int, str]] = Counter()
        self.fallbacks = 0

        # De echte actiecode en de echte boekhouding, gedreven in plaats van
        # nagebouwd, zodat de maand ook díe code raakt.
        #
        # The real action code and the real bookkeeping, driven rather than
        # reimplemented, so the month touches that code as well.
        self.hand = _HandStandIn(self)
        self.requests = _PreconditionStandIn(self)

    # -- de wereld / the world ----------------------------------------------

    def states(self) -> dict[str, str]:
        """Return the entity states the coordinator's own helpers read."""
        found: dict[str, str] = {}
        for resident in self.config.residents:
            home, asleep = self.people[resident.resident_id]
            if resident.presence_entity:
                found[resident.presence_entity] = "home" if home else "not_home"
            if resident.sleep_entity:
                found[resident.sleep_entity] = resident.sleep_state if asleep else "none"
        return found

    @property
    def climates(self) -> dict[str, ClimateState]:
        """Return what Home Assistant would report about each appliance.

        Een apparaat dat wegvalt leest als niets - precies zoals `_climate()`
        het opbouwt - terwijl het fysiek gewoon doordraait.

        An appliance that drops out reads as nothing - exactly as `_climate()`
        builds it - while it physically keeps running.
        """
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
            for entity in self.appliances
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
                resident_id: ResidentState(home=home, asleep=asleep)
                for resident_id, (home, asleep) in self.people.items()
            },
            openings={
                entity: OpeningState(open=self.open[entity], changed_at=self.opened_at[entity])
                for entity in self.openings
            },
            presence={
                zone_id: PresenceState(
                    occupied=self.occupied[zone_id], changed_at=self.occupied_at[zone_id]
                )
                for zone_id in self.presence_zones
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

    def _people_move(self) -> None:
        """Send residents out, bring them back, and put them to bed."""
        chance = self.scenario.profile
        for resident_id, state in self.people.items():
            home, asleep = state
            leaving = chance.leaving if 7 <= self.now.hour < 18 else chance.leaving / 10
            returning = chance.returning if 15 <= self.now.hour < 23 else chance.returning / 8

            if home and not asleep and self.random.random() < leaving:
                home = False
                self.events[f"{resident_id}_left"] += 1
            elif not home and self.random.random() < returning:
                home = True
                self.events[f"{resident_id}_home"] += 1

            if home:
                bedtime = self.now.hour >= 22 or self.now.hour < 7
                if not asleep and bedtime and self.random.random() < chance.turning_in:
                    asleep = True
                    self.events[f"{resident_id}_asleep"] += 1
                elif asleep and not bedtime and self.random.random() < chance.getting_up:
                    asleep = False
                    self.events[f"{resident_id}_awake"] += 1
            else:
                asleep = False

            state[0], state[1] = home, asleep

    def _openings_move(self) -> None:
        """Open and close doors and windows now and then."""
        chance = self.scenario.profile
        for entity in self.openings:
            if self.open[entity]:
                if self.random.random() < chance.window_closes:
                    self.open[entity] = False
                    self.opened_at[entity] = self.now
                    self.events["window_closed"] += 1
            elif self.random.random() < chance.window_opens:
                self.open[entity] = True
                self.opened_at[entity] = self.now
                self.events["window_opened"] += 1

    def _presence_moves(self) -> None:
        """Move somebody in and out of the rooms that watch for it."""
        for zone_id in self.presence_zones:
            if self.random.random() < self.scenario.profile.presence_flips:
                self.occupied[zone_id] = not self.occupied[zone_id]
                self.occupied_at[zone_id] = self.now
                self.events["presence"] += 1

    def _switches_flip(self) -> None:
        """Flip the control state a user or an automation can reach."""
        chance = self.scenario.profile
        zones = [zone.zone_id for zone in self.config.zones]
        if self.random.random() < (chance.master_back if not self.master else chance.master):
            self.master = not self.master
            self.events["master"] += 1
        if self.random.random() < (chance.holiday_back if self.holiday else chance.holiday):
            self.holiday = not self.holiday
            self.events["holiday"] += 1
        if self.random.random() < (chance.guest_back if self.guest else chance.guest):
            self.guest = not self.guest
            self.events["guest"] += 1
        if zones:
            standing = [zone for zone, on in self.overrides.items() if on]
            if standing and self.random.random() < chance.override_back:
                self.overrides[self.random.choice(standing)] = False
                self.events["override"] += 1
            elif self.random.random() < chance.override:
                self.overrides[self.random.choice(zones)] = True
                self.events["override"] += 1
        if zones and self.random.random() < chance.priority:
            self.priorities[self.random.choice(zones)] = self.random.randrange(0, 5)
            self.events["priority"] += 1

    def _network_drops(self) -> None:
        """Drop an appliance off the network for a while, and bring it back."""
        chance = self.scenario.profile
        for entity, reachable in list(self.reachable.items()):
            if reachable and self.random.random() < chance.drops_out:
                self.reachable[entity] = False
                self.events["unavailable"] += 1
            elif not reachable and self.random.random() < chance.comes_back:
                self.reachable[entity] = True

    def _hands_on(self) -> None:
        """Let somebody press a button on the appliance itself.

        Alleen standen die het apparaat werkelijk kent: een radiatorknop die
        alleen kan verwarmen biedt "koelen" niet aan, dus die stand kan een hand
        er ook niet op zetten.

        Only modes the appliance really has: a radiator valve that can only heat
        does not offer "cool", so no hand can put it there either.
        """
        if not self.units or self.random.random() > self.scenario.profile.by_hand:
            return
        entity = self.random.choice(self.units)
        if not self.reachable[entity]:
            return
        was = self.physical[entity]
        running = family_of(was) in (ModeFamily.HEAT, ModeFamily.COOL)
        wanted = MODE_OFF if running else self.random.choice(self._modes_of(entity))
        if wanted == was:
            return
        self._set(entity, wanted)
        self.hand.notice(entity, was, wanted)
        self.events["by_hand"] += 1

    def _modes_of(self, entity_id: str) -> list[str]:
        """Return the duties this appliance can actually be put in."""
        modes: list[str] = []
        for _, source in self.config.sources():
            if source.entity_id != entity_id:
                continue
            if source.supports(ModeFamily.HEAT):
                modes.append("heat")
            if source.supports(ModeFamily.COOL):
                modes.append("cool")
        return sorted(set(modes)) or [MODE_OFF]

    def _requests_made(self) -> None:
        """Press a pre-conditioning button now and then, and cancel one now and then."""
        chance = self.scenario.profile
        zones = [zone.zone_id for zone in self.config.zones]
        if zones and self.random.random() < chance.requests:
            granted = self.requests.start(
                [self.random.choice(zones)],
                self.random.choice([15, 45, 60, 90, 240]),
                ignore_openings=self.random.random() < 0.3,
            )
            if granted:
                self.events["precondition"] += 1
        if self.random.random() < chance.cancels:
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
            if not self.reachable.get(command.entity_id, False):
                continue
            self._set(command.entity_id, command.hvac_mode)
            self.commanded[command.hvac_mode] += 1
            self.duty_by_month[(self.now.month, command.hvac_mode)] += 1

    def _drift(self) -> None:
        """Let every room follow its appliances and the weather."""
        scenario = self.scenario
        for zone in self.config.zones:
            temperature = self.indoor.get(zone.zone_id)
            if temperature is None:
                continue

            duty = 0.0
            for source in zone.sources:
                family = family_of(self.physical.get(source.entity_id, MODE_OFF))
                if family is ModeFamily.HEAT:
                    duty = max(duty, scenario.duty_rate)
                elif family is ModeFamily.COOL:
                    duty = min(duty, -scenario.duty_rate)
            for item in self.config.generators:
                if (
                    zone.zone_id in item.zone_ids
                    and family_of(self.physical.get(item.entity_id, MODE_OFF)) is ModeFamily.HEAT
                ):
                    duty = max(duty, scenario.boiler_rate)

            leak = (self.outdoor - temperature) * scenario.leak_rate
            self.indoor[zone.zone_id] = round(
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
        self.outdoor, self.season = self.scenario.weather(self.now, self.random)
        self._people_move()
        self._openings_move()
        self._presence_moves()
        self._switches_flip()
        self._network_drops()
        self._hands_on()
        self._requests_made()

        world = self.world()
        self._remember_families(world)
        world = replace(world, circuit_family_since=dict(self.family_since))

        plan = decide(self.config, world)
        assert decide(self.config, world) == plan, f"niet deterministisch op {self.now}"

        where = f"{self.scenario.name} {self.now}"
        assert_plan_holds(self.config, world, plan, where=where)
        check_duty_and_timing(self.config, world, plan, where=where)
        if self.scenario.extra_check is not None:
            self.scenario.extra_check(self.config, world, plan, where)

        for decision in plan.zones:
            self.reasons[decision.reason.value] += 1
            if decision.on_fallback:
                self.fallbacks += 1
        for command in plan.commands:
            self.reasons[command.reason.value] += 1
        for item in plan.untouched:
            self.reasons[item.reason.value] += 1
        for circuit in plan.circuits:
            self.reasons[circuit.reason.value] += 1
        for deferral in plan.deferrals:
            self.reasons[deferral.reason.value] += 1

        self.plan = plan
        self.hand.data = plan
        self._apply(plan)
        self._drift()

    def run(self) -> Simulation:
        """Step through the whole month and return itself."""
        for _ in range(int(timedelta(days=self.scenario.days) / STEP)):
            self.step()
        return self


def check_duty_and_timing(config: DirectorConfig, world: WorldState, plan, where: str = "") -> None:
    """Assert the promises that only a running clock can break."""
    mark = f"{where}: " if where else ""

    for circuit in config.circuits:
        # Wat er nog draait in de andere taak, moet de director deze ronde
        # aanpakken: stilzetten, meenemen naar de taak die wél opgedragen wordt,
        # of met opzet loslaten. Een mens met een afstandsbediening kan altijd
        # twee taken maken; de director mag er alleen nooit stil bij blijven
        # staan.
        #
        # Whatever still runs in the other duty, the director must deal with
        # this round: stop it, take it along to the duty that *is* being
        # ordered, or deliberately let go of it. A person with a remote can
        # always create two duties; the director simply may never stand by
        # quietly.
        if not circuit.simultaneous_heat_cool:
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
                    handled = command is not None and family_of(command.hvac_mode) in (
                        ModeFamily.NEUTRAL,
                        duty,
                    )
                    assert handled or plan.untouched_for(entity_id) is not None, (
                        f"{mark}{entity_id} draait {other} terwijl {duty} wordt opgedragen"
                    )

        # Kortcyclusbescherming: een unit die net gestopt is mag niet meteen
        # weer starten. Alleen starten wordt tegengehouden, nooit stoppen.
        #
        # Short-cycle protection: a unit that just stopped may not start again
        # at once. Only starts are held back, never stops.
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
                f"{mark}{entity_id} start na {waited}, terwijl {circuit.min_cycle_time} moet"
            )


class _PreconditionStandIn:
    """Drives the coordinator's own pre-conditioning code from the simulation."""

    def __init__(self, sim: Simulation) -> None:
        self.config = sim.config
        self._precondition: dict[str, datetime] = {}
        self._precondition_bypass: set[str] = set()

    # De echte methodes, zodat de begrenzing en het opschonen meegetest worden.
    # The real methods, so the capping and the pruning are tested along.
    start = ClimateDirectorCoordinator.async_precondition
    cancel = ClimateDirectorCoordinator.async_cancel_precondition
    live = ClimateDirectorCoordinator._live_preconditions
    _live_preconditions = ClimateDirectorCoordinator._live_preconditions
    _wake_at_the_first_expiry = ClimateDirectorCoordinator._wake_at_the_first_expiry

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
        self.data = None
        self._issued = None
        self.shadow = False
        self.zone_overrides: dict[str, bool] = {}
        self._handed_back: dict[str, object] = {}
        self._commanded_off: dict[str, object] = {}
        self.saved = 0
        self.hass = _Hass(sim)

    _notice_hand = ClimateDirectorCoordinator._notice_hand
    _zones_of = ClimateDirectorCoordinator._zones_of
    _we_wanted_it_off = ClimateDirectorCoordinator._we_wanted_it_off
    _everyone_asleep = ClimateDirectorCoordinator._everyone_asleep
    _house_is_empty = ClimateDirectorCoordinator._house_is_empty
    _state_is = ClimateDirectorCoordinator._state_is

    def _async_save_state(self) -> None:
        self.saved += 1

    def handed_back(self):
        """Return the zones handed back today, on the simulation's clock."""
        from custom_components.climate_director import coordinator as coordinator_module

        now = coordinator_module.dt_util.now()
        residents = {
            resident.resident_id: ClimateDirectorCoordinator._resident(
                self, resident.presence_entity, resident.sleep_entity, resident.sleep_state
            )
            for resident in self.config.residents
        }
        return ClimateDirectorCoordinator._zones_handed_back(self, now, residents)

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


def run_month(scenario: Scenario, *, seed: int) -> Simulation:
    """Run one scenario with the coordinator's clock moving along.

    `_zones_handed_back` kijkt naar de dag van vandaag. Zonder die klok mee te
    laten lopen vervalt een handmatige uitzetting nooit, en dan test een maand
    op dat punt niets.

    `_zones_handed_back` looks at today's date. Without moving that clock along
    a hand-back never lapses, and then a month tests nothing on that point.
    """
    import pytest

    from custom_components.climate_director import coordinator as coordinator_module

    simulation = Simulation(scenario, seed=seed)
    with pytest.MonkeyPatch.context() as patch:
        holder = {"now": scenario.start}
        patch.setattr(coordinator_module.dt_util, "now", lambda: holder["now"])
        for _ in range(int(timedelta(days=scenario.days) / STEP)):
            holder["now"] = simulation.now + STEP
            simulation.step()
    return simulation
