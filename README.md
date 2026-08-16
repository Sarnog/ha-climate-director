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

**Schaduwmodus staat standaard aan.** De integratie berekent dan elke beslissing en laat
zien wat ze gedaan zou hebben, maar stuurt geen enkele service call. Je kunt haar dus
naast je bestaande automatiseringen laten meedraaien zolang je wilt, en pas overstappen
als de twee het weken achtereen met elkaar eens zijn.

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
- **Openingen** — een deur of raam dat openstaat schort de zone op, eventueel pas na een
  vertraging die je per opening in seconden instelt. Leeg of nul betekent direct.
- **Aanwezigheid** — er moet iemand thuis zijn.
- **Aanwezigheid in de ruimte** — per zone een eigen sensor, met een nalooptijd tegen
  knipperende aanwezigheidsmelders. Iemand thuis zegt niets over of er iemand op zolder
  zit; een zone zonder zo'n sensor wordt hier nooit op tegengehouden.
- **Wakker** — iemand die thuis is moet ook uit bed zijn.
- **Rooster** — per bewoner instelbare tijdvensters. Wie geen rooster invult doet niet
  mee: die opent de poort niet en houdt hem ook niet tegen. Wie thuis nog slaapt terwijl
  zijn eigen venster nog niet open is, laat het huis wachten.
- **Iemand thuis** — dit is geen keuze maar een voorwaarde. Gaat er een trigger af terwijl
  niemand van de ingestelde bewoners thuis is, dan gebeurt er niets.

Een vakantiedag telt als zaterdag, tenzij een bewoner een eigen vakantievenster invult;
dat venster vervangt dan zijn gewone vensters en negeert de dagen van de week. De
vakantiemodus gaat aan met de schakelaar, of vanzelf zodra er in een van de ingestelde
agenda's een item loopt met het ingestelde trefwoord erin.

De gastenmodus zet elke poort over personen opzij — aanwezigheid, slaap en rooster. Er
logeert dan iemand die niet gevolgd wordt, dus dat het huis leeg lijkt zegt niets, en de
verwarming of airco hoort daar niet op uit te gaan. De poort over aanwezigheid in de
ruimte zelf blijft wél gelden: die gaat over de kamer, niet over wie er in huis is.

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

### Wat je in Home Assistant krijgt

Eén device per installatie, met daaronder:

| Entiteit | Waarvoor |
|---|---|
| `sensor.*_laatste_beslissing` | Hoeveel zones bediend worden, met het volledige plan als attributen: elk commando, elk circuit, elke uitgestelde actie, en welke apparaten er aangestuurd zouden zijn |
| `sensor.*_zou_<entiteit>_aansturen` | De stand waarin de director dit apparaat zou zetten — één sensor per aangestuurd apparaat |
| `sensor.*_afwijkingen` | Hoeveel apparaten er nú anders staan dan het plan wil. Nul betekent dat de director het eens is met wat het huis op dit moment stuurt |
| `sensor.*_bron_<zone>` | Welke bron deze zone bedient, met wat de zone wilde, wat hij kreeg en waarom |
| `binary_sensor.*_<zone>_geblokkeerd` | Aan als een zone minder kreeg dan hij vroeg, met de reden als attribuut |
| `switch.*_director` | Hoofdschakelaar; uit betekent dat er niets geregeld wordt |
| `switch.*_vakantiemodus` | Laat elke dag als zaterdag tellen, of als het eigen vakantierooster |
| `switch.*_gastenmodus` | Blijft regelen terwijl de bewoners weg zijn; zet aanwezigheid, slaap en rooster opzij |
| `switch.*_override_<zone>` | Geeft één zone terug aan de gebruiker tot je hem weer uitzet |
| `number.*_prioriteit_<zone>` | Hoe sterk deze zone een gedeelde buitenunit claimt; lager wint. Vanuit een automatisering te wijzigen |

Daarnaast is er een downloadbare diagnose met de configuratie, de laatst gelezen
momentopname en het laatste plan. Met die drie is elke beslissing exact na te spelen.

