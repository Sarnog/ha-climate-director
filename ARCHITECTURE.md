# ARCHITECTURE.md

## NL

Technisch ontwerpdocument voor wie aan de code werkt (geen gebruikershandleiding —
dat is [`README.md`](README.md)). Elke laag heeft precies één verantwoordelijkheid.

**Eenheden:** de engine en de opgeslagen configuratie rekenen in graden Celsius
— dat is de bewuste keuze (de eenheid van Home
Assistant volgen, niet de engine er een tweede stelsel bij geven). De
koppelingslaag is de enige plek die omrekent: de coordinator leest
HA-temperaturen om naar Celsius, de applier zet setpoints terug naar de eenheid
van de gebruiker, het formulier toont en leest in diezelfde eenheid, en de
sensorattributen en het `climate_director_decision`-event publiceren in de
eenheid van de gebruiker (het event met een veld `temperature_unit` erbij).
Een bron wordt gelezen in de eenheid die hij zélf meldt: `unit_of_measurement`
bij een sensor, `temperature_unit` bij een weersbron, en pas anders in het
systeemstelsel. De uitgaande kant — sensorattributen en het event — rondt af
op één decimaal, in beide stelsels. De weergave voor de gebruiker
(`display_temperature`) rondt eveneens af op één decimaal, in beide stelsels
(een bewuste beslissing): zo blijven twee getallen die minder
dan één graad Fahrenheit uit elkaar liggen in de zin van elkaar te
onderscheiden (`67.6 °F` tegenover `68.0 °F`) in plaats van na afronding op
hele graden hetzelfde te lezen en de zin met zichzelf in tegenspraak te
brengen. Eén afrondingsregel voor de hele weergave; een tweede ernaast is
precies de vorm waar dit project zes keer op is gestruikeld. De engine en de
applier rekenen ongeafgerond verder.
**De diagnose blijft Celsius**: dat is een ontwikkelaarsdump, geen
gebruikersweergave.

**Inventarisatielijst "elke tekst voor de gebruiker noemt zijn eenheid"**:
een volgende controle kan aan deze lijst zíén of hij compleet is
in plaats van het te moeten hopen. Elke zin hieronder zet Celsius om met
`display_temperature` — afgerond, met de eenheid erachter:

- `coordinator._wanted` — de reparatiemelding `command_not_taking`;
- `coordinator.unsupported_modes` — de reparatiemelding `unsupported_modes`;
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
breed, dan weer terug. Deze zestien ankers staan daarom hier, vóór alle modules.
Wijk er niet van af zonder ze hier eerst te wijzigen.

1. **Een lopend vooruit-verzoek** is één begrip in de hele engine:
   `world.preconditioning(zone_id)`. Het passeert álles behalve de
   hoofdschakelaar, een override, een openstaande opening waarvoor niemand
   "toch doen" heeft gezegd, en een huisbrede overname die de tegengestelde
   taakfamilie draait: dezelfde ruimte wordt nooit tegelijk verwarmd en
   gekoeld, ook niet op verzoek (anker 12). Er is geen tijdvenster: een
   handmatig verzoek gaat
   altijd boven de automatisering, ongeacht het uur, voor de volledige
   `max_precondition`. De begrenzing is de looptijd van het verzoek zelf plus de
   bevestiging bij een openstaande deur — hetzelfde principe als: wie laat
   opblijft, houdt zijn verwarming. Er zijn twee manieren om dat *toch doen*
   te zeggen: de vlag `ignore_openings` op één verzoek, en de overbrugging per
   opening uit anker 8. Ze betekenen hetzelfde en stapelen niet. Er is
   bewust géén vooruit-venster; een vooruit-venster per weekdag is
   daarom geen idee maar een terugdraaiing van dat besluit.
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
   Daar staat een tweede rem naast: een bron kan een eigen
   `min_cycle_time` dragen (`Source.min_cycle_time`), ook als hij op geen circuit
   zit; leeg of nul betekent geen eigen rem. Een bron op een circuit houdt de
   rusttijd van dat circuit — de eigen rem is een ondergrens per apparaat en
   geldt alleen voor een bron zonder circuit. Dit anker is daarmee **breder**
   geworden: een rusttijd kan nu aan elk apparaat hangen, niet alleen aan een
   apparaat op een circuit; de vaste openingsrust hierboven blijft ernaast
   bestaan. Een overbrugde opening (anker 8) heft deze rust niet op:
   overbruggen is comfort, de rust is branderbescherming.
6. **De hoofdschakelaar uit** betekent: de director laat alles los en stuurt
   niets, ook geen `off` — net als een override. Wie alles uit wil, zet het zelf
   uit; de director laat het dan staan.
7. **Een circuitweigering weigert het apparaat op dat circuit, niet de zone.**
   Valt de eerste keus af met `SHORT_CYCLE_PROTECTION`, `CIRCUIT_AT_CAPACITY` of
   `CIRCUIT_CONFLICT_LOST`, dan dient de zone haar verzoek opnieuw in bij de
   volgende bron — precies zoals bij een onbereikbaar apparaat. De reservebron
   neemt het zichtbaar over (`op_reserve`). Dit anker is breder dan het oude
   gedrag (de zone viel stil) en smaller dan "elke weigering schuift door": een
   eerste keus die huisbreed is stilgezet weigert de zone wél, met
   `OPENING_OPEN_ELSEWHERE`; dat scenario dekt de andere kant.
8. **Een overbrugde opening bestaat niet voor de director.** Staat de
   overbrugging van een opening aan, dan telt hij nergens meer mee: niet voor het
   opschorten van zijn eigen zones, en niet voor de huisbrede stop. Half
   overbruggen bestaat niet. De overbrugging blijft staan tot iemand hem zelf
   terugzet — er is geen looptijd — en zolang hij aanstaat terwijl de opening
   werkelijk openstaat, meldt de integratie dat: anders stook je een winter lang
   met een raam open zonder dat iets het zegt. De rust uit anker 5 loopt er wél
   gewoon door. Een opening draagt hiervoor een eigen `opening_id` én een naam,
   net als elk ander objecttype — zonder eigen identiteit hangt de schakelaar aan
   de `entity_id` van de sensor en verdwijnt hij zodra die sensor vervangen wordt.
   Ontbreekt het id in oudere opslag, dan leidt de serialisatie het af
   uit de `entity_id`, uniek per sensor — twee openingen op dezelfde sensor
   krijgen zo elk een eigen schakelaar. Die afleiding staat op één plek
   (`serialise.opening_ids`) met twee lezers: de opslaglezer en de options
   flow, die de ruwe opslag leest en een ontbrekend id bij het laden invult,
   zodat het opslagscherm het meeschrijft. Zonder die stap leidt het
   bewerkscherm het id af uit de naam die je net intypt, en dan wisselt de
   `unique_id` van de overbruggingsschakelaar: entiteit weg, geschiedenis weg,
   elke dashboardverwijzing stuk. `config_flow._unique_id(naam, ...)` geldt
   daarom alleen nog voor een **nieuwe** opening. Een opening zonder naam heet
   naar zijn id, en omdat dat de `entity_id` is valt de schakelaar dan terug op
   de friendly name van de sensor. Die terugval wordt elke beslisronde opnieuw
   gelezen, niet één keer bij het opzetten: een sensor die pas ná de integratie
   verschijnt, of die later hernoemd wordt, geeft de schakelaar zonder herladen
   zijn nieuwe naam. Home Assistant cachet de naam van een entiteit en maakt die
   cache niet ongeldig als alleen de placeholder verandert, dus de schakelaar
   gooit hem zelf weg zodra het label werkelijk wijzigt (`switch._refresh_label`)
   — dat is een bekende klasse: één momentopname bij het opzetten waar de
   wereld daarna nog kan veranderen. Een opgeslagen dubbel `opening_id` weigert
   `validate()` met `duplicate_opening_id`.
9. **Een vakantiedag telt als zaterdag, behalve waar dat één bewoner het huis
   laat ophouden.** De stiltevensters en de roosters vertalen een vakantiedag naar
   zaterdag, tenzij er vakantievensters zijn opgegeven — die nemen het dan over.
   De uiterste opsta-tijd doet dat uitdrukkelijk **niet**: anders houdt de
   schoolvakantie van de één het huis op terwijl de ander thuis zit te werken. Het
   slaapvenster leest de echte weekdag en weet van vakantie niets. Drie
   verschillende antwoorden, alle drie bewust; wie er één verandert, verandert ze
   niet allemaal.
10. **Een buitengrens is half-open: `[minimum, maximum)`.** Twee vensters die
    aan dezelfde waarde grenzen verdelen de schaal sluitend — geen gat en geen
    overlap, dus geen enkele buitentemperatuur kan tussen twee bronnen vallen.
    Het gevolg is dat een waarde precies óp de grens bij het bovenste venster
    hoort: een grens van 24 koelt ook bij precies 24,0. Een met de hand
    geschreven automatisering die "boven 24" zei is daarmee niet exact na te
    bouwen; de dichtstbijzijnde keuze is de grens zelf, niet 24,1.
11. **Een override met een looptijd draagt zijn eigen einde; een override die je
    met de hand uitzet doet dat niet.** De actie `climate_director.set_override`
    neemt een looptijd én een keuze *bij afloop*: het apparaat uitzetten, of
    laten staan. Verstrijkt de tijd, dan voert de director die keuze uit als één
    commando op dat moment, en daarna beslist hij gewoon weer — dat is het énige
    moment waarop het einde van een override zelf iets stuurt. Zet iemand de
    overrideschakelaar met de hand uit, dan gebeurt er niets bijzonders: de
    engine neemt de zone weer over en het apparaat gaat alleen uit als de
    beslissing dat nodig maakt. Een bron met `autostart: false` blijft dan dus
    draaien tot hij in de weg staat. Diezelfde actie zet de stand en de
    temperatuur zelf, in dezelfde beslisronde als de overdracht: gebeurt dat in
    twee losse aanroepen, dan bestaat er een venster waarin de director het net
    gezette apparaat alsnog wegschakelt, en dan zou de volgorde van die twee
    aanroepen een eigenschap moeten dragen die nergens is vastgelegd. Heeft de
    zone geen bron die de gevraagde stand kan leveren, dan weigert de actie met
    dezelfde vertaalde fout als een onbekende zone (`zone_no_source_for_mode`).
    Het temperatuurveld heeft geen vast bereik in het formulier: de waarde geldt
    in de eenheid van Home Assistant en wordt naar Celsius omgerekend. Wat het
    apparaat zelf aankan is wél een grens: het setpoint wordt geklemd naar
    `min_temp`/`max_temp` van de gekozen bron, met dezelfde regel als het
    engine-pad (`clamped_target`). **Klemmen, niet weigeren** — weigeren zou een
    tweede regel naast de eerste zijn, en dan lopen de twee paden uit elkaar.
    Die klem hangt aan het moment van **versturen**, niet aan het moment van de
    aanroep: tussen die twee kan het apparaat zijn bereik gaan melden of
    juist kwijtraken — een cloud-drop-out laat `min_temp` even verdwijnen — en
    de beslisronde heeft de wereld van dat moment al in de hand. De servicelaag
    rekent daarom alleen nog de eenheid om; de klem staat in de ronde waarin het
    commando de deur uit gaat, waar dezelfde `clamped_target` als op het
    engine-pad geldt. Een aanroep die niets kan zetten weigert nog steeds, met
    `zone_no_source_for_mode`. Naast het einde bewaart de override zijn
    **starttijd** (`zone_override_started`), gezet uit dezelfde kloklezing als
    het einde zelf: twee lezingen naast elkaar zouden een voortgangsring
    opleveren die niet bij zijn eigen eindtijd past. Die starttijd overleeft een
    herstart, en een statusbestand van vóór dit veld laadt gewoon, met een
    onbekende starttijd in plaats van een gegokte. Beide acties nemen naast
    `zone_id` ook een **entiteit** als doel; zonder dat veld in het schema zou
    de annuleerknop van `simple-timer-card` stuklopen op de validatie, want die
    kaart stuurt de sensor zelf als `target.entity_id` mee en Home Assistant
    plakt dat doel vóór de schemavalidatie aan de data. Een entiteit bepaalt dan
    de installatie én de zone; alleen de overrideschakelaar en de eindtijdsensor
    van deze integratie tellen, elke andere entiteit is een typefout en wordt
    geweigerd. Die toets is volledig: de entry moet bestaan en de
    onze zijn, het platform moet dit zijn, het domein moet `sensor` of `switch`
    zijn, en de `unique_id` moet met onze prefix beginnen én pas daarna op het
    patroon passen. Zonder die vier krijgt een entiteit van een andere integratie
    met een look-alike id (`zone_<x>_override`) `unknown_installation` met een
    vreemde `entry_id` erbij, terwijl de opgegeven entiteit deze integratie niet
    eens toebehoort. Wie de override uitzet — de schakelaar, of een van beide
    acties — laat de eindtijdsensor **direct** meeschrijven: de sensor leest zijn
    toestand van de coordinator, dus zonder die stap zou de debouncer er een
    seconde tussen zitten en pas de volgende beslisronde de eindtijd of `unknown`
    tonen.

    **Een override begint met het opheffen van de hand van zijn zone.** Een hand aan
    een apparaat en een override zijn allebei een ingreep van de gebruiker; zet
    iemand na een hand de overrideschakelaar of `set_override` aan, dan is die
    override het jongste oordeel en vervalt de hand van die zone op dat moment.
    Dat is **breder** dan de regel dat alleen dezelfde hand een hand opheft: een
    override is ook een ingreep van de gebruiker, maar dan een die de hele zone
    aangaat. Anders bleef de zone na het einde van de override overgedragen aan een
    hand die allang door een nieuwe ingreep was ingehaald, en bleef het apparaat dat
    de override aanzette ongeregeld draaien tot het huis sliep, leeg was of de
    volgende dag begon. De andere kant blijft staan: de hand vervalt bij het
    **begin**, niet bij het einde, dus een hand die tijdens de override ontstaat
    (iemand zet het apparaat zelf uit) blijft staan en overleeft `clear_override`
    **en een herstart**. Die overleving is **breder** dan de regel dat alleen dezelfde
    hand een hand opheft: ook een herstart laat de hand staan. De uitzondering erop is
    **smaller**: alleen een override die de gebruiker tijdens het opstarten zelf zette,
    heft de opgeslagen hand van die zone op, want die hand was op dat moment nog niet in
    het geheugen. Een override die uit de opslag terugkomt, laat de hand dus staan: die
    hand is tijdens die override ontstaan en is jonger dan het begin van de override.
    En alleen de zone van de override verliest haar hand; een gedeeld apparaat dat
    ook een andere zone bedient, laat de hand van die andere zone staan.

    **Een override draagt elk apparaat van die zone over, huisbreed.** Staat een
    zone onder override — de schakelaar of de actie `set_override` — dan is elk
    apparaat dat in die zone bron is overgedragen: de director stuurt het geen
    enkel commando meer, ook geen aan of uit vanuit een andere zone, en ook niet
    de huisbrede openingsstop. Een override is een noodknop, geen slot, en dat
    geldt voor de hele zone: wie hem indrukt weet iets wat de director niet
    weet. De aanvaarde prijs is even groot als de regel: de "1 uur"-knop van een
    slaapkamer met de cv-thermostaat als tweede bron draagt die ketel dat uur
    over, dus de andere kamers krijgen dan geen gasverwarming en een brandende
    ketel gaat niet uit. Wie de knop indrukt wil die kamer, en een centrale
    installatie is nu eenmaal niet per kamer te verdelen. Dit is **breder** dan
    de zone zelf: de overdracht gaat over de apparaten die er bron zijn,
    huisbreed. De andere kant blijft zoals hij was — een apparaat dat alleen in
    díe zone bron is verandert niets, en zonder override is er geen overdracht:
    staat de schakelaar weer uit, dan neemt de engine de zone en haar apparaten
    gewoon terug. Voor de andere zones is zo'n apparaat geen kandidaat, precies
    zoals `excluding` in `sources.select` er geen is; het staat niet in
    `passed_over` (het is geen storing, dus niet "op reserve"), en een zone
    zonder andere bron meldt `no_source_available`. Een draaiend overgedragen
    apparaat telt als vaststaand (`_standing_firm`) voor het circuit en de
    capaciteit, want er valt niets meer aan te verzetten. De `Generator` houdt
    voorlopig zijn eigen regel — aanzetten mag, uitzetten niet — en dat verschil
    staat als idee in `ROADMAP.md`.

    **Een hand aan het apparaat draagt niet huisbreed over.** Drukt iemand bij het
    apparaat zelf op uit, dan valt de zone stil waarin dat apparaat hangt — elke
    zone die eraan hangt, als het apparaat gedeeld is, want `_zones_of` legt ze
    allemaal stil. Wat er níét gebeurt is een overdracht in de zin van dit anker:
    alleen de schakelaar en de actie `set_override` dragen een zone over, en alleen
    die twee nemen elk apparaat van de zone huisbreed mee. Een gedeeld apparaat
    blijft dus beschikbaar voor de andere zones — de hand zegt iets over de kamer,
    niet over de ketel die er toevallig ook hangt. Wie een gedeeld apparaat echt
    weg wil hebben, drukt op dat apparaat zelf uit, of gebruikt de schakelaar om de
    hele zone over te dragen. Dit anker wordt hier niet breder of smaller van: het
    noemde de schakelaar en de actie al als de twee manieren om over te dragen, en
    dat is wat de code doet. De andere kant blijft zoals hij is: de schakelaar op
    de slaapkamer met de cv-thermostaat als tweede bron draagt die ketel nog
    steeds over, en dan krijgen de andere kamers geen gasverwarming.

    **Een hand vervalt alleen door dezelfde hand, door slapen, door een leeg huis of
    door de volgende dag.** Dat zijn de vier uitwegen, en er is geen vijfde: zet de
    director een apparaat zelf weer aan, dan is dat geen hand aan het apparaat.
    `_notice_hand` heft de hand daarom alleen op als de actieve stand niet van ons
    komt: niet als de wijzigingen van deze ronde (`last_changes`) dat apparaat een
    commando in dezelfde taakfamilie geven, en niet als de boekhouding van een net
    verstuurd aan-commando die stand nog verklaart (een apparaat meldt zijn nieuwe
    stand soms pas een ronde later). Precies zoals `_we_wanted_it_off` een eigen
    uit-commando niet als hand leest. Het plan dat op tafel ligt doet hier niet
    mee: zodra de hand er staat laat de director de zone met rust, dus een plan dat
    dat apparaat vraagt is het plan van vóór de hand — en dan zou dezelfde hand die
    het apparaat weer aanzet zijn eigen hand niet meer opheffen. Zo laat een
    gedeelde ketel die voor de woonkamer aangaat de hand aan de zolder-airco staan:
    dezelfde regel als hierboven, van de andere kant bekeken. Zet iemand het
    apparaat zelf weer aan, dan vervalt de hand voor elke zone die aan dat apparaat
    hangt, zoals altijd. Dit maakt het anker niet breder en niet smaller: het noemde
    de vier uitwegen al, en hier staat welke gebeurtenis er *niet* bij hoort. De
    andere kant blijft zoals hij is: dezelfde hand die het apparaat weer aanzet heft
    de hand op, net als slapen, een leeg huis en de volgende dag.
12. **Het bereik van een bron hangt aan de bron en noemt zones.** Een bron draagt
    `covers_zones`: de zones die hij meeverwarmt of meekoelt zodra hij draait.
    Leeg betekent *alleen de eigen zone* — het gedrag van vóór deze instelling,
    dus een gezoneerde installatie merkt er niets van. Hetzelfde apparaat staat
    vaak als aparte bron onder meerdere kamers; de engine voegt die gebieden
    daarom samen op `entity_id`, precies zoals een uitsluitende groep dat doet
    (`_group_entities`). Eén keer invullen is genoeg. Dit is dezelfde vorm als
    `Generator.zone_ids`, met één bewust verschil: leeg is hier *niets* en daar
    *alles*, want een terugval die standaard aanstaat is geen terugval maar een
    verrassing.

    **De uitspraak die eraan hangt:** valt een beheerde bron in dat gebied weg,
    dan neemt de bron met het gebied de taak over, en levert er in dat hele
    gebied géén ander klimaatapparaat meer warmte of koeling — ook een apparaat
    dat zelf prima bereikbaar is, ook een apparaat dat iemand met de hand heeft
    aangezet. Anders verwarmt de ketel het hele huis terwijl de airco's
    doorstoken, of wordt dezelfde ruimte tegelijk verwarmd en gekoeld. De
    apparaten die zo stilvallen krijgen `SHARED_SOURCE_TOOK_OVER`; de zone met
    de weggevallen bron blijft melden wat er werkelijk aan de hand is
    (`op_reserve`, `SOURCE_UNREACHABLE`).

    **De overname is per taak.** Een overname voor verwarmen gaat alleen in als
    een weggevallen bron in het gebied zelf kon verwarmen; voor koelen idem. Een
    bron die alleen koelt en uit het stopcontact raakt is dus geen reden om het
    gebied van verwarmen te voorzien: de ketel zou anders de hele winter het
    huis op gas zetten — zijn buitenvenster opzij — omdat er een stekker uit
    ligt. Dit maakt de overname **smaller** dan "een bron valt weg, dus neemt de
    vervangende bron het gebied over". De andere kant dekt het bestaande
    scenario: valt een airco weg die zelf ook verwarmt, dan neemt de ketel het
    verwarmen nog steeds over, en de overnemer levert er nog steeds geen andere
    taak naast.

    **Onbereikbaarheid maakt het buitenvenster van de vervangende bron
    voorwaardelijk.** Ligt de buitentemperatuur buiten zijn venster terwijl een
    bron in zijn gebied onbereikbaar is, dan gaat hij alsnog aan. De scheiding
    op buitentemperatuur blijft dus bestaan — die is alleen niet langer een
    reden om een huis koud te laten staan. Dit is een **verbreding**: tot nu toe
    was een buitenvenster onvoorwaardelijk. De andere kant wordt gedekt doordat
    het venster in élke andere situatie gewoon geldt, en doordat een leeg
    `covers_zones` deze uitzondering nergens laat ontstaan.

    **Onbereikbaar is wat de wereld onbereikbaar noemt:** `unavailable`,
    `unknown`, of een entiteit die er niet is — dezelfde definitie die
    `ClimateState.available` al draagt. Een apparaat dat zijn commando niet
    aanneemt telt hier niet mee: dat is bedieningstoestand en die woont buiten
    de engine. De overname wacht `takeover_delay` (standaard vijf minuten, op de
    vervangende bron, nul is meteen) vanaf het moment dat het apparaat
    onbereikbaar werd, zodat een klapperende integratie de brander niet elke
    paar minuten ontsteekt. Is dat moment onbekend, dan is er niets om op te
    wachten en gaat de overname meteen in. Het terugschakelen ná herstel krijgt
    géén eigen rem: dat is `Source.min_cycle_time` en de openingsrust uit
    anker 5, en een tweede rem naast die twee is precies hoe deze engine eerder
    twee bijna-gelijke paden kreeg.

    **Een handbediende bron is geen trigger.** Alleen een bron die de director
    zelf zou aanzetten (*Dit apparaat automatisch aanzetten* aan) telt als
    "beheerde bron in het gebied". Een bron met dat vinkje uit kan de director
    niet kwijtraken — hij zou hem nooit gestart hebben — dus haar uitval is
    geen verlies dat een overname rechtvaardigt; anders zet één losse stekker
    van een slaapkamerairco het hele huis op gas. Dit is een **versmalling**,
    per bronrij: staat hetzelfde apparaat onder een andere kamer wél met
    automatisch aanzetten, dan telt díe rij gewoon mee, want daar zou de
    director hem wel starten. De andere kant blijft zoals hij was: wordt het
    gebied om een ándere reden overgenomen, dan wordt een draaiende
    handbediende bron nog steeds stilgezet.

    **Dit anker verbreedt anker 7 aan één kant.** Daar staat dat een
    circuitweigering het apparaat weigert en niet de zone, met als uitzondering
    dat een huisbreed stilgezette eerste keus de zone wél weigert
    (`OPENING_OPEN_ELSEWHERE`). De huisbrede overname is de tweede zo'n
    uitzondering: een apparaat dat hierdoor stilstaat laat zijn zone niet
    doorschuiven naar een volgende bron, want dan verwarmde die kamer alsnog
    elektrisch binnen een gebied dat de ketel al warm maakt.

    **Wat het niet is.** Het vervangt de uitsluitende groepen niet en bouwt er
    niet op voort: die blijven een handmatige uitsluiting, beslecht op
    zonevoorrang. De overname werkt ervóór — hij haalt de apparaten uit de
    wensen, zodat de groep daarna niets meer te kiezen heeft. Laat je de groep
    beslissen, dan wint de airco op voorrang, valt het gas uit met
    `other_source_chosen` en houdt de kamer met de kapotte airco
    `exclusive_group_lost` over: een koud huis in plaats van een duur huis. De
    director herstelt verder geen handmatige stand — een apparaat dat hierdoor
    uitging blijft uit of gaat verwarmen als de regeling dat vraagt, maar keert
    nooit uit zichzelf terug naar koelen. En is de vervangende bron zélf
    onbereikbaar, dan valt er niets over te nemen: er wordt niets stilgezet en
    de gewone bronkeuze doet zijn werk.
13. **Een stiltevenster remt alleen wie er ná het begin van dat venster
    thuiskomt.** Was minstens één bewoner al thuis vóórdat het venster begon, dan
    is er geen stilte: de zones regelen gewoon door, ook als hun apparaat op dat
    moment toevallig uit stond. Komt er in een leeg huis iemand thuis ná het
    begin, dan blijft het stil tot het venster afloopt — precies het gedrag van
    vóór dit anker. Dit anker maakt het stiltevenster dus **smaller**: het remt
    niet langer iedereen, alleen nog thuiskomers; het lege huis met een aankomst
    ná het begin dekt de andere kant en blijft stil.
    Twee losse voorwaarden, en het hoeven niet dezelfde bewoners te zijn: "iemand
    was al thuis vóór het begin" en "iemand is nu wakker". De slaappoort
    (`EVERYONE_ASLEEP`, `WAITING_FOR_SLEEPER`) blijft ongewijzigd en doet het
    tweede; dit anker gaat alleen over thuis-sinds.
    Het thuiskomstmoment staat per bewoner (`home_since`) en overleeft een
    herstart van Home Assistant: het wordt bewaard en teruggelezen, een herstart
    genereert **geen** nieuw moment, en wie bij het terugkomen niet meer thuis is
    verliest het. Zonder opgeslagen moment valt de lezer terug op HA's
    `last_changed` van de aanwezigheidsentiteit; direct ná een herstart is dat het
    herstartmoment, en dan telt de bewoner tot het einde van het venster als "net
    thuis" — de stille, veilige kant, die hoogstens één keer bijt.
    Gastenmodus heft de stilte op, maar alleen binnen het gastenvenster:
    `_guests_carry_the_house` zegt al precies wanneer gasten het huis dragen, en
    buiten dat venster gelden de gewone regels.
    Wat "vóór het begin" betekent: `home_since` ligt vóór het begin van de
    **lopende venstervoorkomst**. Precies op het begin (21:00:00) telt als ná het
    begin. Een venster over middernacht begint op zijn startdag — om 02:00 dinsdag
    is het begin maandag 21:00 — en voor een vakantievenster (`holiday`,
    `any_day`) geldt hetzelfde met de dag waarop het venster begon. Wie ná het
    begin vertrekt en weer terugkomt is een thuiskomer: het moment vervalt bij
    vertrek en wordt bij terugkomst opnieuw gezet.
    Eén `home_since` per bewoner, en **beide** lezers gebruiken hem:
    `gates._quiet_hours` en de slaap-vs-thuiskomst-vergelijking in
    `world_builder._resident` (een slaapmelding telt alleen als hij van ná de
    thuiskomst is). Na een herstart met een opgeslagen moment is
    `sleeper.last_changed` (het herstartmoment) ≥ dat moment, dus de slaapmelding
    telt — dezelfde uitkomst als vóór dit anker.
    De bestaande uitzonderingen blijven precies zoals ze zijn: een open
    roostervenster van een bewoner die thuis is, en een lopend vooruit-verzoek.
    De zonepoort (`PRESENCE`, de zolder) verandert niet: de stilte is huisbreed,
    en de kamerpoort blijft ná de stilte gelden.
    `home_since` is "wie was wanneer thuis" en wordt in de diagnose **gelakt**,
    net als `home` en `asleep`.

