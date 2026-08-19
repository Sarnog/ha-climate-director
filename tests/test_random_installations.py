"""Duizenden geldige huizen, elk in een willekeurige wereld.

Thousands of valid houses, each in a random world.

`test_fuzz_decide.py` gooit rommel naar de lezer en kijkt of hij blijft staan.
Dit doet het omgekeerde: alleen installaties die kloppen, maar dan wel met elke
optie die de integratie kent, in elke combinatie die het lot kiest. Daar komen
de fouten uit die pas ontstaan als twee instellingen elkaar raken - en dat zijn
precies de fouten die je bij een gebruiker thuis pas ziet.

De weg loopt bovendien via het formulier: wat de gebruiker in de wizard intikt
wordt een opgeslagen dict, die dict wordt een configuratie, en die configuratie
moet gezond zijn en een plan opleveren. Zo wordt de hele keten van scherm tot
besluit doorlopen in plaats van alleen het stuk erna.

`test_fuzz_decide.py` throws rubbish at the reader and checks that it stays
standing. This does the opposite: only installations that make sense, but then
with every option the integration knows, in whatever combination chance picks.
That is where the faults come out that only arise once two settings touch - and
those are exactly the faults you first see in somebody's home.

The route runs through the form as well: what the user types into the wizard
becomes a stored dict, that dict becomes a configuration, and that configuration
has to be sound and yield a plan. So the whole chain from screen to decision is
walked rather than only the part after it.
"""

from __future__ import annotations

import random
from collections import Counter
from datetime import datetime, timedelta

import pytest
from conftest import assert_plan_holds

from custom_components.climate_director.config_flow import _zone_errors, _zone_from_form
from custom_components.climate_director.coordinator import (
    season_from_state,
    temperature_from_state,
)
from custom_components.climate_director.engine import (
    ClimateState,
    ConflictPolicy,
    OpeningState,
    PresenceState,
    Reason,
    ResidentState,
    Season,
    SourceRole,
    WorldState,
    ZoneGate,
    decide,
    validate,
)
from custom_components.climate_director.engine.serialise import config_from_dict, config_to_dict

NOW = datetime(2026, 3, 15, 14, 30)

MODES = ("off", "heat", "cool", "dry", "fan_only", "auto", "heat_cool")


# ---------------------------------------------------------------------------
# Een willekeurig huis dat wél klopt.
# A random house that does make sense.
# ---------------------------------------------------------------------------


def _window(rng: random.Random) -> dict:
    start = rng.randrange(0, 24)
    end = (start + rng.randrange(1, 20)) % 24
    days = rng.choice([None, [0, 1, 2, 3, 4], [5, 6], [0, 2, 4], list(range(7))])
    return {
        "start": f"{start:02d}:00:00",
        "end": f"{end:02d}:00:00",
        "weekdays": days,
        "holiday": rng.random() < 0.2,
    }


def _quiet_window(rng: random.Random) -> dict:
    """Return a quiet window as somebody would really set one: evening to morning.

    Een willekeurig venster kan bij toeval de hele dag beslaan, en dan zet het
    huis zichzelf voorgoed stil - `validate()` klaagt daar sinds deze ronde
    terecht over, dus een generator van geldige huizen hoort het niet te maken.

    A random window can cover the whole day by chance, and then the house
    silences itself for good - `validate()` rightly complains about that as of
    this round, so a generator of valid houses should not make one.
    """
    return {
        "start": f"{rng.randrange(20, 24):02d}:00:00",
        "end": f"{rng.randrange(5, 11):02d}:00:00",
        "weekdays": rng.choice([None, [0, 1, 2, 3, 4], [5, 6]]),
        "holiday": rng.random() < 0.2,
    }


def _mode_settings(rng: random.Random, *, heating: bool) -> dict:
    """Return a sound band: heating aims above its switch-on point, cooling below."""
    # De twee bereiken raken elkaar niet: koelen dat op hetzelfde punt begint als
    # verwarmen is een configuratiefout, en die hoort niet uit een generator van
    # geldige huizen te komen. Eén op de paar duizend keer vielen ze samen.
    #
    # The two ranges do not touch: cooling that starts where heating starts is a
    # configuration mistake, and that should not come out of a generator of valid
    # houses. One in a few thousand they coincided.
    start = rng.uniform(16.0, 21.0) if heating else rng.uniform(22.0, 28.0)
    offset = rng.choice([0.0, 0.5, 1.0, 2.0])
    return {
        "target": round(start + offset if heating else start - offset, 1),
        "start_at": round(start, 1),
        "hysteresis": rng.choice([0.2, 0.5, 1.0, 2.0]),
        "outdoor": (
            {"minimum": None, "maximum": rng.choice([None, 15.0, 19.0])}
            if heating
            else {"minimum": rng.choice([None, 18.0, 24.0]), "maximum": None}
        ),
        "seasons": rng.choice([None, ["summer"], ["winter"], ["summer", "winter"]]),
    }