### Actie

`climate_director.evaluate` laat de director nu opnieuw beslissen, in plaats van te wachten
tot een gevolgde entiteit uit zichzelf verandert. Handig tijdens het inrichten en bij het
napluizen van een afwijking. In schaduwmodus voert die actie nog steeds niets uit — hij
herberekent alleen. Zonder `entry_id` worden alle installaties herberekend.

### Configuratiecontrole

Klopt er iets structureel niet — een zone zonder bruikbare bron, twee bronnen op dezelfde
entiteit, een buitenvenster dat niets toelaat — dan verschijnt dat als reparatiemelding in
Home Assistant. De zones die wél kloppen worden ondertussen gewoon geregeld; één stukke
zone legt de installatie niet stil. De volledige lijst staat in de diagnose.

Dat onderscheid is er met opzet: een fout in de configuratie ziet er van buiten hetzelfde
uit als "de director besluit niets", en dan zoek je een bug die eigenlijk een typefout is.

### Een schaduwrun beoordelen

De drie sensoren hierboven zijn bewust *toestanden* en geen attributen: Home Assistant
bewaart toestandsgeschiedenis, en dat is wat een schaduwrun achteraf beoordeelbaar maakt.

- **`sensor.*_afwijkingen`** is het kerngetal. Nul betekent dat de director het eens is met
  wat er op dat moment daadwerkelijk draait. Een korte piek is normaal — de ene kant handelt
  even eerder dan de andere — maar een waarde die blíjft staan is een echt meningsverschil.
  Zet deze sensor in een geschiedenisgrafiek en je ziet in één oogopslag wanneer het misging.
- **`sensor.*_zou_<entiteit>_aansturen`** leg je naast de geschiedenis van de
  `climate`-entiteit met dezelfde naam. Twee lijnen die elkaar volgen betekenen dat de
  director hetzelfde besloot als je automatiseringen; elk moment waarop ze uiteenlopen is
  een geval om na te kijken.
- **`sensor.*_bron_<zone>`** en **`binary_sensor.*_<zone>_geblokkeerd`** vertellen daarna
  *waarom*: welke bron gekozen werd, en welke poort een zone tegenhield.

Elke sensor draagt de reden als attribuut (`circuit_conflict_lost`, `everyone_asleep`,
`short_cycle_protection`, …), dus een verschil is altijd te herleiden tot één regel in het
ontwerp in plaats van tot een vermoeden.

### Installatie

**Via HACS:** voeg deze repository toe als **custom repository** (HACS > drie puntjes >
Aangepaste repositories > deze GitHub-URL, categorie "Integratie"), installeer, en
herstart Home Assistant.

**Handmatig:** kopieer de map `custom_components/climate_director` naar de
`custom_components`-map van je Home Assistant-configuratie en herstart.

Daarna: **Instellingen > Apparaten en diensten > Integratie toevoegen > Climate Director**.
Je geeft een naam en laat schaduwmodus aan. De installatie verschijnt vervolgens op het
tabblad **Integraties**.

Alles verder — zones, bronnen, koelcircuits, bewoners en openingen — bouw je op via
**Configureren** bij die integratie. Er wordt niets opgeslagen tot je in dat menu
"Opslaan en sluiten" kiest.

Een verstandige volgorde:

1. **Algemene instellingen** — buitentemperatuursensor, herkomst van het seizoen, welke
   poorten je wilt (wakker, rooster), en welke agenda's een vakantie aankondigen met welk
   trefwoord.
2. **Zones en bronnen** — per ruimte de binnentemperatuursensor en de aan-/uitpunten,
   daarna de apparaten die die ruimte kunnen bedienen. Geef een cv-ketel en een warmtepomp
   aansluitende buitenvensters, dan wisselen ze elkaar naadloos af.
3. **Koelcircuits** — alleen nodig als binnenunits een buitenunit delen. Laat leeg als elke
   unit zijn eigen buitenunit heeft.
4. **Bewoners** en **Deuren en ramen** — optioneel.

