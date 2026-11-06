"""De openingschermen. / The opening screens."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.helpers import selector

from .form_common import (
    ADD,
    CONF_NAME,
    EXIT,
    EXIT_KEEP,
    add_option,
    back_option,
    exit_row,
    managed_entities,
)
from .schema_fields import (
    SECONDS,
    TEXT,
)


def openings(flow: Any) -> vol.Schema:
    """Return the opening picker schema, house-wide stops included."""
    openings = flow._list("openings")
    options = [
        selector.SelectOptionDict(
            value=str(index),
            label=opening.get("name") or opening.get("opening_id") or opening["entity_id"],
        )
        for index, opening in enumerate(openings)
    ]
    options.append(add_option("opening"))
    options.append(back_option())
    managed = managed_entities(flow._installation)
    # De huisbrede lijst wordt hier alleen voor het scherm gefilterd en niet
    # weggeschreven: het veld zou anders een waarde tonen die zijn eigen
    # schema (`include_entities`) afkeurt, en dan weigert élke inzending,
    # "terug" inbegrepen. De opgeslagen lijst houdt het oude id, zodat het
    # opslaanscherm het via `validate()` kan melden; dit scherm bevestigen
    # schrijft wat het toont en haalt het er zo zelf uit.
    #
    # The house-wide list is filtered for this screen only and not written
    # away: the field would otherwise show a value its own schema
    # (`include_entities`) rejects, and then every submission would be
    # refused, "back" included. The stored list keeps the old id, so the
    # save screen can report it via `validate()`; confirming this screen
    # writes what it shows and thereby removes it by hand.
    suggested = [
        entity_id
        for entity_id in (flow._installation.get("house_wide_openings") or ())
        if entity_id in managed
    ]
    return vol.Schema(
        {
            vol.Required("opening", default=ADD): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    mode=selector.SelectSelectorMode.LIST,
                    translation_key="opening_list",
                )
            ),
            # Alleen apparaten die deze installatie ook echt aanstuurt.
            # Een vrije keuzelijst zou een apparaat toelaten waar de
            # director nooit een commando aan geeft, en dan doet de
            # instelling stilletjes niets - precies het soort val dat
            # niemand terugvindt.
            #
            # Only appliances this installation actually steers. A free
            # picker would allow one the director never commands, and
            # then the setting quietly does nothing - exactly the kind
            # of trap nobody ever traces back.
            vol.Optional(
                "house_wide_openings",
                description={"suggested_value": suggested or None},
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="climate", multiple=True, include_entities=managed
                )
            ),
        }
    )


def opening(flow: Any, current: dict[str, Any]) -> vol.Schema:
    """Return the single opening schema."""
    zone_options = [
        selector.SelectOptionDict(value=zone["zone_id"], label=zone.get("name") or zone["zone_id"])
        for zone in flow._list("zones")
    ]
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=current.get("name", "")): TEXT,
            vol.Optional(
                "entity_id",
                description={"suggested_value": current.get("entity_id") or None},
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["binary_sensor", "cover", "sensor"])
            ),
            vol.Optional(
                "open_state",
                description={"suggested_value": current.get("open_state") or "on"},
            ): TEXT,
            vol.Optional(
                "zone_ids",
                description={"suggested_value": current.get("zone_ids") or []},
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(options=zone_options, multiple=True)
            ),
            vol.Optional(
                "delay", description={"suggested_value": current.get("delay") or None}
            ): SECONDS,
            vol.Required("delete", default=False): bool,
            vol.Required(EXIT, default=EXIT_KEEP): exit_row(),
        }
    )
