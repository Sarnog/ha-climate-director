"""Wat een apparaat zelf doet en wat de coordinator daarvan vastlegt.

What an appliance does itself and what the coordinator records.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.core import Event, EventStateChangedData
from homeassistant.util import dt as dt_util

from .const import (
    COMMANDED_WINDOW,
)
from .engine import (
    ModeFamily,
    family_of,
)
from .engine.diff import Change
from .readability import unreadable
from .world_builder import reads_as_home

if TYPE_CHECKING:
    from .coordinator import ClimateDirectorCoordinator

_LOGGER = logging.getLogger(__name__)
_COMMAND_NOT_TAKING_ROUNDS = 10


def _handle_change(
    coordinator: ClimateDirectorCoordinator, event: Event[EventStateChangedData]
) -> None:
    """Queue a fresh decision after a tracked entity changed."""
    coordinator._notice_precipitation(event)
    coordinator._notice_home(event)
    coordinator._notice_room_empty(event)
    coordinator._notice_hand_start(event)
    coordinator._notice_hand(event)
    coordinator._debouncer.async_schedule_call()


def _notice_precipitation(
    coordinator: ClimateDirectorCoordinator, event: Event[EventStateChangedData]
) -> None:
    """Remember the moment the precipitation source reports precipitation.

    Het moment hoort hier thuis, in de toestandswijziging van de bron zelf -
    niet in `_precipitation()`, dat alleen een antwoord teruggeeft. Elke
    nieuwe stand die neerslag is telt - dus ook een overgang tussen twee
    neerslagstanden (regen -> plensbui), want dan duurt de neerslag voort
    en hoort de nalooptijd mee te schuiven. Een overgang tussen twee droge
    standen (bewolkt -> zonnig) mag de nalooptijd niet verlengen.

    The moment belongs here, in the source's own state change - not in
    `_precipitation()`, which only returns an answer. Every new state that
    is precipitation counts - so also a transition between two
    precipitation states (rain -> pouring), since the precipitation then
    continues and the grace should move along. A transition between two dry
    states (cloudy -> sunny) must not extend the grace.
    """
    settings = coordinator.config.precipitation
    if not settings.enabled or event.data["entity_id"] != settings.source:
        return
    new_state = event.data["new_state"]
    if new_state is None or new_state.state not in settings.states:
        return
    coordinator._precipitation_seen_at = dt_util.now()


def _notice_hand(
    coordinator: ClimateDirectorCoordinator, event: Event[EventStateChangedData]
) -> None:
    """Record an appliance somebody switched off, or switched back on.

    Iemand die bij het apparaat zelf op uit drukt zegt daarmee iets, en dat
    overstemmen door het meteen weer aan te zetten is het ergste wat deze
    integratie kan doen. Dus: die zone valt stil tot dezelfde hand hem weer
    aanzet, of tot de volgende dag - want een besluit van gisteravond hoort
    vanochtend niet meer te gelden. Onze eigen aanzet van dat apparaat is
    diezelfde hand niet (anker 11); zie `_we_wanted_it_on`.

    Somebody pressing off on the appliance itself is saying something, and
    overriding that by switching it straight back on is the worst thing this
    integration can do. So: that zone falls silent until the same hand turns
    it back on, or until the next day - since last night's decision should
    not still hold this morning. Our own switch-on of that appliance is not
    that same hand (anchor 11); see `_we_wanted_it_on`.
    """
    # In schaduwmodus stuurt de director niets, dus valt er ook niemand te
    # overstemmen - en daarmee vervalt de reden waarom dit bestaat. Wat er
    # wél gebeurt is dat de bestaande automatiseringen de hele dag apparaten
    # aan- en uitzetten. Elk van die uitzettingen las als een hand, waarna
    # de zone werd overgedragen en er niets meer te vergelijken viel. Juist
    # dat vergelijken is het enige product van deze modus.
    #
    # In shadow mode the director steers nothing, so there is nobody to
    # overrule - and with that the reason this exists falls away. What does
    # happen is that the existing automations switch appliances on and off
    # all day. Every one of those switch-offs read as a hand, after which
    # the zone was handed over and there was nothing left to compare. That
    # comparing is this mode's only product.
    if coordinator.shadow:
        return

    entity_id = event.data["entity_id"]
    zones = coordinator.zones_of(entity_id)
    if not zones:
        return

    new_state = event.data["new_state"]
    old_state = event.data["old_state"]
    if new_state is None or old_state is None:
        return

    # Wegvallen en terugkomen is geen hand aan het apparaat. `unavailable`
    # en `unknown` zijn geen standen maar het ontbreken van een stand, en
    # `family_of()` leest ze - terecht - als "geen idee wat dit ding doet".
    # Daardoor las een apparaat dat terugkwam op `off` als iemand die het
    # net had uitgezet, en viel die zone de rest van de dag stil. Andersom
    # net zo: een apparaat dat wegvalt zou een handmatige uitzetting
    # opheffen alsof iemand hem weer had aangezet.
    #
    # Dropping out and coming back is not a hand at the appliance.
    # `unavailable` and `unknown` are not modes but the absence of one, and
    # `family_of()` reads them - rightly - as "no telling what this thing is
    # doing". So an appliance coming back on `off` read as somebody having
    # just switched it off, and that zone fell silent for the rest of the
    # day. The other way round just as much: an appliance dropping out would
    # lift a hand-back as though somebody had switched it on again.
    if unreadable(old_state.state) or unreadable(new_state.state):
        return

    was = family_of(old_state.state)
    now = family_of(new_state.state)
    if was is now:
        return

    if now is not ModeFamily.NEUTRAL:
        # Weer aangezet, met de hand of door ons: hoe dan ook meedoen.
        # Zodra het apparaat op eigen kracht weer een actieve stand meldt,
        # is de verklaring "ons uit-commando" per definitie verbruikt - hoe
        # het `off` ertussenin ook gemeld is, ook via `unavailable`.
        #
        # Switched on again, by hand or by us: taking part either way. Once
        # the appliance reports an active mode on its own again, the "our
        # off command" explanation is spent by definition - however the
        # `off` in between was reported, `unavailable` included.
        coordinator._commanded_off.pop(entity_id, None)

        # Onze eigen aanzet is geen hand aan het apparaat (anker 11); anders
        # hief de ene kamer met een gedeelde ketel de hand aan de andere kamer
        # op. Zie `_we_wanted_it_on`.
        #
        # Our own switch-on is no hand at the appliance (anchor 11); see
        # `_we_wanted_it_on`.
        if coordinator._we_wanted_it_on(entity_id, now):
            coordinator._commanded_on.pop(entity_id, None)
            return

        cleared = False
        for zone in zones:
            cleared = coordinator._handed_back.pop(zone, None) is not None or cleared
        if cleared:
            coordinator._async_save_state()
        return

    # Ook een hand die het apparaat uitzet verbruikt het setpoint: bij de
    # volgende start hoort het opnieuw mee te gaan, want niemand weet wat
    # het apparaat in de tussentijd met zijn eigen setpoint deed.
    #
    # A hand switching the appliance off spends the setpoint too: the next
    # start must carry it again, since nobody knows what the appliance did
    # with its own setpoint in the meantime.
    coordinator._sent_setpoints.pop(entity_id, None)

    # Het apparaat staat nu uit: de verklaring "ons aan-commando" is daarmee
    # verbruikt, hoe dat `off` ook gemeld is.
    #
    # The appliance stands off now: that spends the "our on command"
    # explanation with it, however that `off` was reported.
    coordinator._commanded_on.pop(entity_id, None)

    # Alleen als wíj hem niet net hebben uitgezet. Ons eigen commando is
    # geen handmatige ingreep, en zou de zone anders permanent stilleggen.
    #
    # Only when we did not just switch it off ourselves. Our own command is
    # not a hand at the appliance, and would otherwise silence the zone for
    # good.
    if coordinator._we_wanted_it_off(entity_id):
        # Ons uit-commando is nu aangekomen: de notitie die de late melding
        # moest verklaren is verbruikt. Een volgende `off` - nadat wij hem
        # zelf weer hebben aangezet - is dus weer gewoon een hand aan het
        # apparaat. Het venster blijft alleen nog als vangnet voor een
        # melding die nóóit aankomt.
        #
        # Our off command has now arrived: the note that had to explain the
        # late report is spent. A next `off` - after we switched it back on
        # ourselves - is therefore an ordinary hand at the appliance again.
        # The window remains only as a safety net for a report that never
        # arrives.
        coordinator._commanded_off.pop(entity_id, None)
        return

    today = dt_util.now().date()
    if any(coordinator._handed_back.get(zone) != today for zone in zones):
        for zone in zones:
            coordinator._handed_back[zone] = today
        coordinator._async_save_state()


def _note_commanded_off(
    coordinator: ClimateDirectorCoordinator, applied: tuple[Change, ...]
) -> None:
    """Remember when we last told each appliance to stand down.

    `_we_wanted_it_off` kijkt hierin in plaats van alleen naar het plan dat
    nú op tafel ligt: een apparaat dat zijn stand pas een poll later meldt,
    rapporteert ons eigen `off` soms pas nadat het plan alweer is
    omgeslagen. Het plan zegt dan \"we wilden hem aan\", en zonder deze
    boekhouding las dat late bericht als een hand aan het apparaat.

    `_we_wanted_it_off` looks here rather than only at the plan on the
    table right now: an appliance reporting its state one poll late
    sometimes reports our own `off` only after the plan has flipped back.
    The plan then says \"we wanted it on\", and without this bookkeeping
    that late report read as a hand at the appliance.
    """
    now = dt_util.now()
    for change in applied:
        if family_of(change.command.hvac_mode) is not ModeFamily.NEUTRAL:
            continue
        # Het apparaat gaat uit: een setpoint dat bij het uitzetten vergeten
        # wordt (of met de hand verzet) hoort bij de volgende start gewoon
        # opnieuw te gaan. Anders bleef "al verstuurd" eeuwig staan en kwam
        # het setpoint nooit meer mee.
        #
        # The appliance is going off: a setpoint forgotten on the way out
        # (or moved by hand) must simply be sent again at the next start.
        # Otherwise "already sent" stood forever and the setpoint never
        # came along again.
        coordinator._sent_setpoints.pop(change.entity_id, None)
        reported = coordinator.hass.states.get(change.entity_id)
        if (
            reported is not None
            and not unreadable(reported.state)
            and family_of(reported.state) is ModeFamily.NEUTRAL
        ):
            # Het apparaat meldt ons uit-commando al: er is geen late
            # melding meer te verklaren, en een oude notitie is daarmee ook
            # verbruikt. `_notice_hand` kan deze notitie niet zelf opruimen
            # op dit moment, want die liep al tijdens `apply` - vóórdat
            # deze boekhouding geschreven werd.
            #
            # The appliance already reports our off command: there is no
            # late report left to explain, and any old note is spent with
            # it. `_notice_hand` cannot clear it here itself, because it
            # already ran during `apply` - before this bookkeeping was
            # written.
            coordinator._commanded_off.pop(change.entity_id, None)
        else:
            coordinator._commanded_off[change.entity_id] = now


def _note_commanded_on(
    coordinator: ClimateDirectorCoordinator, applied: tuple[Change, ...]
) -> None:
    """Remember when we last told each appliance to run, and doing what.

    Het spiegelbeeld van `_note_commanded_off`, en om dezelfde reden: een
    apparaat dat zijn stand pas een poll later meldt, meldt onze eigen aanzet
    soms pas nadat het plan alweer is omgeslagen. Zonder deze boekhouding zou
    `_we_wanted_it_on` die late melding voor een hand aan het apparaat
    aanzien, en verviel de hand van elke zone eraan.

    De taakfamilie gaat mee: een apparaat dat wij `heat` vroegen en dat
    vervolgens `cool` meldt, meldt iets wat wij niet vroegen - dat is een hand
    en geen eigen aanzet.

    The mirror image of `_note_commanded_off`, and for the same reason: an
    appliance reporting its mode one poll late sometimes reports our own
    switch-on only after the plan has flipped back. Without this bookkeeping
    `_we_wanted_it_on` would take that late report for a hand at the
    appliance, and the hand of every zone hanging off it would lapse.

    The duty family comes along: an appliance we asked for `heat` and that
    then reports `cool` reports something we did not ask for - that is a hand,
    not our own switch-on.
    """
    now = dt_util.now()
    for change in applied:
        family = family_of(change.command.hvac_mode)
        if family is ModeFamily.NEUTRAL:
            continue
        reported = coordinator.hass.states.get(change.entity_id)
        if (
            reported is not None
            and not unreadable(reported.state)
            and family_of(reported.state) is family
        ):
            # Het apparaat meldt onze aanzet al: er is geen late melding meer
            # te verklaren, en een oude notitie is daarmee ook verbruikt.
            # `_notice_hand` kan deze notitie niet zelf opruimen op dit
            # moment, want die liep al tijdens `apply` - vóórdat deze
            # boekhouding geschreven werd.
            #
            # The appliance already reports our switch-on: there is no late
            # report left to explain, and any old note is spent with it.
            # `_notice_hand` cannot clear it here itself, because it already
            # ran during `apply` - before this bookkeeping was written.
            coordinator._commanded_on.pop(change.entity_id, None)
        else:
            coordinator._commanded_on[change.entity_id] = (now, family)


def _we_wanted_it_off(coordinator: ClimateDirectorCoordinator, entity_id: str) -> bool:
    """Return whether we told this appliance to stand down, or meant to.

    Eerst de boekhouding van wat er écht is uitgezonden: die dekt ook het
    apparaat dat zijn stand pas een poll later meldt, wanneer het plan
    alweer is omgeslagen. Daarna het plan dat op tafel ligt, niet het plan
    dat af is - een apparaat meldt zijn nieuwe stand terwijl de service
    call nog loopt, en op dat moment staat het gepubliceerde besluit nog op
    de vorige ronde.

    First the bookkeeping of what was really sent: that also covers the
    appliance reporting its state one poll late, when the plan has already
    flipped back. Then the plan on the table, not the plan that is
    finished - an appliance reports its new state while the service call is
    still running, and at that moment the published decision is still the
    previous round's.
    """
    when = coordinator._commanded_off.get(entity_id)
    if when is not None and dt_util.now() - when <= COMMANDED_WINDOW:
        return True

    plan = coordinator._issued or coordinator.data
    if plan is None:
        return False
    for command in plan.commands:
        if command.entity_id == entity_id:
            return family_of(command.hvac_mode) is ModeFamily.NEUTRAL
    return False


def _we_wanted_it_on(
    coordinator: ClimateDirectorCoordinator, entity_id: str, family: ModeFamily
) -> bool:
    """Return whether the active mode this appliance reports is our own doing.

    `_notice_hand` gebruikt dit om onze eigen aanzet niet voor een hand aan
    het apparaat aan te zien (anker 11): alleen dezelfde hand, slapen, een
    leeg huis en de volgende dag heffen een hand op, niet het feit dat de
    director een gedeeld apparaat voor een andere kamer aanzet.

    Twee sporen, en allebei nodig. De boekhouding van wat er écht is
    uitgezonden (`_commanded_on`) dekt het apparaat dat zijn stand pas een
    poll later meldt, wanneer het plan alweer is omgeslagen; de familie moet
    daar kloppen - vroegen wij `heat` en meldt het apparaat `cool`, dan is dat
    niet onze aanzet maar een hand. De wijzigingen van deze ronde
    (`last_changes`, gezet vóór `apply`) dekken de melding die tijdens de
    service call zelf binnenkomt - op dat moment is de boekhouding nog niet
    geschreven.

    Het plan dat op tafel ligt doet hier bewust **niet** mee, anders dan bij
    `_we_wanted_it_off`: zodra de hand er staat laat de director de zone met
    rust, dus een plan dat dit apparaat vraagt is het plan van vóór de hand -
    en dan zou dezelfde hand die het apparaat weer aanzet zijn eigen hand niet
    meer opheffen. `last_changes` zegt precies wat wij net stuurden.

    `_notice_hand` uses this so it does not take our own switch-on for a hand
    at the appliance (anchor 11): only the same hand, sleeping, an empty house
    and the next day lift a hand, not the director switching a shared
    appliance on for another room.

    Two traces, and both are needed. The bookkeeping of what was really sent
    (`_commanded_on`) covers the appliance reporting its mode one poll late,
    when the plan has already flipped back; the family has to match there - we
    asked for `heat` and the appliance reports `cool`, and that is not our
    switch-on but a hand. The changes of this round (`last_changes`, set
    before `apply`) cover the report arriving during the service call itself -
    at that moment the bookkeeping has not been written yet.

    The plan on the table deliberately plays no part here, unlike in
    `_we_wanted_it_off`: the moment the hand stands, the director leaves the
    zone alone, so a plan asking for this appliance is the plan from before
    the hand - and the same hand switching the appliance back on would then no
    longer lift its own hand. `last_changes` says exactly what we just sent.
    """
    noted = coordinator._commanded_on.get(entity_id)
    if noted is not None:
        when, duty = noted
        if duty is family and dt_util.now() - when <= COMMANDED_WINDOW:
            return True
    return any(
        change.entity_id == entity_id and family_of(change.command.hvac_mode) is family
        for change in coordinator.last_changes
    )


def _note_home_now(coordinator: ClimateDirectorCoordinator) -> None:
    """Fill in the homecoming moments this process has not seen yet.

    Anker 13, besluit 4: de listener ziet alleen overgangen, en wie al thuis
    was toen dit proces begon heeft er geen gehad. Zonder deze stap zouden al
    die bewoners een onbekend moment hebben, en dan remt het stiltevenster
    voor hen - terwijl zij er juist al zaten. De terugval is `last_changed`
    van de aanwezigheidsentiteit, begrensd door het slaapmoment: bij een
    eerste start is dat "net thuis", en dan blijft het stil tot het venster
    afloopt.

    Anchor 13, decision 4: the listener only sees transitions, and whoever was
    already home when this process started had none. Without this step all
    those residents would have an unknown moment, and then the quiet window
    brakes for them - while they were the ones already sitting there. The
    fallback is the presence entity's `last_changed`: on a first start that is
    "just home", and then it stays quiet until the window has passed. At most
    once, since the listener takes over as soon as the resident moves.

    Nothing is overwritten: a moment from storage stays, even when it is older
    than `last_changed` - that is exactly the difference decision 3 wants. And
    nothing is filled in for whoever is not home.
    """
    for resident in coordinator.config.residents:
        if resident.resident_id in coordinator._home_since:
            continue
        presence = resident.presence_entity
        state = coordinator.hass.states.get(presence) if presence else None
        if reads_as_home(state):
            since = state.last_changed
            if coordinator._asleep_since is not None and since > coordinator._asleep_since:
                since = coordinator._asleep_since
            coordinator._home_since[resident.resident_id] = since