def _zone(rng: random.Random, index: int, units: list[str], shared: str | None) -> dict:
    """Return one zone as the wizard would have stored it."""
    own = units[index]

    heating = rng.random() < 0.85
    cooling = rng.random() < 0.85
    if not heating and not cooling:
        heating = True

    # De rol van de eigen bron dekt wat de zone mag. Een zone die wil verwarmen
    # zonder bron die dat kan is een configuratiefout, en die hoort niet uit een
    # generator te komen die geldige huizen moet maken.
    #
    # The own source's role covers what the zone may do. A zone that wants to
    # heat without a source that can is a configuration mistake, and that should
    # not come out of a generator meant to build valid houses.
    if heating and cooling:
        role = SourceRole.HEAT_COOL
    elif heating:
        role = rng.choice([SourceRole.HEAT_COOL, SourceRole.HEAT_ONLY])
    else:
        role = rng.choice([SourceRole.HEAT_COOL, SourceRole.COOL_ONLY])

    sources = [
        {
            "source_id": f"z{index}_own",
            "entity_id": own,
            "role": role.value,
            "priority": rng.randrange(0, 3),
            "autostart": rng.random() > 0.25,
            "outdoor": {"minimum": rng.choice([None, 3.1]), "maximum": None},
        }
    ]
    if shared is not None and heating and rng.random() < 0.6:
        sources.append(
            {
                "source_id": f"z{index}_shared",
                "entity_id": shared,
                "role": SourceRole.HEAT_ONLY.value,
                "priority": rng.randrange(1, 4),
                "autostart": True,
                "outdoor": {"minimum": None, "maximum": 3.1},
            }
        )

    # Een reservebron: hetzelfde kunstje, geen eigen buitengrens, en een plek
    # verder in de rij. Zonder zo'n bron is er niets om naar uit te wijken als
    # de eerste keus wegvalt, en dan test een onbereikbaar apparaat alleen dat
    # de zone stilvalt.
    #
    # A reserve source: the same trick, no outdoor bound of its own, and a place
    # further down the queue. Without one there is nothing to fall back to when
    # the first choice drops out, and then an unreachable appliance only tests
    # that the zone falls silent.
    if rng.random() < 0.4:
        sources.append(
            {
                "source_id": f"z{index}_reserve",
                "entity_id": f"climate.reserve{index}",
                "role": role.value,
                "priority": 5,
                "autostart": True,
                "outdoor": {"minimum": None, "maximum": None},
            }
        )

    # Een zone waarvan een gewenste taak alleen door handbediende bronnen wordt
    # gedekt, zou de wizard weigeren. De generator hoort alleen te bouwen wat
    # een gebruiker had kunnen invoeren, dus valt de eigen bron dan terug op
    # automatisch starten; haar rol dekt beide gewenste taken.
    #
    # A zone where a wanted duty is covered only by hand-operated sources would
    # be refused by the wizard. The generator should only build what a user
    # could have entered, so the own source then falls back on starting
    # automatically; its role covers both wanted duties.
    def covers(role: str, wants_heat: bool, wants_cool: bool) -> bool:
        if wants_heat and role in (SourceRole.HEAT_COOL.value, SourceRole.HEAT_ONLY.value):
            return True
        return wants_cool and role in (
            SourceRole.HEAT_COOL.value,
            SourceRole.COOL_ONLY.value,
        )

    def has_auto(wants_heat: bool, wants_cool: bool) -> bool:
        return any(
            item["autostart"] and covers(item["role"], wants_heat, wants_cool) for item in sources
        )

    if (heating and not has_auto(True, False)) or (cooling and not has_auto(False, True)):
        sources[0]["autostart"] = True

    gate = rng.choice([item.value for item in ZoneGate])
    return {
        "zone_id": f"zone{index}",
        "name": f"Kamer {index}",
        "indoor_sensor": f"sensor.kamer{index}",
        "priority": index,
        "sources": sources,
        "heat": _mode_settings(rng, heating=True) if heating else None,
        "cool": _mode_settings(rng, heating=False) if cooling else None,
        "gate": gate,
        "presence_entity": (
            f"binary_sensor.kamer{index}"
            if gate == ZoneGate.PRESENCE.value or rng.random() < 0.4
            else ""
        ),
        "presence_state": "on",
        "presence_timeout": rng.choice([0, 300, 1800]),
    }


