"""De bewonerstappen. / The resident steps."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigFlowResult

from . import schemas

if TYPE_CHECKING:
    from .config_flow import ClimateDirectorOptionsFlow

from .flow_validation import (
    missing,
    unique_id,
)
from .schemas import ADD, BACK, CONF_NAME, EXIT, EXIT_DROP


async def residents(
    flow: ClimateDirectorOptionsFlow, user_input: dict[str, Any] | None = None
) -> ConfigFlowResult:
    """Pick a resident to edit, or add one."""
    if user_input is not None:
        choice = user_input["resident"]
        if choice == BACK:
            return await flow.async_step_init()
        flow._resident_index = None if choice == ADD else int(choice)
        return await flow.async_step_resident()

    return flow.async_show_form(
        step_id="residents",
        data_schema=schemas.residents(flow),
    )


async def resident(
    flow: ClimateDirectorOptionsFlow, user_input: dict[str, Any] | None = None
) -> ConfigFlowResult:
    """Edit one resident."""
    residents = flow._list("residents")
    current = residents[flow._resident_index] if flow._resident_index is not None else {}

    errors: dict[str, str] = {}

    if user_input is not None:
        if user_input.get(EXIT) == EXIT_DROP:
            return await flow.async_step_residents()
        if not user_input.get("delete"):
            errors = missing(user_input, "presence_entity")
        if errors:
            current = {**current, **user_input}

    if user_input is not None and not errors:
        if user_input.get("delete") and flow._resident_index is not None:
            residents.pop(flow._resident_index)
            flow._resident_index = None
            return await flow.async_step_init()

        person = {
            "resident_id": current.get("resident_id")
            or unique_id(
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
                "weekdays": ([int(day) for day in user_input.get("sleep_in_days") or ()] or None),
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
            # Geen tijd = geen rem; de dagen blijven staan, zoals hierboven.
            # No time = no brake; the days are kept, as above.
            "rise_brake": {
                "at": user_input.get("rise_from") or "",
                "weekdays": ([int(day) for day in user_input.get("rise_days") or ()] or None),
            },
            # De roosters van deze bewoner blijven staan; die worden in de
            # volgende stap bewerkt, niet in dit formulier.
            #
            # This resident's schedules are kept; they are edited in the
            # next step, not in this form.
            "windows": current.get("windows") or [],
        }
        if flow._resident_index is None:
            residents.append(person)
            flow._resident_index = len(residents) - 1
        else:
            residents[flow._resident_index] = person
        return await flow.async_step_windows()

    return flow.async_show_form(
        step_id="resident",
        errors=errors,
        data_schema=schemas.resident(current),
    )
