"""Een exclusieve groep gaat over apparaten, niet over bron-ID's.

An exclusive group is about appliances, not about source ids.

Een groep wordt opgeslagen als een rijtje bron-ID's, want zo kiest de gebruiker
ze ook: het scherm toont "Woonkamer - climate.ketel". Maar hetzelfde apparaat
staat vaak onder meerdere kamers, en dan heeft het per kamer een eigen bron-ID.
Wie er dan één aanvinkt, denkt klaar te zijn - en de andere kamer start
hetzelfde apparaat gewoon, buiten de groep om.

Dat is stil: de controlelijst blijft leeg, de buitengrenzen kloppen, en de
gasketel en de warmtepomp draaien samen precies zoals de groep had moeten
voorkomen.

A group is stored as a list of source ids, since that is how the user picks
them: the screen shows "Living room - climate.ketel". But the same appliance
often sits under several rooms, and then it has a source id per room. Tick one
of them and you think you are done - while the other room simply starts that
same appliance, right past the group.

That is silent: the problem list stays empty, the outdoor bounds are right, and
the boiler and the heat pump run together exactly as the group should have
prevented.
"""

from __future__ import annotations

from datetime import datetime

from conftest import awake, make_world

from custom_components.climate_director.engine import (
    DirectorConfig,
    ModeFamily,
    ModeSettings,
    OutdoorWindow,
    Reason,
    Resident,
    Source,
    SourceRole,
    Zone,
    decide,
    validate,
)
from custom_components.climate_director.engine.families import family_of

NOON = datetime(2026, 3, 9, 12, 0)

AIRCO = "climate.woonkamer_airco"
BOILER = "climate.ketel"
ATTIC = "climate.zolder_airco"

WARM = ModeSettings(21.0, 20.0)


def shared_boiler() -> DirectorConfig:
    """Return two rooms sharing one boiler, with only one of the two in the group."""
    return DirectorConfig(
        zones=(
            Zone(
                "woonkamer",
                "Woonkamer",
                "sensor.woonkamer",
                priority=0,
                sources=(
                    Source(
                        "woonkamer_airco",
                        AIRCO,
                        role=SourceRole.HEAT_COOL,
                        priority=0,
                        outdoor=OutdoorWindow(minimum=3.1),
                    ),
                    Source(
                        "gas_woonkamer",
                        BOILER,
                        role=SourceRole.HEAT_ONLY,
                        priority=1,
                        outdoor=OutdoorWindow(maximum=3.1),
                    ),
                ),
                heat=WARM,
            ),
            Zone(
                "keuken",
                "Keuken",
                "sensor.keuken",
                priority=1,
                # Dezelfde ketel, eigen bron-ID, en geen buitengrens.
                sources=(Source("gas_keuken", BOILER, role=SourceRole.HEAT_ONLY),),
                heat=WARM,
            ),
        ),
        # De gebruiker vinkte de ketel aan zoals hij bij de woonkamer staat.
        exclusive_groups=(frozenset({"woonkamer_airco", "gas_woonkamer"}),),
        residents=(Resident("danny", presence_entity="person.danny"),),
        outdoor_sensor="sensor.buiten",
    )


def cold(config: DirectorConfig, outdoor: float):
    world = make_world(
        now=NOON,
        outdoor=outdoor,
        indoor={zone.zone_id: 15.0 for zone in config.zones},
        climates={AIRCO: "off", BOILER: "off", ATTIC: "off"},
        residents={"danny": awake()},
    )
    return world, decide(config, world)


def running(plan) -> dict[str, str]:
    """Return the appliances this plan puts to work."""
    return {
        command.entity_id: command.hvac_mode
        for command in plan.commands
        if family_of(command.hvac_mode) in (ModeFamily.HEAT, ModeFamily.COOL)
    }


class TestTheGroupCoversTheAppliance:
    def test_the_configuration_is_sound(self) -> None:
        assert not validate(shared_boiler())

    def test_only_one_of_them_runs(self) -> None:
        """Bij 10 graden mag de airco en mag de ketel van de woonkamer niet."""
        _world, plan = cold(shared_boiler(), 10.0)
        assert len(running(plan)) <= 1, running(plan)

    def test_the_heat_pump_wins_on_priority(self) -> None:
        _world, plan = cold(shared_boiler(), 10.0)
        assert running(plan) == {AIRCO: "heat"}

    def test_the_kitchen_hears_why(self) -> None:
        _world, plan = cold(shared_boiler(), 10.0)
        decision = plan.decision_for("keuken")
        assert decision is not None
        assert decision.granted is ModeFamily.NEUTRAL
        assert decision.reason is Reason.EXCLUSIVE_GROUP_LOST

    def test_below_the_cutover_the_boiler_serves_both(self) -> None:
        """Eén apparaat voor twee kamers is één apparaat: de groep heeft geen bezwaar."""
        _world, plan = cold(shared_boiler(), 0.0)
        assert running(plan) == {BOILER: "heat"}

    def test_both_rooms_are_served_by_it(self) -> None:
        _world, plan = cold(shared_boiler(), 0.0)
        granted = {zone.zone_id for zone in plan.zones if zone.granted is not ModeFamily.NEUTRAL}
        assert granted == {"woonkamer", "keuken"}


