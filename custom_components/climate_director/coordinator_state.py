"""De eigen staat van de onderdelen van de coordinator.

The own state of the coordinator's parts.

Elk `coordinator_*`-onderdeel (`coordinator_tracking.py`, `coordinator_round.py`,
`coordinator_reporting.py`, `coordinator_events.py` en `coordinator_lifecycle.py`)
bezit een klein stuk boekhouding. Dat staat hier als een klasse per onderdeel, in
plaats van als privé attributen op de coordinator zelf; de coordinator houdt één
exemplaar per klasse (`tracking`, `round`, `reporting`,
`events` en `lifecycle`). Een onderdeel leest en zet alleen zijn eigen
staat, of de staat van een ander onderdeel via dat publieke attribuut.

Each `coordinator_*` part (`coordinator_tracking.py`, `coordinator_round.py`,
`coordinator_reporting.py`, `coordinator_events.py` and `coordinator_lifecycle.py`)
owns a small piece of bookkeeping. It stands here as one class per part, instead of
as private attributes on the coordinator itself; the coordinator keeps one instance
per class (`tracking`, `round`, `reporting`, `events` and
`lifecycle`). A part reads and sets only its own state, or the state of
another part through that public attribute.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from homeassistant.core import CALLBACK_TYPE
from homeassistant.helpers.debounce import Debouncer

from .engine import ModeFamily, Plan
from .engine.heat_pick import OFF, HeatPick
from .engine.plan import Reason


@dataclass
class TrackingState:
    """What the coordinator records about what appliances and the weather do themselves."""

    commanded_off: dict[str, datetime] = field(default_factory=dict)
    """Sinds wanneer elk apparaat voor het laatst een uit-commando kreeg.

    Since when each appliance last received an off command.
    """

    commanded_on: dict[str, tuple[datetime, ModeFamily]] = field(default_factory=dict)
    """Sinds wanneer elk apparaat voor het laatst een aan-commando kreeg, en
    in welke taakfamilie: het spiegelbeeld van `commanded_off`, voor een
    apparaat dat zijn nieuwe stand pas een ronde later meldt. Zonder deze
    boekhouding las die late melding als een hand aan het apparaat - zie
    `we_wanted_it_on`.

    Since when each appliance last received an on command, and in which duty
    family: the mirror image of `commanded_off`, for an appliance reporting
    its new mode one round late. Without this bookkeeping that late report
    read as a hand at the appliance - see `we_wanted_it_on`.
    """

    precipitation_seen_at: datetime | None = None
    """Wanneer de neerslagbron voor het laatst neerslag meldde.

    De nalooptijd hangt hieraan: een bui van vijf minuten hoort de regeling
    niet te laten stuiteren, dus zodra de bron neerslag meldt blijft dat
    nog even gelden nadat het ophoudt. Dit moment wordt vastgelegd in de
    toestandswijziging van de bron (`notice_precipitation`) en bij het
    opstarten (`note_precipitation_now`), nooit in de lezer zelf. Zonder
    opstartstap begint een herstart op "geen neerslag", en dat is de
    onschadelijke kant om fout te zitten: dan geldt de gewone buitengrens
    gewoon weer.

    The moment the precipitation source last reported precipitation. The
    grace period hangs off this: a five-minute shower should not make the
    regulation bounce, so once the source reports precipitation it keeps
    counting for a while after it stops. This moment is recorded in the
    source's own state change (`notice_precipitation`) and at startup
    (`note_precipitation_now`), never in the reader itself. Without the
    startup step a restart begins on "no precipitation", which is the
    harmless side to be wrong on: the ordinary outdoor bound simply applies
    again.
    """


@dataclass
class RoundState:
    """What one decision round and its clock keep between two rounds."""

    debouncer: Debouncer[Any]
    """De ontdubbelaar die een reeks aanleidingen tot één ronde samenvoegt.

    The debouncer that folds a series of triggers into one round.
    """

    heat_pick: HeatPick = field(default_factory=lambda: HeatPick(None, OFF))
    zone_heat_picks: dict[str, HeatPick] = field(default_factory=dict)
    """De kostenvoorkeur van de laatste ronde; de volgende houdt er rekening mee.

    The cost preference of the last round; the next one takes it into account.
    """

    issued: Plan | None = None
    """Het plan dat nu uitgevoerd wordt, nog voordat het gepubliceerd is.

    `data` loopt een stap achter zolang de service calls draaien, en
    precies in dat gaatje meldt een apparaat zijn nieuwe stand. Zie
    `we_wanted_it_off`.

    The plan being carried out, before it is published. `data` lags by
    one step while the service calls run, and an appliance reports its new
    state in exactly that gap. See `we_wanted_it_off`.
    """

    sent_setpoints: dict[str, tuple[str, float]] = field(default_factory=dict)
    """Het laatst werkelijk uitgevoerde `(hvac_mode, temperature)` per apparaat.

    `engine.diff.changes()` gebruikt dit als "al verstuurd" voor een apparaat
    dat geen setpoint terugmeldt. Alleen wat `apply()` écht heeft uitgevoerd
    komt erin; een setpoint waarvan de aanroep mislukte dus niet.

    The last really executed `(hvac_mode, temperature)` per appliance.
    `engine.diff.changes()` uses this as "already sent" for an appliance that
    reports no setpoint. Only what `apply()` really executed enters it, so a
    setpoint whose call failed does not.
    """

    family_since: dict[str, datetime | None] = field(default_factory=dict)
    """Sinds wanneer elk circuit zijn huidige taak draait.

    Since when each circuit runs its current duty.
    """

    family_seen: dict[str, ModeFamily] = field(default_factory=dict)
    """De taak die elk circuit de vorige ronde draaide / the duty each circuit ran last round."""

    cancel_deferral: CALLBACK_TYPE | None = None
    """De geplande herbeoordeling bij een verlopende timer / the scheduled re-evaluation."""

    clock_reeval_unsub: CALLBACK_TYPE | None = None
    """De geplande vangnetklok / the scheduled safety-net tick."""

    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    """Houdt één beslisronde tegelijk / keeps one decision round at a time."""


@dataclass
class ReportingState:
    """What the coordinator measures about unusable entities and commands that do not take."""

    unusable_since: dict[str, datetime] = field(default_factory=dict)
    """Sinds wanneer elke ingestelde entiteit onleesbaar is.

    Since when each configured entity has been unreadable.
    """

    unusable_latest: dict[str, str] = field(default_factory=dict)
    """De onleesbare entiteiten van de laatste beslissingsronde.

    The unreadable entities of the latest decision round.
    """

    unsupported_since: dict[str, datetime] = field(default_factory=dict)
    """Sinds wanneer elke bron een stand vraagt die het apparaat niet kan.

    Since when each source asks a mode its appliance cannot run.
    """

    unapplied: dict[str, tuple[tuple[object, ...], int, datetime]] = field(default_factory=dict)
    """Hetzelfde verschil per apparaat: hoe vaak achter elkaar, en sinds wanneer.

    The same difference per appliance: how often in a row, and since when.
    """

    waiting: dict[str, tuple[Reason, datetime]] = field(default_factory=dict)
    """Sinds wanneer elke zone op dezelfde reden wacht.

    Since when each zone waits on the same reason.
    """


@dataclass
class EventsState:
    """What the coordinator remembers about the events it fires."""

    refused: set[str] = field(default_factory=set)
    """De zones waarvan een geweigerd vooruit-verzoek al gemeld is.

    The zones whose refused pre-conditioning request was already reported.
    """


@dataclass
class LifecycleState:
    """Where the coordinator stands between starting up and shutting down."""

    restored: bool = False
    """Pas ná het herstel van de opslag mag er beslist worden.

    De listeners staan meteen aan, zodat een toestandswijziging tijdens het
    opstarten van Home Assistant niet verloren gaat; beslissen op een half
    herstelde wereld mag niet. `async_on_hass_started` zet deze vlag ná
    `async_restore_state` en vóór de eerste beslissing, en `async_evaluate`
    wacht erop.

    Only after the store has been restored may a decision be taken. The
    listeners are on from the start, so a state change during Home
    Assistant's startup is not lost; deciding on a half-restored world is not
    allowed. `async_on_hass_started` raises this flag after
    `async_restore_state` and before the first decision, and
    `async_evaluate` waits for it.
    """

    closing: bool = False
    """Zodra de installatie afgebroken wordt, mag er niets meer naar buiten.

    Once the installation is being torn down, nothing may go out anymore.
    """
