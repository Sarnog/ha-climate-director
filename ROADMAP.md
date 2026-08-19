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

## Should have

- **De "geblokkeerd"-melder gaat ook aan bij een dichte poort** — `binary_sensor.*_<zone>_geblokkeerd`
  volgt nu "vroeg meer dan hij kreeg", en een zone met een dichte poort vraagt niets: die
  komt niet eens aan zijn wens toe. Daardoor staat de melder juist uit in alle gevallen
  waarvoor zijn eigen attribuut `closed_gates` bestaat — een openstaand raam, niemand
  thuis, iedereen in bed, buiten het rooster, stille uren, een lege kamer. De reden en de
  lijst dichte poorten staan er wél in, dus wie de attributen bekijkt ziet alles; wie een
  automatisering op de sensor zelf bouwt krijgt nooit een melding. Te overwegen: de melder
  aan laten gaan zodra er een poort dicht staat én de kamer buiten zijn dode band ligt, of
  er een tweede melder naast zetten zodat de betekenis van de bestaande niet verschuift.
- **Een uitsluitende groep telt ook wat er doordraait in een overgedragen zone** —
  `exclusive_groups` kijkt alleen naar zones die deze ronde iets vrágen. Staat een lid van
  de groep te draaien in een zone die is overgedragen (de override-schakelaar om, of zelf
  bij het apparaat uitgezet), dan stuurt de director daar niets naartoe én mag een ander
  lid gewoon starten — precies de combinatie die de groep hoort uit te sluiten. Voor de
  buitenunit is dat al opgelost (`_standing_claims` telt een doordraaiende unit als een
  bezette plek); voor de groep nog niet. Voorstel: hetzelfde doen — een draaiend lid dat de
  director met rust laat bezet de groep, zodat een ander lid moet wachten in plaats van
  ernaast te gaan draaien. Uitzetten van het overgedragen apparaat blijft uitgesloten; een
  override is een override.
- **Virtuele `climate` per zone** — één bedieningsentiteit per ruimte, waarmee de gewenste
  temperatuur en stand rechtstreeks op een gewone thermostaatkaart te bedienen zijn. De
  director kiest daar dan de bron bij.
- **Huisbreed vermogensplafond** — een maximum in watt over de hele installatie, in plaats
  van alleen een maximum aantal units per circuit. Een grens in stuks zegt niets over wat
  er werkelijk uit de meter loopt: drie kleine units zijn iets heel anders dan één ketel.
  Vraagt een vermogen per bron en een rangorde bij het afkappen.
- **Temperatuurschema per zone** — een streeftemperatuur die met de klok meebeweegt
  (nacht koeler, ochtend warmer), in plaats van één waarde per zone die alleen door de
  poorten aan- en uitgezet wordt.
- **Neerslag zet de "zet een raam open"-grens opzij** — de buitengrens per zone is een
  zuinigheidsregel met een aanname eronder: is het buiten aangenamer dan binnen, dan kun je
  beter een deur of een raam openzetten dan de airco aanzetten. Regent het, dan gaat die
  aanname niet op — dan blijft die deur dicht en gebeurt er dus niets, terwijl het binnen
  te warm of te koud blijft.

  Het voorstel: een neerslagbron aanwijzen (de `condition` van een `weather`-entiteit, of
  een eigen regensensor) en, zolang die neerslag meldt, de **buitengrens per zone**
  overslaan — precies zoals een vooruit-verzoek dat nu al doet. De dode band, het seizoen
  en de buitengrens **per bron** blijven gelden; die kiezen nog steeds het apparaat.

  Uit te zoeken: welke `weather`-condities meetellen (`rainy`, `pouring`, `snowy`,
  `hail`, `lightning-rainy`), of een nalooptijd nodig is zodat een bui van vijf minuten de
  regeling niet laat stuiteren, en of dit per zone aan of uit moet kunnen — een zolder
  zonder ramen heeft er niets aan.
- **Overrides via acties** — `climate_director.set_override` (met een duur of tot de
  volgende gebeurtenis) en `climate_director.clear_override`, plus knoppen die ze
  aanroepen. `climate_director.evaluate` bestaat al.
- **`select` voor het seizoen** — het seizoen met de hand omzetten zonder de options flow.
- **`fan_only` voor een verliezer wordt gegeven zonder te weten of de unit het kan** — bij
  `allow_fan_only_during_conflict` krijgt een verliezende zone `fan_only`. Units die alleen
  heat/cool/off kennen weigeren die modus; de mislukte service call telt als mislukte
  *stop* en breekt de rest van het plan af. Voorstel: `ClimateState` uitbreiden met
  `hvac_modes` en in `_idle_mode` op `off` terugvallen wanneer `fan_only` ontbreekt.
- **Een sensor die bestaat maar geen getal levert, wordt niet gemeld** — een `climate`
  zonder `current_temperature` of een sensor zonder numerieke waarde geeft
  `NO_INDOOR_TEMPERATURE`; de zone doet niets, en de vastloopmelder telt die reden niet
  mee. Voorstel: na het lezen van de wereld melden welke ingestelde sensoren geen getal
  opleveren (met een nalooptijd tegen opstartruis).
