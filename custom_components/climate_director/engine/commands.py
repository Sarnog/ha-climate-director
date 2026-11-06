"""Het commando bouwen en de stopboekhouding. / Building the command and the stop bookkeeping."""

from __future__ import annotations

from . import constraints, takeover
from .candidates import handed_over
from .command_reasons import (
    idle_mode,
    opening_rest_hold,
    opening_stop_reason,
    unreadable_reason,
    untouched_reason,
    was_running,
)
from .command_stops import collapse_shared, stop_blocked
from .families import (
    MODE_HEAT,
    MODE_OFF,
    ModeFamily,
    preferred_mode,
)
from .grants import manual_conflict
from .models import DirectorConfig
from .plan import (
    Deferral,
    Plan,
    Reason,
    UnitCommand,
    UntouchedSource,
)
from .untouched import first_per_entity
from .world import WorldState
from .zone_decisions import clamped_target, command_order


def build_commands(
    config: DirectorConfig,
    world: WorldState,
    grants: dict[str, constraints.Grant],
    reasons: dict[str, Reason],
    wishes: dict[str, constraints.Request],
    refusals: dict[str, Reason],
    families: dict[str, ModeFamily],
    blocked: frozenset[str] = frozenset(),
    previous: Plan | None = None,
    takeovers: tuple[takeover.Takeover, ...] = (),
) -> tuple[
    tuple[UnitCommand, ...],
    tuple[UntouchedSource, ...],
    tuple[Deferral, ...],
    frozenset[str],
]:
    """Return the end state for every managed climate entity, and what is left alone.

    Sources that were not chosen are commanded off explicitly rather than left
    alone. That is what makes two appliances running against each other
    unreachable instead of merely unlikely.

    Drie gevallen krijgen wél niets, en alle drie met opzet. Die worden
    apart teruggegeven in plaats van stil overgeslagen: van buiten is "de
    director laat dit met rust" niet te onderscheiden van "de director doet
    niets", en dat verschil is nu juist wat je wilt weten.

    Three cases do get nothing, all three deliberately. Those are returned
    separately rather than quietly skipped: from the outside "the director is
    leaving this alone" is indistinguishable from "the director does nothing",
    and that difference is exactly what you want to know.
    """
    commands: list[UnitCommand] = []
    untouched: list[UntouchedSource] = []
    # Huisbreed overgedragen apparaten: de director stuurt ze nergens meer
    # naartoe, ook niet vanuit een andere zone (anker 11).
    # Appliances handed over house-wide: the director sends them nothing
    # anywhere, not from another zone either (anchor 11).
    handed_over_ids = handed_over(config, world)

    # De blind-reden van een apparaat wordt over ál zijn zones bepaald, zodat
    # NO_OUTDOOR_TEMPERATURE vóór NO_INDOOR_TEMPERATURE gaat ongeacht de
    # zonevolgorde — precies zoals `generator_commands` dat over zijn bediende
    # zones doet.
    #
    # An appliance's blind reason is decided over all its zones, so
    # NO_OUTDOOR_TEMPERATURE outranks NO_INDOOR_TEMPERATURE whatever the zone
    # order — exactly as `generator_commands` does over the zones it serves.
    served_zones: dict[str, list[str]] = {}
    for zone, source in config.sources():
        served_zones.setdefault(source.entity_id, []).append(zone.zone_id)
    blind_by_entity = {
        entity_id: unreadable_reason(refusals, zones) for entity_id, zones in served_zones.items()
    }

    for zone, source in config.sources():
        # Onbereikbaar en hoofdschakelaar uit zijn voor elke bron gelijk en
        # staan in `untouched_reason`, samen met de onleesbare-temperatuurtak
        # van anker 2. De override en de handbediende bron triggeren per pad en
        # blijven hier.
        #
        # Unreachable and master-off are the same for every source and live in
        # `untouched_reason`, together with anchor 2's unreadable-temperature
        # branch. The override and the manual source trigger per path and stay
        # here.
        shared = untouched_reason(world, entity_id=source.entity_id, blind=None)
        if shared is not None:
            untouched.append(UntouchedSource(source.entity_id, zone.zone_id, shared))
            continue

        # Een apparaat van een zone die van de gebruiker is krijgt niets: niet
        # aansturen en ook niet uitzetten, want wie zelf ingrijpt wil het apparaat
        # houden zoals het staat. Een huisbreed overgedragen apparaat krijgt om
        # dezelfde reden van niemand een commando, ook niet van een zone die het
        # anders zou uitzetten (`handed_over_ids`). Een hand zet alleen deze zone
        # stil, dus een gedeeld apparaat blijft voor de andere zones beschikbaar -
        # wordt het daar gekozen, dan valt het hieronder vanzelf af (`commanded`).
        #
        # An appliance of a zone that is the user's gets nothing: not steered and
        # not switched off either, since whoever steps in wants to keep the
        # appliance as it stands. For the same reason a house-wide handed-over
        # appliance gets no command from anyone, not even from a zone that would
        # otherwise switch it off (`handed_over_ids`). A hand silences this zone
        # alone, so a shared appliance stays available to the other zones - and
        # when it is chosen there, it drops out from under this rule by itself
        # (`commanded`).
        if world.overridden(zone.zone_id) or source.entity_id in handed_over_ids:
            untouched.append(
                UntouchedSource(source.entity_id, zone.zone_id, Reason.MANUAL_OVERRIDE)
            )
            continue

        grant = grants.get(zone.zone_id)
        chosen = grant is not None and grant.granted and grant.source_id == source.source_id

        # Een handbediende bron wordt niet aangestuurd tenzij hij in de weg
        # staat. Hem "voor de zekerheid" uitzetten zou precies het apparaat
        # uitschakelen dat iemand net met de hand heeft aangezet.
        #
        # A manual source is left alone unless it is in the way. Switching it
        # off "to be safe" would turn off exactly the appliance somebody just
        # switched on by hand.
        if not source.autostart:
            standing_down = manual_conflict(config, world, zone, source, wishes, families, grants)
            if standing_down is not None:
                commands.append(standing_down)
            else:
                untouched.append(
                    UntouchedSource(source.entity_id, zone.zone_id, Reason.MANUAL_SOURCE)
                )
            continue

        if chosen and grant is not None:
            settings = zone.settings_for(grant.family)
            commands.append(
                UnitCommand(
                    entity_id=source.entity_id,
                    hvac_mode=preferred_mode(grant.family),
                    temperature=clamped_target(
                        settings.target if settings else None,
                        world.climate(source.entity_id),
                    ),
                    zone_id=zone.zone_id,
                    source_id=source.source_id,
                    reason=Reason.REGULATING,
                )
            )
            continue

        # A zone that is being served has its other sources stood down for that
        # reason, not for whatever kept the chosen source waiting.
        served = grant is not None and grant.granted
        opening = opening_stop_reason(
            world,
            previous,
            source.entity_id,
            (zone.zone_id,),
            refusals,
            requires_received_heat=False,
        )
        if opening is not None:
            reason = opening
        else:
            blind = unreadable_reason(refusals, (zone.zone_id,))
            if blind is not None:
                blind = blind_by_entity[source.entity_id]
            shared = untouched_reason(world, entity_id=source.entity_id, blind=blind)
            if shared is not None:
                untouched.append(UntouchedSource(source.entity_id, zone.zone_id, shared))
                continue
            reason = (
                Reason.OTHER_SOURCE_CHOSEN
                if served
                else reasons.get(zone.zone_id, Reason.SATISFIED)
            )

        commands.append(
            UnitCommand(
                entity_id=source.entity_id,
                hvac_mode=idle_mode(config, world, source.entity_id, reason),
                temperature=None,
                zone_id=zone.zone_id,
                source_id=source.source_id,
                reason=reason,
            )
        )

    generator_calls, generator_untouched, generator_deferrals = generator_commands(
        config, world, grants, refusals, blocked, previous
    )
    commands.extend(generator_calls)
    untouched.extend(generator_untouched)
    pre_collapse = list(commands)
    commands = collapse_shared(config, world, commands)
    commands = stop_blocked(config, world, grants, blocked, commands)
    commands = takeover.stop_others(config, world, takeovers, commands, untouched)
    # De openingsstop hangt aan het apparaat, niet aan de reden die de collapse
    # overleefde. Bij een gedeelde ketel wint de reden van de zone met de meeste
    # voorrang, en dat is niet altijd de opening; de pre-collapse-opdrachten
    # weten nog wél welke apparaten erdoor stilgezet werden.
    #
    # The opening stop hangs on the appliance, not on the reason that survived
    # the collapse. On a shared boiler the reason of the highest-priority zone
    # wins, and that is not always the opening; the pre-collapse commands still
    # know which appliances it stopped.
    stopped_now = frozenset(
        command.entity_id
        for command in (*pre_collapse, *commands)
        if command.reason in (Reason.OPENING_OPEN, Reason.OPENING_OPEN_ELSEWHERE)
        and command.hvac_mode == MODE_OFF
        and was_running(world, previous, command.entity_id)
    )

    # Een gedeeld apparaat staat onder meerdere zones. Krijgt het via één zone
    # toch een opdracht, dan wordt het niet met rust gelaten - hoe de andere
    # zones erover dachten doet er dan niet meer toe.
    #
    # A shared appliance sits under several zones. If one of them commands it
    # after all, it is not being left alone - what the other zones thought of
    # it no longer matters.
    left_alone = tuple(first_per_entity(config, world, untouched, commands))

    # Stops before starts. On a circuit that has to swap duty, starting the new
    # one before the old has let go would put two duties on one compressor for
    # as long as the calls take to land.
    ordered = tuple(sorted(commands, key=lambda command: command_order(config, command)))
    return ordered, left_alone, generator_deferrals, stopped_now


