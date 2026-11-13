"""Het volgen van één bewoner: thuis, slapend, thuiskomst en leesbaarheid.

Following one resident: home, asleep, homecoming and readability.

`_resident` en `notice_home` stonden in `world_builder.py` en `coordinator.py`,
maar die modules zijn boven de vijfhonderd regels en dit onderwerp hoort op
zichzelf. Het herstel van het thuiskomstmoment na een herstart (`restore_home_since`)
hoort er ook bij. De leesbaarheid van de aanwezigheids- en slaapsensor gaat mee: de
engine beslist wat een onleesbare invoer voor de drie wachtrema's betekent.

`_resident` and `notice_home` lived in `world_builder.py` and `coordinator.py`,
but those modules are over five hundred lines and this subject belongs on its
own. Restoring the homecoming moment after a restart (`restore_home_since`) belongs
here too. The readability of the presence and sleep sensor travels with it: the
engine decides what an unreadable input means for the three waiting brakes.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime

from homeassistant.core import Event, EventStateChangedData, callback

from .coordinator_surface import CoordinatorSurface
from .engine import ResidentState
from .readability import unreadable
from .world_builder import reads_as_home


def restore_home_since(
    host: CoordinatorSurface, stored: object, parse: Callable[[object], datetime | None]
) -> dict[str, datetime]:
    """Return the homecoming moments to restore, keeping one that is unreadable right now.

    Een opgeslagen moment komt terug als de bewoner thuis is, maar ook als zijn
    aanwezigheidsentiteit ontbreekt of `unavailable`/`unknown` meldt: een
    ontbrekende lezing is geen vertrek. Alleen een leesbare stand die niet thuis
    betekent laat het moment vallen. De opslag geeft zijn eigen lezer van een
    opgeslagen moment mee (`parse`), zodat het bestandsformaat zijn zaak blijft. Het
    staat hier en niet in `state_store.py`: het gaat over het thuiskomstmoment van een
    bewoner, en die module is al boven de vijfhonderd regels.

    A stored moment comes back when the resident is home, but also when their
    presence entity is missing or reports `unavailable`/`unknown`: a missing
    reading is no departure. Only a readable state that does not mean home lets
    the moment lapse. It lives here and not in `state_store.py`: it is about a
    resident's homecoming moment, and that module is already over five hundred
    lines. The store hands over its own reader of a stored moment (`parse`), so the
    format of the file stays the store's business.
    """
    restored: dict[str, datetime] = {}
    if not isinstance(stored, Mapping):
        return restored
    for resident in host.config.residents:
        since = parse(stored.get(resident.resident_id))
        if since is None:
            continue
        state = host.hass.states.get(resident.presence_entity)
        if state is not None and not reads_as_home(state) and not unreadable(state.state):
            continue
        restored[resident.resident_id] = since
    return restored


class ResidentReaderMixin(CoordinatorSurface):
    """De lezer van één bewoner: thuis, slapend en het thuiskomstmoment.

    De leesbaarheid van de sensoren woont in `readability.py`, bij de wereld:
    zij geldt voor meer invoeren dan alleen die van deze bewoner.

    One resident's reader: home, asleep and the homecoming moment. The sensors'
    readability lives in `readability.py`, beside the world: it covers more
    inputs than this resident's alone.
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

        Het moment komt uit de boekhouding van de coördinator (`home_since`),
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

        The moment comes from the coordinator's bookkeeping (`home_since`),
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
        """
        state = self.hass.states.get(presence) if presence else None
        home = reads_as_home(state)
        home_since = self.home_since.get(resident_id) if home else None

        asleep = False
        sleeper = self.hass.states.get(sleep) if sleep else None
        if sleeper is not None and sleeper.state == asleep_state:
            asleep = home_since is None or sleeper.last_changed >= home_since

        return ResidentState(home=home, asleep=asleep, home_since=home_since)

    @callback
    def notice_home(self, event: Event[EventStateChangedData]) -> None:
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
                if resident.resident_id not in self.home_since and not reads_as_home(old_state):
                    self.home_since[resident.resident_id] = new_state.last_changed
                    changed = True
            elif (
                new_state is not None
                and not unreadable(new_state.state)
                and self.home_since.pop(resident.resident_id, None) is not None
            ):
                changed = True
        if changed:
            self.async_save_state()
