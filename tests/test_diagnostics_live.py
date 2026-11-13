"""De diagnose van een draaiende installatie.

The diagnostics of a running installation."""

from __future__ import annotations

import json
from datetime import timedelta

from harness_live import (
    settings,
    source,
    start_house,
    stop_house,
    zone,
)
from homeassistant.util import dt as dt_util
from live_helpers import (
    LIVING,
)


async def test_reading_the_diagnostics_changes_nothing() -> None:
    """Een diagnose downloaden is kijken, niet aanraken.

    Downloading diagnostics is looking, not touching.

    De lezer van de lopende vooruit-verzoeken ruimt op terwijl hij leest. Dat is
    prima op het pad waar er toch al beslist wordt, maar de diagnose hoort geen
    toestand te wijzigen: dan verandert wat je downloadt het huis waar je een
    storing van probeert vast te leggen.

    The reader of the running pre-conditioning requests prunes as it reads. That
    is fine on the path where a decision is being taken anyway, but the
    diagnostics must not alter state: then what you download changes the house
    whose fault you are trying to capture.
    """

    from custom_components.climate_director.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    installation = {
        "zones": [zone("woonkamer", sources=[source("airco", LIVING)], heat=settings(21.0, 20.0))],
        "outdoor_sensor": "sensor.buiten",
    }
    home = await start_house(
        installation,
        states={
            "sensor.woonkamer": ("18.0", {}),
            "sensor.buiten": ("3.0", {}),
            LIVING: ("off", {}),
        },
        entry_id="kijken",
    )
    try:
        stale = dt_util.now() - timedelta(minutes=5)
        home.coordinator.precondition_until = {"woonkamer": stale}
        home.coordinator.precondition_bypass = {"woonkamer"}

        found = await async_get_config_entry_diagnostics(home.hass, home.entry)

        assert found["control_state"]["precondition_requests"] == {}, (
            "een verlopen verzoek hoort niet in de diagnose te staan"
        )
        assert home.coordinator.precondition_until == {"woonkamer": stale}, (
            "de diagnose hoort de toestand niet op te ruimen"
        )
        assert home.coordinator.precondition_bypass == {"woonkamer"}
    finally:
        await stop_house(home)


async def test_the_diagnostics_describe_the_whole_installation() -> None:
    """Wat je downloadt bij een storingsmelding moet compleet en leesbaar zijn.

    What you download with a bug report has to be complete and readable.
    """

    from custom_components.climate_director.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    installation = {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("airco", LIVING, role="heat_cool")],
                heat=settings(21.0, 20.0),
            )
        ],
        "outdoor_sensor": "sensor.buiten",
    }
    home = await start_house(
        installation,
        states={
            "sensor.woonkamer": ("18.0", {}),
            "sensor.buiten": ("3.0", {}),
            LIVING: ("off", {}),
        },
    )
    try:
        found = await async_get_config_entry_diagnostics(home.hass, home.entry)
        assert json.dumps(found, default=str), "de diagnose moet als JSON weg kunnen"
        text = json.dumps(found, default=str)
        assert "woonkamer" in text
        assert LIVING in text
    finally:
        await stop_house(home)


async def test_the_diagnostics_redact_the_resident_profile() -> None:
    """Wie er thuis is, slaapt en wanneer, is een inbraakprofiel en gaat niet mee.

    Who is home, asleep and when is a burglary profile and is left out.
    """
    from homeassistant.components.diagnostics.const import REDACTED

    from custom_components.climate_director.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    installation = {
        "zones": [zone("woonkamer", sources=[source("airco", LIVING)], heat=settings(21.0, 20.0))],
        "residents": [
            {
                "resident_id": "danny",
                "name": "Danny",
                "presence_entity": "person.danny",
                "sleep_entity": "sensor.danny_slaap",
                "sleep_state": "on",
                "sleep_window": {
                    "start": "23:00:00",
                    "end": "07:00:00",
                    "weekdays": [0, 1, 2, 3, 4],
                },
                "windows": [
                    {
                        "start": "06:00:00",
                        "end": "23:00:00",
                        "weekdays": [0, 1, 2, 3, 4],
                        "holiday": False,
                    }
                ],
            }
        ],
        "outdoor_sensor": "sensor.buiten",
    }
    home = await start_house(
        installation,
        states={
            "sensor.woonkamer": ("18.0", {}),
            "sensor.buiten": ("3.0", {}),
            LIVING: ("off", {}),
            "person.danny": ("home", {}),
            "sensor.danny_slaap": ("off", {}),
        },
    )
    try:
        found = await async_get_config_entry_diagnostics(home.hass, home.entry)

        residents = found["world"]["residents"]
        assert residents["danny"]["home"] == REDACTED
        assert residents["danny"]["asleep"] == REDACTED
        stored_resident = found["installation"]["residents"][0]
        assert stored_resident["windows"] == REDACTED
        assert stored_resident["sleep_window"] == REDACTED
    finally:
        await stop_house(home)
