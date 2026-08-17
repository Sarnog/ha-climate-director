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
from homeassistant.helpers import translation

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
            "problems": summarise(hass, problems),
        },
    )
    return problems


def readable(hass: HomeAssistant, problem: str) -> str:
    """Return one complaint in the user's language, or its English text.

    De engine kent geen Home Assistant en schrijft dus Engels. Draagt een
    melding een code, dan zoeken we die hier op; zo niet, dan blijft de Engelse
    zin staan. Een melding zonder vertaling is daarmee nooit slechter af dan hij
    was - en beter half vertaald dan een lijst die half Nederlands is.

    The engine knows no Home Assistant and therefore writes English. If a
    complaint carries a code we look it up here; if not, the English sentence
    stays. A complaint without a translation is thereby never worse off than it
    was - and better than a list that is half translated.
    """
    code = getattr(problem, "code", "")
    if not code:
        return str(problem)
    template = _translated(hass, code)
    if template is None:
        return str(problem)
    try:
        return template.format(**getattr(problem, "params", {}))
    except (KeyError, IndexError):
        return str(problem)


def _translated(hass: HomeAssistant, code: str) -> str | None:
    """Return the translated template for one problem code, if there is one."""
    key = f"component.{DOMAIN}.problems.{code}"
    cached = translation.async_get_cached_translations(hass, hass.config.language, "problems")
    return cached.get(key)


def summarise(hass: HomeAssistant, problems: tuple[str, ...]) -> str:
    """Return the problem list as it appears in the notice, capped in length."""
    listed = [f"- {readable(hass, problem)}" for problem in problems[:MAX_LISTED]]
    remaining = len(problems) - MAX_LISTED
    if remaining > 0:
        listed.append(f"- ... and {remaining} more")
    return "\n".join(listed)


def async_clear(hass: HomeAssistant, entry_id: str) -> None:
    """Drop the repair notice for one installation."""
    ir.async_delete_issue(hass, DOMAIN, _issue_id(entry_id))
