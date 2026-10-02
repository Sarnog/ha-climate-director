"""De eerste beslissing wacht tot Home Assistant is opgestart.

The first decision waits until Home Assistant has started.

Bij het opzetten van de config entry zijn de entiteiten er al, maar Home
Assistant is nog bezig met opstarten: herstelde standen, automatiseringen en
andere integraties komen pas daarna. Een beslissing op dat moment ziet een half
geladen wereld en kan een apparaat uitzetten dat er gewoon hoort te draaien.
Daarom hangt de eerste beoordeling aan `async_at_started`.

When the config entry is set up the entities exist, but Home Assistant is still
starting: restored states, automations and other integrations come only later.
A decision at that moment sees a half-loaded world and can switch off an
appliance that should simply be running. Hence the first evaluation hangs off
`async_at_started`.
"""

from __future__ import annotations

from custom_components.climate_director import coordinator as module
from custom_components.climate_director.coordinator import ClimateDirectorCoordinator


class _Entry:
    def __init__(self) -> None:
        self.unloads: list[object] = []

    def async_on_unload(self, callback) -> None:
        self.unloads.append(callback)


class StandIn:
    def __init__(self) -> None:
        self.hass = object()
        self.name = "stand-in"
        self.config_entry = _Entry()
        self.entry = self.config_entry
        self.restored = 0
        self.evaluated = 0
        self.clock_armed = 0
        self.precipitation_noted = 0
        # De opstartpoort van de echte coördinator; een stand-in draagt hem ook,
        # zodat de toets hem kan volgen.
        # The real coordinator's startup gate; the stand-in carries it too, so the
        # test can follow it.
        self._restored = False
        self.saved_pending = 0
        # Het opslaggeheugen van de echte coördinator: alleen de vlag en de stap,
        # want deze stand-in heeft geen opslag. De toets volgt of de stap loopt.
        #
        # The real coordinator's store memory: only the flag and the step, since
        # this stand-in has no store. The test follows whether the step runs.
        self._save_pending = False
        # De notitie van wat de gebruiker vóór het herstel zelf deed:
        # `_async_on_hass_started` maakt hem na het herstel leeg, en deze stand-in
        # begint leeg.
        #
        # The note of what the user did himself before the restore:
        # `_async_on_hass_started` empties it after the restore, and this stand-in
        # starts empty.
        self._by_hand_before_restore: set[str] = set()

    def tracked_entities(self) -> set[str]:
        """Eén gevolgde entiteit, zodat het opzetten de listener echt aanraakt.

        Een lege verzameling liet `async_start` de listener overslaan, en dan
        bewees deze toets niets over het opstarten: juist tijdens het opstarten
        gebeurt er iets met een gevolgde entiteit - daarom is de poort er.

        One tracked entity, so that setting up really touches the listener. An
        empty set made `async_start` skip the listener, and then this test proved
        nothing about the startup: it is exactly during the startup that
        something happens to a tracked entity - which is why the gate exists.
        """
        return {"sensor.room"}

    def _handle_change(self, _event) -> None:
        """Deze stand-in beslist niets; de listener wordt hier niet aangeroepen."""

    def _cancel_pending_deferral(self) -> None:
        pass

    def _cancel_clock_reeval(self) -> None:
        pass

    async def _async_restore_state(self) -> None:
        self.restored += 1

    def _async_save_pending_state(self) -> None:
        """Deze stand-in bewaart niets; de stap hoort wel op het pad.

        `_async_on_hass_started` schrijft ná het herstel één keer weg wat tijdens
        het opstarten bleef liggen. Zonder opslag valt er niets te schrijven, maar
        de toets volgt of die stap werkelijk loopt.

        This stand-in stores nothing; the step does belong on the path.
        `_async_on_hass_started` writes once after the restore for what stayed
        behind during the startup. Without a store there is nothing to write, but
        the test follows whether that step really runs.
        """
        self.saved_pending += 1

    def _note_precipitation_now(self) -> None:
        self.precipitation_noted += 1

    def _note_home_now(self) -> None:
        """Deze stand-in houdt geen bewoners bij; de stap hoort wel op het pad."""

    async def _async_evaluate(self) -> None:
        self.evaluated += 1

    def _schedule_clock_reeval(self) -> None:
        self.clock_armed += 1

    async_start = ClimateDirectorCoordinator.async_start
    _async_on_hass_started = ClimateDirectorCoordinator._async_on_hass_started