### Los draaien en testen

De beslislaag draait en test zonder Home Assistant:

```bash
pip install -r requirements_test.txt
python -m pytest
python -m ruff check .
```

### Heb je helpers nodig

Nee. Er is geen enkele `input_number`, `input_boolean` of `input_select` die je vooraf moet
aanmaken. Alles wat handgeschreven automatiseringen daarvoor gebruiken — drempels,
setpoints, een hoofdschakelaar, een vakantieschakelaar, een override, de prioriteit per zone
— maakt de integratie zelf aan of bewaart hij in zijn eigen configuratie.

Wat je wél aanwijst zijn entiteiten die je toch al hebt:

| Nodig | Waarvoor |
|---|---|
| Een binnentemperatuursensor per zone | Verplicht; anders weet een zone niets |
| Eén of meer `climate`-entiteiten | Verplicht; dat zijn de apparaten die hij aanstuurt |
| Een buitentemperatuursensor | Alleen nodig als je grenzen op buitentemperatuur zet — en dat wil je vrijwel altijd |
| `person`-entiteiten | Optioneel, voor de aanwezigheidspoort |
| Een slaapsensor per bewoner | Optioneel |
| Een aanwezigheidssensor per ruimte | Optioneel |
| Deur- en raamcontacten | Optioneel |
| Een seizoensentiteit | Optioneel; standaard leidt hij het seizoen af uit de maand |

Heb je al een helper die je wilt blijven gebruiken — een `input_select` voor het seizoen,
een template-sensor die meerdere thermometers middelt — dan wijs je die gewoon aan. De
integratie dwingt je nergens iets nieuws voor aan te maken, maar staat het overal toe.

### Radiatorkranen en een cv

Een cv met slimme radiatorkranen werkt anders dan een multi-split, en dat verschil zit in
het model. Kranen vechten niet om een compressortaak — ze verwarmen allemaal alleen maar —
dus er valt niets te verdelen. Zet ze **niet** in een koelcircuit: dat begrip gaat over een
gedeelde compressor, en een ketel heeft er geen.

Modelleer het zo: elke kamer een zone, de kraan van die kamer als bron met rol *alleen
verwarmen*. Dat werkt met elke integratie die per ruimte een `climate`-entiteit levert —
Tado, Netatmo, Homematic, Z-Wave- en Zigbee-kranen.

Wat kranen wél delen is het apparaat dat het water warm maakt. Draait dat systeem zijn eigen
brander, zoals Tado doet, dan hoef je niets extra's in te stellen: de brug start de ketel
zodra een kraan erom vraagt. Is de warmtebron een aparte entiteit die iemand moet schakelen,
zet die dan onder **Gedeelde warmtebronnen**. Hij draait dan zolang een kamer die hij
bedient verwarmd wordt, en stopt zodra dat er geen meer is.

Zonder vast setpoint volgt de bron het warmste doel van de kamers die vragen. Het koudste
nemen zou de kamer die het hardst om warmte vraagt nooit laten halen wat hij vroeg.

### Talen

De uitleg onder elk invoerveld volgt de taal van je Home Assistant. Staat je HA op
Nederlands, dan zie je alleen Nederlands.

Meegeleverd: Nederlands, Engels, Duits, Frans, Spaans en Arabisch.

Een taal toevoegen is één bestand: kopieer `custom_components/climate_director/strings.json`
naar `custom_components/climate_director/translations/<taalcode>.json` en vertaal de
waarden. De sleutels en de plaatshouders (`{zone}`, `{resident}`, `{name}`, …) moeten
precies hetzelfde blijven; een test bewaakt dat voor elk taalbestand, zodat een vergeten
regel niet stilletjes als Engels doorschiet.

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

**Shadow mode is on by default.** The integration then computes every decision and shows
what it would have done, but issues no service call at all. You can let it run alongside
your existing automations for as long as you like, and only switch over once the two have
agreed with each other for weeks.

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
- **Openings** — a door or window standing open suspends the zone, optionally only after a
  delay you set per opening in seconds. Empty or zero means at once.
