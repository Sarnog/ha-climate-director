"""Downloadbare diagnostiek.

Downloadable diagnostics.

Bevat de configuratie, de laatst gelezen momentopname en het laatste plan. Met
die drie is elke beslissing exact na te spelen in een unit test, zonder toegang
tot de installatie waar hij vandaan komt.

Holds the configuration, the last snapshot read and the last plan. With those
three, any decision is exactly reproducible in a unit test, without access to
the installation it came from.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics.util import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_SHADOW_MODE, DEFAULT_SHADOW_MODE
from .coordinator import ClimateDirectorEntry
from .engine import Plan, WorldState, validate
from .engine.serialise import config_to_dict


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ClimateDirectorEntry
) -> dict[str, Any]:
    """Return everything needed to reproduce the current decision.

    Aanwezigheids- en slaapgegevens worden weggelakt: een diagnose gaat routineus
    een GitHub-issue in, en wie er thuis is, slaapt, en wanneer, is een
    inbraakprofiel. Alles wat een beslissing naspeelt blijft staan.

    Presence and sleep data are redacted: a diagnostics download routinely ends
    up in a GitHub issue, and who is home, asleep, and when, is a burglary
    profile. Everything that replays a decision stays in.
    """
    coordinator = entry.runtime_data
    found = {
        "shadow_mode": entry.options.get(CONF_SHADOW_MODE, DEFAULT_SHADOW_MODE),
        "installation": config_to_dict(coordinator.config),
        "problems": list(validate(coordinator.config)),
        "control_state": {
            "master_enabled": coordinator.master_enabled,
            "holiday_mode": coordinator.holiday_mode,
            "guest_mode": coordinator.guest_mode,
            "season_override": (
                coordinator.season_override.value
                if coordinator.season_override is not None
                else None
            ),
            "zone_overrides": dict(coordinator.zone_overrides),
            "zone_priorities": dict(coordinator.zone_priorities),
            "precondition_requests": {
                zone_id: until.isoformat()
                for zone_id, until in coordinator.live_preconditions().items()
            },
        },
        "tracked_entities": sorted(coordinator.tracked_entities()),
        "world": _world(coordinator.world),
        "plan": _plan(coordinator.data),
        "would_change": [change.entity_id for change in coordinator.last_changes],
        "did_change": [change.entity_id for change in coordinator.last_applied],
    }
    # `home`/`asleep` zitten in de wereldmomentopname, `presence` (met
    # `occupied` en tijdstempel) ook, en `presence_entity`/`sleep_entity`/
    # `windows`/`sleep_window`/`wake_deadline` in de installatie: precies het
    # bewonersprofiel
    # dat hierboven benoemd is. `occupied` staat er apart bij voor het geval
    # kameraanwezigheid ooit buiten `presence` om wordt weggeschreven.
    #
    # `home`/`asleep` sit in the world snapshot, `presence` (with `occupied`
    # and its timestamp) too, and `presence_entity`/`sleep_entity`/`windows`/
    # `sleep_window`/`wake_deadline` in the installation: exactly the resident
    # profile named
    # above. `occupied` is listed separately in case room presence is ever
    # written outside `presence`.
    return async_redact_data(
        found,
        [
            "home",
            "asleep",
            "presence",
            "occupied",
            "presence_entity",
            "sleep_entity",
            "windows",
            "sleep_window",
            "wake_deadline",
        ],
    )


def _world(world: WorldState | None) -> dict[str, Any] | None:
    """Return the last snapshot as plain data."""
    if world is None:
        return None
    return {
        "now": world.now.isoformat(),
        "outdoor_temperature": world.outdoor_temperature,
        "season": world.season.value,
        "indoor_temperatures": dict(world.indoor_temperatures),
        "climates": {
            entity_id: {
                "hvac_mode": state.hvac_mode,
                "current_temperature": state.current_temperature,
                "target_temperature": state.target_temperature,
                "available": state.available,
                "changed_at": state.changed_at.isoformat() if state.changed_at else None,
            }
            for entity_id, state in world.climates.items()
        },
        "residents": {
            resident_id: {"home": state.home, "asleep": state.asleep}
            for resident_id, state in world.residents.items()
        },
        "openings": {
            entity_id: {
                "open": state.open,
                "changed_at": state.changed_at.isoformat() if state.changed_at else None,
            }
            for entity_id, state in world.openings.items()
        },
        "presence": {
            zone_id: {
                "occupied": state.occupied,
                "changed_at": state.changed_at.isoformat() if state.changed_at else None,
            }
            for zone_id, state in world.presence.items()
        },
        "precondition_until": {
            zone_id: until.isoformat() for zone_id, until in world.precondition_until.items()
        },
        "precondition_bypass": sorted(world.precondition_bypass),
        "guest_mode": world.guest_mode,
        "precipitation": world.precipitation,
        "zone_priorities": dict(world.zone_priorities),
        "circuit_family_since": {
            circuit_id: moment.isoformat() if moment else None
            for circuit_id, moment in world.circuit_family_since.items()
        },
        "master_enabled": world.master_enabled,
        "holiday_mode": world.holiday_mode,
        "zone_overrides": dict(world.zone_overrides),
    }


def _plan(plan: Plan | None) -> dict[str, Any] | None:
    """Return the last plan as plain data."""
    if plan is None:
        return None
    return {
        "commands": [
            {
                "entity_id": command.entity_id,
                "hvac_mode": command.hvac_mode,
                "temperature": command.temperature,
                "zone_id": command.zone_id,
                "source_id": command.source_id,
                "reason": command.reason.value,
            }
            for command in plan.commands
        ],
        "zones": [
            {
                "zone_id": zone.zone_id,
                "wanted": zone.wanted.value,
                "granted": zone.granted.value,
                "source_id": zone.source_id,
                "reason": zone.reason.value,
                "closed_gates": [reason.value for reason in zone.closed_gates],
            }
            for zone in plan.zones
        ],
        "circuits": [
            {
                "circuit_id": circuit.circuit_id,
                "family": circuit.family.value,
                "winner_zone_id": circuit.winner_zone_id,
                "displaced_zone_ids": list(circuit.displaced_zone_ids),
                "reason": circuit.reason.value,
            }
            for circuit in plan.circuits
        ],
        "deferrals": [
            {
                "subject": deferral.subject,
                "until": deferral.until.isoformat(),
                "reason": deferral.reason.value,
            }
            for deferral in plan.deferrals
        ],
        "untouched": [
            {
                "entity_id": item.entity_id,
                "zone_id": item.zone_id,
                "reason": item.reason.value,
            }
            for item in plan.untouched
        ],
    }
