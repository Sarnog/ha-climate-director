"""Config flow en options flow van Climate Director.

Climate Director's config flow and options flow.

De installatie wordt volledig via de UI opgebouwd en als één dict in
`entry.options[CONF_INSTALLATION]` bewaard - hetzelfde formaat dat
`engine.serialise` leest. Deze module bevat daarom geen kennis van klimaatregels,
alleen van formulieren.

The installation is built entirely through the UI and stored as one dict in
`entry.options[CONF_INSTALLATION]` - the same format `engine.serialise` reads.
This module therefore holds no knowledge of climate rules, only of forms.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.util import slugify

from . import problems, texts
from .const import CONF_INSTALLATION, CONF_SHADOW_MODE, DEFAULT_SHADOW_MODE, DOMAIN
from .coordinator import ClimateDirectorEntry
from .engine import validate
from .engine.models import (
    ConflictPolicy,
    HeatingLayout,
    PrecipitationSettings,
    Season,
    SeasonSettings,
    SeasonSource,
    SourceRole,
    ZoneGate,
)
from .engine.serialise import config_from_dict

CONF_NAME = "name"

_ADD = "add_new"
_BACK = "back_to_menu"
_EXIT = "when_done"
_EXIT_KEEP = "keep"
_EXIT_DROP = "discard"

_ADD_FALLBACK = {
    "zone": "+ Add zone",
    "source": "+ Add source",
    "circuit": "+ Add circuit",
    "generator": "+ Add heat source",
    "resident": "+ Add resident",
    "window": "+ Add schedule",
    "opening": "+ Add opening",
    "exclusive": "+ Add group",
    "quiet": "+ Add quiet window",
}

#: Maandag is 0, gelijk aan `datetime.weekday()`, dat de engine ook gebruikt.
#: Monday is 0, matching `datetime.weekday()`, which the engine uses too.
_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

#: Zomermaanden per halfrond, als maandnummers 1-12. De engine telt
#: april-september als zomer; wie op het zuidelijk halfrond woont, krijgt
#: oktober-maart. De noordelijke standaard komt uit de engine, zodat hij hier
#: niet stilletjes uit de pas kan lopen.
#:
#: Summer months per hemisphere, as month numbers 1-12. The engine counts
#: April-September as summer; the southern hemisphere gets October-March. The
#: northern default comes from the engine, so it cannot drift apart here.
_SUMMER_NORTH = SeasonSettings().summer_months
_SUMMER_SOUTH = frozenset({1, 2, 3, 10, 11, 12})


def _hemisphere(months: Any) -> str:
    """Return which hemisphere a stored summer-months set describes.

    Alles wat niet precies het zuidelijke rijtje is, telt als noordelijk. Dat is
    de veilige kant: een handmatig bewerkte of half geschreven waarde valt
    terug op de standaard in plaats van de wizard te laten struikelen.

    Anything that is not exactly the southern row counts as northern. That is
    the safe side: a hand-edited or half-written value falls back on the
    default rather than tripping the wizard up.
    """
    try:
        return "south" if frozenset(int(month) for month in months) == _SUMMER_SOUTH else "north"
    except (TypeError, ValueError):
        return "north"


_TEMPERATURE = selector.NumberSelector(
    selector.NumberSelectorConfig(min=-20, max=40, step=0.5, mode=selector.NumberSelectorMode.BOX)
)
_BAND = selector.NumberSelector(
    selector.NumberSelectorConfig(min=0, max=10, step=0.1, mode=selector.NumberSelectorMode.BOX)
)
_MINUTES_OR_OFF = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=0, max=240, step=1, unit_of_measurement="min", mode=selector.NumberSelectorMode.BOX
    )
)

_MINUTES = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=1, max=480, step=1, unit_of_measurement="min", mode=selector.NumberSelectorMode.BOX
    )
)

_SECONDS = selector.NumberSelector(
    selector.NumberSelectorConfig(min=0, max=3600, step=1, mode=selector.NumberSelectorMode.BOX)
)
_RANK = selector.NumberSelector(
    selector.NumberSelectorConfig(min=0, max=99, step=1, mode=selector.NumberSelectorMode.BOX)
)
_CLIMATE = selector.EntitySelector(selector.EntitySelectorConfig(domain="climate"))
_CLIMATE_MULTI = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="climate", multiple=True)
)
_TEXT = selector.TextSelector()
_TIME = selector.TimeSelector()


def _choices(values: list[str], key: str = "") -> selector.SelectSelector:
    """Return a dropdown over plain string values.

    Met een vertaalsleutel toont Home Assistant de vertaalde namen in plaats van
    de opgeslagen waarden. Zonder sleutel blijft het bij de waarde zelf, wat voor
    een lijst die al leesbaar is genoeg is.

    With a translation key Home Assistant shows translated names instead of the
    stored values. Without one the value itself shows, which is enough for a list
    that reads well already.
    """
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=values,
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key=key or None,
        )
    )


def _back_option() -> selector.SelectOptionDict:
    """Return the "back to the main menu" row of a picker.

    De Engelse tekst blijft als terugval staan, net als bij de toevoegregel.
    Anders dan die regel hoeft hier geen sleutel bij: de terugval luidt in elke
    lijst hetzelfde, en de vertaling hangt aan de waarde `back_to_menu`.

    The English text stays as a fallback, as with the add row. Unlike that row
    this one needs no key: the fallback reads the same in every list, and the
    translation hangs off the `back_to_menu` value.
    """
    return selector.SelectOptionDict(value=_BACK, label="< Back to the main menu")


def _missing(user_input: dict[str, Any], *fields: str) -> dict[str, str]:
    """Return an error per field the user left empty.

    Die velden staan in het schema als optioneel, zodat voluptuous een half
    ingevuld formulier niet weigert vóór wij het gezien hebben. Anders kun je
    niet meer terug zodra je ergens aan begonnen bent: je zit dan vast in een
    scherm dat je alleen kunt verlaten door het af te maken, en dat is geen
    keuze maar een val.

    The fields are optional in the schema so voluptuous does not refuse a
    half-filled form before we have seen it. Otherwise there is no way back once
    you have started: you are stuck in a screen you can leave only by finishing
    it, which is not a choice but a trap.
    """
    return {field: "required" for field in fields if not _filled(user_input.get(field))}


def _filled(value: Any) -> bool:
    """Return whether a value counts as filled in.

    Alleen spaties is niet ingevuld. `vol.Required` eist dat het veld er is,
    niet dat er iets in staat, dus zonder deze regel telt een handvol spaties
    als een naam.

    Spaces alone is not filled in. `vol.Required` demands the field is there,
    not that it holds anything, so without this rule a handful of spaces counts
    as a name.
    """
    if isinstance(value, str):
        return bool(value.strip())
    return bool(value)


def _exit_row() -> selector.SelectSelector:
    """Return the row that closes a form, keeping or discarding what is on it.

    Home Assistant tekent precies één knop onder een formulier en laat een
    integratie er geen tweede bij zetten. Deze regel is daarom het dichtste bij
    een "Terug"-knop dat er is: dezelfde lijstopmaak als de keuzeschermen, zodat
    elk submenu er hetzelfde uitziet.

    Home Assistant draws exactly one button under a form and lets an integration
    add no second one. This row is therefore the closest thing to a "Back"
    button there is: the same list styling as the pickers, so every submenu
    looks alike.
    """
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                selector.SelectOptionDict(value=_EXIT_KEEP, label="Keep these changes and go back"),
                selector.SelectOptionDict(value=_EXIT_DROP, label="< Discard and go back"),
            ],
            mode=selector.SelectSelectorMode.LIST,
            translation_key="when_done",
        )
    )


def _source_options(flow: Any) -> list[selector.SelectOptionDict]:
    """Return every source in the installation, labelled by zone and appliance."""
    options: list[selector.SelectOptionDict] = []
    for zone in flow._list("zones"):
        for source in zone.get("sources") or []:
            options.append(
                selector.SelectOptionDict(
                    value=source["source_id"],
                    label=f"{zone.get('name') or zone['zone_id']} - {source['entity_id']}",
                )
            )
    return options


def _group_label(flow: Any, group: list[str]) -> str:
    """Return a readable name for one exclusive group."""
    known = {option["value"]: option["label"] for option in _source_options(flow)}
    return " + ".join(known.get(source_id, source_id) for source_id in group) or "?"


def _add_option(key: str) -> selector.SelectOptionDict:
    """Return the "add one" row of a picker.

    De Engelse tekst blijft als terugval staan: vertaalt Home Assistant de
    sleutel niet, dan staat er nog altijd iets leesbaars in plaats van niets.

    The English text stays as a fallback: if Home Assistant does not translate
    the key, something readable still shows rather than nothing.

    Een onbekende sleutel valt terug op een generieke tekst in plaats van het
    scherm op te blazen. Een terugval hoort nooit de reden te zijn dat er niets
    te zien is - dat was precies wat er misging toen hier een sleutel ontbrak.

    An unknown key falls back on generic wording rather than blowing the screen
    up. A fallback should never itself be the reason nothing shows - which is
    exactly what went wrong when a key was missing here.
    """
    return selector.SelectOptionDict(value=_ADD, label=_ADD_FALLBACK.get(key, "+ Add"))


class ClimateDirectorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create one installation; everything else happens in the options flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for a name and create an empty installation.

        De naam wordt de titel van de installatie, en die titel gaat vooraf aan
        de naam van elke entiteit die hier uit voortkomt. Leeg laten mocht, want
        `vol.Required` eist alleen dat het veld er is - en dan sta je met een
        naamloze installatie vol naamloze entiteiten.

        The name becomes the installation's title, and that title precedes the
        name of every entity that comes out of it. Leaving it empty was allowed,
        since `vol.Required` only demands the field is there - and then you end
        up with a nameless installation full of nameless entities.
        """
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _missing(user_input, CONF_NAME)
            if not errors:
                return self.async_create_entry(
                    title=user_input[CONF_NAME].strip(),
                    data={},
                    options={
                        CONF_INSTALLATION: {},
                        CONF_SHADOW_MODE: user_input[CONF_SHADOW_MODE],
                    },
                )

        return self.async_show_form(
            step_id="user",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default="Climate Director"): _TEXT,
                    vol.Required(CONF_SHADOW_MODE, default=DEFAULT_SHADOW_MODE): bool,
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ClimateDirectorEntry) -> OptionsFlow:
        """Return the options flow, where the installation is actually built."""
        return ClimateDirectorOptionsFlow()