- **Occupancy** — somebody must be home.
- **Room presence** — a sensor per zone, with a grace period against flickering presence
  detectors. Somebody being home says nothing about whether anybody is in the attic; a
  zone without such a sensor is never held back on this.
- **Awake** — somebody home must also be out of bed.
- **Schedule** — time windows set per resident. Whoever fills in no schedule does not take
  part: they neither open the gate nor hold it shut. Whoever is home asleep while their own
  window has not opened yet makes the house wait.
- **Somebody home** — not a choice but a condition. If a trigger fires while none of the
  configured residents is home, nothing happens.

A holiday counts as a Saturday, unless a resident fills in a holiday window of their own;
that window then replaces their ordinary ones and ignores the days of the week. Holiday
mode goes on with the switch, or by itself as soon as one of the configured calendars has
an event running that carries the configured keyword.

Guest mode sets every gate about people aside — presence, sleep and schedule. Somebody is
staying who is not tracked, so the house looking empty says nothing, and the heating or air
conditioning should not go off over it. The gate about presence in the room itself still
applies: that one is about the room, not about who is in the house.

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

### What you get in Home Assistant

One device per installation, holding:

| Entity | For |
|---|---|
| `sensor.*_last_decision` | How many zones are being served, with the full plan as attributes: every command, every circuit, every deferred action, and which appliances would have been steered |
| `sensor.*_would_command_<entity>` | The mode the director would put this appliance in — one sensor per steered appliance |
| `sensor.*_mismatch` | How many appliances currently sit somewhere other than where the plan wants them. Zero means the director agrees with whatever is steering the house right now |
| `sensor.*_<zone>_source` | Which source serves this zone, with what the zone wanted, what it got and why |
| `binary_sensor.*_<zone>_blocked` | On when a zone got less than it asked for, with the reason as an attribute |
| `switch.*_director` | Master switch; off means nothing is regulated |
| `switch.*_holiday_mode` | Makes every day count as a Saturday, or as its own holiday schedule |
| `switch.*_guest_mode` | Keeps regulating while the residents are away; sets presence, sleep and schedule aside |
| `switch.*_<zone>_override` | Hands one zone back to the user until you turn it off again |
| `number.*_<zone>_priority` | How strongly this zone claims a shared outdoor unit; lower wins. Settable from an automation |

There is also a downloadable diagnostics export holding the configuration, the last
snapshot read and the last plan. With those three, any decision is exactly reproducible.

### Action

`climate_director.evaluate` makes the director decide again right now, instead of waiting
for a tracked entity to change of its own accord. Useful while setting up and while chasing
down a difference. In shadow mode that action still executes nothing — it only recomputes.
Without an `entry_id`, every installation is recomputed.

### Configuration check

If something is structurally wrong — a zone with no usable source, two sources on the same
entity, an outdoor window that admits nothing — it shows up as a repair notice in Home
Assistant. The zones that are sound carry on being regulated meanwhile; one broken zone does
not stop the installation. The full list is in the diagnostics.

That distinction is deliberate: a mistake in the configuration looks, from the outside, the
same as "the director decides nothing", and you end up hunting a bug that is really a typo.

### Judging a shadow run

The three sensors above are deliberately *states* rather than attributes: Home Assistant
records state history, and that is what makes a shadow run judgeable afterwards.

- **`sensor.*_mismatch`** is the headline number. Zero means the director agrees with
  whatever is actually running at that moment. A brief spike is normal — one side acts a
  moment before the other — but a reading that stays up is a real disagreement. Put this
  sensor in a history graph and every moment things went apart stands out at a glance.
- **`sensor.*_would_command_<entity>`** goes next to the history of the `climate` entity it
  names. Two lines following each other mean the director decided the same thing your
  automations did; every moment they diverge is a case to look into.
- **`sensor.*_<zone>_source`** and **`binary_sensor.*_<zone>_blocked`** then tell you *why*:
  which source was chosen, and which gate held a zone back.

