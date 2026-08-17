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
| **Airco-circuit** | Eén buitenunit met de binnenunits die eraan hangen. Beschrijft *wat technisch tegelijk kan*. |

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

### Poorten en rangorde

Poorten bepalen of er überhaupt geregeld mag worden. Ze kijken naar omstandigheden, nooit
naar temperaturen — "mag het", niet "moet het". Ze worden van breed naar smal afgelopen, en
de eerste die dichtzit is de reden die je terugziet in `sensor.*_bron_<zone>`.

| # | Poort | Geldt voor | Wordt overruled door | Uit te zetten |
|---|---|---|---|---|
| 1 | **Hoofdschakelaar** | alles | niets | nee |
| 2 | **Handmatige override** | één zone | niets | nee, maar hij loopt af: zelf uitgezet geldt tot de volgende dag |
| 3 | **Openingen** | de zones die je aan de opening koppelt | niets | door de opening niet in te stellen |
| 4 | **Iemand thuis** | het hele huis | vooruit verwarmen, gastenmodus, aanwezigheidszones | nee, dit is een voorwaarde |
| 5 | **Wakker** | het hele huis | aanwezigheidszones | ja, *Iemand moet wakker zijn* |
| 6 | **Rooster** | het hele huis | gastenmodus, aanwezigheidszones | ja, *Het rooster van een bewoner moet openstaan* |
| 7 | **Aanwezigheid in de ruimte** | één zone | vooruit verwarmen | door geen sensor in te stellen |

Zo lees je de tabel: staat de hoofdschakelaar uit, dan doet de rest er niet toe. Staat er
een raam open, dan helpt geen enkele aanwezigheid. En is een kamer aantoonbaar leeg, dan
wordt hij niet verwarmd hoe wakker en aanwezig de rest van het huis ook is.

**Iemand thuis is bewust geen instelling.** Een leeg huis verwarmen is iets waar je alleen
per ongeluk voor kiest, dus die knop bestaat niet. Wil je toch dat een ruimte draait
zonder dat er iemand thuis is, dan is dat precies waar de twee uitzonderingen hieronder
voor zijn.

#### Wat bepaalt een zone: het huishouden of de kamer

Per zone kies je bij *Wat bepaalt of deze zone draait*:

- **Het huishouden** (standaard) — poorten 4 tot en met 7 gelden. Dit is de woonkamer:
  hij volgt het ritme van het huis. Stel je hier óók een aanwezigheidssensor in, dan knijpt
  die het verder dicht: het huishouden moet het toestaan **en** de kamer moet bezet zijn.
- **De ruimte zelf** — poorten 4 tot en met 6 worden overgeslagen. Alleen de
  aanwezigheidssensor beslist. Dit is de zolder: wie er zit, zit er, en dat is een beter
  antwoord dan welk rooster ook kan geven. Deze keuze vereist een aanwezigheidssensor,
  anders kan de zone nooit draaien — de configuratiecontrole zegt dat ook.

Poorten 1, 2 en 3 blijven in beide gevallen gelden. Die gaan niet over mensen.

Zo kun je in één huis de woonkamer op het rooster laten lopen en de zolder op
aanwezigheid, zonder dat de een de ander in de weg zit.

#### Zelf een airco uitzetten

Zet je een airco uit bij het apparaat of op de afstandsbediening, dan valt die zone stil.
De director zet hem niet twee seconden later weer aan — dat is het ergste wat hij kan doen,
want jij had hem net expres stilgezet.

De zone doet weer mee zodra:

- **jij hem weer aanzet**, in welke stand dan ook;
- **het de volgende dag is.** Een besluit van gisteravond hoort vanochtend niet meer te
  gelden, dus de zone doet vanaf middernacht gewoon weer mee.

Uitzetten dat de director zélf doet telt niet mee, anders zou elke zone die hij ooit
uitzet permanent stil komen te staan. De schakelaar `switch.*_override_<zone>` blijft
daarnaast gewoon werken en staat boven dit alles.


#### Waar de grens tussen twee bronnen precies valt

Buitengrenzen zijn **half open**: de ondergrens hoort erbij, de bovengrens niet. Twee
aangrenzende bronnen dekken zo de hele schaal, zonder gat en zonder overlap — er is altijd
precies één bron aan de beurt.

Wil je gas onder de 3 °C en de airco erboven, dan zet je de grens **niet** op 3,0:

| Grens | 2,9 °C | 3,0 °C | 3,1 °C |
|---|---|---|---|
| beide op `3.0` | gas | **airco** | airco |
| beide op `3.1` | gas | **gas** | airco |

De grenswaarde zelf valt dus altijd naar de bron met de ondergrens. Wil je dat 3,0 °C nog
naar het gas gaat, zet dan beide op `3.1`. Zet ze **nooit verschillend** — gas tot `3.1` en
airco vanaf `3.0` geeft een overlap waarin allebei mogen, en dan bepaalt de volgorde binnen
de zone wie het wordt in plaats van de buitentemperatuur.

Belangrijk: zet de grens bij **elke** bron gelijk. Staat de woonkamer-airco op `3.1` en de
zolder-airco nog op `3.0`, dan kan bij precies 3,0 °C het gas de woonkamer verwarmen terwijl
de zolder-airco aanslaat — precies de combinatie die je wilde vermijden.

#### Een kamer die je zelf bedient

Voor een ruimte zonder eigen thermometer en zonder aanwezigheidssensor, waar je het apparaat
met de hand of met een script aanzet. Je maakt er toch een zone van, want alleen dan weet de
integratie van dat apparaat af.

