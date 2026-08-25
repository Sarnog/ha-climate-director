"""Meetinstrument: hoe vaak ontsteekt een apparaat zonder circuit per uur.

Geen test — een meting. Draai hem vanuit de repo-root met `python
tests/measure_short_cycles.py`. Hij bouwt honderden willekeurige huizen met een
gedeelde ketel, een generator, een multi-split en twee openingen (één huisbreed,
één aan één zone gekoppeld), laat er drie uur realistisch weer overheen lopen,
voert het plan elke minuut uit, en meet het **kleinste gat tussen twee
ontstekingen** van elk apparaat zonder circuit.

Waarom dit bestaat: kortcyclusbescherming hangt aan een circuit, en een gasketel
of een gedeelde warmtebron hangt aan geen circuit. Dat gat is in ronde 3 (H2) en
ronde 4 (H3, R1) drie keer opnieuw opgedoken, telkens langs een ander pad. Deze
meting vindt het ongeacht het pad, want hij kijkt naar de uitkomst.

Verwachting bij een gezonde engine: het kleinste gat is >= OPENING_MIN_REST
(drie minuten) voor élk apparaat zonder circuit, generator inbegrepen. Komt er
iets van 1 of 2 minuten uit, dan is er een route waarlangs de rust niet geldt -
druk dan de configuratie en de reden af en bouw er een deterministische probe van.

Het weer is bewust traag (0,05 graad per minuut). Met een wilder random-walk
kruist de buitentemperatuur de gas/airco-grens zo vaak dat je je eigen artefact
meet in plaats van de engine; dat is tijdens ronde 4 één keer gebeurd.

IJKPUNT. Op `1057126` (2026-08-24, versie 7.1.5, dus **ná** de reparatie van R1)
meldt dit instrument nog stééds **FOUT: 2 < 3** op `climate.cv` in run 329. R1
zette alleen het gemelde pad dicht: een generator krijgt zijn openingsrust
alleen als élke bediende zone door een opening geweigerd is, en in run 329 is de
andere kamer gewoon op temperatuur. Dat is R14 op de restlijst. Zolang R14 open
staat is dit de verwachte uitslag; komt er iets ánders uit, dan is er iets
nieuws.

Draai dit instrument **ná** elke reparatie aan de openingsrust, niet ervoor.
Tijdens ronde 4 is dat niet gebeurd, en daardoor ging een reparatie de deur uit
die zijn eigen ijkpunt niet haalde.

En een waarschuwing over dit instrument zelf: een groene uitslag is géén bewijs.
Twee eerdere versies meldden OK terwijl de deterministische probe rood stond,
omdat de zoekruimte de vorm miste die breekt (`min_cycle_time = 0`, en een kamer
zonder de ketel als reserve). Een sweep vindt bugs; hij bewijst hun afwezigheid
niet. De probes in `review-probes-2026-08-24c.py` zijn het bewijs.
"""

from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from conftest import climate, make_world  # noqa: E402

from custom_components.climate_director.engine import (  # noqa: E402
    Circuit,
    DirectorConfig,
    Generator,
    ModeSettings,
    Opening,
    OpeningState,
    OutdoorWindow,
    Source,
    SourceRole,
    Zone,
    decide,
)
from custom_components.climate_director.engine.families import (  # noqa: E402
    ModeFamily,
    family_of,
)
from custom_components.climate_director.engine.gates import OPENING_MIN_REST  # noqa: E402

START = datetime(2026, 1, 12, 6, 0)
BOILER = "climate.ketel"
GENERATOR = "climate.cv"
UNIT_A = "climate.unit_a"
UNIT_B = "climate.unit_b"
DOOR = "binary_sensor.deur"
WINDOW = "binary_sensor.raam"

#: De apparaten zonder circuit. Die missen `min_cycle_time` en leunen dus
#: volledig op de openingsrust.
NO_CIRCUIT = (BOILER, GENERATOR)


