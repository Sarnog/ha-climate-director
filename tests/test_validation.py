"""Tests voor alles wat een gebruiker verkeerd kan instellen.

Tests for everything a user can set up wrongly.

Elke controle hier bestaat omdat de fout die hij vangt van buiten niet te
onderscheiden is van "de director besluit niets". Dat is de stilste manier
waarop deze integratie kan falen, en daarom hoort elke instelfout een naam te
krijgen in plaats van een symptoom.

Every check here exists because the mistake it catches is, from the outside,
indistinguishable from "the director decides nothing". That is the quietest way
this integration can fail, so every configuration mistake should get a name
rather than a symptom.
"""

from __future__ import annotations

from datetime import time, timedelta

import pytest
from conftest import house

from custom_components.climate_director.engine import (
    Circuit,
    DirectorConfig,
    GateSettings,
    ModeSettings,
    Opening,
    Resident,
    Source,
    TimeWindow,
    Zone,
    validate,
)


def problem(config: DirectorConfig, fragment: str) -> bool:
    """Return whether any reported problem mentions `fragment`."""
    return any(fragment in item for item in validate(config))


def zone(zone_id: str, **kwargs: object) -> Zone:
    """Return a workable zone, overridden by whatever the test cares about."""
    settings: dict[str, object] = {
        "indoor_sensor": f"sensor.{zone_id}",
        "sources": (Source(f"{zone_id}_s", f"climate.{zone_id}"),),
        "heat": ModeSettings(21.0, 20.0),
    }
    settings.update(kwargs)
    return Zone(zone_id, zone_id.title(), **settings)  # type: ignore[arg-type]


def test_the_existing_installation_is_still_sound() -> None:
    assert validate(house()) == ()


class TestSharedPriority:
    """Two rooms on one outdoor unit must not hold the same number."""

    def _config(self, first: int, second: int) -> DirectorConfig:
        return DirectorConfig(
            zones=(zone("woonkamer", priority=first), zone("zolder", priority=second)),
            circuits=(
                Circuit(
                    "c",
                    "C",
                    units=("climate.woonkamer", "climate.zolder"),
                    simultaneous_heat_cool=False,
                ),
            ),
        )

    def test_distinct_numbers_are_fine(self) -> None:
        assert not problem(self._config(0, 1), "share priority")

    def test_the_same_number_is_reported(self) -> None:
        assert problem(self._config(0, 0), "share priority")

    def test_rooms_on_separate_circuits_may_share_a_number(self) -> None:
        """They never compete, so making them differ would be a rule without a reason."""
        config = DirectorConfig(
            zones=(zone("woonkamer", priority=0), zone("zolder", priority=0)),
            circuits=(
                Circuit("a", "A", units=("climate.woonkamer",)),
                Circuit("b", "B", units=("climate.zolder",)),
            ),
        )
        assert not problem(config, "share priority")


class TestZonesThatCanNeverAct:
    def test_a_zone_without_an_indoor_sensor(self) -> None:
        assert problem(DirectorConfig(zones=(zone("a", indoor_sensor=""),)), "no indoor")

    def test_a_zone_that_may_neither_heat_nor_cool(self) -> None:
        assert problem(DirectorConfig(zones=(zone("a", heat=None),)), "neither heat nor cool")

    def test_overlapping_switch_on_points(self) -> None:
        """Heating and cooling would ask for the same room at the same moment."""
        config = DirectorConfig(
            zones=(zone("a", heat=ModeSettings(21.0, 22.0), cool=ModeSettings(20.0, 20.0)),)
        )
        assert problem(config, "starts cooling at or below")

    def test_sensible_switch_on_points_are_fine(self) -> None:
        config = DirectorConfig(
            zones=(zone("a", heat=ModeSettings(21.0, 20.0), cool=ModeSettings(23.0, 25.0)),)
        )
        assert not problem(config, "starts cooling")