class TestTheOverlapWarningIsGone:
    """De controle waarschuwde op precies het voorbeeld dat het scherm aanraadt.

    The check warned about exactly the example the screen recommends.

    "Zet de gasketel en de warmtepompen bij elkaar", zegt de tekst bij het
    scherm. Doe je dat met twee warmtepompen, dan overlappen die twee elkaars
    buitengrens - ze mogen allebei boven dezelfde omslag - en kwam er een
    reparatiemelding met het advies om ze aansluitende grenzen te geven. Dat
    advies maakt de groep juist zinloos: hij bestaat om te kiezen tussen
    apparaten die elkaar wél kunnen tegenkomen.

    De eigen testset moest die melding al wegfilteren met de opmerking "dat is
    hier de bedoeling". Dan is het geen waarschuwing meer maar ruis.

    "Put the gas boiler and the heat pumps together", says the text beside the
    screen. Do that with two heat pumps and their outdoor bounds overlap - both
    are allowed above the same changeover - and a repair notice arrived advising
    you to give them adjacent bounds. That advice is what makes the group
    pointless: it exists to choose between appliances that can meet.

    The test suite already had to filter that notice out with the remark "that
    is the point here". At which point it is no longer a warning but noise.
    """

    @staticmethod
    def _pumps_and_a_boiler() -> DirectorConfig:
        def pump(source_id: str, entity_id: str, zone_id: str, priority: int) -> Zone:
            return Zone(
                zone_id,
                zone_id.title(),
                f"sensor.{zone_id}",
                priority=priority,
                sources=(
                    Source(
                        source_id,
                        entity_id,
                        role=SourceRole.HEAT_COOL,
                        outdoor=OutdoorWindow(minimum=3.1),
                    ),
                ),
                heat=WARM,
            )

        living = pump("woonkamer_airco", AIRCO, "woonkamer", 0)
        living = Zone(
            living.zone_id,
            living.name,
            living.indoor_sensor,
            priority=0,
            sources=(
                *living.sources,
                Source(
                    "gasketel",
                    BOILER,
                    role=SourceRole.HEAT_ONLY,
                    priority=1,
                    outdoor=OutdoorWindow(maximum=3.1),
                ),
            ),
            heat=WARM,
        )
        return DirectorConfig(
            zones=(living, pump("zolder_airco", ATTIC, "zolder", 1)),
            exclusive_groups=(frozenset({"gasketel", "woonkamer_airco", "zolder_airco"}),),
            residents=(Resident("danny", presence_entity="person.danny"),),
            outdoor_sensor="sensor.buiten",
        )

    def test_the_documented_example_is_sound(self) -> None:
        assert not validate(self._pumps_and_a_boiler())

    def test_two_plain_air_conditioners_are_sound(self) -> None:
        """De gewone reden voor een groep: twee apparaten aan dezelfde meterkast."""
        config = DirectorConfig(
            zones=(
                Zone(
                    "woonkamer",
                    "Woonkamer",
                    "sensor.woonkamer",
                    priority=0,
                    sources=(Source("woon", AIRCO),),
                    heat=WARM,
                ),
                Zone(
                    "zolder",
                    "Zolder",
                    "sensor.zolder",
                    priority=1,
                    sources=(Source("zolder", ATTIC),),
                    heat=WARM,
                ),
            ),
            exclusive_groups=(frozenset({"woon", "zolder"}),),
            residents=(Resident("danny", presence_entity="person.danny"),),
        )
        assert not validate(config)

    def test_it_still_rules_them_out(self) -> None:
        """Geen waarschuwing betekent niet dat de groep niets doet."""
        config = self._pumps_and_a_boiler()
        _world, plan = cold(config, 10.0)
        assert len(running(plan)) == 1, running(plan)

    def test_an_unknown_source_is_still_reported(self) -> None:
        """De controle die er wél toe doet, blijft staan."""
        config = self._pumps_and_a_boiler()
        broken = DirectorConfig(
            zones=config.zones,
            exclusive_groups=(frozenset({"gasketel", "bestaatniet"}),),
            residents=config.residents,
            outdoor_sensor=config.outdoor_sensor,
        )
        assert any("unknown source" in str(item) for item in validate(broken))
