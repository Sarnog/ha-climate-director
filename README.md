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
| 6b | **Stiltevenster** | het hele huis, alleen bij starten | een zone die al draait | door geen venster in te stellen |
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
- **iedereen die thuis is naar bed gaat.** Dan is de dag voorbij en doet de zone weer mee.
- **het de volgende dag is.** Een besluit van gisteravond hoort vanochtend niet meer te
  gelden, dus de zone doet uiterlijk vanaf middernacht gewoon weer mee.

Uitzetten dat de director zélf doet telt niet mee, anders zou elke zone die hij ooit
uitzet permanent stil komen te staan. De schakelaar `switch.*_override_<zone>` blijft
daarnaast gewoon werken en staat boven dit alles.


#### Twee apparaten die elkaar uitsluiten

Wil je dat een gasketel en een warmtepomp **nooit** tegelijk draaien, vertrouw dat dan niet
aan de buitengrenzen toe. Die sluiten elkaar alleen uit zolang elk getal klopt, en één
achtergebleven waarde is genoeg om ze samen te laten aanslaan — zonder dat er iets van
gemeld wordt, want los van elkaar is er niets mis met beide instellingen.

Onder **Exclusieve groepen** zet je ze bij elkaar. Van de apparaten in één groep draait er
altijd maar één; de rest krijgt `exclusive_group_lost` als reden. Dat is een afgedwongen
regel in plaats van een gelukkige samenloop.

Let op wat een groep betekent: **één** apparaat uit de groep tegelijk. Wil je dat de
gasketel geen enkele airco in de weg zit, maar dat twee airco's op hetzelfde circuit wél
samen mogen koelen, maak dan één groep per paar — gas met de ene airco, gas met de andere —
in plaats van alles in één groep.

Een groep geldt ook voor apparaten die je **zelf** aanzet. Staat er een apparaat met
*automatisch aanzetten* uit in een groep, en komt een ander lid van die groep aan de beurt,
dan gaat het handbediende apparaat uit met reden `exclusive_group_lost` — ook al doen ze
hetzelfde en delen ze geen buitenunit. Zonder die regel zou juist het apparaat dat jij met
de hand bedient de groep straffeloos negeren, en dan is de groep een regel op papier.

De configuratiecontrole meldt het wanneer de buitengrenzen van twee apparaten in dezelfde
groep elkaar overlappen. Dat hoeft geen fout te zijn — de groep vangt het immers op — maar
het betekent dat er bij die temperatuur echt gekozen moet worden, en dat is meestal niet wat
je dacht te hebben ingesteld.

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

#### De override als noodknop

`switch.*_override_<zone>` geeft één zone **volledig** aan jou terug. De director stuurt
die zone dan niets meer — ook geen uit. Wat jij met de hand instelt blijft staan, ongeacht
de buitengrenzen, het seizoen, een openstaand raam of de dode band.

Dat is de bedoeling: het is de noodknop voor gevallen die de regels niet dekken. Het is te
warm binnen, de deur mag niet open, en het systeem wil niet koelen omdat het buiten onder
je koelgrens zit — dan zet je de override aan en regel je het zelf.

De circuitregels blijven wel gelden voor de *andere* kamers: twee binnenunits op één
buitenunit kunnen fysiek niet tegengesteld draaien, en dat verandert niet doordat jij er
één overneemt.

De override vervalt vanzelf zodra iedereen die thuis is naar bed gaat, of zodra het huis
leeg is. Een noodknop hoort niet dagenlang te blijven hangen omdat iemand vergat hem uit te
zetten.

Wil je juist dat een zone **stil blijft**, zet dan het apparaat zelf uit. Dat houdt die
zone stil tot je hem weer aanzet of tot de volgende dag.

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
      entity_id: timer.<jouw_timer>
  - action: climate.set_temperature
    data:
      temperature: 20
      hvac_mode: heat
    target:
      entity_id: <entiteit>
```

En het aflopen van de timer zet alles weer terug:

```yaml
alias: Gasverwarming timer afgelopen
triggers:
  - trigger: event
    event_type: timer.finished
    event_data:
      entity_id: timer.<jouw_timer>
actions:
  - action: climate.turn_off
    target:
      entity_id: <entiteit>
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

#### Vooruit verwarmen en koelen

De enige manier om een leeg huis te laten draaien, en met opzet de enige die je met de hand
moet aanzetten. De zones die je erom vraagt beginnen alvast te werken, zodat het goed is als
je binnenloopt.

**Met een knop.** Elke zone heeft er één: `button.*_<zone>_vooruit`. Zet hem op je dashboard
en druk erop. Hoe lang zo'n druk duurt staat ernaast, in `number.*_vooruitduur` — standaard
een uur, in te stellen van een kwartier tot twee uur. Eén duur voor de hele installatie, dus
je stelt hem één keer in op wat bij je huis past.

**Met de actie**, voor wat niet op een knop past: meerdere zones tegelijk, een afwijkende
duur, of een open raam overbruggen.

```yaml
action: climate_director.precondition
data:
  zone_ids: [<zone>]
  minutes: 45
```

##### Je vraagt niet om verwarmen, je vraagt om aandacht

Dit is het belangrijkste om te begrijpen: **je zegt niet wát er moet gebeuren.** Het verzoek
opent alleen de deur; daarna beslist de integratie precies zoals wanneer je gewoon thuis
bent — de dode band kijkt of het te koud of te warm is, het seizoen en de buitengrens per
bron kiezen het apparaat.

Hetzelfde verzoek geeft dus verschillende uitkomsten:

| Binnen | Buiten | Uitkomst |
| --- | --- | --- |
| 18 °C | 21 °C | verwarmen, via de airco |
| 18 °C | −5 °C | verwarmen, via de gasverwarming |
| 26 °C | 28 °C | koelen |
| 23 °C | 21 °C | **niets** — de kamer ligt al goed |

Die laatste regel is geen tekortkoming. Een verzoek is geen "aanzetten"; ligt de kamer al
goed, dan blijft het apparaat uit.

##### Wat het overslaat, en wat niet

| Blijft gelden | Wordt overgeslagen |
| --- | --- |
| De hoofdschakelaar | *Iemand thuis* |
| Een handmatige override | *Wakker* |
| De dode band | *Rooster* |
| Het seizoen | *Aanwezigheid in de ruimte* |
| De buitengrens **per bron** (die kiest het apparaat) | De buitengrens **per zone** |
| Ramen en deuren (zie hieronder) | Het stiltevenster |
| Circuit, uitsluitende groepen, voorrang | |

Twee rijen verdienen uitleg.

**De buitengrens per zone vervalt.** Die grens beantwoordt de vraag *"mag er bij dit weer
überhaupt geregeld worden"* — een zuinigheidsregel die ervan uitgaat dat er iemand thuis is.
Vraag je er zelf om, dan is dat antwoord al gegeven. Zonder deze uitzondering zit er een gat
tussen je twee grenzen: staat verwarmen op *tot 19 °C buiten* en koelen op *vanaf 24 °C*,
dan doet een verzoek bij 21 °C buiten helemaal niets. De grens **per bron** blijft wel
gelden, want die kiest welk apparaat geschikt is.

**Aanwezigheid wordt overgeslagen, ook per kamer.** Staat een zone op *Ruimte* in plaats van
*Huishouden*, dan werkt vooruit verwarmen daar net zo goed. Vooruit verwarmen staat in de
rangorde vóór alles wat over mensen gaat, en een lege kamer valt daar vanzelf onder — dat is
juist het punt.

##### Ramen en deuren

Een openstaand raam of een openstaande deur **weigert** een verzoek. Stoken tegen de
buitenlucht in is weggegooid geld, dus dat is de standaard.

Maar wie het raam zelf openzette weet dat, en mag zeggen: toch doen.

```yaml
action: climate_director.precondition
data:
  zone_ids: [<zone>]
  minutes: 90
  ignore_openings: true
```

