"""Zones die op de kamer draaien in plaats van op het huishouden.

Zones that run on the room rather than on the household.

Niet elke ruimte hoort aan hetzelfde touwtje. Een woonkamer volgt het ritme van
het huishouden: een rooster, wie er slaapt, wie er thuis is. Een zolderkamer
volgt of er iemand zit, en verder niets. Dit bestand schrijft dat verschil uit,
en vooral wat er níet verandert: de hoofdschakelaar, een handmatige override en
een openstaand raam gaan niet over mensen en blijven dus altijd gelden.

Not every room hangs on the same string. A living room follows the rhythm of the
household: a schedule, who is asleep, who is home. An attic room follows whether
somebody is sitting in it, and nothing else. This file writes out that
difference, and above all what does not change: the master switch, a manual
override and an open window are not about people and therefore always apply.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest
from conftest import asleep, awake, away, gate_verdict, make_world

from custom_components.climate_director.engine import (
    DirectorConfig,
    GateSettings,
    ModeSettings,
    Opening,
    Reason,
    Resident,
    Source,
    TimeWindow,
    Zone,
    ZoneGate,
    validate,
)
from custom_components.climate_director.engine.serialise import config_from_dict, config_to_dict
from custom_components.climate_director.engine.world import OpeningState, PresenceState

#: Dinsdag 11 augustus 2026, buiten elk rooster in dit bestand.
#: Tuesday 11 August 2026, outside every schedule in this file.
LATE = datetime(2026, 8, 11, 23, 30)
MIDDAY = datetime(2026, 8, 11, 12, 0)

DANNY = Resident(
    "danny",
    "Danny",
    windows=(TimeWindow(time(6, 0), time(22, 0)),),
    presence_entity="person.danny",
    sleep_entity="sensor.danny_charger_type",
    sleep_state="wireless",
)


def house(**zone_kwargs: object) -> DirectorConfig:
    """Return a house with a scheduled living room and an attic on presence."""
    return DirectorConfig(
        zones=(
            Zone(
                "woonkamer",
                "Woonkamer",
                "sensor.woonkamer",
                sources=(Source("w", "climate.huiskamer"),),
                heat=ModeSettings(21.0, 20.0),
            ),
            Zone(
                "zolder",
                "Zolder",
                "sensor.zolder",
                sources=(Source("z", "climate.zolder"),),
                heat=ModeSettings(21.0, 20.0),
                gate=ZoneGate.PRESENCE,
                presence_entity="binary_sensor.zolder",
                **zone_kwargs,  # type: ignore[arg-type]
            ),
        ),
        residents=(DANNY,),
        openings=(Opening("binary_sensor.raam", zone_ids=("zolder",)),),
        gates=GateSettings(require_schedule=True),
    )


def verdict(config: DirectorConfig, zone_id: str, **kwargs: object):
    zone = config.zone(zone_id)
    assert zone is not None
    return gate_verdict(config, make_world(**kwargs), zone)  # type: ignore[arg-type]


def occupied(state: bool = True, **extra: object) -> dict[str, PresenceState]:
    return {"zolder": PresenceState(occupied=state, **extra)}  # type: ignore[arg-type]


class TestPresenceOverrulesTheSchedule:
    """The whole point: somebody in the room beats any schedule."""

    def test_the_attic_runs_outside_the_schedule(self) -> None:
        result = verdict(
            house(),
            "zolder",
            now=LATE,
            residents={"danny": awake()},
            presence=occupied(),
        )
        assert result.allowed

    def test_the_living_room_does_not(self) -> None:
        """Same moment, same house: the scheduled zone stays shut."""
        result = verdict(
            house(),
            "woonkamer",
            now=LATE,
            residents={"danny": awake()},
            presence=occupied(),
        )
        assert result.reason is Reason.OUTSIDE_SCHEDULE

    def test_it_runs_while_the_residents_are_out(self) -> None:
        """The sensor says somebody is up there, and it is right."""
        result = verdict(
            house(), "zolder", now=MIDDAY, residents={"danny": away()}, presence=occupied()
        )
        assert result.allowed

    def test_it_runs_while_the_residents_sleep(self) -> None:
        """Whoever is in the attic at half past eleven is not the one asleep."""
        result = verdict(
            house(), "zolder", now=LATE, residents={"danny": asleep()}, presence=occupied()
        )
        assert result.allowed

    def test_an_empty_attic_never_runs(self) -> None:
        """Even at noon, with everybody home, awake and inside the schedule."""
        result = verdict(
            house(),
            "zolder",
            now=MIDDAY,
            residents={"danny": awake()},
            presence=occupied(False),
        )
        assert result.reason is Reason.ZONE_UNOCCUPIED

    def test_an_unread_sensor_counts_as_empty(self) -> None:
        """No reading is not the same as somebody being there."""
        result = verdict(house(), "zolder", now=MIDDAY, residents={"danny": awake()})
        assert result.reason is Reason.ZONE_UNOCCUPIED


class TestWhatStillApplies:
    """Presence overrules the household, never the house itself."""

    def test_the_master_switch(self) -> None:
        result = verdict(
            house(),
            "zolder",
            now=MIDDAY,
            residents={"danny": awake()},
            presence=occupied(),
            master_enabled=False,
        )
        assert result.reason is Reason.MASTER_DISABLED

    def test_a_manual_override(self) -> None:
        result = verdict(
            house(),
            "zolder",
            now=MIDDAY,
            residents={"danny": awake()},
            presence=occupied(),
            zone_overrides={"zolder": True},
        )
        assert result.reason is Reason.MANUAL_OVERRIDE

    def test_an_open_window(self) -> None:
        result = verdict(
            house(),
            "zolder",
            now=MIDDAY,
            residents={"danny": awake()},
            presence=occupied(),
            openings={"binary_sensor.raam": OpeningState(open=True, changed_at=None)},
        )
        assert result.reason is Reason.OPENING_OPEN

    def test_the_grace_period(self) -> None:
        """Presence sensors flicker, so the room stays warm a little longer."""
        config = house(presence_timeout=timedelta(seconds=120))
        just_left = {
            "zolder": PresenceState(occupied=False, changed_at=MIDDAY - timedelta(seconds=30))
        }
        long_gone = {
            "zolder": PresenceState(occupied=False, changed_at=MIDDAY - timedelta(seconds=300))
        }
        assert verdict(
            config, "zolder", now=MIDDAY, residents={"danny": awake()}, presence=just_left
        ).allowed
        assert not verdict(
            config, "zolder", now=MIDDAY, residents={"danny": awake()}, presence=long_gone
        ).allowed


class TestTheTwoKindsLiveTogether:
    """One house, two rooms, two different answers at the same instant."""

    @pytest.mark.parametrize(
        ("moment", "living_room", "attic"),
        [
            (MIDDAY, True, True),
            (LATE, False, True),
        ],
    )
    def test_each_zone_is_judged_on_its_own(
        self, moment: datetime, living_room: bool, attic: bool
    ) -> None:
        config = house()
        world = dict(now=moment, residents={"danny": awake()}, presence=occupied())
        assert verdict(config, "woonkamer", **world).allowed is living_room  # type: ignore[arg-type]
        assert verdict(config, "zolder", **world).allowed is attic  # type: ignore[arg-type]


class TestConfiguringItWrongly:
    def test_presence_without_a_sensor_is_reported(self) -> None:
        config = DirectorConfig(
            zones=(
                Zone(
                    "zolder",
                    "Zolder",
                    "sensor.zolder",
                    sources=(Source("z", "climate.zolder"),),
                    heat=ModeSettings(21.0, 20.0),
                    gate=ZoneGate.PRESENCE,
                ),
            )
        )
        assert any("can never run" in item for item in validate(config))

    def test_with_a_sensor_it_is_sound(self) -> None:
        assert not any("can never run" in item for item in validate(house()))

    def test_the_household_default_needs_no_sensor(self) -> None:
        config = DirectorConfig(
            zones=(
                Zone(
                    "woonkamer",
                    "Woonkamer",
                    "sensor.woonkamer",
                    sources=(Source("w", "climate.huiskamer"),),
                    heat=ModeSettings(21.0, 20.0),
                ),
            )
        )
        assert not any("can never run" in item for item in validate(config))


class TestItSurvivesStorage:
    def test_the_choice_round_trips(self) -> None:
        config = house()
        assert config_from_dict(config_to_dict(config)) == config

    def test_older_options_default_to_the_household(self) -> None:
        """Configurations stored before this setting existed must not change meaning."""
        config = config_from_dict({"zones": [{"zone_id": "z", "indoor_sensor": "sensor.z"}]})
        assert config.zones[0].gate is ZoneGate.HOUSEHOLD

    def test_an_unknown_value_falls_back_to_the_household(self) -> None:
        config = config_from_dict(
            {"zones": [{"zone_id": "z", "indoor_sensor": "sensor.z", "gate": "verzonnen"}]}
        )
        assert config.zones[0].gate is ZoneGate.HOUSEHOLD
