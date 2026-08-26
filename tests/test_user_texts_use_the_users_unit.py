"""G1: elke tekst voor de gebruiker die een temperatuur noemt, noemt zijn eenheid.

G1: every user-facing text naming a temperature names its unit.

De derde ronde op rij dat "alles naar de gebruiker in de eenheid van de gebruiker"
één plek verderop terugkwam. Dit bestand is de inventarisatielijst: drie plekken,
elk geparametriseerd over metriek en imperiaal, en elke plek hoort rood te worden
zodra iemand de omrekening terugdraait.

The third round in a row in which "everything toward the user in the user's unit"
came back one place further on. This file is the inventory list: three places,
each parametrised over metric and imperial, and each place should go red the
moment somebody reverts its conversion.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest
from conftest import make_world
from harness_live import LiveHome, settings, source, start_house, stop_house, zone
from homeassistant.helpers import issue_registry as ir
from homeassistant.util.unit_system import IMPERIAL_SYSTEM, METRIC_SYSTEM

from custom_components.climate_director import texts
from custom_components.climate_director.const import DOMAIN
from custom_components.climate_director.coordinator import ClimateDirectorCoordinator, _wanted
from custom_components.climate_director.engine import (
    DirectorConfig,
    GateSettings,
    ModeSettings,
    Opening,
    OpeningState,
    Season,
    Source,
    Zone,
)
from custom_components.climate_director.engine.diff import Change
from custom_components.climate_director.engine.plan import UnitCommand

LIVING = "climate.woonkamer"


def issue_for(live: LiveHome, key: str):
    """Return the issue carrying `key` for this installation, if it stands."""
    registry = ir.async_get(live.hass)
    return registry.async_get_issue(DOMAIN, f"{key}_{live.entry.entry_id}")


class TestTheCommandNotTakingNotice:
    """Plek A: `coordinator._wanted` — de melding `command_not_taking`."""

    @pytest.mark.parametrize(
        ("unit", "temperature", "expected"),
        [
            ("°F", 21.0, "heat, 70.0 °F"),
            # Een installatie die ooit in Fahrenheit was ingericht bewaart
            # 21,111... °C; de melding hoort dat af te ronden, niet te lekken.
            # An installation once set up in Fahrenheit stores 21.111... °C;
            # the notice should round that, not leak it.
            ("°C", 21.11111111111111, "heat, 21.1 °C"),
        ],
    )
    def test_the_notice_names_the_unit(self, unit: str, temperature: float, expected: str) -> None:
        change = Change(
            UnitCommand(LIVING, "heat", temperature=temperature),
            set_mode=True,
            set_temperature=True,
        )
        assert _wanted(change, unit) == expected

    def test_a_change_without_a_setpoint_names_only_the_mode(self) -> None:
        change = Change(UnitCommand(LIVING, "heat"), set_mode=True, set_temperature=False)
        assert _wanted(change, "°F") == "heat"


class TestTheValidationComplaint:
    """Plek B: `target_outside_band` — placeholders blijven Celsius in de engine,
    `problems.readable` rekent ze om."""

    def _installation(self) -> dict[str, Any]:
        # Streven 19 onder aanpunt 20: verwarmen begint en doet dan niets.
        # Target 19 below switch-on 20: heating starts and then does nothing.
        return {
            "zones": [
                zone(
                    "woonkamer",
                    sources=[source("woonkamer_airco", LIVING, role="heat_cool")],
                    indoor_sensor="sensor.woonkamer",
                    heat=settings(19.0, 20.0),
                )
            ],
            "outdoor_sensor": "sensor.buiten",
        }

    @pytest.mark.parametrize(
        ("unit_system", "unit", "expected_parts"),
        [
            (IMPERIAL_SYSTEM, "°F", ("68.0 °F", "66.0 °F")),
            (METRIC_SYSTEM, "°C", ("20.0 °C", "19.0 °C")),
        ],
    )
    async def test_the_complaint_names_the_unit(
        self, unit_system, unit: str, expected_parts: tuple[str, str]
    ) -> None:
        live = await start_house(
            self._installation(),
            states={
                "sensor.woonkamer": ("68.0", {"unit_of_measurement": unit}),
                "sensor.buiten": ("40.0", {"unit_of_measurement": unit}),
                LIVING: ("off", {"hvac_modes": ["heat", "cool", "off"]}),
            },
            unit_system=unit_system,
        )
        try:
            issue = issue_for(live, "invalid_config")
            assert issue is not None
            placeholders = issue.translation_placeholders or {}
            for part in expected_parts:
                assert part in placeholders["problems"], placeholders["problems"]
        finally:
            await stop_house(live)


class TestThePhoneSentence:
    """Plek C: `coordinator._refusal_data` — de zin die met een vooruit-verzoek
    meegaat en via de blueprint op de telefoon belandt."""

    def _coordinator(self, unit: str, indoor: float = 15.0):
        attic = "climate.zolder"
        window = "binary_sensor.dakraam"
        noon = datetime(2026, 8, 18, 12, 0)

        class State:
            name = "Dakraam"

        class Registry:
            def get(self, entity_id: str):
                return State() if entity_id == window else None

        class Config:
            language = "en"

        class Hass:
            states = Registry()
            config = Config()

        class Entry:
            entry_id = "abc"

        class StandIn:
            def __init__(self) -> None:
                self.config = DirectorConfig(
                    zones=(
                        Zone(
                            "zolder",
                            "Zolder",
                            "sensor.zolder",
                            sources=(Source("z", attic),),
                            heat=ModeSettings(target=21.0, start_at=20.0),
                            cool=ModeSettings(target=23.0, start_at=24.0),
                        ),
                    ),
                    openings=(Opening(entity_id=window),),
                    gates=GateSettings(max_precondition=timedelta(hours=2)),
                )
                self.hass = Hass()
                self.config_entry = Entry()
                self.data = None
                self.temperature_unit = unit
                self._precondition = {"zolder": noon + timedelta(hours=1)}
                self.world = make_world(
                    now=noon,
                    outdoor=8.0,
                    indoor={} if indoor is None else {"zolder": indoor},
                    climates={attic: "off"},
                    openings={window: OpeningState(open=True, changed_at=None)},
                )

            _refusal_data = ClimateDirectorCoordinator._refusal_data
            _friendly = ClimateDirectorCoordinator._friendly
            _open_openings = ClimateDirectorCoordinator._open_openings

            def refusal_data(self, zone_id: str):
                return self._refusal_data(zone_id, self.data)

        return StandIn()

    @pytest.fixture(autouse=True)
    def _without_translations(self, monkeypatch: pytest.MonkeyPatch):
        """Keep the English fallback in place, since a stand-in has no cache."""
        monkeypatch.setattr(texts, "lookup", lambda hass, code: None)

    @pytest.mark.parametrize(
        ("unit", "expected"),
        [
            ("°F", "Now 59.0 °F, aiming for 70.0 °F."),
            ("°C", "Now 15.0 °C, aiming for 21.0 °C."),
        ],
    )
    def test_the_sentence_names_the_unit(self, unit: str, expected: str) -> None:
        data = self._coordinator(unit).refusal_data("zolder")
        assert expected in data["confirmed_message"]

    def test_the_satisfied_sentence_names_the_unit_too(self) -> None:
        """Alleen `{indoor}` komt voorbij; ook die hoort zijn eenheid te noemen."""
        data = self._coordinator("°F", indoor=21.5).refusal_data("zolder")
        assert "Now 71.0 °F" in data["confirmed_message"]

    def test_the_idle_sentence_names_the_unit_too(self) -> None:
        """De idlekant noemt hetzelfde getal, in dezelfde eenheid."""
        attic = "climate.zolder"
        window = "binary_sensor.dakraam"
        item = self._coordinator("°F", indoor=15.0)
        item.config = DirectorConfig(
            zones=(
                Zone(
                    "zolder",
                    "Zolder",
                    "sensor.zolder",
                    sources=(Source("z", attic),),
                    cool=ModeSettings(
                        target=23.0, start_at=24.0, seasons=frozenset({Season.SUMMER})
                    ),
                ),
            ),
            openings=(Opening(entity_id=window),),
            gates=GateSettings(max_precondition=timedelta(hours=2)),
        )
        data = item.refusal_data("zolder")
        assert "Now 59.0 °F" in data["confirmed_message"]
