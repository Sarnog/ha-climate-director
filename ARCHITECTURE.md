# ARCHITECTURE.md

## NL

Technisch ontwerpdocument voor wie aan de code werkt (geen gebruikershandleiding —
dat is [`README.md`](README.md)). Elke laag heeft precies één verantwoordelijkheid.

**Eenheden:** de engine en de opgeslagen configuratie rekenen in graden Celsius
— dat is de bewuste keuze (beslissing 3 van 2026-08-25: de eenheid van Home
Assistant volgen, niet de engine er een tweede stelsel bij geven). De
koppelingslaag is de enige plek die omrekent: de coordinator leest
HA-temperaturen om naar Celsius, de applier zet setpoints terug naar de eenheid
van de gebruiker, het formulier toont en leest in diezelfde eenheid, en de
sensorattributen en het `climate_director_decision`-event publiceren in de
eenheid van de gebruiker (het event met een veld `temperature_unit` erbij).
Een bron wordt gelezen in de eenheid die hij zélf meldt: `unit_of_measurement`
bij een sensor, `temperature_unit` bij een weersbron, en pas anders in het
systeemstelsel. De uitgaande kant — sensorattributen en het event — rondt af
op één decimaal, in beide stelsels; de engine en de applier rekenen
ongeafgerond verder.
**De diagnose blijft Celsius**: dat is een ontwikkelaarsdump, geen
gebruikersweergave.

**Inventarisatielijst "elke tekst voor de gebruiker noemt zijn eenheid"**
(ronde 11, G1): een volgende ronde kan aan deze lijst zíén of hij compleet is
in plaats van het te moeten hopen. Elke zin hieronder zet Celsius om met
`display_temperature` — afgerond, met de eenheid erachter:

- `coordinator._wanted` — de reparatiemelding `command_not_taking`;
- `engine/models.py` `target_outside_band` — de placeholders blijven Celsius in
  de engine; `problems.readable` rekent `start` en `target` om. Wélke
  placeholder bij welke `Problem`-code een temperatuur is staat op één plek:
  `problems.TEMPERATURE_PLACEHOLDERS`;
- `coordinator._refusal_data` — de zin die met een vooruit-verzoek meegaat en
  via de blueprint op de telefoon belandt (`precondition_confirmed`,
  `_satisfied`, `_idle`), in alle zes talen.

De sensorattributen en het `climate_director_decision`-event gebruiken
`rounded_from_celsius` (één decimaal, machineleesbaar); de diagnose blijft
Celsius. Die twee horen niet in deze lijst: het ene is geen zin, het andere
geen gebruikersweergave.

### De ankers — lees dit eerst

Een uitspraak in deze engine hangt altijd aan één ding, en welk ding dat is, is
een ontwerpbesluit. Waar dat besluit niet opgeschreven stond, is het in vier
achtereenvolgende reparatierondes telkens één stap opgeschoven — smal, dan te
breed, dan weer terug. Deze zes ankers staan daarom hier, vóór alle modules.
Wijk er niet van af zonder ze hier eerst te wijzigen.

1. **Een lopend vooruit-verzoek** is één begrip in de hele engine:
   `world.preconditioning(zone_id)`. Het passeert álles behalve de
   hoofdschakelaar, een override, en een openstaande opening waarvoor niemand
   "toch doen" heeft gezegd. Er is geen tijdvenster: een handmatig verzoek gaat
   altijd boven de automatisering, ongeacht het uur, voor de volledige
   `max_precondition`. De begrenzing is de looptijd van het verzoek zelf plus de
   bevestiging bij een openstaande deur — hetzelfde principe als: wie laat
   opblijft, houdt zijn verwarming.
2. **Een onleesbare buitentemperatuur** weigert een taak alleen als díe taak zelf
   een begrensd venster moet passeren — op de zone, of op een bron die deze taak
   kan leveren. Vensters van bronnen die de taak niet leveren tellen niet mee:
   dan valt er wél iets te kiezen.
3. **"Al verstuurd"** betekent: deze exacte `(stand, setpoint)` is werkelijk
   uitgevoerd én er is sindsdien geen uit-commando geweest. Een uit-commando wist
   de notitie, want een apparaat dat uitgaat mag zijn setpoint vergeten.
4. **Een uit-commando verklaart precies één waarneming.** De notitie vervalt
   zodra die waarneming binnen is, zodra het apparaat op eigen kracht weer een
   actieve stand meldt, of na het venster. De klok is het vangnet, niet het anker.
5. **De openingsrust hangt aan het apparaat**, niet aan de reden van het vorige
   commando: een collapse kan die reden overschrijven. Hij staat in
   `Plan.opening_rest_until`, geldt voor élk apparaat zonder circuit dat
   werkelijk draaide toen de stop kwam — een gedeelde warmtebron inbegrepen — en
   is een vaste `OPENING_MIN_REST` van drie minuten, gerekend vanaf de stop.
   Direct na een herstart is er geen vorig plan: een gewone bron die de wereld
   als draaiend kent rust dan nog steeds (`_was_running` leest de wereld), maar
   een gedeelde warmtebron rust niet, want zijn stop telt alleen met een vorig
   plan dat zegt welke zone werkelijk warmte kreeg (`_received_heat`).
   Bewust geen instelling: één knop minder om verkeerd te zetten, en drie minuten
   is veilig voor elke brander.
6. **De hoofdschakelaar uit** betekent: de director laat alles los en stuurt
   niets, ook geen `off` — net als een override. Wie alles uit wil, zet het zelf
   uit; de director laat het dan staan.

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
config_flow.py         wizard; schrijft één dict in entry.options
      │
      ▼
engine/serialise.py    dict → dataclasses (puur, vergevingsgezind)
      │
      ▼
Home Assistant (entiteitstoestanden, klokgebeurtenissen)
      │
      ▼
  coordinator          verzamelt toestanden, ontdubbelt, serialiseert
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
│  diff.py        Plan vs werkelijkheid → wat er echt moet         │
│  serialise.py   dict ↔ dataclasses                               │
└──────────────────────────────────────────────────────────────────┘
      │
      ▼
  applier              voert het verschil uit, of in schaduwmodus niet
      │
      ▼
  entiteiten + event   sensor / binary_sensor / switch / button / number
                       + diagnostics
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

Een configuratie zonder bewoners slaat de poorten óver bewoners over - die zouden nooit
kunnen slagen. De kamerpoort blijft daar wél gelden: die gaat over de ruimte, niet over
wie er in het huis is. Een opening zonder
tijdstempel blokkeert direct: opschorten is de onschadelijke richting om fout in te
zitten, en weigeren te handelen op een onbekende leeftijd zou een openstaande kamer
blijven verwarmen.

Daarnaast staat hier `house_wide_blocked()`: de apparaten uit
`DirectorConfig.house_wide_openings` die stil moeten vallen zodra wélke opening in de
installatie dan ook openstaat. Bewust zónder het `affects()`-filter — deze lijst bestaat
juist voor het apparaat dat het hele huis bedient, en dan valt niet uit te leggen dat de
voordeur wel telt en het slaapkamerraam niet. De instelling hangt aan het apparaat en
niet aan de opening: zo hoeft de ketel niet bij elke deur opnieuw aangevinkt te worden,
en telt een raam dat er later bij komt vanzelf mee. Leeg geeft een lege verzameling, dus
een installatie die dit niet gebruikt merkt er niets van.

