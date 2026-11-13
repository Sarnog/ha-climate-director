"""Schermcontroles en formulieromzetting voor de configuratiestroom.

Screen checks and form conversion for the configuration flow.
"""

from __future__ import annotations

from typing import Any

from homeassistant.util import slugify

from .engine.energy import parse_cop_curve
from .engine.models import Season, SeasonSource, ZoneGate
from .form_common import CONF_NAME
from .units import delta_to_celsius, to_celsius


def missing(user_input: dict[str, Any], *fields: str) -> dict[str, str]:
    """Return an error per field the user left empty.

    Die velden staan in het schema als optioneel, zodat voluptuous een half
    ingevuld formulier niet weigert vóór wij het gezien hebben. Anders kun je
    niet meer terug zodra je ergens aan begonnen bent: je zit dan vast in een
    scherm dat je alleen kunt verlaten door het af te maken, en dat is geen
    keuze maar een val.

    The fields are optional in the schema so voluptuous does not refuse a
    half-filled form before we have seen it. Otherwise there is no way back once
    you have started: you are stuck in a screen you can leave only by finishing
    it, which is not a choice but a trap.
    """
    return {field: "required" for field in fields if not filled(user_input.get(field))}


def filled(value: Any) -> bool:
    """Return whether a value counts as filled in.

    Alleen spaties is niet ingevuld. `vol.Required` eist dat het veld er is,
    niet dat er iets in staat, dus zonder deze regel telt een handvol spaties
    als een naam.

    Spaces alone is not filled in. `vol.Required` demands the field is there,
    not that it holds anything, so without this rule a handful of spaces counts
    as a name.
    """
    if isinstance(value, str):
        return bool(value.strip())
    return bool(value)


def blank_to_none(value: Any) -> Any:
    """Return `None` for an empty form value, the value itself otherwise.

    De opslagkant mag nooit `""` in de configuratie schrijven voor een veld dat
    een getal of een entiteit hoort te zijn. Alleen `None` en `""` tellen als
    leeg; `0` en een lege lijst zijn echte waarden en blijven staan. De
    `""`-tak is vandaag op elk bereikbaar pad onbereikbaar — de selectors
    ervóór weigeren een lege string al — maar blijft staan als vangnet voor een
    route die de interface nog niet neemt.

    The storage side must never write `""` into the configuration for a field
    that is supposed to hold a number or an entity. Only `None` and `""` count
    as empty; `0` and an empty list are real values and stay. The `""` branch
    is unreachable on every reachable path today — the selectors in front of it
    already refuse an empty string — but stays as a safety net for a route the
    frontend does not take yet.
    """
    return None if value is None or value == "" else value


def settings_errors(user_input: dict[str, Any]) -> dict[str, str]:
    """Return what the settings screen refuses to store.

    Staat de herkomst van het seizoen op *entiteit* zonder dat er een gekozen is,
    dan blijft het seizoen onbekend en doet elke taak met een seizoensbeperking
    niets. Dat is het stille niets waarvoor `unreadable_entities` bestaat, maar
    dan zonder dat er iets te herlezen valt - en dit scherm is de enige plek waar
    de gebruiker het recht kan zetten.

    With the season source on *entity* and none chosen, the season stays unknown
    and every duty with a season restriction does nothing. That is the silent
    nothing `unreadable_entities` exists for, but with nothing to re-read - and
    this screen is the only place the user can put it right.
    """
    source = str(user_input.get("season_source") or "")
    entity = str(user_input.get("season_entity") or "")
    if source == SeasonSource.ENTITY.value and not entity.strip():
        return {"season_entity": "season_entity_missing"}
    return {}


def energy_errors(user_input: dict[str, Any]) -> dict[str, str]:
    """Return what the energy screen refuses to store.

    Een ingevulde COP-curve die niet te lezen is, zou later stil geen kosten
    geven. Leeg mag: dan is er gewoon geen vergelijking.

    A filled-in COP curve that does not read would later quietly give no cost.
    Empty is fine: there is then simply no comparison.
    """
    curve = str(user_input.get("cop_curve") or "").strip()
    if curve and parse_cop_curve(curve) is None:
        return {"cop_curve": "cop_curve_invalid"}
    return {}


