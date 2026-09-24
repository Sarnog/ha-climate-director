"""Elke sleutel in `strings.json` heeft een producent in de code.

Every key in `strings.json` has a producer in the code.

R30-3c. De bestaande bewakingen kijken één kant op: elke `Problem`-code heeft
een tekst, elke vertaling heeft de sleutels van het Engels, elk formulierveld
heeft een label. Wat nergens bewaakt werd is de andere kant - een sleutel die
in alle zeven bestanden staat terwijl geen enkele code, entiteit, actie of
`Problem`-code hem ooit opvraagt. Zo'n sleutel kan jaren blijven staan, en dan
is "alles is vertaald" een getal zonder betekenis.

Gemeten op 2026-09-14: `selector.save_exit` was zo'n sleutel. `schemas.save()`
bouwt zijn afsluitregel met `_exit_row()`, en die draagt
`translation_key="when_done"`; het hele `save_exit`-blok in de zeven bestanden
werd door niets gelezen.

Deze test leest de producenten uit de bron - de stapmethodes uit
`config_flow.py`, de letterlijke sleutels uit de code, `icons.json` voor de
entiteiten, `services.yaml` voor de acties - en eist dat elke sleutel er een
heeft. De rekenkern is een pure functie, zodat de bewaking zelf ook getest kan
worden op verzonnen invoer.

R30-3c. The existing guards look one way only: every `Problem` code has a text,
every translation has the English keys, every form field has a label. What was
guarded nowhere is the other side - a key that stands in all seven files while
no code, entity, action or `Problem` code ever asks for it. Such a key can stay
for years, and then "everything is translated" is a number without meaning.

Measured on 2026-09-14: `selector.save_exit` was such a key. `schemas.save()`
builds its exit row with `_exit_row()`, and that carries
`translation_key="when_done"`; the whole `save_exit` block in the seven files
was read by nothing.

This test reads the producers from the source - the step methods from
`config_flow.py`, the literal keys from the code, `icons.json` for the entities,
`services.yaml` for the actions - and demands that every key has one. The
computation is a pure function, so the guard itself can be tested on invented
input too.

Dekking: elke sleutel in `strings.json` tegen de bron van de integratie - de
stapmethodes en de letterlijke sleutels in de code, `icons.json` en
`services.yaml`. Niet gedekt: de waarde van een sleutel of zijn vertaling; deze
toets kijkt alleen of iemand hem opvraagt.

Coverage: every key in `strings.json` against the integration's source - the step
methods and the literal keys in the code, `icons.json` and `services.yaml`. Not
covered: the value of a key or its translation; this guard only checks that
something asks for it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PACKAGE = Path(__file__).resolve().parents[1] / "custom_components" / "climate_director"
STRINGS = PACKAGE / "strings.json"
ICONS = PACKAGE / "icons.json"
SERVICES = PACKAGE / "services.yaml"


def package_source() -> str:
    """Return every line of Python in the integration, joined.

    Return every line of Python in the integration, joined.
    """
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(PACKAGE.rglob("*.py")))


def mentions(source: str, name: str) -> bool:
    """Return whether a name stands in the source as a literal.

    Return whether a name stands in the source as a literal.
    """
    return f'"{name}"' in source or f"'{name}'" in source


def dead_keys(
    strings: dict[str, Any],
    source: str,
    icons: dict[str, Any],
    services: str,
) -> list[str]:
    """Return every key of `strings.json` that no producer can ask for.

    Return every key of `strings.json` that no producer can ask for.

    Per sectie is er één regel, en die is telkens dezelfde soort: bestaat de
    producent van deze sleutel in de bron?

    Per section there is one rule, and it is the same kind every time: does this
    key's producer exist in the source?
    """
    dead: list[str] = []

    for section in ("config", "options"):
        steps = strings.get(section, {}).get("step", {})
        if not isinstance(steps, dict):
            continue
        for step, block in steps.items():
            if f"async_step_{step}" not in source:
                dead.append(f"{section}.step.{step}")
            fields = block.get("data") if isinstance(block, dict) else None
            if isinstance(fields, dict):
                for field in fields:
                    if not mentions(source, field):
                        dead.append(f"{section}.step.{step}.data.{field}")

    for code in strings.get("exceptions", {}):
        if not mentions(source, code):
            dead.append(f"exceptions.{code}")

    for key in strings.get("issues", {}):
        if not mentions(source, key):
            dead.append(f"issues.{key}")

    for name in strings.get("selector", {}):
        # Een keuzelijst draagt zijn sleutel als `translation_key`, of zijn
        # volledige pad wordt in `texts.py` opgebouwd (`weekday_summary`).
        #
        # A picker carries its key as `translation_key`, or its full path is
        # built in `texts.py` (`weekday_summary`).
        if not (mentions(source, name) or f".selector.{name}." in source):
            dead.append(f"selector.{name}")

    entity_icons = icons.get("entity", {})
    for domain, keys in strings.get("entity", {}).items():
        for key in keys:
            if not (mentions(source, key) or key in entity_icons.get(domain, {})):
                dead.append(f"entity.{domain}.{key}")

    for key in strings.get("services", {}):
        if key not in services:
            dead.append(f"services.{key}")

    return dead


def test_no_key_is_without_a_producer() -> None:
    """Geen enkele sleutel in de zeven bestanden staat er zonder producent.

    No key in the seven files stands there without a producer.
    """
    strings = json.loads(STRINGS.read_text(encoding="utf-8"))
    icons = json.loads(ICONS.read_text(encoding="utf-8"))
    dead = dead_keys(strings, package_source(), icons, SERVICES.read_text(encoding="utf-8"))
    assert not dead, (
        "deze sleutels staan in strings.json maar geen enkele code, entiteit, "
        f"actie of Problem-code vraagt ze ooit op: {sorted(dead)}"
    )


def test_the_guard_has_something_to_guard() -> None:
    """De scan ziet de sleutels die er wél zijn.

    The scan sees the keys that are there.
    """
    strings = json.loads(STRINGS.read_text(encoding="utf-8"))
    assert len(strings.get("options", {}).get("step", {})) > 10
    assert len(strings.get("selector", {})) > 5
    assert strings.get("exceptions") and strings.get("entity")


def test_the_guard_catches_a_dead_key() -> None:
    """Een verzonnen dode sleutel valt op; de producenten blijven groen.

    An invented dead key stands out; the producers stay green.
    """
    strings = {
        "config": {"step": {"user": {"data": {"name": "Name"}}}},
        "exceptions": {"some_code": "text"},
        "issues": {"some_issue": {"title": "t"}},
        "selector": {"save_exit": {"options": {"keep": "k"}}, "weekday": {"options": {}}},
        "entity": {"sensor": {"last_decision": {"name": "n"}}},
        "services": {"evaluate": {"name": "e"}},
    }
    source = (
        "async def async_step_user(...):\n"
        '    ... = "name"\n'
        '    ... = "some_code"\n'
        '    ... = "some_issue"\n'
        '    ... = "weekday"\n'
        '    _attr_translation_key = "last_decision"\n'
    )
    icons = {"entity": {"sensor": {"last_decision": {"default": "mdi:x"}}}}
    dead = dead_keys(strings, source, icons, "evaluate:")
    assert dead == ["selector.save_exit"]
