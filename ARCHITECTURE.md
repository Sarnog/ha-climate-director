# ARCHITECTURE.md

## NL

Technisch ontwerpdocument voor wie aan de code werkt (geen gebruikershandleiding —
dat is [`README.md`](README.md)). Elke laag heeft precies één verantwoordelijkheid.

### De belangrijkste scheidslijn

Het project bestaat uit twee helften met een harde grens ertussen:

```
custom_components/climate_director/
  ├─ engine/          ← pure Python. Geen hass, geen entiteiten, geen I/O.
  └─ (de rest)        ← alles wat Home Assistant aanraakt.
```

`engine/` importeert Home Assistant nergens. Alle besliskunde zit daar, en is dus als
gewoon dataobject na te bouwen en in milliseconden te testen zonder draaiende Home
Assistant. Elk denkbaar klimaatscenario — nachtvorst, twee zones die ruziën om één
buitenunit, een openstaande deur tijdens een taakwissel — is een unit test in plaats van
een middag handmatig proberen.

Die grens is geen stijlkeuze. De reden dat losse automatiseringen voor dit probleem
onhoudbaar worden, is dat besliskunde en uitvoering door elkaar lopen; deze scheiding is
precies de correctie daarop.

### Overzicht

```
Home Assistant (entiteitstoestanden, klokgebeurtenissen)
      │
      ▼
  coordinator          verzamelt toestanden, ontdubbelt, serialiseert   [nog te bouwen]
      │
      ▼
  world.WorldState     momentopname: één dataobject, verder niets
      │
      ▼
┌─ engine/ ────────────────────────────────────────────────────────┐
│                                                                  │
│  gates.py       mag er geregeld worden (omstandigheden)          │
│      │                                                           │
│      ▼                                                           │
│  hysteresis.py  moet er geregeld worden (temperaturen)           │
│      │                                                           │
│      ▼                                                           │
│  sources.py     welk apparaat levert die taak                    │
│      │                                                           │
│      ▼                                                           │
│  constraints.py wat mag er tegelijk op één buitenunit            │
│      │                                                           │
│      ▼                                                           │
│  decide.py      één samenhangend Plan                            │
│                                                                  │
│  models.py      configuratie (Zone, Source, Circuit, …)          │
│  families.py    hvac_mode → compressorbedrijf                    │
│  plan.py        uitvoer (UnitCommand, ZoneDecision, Reason, …)   │
└──────────────────────────────────────────────────────────────────┘
      │
      ▼
  applier              vergelijkt Plan met werkelijkheid, roept aan   [nog te bouwen]
      │
      ▼
  entiteiten + event   climate/sensor/switch/number/select/button     [nog te bouwen]
```

### families.py — modusfamilies

Zet een `hvac_mode` om naar het *compressorbedrijf* dat hij claimt. Een conflict op een
multi-split ontstaat niet tussen standen maar tussen bedrijven:

- `heat` → HEAT
- `cool`, `dry` → COOL (ontvochtigen is koelbedrijf)
- `off`, `fan_only` → NEUTRAL (geen compressorclaim, altijd toegestaan)
- `heat_cool`, `auto` → AMBIGUOUS (de unit kiest zelf)

Een onbekende stand telt als AMBIGUOUS, niet als NEUTRAL: een stand die deze engine niet
kent kan best de compressor laten draaien, en die als onschuldig behandelen is de
schadelijkste manier om fout te zitten.

### models.py — configuratie

Uitsluitend dataclasses plus `validate()`. Drie niveaus staan los van elkaar: `Zone`
(wat je wilt), `Circuit` (wat technisch tegelijk kan) en `DirectorConfig` (het geheel).

`Circuit.units` bevat **entity-ids, geen source-ids**, en is de enige waarheid over
circuitlidmaatschap. Dat is bewust: een binnenunit die de director níét beheert claimt
nog steeds de compressor, dus zijn taak moet meetellen. Eén representatie voorkomt
bovendien dat twee lijsten uit elkaar kunnen lopen.

`OutdoorWindow` is half-open, `[minimum, maximum)`. Daardoor dekken twee aangrenzende
vensters `(None, 3.0)` en `(3.0, None)` de hele schaal zonder gat en zonder overlap — er
is geen buitentemperatuur waarbij een cv-ketel en een warmtepomp allebei of geen van
beide in aanmerking komen. Een venster met een onbekende buitentemperatuur is niet
voldaan tenzij het onbegrensd is: een grens die je niet kunt controleren geldt niet.

