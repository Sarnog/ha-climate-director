"""De handbediend-melding van kaart tot bevestiging, in een echt huis.

The hand-operated notice from card to confirmation, in a real house.

De stand-in-tests in `test_watchdog.py` bewaken de logica van de melding en van
de oplosflow; deze test bewaakt de keten: de melding wordt via de échte
`issue_registry` aangemaakt, het reparatieformulier wordt werkelijk getekend en
bevestigd, de handtekening belandt in de entry-opties en de melding komt na een
herstart niet terug.

The stand-in tests in `test_watchdog.py` guard the logic of the notice and of
the fix flow; this test guards the chain: the notice is created through the
real `issue_registry`, the repair form is really drawn and confirmed, the
signature lands in the entry options and the notice does not return after a
restart.
"""

from __future__ import annotations

from typing import Any

from harness_live import settings, source, start_house, stop_house, zone

from custom_components.climate_director.const import CONF_MANUAL_SOURCES_SEEN, DOMAIN

LIVING = "climate.woonkamer"
ENTRY_ID = "handbediend"


def installation() -> dict[str, Any]:
    """Return one room whose only source is hand-operated."""
    return {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("airco", LIVING, role="heat_cool", autostart=False)],
                heat=settings(21.0, 20.0),
            )
        ]
    }


def states() -> dict[str, tuple[str, dict[str, Any]]]:
    return {"sensor.woonkamer": ("18.0", {}), LIVING: ("off", {})}


async def test_the_hand_operated_notice_runs_the_whole_chain() -> None:
    """Kaart, dialoog, bevestiging en herstart, allemaal tegen de echte registers.

    Card, dialog, confirmation and restart, all against the real registries.
    """
    from homeassistant.helpers import issue_registry as ir

    home = await start_house(installation(), states=states(), entry_id=ENTRY_ID)
    config_dir = home.config_dir
    try:
        registry = ir.async_get(home.hass)
        issue = registry.async_get_issue(DOMAIN, f"manual_sources_{ENTRY_ID}")
        assert issue is not None, "de handbediend-melding hoort in de echte issue_registry te staan"
        assert issue.is_fixable is True
        assert issue.translation_key == "manual_sources"
        assert issue.translation_placeholders["name"] == home.entry.title
        assert issue.translation_placeholders["count"] == "1"
        assert issue.translation_placeholders["problems"]

        from homeassistant.components.repairs import DOMAIN as REPAIRS_DOMAIN

        flow_manager = home.hass.data[REPAIRS_DOMAIN]["flow_manager"]
        result = await flow_manager.async_init(DOMAIN, data={"issue_id": issue.issue_id})
        assert result["type"] == "form", (
            "de échte flow-manager hoort het reparatiedialoog te tonen, niet meteen te sluiten"
        )
        assert result["step_id"] == "init"
        assert result["description_placeholders"] == issue.translation_placeholders, (
            "het reparatiedialoog hoort de placeholders van zijn melding door te geven"
        )
        assert set(issue.translation_placeholders) == {"name", "count", "problems"}

        result = await flow_manager.async_configure(result["flow_id"], {})
        assert result["type"] == "create_entry"
        await home.hass.async_block_till_done()

        assert home.entry.options.get(CONF_MANUAL_SOURCES_SEEN), (
            "de handtekening hoort in de entry-opties te staan"
        )
        assert registry.async_get_issue(DOMAIN, f"manual_sources_{ENTRY_ID}") is None, (
            "de melding hoort na de bevestiging weg te zijn"
        )
    finally:
        await stop_house(home)

    restarted = await start_house(
        installation(), states=states(), config_dir=config_dir, entry_id=ENTRY_ID
    )
    try:
        registry = ir.async_get(restarted.hass)
        assert registry.async_get_issue(DOMAIN, f"manual_sources_{ENTRY_ID}") is None, (
            "de melding hoort na een herstart niet terug te komen"
        )
    finally:
        await stop_house(restarted)
