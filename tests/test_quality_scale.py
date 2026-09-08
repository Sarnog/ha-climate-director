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