1. **Zone toevoegen.** Als binnentemperatuursensor kies je de `climate.*`-entiteit van het
   apparaat zelf — bijna elke airco meldt zijn eigen kamertemperatuur, en de integratie
   leest dan het attribuut `current_temperature`.
2. **Wat bepaalt of deze zone draait:** laat op *Het huishouden* staan. Kies je *De ruimte
   zelf* zonder aanwezigheidssensor, dan kan de zone nooit draaien — ook niet om het
   apparaat uit te zetten.
3. **Bron toevoegen** met datzelfde apparaat, en zet **Dit apparaat automatisch aanzetten**
   uit.

Wat je daarmee krijgt: de integratie zet het apparaat **nooit zelf aan**, laat hem staan
zoals jij hem zet, en zet hem **alleen uit** wanneer de gedeelde buitenunit een andere taak
moet doen of wanneer er niemand meer thuis is.

Sla je deze stap over en zet je het apparaat alleen in het airco-circuit, dan is het voor de
integratie een onbeheerde unit: draait hij, dan houdt hij het hele circuit op zijn taak en
kan geen enkele kamer nog iets anders vragen — en uitzetten kan de integratie hem niet, want
hij is van niemand. De configuratiecontrole meldt dat.

#### Een handmatige timer ernaast laten lopen

Wil je een apparaat een paar uur met de hand aanzetten — "de gasverwarming twee uur aan" —
dan hoeft dat niet in de integratie. Het kan gewoon met een script ernaast, mits je die
zone zolang aan jezelf teruggeeft met de override. Zonder dat rekent de director bij de
eerstvolgende evaluatie haar eigen plan door en zet ze je apparaat weer uit.

```yaml
alias: Gasverwarming twee uur aan
sequence:
  - action: switch.turn_on
    target:
      entity_id: switch.climate_director_override_woonkamer
  - action: timer.start
    data:
      duration: "02:00:00"
    target:
      entity_id: timer.verwarming
  - action: climate.set_temperature
    data:
      temperature: 20
      hvac_mode: heat
    target:
      entity_id: climate.smart_thermostat_x
```

En het aflopen van de timer zet alles weer terug:

```yaml
alias: Gasverwarming timer afgelopen
triggers:
  - trigger: event
    event_type: timer.finished
    event_data:
      entity_id: timer.verwarming
actions:
  - action: climate.turn_off
    target:
      entity_id: climate.smart_thermostat_x
  - action: switch.turn_off
    target:
      entity_id: switch.climate_director_override_woonkamer
```

Een apparaat waarvan *Dit apparaat automatisch aanzetten* uit staat heeft die override niet
nodig: de director start hem toch al nooit en laat hem staan zoals hij staat. Een
slaapkamerairco die je met een script aanzet, blijft dus gewoon draaien tot je timer
afloopt — en gaat alleen uit als de gedeelde buitenunit een andere taak moet doen.

Verwar dit niet met **vooruit verwarmen**. Dat is bedoeld voor een leeg huis, geldt alleen
binnen het ingestelde venster en heeft een maximum. Een handmatige timer met override is
het gereedschap voor "ik wil dit nu, en ik bepaal hoe lang".

#### Vooruit verwarmen

De enige manier om een leeg huis te laten draaien, en met opzet de enige die je met de
hand moet aanzetten. Roep de actie `climate_director.precondition` aan vanaf je telefoon,
een dashboardknop of een automatisering, en de opgegeven zones beginnen alvast te
verwarmen of te koelen zodat het goed is als je binnenloopt.

```yaml
action: climate_director.precondition
data:
  zone_ids: [woonkamer]
  minutes: 45
```

Wat het overslaat: *iemand thuis*, *wakker*, *rooster* en *aanwezigheid in de ruimte* —
precies de poorten die een leeg huis tegenhouden. Wat het niet overslaat: de
hoofdschakelaar, een handmatige override, een openstaand raam, de dode band, de
buitengrenzen en alle circuitregels. Vooruit verwarmen is een reden om te mogen, geen
reden om te moeten.

Twee grenzen maken dit veilig, en geen van beide is te vergeten:

- **Het verloopt vanzelf.** Er is geen schakelaar die aan kan blijven staan, alleen een
  teller die afloopt. Vraag je langer dan het ingestelde maximum (standaard twee uur), dan
  wordt je verzoek ingekort in plaats van geweigerd. Geen tijd opgeven geeft het maximum.
- **Het geldt alleen binnen het venster**, standaard 06:00 tot 23:00. Daarbuiten telt een
  verzoek eenvoudig niet mee, dus een vertypte automatisering kan je 's nachts niet de
  ketel laten aanslaan.

Bij het aflopen van de teller neemt niets het over: de gewone poorten gelden weer. Ben je
inmiddels thuis, dan draait alles gewoon door. Is er niemand thuis, dan gaat alles uit.
Dat is dezelfde poort die het altijd al was, en precies wat je wilt.

Afblazen kan met `climate_director.cancel_precondition`, met of zonder `zone_ids`.

#### Vakantiemodus

Een vakantiedag telt als **zaterdag**: elk rooster in huis wordt als een zaterdagrooster
gelezen, inclusief het wachten op wie er nog slaapt. Wil iemand op vakantie andere uren,
dan vinkt die bij een venster *Dit is een vakantievenster* aan; dat venster vervangt dan
zijn gewone vensters en negeert de dagen van de week.

De vakantiemodus gaat aan met `switch.*_vakantiemodus`, of vanzelf zodra er in een van de
ingestelde agenda's een item loopt met het ingestelde trefwoord erin. **Zonder trefwoord
blijven de agenda's helemaal buiten beschouwing** — raden welk agenda-item vakantie
bedoelde is niet aan de integratie.