def zone_errors(zone: dict[str, Any]) -> dict[str, str]:
    """Return every complaint this screen can make about one zone.

    De verzamelplek, zodat de vlucht er maar op één ding hoeft te leunen en er
    geen controle vergeten kan worden. Wat hier doorheen komt, hoort door
    `validate()` heen te komen - `test_random_installations.py` legt precies dat
    vast, in beide richtingen.

    The gathering point, so the flow leans on one thing only and no check can
    be forgotten. What passes here should pass `validate()` -
    `test_random_installations.py` pins down exactly that, in both directions.
    """
    return name_errors(zone) | band_errors(zone) | gate_errors(zone) | mode_errors(zone)


def name_errors(zone: dict[str, Any]) -> dict[str, str]:
    """Return an error when the name cannot carry a zone id.

    De naam bepaalt het id van een nieuwe zone, dus hij moet iets opleveren om
    te sluggen. Een lege naam valt terug op `zone`, en twee van zulke zones
    botsen alsnog op hetzelfde id - precies wat de unieke-id-stap hierboven
    hoort te voorkomen.

    The name decides a new zone's id, so it must yield something to slug. An
    empty name falls back to `zone`, and two such zones still collide on the
    same id - exactly what the unique-id step above is there to prevent.
    """
    if slugify(zone.get("name") or ""):
        return {}
    return {"name": "required"}


def mode_errors(zone: dict[str, Any]) -> dict[str, str]:
    """Return an error when a zone may neither heat nor cool.

    Zo'n zone kan per definitie nooit iets doen. Hij verschijnt wel met al zijn
    entiteiten, en dan zoek je later waarom er niets gebeurt in een kamer die
    het nooit had mogen proberen.

    Such a zone can never do anything by definition. It still appears with all
    its entities, and then you go looking later for why nothing happens in a
    room that was never allowed to try.
    """
    if zone.get("heat") or zone.get("cool"):
        return {}
    return {"enable_heat": "zone_without_modes"}


def gate_errors(zone: dict[str, Any]) -> dict[str, str]:
    """Return an error when the room gate has no room sensor to lean on.

    Een zone op *Ruimte* kijkt naar de aanwezigheidssensor en naar niets
    anders. Is die er niet, dan is de kamer per definitie leeg en doet de zone
    nooit meer iets - stil, want een zone die niets doet ziet er precies zo uit
    als een zone die niets hoeft te doen.

    `validate()` klaagt hier terecht over, maar pas achteraf. Het scherm waarop
    je de poort kiest weet het meteen.

    A zone on *Room* looks at the presence sensor and at nothing else. Without
    one the room is empty by definition and the zone never does anything again
    - quietly, since a zone doing nothing looks exactly like a zone with
    nothing to do.

    `validate()` rightly complains about this, but only afterwards. The screen
    where you pick the gate knows at once.
    """
    if zone.get("gate") != ZoneGate.PRESENCE.value:
        return {}
    if zone.get("presence_entity"):
        return {}
    return {"presence_entity": "presence_gate_without_sensor"}


