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

    def __init__(self) -> None:
        """Track whether the first call (which opens the form) has happened."""
        super().__init__()
        self._shown = False

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        """Show the confirmation, then store it on submit.

        De flow-manager van Home Assistant opent de fix-flow door
        `async_step_init` met `{"issue_id": ...}` aan te roepen. Zonder deze
        wacht zou die openingsaanroep als bevestiging tellen en verdween de
        melding zonder dat er ooit een dialoog verscheen — precies wat
        `ConfirmRepairFlow` uit core omzeilt door de openingsaanroep te negeren.
        Hier gebeurt hetzelfde in één stap: de eerste aanroep toont het
        formulier, de tweede (met `user_input`) bevestigt.

        Home Assistant's flow manager opens the fix flow by calling
        `async_step_init` with `{"issue_id": ...}`. Without this guard that
        opening call would count as a confirmation and the notice would
        disappear without a dialog ever appearing — exactly what core's
        `ConfirmRepairFlow` avoids by ignoring the opening call. The same
        happens here in a single step: the first call shows the form, the
        second (with `user_input`) confirms.
        """
        if self._shown and user_input is not None:
            data = self.data or {}
            entry_id = data.get("entry_id")
            signature = data.get("signature") or ""
            entry = self.hass.config_entries.async_get_entry(entry_id) if entry_id else None
            if entry is not None:
                options = dict(entry.options)
                options[CONF_MANUAL_SOURCES_SEEN] = signature
                self.hass.config_entries.async_update_entry(entry, options=options)
            return self.async_create_entry(data={})

        self._shown = True
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