class ClimateDirectorOptionsFlow(OptionsFlow):
    """Menu-driven editor for zones, sources, circuits, residents and openings."""

    def __init__(self) -> None:
        """Start with an empty edit cursor."""
        self._installation: dict[str, Any] = {}
        self._shadow_mode: bool | None = None
        # Elke geneste lijst krijgt een eigen cursor. Eén gedeelde cursor laat
        # een bewerking in de ene lijst de plek in de andere verzetten.
        #
        # Every nested list gets its own cursor. One shared cursor lets an edit
        # in one list move the position in another.
        self._zone_index: int | None = None
        self._source_index: int | None = None
        self._circuit_index: int | None = None
        self._priority_zone_id: str | None = None
        self._resident_index: int | None = None
        self._window_index: int | None = None
        self._index: int | None = None

    # -- ingang / entry point ------------------------------------------------

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the main menu."""
        if not self._installation:
            stored = self.config_entry.options.get(CONF_INSTALLATION) or {}
            self._installation = _deep_copy(stored)
        if self._shadow_mode is None:
            self._shadow_mode = self.config_entry.options.get(CONF_SHADOW_MODE, DEFAULT_SHADOW_MODE)

        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "settings",
                "zones",
                "circuits",
                "generators",
                "exclusives",
                "quiets",
                "residents",
                "openings",
                "save",
            ],
        )

    async def async_step_save(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Write the edited installation back to the config entry.

        Everything is written here and nowhere else. Saving a setting halfway
        through would reload the entry while the user is still editing, which
        pulls the ground out from under the flow they are standing in.
        """
        found = validate(config_from_dict(self._installation))
        if found and user_input is None:
            await texts.async_prepare(self.hass)
            return self.async_show_form(
                step_id="save",
                data_schema=vol.Schema({vol.Required(_EXIT, default=_EXIT_KEEP): _exit_row()}),
                description_placeholders={
                    "problems": "\n".join(
                        f"- {problems.readable(self.hass, item)}" for item in found
                    )
                },
            )

        if user_input is not None and user_input.get(_EXIT) == _EXIT_DROP:
            return await self.async_step_init()

        options = dict(self.config_entry.options)
        options[CONF_INSTALLATION] = self._installation
        if self._shadow_mode is not None:
            options[CONF_SHADOW_MODE] = self._shadow_mode
        return self.async_create_entry(data=options)

    # -- algemene instellingen / general settings ----------------------------

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the outdoor sensor, the season source, the gates and shadow mode."""
        if user_input is not None:
            if user_input.get(_EXIT) == _EXIT_DROP:
                return await self.async_step_init()
            # Optionele velden worden hier bewust met `or ""` / `or ()` gelezen.
            # De echte HA-interface vult een selector met een `suggested_value`
            # voor en stuurt die waarde mee bij het opslaan; alleen een
            # leeggemaakt veld komt als leeg binnen. Wie hier "afwezig = bewaren"
            # van maakt, blokkeert het leegmaken van de buitensensor en de
            # neerslagbron - een gedragswijziging, geen reparatie.
            #
            # Optional fields are deliberately read with `or ""` / `or ()`.
            # The real HA frontend pre-fills a selector with a `suggested_value`
            # and submits that value on save; only a field the user cleared
            # arrives empty. Turning this into "absent = keep" would stop users
            # from clearing the outdoor sensor and the precipitation source - a
            # behaviour change, not a repair.
            self._installation["outdoor_sensor"] = user_input.get("outdoor_sensor", "")
            self._installation["heating_layout"] = user_input["heating_layout"]
            self._installation["seasons"] = {
                "source": user_input["season_source"],
                "entity_id": user_input.get("season_entity", ""),
                "summer_months": sorted(
                    _SUMMER_SOUTH if user_input["hemisphere"] == "south" else _SUMMER_NORTH
                ),
            }
            # `gates` wordt bewust bijgewerkt in plaats van vervangen: het
            # stiltevensterscherm schrijft in dezelfde sleutel (`quiet_windows`),
            # en een compleet nieuw dict zou dat werk stilletjes wissen.
            #
            # `gates` is deliberately updated rather than replaced: the quiet
            # window screen writes into the same key (`quiet_windows`), and a
            # brand-new dict would silently erase that work.
            gates = self._installation.setdefault("gates", {})
            gates.update(
                {
                    "require_awake": user_input["require_awake"],
                    "require_schedule": user_input["require_schedule"],
                    "guest_window": {
                        "start": user_input.get("guest_start") or "",
                        "end": user_input.get("guest_end") or "",
                    },
                    "precondition_window": {
                        "start": user_input.get("precondition_start") or "",
                        "end": user_input.get("precondition_end") or "",
                    },
                    "max_precondition": int(user_input.get("max_precondition") or 0) * 60,
                }
            )
            self._installation["holiday_calendars"] = list(
                user_input.get("holiday_calendars") or ()
            )
            self._installation["stuck_after"] = int(user_input.get("stuck_after") or 0) * 60
            self._installation["outdoor_hysteresis"] = float(
                user_input.get("outdoor_hysteresis") or 0
            )
            self._installation["holiday_keyword"] = (
                user_input.get("holiday_keyword") or ""
            ).strip()
            self._installation["precipitation"] = {
                "source": user_input.get("precipitation_source") or "",
                "states": sorted(
                    {
                        item.strip()
                        for item in (user_input.get("precipitation_states") or "").split(",")
                        if item.strip()
                    }
                ),
                "grace": int(user_input.get("precipitation_grace") or 0) * 60,
            }
            self._shadow_mode = user_input[CONF_SHADOW_MODE]
            return await self.async_step_init()

        seasons = self._installation.get("seasons") or {}
        gates = self._installation.get("gates") or {}
        guest = gates.get("guest_window") or {}
        precondition = gates.get("precondition_window") or {}
        precipitation = self._installation.get("precipitation") or {}
        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "outdoor_sensor",
                        description={
                            "suggested_value": self._installation.get("outdoor_sensor") or None
                        },
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=["sensor", "weather"])
                    ),
                    vol.Required(
                        "outdoor_hysteresis",
                        default=float(self._installation.get("outdoor_hysteresis", 0.5)),
                    ): _BAND,
                    vol.Required(
                        "heating_layout",
                        default=self._installation.get(
                            "heating_layout", HeatingLayout.PER_ZONE.value
                        ),
                    ): _choices([item.value for item in HeatingLayout], "heating_layout"),
                    vol.Required(
                        "season_source", default=seasons.get("source", SeasonSource.AUTO.value)
                    ): _choices([item.value for item in SeasonSource], "season_source"),
                    vol.Optional(
                        "season_entity",
                        description={"suggested_value": seasons.get("entity_id") or None},
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=["sensor", "input_select", "select", "season"]
                        )
                    ),
                    vol.Required(
                        "hemisphere",
                        default=_hemisphere(seasons.get("summer_months")),
                    ): _choices(["north", "south"], "hemisphere"),
                    vol.Required("require_awake", default=gates.get("require_awake", True)): bool,
                    vol.Required(
                        "require_schedule", default=gates.get("require_schedule", False)
                    ): bool,
                    vol.Optional(
                        "holiday_calendars",
                        description={
                            "suggested_value": self._installation.get("holiday_calendars") or None
                        },
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="calendar", multiple=True)
                    ),
                    vol.Optional(
                        "holiday_keyword",
                        description={
                            "suggested_value": self._installation.get("holiday_keyword") or None
                        },
                    ): str,
                    # Een echte standaard en geen suggestie. Bleef het veld
                    # leeg, dan schreef de flow een leeg venster weg, en dat
                    # leest de integratie als "de hele dag" - precies het
                    # tegenovergestelde van de bedoeling, want vooruit
                    # verwarmen is het enige dat een leeg huis mag laten
                    # draaien.
                    #
                    # A real default rather than a suggestion. If the field was
                    # left empty the flow wrote an empty window, which the
                    # integration reads as "all day" - the exact opposite of
                    # the intent, since pre-conditioning is the only thing
                    # allowed to run an empty house.
                    vol.Required(
                        "precondition_start",
                        default=precondition.get("start") or "06:00:00",
                    ): _TIME,
                    vol.Required(
                        "precondition_end",
                        default=precondition.get("end") or "23:00:00",
                    ): _TIME,
                    vol.Required(
                        "max_precondition",
                        default=int(gates.get("max_precondition", 7200)) // 60,
                    ): _MINUTES,
                    vol.Optional(
                        "guest_start",
                        description={"suggested_value": guest.get("start") or None},
                    ): _TIME,
                    vol.Optional(
                        "guest_end",
                        description={"suggested_value": guest.get("end") or None},
                    ): _TIME,
                    vol.Required(
                        "stuck_after",
                        default=int(self._installation.get("stuck_after", 900)) // 60,
                    ): _MINUTES_OR_OFF,
                    vol.Optional(
                        "precipitation_source",
                        description={"suggested_value": precipitation.get("source") or None},
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=["weather", "sensor"])
                    ),
                    vol.Required(
                        "precipitation_states",
                        default=", ".join(
                            precipitation.get("states") or sorted(PrecipitationSettings().states)
                        ),
                    ): _TEXT,
                    vol.Required(
                        "precipitation_grace",
                        default=int(
                            precipitation.get(
                                "grace", PrecipitationSettings().grace.total_seconds()
                            )
                        )
                        // 60,
                    ): _MINUTES,
                    vol.Required(
                        CONF_SHADOW_MODE,
                        default=(
                            self._shadow_mode
                            if self._shadow_mode is not None
                            else DEFAULT_SHADOW_MODE
                        ),
                    ): bool,
                    vol.Required(_EXIT, default=_EXIT_KEEP): _exit_row(),
                }
            ),
        )

    # -- exclusieve groepen / exclusive groups -------------------------------

    async def async_step_exclusives(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick an exclusive group to edit, or add one."""
        groups = self._list("exclusive_groups")
        if user_input is not None:
            choice = user_input["group"]
            if choice == _BACK:
                return await self.async_step_init()
            self._index = None if choice == _ADD else int(choice)
            return await self.async_step_exclusive()

        options = [
            selector.SelectOptionDict(value=str(index), label=_group_label(self, group))
            for index, group in enumerate(groups)
        ]
        options.append(_add_option("exclusive"))
        options.append(_back_option())
        return self.async_show_form(
            step_id="exclusives",
            data_schema=vol.Schema(
                {
                    vol.Required("group", default=_ADD): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.LIST,
                            translation_key="exclusive_list",
                        )
                    )
                }
            ),
        )

    async def async_step_exclusive(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit one exclusive group: the sources that may never run together."""
        groups = self._list("exclusive_groups")
        current = groups[self._index] if self._index is not None else []

        errors: dict[str, str] = {}

        if user_input is not None:
            if user_input.get(_EXIT) == _EXIT_DROP:
                return await self.async_step_exclusives()
            if user_input.get("delete") and self._index is not None:
                groups.pop(self._index)
                self._index = None
                return await self.async_step_exclusives()
            chosen = list(user_input.get("sources") or ())
            if len(chosen) < 2:
                errors["sources"] = "too_few"
            else:
                if self._index is None:
                    groups.append(chosen)
                else:
                    groups[self._index] = chosen
                self._index = None
                return await self.async_step_exclusives()
            current = chosen

        return self.async_show_form(
            step_id="exclusive",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "sources", description={"suggested_value": list(current) or None}
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=_source_options(self),
                            mode=selector.SelectSelectorMode.LIST,
                            multiple=True,
                        )
                    ),
                    vol.Required("delete", default=False): bool,
                    vol.Required(_EXIT, default=_EXIT_KEEP): _exit_row(),
                }
            ),
        )

    # -- stiltevensters / quiet windows --------------------------------------

    def _quiet_windows(self) -> list[dict[str, Any]]:
        """Return the stored quiet windows, creating the list on first use."""
        gates = self._installation.setdefault("gates", {})
        return gates.setdefault("quiet_windows", [])

    async def async_step_quiets(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pick a quiet window to edit, add one, or go back."""
        windows = self._quiet_windows()

        if user_input is not None:
            choice = user_input["quiet"]
            if choice == _BACK:
                return await self.async_step_init()
            self._index = None if choice == _ADD else int(choice)
            return await self.async_step_quiet()

        options = [
            selector.SelectOptionDict(value=str(index), label=_window_label(window))
            for index, window in enumerate(windows)
        ]
        options.append(_add_option("quiet"))
        options.append(_back_option())
        return self.async_show_form(
            step_id="quiets",
            data_schema=vol.Schema(
                {
                    vol.Required("quiet", default=_BACK if windows else _ADD): (
                        selector.SelectSelector(
                            selector.SelectSelectorConfig(
                                options=options,
                                mode=selector.SelectSelectorMode.LIST,
                                translation_key="quiet_list",
                            )
                        )
                    )
                }
            ),
        )

    async def async_step_quiet(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Edit one quiet window: when the director may not start anything."""
        windows = self._quiet_windows()
        current = windows[self._index] if self._index is not None else {}

        if user_input is not None:
            if user_input.get(_EXIT) == _EXIT_DROP:
                return await self.async_step_quiets()
            if user_input.get("delete") and self._index is not None:
                windows.pop(self._index)
            else:
                window = {
                    "start": user_input["start"],
                    "end": user_input["end"],
                    "weekdays": ([int(day) for day in user_input.get("weekdays") or ()] or None),
                    "holiday": user_input.get("holiday", False),
                }
                if self._index is None:
                    windows.append(window)
                else:
                    windows[self._index] = window
            self._index = None
            return await self.async_step_quiets()

        weekdays = current.get("weekdays")
        return self.async_show_form(
            step_id="quiet",
            data_schema=vol.Schema(
                {
                    vol.Required("holiday", default=current.get("holiday", False)): bool,
                    vol.Required("start", default=current.get("start", "21:00:00")): _TIME,
                    vol.Required("end", default=current.get("end", "09:00:00")): _TIME,
                    vol.Optional(
                        "weekdays",
                        description={
                            "suggested_value": (
                                None if weekdays is None else [str(day) for day in weekdays]
                            )
                        },
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=str(number), label=label)
                                for number, label in enumerate(_WEEKDAYS)
                            ],
                            multiple=True,
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    ),
                    vol.Required("delete", default=False): bool,
                    vol.Required(_EXIT, default=_EXIT_KEEP): _exit_row(),
                }
            ),
        )

    # -- zones ---------------------------------------------------------------

    async def async_step_zones(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pick a zone to edit, or add one."""
        zones = self._list("zones")
        if user_input is not None:
            choice = user_input["zone"]
            if choice == _BACK:
                return await self.async_step_init()
            self._zone_index = None if choice == _ADD else int(choice)
            return await self.async_step_zone()

        options = [
            selector.SelectOptionDict(value=str(index), label=zone.get("name") or zone["zone_id"])
            for index, zone in enumerate(zones)
        ]
        options.append(_add_option("zone"))
        options.append(_back_option())
        return self.async_show_form(
            step_id="zones",
            data_schema=vol.Schema(
                {
                    vol.Required("zone", default=_ADD): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.LIST,
                            translation_key="zone_list",
                        )
                    )
                }
            ),
        )

    async def async_step_zone(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Edit one zone's comfort settings."""
        zones = self._list("zones")
        current = zones[self._zone_index] if self._zone_index is not None else {}
        stored_id = current.get("zone_id") if self._zone_index is not None else None

        errors: dict[str, str] = {}

        if user_input is not None:
            if user_input.get(_EXIT) == _EXIT_DROP:
                return await self.async_step_zones()
            if not user_input.get("delete"):
                errors = _missing(user_input, "indoor_sensor")
            if errors:
                current = {**current, **user_input}

        if user_input is not None and not errors:
            if user_input.get("delete") and self._zone_index is not None:
                zones.pop(self._zone_index)
                self._zone_index = None
                return await self.async_step_init()

            taken = [
                item.get("zone_id")
                for index, item in enumerate(zones)
                if index != self._zone_index and item.get("zone_id")
            ]
            zone = _zone_from_form(user_input, current, taken, stored_id=stored_id)
            errors |= _zone_errors(zone)
            if self._priority_clash(zone["zone_id"], zone["priority"]):
                errors["priority"] = "duplicate_priority"
            if errors:
                # Het formulier komt terug met wat er ingevuld stónd, niet met
                # wat er stond voordat je begon. Anders wijst de melding een
                # veld aan dat inmiddels weer zijn oude waarde toont, en zoek
                # je naar een fout die er niet meer lijkt te zijn.
                #
                # The form comes back with what was filled in, not with what
                # stood there before you started. Otherwise the complaint points
                # at a field that has reverted to its old value, and you go
                # looking for a mistake that no longer appears to be there.
                current = zone
            if not errors:
                if self._zone_index is None:
                    zones.append(zone)
                    self._zone_index = len(zones) - 1
                else:
                    zones[self._zone_index] = zone
                return await self.async_step_sources()

        heat = current.get("heat") or {}
        cool = current.get("cool") or {}
        priority = current.get("priority", _next_priority(zones))
        return self.async_show_form(
            step_id="zone",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=current.get("name", "")): _TEXT,
                    vol.Optional(
                        "indoor_sensor",
                        description={"suggested_value": current.get("indoor_sensor") or None},
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=["sensor", "climate"])
                    ),
                    vol.Required("priority", default=priority): _RANK,
                    vol.Required(
                        "gate", default=current.get("gate", ZoneGate.HOUSEHOLD.value)
                    ): _choices([item.value for item in ZoneGate], "zone_gate"),
                    vol.Optional(
                        "presence_entity",
                        description={"suggested_value": current.get("presence_entity") or None},
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=["binary_sensor", "sensor", "input_boolean"]
                        )
                    ),
                    vol.Required(
                        "presence_state", default=current.get("presence_state", "on")
                    ): _TEXT,
                    vol.Optional(
                        "presence_timeout",
                        description={"suggested_value": current.get("presence_timeout") or None},
                    ): _SECONDS,
                    vol.Required(
                        "ignore_precipitation",
                        default=current.get("ignore_precipitation", False),
                    ): bool,
                    vol.Required("enable_heat", default=bool(heat)): bool,
                    vol.Required("heat_target", default=heat.get("target", 21.0)): _TEMPERATURE,
                    vol.Required("heat_start_at", default=heat.get("start_at", 20.0)): _TEMPERATURE,
                    vol.Required("heat_hysteresis", default=heat.get("hysteresis", 1.0)): _BAND,
                    vol.Optional(
                        "heat_outdoor_max",
                        description={"suggested_value": (heat.get("outdoor") or {}).get("maximum")},
                    ): _TEMPERATURE,
                    vol.Required("enable_cool", default=bool(cool)): bool,
                    vol.Required("cool_target", default=cool.get("target", 23.0)): _TEMPERATURE,
                    vol.Required("cool_start_at", default=cool.get("start_at", 24.0)): _TEMPERATURE,
                    vol.Required("cool_hysteresis", default=cool.get("hysteresis", 1.0)): _BAND,
                    vol.Optional(
                        "cool_outdoor_min",
                        description={"suggested_value": (cool.get("outdoor") or {}).get("minimum")},
                    ): _TEMPERATURE,
                    vol.Required(
                        "cool_summer_only",
                        default=Season.SUMMER.value in (cool.get("seasons") or []),
                    ): bool,
                    vol.Required("delete", default=False): bool,
                    vol.Required(_EXIT, default=_EXIT_KEEP): _exit_row(),
                }
            ),
        )

    # -- bronnen / sources ---------------------------------------------------

    async def async_step_sources(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a source of the current zone to edit, add one, or go back."""
        zone = self._current_zone()
        if zone is None:
            return await self.async_step_init()
        sources = zone.setdefault("sources", [])

        if user_input is not None:
            choice = user_input["source"]
            if choice == _BACK:
                return await self.async_step_init()
            self._source_index = None if choice == _ADD else int(choice)
            return await self.async_step_source()

        options = [
            selector.SelectOptionDict(value=str(index), label=source["entity_id"])
            for index, source in enumerate(sources)
        ]
        options.append(_add_option("source"))
        options.append(_back_option())
        return self.async_show_form(
            step_id="sources",
            data_schema=vol.Schema(
                {
                    vol.Required("source", default=_ADD): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.LIST,
                            translation_key="source_list",
                        )
                    )
                }
            ),
            description_placeholders={"zone": zone.get("name") or zone["zone_id"]},
        )

    async def async_step_source(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Edit one source of the current zone."""
        zone = self._current_zone()
        if zone is None:
            return await self.async_step_init()
        sources = zone.setdefault("sources", [])
        current = sources[self._source_index] if self._source_index is not None else {}

        errors: dict[str, str] = {}

        if user_input is not None:
            if user_input.get(_EXIT) == _EXIT_DROP:
                return await self.async_step_sources()
            if not user_input.get("delete"):
                errors = _missing(user_input, "entity_id")
            if errors:
                current = {**current, **user_input}

        if user_input is not None and not errors:
            if user_input.get("delete") and self._source_index is not None:
                sources.pop(self._source_index)
            else:
                source = {
                    "source_id": current.get("source_id")
                    or _unique_id(
                        f"{zone['zone_id']}_{user_input['entity_id'].split('.')[-1]}",
                        _all_source_ids(self._installation),
                    ),
                    "entity_id": user_input["entity_id"],
                    "role": user_input["role"],
                    "autostart": user_input["autostart"],
                    "priority": int(user_input["priority"]),
                    "outdoor": {
                        "minimum": user_input.get("outdoor_min"),
                        "maximum": user_input.get("outdoor_max"),
                    },
                }
                if self._source_index is None:
                    sources.append(source)
                else:
                    sources[self._source_index] = source
            self._source_index = None
            return await self.async_step_sources()

        outdoor = current.get("outdoor") or {}
        return self.async_show_form(
            step_id="source",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "entity_id",
                        description={"suggested_value": current.get("entity_id") or None},
                    ): _CLIMATE,
                    vol.Required(
                        "role", default=current.get("role", SourceRole.HEAT_COOL.value)
                    ): _choices([item.value for item in SourceRole], "source_role"),
                    vol.Required("autostart", default=current.get("autostart", True)): bool,
                    vol.Required("priority", default=current.get("priority", 0)): _RANK,
                    vol.Optional(
                        "outdoor_min",
                        description={"suggested_value": outdoor.get("minimum")},
                    ): _TEMPERATURE,
                    vol.Optional(
                        "outdoor_max",
                        description={"suggested_value": outdoor.get("maximum")},
                    ): _TEMPERATURE,
                    vol.Required("delete", default=False): bool,
                    vol.Required(_EXIT, default=_EXIT_KEEP): _exit_row(),
                }
            ),
        )

    # -- circuits ------------------------------------------------------------

    async def async_step_circuits(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a refrigerant circuit to edit, or add one."""
        circuits = self._list("circuits")
        if user_input is not None:
            choice = user_input["circuit"]
            if choice == _BACK:
                return await self.async_step_init()
            self._circuit_index = None if choice == _ADD else int(choice)
            return await self.async_step_circuit()

        options = [
            selector.SelectOptionDict(
                value=str(index), label=circuit.get("name") or circuit["circuit_id"]
            )
            for index, circuit in enumerate(circuits)
        ]
        options.append(_add_option("circuit"))
        options.append(_back_option())
        return self.async_show_form(
            step_id="circuits",
            data_schema=vol.Schema(
                {
                    vol.Required("circuit", default=_ADD): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.LIST,
                            translation_key="circuit_list",
                        )
                    )
                }
            ),
        )

    async def async_step_circuit(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit one refrigerant circuit."""
        circuits = self._list("circuits")
        current = circuits[self._circuit_index] if self._circuit_index is not None else {}

        errors: dict[str, str] = {}

        if user_input is not None:
            if user_input.get(_EXIT) == _EXIT_DROP:
                return await self.async_step_circuits()
            if not user_input.get("delete"):
                errors = _missing(user_input, "units")
            if errors:
                current = {**current, **user_input}

        if user_input is not None and not errors:
            if user_input.get("delete") and self._circuit_index is not None:
                circuits.pop(self._circuit_index)
                self._circuit_index = None
                return await self.async_step_init()

            circuit = {
                "circuit_id": current.get("circuit_id")
                or _unique_id(
                    user_input[CONF_NAME],
                    [item["circuit_id"] for item in circuits],
                ),
                "name": user_input[CONF_NAME],
                "units": user_input["units"],
                "simultaneous_heat_cool": user_input["simultaneous_heat_cool"],
                "conflict_policy": user_input["conflict_policy"],
                "allow_fan_only_during_conflict": user_input["allow_fan_only_during_conflict"],
                "family_switch_delay": user_input["family_switch_delay"],
                "min_family_switch_interval": user_input["min_family_switch_interval"],
                "min_cycle_time": user_input["min_cycle_time"],
                "max_concurrent_units": user_input.get("max_concurrent_units"),
            }
            if self._circuit_index is None:
                circuits.append(circuit)
                self._circuit_index = len(circuits) - 1
            else:
                circuits[self._circuit_index] = circuit
            return await self.async_step_circuit_priorities()

        return self.async_show_form(
            step_id="circuit",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=current.get("name", "")): _TEXT,
                    vol.Optional(
                        "units", description={"suggested_value": current.get("units") or []}
                    ): _CLIMATE_MULTI,
                    vol.Required(
                        "simultaneous_heat_cool",
                        default=current.get("simultaneous_heat_cool", False),
                    ): bool,
                    vol.Required(
                        "conflict_policy",
                        default=current.get("conflict_policy", ConflictPolicy.PRIORITY.value),
                    ): _choices([item.value for item in ConflictPolicy], "conflict_policy"),
                    vol.Required(
                        "allow_fan_only_during_conflict",
                        default=current.get("allow_fan_only_during_conflict", False),
                    ): bool,
                    vol.Required(
                        "family_switch_delay", default=current.get("family_switch_delay", 0)
                    ): _SECONDS,
                    vol.Required(
                        "min_family_switch_interval",
                        default=current.get("min_family_switch_interval", 0),
                    ): _SECONDS,
                    vol.Required(
                        "min_cycle_time", default=current.get("min_cycle_time", 180)
                    ): _SECONDS,
                    vol.Optional(
                        "max_concurrent_units",
                        description={"suggested_value": current.get("max_concurrent_units")},
                    ): _RANK,
                    vol.Required("delete", default=False): bool,
                    vol.Required(_EXIT, default=_EXIT_KEEP): _exit_row(),
                }
            ),
        )

    # -- prioriteiten op een circuit / priorities on a circuit ---------------

    async def async_step_circuit_priorities(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a zone on this circuit whose priority to change, or go back.

        Priority lives on the zone, because that is what it belongs to, but it
        only ever matters on a shared outdoor unit. Reachable from both places,
        writing the same field, so the two can never disagree.
        """
        circuit = self._current_circuit()
        if circuit is None:
            return await self.async_step_init()
        zones = self._zones_on(circuit)

        if user_input is not None:
            choice = user_input["zone"]
            if choice == _BACK:
                return await self.async_step_init()
            self._priority_zone_id = choice
            return await self.async_step_circuit_priority()

        options = [
            selector.SelectOptionDict(
                value=zone["zone_id"],
                label=f"{zone.get('name') or zone['zone_id']} — {zone.get('priority', 0)}",
            )
            for zone in zones
        ]
        options.append(_back_option())
        return self.async_show_form(
            step_id="circuit_priorities",
            data_schema=vol.Schema(
                {
                    vol.Required("zone", default=_BACK): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.LIST,
                            translation_key="circuit_priority_list",
                        )
                    )
                }
            ),
            description_placeholders={"circuit": circuit.get("name") or circuit["circuit_id"]},
        )

    async def async_step_circuit_priority(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set one zone's priority from the circuit it sits on."""
        zone = next(
            (item for item in self._list("zones") if item["zone_id"] == self._priority_zone_id),
            None,
        )
        if zone is None:
            self._priority_zone_id = None
            return await self.async_step_circuit_priorities()

        errors: dict[str, str] = {}

        if user_input is not None:
            if user_input.get(_EXIT) == _EXIT_DROP:
                return await self.async_step_circuit_priorities()
            wanted = int(user_input["priority"])
            if self._priority_clash(zone["zone_id"], wanted):
                errors["priority"] = "duplicate_priority"
            else:
                zone["priority"] = wanted
                self._priority_zone_id = None
                return await self.async_step_circuit_priorities()

        return self.async_show_form(
            step_id="circuit_priority",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required("priority", default=zone.get("priority", 0)): _RANK,
                    vol.Required(_EXIT, default=_EXIT_KEEP): _exit_row(),
                }
            ),
            description_placeholders={"zone": zone.get("name") or zone["zone_id"]},
        )

    # -- warmtebronnen / heat generators -------------------------------------

    async def async_step_generators(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a shared heat source to edit, or add one."""
        generators = self._list("generators")
        if user_input is not None:
            choice = user_input["generator"]
            if choice == _BACK:
                return await self.async_step_init()
            self._index = None if choice == _ADD else int(choice)
            return await self.async_step_generator()

        options = [
            selector.SelectOptionDict(
                value=str(index), label=item.get("name") or item["generator_id"]
            )
            for index, item in enumerate(generators)
        ]
        options.append(_add_option("generator"))
        options.append(_back_option())
        return self.async_show_form(
            step_id="generators",
            data_schema=vol.Schema(
                {
                    vol.Required("generator", default=_ADD): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.LIST,
                            translation_key="generator_list",
                        )
                    )
                }
            ),
        )

    async def async_step_generator(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit one shared heat source."""
        generators = self._list("generators")
        current = generators[self._index] if self._index is not None else {}

        errors: dict[str, str] = {}

        if user_input is not None:
            if user_input.get(_EXIT) == _EXIT_DROP:
                return await self.async_step_generators()
            if not user_input.get("delete"):
                errors = _missing(user_input, "entity_id")
            if errors:
                current = {**current, **user_input}

        if user_input is not None and not errors:
            if user_input.get("delete") and self._index is not None:
                generators.pop(self._index)
            else:
                item = {
                    "generator_id": current.get("generator_id")
                    or _unique_id(
                        user_input[CONF_NAME], [entry["generator_id"] for entry in generators]
                    ),
                    "name": user_input[CONF_NAME],
                    "entity_id": user_input["entity_id"],
                    "zone_ids": user_input.get("zone_ids") or [],
                    "setpoint": user_input.get("setpoint"),
                }
                if self._index is None:
                    generators.append(item)
                else:
                    generators[self._index] = item
            self._index = None
            return await self.async_step_init()

        zone_options = [
            selector.SelectOptionDict(
                value=zone["zone_id"], label=zone.get("name") or zone["zone_id"]
            )
            for zone in self._list("zones")
        ]
        return self.async_show_form(
            step_id="generator",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=current.get("name", "")): _TEXT,
                    vol.Optional(
                        "entity_id",
                        description={"suggested_value": current.get("entity_id") or None},
                    ): _CLIMATE,
                    vol.Optional(
                        "zone_ids",
                        description={"suggested_value": current.get("zone_ids") or []},
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=zone_options, multiple=True)
                    ),
                    vol.Optional(
                        "setpoint", description={"suggested_value": current.get("setpoint")}
                    ): _TEMPERATURE,
                    vol.Required("delete", default=False): bool,
                    vol.Required(_EXIT, default=_EXIT_KEEP): _exit_row(),
                }
            ),
        )

    # -- bewoners / residents ------------------------------------------------

    async def async_step_residents(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a resident to edit, or add one."""
        residents = self._list("residents")
        if user_input is not None:
            choice = user_input["resident"]
            if choice == _BACK:
                return await self.async_step_init()
            self._resident_index = None if choice == _ADD else int(choice)
            return await self.async_step_resident()

        options = [
            selector.SelectOptionDict(
                value=str(index), label=person.get("name") or person["resident_id"]
            )
            for index, person in enumerate(residents)
        ]
        options.append(_add_option("resident"))
        options.append(_back_option())
        return self.async_show_form(
            step_id="residents",
            data_schema=vol.Schema(
                {
                    vol.Required("resident", default=_ADD): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.LIST,
                            translation_key="resident_list",
                        )
                    )
                }
            ),
        )

    async def async_step_resident(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit one resident."""
        residents = self._list("residents")
        current = residents[self._resident_index] if self._resident_index is not None else {}

        errors: dict[str, str] = {}

        if user_input is not None:
            if user_input.get(_EXIT) == _EXIT_DROP:
                return await self.async_step_residents()
            if not user_input.get("delete"):
                errors = _missing(user_input, "presence_entity")
            if errors:
                current = {**current, **user_input}

        if user_input is not None and not errors:
            if user_input.get("delete") and self._resident_index is not None:
                residents.pop(self._resident_index)
                self._resident_index = None
                return await self.async_step_init()

            person = {
                "resident_id": current.get("resident_id")
                or _unique_id(
                    user_input[CONF_NAME],
                    [item["resident_id"] for item in residents],
                ),
                "name": user_input[CONF_NAME],
                "presence_entity": user_input["presence_entity"],
                "sleep_entity": user_input.get("sleep_entity", ""),
                "sleep_state": user_input.get("sleep_state") or "on",
                "sleep_window": {
                    "start": user_input.get("sleep_from") or "",
                    "end": user_input.get("sleep_until") or "",
                    # Geen dagen aangevinkt betekent elke dag, net als bij een
                    # rooster. Een slaapvenster op geen enkele dag zou de
                    # slaapsensor voorgoed uitzetten.
                    #
                    # No days ticked means every day, just like a schedule. A
                    # sleep window on no day at all would switch the sleep
                    # sensor off for good.
                    "weekdays": ([int(day) for day in user_input.get("sleep_days") or ()] or None),
                },
                # De roosters van deze bewoner blijven staan; die worden in de
                # volgende stap bewerkt, niet in dit formulier.
                #
                # This resident's schedules are kept; they are edited in the
                # next step, not in this form.
                "windows": current.get("windows") or [],
            }
            if self._resident_index is None:
                residents.append(person)
                self._resident_index = len(residents) - 1
            else:
                residents[self._resident_index] = person
            return await self.async_step_windows()

        stored_days = (current.get("sleep_window") or {}).get("weekdays")
        sleep_days = None if stored_days is None else [str(day) for day in stored_days]
        return self.async_show_form(
            step_id="resident",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=current.get("name", "")): _TEXT,
                    vol.Optional(
                        "presence_entity",
                        description={"suggested_value": current.get("presence_entity") or None},
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=["person", "device_tracker", "binary_sensor", "input_boolean"]
                        )
                    ),
                    vol.Optional(
                        "sleep_entity",
                        description={"suggested_value": current.get("sleep_entity") or None},
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=["binary_sensor", "sensor", "input_boolean"]
                        )
                    ),
                    vol.Required("sleep_state", default=current.get("sleep_state", "on")): _TEXT,
                    vol.Optional(
                        "sleep_from",
                        description={
                            "suggested_value": (current.get("sleep_window") or {}).get("start")
                        },
                    ): _TIME,
                    vol.Optional(
                        "sleep_until",
                        description={
                            "suggested_value": (current.get("sleep_window") or {}).get("end")
                        },
                    ): _TIME,
                    vol.Optional(
                        "sleep_days",
                        description={"suggested_value": sleep_days},
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=str(number), label=label)
                                for number, label in enumerate(_WEEKDAYS)
                            ],
                            multiple=True,
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    ),
                    vol.Required("delete", default=False): bool,
                    vol.Required(_EXIT, default=_EXIT_KEEP): _exit_row(),
                }
            ),
        )

    # -- roosters / schedules ------------------------------------------------

    async def async_step_windows(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a schedule window of the current resident, add one, or go back."""
        resident = self._current_resident()
        if resident is None:
            return await self.async_step_init()
        windows = resident.setdefault("windows", [])

        if user_input is not None:
            choice = user_input["window"]
            if choice == _BACK:
                return await self.async_step_init()
            self._window_index = None if choice == _ADD else int(choice)
            return await self.async_step_window()

        options = [
            selector.SelectOptionDict(value=str(index), label=_window_label(window))
            for index, window in enumerate(windows)
        ]
        options.append(_add_option("window"))
        options.append(_back_option())
        return self.async_show_form(
            step_id="windows",
            data_schema=vol.Schema(
                {
                    vol.Required("window", default=_BACK if windows else _ADD): (
                        selector.SelectSelector(
                            selector.SelectSelectorConfig(
                                options=options,
                                mode=selector.SelectSelectorMode.LIST,
                                translation_key="window_list",
                            )
                        )
                    )
                }
            ),
            description_placeholders={"resident": resident.get("name") or resident["resident_id"]},
        )

    async def async_step_window(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Edit one schedule window."""
        resident = self._current_resident()
        if resident is None:
            return await self.async_step_init()
        windows = resident.setdefault("windows", [])
        current = windows[self._window_index] if self._window_index is not None else {}

        if user_input is not None:
            if user_input.get(_EXIT) == _EXIT_DROP:
                return await self.async_step_windows()
            if user_input.get("delete") and self._window_index is not None:
                windows.pop(self._window_index)
            else:
                window = {
                    "start": user_input["start"],
                    "end": user_input["end"],
                    # Geen dagen aangevinkt betekent elke dag, niet nooit. Een
                    # rooster zonder dagen zou de bewoner permanent buitensluiten.
                    #
                    # No days ticked means every day, not never. A schedule with
                    # no days would lock the resident out permanently.
                    "weekdays": ([int(day) for day in user_input.get("weekdays") or ()] or None),
                    "holiday": user_input.get("holiday", False),
                }
                if self._window_index is None:
                    windows.append(window)
                else:
                    windows[self._window_index] = window
            self._window_index = None
            return await self.async_step_windows()

        weekdays = current.get("weekdays")
        return self.async_show_form(
            step_id="window",
            data_schema=vol.Schema(
                {
                    vol.Required("holiday", default=current.get("holiday", False)): bool,
                    vol.Required("start", default=current.get("start", "08:00:00")): _TIME,
                    vol.Required("end", default=current.get("end", "23:00:00")): _TIME,
                    vol.Optional(
                        "weekdays",
                        description={
                            "suggested_value": (
                                None if weekdays is None else [str(day) for day in weekdays]
                            )
                        },
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=str(number), label=label)
                                for number, label in enumerate(_WEEKDAYS)
                            ],
                            multiple=True,
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    ),
                    vol.Required("delete", default=False): bool,
                    vol.Required(_EXIT, default=_EXIT_KEEP): _exit_row(),
                }
            ),
        )

    # -- openingen / openings ------------------------------------------------

    async def async_step_openings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick an opening to edit, or add one."""
        openings = self._list("openings")
        if user_input is not None:
            choice = user_input["opening"]
            if choice == _BACK:
                return await self.async_step_init()
            self._index = None if choice == _ADD else int(choice)
            return await self.async_step_opening()

        options = [
            selector.SelectOptionDict(value=str(index), label=opening["entity_id"])
            for index, opening in enumerate(openings)
        ]
        options.append(_add_option("opening"))
        options.append(_back_option())
        return self.async_show_form(
            step_id="openings",
            data_schema=vol.Schema(
                {
                    vol.Required("opening", default=_ADD): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.LIST,
                            translation_key="opening_list",
                        )
                    )
                }
            ),
        )

    async def async_step_opening(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit one opening."""
        openings = self._list("openings")
        current = openings[self._index] if self._index is not None else {}

        errors: dict[str, str] = {}

        if user_input is not None:
            if user_input.get(_EXIT) == _EXIT_DROP:
                return await self.async_step_openings()
            if not user_input.get("delete"):
                errors = _missing(user_input, "entity_id")
            if errors:
                current = {**current, **user_input}

        if user_input is not None and not errors:
            if user_input.get("delete") and self._index is not None:
                openings.pop(self._index)
            else:
                opening = {
                    "entity_id": user_input["entity_id"],
                    "zone_ids": user_input.get("zone_ids") or [],
                    "open_state": user_input.get("open_state") or "on",
                    "delay": user_input.get("delay") or 0,
                }
                if self._index is None:
                    openings.append(opening)
                else:
                    openings[self._index] = opening
            self._index = None
            return await self.async_step_init()

        zone_options = [
            selector.SelectOptionDict(
                value=zone["zone_id"], label=zone.get("name") or zone["zone_id"]
            )
            for zone in self._list("zones")
        ]
        return self.async_show_form(
            step_id="opening",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "entity_id",
                        description={"suggested_value": current.get("entity_id") or None},
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=["binary_sensor", "cover", "sensor"])
                    ),
                    vol.Optional(
                        "open_state",
                        description={"suggested_value": current.get("open_state") or "on"},
                    ): _TEXT,
                    vol.Optional(
                        "zone_ids",
                        description={"suggested_value": current.get("zone_ids") or []},
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=zone_options, multiple=True)
                    ),
                    vol.Optional(
                        "delay", description={"suggested_value": current.get("delay") or None}
                    ): _SECONDS,
                    vol.Required("delete", default=False): bool,
                    vol.Required(_EXIT, default=_EXIT_KEEP): _exit_row(),
                }
            ),
        )

    # -- hulpjes / helpers ---------------------------------------------------

    def _list(self, key: str) -> list[dict[str, Any]]:
        """Return the editable list stored under `key`, creating it if needed."""
        return self._installation.setdefault(key, [])

    def _priority_clash(self, zone_id: str, priority: int) -> bool:
        """Return whether another zone on the same circuit already holds this number.

        Only zones sharing an outdoor unit are checked. Rooms on separate
        circuits never compete, so making them pick different numbers would be
        an obstacle without a reason behind it.
        """
        for circuit in self._list("circuits"):
            units = set(circuit.get("units") or ())
            on_it = [
                zone
                for zone in self._list("zones")
                if any(source.get("entity_id") in units for source in zone.get("sources") or ())
            ]
            if not any(zone["zone_id"] == zone_id for zone in on_it):
                continue
            if any(
                zone["zone_id"] != zone_id and zone.get("priority") == priority for zone in on_it
            ):
                return True
        return False

    def _current_circuit(self) -> dict[str, Any] | None:
        """Return the circuit being edited, or `None` when the cursor is stale."""
        circuits = self._list("circuits")
        if self._circuit_index is None or not 0 <= self._circuit_index < len(circuits):
            return None
        return circuits[self._circuit_index]

    def _zones_on(self, circuit: dict[str, Any]) -> list[dict[str, Any]]:
        """Return the zones with a source on this circuit, most preferred first."""
        units = set(circuit.get("units") or ())
        on_it = [
            zone
            for zone in self._list("zones")
            if any(source.get("entity_id") in units for source in zone.get("sources") or ())
        ]
        return sorted(on_it, key=lambda zone: (zone.get("priority", 0), zone["zone_id"]))

    def _current_resident(self) -> dict[str, Any] | None:
        """Return the resident being edited, or `None` when the cursor is stale."""
        residents = self._list("residents")
        if self._resident_index is None or not 0 <= self._resident_index < len(residents):
            return None
        return residents[self._resident_index]

    def _current_zone(self) -> dict[str, Any] | None:
        """Return the zone being edited, or `None` when the cursor is stale.

        A stale cursor sends the user back to the menu rather than raising:
        a config flow that crashes leaves a half-built installation behind with
        no way back into it.
        """
        zones = self._list("zones")
        if self._zone_index is None or not 0 <= self._zone_index < len(zones):
            return None
        return zones[self._zone_index]