def build(rng: random.Random) -> DirectorConfig:
    """Return one random house: two zones, a multi-split, a boiler, maybe a generator."""
    heat = ModeSettings(target=21.0, start_at=20.0, hysteresis=rng.choice([0.5, 1.0]))
    cool = ModeSettings(target=23.0, start_at=24.0, hysteresis=1.0)

    def room(zone_id: str, unit: str, priority: int) -> Zone:
        sources = [
            Source(
                source_id=f"{zone_id}_unit",
                entity_id=unit,
                role=SourceRole.HEAT_COOL,
                outdoor=OutdoorWindow(minimum=3.0),
            )
        ]
        # Niet elke kamer heeft de ketel als reserve. Een kamer met alleen een
        # binnenunit is doodgewoon - en juist daar remt niets de gedeelde
        # warmtebron indirect af, want de unit valt onder het circuit en de
        # ketel doet niet mee. Zonder deze variatie meldt de meting groen op een
        # bug die een deterministische probe wél laat zien.
        if rng.random() < 0.5:
            sources.append(
                Source(
                    source_id=f"{zone_id}_ketel",
                    entity_id=BOILER,
                    role=SourceRole.HEAT_ONLY,
                    priority=1,
                    outdoor=OutdoorWindow(maximum=3.0),
                )
            )
        return Zone(
            zone_id=zone_id,
            name=zone_id,
            indoor_sensor=f"sensor.{zone_id}",
            priority=priority,
            sources=tuple(sources),
            heat=heat,
            cool=cool,
        )

    generators = ()
    if rng.random() < 0.4:
        generators = (Generator(generator_id="cv", name="CV", entity_id=GENERATOR),)

    return DirectorConfig(
        zones=(room("woonkamer", UNIT_A, 0), room("zolder", UNIT_B, 1)),
        circuits=(
            Circuit(
                circuit_id="multi",
                name="Multi",
                units=(UNIT_A, UNIT_B),
                # Ook nul: dat is een geldige instelling, en juist dán remt de
                # binnenunit de gedeelde warmtebron niet meer indirect af. Met
                # alleen drie minuten meldde deze meting groen terwijl er een
                # deterministische probe rood stond - een vals-groen is erger
                # dan geen meting.
                min_cycle_time=timedelta(minutes=rng.choice([0, 3])),
            ),
        ),
        generators=generators,
        openings=(
            # Eén die het hele huis raakt, één die maar bij één kamer hoort -
            # die tweede is waar de reden bij `_collapse_shared` verloren ging.
            Opening(entity_id=DOOR, delay=timedelta(seconds=rng.choice([0, 30]))),
            Opening(entity_id=WINDOW, zone_ids=("zolder",)),
        ),
        house_wide_openings=rng.choice([(), (BOILER,), (BOILER, GENERATOR)]),
        outdoor_sensor="sensor.buiten",
    )


def run_house(rng: random.Random, config: DirectorConfig, minutes: int) -> dict[str, list[int]]:
    """Return, per appliance, the minutes at which it went from standing still to active."""
    previous = None
    modes = dict.fromkeys((BOILER, GENERATOR, UNIT_A, UNIT_B), "off")
    changed_at = {entity: START - timedelta(hours=2) for entity in modes}
    door = window = False
    door_since = window_since = START - timedelta(hours=2)
    indoor = {"woonkamer": rng.uniform(18, 21), "zolder": rng.uniform(18, 21)}
    outdoor = rng.uniform(1.5, 4.5)
    fires: dict[str, list[int]] = {entity: [] for entity in modes}

    for minute in range(minutes):
        now = START + timedelta(minutes=minute)
        if rng.random() < 0.25:
            door, door_since = not door, now
        if rng.random() < 0.125:
            window, window_since = not window, now
        outdoor += rng.uniform(-0.05, 0.05)
        for room in indoor:
            indoor[room] += rng.uniform(-0.05, 0.05)

        world = make_world(
            now=now,
            outdoor=outdoor,
            indoor=dict(indoor),
            climates={
                entity: climate(mode, changed_at=changed_at[entity])
                for entity, mode in modes.items()
            },
            openings={
                DOOR: OpeningState(open=door, changed_at=door_since),
                WINDOW: OpeningState(open=window, changed_at=window_since),
            },
        )
        plan = decide(config, world, previous)

        for command in plan.commands:
            if modes.get(command.entity_id) == command.hvac_mode:
                continue
            was_still = family_of(modes.get(command.entity_id, "off")) is ModeFamily.NEUTRAL
            now_active = family_of(command.hvac_mode) is not ModeFamily.NEUTRAL
            if was_still and now_active:
                fires[command.entity_id].append(minute)
            modes[command.entity_id] = command.hvac_mode
            changed_at[command.entity_id] = now
        previous = plan

    return fires


def main(runs: int = 400, minutes: int = 180, seed: int = 99) -> int:
    """Measure and report; return a non-zero exit code when the rest is violated."""
    rng = random.Random(seed)
    floor = int(OPENING_MIN_REST.total_seconds() // 60)
    worst: tuple[int, str, int, tuple[str, ...]] | None = None

    for run in range(runs):
        config = build(rng)
        fires = run_house(rng, config, minutes)
        for entity in NO_CIRCUIT:
            moments = fires[entity]
            for first, second in zip(moments, moments[1:], strict=False):
                gap = second - first
                if worst is None or gap < worst[0]:
                    worst = (gap, entity, run, config.house_wide_openings)

    print(f"{runs} huizen x {minutes} minuten, ondergrens = {floor} minuten")
    if worst is None:
        print("geen enkele ontsteking gemeten - de opstelling vraagt nooit warmte?")
        return 1
    gap, entity, run, house_wide = worst
    print(f"kleinste gat tussen twee ontstekingen: {gap} minuten")
    print(f"  apparaat      : {entity}")
    print(f"  run           : {run}")
    print(f"  house_wide    : {house_wide or '()'}")
    if gap < floor:
        print(f"\nFOUT: {gap} < {floor}. Er is een route waarlangs de openingsrust niet geldt.")
        print("Bouw hier een deterministische probe van voordat je iets repareert.")
        return 1
    print("\nOK: elk apparaat zonder circuit houdt zijn rusttijd.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
