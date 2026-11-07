"""De leesbare beslissing.

The readable decision.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_registry import DATA_REGISTRY

from .engine import Plan, UnitCommand, WorldState, ZoneDecision
from .engine.families import ModeFamily, family_of
from .engine.models import DirectorConfig
from .texts import (
    ACTION_KEY,
    ATTRIBUTE_KEY,
    MESSAGE_KEY,
    REASON_KEY,
    english_readable,
    entity_cache,
)
from .units import display_temperature, from_celsius, rounded_from_celsius


def reason_sentence(hass: HomeAssistant, reason: str, duty: str | None = None) -> str:
    """Return the reason of a decision as one ordinary sentence.

    Met een taak (`heat` of `cool`) komt eerst de zin voor die taak, als de reden er
    een heeft: `outdoor_outside_window` is bij verwarmen "te warm om te verwarmen" en
    bij koelen "te koud om te koelen". Zonder taak, of zonder zin voor die taak, is
    het de algemene zin van de reden, met dezelfde terugvallen.

    With a duty (`heat` or `cool`) the sentence for that duty comes first, when the
    reason has one: `outdoor_outside_window` is "too warm to heat" for heating and
    "too cold to cool" for cooling. Without a duty, or without a sentence for that
    duty, it is the reason's general sentence, with the same fallbacks.

    De eigenschap is "wat de gebruiker leest is een zin in zijn taal, geen
    identifier". Twee terugvallen, net als `translated`: de vertaling kan
    ontbreken, en de Engelse zin uit `strings.json` is dan de tweede. `reason`
    zelf is de allerlaatste terugval en hoort nooit bereikt te worden - de
    bewaking eist dat alle dertig redenen in alle zeven bestanden staan.

    The property is "what the user reads is a sentence in their language, not an
    identifier". Two fallbacks, like `translated`: the translation may be
    missing, and the English sentence from `strings.json` is then the second.
    `reason` itself is the very last fallback and should never be reached - the
    guard demands all thirty reasons in all seven files.
    """
    english = english_readable() or {}
    cache = entity_cache(hass)
    if duty is not None:
        for_duty = cache.get(f"{ATTRIBUTE_KEY}{reason}.state.{duty}") or english.get(
            f"{reason}.{duty}"
        )
        if for_duty:
            return for_duty
    translated_sentence = cache.get(f"{REASON_KEY}{reason}")
    return translated_sentence or english.get(f"reason.{reason}") or reason


def action_sentence(hass: HomeAssistant, action: str) -> str:
    """Return what a decision does as a short phrase in the user's language.

    `action` is een sleutel als `heat`, `cool`, `off`, `left_alone` of
    `stays_off`; wat er terugkomt is "gaat verwarmen", "wordt met rust gelaten".

    `action` is a key such as `heat`, `cool`, `off`, `left_alone` or
    `stays_off`; what comes back is "is going to heat", "is left alone".
    """
    english = english_readable() or {}
    translated_phrase = entity_cache(hass).get(f"{ACTION_KEY}{action}")
    return translated_phrase or english.get(f"action.{action}") or action


def connector(hass: HomeAssistant, english: dict[str, str], which: str, fallback: str) -> str:
    """Return the little word that glues a piece onto the sentence.

    `met`/`op` (en `with`/`at`) staan als losse vertaalwaarden in de
    tekstbestanden, en `after_zone` is het scheidingsteken tussen de kamer en de
    actie - in het Frans met een spatie ervoor. Losse woorden en geen sjablonen,
    omdat hassfest geen plaatsaanduidingen in een vertaalwaarde accepteert - en de
    zin zelf is presentatie die de integratie opbouwt, geen tekst die een vertaler
    hoort over te typen.

    `met`/`op` (and `with`/`at`) stand as separate translation values in the text
    files, and `after_zone` is the separator between the room and the action - in
    French with a space before it. Separate words and not templates, because
    hassfest does not accept placeholders in a translation value - and the
    sentence itself is presentation the integration builds, not text a translator
    should retype.
    """
    return (
        entity_cache(hass).get(f"{MESSAGE_KEY}{which}")
        or english.get(f"message.{which}")
        or fallback
    )


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

    De vorm is `<kamer> <scheidingsteken> <actie> — <reden>`, met het apparaat en
    zijn setpoint ertussen alleen als er een commando is; een apparaat zonder naam
    levert dan nog steeds het setpoint op. De verbindingswoorden, het
    scheidingsteken tussen kamer en actie en de twee zinnen komen uit de taal van
    de interface. Het scheidingsteken is een eigen verbindingswoord omdat het
    Frans een spatie vóór de dubbele punt zet en het Nederlands niet; de rest is
    volgorde en het streepje, en die zijn in deze zeven talen dezelfde.

    The shape is `<room> <separator> <action> — <reason>`, with the appliance and
    its setpoint in between only when there is a command; an appliance without a
    name still yields the setpoint. The connecting words, the separator between
    room and action and the two sentences come from the interface's language. The
    separator is a connecting word of its own because French puts a space before
    the colon and Dutch does not; the rest is order and the dash, and those are
    the same in these seven languages.
    """
    english = english_readable() or {}
    parts = [f"{zone}{connector(hass, english, 'after_zone', ':')} {action}"]
    if source:
        parts.append(f"{connector(hass, english, 'before_appliance', 'with')} {source}")
    if target:
        parts.append(f"{connector(hass, english, 'before_target', 'at')} {target}")
    return f"{' '.join(parts)} — {reason}."