def _zone_errors(zone: dict[str, Any]) -> dict[str, str]:
    """Return every complaint this screen can make about one zone.

    De verzamelplek, zodat de vlucht er maar op één ding hoeft te leunen en er
    geen controle vergeten kan worden. Wat hier doorheen komt, hoort door
    `validate()` heen te komen - `test_random_installations.py` legt precies dat
    vast, in beide richtingen.

    The gathering point, so the flow leans on one thing only and no check can
    be forgotten. What passes here should pass `validate()` -
    `test_random_installations.py` pins down exactly that, in both directions.
    """
    return _name_errors(zone) | _band_errors(zone) | _gate_errors(zone) | _mode_errors(zone)


def _name_errors(zone: dict[str, Any]) -> dict[str, str]:
    """Return an error when the name cannot carry a zone id.

    De naam bepaalt het id van een nieuwe zone, dus hij moet iets opleveren om
    te sluggen. Een lege naam valt terug op `zone`, en twee van zulke zones
    botsen alsnog op hetzelfde id - precies wat de unieke-id-stap hierboven
    hoort te voorkomen.

    The name decides a new zone's id, so it must yield something to slug. An
    empty name falls back to `zone`, and two such zones still collide on the
    same id - exactly what the unique-id step above is there to prevent.
    """
    if slugify(zone.get("name") or ""):
        return {}
    return {"name": "required"}


