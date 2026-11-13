"""De mutatielijst van de controle: elke mutatie een eigenschap, elke eigenschap een toets.

The review's mutation list: every mutation a property, every property a test.

`script/mutation_probe.py` is de baan die bij elke push draait en klein blijft. Deze lijst
is de uitgebreide set waarmee een controle meet of de toetsen een eigenschap werkelijk
bewaken na een verhuizing of een ingreep: per mutatie een stuk bronregels dat precies één
keer voorkomt, de vervanging, en de toetsen die het moeten vangen. Een mutatie die groen
blijft is een gat; een mutatie met het veld `equivalent` verandert het gedrag aantoonbaar
niet en hoort groen te blijven (de reden staat erbij). `tests/test_select_tests.py` eist
dat elk patroon nog precies één keer in zijn bestand staat, zodat een verhuizing de lijst
niet stilletjes laat verouderen.

`script/mutation_probe.py` is the lane that runs on every push and stays small. This list is
the extended set with which a review measures whether the tests really guard a property
after a move or an intervention: per mutation a piece of source lines that occurs exactly
once, the replacement, and the tests that must catch it. A mutation that stays green is a
hole; a mutation with the field `equivalent` demonstrably does not change behaviour and is
supposed to stay green (the reason stands beside it). `tests/test_select_tests.py` demands
that every pattern still stands exactly once in its file, so a move cannot let the list go
stale unnoticed.

Gebruik / usage, vanuit een wegwerp-worktree (de run past bestanden ter plekke aan en zet ze
terug) / from a throwaway worktree (the run edits files in place and restores them):

    python script/mutation_review.py [--lane N --lanes 4] [--only naam,naam]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

REVIEW_MUTATIONS: list[dict[str, object]] = [
    {
        "name": "A01-aanwezigheid-niet-gecontroleerd",
        "file": "custom_components/climate_director/readability.py",
        "old": (
            "        if resident.presence_entity and _no_reading(hass, resident.presence_entity):"
        ),
        "new": (
            "        if False and resident.presence_entity and _no_reading(hass, "
            "resident.presence_entity):"
        ),
        "tests": [
            "tests/test_hand_start.py",
            "tests/test_hand_start_live.py",
            "tests/test_ha_layer.py",
            "tests/test_readability.py",
        ],
    },
    {
        "name": "A02-slaap-niet-gecontroleerd",
        "file": "custom_components/climate_director/readability.py",
        "old": "        if resident.sleep_entity and _no_reading(hass, resident.sleep_entity):",
        "new": (
            "        if False and resident.sleep_entity and _no_reading(hass, "
            "resident.sleep_entity):"
        ),
        "tests": [
            "tests/test_hand_start.py",
            "tests/test_hand_start_live.py",
            "tests/test_ha_layer.py",
            "tests/test_readability.py",
        ],
    },
    {
        "name": "A03-agenda-telt-als-leesbaar",
        "file": "custom_components/climate_director/readability.py",
        "old": (
            "    if holiday_feeds_brakes(config):\n        for calendar in "
            "config.holiday_calendars:"
        ),
        "new": "    if False:\n        for calendar in config.holiday_calendars:",
        "tests": [
            "tests/test_hand_start.py",
            "tests/test_hand_start_live.py",
            "tests/test_ha_layer.py",
            "tests/test_readability.py",
        ],
    },
    {
        "name": "A04-agenda-zonder-trefwoord-telt-mee",
        "file": "custom_components/climate_director/readability.py",
        "old": (
            "    if holiday_feeds_brakes(config):\n        for calendar in "
            "config.holiday_calendars:"
        ),
        "new": "    if True:\n        for calendar in config.holiday_calendars:",
        "tests": [
            "tests/test_hand_start.py",
            "tests/test_hand_start_live.py",
            "tests/test_ha_layer.py",
            "tests/test_readability.py",
        ],
    },
    {
        "name": "A05-alleen-eerste-agenda",
        "file": "custom_components/climate_director/readability.py",
        "old": (
            "        for calendar in config.holiday_calendars:\n          "
            "  if calendar and _no_reading"
        ),
        "new": (
            "        for calendar in config.holiday_calendars[:1]:\n      "
            "      if calendar and _no_reading"
        ),
        "tests": [
            "tests/test_hand_start.py",
            "tests/test_hand_start_live.py",
            "tests/test_ha_layer.py",
            "tests/test_readability.py",
        ],
    },
    {
        "name": "A06-lus-slaat-eerste-bewoner-over",
        "file": "custom_components/climate_director/readability.py",
        "old": (
            "    for resident in config.residents:\n        if resident.presence_entity "
            "and _no_reading"
        ),
        "new": (
            "    for resident in config.residents[1:]:\n        if resident.presence_entity "
            "and _no_reading"
        ),
        "tests": [
            "tests/test_hand_start.py",
            "tests/test_hand_start_live.py",
            "tests/test_ha_layer.py",
            "tests/test_readability.py",
        ],
    },
    {
        "name": "A07-lus-slaat-laatste-bewoner-over",
        "file": "custom_components/climate_director/readability.py",
        "old": (
            "    for resident in config.residents:\n        if resident.presence_entity "
            "and _no_reading"
        ),
        "new": (
            "    for resident in config.residents[:-1]:\n        if resident.presence_entity "
            "and _no_reading"
        ),
        "tests": [
            "tests/test_hand_start.py",
            "tests/test_hand_start_live.py",
            "tests/test_ha_layer.py",
            "tests/test_readability.py",
        ],
    },
    {
        "name": "A08-ontbrekende-entiteit-leesbaar",
        "file": "custom_components/climate_director/readability.py",
        "old": "    return state is None or unreadable(state.state)",
        "new": "    return state is not None and unreadable(state.state)",
        "tests": [
            "tests/test_hand_start.py",
            "tests/test_hand_start_live.py",
            "tests/test_ha_layer.py",
            "tests/test_readability.py",
        ],
    },
    {
        "name": "A09-unknown-leesbaar",
        "file": "custom_components/climate_director/readability.py",
        "old": "    return state is None or state in (STATE_UNAVAILABLE, STATE_UNKNOWN)",
        "new": "    return state is None or state == STATE_UNAVAILABLE",
        "tests": [
            "tests/test_hand_start.py",
            "tests/test_hand_start_live.py",
            "tests/test_ha_layer.py",
            "tests/test_readability.py",
        ],
    },
    {
        "name": "A10-unavailable-leesbaar",
        "file": "custom_components/climate_director/readability.py",
        "old": "    return state is None or state in (STATE_UNAVAILABLE, STATE_UNKNOWN)",
        "new": "    return state is None or state == STATE_UNKNOWN",
        "tests": [
            "tests/test_hand_start.py",
            "tests/test_hand_start_live.py",
            "tests/test_ha_layer.py",
            "tests/test_readability.py",
        ],
    },
    {
        "name": "A11-brakes-readable-negeert-agenda",
        "file": "custom_components/climate_director/engine/hand_start.py",
        "old": "        return UnreadableInput(ReadableInput.HOLIDAY) not in world.unreadable",
        "new": "        return True",
        "tests": [
            "tests/test_hand_start.py",
            "tests/test_hand_start_live.py",
            "tests/test_ha_layer.py",
            "tests/test_readability.py",
        ],
    },
    {
        "name": "A12-brakes-readable-agenda-zonder-trefwoord",
        "file": "custom_components/climate_director/engine/hand_start.py",
        "old": (
            "    return bool(config.holiday_keyword.strip() and any(config.holiday_calendars))"
        ),
        "new": "    return bool(any(config.holiday_calendars))",
        "tests": [
            "tests/test_hand_start.py",
            "tests/test_hand_start_live.py",
            "tests/test_ha_layer.py",
            "tests/test_readability.py",
        ],
    },
    {
        "name": "A13-brakes-readable-agenda-zonder-agenda",
        "file": "custom_components/climate_director/engine/hand_start.py",
        "old": (
            "    return bool(config.holiday_keyword.strip() and any(config.holiday_calendars))"
        ),
        "new": "    return bool(config.holiday_keyword.strip())",
        "tests": [
            "tests/test_hand_start.py",
            "tests/test_hand_start_live.py",
            "tests/test_ha_layer.py",
            "tests/test_readability.py",
        ],
    },
    {
        "name": "A14-ontbrekende-bewoner-leesbaar",
        "file": "custom_components/climate_director/engine/hand_start.py",
        "old": (
            "        if resident.presence_entity and (state is None or presence_missing "
            "in world.unreadable):"
        ),
        "new": (
            "        if resident.presence_entity and (state is not None and "
            "presence_missing in world.unreadable):"
        ),
        "tests": [
            "tests/test_hand_start.py",
            "tests/test_hand_start_live.py",
            "tests/test_ha_layer.py",
            "tests/test_readability.py",
        ],
    },
    {
        "name": "A15-niet-gevuld-door-wereldbouwer",
        "file": "custom_components/climate_director/world_builder.py",
        "old": "            unreadable=unreadable_inputs(self.hass, self.config),",
        "new": "            unreadable=frozenset(),",
        "tests": [
            "tests/test_hand_start.py",
            "tests/test_hand_start_live.py",
            "tests/test_ha_layer.py",
            "tests/test_readability.py",
        ],
    },
    {
        "name": "A16-bewoner-zonder-sensor-telt-mee",
        "file": "custom_components/climate_director/readability.py",
        "old": (
            "        if resident.presence_entity and _no_reading(hass, resident.presence_entity):"
        ),
        "new": "        if _no_reading(hass, resident.presence_entity or 'x.x'):",
        "tests": [
            "tests/test_hand_start.py",
            "tests/test_hand_start_live.py",
            "tests/test_ha_layer.py",
            "tests/test_readability.py",
        ],
    },
    {
        "name": "A17-volgende-dag-alleen-bij-leesbaar",
        "file": "custom_components/climate_director/hand_start.py",
        "old": "                    or started.date() != world.now.date()",
        "new": "                    or (readable and started.date() != world.now.date())",
        "tests": [
            "tests/test_hand_start.py",
            "tests/test_hand_start_live.py",
            "tests/test_ha_layer.py",
            "tests/test_readability.py",
        ],
    },
    {
        "name": "A18-slapen-ook-uit-onleesbare-wereld",
        "file": "custom_components/climate_director/hand_start.py",
        "old": "        if readable and (\n            self.everyone_asleep",
        "new": "        if (\n            self.everyone_asleep",
        "tests": [
            "tests/test_hand_start.py",
            "tests/test_hand_start_live.py",
            "tests/test_ha_layer.py",
            "tests/test_readability.py",
        ],
    },
    {
        "name": "L1a-slaapsensor-aanwezig-wordt-gemeld",
        "file": "custom_components/climate_director/engine/validation_residents.py",
        "old": "        if resident.sleep_entity:\n            continue",
        "new": "        if not resident.sleep_entity:\n            continue",
        "tests": ["tests/test_validation.py"],
    },
    {
        "name": "L1b-uitslapen-niet-gemeld",
        "file": "custom_components/climate_director/engine/validation_residents.py",
        "old": "        if resident.sleep_in is not None:",
        "new": "        if False:",
        "tests": ["tests/test_validation.py"],
    },
    {
        "name": "L1c-uiterste-tijd-niet-gemeld",
        "file": "custom_components/climate_director/engine/validation_residents.py",
        "old": "        if resident.wake_deadline is not None:",
        "new": "        if False:",
        "tests": ["tests/test_validation.py"],
    },
    {
        "name": "L1d-opstarem-altijd-gemeld",
        "file": "custom_components/climate_director/engine/validation_residents.py",
        "old": (
            "        if resident.rise_brake is not None and resident.sleep_window is not None:"
        ),
        "new": "        if resident.rise_brake is not None:",
        "tests": ["tests/test_validation.py"],
    },
    {
        "name": "L1e-opstarem-nooit-gemeld",
        "file": "custom_components/climate_director/engine/validation_residents.py",
        "old": (
            "        if resident.rise_brake is not None and resident.sleep_window is not None:"
        ),
        "new": "        if False:",
        "tests": ["tests/test_validation.py"],
    },
    {
        "name": "L1f-slaapvenster-niet-gemeld",
        "file": "custom_components/climate_director/engine/validation_residents.py",
        "old": "        if resident.sleep_window is not None:\n            dead.append",
        "new": "        if False:\n            dead.append",
        "tests": ["tests/test_validation.py"],
    },
    {
        "name": "L3a-vijf-weekdagen",
        "file": "custom_components/climate_director/engine/validation_zones.py",
        "old": (
            "        for day in range(7)\n        if not any(resident.takes_part(holiday=False"
        ),
        "new": (
            "        for day in range(5)\n        if not any(resident.takes_part(holiday=False"
        ),
        "tests": ["tests/test_validation.py"],
    },
    {
        "name": "L3b-vakantie-telt-als-gewone-dag",
        "file": "custom_components/climate_director/engine/validation_zones.py",
        "old": "resident.takes_part(holiday=False, weekday=day)",
        "new": "resident.takes_part(holiday=True, weekday=day)",
        "tests": ["tests/test_validation.py"],
    },
    {
        "name": "L3c-alleen-bij-nul-dagen-gedekt",
        "file": "custom_components/climate_director/engine/validation_zones.py",
        "old": (
            '    if missing:\n        yield Problem(\n            "schedule_gate_without_schedules"'
        ),
        "new": (
            "    if len(missing) == 7:\n        yield Problem(\n           "
            ' "schedule_gate_without_schedules"'
        ),
        "tests": ["tests/test_validation.py"],
    },
    {
        "name": "L4a-circuits-niet-gecontroleerd",
        "file": "custom_components/climate_director/engine/validation_openings.py",
        "old": "    for circuit in config.circuits:\n        for label, rest in (",
        "new": "    for circuit in ():\n        for label, rest in (",
        "tests": ["tests/test_validation.py"],
    },
    {
        "name": "L4b-bronnen-niet-gecontroleerd",
        "file": "custom_components/climate_director/engine/validation_openings.py",
        "old": "    for _zone, source in config.sources():\n        source_rest",
        "new": "    for _zone, source in ():\n        source_rest",
        "tests": ["tests/test_validation.py"],
    },
    {
        "name": "L4c-wisselinterval-niet-gecontroleerd",
        "file": "custom_components/climate_director/engine/validation_circuits.py",
        "old": (
            '            ("minimum switch interval", circuit.min_family_switch_interval),\n'
            '            ("minimum cycle time", circuit.min_cycle_time),'
        ),
        "new": (
            '            ("minimum switch interval", circuit.min_family_switch_interval '
            '* 0),\n            ("minimum cycle time", circuit.min_cycle_time),'
        ),
        "tests": ["tests/test_validation.py"],
    },
    {
        "name": "L4d-kortcyclus-niet-gecontroleerd",
        "file": "custom_components/climate_director/engine/validation_circuits.py",
        "old": (
            '            ("minimum switch interval", circuit.min_family_switch_interval),\n'
            '            ("minimum cycle time", circuit.min_cycle_time),'
        ),
        "new": (
            '            ("minimum switch interval", circuit.min_family_switch_interval),\n'
            '            ("minimum cycle time", circuit.min_cycle_time * '
            "0),"
        ),
        "tests": ["tests/test_validation.py"],
    },
    {
        "name": "L5a-cover-nooit-gemeld",
        "file": "custom_components/climate_director/engine/validation_openings.py",
        "old": 'opening.entity_id.startswith("cover.") and',
        "new": 'opening.entity_id.startswith("covers.") and',
        "tests": ["tests/test_validation.py"],
    },
    {
        "name": "L5b-alleen-on-gemeld",
        "file": "custom_components/climate_director/engine/validation_openings.py",
        "old": 'opening.open_state != "open"',
        "new": 'opening.open_state == "on"',
        "tests": ["tests/test_validation.py"],
    },
    {
        "name": "L6a-gelijk-begin-eind-niet-gemeld",
        "file": "custom_components/climate_director/engine/validation_windows.py",
        "old": "        if window.start == window.end:",
        "new": "        if False:",
        "tests": ["tests/test_validation.py"],
    },
    {
        "name": "L6b-half-gastenvenster-niet-gemeld",
        "file": "custom_components/climate_director/engine/validation_windows.py",
        "old": "    if config.gates.guest_window_incomplete:",
        "new": "    if False:",
        "tests": ["tests/test_validation.py"],
    },
    {
        "name": "L6c-gastenvenster-niet-doorzocht",
        "file": "custom_components/climate_director/engine/validation_shared.py",
        "old": '    if guest is not None:\n        yield "guest window", guest',
        "new": '    if False:\n        yield "guest window", guest',
        "tests": ["tests/test_validation.py"],
    },
    {
        "name": "L6d-stiltevenster-niet-doorzocht",
        "file": "custom_components/climate_director/engine/validation_shared.py",
        "old": '    for window in config.gates.quiet_windows:\n        yield "quiet window"',
        "new": '    for window in ():\n        yield "quiet window"',
        "tests": ["tests/test_validation.py"],
    },
    {
        "name": "L6e-bewonersvensters-niet-doorzocht",
        "file": "custom_components/climate_director/engine/validation_shared.py",
        "old": '        for window in resident.windows:\n            yield f"schedule',
        "new": '        for window in ():\n            yield f"schedule',
        "tests": ["tests/test_validation.py"],
    },
    {
        "name": "L6f-incomplete-nooit-gezet",
        "file": "custom_components/climate_director/engine/installation_storage.py",
        "old": 'guest_window_incomplete=bool(guest.get("start")) != bool(guest.get("end")),',
        "new": "guest_window_incomplete=False,",
        "tests": ["tests/test_validation.py"],
    },
    {
        "name": "L2a-48-uur",
        "file": "custom_components/climate_director/engine/night.py",
        "old": "world.now - since > timedelta(hours=24)",
        "new": "world.now - since > timedelta(hours=48)",
        "tests": [
            "tests/test_the_night.py",
            "tests/test_handed_back.py",
            "tests/test_hand_start.py",
        ],
    },
    {
        "name": "L2b-geen-24-uursgrens",
        "file": "custom_components/climate_director/engine/night.py",
        "old": "    if since is None or world.now - since > timedelta(hours=24):",
        "new": "    if since is None:",
        "tests": [
            "tests/test_the_night.py",
            "tests/test_handed_back.py",
            "tests/test_hand_start.py",
        ],
    },
    {
        "name": "L2c-late-thuiskomer-omgekeerd",
        "file": "custom_components/climate_director/engine/night.py",
        "old": "        and state.home_since > since\n",
        "new": "        and state.home_since < since\n",
        "tests": [
            "tests/test_the_night.py",
            "tests/test_handed_back.py",
            "tests/test_hand_start.py",
        ],
    },
    {
        "name": "L2d-toekomstige-thuiskomst-telt-als-laat",
        "file": "custom_components/climate_director/engine/night.py",
        "old": "        and state.home_since <= world.now\n",
        "new": "",
        "tests": [
            "tests/test_the_night.py",
            "tests/test_handed_back.py",
            "tests/test_hand_start.py",
        ],
    },
    {
        "name": "L2e-late-thuiskomer-check-weg",
        "file": "custom_components/climate_director/engine/night.py",
        "old": "    if (\n        state is not None\n        and state.home_since is not None",
        "new": "    if (\n        False\n        and state.home_since is not None",
        "tests": [
            "tests/test_the_night.py",
            "tests/test_handed_back.py",
            "tests/test_hand_start.py",
        ],
    },
    {
        "name": "L8a-sleep_in-niet-gelakt",
        "file": "custom_components/climate_director/diagnostics.py",
        "old": '            "sleep_in",\n',
        "new": "",
        "tests": ["tests/test_diagnostics.py"],
    },
    {
        "name": "L8b-tracked-ongefilterd",
        "file": "custom_components/climate_director/diagnostics.py",
        "old": (
            "    return sorted(entity for entity in coordinator.tracked_entities() "
            "if entity not in hidden)"
        ),
        "new": "    return sorted(coordinator.tracked_entities())",
        "tests": ["tests/test_diagnostics.py"],
    },
    {
        "name": "L8c-slaapentiteit-niet-verborgen",
        "file": "custom_components/climate_director/diagnostics.py",
        "old": "for entity in (resident.presence_entity, resident.sleep_entity)",
        "new": "for entity in (resident.presence_entity,)",
        "tests": ["tests/test_diagnostics.py"],
    },
    {
        "name": "L8d-kamerpresentie-niet-verborgen",
        "file": "custom_components/climate_director/diagnostics.py",
        "old": (
            "    hidden.update(zone.presence_entity for zone in coordinator.config.zones "
            "if zone.presence_entity)\n"
        ),
        "new": "",
        "tests": ["tests/test_diagnostics.py"],
    },
    {
        "name": "L9a-schakelaar-schrijft-altijd",
        "file": "custom_components/climate_director/switch.py",
        "old": "        if self._is_on != previous or label_changed:",
        "new": "        if True:",
        "tests": ["tests/test_switches.py"],
    },
    {
        "name": "L9b-naamwijziging-niet-gepubliceerd",
        "file": "custom_components/climate_director/switch.py",
        "old": "        if self._is_on != previous or label_changed:",
        "new": "        if self._is_on != previous:",
        "tests": ["tests/test_switches.py"],
    },
    {
        "name": "L9c-standwijziging-niet-gepubliceerd",
        "file": "custom_components/climate_director/switch.py",
        "old": "        if self._is_on != previous or label_changed:",
        "new": "        if label_changed:",
        "tests": ["tests/test_switches.py"],
    },
    {
        "name": "L10a-doelen-niet-gekeurd",
        "file": "custom_components/climate_director/services.py",
        "old": "            if entry.runtime_data.override_source(zone_id, hvac_mode) is None:",
        "new": (
            "            if False and entry.runtime_data.override_source(zone_id, "
            "hvac_mode) is None:"
        ),
        "tests": ["tests/test_override_duration.py"],
    },
    {
        "name": "L10b-alleen-eerste-doel-gekeurd",
        "file": "custom_components/climate_director/services.py",
        "old": (
            "        for entry, zone_id in targets:\n"
            "            if entry.runtime_data.override_source"
        ),
        "new": (
            "        for entry, zone_id in targets[:1]:\n"
            "            if entry.runtime_data.override_source"
        ),
        "tests": ["tests/test_override_duration.py"],
    },
    {
        "name": "L11a-eerste-zone-wint",
        "file": "custom_components/climate_director/engine/untouched.py",
        "old": "item.reason is Reason.MANUAL_OVERRIDE and item.zone_id in overridden",
        "new": "False",
        "tests": ["tests/test_override_handover.py"],
    },
    {
        "name": "L11b-elke-override-reden-wint",
        "file": "custom_components/climate_director/engine/untouched.py",
        "old": "item.reason is Reason.MANUAL_OVERRIDE and item.zone_id in overridden",
        "new": "item.reason is Reason.MANUAL_OVERRIDE",
        "tests": ["tests/test_override_handover.py"],
    },
    {
        "name": "L12-vlag-voor-herstel",
        "file": "custom_components/climate_director/coordinator_lifecycle.py",
        "old": "    try:\n        await coordinator.async_restore_state()",
        "new": (
            "    coordinator.lifecycle.restored = True\n    try:\n        await "
            "coordinator.async_restore_state()"
        ),
        "tests": ["tests/test_startup.py"],
    },
    {
        "name": "P2a-oude-uitzetting-komt-terug",
        "file": "custom_components/climate_director/stored_state.py",
        "old": "        if when is not None and now - when <= COMMANDED_WINDOW:",
        "new": "        if when is not None:",
        "tests": ["tests/test_handed_back.py"],
    },
    {
        "name": "P2b-uitzetting-niet-bewaard",
        "file": "custom_components/climate_director/state_store.py",
        "old": '            "commanded_off": {\n                entity_id: when.isoformat()',
        "new": (
            '            "commanded_off": {} if True else {\n             '
            "   entity_id: when.isoformat()"
        ),
        "tests": ["tests/test_handed_back.py"],
    },
    {
        "name": "P2c-uitzetting-niet-hersteld",
        "file": "custom_components/climate_director/state_store.py",
        "old": (
            'self.tracking.commanded_off.update(restore_commanded_off(stored.get("commanded_off"), '
            "now))"
        ),
        "new": "self.tracking.commanded_off.update({})",
        "tests": ["tests/test_handed_back.py"],
    },
    {
        "name": "P2d-venster-te-krap",
        "file": "custom_components/climate_director/stored_state.py",
        "old": "now - when <= COMMANDED_WINDOW",
        "new": "now - when <= COMMANDED_WINDOW / 100",
        "tests": ["tests/test_handed_back.py"],
    },
    {
        "name": "K1-veld-ongeclassificeerd",
        "file": "tests/test_hand_start.py",
        "old": '        "unreadable",\n        "openings",',
        "new": '        "openings",',
        "tests": ["tests/test_hand_start.py"],
    },
    {
        "name": "K2-residents-niet-meer-een-remveld",
        "file": "tests/test_hand_start.py",
        "old": '        "residents": {"presence", "sleep"},\n',
        "new": "",
        "tests": ["tests/test_hand_start.py"],
    },
    {
        "name": "K3-veld-dubbel-ingedeeld",
        "file": "tests/test_hand_start.py",
        "old": 'INTERNAL_WORLD_FIELDS = {"now", "asleep_since"}',
        "new": 'INTERNAL_WORLD_FIELDS = {"now", "asleep_since", "season"}',
        "tests": ["tests/test_hand_start.py"],
    },
    {
        "name": "K4-nieuwe-soort-zonder-veld",
        "file": "custom_components/climate_director/engine/world.py",
        "old": '    HOLIDAY = "holiday"\n',
        "new": '    HOLIDAY = "holiday"\n    CALENDAR2 = "calendar2"\n',
        "tests": ["tests/test_hand_start.py"],
    },
    {
        "name": "K5-nieuw-veld-zonder-klasse",
        "file": "custom_components/climate_director/engine/world.py",
        "old": "    guest_mode: bool = False",
        "new": '    guest_mode: bool = False\n    new_sensor: str = ""',
        "tests": ["tests/test_hand_start.py"],
    },
    {
        "name": "K6-agenda-soort-van-veld-gehaald",
        "file": "tests/test_hand_start.py",
        "old": '        "holiday_mode": {"holiday"},\n',
        "new": '        "holiday_mode": set(),\n',
        "tests": ["tests/test_hand_start.py"],
    },
    {
        "name": "gebied-M1-len-kleiner-dan-twee-weg",
        "file": "custom_components/climate_director/engine/takeover.py",
        "old": "if len(area) < 2 or entity_id in taking:",
        "new": "if entity_id in taking:",
        "tests": [
            "tests/test_central_cover_clash.py",
            "tests/test_shared_source_takeover.py",
            "tests/test_area_clash.py",
        ],
        "equivalent": (
            "de bewaking `len(area) < 2` is overbodig: één zone in het gebied "
            "levert geen rivalen op"
        ),
    },
    {
        "name": "gebied-M2-overnemer-niet-overslaan",
        "file": "custom_components/climate_director/engine/takeover.py",
        "old": "if len(area) < 2 or entity_id in taking:",
        "new": "if len(area) < 2:",
        "tests": [
            "tests/test_central_cover_clash.py",
            "tests/test_shared_source_takeover.py",
            "tests/test_area_clash.py",
        ],
    },
    {
        "name": "gebied-M3-gelijk-wordt-kleiner",
        "file": "custom_components/climate_director/engine/takeover.py",
        "old": (
            "best = min(owners, key=lambda r: r.rank).rank <= min(rivals, "
            "key=lambda r: r.rank).rank"
        ),
        "new": (
            "best = min(owners, key=lambda r: r.rank).rank < min(rivals, key=lambda r: r.rank).rank"
        ),
        "tests": [
            "tests/test_central_cover_clash.py",
            "tests/test_shared_source_takeover.py",
            "tests/test_area_clash.py",
        ],
        "equivalent": (
            "de rang bevat de zone-id, dus twee verzoeken hebben nooit dezelfde "
            "rang en `<=` en `<` kunnen niet verschillen"
        ),
    },
    {
        "name": "gebied-M4-verliezers-en-eigenaars-verwisseld",
        "file": "custom_components/climate_director/engine/takeover.py",
        "old": "for loser in rivals if best else owners:",
        "new": "for loser in owners if best else rivals:",
        "tests": [
            "tests/test_central_cover_clash.py",
            "tests/test_shared_source_takeover.py",
            "tests/test_area_clash.py",
        ],
    },
    {
        "name": "gebied-M5-kept.pop-wordt-get",
        "file": "custom_components/climate_director/engine/takeover.py",
        "old": "dropped[loser.zone.zone_id] = kept.pop(loser.zone.zone_id)",
        "new": "dropped[loser.zone.zone_id] = kept.get(loser.zone.zone_id)",
        "tests": [
            "tests/test_central_cover_clash.py",
            "tests/test_shared_source_takeover.py",
            "tests/test_area_clash.py",
        ],
    },
    {
        "name": "gebied-M6-beste-eigenaar-wordt-slechtste",
        "file": "custom_components/climate_director/engine/takeover.py",
        "old": "best = min(owners, key=lambda r: r.rank).rank",
        "new": "best = max(owners, key=lambda r: r.rank).rank",
        "tests": [
            "tests/test_central_cover_clash.py",
            "tests/test_shared_source_takeover.py",
            "tests/test_area_clash.py",
        ],
    },
    {
        "name": "gebied-M7-beste-rivaal-wordt-slechtste",
        "file": "custom_components/climate_director/engine/takeover.py",
        "old": "<= min(rivals, key=lambda r: r.rank).rank",
        "new": "<= max(rivals, key=lambda r: r.rank).rank",
        "tests": [
            "tests/test_central_cover_clash.py",
            "tests/test_shared_source_takeover.py",
            "tests/test_area_clash.py",
        ],
    },
    {
        "name": "gebied-M8-alleen-stoppen-als-beide-leeg",
        "file": "custom_components/climate_director/engine/takeover.py",
        "old": "if not owners or not rivals:",
        "new": "if not owners and not rivals:",
        "tests": [
            "tests/test_central_cover_clash.py",
            "tests/test_shared_source_takeover.py",
            "tests/test_area_clash.py",
        ],
    },
    {
        "name": "gebied-M9-rivaal-hoeft-niet-in-het-gebied",
        "file": "custom_components/climate_director/engine/takeover.py",
        "old": (
            "r for r in kept.values() if r.source.entity_id != entity_id and r.zone.zone_id in area"
        ),
        "new": "r for r in kept.values() if r.source.entity_id != entity_id",
        "tests": [
            "tests/test_central_cover_clash.py",
            "tests/test_shared_source_takeover.py",
            "tests/test_area_clash.py",
        ],
    },
    {
        "name": "gebied-M10-rivaal-is-zelfde-apparaat",
        "file": "custom_components/climate_director/engine/takeover.py",
        "old": "if r.source.entity_id != entity_id and r.zone.zone_id in area",
        "new": "if r.source.entity_id == entity_id and r.zone.zone_id in area",
        "tests": [
            "tests/test_central_cover_clash.py",
            "tests/test_shared_source_takeover.py",
            "tests/test_area_clash.py",
        ],
    },
    {
        "name": "gebied-M11-aanroep-weg-in-candidates",
        "file": "custom_components/climate_director/engine/candidates.py",
        "old": "kept, dropped = takeover.area_clash(config, wishes, takeovers)",
        "new": "kept, dropped = dict(wishes), {}",
        "tests": [
            "tests/test_central_cover_clash.py",
            "tests/test_shared_source_takeover.py",
            "tests/test_area_clash.py",
        ],
    },
    {
        "name": "gebied-M12-overnames-niet-doorgegeven",
        "file": "custom_components/climate_director/engine/grants.py",
        "old": "apply_exclusive_groups(config, world, wishes, takeovers)",
        "new": "apply_exclusive_groups(config, world, wishes)",
        "tests": [
            "tests/test_central_cover_clash.py",
            "tests/test_shared_source_takeover.py",
            "tests/test_area_clash.py",
        ],
    },
    {
        "name": "gebied-M13-gebieden-gesorteerd-weg-eigenaren-alle",
        "file": "custom_components/climate_director/engine/takeover.py",
        "old": "owners = [r for r in kept.values() if r.source.entity_id == entity_id]",
        "new": "owners = [r for r in kept.values() if r.source.entity_id == entity_id][:1]",
        "tests": [
            "tests/test_central_cover_clash.py",
            "tests/test_shared_source_takeover.py",
            "tests/test_area_clash.py",
        ],
    },
]


def run_one(mutation: dict[str, object]) -> str:
    """Apply one mutation in place, run its tests and put the file back."""
    path = REPO / str(mutation["file"])
    with open(path, encoding="utf-8", newline="") as handle:
        original = handle.read()
    old, new = str(mutation["old"]), str(mutation["new"])
    if original.count(old) != 1:
        return f"PATROON {original.count(old)}x gevonden / pattern found {original.count(old)}x"
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(original.replace(old, new, 1))
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-x",
                "-p",
                "no:cacheprovider",
                "--no-header",
                *list(mutation["tests"]),  # type: ignore[call-overload]
            ],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
    finally:
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(original)
    if result.returncode != 0:
        return "gevangen"
    return "gelijkwaardig, groen zoals verwacht" if "equivalent" in mutation else "OVERLEEFD"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lane", type=int, default=0)
    parser.add_argument("--lanes", type=int, default=1)
    parser.add_argument("--only", help="alleen deze mutaties, komma-gescheiden")
    args = parser.parse_args()
    only = set(args.only.split(",")) if args.only else None
    survivors: list[str] = []
    for index, mutation in enumerate(REVIEW_MUTATIONS):
        if index % args.lanes != args.lane or (only and mutation["name"] not in only):
            continue
        verdict = run_one(mutation)
        print(f"{mutation['name']}: {verdict}", flush=True)
        if verdict.startswith(("OVERLEEFD", "PATROON")):
            survivors.append(str(mutation["name"]))
    print("ongedekt: " + (", ".join(survivors) if survivors else "geen"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
