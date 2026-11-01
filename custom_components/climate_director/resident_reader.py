"""Het volgen van één bewoner: thuis, slapend, thuiskomst en leesbaarheid.

Following one resident: home, asleep, homecoming and readability.

`_resident` en `_notice_home` stonden in `world_builder.py` en `coordinator.py`,
maar die modules zijn boven de vijfhonderd regels en dit onderwerp hoort op
zichzelf. De leesbaarheid van de aanwezigheids- en slaapsensor gaat mee: de
engine beslist wat een onleesbare invoer voor de drie wachtrema's betekent.

`_resident` and `_notice_home` lived in `world_builder.py` and `coordinator.py`,
but those modules are over five hundred lines and this subject belongs on its
own. The readability of the presence and sleep sensor travels with it: the
engine decides what an unreadable input means for the three waiting brakes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import Event, EventStateChangedData, callback

from .engine import ResidentState
from .world_builder import _unreadable, reads_as_home

if TYPE_CHECKING:
    from .coordinator import CoordinatorSurface

    # De mixin ligt op de coördinator maar erft er niet van: de coördinator erft
    # van hém. Voor mypy is dit de gastheer, zodat `self.hass` en de rest
    # kloppen; buiten de typecontrole is de basis gewoon `object`.
    #
    # The mixin sits on the coordinator but does not inherit from it: the
    # coordinator inherits from the mixin. For mypy this is the host, so
    # `self.hass` and the rest resolve; outside the type check the base is
    # simply `object`.
    _CoordinatorBase = CoordinatorSurface
else:
    _CoordinatorBase = object


class _ResidentReaderMixin(_CoordinatorBase):
    """De lezer van één bewoner, met de leesbaarheid van zijn twee sensoren.

    One resident's reader, with the readability of their two sensors.
    """

    def _resident(
        self, resident_id: str, presence: str, sleep: str, asleep_state: str
    ) -> ResidentState:
        """Return one resident's state, with a stale sleep reading ignored.

        Opstaan en thuiskomen zijn twee verschillende dingen, en de slaapsensor
        kent alleen het eerste. "Telefoon op de draadloze lader" zegt iets over
        iemand die de hele tijd thuis was; wie binnenkomt met zijn telefoon nog
        aan de lader in de auto, is klaarwakker. Die melding is ouder dan de
        thuiskomst en zegt dus niets over nu.

        Daarom telt een slaapmelding alleen als hij van ná de thuiskomst is.
        Legt iemand zijn telefoon thuis opnieuw op de lader, dan is dat een
        verse melding en telt hij gewoon weer. Bij gelijke tijdstempels - na een
        herstart krijgt alles hetzelfde moment - telt de melding wél, want
        opschorten is de onschadelijke kant om fout te zitten.

        Het moment komt uit de boekhouding van de coördinator (`_home_since`),
        die een herstart overleeft en bij een terugval op
        `last_changed` van de aanwezigheidsentiteit begint. Deze lezer schrijft
        daar nooit in: de wereld lezen en de wereld veranderen zijn twee dingen.
        Eén gevolg hoort opgeschreven: een bewoner die thuis is zonder bekend
        moment leest als *slapend* zodra zijn slaapsensor dat zegt. Dat is
        dezelfde uitkomst als zonder die boekhouding - daar was het moment het
        tijdstempel van de aanwezigheidsentiteit, en bij gelijke tijdstempels
        telt de melding - en het is de onschadelijke kant: opschorten remt.

        Belangrijker voor het stiltevenster: na een herstart met een opgeslagen
        moment is `sleeper.last_changed` (het herstartmoment) nieuwer dan dat
        moment, dus de slaapmelding telt gewoon.

        De leesbaarheidsvlaggen gaan mee: ontbrekend, `unavailable` en `unknown`
        zijn geen lezing, iedere andere stand wel; zonder entiteit blijven ze waar.

        Getting up and coming home are two different things, and the sleep
        sensor knows only the first. "Phone on the wireless charger" says
        something about somebody who was home all along; whoever walks in with
        their phone still on the car charger is wide awake. That reading is
        older than the arrival and therefore says nothing about now.

        So a sleep reading only counts when it postdates the arrival. Put the
        phone back on the charger at home and that is a fresh reading, counting
        as before. On equal timestamps - after a restart everything carries the
        same moment - the reading does count, since suspending is the harmless
        direction to be wrong in.

        The moment comes from the coordinator's bookkeeping (`_home_since`),
        which survives a restart and starts as a fallback on the presence
        entity's `last_changed`. This reader never writes there: reading the
        world and changing the world are two different things. One
        consequence belongs on paper: a resident who is home without a known
        moment reads as *asleep* whenever their sleep sensor says so. That is the
        same outcome as without that bookkeeping - there the moment was the
        presence entity's timestamp, and on equal timestamps the reading counts -
        and it is the harmless direction: suspending brakes.

        More important for the quiet window: after a restart with a stored
        moment `sleeper.last_changed` (the restart moment) is newer than that
        moment, so the sleep reading simply counts.

        The readability flags travel along: missing, `unavailable` and `unknown`
        are no reading, every other state is; without an entity they stay true.
        """
        state = self.hass.states.get(presence) if presence else None
        home = reads_as_home(state)
        home_since = self._home_since.get(resident_id) if home else None

        asleep = False
        sleeper = self.hass.states.get(sleep) if sleep else None
        if sleeper is not None and sleeper.state == asleep_state:
            asleep = home_since is None or sleeper.last_changed >= home_since

        return ResidentState(
            home=home,
            asleep=asleep,
            home_since=home_since,
            presence_readable=not presence or (state is not None and not _unreadable(state.state)),
            sleep_readable=not sleep or (sleeper is not None and not _unreadable(sleeper.state)),
        )

    @callback
    def _notice_home(self, event: Event[EventStateChangedData]) -> None:
        """Record when a resident comes home, and forget it when they leave.

        Anker 13: het moment waarop iemand thuiskwam is wat het stiltevenster
        onderscheidt van "er is iemand thuis", en het hoort hier - in de
        toestandswijziging van de aanwezigheidsentiteit zelf, niet in een lezer
        die alleen een antwoord teruggeeft. Alleen een **overgang** telt: iemand
        die thuis is en wiens entiteit opnieuw gemeld wordt (een GPS-sprietje,
        een herstelde stand) is geen thuiskomer, en zou met een vers moment het
        huis de hele nacht laten doorstoken. Wie weggaat verliest zijn moment,
        maar een onleesbare stand (`unavailable`, `unknown` of ontbrekend) is
        geen vertrek: dan blijft het moment staan tot er weer een lezing is.

        Het moment is `last_changed` van de entiteit zelf, niet `dt_util.now()`:
        dat is precies het moment van de overgang, en het is hetzelfde moment dat
        de slaap-vs-thuiskomst-vergelijking al las. Eén tijdbasis voor beide
        lezers.

        Anchor 13: the moment somebody came home is what separates the quiet
        window from "somebody is home", and it belongs here - in the presence
        entity's own state change, not in a reader that only hands back an answer.
        Only a **transition** counts: somebody who is home and whose entity is
        reported again (GPS jitter, a restored state) is not a homecomer, and a
        fresh moment would let the house keep heating all night. Whoever leaves
        loses their moment, but an unreadable state (`unavailable`, `unknown` or
        missing) is no departure: the moment stays until there is a reading
        again.

        The moment is the entity's own `last_changed`, not `dt_util.now()`: that is
        exactly the moment of the transition, and it is the same moment the
        sleep-versus-homecoming comparison already read. One time base for both
        readers.
        """
        entity_id = event.data["entity_id"]
        old_state = event.data["old_state"]
        new_state = event.data["new_state"]
        changed = False
        # Geen `return` bij de eerste treffer: twee bewoners mogen dezelfde
        # aanwezigheidsentiteit delen (een "is er iemand thuis"-sensor), en dan
        # hoort elk van hen het moment te krijgen. Eén schrijfactie na de lus.
        #
        # No `return` on the first hit: two residents may share one presence entity
        # (an "is anybody home" sensor), and then each of them should get the
        # moment. One write after the loop.
        for resident in self.config.residents:
            if resident.presence_entity != entity_id:
                continue
            # De toets staat met opzet in de `if` en niet in een variabele: `mypy`
            # versmalt een `TypeGuard` alleen daar, en in een variabele blijft het
            # `State | None` - dat is op de bouwserver gemeten (één `union-attr`).
            #
            # The check deliberately sits in the `if` and not in a variable: `mypy`
            # only narrows a `TypeGuard` there, and in a variable it stays
            # `State | None` - measured on the build server (one `union-attr`).
            if reads_as_home(new_state):
                if resident.resident_id not in self._home_since and not reads_as_home(old_state):
                    self._home_since[resident.resident_id] = new_state.last_changed
                    changed = True
            elif (
                new_state is not None
                and not _unreadable(new_state.state)
                and self._home_since.pop(resident.resident_id, None) is not None
            ):
                changed = True
        if changed:
            self._async_save_state()
