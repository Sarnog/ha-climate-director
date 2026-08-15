"""Configuratieproblemen zichtbaar maken in Home Assistant zelf.

Surfacing configuration problems in Home Assistant itself.

`validate()` vindt structurele fouten, maar tot nu toe kwamen die alleen in de
diagnose terecht. Dat is precies verkeerd tijdens een schaduwrun: een zone met
een verkeerd venster of zonder bruikbare bron ziet er van buiten hetzelfde uit
als "de director besluit niets", en dan ga je een bug zoeken die eigenlijk een
typefout in de configuratie is.

`validate()` finds structural mistakes, but until now those only reached the
diagnostics. That is exactly the wrong place during a shadow run: a zone with a
wrong window or without a usable source looks, from the outside, the same as
"the director decides nothing", and you end up hunting a bug that is really a
typo in the configuration.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN
from .engine import DirectorConfig, validate

#: Hoeveel problemen er hoogstens in de melding zelf komen te staan. De rest
#: staat in de diagnose; een reparatiemelding van dertig regels leest niemand.
#:
#: How many problems at most go into the notification itself. The rest are in
#: the diagnostics; nobody reads a thirty-line repair notice.
MAX_LISTED = 5


def _issue_id(entry_id: str) -> str:
    """Return the issue id for one installation."""
    return f"invalid_config_{entry_id}"


def async_report(
    hass: HomeAssistant, entry_id: str, title: str, config: DirectorConfig
) -> tuple[str, ...]:
    """Raise or clear the repair notice for one installation, and return its problems.

    A warning rather than an error: the director carries on regulating every
    sound zone, so a flawed configuration degrades the installation without
    stopping it. Calling this again with a sound configuration removes the
    notice, so a fixed problem disappears on the next reload without anything
    else having to remember it was there.
    """
    problems = validate(config)

    if not problems:
        ir.async_delete_issue(hass, DOMAIN, _issue_id(entry_id))
        return ()

    ir.async_create_issue(
        hass,
        DOMAIN,
        _issue_id(entry_id),
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="invalid_config",
        translation_placeholders={
            "name": title,
            "count": str(len(problems)),
            "problems": summarise(problems),
        },
    )
    return problems


def summarise(problems: tuple[str, ...]) -> str:
    """Return the problem list as it appears in the notice, capped in length."""
    listed = [f"- {problem}" for problem in problems[:MAX_LISTED]]
    remaining = len(problems) - MAX_LISTED
    if remaining > 0:
        listed.append(f"- ... and {remaining} more")
    return "\n".join(listed)


def async_clear(hass: HomeAssistant, entry_id: str) -> None:
    """Drop the repair notice for one installation."""
    ir.async_delete_issue(hass, DOMAIN, _issue_id(entry_id))