Het trefwoord wordt ruim herkend: hoofdletters en schrijfwijze maken niet uit, en het telt
ook midden in een langer woord. Met `vakantie` als trefwoord worden `Herfstvakantie`,
`Zomervakantie 2026` en `VAKANTIE Frankrijk` dus allemaal herkend. Een agenda staat immers
vol met samenstellingen en niet met het kale woord.

#### Gastenmodus

`switch.*_gastenmodus` neemt de poorten over die over afwezigheid gaan: *iemand thuis* en
*rooster*. Er logeert dan iemand die niet gevolgd wordt, dus dat het huis leeg lijkt zegt
niets.

Wat blijft gelden:

- **Slaap**, maar alleen van wie thuis is. Komt een bewoner thuis en gaat die naar bed,
  dan is de dag voorbij en gaat het huis uit. Is er niemand thuis, dan slaapt er ook
  niemand en blijft het draaien.
- **Het gastenvenster**. Daarbuiten nemen de gewone poorten het weer over, zodat een
  schakelaar die niemand uitzette niet de hele nacht doordraait. Beide velden leeg laten
  betekent de hele dag.
- **Aanwezigheid in de ruimte.** Die gaat over de kamer, niet over wie er in huis is.

Een installatie zonder bewoners (kantoor, vakantiehuis, serverruimte) slaat poorten 4 tot
en met 6 over in plaats van permanent op slot te zitten.

### Welke entiteiten heb je nodig

| Entiteit | Verplicht | Waarvoor |
|---|---|---|
| Eén `climate.*` per zone | **ja** | zonder apparaat valt er niets aan te sturen |
| Een temperatuursensor per zone | **ja** | zonder meting weet de integratie niet of het te koud of te warm is; een `climate.*` met `current_temperature` mag ook |
| `sensor.*` of `weather.*` buitentemperatuur | nee | alleen nodig als je bronnen of taken op buitentemperatuur wilt begrenzen — bijvoorbeeld gas onder 3 °C, warmtepomp erboven |
| `person.*` of `device_tracker.*` per bewoner | ja, zodra je bewoners instelt | anders kan die bewoner nooit thuis zijn |
| Een slaapsensor per bewoner | nee | zonder deze telt niemand ooit als slapend; de wakker-poort staat dan altijd open |
| `binary_sensor.*` aanwezigheid per zone | nee, tenzij de zone op *de ruimte zelf* draait | dan is het de enige poort die de zone heeft |
| `binary_sensor.*` deur of raam | nee | schort de gekoppelde zones op zolang hij openstaat |
| `calendar.*` | nee | zet de vakantiemodus vanzelf aan; werkt alleen mét trefwoord |
| Een seizoensentiteit | nee | alleen als je het seizoen niet uit de maand wilt afleiden |

Helpers hoef je nergens voor aan te maken. De integratie levert haar eigen schakelaars en
regelaars.

### Alle instellingen

**Algemene instellingen**

| Instelling | Wat het doet | Waarom |
|---|---|---|
| Buitentemperatuursensor | voedt alle buitengrenzen | zonder deze telt elke ingestelde grens als niet gehaald |
| Herkomst van het seizoen | maand, entiteit, of vast op zomer/winter | een entiteit laat een bestaande helper gewoon doorwerken |
| Iemand moet wakker zijn | poort 5 aan of uit | uit als je slaapsensoren niet vertrouwt |
| Het rooster van een bewoner moet openstaan | poort 6 aan of uit | uit als je alleen op aanwezigheid wilt sturen |
| Vooruit verwarmen vanaf / tot | het venster waarin een verzoek meetelt | dit is het enige dat een leeg huis laat draaien |
| Vooruitverwarmingsduur | het plafond op één verzoek | een verzoek kun je niet vergeten, alleen vertypen |
| Gastenmodus vanaf / tot | het gastenvenster | voorkomt dat een vergeten schakelaar de nacht doordraait |
| Vakantieagenda's | welke agenda's vakantie mogen aankondigen | meerdere toegestaan |
| Woord dat vakantie aangeeft | het trefwoord dat een item moet dragen | leeg = agenda's worden genegeerd |
| Schaduwmodus | rekent alles door, stuurt niets aan | om naast je bestaande automatiseringen mee te kijken |

**Per zone**

| Instelling | Wat het doet |
|---|---|
| Naam | de naam in de entiteiten |
| Binnentemperatuursensor | waarop de dode band rekent |
| Prioriteit | hoe hard deze zone een gedeelde buitenunit claimt; **lager wint**. Op één multi-split mag geen enkel nummer dubbel voorkomen |
| Wat bepaalt of deze zone draait | het huishouden of de ruimte zelf, zie hierboven |
| Aanwezigheidssensor + status + nalooptijd | wanneer de kamer als bezet telt; de nalooptijd vangt knipperende melders op |
| Verwarmen aan/uit, doel, aanzetpunt, dode band, buitengrens | wanneer verwarmen mag beginnen en stoppen |
| Koelen aan/uit, doel, aanzetpunt, dode band, buitengrens | idem voor koelen |

Verwarmen start bij `binnen <= aanzetpunt` en stopt bij `binnen >= aanzetpunt + dode band`.
Koelen start bij `binnen >= aanzetpunt` en stopt bij `binnen <= aanzetpunt - dode band`.
Het aanzetpunt telt als bereikt, het uitzetpunt als gepasseerd — dat is wat een apparaat
belet om op één tiende graad te blijven klepperen.

**Per bron**