14. **De reden van een zone die stopt, hoort bij de taak die draaide.** Weigeren
    verwarmen en koelen allebei en draaide er net één van de twee, dan zegt díe taak
    waarom ze stopt: koelen dat stopt omdat de kamer koel genoeg is, meldt
    `satisfied`, ook als verwarmen op dat moment niet zou mogen van het buitenweer.
    Dit anker maakt de reden **smaller** dan "de informatiefste weigering van de
    twee". Een zone die niets deed houdt die rangorde (`_best_refusal`), en ook een
    taak die de zone niet kent - koelen met de hand in een zone zonder koelen - valt
    erop terug. De taak reist met de reden mee (`Demand.duty`, `ZoneDecision.duty`,
    buiten de gelijkheid), zodat de melding bij `outdoor_outside_window` kan zeggen of
    het buiten te warm is om te verwarmen of te koud om te koelen. Een reden uit een
    poort, een circuit of een groep heeft geen taak.
15. ***Wacht op deze slaper tot* geldt voor de ochtend na een nacht waarin het huis
    sliep.** Het huis gaat slapen op het moment dat iedereen die thuis is slaapt
    (`night.house_asleep_since`); zolang er thuis nog iemand op is, houdt een slaper
    niemand tegen, ook niet na middernacht. Het moment (`WorldState.asleep_since`)
    blijft staan zolang het in de lopende nacht van minstens één bewoner **met** een
    slaapvenster valt: wie om drie uur even opstaat, of 's ochtends als enige thuis
    opstaat, maakt de nacht niet ongedaan, en wie 's avonds laat nog op is houdt het
    moment niet vast. Valt het erbuiten, dan is het weg - in een huis waar niemand een
    slaapvenster heeft is de grens tussen twee nachten het moment zelf, dus daar
    vervalt het zodra niemand thuis meer slaapt. Een
    slaper wacht alleen op een moment ná de laatste start van zijn eigen
    slaapvenster (`night.slept_tonight`), dus het moment van vrijdagnacht telt
    zaterdagnacht niet. Dit anker maakt het wachten **smaller** dan "thuis, slapend
    en vóór de uiterste tijd van vandaag"; de avond ervoor dekt de slaappoort
    (`EVERYONE_ASLEEP`), zoals altijd. Het moment overleeft een herstart via de
    opslag. Is het onbekend, bijvoorbeeld na een herstart terwijl iemand op was, dan
    wordt er niet gewacht, en zodra iedereen slaapt wordt het alsnog vastgelegd. Een
    bewoner die thuis is zonder slaapsensor slaapt nooit, dus zo'n huis gaat nooit
    slapen en wacht 's ochtends op niemand. Zo'n bewoner is altijd wakker, dus de
    opsta-rem van een ander remt daar niet, tenzij de bewoner zonder slaapsensor zelf
    ook geremd wordt (anker 16). In de diagnose wordt het moment gelakt, net als
    `home_since`. Een **handstart** maakt dit wachten smaller: een zone die
    iemand zelf start passeert `WAITING_FOR_SLEEPER` tot het wachten voorbij is.
    De andere kant blijft: zonder handstart verandert er niets, en een handstart
    passeert `EVERYONE_ASLEEP` nooit - de hele nacht is geen ochtendwacht.
16. ***Opstaan zet het huis pas aan vanaf* remt het opstaan van één bewoner, en
    alleen het beginnen.** Vóór die tijd, op de dagen van de rem (`RiseBrake`), telt
    die bewoner niet als "op" voor de wakker-poort; telt daardoor niemand als op, dan
    start het huis niet, met `EARLY_RISER`. Staat een ander op zonder rem, dan start
    het huis gewoon. De rem geldt nooit op een vakantiedag. Voor een bewoner **met**
    een slaapvenster remt ze alleen wie **opstaat**, dus na een nacht waarin het huis
    sliep (anker 15): wie 's avonds laat nog op is en een onbekend moment worden daar
    niet geremd. Zonder slaapvenster valt er geen nacht te lezen - de slaapsensor
    telt dan de klok rond - en telt die bewoner op de remdagen vóór de remtijd niet
    als op, ook als het moment van het huis onbekend is. De aanvaarde prijs daarvan:
    wie in zo'n huis 's nachts nog op is, start het huis niet vóór de remtijd. Het is
    een rem op beginnen: een zone die al draait, regelt door. Gastenmodus binnen het
    gastenvenster heft de rem op, een vooruit-verzoek gaat er altijd voor, en het
    stiltevenster en de roosters zijn niet geraakt. *Wacht op deze slaper tot* blijft
    ernaast gewoon gelden. Een **handstart** maakt de opsta-rem smaller: de zone
    passeert `EARLY_RISER` tot de rem voorbij is. De andere kant blijft: zonder
    handstart verandert er niets, en de handstart passeert de hoofdschakelaar,
    openingen, buitengrenzen, het seizoen, de kortcyclus en de circuits nooit.

    **Met de hand starten.** Zet iemand zelf een apparaat aan - aan het apparaat,
    of met de knop *Met de hand starten* per zone - terwijl zijn zone op
    `WAITING_FOR_SLEEPER`, `EARLY_RISER` of `QUIET_HOURS` wacht, dan noteert de
    coordinator een handstart voor die zone. Een actieve stand die van de director
    zelf komt telt niet, en een bron met *Dit apparaat automatisch aanzetten* uit
    ook niet: daar regelt de director het aanzetten nooit, dus valt er geen
    wachttijd te overbruggen. Een gedeeld apparaat start elke zone die het
    bedient. De zone passeert die drie remmen en verder niets. De handstart vervalt
    in de eerste leesbare ronde waarin die drie de zone ook zonder hem doorlaten,
    en verder bij slapen, een leeg huis of de volgende dag. Een ronde met een
    onleesbare aanwezigheids- of slaapsensor laat hem staan (zie hieronder). Hij
    overleeft een herstart tot dan. In een zone zonder wachtreden doet hij niets.

### Een onleesbare invoer laat een handstart staan

De drie wachtrema's lezen vier soorten invoer. Twee zijn een sensor per bewoner,
één is de feestdagenagenda, en de rest is klok en ingesteldheid. Zonder lezing is
er geen antwoord op "is hij thuis" of "slaapt hij", en wat de engine dan leest is
een gekleurde gok: een onbekende aanwezigheid leest als weg, een onbekende
slaapsensor als wakker, en een onbekende agenda laat de dag als werkdag lezen.

| invoer | extern? | voedt | zonder lezing | telt mee |
|---|---|---|---|---|
| aanwezigheidsentiteit per bewoner | ja, entiteit | `QUIET_HOURS` (thuis en `home_since`), `WAITING_FOR_SLEEPER` en `EARLY_RISER` (thuis), en de leeg-huis-poort | leest als weg; de wacht en de opsta-rem kunnen verdwijnen en het huis kan als leeg gelden; `QUIET_HOURS` blijft dan juist staan | ja, als de bewoner een aanwezigheidsentiteit heeft |
| slaapsensor per bewoner | ja, entiteit | `WAITING_FOR_SLEEPER` en `EARLY_RISER` (slapend/op), en via `asleep_since` de nacht | leest als wakker; de wacht op de laatste slaper kan verdwijnen; de opsta-rem kan verschuiven omdat iemand als op telt | ja, als de bewoner een slaapsensor heeft |
| feestdagenagenda's (`holiday_calendars` met `holiday_keyword`) | ja, entiteit | `holiday_mode`, en daarmee de uiterste tijd, het stiltevenster, de opsta-rem en de roosters | `holiday_mode` valt terug op de schakelaar; op een vakantiedag leest de dag als werkdag | ja, als er een trefwoord én minstens één agenda is |
| gastenmodus-schakelaar | nee, eigen staat | `QUIET_HOURS` (de gastenmodus heft de stilte op) | niet van toepassing | nee, nooit onleesbaar |
| vakantiemodus-schakelaar | nee, eigen staat | `holiday_mode` | niet van toepassing | nee, nooit onleesbaar |
| klok | nee | alle drie | niet van toepassing | nee, altijd leesbaar |
| roosters, slaapvenster, uiterste tijd, opsta-rem, stiltevensters en gastenvenster | nee, ingesteldheid | alle drie | niet van toepassing | nee, altijd leesbaar |
| `asleep_since` | afgeleid van de slaapsensoren | `WAITING_FOR_SLEEPER` en `EARLY_RISER` | onbekend; er wordt niet gewacht | via de slaapsensoren |
| `home_since` | afgeleid van de aanwezigheid | `QUIET_HOURS` (anker 13) | blijft staan; een onleesbare stand is geen vertrek | via de aanwezigheidsentiteit |

Het model is één verzameling `UnreadableInput(kind, subject)` in
`WorldState.unreadable`. `ReadableInput` kent drie soorten: `PRESENCE` en `SLEEP`
met de bewoner als `subject`, en `HOLIDAY` zonder subject omdat de agenda aan het
huis hangt. De koppelingslaag vult de verzameling in `readability.py`; de engine
leest haar in `hand_start.brakes_readable`. Er is geen derde los vlaggetje: een
nieuwe externe invoer is een nieuwe `ReadableInput` plus een regel in de vulling.
Elk veld van `WorldState` staat in precies één van drie klassen
(`BRAKE_INPUT_FIELDS` met zijn soorten, `EXTERNAL_WORLD_FIELDS`,
`INTERNAL_WORLD_FIELDS`, alle drie in `tests/test_hand_start.py`), en
`test_every_world_field_is_classified` valt om zodra een veld in geen van de drie
staat; `test_every_readable_input_belongs_to_a_field` valt om bij een soort zonder
veld. Een nieuw veld kan dus niet ongemerkt
verschijnen, maar de bewaking kan niet weten of een veld in `EXTERNAL_WORLD_FIELDS`
de remmen toch voedt: dat blijft een bewuste keuze van wie het veld toevoegt, met
de invoerentabel hierboven als maat.

Een handstart vervalt daarom niet in een ronde waarin een van deze invoeren geen
lezing heeft. Onleesbaar betekent hier: de entiteit ontbreekt, of haar stand is
`unavailable` of `unknown`; iedere andere stand is een lezing, ook `none`,
`not_home` of `off`. Alleen invoeren die deze installatie werkelijk gebruikt
tellen: een bewoner zonder sensor levert geen invoer, en de agenda's tellen
alleen met een trefwoord. Zodra alle invoeren weer leesbaar zijn, geldt de gewone
regel in die eerste leesbare ronde: houden de drie remmen de zone nog, dan blijft
de handstart; laten ze de zone door, dan vervalt hij. De drie uitwegen die niets
met de remmen te maken hebben blijven: slapen (iedereen die thuis is naar bed),
een leeg huis en de volgende dag. Ook de eerste twee worden alleen uit een
leesbare wereld afgeleid; de volgende dag is de harde grens voor een sensor die
nooit terugkomt. De opslag blijft versie 1 en een bestand zonder `hand_starts`
leest nog steeds als geen handstart.

De koppelingslaag levert de leesbaarheid als gewone data in `WorldState`; de
engine beslist wat dat voor de remmen betekent. Zo blijft `engine/` vrij van Home
Assistant en van I/O. Een korte nalooptijd is niet gekozen: die verschuift
hetzelfde probleem naar een willekeurig moment, laat een handstart alsnog vallen
wanneer de sensor na de nalooptijd terugkomt, en vraagt een tweede grens naast de
volgende dag. Onleesbaarheid is geen termijn maar het ontbreken van een meting,
en de volgende dag begrenst al wat nooit terugkomt.

Een onleesbare aanwezigheid is ook geen vertrek: het thuiskomstmoment blijft
staan zolang er geen lezing is. Anders zou de slaapsensor na terugkeer als
verouderd gelden en zou de wacht alsnog verdwijnen, waarmee de onleesbare ronde
alsnog de handstart zou vellen.

In de diagnose en de beslissensor verandert niets: zij noemen nog steeds alleen
de zone-ids onder `hand_starts`. Er is geen nieuwe `Problem`-code en geen nieuwe
entiteit.

### Wat de koppelingslaag rechtzet

De diagnose lakt ook `sleep_in` weg en laat aanwezigheids- en slaapentiteiten uit
`tracked_entities`, zodat een download geen bewonersprofiel via de entiteitenlijst
alsnog prijsgeeft. `stored_state.py` draagt de publieke `stored_time` en
`restore_commanded_off`; `state_store.py` bewaart `commanded_off` en herstelt het
alleen binnen `COMMANDED_WINDOW`, zodat een oude uitzetting geen late melding meer
verklaart. De overbruggingsschakelaar schrijft alleen bij een echte stand- of
naamwijziging. `set_override` keurt eerst alle doelen en past er daarna pas een
toe. Bij een gedeeld apparaat noemt `engine/untouched.py` de zone met de override,
niet de eerste zone die het apparaat toevallig ook draagt.

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

De regels die deze vorm in stand houden — en de plekken waar de code ze vandaag
niet haalt — staan verderop onder "Uitbreidbaarheid — de vorm die dat mogelijk
maakt".

### Overzicht

