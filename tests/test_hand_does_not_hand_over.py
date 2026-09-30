"""Een hand zet een zone stil, maar draagt geen apparaat over (anker 11).

A hand silences a zone, but hands no appliance over (anchor 11).

Een hand aan het apparaat laat die zone vallen; de schakelaar en de actie
`set_override` nemen de hele zone over en dragen daarmee elk apparaat van die zone
huisbreed over. Een gedeeld apparaat dat naast de stilgevallen zone ook onder een
andere kamer hangt blijft dus voor die andere kamer beschikbaar - en dat is wat
deze toetsen vastleggen, met de schakelaar in dezelfde wereld als tegenproef.

A hand at the appliance drops that zone; the switch and the `set_override` action
take the whole zone over and with it hand every appliance of that zone over
house-wide. A shared appliance that hangs under another room as well as the
silenced zone therefore stays available to that other room - and that is what
these tests pin down, with the switch in the same world as the counter-test.
"""

from __future__ import annotations

from conftest import climate, make_world

from custom_components.climate_director.engine import (
    MODE_HEAT,
    DirectorConfig,
    ModeSettings,
    Plan,
    Reason,
    Source,
    SourceRole,
    Zone,
    decide,
)

HEAT = ModeSettings(target=21.0, start_at=20.0, hysteresis=1.0)
KETEL = "climate.ketel"
AIRCO = "climate.airco_zolder"


def installation() -> DirectorConfig:
    """Return two rooms on one boiler; the attic has an air conditioner too.

    Alleen de woonkamer hangt uitsluitend aan de ketel: zakt die weg, dan valt er
    voor die kamer niets meer te kiezen. De zolder kan zichzelf redden.

    Only the living room hangs on the boiler alone: when that drops out there is
    nothing left to choose for that room. The attic can fend for itself.
    """
    return DirectorConfig(
        zones=(
            Zone(
                "woonkamer",
                "Woonkamer",
                "sensor.woonkamer",
                sources=(Source("ketel", KETEL, role=SourceRole.HEAT_ONLY),),
                heat=HEAT,
            ),
            Zone(
                "zolder",
                "Zolder",
                "sensor.zolder",
                sources=(
                    Source("z_airco", AIRCO, role=SourceRole.HEAT_COOL),
                    Source("ketel", KETEL, role=SourceRole.HEAT_ONLY),
                ),
                heat=HEAT,
            ),
        ),
    )


def sitting_still(*, by_hand: bool):
    """Return a cold living room, a warm attic and a boiler that is off.

    De zolder is van de gebruiker; `by_hand` zegt hoe. Met de hand staat de zone
    alleen stil, met de schakelaar is ze overgedragen - het enige verschil tussen
    de twee werelden hier.

    The attic is the user's; `by_hand` says how. By hand the zone merely stands
    still, by the switch it is handed over - the only difference between the two
    worlds here.
    """
    return make_world(
        indoor={"woonkamer": 18.0, "zolder": 23.0},
        outdoor=5.0,
        climates={KETEL: climate("off"), AIRCO: climate("off")},
        zone_overrides={"zolder": True},
        zone_hands=frozenset({"zolder"}) if by_hand else frozenset(),
    )


def modes(plan: Plan) -> dict[str, str]:
    """Return the plan's commands keyed by appliance."""
    return {command.entity_id: command.hvac_mode for command in plan.commands}


class TestAHandLeavesTheSharedApplianceAvailable:
    """De hand laat de ketel met rust; de schakelaar neemt hem mee.

    The hand leaves the boiler alone; the switch takes it along.
    """

    def test_the_cold_room_heats_with_the_boiler(self) -> None:
        """De woonkamer is de enige die nog warmte vraagt en krijgt de ketel."""
        commands = modes(decide(installation(), sitting_still(by_hand=True)))
        assert commands[KETEL] == MODE_HEAT

    def test_the_silenced_room_itself_is_left_alone(self) -> None:
        """Stilvallen geldt nog steeds voor de zone waarin de hand zat.

        De airco staat al uit en blijft dat: de zone is van de gebruiker, dus de
        director stuurt hem niets - ook geen `off`. Precies zoals een hand aan het
        apparaat bedoeld is, en precies zoals de zone het zelf aangaf.

        Standing still still holds for the zone the hand was in. The air
        conditioner is already off and stays off: the zone is the user's, so the
        director sends it nothing - not even an `off`. Exactly what a hand at the
        appliance is meant to do, and exactly what the zone said itself.
        """
        plan = decide(installation(), sitting_still(by_hand=True))
        assert AIRCO not in modes(plan)
        assert (AIRCO, Reason.MANUAL_OVERRIDE) in {
            (item.entity_id, item.reason) for item in plan.untouched
        }

    def test_the_switch_does_hand_the_boiler_over(self) -> None:
        """De tegenproef: dezelfde wereld, maar de zone is overgedragen.

        The counter-test: the same world, but the zone is handed over.
        """
        plan = decide(installation(), sitting_still(by_hand=False))
        assert KETEL not in modes(plan)
        assert plan.decision_for("woonkamer") is not None
        assert plan.decision_for("woonkamer").reason is Reason.NO_SOURCE_AVAILABLE