| Instelling | Wat het doet |
|---|---|
| Climate-entiteit | het apparaat zelf |
| Taak | alleen verwarmen, alleen koelen, of allebei |
| Dit apparaat automatisch aanzetten | uit laat hem met rust, zie hieronder |
| Prioriteit | welke bron binnen de zone de voorkeur heeft; lager wint |
| Buitengrenzen | tussen welke buitentemperaturen deze bron de verstandige keuze is |

#### Een apparaat dat je zelf aanzet

Zet *Dit apparaat automatisch aanzetten* uit voor een airco die je met de hand bedient en
verder met rust gelaten wilt hebben — een slaapkamer zonder aanwezigheidssensor,
bijvoorbeeld. De director:

- **zet hem nooit aan**, hoe koud of warm die kamer ook wordt;
- **laat hem staan** zoals hij staat als jij hem aanzet;
- **zet hem alleen uit** als hij een taak draait die de gedeelde buitenunit niet toestaat,
  bijvoorbeeld wanneer hij verwarmt terwijl de woonkamer moet koelen.

Zo'n bron telt ook niet mee als antwoord op een warmte- of koudevraag. Hij claimt dus geen
plek op de buitenunit die hij nooit gebruikt, en houdt een kamer met meer voorrang niet
tegen. Heeft een zone alleen zulke bronnen, dan kan hij nooit vanzelf draaien — de
configuratiecontrole meldt dat.

**Per bewoner**

| Instelling | Wat het doet |
|---|---|
| Aanwezigheidsentiteit | of deze persoon thuis is |
| Slaapentiteit + status | wanneer deze persoon slaapt, bijvoorbeeld `sensor.danny_charger_type` op `wireless` |
| Roostervensters | begin, eind, dagen van de week, en of het een vakantievenster is |

Een bewoner zonder rooster doet niet mee aan poort 6: die opent hem niet en houdt hem ook
niet tegen. Datzelfde geldt **per dag**: wie op dinsdag geen venster heeft, doet dinsdag
niet mee. Anders zou iemand met alleen weekendvensters het huis elke doordeweekse ochtend
tegenhouden tot hij wakker wordt, en dat is geen rooster maar een slot. Een bewoner die thuis is en slaapt terwijl zijn eigen venster nog niet open is,
houdt het huis tegen — dat is wat het huis op zaterdag op de laatste slaper laat wachten.

**Per airco-circuit**

| Instelling | Wat het doet |
|---|---|
| Binnenunits | welke `climate.*` aan deze buitenunit hangen |
| Verwarmen en koelen tegelijk | uit voor een gewone multi-split: die kan maar één taak tegelijk |
| Conflictbeleid | wie wint als twee kamers het oneens zijn: prioriteit, wie eerst was, grootste afwijking, of het seizoen |
| Pauze bij het wisselen van taak | hoe lang alles uit moet staan vóór de omschakeling |
| Minimale looptijd voor een taakwissel | hoe lang een taak minstens moet hebben gedraaid voordat de andere hem mag overnemen |
| Minimale cyclustijd | hoe lang een unit uit blijft na het stoppen; vertraagt alleen starten, nooit stoppen |
| Maximum aantal units tegelijk | de capaciteitsgrens van de buitenunit |

#### Als er iets vastloopt

De mismatch-teller vergelijkt het plan met de werkelijkheid, en loopt daarvoor over de
commando's. Een apparaat waar het plan **geen** commando voor heeft komt daar niet in voor
— een klem waarbij er niets wordt aangestuurd is voor die teller dus onzichtbaar.

`binary_sensor.*_vastgelopen` kijkt naar het andere spoor. Een handvol redenen hoort uit
zichzelf op te lossen: wachten op de omschakelpauze, op de minimale looptijd, op de
minimale cyclustijd, of op een vrije plek op de buitenunit. Staat een zone daar langer op
dan de ingestelde tijd (standaard vijftien minuten), dan wacht hij niet meer maar zit hij
vast, en gaat de melder aan. In de attributen staat welke zones, waarop, en hoe lang.

Dezelfde melder gaat ook aan als een **ingestelde entiteit niet te lezen is** — verkeerd
getikt, verwijderd, of tijdelijk `unavailable`. Ook dat faalt stil: de poort die erop leunt
gaat dicht, de zone doet niets, en dat lijkt op een zone die niets hoeft te doen. Welke
entiteiten het zijn staat in het attribuut `unusable_entities`.

Redenen die wél lang mogen blijven staan — niemand thuis, kamer leeg, buiten het
temperatuurvenster — tellen niet mee. Nul minuten zet de melder uit.

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

Wat er in het event zit: `zone_id`, `zone_name`, `wanted`, `granted`, `source_id`,
`entity_id`, `hvac_mode`, `temperature` en `reason`.

Één automatisering vervangt daarmee al je losse notificatieblokken. Met de gewone
`notify`-actie:

```yaml
alias: Klimaat: melden wat er besloten is
triggers:
  - trigger: event
    event_type: climate_director_decision
actions:
  - action: notify.mobile_app_telefoon
    data:
      message: >-
        {{ trigger.event.data.zone_name }}: {{ trigger.event.data.hvac_mode }}
        via {{ trigger.event.data.source_id }} ({{ trigger.event.data.reason }})
```

Heb je een eigen notificatiescript, dan roep je dat op dezelfde plek aan:

```yaml
actions:
  - action: script.notify_algemeen_met_keuzemenu
    data:
      bericht: >-
        {{ trigger.event.data.zone_name }} staat nu op
        {{ trigger.event.data.hvac_mode }}
```

