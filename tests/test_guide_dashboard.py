"""De dashboardsectie van de zes gidsen, als geheel.

De gidsentest hiernaast meet de koppen, de interfacewoorden en de entiteit-ID's;
wat daar buiten viel is het dashboardvoorbeeld zelf. Daardoor kon één gids de
kaart-URL, de installatiestap of een veld in het YAML-voorbeeld kwijtraken
zonder dat er iets rood werd. Deze test houdt de zes secties bij elkaar: hij
zoekt per gids de sectie met de timerkaart, haalt het YAML-blok eruit en parseert
dat met `yaml.safe_load` — het echte gereedschap, geen tekstpatroon — en eist dat
hetzelfde voorbeeld in alle zes staat.

Wat hier vastligt, per taal:

* het blok is één `vertical-stack`;
* er zit een kaart `custom:simple-timer-card` in;
* er is een `tap_action` op `climate_director.set_override` met `zone_id`,
  `hvac_mode`, `minutes` en `when_done` in de `data`;
* er is een knop op `climate_director.clear_override`;
* de kaart-URL staat letterlijk in de sectie, met de twee manieren om de kaart
  te installeren (`config/www`, `/local/simple-timer-card.js`, `module`);
* de entiteit in de kaart is de vertaalde slug van díe taal: dezelfde
  `slugify` die Home Assistant gebruikt op de vertaalde naam van de
  eindtijdsensor, met de zone ingevuld.

De sectie wordt herkend aan de kaart zelf en niet aan een handlijst van zes
koppen: verandert een kop, dan blijft deze test werken. De prijs is dat een gids
zonder kaart geen sectie meer heeft, en dat is precies wat er dan gemeld wordt.

The dashboard section of the six guides, as a whole.

The guide test beside this one measures the headers, the interface words and the
entity ids; what fell outside it is the dashboard example itself. So one guide
could lose the card URL, the installation step or a field in the YAML example
without anything turning red. This test keeps the six sections together: it finds
the section with the timer card per guide, takes the YAML block out and parses it
with `yaml.safe_load` — the real tool, not a text pattern — and demands the same
example in all six.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from test_guide_inventory import _slug_pattern

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "docs" / "install"

LANGUAGES = ("en", "nl", "de", "es", "fr", "ar")

#: De kaart waar het hier om gaat, en de plek waar hij vandaan komt.
#:
#: The card this is about, and where it comes from.
CARD = "simple-timer-card"
CARD_TYPE = "custom:simple-timer-card"
CARD_URL = "https://github.com/eyalgal/simple-timer-card"

#: De zone die het voorbeeld in alle zes gidsen gebruikt.
#:
#: The zone the example uses in all six guides.
ZONE = "slaapkamer"

SET_OVERRIDE = "climate_director.set_override"
CLEAR_OVERRIDE = "climate_director.clear_override"

#: De velden die de startknop meegeeft. Zonder `minutes` en `when_done` is het
#: geen override met looptijd meer maar een gewone overdracht.
#:
#: The fields the start button passes. Without `minutes` and `when_done` it is no
#: longer an override with a run time but an ordinary hand-over.
REQUIRED_FIELDS = ("zone_id", "hvac_mode", "minutes", "when_done")

#: De twee manieren om de kaart te installeren, met het woord dat de
#: dashboardresource tot een module maakt.
#:
#: The two ways to install the card, with the word that makes the dashboard
#: resource a module.
INSTALL_WORDS = ("config/www", "/local/simple-timer-card.js", "module")


def guide_sections(language: str) -> list[list[str]]:
    """De gids in `## `-secties, zonder de kop zelf.

    The guide split into `## ` sections, without the header itself.
    """
    lines = (INSTALL / f"{language}.md").read_text(encoding="utf-8").splitlines()
    sections: list[list[str]] = []
    current: list[str] | None = None
    for line in lines:
        if line.startswith("## "):
            current = []
            sections.append(current)
            continue
        if current is not None:
            current.append(line)
    return sections


def dashboard_section(language: str) -> list[str] | None:
    """De sectie die over de timerkaart gaat, of `None`.

    The section about the timer card, or `None`.
    """
    for section in guide_sections(language):
        if any(CARD in line for line in section):
            return section
    return None


def yaml_blocks(section: list[str]) -> list[str]:
    """De inhoud van elk ```yaml-blok in een sectie.

    The contents of every ```yaml block in a section.
    """
    blocks: list[str] = []
    inside = False
    current: list[str] = []
    for line in section:
        stripped = line.strip()
        if not inside and stripped in ("```yaml", "```yml"):
            inside = True
            current = []
            continue
        if inside and stripped == "```":
            inside = False
            blocks.append("\n".join(current))
            continue
        if inside:
            current.append(line)
    return blocks


def mappings(node: object) -> list[dict]:
    """Elke mapping in een geparseerde YAML-boom, ook de geneste.

    Every mapping in a parsed YAML tree, nested ones included.
    """
    found: list[dict] = []
    if isinstance(node, dict):
        found.append(node)
        for value in node.values():
            found += mappings(value)
    elif isinstance(node, list):
        for value in node:
            found += mappings(value)
    return found


def expected_entity_slug(language: str) -> str:
    """De slug van de eindtijdsensor van die taal, met de zone ingevuld.

    Dezelfde helper als de slugbewaking in `test_guide_inventory.py` - HA's eigen
    `slugify` op de vertaalde naam - alleen is `{zone}` hier de zone uit het
    voorbeeld, want het dashboard toont één concrete kaart en geen patroon.

    The same helper as the slug guard in `test_guide_inventory.py` - HA's own
    `slugify` on the translated name - only `{zone}` is the example's zone here,
    because the dashboard shows one concrete card rather than a pattern.
    """
    return _slug_pattern(language, "sensor", "zone_override_ends").replace("<zone>", ZONE)


def findings(language: str) -> list[str]:
    """Alles wat er in de dashboardsectie van deze taal niet klopt.

    Everything that is wrong in this language's dashboard section.
    """
    problems: list[str] = []
    section = dashboard_section(language)
    if section is None:
        return [f"{language}: geen enkele sectie noemt {CARD}"]
    text = "\n".join(section)

    blocks = yaml_blocks(section)
    if len(blocks) != 1:
        problems.append(f"{language}: verwacht precies één ```yaml-blok, vond er {len(blocks)}")
    for block in blocks:
        document = yaml.safe_load(block)
        if not isinstance(document, dict) or document.get("type") != "vertical-stack":
            problems.append(f"{language}: het YAML-blok is geen `vertical-stack`")

        cards = document.get("cards") if isinstance(document, dict) else None
        if not isinstance(cards, list):
            problems.append(f"{language}: het YAML-blok heeft geen `cards`-lijst")
            cards = []

        if not any(isinstance(card, dict) and card.get("type") == CARD_TYPE for card in cards):
            problems.append(f"{language}: geen kaart van het type {CARD_TYPE}")

        performers = [
            mapping.get("perform_action")
            for mapping in mappings(document)
            if "perform_action" in mapping
        ]
        if SET_OVERRIDE not in performers:
            problems.append(f"{language}: geen aanroep van {SET_OVERRIDE}")
        if CLEAR_OVERRIDE not in performers:
            problems.append(f"{language}: geen knop op {CLEAR_OVERRIDE}")

        for mapping in mappings(document):
            if mapping.get("perform_action") != SET_OVERRIDE:
                continue
            data = mapping.get("data")
            if not isinstance(data, dict):
                problems.append(f"{language}: de aanroep van {SET_OVERRIDE} heeft geen `data`")
                continue
            for field in REQUIRED_FIELDS:
                if field not in data:
                    problems.append(
                        f"{language}: `{field}` ontbreekt in de aanroep van {SET_OVERRIDE}"
                    )

        sensor_entities = [
            entry["entity"]
            for card in cards
            if isinstance(card, dict)
            for entry in card.get("entities") or []
            if isinstance(entry, dict) and str(entry.get("entity", "")).startswith("sensor.")
        ]
        if not sensor_entities:
            problems.append(f"{language}: de timerkaart noemt geen sensorentiteit")
        slug = expected_entity_slug(language)
        for entity in sensor_entities:
            if not entity.endswith(f"_{slug}"):
                problems.append(
                    f"{language}: de kaart noemt {entity!r}, terwijl de vertaalde naam op "
                    f"`sensor.*_{slug}` uitkomt"
                )

    if CARD_URL not in text:
        problems.append(f"{language}: de kaart-URL {CARD_URL} staat niet in de sectie")
    for word in INSTALL_WORDS:
        if word not in text:
            problems.append(f"{language}: de installatiestap noemt {word!r} niet")
    return problems


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_dashboard_example_is_the_same_in_every_guide(language: str) -> None:
    """De dashboardsectie van deze taal is compleet en gelijk aan de andere vijf.

    This language's dashboard section is complete and equal to the other five.
    """
    problems = findings(language)
    assert not problems, "de dashboardsectie loopt weg:\n" + "\n".join(problems)


def test_all_six_guides_are_read() -> None:
    """De bewaking leest zes echte bestanden, niet een lege of verkeerde.

    The guard reads six real files, not an empty or wrong one.
    """
    for language in LANGUAGES:
        path = INSTALL / f"{language}.md"
        assert path.exists(), f"{path} niet gevonden"
        assert dashboard_section(language) is not None, f"{language}: geen dashboardsectie"
