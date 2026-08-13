"""Constanten voor Climate Director.

Constants for Climate Director.
"""

from __future__ import annotations

DOMAIN = "climate_director"

# Event dat na elke beslissing op de Home Assistant event bus komt, zodat
# gebruikers hun eigen notificatie-automatiseringen kunnen bouwen.
#
# Event fired on the Home Assistant event bus after every decision, so users
# can build their own notification automations.
EVENT_DECISION = f"{DOMAIN}_decision"
