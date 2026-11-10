"""Alle configuratiecontroles van de installatie op één plek.

Every configuration check of the installation in one place.

`Problem` draagt de code en de plaatshouders, `validate()` loopt de regels in
vaste volgorde af en `RULES` is die volgorde. De controles wonen hier en niet in
`models.py`: het model beschrijft de installatie, deze module zegt wat eraan
mankeert. Een nieuwe controle hoort in `RULES`, niet in een tweede lijst.

`Problem` carries the code and the placeholders, `validate()` walks the rules in
a fixed order and `RULES` is that order. The checks live here, not in
`models.py`: the model describes the installation, this module says what is
wrong with it. A new check belongs in `RULES`, not in a second list.
"""

from __future__ import annotations

from .models import DirectorConfig
from .validation_circuits import (
    layout_problems,
    rule_circuits,
    rule_duplicate_circuit_ids,
    rule_unit_on_two_circuits,
    timing_problems,
)
from .validation_openings import (
    rule_cover_open_state,
    rule_duplicate_opening_ids,
    rule_house_wide_stops,
    rule_openings,
    rule_stuck_below_configured_rest,
)
from .validation_residents import (
    quiet_problems,
    rule_dead_sleep_settings,
    rule_resident_without_presence,
)
from .validation_shared import rule_seasons
from .validation_sources import (
    rule_duplicate_source_ids,
    rule_exclusive_groups,
    rule_generators,
    rule_source_covered_zones,
)
from .validation_windows import (
    rule_guest_window_half_filled,
    rule_holiday_calendars,
    rule_windows_without_length,
)
from .validation_zones import (
    rule_duplicate_zone_ids,
    rule_entity_twice_in_one_zone,
    rule_nonpositive_max_precondition,
    rule_outdoor_deadband,
    rule_schedule_gate,
    rule_stuck_time,
    rule_unit_in_no_zone,
    rule_zones,
)


def validate(config: DirectorConfig) -> tuple[str, ...]:
    """Return every structural problem found in `config`, newest checks last.

    Returns an empty tuple for a sound configuration. Meant for the config flow
    and for tests; `decide()` itself never raises on a flawed configuration,
    since refusing to regulate a whole house over one bad zone is worse than
    regulating the sound zones and reporting the rest.

    De controles staan als losse regelfuncties in `_RULES`, op volgorde; deze
    functie is alleen nog de lus erover. Die volgorde is zichtbaar op het
    bewaarscherm en in de reparatiemelding `invalid_config`, en wordt door
    `tests/test_validation.py` tegen letterlijke lijsten gehouden.

    The checks live as separate rule functions in `_RULES`, in order; this
    function is only the loop over them. That order is visible on the save
    screen and in the `invalid_config` repair notice, and is held by
    `tests/test_validation.py` against literal lists.
    """
    problems: list[str] = []
    for rule in RULES:
        problems.extend(rule(config))
    return tuple(problems)


RULES = (
    rule_duplicate_zone_ids,
    rule_duplicate_circuit_ids,
    rule_duplicate_source_ids,
    rule_duplicate_opening_ids,
    rule_entity_twice_in_one_zone,
    rule_unit_in_no_zone,
    rule_unit_on_two_circuits,
    rule_source_covered_zones,
    rule_zones,
    rule_generators,
    rule_circuits,
    rule_openings,
    rule_schedule_gate,
    rule_stuck_time,
    rule_outdoor_deadband,
    rule_nonpositive_max_precondition,
    rule_house_wide_stops,
    rule_holiday_calendars,
    rule_resident_without_presence,
    rule_exclusive_groups,
    rule_seasons,
    layout_problems,
    quiet_problems,
    timing_problems,
    rule_dead_sleep_settings,
    rule_windows_without_length,
    rule_guest_window_half_filled,
    rule_cover_open_state,
    rule_stuck_below_configured_rest,
)