class TestCircuitsThatCanNeverAct:
    def test_a_capacity_of_zero(self) -> None:
        config = DirectorConfig(
            zones=(zone("a"),),
            circuits=(Circuit("c", "C", units=("climate.a",), max_concurrent_units=0),),
        )
        assert problem(config, "no unit to run at all")

    @pytest.mark.parametrize(
        ("field", "fragment"),
        [
            ("family_switch_delay", "negative family switch delay"),
            ("min_family_switch_interval", "negative minimum switch interval"),
            ("min_cycle_time", "negative minimum cycle time"),
        ],
    )
    def test_a_negative_duration(self, field: str, fragment: str) -> None:
        config = DirectorConfig(
            zones=(zone("a"),),
            circuits=(Circuit("c", "C", units=("climate.a",), **{field: timedelta(seconds=-5)}),),  # type: ignore[arg-type]
        )
        assert problem(config, fragment)


class TestReferencesThatGoNowhere:
    def test_an_opening_naming_an_unknown_zone(self) -> None:
        config = DirectorConfig(
            zones=(zone("a"),),
            openings=(Opening("binary_sensor.door", zone_ids=("kelder",)),),
        )
        assert problem(config, "unknown zone kelder")

    def test_an_opening_naming_a_real_zone(self) -> None:
        config = DirectorConfig(
            zones=(zone("a"),), openings=(Opening("binary_sensor.door", zone_ids=("a",)),)
        )
        assert not problem(config, "unknown zone")

    def test_a_negative_opening_delay(self) -> None:
        config = DirectorConfig(
            zones=(zone("a"),),
            openings=(Opening("binary_sensor.door", delay=timedelta(seconds=-1)),),
        )
        assert problem(config, "negative delay")


class TestResidentsWhoCanNeverBeHome:
    def test_a_resident_without_a_presence_entity(self) -> None:
        """Being home is required outright, so an untracked resident is a mistake."""
        config = DirectorConfig(
            zones=(zone("a"),),
            residents=(Resident("danny", "Danny"),),
        )
        assert problem(config, "can never be home")

    def test_a_tracked_resident_is_fine(self) -> None:
        config = DirectorConfig(
            zones=(zone("a"),),
            residents=(Resident("danny", "Danny", presence_entity="person.danny"),),
        )
        assert not problem(config, "can never be home")


class TestNegativeTimeouts:
    def test_a_negative_presence_timeout(self) -> None:
        config = DirectorConfig(zones=(zone("a", presence_timeout=timedelta(seconds=-1)),))
        assert problem(config, "negative presence timeout")


