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

<a href="#en">→ Go to the English version</a>

Een integratie voor Home Assistant die bestaande klimaatapparaten aanstuurt: hij
beslist welke warmte- of koudebron in welke ruimte, in welke stand en op welke
temperatuur draait.

**Schaduwmodus staat standaard aan.** De integratie berekent dan elke beslissing
en laat zien wat ze gedaan zou hebben, maar stuurt geen enkele service call. Je
kunt haar dus naast je bestaande automatiseringen laten meedraaien zolang je
wilt, en pas overstappen als de twee het weken achtereen met elkaar eens zijn.

### Wat doet dit

Climate Director bezit geen hardware. Hij dirigeert de `climate`-entiteiten die
je al hebt: een cv-ketel, warmtepompen, airco's, een houtkachel met thermostaat.
Op elk moment berekent hij één samenhangende eindtoestand voor het hele huis en
zet die om in service calls. Dat lost drie dingen op die met losse
automatiseringen lastig blijven:

- **Bronkeuze.** Onder een instelbare buitentemperatuur verwarmt de cv-ketel,
  daarboven de warmtepomp. De vensters sluiten naadloos op elkaar aan.
- **Multi-split-beperkingen.** Binnenunits die een buitenunit delen kunnen niet
  tegelijk verwarmen en koelen. Climate Director lost het conflict op volgens
  een beleid dat je zelf kiest.
- **Eén beslispunt.** Omdat alles in één functie besloten wordt, komt een
  toestand als "cv-ketel en warmtepomp draaien tegen elkaar in" er niet uit.

### Voor wie

Voor iedereen met meer dan één klimaatapparaat dat elkaar in de weg kan zitten:
een cv-ketel naast een warmtepomp, een multi-split airco over meerdere kamers,
of zones die je per ruimte wilt regelen — met bewoners, roosters, aanwezigheid,
vooruit verwarmen en een optionele neerslagregel als extra's.

