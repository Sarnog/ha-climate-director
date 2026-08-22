# Climate Director — Installatiehandleiding (Nederlands)

[![Koop me een koffie op Ko-fi](https://img.shields.io/badge/Ko--fi-Koop%20me%20een%20koffie-FF5E5B?style=for-the-badge&logo=kofi&logoColor=white)](https://ko-fi.com/sarnog)
[![Sponsor via GitHub](https://img.shields.io/github/sponsors/sarnog?style=for-the-badge&logo=github&label=Sponsors&color=EA4AAA)](https://github.com/sponsors/sarnog)

Deze handleiding legt stap voor stap uit hoe je Climate Director installeert en
instelt. Volg de stappen gewoon van boven naar beneden; elke stap bouwt voort op
de vorige.

## Inhoud

- [Wat is Climate Director](#wat-is-climate-director)
- [Wat je nodig hebt](#wat-je-nodig-hebt)
- [Stap 1 — Installeren](#stap-1--installeren)
- [Stap 2 — De integratie toevoegen](#stap-2--de-integratie-toevoegen)
- [Het hoofdmenu](#het-hoofdmenu)
- [Stap 3 — Algemene instellingen](#stap-3--algemene-instellingen)
- [Stap 4 — Zones](#stap-4--zones)
- [Stap 5 — Bronnen](#stap-5--bronnen)
- [Stap 6 — Airco-circuits](#stap-6--airco-circuits)
- [Stap 7 — Gedeelde warmtebronnen](#stap-7--gedeelde-warmtebronnen)
- [Stap 8 — Exclusieve groepen](#stap-8--exclusieve-groepen)
- [Stap 9 — Stiltevensters](#stap-9--stiltevensters)
- [Stap 10 — Bewoners](#stap-10--bewoners)
- [Stap 11 — Deuren en ramen](#stap-11--deuren-en-ramen)
- [Stap 12 — Opslaan en sluiten](#stap-12--opslaan-en-sluiten)
- [Wat je in Home Assistant krijgt](#wat-je-in-home-assistant-krijgt)
- [De schakelaars en knoppen](#de-schakelaars-en-knoppen)
- [Acties](#acties)
- [Vooruit verwarmen en koelen](#vooruit-verwarmen-en-koelen)
- [Zelf de baas](#zelf-de-baas)
- [Een schaduwrun beoordelen](#een-schaduwrun-beoordelen)
- [Blueprints en meldingen](#blueprints-en-meldingen)
- [Problemen oplossen](#problemen-oplossen)
- [Talen](#talen)

## Wat is Climate Director

Climate Director is een integratie voor Home Assistant die bestaande
klimaatapparaten aanstuurt. Hij bezit zelf geen hardware: hij dirigeert de
`climate`-entiteiten die je al hebt — een cv-ketel, een warmtepomp, airco's.
Op elk moment berekent hij één samenhangende eindtoestand voor het hele huis
en zet die om in service calls.

**Schaduwmodus staat standaard aan.** De integratie berekent dan elke
beslissing en laat zien wat ze gedaan zou hebben, maar stuurt niets aan. Zo kun
je hem wekenlang naast je bestaande automatiseringen laten meedraaien en pas
overstappen als je er vertrouwen in hebt.

Drie begrippen vormen de basis:

| Begrip | Betekenis |
|---|---|
| **Zone** | Een ruimte. Beschrijft *wat je wilt*: gewenste temperatuur, wanneer verwarmen of koelen mag beginnen, en in welk seizoen. |
| **Bron** | Een apparaat dat een zone kan bedienen, met een taak (verwarmen, koelen of beide), een voorkeursvolgorde en een buitentemperatuurvenster. |
| **Airco-circuit** | Eén buitenunit met de binnenunits die eraan hangen. Beschrijft *wat technisch tegelijk kan*. |

De vuistregel voor een gedeelde buitenunit: alle binnenunits op één circuit
doen dezelfde taak — verwarmen, koelen, uit, of alleen ventileren. Twee
binnenunits op één buitenunit kunnen dus niet tegelijk de ene verwarmen en de
andere koelen. Climate Director weet welke units bij elkaar horen en lost dat
conflict voor je op.

## Wat je nodig hebt

| Entiteit | Verplicht | Waarvoor |
|---|---|---|
| Eén `climate.*` per zone | **ja** | zonder apparaat valt er niets aan te sturen |
| Eén temperatuursensor per zone | **ja** | zonder meting weet de integratie niet of het te koud of te warm is; een `climate.*` met `current_temperature` mag ook |
| `sensor.*` of `weather.*` buitentemperatuur | nee | alleen nodig als je grenzen op buitentemperatuur wilt — gas onder 3 °C, warmtepomp erboven, bijvoorbeeld |
| `weather.*` of `sensor.*` neerslag | nee | alleen als neerslag de 'zet een raam open'-grens mag opheffen |
| `person.*` of `device_tracker.*` per bewoner | ja, zodra je bewoners instelt | anders kan die bewoner nooit thuis zijn |
| Een slaapsensor per bewoner | nee | zonder deze telt niemand ooit als slapend |
| `binary_sensor.*` aanwezigheid per zone | alleen als een zone op *de ruimte zelf* draait | dan is het de enige poort die de zone heeft |
| `binary_sensor.*` deur of raam | nee | schort de gekoppelde zones op zolang het openstaat |
| `calendar.*` | nee | zet het vakantieschema vanzelf aan; werkt alleen met een trefwoord |
| Een seizoensentiteit | nee | alleen als je het seizoen niet uit de maand wilt afleiden |

Helpers hoef je nergens voor aan te maken. Alle schakelaars en regelaars maakt
de integratie zelf.

## Stap 1 — Installeren

**Minimale versie:** Home Assistant **2025.3** of nieuwer. De integratie voegt
haar entiteiten toe met een API die sinds 2025.3 bestaat.

**Via HACS** (aanbevolen):

1. Open HACS.
2. Ga naar de drie puntjes rechtsboven en kies **Aangepaste repositories**.
3. Voeg deze URL toe, met categorie **Integratie**:

   ```
   https://github.com/Sarnog/ha-climate-director
   ```

4. Zoek in HACS op **Climate Director**, installeer, en herstart Home Assistant.

**Handmatig:**

1. Download of kloon deze repository.
2. Kopieer de map `custom_components/climate_director` naar de map
   `custom_components` in je Home Assistant-configuratie.
3. Herstart Home Assistant.

## Stap 2 — De integratie toevoegen

1. Ga naar **Instellingen → Apparaten en diensten → Integratie toevoegen**.
2. Zoek **Climate Director** en kies hem.
3. Geef de installatie een **naam**. Die naam wordt de titel en komt vóór de
   naam van elke entiteit die de integratie maakt.
4. Laat **Schaduwmodus** aan staan. Zo kijk je eerst mee voordat er echt iets
   aangestuurd wordt.
5. Sla op. De installatie verschijnt op het tabblad **Integraties**.

Alles daarna bouw je op via **Configureren** bij deze integratie.

## Het hoofdmenu

Onder **Configureren** vind je het hoofdmenu, in deze volgorde:

| Menu | Waarvoor |
|---|---|
| **Algemene instellingen** | buitentemperatuur, seizoen, poorten, vensters, agenda's, schaduwmodus |
| **Zones en bronnen** | per ruimte: temperatuur, aan- en uitpunten, en de apparaten die erbij horen |
| **Airco-circuits** | welke binnenunits één buitenunit delen |
| **Gedeelde warmtebronnen** | een ketel of warmtepomp waar meerdere kamers op draaien |
| **Exclusieve groepen** | apparaten die nooit tegelijk mogen draaien |
| **Stiltevensters** | uren waarin de director uit zichzelf niets begint |
| **Bewoners** | wie er thuis is, wie slaapt, en ieders rooster |
| **Deuren en ramen** | welke openingen welke zones stilzetten |
| **✅ Opslaan en sluiten** | pas hier wordt alles echt opgeslagen |

Twee dingen maken het menu prettig:

- Elk scherm eindigt met **Als je hier klaar bent**, met de keuze *Deze
  wijzigingen bewaren en teruggaan* of *Weggooien en teruggaan*.
- Elke keuzelijst heeft een regel **← Terug naar het hoofdmenu**.

Je zit dus nergens vast. Teruggaan kan altijd, ook met een half ingevuld
scherm — wat je intikte gaat dan verloren. En er wordt **niets** opgeslagen tot
je in het hoofdmenu **Opslaan en sluiten** kiest.

## Stap 3 — Algemene instellingen

| Instelling | Wat het doet |
|---|---|
| **Buitentemperatuursensor** | voedt elke buitengrens. Zonder sensor telt elke ingestelde grens als niet gehaald en staat de installatie stil |
| **Verwarmingssysteem** | *Centraal* of *Per zone*, zie hieronder |
| **Seizoensbron** | waar het seizoen vandaan komt: de maand, een entiteit, of vast zomer/winter |
| **Seizoensentiteit** | alleen nodig als de bron op *entiteit* staat; ook de ingebouwde `season.*`-entiteit is kiesbaar |
| **Halfrond** | welke maanden als zomer tellen wanneer het seizoen uit de maand komt: noordelijk april–september, zuidelijk oktober–maart |
| **Seizoenskeuze** | de `select.*`-entiteit *Seizoen* zet het seizoen met de hand op Automatisch, Zomer of Winter; de keuze overleeft een herstart |
| **Iemand thuis moet wakker zijn** | aan = het huis wacht tot er iemand thuis én wakker is; uit = slapen telt niet |
| **Het rooster van een bewoner moet openstaan** | aan = het huis wacht op het eerste roostervenster; uit = alleen aanwezigheid telt |
| **Vakantieagenda's** | welke agenda's een vakantie mogen aankondigen; meerdere toegestaan |
| **Woord dat vakantie aangeeft** | het trefwoord dat een agenda-item moet dragen; leeg = agenda's worden genegeerd |
| **Vooruit verwarmen vanaf / tot** | het venster waarin een vooruit-verzoek meetelt; standaard 06:00–23:00 |
| **Vooruitverwarmingsduur** | het plafond op één verzoek; standaard 120 minuten |
| **Gastenmodus vanaf / tot** | het venster waarin de gastenmodus geldt; beide leeg = de hele dag |
| **Meld een zone vastgelopen na** | na hoeveel minuten wachten een zone als vastgelopen geldt; 0 zet de melder uit |
| **Neerslagbron** | een `weather.*`- of `sensor.*`-entiteit die zegt of er neerslag valt; leeg = de neerslagregel doet niet mee |
| **Staten die als neerslag tellen** | welke standen van die entiteit neerslag betekenen; standaard regen, sneeuw en hagel |
| **Hoe lang neerslag blijft tellen (minuten)** | nalooptijd na het stoppen van de neerslag; standaard 15 minuten |
| **Schaduwmodus** | aan = alles doorrekenen, niets aansturen |

### Neerslag zet de buitengrens opzij

De buitengrens per zone is een zuinigheidsregel met een aanname eronder: is
het buiten aangenamer dan binnen, dan kun je beter een raam openzetten dan de
airco aanzetten. Valt er neerslag, dan blijft dat raam dicht en gebeurt er
dus niets, terwijl het binnen te warm of te koud blijft.

Stel daarom een **neerslagbron** in. Zolang die neerslag meldt, slaat Climate
Director de **buitengrens per zone** over — precies zoals een vooruit-verzoek
dat doet. De dode band, het seizoen en de buitengrens **per bron** blijven
gewoon gelden; die kiezen nog steeds het apparaat. De nalooptijd zorgt dat een
bui van vijf minuten de regeling niet laat stuiteren. Zonder bron doet de
neerslagregel niet mee.

Een ruimte zonder ramen heeft er niets aan. Zet daar in de zone **Neerslag
heft de 'zet een raam open'-regel niet op** aan, en de buitengrens blijft ook
bij neerslag gelden.

### Verwarmingssysteem: centraal of per zone

### Verwarmingssysteem: centraal of per zone

| Keuze | Wat het betekent | Zo vul je het in |
|---|---|---|
| **Centraal** | Eén warmtebron voor het hele huis. Aanzetten voor één kamer verwarmt de rest mee. Denk aan één slimme thermostaat, met of zonder radiatorknoppen. | Zet **dezelfde** thermostaat als bron onder elke zone |
| **Per zone** | Elk deel van het huis kan zijn warmte apart krijgen, via een zoneventiel of een eigen warmtebron. | Geef elke zone zijn **eigen** klep of apparaat als bron; is er één gedeelde ketel, zet die er dan bij als gedeelde warmtebron |

Slimme radiatorknoppen alleen zijn géén zonering: het huis heeft dan nog steeds
één circuit en één warmtebron die voor iedereen tegelijk aan of uit gaat. Kies
dan **Centraal**. Eén ketel met drie zoneventielen is juist **Per zone**.

Deze instelling verandert niets aan wie er mag draaien. Hij legt vast wat je
installatie is, zodat de configuratiecontrole kan waarschuwen als je invulling
er niet bij past.

## Stap 4 — Zones

Een zone is een ruimte. Per zone stel je in:

| Instelling | Wat het doet |
|---|---|
| **Naam** | de naam die overal terugkomt |
| **Binnentemperatuursensor** | waarop de dode band rekent; een `climate.*` die zelf meet mag ook |
| **Voorrang op een gedeelde buitenunit** | hoe hard deze zone een gedeelde buitenunit claimt; **lager wint**. Op één circuit mag geen nummer dubbel voorkomen |
| **Wat bepaalt of deze zone draait** | *het huishouden* (rooster, slaap, iemand thuis) of *de ruimte zelf* (alleen de aanwezigheidssensor) |
| **Aanwezigheidssensor + status + nalooptijd** | wanneer de kamer als bezet telt; de nalooptijd vangt knipperende melders op |
| **Neerslag heft de 'zet een raam open'-regel niet op** | aan voor een ruimte zonder ramen; daar blijft de buitengrens ook bij neerslag gelden |
| **Deze zone mag verwarmen** | uit = deze kamer wordt nooit verwarmd |
| **Streeftemperatuur verwarmen** | het setpoint dat het apparaat krijgt als verwarmen draait — niet het startpunt |
| **Verwarmen starten bij** | verwarmen start bij deze binnentemperatuur of lager |
| **Dode band verwarmen** | hoe ver boven het startpunt verwarmen stopt |
| **Alleen verwarmen onder deze buitentemperatuur** | daarboven blijft verwarmen uit; leeg = geen grens |
| **Deze zone mag koelen** | uit = deze kamer wordt nooit gekoeld |
| **Streeftemperatuur koelen** | het setpoint dat het apparaat krijgt als koelen draait |
| **Koelen starten bij** | koelen start bij deze binnentemperatuur of hoger |
| **Dode band koelen** | hoe ver onder het startpunt koelen stopt |
| **Alleen koelen boven deze buitentemperatuur** | daaronder blijft koelen uit; leeg = geen grens |
| **Alleen koelen in de zomer** | koppelt koelen aan het seizoen uit de algemene instellingen |

### Zo werkt de dode band

Aan- en uitschakelen gebeuren op twee verschillende temperaturen, zodat een
apparaat niet op één tiende graad blijft klepperen:

- verwarmen start bij `binnen ≤ startpunt` en stopt bij `binnen ≥ startpunt + band`;
- koelen start bij `binnen ≥ startpunt` en stopt bij `binnen ≤ startpunt − band`.

Het startpunt telt als bereikt, het stoppunt als gepasseerd. Eén graad band is
een verstandig begin.

### Wat het scherm weigert

Drie combinaties worden bij het opslaan geweigerd, omdat ze een zone opleveren
die er wel staat maar nooit iets doet:

- een **streeftemperatuur aan de verkeerde kant van het startpunt** — het
  apparaat krijgt dan een temperatuur waar het niets voor hoeft te doen;
- **koelen dat start op of onder het punt waar verwarmen start** — dan vragen
  de twee tegelijk om dezelfde kamer;
- de zone op **de ruimte zelf zonder aanwezigheidssensor**, of een zone die
  **niet mag verwarmen en niet mag koelen**.

### Huishouden of de ruimte zelf

- **Het huishouden** (standaard): rooster, slaap en iemand-thuis tellen mee.
  Stel je óók een aanwezigheidssensor in, dan geldt die als extra voorwaarde:
  het huishouden moet het toestaan **en** de kamer moet bezet zijn.
- **De ruimte zelf**: rooster, slaap en iemand-thuis worden overgeslagen.
  Alleen de aanwezigheidssensor beslist. Dit vereist dus een
  aanwezigheidssensor, anders kan de zone nooit draaien.

Zo kan de ene kamer op het rooster lopen en de andere op aanwezigheid.

## Stap 5 — Bronnen

Een bron is een apparaat dat de zone kan bedienen. Nadat je een zone hebt
opgeslagen, kies je meteen de bronnen ervan.

| Instelling | Wat het doet |
|---|---|
| **Climate-entiteit** | het apparaat zelf |
| **Wat dit apparaat kan** | alleen verwarmen, alleen koelen, of allebei. Een ketel is *alleen verwarmen* |
| **Dit apparaat automatisch starten** | uit laat hem met rust, zie hieronder |
| **Volgorde binnen deze zone** | welke bron de voorkeur heeft; **lager wint** |
| **Gebruiken vanaf deze buitentemperatuur** | de ondergrens; hoort bij het venster |
| **Gebruiken tot deze buitentemperatuur** | de bovengrens; hoort niet bij het venster |

### Buitengrenzen: half open

De ondergrens hoort bij het venster, de bovengrens niet. Twee aangrenzende
bronnen dekken zo de hele schaal, zonder gat en zonder overlap.

Wil je gas onder de 3 °C en de airco erboven, zet de grens dan **niet** op 3,0:

| Grens | 2,9 °C | 3,0 °C | 3,1 °C |
|---|---|---|---|
| beide op `3.0` | gas | **airco** | airco |
| beide op `3.1` | gas | **gas** | airco |

Zet de grens bij **elke** bron gelijk, en nooit verschillend — anders ontstaat
er een overlap waarin allebei mogen.

### Een apparaat dat je zelf aanzet

Zet **Dit apparaat automatisch starten** uit voor een apparaat dat je met de
hand bedient (bijvoorbeeld een airco op een slaapkamer zonder
aanwezigheidssensor). De director:

- **zet hem nooit aan**, hoe koud of warm die kamer ook wordt;
- **laat hem staan** zoals jij hem zet;
- **zet hem alleen uit** als hij een taak draait die de gedeelde buitenunit
  niet toestaat.

Zit er een taak die alleen zo’n apparaat kan, dan meldt de integratie dat één
keer onder *Reparaties*. Bevestig je die melding, dan blijft hij weg — ook na
een herstart. Krijgt de zone er later een nieuwe handbediende taak bij, dan
volgt er opnieuw één melding.

Zit er een taak die alleen zo’n apparaat kan, dan meldt de integratie dat één
keer onder *Reparaties*. Bevestig je die melding, dan blijft hij weg — ook na
een herstart. Krijgt de zone er later een nieuwe handbediende taak bij, dan
volgt er opnieuw één melding.

## Stap 6 — Airco-circuits

Alleen nodig als binnenunits een buitenunit delen. Heeft elke unit zijn eigen
buitenunit, laat dit dan leeg.

| Instelling | Wat het doet |
|---|---|
| **Naam** | een label om circuits uit elkaar te houden |
| **Binnenunits** | welke `climate.*`-entiteiten aan deze buitenunit hangen. Neem ook units mee die de director niet beheert: die claimen de compressor ook |
| **Kan tegelijk verwarmen en koelen** | uit voor een gewone multi-split; aan voor een losse split of driepijps-VRF met warmteterugwinning |
| **Conflictbeleid** | wie wint als twee kamers tegengestelde taken willen |
| **Een verliezende zone mag ventileren** | aan = de verliezer gaat naar `fan_only` in plaats van uit, maar alleen als de unit die stand kent; anders gaat hij uit |
| **Pauze bij taakwissel** | hoe lang alles uit staat vóór de omschakeling |
| **Minimale looptijd voor een taakwissel** | hoe lang een taak minstens moet hebben gedraaid voor de andere hem mag overnemen |
| **Rust voor een unit opnieuw mag starten** | vertraagt alleen starten, nooit stoppen; standaard 180 seconden |
| **Maximum aantal units tegelijk** | de capaciteitsgrens van de buitenunit; leeg = geen grens |

### Conflictbeleid

| Beleid | Gedrag |
|---|---|
| **Prioriteit** (standaard) | de zone met het laagste prioriteitsnummer wint |
| **Wie eerst was** | de taak die al draait houdt het circuit; een nieuwe aanvraag wacht |
| **Grootste afwijking** | de grootste afwijking van het setpoint wint |
| **Seizoen** | het seizoen bepaalt de taak; alles wat de andere kant op wil staat af |

## Stap 7 — Gedeelde warmtebronnen

Een ketel of warmtepomp waar meerdere kamers op draaien via hun eigen klep.
Laat dit leeg als het systeem zijn eigen brander start zodra een klep erom
vraagt.

| Instelling | Wat het doet |
|---|---|
| **Naam** | een label om warmtebronnen uit elkaar te houden |
| **Climate-entiteit** | de ketel of warmtepomp zelf; mag niet óók een bron van een zone zijn, anders krijgt hij twee opdrachten |
| **Zones die hij bedient** | leeg = alle kamers |
| **Vaste streeftemperatuur** | leeg = hij volgt het warmste doel van de kamers die vragen |

De warmtebron draait zolang een kamer die hij bedient verwarmd wordt, en stopt
zodra er geen meer is.

## Stap 8 — Exclusieve groepen

Wil je dat twee apparaten **nooit** tegelijk draaien — een gasketel en een
warmtepomp bijvoorbeeld — vertrouw dat dan niet op de buitengrenzen alleen. Eén
achtergebleven waarde is genoeg om ze samen te laten aanslaan. Zet ze daarom in
een exclusieve groep: van de apparaten in één groep draait er altijd maar één.

Let op wat een groep betekent: **één** apparaat uit de groep tegelijk. Wil je
dat de gasketel geen enkele airco in de weg zit, maar dat twee airco's op
hetzelfde circuit wél samen mogen koelen, maak dan één groep per paar — gas met
de ene airco, gas met de andere.

Een groep geldt ook voor apparaten die je zelf aanzet: komt een ander lid van de
groep aan de beurt, dan gaat het handbediende apparaat uit. En andersom: draait
zo’n apparaat al, dan bezet het de groep en wacht een ander lid.

## Stap 9 — Stiltevensters

Uren waarin de director **uit zichzelf niets begint**. Thuiskomen om elf uur
's avonds terwijl je zo naar bed gaat, hoeft het huis niet te laten opstoken.

Het is een rem op **beginnen**, niet op doorgaan:

- wat al draait blijft gewoon geregeld;
- zet je zelf iets aan, dan wordt dat opgepakt;
- wat uit staat blijft uit tot het venster voorbij is.

Vensters mogen over middernacht lopen en kennen weekdagen. Een huishouden dat
doordeweeks om negen uur naar bed gaat en in het weekend om elf uur, zet er
twee:

| Van | Tot | Dagen |
|---|---|---|
| 21:00 | 09:00 | ma di wo do zo |
| 23:00 | 09:00 | vr za |

Stel je geen vensters in, dan doet de rem niet mee.

## Stap 10 — Bewoners

Laat dit leeg voor een gebouw waar niemand gevolgd wordt; de
aanwezigheidspoorten worden dan overgeslagen in plaats van dat ze alles
tegenhouden.

| Instelling | Wat het doet |
|---|---|
| **Naam** | een label om bewoners uit elkaar te houden |
| **Aanwezigheidssensor** | meestal een `person.*`; zegt of deze bewoner thuis is |
| **Slaapsensor** | wanneer deze bewoner slaapt; leeg = slaap wordt niet bijgehouden |
| **Status die slapen betekent** | de stand die de slaapsensor meldt bij slapen |
| **Slaapsensor telt vanaf / tot** | de uren waarin die sensor iets betekent; beide leeg = de klok rond |
| **Dagen van het slaapvenster** | op welke dagen dat venster geldt; leeg = elke dag |

### Roosters

Na het opslaan van een bewoner stel je zijn roosters in:

| Instelling | Wat het doet |
|---|---|
| **Dit is een vakantievenster** | geldt alleen tijdens het vakantieschema en vervangt dan de gewone vensters |
| **Van / Tot** | het venster; mag over middernacht lopen |
| **Dagen** | leeg = elke dag |

Een bewoner zonder rooster doet niet mee aan de roosterpoort. Wie op een dag
geen venster heeft, houdt het huis die dag niet tegen.

### Slaapsensor: geen sensor, wel een knop?

Een knop (`button` of `input_button`) kan niet zeggen of je slaapt — zijn status
is het tijdstip van de laatste druk. Wat wél werkt is een `input_boolean` die je
met een knop omschakelt: maak de schakelaar, kies hem als slaapsensor met `on`
als slaapstand, en laat een knop hem omzetten. Wie wél een slaapsensor heeft
(een bed-sensor, een draadloze lader) gebruikt die: dat is nauwkeuriger.

Laat je de slaapsensor leeg, dan telt die bewoner nooit als slapend.

## Stap 11 — Deuren en ramen

Een opening die lang genoeg openstaat, zet de gekoppelde zones stil.

| Instelling | Wat het doet |
|---|---|
| **Sensor** | het deur- of raamcontact; open telt als `on` |
| **Zones die het raakt** | leeg = de hele installatie |
| **Vertraging voor het stilzetten** | leeg of 0 = meteen bij openen |

## Stap 12 — Opslaan en sluiten

Kies in het hoofdmenu **✅ Opslaan en sluiten**. Pas op dat moment wordt de
installatie weggeschreven.

Klopt er iets structureel niet — een zone zonder bruikbare bron, twee bronnen op
dezelfde entiteit, een buitenvenster dat niets toelaat — dan krijg je eerst een
lijst te zien met de keuze *Toch opslaan* of *Terug om iets aan te passen*.
Het is een **waarschuwing, geen weigering**: een installatie mag met opzet
afwijkend zijn, en alleen jij weet of dat zo is. Dezelfde lijst staat zolang het
geldt ook onder **Reparaties**.

## Wat je in Home Assistant krijgt

Eén device per installatie, met daaronder:

| Entiteit | Waarvoor |
|---|---|
| `sensor.*_laatste_beslissing` | hoeveel zones bediend worden, met het volledige plan als attributen |
| `sensor.*_zou_<entiteit>_aansturen` | de stand waarin de director dit apparaat zou zetten — één sensor per apparaat |
| `sensor.*_afwijkingen` | hoeveel apparaten er nú anders staan dan het plan wil; 0 = director en huis zijn het eens |
| `sensor.*_bron_<zone>` | welke bron deze zone bedient, met wat de zone wilde, kreeg en waarom |
| `binary_sensor.*_<zone>_geblokkeerd` | aan als een zone minder kreeg dan hij vroeg, of wilde draaien maar een omstandigheid haar tegenhield; de dichte poorten staan in de attributen |
| `binary_sensor.*_<zone>_op_reserve` | aan als een zone op een reserve-apparaat draait omdat de eerste keus onbereikbaar is |
| `binary_sensor.*_vastgelopen` | aan als een zone te lang op dezelfde wachtreden staat |
| `switch.*_director` | de hoofdschakelaar; uit = er wordt niets geregeld |
| `switch.*_vakantieschema` | laat elke dag als zaterdag tellen, of als het eigen vakantierooster |
| `switch.*_gastenmodus` | blijft regelen terwijl de bewoners weg zijn |
| `switch.*_override_<zone>` | geeft één zone volledig aan jou terug |
| `number.*_prioriteit_<zone>` | de voorrang van deze zone; ook vanuit een automatisering te wijzigen |
| `number.*_vooruitduur` | hoe lang één druk op een vooruit-knop duurt |
| `button.*_<zone>_vooruit` | laat deze zone vooruit verwarmen of koelen |

Daarnaast is er een downloadbare diagnose met de configuratie, de laatst
gelezen momentopname en het laatste plan.

## De schakelaars en knoppen

- **Hoofdschakelaar** (`switch.*_director`): uit = de director doet helemaal
  niets.
- **Gastenmodus** (`switch.*_gastenmodus`): er logeert iemand die niet gevolgd
  wordt, dus "huis leeg" zegt niets. Slaap van wie thuis is blijft gelden, en
  buiten het gastenvenster nemen de gewone poorten het over.
- **Vakantieschema** (`switch.*_vakantieschema`): elke dag telt als zaterdag,
  of als het eigen vakantievenster. Gaat ook vanzelf aan zodra een ingestelde
  agenda een lopend item heeft met het trefwoord erin. Zonder trefwoord blijven
  de agenda's buiten beschouwing.
- **Override** (`switch.*_override_<zone>`): geeft één zone volledig aan jou.
  De director stuurt die zone dan niets meer — ook geen uit. De circuitregels
  blijven wel gelden voor de andere kamers. De override vervalt vanzelf zodra
  iedereen die thuis is naar bed gaat of het huis leeg is.
- **Vooruit-knop** (`button.*_<zone>_vooruit`) en **vooruitduur**
  (`number.*_vooruitduur`): zie hieronder.

## Acties

| Actie | Waarvoor |
|---|---|
| `climate_director.evaluate` | nu opnieuw laten beslissen, zonder op een toestandswijziging te wachten |
| `climate_director.precondition` | vooruit verwarmen of koelen starten |
| `climate_director.cancel_precondition` | een lopend vooruit-verzoek afblazen |

`climate_director.evaluate` is handig tijdens het inrichten. In schaduwmodus
voert hij nog steeds niets uit — hij herberekent alleen.

## Vooruit verwarmen en koelen

De enige manier om een leeg huis te laten draaien, en met opzet de enige die je
met de hand moet aanzetten.

- **Met een knop**: elke zone heeft `button.*_<zone>_vooruit`. Hoe lang zo'n
  druk duurt staat in `number.*_vooruitduur` (standaard 60 minuten, een
  kwartier tot twee uur).
- **Met de actie**:

  ```yaml
  action: climate_director.precondition
  data:
    zone_ids: [<zone>]
    minutes: 45
  ```

**Belangrijk:** je zegt niet wát er moet gebeuren. Het verzoek opent alleen de
deur; daarna beslist de integratie precies zoals anders — de dode band kijkt of
het te koud of te warm is, het seizoen en de buitengrens per bron kiezen het
apparaat. Ligt de kamer al goed, dan blijft het apparaat uit.

Bij een vooruit-verzoek blijven de hoofdschakelaar, een override, de dode band,
het seizoen, de buitengrens per bron, ramen en deuren, het circuit en de
uitsluitende groepen gewoon gelden. Overgeslagen worden: *iemand thuis*,
*wakker*, *rooster*, *aanwezigheid in de ruimte*, de buitengrens per zone en
het stiltevenster.

Een openstaand raam of een openstaande deur **weigert** een verzoek. Wie het
raam zelf openzette mag zeggen: toch doen.

```yaml
action: climate_director.precondition
data:
  zone_ids: [<zone>]
  minutes: 90
  ignore_openings: true
```

Twee grenzen die je niet kunt vergeten:

- **Het verloopt vanzelf.** Vraag je langer dan het ingestelde maximum, dan
  wordt je verzoek ingekort. Geen tijd opgeven geeft het maximum.
- **Het geldt alleen binnen het venster** (standaard 06:00–23:00). Daarbuiten
  telt een verzoek niet mee.

Afblazen kan met `climate_director.cancel_precondition`.

## Zelf de baas

- **Een apparaat zelf uitzetten** (bij het apparaat of op de afstandsbediening)
  zet die zone stil. De director zet hem niet twee seconden later weer aan. De
  zone doet weer mee zodra je hem zelf aanzet, zodra iedereen die thuis is naar
  bed gaat, of zodra het de volgende dag is.
- **Een apparaat een paar uur met de hand aanzetten** kan gewoon met een script
  ernaast, mits je die zone zolang met de override aan jezelf teruggeeft. Zonder
  override rekent de director bij de eerstvolgende evaluatie zijn eigen plan
  door en zet hij je apparaat weer uit. Een apparaat met *Dit apparaat
  automatisch starten* uit heeft die override niet nodig.
- **Een kamer die je altijd zelf bedient**: maak er tóch een zone van (anders
  weet de integratie niet van dat apparaat af), kies als binnentemperatuursensor
  de `climate.*`-entiteit van het apparaat zelf, en zet bij de bron *Dit
  apparaat automatisch starten* uit.

## Een schaduwrun beoordelen

Drie sensoren maken een schaduwrun achteraf beoordeelbaar:

- **`sensor.*_afwijkingen`** is het kerngetal. Nul betekent dat de director het
  eens is met wat er op dat moment draait. Een korte piek is normaal; een
  waarde die blijft staan is een echt meningsverschil. Zet deze sensor in een
  geschiedenisgrafiek.
- **`sensor.*_zou_<entiteit>_aansturen`** leg je naast de geschiedenis van de
  `climate`-entiteit met dezelfde naam. Twee lijnen die elkaar volgen = de
  director besloot hetzelfde als je automatiseringen.
- **`sensor.*_bron_<zone>`** en **`binary_sensor.*_<zone>_geblokkeerd`**
  vertellen daarna *waarom*: welke bron gekozen werd, en welke poort een zone
  tegenhield.

## Blueprints en meldingen

Climate Director stuurt zelf geen berichten. Waar een melding heen gaat, hoe
hij klinkt en of hij 's nachts mag komen, verschilt per huishouden. In plaats
daarvan zet de integratie gebeurtenissen en melders klaar waar je je eigen
automatisering aan hangt. Drie daarvan zou je niet moeten overslaan:

| Blueprint | Waarom je hem niet kunt missen | Importlink |
|---|---|---|
| **Bewaking** | meldt stil falen: een zone die vastzit, of een zone die op een duurder reserve-apparaat draait | `https://github.com/Sarnog/ha-climate-director/blob/main/blueprints/automation/climate_director/monitoring.yaml` |
| **Geweigerd vooruit-verzoek** | je drukte op een knop en er gebeurde niets; deze meldt het, met een knop *Toch doen* | `https://github.com/Sarnog/ha-climate-director/blob/main/blueprints/automation/climate_director/precondition_refused.yaml` |
| **Wat er besloten is** | het handigste gereedschap bij het instellen en bij een schaduwrun | `https://github.com/Sarnog/ha-climate-director/blob/main/blueprints/automation/climate_director/decisions.yaml` |

Importeren gaat via **Instellingen → Automatiseringen en scènes → Blueprints →
Blueprint importeren**, met de link hierboven.

> **Importeren alleen is niet genoeg.** Een blueprint is een sjabloon; er
> luistert pas iets zodra je er een automatisering van maakt. Doe dat meteen na
> het importeren.

Zolang er niemand naar een geweigerd vooruit-verzoek luistert, staat daar een
reparatiemelding over in Home Assistant. Die verdwijnt vanzelf zodra er een
automatisering op die gebeurtenis staat.

## Problemen oplossen

- **`binary_sensor.*_vastgelopen`** gaat aan als een zone te lang op dezelfde
  wachtreden staat (standaard na 15 minuten), of als een ingestelde entiteit
  niet te lezen is — verkeerd getikt, verwijderd, of tijdelijk `unavailable`.
  Welke entiteiten het zijn staat in het attribuut `unusable_entities`. Een
  sensor die wel leesbaar is maar geen getal oplevert, staat er ook in
  (`no number`).
- **`binary_sensor.*_<zone>_op_reserve`** gaat aan als een zone draait op een
  bron die niet de eerste keus was, omdat de eerste keus onbereikbaar is. De
  kamer wordt gewoon warm — en precies daarom merk je zonder melder niets tot
  de energierekening komt.
- **Reparatiemeldingen** onder *Reparaties* tonen structurele fouten in de
  configuratie. De zones die kloppen worden ondertussen gewoon geregeld; één
  stukke zone legt de installatie niet stil.
- **De diagnose** (downloaden bij de integratie) bevat de configuratie, de
  laatst gelezen momentopname en het laatste plan. Met die drie is elke
  beslissing exact na te spelen.

## Talen

De uitleg onder elk invoerveld volgt de taal van je Home Assistant.
Meegeleverd: Nederlands, Engels, Duits, Frans, Spaans en Arabisch.

[![Koop me een koffie op Ko-fi](https://img.shields.io/badge/Ko--fi-Koop%20me%20een%20koffie-FF5E5B?style=for-the-badge&logo=kofi&logoColor=white)](https://ko-fi.com/sarnog)
[![Sponsor via GitHub](https://img.shields.io/github/sponsors/sarnog?style=for-the-badge&logo=github&label=Sponsors&color=EA4AAA)](https://github.com/sponsors/sarnog)