def _mode_errors(zone: dict[str, Any]) -> dict[str, str]:
    """Return an error when a zone may neither heat nor cool.

    Zo'n zone kan per definitie nooit iets doen. Hij verschijnt wel met al zijn
    entiteiten, en dan zoek je later waarom er niets gebeurt in een kamer die
    het nooit had mogen proberen.

    Such a zone can never do anything by definition. It still appears with all
    its entities, and then you go looking later for why nothing happens in a
    room that was never allowed to try.
    """
    if zone.get("heat") or zone.get("cool"):
        return {}
    return {"enable_heat": "zone_without_modes"}


def _gate_errors(zone: dict[str, Any]) -> dict[str, str]:
    """Return an error when the room gate has no room sensor to lean on.

    Een zone op *Ruimte* kijkt naar de aanwezigheidssensor en naar niets
    anders. Is die er niet, dan is de kamer per definitie leeg en doet de zone
    nooit meer iets - stil, want een zone die niets doet ziet er precies zo uit
    als een zone die niets hoeft te doen.

    `validate()` klaagt hier terecht over, maar pas achteraf. Het scherm waarop
    je de poort kiest weet het meteen.

    A zone on *Room* looks at the presence sensor and at nothing else. Without
    one the room is empty by definition and the zone never does anything again
    - quietly, since a zone doing nothing looks exactly like a zone with
    nothing to do.

    `validate()` rightly complains about this, but only afterwards. The screen
    where you pick the gate knows at once.
    """
    if zone.get("gate") != ZoneGate.PRESENCE.value:
        return {}
    if zone.get("presence_entity"):
        return {}
    return {"presence_entity": "presence_gate_without_sensor"}