def generator_commands(
    config: DirectorConfig,
    world: WorldState,
    grants: dict[str, constraints.Grant],
    refusals: dict[str, Reason],
    blocked: frozenset[str] = frozenset(),
    previous: Plan | None = None,
) -> tuple[list[UnitCommand], list[UntouchedSource], tuple[Deferral, ...]]:
    """Return the command for each shared heat source, and the ones left alone.

    A generator runs while any zone it serves is being heated, and stops once
    none is. There is nothing to arbitrate here - radiator valves all only ever
    heat - so this is a plain follow-along, not a conflict to resolve.

    De tweede lijst is voor `Plan.untouched`: een onbereikbare ketel hoort daar
    met `SOURCE_UNREACHABLE` in, niet stilletjes nergens. Een generator hoort
    bij geen enkele zone, dus zijn `UntouchedSource.zone_id` is leeg - behalve
    bij een override, waar de zone die de override draagt genoemd wordt.

    The second list feeds `Plan.untouched`: an unreachable boiler belongs there
    as `SOURCE_UNREACHABLE`, not silently nowhere. A generator belongs to no
    zone, so its `UntouchedSource.zone_id` is empty - except under an override,
    where the zone carrying the override is named.
    """
    commands: list[UnitCommand] = []
    untouched: list[UntouchedSource] = []
    deferrals: list[Deferral] = []

    for generator in config.generators:
        # Onbereikbaar en hoofdschakelaar uit zijn voor elke bron gelijk en
        # staan in `untouched_reason`. De override triggert hier pas zodra
        # niemand vraagt: aanzetten mag altijd, alleen het uitzetten wordt
        # ingehouden.
        #
        # Unreachable and master-off are the same for every source and live in
        # `untouched_reason`. The override triggers here only once nobody asks:
        # switching on stays allowed, only the off is withheld.
        shared = untouched_reason(world, entity_id=generator.entity_id, blind=None)
        if shared is not None:
            untouched.append(UntouchedSource(generator.entity_id, "", shared))
            continue

        asking = [
            zone
            for zone in config.zones
            if generator.serves(zone.zone_id)
            and (grant := grants.get(zone.zone_id)) is not None
            and grant.granted
            and grant.family is ModeFamily.HEAT
        ]

        if not asking:
            # Een zone met een override is overgedragen: de director weet niet
            # meer wat daar nodig is. Hem dan toch de gedeelde ketel laten
            # uitzetten maakt de override een halve maatregel - de kamer mag
            # zijn eigen kraan houden, maar het water wordt koud. Wie de
            # noodknop gebruikt, of een zone tijdelijk aan een eigen
            # automatisering laat, verwacht dat de director van die warmte
            # afblijft.
            #
            # Aanzetten mag wel: dat botst nooit met een zone die warmte wil.
            # Alleen het uitzetten wordt hier ingehouden.
            #
            # A zone under override has been handed over: the director no
            # longer knows what it needs. Letting it switch off the shared
            # boiler anyway would make the override a half measure - the room
            # keeps its own valve, but the water goes cold. Whoever reaches for
            # the override, or leaves a zone to an automation of their own,
            # expects the director to keep its hands off that heat.
            #
            # Switching on stays allowed: that never clashes with a zone that
            # wants heat. Only the switching off is withheld here.
            overridden = next(
                (
                    zone.zone_id
                    for zone in config.zones
                    if generator.serves(zone.zone_id) and world.overridden(zone.zone_id)
                ),
                "",
            )
            if overridden:
                untouched.append(
                    UntouchedSource(generator.entity_id, overridden, Reason.MANUAL_OVERRIDE)
                )
                continue

            # Waarom vraagt niemand? Is minstens één zone die vórige ronde
            # werkelijk warmte kreeg nu door een opening geweigerd, dan is deze
            # stop een openingsstop en hoort de generator dezelfde rust te
            # krijgen als elke andere bron zonder circuit - anders ontsteekt hij
            # zodra de deur weer dicht is. Eén tevreden kamer ernaast verandert
            # dat niet: de opening nam de vraag weg die deze generator bediende.
            # Vraagt niemand omdat elke zone om een andere reden stil is
            # (tevreden, buiten het seizoen), dan is dit een gewone vraagloze
            # stop en rust hij niet. Een generator die al uit stond rust ook
            # niet: anker 5 geldt alleen voor een apparaat dat werkelijk
            # draaide toen de stop kwam. De huisbrede stop gaat voor: die noemt
            # zijn eigen reden.
            #
            # Why is nobody asking? If at least one zone that really received
            # heat last round is now refused by an opening, this stop is an
            # opening stop and the generator deserves the same rest as any other
            # source without a circuit - otherwise it re-ignites the moment the
            # door closes again. One satisfied room next to it does not change
            # that: the opening took away the demand this generator was serving.
            # If nobody asks because every zone is silent for another reason
            # (satisfied, out of season), this is an ordinary no-demand stop and
            # it does not rest. A generator that was already off does not rest
            # either: anchor 5 only covers an appliance that really was running
            # when the stop came. The house-wide stop comes first: it names its
            # own reason.
            served = [zone.zone_id for zone in config.zones if generator.serves(zone.zone_id)]
            opening = opening_stop_reason(
                world,
                previous,
                generator.entity_id,
                served,
                refusals,
                requires_received_heat=True,
            )
            blind = unreadable_reason(refusals, served)
            if generator.entity_id in blocked:
                reason = Reason.OPENING_OPEN_ELSEWHERE
            elif opening is not None:
                reason = opening
            else:
                shared = untouched_reason(world, entity_id=generator.entity_id, blind=blind)
                if shared is not None:
                    untouched.append(UntouchedSource(generator.entity_id, "", shared))
                    continue
                reason = Reason.SATISFIED

            commands.append(
                UnitCommand(
                    entity_id=generator.entity_id,
                    hvac_mode=idle_mode(config, world, generator.entity_id, reason),
                    source_id=generator.generator_id,
                    reason=reason,
                )
            )
            continue

        # Zonder vaste waarde volgt de bron de warmste vraag. Het koudste
        # setpoint nemen zou de kamer die het hardst om warmte vraagt nooit
        # laten halen wat hij vroeg.
        #
        # Without a fixed value the source follows the warmest demand. Taking
        # the coldest setpoint would leave the room asking hardest never
        # reaching what it asked for.
        setpoint = generator.setpoint
        if setpoint is None:
            targets = [zone.heat.target for zone in asking if zone.heat]
            setpoint = max(targets) if targets else None

        if opening_rest_hold(
            config,
            world,
            previous,
            generator.entity_id,
            ignores_openings=any(
                world.precondition_ignores_openings(zone.zone_id) for zone in asking
            ),
            deferrals=deferrals,
        ):
            # De huisbrede stop geldt ook voor een generator; de herstart wacht
            # dezelfde rusttijd als een bron zonder circuit.
            #
            # The house-wide stop covers a generator too; the restart waits the
            # same rest as a source without a circuit.
            commands.append(
                UnitCommand(
                    entity_id=generator.entity_id,
                    hvac_mode=idle_mode(
                        config, world, generator.entity_id, Reason.SHORT_CYCLE_PROTECTION
                    ),
                    source_id=generator.generator_id,
                    reason=Reason.SHORT_CYCLE_PROTECTION,
                )
            )
            continue

        commands.append(
            UnitCommand(
                entity_id=generator.entity_id,
                hvac_mode=MODE_HEAT,
                temperature=clamped_target(setpoint, world.climate(generator.entity_id)),
                source_id=generator.generator_id,
                reason=Reason.REGULATING,
            )
        )

    return commands, untouched, tuple(deferrals)
