"""Vertaalde teksten voor wat de integratie naar buiten meegeeft.

Translated texts for what the integration hands outward.

De integratie stuurt zelf geen berichten - waar een melding heen gaat is niets
waar een klimaatregelaar over hoort te beslissen. Maar de tékst hoort hier wel
vandaan te komen: een blueprint kan niet vertalen, en een gebruiker die zijn
huis in het Nederlands bedient wil geen Engelse melding op zijn telefoon.

Dus: de gebeurtenis draagt de zin al kant-en-klaar mee, in de taal van de
interface, met Engels als terugval. De automatisering hoeft hem alleen nog door
te geven aan wat dan ook.

The integration sends no messages of its own - where a notification goes is
nothing a climate controller should decide. But the *text* does belong here: a
blueprint cannot translate, and somebody running their house in Dutch does not
want an English notice on their phone.

So: the event carries the sentence ready-made, in the language of the
interface, with English as the fallback. The automation only has to hand it on
to whatever it likes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import translation

from .const import DOMAIN

#: De Engelse uitzonderingszinnen, één keer uit `strings.json` gelezen. De
#: bestandslezing zelf gebeurt in `async_prepare`, nooit in `lookup`/`readable`:
#: een synchrone `read_text` in de event loop is een blokkerende aanroep die
#: Home Assistant met naam en toenaam in het logboek meldt.
#:
#: The English exception sentences, read once from `strings.json`. The file read
#: itself happens in `async_prepare`, never in `lookup`/`readable`: a synchronous
#: `read_text` in the event loop is a blocking call Home Assistant reports in the
#: log by name.
_ENGLISH_TEMPLATES: dict[str, str] | None = None


def english_templates() -> dict[str, str] | None:
    """Return the cached English exception templates, or `None` before loading.

    De lezer is bewust alleen-lezen: hij mag nooit zelf naar de schijf gaan,
    anders is `readable()` weer blokkerend zodra iemand hem op een pad aanroept
    waarop de cache nog leeg is. `None` betekent simpelweg "geen tweede
    terugval", en `readable()` valt dan door naar de rauwe engine-tekst.

    The reader is deliberately read-only: it must never go to disk itself,
    otherwise `readable()` becomes blocking again the moment somebody calls it on
    a path where the cache is still empty. `None` simply means "no second
    fallback", and `readable()` then falls through to the raw engine text.
    """
    return _ENGLISH_TEMPLATES


def _read_english_templates() -> dict[str, str]:
    """Read every English exception template out of `strings.json`.

    Puur bestandswerk, bedoeld om via `async_add_executor_job` buiten de event
    loop te draaien. Een onleesbaar of onverwacht gevormd bestand levert een lege
    dict op, nooit een uitzondering: de tweede terugval mag het scherm niet
    laten omvallen, hij is er juist voor het geval de vertaling ontbreekt.

    Pure file work, meant to run through `async_add_executor_job` off the event
    loop. An unreadable or unexpectedly shaped file yields an empty dict, never
    an exception: the second fallback must not bring the screen down, it exists
    precisely for the case the translation is missing.
    """
    templates: dict[str, str] = {}
    try:
        data = json.loads(Path(__file__).with_name("strings.json").read_text(encoding="utf-8"))
        exceptions = data.get("exceptions") if isinstance(data, dict) else None
        if isinstance(exceptions, dict):
            for key, value in exceptions.items():
                message = value.get("message") if isinstance(value, dict) else None
                if message:
                    templates[key] = message
    except (OSError, ValueError):
        pass
    return templates


async def async_prepare(hass: HomeAssistant) -> None:
    """Load the texts before anyone asks for them.

    `async_get_cached_translations` leest een cache en niets meer: is de
    categorie nooit geladen, dan komt er een lege dict uit en valt elke zin
    stil terug op Engels. Laden is asynchroon en opzoeken niet, dus dit moet
    gebeuren op de plek die vroeg genoeg is - één keer, bij het opzetten.

    Daarnaast worden de Engelse sjablonen hier uit `strings.json` gelezen, via
    `async_add_executor_job` zodat de bestandslezing niet in de event loop
    gebeurt. `problems._english_template` leest daarna alleen nog deze cache en
    kan nooit meer blokkeren.

    `async_get_cached_translations` reads a cache and no more: if the category
    was never loaded it returns an empty dictionary and every sentence quietly
    falls back to English. Loading is asynchronous and looking up is not, so
    this has to happen somewhere early enough - once, while setting up.

    On top of that the English templates are read here from `strings.json`,
    through `async_add_executor_job` so the file read does not happen on the
    event loop. `problems._english_template` then only reads this cache and can
    never block again.
    """
    await translation.async_load_integrations(hass, {DOMAIN})
    global _ENGLISH_TEMPLATES
    if _ENGLISH_TEMPLATES is None:
        _ENGLISH_TEMPLATES = await hass.async_add_executor_job(_read_english_templates)


#: De Engelse dagnamen, in de volgorde van `datetime.weekday()` (maandag is 0).
#: Ze zijn de terugval wanneer een taal geen vertaling heeft; de vertalingen
#: zelf wonen onder `selector`, waar de keuzevelden ze ook vandaan halen.
#:
#: The English day names, in `datetime.weekday()` order (Monday is 0). They are
#: the fallback for a language without a translation; the translations
#: themselves live under `selector`, where the pickers read them too.
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


async def async_selector_texts(hass: HomeAssistant) -> dict[str, str]:
    """Return this integration's selector translations in the user's language.

    De keuzevelden zelf vertaalt Home Assistant: die dragen een
    `translation_key` en de interface zoekt de tekst er zelf bij. Maar een
    lijstregel als "08:00 - 15:00, za, zo" wordt hier in Python opgebouwd, en
    daar komt geen interface aan te pas. Dus halen we dezelfde teksten op waar
    het keuzeveld ze ook vandaan haalt - één bron, geen tweede lijst die uit de
    pas kan lopen.

    Home Assistant translates the pickers themselves: those carry a
    `translation_key` and the interface looks the text up. But a list line like
    "08:00 - 15:00, Sat, Sun" is built here in Python, where no interface is
    involved. So we fetch the same texts the picker reads - one source, no
    second list to drift apart.
    """
    return await translation.async_get_translations(
        hass, hass.config.language, "selector", {DOMAIN}
    )


def weekday_names(texts: dict[str, str], *, short: bool = False) -> tuple[str, ...]:
    """Return the seven day names, abbreviated on request."""
    key = "weekday_short" if short else "weekday"
    prefix = f"component.{DOMAIN}.selector.{key}.options."
    names = []
    for day in range(7):
        fallback = WEEKDAYS[day][:3] if short else WEEKDAYS[day]
        names.append(texts.get(f"{prefix}{day}") or fallback)
    return tuple(names)


def every_day(texts: dict[str, str]) -> str:
    """Return the words that stand for a window without days."""
    key = f"component.{DOMAIN}.selector.weekday_summary.options.every_day"
    return texts.get(key) or "every day"


def lookup(hass: HomeAssistant, code: str) -> str | None:
    """Return the translated template for one code, if there is one.

    De teksten wonen onder `exceptions`. Dat is geen willekeurige keuze: Home
    Assistant valideert `strings.json` tegen een vast schema, en een zelf
    verzonnen blok op het hoogste niveau wordt afgewezen - voor elke taal
    tegelijk.

    The texts live under `exceptions`. That is not an arbitrary choice: Home
    Assistant validates `strings.json` against a fixed schema, and a
    self-invented top-level block is rejected - for every language at once.
    """
    key = f"component.{DOMAIN}.exceptions.{code}.message"
    cached = translation.async_get_cached_translations(hass, hass.config.language, "exceptions")
    return cached.get(key)


def translated(hass: HomeAssistant, code: str, fallback: str, **params: Any) -> str:
    """Return one sentence in the user's language, filled in.

    Twee keer terugvallen, want beide kunnen misgaan: de vertaling kan
    ontbreken, en een vertaling die uit de pas loopt met de code kan een
    plaatshouder missen die wij invullen. In beide gevallen is een Engelse zin
    die klopt beter dan een lege plek of een uitzondering.

    Two fallbacks, since both can go wrong: the translation may be missing, and
    a translation that has drifted from the code may lack a placeholder we fill
    in. In both cases an English sentence that is right beats a hole or an
    exception.
    """
    for template in (lookup(hass, code), fallback):
        if not template:
            continue
        try:
            return template.format(**params)
        except (KeyError, IndexError, ValueError):
            continue
    return fallback
