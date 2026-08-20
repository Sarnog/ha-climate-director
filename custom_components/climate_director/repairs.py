"""De oplosflow voor de eenmalige handbediend-melding.

The fix flow for the one-time hand-operated notice.

Een handbediende unit is geen fout, dus deze flow repareert niets: hij
bevestigt alleen dat de gebruiker de situatie kent en bewaart die bevestiging
in de configuratie. Dezelfde situatie meldt zich daarna niet opnieuw, ook niet
na een herstart; verandert wélke taken handbediend zijn, dan volgt een nieuwe
melding.

A hand-operated unit is no mistake, so this flow fixes nothing: it merely
confirms the user is aware of the situation and stores that confirmation in the
configuration. The same situation then stays quiet, across restarts too; when
which duties are hand-operated changes, a fresh notice follows.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.repairs.models import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import CONF_MANUAL_SOURCES_SEEN


class ManualSourcesFlow(RepairsFlow):
    """Ask for a confirmation and remember it in the configuration."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        """Show the confirmation, then store it on submit."""
        if user_input is not None:
            data = self.data or {}
            entry_id = data.get("entry_id")
            signature = data.get("signature") or ""
            entry = self.hass.config_entries.async_get_entry(entry_id) if entry_id else None
            if entry is not None:
                options = dict(entry.options)
                options[CONF_MANUAL_SOURCES_SEEN] = signature
                self.hass.config_entries.async_update_entry(entry, options=options)
            return self.async_create_entry(data={})

        issue_registry = ir.async_get(self.hass)
        description_placeholders = None
        if issue := issue_registry.async_get_issue(self.handler, self.issue_id):
            description_placeholders = issue.translation_placeholders

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({}),
            description_placeholders=description_placeholders,
        )


async def async_create_fix_flow(
    _hass: HomeAssistant,
    _issue_id: str,
    _data: dict[str, Any] | None,
) -> RepairsFlow:
    """Return the flow that resolves the hand-operated notice."""
    return ManualSourcesFlow()