```
config_flow.py         wizard; schrijft één dict in entry.options
  schemas.py            bouwt per scherm het vol.Schema uit de huidige waarden
      │
      ▼
engine/serialise.py    dict → dataclasses (puur, vergevingsgezind)
engine/fields.py       declaratieve veldtabel (naam, type, standaard, vertaling, doel)
      │
      ▼
Home Assistant (entiteitstoestanden, klokgebeurtenissen)
      │
      ▼
  coordinator          verzamelt toestanden, ontdubbelt, serialiseert
    state_store.py     opslag, herstel en quarantaine van wat een mens zei
    stored_state.py     bewaarde momenten en de eigen uitzetting
    preconditions.py   vooruit-verzoeken en hun timers
    overrides.py       override met looptijd en het opheffen van een hand
    room_presence.py   de kamerpoort: bezette kamers en de nalooptijd
    resident_reader.py de lezer van één bewoner: thuis, slaap, thuiskomst
    hand_start.py      de handstart: herkenning, opslag en verval
    readability.py     de ene lezing van onleesbaarheid
    world_builder.py   de momentopname (build_world)
      │
      ▼
  world.WorldState     momentopname: één dataobject, verder niets
      │
      ▼
┌─ engine/ ────────────────────────────────────────────────────────┐
│                                                                  │
│  hand_start.py  wachtrema's, leesbaarheid en hertoets            │
│  gates.py       mag er geregeld worden (omstandigheden)          │
│      │                                                           │
│      ▼                                                           │
│  hysteresis.py  moet er geregeld worden (temperaturen)           │
│      │                                                           │
│      ▼                                                           │
│  takeover.py    wie het gebied van een weggevallen bron overneemt│
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
│    resident_storage.py  de ochtendinstellingen van een bewoner   │
│  validation.py  validatieregels buiten het model                │
│  untouched.py   welke zone een gedeeld apparaat met rust laat    │
│  night.py       de nacht: wie slaapt, sinds wanneer, wie opstaat │
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
kortcyclusbescherming), bewoners (met `home_since`: wanneer iemand thuiskwam),
openingen en per circuit wanneer de huidige taak begon.

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

De kamerpoort kent een nalooptijd: een kamer die net leeg werd, telt nog
`presence_timeout` seconden als bezet, zodat iemand die de deur uitloopt niet meteen
de verwarming voelt afslaan. Die tijd begint bij een **vertrek**: de overgang van
bezet naar niet-bezet, en ook de overgang van bezet naar `unavailable` of `unknown`.
Wegvallen is geen bewijs van leegte, maar een kamer die bezet was en onleesbaar wordt,
kan net leeg zijn geraakt; de teruggekeerde sensor beslist daarna. Dat is **breder** dan
de regel dat alleen een leesbare overgang naar niet-bezet telt: een bezette kamer waarvan
de sensor wegvalt, loopt nu hoogstens de nalooptijd door in plaats van meteen leeg te
tellen. De andere kant is **smaller**: een kamer die al onleesbaar was en daarna
niet-bezet wordt, krijgt geen verse nalooptijd, en een onleesbare sensor zonder bezet
moment ervoor telt als leeg. De coordinator bewaart in de opslag per zone het
vertrekmoment en welke kamers bezet waren, en `world_builder._presence` geeft dat
moment door in plaats van `last_changed`. Is een kamer bij het herstel nog onleesbaar terwijl zij
bezet was, dan begint haar nalooptijd op het herstelmoment. Zonder bewaard moment is het
moment onbekend, en dan telt de kamer als leeg: een lege kamer met rust laten is de
onschadelijke kant om fout in te zitten. Een kamer zonder nalooptijd telt bij het
wegvallen meteen als leeg.

De slaappoort kent twee standen. Is er niemand op, dan is dat `EVERYONE_ASLEEP`. Staat er
wél iemand op terwijl een ander thuis nog slaapt, dan geldt de uiterste opsta-tijd van die
slaper (`Resident.wake_deadline`): vóór dat tijdstip houdt hij het huis tegen met
`WAITING_FOR_SLEEPER`, daarna niet meer. Geen uiterste tijd is de stand van vóór die
instelling — dan opent de eerste die opstaat het huis. De tijd staat met opzet los van het
rooster: een roostervenster zegt óók wanneer het huis weer uit moet, deze tijd zegt alleen
tot wanneer je op iemand wacht.

Dat wachten geldt pas als het huis deze nacht geslapen heeft (anker 15): een slaper houdt
niemand tegen zolang er thuis nog iemand op is. En staat iedereen die op is te vroeg op
(`Resident.rise_brake`, anker 16), dan is dat `EARLY_RISER`, maar alleen voor een zone die
nog niet draait: `_household` krijgt daarvoor mee of de zone draait.

De slaapsensor zelf kent twee grenzen. Het **slaapvenster** is de nacht: daarbinnen
betekent "telefoon op de lader" dat iemand in bed ligt, en het is dat venster dat het huis
om bedtijd uitzet. **`Resident.sleep_in`** rekt daar alleen de ochtend van op, op de dagen
die dat mogen. Die twee staan bewust los: één venster kan de twee taken niet doen. Trek je
het door tot een uur of één, dan telt de lader ook op een woensdag als slapen en blijft het
huis uit terwijl er iemand thuis werkt; knip je het terug tot het weekend, dan zet niets
het huis doordeweeks 's nachts nog uit. De dagen van `sleep_in` hangen aan de **ochtend**
en niet aan de avond ervoor - anders erft deze instelling de middernachtverankering van
`TimeWindow`, en dat is een val die niemand verwacht.

En één laag lager, in de koppelingslaag: **thuiskomen is geen slapen**. De slaapsensor kent
opstaan, niet thuiskomen. `ClimateDirectorCoordinator._resident()` telt een slaapmelding
daarom alleen als die van ná de thuiskomst is; wie binnenkomt met zijn telefoon nog aan de
lader in de auto, is klaarwakker. Bij gelijke tijdstempels - na een herstart draagt alles
hetzelfde moment - telt de melding wél, want opschorten is de onschadelijke kant.

**Een vakantiedag telt voor deze tijd niet als zaterdag**, anders dan bij de roosters. Dat
is een bewuste versmalling: de vakantie van de één is de werkdag van de ander, en telde een
schoolvakantie als zaterdag, dan hield de uitslaper het hele huis op terwijl de ander thuis
zat te werken — inclusief de kamer waar diegene zat. De dagen van `WakeDeadline` betekenen
dus letterlijk wat er staat. De andere kant wordt gedekt door `WakeDeadline.holiday`: wie
ook op een vrije doordeweekse dag gewacht wil worden, zet die vlag, en dan geldt de tijd op
elke vakantiedag ongeacht de weekdag. Een vakantie-zaterdag blijft in beide gevallen een
zaterdag, want die dag ís een zaterdag.

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

De **stiltevensters** remmen het beginnen, niet het doorgaan: wat al draait houdt zijn
gewone regeling. Ze kennen drie uitzonderingen, in deze volgorde:
gastenmodus binnen het gastenvenster (`_guests_carry_the_house`), een bewoner die al
thuis was vóór het begin van dit venster (`home_since < started_at`), en het bestaande
open roostervenster van een bewoner die thuis is. Wie in een leeg huis ná het begin
thuiskomt, blijft stil tot het venster afloopt; dat is de andere kant van anker 13.
Een **handstart** maakt ook dit venster smaller: de zone die iemand zelf start
passeert `QUIET_HOURS` tot het venster voorbij is. De andere kant blijft: zonder
handstart verandert er niets, en de handstart passeert de hoofdschakelaar, een
opening of de kamerpoort nooit.

### night.py — de nacht van het huis

Alles over de slaap van het huis op één plek, puur en zonder Home Assistant: wie als
slapend telt (`asleep_at`, `asleep`: de slaapsensor binnen het slaapvenster, met het
uitslapen erbij), wanneer de lopende nacht van een bewoner begon (`night_began`: de laatste
start van zijn slaapvenster), of het huis in die nacht geslapen heeft (`slept_tonight`),
het bijhouden van dat moment ronde na ronde (`house_asleep_since`, anker 15) en de
opstaan-rem (`rise_braked`, anker 16). `gates.py` leest het; de koppelingslaag bewaart het
moment en geeft het de engine terug in `WorldState.asleep_since`.

`slept_tonight` kijkt ook naar de bewoner zelf. Een moment dat meer dan vierentwintig uur
oud is telt niet, en een bewoner die pas thuiskwam nadat het huis ging slapen heeft die
nacht niet meegeslapen. Het thuiskomstmoment (`ResidentState.home_since`) komt uit de
koppelingslaag; is het onbekend, dan blijft de oude uitkomst staan. Zo kan een late
thuiskomer het huis 's ochtends niet tegenhouden en telt een achtergebleven moment van
gisteren niet als nacht.

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

Weigeren beide taken, dan zegt de taak die net draaide waarom ze stopt (anker 14); alleen
een zone die niets deed krijgt de informatiefste van de twee weigeringen. Elk antwoord zegt
voor welke taak het geldt (`Demand.duty`).

### takeover.py — wie het overneemt

Anker 12 als eigen module. `in_force()` zegt vóór de bronkeuze wélke overnames er
op dit moment gelden: een bron met een gebied (`covers_zones`) neemt over zodra
een beheerde bron in dat gebied onbereikbaar is en dat lang genoeg
(`takeover_delay`, geteld vanaf het moment van uitvallen; een onbekend moment is
meteen). De gebieden worden samengevoegd op `entity_id`, precies zoals een
uitsluitende groep dat doet — hetzelfde apparaat staat vaak als aparte bron onder
meerdere kamers, en één keer invullen hoort genoeg te zijn.

De twee gevolgen hangen aan verschillende momenten, en daarom staan ze als twee
functies naast elkaar. `narrowing()` is invoer voor `sources.select()`: in het
gebied is de overnemer de énige kandidaat en telt zijn buitenvenster deze ronde
niet. `stop_others()` draait ná het plan, want het hangt eraan of de overnemer
werkelijk een taak kreeg: pas dan kan dezelfde ruimte tegelijk verwarmd en
gekoeld worden, en pas dan stookt een airco mee in een kamer die de ketel al warm
maakt. Wat daardoor stilvalt draagt `SHARED_SOURCE_TOOK_OVER`.

Een tweede functie, `area_clash()`, hoort bij hetzelfde gebied maar gaat over een ander
moment: de keuze tussen de ketel en een ander apparaat dat in zijn gebied wil draaien,
terwijl er niets is weggevallen. Een bron met `covers_zones` verwarmt zijn hele gebied, ook
de kamers die er zelf niet om vroegen. Houdt de ene kamer een airco vast op de dode band en
kiest een andere kamer in datzelfde gebied de ketel, dan draaien ketel en airco naast
elkaar. `area_clash()` laat daarom per gebied één kant over: het verzoek met de meeste
voorrang (bij gelijke rang de ketel). Wint de ketel, dan vervallen de verzoeken van andere
apparaten in het gebied; wint een ander apparaat, dan vervalt elk verzoek om de ketel. De
verliezers worden teruggegeven in plaats van weggegooid, zodat het plan kan melden wat ze
wilden (`EXCLUSIVE_GROUP_LOST`). De functie draait binnen `apply_exclusive_groups()`, vóór
de groepen, en slaat een apparaat over dat het gebied al overneemt: dat regelt
`stop_others()`. Dit is een bewuste keuze voor een koude kamer boven twee systemen
tegelijk. Wat er niet onder valt staat onder "Nog te bouwen".

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

`select()` laat ook een overgedragen apparaat vallen (`excluding`), precies zoals een
huisbreed stilgezet apparaat, en `passed_over` noemt het niet. Een overdracht is geen
storing maar een besluit van de gebruiker, dus zo'n apparaat hoort niet als "op reserve" op
het scherm. Wat er naast ligt blijft staan: een onbereikbare bron die voorrang had op de
gekozen bron staat nog gewoon in die lijst, ook als er een overgedragen apparaat tussen zit.

### constraints.py — wat mag tegelijk

`constraints.py` lost de verzoeken van één circuit op. De taakkeuze (`active_family`, de
afgedwongen taken en de keuze tussen twee taken) staat in `circuit_policy.py`, de capaciteit
en de kortcyclus in `capacity.py`, en het verzoek, de toekenning en de uitkomst in
`circuit_requests.py`.

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

De **hoofdschakelaar is een noodknop**, geen uitknop (een bewuste beslissing):
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
bezet het handbediende apparaat zelf de plek (`keeps_claiming` telt hem mee) en krijgt
de tegenstander blijvend `CIRCUIT_AT_CAPACITY`; dat blijft bewust
zo. Een exclusieve groep waarvan de leden dezelfde buitenunit delen kan zichzelf dus
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
`validate()`, niet uit een exception hier. De vertaling zelf is verdeeld over
`installation_storage.py` (algemene velden), `equipment_storage.py` (apparaten en
gebieden), `resident_storage.py` (de bewoner en zijn ochtend) en
`storage_values.py` (veilig lezen); `serialise.py` is de ingang.

Booleans worden expliciet níét als getal gelezen: `True` is in Python een `int`, en een
prioriteit van `True` zou stilletjes 1 worden.

De drie ochtendinstellingen van een bewoner - *Uitslapen tot*, *Wacht op deze slaper tot*
en *Opstaan zet het huis pas aan vanaf* - lezen en schrijven in `resident_storage.py`, met
één regel voor alle drie: zonder tijd is er geen instelling, ook als er dagen staan.

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

De klasse bestaat uit de coördinator en een reeks mixins die elk één onderwerp
dragen. `state_store.py` bewaart, herstelt en quarantaineert wat een mens met de
hand heeft gezegd — een vooruit-verzoek en een apparaat dat iemand zelf uitzette —
en herstelt het thuiskomstmoment (`home_since`), `resident_reader.py` leest één
bewoner (thuis, slapend, leesbaarheid) en houdt zijn thuiskomstmoment bij,
`preconditions.py` beheert de vooruit-verzoeken en hun timers, `overrides.py`
beheert de override met zijn looptijd en heft bij zijn begin de hand van zijn zone
op, `room_presence.py` houdt bij welke kamers bezet zijn en wanneer een kamer leeg
werd of wegviel (de nalooptijd van de kamerpoort, ook over een herstart heen),
`hand_start.py` herkent de handstart aan het apparaat of aan de knop, bewaart hem
over een herstart en laat hem vervallen, en `world_builder.py` bouwt de
momentopname met zijn lezers, waarin `reads_as_home` de enige plek is die een
aanwezigheidsentiteit als thuis leest; de coördinator zelf luistert, beslist,
voert uit en publiceert.

Zes dingen zijn er subtiel aan:

- **Alles in lokale, tijdzonebewuste tijd.** Roostervensters worden in lokale tijd gelezen,
  terwijl tijdstempels van entiteiten in UTC binnenkomen. Die twee mengen zou de leeftijd
  van een openstaande deur uren verschuiven.
- **Circuitgeschiedenis komt uit waarnemingen, niet uit het vorige plan.** Een unit die
  iemand met de afstandsbediening omzet verandert de taak van een circuit net zo goed als
  de director, en de minimale-looptijdtimer hoort dat te respecteren.
- **Het thuiskomstmoment komt uit bewegingen, niet uit een lezing.** Wie thuiskomt zet het
  moment, wie weggaat verliest het, en bij het opstarten vult de opslag het aan of valt het
  terug op `last_changed` van de aanwezigheidsentiteit. Eén moment voor de stiltepoort én
  voor de bestaande slaap-vs-thuiskomst-vergelijking, en in de diagnose gelakt.
- **Eén event per zone, en alleen bij verandering.** Er wordt herrekend bij elke
  toestandswijziging van elke gevolgde entiteit; elke keer vuren zou elke automatisering
  die erop luistert verzuipen.
- **Dat event draagt de beslissing ook in gewone taal.** Naast de identifiers staan er
  `reason_text`, `action_text`, `source_name` en `message`: de reden als zin, wat er met het
  apparaat gebeurt, de naam zoals de gebruiker die ziet, en de kant-en-klare melding die de
  blueprint standaard toont. De zinnen komen uit `texts.py`; de identifier blijft het
  contract — wie op `reason` filtert merkt van die vier velden niets. De actie volgt het
  commando dat het plan dit apparaat geeft, niet de reden: een zone die door een poort wordt
  tegengehouden krijgt evengoed een stand, en "met rust gelaten" zeggen terwijl het apparaat
  wordt uitgezet is een leugen die de gebruiker ziet gebeuren.
- **Het event draagt de actie ook als vaste sleutel.** `action` is `heat`, `cool`, `off`,
  `stays_off` of `left_alone`: de sleutel waarvan `action_text` de zin is, uit dezelfde
  aanroep, zodat de twee niet uit elkaar lopen. Wie alleen wil horen dat iets uitgaat,
  filtert daarop in plaats van op een vertaalde zin.
- **Het moment waarop het huis ging slapen komt uit de rondes zelf.** `build_world` leest
  het alleen; `world_builder._note_house_asleep` vraagt elke ronde
  `night.house_asleep_since` en schrijft het weg zodra het verandert, zodat een herstart
  midden in de nacht het niet kwijtraakt. In de diagnose gelakt.

De listeners staan meteen aan — een toestandswijziging tijdens het opstarten van Home
Assistant gaat dus niet verloren — maar er wordt niet beslist voordat het herstel gedraaid
heeft: `_async_evaluate` doet niets zolang de vlag `_restored` niet staat, en die vlag gaat
aan in `_async_on_hass_started`, ná het herstel van de opslag en vóór de eerste beslissing.
Zonder die poort besliste de director op een half huis: de sensoren die tijdens het laden
binnenkomen wekken de debouncer, en een apparaat dat iemand eerder die dag met de hand uitzette
stond dan al weer aan voordat `_handed_back` gelezen was — de rest van de dag. Noteren
(`_notice_home`, `_notice_hand`, de neerslag) mag intussen wel, en het herstel **voegt
samen** in plaats van te vervangen, zodat een hand van tijdens het opstarten niet stil
verdwijnt onder een ouder opgeslagen oordeel.

**Wat iemand in die seconden aan een override of een vooruit-verzoek doet, wint van het
herstel.** Wie tijdens het opstarten de overrideschakelaar omzet, `set_override` of
`clear_override` aanroept, of een vooruit-verzoek zet of annuleert, zegt iets over dit
moment; in de opslag staat een oordeel van vóór de herstart. De coordinator noteert daarom
per zone **en per soort** wat de gebruiker er vóór het herstel zelf deed: een override (de
schakelaar, `set_override`, `clear_override`) staat in de ene notitie, een vooruit-verzoek
of zijn annulering in de andere. `_restore_overrides` leest alleen de overridenotitie en
het herstel van `until` alleen de verzoeknotitie. Zo houdt een vers vooruit-verzoek geen
opgeslagen override meer tegen, en een verse override geen opgeslagen verzoek:
`clear_override` houdt de opgeslagen looptijd niet in leven, `set_override` zonder
looptijd erft de opgeslagen eindtijd en afloopkeuze niet, en een vers verzoek houdt zijn
eigen eindtijd, maar elk laat de andere soort met rust. `cancel_precondition` zonder zones
noteert elke zone in de verzoeknotitie en laat een opgeslagen override dus staan. Het
herstel van `bypass` vervangt niet maar **voegt samen**, zodat de keuze `ignore_openings`
van een vers verzoek blijft staan naast wat er al lag. Een zone waaraan de gebruiker niets
deed, leest gewoon de opslag, precies zoals eerst. De notities gaan na het herstel weg; het
herstel van de schakelaarstand zelf (de `RestoreEntity` in `async_added_to_hass`) is geen
handeling van de gebruiker en telt dus niet mee. Op dat ene punt na gaat er zo alleen een
beslissing verloren, geen invoer.
Er wordt vóór het herstel ook niets weggeschreven. Noteren mag, maar de opslag
blijft onaangeroerd tot hij gelezen is: `Store.async_load` leest een wachtende schrijfactie
in plaats van het bestand, dus staat er één klaar, dan komt het herstel uit op de half
opgebouwde staat van dit moment en is het opgeslagen oordeel van de gebruiker verdwenen.
`_async_save_state` onthoudt daarom alleen dát er iets te bewaren viel, en
`_async_on_hass_started` schrijft één keer direct ná het herstel — ook als het herstel zelf
omviel. Een installatie die tijdens het opstarten weer weggehaald wordt schrijft niets
terug: de afbraakpoort (`_closing`) staat daar vóór.

### applier.py — uitvoeren

Beslist niets. Vraagt `diff.py` wat er moet gebeuren en zet dat om in service calls, of
logt het alleen in schaduwmodus. `climate.set_temperature` draagt de `hvac_mode` mee, zodat
een unit die zowel een stand als een setpoint nodig heeft met één aanroep klaar is — twee
aanroepen zouden hem kort op de nieuwe stand met het oude setpoint laten draaien.

Faalt een aanroep, dan hangt de reactie af van wat er faalde. Een mislukte **stop** breekt
de aanname waar de rest van het plan op rust: de starts erachteraan zouden landen bovenop
een apparaat dat had moeten stoppen, precies de combinatie die dit ontwerp onbereikbaar
hoort te maken. Die **starts** vervallen dan ook — maar de overige **stops** gaan gewoon
door. De commando's staan al gesorteerd met de stops vooraan, en een apparaat dat moet
stoppen hoort te stoppen ook als een ánder apparaat weigert; één weerspannige cloudkoppeling
houdt zo niet langer de hele huisbrede stop tegen. Een mislukte **start** blijft onschuldig
— er gebeurt alleen minder dan gepland — en de rest gaat gewoon door.

Een stand die een apparaat uitdrukkelijk niet in `hvac_modes` meldt, krijgt het niet
gevraagd: `diff.changes` laat zo'n commando vallen (onbekend is toegestaan, precies zoals
`sources._reachable` dat al voor verwarmen en koelen doet), zodat een apparaat zonder `off`
niet elke ronde opnieuw omvalt en elke ronde de starts meesleept. `unsupported_modes` meldt
dat ontbrekende `off` net zo goed als een ontbrekende `heat` of `cool`.

### config_flow.py — de wizard

Bevat geen kennis van klimaatregels, alleen van formulieren. De installatie wordt in een
lokale kopie opgebouwd en pas bij "Opslaan en sluiten" weggeschreven. Halverwege opslaan
zou de entry herladen terwijl de gebruiker nog aan het bewerken is, en de grond wegtrekken
onder de flow waar hij in staat.

Een verlopen cursor (bijvoorbeeld naar een zone die net verwijderd is) stuurt terug naar
het menu in plaats van een uitzondering te gooien: een config flow die crasht laat een half
opgebouwde installatie achter zonder weg terug.

Sinds S5 staan de schema's in `schemas.py`: die module bouwt per scherm het
`vol.Schema` uit de huidige waarden, en de `async_step_*`-methodes houden de
navigatie, de validatie en het opslaan. De `async_show_form`-aanroepen zijn
bewust in `config_flow.py` gebleven, want daar hangen de bewakingen op de
formulieren aan.

**Eigenschap:** een scherm dat je binnen kunt, kun je ook weer uit — ongeacht wat er in
de **optionele** velden staat of juist niet staat. "Verwerpen en teruggaan" komt aan zodra
de verplichte velden geldig zijn. Elk optioneel veld staat daarom als kale selector in het
schema. De omzetter kent maar één `vol.Any`-vorm: `vol.Any(None, validator)` — dat is wat
`vol.Maybe(validator)` oplevert — en maakt daar `allow_none: true` van; élke andere vorm
(een derde tak, een lege string) maakt het scherm onrenderbaar (gemeten). Die ene
vorm gooit alsnog wanneer de binnenste validator een mapping-schema is
(`vol.Maybe(vol.Schema({...}))`), en de omgekeerde volgorde `vol.Any(validator, None)`
serialiseert niet — de volgorde in het anker is dus niet toevallig. De
huidige keuze voor kale selectors is daarmee **smaller** dan wat de bibliotheek toestaat:
`vol.Maybe(selector)` zou ook tekenen, maar is overbodig zolang de aanname hieronder klopt
en zou alleen het scenario dekken waarin de interface een leeggemaakt veld als `None`
doorgeeft. Dát is een **aanname over de interface, geen meting**: de interface stuurt een
leeggemaakt optioneel veld door als ontbrekende sleutel. Klopt die aanname niet, dan
weigeren 31 van de 33 optionele velden zowel `None` als `""` — alleen de twee tekstvelden
komen erdoor — en is hetzelfde symptoom in volle omvang terug. Een ingevuld veld gaat
gewoon door de selector en wordt dus nog steeds gevalideerd; verplichte velden vallen
bewust buiten deze belofte (een leeggemaakt verplicht getalveld kan het scherm nog steeds
op slot zetten), en een lege waarde mag nooit als zodanig de configuratie in
(`_blank_to_none`).

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

**Categorieën.** Elke entiteit kent haar `entity_category`, en die keuze
verandert wat een gebruiker in zijn lijst ziet: de waarneemsensoren
(`sensor.*`) en de blokkade/valt-terug/vast-binaire sensoren staan op
`DIAGNOSTIC`; de twee `number`-entiteiten en de seizoenskeuze op `CONFIG`; de
knoppen en schakelaars blijven gewoon zichtbaar (geen categorie). Eén sensor is
de uitzondering: de eindtijdsensor van een override (`..._override_ends`) volgt
de coordinator, maar hoort op een dashboard naast de overrideschakelaar te
staan en blijft daarom bewust zichtbaar. Nergens
wordt `entity_registry_enabled_default` gezet: er verdwijnt niets uit
bestaande dashboards en kaarten, en dat is een bewaakte eigenschap
(`test_entity_categories.py`), geen afspraak.

### texts.py — vertaalde zinnen naar buiten

De integratie stuurt zelf geen berichten; waar een melding heen gaat hoort een gebruiker te
bepalen. De **tekst** komt wel hiervandaan: een blueprint kan niet vertalen, en een half
Engelse melding op een Nederlands scherm leest als een fout.

Deze module zoekt een zin op in de taal van de interface en valt terug op Engels — twee keer
zelfs, want een vertaling kan ontbreken én uit de pas lopen met de code. De zinnen wonen
onder `exceptions` in `strings.json`, omdat Home Assistant het hoogste niveau van dat bestand
tegen een vast schema valideert.

De beslismelding heeft er een tweede woonplaats bij: de dertig redenen, de vijf
actiewoorden en de twee verbindingswoorden van de melding staan onder
`entity.sensor.zone_source.state_attributes...` en `entity.sensor.would_command...`. Die plek
is gekozen omdat hassfest hem accepteert en Home Assistant het attribuut dan ook op de
entiteit zelf vertaald toont. `reason_sentence` en `action_sentence` lezen één stuk, en
`decision_message` bouwt de zin: `<kamer>: <actie> — <reden>`, met het apparaat en zijn
setpoint ertussen alleen als de director dat apparaat werkelijk aanstuurt. `decision_fields`
is de enige aanroep die de coordinator nog doet: het zoekt de vier leesbare velden bij elkaar
(welk apparaat, welke actie, welke zin) en woont hier en niet in de coordinator, omdat die al
op de maatlijst staat en de zin tekst is en geen koppeling. Het resultaat is presentatie; de
identifier blijft het contract.

Eén reden heeft een zin per taak: `outdoor_outside_window` is bij verwarmen *het is buiten
te warm om te verwarmen* en bij koelen *het is buiten te koud om te koelen*
(`state_attributes.outdoor_outside_window.state.<taak>`). `reason_sentence` neemt die als
de beslissing een taak meedraagt (`ZoneDecision.duty`); zonder taak is het de algemene zin,
die beide noemt.

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

De besluitmelder filtert op `reason` (*Alleen deze redenen*), op `action` (*Alleen deze
acties*) en op zone. Een event zonder `action`, van een oudere integratie, valt niet weg op
het actiefilter: een filter dat nooit kan slagen zou anders alles stil maken.

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

De handbediend-melding (`manual_sources`) is de énige met een oplosflow. De lange
uitleg staat in `issues.manual_sources.fix_flow.step.init` (titel én beschrijving,
alle zeven talen) — de plek waar Home Assistant hem bij een fixable melding toont;
een `description` op meldingsniveau mag daar niet naast staan, want hassfest sluit
beide voor fixable meldingen uit. Het dialoog verschijnt ook echt: de openingsaanroep
van de flow-manager (`{"issue_id": ...}`) telt niet als bevestiging, pas de tweede
aanroep — hetzelfde patroon als `ConfirmRepairFlow` uit core.

### Nog te bouwen — ontwerpvoorstellen

De ideeënbus staat in [`ROADMAP.md`](ROADMAP.md); hier staat per idee het ontwerp, zodat
duidelijk is wat het inhoudt vóór eraan begonnen wordt. De prioriteiten (should/could/would)
volgen de ROADMAP.

#### Should have

**Een onleesbare aanwezigheid of slaapsensor houdt de laatst leesbare stand even vast (N14,
N15).** Nu leest een weggevallen aanwezigheid als *weg* en een weggevallen slaapsensor als
*wakker*, met als gevolg dat een handstart-zone uitgaat (`EVERYONE_ASLEEP`, `NOBODY_HOME`) en
dat alle wachtende zones tijdens de uitval starten.
- Optie (a), alleen de handstart: de twee redenen gaan er ook langs, zolang de oorzaak een
  onleesbare aanwezigheid is. Smal, maar de wachtende zones zonder handstart blijven starten.
- Optie (b), alle zones: de koppelingslaag houdt de laatste leesbare stand van een bewoner
  vast voor een korte tijd (`unreadable_hold`, in `WorldState` als gewone waarde); daarna
  leest de uitval weer als nu. Eén plek lost N14 en N15 op, maar verandert het gedrag voor
  elke installatie en vraagt dus een ankerbesluit eerst.
- De gebruiker beslist tussen (a) en (b) voordat er gebouwd wordt.

**Meldingen noemen de instelling in de taal van de gebruiker (N16).** De regels in
`engine/validation_*.py` vullen `settings`, `window` en `label` met Engelse woorden
("sleep window", "quiet window", "minimum cycle time"); `problems.readable` zet ze
ongewijzigd in de vertaalde zin. Ontwerp: de engine levert vaste sleutels in plaats van
woorden (`wake_by`, `sleep_in_until`, `quiet_window`, ...), en de koppelingslaag zoekt per
sleutel het schermwoord op in de taal van de gebruiker, met de Engelse sleutel als terugval.
- De woorden komen uit dezelfde vertaalbestanden als de schermen, zodat de melding het
  schermwoord noemt en geen eigen woord.
- Bewaakt door een toets die elke melding in elke taal rendert en eist dat er geen Engels
  sleutelwoord in staat.

**De bewaking van de remmen-invoer meet het gedrag.** De indeling in drie klassen dwingt een
bewuste keuze af. Een verstoringstoets haalt per extern veld buiten de remmen-invoer een
andere waarde door een vaste proefwereld en eist dat de remmen hetzelfde antwoord geven; zo
blijkt een veld dat de remmen toch voedt zonder dat iemand het opschrijft.

**Live prioriteiten gelijk trekken op één circuit.** Twee zones met dezelfde prioriteit op
hetzelfde circuit kunnen elkaars taak niet krijgen; de tie-break is nu de bron- en
zonevolgorde. Het idee is een zone die lang wacht tijdelijk één stap voorrang te geven,
met een vaste maximumverschuiving en terugval naar de ingestelde prioriteit zodra de
wachttijd voorbij is. Dat is een **verbreding** van de bronkeuze; de andere kant blijft dat
de ingestelde prioriteit het plafond is, en zonder wachttijd moet het plan exact hetzelfde
blijven. Niet gebouwd.

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

**De afspraken achter de bronbewakingen in de repo.** De structurele afspraken die
een bronbewaking aanvullen - de bewakingsregel, welke bronbewakingen er zijn en wat
ze dekken - staan in `AGENTS.md`, en dat bestand staat in `.gitignore`.
- Plek: een eigen hoofdstuk *Bewakingen en hun afspraken* in dit document, NL + EN,
  met per bronbewaking het bestand, de afspraak en wat hij dekt en niet dekt.
- Verwijzing: de docstrings van de bewakingen wijzen naar dat hoofdstuk in plaats
  van naar `AGENTS.md`; `AGENTS.md` houdt alleen de samenwerkingsafspraken.
- Bewaakt: `test_every_source_guard_names_its_coverage` kan dan ook eisen dat elke
  bronbewaking in dat hoofdstuk staat, want dit document gaat mee in de repo en de
  CI kan het lezen.
- Risico: twee plekken voor dezelfde afspraak. De verhuizing haalt de afspraken in
  dezelfde wijziging uit `AGENTS.md` weg.

**De generator gelijktrekken met de override-overdracht.** Eén regel voor een
overgedragen apparaat, of het nu als bron of als `Generator` onder de zone hangt.
- Engine: `decide._generator_commands` leest dezelfde overdracht als `_handed_over`: een
  generator die een zone onder override bedient krijgt geen enkel commando meer, ook geen
  aan vanuit een andere zone.
- Prijs: de andere zones op die generator krijgen die tijd geen warmte van hem, precies
  zoals bij een gedeelde bron (anker 11).
- Bewaakt: de generatorvariant in `tests/test_override_handover.py` legt "aanzetten mag"
  vast en verandert mee; de bronvariant ernaast is het voorbeeld.

**Vakantieagenda: alle overlappende afspraken lezen.** De toestand van een
agenda-entiteit toont maar één lopende afspraak.
- HA-laag: `_calendar_says_holiday` vraagt `calendar.get_events` op over het huidige
  moment en zoekt het trefwoord in elke afspraak die dan loopt, in plaats van alleen de
  toestand van de entiteit te lezen.
- Risico: een service-aanroep met antwoord per beslisronde; de uitkomst hoort bewaard te
  worden tot de agenda-entiteit zelf verandert.

**Een time-out op de service calls.** Een hangende cloudkoppeling houdt de beslislock
vast.
- HA-laag: `applier._execute` begrenst elke aanroep met `asyncio.timeout`; een aanroep die
  niet op tijd terugkomt telt als mislukt, met de bestaande regel: een mislukte stop laat
  de overige stops door en alleen de starts vervallen.
- Open keuze: één vaste grens voor alle apparaten, of een grens per bron.

**Waarschuwen als de streeftemperatuur op het uitschakelpunt ligt.** De taak eindigt pas
als de ruimtesensor het uitschakelpunt haalt.
- Config: het zonescherm en `validate()` noemen een streeftemperatuur die op of voorbij
  het uitschakelpunt ligt (`start_at + hysteresis` bij verwarmen, `start_at - hysteresis` bij
  koelen) als waarschuwing, niet als weigering: het kan werken, maar alleen als het
  apparaat zelf verder regelt dan de ruimtesensor.
- Risico: een gangbare instelling valt hier zelf onder; de melding legt uit en weigert
  niets.

**Een geweigerde winnaar van een gebied geeft de verliezer een tweede kans.** `area_clash()`
haalt het verliezende verzoek uit de wensen vóórdat de circuits oordelen. Weigert het circuit
daarna de winnaar (`CIRCUIT_AT_CAPACITY`, `SHORT_CYCLE_PROTECTION` of `CIRCUIT_CONFLICT_LOST`),
dan draait de winnaar niet en blijft de verliezende zone die ronde onbediend: de
terugvallus in `resolve_with_fallbacks()` probeert alleen verzoeken die nog in de wensen
staan. De uitkomst valt aan de veilige kant (kort koud, nooit twee systemen tegelijk).
- Optie (a), laten zoals het is: de weigering van een circuit is tijdelijk en de volgende
  ronde beslist opnieuw.
- Optie (b), het verliezende verzoek terugzetten zodra de winnaar geweigerd is. De kamer
  wordt dan sneller bediend, maar de twee apparaten kunnen elkaar afwisselen als het circuit
  en het gebied elkaar steeds tegenspreken, en dat vraagt een eindigheidsbewijs zoals de lus
  van anker 7 dat heeft.
- De gebruiker beslist tussen (a) en (b) voordat er gebouwd wordt.

**Een bron die niet automatisch start, maar in het gebied van een ketel staat, hoort in een
groep met die ketel.** `area_clash()` kijkt naar verzoeken van de director. Een bron met
`autostart` uit vraagt nooit iets: hij wordt alleen door een exclusieve groep of door
`manual_conflict()` in bedwang gehouden. Staat zo'n bron in het gebied van een ketel en in
geen enkele groep, dan kan hij naast de ketel draaien zonder dat de director ingrijpt
(gemeten met een airco die met de hand draait en een ketel die voor een andere zone wordt
gevraagd: de ketel krijgt `heat`, de airco blijft als `MANUAL_SOURCE` ongemoeid).
- Optie (a), impliciet: elke bron zonder `autostart` in een gebied telt als groepslid met
  de ketel van dat gebied. Geen invulwerk, maar het verandert het gedrag voor elke
  installatie die zulke bronnen heeft.
- Optie (b), waarschuwen: `validate()` meldt een bron zonder `autostart` in een gebied
  zonder groep met de ketel, en de gebruiker vult de groep zelf in. Smal en zichtbaar.
- De gebruiker beslist tussen (a) en (b) voordat er gebouwd wordt.

#### Could have

**De open punten van de opruimronde.** Zes punten, in volgorde van belang: (1)
`engine/validation.py` (1288 regels) splitst per onderwerp (zones, bronnen, circuits,
bewoners, vensters), elk met zijn eigen regels, achter dezelfde ene `RULES`-lijst in de
bestaande volgorde. (2) `engine/constraints.py` (618) geeft de taakkeuze en de
capaciteit/kortcyclus aan `circuit_policy.py` en `capacity.py`. (3) Elk `coordinator_*`-onderdeel
krijgt een eigen kleine staatsklasse in plaats van privé attributen van de coordinator te
lezen en te zetten (nu ruim tachtig plekken). (4) De `TYPE_CHECKING`-terugimports van `flow_*`
en `coordinator_*` verdwijnen met een protocol per laag, waarmee de uitsluitingenpoort van 75
terug naar 41 of lager kan. (5) `texts.py` houdt geen her-export van `entity_texts.py` meer
(en `problems.py` geen onderaan-import van `repair_notices.py`); aanroepers importeren
rechtstreeks. (6) De stand-ins in de toetsen krijgen de attributen waarvoor dertien
`getattr(self, "<attribuut>", standaard)`-regels een terugval zijn. De impactkaart heeft een
eigen punt: een volledige run voegt bestaande regels samen met wat hij ziet, zodat een lokale
run op Windows de map `script/` niet meer laat vallen.

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

### Code-indeling — de opruimronde

Sinds deze indeling staat elke module bij één onderwerp. Deze ronde verplaatst alleen
code: dezelfde regels, dezelfde namen van `Reason`-waarden en `Problem`-codes,
dezelfde opslagvorm en dezelfde entiteiten. Een verhuizing die een regel
inhoudelijk verandert, is geen verhuizing maar een reparatie en hoort in een
eigen commit. De tabellen hieronder zijn de afspraak; wie een bestand opnieuw
wil indelen, wijzigt eerst dit hoofdstuk.

#### Nieuwe bestanden

| Nieuw bestand | Onderwerp | Wat er staat of naartoe verhuist |
|---|---|---|
| `engine/models.py` | de installatie als geheel | `DirectorConfig`; de kleine bouwstenen staan in de modules hieronder |
| `engine/seasons.py` | seizoen en neerslag | `Season`, `SeasonSource`, `SeasonSettings`, `PrecipitationSettings` |
| `engine/windows.py` | het tijdvenster | `TimeWindow` |
| `engine/residents.py` | de bewoner | `Resident`, `SleepIn`, `WakeDeadline` en `RiseBrake` |
| `engine/equipment.py` | apparaten en hun samenhang | `SourceRole`, `OutdoorWindow`, `ModeSettings`, `Source`, `Circuit`, `ConflictPolicy`, `Generator`, `Opening`, `HeatingLayout` |
| `engine/rooms.py` | de ruimte en haar poortkeuze | `ZoneGate`, `Zone`, `GateSettings` |
| `engine/validation.py` | alle configuratiecontroles | `validate()` en één `RULES`-lijst in de bestaande volgorde: één ingang, één volgorde. De regelfuncties staan per onderwerp in `engine/validation_zones.py`, `validation_sources.py`, `validation_circuits.py`, `validation_openings.py`, `validation_residents.py`, `validation_windows.py` en `validation_shared.py`; `Problem` staat in `engine/problem.py`. |
| `engine/manual_sources.py` | de eenmalige melding over handbediende bronnen | `manual_only_problems` |
| `engine/candidates.py` | wie mag meedoen | `handed_over`, `collect_wishes`, `serving`, de exclusieve groepen, `standing_firm` |
| `engine/grants.py` | wie krijgt de taak | `resolve_with_fallbacks`, `resolve_circuits`, `zone_reasons`, `manual_conflict`, `exclusive_rival`, `stand_down` |
| `engine/commands.py` | het commando bouwen | `build_commands`, `generator_commands` |
| `engine/command_stops.py` | de stopboekhouding en het samenvouwen | `opening_rest_bookkeeping`, `stop_blocked`, `ignores_openings`, `collapse_shared`, `claim` |
| `engine/command_reasons.py` | waarom een apparaat niets krijgt | `was_running`, `received_heat`, `unreadable_reason`, `untouched_reason`, `opening_stop_reason`, `opening_rest_hold`, `idle_mode` |
| `engine/zone_decisions.py` | wat een zone uiteindelijk te horen krijgt | `build_zone_decisions`, `lost_to_another_zone`, `command_order`, `clamped_target` |
| `engine/quiet.py` | het stiltevenster en de draaiende zone | `guests_carry_the_house`, `quiet_hours`, `open_quiet_windows`, `was_home_before`, `zone_running`; dit sluit de kring met `hand_start` |
| `engine/schedule.py` | het rooster als poort | `schedule_open`, `counts_towards_schedule` |
| `engine/gates.py` | de poort als geheel | `closed`, de huishoudpoort, de openingen, `house_wide_blocked`, `opening_rest_until`, en `brakes_remaining` (de poort leest de handstart, niet andersom) |
| `engine/hand_start.py` | de handstartregel | `HAND_START_BRAKES`, `brakes_readable`, `passes`, `quiet_holds`, `early_riser_holds`, `waits_for_sleeper`, `up_and_about`, `still_in_bed`; geen luie import meer |
| `engine/serialise.py` | de ingang van de opslag | `config_from_dict`, `config_to_dict`, `opening_ids` |
| `engine/installation_storage.py` | algemene installatievelden | poorten, gastenvenster, seizoenen, neerslag, ligging en het slaapvenster |
| `engine/equipment_storage.py` | apparaten en gebieden | bron, modus, buitengrens, circuit, generator, opening en zone lezen en schrijven |
| `engine/resident_storage.py` | de bewoner in de opslag | de bewoner plus zijn drie ochtendinstellingen |
| `engine/storage_values.py` | opgeslagen waarden veilig lezen | de naam van `storage_helpers.py`; alle lezers krijgen een publieke naam (`as_dict`, `items`, `weekdays`, `sequence`, `strings`, `text`, `float_or`, `optional_float`, `int_or`, `optional_int`, `bool_or`, `seconds_or`, `time_or`, `choice`) |
| `coordinator_surface.py` | het oppervlak van de koppeling | `CoordinatorSurface`; alle mixins lezen hier hun gastheer |
| `coordinator.py` | de coordinator zelf | `__init__`, de eigenschappen, `async_request_evaluation`, de klok en de levensduur; hij erft de publieke mixins en houdt per onderdeel een dunne methode die de functie in de `coordinator_*`-module aanroept |
| `coordinator_lifecycle.py` | opstarten en stoppen | `async_start`, `_async_on_hass_started`, `tracked_entities`, `_calendar_says_holiday`, `async_shutdown` |
| `coordinator_tracking.py` | wat een apparaat zelf doet | `_handle_change`, `_notice_precipitation`, `_notice_hand`, `_note_commanded_off`, `_note_commanded_on`, `_we_wanted_it_off`, `_we_wanted_it_on` |
| `coordinator_round.py` | één beslisronde en haar klok | `_async_evaluate`, `_remember_families`, `_with_family_history`, `_schedule_deferral`, `_cancel_pending_deferral`, de klokherhaling |
| `coordinator_reporting.py` | wat de koppeling meet en meldt | `unusable_entities`, `unsupported_modes`, `waiting_seconds`, `unusable_latest`, `stuck_zones` en de bijbehorende notitie- en meldfuncties |
| `coordinator_events.py` | de events naar buiten | `_fire_events`, `_fire_refusals`, `_refusal_data`, `_friendly`, `_open_openings`, `_event_data`, `wanted` |
| `hand_start.py` | de handstart in de koppeling | `HandStartMixin`: herkenning, opslag en verval van een handstart |
| `hand.py` | de hand aan het apparaat | `HandMixin`: `zones_of`, `zones_handed_back`, `everyone_asleep`, `house_is_empty` |
| `overrides.py` | de override | `OverridesMixin` (publieke naam; dezelfde methodes) |
| `preconditions.py` | het vooruit-verzoek | `PreconditionsMixin` en `still_running` (publieke namen) |
| `resident_reader.py` | de bewoner lezen | `ResidentReaderMixin` |
| `room_presence.py` | de kamerpresentie | `RoomPresenceMixin` |
| `state_store.py` | de opslag van de koppeling | `StateStoreMixin`; `_hand_starts_payload` wordt gewoon aangeroepen |
| `world_builder.py` | de momentopname bouwen | `WorldBuilderMixin`; de losse lezers gaan naar `entity_reading.py` |
| `entity_reading.py` | één entiteit lezen | `reads_as_home`, `temperature_from_state`, `season_from_state`, `as_float`, `as_modes` |
| `stored_state.py` | bewaarde momenten en eigen uitzetting | `stored_time`, `restore_commanded_off` |
| `schema_fields.py` | de vorm van een formulierveld en de veldtabel | de selectors (`CLIMATE`, `CLIMATE_MULTI`, `RANK`, `SECONDS`, `TEXT`, `TIME`, `band`, `choices`, `temperature`), `table_schema` en `write_table` |
| `form_common.py` | de vaste rijen van elk scherm | `user`, `save`, `ADD`, `BACK`, `EXIT`, `EXIT_KEEP`, `EXIT_DROP`, de keuzeregels en `source_options`, `group_label`, `window_label`, `add_option`, `back_option`, `exit_row`, `managed_entities` |
| `form_installation.py` | de installatieschermen | `settings`, `exclusives`, `exclusive`, `quiets`, `quiet` |
| `form_zones.py` | de zoneschermen | `zones`, `zone`, `sources`, `source` |
| `form_circuits.py` | de circuitschermen | `circuits`, `circuit`, `circuit_priorities`, `circuit_priority`, `generators`, `generator` |
| `form_residents.py` | de bewoner- en vensterschermen | `residents`, `resident`, `windows`, `window`, de weekdagkiezer en de opgeslagen dagen |
| `form_openings.py` | de openingschermen | `openings`, `opening` |
| `flow_installation.py` | de installatiestappen | `settings`, `exclusives`, `exclusive`, `quiets`, `quiet` |
| `flow_zones.py` | de zonestappen | `zones`, `zone` |
| `flow_sources.py` | de bronstappen | `sources`, `source` |
| `flow_circuits.py` | de circuitstappen | `circuits`, `circuit`, `circuit_priorities`, `circuit_priority` |
| `flow_generators.py` | de generatorstappen | `generators`, `generator` |
| `flow_residents.py` | de bewonerstappen | `residents`, `resident` |
| `flow_windows.py` | de vensterstappen | `windows`, `window` |
| `flow_openings.py` | de openingstappen | `openings`, `opening` |
| `flow_validation.py` | de schermcontroles en formulieromzetting | `settings_errors`, `zone_errors`, `name_errors`, `mode_errors`, `gate_errors`, `band_errors`, `heat_cool_from_form`, `zone_from_form`, `next_priority`, `all_source_ids`, `unique_id`, `deep_copy` |
| `repair_notices.py` | de bijzondere reparatiemeldingen | de meldingen over onleesbaar, onbruikbare standen, seizoen, commando, overbrugging, beschadigde opslag en de waarnemers |
| `entity_texts.py` | de leesbare beslissing | `reason_sentence`, `action_sentence`, `decision_message`, `decision_fields` en de sleutels daaromheen |
| `services.py` | de service-API | de schema's, doelkeuze en registratie van `evaluate`, `precondition`, `cancel_precondition`, `set_override` en `clear_override` |

De taakkeuze op een circuit staat in `engine/circuit_policy.py`, de capaciteit en de
kortcyclus in `engine/capacity.py` en het verzoek, de toekenning en de uitkomst in
`engine/circuit_requests.py`; `engine/constraints.py` houdt het oplossen van één
circuit.

`engine/decide.py` blijft de enige ingang van de beslissing; het bevat alleen nog
`decide()` en de volgorde van de stappen. `config_flow.py` blijft het enige
bestand dat Home Assistant als configuratiestroom laadt; het bevat de basisklasse,
de menu-navigatie, het opslaan en de gedeelde lezers. De stappen zelf staan als
functies in de `flow_*`-modules; `config_flow.py` houdt per stap een dunne methode
die ze aanroept. `problems.py` en `texts.py` blijven de algemene ingangen;
`repair_notices.py` en `entity_texts.py` dragen de bijzondere onderwerpen.
`__init__.py` blijft de levensduur van de entry; `services.py` draagt de
service-API.

#### Grenzen

- `engine/` importeert nergens Home Assistant en doet geen I/O; dat blijft
  bewaakt door `tests/test_the_border.py`.
- De richting is `engine/` ← koppelingslaag ← Home Assistant-platforms. Een
  module importeert alleen naar beneden; er komt geen kring.
- De bestaande luie imports in `engine/models.py` (de validatielijst) en
  `engine/hand_start.py` (de poort) verdwijnen. De poort leest de handstart, de
  handstart leest de poort niet; de validatie leest het model, het model leest
  de validatie niet.
- Over een modulegrens staat geen naam met een leidende onderstreping. De
  mixins, hun helpers en de schemabouwers krijgen een publieke naam in het
  bestand waar ze wonen.
- `tests/test_module_boundaries.py` bewaakt vier van deze grenzen met `ast` en
  `tokenize`: geen privé naam over een modulegrens, geen `getattr(self, "<naam>",
  terugval)` op een eigen lid, geen import binnen een functie en geen
  `# noqa: E402` (een import staat bovenaan, zonder uitzondering).
