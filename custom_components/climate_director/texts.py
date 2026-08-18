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

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import translation

from .const import DOMAIN


async def async_prepare(hass: HomeAssistant) -> None:
    """Load the texts before anyone asks for them.

    `async_get_cached_translations` leest een cache en niets meer: is de
    categorie nooit geladen, dan komt er een lege dict uit en valt elke zin
    stil terug op Engels. Laden is asynchroon en opzoeken niet, dus dit moet
    gebeuren op de plek die vroeg genoeg is - één keer, bij het opzetten.

    `async_get_cached_translations` reads a cache and no more: if the category
    was never loaded it returns an empty dictionary and every sentence quietly
    falls back to English. Loading is asynchronous and looking up is not, so
    this has to happen somewhere early enough - once, while setting up.
    """
    await translation.async_load_integrations(hass, {DOMAIN})


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


def number(value: float | None) -> str:
    """Return a temperature as it should read in a sentence, or a dash.

    `21.5` in plaats van `21.5000`, en `21` in plaats van `21.0`. Een streepje
    bij niets, want "Nu None graden" is geen zin.

    `21.5` rather than `21.5000`, and `21` rather than `21.0`. A dash for
    nothing, since "Now None degrees" is not a sentence.
    """
    return "-" if value is None else f"{value:g}"