`validate()` geeft een lijst problemen terug en gooit nooit. `decide()` weigert nooit te
regelen om een gebrekkige configuratie — één stukke zone het hele huis laten stilleggen
is erger dan de gezonde zones bedienen en de rest melden.

### world.py — momentopname

`WorldState` is naast de configuratie de enige invoer. De engine leest nooit zelf
entiteiten uit. Bevat onder meer de buitentemperatuur, binnentemperatuur per zone, de
toestand van elke `climate`-entiteit (inclusief `changed_at` voor
kortcyclusbescherming), bewoners, openingen en per circuit wanneer de huidige taak
begon.

### gates.py — mag het

Kijkt uitsluitend naar omstandigheden, nooit naar temperaturen. Van breed naar smal
geëvalueerd, zodat de gemelde oorzaak degene is die een gebruiker als eerste zou noemen:
hoofdschakelaar vóór openstaand raam vóór niemand thuis.

Een configuratie zonder bewoners slaat de aanwezigheidspoorten over. Een opening zonder
tijdstempel blokkeert direct: opschorten is de onschadelijke richting om fout in te
zitten, en weigeren te handelen op een onbekende leeftijd zou een openstaande kamer
blijven verwarmen.

### hysteresis.py — moet het

Bepaalt de gevraagde taak uit de binnentemperatuur, het seizoen en het
buitentemperatuurvenster. Krijgt de *draaiende* taak mee; dat is wat de dode band laat
werken. Het aanpunt telt als bereikt (`<=` / `>=`), het uitpunt als gepasseerd (`<` /
`>`) — waren beide inclusief, dan zou een band van nul een taak nooit laten stoppen.

Vragen verwarmen en koelen tegelijk (overlappende setpoints, dus een
configuratiefout), dan houdt de draaiende taak de zone; anders wint de grootste
afwijking. In beide gevallen pendelt de zone niet.

### sources.py — waarmee

Kiest per zone en taak het apparaat: geschiktheid (rol), dan beschikbaarheid, dan
voorkeur (`priority`, met `source_id` als tie-break zodat de uitkomst deterministisch
is).

### constraints.py — wat mag tegelijk

De circuitregel:

> Zij **F** de actieve taak van een circuit. Elke binnenunit op dat circuit staat in
> **F ∪ {`off`, `fan_only`}**.

Volgorde van afhandeling:

1. **Vergrendeling door onbeheerde units.** Draait een unit op het circuit die de
   director niet aanstuurt, dan is de taak van het circuit al bepaald en kan niets dat
   overrulen.
2. **Conflictbeleid** (`priority`, `first_come`, `demand`, `season_lock`) kiest de taak
   als zones het oneens zijn. Elk beleid dat niet tot een keuze komt valt terug op
   prioriteit.
3. **Minimale looptijd** houdt de huidige taak vast als er te kort geleden gewisseld is.
   Ontbreekt de tijdstempel, dan gaat de wissel door: de installatie bevriezen op een
   onbekende waarde is erger dan iets te vroeg wisselen.
4. **Wisselpauze** stopt eerst de oude taak en start de nieuwe pas na een `Deferral`.
5. **Capaciteitsgrens** snoeit de winnaars terug; onbeheerde draaiende units tellen mee.
6. **Kortcyclusbescherming** houdt een start tegen van een unit die net gestopt is —
   alleen starten, nooit stoppen.

### decide.py — het geheel

De enige ingang, en het enige punt waar besloten wordt. Levert een `Plan`: gewenste
eindtoestanden, geen handelingen.

Twee eigenschappen die de rest van het systeem dragen:

- **Elke beheerde bron krijgt een commando**, ook de bronnen die níét gekozen zijn. Die
  worden expliciet uitgezet. Dát maakt "twee apparaten werken tegen elkaar in"
  onbereikbaar in plaats van onwaarschijnlijk.
- **Stoppen staat vóór starten** in de commandovolgorde. Zou je op een circuit dat van
  taak wisselt de nieuwe taak eerst starten, dan delen twee bedrijven één compressor
  zolang de service calls onderweg zijn.

Elke zone krijgt precies één `Reason`, ook als hij niets doet, zodat een unit die
uitgaat altijd kan zeggen waaróm — "de warmtepomp bedient deze zone" leest anders dan
"er is niets te doen".