def _band_errors(zone: dict[str, Any]) -> dict[str, str]:
    """Return an error per mode whose target sits on the wrong side of its switch-on point.

    Het aanpunt is waar de zone besluit te beginnen, de streeftemperatuur is wat
    het apparaat te horen krijgt. Ligt het streven aan de verkeerde kant, dan
    start de zone keurig en zet hij het apparaat vervolgens op een temperatuur
    waar het niets voor hoeft te doen. Van buiten lijkt dat op een apparaat dat
    weigert, en daar ga je een dag mee zoeken.

    `validate()` waarschuwt hier ook over, maar pas achteraf, in een
    reparatiemelding. Achteraf is te laat als het scherm waarop je het intikte
    het meteen had kunnen zeggen.

    The switch-on point is where the zone decides to begin, the target is what
    the appliance is told. If the target sits on the wrong side, the zone starts
    dutifully and then sets the appliance to a temperature it need do nothing
    for. From the outside that looks like an appliance refusing, and you can
    spend a day chasing it.

    `validate()` warns about this too, but only afterwards, in a repair notice.
    Afterwards is too late when the screen you typed it on could have said so at
    once.
    """
    errors: dict[str, str] = {}

    heat = zone.get("heat") or {}
    if heat and heat["target"] < heat["start_at"]:
        errors["heat_target"] = "target_outside_band"

    cool = zone.get("cool") or {}
    if cool and cool["target"] > cool["start_at"]:
        errors["cool_target"] = "target_outside_band"

    # Begint koelen op of onder het punt waar verwarmen begint, dan vragen de
    # twee tegelijk om dezelfde kamer. De engine kiest dan nog steeds
    # deterministisch, maar dat het zover komt kan niemand bedoeld hebben - en
    # het is aan dit scherm om dat te zeggen, niet aan een melding achteraf.
    #
    # If cooling starts at or below where heating starts, the two ask for the
    # same room at once. The engine still picks deterministically, but getting
    # there is something nobody can have meant - and it is for this screen to
    # say so, rather than for a notice afterwards.
    if heat and cool and cool["start_at"] <= heat["start_at"]:
        errors["cool_start_at"] = "bands_overlap"

    return errors


