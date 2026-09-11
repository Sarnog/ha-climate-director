"""Elke entiteit kent haar categorie, en niets staat standaard uit.

Every entity knows its category, and nothing is disabled by default.

C10: besloten is "alleen categorieën zetten, niets standaard uitschakelen".
Deze test pint per entiteit de categorie vast — `DIAGNOSTIC`, `CONFIG` of
uitdrukkelijk `None` voor "gewoon zichtbaar" — zodat een nieuwe entiteit niet
ongemerkt zonder keuze binnenkomt. En hij eist dat geen enkel platform
`entity_registry_enabled_default` zet, zodat "niets standaard uit" een bewaakte
eigenschap is en geen afspraak.

C10: the decision is "set categories only, never disable anything by default".
This test pins the category per entity — `DIAGNOSTIC`, `CONFIG` or explicitly
`None` for "plainly visible" — so a new entity cannot slip in without a choice.
And it requires that no platform sets `entity_registry_enabled_default`, so
"nothing off by default" is a guarded property rather than a promise.
"""

from __future__ import annotations

import importlib

from homeassistant.const import EntityCategory

from custom_components.climate_director.const import PLATFORMS

EXPECTED: dict[str, dict[str, EntityCategory | None]] = {
    "binary_sensor": {
        "zone_blocked": EntityCategory.DIAGNOSTIC,
        "zone_fallback": EntityCategory.DIAGNOSTIC,
        "stuck": EntityCategory.DIAGNOSTIC,
    },
    "button": {
        "zone_precondition": None,
    },
    "number": {
        "zone_priority": EntityCategory.CONFIG,
        "precondition_minutes": EntityCategory.CONFIG,
    },
    "select": {
        "season": EntityCategory.CONFIG,
    },
    "sensor": {
        "last_decision": EntityCategory.DIAGNOSTIC,
        "would_command": EntityCategory.DIAGNOSTIC,
        "mismatch": EntityCategory.DIAGNOSTIC,
        "zone_source": EntityCategory.DIAGNOSTIC,
    },
    "switch": {
        "master": None,
        "holiday": None,
        "guest": None,
        "zone_override": None,
        "opening_bypass": None,
    },
}


def _entity_classes(platform: str) -> dict[str, type]:
    """Return each entity class of a platform, keyed by its translation key.

    De HA-metaclass verhuist `_attr_*`-klasseattributen naar hun gemangelde
    naam (`__attr_*`), dus hier wordt rechtstreeks in `__dict__` gekeken in
    plaats van `getattr` op de klasse te doen.

    HA's metaclass moves `_attr_*` class attributes to their mangled name
    (`__attr_*`), so this reads `__dict__` directly instead of using `getattr`
    on the class.
    """
    module = importlib.import_module(f"custom_components.climate_director.{platform}")
    return {
        cls.__dict__["__attr_translation_key"]: cls
        for cls in vars(module).values()
        if isinstance(cls, type)
        and cls.__module__ == module.__name__
        and "__attr_translation_key" in cls.__dict__
    }


def test_every_entity_pins_its_category() -> None:
    """Elke entiteit declareert precies de afgesproken categorie.

    Every entity declares exactly the agreed category.
    """
    problems: list[str] = []
    for platform in PLATFORMS:
        expected = EXPECTED.get(platform.value, {})
        found = _entity_classes(platform.value)
        for key, cls in found.items():
            actual = cls.__dict__.get("__attr_entity_category", "ontbreekt")
            if key not in expected:
                problems.append(f"{platform.value}.{key}: geen afspraak in de test")
            elif actual != expected[key]:
                problems.append(
                    f"{platform.value}.{key}: {actual!r}, afgesproken {expected[key]!r}"
                )
        for key in expected:
            if key not in found:
                problems.append(f"{platform.value}.{key}: entiteit niet gevonden")
    assert not problems, "categorieën: " + "; ".join(problems)


def test_nothing_is_disabled_by_default() -> None:
    """Geen platform zet `entity_registry_enabled_default`; de standaard is aan.

    No platform sets `entity_registry_enabled_default`; the default is on.
    """
    from pathlib import Path

    package = Path(__file__).resolve().parents[1] / "custom_components" / "climate_director"
    offenders = []
    for platform in PLATFORMS:
        source = (package / f"{platform.value}.py").read_text(encoding="utf-8")
        if "entity_registry_enabled_default" in source:
            offenders.append(platform.value)
    assert not offenders, "platforms die enabled_default zetten: " + ", ".join(offenders)
