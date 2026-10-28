"""De kamerpoort: wanneer een kamer bezet telt en wanneer haar nalooptijd begint.

The room gate: when a room counts as occupied and when its grace period starts.

Een aanwezigheidssensor zegt alleen iets op het moment dat hij leest. Wegvallen
is geen bewijs van leegte, maar ook geen bewijs van aanwezigheid: een kamer die
bezet was en onleesbaar wordt, kan net leeg zijn geraakt. Daarom telt dat
wegvallen als vertrek, en beslist de teruggekeerde sensor daarna. Wat de kamer
was en wanneer zij leeg werd, staat in de opslag, zodat de nalooptijd een
herstart overleeft.

A presence sensor only says something at the moment it reads. Dropping out is no
proof of emptiness, but neither is it proof of presence: a room that was
occupied and turns unreadable may just have become empty. The drop-out therefore
counts as a departure, and the returning sensor decides after that. What the
room was and when it became empty live in the store, so the grace period
survives a restart.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.core import Event, EventStateChangedData, callback
from homeassistant.util import dt as dt_util

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


class _RoomPresenceMixin(_CoordinatorBase):
    """De bezetting van een kamer en de nalooptijd die eraan hangt.

    The occupancy of a room and the grace period hanging off it.
    """

    @callback
    def _notice_room_empty(self, event: Event[EventStateChangedData]) -> None:
        """Record the moment a room really became empty or dropped out.

        De nalooptijd van een kamer begint bij een **vertrek**: een overgang van
        bezet naar niet-bezet, en ook een overgang van bezet naar `unavailable`
        of `unknown`. Dat laatste is geen leesbare leegte, maar een bezette
        kamer die onleesbaar wordt kan net leeg zijn geraakt; de teruggekeerde
        sensor beslist daarna. Alleen een kamer die op dat moment als bezet
        bekendstaat begint de nalooptijd - een sensor die al onleesbaar was en
        daarna `off` meldt, laat het bewaarde moment staan en krijgt dus geen
        verse nalooptijd.

        Het moment is `last_changed` van de entiteit zelf, precies zoals bij
        `_notice_home`: dat is het moment van de overgang, en het is dezelfde
        tijdbasis die de lezer vroeger las. Verdwijnt de entiteit zelf, dan is er
        geen `last_changed` en neemt de coordinator het moment van de melding.
        Komt de kamer weer bezet, dan gaat het moment weg. De verzameling
        bezette kamers gaat mee de opslag in, zodat een herstart weet of een
        kamer die nog onleesbaar is bezet was.

        The room's grace period starts at a **departure**: a transition from
        occupied to not occupied, and also a transition from occupied to
        `unavailable` or `unknown`. The latter is no readable emptiness, but a
        room that was occupied and turns unreadable may just have become empty;
        the returning sensor decides after that. Only a room known to be
        occupied at that moment starts the grace period - a sensor that was
        already unreadable and then reports `off` leaves the stored moment
        standing and therefore gets no fresh grace period.

        The moment is the entity's own `last_changed`, exactly as in
        `_notice_home`: that is the moment of the transition, and it is the same
        time base the reader used before. When the entity itself disappears
        there is no `last_changed`, and the coordinator takes the moment of the
        report. When the room becomes occupied again the moment goes. The set of
        occupied rooms travels to the store with it, so a restart knows whether
        a room that is still unreadable was occupied.
        """
        old_state = event.data["old_state"]
        new_state = event.data["new_state"]
        if old_state is None and new_state is None:
            return

        entity_id = event.data["entity_id"]
        changed = False
        for zone in self.config.zones:
            if zone.presence_entity != entity_id:
                continue
            if new_state is not None and new_state.state == zone.presence_state:
                if zone.zone_id not in self._occupied_rooms:
                    self._occupied_rooms.add(zone.zone_id)
                    changed = True
                if self._empty_since.pop(zone.zone_id, None) is not None:
                    changed = True
                continue

            # Een kamer die al onleesbaar was en nu leesbaar leeg wordt, is geen
            # nieuw vertrek: het bewaarde moment blijft staan.
            #
            # A room that was already unreadable and now reads empty gets no new
            # departure: the stored moment stays.
            was_occupied = (
                old_state is not None and old_state.state == zone.presence_state
            ) or zone.zone_id in self._occupied_rooms
            if zone.zone_id in self._occupied_rooms:
                self._occupied_rooms.discard(zone.zone_id)
                changed = True
            if not was_occupied:
                continue
            moment = new_state.last_changed if new_state is not None else dt_util.now()
            if self._empty_since.get(zone.zone_id) != moment:
                self._empty_since[zone.zone_id] = moment
                changed = True

        if changed:
            self._async_save_state()

    def _room_presence_payload(self) -> dict[str, Any]:
        """Return what the store needs to know about the room gate.

        Het vertrekmoment per zone en de kamers die op dit moment als bezet
        bekendstaan. Beide zijn kamerdata: het moment zegt wanneer een kamer leeg
        raakte, en de verzameling zegt waar iemand zat. De diagnose neemt ze niet
        als los veld op; zou dat ooit gebeuren, dan vallen ze onder dezelfde
        weglakking als de rest van de aanwezigheid.

        The departure moment per zone and the rooms currently known to be
        occupied. Both are room data: the moment says when a room became empty,
        and the set says where somebody was sitting. Diagnostics do not include
        them as separate fields; if that ever changes, they fall under the same
        redaction as the rest of the presence data.
        """
        return {
            "empty_since": {
                zone_id: moment.isoformat() for zone_id, moment in self._empty_since.items()
            },
            "occupied_rooms": sorted(self._occupied_rooms),
        }

    def _restore_room_presence(self, stored: Mapping[str, Any], now: datetime) -> None:
        """Restore the room gate after a restart.

        De opslag onthoudt welke kamers bezet waren en wanneer een kamer leeg
        werd. Is een kamer bij het herstel nog onleesbaar terwijl zij bezet was,
        dan begint haar nalooptijd op het herstelmoment: de sensor is niet terug,
        dus over het vertrek valt niets te zeggen. Is zij inmiddels leesbaar
        leeg, dan geldt het bewaarde vertrekmoment. Een ouder bestand zonder
        `occupied_rooms` levert geen bezette kamer op; een nog onleesbare kamer
        telt dan als leeg. Dat is de onschadelijke kant - een lege kamer met rust
        laten - en daarom hoeft de opslagversie niet omhoog voor een sleutel die
        er nooit was.

        Een moment dat tijdens het opstarten al door een echte toestandswijziging
        genoteerd is, blijft staan: het herstel voegt samen en vervangt niet.

        The store remembers which rooms were occupied and when a room became
        empty. If a room is still unreadable at the restore while it was
        occupied, its grace period starts at the restore moment: the sensor is
        not back, so nothing can be said about the departure. If it reads empty
        by now, the stored departure moment applies. An older file without
        `occupied_rooms` yields no occupied room; a still unreadable room then
        counts as empty. That is the harmless side - leaving an empty room alone
        - and therefore the storage version need not rise for a key that was
        never there.

        A moment already noted during the startup by a real state change stays
        put: the restore merges rather than replaces.
        """
        rooms = {zone.zone_id: zone for zone in self.config.zones if zone.presence_entity}
        occupied_raw = stored.get("occupied_rooms")
        occupied = (
            {zone_id for zone_id in occupied_raw if isinstance(zone_id, str) and zone_id in rooms}
            if isinstance(occupied_raw, list | tuple | set | frozenset)
            else set()
        )
        empty_raw = stored.get("empty_since")
        empty: dict[str, datetime] = {}
        if isinstance(empty_raw, Mapping):
            for zone_id, raw in empty_raw.items():
                if zone_id not in rooms:
                    continue
                moment = _stored_time(raw)
                if moment is not None:
                    empty[zone_id] = moment

        before = (dict(self._empty_since), set(self._occupied_rooms))
        live_empty = set(self._empty_since)
        self._occupied_rooms.clear()
        for zone_id, zone in rooms.items():
            current = self.hass.states.get(zone.presence_entity)
            if current is not None and current.state == zone.presence_state:
                self._occupied_rooms.add(zone_id)
                self._empty_since.pop(zone_id, None)
                continue
            if zone_id in live_empty:
                continue
            if (current is None or _unreadable(current.state)) and zone_id in occupied:
                self._empty_since[zone_id] = now
            elif zone_id in empty:
                self._empty_since[zone_id] = empty[zone_id]
            else:
                self._empty_since.pop(zone_id, None)
        for zone_id in [zone_id for zone_id in self._empty_since if zone_id not in rooms]:
            self._empty_since.pop(zone_id, None)

        if (self._empty_since, self._occupied_rooms) != before:
            self._async_save_state()

    def _note_room_presence_now(self) -> None:
        """Seed the occupied rooms from the states read at the startup.

        Zonder deze stap kent de coordinator na een eerste start alleen kamers
        die daarna nog van toestand veranderen; een kamer die de hele tijd bezet
        bleef, zou dan niet in de opslag komen en na een herstart met een
        onleesbare sensor als leeg tellen.

        Without this step the coordinator knows only rooms that change state
        after a first start; a room that stayed occupied all along would not
        enter the store and would count as empty after a restart with an
        unreadable sensor.
        """
        occupied = {
            zone.zone_id
            for zone in self.config.zones
            if zone.presence_entity
            and (state := self.hass.states.get(zone.presence_entity)) is not None
            and state.state == zone.presence_state
        }
        changed = occupied != self._occupied_rooms
        self._occupied_rooms.clear()
        self._occupied_rooms.update(occupied)
        for zone_id in occupied & self._empty_since.keys():
            self._empty_since.pop(zone_id, None)
            changed = True
        if changed:
            self._async_save_state()