De keuze hoort **bij het verzoek**, niet bij de aanroep: de poort wordt telkens opnieuw
beoordeeld, dus anders sneuvelde het verzoek een minuut later alsnog. Hij vervalt vanzelf
met de teller — het is geen instelling die blijft hangen.

Wordt een verzoek geweigerd, dan gaat de gebeurtenis `climate_director_precondition_refused`
af. Daarin zit alles wat een melding nodig heeft: de zone, de openstaande entiteiten met hun
naam, de kamertemperatuur, de streeftemperatuur, en **twee kant-en-klare zinnen in de taal van
je interface** — één voor de weigering en één voor na de bevestiging. Zie
[Must-have automatiseringen](#must-have-automatiseringen-en-notificaties) voor de blueprint met
een knop *"Toch doen"* eronder.

##### Twee grenzen die je niet kunt vergeten

- **Het verloopt vanzelf.** Er is geen schakelaar die aan kan blijven staan, alleen een
  teller die afloopt. Vraag je langer dan het ingestelde maximum (standaard twee uur), dan
  wordt je verzoek ingekort in plaats van geweigerd — dat geldt ook voor de knop, dus
  `number.*_vooruitduur` kan het maximum van de installatie nooit oprekken. Geen tijd opgeven
  geeft het maximum.
- **Het geldt alleen binnen het venster**, standaard 06:00 tot 23:00. Daarbuiten telt een
  verzoek eenvoudig niet mee, dus een vertypte automatisering kan je 's nachts niet de ketel
  laten aanslaan.

Een lopend verzoek **overleeft een herstart** van Home Assistant. Een verzoek dat intussen
is afgelopen komt bewust niet terug: de tijd liep door terwijl HA weg was.

Bij het aflopen van de teller neemt niets het over: de gewone poorten gelden weer. Ben je
inmiddels thuis, dan draait alles door. Is er niemand thuis, dan gaat alles uit.

Afblazen kan met `climate_director.cancel_precondition`, met of zonder `zone_ids`.

#### Stiltevensters

Uren waarin de director **uit zichzelf niets begint**. Thuiskomen om elf uur 's avonds
terwijl je zo naar bed gaat, hoeft het huis niet te laten opstoken.

Het is een rem op **beginnen**, niet op doorgaan:

- Wat al draait blijft gewoon geregeld, en gaat bij bedtijd uit zoals altijd.
- Zet je zelf iets aan, dan wordt dat opgepakt en doorgeregeld — je kunt dus prima besluiten
  toch nog even op te blijven.
- Wat uit staat blijft uit tot het venster voorbij is.

**Een open roostervenster wint.** Staat het venster van iemand die thuis is open, dan wijkt
de stilte — anders zou een stiltevenster van 21:00 tot 09:00 precies het ochtendritme
afknijpen dat het rooster beschrijft. Wie om vijf uur opstaat heeft dat immers in zijn
rooster gezet omdat het vroeg is. Het rooster van iemand die weg is telt niet mee.

Vensters mogen over middernacht heen lopen en kennen weekdagen, zodat een weekendritme
apart te zetten is. Stel je geen vensters in, dan doet de rem niet mee: de integratie start
dan altijd wanneer de andere poorten dat toestaan.

Onder **Stiltevensters** in het hoofdmenu. Een huishouden dat doordeweeks om negen uur 's
avonds naar bed gaat en in het weekend om elf uur, zet er twee:

| Van | Tot | Dagen |
|---|---|---|
| 21:00 | 09:00 | ma di wo do zo |
| 23:00 | 09:00 | vr za |

#### Geen slaapsensor? Gebruik een knop

De integratie leest de slaapsensor als een **toestand**: hij staat op de slaapstand of hij
staat er niet op. Een `button` of `input_button` kan dat niet zeggen — de status daarvan is
het tijdstip van de laatste druk, niet of je nu slaapt. Zo'n knop is dus niet rechtstreeks
als slaapsensor te gebruiken.

Wat wel werkt is een `input_boolean` die je met een knop omschakelt. Drie stappen:

1. Maak een helper van het type **Schakelaar** (`input_boolean`), bijvoorbeeld
   `input_boolean.<naam>_slaapt`.
2. Kies die bij de bewoner als **Slaapsensor**, met `on` als slaapstand.
3. Laat een slimme knop of een dashboardknop hem omschakelen:

```yaml
alias: Slaapknop <naam>
triggers:
  - trigger: state
    entity_id: input_button.<naam>_slaapknop
actions:
  - action: input_boolean.toggle
    target:
      entity_id: input_boolean.<naam>_slaapt
```

Eén knop voor beide richtingen: 's avonds indrukken zet hem aan, 's ochtends uit. Liever
twee aparte knoppen, of kort en lang indrukken? Dat werkt net zo goed — de integratie kijkt
alleen naar de boolean.

Voor wie wél een sensor heeft die slapen verraadt — een draadloze lader, een
slaapmatje, een bedsensor — is dat nauwkeuriger, want je hoeft er niet aan te denken. Een
knop is de uitweg voor wie zoiets niet heeft, en je kunt ze combineren: maak een
template-boolean die aan staat als de lader óf de knop aan staat.

Laat je de slaapsensor helemaal leeg, dan telt die bewoner nooit als slapend. De
wakker-poort staat dan altijd open, en een zone die je met de hand uitzette komt pas om
middernacht weer vrij in plaats van bij het naar bed gaan.

#### Vakantieschema

Een vakantiedag telt als **zaterdag**: elk rooster in huis wordt als een zaterdagrooster
gelezen, inclusief het wachten op wie er nog slaapt. Wil iemand op vakantie andere uren,
dan vinkt die bij een venster *Dit is een vakantievenster* aan; dat venster vervangt dan
zijn gewone vensters en negeert de dagen van de week.

Het vakantieschema gaat aan met `switch.*_vakantieschema`, of vanzelf zodra er in een van de
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
| `calendar.*` | nee | zet het vakantieschema vanzelf aan; werkt alleen mét trefwoord |
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

Drie combinaties weigert dit scherm bij het opslaan, omdat ze alle drie een zone opleveren
die er wel staat maar nooit iets doet:

- een **streeftemperatuur aan de verkeerde kant van het aanzetpunt** — het apparaat krijgt
  dan een temperatuur waar het niets voor hoeft te doen, wat eruitziet alsof het weigert;
- **koelen dat begint op of onder het punt waar verwarmen begint** — dan vragen de twee
  tegelijk om dezelfde kamer;
- de zone op **de ruimte zelf zonder aanwezigheidssensor**, of een zone die **niet mag
  verwarmen en niet mag koelen** — allebei kan de zone dan per definitie nooit draaien.

Achteraf melden kan ook, en dat gebeurde eerder ook — maar dan zoek je eerst een dag naar
een apparaat dat het niet doet.

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
| Slaapsensor + status | wanneer deze persoon slaapt, bijvoorbeeld `<entiteit>` op de stand die slapen verraadt |
| Slaapsensor telt vanaf / tot | de uren waarin die sensor iets betekent; leeg is de klok rond |
| Roostervensters | begin, eind, dagen van de week, en of het een vakantievenster is |

Een oplaadsensor is niet altijd een bedtijd. Vul je bij een bewoner **Slaapsensor telt
vanaf/tot** in, dan telt die sensor alleen binnen die uren; daarbuiten is een oplader gewoon
een oplader. Laat je ze leeg, dan geldt hij de klok rond — en legt iemand zijn telefoon om
drie uur 's middags neer, dan telt dat als slapen.

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
| Maximum aantal units tegelijk | de capaciteitsgrens van de buitenunit. Alles wat draait telt mee — ook een kamer die je zelf hebt overgenomen en een handbediend apparaat |

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

#### Als een apparaat niet te bereiken is

Een apparaat dat `unavailable` of `unknown` is laat niets omvallen. De director behandelt
onbereikbaarheid als een toestand, niet als een ongeluk: zo'n bron telt gewoon niet mee als
kandidaat, en de volgende bron op voorkeur neemt het over.

Concreet, met een kamer die een warmtepomp of airco als eerste bron heeft en de
gasverwarming als tweede: valt `<entiteit>` van de airco weg, dan neemt het gas het over. De
kamer wordt gewoon warm. Je hoeft daar niets voor in te stellen — het is voldoende dat beide
apparaten als bron onder dezelfde zone staan, met de goedkoopste op de laagste voorkeur.

En precies daar zit het gevaar. **Een vangnet dat werkt, voel je niet.** De kamer komt op
temperatuur, alles lijkt in orde, en pas op de energierekening merk je dat er wekenlang op
gas gestookt is — duurder dan elektrisch — omdat niemand de kapotte airco gerepareerd
heeft.

Daarom is er per zone een melder: `binary_sensor.*_op_reserve`. Die gaat aan zodra een zone
draait op een bron die níét de eerste keus was, omdat de eerste keus onbereikbaar is. In de
attributen staat wat er overgeslagen is en wat het overgenomen heeft:

| Attribuut | Betekenis |
| --- | --- |
| `unreachable` | De bron-ID's die overgeslagen zijn omdat ze niet te bereiken waren |
| `serving` | De bron-ID die het nu doet |
| `zone` | De zone waar het over gaat |

De melder maakt onderscheid tussen een storing en een normale keuze. Hij gaat **niet** aan
als de airco koelt terwijl de gasverwarming stilstaat — die kan nu eenmaal niet koelen. Hij
gaat ook niet aan voor een bron die buiten zijn buitentemperatuurvenster valt: die stond
toch al stil, dat is precies waar dat venster voor is. En hij gaat niet aan voor een bron
die mínder voorrang heeft dan wat er nu draait. Alleen wat écht aan de beurt was en niet
opnam, telt.

Blijft de eerste keus lang weg, dan gaat ook `binary_sensor.*_vastgelopen` aan, met de
onleesbare entiteit in `unusable_entities`. De twee melders vullen elkaar aan: de ene zegt
*er is uitgeweken*, de andere zegt *er is iets niet te lezen*. Een uitgewerkte melding voor
allebei staat bij
[Must-have automatiseringen](#must-have-automatiseringen-en-notificaties).

#### Wat voor verwarmingssysteem heb je

Onder **Instellingen** staat **Verwarmingssysteem**, met twee keuzes. Die instelling
verandert niets aan wie er mag draaien — dat blijft aan de poorten en de voorrang. Hij legt
vast wat je installatie *is*, zodat de configuratiecontrole kan waarschuwen als je invulling
er niet bij past.

##### Wanneer is een systeem gezoneerd

Een systeem is gezoneerd als het de warmte per deel van het huis kan **afsluiten of apart
opwekken**. Dat kan op twee manieren:

- **Zoneventielen** — motorische kleppen (of aparte zonepompen) die de toevoer naar een
  groep radiatoren of een vloerverwarmingsgroep open- en dichtzetten, elk met een eigen
  thermostaat die om warmte vraagt.
- **Meerdere warmtebronnen** — bijvoorbeeld een ketel voor beneden en een warmtepomp of
  airco voor boven.

**Slimme radiatorknoppen alleen zijn géén gezoneerd systeem.** Een knop smoort de doorstroming
van één radiator, maar het huis heeft nog steeds één circuit en één warmtebron die voor
iedereen tegelijk aan of uit gaat. Draai je de knoppen in de slaapkamer dicht, dan stookt de
ketel gewoon door voor de rest van het huis. Kies dan **Centraal**.

##### De twee keuzes

| Keuze | Wat het betekent | Zo vul je het in |
| --- | --- | --- |
| **Centraal** | Eén warmtebron voor het hele huis. Aanzetten voor één kamer verwarmt de rest mee. Denk aan één slimme thermostaat, met of zonder radiatorknoppen. | Zet **dezelfde** thermostaat als bron onder elke zone |
| **Per zone** | Elk deel van het huis kan zijn warmte apart krijgen, via een zoneventiel of een eigen warmtebron. | Geef elke zone zijn **eigen** klep of apparaat als bron; is er één gedeelde ketel, zet die er dan bij als generator |

Eén ketel met drie zoneventielen is dus **per zone**, ook al is er maar één brander: de
ventielen bepalen wie warmte krijgt. Eén ketel met vijftien radiatorknoppen is **centraal**.

##### Zo modelleer je een cv met kleppen of knoppen

Elke kamer een zone, en de `climate`-entiteit van die kamer als bron met rol *alleen
verwarmen*. Dat werkt met elke integratie die per ruimte zo'n entiteit levert. Zet ze
**niet** in een circuit: dat begrip gaat over een gedeelde compressor van airco's, en een
ketel heeft er geen.

Wat ze wél delen is het apparaat dat het water warm maakt. Draait dat systeem zijn eigen
brander zodra een kraan erom vraagt, dan hoef je niets extra's in te stellen. Is de
warmtebron een aparte entiteit die geschakeld moet worden, zet die dan onder **Gedeelde
warmtebronnen**. Hij draait zolang een kamer die hij bedient verwarmd wordt, en stopt zodra
dat er geen meer is. Zonder vast setpoint volgt hij het warmste doel van de kamers die
vragen — het koudste nemen zou de kamer die het hardst om warmte vraagt nooit laten halen
wat hij vroeg.

##### Wat de controle wel en niet meldt

De controle telt niet zomaar gedeelde apparaten. Eén ketel onder tien zones is geen fout.
De waarschuwing komt pas als twee of meer kamers **uitsluitend** op hetzelfde apparaat zijn
aangewezen en niets van zichzelf hebben: dan valt er per kamer niets meer te regelen.
Heeft een kamer een eigen airco én de gasverwarming als reserve, dan is dat gewoon gezoneerd
en zwijgt de controle. Andersom net zo: staat de keuze op *centraal* terwijl elke kamer zijn
eigen bron heeft, dan is het systeem gezoneerd.

Het blijft een **waarschuwing, geen blokkade**. De director regelt gewoon door.

Had je de integratie al draaien voordat deze instelling bestond? Dan wordt de keuze afgeleid
uit wat er al stond: deelt een warmtebron twee of meer zones, dan is het centraal. Je krijgt
dus geen waarschuwing voor een keuze die je nooit gemaakt hebt.

##### Wat er gebeurt bij een gedeelde bron

Een apparaat krijgt altijd **één** opdracht, ook als het onder vijf zones hangt. Vraagt de
ene kamer warmte en de andere niets, dan gaat de thermostaat aan — vraag wint van stilte,
want een gesloten systeem heeft geen manier om dat te scheiden. Vragen er meerdere tegelijk,
dan volgt het apparaat de zone met de meeste voorrang, net zoals een gewone thermostaat de
leidende kamer volgt.

Wil je dat een kamer níét meeverwarmt, dan heb je geen instelling nodig maar een
zoneventiel — en daarmee wordt het systeem gezoneerd.

### Dode band

Aan- en uitschakelen gebeuren op twee verschillende temperaturen. Je stelt een aanpunt in
plus de breedte van de band:

- verwarmen start bij `binnen <= aanpunt` en stopt bij `binnen >= aanpunt + band`;
- koelen start bij `binnen >= aanpunt` en stopt bij `binnen <= aanpunt - band`.

Twee getallen per stand in plaats van vier losse minimum-/maximumdrempels, en de band is een
bewuste keuze in plaats van een toevalligheid.

### Must-have automatiseringen en notificaties

Climate Director stuurt zelf geen berichten. Waar een melding heen gaat, hoe hij klinkt en
of hij 's nachts mag komen, is niets waar een klimaatregelaar over hoort te beslissen — en
het is precies het deel dat bij iedereen anders is. In plaats daarvan zet de integratie
gebeurtenissen en melders klaar waar je je eigen automatisering aan hangt.

Drie daarvan zou ik niet overslaan. De eerste twee melden dingen die **stil** misgaan: je
huis wordt gewoon warm, en zonder melding merk je maanden niets.

| Wat | Waarom je het niet zonder kunt |
| --- | --- |
| **1. Vastgelopen en op reserve** | Een zone die blijft wachten, of die op een duurder apparaat draait omdat het eerste onbereikbaar is. Beide zijn van buiten onzichtbaar |
| **2. Geweigerd vooruit-verzoek** | Je drukte op een knop en er gebeurde niets. Zonder melding weet je niet dát het geweigerd is, laat staan waarom |
| **3. Wat er besloten is** | Niet noodzakelijk, wel het handigste stuk gereedschap bij het instellen en bij een schaduwrun |

#### Kant-en-klaar: importeer de blueprints

Alle drie staan als blueprint in deze repo. Importeren gaat via **Instellingen → Automatiseringen
en scènes → Blueprints → Blueprint importeren**, met een van deze links:

| Blueprint | Link om te importeren |
| --- | --- |
| Bewaking | `https://github.com/Sarnog/ha-climate-director/blob/main/blueprints/automation/climate_director/monitoring.yaml` |
| Geweigerd vooruit-verzoek | `https://github.com/Sarnog/ha-climate-director/blob/main/blueprints/automation/climate_director/precondition_refused.yaml` |
| Wat er besloten is | `https://github.com/Sarnog/ha-climate-director/blob/main/blueprints/automation/climate_director/decisions.yaml` |

> **Importeren alleen is niet genoeg.** Een blueprint is een sjabloon; er luistert pas iets
> zodra je er een automatisering van maakt. Doe dat meteen na het importeren — kies de
> blueprint, vul je entiteiten in, en sla op.

Zolang er niemand naar een geweigerd vooruit-verzoek luistert, staat daar een
reparatiemelding over in Home Assistant. Die verdwijnt vanzelf zodra er een automatisering
op die gebeurtenis staat, of die nu uit de blueprint komt of van jezelf.

De teksten van de tweede blueprint komen uit de integratie zelf en staan dus in de taal van
je interface, met Engels als terugval. De andere twee hebben hun berichten als invulveld, met
een Engels sjabloon als vertrekpunt — die schrijf je in je eigen woorden.

De blueprints zijn een **vertrekpunt en geen keurslijf**: je kunt ze openmaken en aanpassen.
Wil je liever zelf schrijven, dan staat hieronder precies wat je nodig hebt.

#### 1. Vastgelopen en op reserve

Twee melders, één automatisering. `binary_sensor.*_vastgelopen` gaat aan als een zone te
lang op dezelfde wachtreden staat of als een ingestelde entiteit niet te lezen is;
`binary_sensor.*_<zone>_op_reserve` als een zone op een tweede keus draait.

```yaml
alias: Klimaat - bewaking
mode: queued
max: 10
triggers:
  - trigger: state
    id: vastgelopen
    entity_id: binary_sensor.<installatie>_vastgelopen
    from: "off"
    to: "on"
    for: "00:02:00"
  - trigger: state
    id: reserve
    entity_id:
      - binary_sensor.<installatie>_<zone>_op_reserve
    from: "off"
    to: "on"
    for: "00:05:00"
  - trigger: state
    id: hersteld
    entity_id:
      - binary_sensor.<installatie>_vastgelopen
      - binary_sensor.<installatie>_<zone>_op_reserve
    from: "on"
    to: "off"
actions:
  - choose:
      - conditions: [{condition: trigger, id: vastgelopen}]
        sequence:
          - action: notify.mobile_app_<telefoon>
            data:
              title: Klimaat loopt vast
              message: >-
                {{ state_attr(trigger.entity_id, 'zones') | join(', ') }} wacht te lang.
                {{ state_attr(trigger.entity_id, 'reasons') }}
      - conditions: [{condition: trigger, id: reserve}]
        sequence:
          - action: notify.mobile_app_<telefoon>
            data:
              title: Klimaat wijkt uit
              message: >-
                {{ state_attr(trigger.entity_id, 'zone') }} draait op
                {{ state_attr(trigger.entity_id, 'serving') }}, want
                {{ state_attr(trigger.entity_id, 'unreachable') | join(', ') }}
                is niet te bereiken.
      - conditions: [{condition: trigger, id: hersteld}]
        sequence:
          - action: notify.mobile_app_<telefoon>
            data:
              message: Klimaat is weer in orde.
```

De wachttijden zijn het belangrijkste eraan: een apparaat dat één keer knippert bij een
herstart is geen storing. En meld ook het herstel — anders weet je nooit of het probleem nog
speelt, en wordt de melding iets wat je wegklikt.

#### 2. Een geweigerd vooruit-verzoek, met een knop om door te zetten

Staat er een raam open, dan weigert een vooruit-verzoek. De gebeurtenis
`climate_director_precondition_refused` vertelt welke zone en welk raam. Hang er een melding
aan met een knop die hetzelfde verzoek nog eens doet, nu met `ignore_openings: true`.

```yaml
alias: Klimaat - vooruit verwarmen geweigerd
mode: queued
triggers:
  - trigger: event
    event_type: climate_director_precondition_refused
actions:
  - variables:
      zone_id: "{{ trigger.event.data.zone_id }}"
  - action: notify.mobile_app_<telefoon>
    data:
      title: Vooruit verwarmen geweigerd
      message: >-
        {{ trigger.event.data.zone }}: {{ trigger.event.data.openings | join(', ') }}
        staat open.
      data:
        actions:
          - action: "KLIMAAT_TOCH_{{ zone_id }}"
            title: Toch doen
```

En de tweede helft, die op de knop reageert:

```yaml
alias: Klimaat - toch vooruit verwarmen
triggers:
  - trigger: event
    event_type: mobile_app_notification_action
    event_data: {}
conditions:
  - condition: template
    value_template: "{{ trigger.event.data.action.startswith('KLIMAAT_TOCH_') }}"
actions:
  - action: climate_director.precondition
    data:
      zone_ids: >-
        {{ [ trigger.event.data.action | replace('KLIMAAT_TOCH_', '') ] }}
      minutes: 60
      ignore_openings: true
```

Dit is dezelfde vorm als een gewone bevestigingsvraag: melden, een knop tonen, en op de knop
handelen. De keuze geldt alleen voor dat ene verzoek en vervalt met de teller.

#### 3. Wat er besloten is

Na elke beslissing komt er een gebeurtenis `climate_director_decision` op de bus, met de
zone, de gekozen bron, de stand, de temperatuur en de reden. Redenen zijn stabiele
identifiers (`circuit_conflict_lost`, `everyone_asleep`, `short_cycle_protection`, …), zodat
je erop kunt filteren.

In het event zitten: `zone_id`, `zone_name`, `wanted`, `granted`, `source_id`, `entity_id`,
`hvac_mode`, `temperature` en `reason`.

```yaml
alias: Klimaat - melden wat er besloten is
triggers:
  - trigger: event
    event_type: climate_director_decision
actions:
  - action: notify.mobile_app_<telefoon>
    data:
      message: >-
        {{ trigger.event.data.zone_name }}: {{ trigger.event.data.hvac_mode }}
        via {{ trigger.event.data.source_id }} ({{ trigger.event.data.reason }})
```

Eén automatisering vervangt daarmee al je losse notificatieblokken. Tijdens een schaduwrun
is dit het handigste dat je kunt aanzetten; als alles eenmaal draait wil je hem waarschijnlijk
filteren op de redenen die je echt wilt weten.

### Wat je in Home Assistant krijgt

Eén device per installatie, met daaronder:

| Entiteit | Waarvoor |
|---|---|
| `sensor.*_laatste_beslissing` | Hoeveel zones bediend worden, met het volledige plan als attributen: elk commando, elk circuit, elke uitgestelde actie, en welke apparaten er aangestuurd zouden zijn |
| `sensor.*_zou_<entiteit>_aansturen` | De stand waarin de director dit apparaat zou zetten — één sensor per aangestuurd apparaat. Staat er geen opdracht, dan leest hij `left_alone` (met opzet met rust gelaten) of `unreachable` (niet te bereiken), met de precieze reden als attribuut |
| `sensor.*_afwijkingen` | Hoeveel apparaten er nú anders staan dan het plan wil. Nul betekent dat de director het eens is met wat het huis op dit moment stuurt |
| `sensor.*_bron_<zone>` | Welke bron deze zone bedient, met wat de zone wilde, wat hij kreeg en waarom |
| `binary_sensor.*_<zone>_geblokkeerd` | Aan als een zone minder kreeg dan hij vroeg, met de eerste reden én alle dichte poorten (`closed_gates`) als attributen |
| `binary_sensor.*_<zone>_op_reserve` | Aan als een zone draait op een reserve-apparaat omdat de eerste keus onbereikbaar is, met de overgeslagen bron als attribuut |
| `binary_sensor.*_vastgelopen` | Aan als een zone te lang op dezelfde wachtreden staat, met de zones en de wachttijd als attribuut |
| `switch.*_director` | Hoofdschakelaar; uit betekent dat er niets geregeld wordt |
| `switch.*_vakantieschema` | Laat elke dag als zaterdag tellen, of als het eigen vakantierooster |
| `switch.*_gastenmodus` | Blijft regelen terwijl de bewoners weg zijn; slaap en het gastenvenster blijven gelden |
| `switch.*_override_<zone>` | Geeft één zone volledig terug aan jou: de director stuurt hem niets meer, ook geen uit |
| `number.*_prioriteit_<zone>` | Hoe sterk deze zone een gedeelde buitenunit claimt; lager wint. Vanuit een automatisering te wijzigen |
| `number.*_vooruitduur` | Hoe lang één druk op een vooruit-knop duurt; een kwartier tot twee uur |
| `button.*_<zone>_vooruit` | Laat deze zone vooruit verwarmen of koelen — zie [Vooruit verwarmen en koelen](#vooruit-verwarmen-en-koelen) |

Daarnaast is er een downloadbare diagnose met de configuratie, de laatst gelezen
momentopname en het laatste plan. Met die drie is elke beslissing exact na te spelen.

### Acties

| Actie | Waarvoor |
| --- | --- |
| `climate_director.evaluate` | Nu opnieuw laten beslissen |
| `climate_director.precondition` | Vooruit verwarmen of koelen aanzetten — zie [Vooruit verwarmen en koelen](#vooruit-verwarmen-en-koelen) |
| `climate_director.cancel_precondition` | Een lopend vooruit-verzoek afblazen |

`climate_director.evaluate` laat de director nu opnieuw beslissen, in plaats van te wachten
tot een gevolgde entiteit uit zichzelf verandert. Handig tijdens het inrichten en bij het
napluizen van een afwijking. In schaduwmodus voert die actie nog steeds niets uit — hij
herberekent alleen. Zonder `entry_id` worden alle installaties herberekend.

### Configuratiecontrole

Klopt er iets structureel niet — een zone zonder bruikbare bron, twee bronnen op dezelfde
entiteit, een buitenvenster dat niets toelaat, dezelfde binnenunit aan twee buitenunits —
dan verschijnt dat als reparatiemelding in Home Assistant. De zones die wél kloppen worden
ondertussen gewoon geregeld; één stukke zone legt de installatie niet stil. De volledige
lijst staat in de diagnose.

Er wordt ook geklaagd over instellingen die stilletjes niets doen. Twee daarvan zijn
makkelijk te maken:

- **stiltevensters die samen de klok rondgaan.** Een stiltevenster is de omgekeerde van een
  rooster: het zegt wanneer er níets mag beginnen. Blijft er op een dag minder dan een
  kwartier over en heeft niemand een rooster dat de stilte kan verslaan, dan kan het huis
  uit zichzelf niets meer beginnen;
- **een omschakelpauze op een buitenunit die verwarmen en koelen tegelijk aankan.** Zo'n
  unit wisselt nooit van taak, dus die pauze en de minimale looptijd ervoor doen er niets.
  De minimale cyclustijd en de capaciteitsgrens blijven wél gelden.

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

**Vereist:** Home Assistant **2025.3** of nieuwer. De integratie voegt haar
entiteiten toe met `AddConfigEntryEntitiesCallback` (bestaat sinds 2025.3) en
gebruikt `entry.runtime_data` met getypeerde config entries (sinds 2024.6).

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

De testset heeft twee helften. De ene beslist op nagebouwde momentopnamen — duizenden
willekeurige installaties, en simulaties die maand na maand doorlopen met wisselend weer,
mensen die komen en gaan en apparaten die wegvallen. Die maanden zijn **gesimuleerde tijd**
aan een nagebouwde klok en zeggen niets over draaiuren in een echt huis. De andere zet een échte Home Assistant
in het geheugen op, met deze integratie als custom component erin: de config entry wordt
opgezet, de platforms komen omhoog, de entiteiten en acties worden aangemaakt, en de
klimaatapparaten schrijven hun stand terug. Daarvoor is verder niets nodig — het
`homeassistant`-pakket staat al in `requirements_test.txt`.

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
| 6b | **Quiet window** | the whole house, on starting only | a zone already running | by setting no window |
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
- **everybody who is home turns in.** The day is over then, and the zone joins in again.
- **it is the next day.** Last night's decision should not still hold this morning, so from
  midnight at the latest the zone simply joins in again.

Switching off that the director does itself does not count, or every zone it ever switches
off would fall silent for good. The `switch.*_<zone>_override` switch keeps working
alongside this and outranks all of it.


#### Two appliances that rule each other out

Want a gas boiler and a heat pump to run **never** at the same time? Do not entrust that to
the outdoor bounds. Those rule each other out only while every number is right, and one
value left behind is enough to have them fire together — with nothing reported, because
taken separately there is nothing wrong with either setting.

Under **Exclusive groups** you put them together. Of the appliances in one group only one
ever runs; the rest get `exclusive_group_lost` as their reason. That is an enforced rule
rather than a happy coincidence.

Mind what a group means: **one** appliance from the group at a time. If you want the gas
boiler to stay out of every air conditioner's way, while two air conditioners on the same
circuit may still cool together, make one group per pair — gas with the one, gas with the
other — rather than putting everything in a single group.

A group also binds appliances you switch on **yourself**. With an appliance whose *start
automatically* is off sitting in a group, and another member of that group getting its turn,
the hand-operated one goes off with reason `exclusive_group_lost` — even when they do the
same thing and share no outdoor unit. Without that rule it would be precisely the appliance
you operate by hand that ignores the group with impunity, leaving the group a rule on paper.

The configuration check reports it when the outdoor bounds of two appliances in the same
group overlap. That need not be a mistake — the group catches it, after all — but it does
mean a real choice has to be made at that temperature, and that is usually not what you
thought you had set up.

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

#### The override as an emergency handle

`switch.*_<zone>_override` hands one zone over to you **completely**. The director then
sends that zone nothing at all — an off included. What you set by hand stays, whatever the
outdoor bounds, the season, an open window or the dead band would otherwise say.

That is the point: it is the emergency handle for cases the rules do not cover. It is too
warm inside, the door may not be opened, and the system refuses to cool because it is below
your cooling bound outside — then you switch the override on and see to it yourself.

The circuit rules do still apply to the *other* rooms: two indoor units on one outdoor unit
cannot physically run opposing duties, and that does not change because you took one of
them over.

The override lapses by itself once everybody who is home turns in, or as soon as the house
is empty. An emergency handle should not hang about for days because somebody forgot to
release it.

Want a zone to **stay silent** instead? Switch the appliance off yourself. That holds the
zone still until you switch it back on or until the next day.

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
      entity_id: timer.<your_timer>
  - action: climate.set_temperature
    data:
      temperature: 20
      hvac_mode: heat
    target:
      entity_id: <entiteit>
```

And the timer running out puts everything back:

```yaml
alias: Gas heating timer finished
triggers:
  - trigger: event
    event_type: timer.finished
    event_data:
      entity_id: timer.<your_timer>
actions:
  - action: climate.turn_off
    target:
      entity_id: <entiteit>
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
hand. The zones you ask for start working ahead of time, so it is right when you walk in.

**With a button.** Every zone has one: `button.*_<zone>_pre_condition`. Put it on your
dashboard and press it. How long such a press lasts sits beside it, in
`number.*_pre_conditioning_duration` — an hour by default, settable from a quarter of an hour
to two hours. One duration for the whole installation, so you set it once to what suits your
house.

**With the action**, for what does not fit on a button: several zones at once, a different
duration, or overriding an open window.

```yaml
action: climate_director.precondition
data:
  zone_ids: [<zone>]
  minutes: 45
```

##### You are not asking for heat, you are asking for attention

This is the thing to understand: **you do not say what should happen.** The request only
opens the door; after that the integration decides exactly as it would while you are home —
the dead band checks whether it is too cold or too warm, the season and the outdoor window
per source pick the appliance.

So the same request gives different outcomes:

| Indoors | Outdoors | Outcome |
| --- | --- | --- |
| 18 °C | 21 °C | heating, through the air conditioner |
| 18 °C | −5 °C | heating, through the gas heating |
| 26 °C | 28 °C | cooling |
| 23 °C | 21 °C | **nothing** — the room is already fine |

That last row is no shortcoming. A request is not "switch on"; if the room already sits
right, the appliance stays off.

##### What it skips, and what it does not

| Still applies | Skipped |
| --- | --- |
| The master switch | *Somebody home* |
| A manual override | *Awake* |
| The dead band | *Schedule* |
| The season | *Presence in the room* |
| The outdoor window **per source** (it picks the appliance) | The outdoor window **per zone** |
| Windows and doors (see below) | The quiet window |
| Circuit, exclusive groups, priorities | |

Two rows deserve explaining.

**The outdoor window per zone lapses.** That window answers *"may anything be regulated in
this weather at all"* — a thrift rule assuming somebody is home. If you ask for it yourself,
that answer is already given. Without this exception a gap sits between your two windows:
with heating set to *up to 19 °C outside* and cooling to *from 24 °C*, a request at 21 °C
outside does nothing at all. The window **per source** does still apply, since it picks
which appliance is suitable.

**Presence is skipped, per room as well.** If a zone is set to *Room* rather than
*Household*, pre-conditioning works there just as well. It sits ahead of everything about
people in the order of precedence, and an empty room falls under that by itself — which is
precisely the point.

##### Windows and doors

An open window or door **refuses** a request. Heating against the outside air is money
thrown away, so that is the default.

But whoever opened the window knows that, and may say: do it anyway.

```yaml
action: climate_director.precondition
data:
  zone_ids: [<zone>]
  minutes: 90
  ignore_openings: true
```

The choice belongs **to the request** rather than to the call: the gate is judged afresh
every time, so otherwise the request would die a minute later after all. It lapses with the
timer — it is not a setting that lingers.

If a request is refused, the event `climate_director_precondition_refused` fires. It carries
everything a notification needs: the zone, the open entities by name, the room temperature,
the target, and **two ready-made sentences in the language of your interface** — one for the
refusal and one for after the confirmation. See
[Must-have automations](#must-have-automations-and-notifications) for the blueprint with a
*"Do it anyway"* button under it.

##### Two limits you cannot forget

- **It expires by itself.** There is no switch that can stay on, only a timer running down.
  Ask for longer than the configured maximum (two hours by default) and your request is
  shortened rather than refused — the button included, so
  `number.*_pre_conditioning_duration` can never stretch the installation's own maximum.
  Naming no time gives you the maximum.
- **It applies only inside the window**, 06:00 to 23:00 by default. Outside it a request
  simply does not count, so a mistyped automation cannot fire the boiler at night.

A running request **survives a restart** of Home Assistant. A request that ran out
meanwhile deliberately does not come back: time ran on while HA was away.

When the timer runs out nothing takes over: the ordinary gates apply again. If you are home
by then everything carries on. If nobody is home everything switches off.

Call it off with `climate_director.cancel_precondition`, with or without `zone_ids`.

#### Quiet windows

Hours in which the director **starts nothing of its own accord**. Coming home at eleven at
night when you are about to turn in need not fire the boiler.

It is a brake on **starting**, not on continuing:

- Whatever already runs stays regulated, and goes off at bedtime as usual.
- Switch something on yourself and it is picked up and carried on — so you can perfectly
  well decide to stay up after all.
- Whatever is off stays off until the window has passed.

**An open schedule window wins.** With the window of somebody who is home open, the quiet
yields — otherwise a quiet window from 21:00 to 09:00 would pinch off the very morning
rhythm the schedule describes. Whoever gets up at five put that in their schedule because it
is early, after all. The schedule of somebody who is out does not count.

Windows may cross midnight and carry weekdays, so a weekend rhythm can be set apart. Set no
windows and the brake does not apply: the integration then starts whenever the other gates
allow it.

Under **Quiet windows** in the main menu. A household turning in at nine on weekdays and at
eleven at weekends sets two:

| From | Until | Days |
|---|---|---|
| 21:00 | 09:00 | Mon Tue Wed Thu Sun |
| 23:00 | 09:00 | Fri Sat |

#### No sleep sensor? Use a button

The integration reads the sleep sensor as a **state**: it either sits on the sleeping state
or it does not. A `button` or `input_button` cannot say that — its state is the moment of
the last press, not whether you are asleep now. Such a button therefore cannot serve as a
sleep sensor directly.

What does work is an `input_boolean` you toggle with a button. Three steps:

1. Create a helper of type **Toggle** (`input_boolean`), say
   `input_boolean.<name>_asleep`.
2. Pick it as the resident's **Sleep sensor**, with `on` as the sleeping state.
3. Have a smart button or a dashboard button toggle it:

```yaml
alias: <name>'s sleep button
triggers:
  - trigger: state
    entity_id: input_button.<name>_sleep_button
actions:
  - action: input_boolean.toggle
    target:
      entity_id: input_boolean.<name>_asleep
```

One button for both directions: pressing it at night switches it on, in the morning off.
Prefer two separate buttons, or a short and a long press? That works just as well — the
integration only looks at the boolean.

For anyone who does have a sensor that betrays sleeping — a wireless charger, a sleep mat,
a bed sensor — that is more accurate, since you never have to remember it. A button is the
way out for those without one, and you can combine them: make a template boolean that is on
when either the charger or the button is on.

Leave the sleep sensor empty altogether and that resident never counts as asleep. The awake
gate then stays open at all times, and a zone you switched off by hand comes free at
midnight rather than at bedtime.

#### Holiday schedule

A holiday counts as a **Saturday**: every schedule in the house is read as a Saturday's,
including waiting for whoever is still asleep. Want different hours on holiday? Tick *This
is a holiday window* on a window; it then replaces that resident's ordinary windows and
ignores the days of the week.

The holiday schedule goes on with `switch.*_holiday_schedule`, or by itself as soon as one of the
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
| `calendar.*` | no | switches the holiday schedule on by itself; works only with a keyword |
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

Three combinations are refused by this screen on saving, since all three produce a zone that
is there but never does anything:

- a **target on the wrong side of the switch-on point** — the appliance is then set to a
  temperature it need do nothing for, which looks like it is refusing;
- **cooling that starts at or below where heating starts** — the two then ask for the same
  room at once;
- the zone set to **the room itself without a presence sensor**, or a zone that **may
  neither heat nor cool** — either way the zone can never run by definition.

Reporting it afterwards works too, and that is what used to happen — but then you spend a
day first looking for an appliance that will not do its job.

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
| Sleep sensor + state | when this person is asleep, for example `<entity>` at the state that betrays sleeping |
| Sleep sensor counts from / until | the hours in which that sensor means anything; empty is around the clock |
| Schedule windows | start, end, days of the week, and whether it is a holiday window |

A charging sensor is not always a bedtime. Fill in **Sleep sensor counts from/until** for a
resident and that sensor counts only within those hours; outside them a charger is just a
charger. Leave them empty and it counts around the clock — and somebody putting their phone
down at three in the afternoon counts as sleeping.

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
| Maximum units at once | the capacity limit of the outdoor unit. Everything running counts — a room you took over yourself and a hand-operated appliance included |

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

#### When an appliance cannot be reached

An appliance that is `unavailable` or `unknown` breaks nothing. The director treats
unreachability as a state rather than an accident: such a source simply does not count as a
candidate, and the next source by preference takes over.

Concretely, with a room that has a heat pump or air conditioner as its first source and the
gas heating as its second: if `<entity>` of the air conditioner drops out, the gas takes
over. The room simply gets warm. There is nothing to configure for this — it is enough that
both appliances sit as sources under the same zone, with the cheapest on the lowest
preference number.

And that is exactly where the danger sits. **A safety net that works is one you do not
feel.** The room reaches temperature, everything looks fine, and you notice on the energy
bill that it has been burning gas for weeks — dearer than electricity — because nobody
fixed the broken air conditioner.

Hence a sensor per zone: `binary_sensor.*_on_stand_in`. It comes on as soon as a zone runs
on a source that was not the first choice, because the first choice cannot be reached. The
attributes say what was skipped and what took over:

| Attribute | Meaning |
| --- | --- |
| `unreachable` | The source ids skipped because they could not be reached |
| `serving` | The source id doing the work now |
| `zone` | The zone this is about |

The sensor tells a fault apart from an ordinary choice. It does **not** come on when the
air conditioner cools while the gas heating sits idle — that one cannot cool. Nor does it
come on for a source outside its outdoor-temperature window: that one was standing still
anyway, which is precisely what the window is for. And it does not come on for a source
ranked below whatever is running now. Only what was genuinely up next and did not answer
counts.

If the first choice stays away for long, `binary_sensor.*_stuck` comes on as well, with the
unreadable entity in `unusable_entities`. The two sensors complement each other: one says
*something fell back*, the other says *something cannot be read*. A worked notification for
both sits under
[Must-have automations](#must-have-automations-and-notifications).

#### What kind of heating system do you have

Under **Settings** sits **Heating system**, with two choices. The setting changes nothing
about who may run — that stays with the gates and the priorities. It records what your
installation *is*, so the configuration check can warn you when your setup does not match.

##### When is a system zoned

A system is zoned when it can **shut off or separately generate** heat per part of the
house. That happens in one of two ways:

- **Zone valves** — motorised valves (or separate zone pumps) that open and close the flow
  to a group of radiators or an underfloor loop, each with its own thermostat calling for
  heat.
- **Several heat sources** — a boiler downstairs and a heat pump or air conditioner
  upstairs, for instance.

**Smart radiator valves on their own are not a zoned system.** A knob throttles the flow
through one radiator, but the house still has one circuit and one heat source that goes on
or off for everybody at once. Close the knobs in the bedroom and the boiler keeps firing for
the rest of the house. Choose **Central** in that case.

##### The two choices

| Choice | What it means | How you fill it in |
| --- | --- | --- |
| **Central** | One heat source for the whole house. Switching on for one room warms the rest along with it. Think of a single smart thermostat, with or without radiator valves. | Put the **same** thermostat as a source under every zone |
| **Per zone** | Each part of the house can get its heat separately, through a zone valve or a heat source of its own. | Give each zone its **own** valve or appliance as a source; if there is one shared boiler, add it as a generator |

So one boiler with three zone valves is **per zone**, even though there is only one burner:
the valves decide who gets heat. One boiler with fifteen radiator knobs is **central**.

##### Modelling a boiler with valves or knobs

One zone per room, and that room's `climate` entity as its source with role *heating only*.
That works with any integration providing such an entity per room. Do **not** put them in a
circuit: that idea is about a shared compressor in air conditioners, and a boiler has none.

What they do share is the appliance heating the water. If that system fires its own burner
as soon as a valve asks, there is nothing extra to configure. If the heat source is a
separate entity that has to be switched, put it under **Shared heat sources**. It runs while
a room it serves is being heated, and stops once none is. Without a fixed setpoint it
follows the warmest target among the rooms asking — taking the coldest would never let the
room asking hardest reach what it asked for.

##### What the check does and does not report

The check does not simply count shared appliances. One boiler under ten zones is no fault.
The warning comes only when two or more rooms depend on the same appliance and **nothing**
else: then there is nothing left to settle per room. A room with its own air conditioner
plus the gas heating as a stand-in is zoned, and the check stays quiet. The other way round
just as much: if the choice says *central* while every room has its own source, the system
is zoned.

It stays a **warning, not a block**. The director carries on regulating.

Were you already running the integration before this setting existed? Then the choice is
inferred from what was already there: if a heat source spans two or more zones, it is
central. So you never get a warning about a choice you never made.

##### What happens with a shared source

An appliance always gets **one** command, even when it hangs under five zones. If one room
asks for heat and another does not, the thermostat comes on — demand beats silence, since a
closed system has no way to separate the two. If several ask at once, the appliance follows
the zone with the most claim, just as an ordinary thermostat follows the leading room.

Want a room to stay out of it? That needs a zone valve rather than a setting — and with
that, the system becomes zoned.

### Dead band

Switching on and switching off happen at two different temperatures. You set a switch-on
point plus the width of the band:

- heating starts at `indoor <= switch-on` and stops at `indoor >= switch-on + band`;
- cooling starts at `indoor >= switch-on` and stops at `indoor <= switch-on - band`.

Two numbers per mode instead of four separate minimum/maximum thresholds, and the band is a
deliberate choice rather than an accident.

### Must-have automations and notifications

Climate Director sends no messages of its own. Where a notification goes, how it sounds and
whether it may arrive at night is nothing a climate controller should decide — and it is
exactly the part that differs for everybody. Instead the integration lays out events and
sensors for your own automation to hang on.

Three of them I would not skip. The first two report things that fail **silently**: your
house simply gets warm, and without a notification you notice nothing for months.

| What | Why you cannot do without it |
| --- | --- |
| **1. Stuck and on stand-in** | A zone that keeps waiting, or that runs on a dearer appliance because the first cannot be reached. Both are invisible from the outside |
| **2. A refused pre-conditioning request** | You pressed a button and nothing happened. Without a notification you do not know it was refused, let alone why |
| **3. What was decided** | Not essential, but the handiest tool while configuring and during a shadow run |

#### Ready-made: import the blueprints

All three ship as blueprints in this repository. Import them through **Settings → Automations
and scenes → Blueprints → Import blueprint**, with one of these links:

| Blueprint | Link to import |
| --- | --- |
| Monitoring | `https://github.com/Sarnog/ha-climate-director/blob/main/blueprints/automation/climate_director/monitoring.yaml` |
| Refused pre-conditioning | `https://github.com/Sarnog/ha-climate-director/blob/main/blueprints/automation/climate_director/precondition_refused.yaml` |
| What was decided | `https://github.com/Sarnog/ha-climate-director/blob/main/blueprints/automation/climate_director/decisions.yaml` |

> **Importing alone is not enough.** A blueprint is a template; nothing listens until you
> build an automation from it. Do that right after importing — pick the blueprint, fill in
> your entities, and save.

For as long as nobody is listening for a refused pre-conditioning request, Home Assistant
carries a repair notice about it. That disappears by itself once an automation stands on
that event, whether it came from the blueprint or from you.

The texts of the second blueprint come from the integration itself, so they are in the
language of your interface, with English as the fallback. The other two carry their messages
as an input, with an English template as a starting point — write those in your own words.

The blueprints are a **starting point rather than a straitjacket**: you can open them and
change them. If you would rather write your own, everything you need is below.

#### 1. Stuck and on stand-in

Two sensors, one automation. `binary_sensor.*_stuck` comes on when a zone sits on the same
waiting reason too long or when a configured entity cannot be read;
`binary_sensor.*_<zone>_on_stand_in` when a zone runs on a second choice.

```yaml
alias: Climate - monitoring
mode: queued
max: 10
triggers:
  - trigger: state
    id: stuck
    entity_id: binary_sensor.<installation>_stuck
    from: "off"
    to: "on"
    for: "00:02:00"
  - trigger: state
    id: stand_in
    entity_id:
      - binary_sensor.<installation>_<zone>_on_stand_in
    from: "off"
    to: "on"
    for: "00:05:00"
  - trigger: state
    id: recovered
    entity_id:
      - binary_sensor.<installation>_stuck
      - binary_sensor.<installation>_<zone>_on_stand_in
    from: "on"
    to: "off"
actions:
  - choose:
      - conditions: [{condition: trigger, id: stuck}]
        sequence:
          - action: notify.mobile_app_<phone>
            data:
              title: Climate is stuck
              message: >-
                {{ state_attr(trigger.entity_id, 'zones') | join(', ') }} is waiting too
                long. {{ state_attr(trigger.entity_id, 'reasons') }}
      - conditions: [{condition: trigger, id: stand_in}]
        sequence:
          - action: notify.mobile_app_<phone>
            data:
              title: Climate falling back
              message: >-
                {{ state_attr(trigger.entity_id, 'zone') }} runs on
                {{ state_attr(trigger.entity_id, 'serving') }}, because
                {{ state_attr(trigger.entity_id, 'unreachable') | join(', ') }}
                cannot be reached.
      - conditions: [{condition: trigger, id: recovered}]
        sequence:
          - action: notify.mobile_app_<phone>
            data:
              message: Climate is back to normal.
```

The waiting times are the important part: an appliance that blinks once during a restart is
not a fault. And report the recovery too — otherwise you never know whether the problem
still stands, and the notification becomes something you swipe away.

#### 2. A refused pre-conditioning request, with a button to push through

With a window open, a pre-conditioning request is refused. The event
`climate_director_precondition_refused` says which zone and which window. Hang a
notification on it with a button that repeats the same request, now with
`ignore_openings: true`.

```yaml
alias: Climate - pre-conditioning refused
mode: queued
triggers:
  - trigger: event
    event_type: climate_director_precondition_refused
actions:
  - variables:
      zone_id: "{{ trigger.event.data.zone_id }}"
  - action: notify.mobile_app_<phone>
    data:
      title: Pre-conditioning refused
      message: >-
        {{ trigger.event.data.zone }}: {{ trigger.event.data.openings | join(', ') }}
        is open.
      data:
        actions:
          - action: "CLIMATE_ANYWAY_{{ zone_id }}"
            title: Do it anyway
```

And the second half, acting on the button:

```yaml
alias: Climate - pre-condition anyway
triggers:
  - trigger: event
    event_type: mobile_app_notification_action
    event_data: {}
conditions:
  - condition: template
    value_template: "{{ trigger.event.data.action.startswith('CLIMATE_ANYWAY_') }}"
actions:
  - action: climate_director.precondition
    data:
      zone_ids: >-
        {{ [ trigger.event.data.action | replace('CLIMATE_ANYWAY_', '') ] }}
      minutes: 60
      ignore_openings: true
```

This is the same shape as an ordinary confirmation question: report, show a button, act on
the button. The choice applies to that one request and lapses with the timer.

#### 3. What was decided

After every decision an event `climate_director_decision` lands on the bus, carrying the
zone, the chosen source, the mode, the temperature and the reason. Reasons are stable
identifiers (`circuit_conflict_lost`, `everyone_asleep`, `short_cycle_protection`, …), so
you can filter on them.

The event holds: `zone_id`, `zone_name`, `wanted`, `granted`, `source_id`, `entity_id`,
`hvac_mode`, `temperature` and `reason`.

```yaml
alias: Climate - report what was decided
triggers:
  - trigger: event
    event_type: climate_director_decision
actions:
  - action: notify.mobile_app_<phone>
    data:
      message: >-
        {{ trigger.event.data.zone_name }}: {{ trigger.event.data.hvac_mode }}
        through {{ trigger.event.data.source_id }} ({{ trigger.event.data.reason }})
```

One automation thereby replaces all your separate notification blocks. During a shadow run
this is the handiest thing you can switch on; once everything runs you will probably want to
filter it down to the reasons you actually care about.

### What you get in Home Assistant

One device per installation, holding:

| Entity | For |
|---|---|
| `sensor.*_last_decision` | How many zones are being served, with the full plan as attributes: every command, every circuit, every deferred action, and which appliances would have been steered |
| `sensor.*_would_command_<entity>` | The mode the director would put this appliance in — one sensor per steered appliance. With no command it reads `left_alone` (deliberately left alone) or `unreachable` (cannot be reached), with the exact reason as an attribute |
| `sensor.*_mismatch` | How many appliances currently sit somewhere other than where the plan wants them. Zero means the director agrees with whatever is steering the house right now |
| `sensor.*_<zone>_source` | Which source serves this zone, with what the zone wanted, what it got and why |
| `binary_sensor.*_<zone>_blocked` | On when a zone got less than it asked for, with the first reason and every shut gate (`closed_gates`) as attributes |
| `binary_sensor.*_<zone>_on_stand_in` | On when a zone runs on a stand-in appliance because its first choice is unreachable, with the skipped source as an attribute |
| `binary_sensor.*_stuck` | On when a zone sits on the same waiting reason too long, with the zones and the wait as attributes |
| `switch.*_director` | Master switch; off means nothing is regulated |
| `switch.*_holiday_schedule` | Makes every day count as a Saturday, or as its own holiday schedule |
| `switch.*_guest_mode` | Keeps regulating while the residents are away; sleep and the guest window still apply |
| `switch.*_<zone>_override` | Hands one zone over to you completely: the director sends it nothing, an off included |
| `number.*_<zone>_priority` | How strongly this zone claims a shared outdoor unit; lower wins. Settable from an automation |
| `number.*_pre_conditioning_duration` | How long one press of a pre-conditioning button lasts; a quarter of an hour to two hours |
| `button.*_<zone>_pre_condition` | Warms or cools this zone ahead of time — see [Pre-conditioning](#pre-conditioning) |

There is also a downloadable diagnostics export holding the configuration, the last
snapshot read and the last plan. With those three, any decision is exactly reproducible.

### Actions

| Action | What for |
| --- | --- |
| `climate_director.evaluate` | Decide again right now |
| `climate_director.precondition` | Start pre-conditioning — see [Pre-conditioning](#pre-conditioning) |
| `climate_director.cancel_precondition` | Call a running request off |

`climate_director.evaluate` makes the director decide again right now, instead of waiting
for a tracked entity to change of its own accord. Useful while setting up and while chasing
down a difference. In shadow mode that action still executes nothing — it only recomputes.
Without an `entry_id`, every installation is recomputed.

### Configuration check

If something is structurally wrong — a zone with no usable source, two sources on the same
entity, an outdoor window that admits nothing, the same indoor unit on two outdoor units —
it shows up as a repair notice in Home Assistant. The zones that are sound carry on being
regulated meanwhile; one broken zone does not stop the installation. The full list is in the
diagnostics.

Settings that quietly do nothing are reported too. Two of those are easy to make:

- **quiet windows that together go round the clock.** A quiet window is the inverse of a
  schedule: it says when nothing may begin. If under a quarter of an hour is left on a day
  and nobody has a schedule that can beat the quiet, the house can no longer start anything
  of its own accord;
- **a switch pause on an outdoor unit that can heat and cool at once.** Such a unit never
  switches duty, so that pause and the minimum run before it do nothing. The minimum cycle
  time and the capacity limit do still apply.

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

**Requires:** Home Assistant **2025.3** or newer. The integration adds its
entities through `AddConfigEntryEntitiesCallback` (available since 2025.3) and
uses `entry.runtime_data` with typed config entries (since 2024.6).

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

The test set has two halves. One decides on rebuilt snapshots — thousands of random
installations, and simulations running month after month with changing weather, people
coming and going and appliances dropping out. Those months are **simulated time** on a
rebuilt clock and say nothing about running hours in a real house. The other stands up a real Home Assistant in
memory with this integration in it as a custom component: the config entry is set up, the
platforms come up, the entities and actions are created, and the climate appliances write
their state back. Nothing else is needed for that — the `homeassistant` package is already
in `requirements_test.txt`.

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
