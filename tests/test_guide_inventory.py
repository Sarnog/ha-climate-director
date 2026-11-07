"""De zichtbare inventaris uit de bron staat in alle zes de gidsen.

The visible inventory from the source stands in all six guides.

Een nieuwe entiteit, een nieuwe actie of een nieuwe reparatiemelding hoort niet
stilletjes buiten de handleidingen te blijven. Deze test leest de inventaris
daarom uit de **bron** — `icons.json` voor de entiteiten, `services.yaml` voor de
acties, en `problems.py` via een AST voor de meldingen — en eist per gids dat
elk item er met de interfacewoorden in staat: de entiteit onder de id die Home
Assistant uit zijn vertaalde naam afleidt, de actie onder
`climate_director.<naam>`, en de melding onder de titel die de gebruiker in
*Reparaties* ziet (met de plaatshouders als `<naam>`).

De velden van de options-flowschermen worden al op dezelfde manier bewaakt door
`tests/test_install_guides.py`, dat zijn veldenkaart uit de schema's leest en per
label eist dat het in de tekst staat. Dat werk wordt hier niet overgedaan.

A new entity, a new action or a new repair notice should not quietly stay out of
the manuals. This test therefore reads the inventory from the **source** —
`icons.json` for the entities, `services.yaml` for the actions, and `problems.py`
through an AST for the notices — and demands per guide that every item stands
there in the interface's own words: the entity under the id Home Assistant
derives from its translated name, the action under `climate_director.<name>`, and
the notice under the title the user sees in *Repairs* (with its placeholders as
`<name>`).

The options-flow screens' fields are already guarded the same way by
`tests/test_install_guides.py`, which reads its field map from the schemas and
demands per label that it stands in the text. That work is not redone here.

Dekking: de zichtbare inventaris uit `icons.json`, `services.yaml` en
`problems.py`, met de vertaalde namen uit `translations/<taal>.json`, tegen de
zes gidsen. Van een melding telt de titel mee als hij in een alinea staat met
genoeg tekst erachter, en de vervolgregels van een afgebroken bullet tellen
daarbij mee. Niet gedekt: de velden en labels van de options-flowschermen
(`tests/test_install_guides.py`), het dashboardvoorbeeld
(`tests/test_guide_dashboard.py`), de inhoudsopgave (`tests/test_guide_toc.py`)
en de vraag of de uitleg zelf klopt.

Coverage: the visible inventory from `icons.json`, `services.yaml` and
`problems.py`, with the translated names from `translations/<language>.json`,
against the six guides. For a notice, the title counts when it stands in a
paragraph with enough text behind it, and the continuation lines of a wrapped
bullet count along. Not covered: the fields and labels of the options-flow
screens (`tests/test_install_guides.py`), the dashboard example
(`tests/test_guide_dashboard.py`), the table of contents
(`tests/test_guide_toc.py`) and whether the explanation itself is right.
"""

from __future__ import annotations

import re

import pytest
from guide_helpers import INSTALL, LANGUAGES, missing, slug_pattern, translation


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_visible_feature_stands_in_every_guide(language: str) -> None:
    """Elke entiteit, actie en melding staat met de interfacewoorden in de gids."""
    assert not missing(language)


#: Elke vermelding van een entiteitspatroon in een gids. Wat tussen de haken staat
#: hoort bij de plaatshouder (`<zone>`, `<opening>`, …) en blijft staan, zodat de
#: vergelijking de vertaalde slug raakt.
#:
#: Every mention of an entity pattern in a guide. What stands between the brackets
#: belongs to the placeholder (`<zone>`, `<opening>`, …) and stays, so the
#: comparison hits the translated slug.
SLUG_MENTION = re.compile(r"\b(switch|sensor|binary_sensor|button|number|select)\.([a-z0-9_*<>]+)")

#: De zes domeinen waarvan deze bewaking de slugs leest. Ze doen alle zes mee: een
#: slug van het ene domein achter het andere is een gemeten fout, en
#: die fout bestaat net zo goed voor `binary_sensor`, `button`, `number` en
#: `select`. Alle zes staan er, zodat de bewaking niet opnieuw aan een lijstje
#: hangt waar het volgende domein naast valt.
#:
#: The six domains this guard reads the slugs of. All six take part: a slug of one
#: domain behind another is a measured mistake, and that mistake exists
#: just as well for `binary_sensor`, `button`, `number` and `select`. All six stand
#: here, so the guard does not hang on a list the next domain can fall beside.
SLUG_DOMAINS = ("switch", "sensor", "binary_sensor", "button", "number", "select")

#: Een plaatshouder in een slug (`<zone>`, `<opening>`, `<entity>`).
#:
#: A placeholder in a slug (`<zone>`, `<opening>`, `<entity>`).
PLACEHOLDER = re.compile(r"<[a-z_]+>")