- Een tegel van de veldtabel blijft in `engine/fields.py`; de selectors en de
  vertaling naar `vol.Schema` blijven in de Home Assistant-helft.
- Een nieuw bestand is een onderwerp, geen restbak: geen `utils`, `helpers`,
  `extra` of `misc`.

#### Volgorde en bewijs

De volgorde is van de minst naar de meest verweven module. Elke stap is één
commit, elke commit is groen en wordt pas gepusht als de voorganger groen is.

1. publieke namen en de namen van de helpers (geen verhuizing);
2. de toetsen per onderwerp, de gedeelde hulpjes naar `tests/conftest.py` of een
   hulpbestand in `tests/`, en de impactkaart;
3. validatie in één module en `state_extra.py` naar `stored_state.py`;
4. opslag en serialisatie;
5. de hand en de handstart uit elkaar, met `engine/quiet.py`,
   `engine/schedule.py` en `engine/gates.py`;
6. de configuratiestroom en de formulieren;
7. `engine/decide.py` met `candidates`, `grants`, `commands`,
   `command_reasons` en `zone_decisions`;
8. `engine/models.py` met `seasons`, `windows`, `residents`, `equipment` en
   `rooms`;
9. `coordinator.py` met `coordinator_surface`, `coordinator_lifecycle`,
   `coordinator_tracking`, `coordinator_round`, `coordinator_reporting` en
   `coordinator_events`;
10. de overige grote modules: `problems.py`, `texts.py` en `__init__.py`.

Per commit wordt het bewijs vastgelegd in het commitbericht en in het
voortgangsbestand in de repo-root:

- `controle-*-probe-engine.py . all` (42 regels) en
  `controle-*-probe-v1-productie.py .` (64 regels) byte-gelijk met de
  basis, met het logpad en de tijd uit het log;
- de drie `controle-*-probe-eigen.py`-probes (de E-, N- en Q-reeksen)
  identiek op de basis en op HEAD;
- `pytest --collect-only -q` als afbeelding oud → nieuw: hetzelfde aantal,
  nul verdwenen en nul nieuwe toetsen behalve de bewust verhuisde;
- dekking 100 % regels en takken, de poort met 41 benoemde uitsluitingen of
  minder, de kaart schoon, en de mutatielijst van 66 van 66 gevangen;
- `git diff --stat -M` toont alleen verhuizingen en importregels; elke regel
  die geen verhuizing is, wordt in het bericht genoemd;
- de zeven tekstbestanden, `STORAGE_VERSION`, de `Problem`-codes en de
  `Reason`-waarden zijn gelijk aan de basis.

De impactkaart hangt aan de selectie: `script/select_tests.py` laat een
toegevoegd pakketbestand of toetsbestand de hele suite draaien. Een rename is in
`git diff --no-renames` een verwijdering plus een toevoeging en valt dus onder
dezelfde regel. `script/test` werkt de kaart bij en de CI levert hem als artefact `impact-map`.
De kaart is een samenvoeging: een run voegt toe wat hij zelf zag en laat niets weg
wat hij niet zag, en alleen een toetsbestand, bestand of map die er niet meer is
valt eruit. Een lokale volledige run op Windows ziet voor
`tests/test_controls_live.py` de map `script/` niet, de CI wel; die regel blijft
dus staan en de kaart uit een lokale run kan gewoon mee in de commit. De CI keurt
een kaart af waarop een regel ontbreekt die de run zag, niet een kaart met een regel
extra. Een gewijzigd bestaand bestand houdt de gewone selectie.

#### Toetsen per onderwerp

De rondenamen verdwijnen, en de ronde-labels in de ratelcommentaren van `tests/test_the_measure.py` en de diepe takken toets gaan eruit. Deze tabel is de verhuizing; een toets die uit een
campagnebestand komt, houdt zijn class- en functienaam, zodat de collectie
alleen door het bestandspad verschuift.

| Oud | Nieuw |
|---|---|
| `tests/test_campaign_editing.py` | `test_commissioning.py` (formulieren lopen, toevoegen, weigeren, bewaren, verwijderen), `test_screen_state.py` (scherm naast scherm, afronding, weggooien, lege velden, weekdagen), `test_flow_branches.py` (de schermtakken) |
| `tests/test_campaign_live_flows.py` | `test_options_flow_live.py`, `test_setup_live.py`, `test_restart_flow_live.py`, `test_storage_live.py`, `test_entity_reading_live.py`, `test_repair_live.py`; de huisbrede lijst naar `test_house_wide_openings_live.py` |
| `tests/test_campaign_live_ha.py` | `test_setup_live.py`, `test_services_live.py`, `test_lifecycle_live.py`, `test_startup_half_loaded.py`, `test_steering_live.py`, `test_controls_live.py`, `test_reporting_live.py`, `test_restart_live.py`, `test_translations_live.py`, `test_hand_live.py`, `test_storage_live.py`, `test_coverage_exclusions_live.py` |
| `tests/test_campaign_outages.py` | `test_outages.py` (de engine) en `test_outages_live.py` (de koppeling) |
| `tests/test_campaign_settings.py` | `test_season_settings.py`, `test_household_gates_live.py`, `test_holiday_calendar_live.py`, `test_delays_live.py`, `test_circuits_live.py`, `test_shared_boiler_live.py`, `test_hand_on_appliance_live.py`, `test_diagnostics_live.py`, `test_multiple_installations.py` |
| `tests/test_campaign_weather_boundaries.py` | `test_weather_boundaries.py` |
| `tests/test_campaign_year.py` | `test_year_simulation.py`; `BUSY` verhuist naar `tests/simulation.py` |
| `tests/test_reachable_branches.py` | `test_flow_branches.py`, `test_options_flow_live.py`, `test_coordinator_surface.py` |
| `tests/test_reachable_branches_deep.py` | `test_decide_branches.py`, `test_storage_branches.py`, `test_override_branches.py`, `test_entity_texts.py`, `test_takeover_branches.py`, `test_coverage_exclusions.py` |

De gedeelde hulpjes wonen in `tests/conftest.py` of in een van de
hulpbestanden `tests/flow_helpers.py`, `tests/live_helpers.py`,
`tests/live_fixtures.py`, `tests/guide_helpers.py`, `tests/repair_helpers.py`,
`tests/guard_helpers.py`, `tests/override_helpers.py` en
`tests/coverage_helpers.py`. Geen enkel `test_*.py` importeert nog uit een
ander `test_*.py`.

#### Verdere indeling

Deze indeling maakt af wat de opruimronde openliet: elke module bij één onderwerp,
geen module boven de 500 regels buiten de benoemde lijsten, en een modulegrens
die een grens is. Ook hier verhuist alleen code: dezelfde regels, dezelfde
`Reason`-waarden en `Problem`-codes, dezelfde opslagvorm en dezelfde entiteiten,
en een verhuizing die een regel inhoudelijk verandert, krijgt een eigen commit
erna. Alleen de twee gedragsbesluiten aan het eind veranderen wat de integratie
doet. Wie een van de bestanden hieronder anders wil indelen, wijzigt eerst dit
hoofdstuk.

De volgorde is van de minst naar de meest verweven stap; elke stap is één commit
en wordt pas gepusht als de voorganger groen is.

| Stap | Wat | Waarom hier |
|---|---|---|
| 1 | de `getattr`-terugvallen op attributen, en de dubbele sleutelwoordcontrole | raakt alleen de stand-ins in de toetsen en één regel |
| 2 | de kringen tussen `texts.py` en `entity_texts.py`, en tussen `problems.py` en `repair_notices.py` | alleen importregels |
| 3 | de impactkaart onafhankelijk van de omgeving | raakt alleen `script/` |
| 4 | de taakkeuze en de capaciteit uit `engine/constraints.py` | één bestand, één aanroeper |
| 5 | `engine/validation.py` per onderwerp | zuivere verhuizing van regelfuncties |
| 6 | een protocol per laag | haalt de terugimports onder `TYPE_CHECKING` weg |
| 7 | de `coordinator_*`-onderdelen zonder privé attributen van de coordinator | raakt de meeste bestanden |
| 8 | de mutatiebaan met `area_clash` en de lijst in de repo | meet de stappen hierboven |
| 9 | de twee gedragsbesluiten | pas als de verhuizingen gemeten zijn |

##### Stap 1 — geen terugval op eigen attributen

Een mixin leest een attribuut van de coordinator als `self.<naam>`. De dertien
regels `getattr(self, "<naam>", standaard)` in `state_store.py`,
`world_builder.py` en `hand_start.py` bestonden omdat een stand-in in de toetsen
het attribuut niet droeg; de stand-in krijgt het attribuut, en de mixin leest het
gewoon. `tests/test_coordinator_surface.py` eist al dat een stand-in elk lid
draagt dat zijn geleende methodes aanraken; zonder terugval geldt dat voor alle
leden. De controle op het trefwoord en de agenda's die de remmen voeden (nu
dubbel in `readability.unreadable_inputs` en `engine/hand_start.brakes_readable`)
staat op één plek in `engine/hand_start.py` en `readability.py` roept haar aan.

##### Stap 2 — geen kring tussen de algemene en de bijzondere module

| Bestand | Wat verdwijnt | Wat ervoor in de plaats komt |
|---|---|---|
| `texts.py` | de her-export van `entity_texts` onderaan, met `# noqa: E402` | de aanroepers importeren uit `entity_texts` |
| `problems.py` | de her-export van `repair_notices` onderaan, met `# noqa: E402` | de aanroepers importeren uit `repair_notices` |

De bewaking: geen `# noqa: E402` in het pakket.

##### Stap 3 — de impactkaart is niet van de machine

Een volledige run vervangt nu de kaart door wat hij zelf zag, en een lokale run
op Windows ziet de map `script/` voor `tests/test_controls_live.py` niet, de CI
wel. De kaart wordt een samenvoeging: een volledige run voegt bestaande regels
samen met wat hij ziet, en laat een regel alleen vallen als het toetsbestand of
het invoerbestand niet meer bestaat. Bewaking: een toets die een kaart met een
extra regel laat staan en een kaart met een ontbrekende regel afkeurt.

##### Stap 4 — de taakkeuze en de capaciteit

| Nieuw bestand | Onderwerp | Wat verhuist |
|---|---|---|
| `engine/circuit_requests.py` | wat een zone aan een circuit vraagt en krijgt | `Request`, `Grant`, `Outcome` |
| `engine/circuit_policy.py` | de taakkeuze op een circuit | `active_family`, `forced_families`, `choose_family`, `any_managed_running` |
| `engine/capacity.py` | de capaciteit en de kortcyclus | `standing_claims`, `keeps_claiming`, `apply_capacity`, `apply_short_cycle` |

`engine/constraints.py` houdt `resolve` en `finish`. De drie typen staan in een
eigen bestand omdat zowel `circuit_policy` als `capacity` ze nodig hebben en
`constraints` beide aanroept; zo blijft de richting naar beneden. De
aanroepers van `constraints.Request`, `constraints.Grant` en `constraints.Outcome`
importeren uit `circuit_requests`. `constraints.py` valt daarmee van
`FROZEN_MODULES`.

##### Stap 5 — de validatie per onderwerp

`engine/validation.py` houdt `validate()` en de ene `RULES`-lijst in de bestaande
volgorde; de regelfuncties staan per onderwerp, met een publieke naam (zonder
leidende onderstreping, want `validation.py` importeert ze).

| Nieuw bestand | Onderwerp | Wat verhuist |
|---|---|---|
| `engine/problem.py` | de klacht zelf | `Problem` |
| `engine/validation_shared.py` | gedeelde controles en hulpjes | `pinned_season`, `season_names`, `duplicates`, `windows`, `outdoor_is_known` en de seizoensregel |
| `engine/validation_zones.py` | zones | de dubbele zone-id's, een entiteit twee keer in een zone, een eenheid in geen zone, de zoneregels, het rooster, de vastlooptijd, de buitenbanden en het maximum van een vooruit-verzoek |
| `engine/validation_sources.py` | bronnen en generatoren | de dubbele bron-id's, het buitenvenster en de gebieden van een bron, de families, de generatoren en de exclusieve groepen |
| `engine/validation_circuits.py` | circuits | de dubbele circuit-id's, een eenheid op twee circuits, de circuitregels, de indeling en de wisseltijden |
| `engine/validation_residents.py` | bewoners | de bewoner zonder aanwezigheid, de slaapinstellingen en het stiltevenster |
| `engine/validation_windows.py` | vensters | de vensters zonder lengte, het halve gastenvenster en de feestdagenagenda's |
| `engine/validation_openings.py` | openingen | de dubbele opening-id's, de openingen, de huisbrede stops, de open stand van een afdekking en de vastzittijd onder de ingestelde rust |

Een regel die twee onderwerpen raakt, staat bij het onderwerp waarvan hij een veld
controleert. `MODULE_EXCEPTIONS` verliest de ingang `engine/validation.py`. De
importeurs van `Problem` (`engine/__init__.py`, `engine/manual_sources.py` en de
toetsen) importeren uit `engine/problem.py`.

##### Stap 6 — een protocol per laag

Een protocol dat alleen leden noemt (attributen en `Callable`-typen, zonder
methodelichaam) kan gewoon als basis geërfd worden: er ontstaat bij het draaien
niets dat een echte methode kan overschaduwen. Daarom:

- `coordinator_surface.py` (`CoordinatorSurface`) wordt met die vorm geschreven en
  door de mixins en de `coordinator_*`-onderdelen gewoon geïmporteerd. De
  `TYPE_CHECKING`-terugimports van `coordinator_events`, `coordinator_lifecycle`,
  `coordinator_reporting`, `coordinator_round` en `coordinator_tracking`, het
  `_CoordinatorBase`-omweg van `hand.py` en de zeven andere mixins, en de
  stubs `def naam(self) -> X: ...` verdwijnen.
- `flow_surface.py` (`FlowSurface`) is hetzelfde voor de configuratiestroom:
  de indexen en lijsten die de `flow_*`- en `form_*`-functies lezen en de stappen
  die ze aanroepen. `ClimateDirectorOptionsFlow` erft het, en de
  `TYPE_CHECKING`-terugimport van `config_flow` verdwijnt uit negen bestanden.

`NAMED_EXCLUSIONS_BUDGET` in `tests/test_coverage_exclusions.py` zakt tot het
getal dat dan overblijft (de bedoeling is 41 of lager); de bewaking blijft een
ratel die alleen kan dalen.

##### Stap 7 — de onderdelen van de coordinator zonder privé attributen

De zes `coordinator_*`-onderdelen krijgen de coordinator als eerste argument en
lezen en zetten nu ruim tachtig privé attributen ervan. Dat wordt:

| Onderdeel | Eigen staat (klasse in `coordinator_state.py`) | Wat erin staat |
|---|---|---|
| `coordinator_tracking.py` | `TrackingState` (`coordinator.tracking`) | `commanded_off`, `commanded_on`, `precipitation_seen_at` |
| `coordinator_round.py` | `RoundState` (`coordinator.round`) | `issued`, `sent_setpoints`, `family_since`, `family_seen`, `cancel_deferral`, `clock_reeval_unsub`, `lock`, `debouncer` |
| `coordinator_reporting.py` | `ReportingState` (`coordinator.reporting`) | `unusable_since`, `unusable_latest`, `unsupported_since`, `unapplied`, `waiting` |
| `coordinator_events.py` | `EventsState` (`coordinator.events`) | `refused` |
| `coordinator_lifecycle.py` | `LifecycleState` (`coordinator.lifecycle`) | `restored`, `closing` |

Wat een mixin bezit en een onderdeel moet lezen (de verzoeken en de overbrugging
van de vooruit-verzoeken, de teruggegeven handen, het thuiskomst- en
slaapmoment, de opslag) krijgt een publieke naam op de coordinator, zoals
`zone_override_until` die al heeft; de methodes van een mixin die een onderdeel
aanroept krijgen ook een publieke naam. Een onderdeel roept een ander onderdeel
rechtstreeks aan (`coordinator_reporting.note_unusable(coordinator, …)`) en niet
meer via een dunne methode op de coordinator. De coordinator houdt alleen de
methodes die Home Assistant, een mixin of een platform aanroept. `coordinator.py`
blijft onder de 500 regels of staat op `FROZEN_MODULES`.

Bewaking: `tests/test_module_boundaries.py` eist dat geen enkel bestand van het
pakket behalve `coordinator.py` een attribuut met een leidende onderstreping
leest of zet op een naam `coordinator`, en dat geen onderdeel een privé functie
van een ander onderdeel aanroept.

##### Stap 8 — de mutatiebaan

`script/mutation_probe.py` krijgt mutaties op `area_clash`: de aanroep weg, de
overnemer niet overslaan, verliezers en eigenaars verwisseld, `kept.pop` weg, de
beste eigenaar vervangen door de slechtste, en een rivaal buiten het gebied. De
lijst van mutaties waarmee de verhuizingen gemeten worden staat in `script/`, niet
alleen op de machine van wie meet.

##### Stap 9 — twee gedragsbesluiten en een gemeten vervolg

| Punt | Besluit | Wat er gebeurt |
|---|---|---|
| Een geweigerde winnaar van een gebied | laten zoals het is | de verliezer blijft die ronde onbediend en de volgende ronde beslist opnieuw; de uitkomst valt aan de veilige kant (kort koud, nooit twee systemen tegelijk). Het ontwerp onder "Nog te bouwen" noemt het terugzetten van het verzoek als alternatief en blijft staan als idee. |
| Een bron zonder `autostart` buiten een groep met de ketel | `validate()` waarschuwt | een nieuwe `Problem`-code meldt een bron zonder `autostart` die in het gebied van een ketel staat en in geen enkele exclusieve groep; het gedrag van de engine verandert niet |
| Een ketel in meer dan één zone zonder `covers_zones` | `validate()` meldt het | een nieuwe `Problem`-code meldt een ketel die in meer dan één zone staat terwijl `covers_zones` ontbreekt, want zonder dat veld is er geen gebied en dus geen bescherming |

Beide meldingen krijgen een vertaling in alle zeven tekstbestanden en een regel
in de zes gidsen. Wat een probe meet en wat niet, staat in de release notes.

##### Bewijs per stap

Hetzelfde bewijs als bij de eerste indeling: de engine- en v1-probe byte-gelijk,
de E-, N- en Q-probes identiek, een gebiedsprobe gelijk (behalve voor stap 9),
`pytest --collect-only` zonder verdwenen toets, een ast-vergelijking van de
functielichamen, dekking 100 %, de poort op het getal van stap 6, de kaart schoon
en de mutatielijst volledig gevangen.

### Uitbreidbaarheid — de vorm die dat mogelijk maakt

Nieuwe poorten, bronrollen, conflictbeleiden en circuitbeperkingen haken elk op één
bestaande module aan zonder de pijplijn te wijzigen. Nieuwe kunde die niets met Home
Assistant te maken heeft hoort per definitie in `engine/`, met tests ernaast.

Dat blijft alleen waar zolang de code een vorm houdt waarin een toevoeging een
*toevoeging* is en geen verbouwing. Die vorm is geen smaak. De reden dat 34 losse
automatiseringen onhoudbaar werden, is dat elke nieuwe wens een bestaande moest
openbreken; dit zijn de zeven regels die dat hier tegenhouden, met per regel wat hij
voorkomt.

1. **Één module doet één ding**, in één zin te omschrijven — `gates.py` mag het,
   `hysteresis.py` moet het, `sources.py` waarmee. *Voorkomt* dat een wijziging in het
   ene onderwerp het andere sloopt.
2. **De afhankelijkheden lopen één kant op.** Gebruikt A B, dan gebruikt B nooit A.
   *Voorkomt* een kring waarin niets meer los te vervangen of te testen is.
3. **Denken staat los van doen.** Dat is de scheidslijn hierboven, en het is de
   belangrijkste van de zeven. *Voorkomt* dat je een draaiende Home Assistant nodig hebt
   om te weten of de besliskunde klopt.
