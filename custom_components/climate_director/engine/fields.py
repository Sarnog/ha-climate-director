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
    FieldSpec("holiday_keyword", "text", required=False, target="holiday_keyword"),
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
    FieldSpec("precipitation_states", "states_text", target="precipitation.states"),
    FieldSpec(
        "precipitation_grace",
        "number",
        default=900,
        target="precipitation.grace",
        unit="minutes",
    ),
    FieldSpec("shadow_mode", "bool", default=None, target=None),
)

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
