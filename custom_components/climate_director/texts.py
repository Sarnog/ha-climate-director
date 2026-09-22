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
from homeassistant.helpers.entity_registry import DATA_REGISTRY

from .const import DOMAIN
from .engine import DirectorConfig, ModeFamily, Plan, UnitCommand, WorldState, ZoneDecision
from .engine.families import family_of
from .units import display_temperature, from_celsius, rounded_from_celsius

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

#: De Engelse redenzinnen, actiewoorden en berichtsjablonen, uit dezelfde
#: `strings.json`. Apart van `_ENGLISH_TEMPLATES` omdat de uitzonderingen en de
#: beslissingsteksten twee verschillende dingen zijn: een ontbrekende redenzin
#: mag nooit een identifier op het scherm zetten, en de terugval hier is de
#: Engelse zin.
#:
#: The English reason sentences, action words and message templates, from the
#: same `strings.json`. Separate from `_ENGLISH_TEMPLATES` because exceptions
#: and decision texts are two different things: a missing reason sentence must
#: never put an identifier on the screen, and the fallback here is the English
#: sentence.
_ENGLISH_READABLE: dict[str, str] | None = None


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


def english_readable() -> dict[str, str] | None:
    """Return the cached English reason sentences and message templates.

    Alleen-lezen, net als `english_templates()`: nooit zelf naar de schijf, want
    dan zou het opbouwen van een beslismelding kunnen blokkeren.

    Read-only, like `english_templates()`: never goes to disk itself, since
    otherwise building a decision message could block.
    """
    return _ENGLISH_READABLE