<!-- Ko-fi badge via shields.io, geen externe tracking -->
[![Koop me een koffie op Ko-fi](https://img.shields.io/badge/Ko--fi-Koop%20me%20een%20koffie-FF5E5B?style=for-the-badge&logo=kofi&logoColor=white)](https://ko-fi.com/sarnog)

<!-- GitHub Sponsors badge, toont live het aantal sponsors -->
[![Sponsor via GitHub](https://img.shields.io/github/sponsors/sarnog?style=for-the-badge&logo=github&label=Sponsors&color=EA4AAA)](https://github.com/sponsors/sarnog)

### Installatiehandleidingen

Kies je taal voor de volledige, stap-voor-stap handleiding:

| Taal | Handleiding |
|---|---|
| Nederlands | [Installatiehandleiding (Nederlands)](docs/install/nl.md) |
| English | [Installation Guide (English)](docs/install/en.md) |
| Deutsch | [Installationsanleitung (Deutsch)](docs/install/de.md) |
| Français | [Guide d'installation (Français)](docs/install/fr.md) |
| Español | [Guía de instalación (Español)](docs/install/es.md) |
| العربية | [دليل التثبيت (العربية)](docs/install/ar.md) |

### Installeren

**Vereist:** Home Assistant **2025.3** of nieuwer — de integratie meldt haar entiteiten
aan met `AddConfigEntryEntitiesCallback`, en die bestaat sinds 2025.3. Op een oudere
versie laadt ze niet.

**Eenheden:** de integratie volgt het eenhedenstelsel van Home Assistant. De
engine rekent intern in graden Celsius; de koppelingslaag rekent metingen en
setpoints om naar de eenheid die je in Home Assistant hebt ingesteld.

Zolang Climate Director nog niet in de standaard HACS-winkel staat, voeg je deze
repository toe als **custom repository**:

1. HACS → drie puntjes → **Aangepaste repositories**.
2. Voeg deze URL toe, categorie **Integratie**:

   ```
   https://github.com/Sarnog/ha-climate-director
   ```

3. Installeer **Climate Director** en herstart Home Assistant.

Open de integratie in HACS:

[![Open je Home Assistant en open deze repository in de Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Sarnog&repository=ha-climate-director&category=integration)

Handmatig installeren kan ook: kopieer `custom_components/climate_director`
naar de `custom_components`-map van je configuratie en herstart.

### Blueprints

Drie kant-en-klare automatiseringen, te importeren via
**Instellingen → Automatiseringen en scènes → Blueprints → Blueprint importeren**:

| Blueprint | Importlink |
|---|---|
| Bewaking | `https://github.com/Sarnog/ha-climate-director/blob/main/blueprints/automation/climate_director/monitoring.yaml` |
| Geweigerd vooruit-verzoek | `https://github.com/Sarnog/ha-climate-director/blob/main/blueprints/automation/climate_director/precondition_refused.yaml` |
| Wat er besloten is | `https://github.com/Sarnog/ha-climate-director/blob/main/blueprints/automation/climate_director/decisions.yaml` |

> **Importeren alleen is niet genoeg.** Een blueprint is een sjabloon; er
> luistert pas iets zodra je er een automatisering van maakt.

### Meer

- **Repository:** [github.com/Sarnog/ha-climate-director](https://github.com/Sarnog/ha-climate-director)
- **Ontwerp:** [ARCHITECTURE.md](ARCHITECTURE.md)
- **Ideeën:** [ROADMAP.md](ROADMAP.md)
- **Geschiedenis:** [release notes](https://github.com/Sarnog/ha-climate-director/releases)

### Steun dit project ☕

Als u deze integratie nuttig vindt en mijn werk waardeert, overweeg dan om
een bedrag te doneren. Alvast bedankt!

[![Koop me een koffie op Ko-fi](https://img.shields.io/badge/Ko--fi-Koop%20me%20een%20koffie-FF5E5B?style=for-the-badge&logo=kofi&logoColor=white)](https://ko-fi.com/sarnog)

[![Sponsor via GitHub](https://img.shields.io/github/sponsors/sarnog?style=for-the-badge&logo=github&label=Sponsors&color=EA4AAA)](https://github.com/sponsors/sarnog)


---


##### <ins>EN</ins>

<a href="#nl">→ Naar de Nederlandse versie</a>

A Home Assistant integration that steers existing climate appliances: it decides
which heat or cold source runs in which room, in which mode and at which
temperature.

**Shadow mode is on by default.** The integration then computes every decision
and shows what it would have done, but issues no service call at all. You can
let it run alongside your existing automations for as long as you like, and only
switch over once the two have agreed with each other for weeks.

### What this does

Climate Director owns no hardware. It conducts the `climate` entities you
already have: a gas boiler, heat pumps, air conditioners, a wood stove with a
thermostat. At every moment it computes one coherent end state for the whole
house and turns that into service calls. That solves three things separate
automations struggle with:

- **Source selection.** Below a configurable outdoor temperature the boiler
  heats, above it the heat pump does. The windows meet exactly.
- **Multi-split constraints.** Indoor units sharing an outdoor unit cannot heat
  and cool at the same time. Climate Director resolves the conflict under a
  policy you choose.
- **One decision point.** Because everything is decided in one function, a state
  such as "boiler and heat pump running against each other" never comes out.

### Who it is for

Anyone with more than one climate appliance that could get in each other's way:
a gas boiler next to a heat pump, a multi-split air conditioner across several
rooms, or zones you want to control per room — with residents, schedules,
presence, pre-conditioning and an optional precipitation rule as extras.

<!-- Ko-fi badge via shields.io, no external tracking -->
[![Buy me a coffee on Ko-fi](https://img.shields.io/badge/Ko--fi-Buy%20me%20a%20coffee-FF5E5B?style=for-the-badge&logo=kofi&logoColor=white)](https://ko-fi.com/sarnog)

<!-- GitHub Sponsors badge, shows the sponsor count live -->
[![Sponsor via GitHub](https://img.shields.io/github/sponsors/sarnog?style=for-the-badge&logo=github&label=Sponsors&color=EA4AAA)](https://github.com/sponsors/sarnog)

### Installation guides

Pick your language for the full, step-by-step guide:

| Language | Guide |
|---|---|
| Nederlands | [Installatiehandleiding (Nederlands)](docs/install/nl.md) |
| English | [Installation Guide (English)](docs/install/en.md) |
| Deutsch | [Installationsanleitung (Deutsch)](docs/install/de.md) |
| Français | [Guide d'installation (Français)](docs/install/fr.md) |
| Español | [Guía de instalación (Español)](docs/install/es.md) |
| العربية | [دليل التثبيت (العربية)](docs/install/ar.md) |

### Installing

**Requires:** Home Assistant **2025.3** or newer — the integration registers its entities
through `AddConfigEntryEntitiesCallback`, which exists from 2025.3 onwards. On an older
version it does not load.

**Units:** the integration follows Home Assistant's unit system. The engine
works in degrees Celsius internally; the binding layer converts readings and
setpoints into the unit you configured in Home Assistant.

As long as Climate Director is not yet in the default HACS store, add this
repository as a **custom repository**:

1. HACS → three dots → **Custom repositories**.
2. Add this URL, category **Integration**:

   ```
   https://github.com/Sarnog/ha-climate-director
   ```

3. Install **Climate Director** and restart Home Assistant.

Open the integration in HACS:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Sarnog&repository=ha-climate-director&category=integration)

Manual installation works too: copy `custom_components/climate_director` into
your configuration's `custom_components` folder and restart.

### Blueprints

Three ready-made automations, importable through
**Settings → Automations and scenes → Blueprints → Import blueprint**:

| Blueprint | Import link |
|---|---|
| Monitoring | `https://github.com/Sarnog/ha-climate-director/blob/main/blueprints/automation/climate_director/monitoring.yaml` |
| Refused pre-conditioning | `https://github.com/Sarnog/ha-climate-director/blob/main/blueprints/automation/climate_director/precondition_refused.yaml` |
| What was decided | `https://github.com/Sarnog/ha-climate-director/blob/main/blueprints/automation/climate_director/decisions.yaml` |

> **Importing alone is not enough.** A blueprint is a template; nothing listens
> until you build an automation from it.

### More

- **Repository:** [github.com/Sarnog/ha-climate-director](https://github.com/Sarnog/ha-climate-director)
- **Design:** [ARCHITECTURE.md](ARCHITECTURE.md)
- **Ideas:** [ROADMAP.md](ROADMAP.md)
- **History:** [release notes](https://github.com/Sarnog/ha-climate-director/releases)

### Support this project ☕

If you find this integration useful and appreciate my work, please consider
making a donation. Thank you in advance!

[![Buy me a coffee on Ko-fi](https://img.shields.io/badge/Ko--fi-Buy%20me%20a%20coffee-FF5E5B?style=for-the-badge&logo=kofi&logoColor=white)](https://ko-fi.com/sarnog)

[![Sponsor via GitHub](https://img.shields.io/github/sponsors/sarnog?style=for-the-badge&logo=github&label=Sponsors&color=EA4AAA)](https://github.com/sponsors/sarnog)
