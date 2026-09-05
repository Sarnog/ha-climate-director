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

- **De code opdelen zodat uitbreiden een toevoeging blijft** — vier bestanden dragen samen
  56% van de code (`coordinator.py`, `config_flow.py`, `engine/models.py` en
  `engine/decide.py`), en alle vier hebben ze fouten voortgebracht met dezelfde vorm: een
  eigenschap die op het ene pad gerepareerd is en op het pad ernaast blijft staan. Het gaat
  om verplaatsen, niet om nieuw gedrag — de volledige suite hoort bij elke stap even groen
  te blijven. De norm, de meting en de doelindeling staan in
  [`ARCHITECTURE.md`](ARCHITECTURE.md) onder "Uitbreidbaarheid". Volgorde: eerst een
  bewaking op de engine-grens, dan de twee bijna-parallelle paden in `decide.py`
  samenvoegen, dan `validate()` opdelen in losse regelfuncties, dan de coordinator in
  vieren, dan de formulieropbouw uit `config_flow.py`.
- **Virtuele `climate` per zone** — één bedieningsentiteit per ruimte, waarmee de gewenste
  temperatuur en stand rechtstreeks op een gewone thermostaatkaart te bedienen zijn. De
  director kiest daar dan de bron bij.
- **Poortinstellingen per zone voor wakker-, rooster-, stilte- en slaapregels** — die
  gelden nu in `GateSettings` voor de hele installatie. De keuze huishouden-vs-aanwezigheid,
  de aanwezigheidssensor en de nalooptijd zijn al per zone; een slaapkamer wil daarnaast
  andere slaap- en stiltevensters dan een woonkamer.

## Could have

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
- **Een huisbreed stilgezette bron als uitwijking melden** — staat de cv-ketel stil door
  een openstaande deur en neemt de airco het over, dan verwarmt de kamer elektrisch
  zonder dat `binary_sensor.…_op_reserve` daar iets over zegt: `passed_over` telt alleen
  bronnen die onbereikbaar zijn, en een stilgezette bron is dat niet. Een aparte melding
  zou dat zichtbaar maken zonder de melder bij elke openstaande deur te laten knipperen.
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
- **Overrides via acties** — `climate_director.set_override` (met een duur of tot de
  volgende gebeurtenis) en `climate_director.clear_override`, plus knoppen die ze
  aanroepen. De override-schakelaar per zone bestaat al; wat ontbreekt is deze
  actie-interface met een duur. `climate_director.evaluate` bestaat al.
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
- **Documenteren dat meerdere installaties naast elkaar mogen** — de code en de tests
  ondersteunen al twee config entries in één Home Assistant; de handleidingen zeggen er
  nog niets over.
- **Gasten- en vooruit-venster per weekdag** — het slaapvenster van een bewoner kent zijn
  dagen, maar het gastenvenster en het venster waarin vooruit verwarmen mag gelden nog
  voor elke dag hetzelfde. Wie in het weekend andere uren aanhoudt, kan dat daar niet
  zetten. Het model kan het al; het formulier en de opslag vragen er niet naar.
- **Mutatiemeting in de CI** — de dekking wordt gemeten en bewaakt, maar dekking zegt
  alleen dat een regel gedraaid is, niet dat er iets omvalt als hij verkeerd wordt. Een
  mutatieronde, al is het maar wekelijks, laat zien welke wijziging in de code geen enkele
  test raakt — precies het soort gat waar de bugs van de laatste review in zaten.

## Would have

- **Leren van looptijden** — de opwarm- en afkoelsnelheid per zone meten en de dode band
  of het voorverwarmen daarop aanpassen.
- **Balancering over circuits** — bij twee gelijkwaardige bronnen op verschillende
  circuits de belasting verdelen in plaats van altijd dezelfde te kiezen.
- **Opname in de HACS-standaardlijst** — zodat de integratie in HACS vindbaar wordt zonder
  handmatige "custom repository"-toevoeging. Pas indienen als hij zich een tijd in de
  praktijk bewezen heeft.

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

- **Split the code so that extending stays an addition** — four files carry 56% of the code
  between them (`coordinator.py`, `config_flow.py`, `engine/models.py` and
  `engine/decide.py`), and all four have produced bugs of the same shape: a property
  repaired on one path and left standing on the path next to it. This is moving code, not
  new behaviour — the full suite should stay just as green at every step. The norm, the
  measurement and the target layout are in [`ARCHITECTURE.md`](ARCHITECTURE.md) under
  "Extensibility". Order: first a guard on the engine border, then merging the two
  near-parallel paths in `decide.py`, then splitting `validate()` into separate rule
  functions, then the coordinator into four, then form building out of `config_flow.py`.
- **A virtual `climate` per zone** — one control entity per room, so the target temperature
  and mode can be set straight from an ordinary thermostat card. The director then picks the
  source to match.
- **Per-zone gate settings for wake, schedule, quiet and sleep rules** — those currently
  live in `GateSettings` for the whole installation. The household-vs-presence choice, the
  presence sensor and the grace period are already per zone; a bedroom also wants different
  sleep and quiet windows from a living room.

## Could have

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
- **Report a house-wide stopped source as a fallback** — with the boiler stopped by an
  open door and the air conditioner taking over, the room heats electrically without
  `binary_sensor.…_on_fallback` saying anything about it: `passed_over` counts only
  sources that are unreachable, and a stopped source is not. A separate report would make
  that visible without leaving the sensor blinking at every open door.
- **A house-wide power ceiling** — a maximum in watts across the whole installation, rather
  than only a maximum number of units per circuit. A limit in units says nothing about what
  actually leaves the meter: three small units are a very different thing from one boiler.
  Needs a wattage per source and an order in which to shed.
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
- **Overrides through actions** — `climate_director.set_override` (with a duration or
  until the next event) and `climate_director.clear_override`, plus buttons calling them.
  The per-zone override switch already exists; what is missing is this action interface with
  a duration. `climate_director.evaluate` already exists.
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
- **Document that several installations may sit side by side** — the code and tests already
  support two config entries in one Home Assistant; the manuals say nothing about it yet.
- **Guest and pre-conditioning window per weekday** — a resident's sleep window knows its
  days, but the guest window and the window in which pre-conditioning is allowed still
  apply to every day alike. Anyone keeping different hours at the weekend cannot set that
  there. The model already supports it; the form and storage do not ask for it.
- **Mutation measurement in CI** — coverage is measured and guarded, but coverage only says
  a line ran, not that anything breaks when it goes wrong. A mutation round, even a weekly
  one, shows which change to the code touches no test at all - exactly the kind of gap the
  bugs of the last review sat in.

## Would have

- **Learning from run times** — measure each zone's heating and cooling rate and adapt the
  dead band or the pre-heating to it.
- **Balancing across circuits** — with two equivalent sources on different circuits, share
  the load instead of always picking the same one.
- **Inclusion in the HACS default list** — so the integration becomes findable in HACS
  without adding it as a custom repository by hand. Only worth submitting once it has
  proven itself in practice for a while.
