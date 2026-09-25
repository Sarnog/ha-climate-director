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

## Could have

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
  wint zolang die het aankan.
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
- **Het `CoordinatorSurface`-protocol wordt nergens gecontroleerd** — de vier mixins
  erven er onder `TYPE_CHECKING` van, dus mypy gelooft dat hun `self` elk lid heeft,
  maar niets controleert of de coördinator ze ook werkelijk zet. Eén test die na de opzet
  elk protocollid op de coördinator opvraagt zou dat dichten; de `entry`-property van
  ronde 30 laat zien dat zo'n lid er zomaar bij kan komen.
- **De proefopstellingen in de tests dragen de interface met de hand** — de stand-ins
  kopiëren de leesmethodes van de coördinator en zetten de bijbehorende attributen stuk
  voor stuk neer. Elk nieuw lid (`entry`, `season_override`) kostte in ronde 30 een ronde
  mislukte tests. Ze zouden hun attributen kunnen afleiden uit `CoordinatorSurface`, of
  een test zou kunnen eisen dat een stand-in elk lid draagt dat de gekopieerde methodes
  aanraken.
- **De 20 open takken van de dekkingsmeting** — `branch = true` meldt twintig keer één
  kant van een lus of een kortsluiting die nooit langskomt. Ze zijn nu met een pragma noch
  een test gedicht; per stuk is de vraag of de tweede kant te bereiken is (dan een test)
  of niet (dan een herschrijving die de tak laat verdwijnen).
- **De opruimbeurt van verweesde entiteiten mist dezelfde volledigheidstoets** —
  `_async_remove_stale_entities` verwijdert een entiteit als zijn `config_entry_id` de onze is
  én zijn `unique_id` met onze prefix begint, maar kijkt niet naar het platform of het domein;
  het override-doel doet dat sinds ronde 34 wél. Bereikbaar is het nauwelijks (een andere
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

- **Een bewaking op dode code** — er staat nu geen enkele toets op namen die
  niemand meer gebruikt. `vulture` op 60% over pakket, `tests/` en `script/` meldt
  een stuk of wat namen, en alle zijn te verklaren: de Home Assistant-interface in
  het pakket, autouse-fixtures en dubbelgangers van Home Assistant-objecten. Eén
  ervan is een valse melding die je niet zomaar wegstreept: in
  `tests/test_campaign_editing.py` loopt de aanroep per scherm via een
  samengestelde naam (`getattr` op de schermnaam), en zulke helpers leven. Een
  dode-codebewaking op een ratel heeft daar dus een uitzonderingenlijst bij nodig -
  of een eigen AST-inventaris die de samengestelde `getattr`-vorm herkent - zodat
  het aantal onverklaarde treffers op nul blijft zonder de terechte meldingen weg
  te drukken.

- **A guard on dead code** — no test looks at names nobody uses any more.
  `vulture` at 60% over the package, `tests/` and `script/` reports a handful of
  names, and all of them are explainable: the Home Assistant interface in the
  package, autouse fixtures and stand-ins for Home Assistant objects. One is a
  false positive you cannot strike out just like that: in
  `tests/test_campaign_editing.py` the call runs per screen through an assembled
  name (`getattr` on the screen name), and such helpers are alive. A dead-code
  guard on a ratchet therefore needs an exception list with it - or an AST
  inventory of its own that recognises the assembled `getattr` shape - so the
  number of unexplained hits stays at zero without silencing the fair reports.

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

## Could have

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
  into `Source.priority`, so the cheapest source wins as long as it can cope.
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
- **The `CoordinatorSurface` protocol is checked nowhere** — the four mixins inherit from
  it under `TYPE_CHECKING`, so mypy believes their `self` has every member, but nothing
  checks that the coordinator actually sets them. One test asking the coordinator for every
  protocol member after setup would close that; round 30's `entry` property shows such a
  member can simply appear.
- **The test stand-ins carry the interface by hand** — the stand-ins copy the
  coordinator's reading methods and set the matching attributes one by one. Every new
  member (`entry`, `season_override`) cost a round of failing tests in round 30. They could
  derive their attributes from `CoordinatorSurface`, or a test could demand that a stand-in
  carries every member the copied methods touch.
- **The 20 open branches of the coverage measurement** — `branch = true` reports twenty
  times one side of a loop or a short-circuit that never comes past. Neither a pragma nor a
  test covers them now; per one the question is whether the second side is reachable (then a
  test) or not (then a rewrite that removes the branch).
- **The sweep of orphaned entities misses the same completeness check** —
  `_async_remove_stale_entities` removes an entity when its `config_entry_id` is ours and its
  `unique_id` starts with our prefix, but it does not look at the platform or the domain; the
  override target has done that since round 34. It is hardly reachable (another integration
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

## Would have

- **Learning from run times** — measure each zone's heating and cooling rate and adapt the
  dead band or the pre-heating to it.
- **Balancing across circuits** — with two equivalent sources on different circuits, share
  the load instead of always picking the same one.