class TestAQuietWindowThatSilencesEverything:
    """Een stiltevenster is de omgekeerde van een rooster, en dat leest verkeerd.

    Wie het leest als "hier mag het huis regelen" en er een venster van de hele
    dag in zet, krijgt een installatie die uit zichzelf nooit meer iets doet.
    Van buiten is dat niet te onderscheiden van een integratie die stuk is.

    A quiet window is the inverse of a schedule, and that reads the wrong way.
    Read as "the house may regulate here" and given a window covering the whole
    day, you get an installation that never does anything of its own accord
    again. From the outside that is indistinguishable from a broken one.
    """

    def _config(self, *windows: TimeWindow, residents: tuple = ()) -> DirectorConfig:
        return DirectorConfig(
            zones=(
                Zone(
                    "woonkamer",
                    "Woonkamer",
                    "sensor.woonkamer",
                    sources=(Source("w", "climate.woonkamer"),),
                    heat=ModeSettings(target=21.0, start_at=20.0),
                ),
            ),
            residents=residents,
            gates=GateSettings(quiet_windows=windows),
        )

    def _codes(self, config: DirectorConfig) -> set[str]:
        return {getattr(problem, "code", "") for problem in validate(config)}

    def test_an_ordinary_night_window_is_fine(self) -> None:
        config = self._config(TimeWindow(time(21, 0), time(9, 0)))
        assert "quiet_covers_the_day" not in self._codes(config)

    def test_a_window_covering_the_whole_day_is_named(self) -> None:
        """Eén minuut open aan het eind maakt van een dichtgetimmerde dag niets anders."""
        config = self._config(TimeWindow(time(0, 0), time(23, 59)))
        assert "quiet_covers_the_day" in self._codes(config)

    def test_two_windows_that_together_cover_it_are_named_too(self) -> None:
        """Elk venster op zich is redelijk; samen gaan ze de klok rond."""
        config = self._config(
            TimeWindow(time(0, 0), time(12, 0)),
            TimeWindow(time(12, 0), time(0, 0)),
        )
        assert "quiet_covers_the_day" in self._codes(config)

    def test_a_window_that_starts_and_ends_at_the_same_time_is_empty(self) -> None:
        """Het beginpunt telt mee, het eindpunt niet - dus 09:00-09:00 is niets.

        Geen wikkel om middernacht ook: alleen een eind *vóór* de start loopt
        door. Deze regel geldt overal, ook voor roosters en slaapvensters, en
        staat hier vastgelegd omdat je hem net zo goed andersom kunt lezen - en
        omdat de controle hierboven op precies dezelfde manier moet tellen.

        The start counts, the end does not - so 09:00-09:00 is nothing. No wrap
        around midnight either: only an end *before* the start runs through.
        This rule holds everywhere, schedules and sleep windows included, and is
        pinned here because you could just as well read it the other way round -
        and because the check above has to count in exactly the same way.
        """
        window = TimeWindow(time(9, 0), time(9, 0))
        assert not window.contains(time(9, 0), 0)
        assert not window.contains(time(12, 0), 0)
        assert "quiet_covers_the_day" not in self._codes(self._config(window))

    def test_windows_that_meet_on_the_minute_leave_that_minute_free(self) -> None:
        """Eén vrije minuut per dag is geen ruimte maar toeval; de grens ligt hoger."""
        config = self._config(
            TimeWindow(time(0, 0), time(12, 0)),
            TimeWindow(time(12, 0), time(23, 59)),
        )
        assert "quiet_covers_the_day" in self._codes(config)

    def test_an_hour_of_room_is_room_enough(self) -> None:
        config = self._config(
            TimeWindow(time(0, 0), time(12, 0)),
            TimeWindow(time(13, 0), time(0, 0)),
        )
        assert "quiet_covers_the_day" not in self._codes(config)

    def test_a_resident_with_a_schedule_can_beat_it(self) -> None:
        """Een open roostervenster verslaat de stilte, dus dan staat er niets stil."""
        config = self._config(
            TimeWindow(time(0, 0), time(23, 59)),
            residents=(
                Resident(
                    "danny",
                    "Danny",
                    presence_entity="person.danny",
                    windows=(TimeWindow(time(8, 0), time(18, 0)),),
                ),
            ),
        )
        assert "quiet_covers_the_day" not in self._codes(config)

    def test_only_the_days_it_applies_to_count(self) -> None:
        """A window covering the whole of Saturday only silences Saturday."""
        config = self._config(TimeWindow(time(0, 0), time(23, 59), frozenset({5})))
        assert "quiet_covers_the_day" in self._codes(config)

    def test_a_holiday_window_is_left_out_of_it(self) -> None:
        """Die geldt alleen op vakantiedagen, en dan is stilstaan de bedoeling."""
        config = self._config(TimeWindow(time(0, 0), time(23, 59), holiday=True))
        assert "quiet_covers_the_day" not in self._codes(config)


