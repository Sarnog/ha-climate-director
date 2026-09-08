"""Config flow en options flow van Climate Director.

Climate Director's config flow and options flow.

De installatie wordt volledig via de UI opgebouwd en als één dict in
`entry.options[CONF_INSTALLATION]` bewaard - hetzelfde formaat dat
`engine.serialise` leest. Deze module bevat daarom geen kennis van klimaatregels,
alleen van navigatie, validatie en opslaan; de formulieropbouw staat in
`schemas.py`.

The installation is built entirely through the UI and stored as one dict in
`entry.options[CONF_INSTALLATION]` - the same format `engine.serialise` reads.
This module therefore holds no knowledge of climate rules, only of navigation,
validation and saving; the form building lives in `schemas.py`.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.util import slugify

from . import problems, schemas, texts
from .const import CONF_INSTALLATION, CONF_SHADOW_MODE, DEFAULT_SHADOW_MODE, DOMAIN
from .coordinator import ClimateDirectorEntry
from .engine import validate
from .engine.models import Season, ZoneGate
from .engine.serialise import config_from_dict
from .schema_fields import _SUMMER_NORTH, _SUMMER_SOUTH
from .schemas import (
    _ADD,
    _BACK,
    _EXIT,
    _EXIT_DROP,
    CONF_NAME,
    _managed_entities,
)
from .units import delta_to_celsius, temperature_unit_of, to_celsius


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


def _blank_to_none(value: Any) -> Any:
    """Return `None` for an empty form value, the value itself otherwise.

    De opslagkant mag nooit `""` in de configuratie schrijven voor een veld dat
    een getal of een entiteit hoort te zijn. Alleen `None` en `""` tellen als
    leeg; `0` en een lege lijst zijn echte waarden en blijven staan. De
    `""`-tak is vandaag op elk bereikbaar pad onbereikbaar — de selectors
    ervóór weigeren een lege string al — maar blijft staan als vangnet voor een
    route die de interface nog niet neemt.

    The storage side must never write `""` into the configuration for a field
    that is supposed to hold a number or an entity. Only `None` and `""` count
    as empty; `0` and an empty list are real values and stay. The `""` branch
    is unreachable on every reachable path today — the selectors in front of it
    already refuse an empty string — but stays as a safety net for a route the
    frontend does not take yet.
    """
    return None if value is None or value == "" else value


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
            data_schema=schemas.user(),
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
        self._renamed_house_wide: set[str] = set()
        """Apparaten die via een bronbewerking van de huisbrede stoplijst los zijn
        geraakt; die hoort het opslaanscherm te melden in plaats van stilletjes
        op te ruimen.

        Appliances that lost their place on the house-wide stop list through a
        source edit; the save screen should report those instead of tidying them
        away silently.
        """

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

        De huisbrede stoplijst wordt hier opgeschoond, maar een apparaat dat via
        een bronbewerking van de lijst los is geraakt blijft staan: het
        opslaanscherm moet hem via `validate()` kunnen melden in plaats van hem
        stilletjes te laten vallen.

        The house-wide stop list is tidied here, but an appliance that lost its
        place on the list through a source edit stays: the save screen must be
        able to report it via `validate()` rather than let it drop without a
        word.
        """
        steered = _managed_entities(self._installation)
        if self._installation.get("house_wide_openings"):
            self._installation["house_wide_openings"] = [
                entity_id
                for entity_id in self._installation["house_wide_openings"]
                if entity_id in steered or entity_id in self._renamed_house_wide
            ]
        found = validate(config_from_dict(self._installation))
        if found and user_input is None:
            await texts.async_prepare(self.hass)
            return self.async_show_form(
                step_id="save",
                data_schema=schemas.save(),
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
            self._installation["outdoor_sensor"] = user_input.get("outdoor_sensor") or ""
            self._installation["heating_layout"] = user_input["heating_layout"]
            # Een handmatige zomermaandenlijst is een bewuste keuze; het
            # halfrond-veld is alleen de snelle manier om een van de twee
            # standaardlijsten te kiezen. Wijst de opgeslagen lijst af van
            # beide standaarden, dan blijft hij staan; anders volgt hij het
            # halfrond zoals altijd.
            #
            # A hand-picked summer-months list is a deliberate choice; the
            # hemisphere field is only the quick way to pick one of the two
            # default lists. If the stored list differs from both defaults it
            # stays; otherwise it follows the hemisphere as ever.
            stored_seasons = self._installation.get("seasons") or {}
            stored_months = stored_seasons.get("summer_months")
            if stored_months and frozenset(int(month) for month in stored_months) not in (
                _SUMMER_NORTH,
                _SUMMER_SOUTH,
            ):
                summer_months = sorted(int(month) for month in stored_months)
            else:
                summer_months = sorted(
                    _SUMMER_SOUTH if user_input["hemisphere"] == "south" else _SUMMER_NORTH
                )
            self._installation["seasons"] = {
                "source": user_input["season_source"],
                "entity_id": user_input.get("season_entity") or "",
                "summer_months": summer_months,
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
                    "max_precondition": int(user_input.get("max_precondition") or 0) * 60,
                }
            )
            # Het vooruit-venster bestaat niet meer. Een installatie die het
            # ooit opsloeg houdt de dode sleutel niet langer vast zodra er hier
            # iets gewijzigd wordt.
            #
            # The pre-conditioning window no longer exists. An installation
            # that once stored it no longer keeps the dead key once anything is
            # changed here.
            gates.pop("precondition_window", None)
            self._installation["holiday_calendars"] = list(
                user_input.get("holiday_calendars") or ()
            )
            self._installation["stuck_after"] = int(user_input.get("stuck_after") or 0) * 60
            self._installation["outdoor_hysteresis"] = float(
                delta_to_celsius(
                    user_input.get("outdoor_hysteresis"), temperature_unit_of(self.hass)
                )
                or 0
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

        return self.async_show_form(
            step_id="settings",
            data_schema=schemas.settings(self),
        )

    # -- exclusieve groepen / exclusive groups -------------------------------

    async def async_step_exclusives(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick an exclusive group to edit, or add one."""
        if user_input is not None:
            choice = user_input["group"]
            if choice == _BACK:
                return await self.async_step_init()
            self._index = None if choice == _ADD else int(choice)
            return await self.async_step_exclusive()

        return self.async_show_form(
            step_id="exclusives",
            data_schema=schemas.exclusives(self),
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
            data_schema=schemas.exclusive(self, current),
        )

    # -- stiltevensters / quiet windows --------------------------------------

    def _quiet_windows(self) -> list[dict[str, Any]]:
        """Return the stored quiet windows, creating the list on first use."""
        gates = self._installation.setdefault("gates", {})
        return gates.setdefault("quiet_windows", [])

    async def async_step_quiets(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pick a quiet window to edit, add one, or go back."""
        if user_input is not None:
            choice = user_input["quiet"]
            if choice == _BACK:
                return await self.async_step_init()
            self._index = None if choice == _ADD else int(choice)
            return await self.async_step_quiet()

        selector_texts = await texts.async_selector_texts(self.hass)
        return self.async_show_form(
            step_id="quiets",
            data_schema=schemas.quiets(self, selector_texts),
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

        return self.async_show_form(
            step_id="quiet",
            data_schema=schemas.quiet(current),
        )

    # -- zones ---------------------------------------------------------------

    async def async_step_zones(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pick a zone to edit, or add one."""
        if user_input is not None:
            choice = user_input["zone"]
            if choice == _BACK:
                return await self.async_step_init()
            self._zone_index = None if choice == _ADD else int(choice)
            return await self.async_step_zone()

        return self.async_show_form(
            step_id="zones",
            data_schema=schemas.zones(self),
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
                # De defaults lezen `current.get("heat")`/`current.get("cool")`,
                # en die sleutels zitten niet in `user_input`. Zonder deze stap
                # toonde het formulier na een fout de nieuwe naam naast de oude
                # temperaturen.
                #
                # The defaults read `current.get("heat")`/`current.get("cool")`,
                # and those keys are not in `user_input`. Without this step the
                # form showed the new name beside the old temperatures after an
                # error.
                current["heat"], current["cool"] = _heat_cool_from_form(
                    user_input, current, unit=temperature_unit_of(self.hass)
                )

        if user_input is not None and not errors:
            if user_input.get("delete") and self._zone_index is not None:
                removed = zones.pop(self._zone_index)
                self._zone_index = None
                self._drop_zone_references(removed)
                return await self.async_step_init()

            taken = [
                item.get("zone_id")
                for index, item in enumerate(zones)
                if index != self._zone_index and item.get("zone_id")
            ]
            zone = _zone_from_form(
                user_input,
                current,
                taken,
                stored_id=stored_id,
                unit=temperature_unit_of(self.hass),
            )
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

        priority = current.get("priority", _next_priority(zones))
        return self.async_show_form(
            step_id="zone",
            errors=errors,
            data_schema=schemas.zone(self, current, priority),
        )

    # -- bronnen / sources ---------------------------------------------------

    async def async_step_sources(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a source of the current zone to edit, add one, or go back."""
        zone = self._current_zone()
        if zone is None:
            return await self.async_step_init()
        if user_input is not None:
            choice = user_input["source"]
            if choice == _BACK:
                return await self.async_step_init()
            self._source_index = None if choice == _ADD else int(choice)
            return await self.async_step_source()

        return self.async_show_form(
            step_id="sources",
            data_schema=schemas.sources(self),
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
                removed_source_id = sources[self._source_index].get("source_id")
                self._drop_source_references({removed_source_id} if removed_source_id else set())
                sources.pop(self._source_index)
            else:
                # Een gewijzigd apparaat dat op de huisbrede stoplijst staat, wordt
                # niet stilletjes gewist: het opslaanscherm moet het oude id kunnen
                # melden. Daarom wordt het hier onthouden, zodat de opruiming in
                # `async_step_save` het laat staan tot de gebruiker het openingsscherm
                # bevestigt.
                #
                # A changed appliance that sits on the house-wide stop list is not
                # silently wiped: the save screen must be able to report the old id.
                # It is therefore remembered here, so the tidy-up in
                # `async_step_save` leaves it until the user confirms the openings
                # screen.
                if self._source_index is not None:
                    old_entity_id = sources[self._source_index].get("entity_id")
                    if (
                        old_entity_id
                        and old_entity_id != user_input["entity_id"]
                        and old_entity_id in (self._installation.get("house_wide_openings") or ())
                    ):
                        self._renamed_house_wide.add(old_entity_id)
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
                        "minimum": to_celsius(
                            _blank_to_none(user_input.get("outdoor_min")),
                            temperature_unit_of(self.hass),
                        ),
                        "maximum": to_celsius(
                            _blank_to_none(user_input.get("outdoor_max")),
                            temperature_unit_of(self.hass),
                        ),
                    },
                    "min_cycle_time": _blank_to_none(user_input.get("min_cycle_time")),
                }
                if self._source_index is None:
                    sources.append(source)
                else:
                    sources[self._source_index] = source
            self._source_index = None
            return await self.async_step_sources()

        return self.async_show_form(
            step_id="source",
            errors=errors,
            data_schema=schemas.source(self, current),
        )

    # -- circuits ------------------------------------------------------------

    async def async_step_circuits(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a refrigerant circuit to edit, or add one."""
        if user_input is not None:
            choice = user_input["circuit"]
            if choice == _BACK:
                return await self.async_step_init()
            self._circuit_index = None if choice == _ADD else int(choice)
            return await self.async_step_circuit()

        return self.async_show_form(
            step_id="circuits",
            data_schema=schemas.circuits(self),
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
                "max_concurrent_units": _blank_to_none(user_input.get("max_concurrent_units")),
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
            data_schema=schemas.circuit(current),
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
        if user_input is not None:
            choice = user_input["zone"]
            if choice == _BACK:
                return await self.async_step_init()
            self._priority_zone_id = choice
            return await self.async_step_circuit_priority()

        return self.async_show_form(
            step_id="circuit_priorities",
            data_schema=schemas.circuit_priorities(self),
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
            data_schema=schemas.circuit_priority(zone),
            description_placeholders={"zone": zone.get("name") or zone["zone_id"]},
        )

    # -- warmtebronnen / heat generators -------------------------------------

    async def async_step_generators(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a shared heat source to edit, or add one."""
        if user_input is not None:
            choice = user_input["generator"]
            if choice == _BACK:
                return await self.async_step_init()
            self._index = None if choice == _ADD else int(choice)
            return await self.async_step_generator()

        return self.async_show_form(
            step_id="generators",
            data_schema=schemas.generators(self),
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
                    "setpoint": to_celsius(
                        _blank_to_none(user_input.get("setpoint")), temperature_unit_of(self.hass)
                    ),
                }
                if self._index is None:
                    generators.append(item)
                else:
                    generators[self._index] = item
            self._index = None
            return await self.async_step_init()

        return self.async_show_form(
            step_id="generator",
            errors=errors,
            data_schema=schemas.generator(self, current),
        )

    # -- bewoners / residents ------------------------------------------------

    async def async_step_residents(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a resident to edit, or add one."""
        if user_input is not None:
            choice = user_input["resident"]
            if choice == _BACK:
                return await self.async_step_init()
            self._resident_index = None if choice == _ADD else int(choice)
            return await self.async_step_resident()

        return self.async_show_form(
            step_id="residents",
            data_schema=schemas.residents(self),
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
                "sleep_entity": user_input.get("sleep_entity") or "",
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
                # Geen tijd betekent geen uitslapen: het slaapvenster is dan
                # het hele verhaal. De dagen zijn hier de ochtenden waarop je
                # uitslaapt, niet de avonden ervoor.
                #
                # No time means no sleeping in: the sleep window is then the
                # whole story. The days here are the mornings you sleep in on,
                # not the evenings before.
                "sleep_in": {
                    "until": user_input.get("sleep_in_until") or "",
                    "weekdays": (
                        [int(day) for day in user_input.get("sleep_in_days") or ()] or None
                    ),
                    "holiday": user_input.get("sleep_in_holiday", False),
                },
                # Geen tijd betekent geen uiterste tijd: dan houdt deze
                # slaper niemand tegen, precies zoals vóór deze instelling.
                # De dagen blijven wel staan, zodat een tijd terugzetten niet
                # ook de dagen opnieuw vraagt.
                #
                # No time means no deadline: this sleeper then holds nobody
                # back, exactly as before this setting. The days are kept, so
                # putting a time back does not ask for the days again.
                "wake_deadline": {
                    "at": user_input.get("wake_by") or "",
                    "weekdays": ([int(day) for day in user_input.get("wake_days") or ()] or None),
                    "holiday": user_input.get("wake_holiday", False),
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

        return self.async_show_form(
            step_id="resident",
            errors=errors,
            data_schema=schemas.resident(current),
        )

    # -- roosters / schedules ------------------------------------------------

    async def async_step_windows(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a schedule window of the current resident, add one, or go back."""
        resident = self._current_resident()
        if resident is None:
            return await self.async_step_init()
        if user_input is not None:
            choice = user_input["window"]
            if choice == _BACK:
                return await self.async_step_init()
            self._window_index = None if choice == _ADD else int(choice)
            return await self.async_step_window()

        selector_texts = await texts.async_selector_texts(self.hass)
        return self.async_show_form(
            step_id="windows",
            data_schema=schemas.windows(self, selector_texts),
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

        return self.async_show_form(
            step_id="window",
            data_schema=schemas.window(current),
        )

    # -- openingen / openings ------------------------------------------------

    async def async_step_openings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick an opening to edit, or add one, and set the house-wide stops."""
        if user_input is not None:
            # De huisbrede lijst hoort bij dit scherm en niet bij een losse
            # opening: hij hangt aan het apparaat, zodat een raam dat er later
            # bij komt vanzelf meetelt. Hij wordt daarom bij elke uitgang van
            # dit scherm weggeschreven, ook als je alleen doorklikt naar een
            # opening - anders was de keuze weg zodra je er nog iets naast deed.
            #
            # The house-wide list belongs to this screen rather than to a single
            # opening: it hangs on the appliance, so a window added later counts
            # by itself. It is therefore written on every way out of this
            # screen, including clicking through to an opening - otherwise the
            # choice would be gone the moment you did anything else beside it.
            self._installation["house_wide_openings"] = list(
                user_input.get("house_wide_openings") or ()
            )
            choice = user_input["opening"]
            if choice == _BACK:
                return await self.async_step_init()
            self._index = None if choice == _ADD else int(choice)
            return await self.async_step_opening()

        return self.async_show_form(
            step_id="openings",
            data_schema=schemas.openings(self),
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

        return self.async_show_form(
            step_id="opening",
            errors=errors,
            data_schema=schemas.opening(self, current),
        )

    # -- hulpjes / helpers ---------------------------------------------------

    def _list(self, key: str) -> list[dict[str, Any]]:
        """Return the editable list stored under `key`, creating it if needed."""
        return self._installation.setdefault(key, [])

    def _drop_zone_references(self, removed: dict[str, Any]) -> None:
        """Remove a deleted zone from every list that can point at it.

        Openingen en generatoren wijzen met `zone_ids` naar zones, en
        uitsluitende groepen met `source_id`s naar de bronnen van een zone.
        Zonder deze schoonmaak bleven die verwijzingen achter en klaagde
        `validate()` achteraf over onbekende zones en bronnen.

        Openings and generators point at zones through `zone_ids`, and exclusive
        groups at a zone's sources through `source_id`s. Without this cleanup
        those references stayed behind and `validate()` complained afterwards
        about unknown zones and sources.
        """
        zone_id = removed.get("zone_id")
        if zone_id:
            for opening in self._list("openings"):
                opening["zone_ids"] = [
                    item for item in opening.get("zone_ids") or [] if item != zone_id
                ]
            for generator in self._list("generators"):
                generator["zone_ids"] = [
                    item for item in generator.get("zone_ids") or [] if item != zone_id
                ]

        source_ids = {
            source.get("source_id")
            for source in removed.get("sources") or []
            if source.get("source_id")
        }
        self._drop_source_references(source_ids)

    def _drop_source_references(self, source_ids: set[str]) -> None:
        """Remove deleted source ids from every list that can point at them.

        Exclusieve groepen wijzen met `source_id`s naar bronnen. Wordt één bron
        verwijderd, dan hoort zijn ID daar weg te zijn — anders valt het
        apparaat uit de groep (`_group_entities` vindt het bron-ID niet meer)
        en klaagt `validate()` over `exclusive_group_unknown_source`.

        Exclusive groups point at sources through `source_id`s. When one source
        is deleted its id belongs out of there — otherwise the appliance drops
        out of the group (`_group_entities` no longer finds the source id) and
        `validate()` complains about `exclusive_group_unknown_source`.
        """
        if not source_ids:
            return
        groups = self._list("exclusive_groups")
        cleaned = [[item for item in group if item not in source_ids] for group in groups]
        groups[:] = [group for group in cleaned if group]

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


def _heat_cool_from_form(
    user_input: dict[str, Any], current: dict[str, Any], *, unit: str | None = None
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return the stored heat and cool blocks described by a submitted zone form.

    Het formulier toont maar één kant van elke buitengrens en geen
    verwarmingsseizoenen. Wie die waarden eerder instelde - via een oudere
    versie of een met de hand bewerkte configuratie - mag ze bij een gewone
    formulierbewerking niet kwijtraken: wat het formulier niet toont, blijft
    staan.

    `unit` is de eenheid waarin het formulier de temperaturen aanleverde; de
    engine bewaart alles in graden Celsius.

    The form shows only one side of each outdoor bound and no heating seasons.
    Whoever set those values earlier - through an older version or a hand-edited
    configuration - should not lose them on an ordinary form edit: what the form
    does not show stays.

    `unit` is the unit the form supplied the temperatures in; the engine stores
    everything in degrees Celsius.
    """
    stored_heat = current.get("heat") or {}
    stored_cool = current.get("cool") or {}
    stored_heat_outdoor = stored_heat.get("outdoor") or {}
    stored_cool_outdoor = stored_cool.get("outdoor") or {}
    heat = (
        {
            "target": to_celsius(user_input["heat_target"], unit or ""),
            "start_at": to_celsius(user_input["heat_start_at"], unit or ""),
            "hysteresis": delta_to_celsius(user_input["heat_hysteresis"], unit or ""),
            "outdoor": {
                "minimum": stored_heat_outdoor.get("minimum"),
                "maximum": to_celsius(
                    _blank_to_none(user_input.get("heat_outdoor_max")), unit or ""
                ),
            },
            "seasons": stored_heat.get("seasons"),
        }
        if user_input["enable_heat"]
        else None
    )
    cool = (
        {
            "target": to_celsius(user_input["cool_target"], unit or ""),
            "start_at": to_celsius(user_input["cool_start_at"], unit or ""),
            "hysteresis": delta_to_celsius(user_input["cool_hysteresis"], unit or ""),
            "outdoor": {
                "minimum": to_celsius(
                    _blank_to_none(user_input.get("cool_outdoor_min")), unit or ""
                ),
                "maximum": stored_cool_outdoor.get("maximum"),
            },
            "seasons": [Season.SUMMER.value] if user_input["cool_summer_only"] else None,
        }
        if user_input["enable_cool"]
        else None
    )
    return heat, cool


def _zone_from_form(
    user_input: dict[str, Any],
    current: dict[str, Any],
    taken: list[str] | None = None,
    *,
    stored_id: str | None = None,
    unit: str | None = None,
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
    heat, cool = _heat_cool_from_form(user_input, current, unit=unit)
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