- **Poortinstellingen per zone** — nu gelden `GateSettings` voor de hele installatie. Een
  slaapkamer wil andere aanwezigheids- en slaapregels dan een woonkamer.
- **Suggestie voor circuitgroepering** — voorstellen welke binnenunits een buitenunit delen
  op basis van gedeeld `device` / `via_device` / fabrikant, uitdrukkelijk als voorstel en
  niet als feit, omdat de meeste klimaatintegraties die relatie niet blootgeven.

## Could have

- **De droogstand als eigen taak** — de engine leest `dry` wel (het telt als koelen), maar
  kiest hem nooit: er wordt alleen `heat`, `cool`, `fan_only` en `off` aangestuurd. Wie bij
  vochtig weer bewust ontvochtigt, moet dat nu naast de integratie doen. Een zone zou een
  derde taak moeten kunnen hebben, met een eigen aan-/uitpunt op een
  luchtvochtigheidssensor in plaats van op een thermometer — en met de hand aan te zetten
  voor wie geen sensor heeft. Op een niet-simultaan circuit hoort `dry` bij de koelfamilie,
  dus die kant is al geregeld.

- **Meerdere binnensensoren per zone** — nu wijst een zone één entiteit aan. Meerdere
  sensoren met een keuze uit gemiddelde, laagste, hoogste of "de eerste die een waarde
  geeft" scheelt een handgemaakte template- of min/max-helper voor wie meerdere meters in
  één ruimte heeft.
- **Openingen met herstel per zone** — nu schort een opening een zone op; een expliciete
  momentopname-en-herstel-route zou ook handmatig ingestelde standen kunnen teruggeven.
- **Conflictdetector** — signaleren dat units zich gedragen alsof ze een buitenunit delen
  (spontane taakwissels, terugvallende standen) en de gebruiker vragen of de
  circuitgroepering klopt.
- **Voorverwarmen en voorkoelen** — een zone alvast op temperatuur brengen tegen de tijd
  dat het rooster opengaat, in plaats van pas op dat moment te beginnen.
- **Energieprijs als bronvoorkeur** — een dynamisch tarief of een
  zonnepanelenoverschot laten meewegen in `Source.priority`, zodat de goedkoopste bron
  wint zolang die het aankan.
- **Weersvoorspelling in het buitentemperatuurvenster** — schakelen op de verwachte
  temperatuur over enkele uren in plaats van alleen de huidige.
- **Vochtigheid** — `dry` als eigen taak met een eigen drempel, in plaats van alleen als
  lid van de koelfamilie.
- **Meer conflictbeleiden** — bijvoorbeeld beurtelings (round-robin) of een vast schema
  per dagdeel.
- **Vertaal de "en nog N meer"-regel van de reparatiemelding** — `problems.summarise`
  plakt bij meer dan vijf configuratieproblemen een hardcoded Engelse regel
  `- ... and N more` onder de (wel vertaalde) lijst. Voor wie de interface in het
  Nederlands of een andere taal draait, is dat de enige zin in de melding die Engels
  blijft. Een vertaling onder `exceptions` met plaatshouder `{remaining}` lost dat op.

## Would have

- **Meerdere installaties naast elkaar** — een tweede config entry voor een ander pand,
  met eigen zones en circuits.
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

## Should have

- **The "blocked" sensor should also come on for a shut gate** — `binary_sensor.*_<zone>_blocked`
  currently follows "asked for more than it got", and a zone with a shut gate asks for
  nothing: it never gets as far as its wish. So the sensor is off in exactly the cases its
  own `closed_gates` attribute exists for — an open window, nobody home, everybody asleep,
  outside the schedule, quiet hours, an empty room. The reason and the list of shut gates
  are in the attributes, so whoever inspects those sees everything; whoever builds an
  automation on the sensor itself never gets a notification. Worth considering: turning the
  sensor on once a gate is shut *and* the room sits outside its dead band, or adding a
  second sensor beside it so the existing one's meaning does not shift.
- **An exclusive group should count what keeps running in a handed-over zone** —
  `exclusive_groups` only looks at zones asking for something this round. If a member of
  the group is running in a zone that has been handed over (the override switch thrown, or
  switched off at the appliance itself), the director sends it nothing *and* another member
  is free to start — exactly the combination the group is meant to rule out. For the
  outdoor unit this is already solved (`_standing_claims` counts a running unit as an
  occupied slot); for the group it is not. Proposal: do the same — a running member the
  director leaves alone occupies the group, so another member waits rather than running
  alongside it. Switching the handed-over appliance off stays out of the question; an
  override is an override.
- **A virtual `climate` per zone** — one control entity per room, so the target temperature
  and mode can be set straight from an ordinary thermostat card. The director then picks the
  source to match.
