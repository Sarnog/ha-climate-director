"""De quality scale is opgeschreven, en elke vrijstelling legt uit waarom.

The quality scale is written down, and every exemption explains why.

C5: de werkregel is *wat nog niet klopt hoort als `todo` te staan, niet
stilzwijgend te ontbreken*. Dit bestand bewaakt de tweede helft van die regel:
een `exempt` zonder `comment` is een vrijstelling die niemand meer kan
verantwoorden, en dat is precies hoe de administratie verrot.

C5: the working rule is *what does not hold yet should stand as `todo`, not be
silently absent*. This file guards the second half of that rule: an `exempt`
without a `comment` is an exemption nobody can justify any more, and that is
exactly how the administration rots.
"""

from __future__ import annotations

from pathlib import Path

import yaml

QUALITY_SCALE = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "climate_director"
    / "quality_scale.yaml"
)

# De letterlijke checklist van de officiële HA-pagina, opgehaald 2026-09-06:
# https://developers.home-assistant.io/docs/core/integration-quality-scale/checklist/
#
# hassfest bewaakt deze eigenschap NIET zolang manifest.json geen `quality_scale`
# draagt — zijn quality-scale-plugin draait alleen dán. Deze test is dus de enige
# die de lijst compleet houdt; haal hem niet weg met "hassfest doet dat toch".
#
# The literal checklist from the official HA page, retrieved 2026-09-06:
# https://developers.home-assistant.io/docs/core/integration-quality-scale/checklist/
#
# hassfest does NOT guard this property as long as manifest.json carries no
# `quality_scale` — its quality-scale plugin only runs then. So this test is the
# only thing keeping the list complete; do not remove it with "hassfest does that".
QUALITY_SCALE_CHECKLIST: tuple[str, ...] = (
    # Bronze
    "action-setup",
    "appropriate-polling",
    "brands",
    "common-modules",
    "config-flow-test-coverage",
    "config-flow",
    "dependency-transparency",
    "docs-actions",
    "docs-triggers",
    "docs-conditions",
    "docs-high-level-description",
    "docs-installation-instructions",
    "docs-removal-instructions",
    "entity-event-setup",
    "entity-unique-id",
    "has-entity-name",
    "runtime-data",
    "test-before-configure",
    "test-before-setup",
    "unique-config-entry",
    # Silver
    "action-exceptions",
    "config-entry-unloading",
    "docs-configuration-parameters",
    "docs-installation-parameters",
    "entity-unavailable",
    "integration-owner",
    "log-when-unavailable",
    "parallel-updates",
    "reauthentication-flow",
    "test-coverage",
    # Gold
    "devices",
    "diagnostics",
    "discovery-update-info",
    "discovery",
    "docs-data-update",
    "docs-examples",
    "docs-known-limitations",
    "docs-supported-devices",
    "docs-supported-functions",
    "docs-troubleshooting",
    "docs-use-cases",
    "dynamic-devices",
    "entity-category",
    "entity-device-class",
    "entity-disabled-by-default",
    "entity-translations",
    "exception-translations",
    "icon-translations",
    "reconfiguration-flow",
    "repair-issues",
    "stale-devices",
    # Platinum
    "async-dependency",
    "inject-websession",
    "strict-typing",
)


def test_every_exemption_explains_itself() -> None:
    """Elke `exempt`-regel draagt een niet-lege `comment`.

    Every `exempt` rule carries a non-empty `comment`.
    """
    document = yaml.safe_load(QUALITY_SCALE.read_text(encoding="utf-8"))
    assert isinstance(document, dict), "quality_scale.yaml hoort een mapping te zijn"
    rules = document.get("rules")
    assert isinstance(rules, dict), "quality_scale.yaml hoort een `rules:`-mapping te zijn"

    problems = []
    for identifier, value in rules.items():
        if isinstance(value, dict) and value.get("status") == "exempt":
            comment = value.get("comment")
            if not comment or not str(comment).strip():
                problems.append(identifier)
    assert not problems, (
        "elke exempt-regel hoort een comment te hebben; zonder comment: "
        + ", ".join(sorted(problems))
    )


def test_every_rule_has_a_known_status() -> None:
    """Elke regel is `done`, `todo` of `exempt` — niets daarbuiten.

    Every rule is `done`, `todo` or `exempt` — nothing outside that.
    """
    document = yaml.safe_load(QUALITY_SCALE.read_text(encoding="utf-8"))
    rules = document["rules"]
    problems = []
    for identifier, value in rules.items():
        if isinstance(value, str):
            if value not in ("done", "todo"):
                problems.append(f"{identifier}: {value}")
        elif isinstance(value, dict):
            if value.get("status") not in ("done", "todo", "exempt"):
                problems.append(f"{identifier}: {value}")
            elif not value.get("comment"):
                problems.append(f"{identifier}: een uitgebreide regel hoort een comment te hebben")
        else:
            problems.append(f"{identifier}: {value!r}")
    assert not problems, "onbekende status: " + "; ".join(problems)


def test_the_quality_scale_is_complete() -> None:
    """Elke officiële regel-identifier staat in het bestand, en andersom.

    De bron is de officiële HA-checklist (opgehaald 2026-09-06), en die telt
    54 identifiers over Bronze, Silver, Gold en Platinum. Ontbreekt er één in
    `quality_scale.yaml`, dan faalt deze test en noemt hem bij naam; staat er
    een identifier in die niet op de lijst voorkomt, dan faalt hij daar óók op.

    hassfest bewaakt dit niet zolang `manifest.json` geen `quality_scale`
    draagt: de quality-scale-plugin draait alleen dán. Zie de docstring bij de
    lijst hierboven; haal deze test dus niet weg met "hassfest doet dat toch".

    Every official rule identifier sits in the file, and the other way around.

    The source is the official HA checklist (retrieved 2026-09-06), which has
    54 identifiers across Bronze, Silver, Gold and Platinum. When one is missing
    from `quality_scale.yaml`, this test fails and names it; when the file holds
    an identifier that is not on the list, it fails on that too.

    hassfest does not guard this as long as `manifest.json` carries no
    `quality_scale`: the quality-scale plugin only runs then. See the docstring
    with the list above; do not remove this test with "hassfest does that".
    """
    document = yaml.safe_load(QUALITY_SCALE.read_text(encoding="utf-8"))
    assert isinstance(document, dict), "quality_scale.yaml hoort een mapping te zijn"
    rules = document.get("rules")
    assert isinstance(rules, dict), "quality_scale.yaml hoort een `rules:`-mapping te zijn"

    missing = [identifier for identifier in QUALITY_SCALE_CHECKLIST if identifier not in rules]
    extra = [identifier for identifier in rules if identifier not in QUALITY_SCALE_CHECKLIST]
    problems = []
    if missing:
        problems.append("ontbreekt in quality_scale.yaml: " + ", ".join(missing))
    if extra:
        problems.append("staat erin maar niet op de officiële checklist: " + ", ".join(extra))
    assert not problems, "; ".join(problems)
