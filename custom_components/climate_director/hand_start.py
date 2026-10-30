"""De handstart: iemand zet zelf een apparaat aan terwijl zijn zone wacht.

The hand start: somebody switches an appliance on themselves while its zone waits.

Een handstart is géén hand. Een hand zet een apparaat uit en valt stil tot
dezelfde hand, het slapen, een leeg huis of de volgende dag; een handstart zet
een zone aan en laat alleen `WAITING_FOR_SLEEPER`, `EARLY_RISER` en
`QUIET_HOURS` passeren. De knop per zone en een actieve stand die niet van de
director komt zetten dezelfde notitie. De coordinator bewaart haar over een
herstart en laat haar vallen zodra geen van die drie remmen de zone nog
tegenhoudt, of bij slapen, een leeg huis of de volgende dag.

A hand start is not a hand. A hand switches an appliance off and stays silent
until the same hand, sleep, an empty house or the next day; a hand start switches
a zone on and lets only `WAITING_FOR_SLEEPER`, `EARLY_RISER` and `QUIET_HOURS`
pass. The per-zone button and an active mode that does not come from the
director make the same note. The coordinator keeps it across a restart and drops
it as soon as none of those three brakes still holds the zone, or on sleep, an
empty house or the next day.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from homeassistant.core import Event, EventStateChangedData, callback
from homeassistant.util import dt as dt_util

from .engine import ModeFamily, Plan, ResidentState, WorldState, family_of, hand_start
from .engine.night import asleep_at
from .state_store import _stored_time
from .world_builder import _unreadable

if TYPE_CHECKING:
    from .coordinator import CoordinatorSurface

    # De mixin ligt op de coördinator maar erft er niet van: de coördinator erft
    # van hém. Voor mypy is dit de gastheer, zodat `self.config` en de rest
    # kloppen; buiten de typecontrole is de basis gewoon `object`.
    #
    # The mixin sits on the coordinator but does not inherit from it: the
    # coordinator inherits from the mixin. For mypy this is the host, so
    # `self.config` and the rest resolve; outside the type check the base is
    # simply `object`.
    _CoordinatorBase = CoordinatorSurface
else:
    _CoordinatorBase = object


class _HandStartMixin(_CoordinatorBase):
    """Herkenning, opslag en verval van een handstart.

    Recognition, storage and expiry of a hand start.
    """

    _handed_back: dict[str, date]

    def _published_plan(self) -> Plan | None:
        """Return the last published plan, which the protocol does not declare.

        `DataUpdateCoordinator` draagt `data` als eigenschap; het protocol van de
        mixins hoeft die eigenschap niet te herhalen. Deze ene lezer houdt de
        uitzondering bij één plek in plaats van in elke methode.

        `DataUpdateCoordinator` carries `data` as a property; the mixins'
        protocol need not repeat that property. This one reader keeps the
        exception in one place instead of in every method.
        """
        return getattr(self, "data", None)

    @callback
    def _notice_hand_start(self, event: Event[EventStateChangedData]) -> None:
        """Record an appliance somebody switched on while a zone was waiting.

        Alleen een actieve stand die niet van ons komt telt. `_we_wanted_it_on`
        verklaart onze eigen aanzet, ook wanneer het apparaat die pas een poll
        later meldt; die late melding mag geen handstart worden. Een bron met
        *Dit apparaat automatisch aanzetten* uit telt niet, en een gedeeld
        apparaat start elke zone die het bedient - inclusief de zones uit
        `covers_zones`. Staat er geen enkele zone op een wachtreden, dan doet
        de gebeurtenis niets.

        Only an active mode that does not come from us counts. `_we_wanted_it_on`
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
        if _unreadable(old_state.state) or _unreadable(new_state.state):
            return

        duty = family_of(new_state.state)
        if duty is ModeFamily.NEUTRAL or family_of(old_state.state) is duty:
            return

        entity_id = event.data["entity_id"]
        if self._we_wanted_it_on(entity_id, duty):
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
        if not hand_start.brakes_remaining(
            self.config, self.build_world(), zone, self._published_plan()
        ):
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
            self._async_save_state()
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
        plan = self._published_plan()
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
            moment = _stored_time(value)
            if moment is not None and moment.date() == today:
                self._hand_starts[zone_id] = moment

    def _settle_hand_starts(self, world: WorldState) -> WorldState:
        """Drop the hand starts that no longer do anything, and hand the world theirs.

        Slapen, een leeg huis en de volgende dag zijn de drie uitwegen die niets
        met een poort te maken hebben. Daarnaast vervalt een handstart in de
        eerste ronde waarin geen van de drie remmen de zone nog tegenhoudt - ook
        wanneer een andere poort, zoals een open raam, de zone nog wel stilhoudt.
        De rest van de wereld verandert niet.

        Sleep, an empty house and the next day are the three exits that have
        nothing to do with a gate. Beside those, a hand start lapses in the first
        round in which none of the three brakes still holds the zone - even when
        another gate, such as an open window, still silences it. The rest of the
        world does not change.
        """
        residents = world.residents
        previous = self._published_plan()
        expired: list[str] = []
        if self._everyone_asleep(world.now, residents) or self._house_is_empty(residents):
            expired = list(self._hand_starts)
        else:
            for zone_id, started in self._hand_starts.items():
                zone = self.config.zone(zone_id)
                if (
                    zone is None
                    or started.date() != world.now.date()
                    or not hand_start.brakes_remaining(self.config, world, zone, previous)
                ):
                    expired.append(zone_id)
        if expired:
            for zone_id in expired:
                self._hand_starts.pop(zone_id, None)
            self._async_save_state()
        return replace(world, zone_hand_starts=frozenset(self._hand_starts))

    def _zones_of(self, entity_id: str) -> tuple[str, ...]:
        """Return every zone this climate entity serves, if the director drives it.

        Een gedeelde ketel staat onder meer dan één zone. Iemand die bij zo'n
        apparaat zelf op uit drukt zegt iets over dat apparaat, niet over de
        eerste zone die het toevallig bedient - dus elke zone die eraan hangt
        hoort stil te vallen, anders zet de overgeslagen zone het apparaat meteen
        weer aan. Een generator staat niet tussen de bronnen maar bedient
        dezelfde zones; ook die hoort mee te tellen, anders wordt een hand aan de
        gedeelde ketel nooit opgemerkt.

        A shared boiler sits under more than one zone. Somebody pressing off on
        such an appliance says something about the appliance, not about whichever
        zone happens to be listed first - so every zone hanging off it should fall
        silent, otherwise the skipped zone switches it straight back on. A
        generator is not listed among the sources but serves the same zones; it
        has to count too, otherwise a hand at the shared boiler is never noticed.
        """
        zones = [
            zone.zone_id for zone, source in self.config.sources() if source.entity_id == entity_id
        ]
        for generator in self.config.generators:
            if generator.entity_id != entity_id:
                continue
            zones.extend(
                zone.zone_id
                for zone in self.config.zones
                if generator.serves(zone.zone_id) and zone.zone_id not in zones
            )
        return tuple(zones)

    def _zones_handed_back(self, now: datetime, residents: dict[str, ResidentState]) -> set[str]:
        """Return the zones a hand stood down today, forgetting yesterday's.

        De datum is de hele vervaltermijn. Wie gisteravond de slaapkamer uitzette
        wil vanochtend niet dat hij nog steeds stilstaat, en een teller van
        vierentwintig uur zou dat wel doen.

        Dit gaat alleen over de hand aan het apparaat. De overrideschakelaar
        staat daar los van en blijft staan tot iemand hem zelf uitzet: dat is
        geen besluit van vanavond maar een besluit dat je terugdraait. Ze werden
        hier allebei weggegooid, waardoor een zone die je met opzet had
        overgedragen de eerste nacht alweer meedeed.

        The date is the whole expiry. Whoever switched the bedroom off last night
        does not want it still standing still this morning, and a twenty-four
        hour timer would do exactly that.

        This is only about the hand at the appliance. The override switch stands
        apart from it and holds until somebody turns it off themselves: that is
        not tonight's decision but one you undo. Both were thrown away here, so a
        zone deliberately handed over rejoined on the first night.
        """
        if self._everyone_asleep(now, residents) or self._house_is_empty(residents):
            if self._handed_back:
                self._handed_back.clear()
                self._async_save_state()
            return set()

        today = now.date()
        kept = {zone: day for zone, day in self._handed_back.items() if day == today}
        if kept != self._handed_back:
            self._handed_back = kept
            self._async_save_state()
        return set(self._handed_back)

    def _everyone_asleep(self, now: datetime, residents: dict[str, ResidentState]) -> bool:
        """Return whether everybody who is home has turned in.

        Dan is de dag voorbij en hoort een zone die iemand met de hand stilzette
        weer mee te doen - precies zoals de automatiseringen het deden. Wachten
        tot middernacht zou de zone een paar uur langer stil houden dan iemand
        bedoelde, en dat merk je pas de volgende ochtend.

        Het slaapvenster telt hier net zo hard als in de engine: buiten die uren
        is een oplader gewoon een oplader, en is de dag niet voorbij.

        The day is then over, and a zone somebody silenced by hand should join in
        again - exactly as the automations did it. Waiting for midnight would
        hold the zone still a few hours longer than anybody meant, and you only
        notice that the next morning.

        The sleep window counts here exactly as it does in the engine: outside
        those hours a charger is just a charger, and the day is not over.
        """
        at_home = [
            resident
            for resident in self.config.residents
            if resident.presence_entity and residents[resident.resident_id].home
        ]
        if not at_home:
            return False
        return all(
            bool(resident.sleep_entity)
            and asleep_at(
                resident,
                residents[resident.resident_id].asleep,
                now,
                holiday=self.holiday_mode or self._calendar_says_holiday(),
            )
            for resident in at_home
        )

    def _house_is_empty(self, residents: dict[str, ResidentState]) -> bool:
        """Return whether none of the tracked residents is home.

        Wie een apparaat met de hand uitzette deed dat voor de kamer waar hij op
        dat moment in zat. Is er niemand meer, dan is dat geval voorbij, en
        niets is zo vervelend als thuiskomen in een kamer die al dagen stilstaat
        omdat er ooit iemand op uit heeft gedrukt.

        Whoever switched an appliance off by hand did that for the room they were
        sitting in at the time. With nobody left, that case is over - and nothing
        is as annoying as coming home to a room that has stood still for days
        because somebody once pressed off.
        """
        tracked = [resident for resident in self.config.residents if resident.presence_entity]
        if not tracked:
            return False
        return not any(residents[resident.resident_id].home for resident in tracked)
