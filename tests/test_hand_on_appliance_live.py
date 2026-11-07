"""De hand aan het apparaat in een echte Home Assistant.

The hand at the appliance inside a real Home Assistant."""

from __future__ import annotations

import pytest
from harness_live import settings, source, start_house, stop_house, zone
from live_helpers import LIVING, handed_back


class TestAHandOnTheAppliance:
    """Zelf uitzetten geeft de kamer terug tot de volgende dag.

    Switching off yourself hands the room back until the next day.
    """

    async def test_switching_it_off_by_hand_silences_the_zone(self) -> None:
        installation = {
            "zones": [
                zone(
                    "woonkamer",
                    sources=[source("airco", LIVING, role="heat_cool")],
                    heat=settings(21.0, 20.0),
                )
            ],
            "residents": [
                {
                    "resident_id": "danny",
                    "presence_entity": "person.danny",
                    "sleep_entity": "sensor.danny_lader",
                    "sleep_state": "wireless",
                }
            ],
        }
        home = await start_house(
            installation,
            states={
                "sensor.woonkamer": ("18.0", {}),
                LIVING: ("off", {}),
                "person.danny": ("home", {}),
                "sensor.danny_lader": ("none", {}),
            },
        )
        try:
            assert home.state(LIVING) == "heat"

            # Iemand drukt bij het apparaat zelf op uit.
            # Somebody presses off on the appliance itself.
            home.climate(LIVING, "off")
            await home.settle()
            await home.evaluate()

            assert home.state(LIVING) == "off", "de director hoort dat niet te overrulen"
            assert home.value(f"command_{LIVING}") == "left_alone"
            assert home.values(f"command_{LIVING}")["reason"] == "manual_override"

            # En weer aanzetten laat hem gewoon meedoen.
            # And switching it back on has it join in again.
            home.climate(LIVING, "heat")
            await home.settle()
            await home.evaluate()
            assert handed_back(home) == set()
        finally:
            await stop_house(home)

    @pytest.mark.parametrize("gone", ["unavailable", "unknown"])
    async def test_an_appliance_dropping_out_and_back_is_not_a_hand(self, gone: str) -> None:
        """Wegvallen en terugkomen mag geen zone stilleggen.

        Een apparaat dat terugkomt meldt eerst `off`, en dat lijkt sprekend op
        iemand die net op uit drukte. Bij een herstart van Home Assistant komt
        elk apparaat zo langs, dus dit hoort echt niet mee te tellen.

        Dropping out and coming back may not silence a zone. An appliance coming
        back reports `off` first, and that looks exactly like somebody having
        just pressed off. On a restart of Home Assistant every appliance passes
        through this, so it really must not count.
        """
        installation = {
            "zones": [
                zone(
                    "woonkamer",
                    sources=[source("airco", LIVING, role="heat_cool")],
                    heat=settings(21.0, 20.0),
                )
            ]
        }
        home = await start_house(
            installation, states={"sensor.woonkamer": ("18.0", {}), LIVING: ("off", {})}
        )
        try:
            assert home.state(LIVING) == "heat"

            home.set(LIVING, gone)
            await home.settle()
            assert handed_back(home) == set(), "wegvallen is geen hand aan het apparaat"

            home.climate(LIVING, "off")
            await home.settle()
            assert handed_back(home) == set(), "terugkomen is dat evenmin"

            await home.evaluate()
            assert home.state(LIVING) == "heat", "de kamer hoort gewoon weer geregeld te worden"
        finally:
            await stop_house(home)

    @pytest.mark.parametrize("gone", ["unavailable", "unknown"])
    async def test_dropping_out_does_not_lift_a_hand_back(self, gone: str) -> None:
        """Een zone die met de hand is stilgezet blijft dat, ook als het apparaat wegvalt.

        A zone silenced by hand stays that way, even when the appliance drops out.
        """
        installation = {
            "zones": [
                zone(
                    "woonkamer",
                    sources=[source("airco", LIVING, role="heat_cool")],
                    heat=settings(21.0, 20.0),
                )
            ]
        }
        home = await start_house(
            installation, states={"sensor.woonkamer": ("18.0", {}), LIVING: ("off", {})}
        )
        try:
            home.climate(LIVING, "off")
            await home.settle()
            assert handed_back(home) == {"woonkamer"}

            home.set(LIVING, gone)
            await home.settle()
            assert handed_back(home) == {"woonkamer"}
        finally:
            await stop_house(home)

    async def test_in_shadow_mode_nothing_counts_as_a_hand(self) -> None:
        """Meelopen mag het vergelijken niet stilleggen.

        In schaduwmodus stuurt de director niets en zetten de bestaande
        automatiseringen de apparaten aan en uit. Zou elke uitzetting als een
        hand tellen, dan is elke zone binnen een dag overgedragen en meldt de
        integratie niets meer - terwijl dat melden het enige is wat deze modus
        oplevert.

        Running along may not silence the comparison. In shadow mode the
        director steers nothing and the existing automations switch the
        appliances on and off. Were every switch-off to count as a hand, every
        zone would be handed over within a day and the integration would report
        nothing - while that reporting is all this mode yields.
        """
        installation = {
            "zones": [
                zone(
                    "woonkamer",
                    sources=[source("airco", LIVING, role="heat_cool")],
                    heat=settings(21.0, 20.0),
                )
            ]
        }
        home = await start_house(
            installation,
            states={"sensor.woonkamer": ("18.0", {}), LIVING: ("heat", {})},
            shadow=True,
        )
        try:
            assert home.coordinator.data.command_for(LIVING).hvac_mode == "heat"

            # Een bestaande automatisering zet het apparaat uit.
            # An existing automation switches the appliance off.
            home.climate(LIVING, "off")
            await home.settle()
            assert handed_back(home) == set()

            await home.evaluate()
            command = home.coordinator.data.command_for(LIVING)
            assert command is not None and command.hvac_mode == "heat", (
                "de director hoort te blijven melden wat hij gedaan zou hebben"
            )
            assert home.value("mismatch") == "1"
            assert home.climate_calls() == [], "en er mag nog steeds niets gestuurd worden"
        finally:
            await stop_house(home)

    async def test_our_own_switch_off_is_not_a_hand(self) -> None:
        installation = {
            "zones": [
                zone(
                    "woonkamer",
                    sources=[source("airco", LIVING, role="heat_cool")],
                    heat=settings(21.0, 20.0),
                )
            ],
            "residents": [
                {
                    "resident_id": "danny",
                    "presence_entity": "person.danny",
                    "sleep_entity": "sensor.danny_lader",
                    "sleep_state": "wireless",
                }
            ],
        }
        home = await start_house(
            installation,
            states={
                "sensor.woonkamer": ("18.0", {}),
                LIVING: ("off", {}),
                "person.danny": ("home", {}),
                "sensor.danny_lader": ("none", {}),
            },
        )
        try:
            assert home.state(LIVING) == "heat"
            home.set("sensor.woonkamer", "23.0")
            await home.evaluate()
            await home.settle()
            assert home.state(LIVING) == "off"
            assert handed_back(home) == set(), "ons eigen uitzetten mag de zone niet stilleggen"

            home.set("sensor.woonkamer", "18.0")
            await home.evaluate()
            assert home.state(LIVING) == "heat"
        finally:
            await stop_house(home)