def command_for(plan: Plan, decision: ZoneDecision) -> UnitCommand | None:
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


def source_display_name(
    hass: HomeAssistant, config: DirectorConfig, entity_id: str | None
) -> str | None:
    """Return the name a user knows an appliance by, never its id.

    Eerst het entiteitenregister: dat draagt de naam die de gebruiker zelf aan
    het apparaat gaf, en dat is precies wat hij op het scherm ziet. Staat er
    geen registerinvoer, dan de naam uit de configuratie van die bron. Nooit de
    entiteit-id zelf: `AGENTS.md` verbiedt interne id's in teksten die een
    gebruiker leest.

    First the entity registry: it carries the name the user gave the appliance,
    which is exactly what they see on screen. Without a registry entry, the
    name from that source's configuration. Never the entity id itself:
    `AGENTS.md` forbids internal ids in text a user reads.
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
    return None


def was_running(world: WorldState | None, entity_id: str | None) -> bool:
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


def action_key(
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
        return "off" if was_running(world, command.entity_id) else "stays_off"
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
    zoeken. En `action`: de sleutel van de actie zelf (`heat`, `cool`, `off`,
    `stays_off`, `left_alone`), een vaste waarde om op te filteren naast `reason`,
    waar `action_text` de zin is.

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
    time. And `action`: the key of the action itself (`heat`, `cool`, `off`,
    `stays_off`, `left_alone`), a fixed value to filter on beside `reason`, where
    `action_text` is the sentence.

    `source_name` and the setpoint belong to an appliance the director really
    drives: with "stays off" or "is left alone" the sentence names no appliance,
    since there is nothing to drive there. The identifiers stay the contract;
    what comes out here is presentation.
    """
    command = command_for(plan, decision)
    untouched = any(item.zone_id == decision.zone_id for item in plan.untouched)
    action = action_key(world, command, untouched, decision)
    active = action in ("heat", "cool")
    entity_id = command.entity_id if command else None
    source_name = source_display_name(hass, config, entity_id) if active and entity_id else None
    duty = decision.duty.value if decision.duty is not ModeFamily.NEUTRAL else None
    reason_text = reason_sentence(hass, decision.reason.value, duty)
    action_text = action_sentence(hass, action)
    target = (
        display_temperature(from_celsius(command.temperature, unit), unit)
        if active and command is not None and command.temperature is not None
        else None
    )
    zone = config.zone(decision.zone_id)
    return {
        "action": action,
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
