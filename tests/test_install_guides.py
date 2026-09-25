"""De zes handleidingen gebruiken de woorden van de interface.

Er leest vandaag geen enkele test of CI-baan `docs/install/*.md`; daardoor zijn
de handleidingen van de interface weggedreven. Deze test maakt ze weer vast:
voor elke taal wordt elke interfacelabel uit `translations/<taal>.json` —
de veldnamen van `options.step.*.data.*` plus de knopteksten `discard`/`keep`
van de actiekeuze — letterlijk in `docs/install/<taal>.md` gezocht.

De uitzonderingenlijst hieronder is letterlijk de stand van dit moment: het
label hoort in de handleiding thuis maar staat er nog niet letterlijk in.
Wordt een label in de vertaling hernoemd, dan is deze test rood; wordt het in
de handleiding gerepareerd, dan is hij óók rood, met de melding "haal deze van
de lijst". Zo kan de lijst alleen korter worden en is hij nooit stiekem
verouderd. De zes bestanden moeten bovendien een gelijk aantal `## `-koppen
houden, zodat geen taal een sectie kwijtraakt zonder dat iemand het merkt.

Gemeten wordt het **proza**: de sectie "Woordenlijst van de interface" wordt er
eerst uit geknipt. Anders telt een label mee zodra het ergens in een tabel
staat, en dan is deze test groen zonder dat er iets bewezen is - dan keurt de
lijst ontbrekende tekst goed in plaats van hem aan te wijzen. De koppentelling
leest het hele bestand, juist zodat de woordenlijst niet stil kan verdwijnen.

De woordenlijst zelf wordt ook bewaakt: de eerste kolom is precies de
uitzonderingenlijst hieronder, niet meer en niet minder, en elke rij noemt een
label dat werkelijk in de vertaling van die taal staat. Die vergelijking staat
in `script/_gen_guides_test.py`, waar de uitzonderingenlijst ook vandaan komt -
één plek, zodat tabel en lijst alleen samen kunnen veranderen.

The six installation guides use the words of the interface.

No test or CI job reads `docs/install/*.md` today; the guides have therefore
drifted away from the interface. This test ties them back: for each language
every interface label from `translations/<language>.json` — the field names of
`options.step.*.data.*` plus the `discard`/`keep` button texts of the action
picker — is looked up literally in `docs/install/<language>.md`.

The exception list below is literally the state of this moment: the label
belongs in the guide but does not yet stand in it literally. When a label is
renamed in the translation this test is red; when the guide is repaired it is
red too, with the message "remove it from the list". That way the list can only
get shorter and is never silently outdated. The six files must also keep an
equal number of `## ` headers, so no language loses a section unnoticed.

What is measured is the **prose**: the "Interface glossary" section is cut out
first. Otherwise a label counts as soon as it stands in any table, and then this
test is green without anything being proven - the list then approves missing
text instead of pointing at it. The header count reads the whole file, exactly
so the glossary cannot disappear quietly.

The glossary itself is guarded too: its first column is exactly the exception
list below, no more and no less, and every row names a label that really stands
in that language's translation. That comparison lives in
`script/_gen_guides_test.py`, where the exception list comes from as well - one
place, so table and list can only change together.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from homeassistant.util import slugify

COMPONENT = Path(__file__).parent.parent / "custom_components" / "climate_director"
TRANSLATIONS = COMPONENT / "translations"
INSTALL = Path(__file__).parent.parent / "docs" / "install"

LANGUAGES = ("en", "nl", "de", "es", "fr", "ar")
BUTTON_SELECTORS = ("when_done",)

#: De kop van de woordenlijst per taal. Deze test knipt die sectie uit de
#: handleiding voordat hij meet, en die koppen moeten dus letterlijk met de
#: zes bestanden overeenkomen - anders knipt hij niets weg en telt de tabel
#: mee. Deze lijst wordt gegenereerd uit `script/_gen_guides_test.py`, waar
#: dezelfde koppen de uitzonderingen meten.
#:
#: The glossary heading per language. This test cuts that section out of the
#: guide before measuring, so the headings have to match the six files
#: literally - otherwise it cuts nothing away and the table counts along.
#: This list is generated from `script/_gen_guides_test.py`, where the same
#: headings measure the exceptions.
GLOSSARY: dict[str, str] = {
    "en": "Interface glossary",
    "nl": "Woordenlijst van de interface",
    "de": "Wörterliste der Oberfläche",
    "es": "Glosario de la interfaz",
    "fr": "Glossaire de l'interface",
    "ar": "قائمة كلمات الواجهة",
}

EXCEPTIONS: dict[str, dict[str, str]] = {
    "en": {
        "options.step.circuit.data.delete": ("Delete this circuit"),
        "options.step.circuit.data.family_switch_delay": ("Pause when swapping duty (seconds)"),
        "options.step.circuit.data.min_cycle_time": ("Rest before a unit may restart (seconds)"),
        "options.step.circuit.data.min_family_switch_interval": (
            "Minimum run before swapping duty (seconds)"
        ),
        "options.step.circuit_priority.data.priority": ("Precedence on this circuit"),
        "options.step.circuits.data.circuit": ("Circuit"),
        "options.step.exclusive.data.delete": ("Delete this group"),
        "options.step.exclusive.data.sources": ("Appliances in this group"),
        "options.step.exclusives.data.group": ("Group"),
        "options.step.generator.data.delete": ("Delete this heat source"),
        "options.step.generators.data.generator": ("Heat source"),
        "options.step.opening.data.delay": ("Delay before suspending (seconds)"),
        "options.step.opening.data.delete": ("Delete this opening"),
        "options.step.quiet.data.delete": ("Delete this window"),
        "options.step.quiet.data.end": ("Quiet until"),
        "options.step.quiet.data.start": ("Quiet from"),
        "options.step.quiet.data.weekdays": ("Days this applies"),
        "options.step.resident.data.delete": ("Delete this resident"),
        "options.step.resident.data.sleep_until": ("Sleep sensor counts until"),
        "options.step.settings.data.guest_days": ("Guest mode days"),
        "options.step.settings.data.guest_end": ("Guest mode until"),
        "options.step.settings.data.max_precondition": ("Maximum pre-conditioning time (minutes)"),
        "options.step.settings.data.stuck_after": ("Report a zone stuck after (minutes)"),
        "options.step.source.data.delete": ("Delete this source"),
        "options.step.source.data.min_cycle_time": (
            "Rest before this appliance may restart (seconds)"
        ),
        "options.step.source.data.takeover_delay": ("Wait this long before taking over (minutes)"),
        "options.step.window.data.delete": ("Delete this schedule"),
        "options.step.zone.data.delete": ("Delete this zone"),
        "options.step.zone.data.presence_entity": ("Presence sensor for this zone"),
        "options.step.zone.data.presence_state": ("State meaning occupied"),
        "options.step.zone.data.presence_timeout": ("Keep counting as occupied for (seconds)"),
    },
    "nl": {
        "options.step.circuit.data.allow_fan_only_during_conflict": (
            "Een zone die verliest mag lucht blijven circuleren"
        ),
        "options.step.circuit.data.delete": ("Dit circuit verwijderen"),
        "options.step.circuit.data.family_switch_delay": (
            "Pauze bij het wisselen van taak (seconden)"
        ),
        "options.step.circuit.data.max_concurrent_units": ("Maximaal aantal units tegelijk aan"),
        "options.step.circuit.data.min_cycle_time": (
            "Rusttijd voordat een unit opnieuw mag starten (seconden)"
        ),
        "options.step.circuit.data.min_family_switch_interval": (
            "Minimale looptijd voor een taakwissel (seconden)"
        ),
        "options.step.circuit_priority.data.priority": ("Voorrang op dit circuit"),
        "options.step.circuits.data.circuit": ("Circuit"),
        "options.step.exclusive.data.delete": ("Deze groep verwijderen"),
        "options.step.exclusive.data.sources": ("Apparaten in deze groep"),
        "options.step.exclusives.data.group": ("Groep"),
        "options.step.generator.data.delete": ("Deze warmtebron verwijderen"),
        "options.step.generator.data.setpoint": ("Vaste doeltemperatuur"),
        "options.step.generators.data.generator": ("Warmtebron"),
        "options.step.opening.data.delay": ("Vertraging voordat er opgeschort wordt (seconden)"),
        "options.step.opening.data.delete": ("Deze opening verwijderen"),
        "options.step.opening.data.zone_ids": ("Zones die dit raakt"),
        "options.step.openings.data.opening": ("Opening"),
        "options.step.quiet.data.delete": ("Dit venster verwijderen"),
        "options.step.quiet.data.end": ("Stilte tot"),
        "options.step.quiet.data.start": ("Stilte vanaf"),
        "options.step.quiet.data.weekdays": ("Dagen waarop dit geldt"),
        "options.step.resident.data.delete": ("Deze bewoner verwijderen"),
        "options.step.resident.data.sleep_state": ("Toestand die slapen betekent"),
        "options.step.resident.data.sleep_until": ("Slaapsensor telt tot"),
        "options.step.settings.data.guest_end": ("Gastenmodus tot"),
        "options.step.settings.data.require_awake": ("Iemand die thuis is moet wakker zijn"),
        "options.step.settings.data.stuck_after": ("Zone geldt als vastgelopen na (minuten)"),
        "options.step.source.data.delete": ("Deze bron verwijderen"),
        "options.step.source.data.min_cycle_time": (
            "Rusttijd voordat dit apparaat opnieuw mag starten (seconden)"
        ),
        "options.step.source.data.takeover_delay": (
            "Wachttijd voordat dit apparaat overneemt (minuten)"
        ),
        "options.step.window.data.delete": ("Dit rooster verwijderen"),
        "options.step.zone.data.cool_start_at": ("Begin met koelen bij"),
        "options.step.zone.data.cool_target": ("Doeltemperatuur koelen"),
        "options.step.zone.data.delete": ("Deze zone verwijderen"),
        "options.step.zone.data.heat_start_at": ("Begin met verwarmen bij"),
        "options.step.zone.data.presence_entity": ("Aanwezigheidssensor van deze zone"),
        "options.step.zone.data.presence_state": ("Toestand die bezet betekent"),
        "options.step.zone.data.presence_timeout": ("Nog zo lang als bezet tellen (seconden)"),
    },
    "de": {
        "options.step.circuit.data.allow_fan_only_during_conflict": (
            "Eine unterlegene Zone darf Luft umwälzen"
        ),
        "options.step.circuit.data.delete": ("Diesen Kreis löschen"),
        "options.step.circuit.data.family_switch_delay": ("Pause beim Aufgabenwechsel (Sekunden)"),
        "options.step.circuit.data.max_concurrent_units": (
            "Höchstzahl gleichzeitig laufender Geräte"
        ),
        "options.step.circuit.data.min_cycle_time": (
            "Ruhezeit, bevor ein Gerät neu starten darf (Sekunden)"
        ),
        "options.step.circuit.data.min_family_switch_interval": (
            "Mindestlaufzeit vor einem Aufgabenwechsel (Sekunden)"
        ),
        "options.step.circuit_priority.data.priority": ("Vorrang in diesem Kreis"),
        "options.step.exclusive.data.delete": ("Diese Gruppe löschen"),
        "options.step.exclusive.data.sources": ("Geräte in dieser Gruppe"),
        "options.step.generator.data.delete": ("Diese Wärmequelle löschen"),
        "options.step.generator.data.entity_id": ("Climate-Entität"),
        "options.step.generator.data.zone_ids": ("Zonen, die er versorgt"),
        "options.step.opening.data.delay": ("Verzögerung vor dem Aussetzen (Sekunden)"),
        "options.step.opening.data.delete": ("Diese Öffnung löschen"),
        "options.step.quiet.data.delete": ("Dieses Fenster löschen"),
        "options.step.quiet.data.end": ("Ruhe bis"),
        "options.step.quiet.data.start": ("Ruhe ab"),
        "options.step.quiet.data.weekdays": ("Tage, an denen das gilt"),
        "options.step.resident.data.delete": ("Diesen Bewohner löschen"),
        "options.step.resident.data.sleep_from": ("Schlafsensor zählt ab"),
        "options.step.resident.data.sleep_state": ("Zustand, der schlafend bedeutet"),
        "options.step.resident.data.sleep_until": ("Schlafsensor zählt bis"),
        "options.step.settings.data.guest_end": ("Gästemodus bis"),
        "options.step.settings.data.heating_layout": ("Heizungsanlage"),
        "options.step.settings.data.max_precondition": ("Maximale Vorbereitungszeit (Minuten)"),
        "options.step.settings.data.require_awake": ("Wer zu Hause ist, muss wach sein"),
        "options.step.settings.data.season_entity": ("Jahreszeit-Entität"),
        "options.step.settings.data.season_source": ("Herkunft der Jahreszeit"),
        "options.step.settings.data.stuck_after": ("Zone gilt als festgefahren nach (Minuten)"),
        "options.step.source.data.delete": ("Diese Quelle löschen"),
        "options.step.source.data.entity_id": ("Climate-Entität"),
        "options.step.source.data.min_cycle_time": (
            "Ruhezeit, bevor dieses Gerät erneut starten darf (Sekunden)"
        ),
        "options.step.source.data.takeover_delay": (
            "So lange warten, bevor übernommen wird (Minuten)"
        ),
        "options.step.window.data.delete": ("Diesen Zeitplan löschen"),
        "options.step.zone.data.cool_outdoor_min": ("Nur kühlen über dieser Außentemperatur"),
        "options.step.zone.data.cool_start_at": ("Kühlen beginnen bei"),
        "options.step.zone.data.delete": ("Diese Zone löschen"),
        "options.step.zone.data.heat_outdoor_max": ("Nur heizen unter dieser Außentemperatur"),
        "options.step.zone.data.heat_start_at": ("Heizen beginnen bei"),
        "options.step.zone.data.presence_entity": ("Anwesenheitssensor dieser Zone"),
        "options.step.zone.data.presence_state": ("Zustand, der belegt bedeutet"),
        "options.step.zone.data.presence_timeout": ("Noch so lange als belegt zählen (Sekunden)"),
    },
    "es": {
        "options.step.circuit.data.allow_fan_only_during_conflict": (
            "Una zona que pierde puede mover aire"
        ),
        "options.step.circuit.data.conflict_policy": ("Regla de conflicto"),
        "options.step.circuit.data.delete": ("Eliminar este circuito"),
        "options.step.circuit.data.family_switch_delay": ("Pausa al cambiar de tarea (segundos)"),
        "options.step.circuit.data.max_concurrent_units": (
            "Número máximo de unidades funcionando a la vez"
        ),
        "options.step.circuit.data.min_cycle_time": (
            "Descanso antes de que una unidad pueda rearrancar (segundos)"
        ),
        "options.step.circuit.data.min_family_switch_interval": (
            "Tiempo mínimo antes de cambiar de tarea (segundos)"
        ),
        "options.step.circuit.data.when_done": ("Cuando termines aquí"),
        "options.step.circuit_priorities.data.when_done": ("Cuando termines aquí"),
        "options.step.circuit_priority.data.priority": ("Prioridad en este circuito"),
        "options.step.circuit_priority.data.when_done": ("Cuando termines aquí"),
        "options.step.circuits.data.when_done": ("Cuando termines aquí"),
        "options.step.exclusive.data.delete": ("Eliminar este grupo"),
        "options.step.exclusive.data.sources": ("Aparatos de este grupo"),
        "options.step.exclusive.data.when_done": ("Cuando termines aquí"),
        "options.step.exclusives.data.when_done": ("Cuando termines aquí"),
        "options.step.generator.data.delete": ("Eliminar esta fuente de calor"),
        "options.step.generator.data.entity_id": ("Entidad climate"),
        "options.step.generator.data.when_done": ("Cuando termines aquí"),
        "options.step.generator.data.zone_ids": ("Zonas a las que sirve"),
        "options.step.generators.data.generator": ("Fuente de calor"),
        "options.step.generators.data.when_done": ("Cuando termines aquí"),
        "options.step.opening.data.delay": ("Retardo antes de suspender (segundos)"),
        "options.step.opening.data.delete": ("Eliminar esta abertura"),
        "options.step.opening.data.when_done": ("Cuando termines aquí"),
        "options.step.openings.data.opening": ("Abertura"),
        "options.step.openings.data.when_done": ("Cuando termines aquí"),
        "options.step.quiet.data.delete": ("Eliminar esta franja"),
        "options.step.quiet.data.end": ("Silencio hasta"),
        "options.step.quiet.data.start": ("Silencio desde"),
        "options.step.quiet.data.weekdays": ("Días en que se aplica"),
        "options.step.quiet.data.when_done": ("Cuando termines aquí"),
        "options.step.resident.data.delete": ("Eliminar este residente"),
        "options.step.resident.data.sleep_from": ("El sensor de sueño cuenta desde"),
        "options.step.resident.data.sleep_until": ("El sensor de sueño cuenta hasta"),
        "options.step.resident.data.when_done": ("Cuando termines aquí"),
        "options.step.residents.data.when_done": ("Cuando termines aquí"),
        "options.step.settings.data.guest_end": ("Modo invitados hasta"),
        "options.step.settings.data.guest_start": ("Modo invitados desde"),
        "options.step.settings.data.holiday_keyword": ("Palabra que indica vacaciones"),
        "options.step.settings.data.max_precondition": (
            "Tiempo máximo de preacondicionamiento (minutos)"
        ),
        "options.step.settings.data.season_source": ("Origen de la estación"),
        "options.step.settings.data.stuck_after": ("Zona se considera atascada tras (minutos)"),
        "options.step.settings.data.when_done": ("Cuando termines aquí"),
        "options.step.source.data.delete": ("Eliminar esta fuente"),
        "options.step.source.data.entity_id": ("Entidad climate"),
        "options.step.source.data.min_cycle_time": (
            "Descanso antes de que este aparato pueda reiniciarse (segundos)"
        ),
        "options.step.source.data.outdoor_min": ("Usar a partir de esta temperatura exterior"),
        "options.step.source.data.role": ("Lo que puede hacer este aparato"),
        "options.step.source.data.takeover_delay": (
            "Esperar este tiempo antes de asumir el relevo (minutos)"
        ),
        "options.step.source.data.when_done": ("Cuando termines aquí"),
        "options.step.sources.data.when_done": ("Cuando termines aquí"),
        "options.step.window.data.delete": ("Eliminar este horario"),
        "options.step.window.data.start": ("Desde"),
        "options.step.window.data.when_done": ("Cuando termines aquí"),
        "options.step.windows.data.when_done": ("Cuando termines aquí"),
        "options.step.zone.data.cool_hysteresis": ("Banda muerta de refrigeración"),
        "options.step.zone.data.cool_start_at": ("Empezar a enfriar en"),
        "options.step.zone.data.cool_target": ("Temperatura objetivo al enfriar"),
        "options.step.zone.data.delete": ("Eliminar esta zona"),
        "options.step.zone.data.heat_hysteresis": ("Banda muerta de calefacción"),
        "options.step.zone.data.heat_start_at": ("Empezar a calentar en"),
        "options.step.zone.data.heat_target": ("Temperatura objetivo al calentar"),
        "options.step.zone.data.presence_entity": ("Sensor de presencia de esta zona"),
        "options.step.zone.data.presence_state": ("Estado que significa ocupada"),
        "options.step.zone.data.presence_timeout": (
            "Seguir contando como ocupada durante (segundos)"
        ),
        "options.step.zone.data.when_done": ("Cuando termines aquí"),
        "options.step.zones.data.when_done": ("Cuando termines aquí"),
    },
    "fr": {
        "options.step.circuit.data.allow_fan_only_during_conflict": (
            "Une zone perdante peut brasser l'air"
        ),
        "options.step.circuit.data.delete": ("Supprimer ce circuit"),
        "options.step.circuit.data.family_switch_delay": (
            "Pause lors du changement de tâche (secondes)"
        ),
        "options.step.circuit.data.max_concurrent_units": (
            "Nombre maximal d'unités en marche simultanément"
        ),
        "options.step.circuit.data.min_cycle_time": (
            "Repos avant qu'une unité puisse redémarrer (secondes)"
        ),
        "options.step.circuit.data.min_family_switch_interval": (
            "Durée minimale avant un changement de tâche (secondes)"
        ),
        "options.step.circuit_priority.data.priority": ("Priorité sur ce circuit"),
        "options.step.exclusive.data.delete": ("Supprimer ce groupe"),
        "options.step.exclusive.data.sources": ("Appareils de ce groupe"),
        "options.step.generator.data.delete": ("Supprimer cette source de chaleur"),
        "options.step.generator.data.entity_id": ("Entité climate"),
        "options.step.generator.data.zone_ids": ("Zones qu'il dessert"),
        "options.step.generators.data.generator": ("Source de chaleur"),
        "options.step.opening.data.delay": ("Délai avant suspension (secondes)"),
        "options.step.opening.data.delete": ("Supprimer cette ouverture"),
        "options.step.openings.data.opening": ("Ouverture"),
        "options.step.quiet.data.delete": ("Supprimer cette plage"),
        "options.step.quiet.data.end": ("Silence jusqu'à"),
        "options.step.quiet.data.start": ("Silence à partir de"),
        "options.step.quiet.data.weekdays": ("Jours concernés"),
        "options.step.resident.data.delete": ("Supprimer cet occupant"),
        "options.step.resident.data.sleep_from": ("Le capteur de sommeil compte à partir de"),
        "options.step.resident.data.sleep_until": ("Le capteur de sommeil compte jusqu'à"),
        "options.step.settings.data.guest_end": ("Mode invités jusqu'à"),
        "options.step.settings.data.guest_start": ("Mode invités à partir de"),
        "options.step.settings.data.holiday_calendars": ("Agendas de vacances"),
        "options.step.settings.data.holiday_keyword": ("Mot qui signale des vacances"),
        "options.step.settings.data.max_precondition": (
            "Durée maximale de la préparation (minutes)"
        ),
        "options.step.settings.data.require_awake": ("Une personne présente doit être éveillée"),
        "options.step.settings.data.season_source": ("Origine de la saison"),
        "options.step.settings.data.stuck_after": ("Zone considérée bloquée après (minutes)"),
        "options.step.source.data.delete": ("Supprimer cette source"),
        "options.step.source.data.entity_id": ("Entité climate"),
        "options.step.source.data.min_cycle_time": (
            "Repos avant que cet appareil puisse redémarrer (secondes)"
        ),
        "options.step.source.data.priority": ("Ordre au sein de cette zone"),
        "options.step.source.data.role": ("Ce que cet appareil sait faire"),
        "options.step.source.data.takeover_delay": (
            "Attendre ce délai avant de prendre le relais (minutes)"
        ),
        "options.step.window.data.delete": ("Supprimer ce planning"),
        "options.step.zone.data.cool_hysteresis": ("Bande morte de refroidissement"),
        "options.step.zone.data.cool_outdoor_min": (
            "Refroidir uniquement au-dessus de cette température extérieure"
        ),
        "options.step.zone.data.cool_start_at": ("Commencer à refroidir à"),
        "options.step.zone.data.cool_summer_only": ("Refroidir uniquement en été"),
        "options.step.zone.data.cool_target": ("Température cible en refroidissement"),
        "options.step.zone.data.delete": ("Supprimer cette zone"),
        "options.step.zone.data.gate": ("Ce qui décide si cette zone fonctionne"),
        "options.step.zone.data.heat_hysteresis": ("Bande morte de chauffage"),
        "options.step.zone.data.heat_outdoor_max": (
            "Chauffer uniquement sous cette température extérieure"
        ),
        "options.step.zone.data.heat_start_at": ("Commencer à chauffer à"),
        "options.step.zone.data.heat_target": ("Température cible en chauffage"),
        "options.step.zone.data.presence_entity": ("Capteur de présence de cette zone"),
        "options.step.zone.data.presence_state": ("État signifiant occupée"),
        "options.step.zone.data.presence_timeout": (
            "Continuer à compter comme occupée pendant (secondes)"
        ),
    },
    "ar": {
        "options.step.circuit.data.delete": ("حذف هذه الدائرة"),
        "options.step.circuit.data.when_done": ("عند الانتهاء هنا"),
        "options.step.circuit_priorities.data.when_done": ("عند الانتهاء هنا"),
        "options.step.circuit_priority.data.when_done": ("عند الانتهاء هنا"),
        "options.step.circuits.data.when_done": ("عند الانتهاء هنا"),
        "options.step.exclusive.data.delete": ("حذف هذه المجموعة"),
        "options.step.exclusive.data.when_done": ("عند الانتهاء هنا"),
        "options.step.exclusives.data.when_done": ("عند الانتهاء هنا"),
        "options.step.generator.data.delete": ("حذف مصدر الحرارة هذا"),
        "options.step.generator.data.when_done": ("عند الانتهاء هنا"),
        "options.step.generators.data.when_done": ("عند الانتهاء هنا"),
        "options.step.opening.data.delete": ("حذف هذه الفتحة"),
        "options.step.opening.data.when_done": ("عند الانتهاء هنا"),
        "options.step.openings.data.when_done": ("عند الانتهاء هنا"),
        "options.step.quiet.data.delete": ("حذف هذه النافذة"),
        "options.step.quiet.data.when_done": ("عند الانتهاء هنا"),
        "options.step.resident.data.delete": ("حذف هذا الساكن"),
        "options.step.resident.data.when_done": ("عند الانتهاء هنا"),
        "options.step.residents.data.when_done": ("عند الانتهاء هنا"),
        "options.step.settings.data.when_done": ("عند الانتهاء هنا"),
        "options.step.source.data.delete": ("حذف هذا المصدر"),
        "options.step.source.data.when_done": ("عند الانتهاء هنا"),
        "options.step.sources.data.when_done": ("عند الانتهاء هنا"),
        "options.step.window.data.delete": ("حذف هذا الجدول"),
        "options.step.window.data.when_done": ("عند الانتهاء هنا"),
        "options.step.windows.data.when_done": ("عند الانتهاء هنا"),
        "options.step.zone.data.delete": ("حذف هذه المنطقة"),
        "options.step.zone.data.when_done": ("عند الانتهاء هنا"),
        "options.step.zones.data.when_done": ("عند الانتهاء هنا"),
    },
}


def load(path: Path) -> dict:
    """Return one JSON file as a dict."""
    return json.loads(path.read_text(encoding="utf-8"))


def interface_labels(language: str) -> dict[str, str]:
    """Every label of the options flow, keyed by its dotted path.

    De veldnamen van `options.step.*.data.*` zijn wat de gebruiker naast elk
    formulierveld leest; de actiekeuze (`when_done`) draagt de knopteksten
    waaronder `discard` en `keep`.
    """
    data = load(TRANSLATIONS / f"{language}.json")
    labels: dict[str, str] = {}
    for step, step_data in data.get("options", {}).get("step", {}).items():
        if not isinstance(step_data, dict):
            continue
        fields = step_data.get("data")
        if isinstance(fields, dict):
            for key, value in fields.items():
                if isinstance(value, str):
                    labels[f"options.step.{step}.data.{key}"] = value
    for selector_name in BUTTON_SELECTORS:
        options = data.get("selector", {}).get(selector_name, {}).get("options", {})
        for key, value in options.items():
            if isinstance(value, str):
                labels[f"selector.{selector_name}.options.{key}"] = value
    return labels


def guide_raw(language: str) -> str:
    """The whole installation guide of one language, glossary included."""
    return (INSTALL / f"{language}.md").read_text(encoding="utf-8")


def guide_text(language: str) -> str:
    """The guide's prose, without the interface glossary section.

    De woordenlijst staat in de handleiding voor de lezer, niet voor deze ratel:
    die meet of het **proza** de woorden van de interface gebruikt. Zonder deze
    knip telt elk label mee dat ergens in een tabel staat, en dan is de bewaking
    groen zonder dat er iets bewezen is. Dan keurt de lijst ontbrekende tekst
    goed in plaats van hem aan te wijzen.

    The glossary is in the guide for the reader, not for this ratchet: it
    measures whether the **prose** uses the interface's words. Without this cut
    every label in any table counts, and then the guard is green without
    anything being proven - the list then approves missing text instead of
    pointing at it.
    """
    lines = guide_raw(language).splitlines(keepends=True)
    keep: list[str] = []
    skipping = False
    for line in lines:
        if line.strip() == f"## {GLOSSARY[language]}":
            skipping = True
            continue
        if skipping and line.startswith("## "):
            skipping = False
        if not skipping:
            keep.append(line)
    return "".join(keep)


def test_every_guide_uses_the_words_of_its_interface() -> None:
    """Elk interfacelabel staat letterlijk in de handleiding van die taal.

    Every interface label stands literally in that language's guide.
    """
    problems: list[str] = []
    for language in LANGUAGES:
        labels = interface_labels(language)
        text = guide_text(language)
        exceptions = EXCEPTIONS.get(language, {})
        for key, value in sorted(labels.items()):
            if value in text:
                continue
            noted = exceptions.get(key)
            if noted is None:
                problems.append(
                    f"{language}: label {key} = {value!r} komt niet letterlijk "
                    f"voor in docs/install/{language}.md"
                )
            elif noted != value:
                problems.append(
                    f"{language}: label {key} is veranderd van {noted!r} naar "
                    f"{value!r}; pas de uitzondering aan"
                )
        for key, noted in sorted(exceptions.items()):
            if key not in labels:
                problems.append(
                    f"{language}: uitzondering {key} bestaat niet meer in "
                    f"translations/{language}.json; haal deze van de lijst"
                )
                continue
            value = labels[key]
            if noted != value:
                if value in text:
                    problems.append(
                        f"{language}: label {key} is veranderd en staat nu wél "
                        f"in de handleiding; haal deze van de lijst"
                    )
            elif value in text:
                problems.append(
                    f"{language}: label {key} = {noted!r} staat nu wél in de "
                    f"handleiding; haal deze van de lijst"
                )
    assert not problems, "de handleidingen drijven weg van de interface:\n" + "\n".join(problems)


def entity_names(language: str) -> dict[tuple[str, str], str]:
    """Elke vertaalde entiteitsnaam, per domein en translation_key.

    Every translated entity name, per domain and translation key.
    """
    data = load(TRANSLATIONS / f"{language}.json")
    names: dict[tuple[str, str], str] = {}
    for domain, keys in data.get("entity", {}).items():
        if not isinstance(keys, dict):
            continue
        for key, info in keys.items():
            if isinstance(info, dict) and isinstance(info.get("name"), str):
                names[(domain, key)] = info["name"]
    return names


def test_every_guide_names_its_own_entity_ids() -> None:
    """Elke handleiding noemt de entiteit-ID's die HA van die taal afleidt.

    Home Assistant leidt de entiteit-ID af van de vertaalde naam: op een Duitse
    HA heet de mismatchesensor `sensor.*_abweichungen`, niet
    `sensor.*_mismatch`. Deze bewaking rekent per taal de verwachte ID-patronen
    uit met dezelfde `slugify` die HA gebruikt en eist dat elk patroon letterlijk
    in de handleiding staat. Placeholders als `{zone}` verschijnen in de
    handleiding als `<zone>`, dus die vorm wordt in het patroon teruggezet.

    Every guide names the entity ids HA derives from that language. Home
    Assistant derives the entity id from the translated name: on a German HA
    the mismatch sensor is called `sensor.*_abweichungen`, not
    `sensor.*_mismatch`. This guard computes each language's expected id
    patterns with the same `slugify` HA uses and requires every pattern to
    stand literally in the guide. Placeholders such as `{zone}` appear in the
    guide as `<zone>`, so that form is put back into the pattern.
    """
    problems: list[str] = []
    for language in LANGUAGES:
        text = guide_text(language)
        for (domain, key), name in sorted(entity_names(language).items()):
            pattern = slugify(name)
            for placeholder in re.findall(r"\{[a-z_]+\}", name):
                pattern = pattern.replace(slugify(placeholder), f"<{placeholder[1:-1]}>")
            needle = f"{domain}.*_{pattern}"
            if needle not in text:
                problems.append(
                    f"{language}: entiteit {domain}.{key} = {name!r} hoort als "
                    f"`{needle}` in docs/install/{language}.md te staan"
                )
    assert not problems, "de entiteit-ID's drijven weg van de interface:\n" + "\n".join(problems)


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_guide_has_the_same_number_of_headers(language: str) -> None:
    """Zes bestanden, een gelijk aantal `## `-koppen.

    Deze telt het hele bestand (`guide_raw`), dus de woordenlijst-sectie telt
    mee: die is van de lezer en mag in geen enkele taal ontbreken.

    This one counts the whole file (`guide_raw`), so the glossary section counts
    along: it is the reader's and may be missing from no language.
    """
    counts = {
        lang: len(re.findall(r"^## ", guide_raw(lang), flags=re.MULTILINE)) for lang in LANGUAGES
    }
    assert len(set(counts.values())) == 1, f"ongelijke koppentelling: {counts}"
    assert counts[language] > 0, f"{language}: geen enkele `## `-kop"


def glossary_cells(language: str) -> list[list[str]]:
    """Elke rij van de woordenlijst-sectie als lijst cellen, in bestandsorde.

    De kopregel en de scheidingsregel (`|---|---|`) tellen niet mee; alles wat
    daarna in de sectie met een `|` begint is een rij van de lezer.

    Every row of the interface glossary section as a list of cells, in file
    order. The header row and the separator row (`|---|---|`) do not count;
    everything after that inside the section, starting with `|`, is a row for the
    reader.
    """
    rows: list[list[str]] = []
    inside = False
    separator_seen = False
    for line in guide_raw(language).splitlines():
        stripped = line.strip()
        if stripped == f"## {GLOSSARY[language]}":
            inside = True
            continue
        if inside and line.startswith("## "):
            break
        if not inside or not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 2:
            continue
        if set(cells[0]) <= set("-: "):
            separator_seen = True
            continue
        if not separator_seen:
            continue
        rows.append(cells)
    return rows


def glossary_rows(language: str) -> list[str]:
    """De eerste kolom van de woordenlijst-sectie, in bestandsorde.

    The first column of the interface glossary section, in file order.
    """
    return [cells[0] for cells in glossary_cells(language)]


def test_the_glossary_is_the_exception_list() -> None:
    """De woordenlijst is de uitzonderingenlijst van die taal, en niets anders.

    Wat hier vastligt: de eerste kolom van de woordenlijst-sectie komt exact
    overeen met `EXCEPTIONS[taal]` - elke rij staat op de lijst en elke regel van
    de lijst heeft een rij - en elke rij noemt een label dat werkelijk in
    `translations/<taal>.json` staat. Die tweede eis is de scherpe kant: een
    verdwenen interfaceknop laat een rij staan die nergens meer naar verwijst, en
    dat is precies hoe deze tabel eerder is weggelopen. Vergeleken wordt op de
    **tekst** van het label, niet op de sleutel: een label dat twee sleutels
    deelt (een `when_done`-knop die op elk scherm hetzelfde heet) hoort één rij
    te hebben, niet twee. Staat dezelfde rij twee keer in de sectie, dan is dat
    ook rood: een `set` zou de dubbele stil laten vallen.

    What this pins down: the glossary's first column matches `EXCEPTIONS[language]`
    exactly - every row stands on the list and every line of the list has a row -
    and every row names a label that really stands in `translations/<language>.json`.
    That second demand is the sharp side: a disappeared interface button leaves a
    row pointing at nothing, and that is exactly how this table drifted before.
    The comparison is on the **text** of the label, not on the key: a label two
    keys share (a `when_done` button that is called the same on every screen)
    belongs in one row, not two. A row standing twice in the section is red as
    well: a `set` would quietly let the duplicate fall.
    """
    problems: list[str] = []
    for language in LANGUAGES:
        rows = glossary_rows(language)
        expected = {value for value in EXCEPTIONS.get(language, {}).values()}
        labels = set(interface_labels(language).values())
        pairs = [tuple(cells[:2]) for cells in glossary_cells(language)]
        duplicates = sorted({pair for pair in pairs if pairs.count(pair) > 1})
        for pair in duplicates:
            note = f"{language}: rij {pair[0]!r} bij {pair[1]!r} staat er twee keer"
            problems.append(note)
        for row in sorted(set(rows) - expected):
            problems.append(
                f"{language}: de woordenlijst noemt {row!r}, en dat staat niet op de "
                f"uitzonderingenlijst; haal de rij weg"
            )
        for row in sorted(expected - set(rows)):
            problems.append(
                f"{language}: de uitzonderingenlijst noemt {row!r} en de woordenlijst "
                f"niet; zet de rij erin of haal de regel van de lijst"
            )
        for row in sorted(set(rows)):
            if row not in labels:
                problems.append(
                    f"{language}: de woordenlijst noemt {row!r}, en dat label bestaat "
                    f"niet in translations/{language}.json"
                )
    assert not problems, "de woordenlijst is de uitzonderingenlijst niet:\n" + "\n".join(problems)
