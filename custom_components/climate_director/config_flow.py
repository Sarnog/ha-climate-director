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

from . import (
    flow_circuits,
    flow_generators,
    flow_installation,
    flow_openings,
    flow_residents,
    flow_sources,
    flow_windows,
    flow_zones,
    problems,
    schemas,
    texts,
)
from .const import CONF_INSTALLATION, CONF_SHADOW_MODE, DEFAULT_SHADOW_MODE, DOMAIN
from .coordinator import ClimateDirectorEntry
from .engine import validate
from .engine.serialise import config_from_dict, opening_ids
from .flow_surface import FlowSurface
from .flow_validation import (
    deep_copy,
    missing,
)
from .schemas import (
    CONF_NAME,
    EXIT,
    EXIT_DROP,
    managed_entities,
)


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
            errors = missing(user_input, CONF_NAME)
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
    def async_get_options_flow(_entry: ClimateDirectorEntry) -> OptionsFlow:
        """Return the options flow, where the installation is actually built."""
        return ClimateDirectorOptionsFlow()


class ClimateDirectorOptionsFlow(FlowSurface):
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

    async def async_step_init(self, _user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the main menu."""
        if not self._installation:
            stored = self.config_entry.options.get(CONF_INSTALLATION) or {}
            self._installation = deep_copy(stored)
            self._normalise_opening_ids()
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
                "energy",
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
        steered = managed_entities(self._installation)
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

        if user_input is not None and user_input.get(EXIT) == EXIT_DROP:
            return await self.async_step_init()

        options = dict(self.config_entry.options)
        options[CONF_INSTALLATION] = self._installation
        if self._shadow_mode is not None:
            options[CONF_SHADOW_MODE] = self._shadow_mode
        return self.async_create_entry(data=options)

    # -- algemene instellingen / general settings ----------------------------

    # -- exclusieve groepen / exclusive groups -------------------------------

    # -- stiltevensters / quiet windows --------------------------------------

    # -- zones ---------------------------------------------------------------

    # -- bronnen / sources ---------------------------------------------------

    # -- circuits ------------------------------------------------------------

    # -- prioriteiten op een circuit / priorities on a circuit ---------------

    # -- warmtebronnen / heat generators -------------------------------------

    # -- bewoners / residents ------------------------------------------------

    # -- roosters / schedules ------------------------------------------------

    # -- openingen / openings ------------------------------------------------

    # -- hulpjes / helpers ---------------------------------------------------

    def _normalise_opening_ids(self) -> None:
        """Fill a derived `opening_id` for every opening that lacks one.

        Oudere opslag draagt geen `opening_id`, en deze flow leest de
        ruwe opslag. Zonder deze stap leidt het bewerkscherm het id af uit de
        naam die je net intypt, en dan wisselt de `unique_id` van de
        overbruggingsschakelaar: entiteit weg, geschiedenis weg, elke
        dashboardverwijzing stuk. Daarom dezelfde afleiding als de opslaglezer,
        uit één functie, en wat die toevoegt schrijft het opslagscherm meteen
        mee - de migratie die `async_migrate_entry` niet doet.

        Older storage carries no `opening_id`, and this flow reads
        the raw storage. Without this step the edit screen derives the id from
        the name you just typed, and then the bypass switch's `unique_id`
        changes: entity gone, history gone, every dashboard reference broken.
        Hence the same derivation as the storage reader, from one function, and
        whatever it adds is written along by the save screen - the migration
        `async_migrate_entry` does not do.
        """
        stored = [
            item for item in self._installation.get("openings") or [] if isinstance(item, dict)
        ]
        for opening, opening_id in zip(stored, opening_ids(stored), strict=True):
            opening["opening_id"] = opening_id

    def _list(self, key: str) -> list[dict[str, Any]]:
        """Return the editable list stored under `key`, creating it if needed."""
        found: list[dict[str, Any]] = self._installation.setdefault(key, [])
        return found

    def _groups(self) -> list[list[str]]:
        """Return the exclusive groups, creating the list on first use."""
        found: list[list[str]] = self._installation.setdefault("exclusive_groups", [])
        return found

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
        groups = self._groups()
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

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await flow_installation.settings(self, user_input)

    async def async_step_energy(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await flow_installation.energy(self, user_input)

    async def async_step_exclusives(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await flow_installation.exclusives(self, user_input)

    async def async_step_exclusive(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await flow_installation.exclusive(self, user_input)

    async def async_step_quiets(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await flow_installation.quiets(self, user_input)

    async def async_step_quiet(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await flow_installation.quiet(self, user_input)

    async def async_step_zones(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await flow_zones.zones(self, user_input)

    async def async_step_zone(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await flow_zones.zone(self, user_input)

    async def async_step_sources(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await flow_sources.sources(self, user_input)

    async def async_step_source(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await flow_sources.source(self, user_input)

    async def async_step_circuits(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await flow_circuits.circuits(self, user_input)

    async def async_step_circuit(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await flow_circuits.circuit(self, user_input)

    async def async_step_circuit_priorities(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await flow_circuits.circuit_priorities(self, user_input)

    async def async_step_circuit_priority(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await flow_circuits.circuit_priority(self, user_input)

    async def async_step_generators(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await flow_generators.generators(self, user_input)

    async def async_step_generator(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await flow_generators.generator(self, user_input)

    async def async_step_residents(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await flow_residents.residents(self, user_input)

    async def async_step_resident(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await flow_residents.resident(self, user_input)

    async def async_step_windows(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await flow_windows.windows(self, user_input)

    async def async_step_window(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await flow_windows.window(self, user_input)

    async def async_step_openings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await flow_openings.openings(self, user_input)

    async def async_step_opening(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await flow_openings.opening(self, user_input)