def _slug_regex(language: str, domain: str, key: str) -> re.Pattern[str]:
    """Een vertaalde slug als patroon, waarin een plaatshouder ook een naam mag zijn.

    De gidsen schrijven naast `<zone>` ook een voorbeeld als `slaapkamer`; beide
    horen te kloppen. Alles buiten de plaatshouder staat letterlijk vast.

    A translated slug as a pattern, in which a placeholder may also be a real
    name. The guides write an example such as `slaapkamer` next to `<zone>`; both
    should match. Everything outside the placeholder stands literally.
    """
    parts = re.split(r"(<[a-z_]+>)", slug_pattern(language, domain, key))
    return re.compile(
        "".join(
            rf"(?:{part}|[a-z0-9]+(?:_[a-z0-9]+)*)"
            if PLACEHOLDER.fullmatch(part)
            else re.escape(part)
            for part in parts
        )
        + r"\Z"
    )


def _translated_slugs(language: str) -> dict[str, list[re.Pattern[str]]]:
    """Elke slug die deze taal per domein werkelijk uit zijn vertaling afleidt.

    Every slug this language really derives per domain from its translation.
    """
    entity = translation(language)["entity"]
    return {
        domain: [_slug_regex(language, domain, key) for key in entity.get(domain, {})]
        for domain in SLUG_DOMAINS
    }


def _mention_problem(domain: str, rest: str, slugs: dict[str, list[re.Pattern[str]]]) -> str | None:
    """Of deze vermelding een bestaande entiteit kan aanduiden.

    `rest` is wat in de gids achter `switch.` of `sensor.` staat. De gids schrijft
    een voorvoegsel (`*`, een plaatshouder of de naam van de installatie) en
    daarna de slug; welk voorvoegsel dat is hangt van de installatie af. Daarom
    probeert deze functie elke knip op een `_`: is de rest achter de eerste knip
    een vertaalde slug van **dit** domein, dan klopt de vermelding. Is die rest
    een slug van een ánder domein, dan noemt de gids een entiteit die niet bestaat
    — een gemeten fout (`switch.*_nhy_tjwz_<zone>`). Vindt geen enkele
    knip een slug, dan is de slug zelf verkeerd. De oude regel zocht alleen
    `domein.*_`, en daarmee glipte elke andere schrijfwijze van het voorvoegsel
    erlangs (gemeten: `switch.climate_director_nhy_tjwz_<zone>` bleef groen).

    Whether this mention can point at an existing entity. `rest` is what
    stands behind `switch.` or `sensor.` in the guide. The guide writes a prefix
    (`*`, a placeholder or the installation's name) and then the slug; which prefix
    that is depends on the installation. This function therefore tries every split
    on a `_`: if the remainder behind the first split is a translated slug of
    **this** domain, the mention is right. If that remainder is a slug of another
    domain, the guide names an entity that does not exist — a measured
    mistake (`switch.*_nhy_tjwz_<zone>`). When no split yields a slug, the slug
    itself is wrong. The old rule only looked for `domain.*_`, and every other
    spelling of the prefix slipped past it (measured:
    `switch.climate_director_nhy_tjwz_<zone>` stayed green).
    """
    for index, character in enumerate(rest):
        if character != "_":
            continue
        remainder = rest[index + 1 :]
        if not remainder:
            continue
        if any(pattern.fullmatch(remainder) for pattern in slugs.get(domain, ())):
            return None
        for other, patterns in slugs.items():
            if other != domain and any(pattern.fullmatch(remainder) for pattern in patterns):
                return f"slug van {other}"
    return "geen vertaalde slug"


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_entity_id_a_guide_names_comes_from_its_translation(language: str) -> None:
    """Elke entiteit-id in de gids komt uit de vertaling van die taal.

    Home Assistant leidt de entiteit-id af uit de vertaalde naam, dus een gids die
    de slug van een ánder domein noemt — de sensorslug achter `switch.` — stuurt de
    lezer naar een entiteit die niet bestaat. Gemeten: de Arabische gids noemde
    `switch.*_nhy_tjwz_<zone>` terwijl de schakelaar `switch.*_tjwz_<zone>`
    heet; de andere vijf gidsen klopten. De schrijfwijze van het voorvoegsel
    doet er niet toe: de test knipt op elke `_`, accepteert `*`, een
    plaatshouder en een echte naam, en toetst zes domeinen. De test loopt regel
    voor regel, zodat de melding het bestand én de regel noemt.

    Every entity id in the guide comes from that language's translation.
    Home Assistant derives the entity id from the translated name, so a
    guide naming another domain's slug — the sensor slug after `switch.` — sends
    the reader to an entity that does not exist. Measured: the Arabic guide
    named `switch.*_nhy_tjwz_<zone>` while the switch is called
    `switch.*_tjwz_<zone>`; the other five guides were right. The spelling of
    the prefix does not matter: the test splits on every `_`,
    accepts `*`, a placeholder and a real name, and covers six domains. The test
    walks line by line, so the message names both the file and the line.
    """
    slugs = _translated_slugs(language)
    text = (INSTALL / f"{language}.md").read_text(encoding="utf-8")
    offenders: list[str] = []
    for number, line in enumerate(text.splitlines(), 1):
        for domain, rest in SLUG_MENTION.findall(line):
            if rest == "*":
                continue
            problem = _mention_problem(domain, rest, slugs)
            if problem is not None:
                offenders.append(f"{language}.md:{number}: {domain}.{rest} ({problem})")
    assert not offenders, (
        "deze slugs komen niet uit de vertaling van deze taal, dus de gids noemt "
        "een entiteit die niet bestaat: " + "; ".join(offenders)
    )