Filteren op wat je interesseert kan met een conditie op `reason`. Alleen melden wanneer een
kamer iets niet kreeg:

```yaml
conditions:
  - condition: template
    value_template: "{{ trigger.event.data.granted == 'neutral' }}"
```


### Wat je in Home Assistant krijgt

Eén device per installatie, met daaronder:

| Entiteit | Waarvoor |
|---|---|
| `sensor.*_laatste_beslissing` | Hoeveel zones bediend worden, met het volledige plan als attributen: elk commando, elk circuit, elke uitgestelde actie, en welke apparaten er aangestuurd zouden zijn |
| `sensor.*_zou_<entiteit>_aansturen` | De stand waarin de director dit apparaat zou zetten — één sensor per aangestuurd apparaat |
| `sensor.*_afwijkingen` | Hoeveel apparaten er nú anders staan dan het plan wil. Nul betekent dat de director het eens is met wat het huis op dit moment stuurt |
| `sensor.*_bron_<zone>` | Welke bron deze zone bedient, met wat de zone wilde, wat hij kreeg en waarom |
| `binary_sensor.*_<zone>_geblokkeerd` | Aan als een zone minder kreeg dan hij vroeg, met de reden als attribuut |
| `binary_sensor.*_vastgelopen` | Aan als een zone te lang op dezelfde wachtreden staat, met de zones en de wachttijd als attribuut |
| `switch.*_director` | Hoofdschakelaar; uit betekent dat er niets geregeld wordt |
| `switch.*_vakantiemodus` | Laat elke dag als zaterdag tellen, of als het eigen vakantierooster |
| `switch.*_gastenmodus` | Blijft regelen terwijl de bewoners weg zijn; slaap en het gastenvenster blijven gelden |
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

Alles verder — zones, bronnen, airco-circuits, bewoners en openingen — bouw je op via
**Configureren** bij die integratie. Er wordt niets opgeslagen tot je in dat menu
"Opslaan en sluiten" kiest.

Een verstandige volgorde:

Elk scherm heeft onderaan een regel **Als je hier klaar bent**, met de keuze tussen
bewaren of verwerpen, en elke keuzelijst heeft een regel **← Terug naar het hoofdmenu**.
Je zit dus nergens vast. Home Assistant tekent precies één knop onder een formulier en
laat een integratie er geen tweede bij zetten, dus een echte Terug-knop naast Opslaan
bestaat niet — deze regels zijn wat er wél kan.

Teruggaan kan altijd, ook als je een veld half hebt ingevuld of leeg hebt gelaten. Je krijgt
dan geen "niet alle verplichte velden zijn ingevuld" meer: het scherm laat je gaan en wat
je intikte gaat verloren. Kies je juist wel bewaren en mist er iets, dan wijst de melding
het veld aan in plaats van de deur op slot te doen.

Er wordt sowieso niets naar de installatie geschreven tot je in het hoofdmenu **Opslaan en
sluiten** kiest. Valt er dan iets op aan je configuratie, dan krijg je die lijst eerst te
zien met de keuze *Toch opslaan* of *Terug om iets aan te passen*. Het is een
waarschuwing, geen weigering: een installatie mag met opzet afwijkend zijn, en alleen jij
weet of dat zo is.

1. **Algemene instellingen** — buitentemperatuursensor, herkomst van het seizoen, welke
   poorten je wilt (wakker, rooster), tussen welke tijden de gastenmodus geldt, en welke
   agenda's een vakantie aankondigen met welk trefwoord.
2. **Zones en bronnen** — per ruimte de binnentemperatuursensor en de aan-/uitpunten,
   daarna de apparaten die die ruimte kunnen bedienen. Geef een cv-ketel en een warmtepomp
   aansluitende buitenvensters, dan wisselen ze elkaar naadloos af.
3. **Airco-circuits** — alleen nodig als binnenunits een buitenunit delen. Laat leeg als elke
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
dus er valt niets te verdelen. Zet ze **niet** in een airco-circuit: dat begrip gaat over een
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

### Gates and precedence

Gates decide whether anything may be regulated at all. They look at
circumstances, never at temperatures — "is this allowed", not "is this needed". They are
walked from broad to narrow, and the first one that is shut is the reason you see back in
`sensor.*_<zone>_source`.

| # | Gate | Applies to | Overruled by | Can be turned off |
|---|---|---|---|---|
| 1 | **Master switch** | everything | nothing | no |
| 2 | **Manual override** | one zone | nothing | no, but it expires: switched off by hand holds until the next day |
| 3 | **Openings** | the zones you attach the opening to | nothing | by not configuring the opening |
| 4 | **Somebody home** | the whole house | pre-conditioning, guest mode, presence-driven zones | no, this is a condition |
| 5 | **Awake** | the whole house | presence-driven zones | yes, *Somebody must be awake* |
| 6 | **Schedule** | the whole house | guest mode, presence-driven zones | yes, *A resident's schedule must be open* |
| 7 | **Room presence** | one zone | pre-conditioning | by setting no sensor |

Read the table like this: with the master switch off, the rest does not matter. With a
window open, no amount of presence helps. And a room that is demonstrably empty is not
heated however awake and present the rest of the house may be.

**Somebody being home is deliberately not a setting.** Heating an empty house is something
you only ever choose by accident, so that button does not exist. If you do want a room to
run while nobody is home, that is exactly what the two exceptions below are for.

#### What decides a zone: the household or the room

Per zone you choose under *What decides whether this zone runs*:

- **The household** (default) — gates 4 through 7 apply. This is the living room: it
  follows the rhythm of the house. Set a presence sensor here as well and it narrows things
  further: the household must allow it **and** the room must be occupied.