4. **Gegevens zijn dataclasses, geen losse dicts.** Een `Zone` heeft vaste velden; in een
   dict past alles wat je intikt. *Voorkomt* een typefout die pas maanden later in een
   huis opvalt.
5. **Een functie past op één scherm.** *Voorkomt* een bijwerking veertig regels verderop
   die niemand — mens noch agent — nog overziet.
6. **Elke belofte heeft een bewaking die rood wordt als je hem sloopt.** Niet "er is een
   test", maar "draai de reparatie terug en er valt iets om". *Voorkomt* het patroon waar
   dit project de meeste rondes aan kwijt is: de reparatie staat er, de eigenschap is
   niet vastgepind.
7. **Uitbreiden gebeurt via een lijst, niet via een `if`.** Een nieuwe controle is een
   functie erbij in een lijst, geen tak erbij in een bestaand blok. *Voorkomt* dat elke
   toevoeging bestaande code moet openbreken en dus kan breken.

**Een grens die alleen opgeschreven staat, is geen grens** — regel 6 geldt ook voor deze
regels zelf. Bewaakt zijn: dat `engine/` Home Assistant nergens importeert
(`tests/test_the_border.py`, met `ast.walk`, dus ook een import binnen een functie; de
bewaking merkt het ook als zij niets te scannen vindt, zodat een verplaatsing van
`engine/` haar niet stil uitzet), dat elk formulier uit de bron werkelijk opengaat
(`TestEveryFormInTheSourceIsWalkedTo`), en dat de bewakingen zelf kloppen
(`tests/test_the_guards_themselves.py`).

De grensbewaking heeft één bewust smalle kant, en die hoort hier te staan zodat niemand
hem voor breder aanziet: hij leest **letterlijke** imports van `homeassistant`. Een
relatieve import naar de andere helft van het pakket (`from ..coordinator import ...`) en
een import die pas op het draaimoment ontstaat (`importlib.import_module`) glippen er
langs. Beide zijn vandaag onbereikbaar — er staat er geen enkele — maar de scheidslijn
hangt in die twee vormen nog steeds aan het lezen van de code.

**De maat wordt bewaakt als een ratel** — regel 6 geldt ook voor de maat zelf:
`tests/test_the_measure.py` houdt de norm vast zoals hij hier staat — groter dan wat er
genoteerd is mag niet, kleiner betekent "haal hem van de lijst" — met de definitie van
"regels" erbij: een module telt als het aantal fysieke regels van het bestand
(`len(text.splitlines())`), een functie als `end_lineno - lineno + 1`, van de eerste
regel die `ast` aan de `def` toekent tot en met de laatste regel van het blok, en er
wordt met `ast.walk` over élk bestand onder `custom_components/climate_director/`
gelopen, dus een geneste functie telt mee. Boven de 500 regels groeit een module niet meer
(`test_modules_over_five_hundred_lines_do_not_grow`): wie zo'n module raakt, zet het
geraakte onderwerp in een eigen module.

De maatbewaking heeft één bewust smalle kant, en die hoort hier te staan zodat niemand
haar voor breder aanziet: `function_sizes()` klapt twee gelijknamige functies in één
bestand samen tot de langste. Zijn er ooit twee gelijknamige functies boven de 80, dan
wordt alleen de langste bewaakt. Vandaag onbereikbaar — er zijn 18 gelijknamige paren en
de grootste is 38 regels — en dat staat hier zodat een volgende ronde het niet als bug
aanmeldt.

**De maat.** Een module blijft onder ~700 regels, een functie onder ~80. Geen wet, wel de
grens waarboven de vraag hoort te vallen: *doet dit ding er inmiddels twee?*

**Waar de code die maat niet haalt.** Gemeten na S1 t/m S6 — 33
bestanden, 15.309 regels: zes modules staan boven de 700 regels, zeventien functies boven
de 80, en die zes grootste bestanden dragen samen 8.638 regels, 56,4% van het geheel. Dat
is geen schoonheidsfout: vier van de zes — `coordinator.py`, `config_flow.py`,
`engine/models.py` en `engine/decide.py` — hebben aantoonbaar fouten voortgebracht,
telkens dezelfde vorm.

- **`coordinator.py` (1698).** De coordinator was één klasse met 67 methodes die zeven
  banen tegelijk had — opslag, luisteraars, de momentopname bouwen, problemen melden,
  vooruit-verzoeken, events en drie soorten timers — en de zes nagebouwde coordinators
  in de testset braken erop af; dat is verholpen: sinds S4 staat de opslag (herstel en
  quarantaine inbegrepen) in `state_store.py`, de momentopname in `world_builder.py`, en
  de vooruit-verzoeken met hun timers in `preconditions.py`. Het bestand zelf blijft
  boven de maat doordat wat overblijft — luisteren, beslissen, uitvoeren en publiceren —
  samen in één module staat.
- **`config_flow.py` (1476).** Per scherm liepen formulier bouwen, valideren en opslaan
  door elkaar; dat is verholpen: sinds S5 bouwt `schemas.py` per scherm het `vol.Schema`
  uit de huidige waarden, en houden de stapmethodes de navigatie, de validatie en het
  opslaan. Het bestand zelf blijft boven de maat doordat alle stapmethodes samen in één
  module staan, en het punt is daarmee verplaatst, niet opgelost: `schemas.py` telt 1101
  regels en staat er dus óók boven.
- **`schemas.py` (1101).** Gebouwd in S5: per scherm het `vol.Schema` uit de huidige
  waarden, zodat de stapmethodes in `config_flow.py` de navigatie, de validatie en het
  opslaan houden. Het bestand staat boven de maat doordat alle schermschema's samen in
  één module staan.
- **`engine/models.py` (2021).** `validate()` was één functie van 549 regels; dat is
  verholpen: hij is nu een lus over `_RULES`, een lijst regelfuncties die elk één
  controle doen, dus een controle erbij is een functie erbij. Het bestand zelf blijft
  boven de maat doordat het model en de regels samen in één module staan.
- **`engine/decide.py` (1618).** `_build_commands` (zone-bronnen) en
  `_generator_commands` (gedeelde warmtebronnen) bestaan nog, maar de gedeelde
  beslissingen zijn eruit getrokken naar functies die beide paden aanroepen:
  `_untouched_reason` (onbereikbaar, hoofdschakelaar uit, anker 2),
  `_opening_stop_reason` (anker 5), `_opening_rest_hold` (de herstart-rem),
  `_unreadable_reason` (de blind-reden) en `_idle_mode`. Een eigenschap die op het
  ene pad gerepareerd wordt kan daardoor niet meer op het andere blijven staan — drie
  eerdere bevindingen waren alle drie díé fout. Wat per pad
  blijft zijn de pad-eigen keuzes: override, handbediende bron en gekozen-bron-commando
  bij de zone-bron; vraagvolging en stop-reden bij de gedeelde warmtebron.

- **`engine/serialise.py` (724).** De enige plek waar de platte dict van de config entry
  naar de dataclasses van `engine/models.py` vertaald wordt, en terug; het lezen is
  bewust vergevingsgezind. Het bestand staat boven de maat doordat alle modellen samen in
  één module geserialiseerd worden.

Het plan is uitgevoerd: S1 t/m S6 staan op `main`, en verplaatsen veranderde geen
gedrag — de volledige suite bleef bij elke stap even groen als ervoor, met
`python tests/measure_short_cycles.py` onveranderd op **OK**. Wat de maat voortaan
vasthoudt is de bewaking hierboven (`tests/test_the_measure.py`), niet dit document.

**De veldtabel.** Eén instelling toevoegen raakte nog steeds te veel
plaatsen: de dataclass in `engine/models.py`, lezen en schrijven in
`engine/serialise.py`, het formulier in `schemas.py`, de opslag in `config_flow.py`,
en bij een veld met bedieningstoestand ook de verbruiker in de engine — plus de zeven
tekstbestanden. Dat is de fabriek van "op het ene pad gerepareerd, op het pad ernaast
vergeten". Daarom is de ketting voor het instellingenscherm korter:
`engine/fields.py` draagt één declaratieve veldtabel per scherm — naam, type,
standaard, vertaalsleutel en doel in het model — en zowel `schemas.py` (het
formulier) als `engine/serialise.py` (de opslag van dat scherm) lezen daaruit. De
tabel woont bewust in `engine/`, zodat `serialise.py` haar met een gewone import
binnen het pakket leest en de engine-grens heel blijft; daarom staat er geen enkele
selector en geen `vol.Schema` in — die vertaling kent alleen `schemas.py`. Het
instellingenscherm is de eerste tabel; nieuwe schermen volgen hetzelfde patroon. De
bewakingen die de formulierbron met een AST lezen (`form_field_nodes` en de
veldenkaarten) zijn meeverhuisd: een veld in de tabel telt als een veld in het
schema, en een `schemas.<naam>` die niet bestaat is een fout in plaats van een
stille lege kaart.

**De veldtabel wordt het patroon voor lijst-itemschermen.** Het
instellingenscherm was de eerste tabel, en het is het minst representatieve
scherm dat er is: het is het enige scherm dat geen lijst-item bewerkt. Daarom
leest ook het **bronscherm** zijn velden uit `SOURCE_FIELDS`, en daarmee
staat het patroon vast voor elk scherm dat één item uit een lijst bewerkt: de
tabel zegt wélke velden er zijn, `schema_fields._table_schema` krijgt de
waardebron expliciet mee — de installatie voor het instellingenscherm, het item
zelf (`values=current`) voor een lijst-item — en de opslagkant schrijft elke rij
terug naar haar puntpad.

**De opslagkant is generiek.** `config_flow.py` schrijft een scherm niet meer
veld voor veld terug; `schema_fields.write_table` loopt de tabel af en zet elke
formulierwaarde op haar `target`-pad in de doeldict: genest (`outdoor.minimum`
maakt de tussenliggende dict aan), met eenheidsomrekening waar de tabel een maat
noemt (`temperature` en `delta_celsius` gaan door `to_celsius`, `minutes` maal
zestig), en leeg wordt `None` voor een optioneel veld. Wat een scherm eigenzinnig
doet staat als expliciete haak in de tabel (`hook=`) in plaats van als een tak
in de stapmethode: de zomermaandenlijst die met de hand gekozen is blijft staan,
`precipitation_states` wordt komma-gesplitst en gesorteerd, `holiday_keyword`
wordt getrimd, en `shadow_mode` gaat naar de bedieningstoestand in plaats van
naar de installatie.

**Wat bewust met de hand blijft**, en dat hoort hier te staan zodat een volgende
ronde het niet als achterstallig werk aanziet: het toekennen van een `source_id`
(`_unique_id`), de verwijdertak van een bron, `_drop_source_references` en
`_renamed_house_wide`, de veldvalidatie (`_missing`), en de afsluitregel
`when_done`. Dat zijn geen velden maar navigatie, identiteit en opruiming; ze
generiek maken is risico zonder winst.

**De telling, gemeten en niet geschat.** Er zijn **23** schermen. Het
instellingenscherm is omgezet, en het bronscherm erbij; van de **21** die
overblijven dragen er **zeven** echte gegevensvelden (zone 21, resident 15,
circuit 11, en window / quiet / opening / generator elk 6) en zijn de overige
**veertien** keuzelijsten en menu's — één rij die zegt wélk item je wilt
bewerken — waar een veldtabel niets aan toevoegt.

**De engine-grens blijft heilig.** De tabellen wonen in `engine/fields.py`,
zonder één selector en zonder één `vol.Schema`; `tests/test_the_border.py`
bewaakt dat `engine/` Home Assistant nergens importeert, en dat blijft gelden nu
`serialise.py` de tabel leest.

### De bewakingen bewaken — en daar houdt het op

De testset bewaakt de integratie; `tests/test_the_guards_themselves.py` bewaakt
de bewakingen. Daar houdt het op: er komt geen bewaking op de bewaking van de
bewaking, want die regressie is oneindig. Wie een bewaking wijzigt, wijzigt
haar unittests mee; wie een bewaking alleen met een losse mutatierun valideert,
heeft haar niet gevalideerd.

**Stopregel** (een bewuste beslissing): iets telt alleen als
bevinding wanneer het gedrag raakt dat een gebruiker merkt, óf met een
gedraaide mutatie in deze repo bereikbaar is zónder een plugin te installeren
die niet in `requirements_test.txt` staat. Randen in de testset zonder
bereikbaar scenario gaan naar `ROADMAP.md`, niet naar een nieuwe restlijst.

### Welke toetsen draaien — alleen die van de wijziging

Een toets draait alleen als er iets veranderd is in het deel dat hij toetst, en niets
draait twee keer. `script/select_tests.py` kiest de toetsbestanden uit
`tests/impact_map.json`: per toetsbestand de bestanden die het **bij het draaien**
uitvoerde (de pakketcode, gemeten met coverage, met per toetsbestand een eigen
context) en opende (een gids, een vertaling, een script, en de mappen die het
doorliep), plus de pakketmodules die het bij naam importeert. De kaart komt dus uit
de runtime en niet uit de spelling van een toets. Alles draait als de kaart ontbreekt,
als de basis onbekend is, als een toetsbestand verdwijnt, of als er iets verandert
dat elke toets raakt (de afhankelijkheden, `pyproject.toml`, `tests/conftest.py` en
de andere hulpbestanden in `tests/`, de selectie zelf en de testworkflow).

`script/run_tests.py` draait de selectie en meet de dekking: bij een volledige run
het hele pakket tegen de drempel en de poort, bij een selectie de gewijzigde
pakketbestanden op 100 % — de selectie bevat elke toets die zo'n bestand uitvoert,
dus die meting is volledig. Daarna vergelijkt hij wat de gedraaide toetsen echt
uitvoerden en openden met de kaart. In de CI valt de baan als de kaart iets mist;
lokaal (`script/test`) werkt hij de kaart bij, en die wijziging gaat mee in de commit.
De CI is de enige volledige meting: elke baan draait alleen als haar deel veranderde
(mypy alleen bij pakketcode, de baan op de oudste Home Assistant alleen bij het pakket
of de afhankelijkheden, hassfest en de HACS-validatie alleen bij de integratie). Er is
geen geplande run: zonder wijziging draait er niets. De mutatieprobe draait per
mutatie alleen de toetsen die het gemuteerde bestand raken, en alleen als dat bestand,
een van die toetsen of de probe zelf veranderde. Een release vraagt geen eigen
toetsronde — de tag volgt op de groene CI van de versiecommit.

## EN

Technical design document for anyone working on the code (not a user manual —
that is [`README.md`](README.md)). Each layer has exactly one responsibility.

**Units:** the engine and the stored configuration work in degrees Celsius —
that is the deliberate choice (follow Home
Assistant's unit rather than giving the engine a second system). The binding
layer is the one place that converts: the coordinator reads HA temperatures
into Celsius, the applier turns setpoints back into the user's unit, the form
shows and reads in that same unit, and the sensor attributes and the
`climate_director_decision` event publish in the user's unit (the event with a
`temperature_unit` field alongside). A source is read in the unit it reports
itself: `unit_of_measurement` on a sensor, `temperature_unit` on a weather
source, and only otherwise in the system unit. The outgoing side — sensor
attributes and the event — rounds to one decimal, in both systems. The display
for the user (`display_temperature`) also rounds to one decimal, in both
systems (a deliberate decision): two numbers less than one degree
Fahrenheit apart stay distinguishable in the sentence (`67.6 °F` versus
`68.0 °F`) instead of reading the same after rounding to whole degrees and
making the sentence contradict itself. One rounding rule for the whole display;
a second one next to it is exactly the shape this project has tripped over six
times. The engine and the applier keep computing unrounded.
**The diagnostics stay Celsius**: that is a developer dump, not a user-facing
display.

**Inventory list "every user-facing text names its unit"**: a
next review can *see* whether this list is complete instead of having to hope so.
Each sentence below converts Celsius with `display_temperature` — rounded, with
the unit behind it:

- `coordinator._wanted` — the `command_not_taking` repair notice;
- `coordinator.unsupported_modes` — the `unsupported_modes` repair notice;
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
These sixteen anchors therefore sit here, ahead of every module. Do not depart from
them without changing them here first.

1. **A running pre-conditioning request** is one concept throughout the engine:
   `world.preconditioning(zone_id)`. It passes everything except the master
   switch, an override, an opening standing open that nobody said "do it
   anyway" to, and a house-wide takeover running the opposing duty family: the
   same room is never heated and cooled at once, not even on request (anchor
   12). There is no time window: a hand-given request always outranks the
   automation, whatever the hour, for the full `max_precondition`. The bounds are
   the request's own expiry plus the confirmation on an open door — the same
   principle as: whoever stays up late keeps their heating. There are two ways
   to say that *do it anyway*: the `ignore_openings` flag on a single request,
   and the per-opening bypass of anchor 8. They mean the same and do not stack.
   There is deliberately no pre-conditioning window; a
   pre-conditioning window per weekday is therefore not an idea but a reversal
   of that decision.
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
   A second brake stands beside it: a source may carry its own
   `min_cycle_time` (`Source.min_cycle_time`), even when it sits on no circuit;
   empty or zero means no own brake. A source on a circuit keeps that circuit's
   rest — the own brake is a per-appliance lower bound and applies only to a
   source without a circuit. This anchor has thereby become **broader**: a rest
   can now hang on any appliance, not only on an appliance on a circuit; the
   fixed opening rest above stays alongside. A bypassed opening (anchor 8)
   does not lift this rest: bypassing is comfort, the rest is burner
   protection.
6. **The master switch off** means: the director lets go of everything and issues
   nothing, an `off` included — just like an override. Whoever wants everything
   off switches it off themselves; the director then leaves it be.
7. **A circuit refusal refuses the appliance on that circuit, not the zone.**
   When the first choice falls away with `SHORT_CYCLE_PROTECTION`,
   `CIRCUIT_AT_CAPACITY` or `CIRCUIT_CONFLICT_LOST`, the zone files its request
   again with the next source — exactly as with an unreachable appliance. The
   reserve takes over visibly (`op_reserve`). This anchor is broader than the old
   behaviour (the zone fell silent) and narrower than "every refusal moves on": a
   first choice stopped house-wide refuses the zone instead, with
   `OPENING_OPEN_ELSEWHERE`; that scenario covers the other side.
8. **A bypassed opening does not exist for the director.** With an opening's
   bypass on it counts nowhere any more: neither for suspending its own zones, nor
   for the house-wide stop. There is no half bypass. The bypass stands until
   somebody turns it back themselves — there is no duration — and while it is on
   with the opening really standing open, the integration says so: otherwise you
   heat a whole winter with a window open without anything mentioning it. The rest
   from anchor 5 does keep running. An opening carries its own `opening_id` and a
   name for this, like every other object type — without its own identity the
   switch hangs on the sensor's `entity_id` and disappears the moment that sensor
   is replaced. When the id is missing in older storage,
   serialisation derives it from the `entity_id`, unique per sensor — two
   openings on the same sensor each get their own switch. That derivation lives
   in one place (`serialise.opening_ids`) with two readers: the storage reader
   and the options flow, which reads the raw storage and fills a missing id on
   load so the save screen writes it along. Without that step the edit screen
   derives the id from the name you just typed, and then the bypass switch's
   `unique_id` switches: entity gone, history gone, every dashboard reference
   broken. `config_flow._unique_id(name, ...)` therefore only applies to a
   **new** opening. An opening without a name is called after its id, and since
   that is the `entity_id` the switch falls back to the sensor's friendly name.
   That fallback is read again every decision round, not once at setup: a sensor
   that only appears *after* the integration, or that is renamed later, gives
   the switch its new name without a reload. Home Assistant caches an entity's
   name and does not invalidate that cache when only the placeholder changes, so
   the switch drops it itself as soon as the label really differs
   (`switch._refresh_label`) — a known class: a snapshot taken at
   setup where the world can still change afterwards. A stored duplicate
   `opening_id` is refused by `validate()` with `duplicate_opening_id`.
9. **A holiday counts as a Saturday, except where that would let one resident
   hold the house up.** The quiet windows and the schedules translate a holiday
   into a Saturday, unless holiday windows have been given — those take over then.
   The wake deadline deliberately does **not**: otherwise one person's school
   holiday holds the house up while the other is working from home. The sleep
   window reads the real weekday and knows nothing of holidays. Three different
   answers, all three deliberate; changing one does not change them all.
10. **An outdoor bound is half-open: `[minimum, maximum)`.** Two windows meeting
    at the same value divide the scale exactly — no gap and no overlap, so no
    outdoor temperature can fall between two sources. The consequence is that a
    value exactly on the bound belongs to the upper window: a bound of 24 cools
    at precisely 24.0 too. A hand-written automation saying "above 24" cannot be
    reproduced exactly; the closest choice is the bound itself, not 24.1.
11. **An override with a duration carries its own ending; an override you switch
    off by hand does not.** The `climate_director.set_override` action takes a
    duration and a choice *on expiry*: switch the appliance off, or leave it be.
    When the time runs out the director carries that choice out as one command
    at that moment, and decides normally again afterwards — that is the only
    moment at which the end of an override issues anything itself. When somebody
    switches the override off by hand nothing special happens: the engine takes
    the zone back and the appliance only goes off if the decision makes that
    necessary. A source with `autostart: false` therefore keeps running until it
    is in the way. That same action sets the mode and the temperature itself, in
    the same decision round as the handover: done as two separate calls there is
    a window in which the director stands the just-set appliance down after all,
    and then the order of those two calls would have to carry a property that is
    written down nowhere. If the zone has no source that can deliver the
    requested mode, the action refuses with the same translated error as an
    unknown zone (`zone_no_source_for_mode`). The temperature field has no fixed
    range in the form: the value counts in Home Assistant's unit and is converted
    to Celsius. What the appliance itself accepts *is* a bound: the setpoint is
    clamped to the chosen source's `min_temp`/`max_temp`, by the same rule as the
    engine path (`clamped_target`). **Clamping, not refusing** — refusing would be
    a second rule beside the first, and then the two paths drift apart. That
    clamp hangs on the moment of **sending**, not on the moment of the call:
    between those two the appliance can start reporting its range or
    lose it — a cloud drop-out makes `min_temp` disappear for a while — and the
    decision round already holds the world of that moment. The service layer
    therefore only converts the unit; the clamp sits in the round that puts the
    command on the wire, where the same `clamped_target` applies as on the
    engine path. A call that cannot set anything still refuses, with
    `zone_no_source_for_mode`. Next to its ending the override keeps its **start
    time** (`zone_override_started`), taken from the same clock reading as the
    ending itself: two readings side by side would yield a progress ring that
    does not fit its own end time. That start time survives a restart, and a
    state file from before this field simply loads, with an unknown start time
    rather than a guessed one. Both actions take an **entity** as their target
    next to `zone_id`; without that field in the schema the cancel button of
    `simple-timer-card` would trip over validation, since that card sends the
    sensor itself as `target.entity_id` and Home Assistant merges that target
    into the data before schema validation. An entity then settles both the
    installation and the zone; only this integration's override switch and
    end-time sensor count, any other entity is a typo and is refused. That check
    is complete: the entry has to exist and be ours, the
    platform has to be this one, the domain has to be `sensor` or `switch`, and
    the `unique_id` has to start with our prefix and only then fit the pattern.
    Without those four, an entity of another integration with a look-alike id
    (`zone_<x>_override`) gets `unknown_installation` with a foreign `entry_id`
    alongside it, while the entity given does not even belong to this
    integration. Whoever ends the override — the switch, or either action — has
    the end-time sensor **write along at once**: the sensor reads its state from
    the coordinator, so without that step the debouncer would sit a second in
    between and only the next decision round would show the end time or
    `unknown`.

    **An override begins by lifting its zone's hand.** A hand at an appliance and an
    override are both interventions by the user; when somebody turns the override
    switch or `set_override` on after a hand, that override is the newer verdict and
    the zone's hand lapses at that moment. That is **broader** than the rule that only
    the same hand lifts a hand: an override is an intervention by the user too, but
    one that concerns the whole zone. Otherwise the zone would stay handed over after
    the override ended to a hand that a newer intervention had long overtaken, and the
    appliance the override switched on would keep running unregulated until the house
    slept, emptied or the next day began. The other side stays as it was: the hand
    lapses at the **beginning**, not at the ending, so a hand that arises during the
    override (somebody switches the appliance off at the appliance itself) stays and
    survives `clear_override` **and a restart**. That survival is **broader** than the
    rule that only the same hand lifts a hand: a restart lets the hand stand too. The
    exception to it is **smaller**: only an override the user set during the startup
    itself lifts that zone's stored hand, since that hand was not in memory yet at that
    moment. An override that comes back from the store therefore leaves the
    hand standing: that hand arose during that override and is younger than the
    override's beginning. And only the override's own zone loses its hand; a shared
    appliance that also serves another zone leaves that other zone's hand standing.

    **An override hands over every appliance of that zone, house-wide.** With a
    zone under override — the switch or the `set_override` action — every
    appliance that is a source in that zone is handed over: the director sends
    it no command at all, not even an on or off from another zone, and not the
    house-wide opening stop either. An override is an emergency button, not a
    lock, and that goes for the whole zone: whoever presses it knows something
    the director does not. The accepted price is as large as the rule: the
    "1 hour" button of a bedroom with the boiler thermostat as its second source
    hands that boiler over for that hour, so the other rooms get no gas heating
    then and a burning boiler does not go off. Whoever presses the button wants
    that room, and a central installation simply cannot be split per room. This
    is **broader** than the zone itself: the handover covers the appliances that
    are a source in it, house-wide. The other side stays as it was — an
    appliance that is a source in that zone alone changes nothing, and without
    an override there is no handover: with the switch off again, the engine
    simply takes the zone and its appliances back. For the other zones such an
    appliance is no candidate, exactly as `excluding` in `sources.select` is
    none; it is not in `passed_over` (it is no fault, so not "on reserve"), and
    a zone without another source reports `no_source_available`. A running
    handed-over appliance counts as standing firm (`_standing_firm`) for the
    circuit and the capacity, since there is nothing left to move about it. The
    `Generator` keeps its own rule for now — switching on is allowed, switching
    off is not — and that difference stands as an idea in `ROADMAP.md`.

    **A hand at the appliance does not hand over house-wide.** Pressing off at the
    appliance itself silences the zone that appliance hangs in — every zone hanging
    off it when the appliance is shared, since `_zones_of` silences them all. What
    does *not* happen is a handover in the sense of this anchor: only the switch and
    the `set_override` action hand a zone over, and only those two carry every
    appliance of the zone along house-wide. A shared appliance therefore stays
    available to the other zones — the hand says something about the room, not
    about the boiler that happens to hang there too. Whoever really wants a shared
    appliance out presses off at that appliance itself, or uses the switch to hand
    the whole zone over. This makes the anchor neither broader nor narrower: it
    already named the switch and the action as the two ways to hand over, and that
    is what the code does. The other side stays as it was: the switch on the
    bedroom with the boiler thermostat as its second source still hands that boiler
    over, and then the other rooms get no gas heating.

    **A hand lapses only through the same hand, through sleeping, through an empty
    house or through the next day.** Those are the four ways out, and there is no
    fifth: when the director switches an appliance on itself, that is not a hand at
    the appliance. `_notice_hand` therefore lifts the hand only when the active mode
    does not come from us: not when this round's changes (`last_changes`) carry a
    command in the same duty family for that appliance, and not when the bookkeeping
    of a switch-on just sent still explains that mode (an appliance sometimes reports
    its new mode a round later). Exactly as `_we_wanted_it_off` does not read our own
    off command as a hand. The plan on the table plays no part here: the moment the
    hand stands, the director leaves the zone alone, so a plan asking for that
    appliance is the plan from before the hand — and the same hand switching the
    appliance back on would then no longer lift its own hand. That is how a shared
    boiler switched on for the living room leaves the hand at the attic air
    conditioner standing: the same rule as above, seen from the other side. Switch an
    appliance on yourself, and the hand lapses for every zone hanging off that
    appliance, as always. This makes the anchor neither broader nor narrower: it
    already named the four ways out, and this names the event that is *not* one of
    them. The other side stays as it was: the same hand switching the appliance back
    on lifts the hand, just like sleeping, an empty house and the next day.
