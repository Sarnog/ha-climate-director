"""De overrideschakelaar volgt de coordinator en overleeft een herstart eerlijk.

The override switch follows the coordinator and survives a restart honestly.

De noodknop vervalt bij bedtijd en bij een leeg huis. De coordinator gooit
`zone_overrides` dan leeg, maar de schakelaar hield haar laatst geschreven stand
(`on`) - en een herstart herstelt precies die stand terug de coordinator in. Zo
herleefde een overgedragen zone na elke herstart, totdat de schakelaar zijn
verval ook echt wegschrijft.

The emergency handle lapses at bedtime and on an empty house. The coordinator
then empties `zone_overrides`, but the switch kept its last written state (`on`)
- and a restart restores exactly that state back into the coordinator. A
handed-over zone revived after every restart until the switch actually wrote its
lapse away.
"""

from __future__ import annotations

import asyncio

from custom_components.climate_director.engine import DirectorConfig, ModeSettings, Source, Zone
from custom_components.climate_director.switch import ZoneOverrideSwitch


def config() -> DirectorConfig:
    """Return a single-zone installation."""
    return DirectorConfig(
        zones=(
            Zone(
                "woonkamer",
                "Woonkamer",
                "sensor.woonkamer",
                sources=(Source("w", "climate.huiskamer"),),
                heat=ModeSettings(21.0, 20.0),
            ),
        ),
    )


class _Entry:
    entry_id = "abc"
    title = "Climate Director"


class _Coordinator:
    """Stand-in carrying what the switch and its entity base touch."""

    def __init__(self) -> None:
        self.config = config()
        self.config_entry = _Entry()
        self.version = ""
        self.zone_overrides: dict[str, bool] = {}
        self.evaluations = 0

    def async_add_listener(self, listener, context=None):
        self._listener = listener
        return lambda: None

    def async_request_evaluation(self) -> None:
        self.evaluations += 1


class _State:
    def __init__(self, state: str) -> None:
        self.state = state


def _restore_as(state: str | None):
    """Return an `async_get_last_state` stand-in answering with `state`."""

    async def _get():
        return None if state is None else _State(state)

    return _get


class TestZoneOverrideSwitch:
    def test_when_the_coordinator_lets_go_the_switch_writes_off(self) -> None:
        """Vervalt de override, dan gaat de schakelaar uit en schrijft hij dat weg.

        When the override lapses the switch turns off and writes that away.
        """
        coordinator = _Coordinator()
        switch = ZoneOverrideSwitch(coordinator, "woonkamer")
        written: list[bool] = []
        switch.async_write_ha_state = lambda: written.append(switch.is_on)

        asyncio.run(switch._set(True))
        assert coordinator.zone_overrides == {"woonkamer": True}

        # Wat `_zones_handed_back` doet zodra iedereen slaapt of het huis leeg is.
        # What `_zones_handed_back` does once everybody sleeps or the house is empty.
        coordinator.zone_overrides.clear()
        switch._handle_coordinator_update()

        assert switch.is_on is False
        assert written == [True, False]

    def test_a_restart_does_not_revive_an_expired_override(self) -> None:
        """Herstelt de schakelaar `off`, dan blijft de zone na een herstart van de director.

        When the switch restores `off` the zone stays with the director after a restart.
        """
        coordinator = _Coordinator()
        switch = ZoneOverrideSwitch(coordinator, "woonkamer")
        written: list[bool] = []
        switch.async_write_ha_state = lambda: written.append(switch.is_on)

        asyncio.run(switch._set(True))
        coordinator.zone_overrides.clear()
        switch._handle_coordinator_update()

        # Een herstart geeft de laatst geschreven stand terug; dat is nu `off`.
        # A restart hands back the last written state; that is now `off`.
        revived = ZoneOverrideSwitch(_Coordinator(), "woonkamer")
        revived.async_get_last_state = _restore_as("on" if written[-1] else "off")
        asyncio.run(revived.async_added_to_hass())

        assert revived.is_on is False
        assert revived.coordinator.zone_overrides.get("woonkamer", False) is False