def _zone_from_form(
    user_input: dict[str, Any],
    current: dict[str, Any],
    taken: list[str] | None = None,
    *,
    stored_id: str | None = None,
) -> dict[str, Any]:
    """Return the stored zone described by a submitted zone form.

    Het formulier toont maar één kant van elke buitengrens en geen
    verwarmingsseizoenen. Wie die waarden eerder instelde - via een oudere
    versie of een met de hand bewerkte configuratie - mag ze bij een gewone
    formulierbewerking niet kwijtraken: wat het formulier niet toont, blijft
    staan.

    The form shows only one side of each outdoor bound and no heating seasons.
    Whoever set those values earlier - through an older version or a hand-edited
    configuration - should not lose them on an ordinary form edit: what the form
    does not show stays.
    """
    stored_heat = current.get("heat") or {}
    stored_cool = current.get("cool") or {}
    stored_heat_outdoor = stored_heat.get("outdoor") or {}
    stored_cool_outdoor = stored_cool.get("outdoor") or {}
    heat = (
        {
            "target": user_input["heat_target"],
            "start_at": user_input["heat_start_at"],
            "hysteresis": user_input["heat_hysteresis"],
            "outdoor": {
                "minimum": stored_heat_outdoor.get("minimum"),
                "maximum": user_input.get("heat_outdoor_max"),
            },
            "seasons": stored_heat.get("seasons"),
        }
        if user_input["enable_heat"]
        else None
    )
    cool = (
        {
            "target": user_input["cool_target"],
            "start_at": user_input["cool_start_at"],
            "hysteresis": user_input["cool_hysteresis"],
            "outdoor": {
                "minimum": user_input.get("cool_outdoor_min"),
                "maximum": stored_cool_outdoor.get("maximum"),
            },
            "seasons": [Season.SUMMER.value] if user_input["cool_summer_only"] else None,
        }
        if user_input["enable_cool"]
        else None
    )
    return {
        # Een bestaande zone houdt zijn id: achteraf hernoemen kost de
        # entiteitsgeschiedenis van die zone. Een nieuwe zone krijgt een id uit
        # zijn naam, en bij een al bestaande id een oplopend achtervoegsel -
        # precies zoals bronnen, circuits, generatoren en bewoners dat doen.
        #
        # An existing zone keeps its id: renaming one afterwards costs that
        # zone's entity history. A new zone gets an id from its name, and when
        # that id already exists a counting suffix - exactly as sources,
        # circuits, generators and residents do.
        "zone_id": (
            stored_id if stored_id is not None else _unique_id(user_input[CONF_NAME], taken or [])
        ),
        "name": user_input[CONF_NAME],
        "indoor_sensor": user_input["indoor_sensor"],
        "priority": int(user_input["priority"]),
        "sources": current.get("sources") or [],
        "heat": heat,
        "cool": cool,
        "gate": user_input.get("gate") or ZoneGate.HOUSEHOLD.value,
        "presence_entity": user_input.get("presence_entity") or "",
        "presence_state": user_input.get("presence_state") or "on",
        "presence_timeout": user_input.get("presence_timeout") or 0,
        "ignore_precipitation": bool(user_input.get("ignore_precipitation", False)),
    }


