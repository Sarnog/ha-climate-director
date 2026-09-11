"""De met de hand gegeven staat: bewaren, herstellen en in quarantaine.

The hand-given state: storing, restoring and quarantining.

Een vooruit-verzoek en een apparaat dat iemand zelf uitzette zijn de twee dingen
die een mens met de hand aan de installatie heeft gezegd, en die een herstart
horen te overleven. Deze module bewaart ze, leest ze terug en zet een
onleesbaar bestand opzij zonder de integratie stil te leggen.

A pre-conditioning request and an appliance somebody switched off are the two
things a person has said to the installation by hand, and they should survive a
restart. This module stores them, reads them back and puts an unreadable file
aside without silencing the integration.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from homeassistant.core import callback
from homeassistant.util import dt as dt_util

from . import problems

# De logger heet coordinator, zodat het verplaatsen van deze methodes geen
# enkele logregel verandert.
#
# The logger is called coordinator, so moving these methods changes no log line.
_LOGGER = logging.getLogger(f"{__package__}.coordinator")


class _StateStoreMixin:
    """Opslag, herstel en quarantaine van wat een mens met de hand heeft gezegd.

    Storage, restore and quarantine of what a person said by hand.
    """

    # -- met de hand gegeven, dus bewaren / given by hand, so kept ----------

    def _store_payload(self) -> dict[str, Any]:
        """Return the hand-given state worth keeping across a restart."""
        return {
            "until": {zone_id: until.isoformat() for zone_id, until in self._precondition.items()},
            "bypass": sorted(self._precondition_bypass),
            "handed_back": {zone_id: day.isoformat() for zone_id, day in self._handed_back.items()},
            "override_until": {
                zone_id: until.isoformat()
                for zone_id, until in getattr(self, "zone_override_until", {}).items()
            },
            "override_when_done": dict(getattr(self, "zone_override_when_done", {})),
            "override_entity": dict(getattr(self, "zone_override_entity", {})),
        }

    @callback
    def _async_save_state(self) -> None:
        """Write away wat een mens met de hand heeft gezegd.

        Een verzoek is het enige dat een leeg huis mag laten draaien, en het is
        met de hand gegeven. Herstart Home Assistant tien minuten later, dan is
        het zonder dit spoorloos weg - en de gebruiker komt thuis in een koud
        huis zonder te weten waarom.

        Hetzelfde geldt voor een apparaat dat iemand bij het apparaat zelf heeft
        uitgezet. Dat besluit hoort tot de volgende dag te blijven staan, en een
        herstart is geen reden om er alsnog overheen te gaan - dat is precies
        het ergste wat deze integratie kan doen.

        Wat hier NIET in staat, en na een herstart dus opnieuw begint: de
        wachtteller achter de vastloopmelder, en het moment waarop een circuit
        zijn taak aannam. Die eerste meldt hooguit een kwartier later, die
        tweede geeft een apparaat hooguit een extra pauze. Allebei tijdelijk, en
        allebei aan de veilige kant.

        Write away what a person said by hand.

        A request is the only thing allowed to run an empty house, and it was
        given by hand. If Home Assistant restarts ten minutes later it is gone
        without trace - and the user comes home to a cold house with no idea
        why.

        The same holds for an appliance somebody switched off at the appliance
        itself. That decision should stand until the next day, and a restart is
        no reason to override it after all - which is precisely the worst thing
        this integration can do.

        What is NOT in here, and therefore starts afresh after a restart: the
        waiting clock behind the stuck sensor, and the moment a circuit took on
        its duty. The first reports a quarter of an hour later at worst, the
        second costs an appliance one extra pause at worst. Both temporary, and
        both on the safe side.
        """
        # P1: een ronde die bij het afsluiten nog doorloopt - `apply` wacht op
        # cloud-integraties - mag na de flush geen nieuwe uitgestelde schrijfactie
        # meer plannen; die zou het bestand ná `async_remove_entry` terugschrijven.
        #
        # P1: a round still running during shutdown - `apply` waits on cloud
        # integrations - must not schedule a new delayed write after the flush;
        # that would resurrect the file after `async_remove_entry`.
        if getattr(self, "_closing", False):
            return
        self._store.async_delay_save(self._store_payload, 1)

    async def _async_restore_state(self) -> None:
        """Read back what was standing before the restart.

        Verlopen verzoeken komen niet terug: de tijd liep door terwijl Home
        Assistant weg was, en een verzoek van gisteren alsnog uitvoeren is
        erger dan het te vergeten. Een handmatige uitzetting van gisteren
        vervalt om dezelfde reden - de datum is de hele vervaltermijn.

        Een ouder bestand draagt nog geen `handed_back`. Dat leest gewoon als
        niets, dus de opslagversie hoeft er niet voor omhoog: er valt niets te
        migreren aan een sleutel die er niet was.

        Elk veld wordt net zo vergevingsgezind gelezen als `serialise.py`: een
        waarde met een andere vorm dan verwacht telt als afwezig, niet als
        reden om de hele integratie stil te leggen. Alleen een bestand dat in
        het geheel niet te lezen is wordt opzij gezet.

        Expired requests do not come back: time ran on while Home Assistant was
        away, and carrying out yesterday's request after the fact is worse than
        forgetting it. Yesterday's hand-back lapses for the same reason - the
        date is the whole expiry.

        An older file carries no `handed_back` yet. That simply reads as
        nothing, so the storage version need not go up for it: there is nothing
        to migrate about a key that was never there.

        Every field is read as forgivingly as `serialise.py`: a value of a
        different shape than expected counts as absent, not as a reason to
        silence the whole integration. Only a file that cannot be read at all
        is put aside.
        """
        try:
            stored = await self._store.async_load()
        except Exception:
            _LOGGER.exception("Reading the stored state of %s failed", self.name)
            await self._quarantine_storage()
            return

        if not stored:
            return

        if not isinstance(stored, Mapping):
            _LOGGER.error("The stored state of %s has no readable shape", self.name)
            await self._quarantine_storage()
            return

        now = dt_util.now()

        until_raw = stored.get("until")
        if isinstance(until_raw, Mapping):
            for zone_id, raw in until_raw.items():
                until = dt_util.parse_datetime(str(raw))
                if until is not None and now < until:
                    self._precondition[zone_id] = until

        bypass_raw = stored.get("bypass")
        if isinstance(bypass_raw, (list, tuple, set)):
            self._precondition_bypass = {
                zone_id for zone_id in bypass_raw if zone_id in self._precondition
            }

        handed_raw = stored.get("handed_back")
        if isinstance(handed_raw, Mapping):
            today = now.date()
            for zone_id, raw in handed_raw.items():
                day = dt_util.parse_date(str(raw))
                if day == today:
                    self._handed_back[zone_id] = day

        if hasattr(self, "_restore_overrides"):
            self._restore_overrides(stored, now)

        self._wake_at_the_first_expiry()

    def _restore_overrides(self, stored: Mapping[str, Any], now: datetime) -> None:
        """Restore timed overrides; expired ones lapse without a command.

        Een verlopen looptijd komt niet terug: de tijd liep door terwijl Home
        Assistant weg was, en gisteren aflopende keuze alsnog uitvoeren is erger
        dan haar te vergeten. De overdracht zelf vervalt dan ook: de engine
        neemt de zone weer over, precies zoals na een afloop terwijl de
        integratie draaide.

        An expired duration does not come back: time ran on while Home Assistant
        was away, and carrying out yesterday's expiry choice after the fact is
        worse than forgetting it. The handover itself then lapses too: the
        engine takes the zone back, exactly as after an expiry while the
        integration ran.
        """
        if not hasattr(self, "zone_override_until"):
            # Een stand-in zonder override-staat (tests) laadt gewoon wat hij kent.
            # A stand-in without override state (tests) simply loads what it knows.
            return
        until_raw = stored.get("override_until")
        when_raw = stored.get("override_when_done")
        entity_raw = stored.get("override_entity")
        known_zones = {zone.zone_id for zone in self.config.zones}
        if isinstance(until_raw, Mapping):
            for zone_id, raw in until_raw.items():
                if zone_id not in known_zones:
                    continue
                until = dt_util.parse_datetime(str(raw))
                if until is None or not now < until:
                    self.zone_overrides.pop(zone_id, None)
                    continue
                self.zone_override_until[zone_id] = until
                self.zone_overrides[zone_id] = True
        if isinstance(when_raw, Mapping):
            for zone_id, raw in when_raw.items():
                if zone_id in self.zone_override_until and isinstance(raw, str):
                    self.zone_override_when_done[zone_id] = raw
        if isinstance(entity_raw, Mapping):
            for zone_id, raw in entity_raw.items():
                if zone_id in self.zone_override_until and isinstance(raw, str):
                    self.zone_override_entity[zone_id] = raw
        self._override_wake_at_first_expiry()

    async def _quarantine_storage(self) -> None:
        """Move an unreadable state file aside and tell the user.

        Het bestand is onleesbaar of heeft een vorm die nergens op lijkt. De
        director begint dan met een lege staat - verzoeken en handmatige
        uitzettingen van voor de herstart zijn weg - en het bestand gaat opzij
        zodat elke volgende herstart er niet opnieuw over struikelt. De melding
        zegt dat het gebeurd is; het bestand zelf blijft staan voor wie het uit
        een back-up terug wil zetten.

        The file is unreadable or shaped like nothing at all. The director then
        starts with an empty state - requests and hand-backs from before the
        restart are gone - and the file is moved aside so every next restart
        does not trip over it again. The notice says it happened; the file
        itself stays for anyone wanting to put it back from a backup.
        """
        path = Path(self._store.path)
        # Geen `isoformat()`: de dubbele punten daarin mogen niet in een
        # Windows-bestandsnaam. Not `isoformat()`: its colons are not allowed
        # in a Windows file name.
        stamp = dt_util.utcnow().strftime("%Y%m%dT%H%M%S%f")
        corrupt = path.with_name(f"{path.name}.corrupt.{stamp}")
        try:
            await self.hass.async_add_executor_job(os.rename, path, corrupt)
        except OSError:
            _LOGGER.exception("Moving the unreadable state file %s aside failed", path)
        problems.async_report_corrupt_storage(
            self.hass,
            self.config_entry.entry_id,
            self.config_entry.title,
            str(corrupt),
        )