def _installation(rng: random.Random) -> dict:
    """Return a whole installation as `entry.options` would hold it."""
    count = rng.randrange(1, 5)
    units = [f"climate.unit{index}" for index in range(count)]
    shared = "climate.ketel" if rng.random() < 0.6 else None

    zones = [_zone(rng, index, units, shared) for index in range(count)]

    circuits = []
    if count > 1 and rng.random() < 0.8:
        members = units[: rng.randrange(2, count + 1)]
        # Een buitenunit die beide taken tegelijk aankan wisselt nooit van
        # taak, dus omschakeltijden horen daar niet bij - `validate()` zegt dat
        # ook, en dan hoort een generator van geldige huizen ze niet te maken.
        #
        # An outdoor unit that can run both duties at once never switches duty,
        # so switch timings do not belong there - `validate()` says so too, and
        # a generator of valid houses should not make them.
        simultaneous = rng.random() < 0.3
        circuits.append(
            {
                "circuit_id": "buiten",
                "name": "Buitenunit",
                "units": members,
                "simultaneous_heat_cool": simultaneous,
                "conflict_policy": rng.choice([item.value for item in ConflictPolicy]),
                "allow_fan_only_during_conflict": rng.random() < 0.3,
                "family_switch_delay": 0 if simultaneous else rng.choice([0, 60, 300]),
                "min_family_switch_interval": (0 if simultaneous else rng.choice([0, 600, 1800])),
                "min_cycle_time": rng.choice([0, 300, 1200]),
                "max_concurrent_units": rng.choice([None, 1, 2, len(members)]),
            }
        )

    generators = []
    if shared is not None and rng.random() < 0.3:
        generators.append(
            {
                "generator_id": "vloer",
                "name": "Vloer",
                "entity_id": "climate.vloer",
                "zone_ids": [zone["zone_id"] for zone in zones[:1]],
            }
        )

    residents = [
        {
            "resident_id": f"bewoner{index}",
            "name": f"Bewoner {index}",
            "presence_entity": f"person.bewoner{index}",
            "sleep_entity": rng.choice(["", f"sensor.bewoner{index}"]),
            "sleep_state": "wireless",
            "sleep_window": rng.choice([None, _window(rng)]),
            "windows": [_window(rng) for _ in range(rng.randrange(0, 3))],
        }
        for index in range(rng.randrange(0, 3))
    ]

    openings = [
        {
            "entity_id": f"binary_sensor.raam{index}",
            "delay": rng.choice([0, 30, 120]),
            "zone_ids": rng.choice([[], [zone["zone_id"] for zone in zones[:1]]]),
        }
        for index in range(rng.randrange(0, 3))
    ]

    # Een uitsluitende groep tussen twee bronnen die elkaar bij hetzelfde weer
    # allebei mogen, is een configuratiefout - `validate()` zegt dat ook. De
    # zinnige vorm is de vorm uit een echt huis: een airco vanaf 3,1 graden
    # tegenover een gasverzoek tot 3,1 graden.
    #
    # An exclusive group between two sources both allowed at the same weather is
    # a configuration mistake - `validate()` says so too. The sensible shape is
    # the one from a real house: an air conditioner from 3.1 degrees upward
    # against a gas request up to 3.1.
    scheduled = any(resident["windows"] for resident in residents)
    truly_shared = (
        shared is not None
        and sum(
            1 for zone in zones if any(source["entity_id"] == shared for source in zone["sources"])
        )
        > 1
    )

    groups = []
    if rng.random() < 0.4:
        chilly = next(
            (zone for zone in zones if zone["sources"][0]["outdoor"]["minimum"] is not None),
            None,
        )
        warm_source = next(
            (
                source["source_id"]
                for zone in zones
                for source in zone["sources"]
                if source["source_id"].endswith("_shared")
            ),
            None,
        )
        if chilly is not None and warm_source is not None:
            groups.append([chilly["sources"][0]["source_id"], warm_source])

    outdoor_needed = any(
        (zone[mode] or {}).get("outdoor", {}).get("minimum") is not None
        or (zone[mode] or {}).get("outdoor", {}).get("maximum") is not None
        for zone in zones
        for mode in ("heat", "cool")
    ) or any(
        source["outdoor"]["minimum"] is not None or source["outdoor"]["maximum"] is not None
        for zone in zones
        for source in zone["sources"]
    )

    return {
        # "Centraal" mag alleen als er werkelijk één warmtebron door meerdere
        # zones gedeeld wordt; anders is het een gezoneerd systeem en zegt
        # `validate()` dat ook.
        #
        # "Central" is only allowed when one heat source really is shared
        # between several zones; otherwise it is a zoned system, and
        # `validate()` says so.
        "heating_layout": "central" if truly_shared and rng.random() < 0.6 else "per_zone",
        "zones": zones,
        "circuits": circuits,
        "generators": generators,
        "residents": residents,
        "openings": openings,
        "exclusive_groups": groups,
        "gates": {
            "require_awake": rng.random() < 0.7,
            # De roosterpoort kan alleen aan als er ook iemand een rooster
            # heeft; anders zou het huis nooit iets mogen en klaagt
            # `validate()` daar terecht over.
            #
            # The schedule gate can only be on when somebody actually has a
            # schedule; otherwise the house could never do anything, which
            # `validate()` rightly complains about.
            "require_schedule": scheduled and rng.random() < 0.5,
            "max_precondition": rng.choice([1800, 7200, 14400]),
            "precondition_window": rng.choice([None, _window(rng)]),
            "guest_window": rng.choice([None, _window(rng)]),
            "quiet_windows": [_quiet_window(rng) for _ in range(rng.randrange(0, 3))],
        },
        "seasons": rng.choice(
            [
                {"source": "month"},
                {"source": "summer"},
                {"source": "winter"},
                {"source": "entity", "entity_id": "sensor.seizoen"},
            ]
        ),
        "outdoor_sensor": "sensor.buiten" if outdoor_needed or rng.random() < 0.5 else "",
        # Agenda's zonder trefwoord kunnen nooit iets aanzetten, en daar
        # klaagt `validate()` terecht over; die combinatie hoort dus niet uit
        # een generator van geldige huizen te komen.
        #
        # Calendars without a keyword can never switch anything on, which
        # `validate()` rightly complains about; that combination should not come
        # out of a generator of valid houses.
        **(
            {"holiday_calendars": ["calendar.familie"], "holiday_keyword": "vakantie"}
            if rng.random() < 0.4
            else {"holiday_calendars": [], "holiday_keyword": rng.choice(["", "vakantie"])}
        ),
        "stuck_after": rng.choice([0, 900, 3600]),
    }


