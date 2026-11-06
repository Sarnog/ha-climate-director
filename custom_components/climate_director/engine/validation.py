"""Alle configuratiecontroles van de installatie op één plek.

Every configuration check of the installation in one place.

`Problem` draagt de code en de plaatshouders, `validate()` loopt de regels in
vaste volgorde af en `RULES` is die volgorde. De controles wonen hier en niet in
`models.py`: het model beschrijft de installatie, deze module zegt wat eraan
mankeert. Een nieuwe controle hoort in `RULES`, niet in een tweede lijst.

`Problem` carries the code and the placeholders, `validate()` walks the rules in
a fixed order and `RULES` is that order. The checks live here, not in
`models.py`: the model describes the installation, this module says what is
wrong with it. A new check belongs in `RULES`, not in a second list.
"""

from __future__ import annotations

import math
from collections.abc import Iterator

from .families import ModeFamily
from .models import (
    QUIET_ROOM_MINUTES,
    DirectorConfig,
    HeatingLayout,
    ModeSettings,
    Season,
    SeasonSettings,
    SeasonSource,
    Source,
    TimeWindow,
    Zone,
    ZoneGate,
)
from .plan import OPENING_MIN_REST


class Problem(str):
    """One configuration complaint, readable as text and identifiable by code.

    Een `str`-subklasse met opzet: alles wat er al mee werkte - de diagnose, het
    logboek, de tests - blijft werken alsof er niets veranderd is. De code komt
    er alleen bij, zodat de Home Assistant-laag er een vertaling bij kan zoeken.
    De Engelse tekst blijft de terugval, dus een melding zonder vertaling is
    nooit erger dan hij was.

    A `str` subclass on purpose: everything already working with these - the
    diagnostics, the log, the tests - keeps working as though nothing changed.
    The code is merely added, so the Home Assistant layer can look up a
    translation for it. The English text stays the fallback, so a complaint
    without a translation is never worse off than it was.
    """

    code: str
    params: dict[str, str]

    def __new__(cls, code: str, text: str, **params: object) -> Problem:
        """Return the complaint, carrying its code and placeholders."""
        item = super().__new__(cls, text)
        item.code = code
        item.params = {key: str(value) for key, value in params.items()}
        return item


def _pinned_season(seasons: SeasonSettings) -> Season | None:
    """Return the season `seasons` pins the installation to, if any."""
    if seasons.source is SeasonSource.SUMMER:
        return Season.SUMMER
    if seasons.source is SeasonSource.WINTER:
        return Season.WINTER
    return None


def _season_names(seasons: frozenset[Season] | None) -> str:
    """Return the human-readable names of the seasons a duty is allowed in."""
    return ", ".join(sorted(season.value for season in seasons or ()))


def validate(config: DirectorConfig) -> tuple[str, ...]:
    """Return every structural problem found in `config`, newest checks last.

    Returns an empty tuple for a sound configuration. Meant for the config flow
    and for tests; `decide()` itself never raises on a flawed configuration,
    since refusing to regulate a whole house over one bad zone is worse than
    regulating the sound zones and reporting the rest.

    De controles staan als losse regelfuncties in `_RULES`, op volgorde; deze
    functie is alleen nog de lus erover. Die volgorde is zichtbaar op het
    bewaarscherm en in de reparatiemelding `invalid_config`, en wordt door
    `tests/test_validation.py` tegen letterlijke lijsten gehouden.

    The checks live as separate rule functions in `_RULES`, in order; this
    function is only the loop over them. That order is visible on the save
    screen and in the `invalid_config` repair notice, and is held by
    `tests/test_validation.py` against literal lists.
    """
    problems: list[str] = []
    for rule in RULES:
        problems.extend(rule(config))
    return tuple(problems)


