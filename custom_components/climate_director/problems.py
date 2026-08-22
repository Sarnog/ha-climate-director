"""Stille problemen zichtbaar maken in Home Assistant zelf.

Surfacing quiet problems in Home Assistant itself.

Drie soorten, met dezelfde reden om te bestaan: een fout in de configuratie,
een entiteit die niet te lezen is, en een gebeurtenis waar niemand naar
luistert zien er van buiten alle drie hetzelfde uit als "de director besluit
niets".

Three kinds, with the same reason to exist: a mistake in the configuration, an
entity that cannot be read, and an event nobody listens for all look, from the
outside, the same as "the director decides nothing".

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

from collections.abc import Mapping
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from . import texts
from .const import CONF_MANUAL_SOURCES_SEEN, DOMAIN, EVENT_PRECONDITION_REFUSED
from .engine import DirectorConfig, Problem, manual_only_problems, validate

#: Hoeveel problemen er hoogstens in de melding zelf komen te staan. De rest
#: staat in de diagnose; een reparatiemelding van dertig regels leest niemand.
#:
#: How many problems at most go into the notification itself. The rest are in
#: the diagnostics; nobody reads a thirty-line repair notice.
MAX_LISTED = 5


def _issue_id(entry_id: str) -> str:
    """Return the issue id for one installation."""
    return f"invalid_config_{entry_id}"


def _manual_issue_id(entry_id: str) -> str:
    """Return the one-time notice id for one installation."""
    return f"manual_sources_{entry_id}"


def _manual_signature(found: tuple[Problem, ...]) -> str:
    """Return a stable fingerprint of which duties are hand-operated only.

    De vingerafdruk bestaat uit zone en taak, niet uit namen of vertalingen.
    Verandert er iets aan wélke taken handbediend zijn, dan verandert hij mee
    en komt de melding opnieuw - precies wat je wilt: een nieuwe situatie is
    een nieuwe melding waard, maar dezelfde situatie zeurt niet opnieuw.

    The fingerprint is made of zone and duty, not names or translations. When
    which duties are hand-operated changes, so does the fingerprint and the
    notice returns - exactly what you want: a new situation deserves a new
    notice, but the same situation does not nag twice.
    """
    return ",".join(sorted(f"{item.params['zone_id']}:{item.params['mode']}" for item in found))


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
    """Return the problem list as it appears in the notice, capped in length.

    De "en nog N meer"-regel gaat door `texts` heen: een hardcoded Engelse
    zin onder een vertaalde lijst leest als een fout. Engels blijft de
    terugval als er geen vertaling is.

    The "and N more" line goes through `texts`: a hardcoded English sentence
    under a translated list reads as a fault. English stays the fallback when
    no translation exists.
    """
    listed = [f"- {readable(hass, problem)}" for problem in problems[:MAX_LISTED]]
    remaining = len(problems) - MAX_LISTED
    if remaining > 0:
        listed.append(
            texts.translated(
                hass,
                "and_n_more",
                f"- ... and {remaining} more",
                remaining=remaining,
            )
        )
    return "\n".join(listed)


def async_clear(hass: HomeAssistant, entry_id: str) -> None:
    """Drop the repair notice for one installation."""
    ir.async_delete_issue(hass, DOMAIN, _issue_id(entry_id))


def async_report_manual_sources(
    hass: HomeAssistant,
    entry_id: str,
    title: str,
    options: Mapping[str, Any],
    config: DirectorConfig,
) -> tuple[Problem, ...]:
    """Raise or clear the one-time notice about hand-operated-only duties.

    De melding is oplosbaar via een fix-flow die de vingerafdruk in de
    configuratie bewaart; zolang die klopt, komt dezelfde melding na een
    herstart niet terug. Verdwijnt de situatie (autostart aangezet of de taak
    eruit), dan gaat de melding vanzelf weg; verschijnt er een nieuwe
    handbediende taak, dan is dat een nieuwe melding waard.

    The notice is resolvable through a fix flow that stores the fingerprint in
    the configuration; as long as it matches, the same notice does not return
    after a restart. When the situation disappears (autostart switched on or
    the duty removed) the notice clears by itself; a newly hand-operated duty
    deserves a new notice.
    """
    found = manual_only_problems(config)
    signature = _manual_signature(found)
    seen = options.get(CONF_MANUAL_SOURCES_SEEN, "")

    if not found or seen == signature:
        ir.async_delete_issue(hass, DOMAIN, _manual_issue_id(entry_id))
        return found

    ir.async_create_issue(
        hass,
        DOMAIN,
        _manual_issue_id(entry_id),
        is_fixable=True,
        data={"entry_id": entry_id, "signature": signature},
        severity=ir.IssueSeverity.WARNING,
        translation_key="manual_sources",
        translation_placeholders={
            "name": title,
            "count": str(len(found)),
            "problems": summarise(hass, found),
        },
    )
    return found


def async_clear_manual_sources(hass: HomeAssistant, entry_id: str) -> None:
    """Drop the one-time notice for one installation."""
    ir.async_delete_issue(hass, DOMAIN, _manual_issue_id(entry_id))


def _unreadable_issue_id(entry_id: str) -> str:
    """Return the unreadable-entity notice id for one installation."""
    return f"unreadable_entities_{entry_id}"


def async_report_unreadable(
    hass: HomeAssistant, entry_id: str, title: str, found: Mapping[str, str]
) -> None:
    """Raise or clear the notice about entities that cannot be read.

    Een verkeerd getikte entiteit bestaat niet, en een sensor die wegvalt leest
    als niets. Er valt dan niets om: de poort die erop leunt gaat dicht, de zone
    doet niets, en van buiten is dat niet te onderscheiden van een zone die
    niets hoeft te doen. Tot nu toe stond dat alleen in een attribuut van de
    vastloopmelder, en daar moest je dus al naar zoeken.

    Juist bij een onleesbare binnentemperatuur laat de director een draaiend
    apparaat met rust, en houdt dat apparaat zijn circuit bezet. Dat is precies
    het moment waarop dit hoort op te vallen.

    A mistyped entity does not exist, and a sensor that drops out reads as
    nothing. Nothing breaks: the gate leaning on it closes, the zone does
    nothing, and from the outside that is indistinguishable from a zone with
    nothing to do. Until now that only lived in an attribute of the stuck
    sensor, which you had to be looking for already.

    With an unreadable indoor temperature in particular the director leaves a
    running appliance alone, and that appliance holds its circuit. Which is
    exactly the moment this should stand out.
    """
    if not found:
        ir.async_delete_issue(hass, DOMAIN, _unreadable_issue_id(entry_id))
        return

    listed = "\n".join(f"- `{entity_id}` ({state})" for entity_id, state in sorted(found.items()))
    ir.async_create_issue(
        hass,
        DOMAIN,
        _unreadable_issue_id(entry_id),
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="unreadable_entities",
        translation_placeholders={
            "name": title,
            "count": str(len(found)),
            "entities": listed,
        },
    )


def async_clear_unreadable(hass: HomeAssistant, entry_id: str) -> None:
    """Drop the unreadable-entity notice for one installation."""
    ir.async_delete_issue(hass, DOMAIN, _unreadable_issue_id(entry_id))


def _unsupported_modes_issue_id(entry_id: str) -> str:
    """Return the unsupported-modes notice id for one installation."""
    return f"unsupported_modes_{entry_id}"


def async_report_unsupported_modes(
    hass: HomeAssistant, entry_id: str, title: str, found: Mapping[str, str]
) -> None:
    """Raise or clear the notice about roles asking modes the appliance cannot run.

    Een bron met rol HEAT_COOL op een apparaat dat alleen `heat` en `off` meldt,
    wordt voor koelen overgeslagen. De zone doet dan in stilte niets - precies
    de klasse fout waar de onleesbare-entiteitenmelding voor bestaat. Dit is
    geen apparaatstoring maar een instelfout, en die hoort net zo zichtbaar te
    zijn.

    A source with role HEAT_COOL on an appliance reporting only `heat` and
    `off` is skipped for cooling. The zone then silently does nothing - exactly
    the class of fault the unreadable-entities notice exists for. This is not an
    appliance fault but a configuration mistake, and it deserves to be just as
    visible.
    """
    if not found:
        ir.async_delete_issue(hass, DOMAIN, _unsupported_modes_issue_id(entry_id))
        return

    listed = "\n".join(f"- `{entity_id}` ({modes})" for entity_id, modes in sorted(found.items()))
    ir.async_create_issue(
        hass,
        DOMAIN,
        _unsupported_modes_issue_id(entry_id),
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="unsupported_modes",
        translation_placeholders={
            "name": title,
            "count": str(len(found)),
            "entities": listed,
        },
    )


def async_clear_unsupported_modes(hass: HomeAssistant, entry_id: str) -> None:
    """Drop the unsupported-modes notice for one installation."""
    ir.async_delete_issue(hass, DOMAIN, _unsupported_modes_issue_id(entry_id))


def _command_not_taking_issue_id(entry_id: str) -> str:
    """Return the command-not-taking notice id for one installation."""
    return f"command_not_taking_{entry_id}"


def async_report_command_not_taking(
    hass: HomeAssistant, entry_id: str, title: str, found: Mapping[str, str]
) -> None:
    """Raise or clear the notice about appliances that never take their command.

    Het verschil tussen het plan en de werkelijkheid wordt elke ronde opnieuw
    aangeboden zolang het apparaat niet meebeweegt. Neemt het de aanroep aan
    zonder er iets mee te doen - of zet het zichzelf meteen terug - dan levert
    dat met de vangnetklok ruim veertienhonderd mislukte aanroepen per dag op,
    en van buiten ziet dat er precies zo uit als een zone die niets hoeft.

    The difference between the plan and reality is offered again every round for
    as long as the appliance does not move with it. If it accepts the call
    without doing anything with it - or puts itself straight back - that adds up
    to well over fourteen hundred failed calls a day on the safety-net clock,
    and from the outside it looks exactly like a zone with nothing to do.
    """
    if not found:
        ir.async_delete_issue(hass, DOMAIN, _command_not_taking_issue_id(entry_id))
        return

    listed = "\n".join(f"- `{entity_id}` ({wanted})" for entity_id, wanted in sorted(found.items()))
    ir.async_create_issue(
        hass,
        DOMAIN,
        _command_not_taking_issue_id(entry_id),
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="command_not_taking",
        translation_placeholders={
            "name": title,
            "count": str(len(found)),
            "entities": listed,
        },
    )


def async_clear_command_not_taking(hass: HomeAssistant, entry_id: str) -> None:
    """Drop the command-not-taking notice for one installation."""
    ir.async_delete_issue(hass, DOMAIN, _command_not_taking_issue_id(entry_id))


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
BLUEPRINTS_URL = "https://github.com/Sarnog/ha-climate-director#blueprints"


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