12. **A source's reach hangs on the source and names zones.** A source carries
    `covers_zones`: the zones it heats or cools along with it the moment it runs.
    Empty means *its own zone only* — the behaviour from before this setting, so
    a zoned installation notices nothing. The same appliance often sits as a
    separate source under several rooms; the engine therefore merges those areas
    on `entity_id`, exactly as an exclusive group does (`_group_entities`).
    Filling it in once is enough. This is the same shape as `Generator.zone_ids`,
    with one deliberate difference: empty means *nothing* here and *everything*
    there, because a fallback that is on by default is not a fallback but a
    surprise.

    **The statement hanging off it:** when a managed source inside that area
    drops out, the source owning the area takes the duty over, and no other
    climate appliance anywhere in that area delivers heat or cooling any more —
    not one that is perfectly reachable itself, and not one somebody switched on
    by hand. Otherwise the boiler heats the whole house while the air
    conditioners keep going, or the same room is heated and cooled at once. The
    appliances stood down this way carry `SHARED_SOURCE_TOOK_OVER`; the zone
    whose source dropped out keeps reporting what is really the matter
    (`op_reserve`, `SOURCE_UNREACHABLE`).

    **The takeover is per duty.** A takeover for heating only starts when a
    dropped-out source in the area could itself heat; for cooling likewise. A
    cooling-only source that comes out of its socket is therefore no reason to
    cover the area for heating: the boiler would otherwise put the whole house
    on gas all winter — its outdoor window set aside — because a plug came out.
    This makes the takeover **smaller** than "a source drops out, so the
    replacing source takes the area over". The other side is covered by the
    existing scenario: when an air conditioner that also heats drops out, the
    boiler still takes the heating over, and the taker-over still delivers no
    other duty beside it.

    **Unreachability makes the replacing source's outdoor window conditional.**
    With the outdoor temperature outside its window while a source in its area
    is unreachable, it fires anyway. The split on outdoor temperature therefore
    stays — it simply stops being a reason to leave a house cold. This is a
    **broadening**: until now an outdoor window was unconditional. The other
    side is covered by the window applying normally in every other situation,
    and by an empty `covers_zones` never letting this exception arise at all.

    **Unreachable is what the world calls unreachable:** `unavailable`,
    `unknown`, or an entity that is not there — the same definition
    `ClimateState.available` already carries. An appliance not taking its command
    does not count here: that is control state and it lives outside the engine.
    The takeover waits `takeover_delay` (five minutes by default, on the
    replacing source, zero is immediately) from the moment the appliance became
    unreachable, so a flapping integration does not light the burner every few
    minutes. When that moment is unknown there is nothing to wait for and the
    takeover applies at once. Switching back after recovery gets no brake of its
    own: that is `Source.min_cycle_time` and the opening rest from anchor 5, and
    a second brake beside those two is exactly how this engine ended up with two
    nearly identical paths before.

    **A hand-operated source is no trigger.** Only a source the director would
    switch on itself (*Start this appliance automatically* ticked) counts
    as a "managed source in the area". A source with that box unticked is one
    the director cannot lose — it would never have started it — so its dropping
    out is no loss that justifies a takeover; otherwise one unplugged bedroom
    air conditioner puts the whole house on gas. This is a **narrowing**, per
    source row: where the same appliance sits under another room with automatic
    start on, that row does count, since there the director would start it.
    The other side stays as it was: when the area is taken over for another
    reason, a running hand-operated source is still stood down.

    **This anchor broadens anchor 7 on one side.** There it says a circuit
    refusal refuses the appliance and not the zone, with the exception that a
    first choice stopped house-wide does refuse the zone
    (`OPENING_OPEN_ELSEWHERE`). The house-wide takeover is the second such
    exception: an appliance standing still because of it does not let its zone
    move on to a next source, since that room would then heat electrically
    inside an area the boiler is already warming.

    **What it is not.** It neither replaces the exclusive groups nor builds on
    them: those stay a manual exclusion, settled on zone priority. The takeover
    acts before them — it removes the appliances from the wishes, so the group
    has nothing left to choose. Let the group decide and the air conditioner
    wins on priority, the gas drops out with `other_source_chosen`, and the room
    with the broken unit is left holding `exclusive_group_lost`: a cold house
    instead of an expensive one. Beyond that the director restores no manual
    setting — an appliance switched off by this stays off, or heats if the
    control asks for it, but never returns to cooling by itself. And when the
    replacing source is itself unreachable there is nothing to take over:
    nothing is stood down and ordinary source selection does its work.
13. **A quiet window brakes only whoever comes home *after* that window began.**
    With at least one resident already home before the window began there is no
    quiet: the zones simply carry on regulating, even when their appliance
    happened to stand still at that moment. When somebody comes home to an empty
    house after the beginning, it stays quiet until the window lapses — exactly
    the behaviour from before this anchor. This anchor therefore makes the quiet
    window **narrower**: it no longer brakes everybody, only homecomers; the
    empty house with an arrival after the beginning covers the other side and
    stays quiet.
    Two separate conditions, and they need not be the same residents: "somebody
    was already home before the beginning" and "somebody is awake now". The sleep
    gate (`EVERYONE_ASLEEP`, `WAITING_FOR_SLEEPER`) is unchanged and does the
    second; this anchor is only about home-since.
    The homecoming moment lives per resident (`home_since`) and survives a
    restart of Home Assistant: it is stored and read back, a restart generates
    **no** new moment, and whoever is no longer home when it comes back loses it.
    Without a stored moment the reader falls back to HA's `last_changed` of the
    presence entity; right after a restart that is the restart moment, and then
    the resident counts as "just home" until the window ends — the quiet, safe
    side, which bites at most once.
    Guest mode lifts the quiet, but only inside the guest window:
    `_guests_carry_the_house` already says exactly when guests carry the house,
    and outside that window the ordinary rules apply.
    What "before the beginning" means: `home_since` lies before the start of the
    **current window occurrence**. Exactly on the beginning (21:00:00) counts as
    after it. A window crossing midnight begins on its start day — at 02:00 on
    Tuesday the beginning is Monday 21:00 — and for a holiday window (`holiday`,
    `any_day`) the same holds with the day the window began. Whoever leaves after
    the beginning and comes back is a homecomer: the moment lapses on leaving and
    is set again on returning.
    One `home_since` per resident, and **both** readers use it:
    `gates._quiet_hours` and the sleep-versus-homecoming comparison in
    `world_builder._resident` (a sleep reading only counts when it postdates the
    arrival). After a restart with a stored moment `sleeper.last_changed` (the
    restart moment) is ≥ that moment, so the sleep reading counts — the same
    outcome as before this anchor.
    The existing exceptions stay exactly as they are: an open schedule window of
    a resident who is home, and a running pre-conditioning request. The zone gate
    (`PRESENCE`, the attic) does not change: the quiet is house-wide, and the room
    gate still applies after the quiet.
    `home_since` is "who was home when" and is **redacted** in the diagnostics,
    just like `home` and `asleep`.

14. **The reason of a zone that stops belongs to the duty that ran.** When heating and
    cooling both refuse and one of the two just ran, *that* duty says why it stops:
    cooling that stops because the room is cool enough reports `satisfied`, even when
    heating would not be allowed by the weather outside at that moment. This anchor
    makes the reason **narrower** than "the more informative of the two refusals". A
    zone that was doing nothing keeps that ranking (`_best_refusal`), and so does a
    duty the zone does not know - cooling by hand in a zone without cooling. The duty
    travels along with the reason (`Demand.duty`, `ZoneDecision.duty`, outside
    equality), so the notice can say for `outdoor_outside_window` whether it is too
    warm outside to heat or too cold to cool. A reason from a gate, a circuit or a
    group carries no duty.
15. ***Wait for this sleeper until* applies to the morning after a night the house
    slept.** The house goes to sleep the moment everybody at home is asleep
    (`night.house_asleep_since`); while somebody at home is still up, a sleeper
    holds nobody back, not after midnight either. The moment
    (`WorldState.asleep_since`) stays as long as it falls inside the running night of
    at least one resident **with** a sleep window: whoever gets up for a moment at
    three, or gets up alone in the morning, does not undo the night, and whoever is
    still up late in the evening does not hold the moment. When it falls outside, the
    moment goes - in a house where nobody has a sleep window the boundary between two
    nights is the moment itself, so there it lapses as soon as nobody at home is
    asleep any more. A sleeper only waits on a moment after
    the latest start of their own sleep window (`night.slept_tonight`), so Friday
    night's moment does not count on Saturday night. This anchor makes the waiting
    **narrower** than "home, asleep and before today's deadline"; the evening before
    is covered by the sleep gate (`EVERYONE_ASLEEP`), as always. The moment survives
    a restart through the store. When it is unknown, for instance after a restart
    while somebody was up, nobody is waited for, and once everybody sleeps it is
    recorded after all. A resident at home without a sleep sensor never sleeps, so
    such a house never goes to sleep and waits for nobody in the morning. Such a
    resident is always awake, so another resident's rise brake does not brake
    there, unless the resident without a sleep sensor is braked too (anchor 16). The
    moment is redacted in the diagnostics, just like `home_since`. A **hand start**
    makes this waiting narrower: a zone somebody starts themselves passes
    `WAITING_FOR_SLEEPER` until the waiting is over. The other side stays: without a
    hand start nothing changes, and a hand start never passes `EVERYONE_ASLEEP` -
    the whole night is no morning wait.
16. ***Getting up only starts the house from* brakes one resident's getting up, and
    only the starting.** Before that time, on the brake's days (`RiseBrake`), that
    resident does not count as "up" for the wake gate; when nobody counts as up
    because of it, the house does not start, with `EARLY_RISER`. When somebody else
    without a brake gets up, the house simply starts. The brake never applies on a
    holiday. For a resident **with** a sleep window it only brakes whoever **gets
    up**, so after a night the house slept (anchor 15): whoever is still up late in
    the evening and an unknown moment are not braked there. Without a sleep window
    there is no night to read - the sleep sensor then counts around the clock - and
    that resident does not count as up on the brake's days before the brake time,
    even when the house's moment is unknown. The accepted price of that: whoever is
    still up at night in such a house does not start the house before the brake time.
    It is a brake on starting: a zone already running carries on
    regulating. Guest mode inside the guest window lifts the brake, a
    pre-conditioning request always goes first, and the quiet window and the
    schedules are untouched. *Wait for this sleeper until* keeps applying beside it.
    A **hand start** makes the rise brake narrower: the zone passes `EARLY_RISER`
    until the brake is over. The other side stays: without a hand start nothing
    changes, and the hand start never passes the master switch, openings, outdoor
    bounds, the season, short-cycle protection or the circuits.

    **Starting by hand.** When somebody switches an appliance on themselves - at
    the appliance, or with the *Start by hand* button per zone - while its zone
    waits on `WAITING_FOR_SLEEPER`, `EARLY_RISER` or `QUIET_HOURS`, the
    coordinator notes a hand start for that zone. An active mode coming from the
    director does not count, and neither does a source with *Start this appliance
    automatically* off: the director never switches that on, so there is no
    waiting to bridge. A shared appliance starts every zone it serves. The zone
    passes those three brakes and nothing else. The hand start lapses in the first
    readable round in which those three let the zone through without it, and
    further when everybody sleeps, when the house is empty or on the next day. A
    round with an unreadable presence or sleep sensor leaves it standing (see
    below). It survives a restart until then. In a zone without a waiting reason
    it does nothing.

### An unreadable input leaves a hand start standing

The three waiting brakes read four kinds of input. Two are a sensor per resident,
one is the holiday calendar, and the rest is clock and configuration. Without a
reading there is no answer to "is he home" or "is he asleep", and what the engine
reads then is a coloured guess: an unknown presence reads as away, an unknown
sleep sensor as awake, and an unknown calendar lets the day read as a working day.

| input | external? | feeds | without a reading | counts |
|---|---|---|---|---|
| presence entity per resident | yes, entity | `QUIET_HOURS` (home and `home_since`), `WAITING_FOR_SLEEPER` and `EARLY_RISER` (home), and the empty-house gate | reads as away; the wait and the rise brake can disappear and the house can count as empty; `QUIET_HOURS` then keeps standing instead | yes, when the resident has a presence entity |
| sleep sensor per resident | yes, entity | `WAITING_FOR_SLEEPER` and `EARLY_RISER` (asleep/up), and the night through `asleep_since` | reads as awake; the wait for the last sleeper can disappear; the rise brake can shift because somebody counts as up | yes, when the resident has a sleep sensor |
| holiday calendars (`holiday_calendars` with `holiday_keyword`) | yes, entity | `holiday_mode`, and through it the deadline, the quiet window, the rise brake and the schedules | `holiday_mode` falls back on the switch; on a holiday the day reads as a working day | yes, with a keyword and at least one calendar |
| guest mode switch | no, own state | `QUIET_HOURS` (guest mode lifts the quiet) | not applicable | no, never unreadable |
| holiday mode switch | no, own state | `holiday_mode` | not applicable | no, never unreadable |
| clock | no | all three | not applicable | no, always readable |
| schedules, sleep window, deadline, rise brake, quiet windows and guest window | no, configuration | all three | not applicable | no, always readable |
| `asleep_since` | derived from the sleep sensors | `WAITING_FOR_SLEEPER` and `EARLY_RISER` | unknown; nobody is waited for | through the sleep sensors |
| `home_since` | derived from the presence | `QUIET_HOURS` (anchor 13) | stays put; an unreadable state is no departure | through the presence entity |

The model is one collection of `UnreadableInput(kind, subject)` in
`WorldState.unreadable`. `ReadableInput` has three kinds: `PRESENCE` and `SLEEP`
with the resident as `subject`, and `HOLIDAY` without a subject because the
calendar hangs on the house. The binding layer fills the collection in
`readability.py`; the engine reads it in `hand_start.brakes_readable`. There is
no third loose flag: a new external input is a new `ReadableInput` plus one line
in the fill. Every `WorldState` field stands in exactly one of three classes
(`BRAKE_INPUT_FIELDS` with its kinds, `EXTERNAL_WORLD_FIELDS`,
`INTERNAL_WORLD_FIELDS`, all three in `tests/test_hand_start.py`), and
`test_every_world_field_is_classified` fails as soon as a field stands in none of
the three; `test_every_readable_input_belongs_to_a_field` fails for a kind without
a field. A new field therefore cannot appear unnoticed,
but the guard cannot know whether a field in `EXTERNAL_WORLD_FIELDS` feeds the
brakes after all: that stays a deliberate choice of whoever adds the field, with
the input table above as the yardstick.

A hand start therefore does not lapse in a round in which one of these inputs
has no reading. Unreadable here means: the entity is missing, or its state is
`unavailable` or `unknown`; every other state is a reading, including `none`,
`not_home` or `off`. Only inputs this installation actually uses count: a
resident without a sensor supplies no input, and the calendars count only with a
keyword. Once every input is readable again, the ordinary rule applies in that
first readable round: if the three brakes still hold the zone, the hand start
stays; if they let the zone through, it lapses. The three exits that have
nothing to do with the brakes remain: sleep (everybody at home has turned in),
an empty house and the next day. The first two are also derived only from a
readable world; the next day is the hard bound for a sensor that never returns.
The store stays version 1 and a file without `hand_starts` still reads as no
hand start.

The binding layer supplies readability as ordinary data in `WorldState`; the
engine decides what that means for the brakes. That keeps `engine/` free of Home
Assistant and of I/O. A short grace period was not chosen: it moves the same
problem to an arbitrary moment, still lets a hand start fall when the sensor
returns after the grace period, and asks for a second bound beside the next day.
Unreadability is not a term but the absence of a measurement, and the next day
already bounds whatever never comes back.

An unreadable presence is no departure either: the homecoming moment stays put
as long as there is no reading. Otherwise the sleep sensor would count as stale
after the return and the waiting would disappear anyway, letting the unreadable
round topple the hand start after all.

Nothing changes in the diagnostics and the decision sensor: they still name only
the zone ids under `hand_starts`. There is no new `Problem` code and no new
entity.

### What the binding layer gets right

The diagnostics also redact `sleep_in` and leave presence and sleep entities out
of `tracked_entities`, so a download cannot reveal a resident profile through the
entity list. `stored_state.py` carries the public `stored_time` and
`restore_commanded_off`; `state_store.py` stores `commanded_off` and restores it
only within `COMMANDED_WINDOW`, so an old switch-off no longer explains a late
report. The bypass switch writes only on a real state or name change.
`set_override` checks every target first and only then applies one. For a shared
appliance `engine/untouched.py` names the zone with the override, not the first
zone that happens to carry the appliance too.

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

The rules that keep this shape — and the places where the code does not meet them
today — are further down under "Extensibility — the shape that makes it possible".

### Overview