def _rule_duplicate_zone_ids(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for every zone id that occurs more than once.

    Een zone-id is de sleutel van alle per-zone-toestand in de engine; twee
    zones met dezelfde id delen die sleutel en zijn van buiten niet meer uit
    elkaar te houden.

    A zone id is the key of all per-zone state in the engine; two zones sharing
    one share that key and can no longer be told apart from the outside.
    """
    for zone_id in _duplicates([zone.zone_id for zone in config.zones]):
        yield Problem("duplicate_zone_id", f"duplicate zone id: {zone_id}", zone=zone_id)


def _rule_duplicate_circuit_ids(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for every circuit id that occurs more than once.

    Een circuit-id is de sleutel van de circuittoestand; twee circuits met
    dezelfde id zijn van buiten niet meer uit elkaar te houden.

    A circuit id is the key of circuit state; two circuits sharing one can no
    longer be told apart from the outside.
    """
    for circuit_id in _duplicates([circuit.circuit_id for circuit in config.circuits]):
        yield Problem(
            "duplicate_circuit_id", f"duplicate circuit id: {circuit_id}", circuit=circuit_id
        )


def _rule_duplicate_source_ids(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for every source id that occurs more than once.

    Een bron-id is de sleutel waarmee uitsluitende groepen naar bronnen
    verwijzen; een dubbel id maakt die verwijzing dubbelzinnig.

    A source id is the key exclusive groups use to point at sources; a doubled
    id makes that reference ambiguous.
    """
    for source_id in _duplicates([source.source_id for _, source in config.sources()]):
        yield Problem("duplicate_source_id", f"duplicate source id: {source_id}", source=source_id)


def _rule_duplicate_opening_ids(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for every opening id that occurs more than once.

    Anker 8: een opening draagt een eigen `opening_id`; twee openingen met
    dezelfde id delen de overbruggingsschakelaar, en dan verdwijnt er één stil
    uit het entiteitenregister. Oudere opslag kent die ids niet; ze
    worden bij het lezen afgeleid (`serialise.opening_ids`); een opgeslagen
    dubbel id laat die lezer staan, dus deze controle ziet hem.

    Anchor 8: an opening carries its own `opening_id`; two openings sharing one
    share the bypass switch, and then one disappears quietly from the entity
    registry. Older storage has no such ids; they are
    derived on read (`serialise.opening_ids`); a stored duplicate is left
    alone by that reader, so this check sees it.
    """
    ids = [opening.opening_id for opening in config.openings if opening.opening_id]
    for opening_id in _duplicates(ids):
        yield Problem(
            "duplicate_opening_id", f"duplicate opening id: {opening_id}", opening=opening_id
        )


def _rule_entity_twice_in_one_zone(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint when one room uses the same appliance twice.

    Hetzelfde apparaat twee keer in EEN kamer is onzin: welke van de twee
    bronnen wint, is dan willekeurig, en er valt niets te kiezen. Over
    meerdere kamers heen is het juist normaal - dat is precies hoe een
    centrale verwarming eruitziet, en hoe een gedeelde ketel als reserve
    onder elke zone komt te staan. Dat mocht hier ooit niet, omdat zo'n
    apparaat dan twee tegengestelde opdrachten kon krijgen; sinds die
    opdrachten samenvallen tot een per apparaat is dat bezwaar weg.

    The same appliance twice in ONE room is nonsense: which of the two
    sources wins is then arbitrary, and there is nothing to choose between.
    Across rooms it is ordinary - that is exactly what central heating looks
    like, and how a shared boiler ends up under every zone as a stand-in.
    This used to be forbidden here because such an appliance could then get
    two opposing commands; since those collapse into one per appliance, that
    objection is gone.
    """
    for zone in config.zones:
        for entity_id in _duplicates([source.entity_id for source in zone.sources]):
            yield Problem(
                "entity_twice_in_one_zone",
                f"zone {zone.zone_id} uses {entity_id} for more than one source",
                zone=zone.name or zone.zone_id,
                entity=entity_id,
            )


def _rule_unit_in_no_zone(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for every circuit unit that no zone steers.

    Een unit die wel aan een buitenunit hangt maar in geen enkele zone staat,
    is voor de director onbeheerd. Draait hij, dan zet hij het hele circuit op
    zijn taak en kan geen kamer er meer iets anders vragen - en omdat hij van
    niemand is, zet de director hem ook nooit uit. Van buiten is dat niet te
    onderscheiden van "de director doet niets", dus het hoort gemeld te worden
    vóór iemand zich erop verkijkt.

    A unit that hangs on an outdoor unit but appears in no zone is unmanaged
    as far as the director is concerned. If it runs it holds the whole circuit
    to its duty and no room can ask for anything else - and since it belongs
    to nobody, the director never switches it off either. From the outside
    that is indistinguishable from "the director does nothing", so it should
    be reported before somebody is caught out by it.
    """
    in_a_zone = {source.entity_id for _zone, source in config.sources()}
    for circuit in config.circuits:
        for unit in circuit.units:
            if unit not in in_a_zone:
                yield Problem(
                    "unit_in_no_zone",
                    f"unit {unit} is on circuit {circuit.circuit_id} but in no zone, so it can "
                    f"lock that circuit without the director being able to stand it down",
                    unit=unit,
                    circuit=circuit.circuit_id,
                )


def _rule_unit_on_two_circuits(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for every unit sitting on more than one circuit.

    Een unit kan maar op één buitenunit hangen; staat hij op twee circuits,
    dan is de configuratie met de hand bewerkt of verkeerd overgenomen en
    weet de engine niet welk circuit hij moet geloven.

    A unit can hang on only one outdoor unit; sitting on two circuits means
    the configuration was hand-edited or copied wrongly, and the engine does
    not know which circuit to believe.
    """
    seen_units: dict[str, str] = {}
    for circuit in config.circuits:
        for unit in circuit.units:
            if unit in seen_units:
                yield Problem(
                    "unit_on_two_circuits",
                    f"unit {unit} sits on both circuit {seen_units[unit]} "
                    f"and circuit {circuit.circuit_id}",
                    unit=unit,
                    first=seen_units[unit],
                    second=circuit.circuit_id,
                )
            else:
                seen_units[unit] = circuit.circuit_id


def _outdoor_known(config: DirectorConfig) -> bool:
    """Return whether the installation has an outdoor temperature to read.

    Gedeeld door de bron- en taakvenstercontrole in `_rule_zones`: één
    definitie, één berekening per `validate()`-aanroep.

    Shared by the source- and duty-window checks in `_rule_zones`: one
    definition, one computation per `validate()` call.
    """
    return bool(config.outdoor_sensor)


def _rule_source_outdoor_window(source: Source, outdoor_known: bool) -> Iterator[Problem]:
    """Yield a complaint when a source's outdoor window can never be met.

    Een leeg venster laat de bron nooit draaien; een begrensd venster zonder
    buitensensor kan nooit voldaan worden. Beide zijn van buiten niet te
    onderscheiden van "de director doet niets".

    An empty window never lets the source run; a bounded window without an
    outdoor sensor can never be satisfied. Both look like "the director does
    nothing" from the outside.
    """
    if source.outdoor.empty:
        yield Problem(
            "source_window_admits_nothing",
            f"source {source.source_id} has an outdoor window that admits nothing",
            source=source.source_id,
        )
    elif not outdoor_known and not source.outdoor.unbounded:
        yield Problem(
            "source_outdoor_without_sensor",
            f"source {source.source_id} is limited by outdoor temperature, "
            "but no outdoor sensor is set",
            source=source.source_id,
        )


def _rule_source_covered_zones(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint when a source's area names a zone that does not exist.

    Anker 12: `covers_zones` noemt zones, en een zone die niet bestaat kan dit
    apparaat nooit meebedienen. Stil overslaan zou de overname kleiner maken dan
    de gebruiker denkt en dat is precies het soort verschil dat je nergens ziet -
    dezelfde klacht die een gedeelde warmtebron met een onbekende zone al krijgt.

    Anchor 12: `covers_zones` names zones, and a zone that does not exist can
    never be served along by this appliance. Skipping it quietly would make the
    takeover smaller than the user thinks, and that is exactly the kind of
    difference you never see - the same complaint a shared heat source naming an
    unknown zone already gets.
    """
    known = {zone.zone_id for zone in config.zones}
    for _, source in config.sources():
        for zone_id in source.covers_zones:
            if zone_id not in known:
                yield Problem(
                    "source_unknown_covered_zone",
                    f"source {source.source_id} names unknown zone {zone_id} in its area",
                    source=source.source_id,
                    zone=zone_id,
                )


def _rule_family_hysteresis(
    zone: Zone, family: ModeFamily, settings: ModeSettings
) -> Iterator[Problem]:
    """Yield a complaint when a duty's hysteresis is not a usable number.

    Een niet-eindige hysterese glipt langs de `< 0`-controle, en een negatieve
    is een dode band de verkeerde kant op; beide maken het gedrag van de zone
    onvoorspelbaar.

    A non-finite hysteresis slips past the `< 0` check, and a negative one is
    a dead band the wrong way round; both make the zone's behaviour
    unpredictable.
    """
    if not math.isfinite(settings.hysteresis):
        yield Problem(
            "nonfinite_hysteresis",
            f"zone {zone.zone_id} has a non-finite {family.value} hysteresis",
            zone=zone.zone_id,
            mode=family.value,
        )
    elif settings.hysteresis < 0:
        yield Problem(
            "zone_negative_hysteresis",
            f"zone {zone.zone_id} has a negative {family.value} hysteresis",
            zone=zone.zone_id,
            mode=family.value,
        )


def _rule_family_outdoor_window(
    zone: Zone, family: ModeFamily, settings: ModeSettings, outdoor_known: bool
) -> Iterator[Problem]:
    """Yield a complaint when a duty's outdoor window can never be met.

    Een leeg venster laat de taak nooit draaien; een begrensd venster zonder
    buitensensor kan nooit voldaan worden. Beide zijn het stille niets waar
    deze hele controlelijst voor bestaat.

    An empty window never lets the duty run; a bounded window without an
    outdoor sensor can never be satisfied. Both are the silent nothing this
    whole problem list exists for.
    """
    if settings.outdoor.empty:
        yield Problem(
            "zone_window_admits_nothing",
            f"zone {zone.zone_id} has a {family.value} outdoor window that admits nothing",
            zone=zone.zone_id,
            mode=family.value,
        )
    elif not outdoor_known and not settings.outdoor.unbounded:
        yield Problem(
            "zone_outdoor_without_sensor",
            f"zone {zone.zone_id} limits {family.value} by outdoor temperature, "
            "but no outdoor sensor is set",
            zone=zone.zone_id,
            mode=family.value,
        )


def _rule_zones(config: DirectorConfig) -> Iterator[Problem]:
    """Yield every per-zone complaint, zone by zone.

    De volgorde binnen een zone is zichtbaar en staat vast; daarom is dit één
    regelfunctie met de zone-lus erin in plaats van één functie per controle
    (die zou de meldingen per controle groeperen in plaats van per zone). De
    uitsluitingen per bron en per taak staan elk in hun eigen hulpfunctie,
    zodat geen enkele `elif` uit elkaar valt.

    The order within one zone is visible and fixed; that is why this is one
    rule function containing the zone loop rather than one function per check
    (which would group complaints per check instead of per zone). The
    per-source and per-duty exclusions each live in their own helper, so no
    `elif` falls apart.
    """
    # Een begrensd buitenvenster kan zonder buitentemperatuur nooit voldaan
    # worden, dus alles wat er een heeft valt stil. Dat is de stilste manier
    # waarop een installatie kan blijven staan: elke zone besluit netjes "niets
    # te doen", en nergens staat waarom. Daarom is het een eigen melding.
    #
    # A bounded outdoor window can never be satisfied without an outdoor
    # temperature, so anything carrying one falls still. That is the quietest
    # way an installation can seize up: every zone decides "nothing to do", and
    # nowhere does it say why. Hence a problem of its own.
    outdoor_known = _outdoor_known(config)

    for zone in config.zones:
        if not zone.sources:
            yield Problem(
                "zone_without_sources",
                f"zone {zone.zone_id} has no sources",
                zone=zone.zone_id,
            )
        if not zone.indoor_sensor:
            yield Problem(
                "zone_without_sensor",
                f"zone {zone.zone_id} has no indoor temperature sensor",
                zone=zone.zone_id,
            )
        if zone.heat is None and zone.cool is None:
            yield Problem(
                "zone_neither_heats_nor_cools",
                f"zone {zone.zone_id} may neither heat nor cool",
                zone=zone.zone_id,
            )
        if zone.gate is ZoneGate.PRESENCE and not zone.presence_entity:
            yield Problem(
                "zone_presence_without_sensor",
                f"zone {zone.zone_id} runs on room presence but has no presence entity, "
                f"so it can never run",
                zone=zone.zone_id,
            )
        if zone.presence_timeout.total_seconds() < 0:
            yield Problem(
                "zone_negative_presence_timeout",
                f"zone {zone.zone_id} has a negative presence timeout",
                zone=zone.zone_id,
            )
        if (
            zone.heat is not None
            and zone.cool is not None
            and zone.cool.start_at <= zone.heat.start_at
        ):
            # Anders vragen verwarmen en koelen tegelijk om dezelfde kamer. De
            # engine kiest dan wel deterministisch, maar dat het zover komt is
            # een instelfout die niemand bedoeld kan hebben.
            #
            # Otherwise heating and cooling ask for the same room at once. The
            # engine still picks deterministically, but getting there is a
            # mistake nobody can have meant.
            yield Problem(
                "zone_cools_at_or_below_heats",
                f"zone {zone.zone_id} starts cooling at or below where it starts heating",
                zone=zone.zone_id,
            )
        elif (
            zone.heat is not None
            and zone.cool is not None
            and (
                zone.heat.start_at + zone.heat.hysteresis >= zone.cool.start_at
                or zone.cool.start_at - zone.cool.hysteresis <= zone.heat.start_at
            )
        ):
            # De twee banden raken elkaar of overlappen: het uitschakelpunt van
            # verwarmen ligt op of boven het aanpunt van koelen. Dan zou de kamer
            # om de beurt verwarmen en koelen - een instelfout die het scherm al
            # weigert, maar die uit een oudere opslag kan komen.
            #
            # The two bands touch or overlap: the heating switch-off point sits at
            # or above the cooling switch-on point. The room would then heat and
            # cool by turns - a mistake the screen already refuses, but one that
            # can come from older storage.
            yield Problem(
                "zone_bands_overlap",
                f"zone {zone.zone_id} has a heating and a cooling band that overlap",
                zone=zone.zone_id,
            )
        for source in zone.sources:
            yield from _rule_source_outdoor_window(source, outdoor_known)
        for family in (ModeFamily.HEAT, ModeFamily.COOL):
            settings = zone.settings_for(family)
            if settings is None:
                continue
            yield from _rule_family_hysteresis(zone, family, settings)
            yield from _rule_family_outdoor_window(zone, family, settings, outdoor_known)

            # Staat het seizoen vast op een seizoen waarin deze taak nooit mag
            # draaien, dan kan deze taak nooit draaien - het stille niets waar
            # `unreadable_entities` en `unsupported_modes` voor gebouwd zijn.
            # Alleen de vaste bron telt hier; de select is bedieningstoestand en
            # leeft in de koppelingslaag, die dezelfde melding zelf opent.
            #
            # With the season pinned to one this duty is never allowed in, the
            # duty can never run - the silent nothing `unreadable_entities` and
            # `unsupported_modes` exist for. Only the fixed source counts here;
            # the select is control state and lives in the binding layer, which
            # opens the same notice itself.
            pinned = _pinned_season(config.seasons)
            if pinned is not None and not settings.allowed_in(pinned):
                yield Problem(
                    "season_excludes_mode",
                    f"zone {zone.zone_id} may {family.value} only in "
                    f"{_season_names(settings.seasons)}, but the season is fixed "
                    f"to {pinned.value}",
                    zone=zone.zone_id,
                    mode=family.value,
                    allowed=_season_names(settings.seasons),
                    season=pinned.value,
                )

            if not any(source.supports(family) for source in zone.sources):
                yield Problem(
                    "zone_no_source_for_mode",
                    f"zone {zone.zone_id} wants {family.value} but has no source for it",
                    zone=zone.zone_id,
                    mode=family.value,
                )

            # De streeftemperatuur is wat het apparaat te horen krijgt; het
            # aanpunt is waar de zone besluit te beginnen. Ligt het streven aan
            # de verkeerde kant daarvan, dan start de zone keurig en zet hij
            # het apparaat vervolgens op een temperatuur waar het niets voor
            # hoeft te doen. Van buiten lijkt dat op een apparaat dat weigert.
            #
            # The target is what the appliance is told; the switch-on point is
            # where the zone decides to begin. If the target sits on the wrong
            # side of it, the zone starts dutifully and then sets the appliance
            # to a temperature it need do nothing for. From the outside that
            # looks like an appliance refusing.
            askew = (
                settings.target < settings.start_at
                if family is ModeFamily.HEAT
                else settings.target > settings.start_at
            )
            if askew:
                yield Problem(
                    "target_outside_band",
                    f"zone {zone.zone_id} starts {family.value} at {settings.start_at} "
                    f"but aims for {settings.target}",
                    zone=zone.name or zone.zone_id,
                    mode=family.value,
                    start=f"{settings.start_at:g}",
                    target=f"{settings.target:g}",
                )


def _rule_generators(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for every generator that doubles or names wrongly.

    Een gedeelde warmtebron die ook als zone-bron bestaat krijgt twee
    opdrachtgevers; een generator die een onbekende zone noemt kan die zone
    nooit bedienen.

    A shared heat source that also exists as a zone source gets two masters; a
    generator naming an unknown zone can never serve that zone.
    """
    zone_ids = [zone.zone_id for zone in config.zones]
    source_entities = {source.entity_id for _, source in config.sources()}
    for generator in config.generators:
        if generator.entity_id in source_entities:
            yield Problem(
                "generator_also_a_source",
                f"generator {generator.generator_id} uses climate entity "
                f"{generator.entity_id}, which is already a zone's source",
                generator=generator.generator_id,
                entity=generator.entity_id,
            )
        for zone_id in generator.zone_ids:
            if zone_id not in set(zone_ids):
                yield Problem(
                    "generator_unknown_zone",
                    f"generator {generator.generator_id} names unknown zone {zone_id}",
                    generator=generator.generator_id,
                    zone=zone_id,
                )


def _rule_circuits(config: DirectorConfig) -> Iterator[Problem]:
    """Yield every circuit complaint: shared priority, capacity, timing.

    Twee zones op één buitenunit met hetzelfde nummer laten de uitkomst
    afhangen van hun zone-id, dus alfabetisch. Dat crasht niets en beschadigt
    niets - de tie-break is deterministisch en het circuit houdt zich aan zijn
    ene taak - maar welke kamer wint is dan onzichtbaar en willekeurig.

    Two zones on one outdoor unit sharing a number leave the outcome hanging
    on their zone id, so alphabetical. That crashes nothing and damages
    nothing - the tie-break is deterministic and the circuit still keeps to
    its one duty - but which room wins becomes invisible and arbitrary.
    """
    for circuit in config.circuits:
        seen: dict[int, str] = {}
        for zone, _ in config.sources_on(circuit):
            if zone.priority in seen and seen[zone.priority] != zone.zone_id:
                yield Problem(
                    "shared_priority",
                    f"zones {seen[zone.priority]} and {zone.zone_id} share priority "
                    f"{zone.priority} on circuit {circuit.circuit_id}",
                    first=seen[zone.priority],
                    second=zone.zone_id,
                    priority=zone.priority,
                    circuit=circuit.circuit_id,
                )
            else:
                seen[zone.priority] = zone.zone_id

        if circuit.max_concurrent_units is not None and circuit.max_concurrent_units < 1:
            yield Problem(
                "circuit_allows_no_unit",
                f"circuit {circuit.circuit_id} allows no unit to run at all",
                circuit=circuit.circuit_id,
            )
        for label, span in (
            ("family switch delay", circuit.family_switch_delay),
            ("minimum switch interval", circuit.min_family_switch_interval),
            ("minimum cycle time", circuit.min_cycle_time),
        ):
            if span.total_seconds() < 0:
                yield Problem(
                    "circuit_negative_timing",
                    f"circuit {circuit.circuit_id} has a negative {label}",
                    circuit=circuit.circuit_id,
                    label=label,
                )


def _rule_openings(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for every opening that names or times wrongly.

    Een opening die een onbekende zone noemt kan nooit iets stilzetten; een
    negatieve vertraging is een timer die al verstreken is vóór hij begint.

    An opening naming an unknown zone can never stop anything; a negative
    delay is a timer already expired before it starts.
    """
    known_zones = {zone.zone_id for zone in config.zones}
    for opening in config.openings:
        for zone_id in opening.zone_ids:
            if zone_id not in known_zones:
                yield Problem(
                    "opening_unknown_zone",
                    f"opening {opening.entity_id} names unknown zone {zone_id}",
                    opening=opening.entity_id,
                    zone=zone_id,
                )
        if opening.delay.total_seconds() < 0:
            yield Problem(
                "opening_negative_delay",
                f"opening {opening.entity_id} has a negative delay",
                opening=opening.entity_id,
            )


def _rule_schedule_gate(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint when the schedule gate stands on nobody's schedule.

    De roosterpoort aan zonder één rooster laat niets ooit starten, en dat is
    van buiten niet te onderscheiden van een integratie die stuk is. De controle
    gaat per weekdag: één gewoon rooster op maandag laat dinsdag nog niets
    starten, en een alleen-vakantievenster telt op een gewone dag niet mee.

    The schedule gate on without a single schedule lets nothing ever start,
    which is indistinguishable from a broken integration from the outside. The
    check goes per weekday: one ordinary schedule on Monday still lets nothing
    start on Tuesday, and a holiday-only window does not count on an ordinary day.
    """
    if not config.gates.require_schedule:
        return
    missing = [
        day
        for day in range(7)
        if not any(resident.takes_part(holiday=False, weekday=day) for resident in config.residents)
    ]
    if missing:
        yield Problem(
            "schedule_gate_without_schedules",
            "the schedule gate is on but on some weekdays nobody has an ordinary schedule, "
            "so nothing can run on those days",
            days=str(len(missing)),
            weekdays=", ".join(str(day + 1) for day in missing),
        )


def _rule_stuck_time(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint when the stuck-detection time cannot work.

    Een negatieve tijd kan nooit aflopen. De openingsrust is een ingebouwde
    timer van drie minuten, en `SHORT_CYCLE_PROTECTION` staat in
    `WAITING_REASONS`; staat de vastlooptijd korter, dan kan de melder op die
    rust vals afgaan. Nul is uitgezonderd: dat is de schakelaar die de melder
    uitzet.

    A negative time can never elapse. The opening rest is a built-in
    three-minute timer, and `SHORT_CYCLE_PROTECTION` sits in `WAITING_REASONS`;
    with the stuck time shorter, the sensor can cry wolf on that rest. Zero is
    exempt: that is the switch turning the sensor off.
    """
    if config.stuck_after.total_seconds() < 0:
        yield Problem("negative_stuck_time", "the stuck-detection time is negative")

    stuck_seconds = config.stuck_after.total_seconds()
    if 0 < stuck_seconds < OPENING_MIN_REST.total_seconds():
        yield Problem(
            "stuck_after_below_opening_rest",
            "the stuck-detection time is below the built-in opening rest",
        )


def _rule_outdoor_deadband(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint when the outdoor dead band cannot do its job.

    Een niet-eindige of negatieve dode band maakt elke buitenvergelijking
    onbetrouwbaar; nul zonder circuit haalt de laatste rem onder een begrensde
    brander weg.

    A non-finite or negative dead band makes every outdoor comparison
    unreliable; zero without a circuit removes the last brake under a bounded
    burner.
    """
    if not math.isfinite(config.outdoor_hysteresis):
        yield Problem("nonfinite_outdoor_deadband", "the outdoor dead band is not a finite number")
    elif config.outdoor_hysteresis < 0:
        yield Problem("negative_outdoor_deadband", "the outdoor dead band is negative")
    elif config.outdoor_hysteresis == 0:
        # Zonder circuit is er niets dat de brander nog remt: het begrensde
        # buitenvenster is dan een schakelaar geworden die nergens op ingrijpt.
        # Het venster kan op de bron zelf zitten of op een taak die de bron
        # bedient; beide begrenzen wat het apparaat mag.
        #
        # Without a circuit there is nothing left to brake the burner: the
        # bounded outdoor window has then become a switch that touches nothing.
        # The window may sit on the source itself or on a duty the source
        # serves; both bound what the appliance may do.
        circuit_units = {unit for circuit in config.circuits for unit in circuit.units}

        def bounded(entity_id: str) -> bool:
            for _, source in config.sources():
                if source.entity_id == entity_id and not source.outdoor.unbounded:
                    return True
            for zone in config.zones:
                for source in zone.sources:
                    if source.entity_id != entity_id:
                        continue
                    for family in (ModeFamily.HEAT, ModeFamily.COOL):
                        if not source.supports(family):
                            continue
                        settings = zone.settings_for(family)
                        if settings is not None and not settings.outdoor.unbounded:
                            return True
            return False

        unbraked = sorted(
            eid
            for eid in {source.entity_id for _, source in config.sources() if source.entity_id}
            if eid not in circuit_units and bounded(eid)
        )
        for entity_id in unbraked:
            yield Problem(
                "zero_outdoor_deadband_no_circuit",
                f"appliance {entity_id} has a bounded outdoor window and sits on no "
                "circuit; with the outdoor dead band at zero nothing brakes its burner",
                entity=entity_id,
            )


def _rule_nonpositive_max_precondition(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint when no pre-conditioning request can ever run.

    Een maximum van nul of negatief maakt elk vooruit-verzoek onmogelijk; de
    instelling staat er dan wel, maar doet nooit iets.

    A maximum of zero or negative makes every pre-conditioning request
    impossible; the setting is there, but never does anything.
    """
    if config.gates.max_precondition.total_seconds() <= 0:
        yield Problem(
            "nonpositive_max_precondition",
            "the maximum pre-conditioning time is zero or negative, so no request can ever run",
        )


def _rule_house_wide_stops(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for every house-wide stop that can never stop.

    Een apparaat dat huisbreed stil hoort te vallen terwijl er niets is dat
    het ooit stilzet, is een instelling die er staat en niets doet. Beide
    helften zijn los te vergeten: de openingen kunnen ontbreken, en het
    apparaat kan bij geen enkele zone of gedeelde warmtebron horen - dan
    stuurt de director er nooit iets heen en valt er dus ook niets stil te
    zetten.

    An appliance meant to stop house-wide while nothing can ever stop it is a
    setting that sits there doing nothing. Both halves can be forgotten
    separately: the openings may be missing, and the appliance may belong to
    no zone and no shared heat source - the director then never sends it
    anything, so there is nothing to stop either.
    """
    if config.house_wide_openings and not config.openings:
        for entity_id in config.house_wide_openings:
            yield Problem(
                "house_wide_without_openings",
                f"appliance {entity_id} is set to stop while an opening stands open, "
                "but the installation has no openings at all",
                entity=entity_id,
            )

    steered = {source.entity_id for _, source in config.sources()} | {
        generator.entity_id for generator in config.generators
    }
    for entity_id in config.house_wide_openings:
        if entity_id not in steered:
            yield Problem(
                "house_wide_unmanaged",
                f"appliance {entity_id} is set to stop while an opening stands open, but no "
                "zone and no shared heat source uses it, so the director never steers it",
                entity=entity_id,
            )


def _rule_holiday_calendars(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint when holiday calendars have nothing to match on.

    Agenda's zonder trefwoord kunnen nooit een vakantiedag aanzetten; de
    instelling staat er dan wel, maar doet niets.

    Calendars without a keyword can never switch a holiday on; the setting is
    there, but does nothing.
    """
    if config.holiday_calendars and not config.holiday_keyword.strip():
        yield Problem(
            "calendars_without_keyword",
            "holiday calendars are set but no keyword is, so no event can ever "
            "switch holiday mode on",
        )


def _rule_exclusive_groups(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for every exclusive group naming an unknown source.

    Een groep die naar een onbekende bron wijst kan zijn uitsluiting nooit
    toepassen; de instelling staat er dan wel, maar doet niets.

    A group pointing at an unknown source can never apply its exclusion; the
    setting is there, but does nothing.
    """
    known_sources = {source.source_id for _, source in config.sources()}
    for group in config.exclusive_groups:
        for source_id in sorted(group - known_sources):
            yield Problem(
                "exclusive_group_unknown_source",
                f"exclusive group names unknown source {source_id}",
                source=source_id,
            )


def _quiet_problems(config: DirectorConfig) -> list[Problem]:
    """Return a complaint when the quiet windows leave no room to start.

    Een stiltevenster is het omgekeerde van een rooster: het zegt wanneer er
    níets mag beginnen. Wie dat verkeerd om leest en er vensters in zet die
    samen de klok rondgaan, krijgt een huis dat uit zichzelf nooit meer iets
    doet - en dat ziet er van buiten precies zo uit als een integratie die stuk
    is.

    Er is één ontsnapping: een bewoner die thuis is met een open roostervenster
    verslaat de stilte. Heeft niemand een rooster, dan is die ontsnapping er
    niet.

    Een kwartier is de grens. Niet nul: een gat van één minuut per dag is geen
    ruimte maar toeval, en dan begint er alleen iets als de klok precies goed
    valt.

    A quiet window is the inverse of a schedule: it says when nothing may start.
    Read that the wrong way round and put in windows that together go round the
    clock, and you get a house that never does anything of its own accord again
    - which looks, from the outside, exactly like a broken integration.

    There is one escape: a resident who is home with an open schedule window
    beats the quiet. If nobody has a schedule, that escape does not exist.

    A quarter of an hour is the line. Not zero: a gap of one minute a day is not
    room but coincidence, and then something only starts if the clock happens to
    fall right.
    """
    windows = [window for window in config.gates.quiet_windows if not window.holiday]
    if not windows:
        return []
    if any(resident.windows for resident in config.residents):
        return []

    silent = [day for day in range(7) if _free_minutes(windows, day) < QUIET_ROOM_MINUTES]
    if not silent:
        return []

    return [
        Problem(
            "quiet_covers_the_day",
            f"the quiet windows leave under {QUIET_ROOM_MINUTES} minutes on {len(silent)} day(s) "
            "and nobody has a schedule to beat them, so nothing can start on those days",
            days=str(len(silent)),
            minutes=str(QUIET_ROOM_MINUTES),
        )
    ]


def _free_minutes(windows: list[TimeWindow], weekday: int) -> int:
    """Return how many minutes of that day no quiet window covers.

    Geteld zoals `TimeWindow.contains` het leest: het beginpunt telt mee, het
    eindpunt niet. Zou dit ruimer tellen, dan zou een venster dat om 12:00
    eindigt en een venster dat om 12:00 begint samen als sluitend gelden
    terwijl er in werkelijkheid een minuut tussen zit.

    Counted the way `TimeWindow.contains` reads it: the start counts, the end
    does not. Counting this more loosely would let a window ending at 12:00 and
    one starting at 12:00 pass as watertight while a minute really sits between
    them.
    """
    covered = [False] * (24 * 60)
    for window in windows:
        start = window.start.hour * 60 + window.start.minute
        end = window.end.hour * 60 + window.end.minute

        # Een venster over middernacht hangt aan zijn startdag. Op déze dag telt
        # zowel het stuk na de start als het stuk dat gisteren begon.
        #
        # A window through midnight hangs off its starting day. On *this* day
        # both the piece after the start and the piece begun yesterday count.
        if start < end:
            spans = [(start, end, weekday)]
        elif start == end:
            spans = []
        else:
            spans = [(start, 24 * 60, weekday), (0, end, (weekday - 1) % 7)]

        for first, last, owning_day in spans:
            if window.weekdays is not None and owning_day not in window.weekdays:
                continue
            for minute in range(first, last):
                covered[minute] = True

    return covered.count(False)


def _rule_seasons(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint when the season can never be read.

    Staat de herkomst van het seizoen op *entiteit* zonder dat er een gekozen is,
    dan blijft het seizoen onbekend en doet elke taak met een seizoensbeperking
    niets. Dat is het stille niets waarvoor `unreadable_entities` bestaat, maar
    dan zonder dat er iets te herlezen valt: de entiteit die ontbreekt is er niet
    een die even wegvalt, maar een die nooit gekozen is.

    With the season source on *entity* and none chosen, the season stays unknown
    and every duty with a season restriction does nothing. That is the silent
    nothing `unreadable_entities` exists for, but with nothing to re-read: the
    entity that is missing is not one that dropped out for a moment, but one that
    was never chosen.
    """
    if config.seasons.source is SeasonSource.ENTITY and not config.seasons.entity_id:
        yield Problem(
            "season_entity_missing",
            "the season source is an entity, but none is chosen",
        )


def _layout_problems(config: DirectorConfig) -> list[str]:
    """Return the complaints about a heating layout that does not match the wiring.

    Waarschuwingen, geen blokkade. De director regelt gewoon door; dit zegt
    alleen dat de installatie er anders uitziet dan wat je koos, en dat is bijna
    altijd een vergissing die je pas merkt als het huis op de verkeerde plek
    warm wordt.

    Warnings, not a block. The director carries on regulating; this only says
    the installation looks different from what you picked, which is nearly
    always a mistake you notice when the wrong part of the house gets warm.
    """
    if len(config.zones) < 2:
        return []

    def heats(source: Source) -> bool:
        return bool(source.entity_id) and source.supports(ModeFamily.HEAT)

    # Welke zones leunen op welk verwarmingsapparaat.
    # Which zones lean on which heating appliance.
    shared: dict[str, list[str]] = {}
    for zone in config.zones:
        for entity_id in {source.entity_id for source in zone.sources if heats(source)}:
            shared.setdefault(entity_id, []).append(zone.zone_id)
    spanning = {entity_id: zones for entity_id, zones in shared.items() if len(zones) > 1}

    if config.heating_layout is HeatingLayout.PER_ZONE:
        # Een gedeeld apparaat is op zichzelf geen bewijs van een gesloten
        # systeem. Een gezoneerde cv werkt juist met EEN ketel en kleppen per
        # zone, en een kamer met een eigen airco plus de gasverwarming als
        # reserve is ook gewoon gezoneerd - die kan zichzelf verwarmen.
        #
        # Het gaat mis wanneer kamers uitsluitend op hetzelfde apparaat
        # aangewezen zijn: dan is er niets meer om per kamer te regelen, en
        # verwarmt aanzetten voor de een de ander mee.
        #
        # A shared appliance is no proof of a closed system by itself. A zoned
        # boiler system works precisely with ONE boiler and valves per zone, and
        # a room with its own air conditioner plus the gas heating as a stand-in
        # is zoned too - it can heat itself.
        #
        # It goes wrong when rooms depend on the same appliance and nothing
        # else: then there is nothing left to settle per room, and switching it
        # on for one warms the other along with it.
        for entity_id, zone_ids in sorted(spanning.items()):
            stranded = sorted(
                zone_id
                for zone_id in zone_ids
                if (candidate := config.zone(zone_id)) is not None
                and not [
                    source
                    for source in candidate.sources
                    if heats(source) and source.entity_id != entity_id
                ]
            )
            if len(stranded) > 1:
                return [
                    Problem(
                        "layout_zoned_with_shared_source",
                        (
                            f"heating is set to per zone, but {entity_id} is the only "
                            f"heat source of {len(stranded)} zones"
                        ),
                        entity=entity_id,
                        count=str(len(stranded)),
                        zones=", ".join(stranded),
                    )
                ]
        return []

    if config.heating_layout is HeatingLayout.CENTRAL and not spanning:
        return [
            Problem(
                "layout_central_without_shared_source",
                "heating is set to central, but no heat source is shared between zones",
                count=str(len(config.zones)),
            )
        ]

    return []


def _rule_resident_without_presence(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for every resident who can never be home.

    Een bewoner zonder aanwezigheidsentiteit telt nooit als thuis; elke poort
    die op die bewoner wacht, wacht voor niets.

    A resident without a presence entity never counts as home; every gate
    waiting on that resident waits for nothing.
    """
    for resident in config.residents:
        if not resident.presence_entity:
            yield Problem(
                "resident_without_presence",
                f"resident {resident.resident_id} has no presence entity, so can never be home",
                resident=resident.resident_id,
            )


def _duplicates(values: list[str]) -> list[str]:
    """Return the values occurring more than once, in first-seen order."""
    seen: set[str] = set()
    duplicated: list[str] = []
    for value in values:
        if value in seen and value not in duplicated:
            duplicated.append(value)
        seen.add(value)
    return duplicated


#: De regels die `validate()` afloopt, op volgorde. Die volgorde is zichtbaar
#: en staat vast: het bewaarscherm en de reparatiemelding `invalid_config`
#: tonen de meldingen in deze rij, en `tests/test_validation.py` houdt hem
#: letterlijk tegen een lijst.
#:
#: The rules `validate()` walks, in order. That order is visible and fixed: the
#: save screen and the `invalid_config` repair notice show the complaints in
#: this row, and `tests/test_validation.py` holds it literally against a list.
def _windows(config: DirectorConfig) -> Iterator[tuple[str, TimeWindow]]:
    """Yield every configured window with a readable label."""
    for window in config.gates.quiet_windows:
        yield "quiet window", window
    guest = config.gates.guest_window
    if guest is not None:
        yield "guest window", guest
    for resident in config.residents:
        if resident.sleep_window is not None:
            yield f"sleep window of {resident.name or resident.resident_id}", resident.sleep_window
        for window in resident.windows:
            yield f"schedule of {resident.name or resident.resident_id}", window


def _rule_dead_sleep_settings(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for a sleep setting that can never take effect.

    Een slaapvenster, uitslapen of uiterste tijd zonder slaapsensor kan nooit
    iets doen: de bewoner slaapt dan nooit. De opsta-rem is alleen dood als er
    ook een slaapvenster staat; zonder venster telt de slaapsensor de klok rond
    en remt de opsta-rem wel.

    A sleep window, sleeping in or a deadline without a sleep sensor can never
    do anything: the resident then never sleeps. The rise brake is dead only
    when a sleep window is set too; without a window the sleep sensor counts
    around the clock and the rise brake does brake.
    """
    for resident in config.residents:
        if resident.sleep_entity:
            continue
        dead: list[str] = []
        if resident.sleep_window is not None:
            dead.append("sleep window")
        if resident.sleep_in is not None:
            dead.append("sleep in until")
        if resident.wake_deadline is not None:
            dead.append("wait for this sleeper until")
        if resident.rise_brake is not None and resident.sleep_window is not None:
            dead.append("rise from")
        if dead:
            yield Problem(
                "resident_settings_without_sleep_sensor",
                f"resident {resident.resident_id} has sleep settings but no sleep sensor, "
                f"so they can never take effect: {', '.join(dead)}",
                resident=resident.name or resident.resident_id,
                settings=", ".join(dead),
            )


def _rule_windows_without_length(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for a window whose start equals its end.

    Zo'n venster is nooit open: het begin valt samen met het einde, en de
    vergelijking leest dat als een leeg venster. Dat is van buiten niet te
    onderscheiden van een venster dat iemand expres dicht liet.

    Such a window is never open: its start coincides with its end, and the
    comparison reads that as an empty window. From the outside that cannot be
    told apart from a window somebody deliberately left shut.
    """
    for label, window in _windows(config):
        if window.start == window.end:
            yield Problem(
                "window_without_length",
                f"{label} starts and ends at the same time, so it is never open",
                window=label,
            )


def _rule_guest_window_half_filled(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for a guest window with only one end filled in.

    Half een venster is geen venster: de gastenmodus geldt dan de hele dag.
    Dat is een stille verbreding van wat iemand invulde.

    Half a window is no window: guest mode then applies all day. That is a
    silent widening of what somebody filled in.
    """
    if config.gates.guest_window_incomplete:
        yield Problem(
            "guest_window_half_filled",
            "the guest window has only one end filled in, so guest mode applies all day",
        )


def _rule_cover_open_state(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for a cover opening that never reports open.

    Een `cover` meldt `open`, geen `on`. Staat de openingsstand op `on`, dan
    telt het dakraam nooit als open en stookt de installatie er dwars doorheen.

    A `cover` reports `open`, not `on`. With the opening state on `on`, the
    skylight never counts as open and the installation heats straight through
    it.
    """
    for opening in config.openings:
        if opening.entity_id.startswith("cover.") and opening.open_state != "open":
            yield Problem(
                "cover_opening_without_open_state",
                f"opening {opening.entity_id} is a cover but its open state is "
                f"{opening.open_state!r}, so it never counts as open",
                opening=opening.name or opening.entity_id,
                open_state=opening.open_state,
            )


def _rule_stuck_below_configured_rest(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint when the stuck time is shorter than a configured rest.

    De vastloopmelder staat op de wachtredenen, en een ingestelde circuit- of
    bronrust staat daar ook op. Is de vastlooptijd korter, dan meldt de sensor
    een apparaat als vastgelopen terwijl het netjes zijn rust neemt.

    The stuck notice sits on the waiting reasons, and a configured circuit or
    source rest sits there too. With a shorter stuck time the sensor reports an
    appliance as stuck while it is simply taking its rest.
    """
    stuck = config.stuck_after.total_seconds()
    if stuck <= 0:
        return
    for circuit in config.circuits:
        for label, rest in (
            ("minimum cycle time", circuit.min_cycle_time),
            ("minimum switch interval", circuit.min_family_switch_interval),
        ):
            if rest.total_seconds() > stuck:
                yield Problem(
                    "stuck_after_below_configured_rest",
                    f"the stuck-detection time is below the circuit's {label}",
                    subject=circuit.name or circuit.circuit_id,
                    label=label,
                    rest=str(int(rest.total_seconds())),
                    stuck_after=str(int(stuck)),
                )
    for _zone, source in config.sources():
        source_rest = source.min_cycle_time
        if source_rest is not None and source_rest.total_seconds() > stuck:
            yield Problem(
                "stuck_after_below_configured_rest",
                "the stuck-detection time is below the source's minimum cycle time",
                subject=source.name or source.entity_id,
                label="minimum cycle time",
                rest=str(int(source_rest.total_seconds())),
                stuck_after=str(int(stuck)),
            )


def _timing_problems(config: DirectorConfig) -> list[Problem]:
    """Return a complaint about switch timings on a circuit that never switches.

    Een buitenunit die verwarmen en koelen tegelijk aankan wisselt nooit van
    taak, dus een omschakelpauze en een minimale looptijd voor die wissel doen
    daar niets. Ze staan er dan wel, en dan ga je ervan uit dat ze werken.

    De kortcyclustijd en de capaciteitsgrens blijven wél gelden; die gaan over
    losse units en niet over de taak van het circuit.

    An outdoor unit that can heat and cool at once never switches duty, so a
    switch pause and a minimum run before that switch do nothing there. They
    still sit in the settings, and then you assume they work.

    The short-cycle time and the capacity limit do still apply; those are about
    individual units rather than about the circuit's duty.
    """
    return [
        Problem(
            "switch_timings_without_a_switch",
            f"circuit {circuit.circuit_id} can run both duties at once, so its switch pause "
            "and minimum run before switching never apply",
            circuit=circuit.name or circuit.circuit_id,
        )
        for circuit in config.circuits
        if circuit.simultaneous_heat_cool
        and (circuit.family_switch_delay or circuit.min_family_switch_interval)
    ]


RULES = (
    _rule_duplicate_zone_ids,
    _rule_duplicate_circuit_ids,
    _rule_duplicate_source_ids,
    _rule_duplicate_opening_ids,
    _rule_entity_twice_in_one_zone,
    _rule_unit_in_no_zone,
    _rule_unit_on_two_circuits,
    _rule_source_covered_zones,
    _rule_zones,
    _rule_generators,
    _rule_circuits,
    _rule_openings,
    _rule_schedule_gate,
    _rule_stuck_time,
    _rule_outdoor_deadband,
    _rule_nonpositive_max_precondition,
    _rule_house_wide_stops,
    _rule_holiday_calendars,
    _rule_resident_without_presence,
    _rule_exclusive_groups,
    _rule_seasons,
    _layout_problems,
    _quiet_problems,
    _timing_problems,
    _rule_dead_sleep_settings,
    _rule_windows_without_length,
    _rule_guest_window_half_filled,
    _rule_cover_open_state,
    _rule_stuck_below_configured_rest,
)
