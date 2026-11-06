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

from collections.abc import Iterator, Mapping
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from . import texts
from .const import CONF_MANUAL_SOURCES_SEEN, DOMAIN
from .engine import DirectorConfig, Problem, manual_only_problems, validate
from .units import display_temperature, from_celsius, temperature_unit_of

#: Welke placeholders van welke `Problem`-code temperaturen zijn. De engine
#: kent geen Home Assistant en vult ze in graden Celsius; `readable()` rekent
#: alleen de hier genoemde placeholders om, met `display_temperature`, zodat
#: de gebruiker zijn eigen eenheid ziet en de engine geen `hass` hoeft te
#: kennen. Dit lijstje is de enige plek waar die kennis staat.
#:
#: Which placeholders of which `Problem` code are temperatures. The engine knows
#: no Home Assistant and fills them in degrees Celsius; `readable()` converts
#: only the placeholders named here, with `display_temperature`, so the user
#: sees their own unit and the engine need not know `hass`. This list is the one
#: place carrying that knowledge.
TEMPERATURE_PLACEHOLDERS: dict[str, tuple[str, ...]] = {
    "target_outside_band": ("start", "target"),
}

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


def _converted_params(hass: HomeAssistant, problem: str) -> dict[str, str]:
    """Return the complaint's placeholders with temperatures in the user's unit.

    De engine vult temperatuur-placeholders als Celsius-strings (bijvoorbeeld
    `:g`-geformatteerd); de lezer hoort zijn eigen eenheid te zien, afgerond.
    Placeholders die niet in `TEMPERATURE_PLACEHOLDERS` staan, of die geen
    getal zijn, blijven ongewijzigd.

    The engine fills temperature placeholders as Celsius strings (for instance
    `:g`-formatted); the reader should see their own unit, rounded. Placeholders
    not in `TEMPERATURE_PLACEHOLDERS`, or that are no number, stay unchanged.
    """
    params = dict(getattr(problem, "params", {}))
    unit = temperature_unit_of(hass)
    for key in TEMPERATURE_PLACEHOLDERS.get(getattr(problem, "code", ""), ()):
        raw = params.get(key)
        if raw is None:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        params[key] = display_temperature(from_celsius(value, unit), unit)
    return params


def _english_template(code: str) -> str | None:
    """Return the English template for `code` from the cache `texts` filled.

    De tweede terugval van `readable()`: wanneer de vertaalcache leeg is — het
    laden is misgegaan bij het opzetten — blijft er nog steeds een Engelse zin
    over die door `_converted_params` gaat, zodat ook dán de eenheid van de
    gebruiker genoemd wordt. Alleen de rauwe engine-tekst is de allerlaatste
    terugval.

    De bestandslezing zelf hoort thuis in `texts.async_prepare` (die hem via
    `async_add_executor_job` buiten de event loop doet); hier wordt alleen de
    modulecache gelezen, zodat `readable()` synchroon kan blijven en nooit
    blokkeert.

    The second fallback of `readable()`: when the translation cache is empty —
    loading went wrong at setup — an English sentence still remains that passes
    through `_converted_params`, so even then the user's unit is named. Only the
    raw engine text is the very last fallback.

    The file read itself belongs in `texts.async_prepare` (which does it through
    `async_add_executor_job` off the event loop); here only the module cache is
    read, so `readable()` can stay synchronous and never blocks.
    """
    templates = texts.english_templates()
    if not templates:
        return None
    return templates.get(code)


def readable(hass: HomeAssistant, problem: str) -> str:
    """Return one complaint in the user's language, or its English text.

    De engine kent geen Home Assistant en schrijft dus Engels. Draagt een
    melding een code, dan zoeken we die hier op; zo niet, dan blijft de Engelse
    zin staan. Kan de vertaling niet worden geladen — de cache is leeg, of een
    vertaling loopt uit de pas met de code — dan valt de zin terug op de
    Engelse sjabloon uit `strings.json`, en pas daarna op de rauwe tekst van de
    melding. Temperatuur-placeholders worden vóór het invullen omgerekend naar
    de eenheid van de gebruiker; zie `TEMPERATURE_PLACEHOLDERS`.

    De tweede terugval is lui: zolang de vertaling zelf al slaagt, wordt de
    Engelse cache niet eens geraadpleegd.

    The engine knows no Home Assistant and therefore writes English. If a
    complaint carries a code we look it up here; if not, the English sentence
    stays. When the translation cannot be loaded — the cache is empty, or a
    translation has drifted from the code — the sentence falls back to the
    English template from `strings.json`, and only then to the complaint's raw
    text. Temperature placeholders are converted to the user's unit before
    filling; see `TEMPERATURE_PLACEHOLDERS`.

    The second fallback is lazy: as long as the translation itself succeeds the
    English cache is not even consulted.
    """
    code = getattr(problem, "code", "")
    if not code:
        return str(problem)
    params = _converted_params(hass, problem)

    def _templates() -> Iterator[str | None]:
        yield texts.lookup(hass, code)
        yield _english_template(code)

    for template in _templates():
        if not template:
            continue
        try:
            return template.format(**params)
        except (KeyError, IndexError, ValueError):
            continue
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


#: De melding dat er niemand naar een geweigerd vooruit-verzoek luistert. Eén
#: melding voor de hele integratie, niet per installatie: de gebeurtenis is
#: domeinbreed, dus twee identieke meldingen zouden alleen maar herhalen.
#:
#: The notice that nobody is listening for a refused pre-conditioning request.
#: One notice for the whole integration rather than one per installation: the
#: event is domain-wide, so two identical notices would merely repeat.


from .repair_notices import (  # noqa: E402, I001
    BLUEPRINTS_URL as BLUEPRINTS_URL,
    UNWATCHED_ISSUE as UNWATCHED_ISSUE,
    _unreadable_issue_id as _unreadable_issue_id,
    async_report_unreadable as async_report_unreadable,
    async_clear_unreadable as async_clear_unreadable,
    _unsupported_modes_issue_id as _unsupported_modes_issue_id,
    async_report_unsupported_modes as async_report_unsupported_modes,
    async_clear_unsupported_modes as async_clear_unsupported_modes,
    _season_excludes_mode_issue_id as _season_excludes_mode_issue_id,
    async_report_season_override as async_report_season_override,
    async_clear_season_override as async_clear_season_override,
    _command_not_taking_issue_id as _command_not_taking_issue_id,
    async_report_command_not_taking as async_report_command_not_taking,
    async_clear_command_not_taking as async_clear_command_not_taking,
    _bypassed_opening_issue_id as _bypassed_opening_issue_id,
    async_report_bypassed_openings as async_report_bypassed_openings,
    async_clear_bypassed_openings as async_clear_bypassed_openings,
    _corrupt_storage_issue_id as _corrupt_storage_issue_id,
    async_report_corrupt_storage as async_report_corrupt_storage,
    async_clear_corrupt_storage as async_clear_corrupt_storage,
    async_check_watchers as async_check_watchers,
    async_clear_watchers as async_clear_watchers,
)
