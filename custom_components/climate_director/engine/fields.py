"""Declaratieve veldtabel voor het instellingenscherm.

Declarative field table for the settings screen.

Eén plek die zegt welke velden het instellingenscherm draagt: naam, type,
standaard, vertaalsleutel en doel in het opgeslagen model. `schemas.py` bouwt
er het formulier uit en `engine/serialise.py` leest en schrijft er de
`gates`-sectie mee. De tabel woont in `engine/`, dus hij bevat geen selectors
en geen `vol.Schema`; die vertaling hoort bij `schemas.py`.

One place that says which fields the settings screen carries: name, type,
default, translation key and target in the stored model. `schemas.py` builds
the form from it and `engine/serialise.py` reads and writes the `gates` section
with it. The table lives in `engine/`, so it contains no selectors and no
`vol.Schema`; that translation belongs to `schemas.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import SourceRole


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """Eén veld van het instellingenscherm, als data die beide kanten lezen.

    One settings-screen field, as data both sides read.
    """

    key: str
    """Naam in het formulier en in `strings.json` / translations."""

    kind: str
    """Wat voor veld het is: `bool`, `text`, `time`, `entity`, `choice`, ..."""

    required: bool = True
    """`vol.Required` met standaard, of `vol.Optional` met suggestie."""

    default: Any = None
    """Standaardwaarde aan de opslagkant (niet per se de vorm van het formulier)."""

    translation_key: str | None = None
    """Sleutel van de keuzelijst in de selectorvertalingen, voor `choice`."""

    target: str | None = None
    """Puntpad in de opgeslagen installatie, bijvoorbeeld `gates.require_awake`.

    `None` betekent: dit veld hoort niet in de installatie maar in de
    bedieningstoestand (bijvoorbeeld `shadow_mode`).
    """

    options: tuple[str, ...] = ()
    """De toegestane waarden van een keuzeveld, in de volgorde van het scherm."""

    domain: str | tuple[str, ...] = ()
    """Domein(en) van een entiteitsselector."""

    multiple: bool = False
    """Of een entiteitsselector meerdere waarden toelaat."""

    unit: str | None = None
    """De maat van een getalveld: `temperature`, `delta_celsius`, `minutes`,
    `minutes_or_off`, `seconds` of `rank`."""

    hook: str | None = None
    """De naam van de eigenzinnige behandeling die dit veld bij het opslaan krijgt.

    De opslagkant is generiek: elke rij gaat naar haar `target`-pad. Een enkel
    veld wijkt daar bewust van af — de zomermaanden volgen een halfrondkeuze, de
    neerslagstanden komen als komma-lijst binnen, het vakantietrefwoord wordt
    getrimd, en de schaduwmodus hoort in de bedieningstoestand en niet in de
    installatie. Die uitzonderingen staan hier als naam, zodat ze zichtbaar in
    de tabel staan in plaats van als tak in een stapmethode te verdwijnen.

    The name of the idiosyncratic treatment this field gets when saved. The
    storage side is generic: every row goes to its `target` path. A few fields
    deliberately differ — the summer months follow a hemisphere choice, the
    precipitation states arrive as a comma list, the holiday keyword is trimmed,
    and shadow mode belongs in the control state rather than in the installation.
    Those exceptions sit here as a name, so they show up in the table instead of
    disappearing into a branch of a step method.
    """


def target_key(field: FieldSpec) -> str:
    """Geef het laatste paddeel van `field.target`, de sleutel in de opslag.

    Return the last path component of `field.target`, the key in storage.
    """
    assert field.target is not None, f"veld {field.key} heeft geen doel in de installatie"
    return field.target.split(".")[-1]


#: Het instellingenscherm, in de volgorde waarin het getoond wordt. De
#: afsluitregel (`when_done`) staat niet hier maar in `schemas.settings`: die is
#: voor élk scherm hetzelfde en hoort bij de vorm, niet bij de velden.
#:
#: The settings screen, in display order. The exit row (`when_done`) is not here
#: but in `schemas.settings`: it is the same for every screen and belongs to the
#: shape, not to the fields.
SETTINGS_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        "outdoor_sensor",
        "entity",
        required=False,
        target="outdoor_sensor",
        domain=("sensor", "weather"),
    ),
    FieldSpec(
        "outdoor_hysteresis",
        "number",
        default=0.5,
        target="outdoor_hysteresis",
        unit="delta_celsius",
    ),
    FieldSpec(
        "heating_layout",
        "choice",
        default="per_zone",
        translation_key="heating_layout",
        target="heating_layout",
        options=("central", "per_zone"),
    ),
    FieldSpec(
        "season_source",
        "choice",
        default="auto",
        translation_key="season_source",
        target="seasons.source",
        options=("auto", "entity", "summer", "winter"),
    ),
    FieldSpec(
        "season_entity",
        "entity",
        required=False,
        target="seasons.entity_id",
        domain=("sensor", "input_select", "select", "season"),
    ),
    FieldSpec(
        "hemisphere",
        "hemisphere",
        default="north",
        translation_key="hemisphere",
        target="seasons.summer_months",
        options=("north", "south"),
        hook="summer_months",
    ),
    FieldSpec("require_awake", "bool", default=True, target="gates.require_awake"),
    FieldSpec("require_schedule", "bool", default=False, target="gates.require_schedule"),
    FieldSpec(
        "holiday_calendars",
        "entity",
        required=False,
        target="holiday_calendars",
        domain="calendar",
        multiple=True,
    ),
    FieldSpec("holiday_keyword", "text", required=False, target="holiday_keyword", hook="trim"),
    FieldSpec(
        "max_precondition",
        "number",
        default=7200,
        target="gates.max_precondition",
        unit="minutes",
    ),
    FieldSpec("guest_start", "time", required=False, target="gates.guest_window.start"),
    FieldSpec("guest_end", "time", required=False, target="gates.guest_window.end"),
    FieldSpec(
        "guest_days",
        "weekdays",
        required=False,
        target="gates.guest_window.weekdays",
    ),
    FieldSpec(
        "stuck_after",
        "number",
        default=900,
        target="stuck_after",
        unit="minutes_or_off",
    ),
    FieldSpec(
        "precipitation_source",
        "entity",
        required=False,
        target="precipitation.source",
        domain=("weather", "sensor"),
    ),
    FieldSpec(
        "precipitation_states",
        "states_text",
        target="precipitation.states",
        hook="states",
    ),
    FieldSpec(
        "precipitation_grace",
        "number",
        default=900,
        target="precipitation.grace",
        unit="minutes",
    ),
    FieldSpec("shadow_mode", "bool", default=None, target=None, hook="control_state"),
)

#: Het bronscherm: één apparaat dat een zone kan bedienen. De afsluitregel
#: (`when_done`) en de verwijderregel (`delete`) staan niet hier maar in
#: `schemas.source`: die horen bij de vorm en bij de navigatie, niet bij de
#: velden. Het toekennen van een `source_id` blijft ook met de hand — dat is
#: identiteit, geen veld.
#:
#: The source screen: one appliance able to serve a zone. The exit row
#: (`when_done`) and the delete row (`delete`) are not here but in
#: `schemas.source`: they belong to the shape and to the navigation, not to the
#: fields. Assigning a `source_id` likewise stays by hand — that is identity,
#: not a field.
#:
#: `covers_zones` is de eerste rij met veldtype `zones`: een keuzelijst over de
#: zones van deze installatie. De tabel noemt alleen het type; wélke zones er in
#: die lijst staan weet `schema_fields.py`, want dat is de vorm van het scherm en
#: niet de betekenis van het veld.
#:
#: `covers_zones` is the first row of field kind `zones`: a picker over this
#: installation's zones. The table only names the kind; which zones sit in that
#: list is up to `schema_fields.py`, because that is the shape of the screen and
#: not the meaning of the field.
SOURCE_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("name", "text", required=False, target="name"),
    FieldSpec("entity_id", "entity", required=False, target="entity_id", domain="climate"),
    FieldSpec(
        "role",
        "choice",
        default=SourceRole.HEAT_COOL.value,
        translation_key="source_role",
        target="role",
        options=tuple(item.value for item in SourceRole),
    ),
    FieldSpec("autostart", "bool", default=True, target="autostart"),
    FieldSpec("priority", "number", default=0, target="priority", unit="rank"),
    FieldSpec(
        "outdoor_min",
        "number",
        required=False,
        target="outdoor.minimum",
        unit="temperature",
    ),
    FieldSpec(
        "outdoor_max",
        "number",
        required=False,
        target="outdoor.maximum",
        unit="temperature",
    ),
    FieldSpec(
        "min_cycle_time",
        "number",
        required=False,
        target="min_cycle_time",
        unit="seconds",
    ),
    FieldSpec("covers_zones", "zones", required=False, target="covers_zones"),
    FieldSpec(
        "takeover_delay",
        "number",
        default=300,
        target="takeover_delay",
        unit="minutes",
    ),
)

#: Per veldtabel het model waaraan haar `target`-paden hangen, en de functie in
#: `engine/serialise.py` die dat model naar opgeslagen data schrijft. Een
#: typefout in een `target` is anders stil: het scherm toont de standaard en
#: schrijft die bij het volgende opslaan terug. `tests/test_field_tables.py`
#: loopt over élke tabel in dit bestand en eist een regel hier, zodat een derde
#: tabel niet ongemerkt buiten de bewaking kan vallen.
#:
#: Per field table the model its `target` paths hang on, and the function in
#: `engine/serialise.py` that writes that model to stored data. A typo in a
#: `target` is silent otherwise: the screen shows the default and writes it back
#: on the next save. `tests/test_field_tables.py` walks every table in this file
#: and demands a row here, so a third table cannot quietly fall outside the
#: guard.
TABLE_ROOTS: dict[str, tuple[str, str]] = {
    "SETTINGS_FIELDS": ("DirectorConfig", "config_to_dict"),
    "GATES_FIELDS": ("DirectorConfig", "config_to_dict"),
    "GATES_FLAT_FIELDS": ("DirectorConfig", "config_to_dict"),
    "GUEST_WINDOW_FIELDS": ("DirectorConfig", "config_to_dict"),
    "SOURCE_FIELDS": ("Source", "_source_to_dict"),
}


#: De instellingsvelden die in de `gates`-sectie van de installatie wonen.
#:
#: The settings fields that live in the installation's `gates` section.
GATES_FIELDS = tuple(
    field for field in SETTINGS_FIELDS if field.target and field.target.startswith("gates.")
)

#: De velden van het gastenvenster, als bladeren onder `gates.guest_window.*`.
#:
#: The guest-window fields, as leaves under `gates.guest_window.*`.
GUEST_WINDOW_FIELDS = tuple(
    field for field in GATES_FIELDS if field.target.startswith("gates.guest_window.")
)

#: De platte `gates`-velden (alles behalve het gastenvenster).
#:
#: The flat `gates` fields (everything but the guest window).
GATES_FLAT_FIELDS = tuple(
    field for field in GATES_FIELDS if not field.target.startswith("gates.guest_window.")
)