class TestSwitchTimingsThatNeverApply:
    """Instellingen die er wel staan maar nergens over gaan.

    Een buitenunit die verwarmen en koelen tegelijk aankan wisselt nooit van
    taak. Een omschakelpauze doet daar dus niets - maar hij staat er wel, en dan
    ga je ervan uit dat hij werkt.

    Settings that are there but about nothing. An outdoor unit that can heat and
    cool at once never switches duty. A switch pause does nothing there - but it
    is in the settings, and then you assume it works.
    """

    def _config(self, **kwargs) -> DirectorConfig:
        return DirectorConfig(
            zones=(
                Zone(
                    "woonkamer",
                    "Woonkamer",
                    "sensor.woonkamer",
                    sources=(Source("w", "climate.woonkamer"),),
                    heat=ModeSettings(target=21.0, start_at=20.0),
                ),
            ),
            circuits=(Circuit("c", "C", units=("climate.woonkamer",), **kwargs),),
        )

    def _codes(self, config: DirectorConfig) -> set[str]:
        return {getattr(problem, "code", "") for problem in validate(config)}

    def test_a_pause_on_a_simultaneous_circuit_is_named(self) -> None:
        config = self._config(simultaneous_heat_cool=True, family_switch_delay=timedelta(minutes=5))
        assert "switch_timings_without_a_switch" in self._codes(config)

    def test_a_minimum_run_on_a_simultaneous_circuit_is_named(self) -> None:
        config = self._config(
            simultaneous_heat_cool=True, min_family_switch_interval=timedelta(minutes=30)
        )
        assert "switch_timings_without_a_switch" in self._codes(config)

    def test_the_same_settings_on_a_multi_split_are_fine(self) -> None:
        config = self._config(
            simultaneous_heat_cool=False,
            family_switch_delay=timedelta(minutes=5),
            min_family_switch_interval=timedelta(minutes=30),
        )
        assert "switch_timings_without_a_switch" not in self._codes(config)

    def test_a_simultaneous_circuit_without_those_settings_is_fine(self) -> None:
        config = self._config(simultaneous_heat_cool=True)
        assert "switch_timings_without_a_switch" not in self._codes(config)

    def test_the_short_cycle_time_is_not_complained_about(self) -> None:
        """Die geldt per unit en werkt dus wél op zo'n circuit."""
        config = self._config(simultaneous_heat_cool=True, min_cycle_time=timedelta(minutes=20))
        assert "switch_timings_without_a_switch" not in self._codes(config)


class TestOnlyManualSources:
    """A zone with only hand-operated sources can never start, so it is named."""

    def _config(self, autostart: bool, role: object = None) -> DirectorConfig:
        from custom_components.climate_director.engine.models import SourceRole

        return DirectorConfig(
            zones=(
                zone(
                    "woonkamer",
                    sources=(
                        Source(
                            "s",
                            "climate.woonkamer",
                            role=role or SourceRole.HEAT_COOL,
                            autostart=autostart,
                        ),
                    ),
                ),
            ),
        )

    def test_a_zone_with_only_manual_sources_is_reported(self) -> None:
        assert problem(self._config(autostart=False), "automatic start off")

    def test_one_automatic_source_is_enough(self) -> None:
        assert not problem(self._config(autostart=True), "automatic start off")

    def test_a_manual_cooler_next_to_an_automatic_heater_is_fine_without_cooling(self) -> None:
        """Zolang de zone niet vraagt te koelen, is de handbediende koeler geen dood spoor.

        As long as the zone never asks to cool, the manual cooler is no dead end.
        """
        from custom_components.climate_director.engine.models import SourceRole

        config = DirectorConfig(
            zones=(
                zone(
                    "woonkamer",
                    heat=ModeSettings(21.0, 20.0),
                    sources=(
                        Source("h", "climate.heater", role=SourceRole.HEAT_ONLY, autostart=True),
                        Source("c", "climate.cooler", role=SourceRole.COOL_ONLY, autostart=False),
                    ),
                ),
            ),
        )
        assert not problem(config, "automatic start off")

    def test_a_duty_covered_only_by_manual_sources_is_reported(self) -> None:
        """Koelen dat alleen een handbediend apparaat kan, is een stille dode stand.

        Cooling that only a hand-operated appliance can deliver is a quietly dead
        duty, even when heating starts fine.
        """
        from custom_components.climate_director.engine.models import SourceRole

        config = DirectorConfig(
            zones=(
                zone(
                    "woonkamer",
                    heat=ModeSettings(21.0, 20.0),
                    cool=ModeSettings(23.0, 24.0),
                    sources=(
                        Source("h", "climate.heater", role=SourceRole.HEAT_ONLY, autostart=True),
                        Source("c", "climate.cooler", role=SourceRole.COOL_ONLY, autostart=False),
                    ),
                ),
            ),
        )
        assert problem(config, "automatic start off")