Bij een herstart na een openingsstop remt `opening_rest_until()` het weer aangaan van
elk apparaat **zonder circuit** — en dat is bij dit ontwerp per definitie de gasketel:
het apparaat wacht `OPENING_MIN_REST` (drie minuten) vanaf de stop, met een
`Deferral` (`SHORT_CYCLE_PROTECTION`) waar de coordinator vanzelf op terugkomt. De stop
zelf wordt nooit uitgesteld, en een vooruit-verzoek waarop iemand uitdrukkelijk "toch
doen" zei passeert de rem, precies zoals het de poort zelf passeert.

### hysteresis.py — moet het

Bepaalt de gevraagde taak uit de binnentemperatuur, het seizoen en het
buitentemperatuurvenster. Krijgt de *draaiende* taak mee; dat is wat de dode band laat
werken. Het aanpunt telt als bereikt (`<=` / `>=`), het uitpunt als gepasseerd (`<` /
`>`) — waren beide inclusief, dan zou een band van nul een taak nooit laten stoppen.

Vragen verwarmen en koelen tegelijk (overlappende setpoints, dus een
configuratiefout), dan houdt de draaiende taak de zone; anders wint de grootste
afwijking. In beide gevallen pendelt de zone niet.

Vraagt de zone niets, dan zegt de reden wélk soort niets: `satisfied` als de kamer
voorbij de verre rand van de band ligt, `within_deadband` als hij erbinnen ligt en wacht
tot het aanpunt weer gehaald wordt. Dat onderscheid beantwoordt de vraag die gebruikers
stellen: het is 20,5 en het aanpunt staat op 20, waarom slaat hij niet aan?

### sources.py — waarmee

Kiest per zone en taak het apparaat: geschiktheid (rol), dan beschikbaarheid, dan
voorkeur (`priority`, met `source_id` als tie-break zodat de uitkomst deterministisch
is).

Daarbovenop ligt de **dode band op de buitentemperatuur**. De grens tussen een
gasketel en een warmtepomp is een getal, en het weer schommelt daaromheen — zonder
band wisselde de bron acht keer per dag. De bron die vorige ronde werkelijk leverde
mag daarom doorlopen tot een band voorbij zijn venster. Alleen die bron, alleen buiten
zijn venster: ligt hij er gewoon in, dan beslist de voorkeur weer, zodat een uitwijking
naar een tweede keus terugschuift zodra de eerste keus er weer is.

`select()` neemt ook de huisbreed stilgezette apparaten mee (`blocked`) en laat die als
kandidaat vallen — inclusief de vasthoudgreep van de dode band, want wat stil moet staan
mag ook niet doorlopen. Dat gebeurt hier en niet pas bij het commando: zou het plan zo'n
bron toch toewijzen, dan noemt `sensor.…_bron_<zone>` een apparaat dat vervolgens uitgaat.
De zone kijkt zo netjes door naar zijn volgende bron, en heeft hij die niet, dan komt hij
op neutraal uit met `opening_open_elsewhere` als reden in plaats van het misleidende
`no_source_available`.

### constraints.py — wat mag tegelijk

De circuitregel:

> Zij **F** de actieve taak van een circuit. Elke binnenunit op dat circuit staat in
> **F ∪ {`off`, `fan_only`}**.

Volgorde van afhandeling:

1. **Vergrendeling door units die blijven staan.** Draait er een unit op het circuit
   die de director deze ronde niet wegschakelt, dan is de taak van het circuit al
   bepaald en kan niets dat overrulen — ook de timers hieronder niet, want er valt dan
   niets te wisselen. Dat zijn er drie soorten: een unit die in geen enkele zone staat,
   een unit in een overgedragen zone, en een draaiende unit in een zone waarvan de
   binnentemperatuur niet te lezen is. Staan er twee taken tegelijk vast — met een
   afstandsbediening en een override kan dat — dan is er geen taak die dit circuit
   veilig kan draaien en krijgt niemand iets toegekend.
2. **Conflictbeleid** (`priority`, `first_come`, `demand`, `season_lock`) kiest de taak
   als zones het oneens zijn. Elk beleid dat niet tot een keuze komt valt terug op
   prioriteit.
3. **Minimale looptijd** houdt de huidige taak vast als er te kort geleden gewisseld is.
   Ontbreekt de tijdstempel, dan gaat de wissel door: de installatie bevriezen op een
   onbekende waarde is erger dan iets te vroeg wisselen. Ligt de taak vast (stap 1), dan
   slaat deze timer over.
4. **Wisselpauze** stopt eerst de oude taak en start de nieuwe pas na een `Deferral`.
5. **Capaciteitsgrens** snoeit de winnaars. Elke unit die blijft draaien telt mee, niet
   alleen de units die in geen enkele zone staan: ook een overgedragen zone en een
   handbediend apparaat bezetten een plek op de buitenunit. De grens gaat over wat de
   director erbij zet — staat er al meer te draaien dan het ding aankan, dan doet hij er
   niets bovenop en gaat hij er ook niet dwars voor liggen.
6. **Kortcyclusbescherming** houdt een start tegen van een unit die net gestopt is —
   alleen starten, nooit stoppen.

### decide.py — het geheel

De enige ingang, en het enige punt waar besloten wordt. Levert een `Plan`: gewenste
eindtoestanden, geen handelingen.

Twee eigenschappen die de rest van het systeem dragen:

- **Elke beheerde bron krijgt een commando of een reden om er geen te krijgen.** Wie
  niet gekozen is wordt expliciet uitgezet; dát maakt "twee apparaten werken tegen
  elkaar in" onbereikbaar in plaats van onwaarschijnlijk. Drie apparaten krijgen met
  opzet niets — een onbereikbaar apparaat, een apparaat in een overgedragen zone, en een
  draaiend apparaat in een zone zonder leesbare binnentemperatuur — en staan als
  `UntouchedSource` in het plan. Precies díé twee laatste blijven doordraaien, en worden
  daarom als vergrendeling aan `constraints.py` doorgegeven: zonder dat kon de director
  de tegengestelde taak op dezelfde buitenunit zetten of er een unit bij aanzetten.
- **Stoppen staat vóór starten** in de commandovolgorde. Zou je op een circuit dat van
  taak wisselt de nieuwe taak eerst starten, dan delen twee bedrijven één compressor
  zolang de service calls onderweg zijn.

