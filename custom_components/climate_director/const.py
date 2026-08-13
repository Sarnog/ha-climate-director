"""Constanten voor Climate Director.

Constants for Climate Director.
"""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "climate_director"

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SWITCH,
]

# Event dat na elke beslissing op de Home Assistant event bus komt, zodat
# gebruikers hun eigen notificatie-automatiseringen kunnen bouwen.
#
# Event fired on the Home Assistant event bus after every decision, so users
# can build their own notification automations.
EVENT_DECISION = f"{DOMAIN}_decision"

# Sleutels in de config entry.
# Keys in the config entry.
CONF_INSTALLATION = "installation"
CONF_SHADOW_MODE = "shadow_mode"

# Schaduwmodus staat standaard AAN. Een integratie die bij de eerste start
# meteen de verwarming van een huis overneemt is de verkeerde standaard; wie
# hem laat uitvoeren moet dat bewust aanzetten.
#
# Shadow mode defaults to ON. An integration that takes over a house's heating
# the moment it first starts is the wrong default; letting it execute should be
# a deliberate choice.
DEFAULT_SHADOW_MODE = True

# Zo lang wordt er gewacht na een toestandswijziging voordat er opnieuw
# besloten wordt. Eén klimaatcommando veroorzaakt meerdere state changes; zonder
# deze pauze zou elke daarvan een eigen beslisronde starten.
#
# How long to wait after a state change before deciding again. One climate
# command causes several state changes; without this pause each of them would
# start its own decision round.
DEBOUNCE_SECONDS = 1.0

# Ondergrens voor een uitgestelde herberekening, zodat een timer die al
# verlopen is niet in een strakke lus terechtkomt.
#
# Floor for a deferred re-evaluation, so an already-expired timer cannot end up
# in a tight loop.
MIN_DEFERRAL_SECONDS = 1.0
