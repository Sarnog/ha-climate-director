"""Stille problemen zichtbaar maken in Home Assistant zelf.

Surfacing quiet problems in Home Assistant itself.

Twee soorten, met dezelfde reden om te bestaan: een fout in de configuratie en
een gebeurtenis waar niemand naar luistert zien er van buiten allebei hetzelfde
uit als "de director besluit niets".

Two kinds, with the same reason to exist: a mistake in the configuration and an
event nobody listens for both look, from the outside, the same as "the director
decides nothing".

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

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from . import texts
from .const import DOMAIN, EVENT_PRECONDITION_REFUSED
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
    template = texts.lookup(hass, code)
    if template is None:
        return str(problem)
    try:
        return template.format(**getattr(problem, "params", {}))
    except (KeyError, IndexError, ValueError):
        return str(problem)


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


#: De melding dat er niemand naar een geweigerd vooruit-verzoek luistert. Eén
#: melding voor de hele integratie, niet per installatie: de gebeurtenis is
#: domeinbreed, dus twee identieke meldingen zouden alleen maar herhalen.
#:
#: The notice that nobody is listening for a refused pre-conditioning request.
#: One notice for the whole integration rather than one per installation: the
#: event is domain-wide, so two identical notices would merely repeat.
UNWATCHED_ISSUE = "precondition_unwatched"

#: Waar de melding heen wijst: het hoofdstuk dat de blueprints uitlegt.
#: Where the notice points: the chapter explaining the blueprints.
BLUEPRINTS_URL = (
    "https://github.com/Sarnog/ha-climate-director#must-have-automatiseringen-en-notificaties"
)


@callback
def async_check_watchers(hass: HomeAssistant) -> bool:
    """Raise or clear the notice about a refusal nobody hears, and return who hears.

    Een vooruit-verzoek dat op een openstaand raam strandt meldt zichzelf op de
    bus en verder nergens. Luistert daar niemand naar, dan is het van buiten
    niet te onderscheiden van een knop die niets doet - en dan is de knop stuk,
    ook al werkt hij precies zoals bedoeld.

    Daarom staat deze melding er meteen, en niet pas nadat er een verzoek
    geweigerd is: een halve functie is geen functie. Wie hem wegwerkt moet de
    blueprint niet alleen importeren maar ook instellen, want een geïmporteerde
    blueprint zonder automatisering luistert nog steeds nergens naar.

    A pre-conditioning request stranding on an open window reports itself on the
    bus and nowhere else. If nobody listens, that is indistinguishable from a
    button that does nothing - and then the button is broken, however exactly it
    works as intended.

    Hence this notice stands from the start rather than only after a request has
    been refused: half a feature is no feature. Clearing it means not merely
    importing the blueprint but setting it up, since an imported blueprint
    without an automation still listens to nothing.
    """
    listeners = hass.bus.async_listeners().get(EVENT_PRECONDITION_REFUSED, 0)

    if listeners:
        ir.async_delete_issue(hass, DOMAIN, UNWATCHED_ISSUE)
        return True

    ir.async_create_issue(
        hass,
        DOMAIN,
        UNWATCHED_ISSUE,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=UNWATCHED_ISSUE,
        learn_more_url=BLUEPRINTS_URL,
    )
    return False


@callback
def async_clear_watchers(hass: HomeAssistant) -> None:
    """Drop the notice, for when the last installation goes away."""
    ir.async_delete_issue(hass, DOMAIN, UNWATCHED_ISSUE)
