"""De eenmalige melding over handbediende bronnen.

The one-time notice about hand-operated sources.
"""

from __future__ import annotations

from .families import ModeFamily
from .models import DirectorConfig
from .problem import Problem


def manual_only_problems(config: DirectorConfig) -> tuple[Problem, ...]:
    """Return the duties that only hand-operated sources can deliver.

    Een zone waarvan een gewenste taak (verwarmen of koelen) alleen door bronnen
    met automatisch starten uit geleverd kan worden, start die taak nooit uit
    zichzelf. Dat mag de bedoeling zijn - een handbediende slaapkamerairco is
    een prima keuze - maar van buiten is het niet te onderscheiden van een per
    ongeluk uitgezette autostart. Daarom is dit bewust géén `validate()`-fout:
    het is een eenmalige melding die de gebruiker kan afvinken, geen blijvend
    probleem op de controlelijst.

    A zone whose wanted duty (heating or cooling) can only be delivered by
    sources with automatic start off never starts that duty of its own accord.
    That may well be the point - a hand-operated bedroom airco is a fine choice
    - but from the outside it is indistinguishable from an autostart switched
    off by accident. Hence this is deliberately no `validate()` error: it is a
    one-time notice the user can tick off, not a permanent entry on the problem
    list.
    """
    found: list[Problem] = []
    for zone in config.zones:
        for family in (ModeFamily.HEAT, ModeFamily.COOL):
            if zone.settings_for(family) is None:
                continue
            if not any(source.supports(family) for source in zone.sources):
                continue  # that is a real configuration problem, not this notice
            if not any(source.supports(family) and source.autostart for source in zone.sources):
                found.append(
                    Problem(
                        "zone_only_manual_sources",
                        f"zone {zone.zone_id} wants {family.value} but every source "
                        "able to deliver it has automatic start off",
                        zone=zone.name or zone.zone_id,
                        zone_id=zone.zone_id,
                        mode=family.value,
                    )
                )
    return tuple(found)