def _world(rng: random.Random, config) -> WorldState:
    """Return a plausible world for that installation, edges included.

    De helft van de werelden is een huis waarin gewoon geregeld mag worden:
    iedereen thuis en wakker, ramen dicht, niets overgedragen. Zonder die helft
    staan er zoveel poorten dicht dat de regels áchter de poorten - het
    circuit, de kortcyclus, de omschakelpauze - nooit aan bod komen, en dan
    test de sweep alleen de voordeur.

    Half the worlds are a house where regulating is simply allowed: everybody
    home and awake, windows shut, nothing handed over. Without that half so
    many gates stand shut that the rules *behind* the gates - the circuit,
    short-cycle, the switch pause - never get their turn, and then the sweep
    only tests the front door.
    """
    entities = {source.entity_id for _, source in config.sources() if source.entity_id}
    entities |= {item.entity_id for item in config.generators if item.entity_id}
    calm = rng.random() < 0.5

    # Elke tijdstempel hangt aan deze klok en niet aan een vast punt. Anders
    # ligt alles wat "net gebeurd" heet dagen in het verleden, en dan is elke
    # timer in de engine per definitie al verlopen - de kortcyclusbescherming
    # en de omschakelpauze zouden dan nooit getest worden.
    #
    # Every timestamp hangs off this clock rather than off a fixed point.
    # Otherwise everything called "just happened" lies days in the past, and
    # then every timer in the engine has expired by definition - short-cycle
    # protection and the switch pause would never be tested.
    now = NOW + timedelta(minutes=rng.randrange(0, 60 * 24 * 7))

    return WorldState(
        now=now,
        outdoor_temperature=(
            rng.choice([-12.0, 0.0, 3.0, 3.1, 12.0, 21.0, 30.0])
            if calm
            else rng.choice([None, -12.0, 0.0, 3.0, 3.1, 12.0, 21.0, 30.0, 41.0])
        ),
        season=rng.choice([Season.SUMMER, Season.WINTER] if calm else list(Season)),
        indoor_temperatures={
            zone.zone_id: rng.choice(
                [12.0, 15.0, 18.0, 26.0, 28.0, 31.0]
                if calm
                else [None, 12.0, 15.0, 18.0, 20.5, 23.0, 26.0, 28.0, 31.0]
            )
            for zone in config.zones
        },
        # Een entiteit die wegvalt leest als niets: zo bouwt de coordinator hem
        # ook op. Een niet-bereikbare unit die tóch een stand rapporteert bestaat
        # in Home Assistant niet, en zou de wereld hier onrealistisch maken.
        #
        # An entity that drops out reads as nothing: that is how the coordinator
        # builds it too. An unreachable unit still reporting a mode does not
        # exist in Home Assistant, and would make this world unrealistic.
        climates={
            entity: (
                ClimateState(
                    hvac_mode=rng.choice(MODES),
                    available=True,
                    changed_at=now - timedelta(minutes=rng.randrange(0, 45)),
                )
                if calm or rng.random() > 0.15
                else ClimateState(available=False)
            )
            for entity in entities
        },
        residents={
            resident.resident_id: ResidentState(
                home=calm or rng.random() < 0.8,
                asleep=not calm and rng.random() < 0.25,
            )
            for resident in config.residents
        },
        openings={
            opening.entity_id: OpeningState(
                open=not calm and rng.random() < 0.3,
                changed_at=rng.choice([None, now - timedelta(minutes=rng.randrange(0, 60))]),
            )
            for opening in config.openings
        },
        presence={
            zone.zone_id: PresenceState(
                occupied=calm or rng.random() < 0.5,
                changed_at=rng.choice([None, now - timedelta(minutes=rng.randrange(0, 120))]),
            )
            for zone in config.zones
        },
        circuit_family_since={
            circuit.circuit_id: rng.choice([None, now - timedelta(minutes=rng.randrange(0, 40))])
            for circuit in config.circuits
        },
        master_enabled=calm or rng.random() < 0.9,
        holiday_mode=rng.random() < 0.2,
        guest_mode=rng.random() < 0.2,
        precondition_until=(
            {rng.choice(config.zones).zone_id: now + timedelta(hours=1)}
            if config.zones and rng.random() < 0.25
            else {}
        ),
        precondition_bypass=frozenset(),
        zone_overrides=(
            {} if calm else {zone.zone_id: True for zone in config.zones if rng.random() < 0.15}
        ),
        zone_priorities={
            zone.zone_id: rng.randrange(0, 5) for zone in config.zones if rng.random() < 0.2
        },
    )


