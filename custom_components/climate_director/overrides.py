"""De override met een looptijd (anker 11).

The override with a duration (anchor 11).

Een override zonder looptijd is de schakelaar die al bestond en die nooit
vanzelf vervalt. Deze module beheert de actie-interface eromheen: een looptijd,
een keuze *bij afloop* (uitzetten of laten staan) en hetzelfde-rondes-commando
voor stand en temperatuur. De engine blijft ongewijzigd: die weet alleen van
`zone_overrides`.

An override without a duration is the switch that already existed, which never
lapses by itself. This module manages the action interface around it: a
duration, a choice *on expiry* (turn off or leave be) and the same-round
command for mode and temperature. The engine stays unchanged: it only knows
about `zone_overrides`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.core import callback
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from .const import WHEN_DONE_LEAVE, WHEN_DONE_TURN_OFF
from .engine.diff import Change
from .engine.families import MODE_OFF, ModeFamily, family_of
from .engine.plan import Reason, UnitCommand

# De logger heet coordinator, zodat het verplaatsen van deze methodes geen
# enkele logregel verandert.
# The logger is called coordinator, so moving these methods changes no log line.
_LOGGER = logging.getLogger(f"{__package__}.coordinator")


class _OverridesMixin:
    """De looptijd-override: zetten, aflopen en stil vervallen.

    The timed override: setting it, letting it run out and letting it lapse
    silently.
    """

    # -- override met looptijd / override with a duration --------------------

    def async_set_override(
        self,
        zone_id: str,
        hvac_mode: str,
        temperature: float | None,
        minutes: float | None,
        when_done: str,
    ) -> bool:
        """Hand the zone over and set the appliance in the same decision round.

        De zone wordt hier overgedragen vóór de volgende beslisronde, zodat de
        engine die zone in die ronde met rust laat en de stand hieronder er niet
        meteen weer uit wordt gezet. Het commando zelf gaat via `applier.apply()`
        in díe ronde, samen met de overdracht: dat is de volgorde-valkuil uit de
        migratiebeslissingen.

        `minutes` is `None` when the call omitted the duration - then the
        override never lapses by itself. `when_done` is `turn_off` or `leave`.

        The zone is handed over here before the next decision round, so in that
        round the engine leaves the zone alone and the mode below is not thrown
        out again at once. The command itself goes through `applier.apply()` in
        that round, together with the handover: that is the order trap from the
        migration decisions.

        `minutes` is `None` when the call omitted the duration - then the
        override never lapses by itself. `when_done` is `turn_off` or `leave`.
        """
        zone = self.config.zone(zone_id)
        if zone is None:
            _LOGGER.warning("set_override asked for unknown zone, ignored: %s", zone_id)
            return False
        source = self._override_source(zone, hvac_mode)
        if source is None:
            _LOGGER.warning("set_override: zone %s has no source for %s", zone_id, hvac_mode)
            return False

        self.zone_overrides[zone_id] = True
        self._pending_override[zone_id] = Change(
            command=UnitCommand(
                entity_id=source.entity_id,
                hvac_mode=hvac_mode,
                temperature=temperature,
                zone_id=zone_id,
                source_id=source.source_id,
                reason=Reason.MANUAL_OVERRIDE,
            ),
            set_mode=True,
            set_temperature=temperature is not None,
        )

        if minutes is None:
            self.zone_override_until.pop(zone_id, None)
            self.zone_override_when_done.pop(zone_id, None)
            self.zone_override_entity.pop(zone_id, None)
        else:
            self.zone_override_until[zone_id] = dt_util.now() + timedelta(minutes=minutes)
            self.zone_override_when_done[zone_id] = when_done
            self.zone_override_entity[zone_id] = source.entity_id

        self._async_save_state()
        self._override_wake_at_first_expiry()
        self.async_request_evaluation()
        return True

    def async_clear_override(self, zone_id: str) -> None:
        """End the override the way a hand-off of the switch does: silently.

        Geen commando: de engine neemt de zone weer over en het apparaat gaat
        alleen uit als de beslissing dat nodig maakt. Een bron met
        `autostart: false` blijft dus draaien tot hij in de weg staat (anker 11).

        No command: the engine takes the zone back and the appliance only goes
        off if the decision needs it to. A source with `autostart: false`
        therefore keeps running until it stands in the way (anchor 11).
        """
        self.zone_overrides[zone_id] = False
        self._drop_override_timers(zone_id)
        self._pending_override.pop(zone_id, None)
        self._async_save_state()
        self._override_wake_at_first_expiry()
        self.async_request_evaluation()

    def _override_source(self, zone, hvac_mode: str):
        """Return the zone's source for `hvac_mode`, by priority.

        `off` en `fan_only` draaien niets en passen op elke bron; de hoogste
        prioriteit wint dan zonder familiefilter.

        `off` and `fan_only` run nothing and fit any source; the highest
        priority then wins without a family filter.
        """
        family = family_of(hvac_mode)
        if family is ModeFamily.NEUTRAL:
            candidates = list(zone.sources)
        else:
            candidates = [source for source in zone.sources if source.supports(family)]
        if not candidates:
            return None
        return min(candidates, key=lambda source: (source.priority, source.source_id))

    @callback
    def _consume_pending_override_changes(self) -> tuple[Change, ...]:
        """Return the same-round override commands and forget them."""
        pending = tuple(self._pending_override.values())
        self._pending_override.clear()
        return pending

    @callback
    def _drop_override_timers(self, zone_id: str) -> None:
        """Let one zone's duration lapse without a command."""
        self.zone_override_until.pop(zone_id, None)
        self.zone_override_when_done.pop(zone_id, None)
        self.zone_override_entity.pop(zone_id, None)

    @callback
    def _drop_lapsed_override_timers(self) -> None:
        """Drop durations of zones whose override was switched off by hand.

        De schakelaar schrijft alleen `zone_overrides[zone] = False`; de
        looptijd hoort dan stil te vervallen, zonder commando (anker 11).
        """
        dropped = False
        for zone_id in list(self.zone_override_until):
            if not self.zone_overrides.get(zone_id, False):
                self._drop_override_timers(zone_id)
                self._pending_override.pop(zone_id, None)
                dropped = True
        if dropped:
            self._async_save_state()
            self._override_wake_at_first_expiry()

    @callback
    def _consume_expired_overrides(self, now: datetime) -> tuple[Change, ...]:
        """Carry out every expiry choice due at `now`, and hand the zones back.

        De afloopkeuze is één commando op dat moment; daarna beslist de engine
        gewoon weer (anker 11). De keuze `leave` stuurt niets. In beide gevallen
        eindigt de overdracht hier.
        """
        due = [zone_id for zone_id, until in self.zone_override_until.items() if not now < until]
        if not due:
            return ()
        commands: list[Change] = []
        for zone_id in due:
            when_done = self.zone_override_when_done.get(zone_id, WHEN_DONE_LEAVE)
            entity_id = self.zone_override_entity.get(zone_id)
            if when_done == WHEN_DONE_TURN_OFF and entity_id:
                commands.append(
                    Change(
                        command=UnitCommand(
                            entity_id=entity_id,
                            hvac_mode=MODE_OFF,
                            zone_id=zone_id,
                            reason=Reason.MANUAL_OVERRIDE,
                        ),
                        set_mode=True,
                        set_temperature=False,
                    )
                )
            self.zone_overrides[zone_id] = False
            self._drop_override_timers(zone_id)
        self._async_save_state()
        self._override_wake_at_first_expiry()
        return tuple(commands)

    @callback
    def _override_wake_at_first_expiry(self) -> None:
        """Set the alarm on the first override that is still to run out."""
        self._cancel_pending_override_wake()
        pending = {
            zone_id: until
            for zone_id, until in self.zone_override_until.items()
            if self.zone_overrides.get(zone_id, False) and dt_util.now() < until
        }
        if not pending:
            return
        until = min(pending.values())
        seconds = (until - dt_util.now()).total_seconds()
        if seconds <= 0:
            return
        self._cancel_override_wake = async_call_later(
            self.hass, seconds + 1, self._on_override_expiry
        )

    @callback
    def _on_override_expiry(self, _now: datetime) -> None:
        """Decide again now an override has run out, and wait for the next one."""
        self._cancel_override_wake = None
        self.async_request_evaluation()
        self._override_wake_at_first_expiry()

    @callback
    def _cancel_pending_override_wake(self) -> None:
        """Drop the scheduled override wake-up, if there is one."""
        if self._cancel_override_wake is not None:
            self._cancel_override_wake()
            self._cancel_override_wake = None
