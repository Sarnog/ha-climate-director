"""Constanten voor Climate Director.

Constants for Climate Director.
"""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "climate_director"

#: Versie van het opslagbestand voor lopende vooruit-verzoeken. Verhoog dit
#: alleen als de vorm verandert, en schrijf er dan een migratie bij.
#:
#: Version of the store holding running pre-conditioning requests. Raise this
#: only when its shape changes, and write a migration along with it.
STORAGE_VERSION = 1

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]

# Event dat na elke beslissing op de Home Assistant event bus komt, zodat
# gebruikers hun eigen notificatie-automatiseringen kunnen bouwen.
#
# Event fired on the Home Assistant event bus after every decision, so users
# can build their own notification automations.
EVENT_DECISION = f"{DOMAIN}_decision"

#: Gaat af wanneer een vooruit-verzoek strandt op een openstaand raam of
#: deur. De integratie stuurt zelf geen berichten - waar een melding heen
#: gaat is niets waar een klimaatregelaar over hoort te beslissen - dus dit
#: is het haakje waar een eigen automatisering aan hangt.
#:
#: Fires when a pre-conditioning request runs aground on an open window or
#: door. The integration sends no messages of its own - where a notification
#: goes is nothing a climate controller should decide - so this is the hook
#: an automation of your own hangs on.
EVENT_PRECONDITION_REFUSED = f"{DOMAIN}_precondition_refused"

# Actie om nu opnieuw te laten beslissen, zonder te wachten tot een gevolgde
# entiteit uit zichzelf verandert. Handig bij het inrichten en bij het napluizen
# van een afwijking.
#
# Action to decide again right now, without waiting for a tracked entity to
# change of its own accord. Useful while setting up and while chasing down a
# difference.
SERVICE_EVALUATE = "evaluate"
ATTR_ENTRY_ID = "entry_id"

# Vooruit verwarmen of koelen voor wie onderweg naar huis is. Alleen met de
# hand aan te zetten, met een teller die vanzelf afloopt - er is geen schakelaar
# die aan kan blijven staan.
#
# Pre-conditioning for somebody on their way home. Only ever switched on by
# hand, with a timer that runs out by itself - there is no switch here that can
# be left on.
SERVICE_PRECONDITION = "precondition"
SERVICE_CANCEL_PRECONDITION = "cancel_precondition"
ATTR_ZONE_IDS = "zone_ids"
ATTR_MINUTES = "minutes"
ATTR_IGNORE_OPENINGS = "ignore_openings"

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
