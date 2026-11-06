"""De bronstappen. / The source steps."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigFlowResult

from . import schemas
from .engine.fields import SOURCE_FIELDS

if TYPE_CHECKING:
    from .config_flow import ClimateDirectorOptionsFlow

from .flow_validation import (
    all_source_ids,
    missing,
    unique_id,
)
from .schema_fields import write_table
from .schemas import ADD, BACK, EXIT, EXIT_DROP


async def sources(
    flow: ClimateDirectorOptionsFlow, user_input: dict[str, Any] | None = None
) -> ConfigFlowResult:
    """Pick a source of the current zone to edit, add one, or go back."""
    zone = flow._current_zone()
    if zone is None:
        return await flow.async_step_init()
    if user_input is not None:
        choice = user_input["source"]
        if choice == BACK:
            return await flow.async_step_init()
        flow._source_index = None if choice == ADD else int(choice)
        return await flow.async_step_source()

    return flow.async_show_form(
        step_id="sources",
        data_schema=schemas.sources(flow),
        description_placeholders={"zone": zone.get("name") or zone["zone_id"]},
    )


async def source(
    flow: ClimateDirectorOptionsFlow, user_input: dict[str, Any] | None = None
) -> ConfigFlowResult:
    """Edit one source of the current zone."""
    zone = flow._current_zone()
    if zone is None:
        return await flow.async_step_init()
    sources = zone.setdefault("sources", [])
    current = sources[flow._source_index] if flow._source_index is not None else {}

    errors: dict[str, str] = {}

    if user_input is not None:
        if user_input.get(EXIT) == EXIT_DROP:
            return await flow.async_step_sources()
        if not user_input.get("delete"):
            errors = missing(user_input, "entity_id")
        if errors:
            current = {**current, **user_input}

    if user_input is not None and not errors:
        if user_input.get("delete") and flow._source_index is not None:
            removed_source_id = sources[flow._source_index].get("source_id")
            flow._drop_source_references({removed_source_id} if removed_source_id else set())
            sources.pop(flow._source_index)
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
            if flow._source_index is not None:
                old_entity_id = sources[flow._source_index].get("entity_id")
                if (
                    old_entity_id
                    and old_entity_id != user_input["entity_id"]
                    and old_entity_id in (flow._installation.get("house_wide_openings") or ())
                ):
                    flow._renamed_house_wide.add(old_entity_id)
            # Het `source_id` blijft met de hand: dat is identiteit en geen
            # veld van het scherm, en het mag bij het bewerken niet
            # veranderen. De velden zelf komen uit de tabel.
            #
            # The `source_id` stays by hand: that is identity, not a field of
            # the screen, and it must not change when editing. The fields
            # themselves come from the table.
            source: dict[str, Any] = {
                "source_id": current.get("source_id")
                or unique_id(
                    f"{zone['zone_id']}_{user_input['entity_id'].split('.')[-1]}",
                    all_source_ids(flow._installation),
                )
            }
            write_table(SOURCE_FIELDS, user_input, source, flow=flow)
            if flow._source_index is None:
                sources.append(source)
            else:
                sources[flow._source_index] = source
        flow._source_index = None
        return await flow.async_step_sources()

    return flow.async_show_form(
        step_id="source",
        errors=errors,
        data_schema=schemas.source(flow, current),
    )