```
config_flow.py         wizard; writes one dict into entry.options
  schemas.py            builds each screen's vol.Schema from the current values
      │
      ▼
engine/serialise.py    dict → dataclasses (pure, forgiving)
engine/fields.py       declarative field table (name, type, default, translation, target)
      │
      ▼
Home Assistant (entity states, clock events)
      │
      ▼
  coordinator          gathers states, debounces, serialises
    state_store.py     stores, restores and quarantines what a person said
    stored_state.py     stored moments and our own switch-off
    preconditions.py   pre-conditioning requests and their timers
    overrides.py       override with a duration and the lifting of a hand
    room_presence.py   the room gate: occupied rooms and the grace period
    resident_reader.py one resident's reader: home, sleep, homecoming
    hand_start.py      the hand start: recognition, storage and expiry
    readability.py     the one reading of unreadability
    world_builder.py   the snapshot (build_world)
      │
      ▼
  world.WorldState     snapshot: one data object, nothing more
      │
      ▼
┌─ engine/ ────────────────────────────────────────────────────────┐
│                                                                  │
│  hand_start.py  the three brakes, readability, the re-check      │
│  gates.py       is regulating allowed (circumstances)            │
│      │                                                           │
│      ▼                                                           │
│  hysteresis.py  is regulating needed (temperatures)              │
│      │                                                           │
│      ▼                                                           │
│  takeover.py    who takes over a dropped-out source's area       │
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
│    resident_storage.py  a resident's morning settings            │
│  validation.py  validation rules outside the model              │
│  untouched.py   which zone leaves a shared appliance alone       │
│  night.py       the night: who sleeps, since when, who gets up   │
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
every `climate` entity (including `changed_at` for short-cycle protection), residents
(with `home_since`: when somebody came home), openings, and when each circuit took on its
current duty.

### gates.py — is it allowed

Looks only at circumstances, never at temperatures. Evaluated broadest to narrowest, so
the reported cause is the one a user would name first: master switch before open window
before nobody home.

A configuration without residents skips the gates about residents - those could never
pass. The room gate still applies there: it is about the room, not about who is in the
house. An opening without a
timestamp blocks immediately: suspending is the harmless direction to be wrong in, and
refusing to act on an unknown age would keep heating an open room.

The room gate has a grace period: a room that has just become empty still counts as
occupied for `presence_timeout` seconds, so somebody walking out of the door does not
feel the heating switch off at once. That period starts at a **departure**: the
transition from occupied to not occupied, and also the transition from occupied to
`unavailable` or `unknown`. Dropping out is no proof of emptiness, but a room that was
occupied and turns unreadable may just have become empty; the returning sensor decides
after that. That is **broader** than the rule that only a readable transition to not
occupied counts: a sensor dropping out while the room is occupied now lets the room run
through the grace period at most, instead of declaring it empty at once. The other side
is **smaller**: a room that was already unreadable and then turns not occupied gets no
fresh grace period, and an unreadable sensor with no occupied moment before it counts as
empty. The coordinator keeps each zone's departure moment and which rooms were occupied
in the store, and `world_builder._presence` passes that moment on instead of
`last_changed`. If a room is still unreadable at the restore while it was occupied, its
grace period starts at the restore moment. Without a stored moment the moment is
unknown, and then the room counts as empty: leaving an empty room alone is the harmless
side to be wrong on. A room without a grace period counts as empty the moment its sensor
drops out.

The sleep gate has two states. With nobody up, that is `EVERYONE_ASLEEP`. With somebody up
while another is still asleep at home, that sleeper's wake deadline
(`Resident.wake_deadline`) decides: before it they hold the house back with
`WAITING_FOR_SLEEPER`, after it they no longer do. No deadline is the state from before
that setting — the first one up then opens the house. The time stands deliberately apart
from the schedule: a schedule window also says when the house should go off again, this
time only says how long you wait for somebody.

That waiting only applies once the house has slept this night (anchor 15): a sleeper holds
nobody back while somebody at home is still up. And when everybody who is up got up too
early (`Resident.rise_brake`, anchor 16), that is `EARLY_RISER`, but only for a zone not yet
running: `_household` is told for that whether the zone runs.

The sleep sensor itself knows two bounds. The **sleep window** is the night: inside it
"phone on the charger" means somebody is in bed, and it is that window which switches the
house off at bedtime. **`Resident.sleep_in`** stretches only its morning, on the days that
allow it. The two stand deliberately apart: one window cannot do both jobs. Stretch it to
one in the afternoon and the charger counts as sleep on a Wednesday too, leaving the house
off while somebody works from home; cut it back to the weekend and nothing switches the
house off at night on a working day. The days of `sleep_in` hang on the **morning** rather
than on the evening before - otherwise this setting inherits `TimeWindow`'s midnight
anchoring, a trap nobody expects.

And one layer down, in the binding layer: **coming home is not sleeping**. The sleep sensor
knows getting up, not coming home. `ClimateDirectorCoordinator._resident()` therefore only
counts a sleep reading that postdates the arrival; whoever walks in with their phone still
on the car charger is wide awake. On equal timestamps - after a restart everything carries
the same moment - the reading does count, since suspending is the harmless side.

**A holiday does not count as a Saturday for this time**, unlike for the schedules. That is
a deliberate narrowing: one person's holiday is another's working day, and were a school
holiday to count as a Saturday, the late riser would hold up the whole house while the
other was working from home - including the very room they were sitting in. The days of
`WakeDeadline` therefore mean literally what they say. The other side is covered by
`WakeDeadline.holiday`: whoever wants to be waited for on a weekday off sets that flag, and
the time then applies on every holiday whatever the weekday. A holiday Saturday stays a
Saturday either way, because that day *is* a Saturday.

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

The **quiet windows** brake starting, not continuing: whatever already runs keeps its
ordinary regulation. They know three exceptions, in this order: guest
mode inside the guest window (`_guests_carry_the_house`), a resident who was already
home before this window began (`home_since < started_at`), and the existing open
schedule window of a resident who is home. Whoever comes home to an empty house after
the beginning stays quiet until the window lapses; that is the other side of anchor 13.
A **hand start** makes this window narrower too: the zone somebody starts themselves
passes `QUIET_HOURS` until the window is over. The other side stays: without a hand
start nothing changes, and the hand start never passes the master switch, an opening
or the room gate.

### night.py — the house's night

Everything about the house's sleep in one place, pure and without Home Assistant: who counts
as asleep (`asleep_at`, `asleep`: the sleep sensor inside the sleep window, with sleeping in
added), when a resident's current night began (`night_began`: the latest start of their
sleep window), whether the house slept during that night (`slept_tonight`), keeping that
moment round after round (`house_asleep_since`, anchor 15) and the rise brake
(`rise_braked`, anchor 16). `gates.py` reads it; the binding layer stores the moment and
hands it back to the engine in `WorldState.asleep_since`.

`slept_tonight` also looks at the resident. A moment older than twenty-four hours does not
count, and a resident who only came home after the house went to sleep did not sleep
through that night. The homecoming moment (`ResidentState.home_since`) comes from the
binding layer; when it is unknown the old outcome stands. That keeps a late arrival from
holding the house back in the morning and a stale moment from yesterday from counting as
a night.

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

When both duties refuse, the duty that just ran says why it stops (anchor 14); only a zone
that was doing nothing gets the more informative of the two refusals. Every answer says which
duty it is about (`Demand.duty`).

### takeover.py — who takes over

Anchor 12 as a module of its own. `in_force()` says, before source selection,
which takeovers hold at this moment: a source with an area (`covers_zones`) takes
over as soon as a managed source in that area is unreachable and has been for
long enough (`takeover_delay`, counted from the moment of dropping out; an
unknown moment is at once). The areas are merged on `entity_id`, exactly as an
exclusive group does — the same appliance often sits as a separate source under
several rooms, and filling it in once should be enough.

The two consequences hang off different moments, which is why they stand side by
side as two functions. `narrowing()` is input to `sources.select()`: inside the
area the taker-over is the only candidate and its outdoor window does not count
this round. `stop_others()` runs after the plan, since it depends on whether the
taker-over really got a duty: only then can the same room be heated and cooled at
once, and only then does an air conditioner add to a room the boiler is already
warming. Whatever stands down carries `SHARED_SOURCE_TOOK_OVER`.

A second function, `area_clash()`, belongs to the same area but concerns a different
moment: the choice between the boiler and another appliance that wants to run in its area,
while nothing has dropped out. A source with `covers_zones` heats its whole area, rooms that
did not ask for it included. If one room holds an air conditioner on the dead band and
another room in that same area picks the boiler, boiler and air conditioner run side by
side. `area_clash()` therefore leaves one side per area: the request with the most claim
(the boiler on a tie). If the boiler wins, the requests of other appliances in the area
lapse; if another appliance wins, every request for the boiler lapses. The losers are
returned rather than discarded, so the plan can still report what they wanted
(`EXCLUSIVE_GROUP_LOST`). The function runs inside `apply_exclusive_groups()`, before the
groups, and skips an appliance that already takes the area over: `stop_others()` handles
that. This is a deliberate choice for a cold room over two systems at once. What it does not
cover is listed under "Still to build".

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

`select()` also drops a handed-over appliance (`excluding`), exactly like a house-wide
stopped one, and `passed_over` does not name it. A handover is no fault but a decision by
the user, so such an appliance does not belong on screen as "on reserve". What lies beside
it stays: an unreachable source that outranked the chosen one still stands in that list,
even when a handed-over appliance sits in between.

### constraints.py — what may run together

`constraints.py` resolves the requests of one circuit. The duty choice (`active_family`,
the forced duties and the choice between two duties) stands in `circuit_policy.py`, the
capacity and the short cycle in `capacity.py`, and the request, the grant and the outcome
in `circuit_requests.py`.

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

The **master switch is an emergency stop, not an off switch** (a deliberate
decision): under `MASTER_DISABLED` the director sends nothing at all — an `off`
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
hand-operated appliance occupies the slot itself (`keeps_claiming` counts it), the rival
gets `CIRCUIT_AT_CAPACITY` for good, and that deliberately stays so. An
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
out of `validate()`, not out of an exception here. The translation itself is split
over `installation_storage.py` (general fields), `equipment_storage.py` (appliances
and areas), `resident_storage.py` (the resident and their morning) and
`storage_values.py` (safe reading); `serialise.py` is the entrance.

Booleans are explicitly *not* read as numbers: `True` is an `int` in Python, and a priority
of `True` would silently become 1.

A resident's three morning settings - *Sleeping in until*, *Wait for this sleeper until* and
*Getting up only starts the house from* - are read and written in `resident_storage.py`,
with one rule for all three: without a time there is no setting, even when days stand there.

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

The class consists of the coordinator and a series of mixins, each carrying one
subject. `state_store.py` stores, restores and quarantines what a person said by
hand — a pre-conditioning request and an appliance somebody switched off — and
restores the homecoming moment (`home_since`), `resident_reader.py` reads one
resident (home, asleep, readability) and keeps their homecoming moment,
`preconditions.py` manages the pre-conditioning requests and their timers,
`overrides.py` manages the override with its duration and lifts the hand of its
zone at its beginning, `room_presence.py` keeps track of which rooms are occupied
and when a room became empty or dropped out (the grace period of the room gate,
across a restart too), `hand_start.py` recognises the hand start at the appliance
or at the button, keeps it across a restart and lets it lapse, and
`world_builder.py` builds the snapshot with its readers, in which `reads_as_home`
is the only place reading a presence entity as home; the coordinator itself
listens, decides, executes and publishes.

Six things about it are subtle:

- **Everything in local, timezone-aware time.** Schedule windows are read in local time,
  while entity timestamps arrive in UTC. Mixing the two would put an open door's age hours
  out.
- **Circuit history comes from observation, not from the previous plan.** A unit somebody
  switches by remote changes a circuit's duty just as effectively as the director does, and
  the minimum-run timer has to respect that.
- **The homecoming moment comes from movements, not from a reading.** Whoever comes home
  sets the moment, whoever leaves loses it, and at startup the store fills it in or it falls
  back on the presence entity's `last_changed`. One moment for the quiet gate and for the
  existing sleep-versus-homecoming comparison, and redacted in the diagnostics.
- **One event per zone, and only on change.** A decision is recomputed on every state change
  of every tracked entity; firing each time would drown any automation listening for it.
- **That event also carries the decision in plain language.** Beside the identifiers stand
  `reason_text`, `action_text`, `source_name` and `message`: the reason as a sentence, what
  happens to the appliance, the name as the user sees it, and the ready-made notice the
  blueprint shows by default. The sentences come from `texts.py`; the identifier stays the
  contract — whoever filters on `reason` notices nothing of those four fields. The action
  follows the command the plan gives this appliance, not the reason: a zone held back by a
  gate gets a mode all the same, and saying "left alone" while the appliance is switched off
  is a lie the user watches happen.
- **The event carries the action as a fixed key too.** `action` is `heat`, `cool`, `off`,
  `stays_off` or `left_alone`: the key `action_text` is the sentence of, from the same call,
  so the two cannot drift apart. Whoever only wants to hear that something goes off filters
  on it instead of on a translated sentence.
- **The moment the house went to sleep comes from the rounds themselves.** `build_world`
  only reads it; `world_builder._note_house_asleep` asks `night.house_asleep_since` every
  round and writes it away as soon as it changes, so a restart in the middle of the night
  does not lose it. Redacted in the diagnostics.

The listeners are on from the start — so a state change during Home Assistant's startup is
not lost — but no decision is taken before the restore has run: `_async_evaluate` does
nothing while the `_restored` flag is unset, and that flag goes up in
`_async_on_hass_started`, after the restore of the store and before the first decision.
Without that gate the director decided on half a house: the sensors arriving during loading
wake the debouncer, and an appliance somebody switched off by hand earlier that day was switched on
again before `_handed_back` had been read — for the rest of the day. Noting (`_notice_home`,
`_notice_hand`, the precipitation) is allowed in the meantime, and the restore **merges**
rather than replaces, so a hand from during the startup does not quietly disappear under an
older stored verdict.

**What somebody does to an override or a pre-conditioning request in those seconds wins over
the restore.** Whoever turns the override switch during the startup, calls `set_override` or
`clear_override`, or sets or cancels a pre-conditioning request, says something about this
moment; the store holds a verdict from before the restart. The coordinator therefore notes per
zone **and per kind** what the user did to it before the restore: an override (the switch,
`set_override`, `clear_override`) goes into one note, a pre-conditioning request or its
cancellation into the other. `_restore_overrides` reads only the override note and the restore
of `until` only the request note. A fresh pre-conditioning request therefore no longer holds
back a stored override, and a fresh override no longer holds back a stored request:
`clear_override` does not keep the stored duration alive, `set_override` without a duration
does not inherit the stored end time and expiry choice, and a fresh request keeps its own end
time, but each leaves the other kind alone. `cancel_precondition` without zones notes every
zone in the request note and therefore leaves a stored override standing. The restore of
`bypass` does not replace but **merges**, so the `ignore_openings` choice of a fresh request
stands beside what was already there. A zone the user did nothing to simply reads the store,
exactly as before. The notes go once the restore is done; the restore of the switch position
itself (the `RestoreEntity` in `async_added_to_hass`) is no action by the user and therefore
does not count. Apart from that one point, only a decision is lost that way too, no input.
Nothing is written before the
restore either. Noting is allowed, but the store stays untouched until it has been read:
`Store.async_load` reads a pending write instead of the file, so if one is standing ready
the restore comes out on this moment's half-built state and the user's stored verdict is
gone. `_async_save_state` therefore only remembers *that* something needed saving, and
`_async_on_hass_started` writes once directly after the restore — also when the restore
itself fell over. An installation removed again during the startup writes nothing back: the
teardown gate (`_closing`) stands before that.

### applier.py — execution

Decides nothing. Asks `diff.py` what has to happen and turns that into service calls, or in
shadow mode only logs it. `climate.set_temperature` carries the `hvac_mode` too, so a unit
needing both a mode and a setpoint is served by a single call — two calls would briefly
leave it running the new mode on the old setpoint.

When a call fails, the response depends on what failed. A failed **stop** breaks the
assumption the rest of the plan rests on: the starts behind it would land on top of an
appliance that should have stopped, exactly the combination this design is meant to make
unreachable. Those **starts** therefore lapse — but the remaining **stops** carry on. The
commands are already sorted with the stops first, and an appliance that has to stop should
stop even when a different appliance refuses; one stubborn cloud link no longer holds back
the whole house-wide stop. A failed **start** stays harmless — only less happens than
planned — and the rest carries on.

A mode an appliance explicitly does not list in `hvac_modes` is not asked of it:
`diff.changes` drops such a command (unknown is allowed, exactly as `sources._reachable`
already does for heating and cooling), so an appliance without `off` does not fall over
every round and drag the starts along with it each time. `unsupported_modes` reports that
missing `off` just as it does a missing `heat` or `cool`.

### config_flow.py — the wizard

Holds no knowledge of climate rules, only of forms. The installation is built up in a local
copy and written out only on "Save and close". Saving halfway would reload the entry while
the user is still editing, pulling the ground out from under the flow they are standing in.

A stale cursor (to a zone just deleted, say) sends the user back to the menu rather than
raising: a config flow that crashes leaves a half-built installation behind with no way back
into it.

Since S5 the schemas live in `schemas.py`: that module builds each screen's
`vol.Schema` from the current values, and the `async_step_*` methods keep the
navigation, validation and storage. The `async_show_form` calls have
deliberately stayed in `config_flow.py`, because that is what the form guards
hang on.

**Property:** a screen you can enter, you can leave again — whatever the **optional**
fields hold or do not hold. "Discard and go back" arrives whenever the required fields are
valid. Every optional field therefore stands as a plain selector in the schema. The
converter knows exactly one `vol.Any` shape: `vol.Any(None, validator)` — which is what
`vol.Maybe(validator)` produces — and turns it into `allow_none: true`; every other shape
(a third branch, an empty string) makes the screen undrawable (measured). That
one shape still throws when the inner validator is a mapping schema
(`vol.Maybe(vol.Schema({...}))`), and the reversed order `vol.Any(validator, None)` does
not serialize — the order in the anchor is therefore not accidental. The
current choice of plain selectors is therefore **narrower** than the library allows:
`vol.Maybe(selector)` would draw too, but is redundant as long as the assumption below
holds and would only cover the scenario where the frontend hands in a cleared field as
`None`. That is an **assumption about the frontend, not a measurement**: the frontend
sends a cleared optional field as a missing key. Should that assumption fail, 31 of the 33
optional fields refuse both `None` and `""` — only the two text fields get through — and
the same symptom is back in full. A filled-in value still goes through the selector and
is therefore still validated; required fields are deliberately outside this promise (a
cleared required numeric field can still lock the screen), and an empty value must never
land in the configuration as such (`_blank_to_none`).

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

**Categories.** Every entity carries its `entity_category`, and that
choice changes what a user sees in their list: the observation sensors
(`sensor.*`) and the blocked/fallback/stuck binary sensors sit on
`DIAGNOSTIC`; the two `number` entities and the season picker on `CONFIG`; the
buttons and switches stay plainly visible (no category). One sensor is the
exception: a zone's override end-time sensor (`..._override_ends`) follows the
coordinator but belongs on a dashboard next to the override switch and therefore
deliberately stays visible. Nowhere is
`entity_registry_enabled_default` set: nothing disappears from existing
dashboards and cards, and that is a guarded property
(`test_entity_categories.py`), not a promise.

### texts.py — translated sentences going outward

The integration sends no messages of its own; where a notification goes is for a user to
decide. The **text** does come from here: a blueprint cannot translate, and a half-English
notice on a Dutch screen reads as a fault.

This module looks a sentence up in the language of the interface and falls back on English -
twice, in fact, since a translation may be missing *and* may have drifted from the code. The
sentences live under `exceptions` in `strings.json`, because Home Assistant validates the top
level of that file against a fixed schema.

The decision message has a second home here: the thirty reasons, the five action words
and the two connecting words of the message live under
`entity.sensor.zone_source.state_attributes...` and `entity.sensor.would_command...`. That
spot was chosen because hassfest accepts it and Home Assistant then shows the attribute
translated on the entity itself. `reason_sentence` and `action_sentence` read one piece, and
`decision_message` builds the sentence: `<room>: <action> — <reason>`, with the appliance and
its setpoint in between only when the director really drives that appliance. `decision_fields`
is the one call the coordinator still makes: it gathers the four readable fields (which
appliance, which action, which sentence) and lives here rather than in the coordinator,
because that one already sits on the measure list and the sentence is text, not binding. The
result is presentation; the identifier stays the contract.

One reason has a sentence per duty: `outdoor_outside_window` is *it is too warm outside to
heat* for heating and *it is too cold outside to cool* for cooling
(`state_attributes.outdoor_outside_window.state.<duty>`). `reason_sentence` takes that one
when the decision carries a duty (`ZoneDecision.duty`); without a duty it is the general
sentence, which names both.

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

The decision notifier filters on `reason` (*Only these reasons*), on `action` (*Only these
actions*) and on zone. An event without `action`, from an older integration, does not drop
out on the action filter: a filter that can never match would otherwise silence everything.

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

The hand-operated notice (`manual_sources`) is the only one with a fix flow. The long
explanation lives in `issues.manual_sources.fix_flow.step.init` (title and description,
all seven languages) — the place where Home Assistant shows it for a fixable notice; a
notice-level `description` may not sit beside it, because hassfest excludes the two for
fixable notices. The dialog really appears: the flow manager's opening call
(`{"issue_id": ...}`) does not count as a confirmation, only the second call does — the
same pattern as core's `ConfirmRepairFlow`.

### Still to build — design proposals

The ideas box lives in [`ROADMAP.md`](ROADMAP.md); here stands the design per idea, so it
is clear what it entails before any work starts. The priorities (should/could/would) follow
the ROADMAP.

#### Should have

**An unreadable presence or sleep sensor holds the last readable state for a moment (N14,
N15).** Today a dropped presence reads as *away* and a dropped sleep sensor as *awake*, so a
hand-started zone goes off (`EVERYONE_ASLEEP`, `NOBODY_HOME`) and every waiting zone starts
during the outage.
- Option (a), hand start only: the two reasons pass it too, as long as the cause is an
  unreadable presence. Narrow, but the waiting zones without a hand start keep starting.
- Option (b), every zone: the binding layer holds a resident's last readable state for a
  short time (`unreadable_hold`, an ordinary value in `WorldState`); afterwards the outage
  reads as it does now. One place solves N14 and N15, but it changes the behaviour of every
  installation and therefore needs an anchor decision first.
- The user decides between (a) and (b) before anything is built.

**Notices name the setting in the user's language (N16).** The rules in
`engine/validation_*.py` fill `settings`, `window` and `label` with English words
("sleep window", "quiet window", "minimum cycle time"); `problems.readable` puts them
unchanged into the translated sentence. Design: the engine supplies fixed keys instead of
words (`wake_by`, `sleep_in_until`, `quiet_window`, ...), and the binding layer looks up the
screen word per key in the user's language, with the English key as the fallback.
- The words come from the same translation files as the screens, so the notice names the
  screen word and no word of its own.
- Guarded by a test that renders every notice in every language and demands that no English
  key word stands in it.

**The guard on the brake inputs measures behaviour.** The three-class classification forces
a deliberate choice. A perturbation test takes, per external field outside the brake inputs,
another value through a fixed test world and demands that the brakes give the same answer;
a field that feeds the brakes after all then shows up without anybody writing it down.

**Levelling live priorities on one circuit.** Two zones with the same priority on the same
circuit cannot both get their duty; the tie-break is now source and zone order. The idea is
to give a zone that waits long one temporary step of precedence, with a fixed maximum shift
and a fallback to the configured priority once the wait is over. That is a **broadening**
of source selection; the other side remains that the configured priority is the ceiling,
and without a wait the plan must stay exactly the same. Not built.

**A virtual `climate` per zone.** One control entity per room: a
`climate.climate_director_<zone>` that fits an ordinary thermostat card.
- Config: an option `virtual_climate_per_zone`, off by default. Existing entries lack the
  option and behave exactly the same (`serialise.py` falls back to the default).
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

**The agreements behind the source guards in the repo.** The structural agreements
that complement a source guard - the guard rule, which source guards there are and
what they cover - stand in `AGENTS.md`, and that file is in `.gitignore`.
- Place: a chapter of its own, *Guards and their agreements*, in this document,
  NL + EN, with per source guard the file, the agreement and what it covers and does
  not cover.
- Reference: the docstrings of the guards point at that chapter instead of at
  `AGENTS.md`; `AGENTS.md` keeps only the collaboration agreements.
- Guarded: `test_every_source_guard_names_its_coverage` can then also demand that
  every source guard stands in that chapter, since this document travels with the
  repo and CI can read it.
- Risk: two places for the same agreement. The move takes the agreements out of
  `AGENTS.md` in the same change.

**Align the generator with the override handover.** One rule for a handed-over
appliance, whether it hangs under the zone as a source or as a `Generator`.
- Engine: `decide._generator_commands` reads the same handover as `_handed_over`: a
  generator serving a zone under override gets no command at all any more, not even an
  on from another zone.
- Price: the other zones on that generator get no heat from it for that time, exactly as
  with a shared source (anchor 11).
- Guarded: the generator variant in `tests/test_override_handover.py` pins "switching on
  is allowed" and changes along; the source variant beside it is the example.

**Holiday calendar: read every overlapping appointment.** A calendar entity's state
shows only one running appointment.
- HA layer: `_calendar_says_holiday` asks `calendar.get_events` over the current moment
  and looks for the keyword in every appointment running then, rather than reading only
  the entity's state.
- Risk: a service call with a response per decision round; the outcome should be kept
  until the calendar entity itself changes.

**A timeout on the service calls.** A hanging cloud link holds the decision lock.
- HA layer: `applier._execute` bounds every call with `asyncio.timeout`; a call that does
  not come back in time counts as failed, under the existing rule: a failed stop lets the
  remaining stops through and only the starts lapse.
- Open choice: one fixed bound for every appliance, or a bound per source.

**Warn when the target temperature sits on the switch-off point.** The duty only ends
once the room sensor reaches the switch-off point.
- Config: the zone screen and `validate()` name a target at or beyond the switch-off point
  (`start_at + hysteresis` for heating, `start_at - hysteresis` for cooling) as a warning,
  not a refusal: it can work, but only when the appliance itself regulates further than
  the room sensor.
- Risk: a common setting falls under this itself; the notice explains and refuses
  nothing.

**A refused area winner gives the loser a second chance.** `area_clash()` takes the losing
request out of the wishes before the circuits judge. If the circuit then refuses the winner
(`CIRCUIT_AT_CAPACITY`, `SHORT_CYCLE_PROTECTION` or `CIRCUIT_CONFLICT_LOST`), the winner does
not run and the losing zone is left unserved for that round: the fallback loop in
`resolve_with_fallbacks()` only retries requests that are still in the wishes. The outcome is
on the safe side (briefly cold, never two systems at once).
- Option (a), leave it: a circuit refusal is temporary and the next round decides again.
- Option (b), put the losing request back as soon as the winner is refused. The room is
  served sooner, but the two appliances can alternate if the circuit and the area keep
  contradicting each other, and that needs a termination argument like the anchor 7 loop has.
- The user decides between (a) and (b) before anything is built.

**A source that does not start by itself but sits in a boiler's area belongs in a group with
that boiler.** `area_clash()` looks at requests from the director. A source with `autostart`
off never asks for anything: it is only held in check by an exclusive group or by
`manual_conflict()`. If such a source sits in a boiler's area and in no group, it can run
beside the boiler without the director stepping in (measured with an air conditioner running
by hand and a boiler asked for by another zone: the boiler gets `heat`, the air conditioner
is left alone as `MANUAL_SOURCE`).
- Option (a), implicit: every source without `autostart` in an area counts as a group member
  with that area's boiler. No filling in, but it changes the behaviour of every installation
  that has such sources.
- Option (b), warn: `validate()` reports a source without `autostart` in an area without a
  group with the boiler, and the user fills in the group. Narrow and visible.
- The user decides between (a) and (b) before anything is built.

#### Could have

**The open points of the clean-up round.** Six points, in order of weight: (1)
`engine/validation.py` (1288 lines) splits per subject (zones, sources, circuits,
residents, windows), each with its own rules, behind the same single `RULES` list in the
existing order. (2) `engine/constraints.py` (618) hands the duty choice and the
capacity/short cycle to `circuit_policy.py` and `capacity.py`. (3) Each `coordinator_*` part
gets a small state class of its own instead of reading and setting private attributes of
the coordinator (well over eighty places now). (4) The `TYPE_CHECKING` back-imports of `flow_*`
and `coordinator_*` disappear with a protocol per layer, which lets the exclusions gate go
from 75 back to 41 or lower. (5) `texts.py` keeps no re-export of `entity_texts.py` any more
(and `problems.py` no bottom import of `repair_notices.py`); callers import directly. (6) The
stand-ins in the tests get the attributes for which thirteen
`getattr(self, "<attribute>", default)` lines are a fallback. The impact map has a point of
its own: a full run merges existing lines with what it sees, so a local run on Windows no
longer drops the directory `script/`.

**A house-wide power ceiling.** `Source.wattage` + `DirectorConfig.watt_limit`; after the
circuit resolution a new installation-wide step in `constraints.py` trims the winners by
watts, on zone priority, and only ever holds back starts (never stops).

**A temperature schedule per zone.** `Zone.schedule`: windows with their own target
temperature; `hysteresis.py` picks the setpoint that applies by the clock. The config-flow
editor for such a schedule is the bulk of the work.

**Suggested circuit grouping.** Config flow only: group chosen climate entities on shared
`device` / `via_device` / manufacturer and offer it as a suggestion button. No engine
change; explicitly a proposal, since the relation often does not show.

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

### Code layout — the clean-up round

Since this layout every module stands with one subject. This round only moves code:
the same lines, the same `Reason` values and `Problem` codes, the same storage
shape and the same entities. A move that changes a line's meaning is not a move
but a repair, and belongs in a commit of its own. The tables below are the
agreement; whoever wants to rearrange a file changes this chapter first.

#### New files

| New file | Subject | What it holds or what moves there |
|---|---|---|
| `engine/models.py` | the installation as a whole | `DirectorConfig`; the small building blocks stand in the modules below |
| `engine/seasons.py` | season and precipitation | `Season`, `SeasonSource`, `SeasonSettings`, `PrecipitationSettings` |
| `engine/windows.py` | the time window | `TimeWindow` |
| `engine/residents.py` | the resident | `Resident`, `SleepIn`, `WakeDeadline` and `RiseBrake` |
| `engine/equipment.py` | appliances and how they hang together | `SourceRole`, `OutdoorWindow`, `ModeSettings`, `Source`, `Circuit`, `ConflictPolicy`, `Generator`, `Opening`, `HeatingLayout` |
| `engine/rooms.py` | the room and its gate choice | `ZoneGate`, `Zone`, `GateSettings` |
| `engine/validation.py` | every configuration check | `validate()` and one `RULES` list in the existing order: one entrance, one order. The rule functions stand per subject in `engine/validation_zones.py`, `validation_sources.py`, `validation_circuits.py`, `validation_openings.py`, `validation_residents.py`, `validation_windows.py` and `validation_shared.py`; `Problem` stands in `engine/problem.py`. |
| `engine/manual_sources.py` | the one-time notice about hand-operated sources | `manual_only_problems` |
| `engine/candidates.py` | who may take part | `handed_over`, `collect_wishes`, `serving`, the exclusive groups, `standing_firm` |
| `engine/grants.py` | who gets the duty | `resolve_with_fallbacks`, `resolve_circuits`, `zone_reasons`, `manual_conflict`, `exclusive_rival`, `stand_down` |
| `engine/commands.py` | building the command | `build_commands`, `generator_commands` |
| `engine/command_stops.py` | the stop bookkeeping and collapsing | `opening_rest_bookkeeping`, `stop_blocked`, `ignores_openings`, `collapse_shared`, `claim` |
| `engine/command_reasons.py` | why an appliance gets nothing | `was_running`, `received_heat`, `unreadable_reason`, `untouched_reason`, `opening_stop_reason`, `opening_rest_hold`, `idle_mode` |
| `engine/zone_decisions.py` | what a zone finally hears | `build_zone_decisions`, `lost_to_another_zone`, `command_order`, `clamped_target` |
| `engine/quiet.py` | the quiet window and the running zone | `guests_carry_the_house`, `quiet_hours`, `open_quiet_windows`, `was_home_before`, `zone_running`; this closes the cycle with `hand_start` |
| `engine/schedule.py` | the schedule as a gate | `schedule_open`, `counts_towards_schedule` |
| `engine/gates.py` | the gate as a whole | `closed`, the household gate, the openings, `house_wide_blocked`, `opening_rest_until`, and `brakes_remaining` (the gate reads the hand start, never the other way round) |
| `engine/hand_start.py` | the hand-start rule | `HAND_START_BRAKES`, `brakes_readable`, `passes`, `quiet_holds`, `early_riser_holds`, `waits_for_sleeper`, `up_and_about`, `still_in_bed`; no lazy import left |
| `engine/serialise.py` | the entrance of storage | `config_from_dict`, `config_to_dict`, `opening_ids` |
| `engine/installation_storage.py` | general installation fields | gates, guest window, seasons, precipitation, layout and the sleep window |
| `engine/equipment_storage.py` | appliances and areas | reading and writing source, mode, outdoor bound, circuit, generator, opening and zone |
| `engine/resident_storage.py` | the resident in storage | the resident plus its three morning settings |
| `engine/storage_values.py` | reading stored values safely | the new name of `storage_helpers.py`; every reader gets a public name (`as_dict`, `items`, `weekdays`, `sequence`, `strings`, `text`, `float_or`, `optional_float`, `int_or`, `optional_int`, `bool_or`, `seconds_or`, `time_or`, `choice`) |
| `coordinator_surface.py` | the binding layer's surface | `CoordinatorSurface`; every mixin reads its host here |
| `coordinator.py` | the coordinator itself | `__init__`, the properties, `async_request_evaluation`, the clock and the lifetime; it inherits the public mixins and keeps a thin method per part that calls the function in the `coordinator_*` module |
| `coordinator_lifecycle.py` | starting and stopping | `async_start`, `_async_on_hass_started`, `tracked_entities`, `_calendar_says_holiday`, `async_shutdown` |
| `coordinator_tracking.py` | what an appliance does by itself | `_handle_change`, `_notice_precipitation`, `_notice_hand`, `_note_commanded_off`, `_note_commanded_on`, `_we_wanted_it_off`, `_we_wanted_it_on` |
| `coordinator_round.py` | one decision round and its clock | `_async_evaluate`, `_remember_families`, `_with_family_history`, `_schedule_deferral`, `_cancel_pending_deferral`, the clock repetition |
| `coordinator_reporting.py` | what the binding measures and reports | `unusable_entities`, `unsupported_modes`, `waiting_seconds`, `unusable_latest`, `stuck_zones` and the note and report functions beside them |
| `coordinator_events.py` | the events going out | `_fire_events`, `_fire_refusals`, `_refusal_data`, `_friendly`, `_open_openings`, `_event_data`, `wanted` |
| `hand_start.py` | the hand start in the binding | `HandStartMixin`: recognition, storage and expiry of a hand start |
| `hand.py` | the hand at the appliance | `HandMixin`: `zones_of`, `zones_handed_back`, `everyone_asleep`, `house_is_empty` |
| `overrides.py` | the override | `OverridesMixin` (public name; the same methods) |
| `preconditions.py` | the pre-conditioning request | `PreconditionsMixin` and `still_running` (public names) |
| `resident_reader.py` | reading the resident | `ResidentReaderMixin` |
| `room_presence.py` | room presence | `RoomPresenceMixin` |
| `state_store.py` | the binding layer's storage | `StateStoreMixin`; `_hand_starts_payload` is called directly |
| `world_builder.py` | building the snapshot | `WorldBuilderMixin`; the separate readers move to `entity_reading.py` |
| `entity_reading.py` | reading one entity | `reads_as_home`, `temperature_from_state`, `season_from_state`, `as_float`, `as_modes` |
| `stored_state.py` | stored moments and our own switch-off | `stored_time`, `restore_commanded_off` |
| `schema_fields.py` | the shape of a form field and the field table | the selectors (`CLIMATE`, `CLIMATE_MULTI`, `RANK`, `SECONDS`, `TEXT`, `TIME`, `band`, `choices`, `temperature`), `table_schema` and `write_table` |
| `form_common.py` | the fixed rows of every screen | `user`, `save`, `ADD`, `BACK`, `EXIT`, `EXIT_KEEP`, `EXIT_DROP`, the choice rows and `source_options`, `group_label`, `window_label`, `add_option`, `back_option`, `exit_row`, `managed_entities` |
| `form_installation.py` | the installation screens | `settings`, `exclusives`, `exclusive`, `quiets`, `quiet` |
| `form_zones.py` | the zone screens | `zones`, `zone`, `sources`, `source` |
| `form_circuits.py` | the circuit screens | `circuits`, `circuit`, `circuit_priorities`, `circuit_priority`, `generators`, `generator` |
| `form_residents.py` | the resident and window screens | `residents`, `resident`, `windows`, `window`, the weekday picker and the stored days |
| `form_openings.py` | the opening screens | `openings`, `opening` |
| `flow_installation.py` | the installation steps | `settings`, `exclusives`, `exclusive`, `quiets`, `quiet` |
| `flow_zones.py` | the zone steps | `zones`, `zone` |
| `flow_sources.py` | the source steps | `sources`, `source` |
| `flow_circuits.py` | the circuit steps | `circuits`, `circuit`, `circuit_priorities`, `circuit_priority` |
| `flow_generators.py` | the generator steps | `generators`, `generator` |
| `flow_residents.py` | the resident steps | `residents`, `resident` |
| `flow_windows.py` | the window steps | `windows`, `window` |
| `flow_openings.py` | the opening steps | `openings`, `opening` |
| `flow_validation.py` | the screen checks and form conversion | `settings_errors`, `zone_errors`, `name_errors`, `mode_errors`, `gate_errors`, `band_errors`, `heat_cool_from_form`, `zone_from_form`, `next_priority`, `all_source_ids`, `unique_id`, `deep_copy` |
| `repair_notices.py` | the specialised repair notices | the notices about unreadable, unusable modes, season, command, bypass, corrupt storage and the watchers |
| `entity_texts.py` | the readable decision | `reason_sentence`, `action_sentence`, `decision_message`, `decision_fields` and the keys around them |
| `services.py` | the service API | the schemas, target choice and registration of `evaluate`, `precondition`, `cancel_precondition`, `set_override` and `clear_override` |

The duty choice on a circuit stands in `engine/circuit_policy.py`, the capacity and
the short cycle in `engine/capacity.py` and the request, the grant and the outcome in
`engine/circuit_requests.py`; `engine/constraints.py` keeps the resolving of one
circuit.

`engine/decide.py` stays the only entrance of the decision; it holds only
`decide()` and the order of the steps. `config_flow.py` stays the only file Home
Assistant loads as the configuration flow; it holds the base class, the menu
navigation, the save and the shared readers. The steps themselves stand as
functions in the `flow_*` modules; `config_flow.py` keeps a thin method per step
that calls them. `problems.py` and `texts.py` stay the general entrances;
`repair_notices.py` and `entity_texts.py` carry the specialised subjects.
`__init__.py` stays the lifetime of the entry; `services.py` carries the service
API.

#### Boundaries

- `engine/` imports Home Assistant nowhere and performs no I/O; that stays
  guarded by `tests/test_the_border.py`.
- The direction is `engine/` ← binding layer ← Home Assistant platforms. A
  module only imports downwards; no cycle appears.
- The existing lazy imports in `engine/models.py` (the validation list) and
  `engine/hand_start.py` (the gate) disappear. The gate reads the hand start,
  the hand start does not read the gate; validation reads the model, the model
  does not read validation.
- Across a module boundary no name carries a leading underscore. The mixins,
  their helpers and the schema builders get a public name in the file where they
  live.
- `tests/test_module_boundaries.py` guards four of these borders with `ast` and
  `tokenize`: no private name across a module border, no `getattr(self, "<name>",
  fallback)` on an own member, no import inside a function and no `# noqa: E402` (an
  import stands at the top, without exemption).