- **A house-wide power ceiling** — a maximum in watts across the whole installation, rather
  than only a maximum number of units per circuit. A limit in units says nothing about what
  actually leaves the meter: three small units are a very different thing from one boiler.
  Needs a wattage per source and an order in which to shed.
- **A temperature schedule per zone** — a target that moves with the clock (cooler at
  night, warmer in the morning), instead of one value per zone that the gates merely switch
  on and off.
- **Precipitation sets the "open a window" bound aside** — a zone's outdoor window is a
  thrift rule with an assumption under it: if it is nicer outside than in, you are better
  off opening a door or a window than switching the air conditioner on. When it rains that
  assumption does not hold - the door stays shut, so nothing happens, while the room stays
  too warm or too cold.

  The proposal: name a precipitation source (a `weather` entity's `condition`, or a rain
  sensor of your own) and, for as long as it reports precipitation, skip the **per-zone**
  outdoor window - exactly as a pre-conditioning request already does. The dead band, the
  season and the outdoor window **per source** still apply; those still pick the appliance.

  To work out: which `weather` conditions count (`rainy`, `pouring`, `snowy`, `hail`,
  `lightning-rainy`), whether a grace period is needed so a five-minute shower does not
  make the regulation bounce, and whether this should be switchable per zone - an attic
  without windows gains nothing from it.
- **Overrides through actions** — `climate_director.set_override` (with a duration or
  until the next event) and `climate_director.clear_override`, plus buttons calling them.
  `climate_director.evaluate` already exists.
- **A `select` for the season** — flipping the season by hand without the options flow.
- **`fan_only` is handed to a loser without knowing whether the unit supports it** — with
  `allow_fan_only_during_conflict`, a losing zone gets `fan_only`. Units that only know
  heat/cool/off refuse that mode; the failed service call counts as a failed *stop* and
  aborts the rest of the plan. Proposal: extend `ClimateState` with `hvac_modes` and fall
  back to `off` in `_idle_mode` when `fan_only` is missing.
- **A sensor that exists but reports no number is not reported** — a `climate` without
  `current_temperature` or a sensor without a numeric value yields
  `NO_INDOOR_TEMPERATURE`; the zone does nothing, and the stuck sensor does not count that
  reason. Proposal: after reading the world, report which configured sensors yield no
  number (with a grace period against startup noise).
- **Per-zone gate settings** — `GateSettings` currently applies to the whole installation.
  A bedroom wants different presence and sleep rules from a living room.
- **Suggested circuit grouping** — propose which indoor units share an outdoor unit based on
  shared `device` / `via_device` / manufacturer, explicitly as a proposal rather than a
  fact, since most climate integrations do not expose that relationship.

## Could have

- **Drying as a duty of its own** — the engine does read `dry` (it counts as cooling) but
  never picks it: only `heat`, `cool`, `fan_only` and `off` are commanded. Anyone
  deliberately dehumidifying in muggy weather has to do that beside the integration. A zone
  should be able to carry a third duty, with its own switch-on point on a humidity sensor
  rather than on a thermometer — and switchable by hand for those without such a sensor. On
  a non-simultaneous circuit `dry` already belongs to the cooling family, so that side is
  settled.

- **Several indoor sensors per zone** — a zone currently names one entity. Several sensors
  with a choice of average, lowest, highest or "the first one reporting a value" saves a
  hand-built template or min/max helper for anyone with more than one meter in a room.
- **Openings with per-zone restore** — an opening currently suspends a zone; an explicit
  snapshot-and-restore path could also give manually set modes back.
- **Conflict detector** — spot units behaving as though they share an outdoor unit
  (spontaneous duty swaps, modes falling back) and ask the user whether the circuit
  grouping is right.
- **Pre-heating and pre-cooling** — bring a zone up to temperature by the time the
  schedule opens, rather than starting only at that moment.
- **Energy price as source preference** — let a dynamic tariff or a solar surplus weigh
  into `Source.priority`, so the cheapest source wins as long as it can cope.
- **Weather forecast in the outdoor window** — switch on the temperature expected in a few
  hours rather than only the current one.
- **Humidity** — `dry` as a duty of its own with its own threshold, instead of only as a
  member of the cooling family.
- **More conflict policies** — round-robin, for instance, or a fixed schedule per part of
  the day.
- **Translate the repair notice's "and N more" line** — `problems.summarise` appends a
  hardcoded English line `- ... and N more` under the (translated) list when there are more
  than five configuration problems. For anyone running the interface in Dutch or another
  language, that is the one sentence in the notice that stays English. A translation under
  `exceptions` with a `{remaining}` placeholder solves it.

## Would have

- **Several installations side by side** — a second config entry for another building,
  with its own zones and circuits.
- **Learning from run times** — measure each zone's heating and cooling rate and adapt the
  dead band or the pre-heating to it.
- **Balancing across circuits** — with two equivalent sources on different circuits, share
  the load instead of always picking the same one.
- **Inclusion in the HACS default list** — so the integration becomes findable in HACS
  without adding it as a custom repository by hand. Only worth submitting once it has
  proven itself in practice for a while.
