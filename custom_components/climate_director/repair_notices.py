"""De bijzondere reparatiemeldingen.

The specialised repair notices.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN, EVENT_PRECONDITION_REFUSED

UNWATCHED_ISSUE = "precondition_unwatched"
BLUEPRINTS_URL = "https://github.com/Sarnog/ha-climate-director#blueprints"

_LOGGER = logging.getLogger(__name__)


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


def _season_excludes_mode_issue_id(entry_id: str) -> str:
    """Return the season-excludes-mode notice id for one installation."""
    return f"season_excludes_mode_{entry_id}"


def async_report_season_override(
    hass: HomeAssistant, entry_id: str, title: str, found: Mapping[str, str]
) -> None:
    """Raise or clear the notice about a season select that locks a duty out.

    De select is bedieningstoestand: staat hij op een seizoen waarin een
    ingestelde taak nooit mag draaien, dan kan die taak nooit draaien - en dat
    is van buiten niet te onderscheiden van een zone die niets hoeft. De vaste
    seizoensbron wordt door `validate()` gemeld; dit is dezelfde melding voor
    de select, die de engine niet kent.

    The select is control state: put it on a season an installed duty is never
    allowed in, and that duty can never run - from the outside that is
    indistinguishable from a zone with nothing to do. The fixed season source
    is reported by `validate()`; this is the same notice for the select, which
    the engine does not know.
    """
    if not found:
        ir.async_delete_issue(hass, DOMAIN, _season_excludes_mode_issue_id(entry_id))
        return

    listed = "\n".join(f"- `{item}`" for item in sorted(found.values()))
    ir.async_create_issue(
        hass,
        DOMAIN,
        _season_excludes_mode_issue_id(entry_id),
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="season_excludes_mode",
        translation_placeholders={
            "name": title,
            "count": str(len(found)),
            "entities": listed,
        },
    )


def async_clear_season_override(hass: HomeAssistant, entry_id: str) -> None:
    """Drop the season-excludes-mode notice for one installation."""
    ir.async_delete_issue(hass, DOMAIN, _season_excludes_mode_issue_id(entry_id))


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


def _bypassed_opening_issue_id(entry_id: str) -> str:
    """Return the notice id for openings bypassed while really open."""
    return f"bypassed_openings_{entry_id}"


def async_report_bypassed_openings(
    hass: HomeAssistant, entry_id: str, title: str, found: Mapping[str, str]
) -> None:
    """Raise or clear the notice that a bypassed opening really stands open.

    Anker 8: een overbrugde opening bestaat niet voor de director, en dat is
    precies de bedoeling - maar staat de overbrugging aan terwijl de opening
    werkelijk openstaat, dan stookt de installatie met een raam open zonder
    dat de poort er iets aan doet. Dat hoort zichtbaar te zijn, anders gaat
    een hele winter voorbij zonder dat iets het zegt.

    Anchor 8: a bypassed opening does not exist for the director, and that is
    exactly the point - but with the bypass on while the opening really stands
    open, the installation heats with a window open without the gate doing
    anything about it. That should be visible, otherwise a whole winter goes
    by without anything saying so.
    """
    if not found:
        ir.async_delete_issue(hass, DOMAIN, _bypassed_opening_issue_id(entry_id))
        return

    listed = "\n".join(f"- `{entity_id}` ({name})" for entity_id, name in sorted(found.items()))
    ir.async_create_issue(
        hass,
        DOMAIN,
        _bypassed_opening_issue_id(entry_id),
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="bypassed_openings",
        translation_placeholders={
            "name": title,
            "count": str(len(found)),
            "openings": listed,
        },
    )


def async_clear_bypassed_openings(hass: HomeAssistant, entry_id: str) -> None:
    """Drop the bypassed-openings notice for one installation."""
    ir.async_delete_issue(hass, DOMAIN, _bypassed_opening_issue_id(entry_id))


def _corrupt_storage_issue_id(entry_id: str) -> str:
    """Return the corrupt-storage notice id for one installation."""
    return f"corrupt_storage_{entry_id}"


def async_report_corrupt_storage(hass: HomeAssistant, entry_id: str, title: str, path: str) -> None:
    """Raise the notice that a by-hand state file had to be put aside.

    De melding is geen fout die de gebruiker kan repareren: het bestand was
    onleesbaar en is hernoemd, en de director draait gewoon verder met een lege
    staat. De melding vertelt dát het gebeurd is, want verzoeken en handmatige
    uitzettingen van vóór de herstart zijn daarmee weg - anders ziet dat er van
    buiten uit als een integratie die ze stilletjes vergat.

    The notice is not a mistake the user can repair: the file was unreadable
    and has been renamed, and the director simply carries on with an empty
    state. The notice tells that it happened, because requests and hand-backs
    from before the restart are gone - otherwise that looks, from the outside,
    like an integration that quietly forgot them.
    """
    ir.async_create_issue(
        hass,
        DOMAIN,
        _corrupt_storage_issue_id(entry_id),
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="corrupt_storage",
        translation_placeholders={"name": title, "path": path},
    )


def async_clear_corrupt_storage(hass: HomeAssistant, entry_id: str) -> None:
    """Drop the corrupt-storage notice for one installation."""
    ir.async_delete_issue(hass, DOMAIN, _corrupt_storage_issue_id(entry_id))


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


def async_clear_watchers(hass: HomeAssistant) -> None:
    """Drop the notice, for when the last installation goes away."""
    ir.async_delete_issue(hass, DOMAIN, UNWATCHED_ISSUE)