def _next_priority(zones: list[dict[str, Any]]) -> int:
    """Return the priority a newly added zone should start on.

    Every zone defaulting to zero would leave them all tied, and a tie falls
    back on the zone id - so the room that happens to come first alphabetically
    would quietly win every circuit. Counting up instead means the order rooms
    are added in is the order they win in, which is both predictable and easy
    to correct.
    """
    used = [
        zone["priority"]
        for zone in zones
        if isinstance(zone.get("priority"), int) and not isinstance(zone.get("priority"), bool)
    ]
    return max(used) + 1 if used else 0


def _window_label(window: dict[str, Any]) -> str:
    """Return a one-line summary of a schedule window for the picker."""
    start = str(window.get("start", "?"))[:5]
    end = str(window.get("end", "?"))[:5]
    # Eerst filteren, dan sorteren. Een opgeslagen lijst met een string ertussen
    # laat `sorted` omvallen op de vergelijking, nog voordat de filter hem ziet.
    #
    # Filter first, then sort. A stored list with a string in it makes `sorted`
    # fall over on the comparison, before the filter ever sees it.
    weekdays = [
        day
        for day in (window.get("weekdays") or ())
        if isinstance(day, int) and not isinstance(day, bool) and 0 <= day < 7
    ]
    if not weekdays:
        return f"{start} - {end}, every day"
    return f"{start} - {end}, {', '.join(_WEEKDAYS[day][:3] for day in sorted(weekdays))}"


def _all_source_ids(installation: dict[str, Any]) -> list[str]:
    """Return every source id in use, so a new one can avoid them."""
    return [
        source["source_id"]
        for zone in installation.get("zones") or []
        for source in zone.get("sources") or []
        if "source_id" in source
    ]


def _unique_id(name: str, taken: list[str]) -> str:
    """Return a slug of `name` that is not in `taken`."""
    base = slugify(name) or "item"
    if base not in taken:
        return base
    index = 2
    while f"{base}_{index}" in taken:
        index += 1
    return f"{base}_{index}"


def _deep_copy(value: Any) -> Any:
    """Return a mutable deep copy of stored options.

    Config entry options are shared, immutable-by-convention structures; editing
    them in place would change the running configuration before the user has
    pressed save, and would leave a half-edited installation behind if they
    abandoned the flow.
    """
    if isinstance(value, dict):
        return {key: _deep_copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_deep_copy(item) for item in value]
    return value
