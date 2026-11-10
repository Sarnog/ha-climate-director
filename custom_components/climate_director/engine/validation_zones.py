"""De controles op zones.

The checks on zones.

Dubbele zone-id's, een entiteit twee keer in een zone, een eenheid in geen zone, de
zoneregels, het rooster, de vastlooptijd, de buitenbanden en het maximum van een
vooruit-verzoek.

Doubled zone ids, an entity twice in a zone, a unit in no zone, the zone rules, the
schedule, the stuck time, the outdoor bands and the maximum of a pre-conditioning
request.
"""

from __future__ import annotations

import math
from collections.abc import Iterator

from .families import ModeFamily
from .models import DirectorConfig, ZoneGate
from .plan import OPENING_MIN_REST
from .problem import Problem
from .validation_shared import duplicates, outdoor_is_known, pinned_season, season_names
from .validation_sources import (
    rule_family_hysteresis,
    rule_family_outdoor_window,
    rule_source_outdoor_window,
)


def rule_duplicate_zone_ids(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for every zone id that occurs more than once.

    Een zone-id is de sleutel van alle per-zone-toestand in de engine; twee
    zones met dezelfde id delen die sleutel en zijn van buiten niet meer uit
    elkaar te houden.

    A zone id is the key of all per-zone state in the engine; two zones sharing
    one share that key and can no longer be told apart from the outside.
    """
    for zone_id in duplicates([zone.zone_id for zone in config.zones]):
        yield Problem("duplicate_zone_id", f"duplicate zone id: {zone_id}", zone=zone_id)


def rule_entity_twice_in_one_zone(config: DirectorConfig) -> Iterator[Problem]:
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
        for entity_id in duplicates([source.entity_id for source in zone.sources]):
            yield Problem(
                "entity_twice_in_one_zone",
                f"zone {zone.zone_id} uses {entity_id} for more than one source",
                zone=zone.name or zone.zone_id,
                entity=entity_id,
            )


def rule_unit_in_no_zone(config: DirectorConfig) -> Iterator[Problem]:
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


def rule_zones(config: DirectorConfig) -> Iterator[Problem]:
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
    outdoor_known = outdoor_is_known(config)

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
            yield from rule_source_outdoor_window(source, outdoor_known)
        for family in (ModeFamily.HEAT, ModeFamily.COOL):
            settings = zone.settings_for(family)
            if settings is None:
                continue
            yield from rule_family_hysteresis(zone, family, settings)
            yield from rule_family_outdoor_window(zone, family, settings, outdoor_known)

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
            pinned = pinned_season(config.seasons)
            if pinned is not None and not settings.allowed_in(pinned):
                yield Problem(
                    "season_excludes_mode",
                    f"zone {zone.zone_id} may {family.value} only in "
                    f"{season_names(settings.seasons)}, but the season is fixed "
                    f"to {pinned.value}",
                    zone=zone.zone_id,
                    mode=family.value,
                    allowed=season_names(settings.seasons),
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


def rule_schedule_gate(config: DirectorConfig) -> Iterator[Problem]:
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


def rule_stuck_time(config: DirectorConfig) -> Iterator[Problem]:
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


def rule_outdoor_deadband(config: DirectorConfig) -> Iterator[Problem]:
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


def rule_nonpositive_max_precondition(config: DirectorConfig) -> Iterator[Problem]:
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
