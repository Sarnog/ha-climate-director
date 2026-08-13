  <a href="#nl">NL</a> | <a href="#en">EN</a>

<div align="center">
  <!-- align="center" centreert alles binnen deze div -->
  <h1>
    <!-- h1 = grootste kop, standaard al dikgedrukt en groot -->
    <ins>Climate Director</ins>
    <!-- ins = onderstreepte tekst op GitHub -->
  </h1>
</div>


##### <ins>NL</ins>

Een integratie voor Home Assistant die bestaande klimaatapparaten aanstuurt: hij beslist
welke warmte- of koudebron in welke ruimte, in welke stand en op welke temperatuur draait.

**Status:** de beslislaag (`custom_components/climate_director/engine/`) is af en volledig
getest. De koppeling met Home Assistant — config flow, coordinator en entiteiten — is nog
niet gebouwd, dus de integratie is nog niet te installeren.

### Wat doet dit

Climate Director bezit geen hardware. Hij dirigeert de `climate`-entiteiten die je al hebt:
een cv-ketel, warmtepompen, airco's, een houtkachel met thermostaat. Op elk moment berekent
hij één samenhangende eindtoestand voor het hele huis en zet die om in service calls.

Dat lost drie dingen op die met losse automatiseringen lastig blijven:

- **Bronkeuze.** Onder een instelbare buitentemperatuur verwarmt de cv-ketel, daarboven de
  warmtepomp. De vensters sluiten naadloos op elkaar aan, dus er is geen temperatuur waarbij
  allebei of geen van beide in aanmerking komt.
- **Multi-split-beperkingen.** Binnenunits die een buitenunit delen kunnen niet tegelijk
  verwarmen en koelen. Climate Director weet welke units bij elkaar horen en lost het
  conflict op volgens een beleid dat je zelf kiest.
- **Één beslispunt.** Omdat alles in één functie besloten wordt, is een toestand als
  "cv-ketel en warmtepomp draaien tegen elkaar in" niet iets dat je achteraf moet
  detecteren — die komt er niet uit.

### Kernbegrippen

Drie niveaus, die los van elkaar staan:

| Begrip | Betekenis |
|---|---|
| **Zone** | Een ruimte. Beschrijft *wat je wilt*: gewenste temperatuur, aan- en uitpunt, in welk seizoen. |
| **Bron** | Een apparaat dat een zone kan bedienen, met een rol (verwarmen, koelen of beide), een voorkeursvolgorde en een buitentemperatuurvenster. |
| **Koelcircuit** | Eén buitenunit met de binnenunits die eraan hangen. Beschrijft *wat technisch tegelijk kan*. |

Een circuit spant willekeurige zones, en een zone mag binnenunits van meerdere circuits
hebben. De twee assen kruisen elkaar en zitten nergens aan elkaar vast.

### Multi-split en losse splitunits

De regel die het gedrag van een gedeelde buitenunit bepaalt:

> Zij **F** de actieve taak van een circuit, met verwarmen = {`heat`} en koelen =
> {`cool`, `dry`}. Elke binnenunit op dat circuit staat in **F ∪ {`off`, `fan_only`}**.

Ontvochtigen (`dry`) is koelbedrijf en botst dus met verwarmen. Ventileren (`fan_only`)
gebruikt de compressor niet en mag altijd. `heat_cool` laat de unit zelf kiezen en is op een
gedeeld circuit onbruikbaar — Climate Director zet dat zelf om naar een concrete stand.

`simultaneous_heat_cool` is een losse instelling, geen gevolg van het aantal binnenunits:
een driepijps-VRF met warmteterugwinning kán werkelijk tegelijk verwarmen en koelen, en
wordt dus niet onnodig beperkt.

Elke willekeurige verdeling van buitenunits is uit te drukken:

| Installatie | Circuits | Beperking |
|---|---|---|
| Eén multi-split, drie binnenunits | 1× multi-split `[woonkamer, slaapkamer, zolder]` | alle drie dezelfde taak |
| Drie losse splitunits | 3× single split | geen |
| Multi-split plus losse splitunit | 1× multi-split `[zolder, slaapkamer]`<br>1× single split `[woonkamer]` | zolder ↔ slaapkamer gekoppeld, woonkamer vrij |
| Twee multi-splits, kriskras | 1× `[zolder, slaapkamer 1]`<br>1× `[slaapkamer 2, woonkamer]` | per paar gekoppeld, de twee slaapkamers vrij van elkaar |

De veilige standaardinstelling is dat elke `climate`-entiteit zijn eigen circuit is. Dat
klopt voor iedereen zonder multi-split; wie er wel een heeft, groepeert de betreffende
binnenunits.

### Conflictbeleid

Willen twee zones op één niet-simultaan circuit tegengestelde taken, dan kiest het
circuitbeleid de winnaar:

| Beleid | Gedrag |
|---|---|
| `priority` (standaard) | De zone met het laagste prioriteitsnummer wint. |
| `first_come` | De taak die al draait houdt het circuit; een nieuwe aanvraag wacht. |
| `demand` | De grootste afwijking van het setpoint wint. |
| `season_lock` | Het seizoen bepaalt de taak; alles wat de andere kant op wil staat af. |

