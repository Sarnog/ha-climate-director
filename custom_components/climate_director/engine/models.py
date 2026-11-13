"""De installatie als geheel en de namen van haar onderdelen.

The installation as a whole and the names of its parts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from .energy import EnergySettings
from .equipment import (
    Circuit,
    ConflictPolicy,
    Generator,
    HeatingLayout,
    ModeSettings,
    Opening,
    OutdoorWindow,
    Source,
    SourceRole,
)
from .families import ModeFamily
from .residents import Resident, RiseBrake, SleepIn, WakeDeadline
from .rooms import GateSettings, Zone, ZoneGate
from .seasons import (
    HOLIDAY_WEEKDAY,
    QUIET_ROOM_MINUTES,
    PrecipitationSettings,
    Season,
    SeasonSettings,
    SeasonSource,
)
from .windows import TimeWindow

__all__ = [
    "HOLIDAY_WEEKDAY",
    "QUIET_ROOM_MINUTES",
    "Circuit",
    "ConflictPolicy",
    "EnergySettings",
    "GateSettings",
    "Generator",
    "HeatingLayout",
    "ModeFamily",
    "ModeSettings",
    "Opening",
    "OutdoorWindow",
    "PrecipitationSettings",
    "Resident",
    "RiseBrake",
    "Season",
    "SeasonSettings",
    "SeasonSource",
    "SleepIn",
    "Source",
    "SourceRole",
    "TimeWindow",
    "WakeDeadline",
    "Zone",
    "ZoneGate",
]


@dataclass(frozen=True, slots=True)
class DirectorConfig:
    """A whole installation."""

    zones: tuple[Zone, ...] = ()
    circuits: tuple[Circuit, ...] = ()
    residents: tuple[Resident, ...] = ()
    openings: tuple[Opening, ...] = ()

    house_wide_openings: tuple[str, ...] = ()
    """Appliances that stop while any opening in the installation stands open.

    Een opening werkt op zones: raakt hij een zone, dan valt daar alles stil.
    Bij een centraal geregelde verwarming klopt dat niet. De ketel staat als
    bron onder alle zones, en zolang één andere zone warmte vraagt blijft hij
    branden met de deur open, want vraag wint van stilte (`_collapse_shared` in
    `decide.py`). De opening aan álle zones koppelen lost de ketel op, maar zet
    daarmee ook de airco's in die kamers stil - het hele jaar door, terwijl die
    per kamer geregeld horen te worden.

    Deze lijst hangt daarom aan het apparaat en niet aan de opening: dan hoeft
    de ketel niet bij elke deur opnieuw aangevinkt te worden, en telt een raam
    dat er later bij komt vanzelf mee. Leeg is het gedrag van vóór deze
    instelling, dus een gezoneerde cv blijft gewoon per zone geregeld.

    An opening acts on zones: once it affects a zone, everything there stops.
    For centrally controlled heating that is wrong. The boiler sits as a source
    under every zone, and as long as one other zone asks for heat it keeps
    running with the door open, because demand beats silence (`_collapse_shared`
    in `decide.py`). Linking the opening to *every* zone settles the boiler, but
    it also stops the air conditioners in those rooms - all year round, while
    those belong under per-room control.

    This list therefore hangs on the appliance rather than on the opening: the
    boiler need not be ticked again at every door, and a window added later
    counts by itself. Empty is the behaviour from before this setting, so a
    zoned boiler stays governed per zone.
    """

    generators: tuple[Generator, ...] = ()
    exclusive_groups: tuple[frozenset[str], ...] = ()
    """Source-id groups of which at most one member may run at a time."""

    gates: GateSettings = field(default_factory=GateSettings)
    seasons: SeasonSettings = field(default_factory=SeasonSettings)
    precipitation: PrecipitationSettings = field(default_factory=PrecipitationSettings)
    energy: EnergySettings = field(default_factory=EnergySettings)
    """Prijzen en rendementen voor de kostenvergelijking; hangt aan geen besluit.

    Prices and efficiencies for the cost comparison; no decision hangs on it.
    """

    heating_layout: HeatingLayout = HeatingLayout.PER_ZONE
    """What kind of heating installation this is; see `HeatingLayout`."""

    outdoor_sensor: str = ""
    """Entity carrying the outdoor temperature. Empty leaves it unknown."""

    outdoor_hysteresis: float = 0.5
    """Dead band on every outdoor bound, in degrees.

    Binnen heeft elke zone een dode band, want anders pendelt hij op één getal.
    Buiten was elke grens hard - de grens die de gasketel van de warmtepomp
    scheidt, en de grens die zegt of dit weer verwarmen of koelen toelaat - en
    juist daar schommelt het weer omheen. Een gesimuleerde maand rond de omslag
    van 3,1 graden leverde 296 wisselingen tussen gas en airco op: ruim acht per
    dag, elk een brander die ontsteekt of een compressor die start. De
    kortcyclusbescherming ving daar niets van, want die hangt aan een circuit en
    een gasketel hangt aan geen circuit.

    De band geldt alleen voor wat al draait: die mag doorlopen tot een dode band
    voorbij zijn grens. Wie stilstaat moet de grens gewoon halen, anders zou de
    band de grens alleen maar verschuiven. Nul zet hem uit.

    Indoors every zone has a dead band, since otherwise it chatters on a single
    number. Outdoors every bound was hard - the one separating the boiler from
    the heat pump, and the one saying whether this weather allows heating or
    cooling - and that is exactly what the weather hovers around. A simulated
    month around the 3.1 degree changeover produced 296 swaps between boiler and
    heat pump: over eight a day, each one a burner igniting or a compressor
    starting. Short-cycle protection caught none of it, since that hangs on a
    circuit and a gas boiler hangs on no circuit.

    The band applies only to what already runs: that may carry on until one dead
    band past its bound. Whatever stands still has to reach the bound itself, or
    the band would merely move the bound. Zero switches it off.
    """

    stuck_after: timedelta = timedelta(minutes=15)
    """How long a zone may sit on a waiting reason before it counts as stuck.

    Ruim boven elke pauze die je redelijkerwijs instelt, want een valse melding
    leert je de melder te negeren. Nul zet de melder uit.

    Comfortably above any pause you would reasonably configure, since a false
    alarm teaches you to ignore the alarm. Zero switches it off.
    """

    holiday_calendars: tuple[str, ...] = ()
    """Calendars whose running events may put the house on holiday."""

    holiday_keyword: str = ""
    """Word an event must carry to count.

    Empty switches the calendars off entirely rather than letting every event
    through: a calendar full of dentist appointments is not a holiday calendar,
    and guessing which of its events meant a holiday is not the integration's
    call to make.
    """

    def zone(self, zone_id: str) -> Zone | None:
        """Return the zone with this id, if it exists."""
        return next((zone for zone in self.zones if zone.zone_id == zone_id), None)

    def sources(self) -> tuple[tuple[Zone, Source], ...]:
        """Return every `(zone, source)` pair in the installation."""
        return tuple((zone, source) for zone in self.zones for source in zone.sources)

    def circuit_for_entity(self, entity_id: str) -> Circuit | None:
        """Return the circuit a climate entity sits on, if any.

        An entity on no circuit has an outdoor unit to itself and is therefore
        unconstrained - which is exactly the right default for a single split.
        """
        return next((circuit for circuit in self.circuits if entity_id in circuit.units), None)

    def sources_on(self, circuit: Circuit) -> tuple[tuple[Zone, Source], ...]:
        """Return every managed `(zone, source)` pair sitting on `circuit`."""
        return tuple(
            (zone, source) for zone, source in self.sources() if source.entity_id in circuit.units
        )