- **The room itself** — gates 4 through 6 are skipped. Only the presence sensor decides.
  This is the attic: whoever is sitting there is sitting there, and that is a better answer
  than any schedule can give. This choice requires a presence sensor, or the zone can never
  run — and the configuration check says so.

Gates 1, 2 and 3 apply either way. Those are not about people.

So one house can run its living room on the schedule and its attic on presence, without
either getting in the other's way.

#### Switching an air conditioner off yourself

Switch an air conditioner off at the appliance or on the remote and that zone falls silent.
The director does not put it back on two seconds later — that is the worst thing it could
do, since you had just deliberately silenced it.

The zone takes part again as soon as:

- **you switch it back on**, in whatever mode;
- **it is the next day.** Last night's decision should not still hold this morning, so from
  midnight the zone simply joins in again.

Switching off that the director does itself does not count, or every zone it ever switches
off would fall silent for good. The `switch.*_<zone>_override` switch keeps working
alongside this and outranks all of it.


#### Where the boundary between two sources falls exactly

Outdoor bounds are **half open**: the lower bound belongs to the window, the upper one does
not. Two adjacent sources thereby cover the whole scale, with no gap and no overlap — there
is always exactly one source whose turn it is.

Want gas below 3 °C and the air conditioner above it? Then do **not** put the boundary at
3.0:

| Boundary | 2.9 °C | 3.0 °C | 3.1 °C |
|---|---|---|---|
| both at `3.0` | gas | **air conditioner** | air conditioner |
| both at `3.1` | gas | **gas** | air conditioner |

The boundary value itself always falls to the source carrying it as its lower bound. To have
3.0 °C still go to the gas, put both at `3.1`. **Never set them differently** — gas up to
`3.1` and the air conditioner from `3.0` leaves an overlap where both are allowed, and then
the order within the zone decides rather than the outdoor temperature.

Important: set the boundary the same on **every** source. With the living room unit at `3.1`
and the attic unit still at `3.0`, at exactly 3.0 °C the gas can heat the living room while
the attic unit fires up — precisely the combination you meant to avoid.

#### A room you operate yourself

For a room without a thermometer of its own and without a presence sensor, where you switch
the appliance on by hand or with a script. You still make it a zone, because only then does
the integration know that appliance exists.

1. **Add a zone.** For the indoor temperature sensor, pick the appliance's own `climate.*`
   entity — nearly every air conditioner reports its own room temperature, and the
   integration then reads the `current_temperature` attribute.
2. **What decides whether this zone runs:** leave it on *The household*. Choose *The room
   itself* without a presence sensor and the zone can never run — not even to switch the
   appliance off.
3. **Add a source** with that same appliance, and switch **Start this appliance
   automatically** off.

What that gets you: the integration **never switches it on** itself, leaves it as you set
it, and switches it **off only** when the shared outdoor unit has to do another duty or when
nobody is home any more.

Skip this and put the appliance in the air conditioning circuit alone, and it is an
unmanaged unit as far as the integration is concerned: if it runs it holds the whole circuit
to its duty and no room can ask for anything else — and the integration cannot switch it off,
since it belongs to nobody. The configuration check reports that.

#### Running a manual timer alongside

Want to switch an appliance on by hand for a few hours — "the gas heating on for two
hours" — that need not go through the integration. A script beside it does the job, as long
as you hand that zone back to yourself with the override for the duration. Without it the
director works out its own plan at the next evaluation and switches your appliance off
again.

```yaml
alias: Gas heating on for two hours
sequence:
  - action: switch.turn_on
    target:
      entity_id: switch.climate_director_woonkamer_override
  - action: timer.start
    data:
      duration: "02:00:00"
    target:
      entity_id: timer.heating
  - action: climate.set_temperature
    data:
      temperature: 20
      hvac_mode: heat
    target:
      entity_id: climate.smart_thermostat_x
```

And the timer running out puts everything back:

```yaml
alias: Gas heating timer finished
triggers:
  - trigger: event
    event_type: timer.finished
    event_data:
      entity_id: timer.heating
actions:
  - action: climate.turn_off
    target:
      entity_id: climate.smart_thermostat_x
  - action: switch.turn_off
    target:
      entity_id: switch.climate_director_woonkamer_override
```

An appliance with *Start this appliance automatically* switched off needs no override: the
director never starts it anyway and leaves it as it stands. A bedroom air conditioner you
switch on with a script therefore keeps running until your timer expires — and only goes
off when the shared outdoor unit has to do another duty.

Do not confuse this with **pre-conditioning**. That is meant for an empty house, applies
only inside the configured window and has a maximum. A manual timer with an override is the
tool for "I want this now, and I decide for how long".

#### Pre-conditioning

The only way to run an empty house, and deliberately the only one you have to switch on by
hand. Call the action `climate_director.precondition` from your phone, a dashboard button
or an automation, and the named zones start heating or cooling ahead so the place is right
when you walk in.

```yaml
action: climate_director.precondition
data:
  zone_ids: [woonkamer]
  minutes: 45
```

What it skips: *somebody home*, *awake*, *schedule* and *room presence* — exactly the gates
that hold an empty house back. What it does not skip: the master switch, a manual override,
an open window, the dead band, the outdoor bounds and every circuit rule. Pre-conditioning
is a reason to be allowed, never a reason to be needed.

Two bounds make this safe, and neither can be forgotten:

- **It expires by itself.** There is no switch that can be left on, only a timer that runs
  out. Ask for longer than the configured maximum (two hours by default) and your request
  is shortened rather than refused. Giving no time at all gives you the maximum.
