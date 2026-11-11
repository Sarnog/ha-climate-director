"""De hand aan het apparaat: wat iemand zelf doet, en wanneer dat vervalt.

The hand at the appliance: what somebody does themselves, and when it lapses.
"""

from __future__ import annotations

from datetime import date, datetime

from .coordinator_surface import CoordinatorSurface
from .engine import ResidentState
from .engine.night import asleep_at


class HandMixin(CoordinatorSurface):
    """Zones van een apparaat, de hand van vandaag, slapen en een leeg huis.

    Zones of an appliance, today's hand, sleep and an empty house.
    """

    _handed_back: dict[str, date]

    def zones_of(self, entity_id: str) -> tuple[str, ...]:
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

    def zones_handed_back(self, now: datetime, residents: dict[str, ResidentState]) -> set[str]:
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
        if self.everyone_asleep(now, residents) or self.house_is_empty(residents):
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

    def everyone_asleep(self, now: datetime, residents: dict[str, ResidentState]) -> bool:
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

    def house_is_empty(self, residents: dict[str, ResidentState]) -> bool:
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
