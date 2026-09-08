"""Elk platform verklaart zijn parallelle bijwerkingen.

Every platform declares its parallel side effects.

C7: alles komt uit één coordinator, dus er valt niets te serialiseren.
`PARALLEL_UPDATES = 0` is die verklaring. Deze test hangt niet aan een lijst
met zes namen: hij leest de platformlijst uit `const.PLATFORMS`, dus een
platform dat er later bijkomt moet de verklaring meteen afleggen.

C7: everything comes from one coordinator, so there is nothing to serialise.
`PARALLEL_UPDATES = 0` is that declaration. This test does not hang on a list
of six names: it reads the platform list from `const.PLATFORMS`, so a platform
added later has to make the declaration straight away.
"""

from __future__ import annotations

import importlib

from custom_components.climate_director.const import PLATFORMS


def test_every_platform_declares_parallel_updates() -> None:
    """Elk platform in `PLATFORMS` declareert `PARALLEL_UPDATES = 0`.

    Every platform in `PLATFORMS` declares `PARALLEL_UPDATES = 0`.
    """
    missing: list[str] = []
    for platform in PLATFORMS:
        module = importlib.import_module(f"custom_components.climate_director.{platform.value}")
        if getattr(module, "PARALLEL_UPDATES", None) != 0:
            missing.append(platform.value)
    assert not missing, "platforms zonder PARALLEL_UPDATES = 0: " + ", ".join(missing)