- **It only counts inside the window**, 06:00 to 23:00 by default. Outside it a request
  simply does not count, so a mistyped automation cannot fire the boiler at three at night.

When the timer runs out nothing takes over: the ordinary gates apply again. If you are home
by then, everything simply keeps running. If nobody is home, everything goes off. That is
the same gate it always was, and exactly what you want.

Call it off with `climate_director.cancel_precondition`, with or without `zone_ids`.

#### Holiday mode

A holiday counts as a **Saturday**: every schedule in the house is read as a Saturday's,
including waiting for whoever is still asleep. Want different hours on holiday? Tick *This
is a holiday window* on a window; it then replaces that resident's ordinary windows and
ignores the days of the week.

Holiday mode goes on with `switch.*_holiday_mode`, or by itself as soon as one of the
configured calendars has an event running that carries the configured keyword. **Without a
keyword the calendars are ignored entirely** — guessing which event meant a holiday is not
the integration's call to make.

The keyword is matched generously: spelling and capitals do not matter, and it counts
inside a longer word too. With `holiday` as the keyword, `Summer holiday`, `holidays` and
`HOLIDAY in France` all match. A calendar is full of compounds, after all, rather than the
bare word.

#### Guest mode

`switch.*_guest_mode` takes over the gates that are about absence: *somebody home* and
*schedule*. Somebody untracked is staying, so the house looking empty says nothing.

What still applies:

- **Sleep**, but only of those who are home. Once a resident comes home and turns in, the
  day is over and the house goes off. With nobody home nobody is asleep, and it keeps
  running.
- **The guest window.** Outside it the ordinary gates take over again, so a switch nobody
  turned off does not run all night. Leaving both fields empty means all day.
- **Room presence.** That one is about the room, not about who is in the house.

An installation without residents (an office, a holiday home, a server room) skips gates 4
through 6 rather than staying locked out forever.

### Which entities you need

| Entity | Required | What for |
|---|---|---|
| One `climate.*` per zone | **yes** | without an appliance there is nothing to steer |
| A temperature sensor per zone | **yes** | without a reading the integration cannot tell too cold from too warm; a `climate.*` with `current_temperature` will do |
| `sensor.*` or `weather.*` outdoor temperature | no | only needed to bound sources or duties by outdoor temperature — gas below 3 °C, heat pump above it, say |
| `person.*` or `device_tracker.*` per resident | yes, once you configure residents | otherwise that resident can never be home |
| A sleep sensor per resident | no | without one nobody ever counts as asleep, so the awake gate stays open |
| `binary_sensor.*` presence per zone | no, unless the zone runs on *the room itself* | then it is the only gate the zone has |
| `binary_sensor.*` door or window | no | suspends the attached zones while it is open |
| `calendar.*` | no | switches holiday mode on by itself; works only with a keyword |
| A season entity | no | only if you do not want the season derived from the month |

You need to create no helpers for any of this. The integration ships its own switches and
controls.

### Every setting

**General settings**

| Setting | What it does | Why |
|---|---|---|
| Outdoor temperature sensor | feeds every outdoor bound | without it any bound you set counts as not met |
| Where the season comes from | month, entity, or pinned to summer/winter | an entity lets an existing helper keep working |
| Somebody must be awake | gate 5 on or off | off if you do not trust your sleep sensors |
| A resident's schedule must be open | gate 6 on or off | off if you want to steer on presence alone |
| Pre-conditioning from / until | the window in which a request counts | this is the only thing that runs an empty house |
| Pre-conditioning duration | the ceiling on a single request | a request cannot be forgotten, only mistyped |
| Guest mode from / until | the guest window | keeps a forgotten switch from running all night |
| Holiday calendars | which calendars may announce a holiday | several allowed |
| Word that marks a holiday | the keyword an event must carry | empty = calendars are ignored |
| Shadow mode | works everything out, steers nothing | to watch along beside your existing automations |

**Per zone**

| Setting | What it does |
|---|---|
| Name | the name in the entities |
| Indoor temperature sensor | what the dead band works from |
| Priority | how strongly this zone claims a shared outdoor unit; **lower wins**. On one multi-split no number may appear twice |
| What decides whether this zone runs | the household or the room itself, see above |
| Presence sensor + state + grace period | when the room counts as occupied; the grace period absorbs flickering detectors |
| Heating on/off, target, switch-on point, dead band, outdoor bound | when heating may start and stop |
| Cooling on/off, target, switch-on point, dead band, outdoor bound | the same for cooling |

Heating starts at `indoor <= switch-on point` and stops at `indoor >= switch-on point +
dead band`. Cooling starts at `indoor >= switch-on point` and stops at `indoor <=
switch-on point - dead band`. The switch-on point counts as reached, the switch-off point
as passed — which is what keeps an appliance from chattering on a tenth of a degree.

**Per source**

| Setting | What it does |
|---|---|
| Climate entity | the appliance itself |
| Duty | heating only, cooling only, or both |
| Start this appliance automatically | off leaves it alone, see below |
| Priority | which source within the zone is preferred; lower wins |
| Outdoor bounds | between which outdoor temperatures this source is the sensible choice |

#### An appliance you switch on yourself

Turn *Start this appliance automatically* off for an air conditioner you operate by hand
and want left alone — a bedroom without a presence sensor, say. The director:

- **never switches it on**, however cold or warm that room gets;
- **leaves it as it stands** once you switch it on;
- **switches it off only** when it runs a duty the shared outdoor unit cannot allow, for
  instance heating while the living room needs to cool.