@pytest.fixture(scope="module")
def sweep():
    """Return the outcome of two thousand random installations."""
    rng = random.Random(20260218)
    reasons: Counter[str] = Counter()
    problems = 0
    plans = 0
    fallbacks = 0

    for _ in range(2_000):
        stored = _installation(rng)
        config = config_from_dict(stored)

        # De wizard schrijft alleen gezonde installaties weg, dus een klacht
        # hier betekent dat de generator zelf iets bouwt wat de gebruiker niet
        # had kunnen invoeren.
        #
        # The wizard only writes sound installations, so a complaint here means
        # the generator itself builds something the user could not have entered.
        found = validate(config)
        problems += len(found)
        assert not found, found

        # Opslaan en terugleggen mag niets veranderen.
        # Storing and reading back may change nothing.
        assert config_from_dict(config_to_dict(config)) == config

        world = _world(rng, config)
        plan = decide(config, world)
        assert decide(config, world) == plan

        assert_plan_holds(config, world, plan, where=str(world.now))
        plans += 1

        for decision in plan.zones:
            reasons[decision.reason.value] += 1
            if decision.on_fallback:
                fallbacks += 1
        for command in plan.commands:
            reasons[command.reason.value] += 1
        for item in plan.untouched:
            reasons[item.reason.value] += 1
        # Een circuit dat moet wachten meldt dat op zijn eigen besluit en op de
        # uitgestelde actie, niet op een zone: de zone hoort alleen dat hij
        # niets krijgt.
        #
        # A circuit having to wait reports that on its own decision and on the
        # deferral, not on a zone: the zone only hears that it gets nothing.
        for circuit in plan.circuits:
            reasons[circuit.reason.value] += 1
        for deferral in plan.deferrals:
            reasons[deferral.reason.value] += 1

    return {
        "reasons": reasons,
        "plans": plans,
        "problems": problems,
        "fallbacks": fallbacks,
    }


