"""De handstart: iemand zet zelf een apparaat aan terwijl zijn zone wacht.

The hand start: somebody switches an appliance on themselves while its zone waits.

Een handstart is géén hand. Een hand zet een apparaat uit en valt stil tot
dezelfde hand, het slapen, een leeg huis of de volgende dag; een handstart zet
een zone aan en laat alleen `WAITING_FOR_SLEEPER`, `EARLY_RISER` en
`QUIET_HOURS` passeren. De knop per zone en een actieve stand die niet van de
director komt zetten dezelfde notitie. De coordinator bewaart haar over een
herstart en laat haar vallen in de eerste leesbare ronde waarin geen van die
drie remmen de zone nog tegenhoudt, of bij slapen, een leeg huis of de volgende
dag. Een ronde met een onleesbare aanwezigheids- of slaapsensor laat haar staan.

A hand start is not a hand. A hand switches an appliance off and stays silent
until the same hand, sleep, an empty house or the next day; a hand start switches
a zone on and lets only `WAITING_FOR_SLEEPER`, `EARLY_RISER` and `QUIET_HOURS`
pass. The per-zone button and an active mode that does not come from the
director make the same note. The coordinator keeps it across a restart and drops
it in the first readable round in which none of those three brakes still holds
the zone, or on sleep, an empty house or the next day. A round with an
unreadable presence or sleep sensor leaves it standing.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import date, datetime
from typing import Any

from homeassistant.core import Event, EventStateChangedData, callback
from homeassistant.util import dt as dt_util

from .engine import ModeFamily, WorldState, family_of, hand_start
from .engine.gates import brakes_remaining
from .hand import HandMixin
from .readability import unreadable
from .stored_state import stored_time


class HandStartMixin(HandMixin):
    """Herkenning, opslag en verval van een handstart.

    Recognition, storage and expiry of a hand start.
    """

    handed_back: dict[str, date]

    @callback
    def notice_hand_start(self, event: Event[EventStateChangedData]) -> None:
        """Record an appliance somebody switched on while a zone was waiting.

        Alleen een actieve stand die niet van ons komt telt. `we_wanted_it_on`
        verklaart onze eigen aanzet, ook wanneer het apparaat die pas een poll
        later meldt; die late melding mag geen handstart worden. Een bron met
        *Dit apparaat automatisch aanzetten* uit telt niet, en een gedeeld
        apparaat start elke zone die het bedient - inclusief de zones uit
        `covers_zones`. Staat er geen enkele zone op een wachtreden, dan doet
        de gebeurtenis niets.

        Only an active mode that does not come from us counts. `we_wanted_it_on`
        explains our own switch-on, also when the appliance reports it one poll
        later; that late report must not become a hand start. A source with
        *Start this appliance automatically* off does not count, and a shared
        appliance starts every zone it serves - including the zones in
        `covers_zones`. When no zone waits on a brake, the event does nothing.
        """
        if self.shadow:
            return

        new_state = event.data["new_state"]
        old_state = event.data["old_state"]
        if new_state is None or old_state is None:
            return
        if unreadable(old_state.state) or unreadable(new_state.state):
            return

        duty = family_of(new_state.state)
        if duty is ModeFamily.NEUTRAL or family_of(old_state.state) is duty:
            return

        entity_id = event.data["entity_id"]
        if self.we_wanted_it_on(entity_id, duty):
            return

        zones = self._hand_start_zones(entity_id)
        if not zones or not any(self._waiting_on_a_brake(zone_id) for zone_id in zones):
            return
        self._remember_hand_starts(zones)

    @callback
    def async_hand_start(self, zone_id: str) -> None:
        """Start one zone by hand when its button is pressed.

        De knop is invoer, geen beslissing: een zone die nergens op wacht
        verandert niets en geeft ook geen fout. De verse wereld bepaalt of een
        van de drie remmen nu geldt; een oude beslissing zou net na een
        toestandswissel achterlopen.

        The button is input, not a decision: a zone that waits on nothing
        changes nothing and raises nothing. The fresh world decides whether one
        of the three brakes applies now; an old decision could lag just after a
        state change.
        """
        zone = self.config.zone(zone_id)
        if zone is None or zone_id in self._hand_starts:
            return
        if not brakes_remaining(self.config, self.build_world(), zone, self.data):
            return
        self._remember_hand_starts((zone_id,))

    @callback
    def _remember_hand_starts(self, zone_ids: tuple[str, ...]) -> None:
        """Note the hand start for these zones and ask for a decision."""
        known = {zone.zone_id for zone in self.config.zones}
        now = dt_util.now()
        changed = False
        for zone_id in zone_ids:
            if zone_id not in known or zone_id in self._hand_starts:
                continue
            self._hand_starts[zone_id] = now
            changed = True
        if changed:
            self.async_save_state()
            self.async_request_evaluation()

    def _waiting_on_a_brake(self, zone_id: str) -> bool:
        """Return whether the last decision names one of the three brakes.

        De vorige beslissing is precies wat er vóór de hand aan de hand was. Een
        verse wereld zou de hand zelf al als 'draaiend' zien en een rem kunnen
        laten verdwijnen; daarom leest de herkenning de gepubliceerde
        `closed_gates`.

        The previous decision is exactly what stood before the hand. A fresh
        world would already see the hand as 'running' and could make a brake
        disappear; recognition therefore reads the published `closed_gates`.
        """
        plan = self.data
        decision = plan.decision_for(zone_id) if plan is not None else None
        return decision is not None and bool(
            hand_start.HAND_START_BRAKES.intersection(decision.closed_gates)
        )

    def _hand_start_zones(self, entity_id: str) -> tuple[str, ...]:
        """Return every zone this hand-started appliance serves.

        Een bron met `autostart` uit is geen handstart: de director regelt daar
        het aanzetten nooit. De gebieden uit `covers_zones` horen erbij, want
        een handstart op de cv-thermostaat moet elke kamer starten die hij
        bedient.

        A source with `autostart` off is no hand start: the director never
        switches it on there. The areas in `covers_zones` belong with it, since
        a hand start on the boiler thermostat must start every room it serves.
        """
        known = {zone.zone_id for zone in self.config.zones}
        found: list[str] = []
        for zone in self.config.zones:
            for source in zone.sources:
                if source.entity_id != entity_id or not source.autostart:
                    continue
                for zone_id in (zone.zone_id, *source.covers_zones):
                    if zone_id in known and zone_id not in found:
                        found.append(zone_id)
        return tuple(found)

    def _hand_starts_payload(self) -> dict[str, Any]:
        """Return the hand starts the store must keep across a restart."""
        return {zone_id: started.isoformat() for zone_id, started in self._hand_starts.items()}

    def _restore_hand_starts(self, stored: Mapping[str, Any], now: datetime) -> None:
        """Read the stored hand starts, today's only, without overwriting a fresh one.

        Een ontbrekende sleutel leest als geen handstart - de director wacht dan
        zoals altijd, de onschadelijke kant. Een ouder bestand hoeft daarvoor
        niet opzij en de opslagversie blijft staan. Een moment van gisteren komt
        niet terug; een handstart die tijdens het opstarten al genoteerd is
        blijft staan naast wat de opslag nog heeft.

        A missing key reads as no hand start - the director then waits as always,
        the harmless side. An older file need not be put aside for that and the
        storage version stays. Yesterday's moment does not come back; a hand
        start already noted during the startup stays beside what the store still
        has.
        """
        raw = stored.get("hand_starts")
        if not isinstance(raw, Mapping):
            return
        known = {zone.zone_id for zone in self.config.zones}
        today = now.date()
        for zone_id, value in raw.items():
            if zone_id not in known or zone_id in self._hand_starts:
                continue
            moment = stored_time(value)
            if moment is not None and moment.date() == today:
                self._hand_starts[zone_id] = moment

    def settle_hand_starts(self, world: WorldState) -> WorldState:
        """Drop the hand starts that no longer do anything, and hand the world theirs.

        Slapen, een leeg huis en de volgende dag zijn de drie uitwegen die niets
        met een poort te maken hebben. Daarnaast vervalt een handstart in de
        eerste leesbare ronde waarin geen van de drie remmen de zone nog
        tegenhoudt - ook wanneer een andere poort, zoals een open raam, de zone
        nog wel stilhoudt. Een ronde waarin een van de invoeren van die remmen
        geen lezing heeft, laat hem staan; de engine toetst dat met
        `brakes_readable`. De volgende dag en een onbekende zone vervallen
        altijd. De rest van de wereld verandert niet.

        Sleep, an empty house and the next day are the three exits that have
        nothing to do with a gate. Beside those, a hand start lapses in the first
        readable round in which none of the three brakes still holds the zone -
        even when another gate, such as an open window, still silences it. A
        round in which one of the brake inputs has no reading leaves it
        standing; the engine checks that with `brakes_readable`. The next day and
        an unknown zone always lapse. The rest of the world does not change.
        """
        residents = world.residents
        previous = self.data
        expired: list[str] = []
        readable = hand_start.brakes_readable(self.config, world)
        if readable and (
            self.everyone_asleep(world.now, residents) or self.house_is_empty(residents)
        ):
            expired = list(self._hand_starts)
        else:
            for zone_id, started in self._hand_starts.items():
                zone = self.config.zone(zone_id)
                if (
                    zone is None
                    or started.date() != world.now.date()
                    or (readable and not brakes_remaining(self.config, world, zone, previous))
                ):
                    expired.append(zone_id)
        if expired:
            for zone_id in expired:
                self._hand_starts.pop(zone_id, None)
            self.async_save_state()
        return replace(world, zone_hand_starts=frozenset(self._hand_starts))
