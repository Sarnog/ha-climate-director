"""Twee installaties naast elkaar houden hun eigen entiteiten en acties.

Two installations side by side keep their own entities and actions."""

from __future__ import annotations

from harness_live import (
    settings,
    source,
    start_house,
    stop_house,
    zone,
)
from live_helpers import (
    ATTIC,
    LIVING,
)


async def test_two_installations_keep_their_own_entities_and_actions() -> None:
    """Twee huizen in één Home Assistant mogen elkaar niet in de weg zitten.

    Two houses in one Home Assistant must not get in each other's way.
    """
    first_installation = {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("airco", LIVING, role="heat_cool")],
                heat=settings(21.0, 20.0),
            )
        ]
    }
    home = await start_house(
        first_installation,
        states={"sensor.woonkamer": ("18.0", {}), LIVING: ("off", {}), ATTIC: ("off", {})},
        entry_id="huis_een",
        title="Huis een",
    )
    try:
        from homeassistant.config_entries import ConfigEntry

        second = ConfigEntry(
            data={
                "installation": {
                    "zones": [
                        zone(
                            "zolder",
                            sources=[source("airco2", ATTIC, role="heat_cool")],
                            heat=settings(21.0, 20.0),
                        )
                    ]
                }
            },
            options={"shadow_mode": False},
            domain="climate_director",
            minor_version=1,
            version=1,
            source="user",
            title="Huis twee",
            unique_id=None,
            discovery_keys={},  # type: ignore[arg-type]
            subentries_data=None,
            entry_id="huis_twee",
        )
        home.set("sensor.zolder", "18.0")
        await home.hass.config_entries.async_add(second)
        await home.hass.async_block_till_done()

        assert home.state(LIVING) == "heat"
        assert home.state(ATTIC) == "heat"

        # De actie mag op één installatie gericht worden.
        # The action may be aimed at one installation.
        await home.call(
            "climate_director", "precondition", {"entry_id": "huis_twee", "minutes": 30}
        )
        await home.settle()
        assert home.coordinator._live_preconditions() == {}
        assert second.runtime_data._live_preconditions()

        # En elke installatie houdt zijn eigen entiteiten.
        # And every installation keeps its own entities.
        from homeassistant.helpers import entity_registry

        registry = entity_registry.async_get(home.hass)
        first_ids = {
            item.entity_id
            for item in registry.entities.values()
            if item.config_entry_id == "huis_een"
        }
        second_ids = {
            item.entity_id
            for item in registry.entities.values()
            if item.config_entry_id == "huis_twee"
        }
        assert first_ids and second_ids
        assert not (first_ids & second_ids)
    finally:
        await stop_house(home)