Such a source also does not count as an answer to a demand. It therefore claims no place on
the outdoor unit it never uses, and holds back no room with more claim. If a zone has only
sources like this, it can never run on its own — and the configuration check says so.

**Per resident**

| Setting | What it does |
|---|---|
| Presence entity | whether this person is home |
| Sleep entity + state | when this person is asleep, for example `sensor.danny_charger_type` at `wireless` |
| Schedule windows | start, end, days of the week, and whether it is a holiday window |

A resident without a schedule does not take part in gate 6: they neither open it nor hold
it shut. The same holds **per day**: somebody with no window on a Tuesday does not take
part on Tuesday. Otherwise a resident with weekend windows only would hold the house back
every weekday morning until they woke up, which is not a schedule but a lock. A resident who is home and asleep while their own window has not opened yet holds
the house back — which is what makes the house wait for the last sleeper on a Saturday.

**Per refrigerant circuit**

| Setting | What it does |
|---|---|
| Indoor units | which `climate.*` hang on this outdoor unit |
| Heat and cool at once | off for an ordinary multi-split: it can only do one duty at a time |
| Conflict policy | who wins when two rooms disagree: priority, who was first, largest deviation, or the season |
| Pause when switching duty | how long everything must be off before the changeover |
| Minimum run before a duty switch | how long a duty must have run before the other may take over |
| Minimum cycle time | how long a unit stays off after stopping; only ever delays starting, never stopping |
| Maximum units at once | the capacity limit of the outdoor unit |

#### When something gets stuck

The mismatch count compares the plan with reality by walking the commands. An appliance the
plan has **no** command for does not appear there — so a deadlock in which nothing is
steered is invisible to that count.

`binary_sensor.*_stuck` watches the other trail. A handful of reasons should resolve by
themselves: waiting on the changeover pause, on the minimum run, on the minimum cycle time,
or on a free slot on the outdoor unit. A zone sitting on one of those longer than the
configured time (fifteen minutes by default) is no longer waiting but stuck, and the sensor
comes on. The attributes say which zones, on what, and for how long.

The same sensor also comes on when a **configured entity cannot be read** — mistyped,
deleted, or temporarily `unavailable`. That fails silently too: the gate leaning on it
closes, the zone does nothing, and that looks like a zone with nothing to do. Which
entities they are is in the `unusable_entities` attribute.

Reasons that may rightly hold for a long time — nobody home, room empty, outside the
temperature window — do not count. Zero minutes switches the sensor off.

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

What the event carries: `zone_id`, `zone_name`, `wanted`, `granted`, `source_id`,
`entity_id`, `hvac_mode`, `temperature` and `reason`.

One automation thereby replaces every separate notification block you had. With the
ordinary `notify` action:

```yaml
alias: Climate: report what was decided
triggers:
  - trigger: event
    event_type: climate_director_decision
actions:
  - action: notify.mobile_app_phone
    data:
      message: >-
        {{ trigger.event.data.zone_name }}: {{ trigger.event.data.hvac_mode }}
        via {{ trigger.event.data.source_id }} ({{ trigger.event.data.reason }})
```

Have a notification script of your own? Call it in the same place:

```yaml
actions:
  - action: script.notify_general_with_menu
    data:
      message: >-
        {{ trigger.event.data.zone_name }} is now on
        {{ trigger.event.data.hvac_mode }}
```

Filter down to what interests you with a condition on `reason`. Reporting only when a room
did not get what it asked for:

```yaml
conditions:
  - condition: template
    value_template: "{{ trigger.event.data.granted == 'neutral' }}"
```


### What you get in Home Assistant

One device per installation, holding:

| Entity | For |
|---|---|
| `sensor.*_last_decision` | How many zones are being served, with the full plan as attributes: every command, every circuit, every deferred action, and which appliances would have been steered |
| `sensor.*_would_command_<entity>` | The mode the director would put this appliance in — one sensor per steered appliance |
| `sensor.*_mismatch` | How many appliances currently sit somewhere other than where the plan wants them. Zero means the director agrees with whatever is steering the house right now |
| `sensor.*_<zone>_source` | Which source serves this zone, with what the zone wanted, what it got and why |
| `binary_sensor.*_<zone>_blocked` | On when a zone got less than it asked for, with the reason as an attribute |
| `binary_sensor.*_stuck` | On when a zone sits on the same waiting reason too long, with the zones and the wait as attributes |
| `switch.*_director` | Master switch; off means nothing is regulated |
| `switch.*_holiday_mode` | Makes every day count as a Saturday, or as its own holiday schedule |
| `switch.*_guest_mode` | Keeps regulating while the residents are away; sleep and the guest window still apply |
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

Every screen ends in a **When you are done here** row, choosing between keeping and
discarding, and every picker carries a **← Back to the main menu** row. So nowhere traps
you. Home Assistant draws exactly one button under a form and lets an integration add no
second one, so a real Back button beside Save does not exist — these rows are what is
possible instead.

Going back always works, even with a field half filled in or left empty. You no longer get
"not all required fields are filled in": the screen lets you go and what you typed is
thrown away. Choose to keep instead, and if something is missing the message points at the
field rather than locking the door.

Nothing is written to the installation until you pick **Save and close** in the main menu
in any case. If something about your configuration stands out, you get that list first,
with the choice of *Save anyway* or *Back to change something*. It is a warning, not a
refusal: an installation may deliberately be unusual, and only you know whether it is.

1. **General settings** — outdoor temperature sensor, where the season comes from, which
   gates you want (awake, schedule), between which hours guest mode applies, and which
   calendars announce a holiday with which keyword.
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