def band_errors(zone: dict[str, Any]) -> dict[str, str]:
    """Return an error per mode whose target sits on the wrong side of its switch-on point.

    Het aanpunt is waar de zone besluit te beginnen, de streeftemperatuur is wat
    het apparaat te horen krijgt. Ligt het streven aan de verkeerde kant, dan
    start de zone keurig en zet hij het apparaat vervolgens op een temperatuur
    waar het niets voor hoeft te doen. Van buiten lijkt dat op een apparaat dat
    weigert, en daar ga je een dag mee zoeken.

    `validate()` waarschuwt hier ook over, maar pas achteraf, in een
    reparatiemelding. Achteraf is te laat als het scherm waarop je het intikte
    het meteen had kunnen zeggen.

    The switch-on point is where the zone decides to begin, the target is what
    the appliance is told. If the target sits on the wrong side, the zone starts
    dutifully and then sets the appliance to a temperature it need do nothing
    for. From the outside that looks like an appliance refusing, and you can
    spend a day chasing it.

    `validate()` warns about this too, but only afterwards, in a repair notice.
    Afterwards is too late when the screen you typed it on could have said so at
    once.
    """
    errors: dict[str, str] = {}

    heat = zone.get("heat") or {}
    if heat and heat["target"] < heat["start_at"]:
        errors["heat_target"] = "target_outside_band"

    cool = zone.get("cool") or {}
    if cool and cool["target"] > cool["start_at"]:
        errors["cool_target"] = "target_outside_band"

    # Raken of overlappen de twee banden elkaar, dan vragen verwarmen en koelen
    # om de beurt dezelfde kamer: de kamer zou verwarmen tot het uitschakelpunt
    # en meteen daarna gaan koelen. Dat mag dit scherm zeggen en niet pas een
    # melding achteraf.
    #
    # If the two bands touch or overlap, heating and cooling ask for the same room
    # by turns: the room would heat up to the switch-off point and start cooling
    # right after. This screen is the place to say so, not a notice afterwards.
    if (
        heat
        and cool
        and (
            cool["start_at"] <= heat["start_at"]
            or heat["start_at"] + heat.get("hysteresis", 0.0) >= cool["start_at"]
            or cool["start_at"] - cool.get("hysteresis", 0.0) <= heat["start_at"]
        )
    ):
        errors["cool_start_at"] = "bands_overlap"

    return errors