- A field-table cell stays in `engine/fields.py`; the selectors and the
  translation to `vol.Schema` stay in the Home Assistant half.
- A new file is a subject, not a catch-all: no `utils`, `helpers`, `extra` or
  `misc`.

#### Order and proof

The order runs from the least to the most intertwined module. Every step is one
commit, every commit is green, and a commit is pushed only after its predecessor
is green.

1. public names and the names of the helpers (no move);
2. the tests per subject, the shared helpers to `tests/conftest.py` or a helper
   file in `tests/`, and the impact map;
3. validation in one module and `state_extra.py` to `stored_state.py`;
4. storage and serialisation;
5. the hand and the hand start apart, with `engine/quiet.py`,
   `engine/schedule.py` and `engine/gates.py`;
6. the configuration flow and the forms;
7. `engine/decide.py` with `candidates`, `grants`, `commands`,
   `command_reasons` and `zone_decisions`;
8. `engine/models.py` with `seasons`, `windows`, `residents`, `equipment` and
   `rooms`;
9. `coordinator.py` with `coordinator_surface`, `coordinator_lifecycle`,
   `coordinator_tracking`, `coordinator_round`, `coordinator_reporting` and
   `coordinator_events`;
10. the remaining large modules: `problems.py`, `texts.py` and `__init__.py`.

Per commit the proof is recorded in the commit message and in the progress file
in the repository root:

- `controle-*-probe-engine.py . all` (42 lines) and
  `controle-*-probe-v1-productie.py .` (64 lines) byte-identical to the
  base, with the log path and the time from the log;
- the three `controle-*-probe-eigen.py` probes (the E, N and Q series)
  identical on the base and on HEAD;
- `pytest --collect-only -q` as an old → new image: the same number, zero
  vanished and zero new tests except the deliberately moved ones;
- coverage 100 % lines and branches, the gate with 41 named exclusions or
  fewer, the map clean, and the mutation list at 66 of 66 caught;
- `git diff --stat -M` shows only moves and import lines; every line that is
  not a move is named in the message;
- the seven text files, `STORAGE_VERSION`, the `Problem` codes and the `Reason`
  values are equal to the base.

The impact map hangs off the selection: `script/select_tests.py` lets an added
package file or test file run the whole suite. A rename is a deletion plus an
addition in `git diff --no-renames` and therefore falls under the same rule.
`script/test` updates the map and the CI delivers it as the artifact `impact-map`.
The map is a merge: a run adds what it saw itself and drops nothing it did not see,
and only a test file, file or directory that no longer exists drops out. A local
full run on Windows does not see the directory `script/` for
`tests/test_controls_live.py`, the CI does; that line therefore stays, and the map
from a local run can simply go into the commit. The CI rejects a map that lacks a
line the run saw, not a map with an extra line. A changed existing file keeps the
ordinary selection.

#### Tests per subject

The round names disappear, and the round labels in the ratchet comments of `tests/test_the_measure.py` and the deep branch test go with them. This table is the move; a test coming from a campaign
file keeps its class and function name, so the collection shifts only by file
path.

| Old | New |
|---|---|
| `tests/test_campaign_editing.py` | `test_commissioning.py` (walking forms, adding, refusing, saving, deleting), `test_screen_state.py` (screen beside screen, rounding, discarding, empty fields, weekdays), `test_flow_branches.py` (the screen branches) |
| `tests/test_campaign_live_flows.py` | `test_options_flow_live.py`, `test_setup_live.py`, `test_restart_flow_live.py`, `test_storage_live.py`, `test_entity_reading_live.py`, `test_repair_live.py`; the house-wide list to `test_house_wide_openings_live.py` |
| `tests/test_campaign_live_ha.py` | `test_setup_live.py`, `test_services_live.py`, `test_lifecycle_live.py`, `test_startup_half_loaded.py`, `test_steering_live.py`, `test_controls_live.py`, `test_reporting_live.py`, `test_restart_live.py`, `test_translations_live.py`, `test_hand_live.py`, `test_storage_live.py`, `test_coverage_exclusions_live.py` |
| `tests/test_campaign_outages.py` | `test_outages.py` (the engine) and `test_outages_live.py` (the binding) |
| `tests/test_campaign_settings.py` | `test_season_settings.py`, `test_household_gates_live.py`, `test_holiday_calendar_live.py`, `test_delays_live.py`, `test_circuits_live.py`, `test_shared_boiler_live.py`, `test_hand_on_appliance_live.py`, `test_diagnostics_live.py`, `test_multiple_installations.py` |
| `tests/test_campaign_weather_boundaries.py` | `test_weather_boundaries.py` |
| `tests/test_campaign_year.py` | `test_year_simulation.py`; `BUSY` moves to `tests/simulation.py` |
| `tests/test_reachable_branches.py` | `test_flow_branches.py`, `test_options_flow_live.py`, `test_coordinator_surface.py` |
| `tests/test_reachable_branches_deep.py` | `test_decide_branches.py`, `test_storage_branches.py`, `test_override_branches.py`, `test_entity_texts.py`, `test_takeover_branches.py`, `test_coverage_exclusions.py` |

The shared helpers live in `tests/conftest.py` or in one of the helper files
`tests/flow_helpers.py`, `tests/live_helpers.py`, `tests/live_fixtures.py`,
`tests/guide_helpers.py`, `tests/repair_helpers.py`, `tests/guard_helpers.py`,
`tests/override_helpers.py` and `tests/coverage_helpers.py`. No `test_*.py` imports from another `test_*.py`
any more.

#### Further layout

This layout finishes what the clean-up left open: every module with one subject,
no module over 500 lines outside the named lists, and a module border that is a
border. Here too only code moves: the same lines, the same `Reason` values and
`Problem` codes, the same storage shape and the same entities, and a move that
changes a line's meaning gets a commit of its own afterwards. Only the two
behaviour decisions at the end change what the integration does. Whoever wants to
arrange one of the files below differently changes this chapter first.

The order runs from the least to the most entangled step; every step is one
commit and is pushed only when its predecessor is green.

| Step | What | Why here |
|---|---|---|
| 1 | the `getattr` fallbacks on attributes, and the doubled keyword check | touches only the stand-ins in the tests and one line |
| 2 | the cycles between `texts.py` and `entity_texts.py`, and between `problems.py` and `repair_notices.py` | import lines only |
| 3 | the impact map independent of the environment | touches only `script/` |
| 4 | the duty choice and the capacity out of `engine/constraints.py` | one file, one caller |
| 5 | `engine/validation.py` per subject | pure move of rule functions |
| 6 | a protocol per layer | removes the back-imports under `TYPE_CHECKING` |
| 7 | the `coordinator_*` parts without private attributes of the coordinator | touches the most files |
| 8 | the mutation lane with `area_clash` and the list in the repository | measures the steps above |
| 9 | the two behaviour decisions | only once the moves have been measured |

##### Step 1 — no fallback on own attributes

A mixin reads an attribute of the coordinator as `self.<name>`. The thirteen
`getattr(self, "<name>", default)` lines in `state_store.py`, `world_builder.py`
and `hand_start.py` existed because a stand-in in the tests did not carry the
attribute; the stand-in gets the attribute, and the mixin simply reads it.
`tests/test_coordinator_surface.py` already demands that a stand-in carry every
member its borrowed methods touch; without the fallback that holds for every
member. The check on the keyword and the calendars that feed the brakes (now
doubled in `readability.unreadable_inputs` and `engine/hand_start.brakes_readable`)
stands in one place in `engine/hand_start.py`, and `readability.py` calls it.

##### Step 2 — no cycle between the general and the specialised module

| File | What goes | What takes its place |
|---|---|---|
| `texts.py` | the re-export of `entity_texts` at the bottom, with `# noqa: E402` | the callers import from `entity_texts` |
| `problems.py` | the re-export of `repair_notices` at the bottom, with `# noqa: E402` | the callers import from `repair_notices` |

The guard: no `# noqa: E402` in the package.

##### Step 3 — the impact map is not the machine's

A full run now replaces the map with what it saw itself, and a local run on
Windows does not see the directory `script/` for `tests/test_controls_live.py`
while the CI does. The map becomes a merge: a full run merges existing lines with
what it sees, and drops a line only when the test file or the input file no
longer exists. The guard: a test that leaves a map with an extra line standing and
rejects a map with a missing line.

##### Step 4 — the duty choice and the capacity

| New file | Subject | What moves |
|---|---|---|
| `engine/circuit_requests.py` | what a zone asks of a circuit and gets | `Request`, `Grant`, `Outcome` |
| `engine/circuit_policy.py` | the duty choice on a circuit | `active_family`, `forced_families`, `choose_family`, `any_managed_running` |
| `engine/capacity.py` | the capacity and the short cycle | `standing_claims`, `keeps_claiming`, `apply_capacity`, `apply_short_cycle` |

`engine/constraints.py` keeps `resolve` and `finish`. The three types stand in a
file of their own because both `circuit_policy` and `capacity` need them and
`constraints` calls both; that way the direction stays downward. The callers of
`constraints.Request`, `constraints.Grant` and `constraints.Outcome` import from
`circuit_requests`. `constraints.py` thereby leaves `FROZEN_MODULES`.

##### Step 5 — the validation per subject

`engine/validation.py` keeps `validate()` and the one `RULES` list in the existing
order; the rule functions stand per subject, with a public name (without a
leading underscore, since `validation.py` imports them).

| New file | Subject | What moves |
|---|---|---|
| `engine/problem.py` | the complaint itself | `Problem` |
| `engine/validation_shared.py` | shared checks and helpers | `pinned_season`, `season_names`, `duplicates`, `windows`, `outdoor_is_known` and the season rule |
| `engine/validation_zones.py` | zones | the doubled zone ids, an entity twice in a zone, a unit in no zone, the zone rules, the schedule, the stuck time, the outdoor bands and the maximum of a pre-conditioning request |
| `engine/validation_sources.py` | sources and generators | the doubled source ids, the outdoor window and the areas of a source, the families, the generators and the exclusive groups |
| `engine/validation_circuits.py` | circuits | the doubled circuit ids, a unit on two circuits, the circuit rules, the layout and the switch times |
| `engine/validation_residents.py` | residents | the resident without presence, the sleep settings and the quiet window |
| `engine/validation_windows.py` | windows | the windows without length, the half-filled guest window and the holiday calendars |
| `engine/validation_openings.py` | openings | the doubled opening ids, the openings, the house-wide stops, the open state of a cover and the stuck time below the configured rest |

A rule that touches two subjects stands with the subject whose field it checks.
`MODULE_EXCEPTIONS` loses the entry `engine/validation.py`. The importers of
`Problem` (`engine/__init__.py`, `engine/manual_sources.py` and the tests) import
from `engine/problem.py`.

##### Step 6 — a protocol per layer

A protocol that names only members (attributes and `Callable` types, without a
method body) can simply be inherited as a base: at run time nothing comes about
that could shadow a real method. Therefore:

- `coordinator_surface.py` (`CoordinatorSurface`) is written in that form and
  simply imported by the mixins and the `coordinator_*` parts. The `TYPE_CHECKING`
  back-imports of `coordinator_events`, `coordinator_lifecycle`,
  `coordinator_reporting`, `coordinator_round` and `coordinator_tracking`, the
  `_CoordinatorBase` trick of `hand.py` and the seven other mixins, and the stubs
  `def name(self) -> X: ...` disappear.
- `flow_surface.py` (`FlowSurface`) is the same for the configuration flow: the
  indexes and lists the `flow_*` and `form_*` functions read and the steps they
  call. `ClimateDirectorOptionsFlow` inherits it, and the `TYPE_CHECKING`
  back-import of `config_flow` disappears from nine files.

`NAMED_EXCLUSIONS_BUDGET` in `tests/test_coverage_exclusions.py` drops to the
number that remains (the intention is 41 or lower); the guard stays a ratchet
that can only go down.

##### Step 7 — the coordinator parts without private attributes

The six `coordinator_*` parts receive the coordinator as their first argument and
now read and set well over eighty private attributes of it. That becomes:

| Part | Own state (class in `coordinator_state.py`) | What it holds |
|---|---|---|
| `coordinator_tracking.py` | `TrackingState` (`coordinator.tracking`) | `commanded_off`, `commanded_on`, `precipitation_seen_at` |
| `coordinator_round.py` | `RoundState` (`coordinator.round`) | `issued`, `sent_setpoints`, `family_since`, `family_seen`, `cancel_deferral`, `clock_reeval_unsub`, `lock`, `debouncer` |
| `coordinator_reporting.py` | `ReportingState` (`coordinator.reporting`) | `unusable_since`, `unusable_latest`, `unsupported_since`, `unapplied`, `waiting` |
| `coordinator_events.py` | `EventsState` (`coordinator.events`) | `refused` |
| `coordinator_lifecycle.py` | `LifecycleState` (`coordinator.lifecycle`) | `restored`, `closing` |

What a mixin owns and a part must read (the pre-conditioning requests and their
bypass, the handed-back hands, the homecoming and sleep moment, the storage) gets
a public name on the coordinator, as `zone_override_until` already has; the methods
of a mixin that a part calls get a public name too. A part calls another part
directly (`coordinator_reporting.note_unusable(coordinator, …)`) and no longer
through a thin method on the coordinator. The coordinator keeps only the methods
that Home Assistant, a mixin or a platform calls. `coordinator.py` stays under 500
lines or stands on `FROZEN_MODULES`.

The guard: `tests/test_module_boundaries.py` demands that no file of the package
except `coordinator.py` reads or sets an attribute with a leading underscore on a
name `coordinator`, and that no part calls a private function of another part.

##### Step 8 — the mutation lane

`script/mutation_probe.py` gains mutations on `area_clash`: the call gone, the
taker-over not skipped, losers and owners swapped, `kept.pop` gone, the best
owner replaced by the worst, and a rival outside the area. The list of mutations
the moves are measured with stands in `script/`, not only on the machine of
whoever measures.

##### Step 9 — two behaviour decisions and a measured follow-up

| Point | Decision | What happens |
|---|---|---|
| A refused winner of an area | leave it as it is | the loser stays unserved that round and the next round decides again; the outcome falls on the safe side (briefly cold, never two systems at once). The design under "Still to build" names putting the request back as an alternative and stays as an idea. |
| A source without `autostart` outside a group with the boiler | `validate()` warns | a new `Problem` code reports a source without `autostart` that stands in a boiler's area and in no exclusive group; the engine's behaviour does not change |
| A boiler in more than one zone without `covers_zones` | `validate()` reports it | a new `Problem` code reports a boiler standing in more than one zone while `covers_zones` is missing, because without that field there is no area and so no protection |

Both notices get a translation in all seven text files and a line in the six
guides. What a probe measures and what not stands in the release notes.

##### Proof per step

The same proof as with the first layout: the engine and v1 probes byte-identical,
the E, N and Q probes identical, an area probe equal (except for step 9),
`pytest --collect-only` without a vanished test, an ast comparison of the function
bodies, coverage 100 %, the gate at the number of step 6, the map clean and the
mutation list fully caught.

### Extensibility — the shape that makes it possible

New gates, source roles, conflict policies and circuit constraints each plug into one
existing module without changing the pipeline. New logic with nothing to do with Home
Assistant belongs in `engine/` by definition, with tests alongside it.

That only stays true as long as the code keeps a shape in which an addition is an
*addition* and not a rebuild. That shape is not a matter of taste. The reason 34
hand-built automations became unsustainable is that every new wish had to break open an
existing one; these are the seven rules that stop that here, with what each one prevents.

1. **One module does one thing**, describable in a single sentence — `gates.py` is it
   allowed, `hysteresis.py` is it needed, `sources.py` with what. *Prevents* a change in
   one subject from wrecking another.
2. **Dependencies run one way.** If A uses B, then B never uses A. *Prevents* a cycle in
   which nothing can be replaced or tested on its own any more.
3. **Thinking is separate from doing.** That is the dividing line above, and it is the
   most important of the seven. *Prevents* needing a running Home Assistant to know
   whether the decision logic is right.
4. **Data are dataclasses, not loose dicts.** A `Zone` has fixed fields; a dict holds
   whatever you type into it. *Prevents* a typo that only surfaces in a house months
   later.
5. **A function fits on one screen.** *Prevents* a side effect forty lines further down
   that nobody — human or agent — can still oversee.
6. **Every promise has a guard that turns red when you break it.** Not "there is a test",
   but "revert the fix and something falls over". *Prevents* the pattern this project has
   lost the most rounds to: the fix is there, the property is not pinned down.
7. **Extending happens through a list, not through an `if`.** A new check is one more
   function in a list, not one more branch in an existing block. *Prevents* every
   addition from having to break open existing code, and therefore being able to break
   it.

**A border that is only written down is not a border** — rule 6 applies to these rules
themselves too. Guarded are: that `engine/` imports Home Assistant nowhere
(`tests/test_the_border.py`, using `ast.walk`, so an import inside a function counts as
well; the guard also notices when it finds nothing to scan, so a move of `engine/` does
not silently switch it off), that every form in the source really opens
(`TestEveryFormInTheSourceIsWalkedTo`), and that the guards themselves are right
(`tests/test_the_guards_themselves.py`).

The border guard has one deliberately narrow side, and it belongs here so that nobody
mistakes it for a wider one: it reads **literal** imports of `homeassistant`. A relative
import into the other half of the package (`from ..coordinator import ...`) and an import
created at run time (`importlib.import_module`) slip past it. Both are unreachable today
— there is not a single one — but in those two shapes the dividing line still rests on
reading the code.

**The measure is guarded as a ratchet** — rule 6 applies to the measure itself too:
`tests/test_the_measure.py` holds the norm as written here — larger than what is noted
is not allowed, smaller means "remove it from the list" — with the definition of "lines"
included: a module counts as the number of physical lines of the file
(`len(text.splitlines())`), a function as `end_lineno - lineno + 1`, from the first line
`ast` assigns to the `def` through the last line of the block, and every file under
`custom_components/climate_director/` is walked with `ast.walk`, so a nested function
counts too. Over 500 lines a module grows no further
(`test_modules_over_five_hundred_lines_do_not_grow`): whoever touches such a module puts
the touched subject in a module of its own.

The measure guard has one deliberately narrow side, and it belongs here so that nobody
mistakes it for a wider one: `function_sizes()` collapses two same-named functions in one
file into the longest. Should there ever be two same-named functions above 80, only the
longest is guarded. Unreachable today — there are 18 same-named pairs and the largest is
38 lines — and that is written here so a next round does not report it as a bug.

**The measure.** A module stays under ~700 lines, a function under ~80. Not a law, but
the point past which the question should arise: *is this thing doing two jobs by now?*

**Where the code does not meet that measure.** Measured after S1 through S6 —
33 files, 15,309 lines: six modules sit above 700 lines, seventeen functions
above 80, and those six largest files carry 8,638 lines between them, 56.4% of the whole.
That is not a cosmetic flaw: four of the six — `coordinator.py`, `config_flow.py`,
`engine/models.py` and `engine/decide.py` — have demonstrably produced bugs, each time
the same shape.

- **`coordinator.py` (1,698).** The coordinator used to be one class with 67 methods
  holding seven jobs at once — storage, listeners, building the snapshot, reporting
  problems, pre-conditioning requests, events and three kinds of timer — and the six
  rebuilt coordinators in the test suite broke on it; that is fixed: since S4 the storage
  (restore and quarantine included) lives in `state_store.py`, the snapshot in
  `world_builder.py`, and the pre-conditioning requests with their timers in
  `preconditions.py`. The file itself stays above the measure because what remains —
  listening, deciding, executing and publishing — sits together in one module.
- **`config_flow.py` (1476).** Per screen, building the form, validating and storing used
  to run through one another; that is fixed: since S5 `schemas.py` builds each screen's
  `vol.Schema` from the current values, and the step methods keep the navigation,
  validation and storage. The file itself stays above the measure because all step
  methods sit together in one module, and the point has moved, not been solved:
  `schemas.py` counts 1,101 lines and so sits above it too.
- **`schemas.py` (1,101).** Built in S5: each screen's `vol.Schema` from the current
  values, so the step methods in `config_flow.py` keep the navigation, the validation and
  the storage. The file sits above the measure because all screen schemas live together
  in one module.
- **`engine/models.py` (2021).** `validate()` used to be one function of 549 lines; that
  is fixed: it is now a loop over `_RULES`, a list of rule functions each doing one
  check, so one more check is now one more function. The file itself stays above the
  measure because the model and the rules live together in one module.
- **`engine/decide.py` (1618).** `_build_commands` (zone sources) and
  `_generator_commands` (shared heat sources) still exist, but the shared decisions
  have been pulled out into functions both paths call: `_untouched_reason`
  (unreachable, master off, anchor 2), `_opening_stop_reason` (anchor 5),
  `_opening_rest_hold` (the restart brake), `_unreadable_reason` (the blind reason)
  and `_idle_mode`. A property repaired on one path can therefore no longer stay
  broken on the other — three earlier findings were all three
  *that* mistake. What remains per path are the path-specific choices: override,
  manual source and chosen-source command for the zone source; demand-following and
  stop reason for the shared heat source.

- **`engine/serialise.py` (724).** The only place where the config entry's plain dict is
  translated into the dataclasses of `engine/models.py`, and back; reading is
  deliberately forgiving. The file sits above the measure because all models are
  serialised together in one module.

The plan has been carried out: S1 through S6 are on `main`, and moving code changed no
behaviour — the full suite stayed exactly as green at every step, with
`python tests/measure_short_cycles.py` unchanged at **OK**. What holds the measure from
now on is the guard above (`tests/test_the_measure.py`), not this document.

**The field table.** Adding one setting still touched too many places: the
dataclass in `engine/models.py`, reading and writing in `engine/serialise.py`, the form
in `schemas.py`, the storage in `config_flow.py`, and — for a field carrying control
state — also the consumer in the engine, plus the seven translation files. That is the
factory of "fixed on one path, forgotten on the one beside it". Hence the
chain is shorter for the settings screen: `engine/fields.py` carries one declarative
field table per screen — name, type, default, translation key and target in the model —
and both `schemas.py` (the form) and `engine/serialise.py` (that screen's storage) read
from it. The table deliberately lives in `engine/`, so `serialise.py` reads it with an
ordinary import within the package and the engine border stays intact; therefore it
contains no selector and no `vol.Schema` — that translation belongs to `schemas.py`
alone. The settings screen is the first table; new screens follow the same pattern. The
guards that read the form source with an AST (`form_field_nodes` and the field maps)
moved along with it: a field in the table counts as a field in the schema, and a
`schemas.<name>` that does not exist is an error rather than a silently empty map.

**The field table becomes the pattern for list-item screens.** The
settings screen was the first table, and it is the least representative screen
there is: it is the only screen that does not edit a list item. Hence the
**source screen** also reads its fields from `SOURCE_FIELDS`, and that fixes the
pattern for every screen that edits one item out of a list: the table says which
fields exist, `schema_fields._table_schema` is handed its value source
explicitly — the installation for the settings screen, the item itself
(`values=current`) for a list item — and the storage side writes every row back
to its dotted path.

**The storage side is generic.** `config_flow.py` no longer writes a screen back
field by field; `schema_fields.write_table` walks the table and puts each form
value at its `target` path in the destination dict: nested (`outdoor.minimum`
creates the intermediate dict), with unit conversion wherever the table names a
measure (`temperature` and `delta_celsius` go through `to_celsius`, `minutes`
times sixty), and empty becomes `None` for an optional field. What a screen does
idiosyncratically sits as an explicit hook in the table (`hook=`) rather than as
a branch in the step method: a hand-picked summer-months list stays,
`precipitation_states` is comma-split and sorted, `holiday_keyword` is trimmed,
and `shadow_mode` goes to the control state instead of to the installation.

**What deliberately stays by hand**, and it belongs here so a later round does
not mistake it for unfinished work: assigning a `source_id` (`_unique_id`), the
delete branch of a source, `_drop_source_references` and `_renamed_house_wide`,
field validation (`_missing`), and the exit row `when_done`. Those are not
fields but navigation, identity and tidying up; making them generic is risk
without gain.

**The count, measured rather than estimated.** There are **23** screens. The
settings screen has been converted, and the source screen with it; of the **21**
that remain, **seven** carry real data fields (zone 21, resident 15, circuit 11,
and window / quiet / opening / generator 6 each) and the other **fourteen** are
pickers and menus — one row saying which item you want to edit — that a field
table adds nothing to.

**The engine border stays sacred.** The tables live in `engine/fields.py`,
without a single selector and without a single `vol.Schema`;
`tests/test_the_border.py` guards that `engine/` imports Home Assistant nowhere,
and that keeps holding now that `serialise.py` reads the table.

### The guards are guarded — and there it stops

The test suite guards the integration; `tests/test_the_guards_themselves.py`
guards the guards. There it stops: there will be no guard on the guard of the
guard, because that regression is infinite. Whoever changes a guard changes
its unit tests along with it; whoever validates a guard only with an ad-hoc
mutation run has not validated it.

**Stop rule** (a deliberate decision): something only counts
as a finding when it touches behaviour a user notices, or when it can be
reached with a mutation run in this repo without installing a plugin that is
not in `requirements_test.txt`. Test-suite edges without a reachable scenario
go to `ROADMAP.md`, not to a new rest list.

### Which tests run — only those of the change

A test only runs when something changed in the part it tests, and nothing runs twice.
`script/select_tests.py` picks the test files from `tests/impact_map.json`: per test
file the files it **executed while running** (the package code, measured with
coverage, with a context of its own per test file) and opened (a guide, a
translation, a script, and the directories it walked), plus the package modules it
imports by name. The map therefore comes from the runtime and not from the spelling
of a test. Everything runs when the map is missing, when the base is unknown, when a
test file disappears, or when something changes that touches every test (the
dependencies, `pyproject.toml`, `tests/conftest.py` and the other helper files in
`tests/`, the selection itself and the test workflow).

`script/run_tests.py` runs the selection and measures the coverage: on a full run the
whole package against the threshold and the gate, on a selection the changed package
files at 100 % — the selection holds every test that executes such a file, so that
measurement is complete. Afterwards it compares what the tests that ran really
executed and opened with the map. In CI the job drops when the map misses something;
locally (`script/test`) it updates the map, and that change goes into the commit. CI
is the only full measurement: every job only runs when its part changed (mypy only
for package code, the job on the oldest Home Assistant only for the package or the
dependencies, hassfest and the HACS validation only for the integration). There is no
scheduled run: without a change nothing runs. The mutation probe runs, per mutation,
only the tests that touch the mutated file, and only when that file, one of those
tests or the probe itself changed. A release asks for no test round of its own — the
tag follows the green CI of the version commit.