Verliezers gaan uit, of naar `fan_only` als `allow_fan_only_during_conflict` aanstaat.
Daarnaast beschermen `min_family_switch_interval` (minimale looptijd voor een taakwissel),
`family_switch_delay` (pauze tussen stoppen en starten) en `min_cycle_time` (rusttijd voor
een unit opnieuw mag starten) de buitenunit. Die laatste vertraagt alleen starten, nooit
stoppen.

### Poorten

Poorten bepalen of er überhaupt geregeld mag worden. Ze kijken naar omstandigheden, niet
naar temperaturen:

- **Hoofdschakelaar** — alles uit.
- **Handmatige override** — per zone.
- **Openingen** — een deur of raam dat lang genoeg openstaat schort de zone op.
- **Aanwezigheid** — er moet iemand thuis zijn.
- **Wakker** — iemand die thuis is moet ook uit bed zijn.
- **Rooster** — per bewoner instelbare tijdvensters, met een vakantiemodus die dat overslaat.

Een installatie zonder bewoners (kantoor, vakantiehuis, serverruimte) slaat de
aanwezigheidspoorten over in plaats van permanent op slot te zitten.

### Dode band

Aan- en uitschakelen gebeuren op twee verschillende temperaturen. Je stelt een aanpunt in
plus de breedte van de band:

- verwarmen start bij `binnen <= aanpunt` en stopt bij `binnen >= aanpunt + band`;
- koelen start bij `binnen >= aanpunt` en stopt bij `binnen <= aanpunt - band`.

Twee getallen per stand in plaats van vier losse minimum-/maximumdrempels, en de band is een
bewuste keuze in plaats van een toevalligheid.

### Notificaties

Climate Director stuurt zelf geen notificaties — dat is precies het onuniversele deel. Na
elke beslissing komt er een event op de Home Assistant event bus (`climate_director_decision`)
met de zone, de gekozen bron, de stand, de temperatuur en de reden. Eén automatisering die
daarop luistert vervangt een notificatieblok per automatisering.

Redenen zijn stabiele identifiers (`circuit_conflict_lost`, `everyone_asleep`,
`short_cycle_protection`, …), zodat ze te vertalen zijn en je er in je eigen
automatiseringen op kunt filteren.

### Installatie

Nog niet van toepassing: de Home Assistant-laag is nog niet gebouwd. Zodra die er is, komt
hier de HACS-knop.

De beslislaag is los te draaien en te testen zonder Home Assistant:

```bash
pip install -r requirements_test.txt
python -m pytest
python -m ruff check .
```

### Architectuur

Het technische ontwerp staat in [`ARCHITECTURE.md`](ARCHITECTURE.md).

### Ideeën en geschiedenis