Every sensor carries the reason as an attribute (`circuit_conflict_lost`,
`everyone_asleep`, `short_cycle_protection`, …), so a difference always traces back to one
rule in the design rather than to a hunch.

### Installation

**Through HACS:** add this repository as a **custom repository** (HACS > three dots >
Custom repositories > this GitHub URL, category "Integration"), install it, and restart
Home Assistant.

**Manually:** copy the `custom_components/climate_director` folder into your Home Assistant
configuration's `custom_components` folder and restart.

Then: **Settings > Devices & services > Add integration > Climate Director**. You give it a
name and leave shadow mode on. The installation then appears on the **Integrations** tab.

Everything else — zones, sources, refrigerant circuits, residents and openings — is built up
under **Configure** on that integration. Nothing is stored until you choose "Save and close"
in that menu.

A sensible order:

1. **General settings** — outdoor temperature sensor, where the season comes from, which
   gates you want (awake, schedule), and which calendars announce a holiday with which
   keyword.
2. **Zones and sources** — per room the indoor sensor and the switch-on/off points, then
   the appliances able to serve that room. Give a boiler and a heat pump adjacent outdoor
   windows and they hand over to each other seamlessly.
3. **Refrigerant circuits** — only needed when indoor units share an outdoor unit. Leave
   empty when every unit has its own.
4. **Residents** and **Doors and windows** — optional.

### Running and testing on its own

The decision layer runs and tests without Home Assistant:

```bash
pip install -r requirements_test.txt
python -m pytest
python -m ruff check .
```

### Do you need helpers

No. There is no `input_number`, `input_boolean` or `input_select` you have to create
beforehand. Everything hand-written automations use those for — thresholds, setpoints, a
master switch, a holiday switch, an override, the priority per zone — the integration either
creates itself or keeps in its own configuration.

What you do point at are entities you already have:

| Needed | For |
|---|---|
| An indoor temperature sensor per zone | Required; without one a zone knows nothing |
| One or more `climate` entities | Required; those are the appliances it steers |
| An outdoor temperature sensor | Only needed once you set limits on outdoor temperature — which you almost always want |
| `person` entities | Optional, for the occupancy gate |
| A sleep sensor per resident | Optional |
| A presence sensor per room | Optional |
| Door and window contacts | Optional |
| A season entity | Optional; by default the season is derived from the month |

Already have a helper you want to keep using — an `input_select` for the season, a template
sensor averaging several thermometers — then simply point at it. The integration never makes
you create something new, but allows it everywhere.

### Radiator valves and a boiler

A wet system with smart radiator valves works differently from a multi-split, and that
difference lives in the model. Valves do not fight over a compressor duty — they all only
ever heat — so there is nothing to arbitrate. Do **not** put them in a refrigerant circuit:
that concept is about a shared compressor, and a boiler has none.

Model it like this: every room a zone, that room's valve as its source with the role *heat
only*. That works with any integration exposing a `climate` entity per room — Tado, Netatmo,
Homematic, Z-Wave and Zigbee valves.

What valves do share is the appliance making the water hot. If that system fires its own
burner, as Tado does, nothing extra is needed: the bridge starts the boiler the moment a
valve asks. If the heat source is a separate entity somebody has to switch, put it under
**Shared heat sources**. It then runs while any room it serves is being heated, and stops
once none is.

Without a fixed setpoint the source follows the warmest target among the rooms asking.
Taking the coldest would leave the room asking hardest never reaching what it asked for.

### Languages

The explanation under each input follows your Home Assistant's language. With HA set to
Dutch you see Dutch and nothing else.

Shipped: Dutch, English, German, French, Spanish and Arabic.

Adding a language is one file: copy `custom_components/climate_director/strings.json` to
`custom_components/climate_director/translations/<code>.json` and translate the values. The
keys and the placeholders (`{zone}`, `{resident}`, `{name}`, …) have to stay exactly the
same; a test guards that for every language file, so a forgotten line cannot slip through as
English.

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
