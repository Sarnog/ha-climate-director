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
        self.restored = 0
        self.evaluated = 0
        self.clock_armed = 0
        self.precipitation_noted = 0

    def tracked_entities(self) -> set[str]:
        return set()

    def _cancel_pending_deferral(self) -> None:
        pass

    def _cancel_clock_reeval(self) -> None:
        pass

    async def _async_restore_state(self) -> None:
        self.restored += 1

    def _note_precipitation_now(self) -> None:
        self.precipitation_noted += 1

    async def _async_evaluate(self) -> None:
        self.evaluated += 1

    def _schedule_clock_reeval(self) -> None:
        self.clock_armed += 1

    async_start = ClimateDirectorCoordinator.async_start
    _async_on_hass_started = ClimateDirectorCoordinator._async_on_hass_started


async def test_the_first_decision_waits_for_hass_to_start(monkeypatch) -> None:
    """Opzetten beslist nog niet; pas als Home Assistant meldt dat hij draait.

    Setting up does not decide yet; only once Home Assistant reports it is up.
    """
    scheduled: dict[str, object] = {}
    monkeypatch.setattr(
        module,
        "async_at_started",
        lambda hass, callback: scheduled.__setitem__("callback", callback) or (lambda: None),
    )

    item = StandIn()
    await item.async_start()

    assert item.restored == 0
    assert item.evaluated == 0
    assert "callback" in scheduled

    await scheduled["callback"](item.hass)  # type: ignore[misc]

    assert item.restored == 1
    assert item.precipitation_noted == 1
    assert item.evaluated == 1
    assert item.clock_armed == 1


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