Toekomstige uitbreidingen en ideeën staan in [`ROADMAP.md`](ROADMAP.md). De
wijzigingsgeschiedenis per versie staat in de
[release notes](https://github.com/Sarnog/ha-climate-director/releases).

### Steun dit project ☕

Vind je deze integratie nuttig? Een kleine bijdrage houdt de koffie warm
en de commits komend. Volledig vrijblijvend natuurlijk!

<!-- Ko-fi badge via shields.io, geen externe tracking -->
[![Koop me een koffie op Ko-fi](https://img.shields.io/badge/Ko--fi-Koop%20me%20een%20koffie-FF5E5B?style=for-the-badge&logo=kofi&logoColor=white)](https://ko-fi.com/sarnog)

<!-- GitHub Sponsors badge, toont live het aantal sponsors -->
[![Sponsor via GitHub](https://img.shields.io/github/sponsors/sarnog?style=for-the-badge&logo=github&label=Sponsors&color=EA4AAA)](https://github.com/sponsors/sarnog)


---


##### <ins>EN</ins>

A Home Assistant integration that steers existing climate appliances: it decides which heat
or cold source runs in which room, in which mode and at which temperature.

**Status:** the decision layer (`custom_components/climate_director/engine/`) is finished and
fully tested. The Home Assistant binding — config flow, coordinator and entities — has not
been built yet, so the integration cannot be installed.

### What this does

Climate Director owns no hardware. It conducts the `climate` entities you already have: a gas
boiler, heat pumps, air conditioners, a wood stove with a thermostat. At every moment it
computes one coherent end state for the whole house and turns that into service calls.

That solves three things separate automations struggle with:

- **Source selection.** Below a configurable outdoor temperature the boiler heats, above it
  the heat pump does. The windows meet exactly, so there is no temperature at which both or
  neither qualifies.
- **Multi-split constraints.** Indoor units sharing an outdoor unit cannot heat and cool at
  the same time. Climate Director knows which units belong together and resolves the conflict
  under a policy you choose.
- **One decision point.** Because everything is decided in one function, a state such as
  "boiler and heat pump running against each other" is not something to detect afterwards —
  it never comes out.

### Core concepts

Three levels, standing apart from one another:

| Concept | Meaning |
|---|---|
| **Zone** | A room. Describes *what you want*: target temperature, switch-on and switch-off points, which seasons. |
| **Source** | An appliance able to serve a zone, with a role (heating, cooling or both), a preference order and an outdoor-temperature window. |
| **Refrigerant circuit** | One outdoor unit and the indoor units on it. Describes *what is technically possible at the same time*. |

A circuit spans arbitrary zones, and a zone may hold indoor units from several circuits. The
two axes cross and are never tied to one another.

### Multi-split and single splits

The rule governing a shared outdoor unit:

> Let **F** be a circuit's active duty, with heating = {`heat`} and cooling =
> {`cool`, `dry`}. Every indoor unit on that circuit sits in **F ∪ {`off`, `fan_only`}**.

Drying (`dry`) is cooling duty and therefore clashes with heating. Fan-only does not use the
compressor and is always allowed. `heat_cool` lets the unit pick its own duty and is unusable
on a shared circuit — Climate Director resolves it into a concrete mode itself.

`simultaneous_heat_cool` is a separate flag rather than something derived from a unit count:
three-pipe VRF with heat recovery genuinely does heat and cool at once, and is not needlessly
crippled.

Any pattern of outdoor units can be expressed:

| Installation | Circuits | Constraint |
|---|---|---|
| One multi-split, three indoor units | 1× multi-split `[living, bedroom, attic]` | all three share one duty |
| Three single splits | 3× single split | none |
| Multi-split plus a single split | 1× multi-split `[attic, bedroom]`<br>1× single split `[living]` | attic ↔ bedroom bound, living free |
| Two multi-splits, crosswise | 1× `[attic, bedroom 1]`<br>1× `[bedroom 2, living]` | bound per pair, the two bedrooms free of each other |

The safe default is that every `climate` entity is its own circuit. That is correct for
anyone without a multi-split; anyone who has one groups the indoor units concerned.

### Conflict policies

When two zones on one non-simultaneous circuit want opposing duties, the circuit policy picks
the winner:

| Policy | Behaviour |
|---|---|
| `priority` (default) | The zone with the lowest priority number wins. |
| `first_come` | The duty already running keeps the circuit; a new request waits. |
| `demand` | The largest deviation from setpoint wins. |
| `season_lock` | The season dictates the duty; anything opposing it stands down. |

Losers switch off, or go to `fan_only` when `allow_fan_only_during_conflict` is on. Beyond
that, `min_family_switch_interval` (minimum run before a duty swap), `family_switch_delay`
(pause between stopping and starting) and `min_cycle_time` (rest before a unit may start
again) protect the outdoor unit. The last only ever delays starting, never stopping.

### Gates

Gates decide whether regulating is allowed at all. They look at circumstances, not
temperatures:

- **Master switch** — everything off.
- **Manual override** — per zone.
- **Openings** — a door or window standing open long enough suspends the zone.
- **Occupancy** — somebody must be home.
- **Awake** — somebody home must also be out of bed.
- **Schedule** — per-resident time windows, with a holiday mode that skips them.

An installation without residents (an office, a holiday home, a server room) skips the
presence gates rather than staying locked out forever.

### Dead band

Switching on and switching off happen at two different temperatures. You set a switch-on
point plus the width of the band:

- heating starts at `indoor <= switch-on` and stops at `indoor >= switch-on + band`;
- cooling starts at `indoor >= switch-on` and stops at `indoor <= switch-on - band`.

Two numbers per mode instead of four separate minimum/maximum thresholds, and the band is a
deliberate choice rather than an accident.

### Notifications

Climate Director sends no notifications itself — that is precisely the part that cannot be
made universal. After every decision an event lands on the Home Assistant event bus
(`climate_director_decision`) carrying the zone, the chosen source, the mode, the temperature
and the reason. One automation listening for that replaces a notification block per
automation.

Reasons are stable identifiers (`circuit_conflict_lost`, `everyone_asleep`,
`short_cycle_protection`, …), so they can be translated and filtered on in your own
automations.

### Installation

Not applicable yet: the Home Assistant layer has not been built. The HACS button will appear
here once it has.

The decision layer runs and tests on its own, without Home Assistant:

```bash
pip install -r requirements_test.txt
python -m pytest
python -m ruff check .
```

### Architecture

The technical design lives in [`ARCHITECTURE.md`](ARCHITECTURE.md).

### Ideas and history

Future additions and ideas live in [`ROADMAP.md`](ROADMAP.md). The per-version change history
lives in the [release notes](https://github.com/Sarnog/ha-climate-director/releases).

### Support this project ☕

Do you find this integration useful? A small contribution keeps the coffee
warm and the commits coming. Entirely optional, of course!

<!-- Ko-fi badge via shields.io, no external tracking -->
[![Buy me a coffee on Ko-fi](https://img.shields.io/badge/Ko--fi-Buy%20me%20a%20coffee-FF5E5B?style=for-the-badge&logo=kofi&logoColor=white)](https://ko-fi.com/sarnog)

<!-- GitHub Sponsors badge, shows the sponsor count live -->
[![Sponsor via GitHub](https://img.shields.io/github/sponsors/sarnog?style=for-the-badge&logo=github&label=Sponsors&color=EA4AAA)](https://github.com/sponsors/sarnog)
