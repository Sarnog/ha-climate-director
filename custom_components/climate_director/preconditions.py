"""De vooruit-verzoeken en hun timers.

The pre-conditioning requests and their timers.

Een lopend vooruit-verzoek is en blijft één begrip in de engine:
`world.preconditioning`. Deze module beheert alleen de bedieningskant: het
starten en afbreken van verzoeken, en de wekker die een beslissing aanvraagt
zodra het eerstvolgende verzoek afloopt. De engine blijft ongewijzigd.

A running pre-conditioning request is and remains one concept in the engine:
`world.preconditioning`. This module only manages the control side: starting and
cancelling requests, and the alarm that asks for a decision the moment the first
request runs out. The engine stays unchanged.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime, timedelta

from homeassistant.core import callback
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

# De logger heet coordinator, zodat het verplaatsen van deze methodes geen
# enkele logregel verandert.
#
# The logger is called coordinator, so moving these methods changes no log line.
_LOGGER = logging.getLogger(f"{__package__}.coordinator")


def _still_running(requests: Mapping[str, datetime], now: datetime) -> dict[str, datetime]:
    """Return the pre-conditioning requests that have not run out at `now`.

    Een gewone functie in plaats van een methode: hij wordt zowel gelezen als
    opgeruimd aangeroepen, en dan hoort er geen twijfel te bestaan over welke
    van de twee je krijgt.

    A plain function rather than a method: it is called both to read and to
    prune, and then there should be no doubt about which of the two you get.
    """
    return {zone_id: until for zone_id, until in requests.items() if now < until}


class _PreconditionsMixin:
    """De vooruit-verzoeken en hun timers.

    The pre-conditioning requests and their timers.
    """

    # -- vooruit verwarmen / pre-conditioning --------------------------------

    def live_preconditions(self) -> dict[str, datetime]:
        """Return the requests that have not run out, without touching anything.

        Voor wie alleen wil weten hoe het ervoor staat: de diagnose. Die hoort
        niets te wijzigen aan het huis waar hij een storing van vastlegt.

        For anyone who only wants to know where things stand: the diagnostics.
        Those should alter nothing about the house whose fault they capture.
        """
        return _still_running(self._precondition, dt_util.now())

    @callback
    def async_precondition(
        self,
        zone_ids: list[str] | None,
        minutes: float | None,
        *,
        ignore_openings: bool = False,
    ) -> dict[str, datetime]:
        """Start warming the named zones up for somebody on their way home.

        `zone_ids` is `None` when the call omitted the field - then every known
        zone runs. An explicit empty list means no zones at all: a template that
        renders to nothing must not heat the whole house by accident.

        The request is capped at the configured maximum, so asking for longer
        than the installation allows shortens the request rather than refusing
        it: the intent was clear, only the number was wrong.

        `minutes` is `None` when the call omitted the duration - then the
        configured maximum applies, which is what the blueprint relies on when
        it confirms a refused request. A non-positive number is refused instead:
        zero minutes is no request, and treating it as the maximum would turn a
        typo into the longest run the installation allows.

        `minutes` is `None` als de aanroep de duur wegliet - dan geldt het
        ingestelde maximum, precies wat de blueprint verwacht als hij een
        geweigerd verzoek bevestigt. Een niet-positief getal wordt geweigerd:
        nul minuten is geen verzoek, en dat als maximum tellen zou van een
        typefout de langste run maken die de installatie toestaat.

        `ignore_openings` laat het verzoek doorgaan met een raam of deur open.
        Standaard weigert dat, en terecht - stoken tegen de buitenlucht in is
        weggegooid geld. Wie het raam zelf openzette weet dat en mag zeggen:
        toch doen. De keuze hoort bij het verzoek, niet bij de aanroep, want de
        poort wordt telkens opnieuw beoordeeld.

        `ignore_openings` lets the request run with a window or door open. That
        is refused by default, and rightly so - heating against the outside air
        is money thrown away. Whoever opened the window knows that and may say:
        do it anyway. The choice belongs to the request rather than to the call,
        since the gate is judged afresh every time.
        """
        ceiling = self.config.gates.max_precondition
        if ceiling.total_seconds() <= 0:
            # De instellingen laten dit niet toe, maar een met de hand bewerkte
            # configuratie kan het wel. Dan mag de knop niet in stilte niets
            # doen - de validate()-waarschuwing op het bewaarscherm noemt het,
            # en dit logbericht legt het vast voor wie de melding wegklikte.
            #
            # The settings do not allow this, but a hand-edited configuration
            # can. The button then may not silently do nothing - the validate()
            # warning on the save screen names it, and this log line records it
            # for whoever dismissed the notice.
            _LOGGER.warning("Pre-conditioning is disabled: max_precondition is zero or negative")
            return {}
        if minutes is None:
            length = ceiling
        else:
            if minutes <= 0:
                return {}
            length = min(timedelta(minutes=minutes), ceiling)
        until = dt_util.now() + length

        known = {zone.zone_id for zone in self.config.zones}
        requested = list(zone_ids) if zone_ids is not None else sorted(known)
        unknown = sorted(set(requested) - known)
        if unknown:
            _LOGGER.warning(
                "Pre-conditioning asked for unknown zones, ignored: %s",
                ", ".join(unknown),
            )
        chosen = [zone_id for zone_id in requested if zone_id in known]
        for zone_id in chosen:
            self._precondition[zone_id] = until
            if ignore_openings:
                self._precondition_bypass.add(zone_id)
            else:
                self._precondition_bypass.discard(zone_id)

        if chosen:
            self._async_save_state()
            self._wake_at_the_first_expiry()
            self.async_request_evaluation()
        return dict.fromkeys(chosen, until)

    @callback
    def async_cancel_precondition(self, zone_ids: list[str] | None) -> None:
        """Call the whole thing off, for the named zones or for all of them.

        `zone_ids` is `None` when the call omitted the field - then every
        request is cancelled. An explicit empty list cancels nothing.
        """
        known = {zone.zone_id for zone in self.config.zones}
        if zone_ids is None:
            self._precondition.clear()
            self._precondition_bypass.clear()
        else:
            unknown = sorted(set(zone_ids) - known)
            if unknown:
                _LOGGER.warning(
                    "Cancel pre-conditioning asked for unknown zones, ignored: %s",
                    ", ".join(unknown),
                )
            for zone_id in zone_ids:
                self._precondition.pop(zone_id, None)
                self._precondition_bypass.discard(zone_id)
        # De wekker gaat mee met de verzoeken die er nog staan. Is er niets
        # meer, dan blijft de staande wekker gewoon aflopen: hij vraagt dan een
        # beslisronde die niets te doen vindt, en een ronde zonder verschil kost
        # geen service call.
        #
        # The alarm follows the requests still standing. With nothing left the
        # standing alarm simply runs out: it then asks for a round that finds
        # nothing to do, and a round without a difference costs no service call.
        self._wake_at_the_first_expiry()
        self._async_save_state()
        self.async_request_evaluation()

    @callback
    def _wake_at_the_first_expiry(self) -> None:
        """Set the alarm on the first request that is still to run out.

        Op de opgeschoonde lijst, niet op de ruwe. Een verzoek dat er nog in
        staat maar allang voorbij is, wint anders de `min()`, waarna
        `_preconditions_expire_at` ziet dat dat moment achter ons ligt en
        helemaal geen wekker zet - ook niet voor het verzoek dat wel loopt.

        On the pruned list, not on the raw one. A request still sitting there
        but long since over otherwise wins the `min()`, after which
        `_preconditions_expire_at` sees that moment lies behind us and sets no
        alarm at all - not even for the request that is running.
        """
        pending = self._live_preconditions()
        if pending:
            self._preconditions_expire_at(min(pending.values()))

    @callback
    def _preconditions_expire_at(self, until: datetime) -> None:
        """Re-evaluate the moment the request runs out.

        Zonder dit blijft een lege woning doorstoken tot er toevallig iets
        anders verandert, en op een stille middag gebeurt dat lang niet.

        Er staat er altijd maar één, op het eerstvolgende verzoek dat afloopt;
        gaat die af, dan zet hij zichzelf op het verzoek daarna. Zonder dat
        handvat bleef er bij elk verzoek een wekker hangen die na het afsluiten
        van de installatie alsnog afging, op een coordinator die er niet meer
        was.

        Without this an empty house keeps burning until something else happens
        to change, and on a quiet afternoon that is a long wait.

        There is only ever one, set on the first request to run out; when it
        fires it sets itself on the next one. Without that handle every request
        left an alarm hanging that went off after the installation was torn
        down, on a coordinator that was no longer there.
        """
        self._cancel_pending_precondition_wake()
        seconds = (until - dt_util.now()).total_seconds()
        if seconds <= 0:
            return
        self._cancel_precondition_wake = async_call_later(
            self.hass, seconds + 1, self._on_precondition_expiry
        )

    @callback
    def _on_precondition_expiry(self, _now: datetime) -> None:
        """Decide again now a request has run out, and wait for the next one."""
        self._cancel_precondition_wake = None
        self.async_request_evaluation()
        self._wake_at_the_first_expiry()

    @callback
    def _cancel_pending_precondition_wake(self) -> None:
        """Drop the scheduled wake-up, if there is one."""
        if self._cancel_precondition_wake is not None:
            self._cancel_precondition_wake()
            self._cancel_precondition_wake = None