De **hoofdschakelaar is een noodknop**, geen uitknop (besloten na reviewronde 4, H1):
met `MASTER_DISABLED` stuurt de director helemaal niets — ook geen `off`. Elk beheerd
apparaat staat dan als `UntouchedSource` in het plan, precies zoals een overgedragen
zone. Wie de ketel daarna met de hand aanzet houdt hem aan; zou de director hem tóch
uitzetten, dan was de noodknop een slot. De handleiding ("uit = de director doet
helemaal niets") klopt daarmee weer, en de schakelaar is bruikbaar als handvat in het
migratiedraaiboek.

Elke zone krijgt precies één `Reason`, ook als hij niets doet, zodat een unit die
uitgaat altijd kan zeggen waaróm — "de warmtepomp bedient deze zone" leest anders dan
"er is niets te doen".

Een **exclusieve groep** wordt bewaard als bron-ID's maar werkt op apparaten: elk
bron-ID wordt eerst naar zijn `entity_id` vertaald. Anders ontsnapte een gedeelde ketel
via het bron-ID van een andere kamer. Twee kamers die om hetzelfde apparaat vragen zijn
daarbij geen tegenstanders — dat is één apparaat dat draait.

Staan een handbediend apparaat én zijn groepstegenstander op hetzelfde circuit, dan
bezet het handbediende apparaat zelf de plek (`_keeps_claiming` telt hem mee) en krijgt
de tegenstander blijvend `CIRCUIT_AT_CAPACITY`; per beslissing 2 van 2026-08-25 blijft
dat zo. Een exclusieve groep waarvan de leden dezelfde buitenunit delen kan zichzelf dus
klemzetten — gebruik groepen alleen voor apparaten die geen buitenunit delen.

In de bronkeuze stopt de huisbrede stop de **zone**, niet alleen het apparaat: is de
eerste keus van de zone een huisbreed stilgezet apparaat, dan weigert de zone met
`OPENING_OPEN_ELSEWHERE` in plaats van stilletjes door te schuiven naar de tweede keus —
anders stond de airco elektrisch te verwarmen omdat er elders een deur openstaat, en dat
merk je pas op de energierekening. Alleen een écht onbereikbare eerste keus telt nog als
uitwijking (`passed_over`).

Ná `_collapse_shared` staat `_stop_blocked`: het vangnet dat een huisbreed stilgezet
apparaat (zie `gates.house_wide_blocked`) hoe dan ook op `off` zet. De bronkeuze weigert
de zone al, dus in de gewone gang van zaken doet dit niets; het bestaat voor de paden die
buiten die keuze omgaan — een gedeelde ketel die zijn commando van een andere zone kreeg,
en de generator, die helemaal geen bronkeuze doorloopt. Eén uitzondering gaat erdoorheen:
een vooruit-verzoek waarbij iemand uitdrukkelijk "toch doen" zei, precies zoals dat langs
de gewone raampoort gaat. Wat de director met rust laat blijft met rust: een overgedragen
zone en een handbediende bron krijgen geen commando en komen hier dus niet langs.

Rond de bronkeuze en de generatorcommando's zit de openingsrusttijd voor elk apparaat
zonder circuit: een start binnen `OPENING_MIN_REST` ná de stop wordt vastgehouden met een
`Deferral` (`SHORT_CYCLE_PROTECTION`), precies zoals een circuit dat doet. Alleen
herstarts wachten, nooit de stop zelf.

### plan.py — uitvoer

`UnitCommand`, `ZoneDecision`, `CircuitDecision`, `UntouchedSource`, `Deferral` en `Reason`.
`Reason` is een `StrEnum` met stabiele identifiers in plaats van vrije tekst, zodat de Home
Assistant-laag ze kan vertalen en gebruikers erop kunnen filteren in hun eigen
automatiseringen. Een `Deferral` vertelt de coordinator wanneer er opnieuw beslist moet
worden, zodat een plan dat op een timer wacht vanzelf hervat.

Elk beheerd apparaat staat in precies één van twee lijsten: het krijgt een `UnitCommand`, of
het staat als `UntouchedSource` genoteerd met de reden waarom niet — overgedragen zone,
handbediende bron, of niet te bereiken. Niets aansturen is een uitkomst en geen leegte, en
zonder dat onderscheid was "de director laat dit met rust" van buiten hetzelfde als "de
director doet niets".

`WAITING_REASONS` noemt de redenen die uit zichzelf horen op te lossen; blijft een zone er
lang op staan, dan is dat een klem en gaat de vastloopmelder aan. Alle drie zijn het timers
van seconden tot minuten. Een volle buitenunit hoort er níét bij: die loopt pas leeg als een
andere kamer ophoudt met vragen, en dat kan uren duren zonder dat er iets mis is. De kamer
die zijn plek niet krijgt staat gewoon als geblokkeerd te boek.

### serialise.py — opslag

De enige plek waar het JSON-achtige formaat van een config entry naar dataclasses vertaald
wordt, en terug. Lezen is bewust vergevingsgezind: onbekende sleutels worden genegeerd,
ontbrekende sleutels vallen terug op hun standaard, en rommel in een lijst wordt
overgeslagen. Een entry overleeft zo een versie waarin een veld bijkomt of verdwijnt, in
plaats van bij het opstarten om te vallen. Wat structureel niet klopt komt uit
`validate()`, niet uit een exception hier.

Booleans worden expliciet níét als getal gelezen: `True` is in Python een `int`, en een
prioriteit van `True` zou stilletjes 1 worden.

### diff.py — wat moet er echt gebeuren

Het plan beschrijft eindtoestanden; deze pure functie bepaalt welke daarvan nog niet
kloppen. Een plan dat overeenkomt met de werkelijkheid levert nul service calls op — dat is
wat de director ervan weerhoudt bij elke toestandswijziging van elke gevolgde entiteit
dezelfde aanroep opnieuw te doen. Een unit die uitgezet wordt krijgt nooit een setpoint
mee: die behoudt gewoon wat hij had, en een aanroep die niets zichtbaars verandert is
ruis.

### coordinator.py — de koppeling

Doet precies drie dingen: entiteiten uitlezen tot één `WorldState`, `decide()` daar een
`Plan` van laten maken, en zorgen dat er opnieuw besloten wordt zodra dat zin heeft. Bevat
zelf geen besliskunde; staat er ooit een `if` over temperaturen in dat bestand, dan hoort
die in `engine/`.

Drie dingen zijn er subtiel aan:

- **Alles in lokale, tijdzonebewuste tijd.** Roostervensters worden in lokale tijd gelezen,
  terwijl tijdstempels van entiteiten in UTC binnenkomen. Die twee mengen zou de leeftijd
  van een openstaande deur uren verschuiven.
- **Circuitgeschiedenis komt uit waarnemingen, niet uit het vorige plan.** Een unit die
  iemand met de afstandsbediening omzet verandert de taak van een circuit net zo goed als
  de director, en de minimale-looptijdtimer hoort dat te respecteren.
- **Eén event per zone, en alleen bij verandering.** Er wordt herrekend bij elke
  toestandswijziging van elke gevolgde entiteit; elke keer vuren zou elke automatisering
  die erop luistert verzuipen.

### applier.py — uitvoeren

Beslist niets. Vraagt `diff.py` wat er moet gebeuren en zet dat om in service calls, of
logt het alleen in schaduwmodus. `climate.set_temperature` draagt de `hvac_mode` mee, zodat
een unit die zowel een stand als een setpoint nodig heeft met één aanroep klaar is — twee
aanroepen zouden hem kort op de nieuwe stand met het oude setpoint laten draaien.

Faalt een aanroep, dan hangt de reactie af van wat er faalde. Een mislukte **stop** breekt
de aanname waar de rest van het plan op rust: de starts erachteraan zouden landen bovenop
een apparaat dat had moeten stoppen, precies de combinatie die dit ontwerp onbereikbaar
hoort te maken. Dan wordt de rest van het plan afgebroken. Een mislukte **start** is
onschuldig — er gebeurt alleen minder dan gepland — en de rest gaat gewoon door.

### config_flow.py — de wizard

Bevat geen kennis van klimaatregels, alleen van formulieren. De installatie wordt in een
lokale kopie opgebouwd en pas bij "Opslaan en sluiten" weggeschreven. Halverwege opslaan
zou de entry herladen terwijl de gebruiker nog aan het bewerken is, en de grond wegtrekken
onder de flow waar hij in staat.

Een verlopen cursor (bijvoorbeeld naar een zone die net verwijderd is) stuurt terug naar
het menu in plaats van een uitzondering te gooien: een config flow die crasht laat een half
opgebouwde installatie achter zonder weg terug.

### Entiteiten

Eén device per installatie. De sensoren zijn bewust uitgebreid: in schaduwmodus zijn zij de
enige zichtbare uitkomst, en het hele punt van die modus is kunnen zien wat er gebeurd zou
zijn.

Daarnaast staat er een tweede soort entiteit onder hetzelfde device, en het verschil is
principieel: de schakelaars, de `number`-entiteiten en de knoppen zijn **invoer**, geen
uitvoer. Ze zijn bedieningstoestand, geen configuratie — ze herstellen zichzelf na een
herstart, schrijven hun stand terug naar de coordinator en negeren updates van de
coordinator, want anders zou de uitkomst van een beslissing de invoer van de volgende
overschrijven.

De platforms worden vóór de eerste beslissing opgezet, zodat een uitgeschakelde
hoofdschakelaar niet één ronde lang aan lijkt te staan.

### texts.py — vertaalde zinnen naar buiten

De integratie stuurt zelf geen berichten; waar een melding heen gaat hoort een gebruiker te
bepalen. De **tekst** komt wel hiervandaan: een blueprint kan niet vertalen, en een half
Engelse melding op een Nederlands scherm leest als een fout.

Deze module zoekt een zin op in de taal van de interface en valt terug op Engels — twee keer
zelfs, want een vertaling kan ontbreken én uit de pas lopen met de code. De zinnen wonen
onder `exceptions` in `strings.json`, omdat Home Assistant het hoogste niveau van dat bestand
tegen een vast schema valideert.

### blueprints/ — de must-have automatiseringen, kant-en-klaar

Drie blueprints, buiten `custom_components/` en dus geen onderdeel van de integratie zelf:
bewaking, een geweigerd vooruit-verzoek met bevestigingsknop, en de besluitmelder. Ze worden
bewust **niet** automatisch geïnstalleerd — dat kan technisch wel, maar het is geen gebaand
pad voor een custom integratie, en er moet daarna alsnog een automatisering van gemaakt
worden.

De vindbaarheid wordt in plaats daarvan opgelost met een reparatiemelding: zodra niemand naar
`climate_director_precondition_refused` luistert, staat dat in Home Assistant. Meetbaar via
`hass.bus.async_listeners()`, herbeoordeeld zodra Home Assistant klaar is met starten en bij
elke herlaadbeurt van de automatiseringen.

### problems.py — configuratiefouten zichtbaar maken

`validate()` vindt structurele fouten, maar die kwamen alleen in de diagnose terecht. Deze
module zet ze om in een reparatiemelding in Home Assistant zelf, en haalt die weer weg zodra
de configuratie klopt.

De melding is een waarschuwing, geen fout: `decide()` blijft elke gezonde zone regelen, dus
een gebrekkige configuratie verslechtert de installatie zonder hem stil te leggen. Dat is
precies waarom hij zichtbaar moet zijn - van buiten ziet een fout in de configuratie er
hetzelfde uit als "de director besluit niets".

Er zijn er vijf, met dezelfde reden om te bestaan. Naast de configuratiefout: een eenmalige
melding over taken die alleen handbediend geleverd kunnen worden, en een melding over
ingestelde entiteiten die vijf minuten lang niet te lezen zijn. Die laatste is geen fout in
de configuratie maar in de werkelijkheid — een lege batterij, een apparaat van het net — en
weegt zwaar omdat de director bij een onleesbare binnentemperatuur een draaiend apparaat met
rust laat, waarna dat apparaat zijn buitenunit op zijn taak houdt. De wachttijd houdt een
korte hapering bij een herstart eruit; de teller loopt op de vangnetklok van de coordinator.

De laatste twee gaan over hetzelfde gat, van twee kanten. `unsupported_modes` meldt een rol
die een stand vraagt die het apparaat niet meldt: de engine slaat die bron voor die stand
over, en van buiten is dat niet te onderscheiden van een kamer die niets hoeft.
`command_not_taking` meldt het omgekeerde: de bron krijgt zijn commando wel, elke ronde
opnieuw, en beweegt niet mee. `diff.changes()` biedt hetzelfde verschil aan zolang de
werkelijkheid niet klopt, dus dat is met de vangnetklok van zestig seconden ruim
veertienhonderd mislukte aanroepen per dag zonder één zichtbaar spoor. Per apparaat wordt
geteld hoe vaak hetzelfde verschil achter elkaar is aangeboden; tien gelijke rondes plus
dezelfde wachttijd van vijf minuten geven de melding. In schaduwmodus telt hij niet — daar
wordt met opzet niets uitgevoerd, dus de verschillenlijst is per definitie permanent gevuld.

### Nog te bouwen — ontwerpvoorstellen

De ideeënbus staat in [`ROADMAP.md`](ROADMAP.md); hier staat per idee het ontwerp, zodat
duidelijk is wat het inhoudt vóór eraan begonnen wordt. De prioriteiten (should/could/would)
volgen de ROADMAP.

#### Should have

**Virtuele `climate` per zone.** Eén bedieningsentiteit per ruimte: een
`climate.climate_director_<zone>` die op een gewone thermostaatkaart past.
- Config: optie `virtual_climate_per_zone`, standaard uit. Bestaande entries hebben de
  optie niet en gedragen zich exact als nu (`serialise.py` valt terug op de standaard).
- HA-laag: nieuw `climate.py`-platform; `async_setup_entry` maakt alleen entiteiten aan als
  de optie aan staat. De entiteit is invoer, net als de schakelaars: hij herstelt zijn
  waarde na een herstart, schrijft naar de coordinator (`zone_targets`/`zone_modes`, zelfde
  patroon als `zone_overrides`/`zone_priorities`) en negeert coordinator-updates.
- Engine: `WorldState` krijgt de runtime-waarden; `hysteresis.py` gebruikt een terugval op
  de geconfigureerde streefwaarde. De stand (`off`/`heat`/`cool`) wordt een filter vóór de
  vraagbepaling.
- Open keuze: betekent `off` "deze zone vraagt nooit iets" (nieuwe poort, nieuwe `Reason`),
  en beperken `heat`/`cool` de toegestane taak? Zonder die semantiek is de stand decoratie.
- Bewaakt: zonder optie nul gedragsverandering, en de engine-grens blijft heilig
  (runtime-state leeft in de coordinator; de engine leest alleen `WorldState`).

**Poortinstellingen per zone.** Wakker-, rooster-, stilte- en slaapregels verhuizen van
installatieniveau naar de zone.
- Config: nieuw `ZoneGateSettings` op `Zone` met `require_awake`, `require_schedule` en
  `quiet_windows`; `precondition_window`, `max_precondition` en `guest_window` blijven
  installatiebreed.
- Engine: `gates.py` leest per zone; de huishoudpoorten (`_household`) krijgen de zone mee.
- Migratie: `serialise.py` vult ontbrekende per-zone-velden met de oude installatiewaarde,
  zodat bestaand gedrag ongewijzigd blijft; `config_flow.py` krijgt de poortformulieren per
  zone en de validaties (`_quiet_problems`) worden per zone.
- Risico: de migratie is de kern — zonder terugval op de oude waarde verandert gedrag
  stilletjes bij de eerste upgrade.

#### Could have

**Huisbreed vermogensplafond.** `Source.wattage` + `DirectorConfig.watt_limit`; na de
circuitresolutie snoeit een nieuwe installatiebrede stap in `constraints.py` de winnaars op
watt, op zone-prioriteit, en houdt alleen starts tegen (nooit stops).

**Temperatuurschema per zone.** `Zone.schedule`: vensters met een eigen streeftemperatuur;
`hysteresis.py` kiest het geldende setpoint op de klok. De config-flow-editor voor zo'n
schema is het meeste werk.

**Suggestie voor circuitgroepering.** Alleen config-flow: groepeer gekozen
climate-entiteiten op gedeeld `device` / `via_device` / fabrikant en bied het als
voorstelknop aan. Geen engine-wijziging; nadrukkelijk een voorstel, omdat de relatie vaak
niet blootligt.

**Overrides via acties.** `climate_director.set_override` (duur of tot de volgende
gebeurtenis) en `clear_override`; de coordinator bewaart `zone_override_until` en plant een
evaluatie bij het verlopen. De bestaande schakelaar blijft bestaan.

**Droogstand als eigen taak.** `Zone.dry: ModeSettings` met een luchtvochtigheidssensor;
`dry` wordt een derde taak naast `heat`/`cool` met een eigen aan-/uitpunt. Op een
niet-simultaan circuit blijft `dry` bij de koelfamilie horen.

**Meerdere binnensensoren per zone.** `Zone.indoor_sensors` met een combinatieregel
(gemiddelde/laagste/hoogste/eerste); de coordinator aggregeert vóór `WorldState`.

**Openingen met herstel per zone.** Momentopname van de commando's vóór de opschorting; bij
het sluiten wordt de momentopname teruggezet voor zover nog geldig.

**Conflictdetector.** De coordinator telt onverwachte taakwissels en terugvallende standen
en vraagt via een repair-issue of de circuitgroepering klopt.

**Automatisch voorverwarmen en voorkoelen.** De engine berekent een startmoment vóór het
roostervenster en hergebruikt de bestaande precondition-mechaniek, maar met een automatische
trigger in plaats van een handmatige.

**Energieprijs als bronvoorkeur.** `WorldState` krijgt runtime-bronvoorkeuren; de
coordinator leest een tarief-/overschotsensor en `sources.py` sorteert daarop.

**Weersvoorspelling in het buitentemperatuurvenster.** De coordinator leest de verwachte
temperatuur uit een `weather`-entiteit; `WorldState.outdoor_forecast` laat de vensters op de
verwachting in plaats van op het nu toetsen.

**Meer conflictbeleiden.** `ConflictPolicy.ROUND_ROBIN` en `DAY_PART` in `constraints.py`,
met de circuitgeschiedenis als invoer.

**`number`-entiteiten voor de drempels.** Per zone `number`-entiteiten voor streef-, aanpunt
en hysterese; zelfde runtime-patroon als de prioriteits-`number`s (RestoreEntity, terugval
op de geconfigureerde waarde).

**Documenteren dat meerdere installaties mogen.** Alleen `docs/install/<taal>.md` per taal
bijwerken; de code en tests ondersteunen het al.

#### Would have

**Leren van looptijden.** De coordinator meet opwarm-/afkoelsnelheid per zone en stelt de
dode band of het voorverwarmen bij; opslag via `Store`.

**Balancering over circuits.** Bij gelijkwaardige bronnen op verschillende circuits kiest
`decide.py` beurtelings op basis van draaiuren.

**HACS-standaardlijst.** Geen ontwerp; procesbeslissing na bewezen praktijk.

### Uitbreidbaarheid

Nieuwe poorten, bronrollen, conflictbeleiden en circuitbeperkingen haken elk op één
bestaande module aan zonder de pijplijn te wijzigen. Nieuwe kunde die niets met Home
Assistant te maken heeft hoort per definitie in `engine/`, met tests ernaast.

## EN

Technical design document for anyone working on the code (not a user manual —
that is [`README.md`](README.md)). Each layer has exactly one responsibility.

**Units:** the engine and the stored configuration work in degrees Celsius —
that is the deliberate choice (decision 3 of 2026-08-25: follow Home
Assistant's unit rather than giving the engine a second system). The binding
layer is the one place that converts: the coordinator reads HA temperatures
into Celsius, the applier turns setpoints back into the user's unit, the form
shows and reads in that same unit, and the sensor attributes and the
`climate_director_decision` event publish in the user's unit (the event with a
`temperature_unit` field alongside). A source is read in the unit it reports
itself: `unit_of_measurement` on a sensor, `temperature_unit` on a weather
source, and only otherwise in the system unit. The outgoing side — sensor
attributes and the event — rounds to one decimal, in both systems; the engine
and the applier keep computing unrounded.
**The diagnostics stay Celsius**: that is a developer dump, not a user-facing
display.

**Inventory list "every user-facing text names its unit"** (round 11, G1): a
next round can *see* whether this list is complete instead of having to hope so.
Each sentence below converts Celsius with `display_temperature` — rounded, with
the unit behind it:

- `coordinator._wanted` — the `command_not_taking` repair notice;
- `engine/models.py` `target_outside_band` — the placeholders stay Celsius in
  the engine; `problems.readable` converts `start` and `target`. Which
  placeholder of which `Problem` code is a temperature lives in one place:
  `problems.TEMPERATURE_PLACEHOLDERS`;
- `coordinator._refusal_data` — the sentence travelling with a pre-conditioning
  request and landing on the phone via the blueprint (`precondition_confirmed`,
  `_satisfied`, `_idle`), in all six languages.

The sensor attributes and the `climate_director_decision` event use
`rounded_from_celsius` (one decimal, machine-readable); the diagnostics stay
Celsius. Those two do not belong on this list: the one is no sentence, the
other no user-facing display.

### The anchors — read this first

A statement in this engine always hangs on one thing, and which thing that is, is
a design decision. Wherever that decision was not written down, it shifted by one
step in four successive repair rounds — narrow, then too broad, then back again.
These six anchors therefore sit here, ahead of every module. Do not depart from
them without changing them here first.

1. **A running pre-conditioning request** is one concept throughout the engine:
   `world.preconditioning(zone_id)`. It passes everything except the master
   switch, an override, and an opening standing open that nobody said "do it
   anyway" to. There is no time window: a hand-given request always outranks the
   automation, whatever the hour, for the full `max_precondition`. The bounds are
   the request's own expiry plus the confirmation on an open door — the same
   principle as: whoever stays up late keeps their heating.
2. **An unreadable outdoor temperature** refuses a duty only when that duty
   itself has to pass a bounded window — on the zone, or on a source able to
   deliver this duty. Windows of sources that do not deliver the duty do not
   count: there is something to choose then.
3. **"Already sent"** means: this exact `(mode, setpoint)` really was executed and
   there has been no off command since. An off command clears the note, since an
   appliance that switches off may forget its setpoint.
4. **An off command explains exactly one observation.** The note lapses once that
   observation arrives, once the appliance reports an active mode on its own
   again, or after the window. The clock is the safety net, not the anchor.
5. **The opening rest hangs on the appliance**, not on the previous command's
   reason: a collapse can overwrite that reason. It lives in
   `Plan.opening_rest_until`, applies to every appliance without a circuit that
   really was running when the stop came — a shared heat source included — and is
   a fixed `OPENING_MIN_REST` of three minutes, counted from the stop. Right
   after a restart there is no previous plan: an ordinary source the world knows
   as running still rests (`_was_running` reads the world), but a shared heat
   source does not, since its stop only counts with a previous plan saying which
   zone really received heat (`_received_heat`). Deliberately not a setting: one
   knob fewer to get wrong, and three minutes is safe for any burner.
6. **The master switch off** means: the director lets go of everything and issues
   nothing, an `off` included — just like an override. Whoever wants everything
   off switches it off themselves; the director then leaves it be.

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
config_flow.py         wizard; writes one dict into entry.options
      │
      ▼
engine/serialise.py    dict → dataclasses (pure, forgiving)
      │
      ▼
Home Assistant (entity states, clock events)
      │
      ▼
  coordinator          gathers states, debounces, serialises
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
│  diff.py        Plan vs reality → what actually has to happen    │
│  serialise.py   dict ↔ dataclasses                               │
└──────────────────────────────────────────────────────────────────┘
      │
      ▼
  applier              executes the difference, or in shadow mode does not
      │
      ▼
  entities + event     sensor / binary_sensor / switch / button / number
                       + diagnostics
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

A configuration without residents skips the gates about residents - those could never
pass. The room gate still applies there: it is about the room, not about who is in the
house. An opening without a
timestamp blocks immediately: suspending is the harmless direction to be wrong in, and
refusing to act on an unknown age would keep heating an open room.

Alongside that sits `house_wide_blocked()`: the appliances from
`DirectorConfig.house_wide_openings` that must stand still the moment any opening in the
installation stands open. Deliberately *without* the `affects()` filter — this list
exists precisely for the appliance serving the whole house, and there is no explaining
why the front door would count and the bedroom window would not. The setting hangs on the
appliance rather than on the opening: the boiler need not be ticked again at every door,
and a window added later counts by itself. Empty yields an empty set, so an installation
not using this notices nothing.

On restart after an opening stop `opening_rest_until()` brakes the switching back on of
every appliance **without a circuit** — and by this design that is the boiler: the
appliance waits `OPENING_MIN_REST` (three minutes) from the stop, with a
`Deferral` (`SHORT_CYCLE_PROTECTION`) the coordinator returns on by itself. The stop
itself is never delayed, and a pre-conditioning request on which somebody expressly said
"do it anyway" passes the brake, exactly as it passes the gate itself.

### hysteresis.py — is it needed

Derives the requested duty from indoor temperature, season and outdoor window. It
receives the *running* duty; that is what makes the dead band work. The switch-on point
counts as reached (`<=` / `>=`), the switch-off point as passed (`<` / `>`) — were both
inclusive, a zero-width band would never let a duty stop.

If heating and cooling both ask at once (overlapping setpoints, so a configuration
mistake) the running duty keeps the zone; otherwise the larger deviation wins. Either
way the zone does not oscillate.

When the zone asks for nothing, the reason says which kind of nothing: `satisfied` when
the room lies past the far edge of the band, `within_deadband` when it lies inside it,
waiting for the switch-on point to be reached again. That distinction answers the
question users actually ask: it is 20.5 and the switch-on point is 20, so why does it
not kick in?

### sources.py — with what

Picks the appliance per zone and duty: suitability (role), then availability, then
preference (`priority`, with `source_id` as tie-break so the outcome is deterministic).

On top of that sits the **dead band on the outdoor temperature**. The bound between a
gas boiler and a heat pump is a number, and the weather hovers around it — without a
band the source swapped eight times a day. The source that really delivered last round
may therefore carry on until one band past its window. Only that source, and only
outside its window: sitting plainly inside it, preference decides again, so a fallback
to a second choice moves back the moment the first choice returns.

`select()` also takes the house-wide stopped appliances (`blocked`) and drops them as
candidates — the dead band's grip included, since what must stand still may not carry on
either. That happens here rather than at command level: were the plan to grant such a
source anyway, `sensor.…_source_<zone>` would name an appliance that then goes off. The
zone thus looks neatly on to its next source, and having none it lands on neutral with
`opening_open_elsewhere` as its reason instead of the misleading `no_source_available`.

### constraints.py — what may run together

The circuit rule:

> Let **F** be a circuit's active duty. Every indoor unit on that circuit sits in
> **F ∪ {`off`, `fan_only`}**.

Order of handling:

1. **Lock by units that stay put.** If a unit on the circuit runs that the director does
   not stand down this round, the circuit's duty is already settled and nothing can
   overrule it — the timers below included, since there is then no swap to make. Three
   kinds do that: a unit sitting in no zone at all, a unit in a zone that has been handed
   over, and a running unit in a zone whose indoor temperature cannot be read. With two
   duties locked at once — a remote and an override can arrange that — no duty can safely
   run on this circuit and nobody is granted anything.
2. **Conflict policy** (`priority`, `first_come`, `demand`, `season_lock`) picks the duty
   when zones disagree. Any policy that cannot decide falls back to priority.
3. **Minimum run time** holds the current duty when it was swapped too recently. With the
   timestamp missing the swap goes ahead: freezing the installation over an unknown value
   is worse than swapping a little early. When the duty is locked (step 1) this timer is
   skipped.
4. **Switch delay** stops the old duty first and starts the new one only after a
   `Deferral`.
5. **Capacity cap** trims the winners. Every unit that keeps running counts, not only the
   ones sitting in no zone: a handed-over zone and a hand-operated appliance occupy a place
   on the outdoor unit just the same. The cap is about what the director adds — if more is
   already running than the thing can take, it adds nothing on top and does not get in the
   way either.
6. **Short-cycle protection** holds back a start from a unit that just stopped — starts
   only, never stops.

### decide.py — the whole

The only entry point, and the only place a decision is made. Produces a `Plan`: desired
end states, not actions.

Two properties carry the rest of the system:

- **Every managed source gets a command, or a reason for getting none.** Whatever is
  not chosen is switched off explicitly; that is what makes "two appliances working
  against each other" unreachable rather than unlikely. Three appliances deliberately
  get nothing — an unreachable one, one in a zone that has been handed over, and a
  running one in a zone without a readable indoor temperature — and stand in the plan as
  an `UntouchedSource`. Those last two keep running, and are therefore handed to
  `constraints.py` as a lock: without that the director could put the opposing duty on
  the same outdoor unit, or start yet another unit beside them.
- **Stops come before starts** in the command order. Starting the new duty first on a
  circuit that is swapping would put two duties on one compressor for as long as the
  service calls take to land.

The **master switch is an emergency stop, not an off switch** (decided after review
round 4, H1): under `MASTER_DISABLED` the director sends nothing at all — an `off`
included. Every managed appliance then stands in the plan as an `UntouchedSource`,
exactly like a handed-over zone. Whoever switches the boiler on by hand afterwards keeps
it on; were the director to switch it off anyway, the emergency stop would be a lock.
The manual ("off = the director does nothing at all") matches again, and the switch is
usable as a handle in the migration script.

Every zone gets exactly one `Reason`, even when it does nothing, so a unit switching off
can always say *why* — "the heat pump serves this zone" reads differently from "there is
nothing to do".

An **exclusive group** is stored as source ids but works on appliances: every source id
is translated to its `entity_id` first. Otherwise a shared boiler escaped through
another room's source id. Two rooms asking for the same appliance are no rivals in that
- that is one appliance running.

When a hand-operated appliance and its group rival sit on the same circuit, the
hand-operated appliance occupies the slot itself (`_keeps_claiming` counts it), the rival
gets `CIRCUIT_AT_CAPACITY` for good, and per decision 2 of 2026-08-25 that stays. An
exclusive group whose members share an outdoor unit can therefore clamp itself shut —
use groups only for appliances that do not share an outdoor unit.

In source selection the house-wide stop stops the **zone**, not just the appliance: when
the zone's first choice is a house-wide stopped appliance, the zone refuses with
`OPENING_OPEN_ELSEWHERE` instead of sliding silently onto its second choice — otherwise
the air conditioner would be heating electrically because a door stands open elsewhere,
which you only notice on the energy bill. Only a genuinely unreachable first choice still
counts as a fallback (`passed_over`).

After `_collapse_shared` comes `_stop_blocked`: the safety net forcing an appliance
stopped house-wide (see `gates.house_wide_blocked`) to `off` whatever happens. Source
selection already refuses the zone, so in the ordinary run of things this does nothing; it
exists for the paths going round that choice — a shared boiler that got its command from
another zone, and the generator, which never runs through source selection at all. One
exception passes through: a pre-conditioning request on which somebody expressly said "do
it anyway", exactly as that passes the ordinary window gate. Whatever the director leaves
alone stays left alone: a zone handed over and a hand-operated source get no command and
therefore never come past here.

Around source selection and the generator commands sits the opening rest for every
appliance without a circuit: a start within `OPENING_MIN_REST` after the stop is held
with a `Deferral` (`SHORT_CYCLE_PROTECTION`), exactly as a circuit does. Only restarts
wait, never the stop itself.

### plan.py — output

`UnitCommand`, `ZoneDecision`, `CircuitDecision`, `UntouchedSource`, `Deferral` and `Reason`.
`Reason` is a `StrEnum` of stable identifiers rather than free text, so the Home Assistant
layer can translate them and users can filter on them in their own automations. A `Deferral`
tells the coordinator when to decide again, so a plan held back by a timer resumes on its own.

Every managed appliance sits in exactly one of two lists: it gets a `UnitCommand`, or it is
noted as an `UntouchedSource` with the reason why not - a zone handed over, a hand-operated
source, or one that cannot be reached. Steering nothing is an outcome rather than a void, and
without that distinction "the director is leaving this alone" looked, from the outside, the
same as "the director does nothing".

`WAITING_REASONS` names the reasons that should resolve by themselves; a zone sitting on one
for long is stuck, and the stuck sensor comes on. All three are timers of seconds to minutes.
A full outdoor unit is deliberately absent: it only frees up once another room stops asking,
which may take hours with nothing wrong. The room that does not get its place simply stands
recorded as blocked.

### serialise.py — storage

The only place the JSON-like format of a config entry is translated into dataclasses, and
back. Reading is deliberately forgiving: unknown keys are ignored, missing keys fall back on
their default, and junk in a list is skipped. An entry therefore survives a version that
adds or drops a field, instead of falling over at startup. What is structurally wrong comes
out of `validate()`, not out of an exception here.

Booleans are explicitly *not* read as numbers: `True` is an `int` in Python, and a priority
of `True` would silently become 1.

### diff.py — what actually has to happen

The plan describes end states; this pure function works out which of them do not hold yet.
A plan matching reality produces zero service calls — that is what stops the director
re-issuing the same call on every state change of every tracked entity. A unit being
switched off never gets a setpoint: it simply keeps the one it had, and a call that changes
nothing visible is noise.

### coordinator.py — the binding

Does exactly three things: read entities into one `WorldState`, have `decide()` turn that
into a `Plan`, and make sure a fresh decision happens whenever that is worthwhile. Holds no
decision logic itself; if an `if` about temperatures ever appears in that file, it belongs
in `engine/`.

Three things about it are subtle:

- **Everything in local, timezone-aware time.** Schedule windows are read in local time,
  while entity timestamps arrive in UTC. Mixing the two would put an open door's age hours
  out.
- **Circuit history comes from observation, not from the previous plan.** A unit somebody
  switches by remote changes a circuit's duty just as effectively as the director does, and
  the minimum-run timer has to respect that.
- **One event per zone, and only on change.** A decision is recomputed on every state change
  of every tracked entity; firing each time would drown any automation listening for it.

### applier.py — execution

Decides nothing. Asks `diff.py` what has to happen and turns that into service calls, or in
shadow mode only logs it. `climate.set_temperature` carries the `hvac_mode` too, so a unit
needing both a mode and a setpoint is served by a single call — two calls would briefly
leave it running the new mode on the old setpoint.

When a call fails, the response depends on what failed. A failed **stop** breaks the
assumption the rest of the plan rests on: the starts behind it would land on top of an
appliance that should have stopped, exactly the combination this design is meant to make
unreachable. The rest of the plan is then abandoned. A failed **start** is harmless — only
less happens than planned — and the rest carries on.

### config_flow.py — the wizard

Holds no knowledge of climate rules, only of forms. The installation is built up in a local
copy and written out only on "Save and close". Saving halfway would reload the entry while
the user is still editing, pulling the ground out from under the flow they are standing in.

A stale cursor (to a zone just deleted, say) sends the user back to the menu rather than
raising: a config flow that crashes leaves a half-built installation behind with no way back
into it.

### Entities

One device per installation. The sensors are deliberately detailed: in shadow mode they are
the only visible output, and the whole point of that mode is being able to see what would
have happened.

Beside them sits a second kind of entity under the same device, and the difference is a
matter of principle: the switches, the `number` entities and the buttons are **input**, not
output. They are control state rather than configuration — they restore themselves after a
restart, write their state back to the coordinator and ignore coordinator updates, since
otherwise the outcome of one decision would overwrite the input to the next.

The platforms are set up before the first decision, so a master switch left off does not
appear on for one round.

### texts.py — translated sentences going outward

The integration sends no messages of its own; where a notification goes is for a user to
decide. The **text** does come from here: a blueprint cannot translate, and a half-English
notice on a Dutch screen reads as a fault.

This module looks a sentence up in the language of the interface and falls back on English -
twice, in fact, since a translation may be missing *and* may have drifted from the code. The
sentences live under `exceptions` in `strings.json`, because Home Assistant validates the top
level of that file against a fixed schema.

### blueprints/ — the must-have automations, ready-made

Three blueprints, outside `custom_components/` and therefore not part of the integration
itself: monitoring, a refused pre-conditioning request with a confirm button, and the
decision notifier. They are deliberately **not** installed automatically - technically
possible, but no beaten path for a custom integration, and an automation still has to be
built from them afterwards.

Findability is solved with a repair notice instead: the moment nobody is listening for
`climate_director_precondition_refused`, Home Assistant says so. Measured through
`hass.bus.async_listeners()`, judged afresh once Home Assistant has finished starting and on
every automation reload.

### problems.py — surfacing configuration mistakes

`validate()` finds structural mistakes, but those only reached the diagnostics. This module
turns them into a repair notice in Home Assistant itself, and removes it again as soon as the
configuration is sound.

The notice is a warning rather than an error: `decide()` carries on regulating every sound
zone, so a flawed configuration degrades the installation without stopping it. That is
exactly why it has to be visible - from the outside, a mistake in the configuration looks the
same as "the director decides nothing".

There are five, with the same reason to exist. Besides the configuration mistake: a one-time
notice about duties only hand-operated sources can deliver, and a notice about configured
entities that have been unreadable for five minutes. That last one is a mistake in reality
rather than in the configuration - a flat battery, an appliance off the network - and weighs
heavily because with an unreadable indoor temperature the director leaves a running appliance
alone, after which that appliance holds its outdoor unit to its duty. The settling time keeps
a brief hiccup during a restart out of it; the clock runs on the coordinator's safety net.

The last two are about the same gap, from either side. `unsupported_modes` reports a role
asking a mode the appliance does not report: the engine skips that source for that mode, and
from the outside that is indistinguishable from a room with nothing to do.
`command_not_taking` reports the reverse: the source does get its command, again every round,
and does not move with it. `diff.changes()` offers the same difference for as long as reality
does not match, so on the sixty-second safety-net clock that is well over fourteen hundred
failed calls a day without a single visible trace. Per appliance it counts how often the same
difference has been offered in a row; ten identical rounds plus the same five-minute settling
time raise the notice. In shadow mode it never counts - nothing is executed there on purpose,
so the difference list is by definition permanently filled.

### Still to build — design proposals

The ideas box lives in [`ROADMAP.md`](ROADMAP.md); here stands the design per idea, so it
is clear what it entails before any work starts. The priorities (should/could/would) follow
the ROADMAP.

#### Should have

**A virtual `climate` per zone.** One control entity per room: a
`climate.climate_director_<zone>` that fits an ordinary thermostat card.
- Config: an option `virtual_climate_per_zone`, off by default. Existing entries lack the
  option and behave exactly as today (`serialise.py` falls back to the default).
- HA layer: a new `climate.py` platform; `async_setup_entry` only creates entities when the
  option is on. The entity is input, like the switches: it restores its value after a
  restart, writes to the coordinator (`zone_targets`/`zone_modes`, the same pattern as
  `zone_overrides`/`zone_priorities`) and ignores coordinator updates.
- Engine: `WorldState` gains the runtime values; `hysteresis.py` falls back to the
  configured target. The mode (`off`/`heat`/`cool`) becomes a filter before demand.
- Open choice: does `off` mean "this zone never asks for anything" (a new gate, a new
  `Reason`), and do `heat`/`cool` restrict the allowed duty? Without that semantics the mode
  is decoration.
- Guarded: no behavioural change without the option, and the engine border stays sacred
  (runtime state lives in the coordinator; the engine reads only `WorldState`).

**Per-zone gate settings.** The wake, schedule, quiet and sleep rules move from
installation level to the zone.
- Config: a new `ZoneGateSettings` on `Zone` with `require_awake`, `require_schedule` and
  `quiet_windows`; `precondition_window`, `max_precondition` and `guest_window` stay
  installation-wide.
- Engine: `gates.py` reads per zone; the household gates (`_household`) receive the zone.
- Migration: `serialise.py` fills missing per-zone fields with the old installation value,
  so existing behaviour stays unchanged; `config_flow.py` gains the per-zone gate forms and
  the validations (`_quiet_problems`) run per zone.
- Risk: the migration is the heart of it — without a fallback to the old value, behaviour
  changes silently on the first upgrade.

#### Could have

**A house-wide power ceiling.** `Source.wattage` + `DirectorConfig.watt_limit`; after the
circuit resolution a new installation-wide step in `constraints.py` trims the winners by
watts, on zone priority, and only ever holds back starts (never stops).

**A temperature schedule per zone.** `Zone.schedule`: windows with their own target
temperature; `hysteresis.py` picks the setpoint that applies by the clock. The config-flow
editor for such a schedule is the bulk of the work.

**Suggested circuit grouping.** Config flow only: group chosen climate entities on shared
`device` / `via_device` / manufacturer and offer it as a suggestion button. No engine
change; explicitly a proposal, since the relation often does not show.

**Overrides through actions.** `climate_director.set_override` (a duration or until the next
event) and `clear_override`; the coordinator keeps `zone_override_until` and schedules an
evaluation when it lapses. The existing switch stays.

**Drying as a duty of its own.** `Zone.dry: ModeSettings` with a humidity sensor; `dry`
becomes a third duty beside `heat`/`cool` with its own switch-on point. On a non-simultaneous
circuit `dry` stays in the cooling family.

**Several indoor sensors per zone.** `Zone.indoor_sensors` with a combination rule
(average/lowest/highest/first); the coordinator aggregates before `WorldState`.

**Openings with per-zone restore.** A snapshot of the commands before the suspension; when
the opening closes the snapshot is put back where it still holds.

**Conflict detector.** The coordinator counts unexpected duty swaps and modes falling back,
and asks through a repair issue whether the circuit grouping is right.

**Automatic pre-heating and pre-cooling.** The engine computes a start moment before the
schedule window and reuses the existing pre-conditioning machinery, but with an automatic
trigger instead of a manual one.

**Energy price as source preference.** `WorldState` gains runtime source preferences; the
coordinator reads a tariff/surplus sensor and `sources.py` sorts on it.

**Weather forecast in the outdoor window.** The coordinator reads the expected temperature
from a `weather` entity; `WorldState.outdoor_forecast` lets the windows check the forecast
rather than the now.

**More conflict policies.** `ConflictPolicy.ROUND_ROBIN` and `DAY_PART` in `constraints.py`,
with the circuit history as input.

**Per-zone `number` entities for the thresholds.** Per-zone `number` entities for the
target, switch-on point and hysteresis; the same runtime pattern as the priority `number`s
(RestoreEntity, fallback to the configured value).

**Document that several installations may sit side by side.** Only update
`docs/install/<language>.md` per language; the code and tests already support it.

#### Would have

**Learning from run times.** The coordinator measures each zone's heating and cooling rate
and adjusts the dead band or the pre-heating; kept through `Store`.

**Balancing across circuits.** With equivalent sources on different circuits, `decide.py`
takes turns based on running hours.

**Inclusion in the HACS default list.** No design; a process decision after proven
practice.

### Extensibility

New gates, source roles, conflict policies and circuit constraints each plug into one
existing module without changing the pipeline. New logic with nothing to do with Home
Assistant belongs in `engine/` by definition, with tests alongside it.