class TestEveryInstallationHolds:
    """Tweeduizend huizen, en geen enkele belofte gebroken.

    Two thousand houses, and not one promise broken.
    """

    def test_the_sweep_really_ran(self, sweep: dict) -> None:
        assert sweep["plans"] == 2_000

    def test_the_generator_only_builds_sound_houses(self, sweep: dict) -> None:
        """Otherwise the sweep would be testing the complaint, not the decision."""
        assert sweep["problems"] == 0

    def test_a_room_fell_back_on_its_reserve(self, sweep: dict) -> None:
        """Apparaten vallen weg in deze werelden; dan hoort het vangnet te werken."""
        assert sweep["fallbacks"] > 0, sweep["fallbacks"]

    def test_it_reached_the_interesting_corners(self, sweep: dict) -> None:
        """A sweep in which nothing ever happens proves nothing."""
        reasons = sweep["reasons"]
        assert reasons[Reason.REGULATING.value] > 100, reasons
        assert reasons[Reason.SATISFIED.value] > 100, reasons

    #: `mode_not_configured` staat er niet bij, en dat is goed nieuws: die
    #: reden komt alleen naar buiten als een zone noch mag verwarmen noch mag
    #: koelen, en zo'n zone kan sinds deze ronde niet meer opgeslagen worden -
    #: het scherm weigert hem. Onbereikbaar zijn is hier de bedoeling.
    #:
    #: `mode_not_configured` is absent, and that is good news: that reason only
    #: surfaces when a zone may neither heat nor cool, and such a zone can no
    #: longer be saved as of this round - the screen refuses it. Being
    #: unreachable is the intent here.
    #:
    #: `exclusive_group_lost` staat er ook niet bij, om een andere reden: een
    #: geldige groep mag geen twee bronnen bevatten die bij hetzelfde weer
    #: allebei mogen draaien, dus in een willekeurig huis botsen ze bijna nooit.
    #: Waar hij wél bijt is bij een handbediend apparaat dat opzij moet - en dat
    #: is precies de opstelling van de maandsimulatie, die hem dan ook telt.
    #:
    #: `exclusive_group_lost` is absent too, for a different reason: a valid
    #: group may not hold two sources both allowed to run at the same weather,
    #: so in a random house they hardly ever meet. Where it does bite is a
    #: hand-operated appliance having to step aside - which is exactly the month
    #: simulation's setup, and it counts it there.

    @pytest.mark.parametrize(
        "reason",
        [
            Reason.MASTER_DISABLED,
            Reason.MANUAL_OVERRIDE,
            Reason.OPENING_OPEN,
            Reason.NOBODY_HOME,
            Reason.EVERYONE_ASLEEP,
            Reason.OUTSIDE_SCHEDULE,
            Reason.ZONE_UNOCCUPIED,
            Reason.QUIET_HOURS,
            Reason.NO_INDOOR_TEMPERATURE,
            Reason.SEASON_BLOCKS_MODE,
            Reason.OUTDOOR_OUTSIDE_WINDOW,
            Reason.NO_SOURCE_AVAILABLE,
            Reason.OTHER_SOURCE_CHOSEN,
            Reason.MANUAL_SOURCE,
            Reason.SOURCE_UNREACHABLE,
            Reason.CIRCUIT_CONFLICT_LOST,
            Reason.CIRCUIT_SWITCH_TOO_SOON,
            Reason.CIRCUIT_SWITCH_PENDING,
            Reason.CIRCUIT_AT_CAPACITY,
            Reason.SHORT_CYCLE_PROTECTION,
        ],
        ids=lambda reason: reason.value,
    )
    def test_the_outcome_was_reached(self, sweep: dict, reason: Reason) -> None:
        assert sweep["reasons"][reason.value] > 0, sorted(sweep["reasons"])