def _read_english_readable() -> dict[str, str]:
    """Read the English reason sentences, action words and message templates.

    Puur bestandswerk voor `async_add_executor_job`. De sleutels zijn `reason.*`,
    `action.*` en `message.*`, zodat één opzoeking volstaat. Een onleesbaar
    bestand levert een lege dict op, nooit een uitzondering.

    Pure file work for `async_add_executor_job`. The keys are `reason.*`,
    `action.*` and `message.*`, so one lookup suffices. An unreadable file
    yields an empty dict, never an exception.
    """
    found: dict[str, str] = {}
    try:
        data = json.loads(Path(__file__).with_name("strings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return found
    sensor = data.get("entity", {}).get("sensor", {}) if isinstance(data, dict) else {}
    if not isinstance(sensor, dict):
        return found
    for prefix, key in (
        ("reason", "zone_source"),
        ("action", "would_command"),
        ("message", "zone_source"),
    ):
        block = sensor.get(key)
        attributes = block.get("state_attributes") if isinstance(block, dict) else None
        states = attributes.get(prefix) if isinstance(attributes, dict) else None
        values = states.get("state") if isinstance(states, dict) else None
        if isinstance(values, dict):
            for code, sentence in values.items():
                if isinstance(sentence, str) and sentence:
                    found[f"{prefix}.{code}"] = sentence
    return found


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
    global _ENGLISH_TEMPLATES, _ENGLISH_READABLE
    if _ENGLISH_TEMPLATES is None:
        _ENGLISH_TEMPLATES = await hass.async_add_executor_job(_read_english_templates)
    if _ENGLISH_READABLE is None:
        _ENGLISH_READABLE = await hass.async_add_executor_job(_read_english_readable)


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


#: De puntpaden waaronder de beslissingsteksten in de zeven tekstbestanden
#: staan. Eén bron voor de opzoeking, zodat een test ze tegen de werkelijke
#: bestanden kan houden.
#:
#: The dotted paths under which the decision texts live in the seven text files.
#: One source for the lookup, so a test can hold them against the real files.
REASON_KEY = f"component.{DOMAIN}.entity.sensor.zone_source.state_attributes.reason.state."
ACTION_KEY = f"component.{DOMAIN}.entity.sensor.would_command.state_attributes.action.state."
MESSAGE_KEY = f"component.{DOMAIN}.entity.sensor.zone_source.state_attributes.message.state."


def _entity_cache(hass: HomeAssistant) -> dict[str, str]:
    """Return this integration's entity translations in the user's language.

    Alleen-lezen, net als `lookup`: `async_get_cached_translations` leest de
    cache die `async_prepare` gevuld heeft en raakt de schijf niet aan.

    Read-only, like `lookup`: `async_get_cached_translations` reads the cache
    `async_prepare` filled and never touches the disk.
    """
    return translation.async_get_cached_translations(hass, hass.config.language, "entity", DOMAIN)


def reason_sentence(hass: HomeAssistant, reason: str) -> str:
    """Return the reason of a decision as one ordinary sentence.

    De eigenschap is "wat de gebruiker leest is een zin in zijn taal, geen
    identifier". Twee terugvallen, net als `translated`: de vertaling kan
    ontbreken, en de Engelse zin uit `strings.json` is dan de tweede. `reason`
    zelf is de allerlaatste terugval en hoort nooit bereikt te worden - de
    bewaking eist dat alle negenentwintig redenen in alle zeven bestanden staan.

    The property is "what the user reads is a sentence in their language, not an
    identifier". Two fallbacks, like `translated`: the translation may be
    missing, and the English sentence from `strings.json` is then the second.
    `reason` itself is the very last fallback and should never be reached - the
    guard demands all twenty-nine reasons in all seven files.
    """
    english = english_readable() or {}
    translated_sentence = _entity_cache(hass).get(f"{REASON_KEY}{reason}")
    return translated_sentence or english.get(f"reason.{reason}") or reason


def action_sentence(hass: HomeAssistant, action: str) -> str:
    """Return what a decision does as a short phrase in the user's language.

    `action` is een sleutel als `heat`, `cool`, `off`, `left_alone` of
    `stays_off`; wat er terugkomt is "gaat verwarmen", "wordt met rust gelaten".

    `action` is a key such as `heat`, `cool`, `off`, `left_alone` or
    `stays_off`; what comes back is "is going to heat", "is left alone".
    """
    english = english_readable() or {}
    translated_phrase = _entity_cache(hass).get(f"{ACTION_KEY}{action}")
    return translated_phrase or english.get(f"action.{action}") or action


def decision_message(
    hass: HomeAssistant,
    *,
    zone: str,
    action: str,
    reason: str,
    source: str | None = None,
    target: str | None = None,
) -> str:
    """Return the ready-made sentence the blueprint shows by default.

    De vorm is `<kamer>: <actie> — <reden>`, met het apparaat en zijn setpoint
    ertussen alleen als er een commando is; een apparaat zonder naam levert dan
    nog steeds het setpoint op. De verbindingswoorden (`met`, `op`) komen uit
    het sjabloon van de taal, zodat de zin in elke taal klopt; de aanroeper
    geeft alleen de stukken.

    The shape is `<room>: <action> — <reason>`, with the appliance and its
    setpoint in between only when there is a command; an appliance without a
    name still yields the setpoint. The connecting words (`with`, `at`) come
    from the language's template, so the sentence is right in every language;
    the caller supplies only the pieces.
    """
    english = english_readable() or {}
    if source and target:
        shape = "appliance_target"
    elif source:
        shape = "appliance"
    elif target:
        shape = "target"
    else:
        shape = "plain"
    template = (
        _entity_cache(hass).get(f"{MESSAGE_KEY}{shape}")
        or english.get(f"message.{shape}")
        or "{zone}: {action} — {reason}"
    )
    return template.format(
        zone=zone, action=action, reason=reason, source=source or "", target=target or ""
    )


# -- de leesbare kant van één beslissing / the readable side of one decision ---


def _command_for(plan: Plan, decision: ZoneDecision) -> UnitCommand | None:
    """Return the command that decides this zone's outcome, if there is one.

    De zonebeslissing draagt de bron-id van de aangevraagde bron, en die is leeg
    zodra een poort de zone al tegenhield - een open raam, een leeg huis, een
    stiltevenster. Het plan stuurt dat apparaat dan nog steeds een stand, en
    juist die stand hoort de melding te noemen: "met rust gelaten" zeggen
    terwijl het apparaat wordt uitgezet is een leugen die de gebruiker ziet
    gebeuren. Daarom wordt er op de zone gezocht, met de aangevraagde bron als
    eerste keus en anders het commando dat de compressor opeist - dezelfde
    voorrang die het plan zelf aanhoudt ("vraag wint van stilte"). Krijgt een
    zone met twee apparaten er een warm en een uit, dan is het warme het
    antwoord.

    The zone decision carries the source id of the requested source, and that is
    empty as soon as a gate already held the zone back - an open window, an
    empty house, a quiet window. The plan still sends that appliance a mode, and
    that mode is exactly what the message should name: saying "left alone" while
    the appliance is being switched off is a lie the user watches happen. So the
    lookup goes by zone, with the requested source first and otherwise the
    command that claims the compressor - the same precedence the plan itself
    keeps ("demand beats silence"). When a zone with two appliances gets one
    heating and one off, the heating one is the answer.
    """
    commands = [item for item in plan.commands if item.zone_id == decision.zone_id]
    if not commands:
        return None
    chosen = next((item for item in commands if item.source_id == decision.source_id), None)
    if chosen is not None:
        return chosen
    return next(
        (item for item in commands if family_of(item.hvac_mode) is not ModeFamily.NEUTRAL),
        commands[0],
    )


def _source_display_name(
    hass: HomeAssistant, config: DirectorConfig, entity_id: str | None
) -> str | None:
    """Return the name a user knows an appliance by, never its id.

    Eerst het entiteitenregister: dat draagt de naam die de gebruiker zelf aan
    het apparaat gaf, en dat is precies wat hij op het scherm ziet. Staat er
    geen registerinvoer, dan de naam uit de configuratie, en anders de
    `friendly_name` van de toestand. Nooit de entiteit-id zelf: `AGENTS.md`
    verbiedt interne id's in teksten die een gebruiker leest.

    First the entity registry: it carries the name the user gave the appliance,
    which is exactly what they see on screen. Without a registry entry, the
    name from the configuration, and otherwise the state's `friendly_name`.
    Never the entity id itself: `AGENTS.md` forbids internal ids in text a user
    reads.
    """
    if not entity_id:
        return None
    registry = hass.data.get(DATA_REGISTRY)
    entry = registry.async_get(entity_id) if registry is not None else None
    if entry is not None:
        label = entry.name or entry.original_name
        if label:
            return label
    source = next((item for _zone, item in config.sources() if item.entity_id == entity_id), None)
    if source is not None and source.name:
        return source.name
    states = getattr(hass, "states", None)
    if states is not None:
        state = states.get(entity_id)
        if state is not None:
            friendly = state.attributes.get("friendly_name")
            if isinstance(friendly, str) and friendly:
                return friendly
    return None


def _was_running(world: WorldState | None, entity_id: str | None) -> bool:
    """Return whether an appliance was running when the plan was made.

    "Gaat uit" en "blijft uit" zijn niet hetzelfde voor een lezer: het eerste
    zegt dat er iets stopt, het tweede dat er niets verandert. De wereld waarin
    het plan gemaakt is beslist welke van de twee waar is - niet de toestand van
    dit moment, want de melding gaat uit ná het uitvoeren van het plan en dan
    staat een uitgezet apparaat allang uit. Zo kan een lezer nooit "blijft uit"
    lezen terwijl hij het apparaat ziet stoppen.

    De wereld gebruikt hier dezelfde maatstaf als de engine: een onbeschikbaar
    apparaat draait niets, en een stand die deze integratie niet kent telt als
    draaiend.

    "Goes off" and "stays off" are not the same to a reader: the first says
    something stops, the second says nothing changes. The world the plan was
    made in decides which of the two is true - not the state of this moment,
    since the notice goes out after the plan has been carried out and an
    appliance that was switched off is off by then. That way a reader can never
    read "stays off" while watching the appliance stop.

    The world uses the same yardstick as the engine here: an unavailable
    appliance runs nothing, and a mode this integration does not know counts as
    running.
    """
    if world is None or not entity_id:
        return False
    return world.climate(entity_id).running


def _action_key(
    world: WorldState | None, command: UnitCommand | None, untouched: bool, decision: ZoneDecision
) -> str:
    """Return which of the five action words fits this decision.

    De actie volgt het commando dat het plan dit apparaat geeft - hetzelfde
    commando dat de koppelingslaag uitvoert - en pas als er geen commando is wat
    de zone krijgt. Zo kan er nooit "gaat verwarmen" staan bij een apparaat dat
    uitgezet wordt. Een apparaat dat de director met rust laat levert "wordt met
    rust gelaten", of het nu om een overdracht, een onbereikbaar apparaat of een
    onleesbare temperatuur gaat. "Gaat uit" en "blijft uit" verschillen: de
    wereld waarin het plan gemaakt is beslist welke van de twee het is.

    The action follows the command the plan gives this appliance - the same
    command the binding layer carries out - and only falls back on what the zone
    receives when there is no command. That way "is going to heat" can never
    stand beside an appliance that is being switched off. An appliance the
    director leaves alone yields "is left alone", whether that is a handover, an
    unreachable appliance or an unreadable temperature. "Goes off" and "stays
    off" differ: the world the plan was made in decides which of the two it is.
    """
    if command is not None:
        family = family_of(command.hvac_mode)
        if family is ModeFamily.HEAT:
            return "heat"
        if family is ModeFamily.COOL:
            return "cool"
        return "off" if _was_running(world, command.entity_id) else "stays_off"
    if untouched:
        return "left_alone"
    if decision.granted is ModeFamily.HEAT:
        return "heat"
    if decision.granted is ModeFamily.COOL:
        return "cool"
    return "left_alone"


def decision_fields(
    hass: HomeAssistant,
    *,
    config: DirectorConfig,
    world: WorldState | None,
    plan: Plan,
    decision: ZoneDecision,
    unit: str,
) -> dict[str, Any]:
    """Return the readable half of one decision, identifiers left out.

    Vier velden, op één plek opgebouwd zodat het event en de blueprint het
    dezelfde zin zien: `reason_text` (de reden als gewone zin in de taal van de
    interface), `action_text` (wat er gebeurt), `source_name` (de weergavenaam
    van het apparaat, nooit zijn id) en `message` (de kant-en-klare zin die de
    blueprint standaard toont). Daarnaast de drie stukken die de koppelingslaag
    zelf al publiceert - het apparaat, zijn stand en zijn setpoint in de eenheid
    van de gebruiker - zodat de coordinator ze niet nog een keer hoeft uit te
    zoeken.

    `source_name` en het setpoint horen bij een apparaat dat de director
    werkelijk aanstuurt: bij "blijft uit" of "wordt met rust gelaten" noemt de
    zin geen apparaat, want daar valt niets aan te sturen. De identifiers blijven
    het contract; wat hier uit komt is presentatie.

    Four fields, built in one place so the event and the blueprint see the same
    sentence: `reason_text` (the reason as an ordinary sentence in the interface
    language), `action_text` (what happens), `source_name` (the display name of
    the appliance, never its id) and `message` (the ready-made sentence the
    blueprint shows by default). Beside them the three pieces the binding layer
    already publishes itself - the appliance, its mode and its setpoint in the
    user's unit - so the coordinator does not have to look them up a second
    time.

    `source_name` and the setpoint belong to an appliance the director really
    drives: with "stays off" or "is left alone" the sentence names no appliance,
    since there is nothing to drive there. The identifiers stay the contract;
    what comes out here is presentation.
    """
    command = _command_for(plan, decision)
    untouched = any(item.zone_id == decision.zone_id for item in plan.untouched)
    action = _action_key(world, command, untouched, decision)
    active = action in ("heat", "cool")
    entity_id = command.entity_id if command else None
    source_name = _source_display_name(hass, config, entity_id) if active and entity_id else None
    reason_text = reason_sentence(hass, decision.reason.value)
    action_text = action_sentence(hass, action)
    target = (
        display_temperature(from_celsius(command.temperature, unit), unit)
        if active and command is not None and command.temperature is not None
        else None
    )
    zone = config.zone(decision.zone_id)
    return {
        "entity_id": entity_id,
        "hvac_mode": command.hvac_mode if command else None,
        "temperature": rounded_from_celsius(command.temperature, unit) if command else None,
        "reason_text": reason_text,
        "action_text": action_text,
        "source_name": source_name,
        "message": decision_message(
            hass,
            zone=zone.name if zone else decision.zone_id,
            action=action_text,
            reason=reason_text,
            source=source_name,
            target=target,
        ),
    }
