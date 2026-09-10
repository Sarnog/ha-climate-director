"""Anker 12: een weggevallen bron laat het hele gebied door één bron overnemen.

Anchor 12: a source that dropped out lets one source take the whole area over.

De opstelling is die van dit huis: een gasketel die het hele huis warm maakt en
per kamer een airco. Valt een airco weg, dan neemt de ketel de taak over — en
dan mag er in dat hele gebied niets anders meer verwarmen of koelen, want anders
verwarmt de ketel het huis terwijl de airco's doorstoken, of wordt dezelfde
ruimte tegelijk verwarmd en gekoeld.

The setup is this house's: a gas boiler warming the whole house and an air
conditioner per room. When an air conditioner drops out the boiler takes the
duty over — and then nothing else in that whole area may heat or cool, since
otherwise the boiler heats the house while the air conditioners carry on, or the
same room is heated and cooled at once.

Elke uitspraak van het anker staat hieronder als eigen klasse, geparametriseerd
over de vorm en niet over het ene voorbeeld: het gebied wordt samengevoegd op
`entity_id`, de stilgezette apparaten dragen `SHARED_SOURCE_TOOK_OVER`, een kamer
schuift niet door naar haar volgende bron, het buitenvenster van de overnemer is
voorwaardelijk, en de wachttijd telt vanaf het moment van uitvallen — met een
onbekend moment als "meteen".

Every statement of the anchor sits below as its own class, parameterised over
the shape rather than over the one example: the area is merged on `entity_id`,
the appliances stood down carry `SHARED_SOURCE_TOOK_OVER`, a room does not slide
on to its next source, the taker-over's outdoor window is conditional, and the
wait counts from the moment of dropping out — with an unknown moment meaning "at
once".
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from conftest import climate, make_world

from custom_components.climate_director.engine import (
    MODE_COOL,
    MODE_HEAT,
    MODE_OFF,
    DirectorConfig,
    ModeSettings,
    OutdoorWindow,
    Reason,
    Source,
    SourceRole,
    Zone,
    decide,
)
from custom_components.climate_director.engine import takeover as takeover_module

NOW = datetime(2026, 1, 15, 8, 0)

GAS = "climate.gas"
LIVING_AIRCO = "climate.living_airco"
ATTIC_AIRCO = "climate.attic_airco"
ATTIC_HEATER = "climate.attic_heater"

HEAT = ModeSettings(target=21.0, start_at=20.0, hysteresis=1.0)
COOL = ModeSettings(target=22.0, start_at=24.0, hysteresis=1.0)

#: De omslag gas/airco van deze installatie: de ketel onder 3,1 en de airco
#: erboven. / This installation's boiler/heat-pump split: the boiler below 3.1
#: and the air conditioner above it.
BELOW = OutdoorWindow(maximum=3.1)
ABOVE = OutdoorWindow(minimum=3.1)


def gas_source(
    source_id: str,
    *,
    covers: tuple[str, ...],
    delay: timedelta = timedelta(0),
    window: OutdoorWindow = BELOW,
) -> Source:
    """Return the boiler as a source, carrying the area it also serves."""
    return Source(
        source_id=source_id,
        entity_id=GAS,
        priority=1,
        role=SourceRole.HEAT_ONLY,
        outdoor=window,
        covers_zones=covers,
        takeover_delay=delay,
    )


def airco_source(source_id: str, entity_id: str, *, autostart: bool = True) -> Source:
    """Return an air conditioner as a source, above the changeover."""
    return Source(
        source_id=source_id,
        entity_id=entity_id,
        priority=0,
        role=SourceRole.HEAT_COOL,
        outdoor=ABOVE,
        autostart=autostart,
    )


def house(
    *,
    covers: tuple[str, ...] = ("living", "attic"),
    delay: timedelta = timedelta(0),
    window: OutdoorWindow = BELOW,
    attic_extra: tuple[Source, ...] = (),
    attic_autostart: bool = True,
    covers_on: str = "living",
) -> DirectorConfig:
    """Return two rooms sharing one boiler, each with its own air conditioner.

    `covers_on` zegt op wélke rij van de ketel het gebied ingevuld staat. Dat is
    de parameter waarmee het samenvoegen op `entity_id` te meten valt.

    `covers_on` says which of the boiler's rows carries the area. That is the
    parameter with which merging on `entity_id` can be measured.
    """
    living_gas = gas_source(
        "living_gas",
        covers=covers if covers_on == "living" else (),
        window=window,
        delay=delay,
    )
    attic_gas = gas_source(
        "attic_gas",
        covers=covers if covers_on == "attic" else (),
        window=window,
        delay=delay,
    )
    return DirectorConfig(
        zones=(
            Zone(
                zone_id="living",
                name="Living",
                indoor_sensor="sensor.living",
                sources=(airco_source("living_airco", LIVING_AIRCO), living_gas),
                heat=HEAT,
                cool=COOL,
            ),
            Zone(
                zone_id="attic",
                name="Attic",
                indoor_sensor="sensor.attic",
                sources=(
                    airco_source("attic_airco", ATTIC_AIRCO, autostart=attic_autostart),
                    *attic_extra,
                    attic_gas,
                ),
                heat=HEAT,
                cool=COOL,
                priority=1,
            ),
        )
    )


def world(
    *,
    attic_available: bool = False,
    outdoor: float = 8.0,
    living_indoor: float = 18.0,
    attic_indoor: float = 18.0,
    attic_mode: str = "off",
    changed_at: datetime | None = None,
    extra: dict[str, object] | None = None,
):
    """Return a world in which both rooms want heating and the attic dropped out."""
    climates: dict[str, object] = {
        GAS: climate("off"),
        LIVING_AIRCO: climate("off"),
        ATTIC_AIRCO: climate(attic_mode, available=attic_available, changed_at=changed_at),
    }
    climates.update(extra or {})
    return make_world(
        now=NOW,
        indoor={"living": living_indoor, "attic": attic_indoor},
        outdoor=outdoor,
        climates=climates,
    )


def modes(plan) -> dict[str, str]:
    """Return the commanded mode per appliance."""
    return {command.entity_id: command.hvac_mode for command in plan.commands}


def reasons(plan) -> dict[str, Reason]:
    """Return the commanded reason per appliance."""
    return {command.entity_id: command.reason for command in plan.commands}


class TestTheAreaIsMergedOnTheEntity:
    """Hetzelfde apparaat onder meerdere kamers deelt één gebied.

    The same appliance under several rooms shares one area.

    Dat is de uitspraak, en niet "het staat op de woonkamerrij": één keer
    invullen is genoeg, welke rij dat ook is.

    That is the statement, not "it sits on the living-room row": filling it in
    once is enough, whichever row that is.
    """

    @pytest.mark.parametrize("covers_on", ["living", "attic"])
    def test_one_row_carries_the_whole_area(self, covers_on: str) -> None:
        areas = takeover_module.areas(house(covers_on=covers_on))
        assert areas == {GAS: frozenset({"living", "attic"})}

    @pytest.mark.parametrize("covers_on", ["living", "attic"])
    def test_the_takeover_holds_over_the_whole_area(self, covers_on: str) -> None:
        found = takeover_module.in_force(house(covers_on=covers_on), world())
        assert [item.entity_id for item in found] == [GAS]
        assert found[0].zones == frozenset({"living", "attic"})

    def test_the_own_zone_of_every_row_belongs_to_the_area(self) -> None:
        """Leeg betekent alleen de eigen zone, dus die zone hoort er altijd bij.

        Noemt de woonkamerrij alléén de zolder, dan is de woonkamer nog steeds
        deel van het gebied: het apparaat bedient zijn eigen kamer sowieso. Zonder
        die regel zou het gebied kleiner zijn dan het apparaat werkelijk verwarmt.

        Empty means this zone only, so that zone always belongs. If the
        living-room row names the attic alone, the living room is still part of
        the area: the appliance serves its own room anyway. Without that rule the
        area would be smaller than what the appliance really heats.
        """
        areas = takeover_module.areas(house(covers=("attic",), covers_on="living"))
        assert areas == {GAS: frozenset({"living", "attic"})}

    def test_an_empty_area_never_takes_anything_over(self) -> None:
        """Leeg betekent alleen de eigen zone, dus deze uitzondering ontstaat niet."""
        assert takeover_module.in_force(house(covers=()), world()) == ()

    def test_an_unknown_zone_does_not_widen_the_area(self) -> None:
        """`validate()` meldt hem; stil meerekenen zou het gebied groter maken."""
        areas = takeover_module.areas(house(covers=("living", "kelder")))
        assert areas == {GAS: frozenset({"living", "attic"})}


class TestWhatStandsDownSaysWhy:
    """Wie door de overname stilvalt, draagt `SHARED_SOURCE_TOOK_OVER`.

    Whatever the takeover stands down carries `SHARED_SOURCE_TOOK_OVER`.

    Geparametriseerd over de twee vormen waarin een apparaat anders wél zou
    hebben geleverd: een gewone bron die zou koelen terwijl de ketel verwarmt, en
    een handbediend apparaat dat al draait. Allebei leveren ze warmte of koeling
    in een gebied dat de ketel al bedient.

    Parameterised over the two shapes in which an appliance would otherwise have
    delivered: an ordinary source that would cool while the boiler heats, and a
    hand-operated appliance already running. Both deliver heat or cooling in an
    area the boiler already serves.
    """

    def test_a_room_that_would_cool_is_stood_down(self) -> None:
        plan = decide(house(), world(living_indoor=26.0))
        assert modes(plan)[GAS] == MODE_HEAT
        assert modes(plan)[LIVING_AIRCO] == MODE_OFF
        assert reasons(plan)[LIVING_AIRCO] is Reason.SHARED_SOURCE_TOOK_OVER

    def test_a_hand_operated_appliance_is_stood_down_too(self) -> None:
        """Anker 12 noemt hem uitdrukkelijk: hij staat de natuurkunde in de weg."""
        config = house(attic_autostart=False)
        plan = decide(
            config,
            world(
                attic_available=True, attic_mode=MODE_COOL, extra={ATTIC_AIRCO: climate(MODE_COOL)}
            ),
        )
        # Niets is weggevallen, dus er is geen overname en de hand blijft staan.
        assert ATTIC_AIRCO not in modes(plan)

        plan = decide(
            config,
            world(
                attic_available=True,
                attic_mode=MODE_COOL,
                extra={
                    ATTIC_AIRCO: climate(MODE_COOL),
                    LIVING_AIRCO: climate("off", available=False),
                },
            ),
        )
        assert modes(plan)[GAS] == MODE_HEAT
        assert modes(plan)[ATTIC_AIRCO] == MODE_OFF
        assert reasons(plan)[ATTIC_AIRCO] is Reason.SHARED_SOURCE_TOOK_OVER

    def test_nothing_stands_down_while_the_taker_over_does_not_run(self) -> None:
        """Pas als de ketel werkelijk draait kan er tegelijk gestookt en gekoeld."""
        plan = decide(house(), world(living_indoor=26.0, attic_indoor=26.0, outdoor=30.0))
        assert modes(plan).get(GAS, MODE_OFF) == MODE_OFF
        assert modes(plan)[LIVING_AIRCO] == MODE_COOL

    def test_the_room_that_lost_its_source_keeps_reporting_it(self) -> None:
        """De zolder is overgenomen, maar meldt nog steeds wat er echt is."""
        plan = decide(house(), world())
        decision = plan.decision_for("attic")
        assert decision is not None
        assert "attic_airco" in decision.passed_over


class TestNoRoomSlidesOnToItsNextSource:
    """Een kamer in een overgenomen gebied schuift niet door.

    A room in a taken-over area does not slide on.

    Anders verwarmt die kamer alsnog elektrisch binnen een gebied dat de ketel al
    warm maakt. Geparametriseerd over waar de derde bron staat: op de kamer
    waarvan de bron wegviel, en op de kamer ernaast.

    Otherwise that room heats electrically after all, inside an area the boiler
    is already warming. Parameterised over where the third source sits: in the
    room whose source dropped out, and in the room next to it.
    """

    @staticmethod
    def _heater() -> Source:
        return Source(
            source_id="attic_heater",
            entity_id=ATTIC_HEATER,
            priority=0,
            role=SourceRole.HEAT_ONLY,
        )

    def test_the_electric_heater_does_not_take_over(self) -> None:
        config = house(attic_extra=(self._heater(),))
        plan = decide(config, world(extra={ATTIC_HEATER: climate("off")}))
        assert modes(plan)[GAS] == MODE_HEAT
        assert modes(plan)[ATTIC_HEATER] == MODE_OFF

    def test_without_an_area_the_heater_would_have_taken_over(self) -> None:
        """De tegenproef: zonder gebied doet de bronkeuze wat ze altijd deed."""
        config = house(covers=(), attic_extra=(self._heater(),))
        plan = decide(config, world(extra={ATTIC_HEATER: climate("off")}))
        assert modes(plan)[ATTIC_HEATER] == MODE_HEAT

    def test_a_room_outside_the_area_slides_on_as_ever(self) -> None:
        """Het anker geldt binnen het gebied, niet erbuiten.

        De zolder heeft de ketel hier helemaal niet als bron, en staat ook niet
        in zijn gebied. Dan doet de bronkeuze wat ze altijd deed. Let op de
        eigenschap die dit meteen laat zien: staat de ketel wél als bron onder
        de zolder, dan hoort die kamer per definitie bij zijn gebied — de eigen
        zone van élke rij telt mee, en dat is wat "leeg betekent alleen de eigen
        zone" samen met het samenvoegen op `entity_id` oplevert.

        The attic here does not have the boiler as a source at all, and is not in
        its area either. Then source selection does what it always did. Note the
        property this shows straight away: if the boiler does sit as a source
        under the attic, that room belongs to its area by definition — the own
        zone of every row counts, and that is what "empty means this zone only"
        plus merging on `entity_id` produces.
        """
        config = DirectorConfig(
            zones=(
                Zone(
                    zone_id="living",
                    name="Living",
                    indoor_sensor="sensor.living",
                    sources=(
                        airco_source("living_airco", LIVING_AIRCO),
                        gas_source("living_gas", covers=("living",)),
                    ),
                    heat=HEAT,
                    cool=COOL,
                ),
                Zone(
                    zone_id="attic",
                    name="Attic",
                    indoor_sensor="sensor.attic",
                    sources=(airco_source("attic_airco", ATTIC_AIRCO), self._heater()),
                    heat=HEAT,
                    cool=COOL,
                    priority=1,
                ),
            )
        )
        plan = decide(config, world(extra={ATTIC_HEATER: climate("off")}))
        assert modes(plan)[ATTIC_HEATER] == MODE_HEAT


class TestTheOutdoorWindowBecomesConditional:
    """Buiten zijn venster gaat de overnemer alsnog aan — en anders nooit.

    Outside its window the taker-over runs anyway — and otherwise never.

    Dit is een verbreding, dus de andere kant hoort er als eigen geval bij: in
    élke situatie waarin niets weggevallen is, geldt het venster gewoon.

    This is a widening, so the other side belongs here as its own case: in every
    situation where nothing dropped out, the window simply holds.
    """

    @pytest.mark.parametrize("outdoor", [3.1, 8.0, 18.0])
    def test_the_boiler_runs_outside_its_window_while_a_source_is_gone(
        self, outdoor: float
    ) -> None:
        plan = decide(house(), world(outdoor=outdoor))
        assert modes(plan)[GAS] == MODE_HEAT

    @pytest.mark.parametrize("outdoor", [3.1, 8.0, 18.0])
    def test_the_window_holds_while_nothing_is_gone(self, outdoor: float) -> None:
        plan = decide(house(), world(attic_available=True, outdoor=outdoor))
        assert modes(plan).get(GAS, MODE_OFF) == MODE_OFF

    @pytest.mark.parametrize("outdoor", [3.1, 8.0, 18.0])
    def test_an_empty_area_never_sets_the_window_aside(self, outdoor: float) -> None:
        plan = decide(house(covers=()), world(outdoor=outdoor))
        assert modes(plan).get(GAS, MODE_OFF) == MODE_OFF

    def test_inside_its_window_nothing_changes(self) -> None:
        plan = decide(house(), world(attic_available=True, outdoor=-5.0))
        assert modes(plan)[GAS] == MODE_HEAT


class TestTheWaitBeforeTakingOver:
    """De overname wacht vanaf het moment dat het apparaat onbereikbaar werd.

    The takeover waits from the moment the appliance became unreachable.

    Is dat moment onbekend, dan is er niets om op te wachten en gaat de overname
    meteen in. Dat is de scherpste kant van deze uitspraak, want een onbekend
    moment is precies wat een herstart oplevert.

    If that moment is unknown there is nothing to wait for and the takeover
    starts at once. That is the sharpest side of this statement, because an
    unknown moment is exactly what a restart produces.
    """

    @pytest.mark.parametrize(
        ("gone_for", "expected"),
        [
            pytest.param(timedelta(minutes=1), False, id="een_minuut"),
            pytest.param(timedelta(minutes=4, seconds=59), False, id="net_niet"),
            pytest.param(timedelta(minutes=5), True, id="precies"),
            pytest.param(timedelta(minutes=30), True, id="ruim"),
        ],
    )
    def test_the_wait_is_counted_from_the_drop_out(
        self, gone_for: timedelta, expected: bool
    ) -> None:
        config = house(delay=timedelta(minutes=5))
        found = takeover_module.in_force(config, world(changed_at=NOW - gone_for))
        assert bool(found) is expected

    def test_an_unknown_moment_takes_over_at_once(self) -> None:
        config = house(delay=timedelta(minutes=5))
        assert takeover_module.in_force(config, world(changed_at=None)) != ()

    def test_zero_takes_over_at_once(self) -> None:
        config = house(delay=timedelta(0))
        assert takeover_module.in_force(config, world(changed_at=NOW)) != ()

    def test_the_longest_wait_of_the_rows_carrying_the_area_wins(self) -> None:
        """Eén keer invullen is genoeg; de standaard van een lege rij wint niet."""
        config = house(covers_on="living", delay=timedelta(minutes=20))
        assert takeover_module.in_force(config, world(changed_at=NOW - timedelta(minutes=10))) == ()
        assert takeover_module.in_force(config, world(changed_at=NOW - timedelta(minutes=25))) != ()

    def test_the_wait_shows_in_the_plan(self) -> None:
        config = house(delay=timedelta(minutes=5))
        early = decide(config, world(changed_at=NOW - timedelta(minutes=1)))
        late = decide(config, world(changed_at=NOW - timedelta(minutes=6)))
        assert modes(early).get(GAS, MODE_OFF) == MODE_OFF
        assert modes(late)[GAS] == MODE_HEAT