def heat_cool_from_form(
    user_input: dict[str, Any], current: dict[str, Any], *, unit: str | None = None
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return the stored heat and cool blocks described by a submitted zone form.

    Het formulier toont maar één kant van elke buitengrens en geen
    verwarmingsseizoenen. Wie die waarden eerder instelde - via een oudere
    versie of een met de hand bewerkte configuratie - mag ze bij een gewone
    formulierbewerking niet kwijtraken: wat het formulier niet toont, blijft
    staan.

    `unit` is de eenheid waarin het formulier de temperaturen aanleverde; de
    engine bewaart alles in graden Celsius.

    The form shows only one side of each outdoor bound and no heating seasons.
    Whoever set those values earlier - through an older version or a hand-edited
    configuration - should not lose them on an ordinary form edit: what the form
    does not show stays.

    `unit` is the unit the form supplied the temperatures in; the engine stores
    everything in degrees Celsius.
    """
    stored_heat = current.get("heat") or {}
    stored_cool = current.get("cool") or {}
    stored_heat_outdoor = stored_heat.get("outdoor") or {}
    stored_cool_outdoor = stored_cool.get("outdoor") or {}
    heat = (
        {
            "target": to_celsius(user_input["heat_target"], unit or ""),
            "start_at": to_celsius(user_input["heat_start_at"], unit or ""),
            "hysteresis": delta_to_celsius(user_input["heat_hysteresis"], unit or ""),
            "outdoor": {
                "minimum": stored_heat_outdoor.get("minimum"),
                "maximum": to_celsius(
                    blank_to_none(user_input.get("heat_outdoor_max")), unit or ""
                ),
            },
            "seasons": stored_heat.get("seasons"),
        }
        if user_input["enable_heat"]
        else None
    )
    cool = (
        {
            "target": to_celsius(user_input["cool_target"], unit or ""),
            "start_at": to_celsius(user_input["cool_start_at"], unit or ""),
            "hysteresis": delta_to_celsius(user_input["cool_hysteresis"], unit or ""),
            "outdoor": {
                "minimum": to_celsius(
                    blank_to_none(user_input.get("cool_outdoor_min")), unit or ""
                ),
                "maximum": stored_cool_outdoor.get("maximum"),
            },
            "seasons": [Season.SUMMER.value] if user_input["cool_summer_only"] else None,
        }
        if user_input["enable_cool"]
        else None
    )
    return heat, cool


def zone_from_form(
    user_input: dict[str, Any],
    current: dict[str, Any],
    taken: list[str] | None = None,
    *,
    stored_id: str | None = None,
    unit: str | None = None,
) -> dict[str, Any]:
    """Return the stored zone described by a submitted zone form.

    Het formulier toont maar één kant van elke buitengrens en geen
    verwarmingsseizoenen. Wie die waarden eerder instelde - via een oudere
    versie of een met de hand bewerkte configuratie - mag ze bij een gewone
    formulierbewerking niet kwijtraken: wat het formulier niet toont, blijft
    staan.

    The form shows only one side of each outdoor bound and no heating seasons.
    Whoever set those values earlier - through an older version or a hand-edited
    configuration - should not lose them on an ordinary form edit: what the form
    does not show stays.
    """
    heat, cool = heat_cool_from_form(user_input, current, unit=unit)
    return {
        # Een bestaande zone houdt zijn id: achteraf hernoemen kost de
        # entiteitsgeschiedenis van die zone. Een nieuwe zone krijgt een id uit
        # zijn naam, en bij een al bestaande id een oplopend achtervoegsel -
        # precies zoals bronnen, circuits, generatoren en bewoners dat doen.
        #
        # An existing zone keeps its id: renaming one afterwards costs that
        # zone's entity history. A new zone gets an id from its name, and when
        # that id already exists a counting suffix - exactly as sources,
        # circuits, generators and residents do.
        "zone_id": (
            stored_id if stored_id is not None else unique_id(user_input[CONF_NAME], taken or [])
        ),
        "name": user_input[CONF_NAME],
        "indoor_sensor": user_input["indoor_sensor"],
        "priority": int(user_input["priority"]),
        "sources": current.get("sources") or [],
        "heat": heat,
        "cool": cool,
        "gate": user_input.get("gate") or ZoneGate.HOUSEHOLD.value,
        "presence_entity": user_input.get("presence_entity") or "",
        "presence_state": user_input.get("presence_state") or "on",
        "presence_timeout": user_input.get("presence_timeout") or 0,
        "ignore_precipitation": bool(user_input.get("ignore_precipitation", False)),
    }


def next_priority(zones: list[dict[str, Any]]) -> int:
    """Return the priority a newly added zone should start on.

    Every zone defaulting to zero would leave them all tied, and a tie falls
    back on the zone id - so the room that happens to come first alphabetically
    would quietly win every circuit. Counting up instead means the order rooms
    are added in is the order they win in, which is both predictable and easy
    to correct.
    """
    used = [
        zone["priority"]
        for zone in zones
        if isinstance(zone.get("priority"), int) and not isinstance(zone.get("priority"), bool)
    ]
    return max(used) + 1 if used else 0


def all_source_ids(installation: dict[str, Any]) -> list[str]:
    """Return every source id in use, so a new one can avoid them."""
    return [
        source["source_id"]
        for zone in installation.get("zones") or []
        for source in zone.get("sources") or []
        if "source_id" in source
    ]


def unique_id(name: str, taken: list[str]) -> str:
    """Return a slug of `name` that is not in `taken`."""
    base = slugify(name) or "item"
    if base not in taken:
        return base
    index = 2
    while f"{base}_{index}" in taken:
        index += 1
    return f"{base}_{index}"


def deep_copy(value: Any) -> Any:
    """Return a mutable deep copy of stored options.

    Config entry options are shared, immutable-by-convention structures; editing
    them in place would change the running configuration before the user has
    pressed save, and would leave a half-edited installation behind if they
    abandoned the flow.
    """
    if isinstance(value, dict):
        return {key: deep_copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [deep_copy(item) for item in value]
    return value