class TestTheFormBuildsSoundZones:
    """Wat de wizard uit een ingevuld formulier maakt, moet de engine aankunnen.

    What the wizard makes of a filled-in form, the engine has to cope with.
    """

    def _form(self, rng: random.Random) -> dict:
        heat_start = round(rng.uniform(15.0, 23.0), 1)
        cool_start = round(rng.uniform(20.0, 30.0), 1)
        return {
            "name": rng.choice(["Woonkamer", "Zolder", "Slaap kamer", "Café", "1", " "]),
            "indoor_sensor": "sensor.kamer",
            "priority": rng.randrange(0, 10),
            "gate": rng.choice([item.value for item in ZoneGate]),
            "presence_entity": rng.choice(["", "binary_sensor.kamer"]),
            "presence_state": rng.choice(["on", "home", ""]),
            "presence_timeout": rng.choice([None, 0, 900]),
            "enable_heat": rng.random() < 0.8,
            "heat_target": round(heat_start + rng.choice([-1.0, 0.0, 1.0, 2.0]), 1),
            "heat_start_at": heat_start,
            "heat_hysteresis": rng.choice([0.0, 0.5, 1.0]),
            "heat_outdoor_max": rng.choice([None, 19.0]),
            "enable_cool": rng.random() < 0.8,
            "cool_target": round(cool_start + rng.choice([-2.0, -1.0, 0.0, 1.0]), 1),
            "cool_start_at": cool_start,
            "cool_hysteresis": rng.choice([0.0, 0.5, 1.0]),
            "cool_outdoor_min": rng.choice([None, 24.0]),
            "cool_summer_only": rng.random() < 0.5,
        }

    def _single_zone(self, zone: dict) -> dict:
        """Return the smallest installation holding just that zone."""
        return {
            "zones": [{**zone, "sources": [{"source_id": "s", "entity_id": "climate.unit"}]}],
            "outdoor_sensor": "sensor.buiten",
        }

    def test_a_thousand_filled_in_forms(self) -> None:
        """What the screen accepts, the engine must be able to work with."""
        rng = random.Random(99)
        refused = 0
        for _ in range(1_000):
            zone = _zone_from_form(self._form(rng), {})
            if _zone_errors(zone):
                refused += 1
                continue

            config = config_from_dict(self._single_zone(zone))
            assert not validate(config), validate(config)
            assert config_from_dict(config_to_dict(config)) == config

        assert refused > 0, "geen enkel formulier werd geweigerd; de controle doet niets"
        assert refused < 1_000, "elk formulier werd geweigerd; de generator deugt niet"

    def test_the_screen_refuses_exactly_what_the_engine_complains_about(self) -> None:
        """Twee plekken, één waarheid - in beide richtingen.

        Weigert het scherm te weinig, dan sla je een zone op die nooit kan
        werken en zoek je later waarom er niets gebeurt. Weigert het te veel,
        dan houdt het je tegen bij iets wat prima had gekund. Deze test breekt
        zodra de engine een nieuwe klacht over een zone leert die het scherm
        nog niet kent.

        Two places, one truth - in both directions. Refuse too little and you
        save a zone that can never work, then go looking later for why nothing
        happens. Refuse too much and it holds you back from something perfectly
        fine. This test breaks the moment the engine learns a new complaint
        about a zone that the screen does not know yet.
        """
        rng = random.Random(7)
        seen = {True: 0, False: 0}
        for _ in range(2_000):
            zone = _zone_from_form(self._form(rng), {})
            accepted = not _zone_errors(zone)
            sound = not validate(config_from_dict(self._single_zone(zone)))
            assert accepted == sound, (zone, validate(config_from_dict(self._single_zone(zone))))
            seen[accepted] += 1

        assert seen[True] > 100, seen
        assert seen[False] > 100, seen


