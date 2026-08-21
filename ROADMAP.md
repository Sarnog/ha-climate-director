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

## Reparaties — uit de audit van 2026-08-20

Gevonden gebreken die eerst gerepareerd worden vóór de schaduwmodus uitgaat.
Het volledige stappenplan staat in de projectkennis van deze repo
(`.claude/skills/climate-director/SKILL.md`).

- **H3** een cover als raam/deur wordt nooit als open gezien.
- **H4** er is geen klokgestuurde herbeoordeling; alle tijdregels hangen op toeval.
- **M1–M8** opstartgedrag, gedeelde apparaten, `minutes: 0`, diagnose, zoneformulier, commandosensor voor generatoren, neerslag-bijwerking, vakantievlag op stiltevensters.

## Should have

- **Virtuele `climate` per zone** — één bedieningsentiteit per ruimte, waarmee de gewenste
  temperatuur en stand rechtstreeks op een gewone thermostaatkaart te bedienen zijn. De
  director kiest daar dan de bron bij.
- **Poortinstellingen per zone voor wakker-, rooster-, stilte- en slaapregels** — die
  gelden nu in `GateSettings` voor de hele installatie. De keuze huishouden-vs-aanwezigheid,
  de aanwezigheidssensor en de nalooptijd zijn al per zone; een slaapkamer wil daarnaast
  andere slaap- en stiltevensters dan een woonkamer.

## Could have

- **Huisbreed vermogensplafond** — een maximum in watt over de hele installatie, in plaats
  van alleen een maximum aantal units per circuit. Een grens in stuks zegt niets over wat
  er werkelijk uit de meter loopt: drie kleine units zijn iets heel anders dan één ketel.
  Vraagt een vermogen per bron en een rangorde bij het afkappen.
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

## Repairs — from the 2026-08-20 audit

Defects found, to be repaired before shadow mode is switched off. The full
step-by-step plan lives in this repo's project knowledge
(`.claude/skills/climate-director/SKILL.md`).

- **H3** a cover used as a door/window is never seen as open.
- **H4** there is no clock-driven re-evaluation; every time rule depends on chance.
- **M1–M8** startup behaviour, shared appliances, `minutes: 0`, diagnostics, zone form, command sensor for generators, precipitation side effect, holiday flag on quiet windows.

## Should have

- **A virtual `climate` per zone** — one control entity per room, so the target temperature
  and mode can be set straight from an ordinary thermostat card. The director then picks the
  source to match.
- **Per-zone gate settings for wake, schedule, quiet and sleep rules** — those currently
  live in `GateSettings` for the whole installation. The household-vs-presence choice, the
  presence sensor and the grace period are already per zone; a bedroom also wants different
  sleep and quiet windows from a living room.

## Could have

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

## Would have

- **Learning from run times** — measure each zone's heating and cooling rate and adapt the
  dead band or the pre-heating to it.
- **Balancing across circuits** — with two equivalent sources on different circuits, share
  the load instead of always picking the same one.
- **Inclusion in the HACS default list** — so the integration becomes findable in HACS
  without adding it as a custom repository by hand. Only worth submitting once it has
  proven itself in practice for a while.