async def test_the_first_decision_waits_for_hass_to_start(monkeypatch) -> None:
    """Opzetten beslist nog niet; pas als Home Assistant meldt dat hij draait.

    De listener staat er wél al: een toestandswijziging tijdens het opstarten
    mag niet verloren gaan, en juist daarom wacht het beslissen op een poort.
    Zonder gevolgde entiteit sloeg de stand-in die stap over en zei deze toets
    niets over het opstarten zelf.

    Setting up does not decide yet; only once Home Assistant reports it is up.
    The listener is already there, though: a state change during the startup must
    not get lost, and that is exactly why deciding waits for a gate. Without a
    tracked entity the stand-in skipped that step and this test said nothing
    about the startup itself.
    """
    scheduled: dict[str, object] = {}
    monkeypatch.setattr(
        module,
        "async_at_started",
        lambda _hass, callback: scheduled.__setitem__("callback", callback) or (lambda: None),
    )
    watched: list[list[str]] = []

    def _track(_hass, entities, _callback) -> object:
        watched.append(list(entities))
        return lambda: None

    monkeypatch.setattr(module, "async_track_state_change_event", _track)

    item = StandIn()
    await item.async_start()

    assert watched == [["sensor.room"]], "de listener hoort er vóór het opstarten te staan"
    assert item.restored == 0
    assert item.evaluated == 0
    assert item._restored is False, "de opstartpoort hoort nog dicht te staan"
    assert "callback" in scheduled

    await scheduled["callback"](item.hass)  # type: ignore[misc]

    assert item.restored == 1
    assert item.precipitation_noted == 1
    assert item.evaluated == 1
    assert item.clock_armed == 1
    assert item._restored is True, "na het herstel hoort de poort open te staan"


async def test_a_broken_restore_still_opens_the_gate() -> None:
    """Eén kapotte lezing mag de director niet voorgoed stil leggen.

    Herstellen, beslissen en de klok zetten zijn vier stappen op één pad. Valt
    het herstel zelf om, dan is er niets hersteld - maar de poort moet alsnog
    opengaan. Bleef hij dicht, dan besliste de director nooit meer, en dat is
    erger dan een wereld zonder de bewaarde hand: elke tijdregel zou dan op een
    toevallige wijziging wachten die niet meer beslist.

    One broken reading must not silence the director for good. Restoring,
    deciding and arming the clock are four steps on one path. When the restore
    itself falls over, nothing has been restored - but the gate has to open all
    the same. If it stayed shut the director would never decide again, and that
    is worse than a world without the stored hand: every time rule would then
    wait for a chance change that no longer decides.
    """
    item = StandIn()

    async def broken_restore() -> None:
        raise RuntimeError("kapotte opslag")

    item._async_restore_state = broken_restore  # type: ignore[method-assign]

    await item._async_on_hass_started(item.hass)  # type: ignore[arg-type]

    assert item.clock_armed == 1, "de vangnetklok hoort ondanks de fout te lopen"
    assert item._restored is True, "de poort hoort ook na een kapotte lezing open te gaan"


async def test_an_exception_from_the_first_decision_still_arms_the_clock() -> None:
    """Eén kapotte eerste beslissing mag de vangnetklok niet tegenhouden.

    Herstellen, beslissen en de klok zetten zijn vier stappen op één pad. Slaat
    de beslissing om, dan is de schade het grootst als daardoor ook de klok
    nooit loopt: dan wacht elke tijdregel op een toevallige wijziging die nooit
    komt. De klok hoort dus hoe dan ook gezet te worden, en de uitzondering
    hoort gelogd te worden in plaats van de integratie stil te leggen.

    One broken first decision must not hold the safety-net clock back.
    Restoring, deciding and arming the clock are four steps on one path. When
    the decision falls over the damage is greatest if the clock never starts
    either: every time rule then waits for a chance change that never comes.
    The clock therefore has to be armed no matter what, and the exception has
    to be logged rather than silencing the integration.
    """
    item = StandIn()

    async def broken_evaluate() -> None:
        raise RuntimeError("kapotte eerste beslissing")

    item._async_evaluate = broken_evaluate  # type: ignore[method-assign]

    await item._async_on_hass_started(item.hass)  # type: ignore[arg-type]

    assert item.clock_armed == 1, "de vangnetklok hoort ondanks de fout te lopen"