### plan.py — uitvoer

`UnitCommand`, `ZoneDecision`, `CircuitDecision`, `Deferral` en `Reason`. `Reason` is een
`StrEnum` met stabiele identifiers in plaats van vrije tekst, zodat de Home
Assistant-laag ze kan vertalen en gebruikers erop kunnen filteren in hun eigen
automatiseringen. Een `Deferral` vertelt de coordinator wanneer er opnieuw beslist moet
worden, zodat een plan dat op een timer wacht vanzelf hervat.

### Nog te bouwen

De koppelingslaag: `config_flow.py` (wizard: zones → bronnen → circuits → poorten →
drempels), `coordinator.py` (toestanden volgen, ontdubbelen, serialiseren, `Deferral`s
inplannen), `applier.py` (Plan vergelijken met de werkelijkheid en alleen het verschil
uitvoeren) en de entiteiten. Ideeën staan in [`ROADMAP.md`](ROADMAP.md).

### Uitbreidbaarheid

Nieuwe poorten, bronrollen, conflictbeleiden en circuitbeperkingen haken elk op één
bestaande module aan zonder de pijplijn te wijzigen. Nieuwe kunde die niets met Home
Assistant te maken heeft hoort per definitie in `engine/`, met tests ernaast.

## EN

Technical design document for anyone working on the code (not a user manual —
that is [`README.md`](README.md)). Each layer has exactly one responsibility.

### The most important dividing line

The project consists of two halves with a hard border between them:

```
custom_components/climate_director/
  ├─ engine/          ← pure Python. No hass, no entities, no I/O.
  └─ (the rest)       ← everything touching Home Assistant.
```

`engine/` imports Home Assistant nowhere. All decision logic lives there, and is
therefore reproducible as a plain data object and testable in milliseconds without a
running Home Assistant. Every conceivable climate scenario — a night frost, two zones
fighting over one outdoor unit, a door left open during a duty swap — is a unit test
rather than an afternoon of manual trials.

That border is not a matter of style. The reason hand-built automations become
unsustainable for this problem is that decision logic and execution are interleaved;
this separation is precisely the correction for that.

### Overview

```
Home Assistant (entity states, clock events)
      │
      ▼
  coordinator          gathers states, debounces, serialises        [to be built]
      │
      ▼
  world.WorldState     snapshot: one data object, nothing more
      │
      ▼
┌─ engine/ ────────────────────────────────────────────────────────┐
│                                                                  │
│  gates.py       is regulating allowed (circumstances)            │
│      │                                                           │
│      ▼                                                           │
│  hysteresis.py  is regulating needed (temperatures)              │
│      │                                                           │
│      ▼                                                           │
│  sources.py     which appliance delivers that duty               │
│      │                                                           │
│      ▼                                                           │
│  constraints.py what may run at once on one outdoor unit         │
│      │                                                           │
│      ▼                                                           │
│  decide.py      one coherent Plan                                │
│                                                                  │
│  models.py      configuration (Zone, Source, Circuit, …)         │
│  families.py    hvac_mode → compressor duty                      │
│  plan.py        output (UnitCommand, ZoneDecision, Reason, …)    │
└──────────────────────────────────────────────────────────────────┘
      │
      ▼
  applier              compares Plan to reality, calls services     [to be built]
      │
      ▼
  entities + event     climate/sensor/switch/number/select/button   [to be built]
```

### families.py — mode families

Maps an `hvac_mode` onto the *compressor duty* it claims. A conflict on a multi-split
arises not between modes but between duties:

- `heat` → HEAT
- `cool`, `dry` → COOL (drying is cooling duty)
- `off`, `fan_only` → NEUTRAL (no compressor claim, always allowed)
- `heat_cool`, `auto` → AMBIGUOUS (the unit picks for itself)

An unrecognised mode counts as AMBIGUOUS, not NEUTRAL: a mode this engine does not know
may well run the compressor, and treating it as harmless is the most damaging way to be
wrong.

### models.py — configuration

Dataclasses only, plus `validate()`. Three levels stand apart: `Zone` (what you want),
`Circuit` (what is technically possible at once) and `DirectorConfig` (the whole).

`Circuit.units` holds **entity ids, not source ids**, and is the single source of truth
for circuit membership. Deliberately so: an indoor unit the director does *not* manage
still claims the compressor, so its duty has to count. One representation also stops two
lists from drifting apart.

