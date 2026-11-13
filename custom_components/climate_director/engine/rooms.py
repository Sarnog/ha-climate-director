"""De ruimte en haar poortkeuze. / The room and its gate choice."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum

from .equipment import ModeSettings, Source
from .families import ModeFamily
from .windows import TimeWindow


class ZoneGate(StrEnum):
    """What decides whether a zone may run at all.

    Niet elke ruimte hoort aan hetzelfde touwtje. Een woonkamer volgt het ritme
    van het huishouden, een zolderkamer volgt of er iemand zit. Dat verschil is
    een eigenschap van de ruimte, geen uitzondering in de logica.

    Not every room hangs on the same string. A living room follows the rhythm of
    the household, an attic room follows whether somebody is sitting in it. That
    difference is a property of the room, not an exception in the logic.
    """

    HOUSEHOLD = "household"
    """The household gates decide: somebody home, awake, inside the schedule.

    A presence sensor on the zone still narrows this further: being home says
    nothing about whether anybody is in the attic.
    """

    PRESENCE = "presence"
    """The room's own presence sensor decides, on its own.

    Somebody sitting in the room is a better answer than any schedule could
    give, so the household gates step aside entirely. The master switch, a
    manual override and an open window still apply: those are not about people.
    """


@dataclass(frozen=True, slots=True)
class Zone:
    """A room, with the sources able to serve it and the comfort it aims for."""

    zone_id: str
    name: str
    indoor_sensor: str
    sources: tuple[Source, ...] = ()
    priority: int = 0
    """Weight in circuit conflicts; the lowest number wins."""

    heat: ModeSettings | None = None
    cool: ModeSettings | None = None

    gate: ZoneGate = ZoneGate.HOUSEHOLD
    """What decides whether this zone may run: the household, or the room.

    `PRESENCE` lets an occupied room overrule the schedule, which is what a room
    somebody only uses now and then needs. It requires a `presence_entity`:
    without one there is nothing left to decide with.
    """

    presence_entity: str = ""
    """Entity saying whether this room is occupied. Empty means never checked.

    Distinct from the installation-wide occupancy gate: somebody being home
    says nothing about whether they are in the attic. A room nobody sits in is
    a room worth leaving alone, however awake the household is.
    """

    presence_state: str = "on"
    """The `presence_entity` state that means occupied."""

    presence_timeout: timedelta = timedelta(0)
    """How long the room still counts as occupied after presence drops.

    Presence sensors flicker, and a zone that stops the moment somebody sits
    still would cycle its compressor for no reason. Zero means react at once.
    """

    ignore_precipitation: bool = False
    cost_control: bool = True
    """Whether this zone follows the cost choice between gas and electric."""
    cold_limit: float | None = None
    """An own cold limit for this zone; `None` follows the house's."""
    """Whether this zone keeps its outdoor window even during precipitation.

    Een zolder zonder ramen heeft niets aan de "zet een raam open"-regel, dus
    daar mag neerslag de buitengrens niet opzij zetten.

    An attic without windows gains nothing from the "open a window" rule, so
    there precipitation must not set the outdoor bound aside.
    """

    def settings_for(self, family: ModeFamily) -> ModeSettings | None:
        """Return the settings for `family`, or `None` if the zone forbids it."""
        if family is ModeFamily.HEAT:
            return self.heat
        if family is ModeFamily.COOL:
            return self.cool
        return None


@dataclass(frozen=True, slots=True)
class GateSettings:
    """Which conditions must hold before the director regulates at all."""

    require_awake: bool = True
    """Someone home must also be awake."""

    require_schedule: bool = False
    """Someone's schedule window must be open."""

    quiet_windows: tuple[TimeWindow, ...] = ()
    """Hours in which the director may not start anything of its own accord.

    Thuiskomen om elf uur 's avonds terwijl je zo naar bed gaat, hoeft het huis
    niet te laten opstoken. Binnen deze vensters begint de director dus niets
    uit zichzelf. Wat al draait blijft gewoon geregeld, en zet je zelf iets aan,
    dan pakt hij dat op en regelt door - het is een rem op beginnen, niet op
    doorgaan. Leeg laten zet de rem uit.

    Coming home at eleven at night when you are about to turn in need not fire
    the boiler. Inside these windows the director therefore starts nothing of its
    own accord. Whatever already runs stays regulated, and if you switch
    something on yourself it is picked up and carried on - this is a brake on
    starting, not on continuing. Leaving it empty releases the brake.
    """

    max_precondition: timedelta = timedelta(hours=2)
    """Longest a single request may last, however long somebody asks for.

    A request cannot be forgotten, only mistyped - so the ceiling is what keeps
    a slip of the thumb from becoming an afternoon of heating an empty house.
    """

    guest_window: TimeWindow | None = None
    """Hours in which guest mode carries the house. `None` means all day.

    Guest mode stands in for people the integration cannot see, and people are
    only unaccounted for while they are up. Outside these hours the ordinary
    gates take over again.
    """

    guest_window_incomplete: bool = False
    """Whether only one end of the guest window was filled in.

    Niet bewaard en niet gebruikt door de poorten: `serialise.py` zet dit uit
    de ruwe opslag, en `validate()` meldt het. Zonder deze vlag zou een half
    venster stil als "de hele dag" lezen en was er niets te melden.

    Not stored and not used by the gates: `serialise.py` sets it from the raw
    store, and `validate()` reports it. Without this flag a half window would
    quietly read as "all day" and there would be nothing to report.
    """