class TestReadingEntitiesNeverBreaks:
    """De twee vertalingen van een entiteitstoestand naar een getal of seizoen.

    The two translations from an entity state into a number or a season.
    """

    JUNK = (
        "",
        " ",
        "unknown",
        "unavailable",
        "None",
        "12,5",
        "12.5",
        "-40",
        "1e400",
        "nan",
        "zomer",
        "SUMMER",
        "Hiver",
        "❄",
        "21.0",
    )

    def test_any_state_reads_as_a_number_or_nothing(self) -> None:
        rng = random.Random(3)
        for _ in range(2_000):
            entity = rng.choice(["sensor.x", "weather.home", "climate.unit"])
            attributes = rng.choice(
                [
                    {},
                    {"temperature": rng.choice([*self.JUNK, 21.5, None])},
                    {"current_temperature": rng.choice([*self.JUNK, 19.0, None])},
                    {"temperature": "x", "current_temperature": 20.0},
                ]
            )
            value = temperature_from_state(entity, rng.choice(self.JUNK), attributes)
            assert value is None or isinstance(value, float)

    def test_a_non_finite_reading_is_no_reading(self) -> None:
        """`nan` and `inf` are unreadable too, exactly like `unknown`.

        Every comparison with them is false, so a broken sensor reporting one
        would satisfy each bounded outdoor window at once and quietly pick a
        source that an unreadable temperature should have shut out.
        """
        for raw in ("nan", "-nan", "inf", "-inf", "1e400", "-1e400", "NaN", "Infinity"):
            assert temperature_from_state("sensor.x", raw, {}) is None
            assert temperature_from_state("weather.home", "cloudy", {"temperature": raw}) is None
            assert (
                temperature_from_state("climate.unit", "heat", {"current_temperature": raw}) is None
            )

    def test_any_state_reads_as_a_season(self) -> None:
        rng = random.Random(4)
        for _ in range(500):
            season = season_from_state(rng.choice([*self.JUNK, None]))
            assert isinstance(season, Season)

    def test_a_climate_setpoint_is_never_read_as_the_room(self) -> None:
        """`temperature` on a climate entity is the setpoint, not the measurement."""
        assert temperature_from_state("climate.unit", "heat", {"temperature": 23.0}) is None
        assert temperature_from_state("climate.unit", "heat", {"current_temperature": 19.0}) == 19.0


class TestTheActionAcceptsAnything:
    """De actie voor vooruit verwarmen, met alles wat een gebruiker kan intikken.

    The pre-conditioning action, with everything a user can type in.
    """

    def _coordinator(self, ceiling: timedelta):
        from custom_components.climate_director.coordinator import ClimateDirectorCoordinator
        from custom_components.climate_director.engine import (
            DirectorConfig,
            GateSettings,
            Zone,
        )

        config = DirectorConfig(
            zones=(
                Zone("a", "A", "sensor.a"),
                Zone("b", "B", "sensor.b"),
            ),
            gates=GateSettings(max_precondition=ceiling),
        )

        class StandIn:
            def __init__(self) -> None:
                self.config = config
                self._precondition: dict[str, datetime] = {}
                self._precondition_bypass: set[str] = set()

            def async_request_evaluation(self) -> None:
                pass

            def _async_save_state(self) -> None:
                pass

            def _preconditions_expire_at(self, until: datetime) -> None:
                pass

            async_precondition = ClimateDirectorCoordinator.async_precondition
            async_cancel_precondition = ClimateDirectorCoordinator.async_cancel_precondition
            _live_preconditions = ClimateDirectorCoordinator._live_preconditions

        return StandIn()

    def test_every_number_a_user_can_type(self) -> None:
        rng = random.Random(11)
        ceiling = timedelta(hours=2)
        for _ in range(500):
            item = self._coordinator(ceiling)
            minutes = rng.choice([0, 0.5, 1, 15, 60, 119.9, 120, 121, 10_000, -5, 1e9])
            zones = rng.choice([None, [], ["a"], ["a", "b"], ["onbekend"], ["a", "onbekend"]])
            granted = item.async_precondition(zones, minutes, ignore_openings=rng.random() < 0.5)

            known = {zone.zone_id for zone in item.config.zones}
            assert set(granted) <= known, granted
            # Een lege lijst betekent het hele huis, net als geen lijst; alleen
            # een lijst met louter onbekende zones levert niets op.
            #
            # An empty list means the whole house, just like no list at all;
            # only a list of purely unknown zones yields nothing.
            if zones and not set(zones) & known:
                assert not granted
            for until in granted.values():
                assert until <= datetime.now(until.tzinfo) + ceiling + timedelta(seconds=1)

    def test_cancelling_anything_is_safe(self) -> None:
        rng = random.Random(12)
        for _ in range(200):
            item = self._coordinator(timedelta(hours=1))
            item.async_precondition(["a", "b"], 30)
            item.async_cancel_precondition(
                rng.choice([None, [], ["a"], ["onbekend"], ["a", "b", "onbekend"]])
            )
            assert set(item._live_preconditions()) <= {"a", "b"}