`OutdoorWindow` is half-open, `[minimum, maximum)`. Two adjacent windows `(None, 3.0)`
and `(3.0, None)` therefore cover the whole scale with neither gap nor overlap — there is
no outdoor temperature at which a boiler and a heat pump both, or neither, qualify. A
window with an unknown outdoor temperature is not satisfied unless it is unbounded: a
bound you cannot check is not met.

`validate()` returns a list of problems and never raises. `decide()` never refuses to
regulate over a flawed configuration — letting one broken zone shut down a whole house is
worse than serving the sound zones and reporting the rest.

### world.py — the snapshot

`WorldState` is the only input besides the configuration. The engine never reads entities
itself. It carries the outdoor temperature, indoor temperature per zone, the state of
every `climate` entity (including `changed_at` for short-cycle protection), residents,
openings, and when each circuit took on its current duty.

### gates.py — is it allowed

Looks only at circumstances, never at temperatures. Evaluated broadest to narrowest, so
the reported cause is the one a user would name first: master switch before open window
before nobody home.

A configuration without residents skips the presence gates. An opening without a
timestamp blocks immediately: suspending is the harmless direction to be wrong in, and
refusing to act on an unknown age would keep heating an open room.

### hysteresis.py — is it needed

Derives the requested duty from indoor temperature, season and outdoor window. It
receives the *running* duty; that is what makes the dead band work. The switch-on point
counts as reached (`<=` / `>=`), the switch-off point as passed (`<` / `>`) — were both
inclusive, a zero-width band would never let a duty stop.

If heating and cooling both ask at once (overlapping setpoints, so a configuration
mistake) the running duty keeps the zone; otherwise the larger deviation wins. Either
way the zone does not oscillate.

### sources.py — with what

Picks the appliance per zone and duty: suitability (role), then availability, then
preference (`priority`, with `source_id` as tie-break so the outcome is deterministic).

### constraints.py — what may run together

The circuit rule:

> Let **F** be a circuit's active duty. Every indoor unit on that circuit sits in
> **F ∪ {`off`, `fan_only`}**.

Order of handling:

1. **Lock by unmanaged units.** If a unit on the circuit the director does not steer is
   running, the circuit's duty is already settled and nothing can overrule it.
2. **Conflict policy** (`priority`, `first_come`, `demand`, `season_lock`) picks the duty
   when zones disagree. Any policy that cannot decide falls back to priority.
3. **Minimum run time** holds the current duty when it was swapped too recently. With the
   timestamp missing the swap goes ahead: freezing the installation over an unknown value
   is worse than swapping a little early.
4. **Switch delay** stops the old duty first and starts the new one only after a
   `Deferral`.
5. **Capacity cap** trims the winners; unmanaged running units count towards it.
6. **Short-cycle protection** holds back a start from a unit that just stopped — starts
   only, never stops.

### decide.py — the whole

The only entry point, and the only place a decision is made. Produces a `Plan`: desired
end states, not actions.

Two properties carry the rest of the system:

- **Every managed source gets a command**, including the sources that were *not* chosen.
  Those are switched off explicitly. That is what makes "two appliances working against
  each other" unreachable rather than unlikely.
- **Stops come before starts** in the command order. Starting the new duty first on a
  circuit that is swapping would put two duties on one compressor for as long as the
  service calls take to land.

Every zone gets exactly one `Reason`, even when it does nothing, so a unit switching off
can always say *why* — "the heat pump serves this zone" reads differently from "there is
nothing to do".

### plan.py — output

`UnitCommand`, `ZoneDecision`, `CircuitDecision`, `Deferral` and `Reason`. `Reason` is a
`StrEnum` of stable identifiers rather than free text, so the Home Assistant layer can
translate them and users can filter on them in their own automations. A `Deferral` tells
the coordinator when to decide again, so a plan held back by a timer resumes on its own.

### Still to build

The binding layer: `config_flow.py` (wizard: zones → sources → circuits → gates →
thresholds), `coordinator.py` (tracking states, debouncing, serialising, scheduling
`Deferral`s), `applier.py` (comparing the Plan against reality and executing only the
difference) and the entities. Ideas live in [`ROADMAP.md`](ROADMAP.md).

### Extensibility

New gates, source roles, conflict policies and circuit constraints each plug into one
existing module without changing the pipeline. New logic with nothing to do with Home
Assistant belongs in `engine/` by definition, with tests alongside it.
