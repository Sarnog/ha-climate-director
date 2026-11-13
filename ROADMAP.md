🇳🇱 [Nederlands](#routekaart) | 🇬🇧 [English](#roadmap)

---

# Routekaart

Dit bestand is de ideeënbus van deze integratie: toekomstige aanpassingen, verbeteringen
en uitbreidingen die nog **niet** gebouwd zijn, geordend als *should have* (waarschijnlijk
waardevol), *could have* (leuk, situationeel) en *would have* (later, apart traject). Nog
niet alles is besproken of goedgekeurd — het is een verzamelplek om uit te kiezen, te
prioriteren of af te wijzen.

De geschiedenis van wat er al gebouwd en gewijzigd is, staat **niet** hier maar in de
[release notes](https://github.com/Sarnog/ha-climate-director/releases) van elke versie.

De uitgewerkte ontwerpvoorstellen voor alles hieronder staan in
[`ARCHITECTURE.md`](ARCHITECTURE.md) onder "Nog te bouwen".

## Should have

- **Een onleesbare aanwezigheid van wie op is zet een handstart-zone alsnog uit (N14)** —
  de handstart blijft staan, maar `EVERYONE_ASLEEP` en `NOBODY_HOME` zijn geen remmen die
  hij passeert: valt de aanwezigheidsentiteit van de enige bewoner die op is weg, dan leest
  het huis als slapend of leeg en gaat de airco uit tot de entiteit terug is (gemeten:
  `cmds=[None, 'off', 'heat']`, drie ronden `everyone_asleep`). De releasenotes van de
  handstart-update zeggen dat de zone "gewoon blijft regelen". Keuze voor de gebruiker: (a) een handstart
  laat ook deze twee redenen passeren zolang de oorzaak een onleesbare aanwezigheid is, of
  (b) een onleesbare aanwezigheid houdt de laatst bekende lezing een korte tijd vast, voor
  alle zones (zie ook N15).
- **Een onleesbare slaapsensor laat alle wachtende zones starten (N15)** — zonder handstart
  leest een weggevallen slaapsensor als *wakker*: de wacht verdwijnt, de wachtende zones
  starten en bij terugkeer zet de director ze weer uit (gemeten in een controle,
  gedeelde ketel: alle drie de zones `regulating` tijdens de uitval, daarna twee keer
  `waiting_for_sleeper`). Hetzelfde ontwerp als N14 (b): een korte vasthoudtijd van de
  laatste leesbare stand.
- **Meldingen over dode instellingen noemen de instelling in het Engels (N16)** — de
  meldingen over een slaapinstelling zonder slaapsensor, een venster zonder lengte en een
  vastlooptijd onder de rust vullen `{settings}`, `{window}` en `{label}` met Engelse
  woorden uit de engine ("sleep window, wait for this sleeper until", "quiet window",
  "minimum cycle time"), ook in het Nederlands, Duits, Frans, Spaans en Arabisch. Gemeten:
  de Nederlandse melding eindigt op "...kunnen nooit werken: sleep window, wait for this
  sleeper until." De melding hoort het schermwoord van de taal van de gebruiker te noemen.
- **De bewaking van de remmen-invoer kan niet weten of een extern veld de remmen voedt** —
  `test_every_world_field_is_classified` dwingt een bewuste indeling af, maar een nieuw
  veld in `EXTERNAL_WORLD_FIELDS` dat de remmen toch voedt blijft groen. Een
  verstoringstoets zou dat meten: verander elk extern veld buiten de remmen-invoer en eis
  dat de remmen hetzelfde antwoord geven.
- **Virtuele `climate` per zone** — één bedieningsentiteit per ruimte, waarmee de gewenste
  temperatuur en stand rechtstreeks op een gewone thermostaatkaart te bedienen zijn. De
  director kiest daar dan de bron bij.
- **Poortinstellingen per zone voor wakker-, rooster-, stilte- en slaapregels** — die
  gelden nu in `GateSettings` voor de hele installatie. De keuze huishouden-vs-aanwezigheid,
  de aanwezigheidssensor en de nalooptijd zijn al per zone; een slaapkamer wil daarnaast
  andere slaap- en stiltevensters dan een woonkamer.

- **De structurele afspraken achter de bronbewakingen staan in een genegeerd bestand** — de
  docstrings van de tekstbewakingen verwijzen voor de afspraak achter de toets naar
  `AGENTS.md`, en dat bestand staat in `.gitignore`. Wie de repo kloont kan die afspraak dus
  niet nalezen, en een bewaking die er zelf naar zou kijken zou in CI omvallen. De afspraken
  horen in `ARCHITECTURE.md`, dat wél meegaat in de repo.
- **De generator gelijktrekken met de override-overdracht** — een `Generator` mag onder een
  override nog wél aangezet worden door een andere zone; alleen het uitzetten wordt
  ingehouden. Een apparaat dat als bron onder een overgedragen zone hangt krijgt helemaal
  geen commando meer, ook geen aan. Eén regel voor beide haalt dat verschil weg.
- **Vakantieagenda: alle overlappende afspraken lezen** — Home Assistant toont per
  agenda-entiteit maar één evenement, en een langere afspraak die eerder begon kan een
  vakantie-item maskeren; dan blijft de vakantiemodus ongemerkt uit. `calendar.get_events`
  over het huidige moment zou alle afspraken zien.
- **Een time-out op de service calls** — `apply` wacht met `blocking=True` zonder time-out
  terwijl de beslislock vastzit; één hangende cloudaanroep houdt elke volgende ronde tegen.
  Een begrensde wachttijd laat de director doorgaan met de rest.
- **Waarschuwen als de streeftemperatuur op het uitschakelpunt ligt** — de taak eindigt pas
  als de ruimtesensor het uitschakelpunt haalt; regelt het apparaat op zijn eigen sensor net
  daaronder, dan blijft de taak (en het circuit) eindeloos doorlopen. Het scherm kan zeggen
  dat een doel gelijk aan het uitschakelpunt geen marge laat.
- **Een geweigerde winnaar van een gebied geeft de verliezer geen tweede kans** —
  `area_clash()` laat per gebied (`covers_zones`) één kant over en haalt het verliezende
  verzoek uit de wensen vóór de circuits oordelen. Weigert het circuit daarna de winnaar,
  dan draait die niet en blijft de verliezende zone die ronde onbediend. De uitkomst valt aan
  de veilige kant (kort koud, nooit twee systemen tegelijk). Gekozen is (a), laten zoals het
  is; (b), het verliezende verzoek terugzetten zodra de winnaar geweigerd is, blijft een idee
  voor als een meting laat zien dat de kamer te lang koud blijft, tegen het risico dat de twee
  apparaten elkaar afwisselen (ontwerp in `ARCHITECTURE.md` onder "Nog te bouwen").

## Could have

- **De impactkaart hangt aan de selectie van de run** — code op moduleniveau draait één keer,
  bij het toetsbestand dat de module als eerste importeert. Een kleinere selectie in de CI dan
  lokaal (de commit tegen zijn voorganger, tegen alles wat nog niet gepusht is) legt die code
  bij een ander toetsbestand, en de kaartcontrole valt dan op een rij die lokaal klopte
  (`test_random_installations.py` kreeg zo `schemas.py`). De kaart zou de moduleniveaucode van
  het bestand dat hem importeert niet als eis moeten tellen, of lokaal de selectie van de CI
  moeten nabootsen (`CD_BASE` op de voorganger).
- **Een nieuwe import in een bestaande module verandert wat andere toetsen uitvoeren, en de
  selectie ziet dat niet** — een regel die een bestaande module importeert (hier
  `validation_sources.py` die `takeover.py` ging gebruiken) laat elke toets die `validate()`
  aanroept dat bestand ook uitvoeren, maar de selectie kiest alleen de toetsen die de kaart al
  bij het gewijzigde bestand noemt. De vier ontbrekende toetsen kwamen pas aan het licht in de
  volledige CI-run (rood op alleen de kaart). De selectie zou de toetsen moeten meenemen die het
  gewijzigde bestand indirect importeren, of de kaart zou ook per import vastleggen wie wie
  aanroept.
- **De `flow_*`-, `form_*`- en `schema_fields`-functies lezen ruim honderd privé cursors en
  lijsten van de configuratiestroom** (`flow._index`, `flow._installation`, `flow._list`...),
  dezelfde vorm als de privé attributen van de coordinator die de onderdelen niet meer lezen.
  `FlowSurface` noemt ze met een leidende onderstreping en de bewaking `coordinator._naam`
  ziet ze niet. Geef de stroom publieke namen of een eigen staatsklasse per scherm, en breid de
  bewaking uit tot `flow._naam` buiten `config_flow.py`.
- **Twee `hasattr(self, ...)` in `state_store.py` bestaan alleen voor stand-ins in de toetsen**
  (`_restore_overrides` en `zone_override_until`), dezelfde terugval als de weggehaalde
  `getattr(self, ...)`. De stand-ins in `test_handed_back.py` en `test_override_branches.py`
  moeten die leden krijgen; de bewaking op `getattr` kan dan `hasattr` meenemen.
- **De dunne methodes van `coordinator.py` geven `*args, **kwargs` door** (tweeënveertig
  stuks), zodat hun handtekening en typen aan de buitenkant verdwijnen. Geef ze de handtekening
  van het onderdeel dat ze aanroepen.
- **Een nieuwe pakketmodule valt buiten de selectie van de toetsen die hem indirect
  uitvoeren** — `script/select_tests.py` kiest bij een nieuw bestand alleen de toetsen die
  het rechtstreeks importeren of al in de kaart staan. een nieuwe bewonersmodule kwam zo
  pas volledig in de kaart na twee rode CI-runs: zes brede campagne- en
  simulatietoetsen voeren hem uit via de coordinator. Een nieuw pakketbestand zou de
  toetsen moeten kiezen die de coordinator importeren, of ALL, zodat de kaart bij de eerste
  run klopt.
- **Een sensor die de hele dag dood blijft houdt de handstart tot middernacht** — de
  handstart vervalt pas in een ronde waarin elke slaap- en aanwezigheidssensor van elke
  bewoner leest, ook die van iemand die op reis is of wiens telefoon uit staat. Gemeten in
  een controle: met de slaapsensor van de bewoner die op is op `unavailable`
  blijft de handstart staan nadat de andere bewoner wakker werd, terwijl hij zonder dode
  sensor in die ronde vervalt. Hetzelfde geldt voor een feestdagenagenda die de hele dag
  dood blijft: slapen en een leeg huis laten de handstart dan ook niet vervallen (gemeten).
  De volgende dag begrenst het; wat ontbreekt is een grens
  per sensor (alleen de sensoren van wie thuis is, of een maximum aan onleesbare rondes).
- **De mutatieprobe draait na een versiecommit alle mutaties** — alleen `manifest.json` en
  `pyproject.toml` veranderen, maar `pyproject.toml` geldt als gedeeld hulpbestand en laat
  alle veertien mutaties draaien (ruim anderhalf uur). Een padvoorwaarde die een
  wijziging van alleen de versieregel negeert, bespaart die run.
- **De gidsen citeren de handstartknop op twee manieren** — fr, es en ar noemen het
  schermwoord met `{zone}` (*Démarrer {zone} manuellement*), nl, en en de zonder (*Met de
  hand starten*, *Start by hand*, *Von Hand starten*). Eén vorm, met een toets erop.
- **De knop *Met de hand starten* bewaart ook in schaduwmodus een handstart** — de
  herkenning aan het apparaat slaat schaduwmodus over, de knop niet; bij het verlaten van
  schaduwmodus later die dag start de zone dan alsnog. De vooruit-knop en de
  overrideschakelaar kijken evenmin naar schaduwmodus, dus het is een keuze: alle
  invoer negeren of alle invoer bewaken.
- **Een aanwezigheidsentiteit die helemaal uit de toestandsmachine verdwijnt, krijgt geen
  nalooptijd** — de kamerpoort noteert wel een vertrekmoment als de entiteit van een
  bezette kamer verdwijnt (of bij een herstart ontbreekt), maar `world_builder._presence`
  geeft zonder toestand geen moment door, dus de kamer telt meteen als leeg. Een sensor
  die `unavailable` meldt krijgt de nalooptijd wel. Een geregistreerde entiteit staat bij
  het opstarten als `unavailable` in de toestandsmachine, dus in de praktijk komt dit
  zelden voor; het is een verschil tussen wat de poort bewaart en wat de lezer doorgeeft.
- **Een override die tijdens het opstarten aan en weer uit gaat, laat de opgeslagen hand
  terugkomen** — draaiend heft een override de hand bij zijn begin op, ook als hij daarna
  weer uitgaat. Tijdens het opstarten telt alleen een override die er na het herstel nog
  staat; wordt hij binnen die tijd ook weer uitgezet, dan komt de opgeslagen hand terug.
- **De voorwaarde `zone in _occupied_rooms` in `notice_room_empty` heeft geen toets** —
  haal hem weg zonder dat een toets rood wordt. Ofwel is hij overbodig (dan kan hij weg),
  ofwel mist er een toets voor het geval waarin hij iets doet.
- **De veldenkaart van de formulierbewaking valt stil terug op de `Call`-knoop** —
  `conftest.form_field_nodes()` geeft 0 velden terug wanneer de genoemde
  `schemas.<naam>` niet bestaat, in plaats van een harde fout
  ("`schemas.<naam>` bestaat niet"). Vandaag gedekt doordat de veldenkaart een exacte
  gelijkheid is; een harde fout zou dat anker weghalen.
- **`TestEveryScreenCanBeLeft._steps()` plakt elke schemabron van een stapmethode aan
  élk step_id in díe methode** — geen kruisbesmetting zolang elke stapmethode precies
  één formulier toont, wat vandaag zo is maar nergens staat. Een stapmethode met twee
  formulieren zou één bron aan beide step_id's hangen zonder dat iemand het merkt.
- **Een controle op exclusieve groepen die wél klopt** — er stond er een die waarschuwde
  zodra de buitengrenzen van twee groepsleden elkaar overlapten, met het advies ze
  aansluitend te maken. Dat advies maakt de groep juist zinloos: hij bestaat om te kiezen
  tussen apparaten die elkaar kunnen tegenkomen. Die controle is weg. Wat wél te melden
  valt, is een groep die niets kan uitsluiten — twee bronnen in dezelfde kamer bijvoorbeeld,
  die elkaar toch al uitsluiten omdat een zone maar één bron kiest.
- **Een huisbrede stop die ook een handbediend apparaat pakt** — de lijst apparaten die
  stilvallen zodra ergens een opening openstaat, stuurt alleen wat de director toch al
  stuurt. Een handbediende bron en een zone met een override blijven met rust, precies
  zoals bij de gewone raampoort. Voor wie een handbediende airco in die lijst zet is dat
  niet wat hij verwacht; wat ontbreekt is een keuze tussen "alleen wat ik stuur" en "ook
  wat ik met de hand aanzet".
- **Huisbreed vermogensplafond** — een maximum in watt over de hele installatie, in plaats
  van alleen een maximum aantal units per circuit. Een grens in stuks zegt niets over wat
  er werkelijk uit de meter loopt: drie kleine units zijn iets heel anders dan één ketel.
  Vraagt een vermogen per bron en een rangorde bij het afkappen.
- **De onleesbare-entiteitenmelding kan dagelijks knipperen** — `unusable_entities()`
  loopt over álle gevolgde entiteiten, cloud-`climate` en agenda's inbegrepen. Een meting
  in de echte installatie ontbreekt nog; beoordeel tijdens de controleronde of de melder
  knippert en of er een demping of een aparte melding nodig is.
- **Neerslagintensiteit als drempel** — neerslag telt nu als ja/nee: een ingestelde staat
  heft de buitengrens op, hoe licht de neerslag ook is. Wie bij een miezerbui de ramen
  gewoon open wil houden, zou een ondergrens moeten kunnen opgeven (een sensor met mm/h en
  een drempel, of een aparte `weather`-conditie apart uitsluiten), zodat alleen neerslag
  boven die intensiteit de buitengrens opzij zet. De drempel hoort per zone instelbaar te
  zijn: een achterdeur mag bij een lichte bui best open blijven, terwijl een schuin dakraam
  bij de minste neerslag al dicht moet.
- **Temperatuurschema per zone** — een streeftemperatuur die met de klok meebeweegt
  (nacht koeler, ochtend warmer), in plaats van één waarde per zone die alleen door de
  poorten aan- en uitgezet wordt.
- **Suggestie voor circuitgroepering** — voorstellen welke binnenunits een buitenunit delen
  op basis van gedeeld `device` / `via_device` / fabrikant, uitdrukkelijk als voorstel en
  niet als feit, omdat de meeste klimaatintegraties die relatie niet blootgeven.
- **De droogstand als eigen taak, met een eigen drempel** — de engine leest `dry` wel (het
  telt als koelen), maar kiest hem nooit: er wordt alleen `heat`, `cool`, `fan_only` en
  `off` aangestuurd. Wie bij vochtig weer bewust ontvochtigt, moet dat nu naast de
  integratie doen. Een zone zou een derde taak moeten kunnen hebben, met een eigen aan-/
  uitpunt op een luchtvochtigheidssensor in plaats van op een thermometer — en met de hand
  aan te zetten voor wie geen sensor heeft. Op een niet-simultaan circuit hoort `dry` bij
  de koelfamilie, dus die kant is al geregeld.
- **Meerdere binnensensoren per zone** — nu wijst een zone één entiteit aan. Meerdere
  sensoren met een keuze uit gemiddelde, laagste, hoogste of "de eerste die een waarde
  geeft" scheelt een handgemaakte template- of min/max-helper voor wie meerdere meters in
  één ruimte heeft.
- **Openingen met herstel per zone** — nu schort een opening een zone op; een expliciete
  momentopname-en-herstel-route zou ook handmatig ingestelde standen kunnen teruggeven.
- **Conflictdetector** — signaleren dat units zich gedragen alsof ze een buitenunit delen
  (spontane taakwissels, terugvallende standen) en de gebruiker vragen of de
  circuitgroepering klopt.
- **Automatisch voorverwarmen en voorkoelen** — een zone alvast op temperatuur brengen
  tegen de tijd dat het rooster opengaat, in plaats van pas op dat moment te beginnen.
  Vooruit verwarmen en koelen met de hand bestaat al (knop per zone, de `precondition`-
  actie en een timer die vanzelf afloopt); dit idee gaat alleen over het automatische deel.
- **Energieprijs als bronvoorkeur** — een dynamisch tarief of een
  zonnepanelenoverschot laten meewegen in `Source.priority`, zodat de goedkoopste bron
  wint zolang die het aankan. Stap 1, het kostenrekenwerk (`engine/cost.py`), is er, en stap 2: de
  energie-instellingen en de sensor *Goedkoopste warmtebron* (alleen kijken). Het schakelen op
  kosten is er nog niet.
- **Live prioriteiten gelijk trekken op één circuit** — twee zones met dezelfde prioriteit
  op hetzelfde circuit laten nu de bron- en zonevolgorde beslissen. Een zone die lang
  wacht zou tijdelijk één stap voorrang kunnen krijgen, met terugval naar de ingestelde
  prioriteit. Het ontwerp staat in `ARCHITECTURE.md` onder "Nog te bouwen".
- **Weersvoorspelling in het buitentemperatuurvenster** — schakelen op de verwachte
  temperatuur over enkele uren in plaats van alleen de huidige.
- **Meer conflictbeleiden** — bijvoorbeeld beurtelings (round-robin) of een vast schema
  per dagdeel. Vier beleiden bestaan al (`priority`, `first_come`, `demand`,
  `season_lock`); het uitbreidpunt is er.
- **`number`-entiteiten voor de drempels per zone** — streeftemperatuur, aanpunt en
  hysterese zijn nu alleen via de config flow te wijzigen; eigen `number`-entiteiten maken
  ze bedienbaar zonder de hele installatie te herladen. Staat ook in `ARCHITECTURE.md`
  onder "Nog te bouwen".
- **De regelbreedte 100 staat op twee plekken** — `pyproject.toml` en
  `script/_gen_guides_test.py` (`LINE_LENGTH`). Verandert de eerste, dan schrijft de
  generator een uitzonderingenlijst die `ruff format --check` opnieuw wil opmaken; hij
  hoort die breedte uit `pyproject.toml` te lezen.
- **De grote modules per onderwerp opsplitsen** — `coordinator.py`, `engine/models.py`,
  `engine/decide.py`, `config_flow.py` en `schemas.py` zijn elk ruim boven de 500 regels
  en dragen meerdere onderwerpen. Nieuwe code komt al bij zijn onderwerp; de bestaande
  delen kunnen dezelfde weg gaan (de koppelingslaag in mixins per onderwerp, de engine in
  modules per onderwerp), zonder gedrag te veranderen.
- **De toetsen per onderwerp in plaats van per ronde** — `test_reachable_branches.py`,
  `test_reachable_branches_deep.py` en `test_wens2_live.py` zijn naar een ronde of wens
  genoemd, en zes toetsbestanden importeren hulpjes uit een ander toetsbestand. Die toetsen
  horen bij het bestand van hun onderwerp, en de gedeelde hulpjes in `tests/conftest.py` of
  een hulpbestand.
- **De proefopstellingen in de tests dragen de interface met de hand** — de stand-ins
  kopiëren de leesmethodes van de coördinator en zetten de bijbehorende attributen stuk
  voor stuk neer. Een toets eist dat elke stand-in elk protocollid draagt dat zijn
  geleende methodes aanraken, maar het neerzetten blijft handwerk: elk nieuw lid kost een
  aanpassing in elke stand-in die het raakt. Ze zouden hun attributen kunnen afleiden uit
  `CoordinatorSurface`.
- **De opruimbeurt van verweesde entiteiten mist dezelfde volledigheidstoets** —
  `_async_remove_stale_entities` verwijdert een entiteit als zijn `config_entry_id` de onze is
  én zijn `unique_id` met onze prefix begint, maar kijkt niet naar het platform of het domein;
  het override-doel doet dat wél. Bereikbaar is het nauwelijks (een andere
  integratie zou een entiteit aan onze entry moeten hangen), dus dit is een harding met een
  test, geen reparatie.
- **De maat in `test_the_measure.py` telt fysieke regels** — een commentaarregel, een
  decorator of een vervolgregel in een genoteerd bestand verschuift daardoor het getal en
  vraagt een nieuwe meting. De poort telt alleen nog statementregels (`statement_lines`);
  de maat zou dat kunnen volgen, zodat commentaar, decorators en vervolgregels buiten de
  maat vallen.
- **De markdown-bewaking kent `- ` en `* ` maar niet `+ `** — een opsomming met
  plustekens is geldige Markdown en wordt toch overgeslagen, alsof de regel geen lijstitem
  is.
- **Een lijst direct onder een kop zonder lege regel is geldige Markdown en toch rood** —
  de bewaking eist een lege regel tussen kop en lijst; dat is een smaakregel, geen
  markdownregel.
- **Alle zes gidsen zeggen *vóór deze versie* of *avant l'installation de cette
  version*** — die formulering veroudert met elke uitgave; een gewone voorwaarde (*vóór je
  begint*) blijft waar.
- **De geslachtsbewaking dekt geen bijvoeglijk naamwoord** — *une zone actif* glipt
  erdoor; de bewaking kijkt naar lidwoorden en voornaamwoorden, niet naar de vorm van het
  bijvoeglijk naamwoord.
- **De richtingsbewaking kent alleen de werkwoorden uit `DIRECTION_WORDS`** — een synoniem
  dat ook een richting uitspreekt, zoals Nederlands *stookt*, blijft groen; een
  synoniemlijst per taal zou dat dichten.
- **De actiewoord-bewaking draagt een lijst goedgekeurde tokens** — in het Spaans eindigen
  *va*, *apaga*, *deja* en *reposo* toevallig op een geslachtsuitgang en in het Arabisch
  begint *تشغيل* toevallig met een persoonsvoorvoegsel, zonder dat die woorden buigen; een
  fijnere regel zou die lijst overbodig maken.
- **De geslachtsbewaking ziet het schermwoord niet binnen een entiteit-id** — de `_` in
  `switch.*_puenteo_<opening>` is voor een reguliere expressie een letter, dus daar houdt de
  woordgrens op; de **tabelvorm** (`| ... | activado = ... |`) zet de beschrijvende vorm vóór
  het scheidingsteken, terwijl de bewaking achter het teken kijkt. Juist op die twee plekken
  kan het geslacht fout gaan; de bewaking heeft ze met naam in haar docstring staan.
- **Het decimaalteken van `units.display_temperature` is een punt** — de melding leest
  *23.0 °C*, terwijl de nl-, de-, fr- en es-gidsen zelf *0,5* schrijven. Eén tekenkeuze
  voor beide zou de gidsen en de melding gelijk maken.
- **`options.step.zone.data_description.gate` toont de ruwe waarden `'household'` en
  `'presence'`** — de gebruiker leest de sleutel in plaats van een zin in zijn taal.
- **De laatste terugval van `reason_sentence` is de identifier zelf** — valt elke
  vertaling weg, dan leest de gebruiker `circuit_conflict_lost` in plaats van een zin.
- **Een bewaking op dode code** — er staat geen enkele toets op namen die niemand meer
  gebruikt: een ongebruikte functie in het pakket of een ongebruikte testhulp maakt
  niets rood. `vulture` op 60% over pakket, `tests/` en `script/` meldt namen die alle
  te verklaren zijn: de Home Assistant-interface in het pakket, autouse-fixtures,
  dubbelgangers van Home Assistant-objecten, en de helpers `_fill_*` en `_check_*` in
  `tests/test_campaign_editing.py`. Die helpers zijn één mechanisme en leven: de
  aanroep per scherm loopt via een samengestelde naam (`getattr` op de schermnaam), en
  die vorm ziet `vulture` niet. Een dode-codebewaking op een ratel heeft daar dus een
  uitzonderingenlijst bij nodig - of een eigen AST-inventaris die de samengestelde
  `getattr`-vorm herkent - zodat het aantal onverklaarde treffers op nul blijft zonder
  de terechte meldingen weg te drukken.
- **De filtertoets van de blauwdruk rendert met `StrictUndefined`** — elk nieuw
  filterveld in de blauwdruk maakt die toets rood totdat de toets het veld zelf ook
  meegeeft; een toets die de velden uit de blauwdruk leest, groeit vanzelf mee.
- **De uitleg bij `outdoor_hysteresis` staat in de verleden tijd** — in alle zes talen
  (*buiten was elke grens hard*). De uitleg hoort te zeggen wat het veld doet, niet hoe
  het vroeger was.
- **De Arabische reden `outside_schedule` zegt *الآن*** — *لا جدول لأي ساكن مفتوح الآن*
  noemt een moment ("nu") dat de andere talen niet noemen en dat de zin niet nodig heeft.
- **De terugval van het standaardbericht van de blauwdruk toont ruwe identifiers** —
  valt een vertaling weg, dan leest de gebruiker een waarde als `neutral` in plaats van
  een woord in zijn taal.
- **Het Arabische actiewoord *بقاء من دون تشغيل* kan korter** — *من دون تشغيل* zegt
  hetzelfde; *بقاء* ("blijven") voegt niets toe.
- **Het Engelse actiewoord *is going off* is dubbelzinnig** — het leest ook als een
  wekker die afgaat; een eenduidig werkwoord zegt dat het apparaat uitgaat.
- **De geslachtsbewaking op de beschrijvende vorm kijkt alleen direct achter `:` of
  `=`** — een beschrijvende vorm verderop in de regel, zoals es *mientras siga activa*,
  glipt erdoor.
- **Het Arabisch gebruikt twee keer één woord voor drie begrippen** — *نافذة* staat voor
  het raam, het tijdvenster en het buitentemperatuurvenster, en *النطاق* voor het
  temperatuurbereik, de zonegroep van `covers_zones` en de dode band. Eén woord per
  begrip zou gids en scherm eenduidig maken.
- **De Arabische reden `circuit_at_capacity` zegt *الوحدة الخارجية ممتلئة*** — *ممتلئة*
  leest als "vol", alsof er iets in de buitenunit zit; bedoeld is dat hij al zoveel
  binnenunits bedient als hij kan.
- **De gidsen noemen de verwerp-knop cursief in plaats van tussen aanhalingstekens** — de
  vertaalbestanden citeren het label tussen aanhalingstekens, de gidsen zetten het
  cursief, en alleen `nl.md` zet het op één plek tussen aanhalingstekens. Eén vorm in
  gids en scherm, met een toets erop, zou dat gelijktrekken.
- **Geen toets legt een veldnaam in het proza naast het label** — de tabeltoets meet
  alleen de vette tabelrijen. Een cursieve of vette veldnaam in de lopende tekst kan
  daardoor van het scherm afwijken zonder dat iets rood wordt. Een toets die zo'n naam
  naast de labels van die taal legt, zou dat vangen.
- **De grens van 80 tekens voor de opening-id-alinea's van Stap 11 wordt niet
  bewaakt** — de regellengtetoets kent alleen de grens van 120 tekens, dus een regel
  van 81 tekens in die twee alinea's valt alleen bij het proeflezen op.
- **Het Frans en het Spaans noemen een taak in de gids ook *fonction* / *función*** —
  het scherm zegt *tâche* / *tarea* (*Pause lors du changement de tâche*), maar de uitleg
  in de tabel en in de lopende tekst zegt vaak *fonction* / *función*, een woord dat de
  gids ook voor de rol van een bron gebruikt.
- **Het Frans noemt het vakantierooster in de gids *programme vacances*** — de
  schakelaar heet *Planning de vacances*, en de rest van de gids en het scherm zeggen
  *planning*.
- **Het Duitse lidwoord bij de nieuwe woorden wordt niet bewaakt** — *der Übersteuerung*
  als onderwerp, *die Außengerät* of *das Totzone* maakt niets rood; alleen de
  proeflezing ziet het.
- **De zin over wanneer het wachten begint wordt niet bewaakt** — de beschrijving van
  *Wacht op deze slaper tot* en de gidsalinea zeggen dat het wachten pas begint als
  iedereen die thuis is naar bed is geweest. Schrapt iemand die zin in één taal, dan blijft
  alles groen; alleen de proeflezing ziet het.


## Would have

- **Leren van looptijden** — de opwarm- en afkoelsnelheid per zone meten en de dode band
  of het voorverwarmen daarop aanpassen.
- **Balancering over circuits** — bij twee gelijkwaardige bronnen op verschillende
  circuits de belasting verdelen in plaats van altijd dezelfde te kiezen.

---

# Roadmap

This file is this integration's ideas box: future changes, improvements and additions not
yet built, ordered as *should have* (probably valuable), *could have* (nice, situational)
and *would have* (later, a separate effort). Not everything here has been discussed or
approved — it is a place to pick from, prioritise or reject.

The history of what has already been built and changed is **not** here but in the
[release notes](https://github.com/Sarnog/ha-climate-director/releases) of each version.

The worked-out design proposals for everything below live in
[`ARCHITECTURE.md`](ARCHITECTURE.md) under "Still to build".

## Should have

- **An unreadable presence of whoever is up still switches a hand-started zone off (N14)** —
  the hand start stays, but `EVERYONE_ASLEEP` and `NOBODY_HOME` are not brakes it passes: if
  the presence entity of the only resident who is up drops out, the house reads as asleep or
  empty and the air conditioner goes off until the entity returns (measured: `cmds=[None,
  'off', 'heat']`, three rounds of `everyone_asleep`). The release notes of the hand-start update say the zone
  "simply keeps regulating". A choice for the user: (a) a hand start also passes these two
  reasons while the cause is an unreadable presence, or (b) an unreadable presence keeps the
  last known reading for a short time, for every zone (see also N15).
- **An unreadable sleep sensor lets every waiting zone start (N15)** — without a hand start a
  dropped sleep sensor reads as *awake*: the wait disappears, the waiting zones start and on
  its return the director switches them off again (measured in a review, shared
  boiler: all three zones `regulating` during the outage, then two back to
  `waiting_for_sleeper`). Same design as N14 (b): a short hold on the last readable state.
- **Notices about dead settings name the setting in English (N16)** — the notices about a
  sleep setting without a sleep sensor, a window without length and a stuck time below the
  rest fill `{settings}`, `{window}` and `{label}` with English words from the engine
  ("sleep window, wait for this sleeper until", "quiet window", "minimum cycle time"), in
  Dutch, German, French, Spanish and Arabic as well. Measured: the Dutch notice ends on
  "...kunnen nooit werken: sleep window, wait for this sleeper until." The notice should
  name the screen word of the user's language.
- **The guard on the brake inputs cannot know whether an external field feeds the brakes**
  — `test_every_world_field_is_classified` forces a deliberate classification, but a new
  field in `EXTERNAL_WORLD_FIELDS` that feeds the brakes after all stays green. A
  perturbation test would measure it: change every external field outside the brake inputs
  and demand that the brakes give the same answer.
- **A virtual `climate` per zone** — one control entity per room, so the target temperature
  and mode can be set straight from an ordinary thermostat card. The director then picks the
  source to match.
- **Per-zone gate settings for wake, schedule, quiet and sleep rules** — those currently
  live in `GateSettings` for the whole installation. The household-vs-presence choice, the
  presence sensor and the grace period are already per zone; a bedroom also wants different
  sleep and quiet windows from a living room.
- **The structural agreements behind the source guards stand in an ignored file** — the
  docstrings of the text guards point for the agreement behind the test at `AGENTS.md`, and
  that file is in `.gitignore`. Anyone cloning the repo therefore cannot read the agreement,
  and a guard that looked at it itself would fall over in CI. Those agreements belong in
  `ARCHITECTURE.md`, which does travel with the repo.
- **Align the generator with the override handover** — under an override a `Generator` may
  still be switched on by another zone; only the switching off is withheld. An appliance
  that is a source under a handed-over zone gets no command at all any more, not even an on.
  One rule for both would take that difference away.
- **Holiday calendar: read every overlapping appointment** — Home Assistant shows only one
  event per calendar entity, and a longer appointment that started earlier can mask a
  holiday item; the holiday mode then stays off unnoticed. `calendar.get_events` over the
  current moment would see all appointments.
- **A timeout on the service calls** — `apply` waits with `blocking=True` without a timeout
  while the decision lock is held; one hanging cloud call holds up every following round. A
  bounded wait lets the director carry on with the rest.
- **Warn when the target temperature sits on the switch-off point** — the duty only ends once
  the room sensor reaches the switch-off point; if the appliance regulates on its own sensor
  just below it, the duty (and the circuit) keeps running endlessly. The screen could say
  that a target equal to the switch-off point leaves no margin.

- **A refused area winner gives the loser no second chance** — `area_clash()` leaves one
  side per area (`covers_zones`) and takes the losing request out of the wishes before the
  circuits judge. If the circuit then refuses the winner, it does not run and the losing zone
  is left unserved for that round. The outcome is on the safe side (briefly cold, never two
  systems at once). (a), leave it, is chosen; (b), putting the losing request back as soon as
  the winner is refused, stays an idea for when a measurement shows the room stays cold too
  long, at the risk of the two appliances alternating (design in `ARCHITECTURE.md` under
  "Still to build").

## Could have

- **The impact map depends on the selection of the run** — module-level code runs once, for
  the test file that imports the module first. A smaller selection in CI than locally (the
  commit against its predecessor, against everything not pushed yet) moves that code to
  another test file, and the map check then fails on a row that was right locally
  (`test_random_installations.py` got `schemas.py` that way). The map should not count the
  module-level code of the importing file as a requirement, or the local run should mimic
  the CI selection (`CD_BASE` on the predecessor).
- **A new import in an existing module changes what other tests execute, and the selection
  does not see it** — a line that imports an existing module (here `validation_sources.py`
  starting to use `takeover.py`) makes every test that calls `validate()` execute that file as
  well, but the selection only picks the tests the map already names for the changed file. The
  four missing tests only came to light in the full CI run (red on the map alone). The
  selection should include the tests that import the changed file indirectly, or the map
  should record per import who calls whom.
- **The `flow_*`, `form_*` and `schema_fields` functions read well over a hundred private
  cursors and lists of the configuration flow** (`flow._index`, `flow._installation`,
  `flow._list`...), the same shape as the private attributes of the coordinator that the parts no
  longer read. `FlowSurface` names them with a leading underscore and the guard on
  `coordinator._name` does not see them. Give the flow public names or a state class of its own
  per screen, and extend the guard to `flow._name` outside `config_flow.py`.
- **Two `hasattr(self, ...)` in `state_store.py` exist only for stand-ins in the tests**
  (`_restore_overrides` and `zone_override_until`), the same fallback as the removed
  `getattr(self, ...)`. The stand-ins in `test_handed_back.py` and `test_override_branches.py`
  must get those members; the guard on `getattr` can then take `hasattr` along.
- **The thin methods of `coordinator.py` pass `*args, **kwargs` on** (forty-two of them), so
  their signature and types disappear on the outside. Give them the signature of the part they
  call.
- **A new package module falls outside the selection of the tests that execute it
  indirectly** — `script/select_tests.py` picks, for a new file, only the tests that import
  it directly or already stand in the map. a new resident module only reached the map
  completely after two red CI runs: six broad campaign and simulation tests
  execute it through the coordinator. A new package file should pick the tests that import
  the coordinator, or ALL, so that the map is right on the first run.
- **A sensor that stays dead all day keeps the hand start until midnight** — the hand
  start lapses only in a round in which every sleep and presence sensor of every resident
  reads, including that of somebody who is travelling or whose phone is off. Measured in
  a review: with the sleep sensor of the resident who is up on `unavailable`, the
  hand start stays after the other resident woke up, whereas without a dead sensor it lapses
  in that round. The same holds for a holiday calendar that stays dead all day: sleeping
  and an empty house then do not let the hand start lapse either (measured). The next day
  bounds it; what is missing is a bound per sensor (only the
  sensors of whoever is home, or a maximum of unreadable rounds).
- **The mutation probe runs every mutation after a version commit** — only `manifest.json`
  and `pyproject.toml` change, but `pyproject.toml` counts as a shared helper file and
  makes all fourteen mutations run (well over an hour and a half). A path condition that
  ignores a change to the version line alone would save that run.
- **The guides cite the hand-start button in two ways** — fr, es and ar give the screen
  word with `{zone}` (*Démarrer {zone} manuellement*), nl, en and de without (*Met de hand
  starten*, *Start by hand*, *Von Hand starten*). One form, with a test on it.
- **The *Start by hand* button also keeps a hand start in shadow mode** — recognition at
  the appliance skips shadow mode, the button does not; when shadow mode is left later that
  day the zone starts after all. The pre-conditioning button and the override switch do not
  look at shadow mode either, so it is a choice: ignore all input or guard all input.
- **A presence entity that disappears from the state machine altogether gets no grace
  period** — the room gate does note a departure moment when the entity of an occupied
  room disappears (or is missing at a restart), but `world_builder._presence` passes no
  moment on without a state, so the room counts as empty at once. A sensor that reports
  `unavailable` does get the grace period. A registered entity stands in the state
  machine as `unavailable` at startup, so in practice this is rare; it is a difference
  between what the gate keeps and what the reader passes on.
- **An override that goes on and off again during the startup lets the stored hand come
  back** — while running, an override lifts the hand at its beginning, also when it goes
  off again afterwards. During the startup only an override still standing after the
  restore counts; when it is switched off again within that time, the stored hand comes
  back.
- **The condition `zone in _occupied_rooms` in `notice_room_empty` has no test** —
  remove it and no test turns red. Either it is redundant (then it can go), or a test is
  missing for the case in which it does something.
- **The form guard's field map silently falls back to the `Call` node** —
  `conftest.form_field_nodes()` returns 0 fields when the named `schemas.<name>`
  does not exist, instead of a hard error ("`schemas.<name>` does not exist").
  Covered today because the field map is an exact equality; a hard error would
  remove that anchor.
- **`TestEveryScreenCanBeLeft._steps()` attaches every schema source of a step method
  to every step_id in that method** — no cross-contamination as long as each step
  method shows exactly one form, which is true today but stated nowhere. A step method
  with two forms would attach one source to both step_ids without anyone noticing.
- **A check on exclusive groups that actually holds** — there used to be one warning as soon
  as two members' outdoor bounds overlapped, advising you to make them adjacent. That advice
  is what makes the group pointless: it exists to choose between appliances that can meet.
  That check has gone. What would be worth reporting is a group that cannot rule anything
  out — two sources in the same room, say, which already rule each other out because a zone
  only ever picks one source.
- **A house-wide stop that catches a hand-operated appliance too** — the list of
  appliances that stop the moment an opening stands open anywhere steers only what the
  director steers already. A hand-operated source and a zone under override are left
  alone, exactly as with the ordinary window gate. For anyone putting a hand-operated air
  conditioner on that list this is not what they expect; what is missing is a choice
  between "only what I steer" and "what I switch on by hand as well".
- **A house-wide power ceiling** — a maximum in watts across the whole installation, rather
  than only a maximum number of units per circuit. A limit in units says nothing about what
  actually leaves the meter: three small units are a very different thing from one boiler.
  Needs a wattage per source and an order in which to shed.
- **The unreadable-entities notice may blink daily** — `unusable_entities()` runs
  over *all* tracked entities, cloud `climate` entities and calendars included. A
  measurement on the real installation is still missing; judge during the control
  round whether the reporter blinks and whether it needs damping or a notice of its
  own.
- **Precipitation intensity as a threshold** — precipitation currently counts as yes/no: a
  configured state lifts the outdoor bound, however light the precipitation. Anyone who
  wants to keep the windows open during a drizzle should be able to set a floor (a sensor
  in mm/h with a threshold, or exclude a separate `weather` condition such as `light
  drizzle`), so only precipitation above that intensity sets the outdoor bound aside. The
  threshold should be settable per zone: a back door may well stay open during a light
  shower, while a slanted skylight must close at the first drop.
- **A temperature schedule per zone** — a target that moves with the clock (cooler at
  night, warmer in the morning), instead of one value per zone that the gates merely switch
  on and off.
- **Suggested circuit grouping** — propose which indoor units share an outdoor unit based on
  shared `device` / `via_device` / manufacturer, explicitly as a proposal rather than a
  fact, since most climate integrations do not expose that relationship.
- **Drying as a duty of its own, with its own threshold** — the engine does read `dry` (it
  counts as cooling) but never picks it: only `heat`, `cool`, `fan_only` and `off` are
  commanded. Anyone deliberately dehumidifying in muggy weather has to do that beside the
  integration. A zone should be able to carry a third duty, with its own switch-on point on
  a humidity sensor rather than on a thermometer — and switchable by hand for those without
  such a sensor. On a non-simultaneous circuit `dry` already belongs to the cooling family,
  so that side is settled.
- **Several indoor sensors per zone** — a zone currently names one entity. Several sensors
  with a choice of average, lowest, highest or "the first one reporting a value" saves a
  hand-built template or min/max helper for anyone with more than one meter in a room.
- **Openings with per-zone restore** — an opening currently suspends a zone; an explicit
  snapshot-and-restore path could also give manually set modes back.
- **Conflict detector** — spot units behaving as though they share an outdoor unit
  (spontaneous duty swaps, modes falling back) and ask the user whether the circuit
  grouping is right.
- **Automatic pre-heating and pre-cooling** — bring a zone up to temperature by the time
  the schedule opens, rather than starting only at that moment. Pre-heating and pre-cooling
  by hand already exist (a button per zone, the `precondition` action and a timer that runs
  out by itself); this idea is only about the automatic part.
- **Energy price as source preference** — let a dynamic tariff or a solar surplus weigh
  into `Source.priority`, so the cheapest source wins as long as it can cope. Step 1, the cost
  arithmetic (`engine/cost.py`), is in, and step 2: the
  energy settings and the *Cheapest heat source* sensor (watching only). Switching on cost is
  not there yet.
- **Levelling live priorities on one circuit** — two zones with the same priority on the
  same circuit now let source and zone order decide. A zone that waits long could get one
  temporary step of precedence, falling back to the configured priority. The design stands
  in `ARCHITECTURE.md` under "Still to build".
- **Weather forecast in the outdoor window** — switch on the temperature expected in a few
  hours rather than only the current one.
- **More conflict policies** — round-robin, for instance, or a fixed schedule per part of
  the day. Four policies already exist (`priority`, `first_come`, `demand`, `season_lock`);
  the extension point is there.
- **Per-zone `number` entities for the thresholds** — target temperature, switch-on point
  and hysteresis can currently only be changed through the config flow; `number` entities
  of their own would make them controllable without reloading the whole installation. Also
  listed in `ARCHITECTURE.md` under "Still to build".
- **The line width 100 stands in two places** — `pyproject.toml` and
  `script/_gen_guides_test.py` (`LINE_LENGTH`). Change the first and the generator writes
  an exception list that `ruff format --check` wants to redo; it should read that width
  from `pyproject.toml`.
- **Splitting the large modules per subject** — `coordinator.py`, `engine/models.py`,
  `engine/decide.py`, `config_flow.py` and `schemas.py` are each well over 500 lines and
  carry several subjects. New code already goes to its subject; the existing parts can go
  the same way (the binding layer in mixins per subject, the engine in modules per
  subject), without changing behaviour.
- **The tests per subject instead of per round** — `test_reachable_branches.py`,
  `test_reachable_branches_deep.py` and `test_wens2_live.py` are named after a round or a
  wish, and six test files import helpers from another test file. Those tests belong in
  the file of their subject, and the shared helpers in `tests/conftest.py` or a helper
  file.
- **The test stand-ins carry the interface by hand** — the stand-ins copy the
  coordinator's reading methods and set the matching attributes one by one. A test demands
  that every stand-in carries each protocol member its borrowed methods touch, but setting
  them stays handwork: every new member costs an edit in each stand-in it reaches. They
  could derive their attributes from `CoordinatorSurface`.
- **The sweep of orphaned entities misses the same completeness check** —
  `_async_remove_stale_entities` removes an entity when its `config_entry_id` is ours and its
  `unique_id` starts with our prefix, but it does not look at the platform or the domain; the
  override target does. It is hardly reachable (another integration
  would have to hang an entity off our entry), so this is a hardening with a test rather than
  a repair.
- **The measure in `test_the_measure.py` counts physical lines** — a comment line, a
  decorator or a continuation line in a noted file therefore shifts the number and asks for
  a fresh measurement. The gate counts statement lines only (`statement_lines`); the measure
  could follow, so that comments, decorators and continuation lines fall outside the measure.
- **The markdown guard knows `- ` and `* ` but not `+ `** — a list with plus signs is
  valid Markdown and is skipped anyway, as if the line were not a list item.
- **A list straight under a heading without a blank line is valid Markdown and yet red** —
  the guard demands a blank line between heading and list; that is a taste rule, not a
  markdown rule.
- **All six guides say *before this version* or *avant l'installation de cette version*** —
  that wording ages with every release; an ordinary condition (*before you start*) stays
  true.
- **The gender guard does not cover an adjective** — *une zone actif* slips through; the
  guard looks at articles and pronouns, not at the adjective's form.
- **The direction guard only knows the verbs in `DIRECTION_WORDS`** — a synonym that also
  names a direction, such as Dutch *stookt*, stays green; a synonym list per language would
  close that.
- **The action-word guard carries a list of approved tokens** — in Spanish *va*, *apaga*,
  *deja* and *reposo* happen to end in a gender ending and in Arabic *تشغيل* happens to begin
  with a person prefix without those words bending; a finer rule would make that list
  superfluous.
- **The gender guard does not see the screen word inside an entity id** — the `_` in
  `switch.*_puenteo_<opening>` counts as a letter to a regular expression, so the word
  boundary stops there; and the **table shape** (`| ... | activado = ... |`) puts the
  descriptive form before the separator, while the guard looks behind the sign. Those two are
  exactly where the gender can go wrong; the guard names them in its docstring.
- **The decimal mark of `units.display_temperature` is a point** — the message reads
  *23.0 °C*, while the nl, de, fr and es guides themselves write *0,5*. One choice of
  character for both would make the guides and the message agree.
- **`options.step.zone.data_description.gate` shows the raw values `'household'` and
  `'presence'`** — the user reads the key instead of a sentence in their language.
- **The last fallback of `reason_sentence` is the identifier itself** — if every
  translation falls away, the user reads `circuit_conflict_lost` instead of a sentence.
- **A guard on dead code** — no test looks at names nobody uses any more: an unused
  function in the package or an unused test helper turns nothing red. `vulture` at 60%
  over the package, `tests/` and `script/` reports names that are all explainable: the
  Home Assistant interface in the package, autouse fixtures, stand-ins for Home
  Assistant objects, and the helpers `_fill_*` and `_check_*` in
  `tests/test_campaign_editing.py`. Those helpers are one mechanism and alive: the call
  runs per screen through an assembled name (`getattr` on the screen name), and
  `vulture` does not see that shape. A dead-code guard on a ratchet therefore needs an
  exception list with it - or an AST inventory of its own that recognises the assembled
  `getattr` shape - so the number of unexplained hits stays at zero without silencing
  the fair reports.
- **The blueprint's filter test renders with `StrictUndefined`** — every new filter
  field in the blueprint turns that test red until the test passes the field itself; a
  test reading the fields from the blueprint grows along by itself.
- **The explanation of `outdoor_hysteresis` is in the past tense** — in all six
  languages (*outdoors every bound was hard*). The explanation should say what the
  field does, not how things used to be.
- **The Arabic reason `outside_schedule` says *الآن*** — *لا جدول لأي ساكن مفتوح الآن*
  names a moment ("now") that the other languages do not name and the sentence does not
  need.
- **The fallback of the blueprint's default message shows raw identifiers** — if a
  translation falls away, the user reads a value such as `neutral` instead of a word in
  their language.
- **The Arabic action word *بقاء من دون تشغيل* can be shorter** — *من دون تشغيل* says
  the same; *بقاء* ("staying") adds nothing.
- **The English action word *is going off* is ambiguous** — it also reads as an alarm
  going off; an unambiguous verb says the appliance switches off.
- **The gender guard on the descriptive form only looks right behind `:` or `=`** — a
  descriptive form further along the line, such as es *mientras siga activa*, slips
  through.
- **Arabic uses one word for three concepts, twice** — *نافذة* stands for the window,
  the time window and the outdoor temperature window, and *النطاق* for the temperature
  range, the zone group of `covers_zones` and the dead band. One word per concept would
  make guide and screen unambiguous.
- **The Arabic reason `circuit_at_capacity` says *الوحدة الخارجية ممتلئة*** — *ممتلئة*
  reads as "full", as if something were inside the outdoor unit; what is meant is that
  it already serves as many indoor units as it can.
- **The guides name the discard button in italics rather than between quotation
  marks** — the translation files quote the label between quotation marks, the guides
  set it in italics, and only `nl.md` quotes it in one place. One form in guide and
  screen, with a test on it, would even that out.
- **No test lays a field name in the prose next to the label** — the table test only
  measures the bold table rows. An italic or bold field name in running text can
  therefore differ from the screen without anything turning red. A test laying such a
  name next to that language's labels would catch it.
- **The 80-character limit for the opening-id paragraphs of Step 11 is not
  guarded** — the line-length test only knows the 120-character limit, so an
  81-character line in those two paragraphs only shows up when proofreading.
- **French and Spanish also call a duty *fonction* / *función* in the guide** — the
  screen says *tâche* / *tarea* (*Pause lors du changement de tâche*), but the
  explanation in the table and in running text often says *fonction* / *función*, a
  word the guide also uses for a source's role.
- **French calls the holiday schedule *programme vacances* in the guide** — the switch
  is called *Planning de vacances*, and the rest of the guide and the screen say
  *planning*.
- **The German article with the new words is not guarded** — *der Übersteuerung* as
  a subject, *die Außengerät* or *das Totzone* turns nothing red; only proofreading
  sees it.
- **The sentence about when the waiting begins is not guarded** — the description of
  *Wait for this sleeper until* and the guide paragraph say the waiting only begins once
  everybody at home has been to bed. Whoever drops that sentence in one language keeps
  everything green; only proofreading sees it.


## Would have

- **Learning from run times** — measure each zone's heating and cooling rate and adapt the
  dead band or the pre-heating to it.
- **Balancing across circuits** — with two equivalent sources on different circuits, share
  the load instead of always picking the same one.
