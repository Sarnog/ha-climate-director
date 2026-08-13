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

- **Applier** — `Plan` vergelijken met de werkelijke entiteitstoestanden en alleen het
  verschil uitvoeren, zodat opnieuw beslissen op hetzelfde moment nul service calls
  oplevert.
- **Coordinator** — toestandswijzigingen volgen van elke betrokken entiteit, ontdubbelen
  met een korte debounce, beslissingen serialiseren met een lock, en `Deferral`s inplannen
  zodat een plan dat op een timer wacht vanzelf hervat.
- **Schaduwmodus** — de integratie draait volledig mee, berekent elke beslissing en
  publiceert die, maar voert niets uit. Bedoeld om een bestaande set automatiseringen
  weken naast de engine te laten lopen en elk verschil te onderzoeken vóór de overname.
  Dit is de belangrijkste veiligheidsmaatregel van het hele project.
- **Config flow en options flow** — wizard: zones → bronnen → circuits → poorten →
  drempels. Inclusief een suggestie voor circuitgroepering op basis van gedeeld `device` /
  `via_device` / fabrikant, uitdrukkelijk als voorstel en niet als feit, omdat de meeste
  klimaatintegraties de buitenunit-relatie niet blootgeven.
- **Entiteiten** — een virtuele `climate` per zone als bedieningspunt, plus
  `sensor` (actieve bron met reden), `binary_sensor` (geblokkeerd), `number` per drempel,
  `switch` (hoofdschakelaar, vakantiemodus, override per zone), `select` (seizoen) en
  `button` (uit, opnieuw beslissen).
- **`climate_director_decision`-event** — na elke beslissing, met zone, bron, stand,
  temperatuur en reden, zodat notificaties buiten de integratie blijven.
- **Vertalingen** — `strings.json` plus `nl.json` en `en.json`, met elke `Reason` als
  `translation_key`.
- **Diagnostics** — downloadbare export van configuratie, laatste `WorldState` en laatste
  `Plan`, zodat een meldingsrapport meteen reproduceerbaar is.
- **Poortinstellingen per zone** — nu gelden `GateSettings` voor de hele installatie. Een
  slaapkamer wil andere aanwezigheids- en slaapregels dan een woonkamer.

## Could have

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
- **Blueprint voor notificaties** — een kant-en-klare automatisering die op
  `climate_director_decision` luistert, zodat nieuwe gebruikers niets hoeven te schrijven.
- **Meer conflictbeleiden** — bijvoorbeeld beurtelings (round-robin) of een vast schema
  per dagdeel.

## Would have

- **Meerdere installaties naast elkaar** — een tweede config entry voor een ander pand,
  met eigen zones en circuits.
- **Leren van looptijden** — de opwarm- en afkoelsnelheid per zone meten en de dode band
  of het voorverwarmen daarop aanpassen.
- **Balancering over circuits** — bij twee gelijkwaardige bronnen op verschillende
  circuits de belasting verdelen in plaats van altijd dezelfde te kiezen.
- **Opname in de HACS-standaardlijst** — pas zinvol als de integratie installeerbaar is.

---

# Roadmap

This file is this integration's ideas box: future changes, improvements and additions not
yet built, ordered as *should have* (probably valuable), *could have* (nice, situational)
and *would have* (later, a separate effort). Not everything here has been discussed or
approved — it is a place to pick from, prioritise or reject.

The history of what has already been built and changed is **not** here but in the
[release notes](https://github.com/Sarnog/ha-climate-director/releases) of each version.

## Should have

- **Applier** — compare the `Plan` against actual entity states and execute only the
  difference, so deciding again at the same moment produces zero service calls.
- **Coordinator** — track state changes of every entity involved, debounce briefly,
  serialise decisions with a lock, and schedule `Deferral`s so a plan held back by a timer
  resumes on its own.
- **Shadow mode** — the integration runs alongside, computes every decision and publishes
  it, but executes nothing. Meant for running an existing set of automations next to the
  engine for weeks and investigating every difference before handover. This is the single
  most important safety measure of the whole project.
- **Config flow and options flow** — wizard: zones → sources → circuits → gates →
  thresholds. Including a suggested circuit grouping based on shared `device` /
  `via_device` / manufacturer, explicitly as a proposal rather than a fact, since most
  climate integrations do not expose the outdoor-unit relationship.
- **Entities** — a virtual `climate` per zone as the control point, plus `sensor` (active
  source with reason), `binary_sensor` (blocked), `number` per threshold, `switch` (master,
  holiday mode, per-zone override), `select` (season) and `button` (off, re-evaluate).
- **`climate_director_decision` event** — after every decision, carrying zone, source,
  mode, temperature and reason, so notifications stay outside the integration.
- **Translations** — `strings.json` plus `nl.json` and `en.json`, with every `Reason` as a
  `translation_key`.
- **Diagnostics** — downloadable export of the configuration, the last `WorldState` and
  the last `Plan`, so a bug report is reproducible straight away.
- **Per-zone gate settings** — `GateSettings` currently applies to the whole installation.
  A bedroom wants different presence and sleep rules from a living room.

## Could have

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
- **Notification blueprint** — a ready-made automation listening for
  `climate_director_decision`, so new users need write nothing.
- **More conflict policies** — round-robin, for instance, or a fixed schedule per part of
  the day.

## Would have

- **Several installations side by side** — a second config entry for another building,
  with its own zones and circuits.
- **Learning from run times** — measure each zone's heating and cooling rate and adapt the
  dead band or the pre-heating to it.
- **Balancing across circuits** — with two equivalent sources on different circuits, share
  the load instead of always picking the same one.
- **Inclusion in the HACS default list** — only meaningful once the integration is
  installable.
