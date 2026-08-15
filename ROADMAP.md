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

- **Virtuele `climate` per zone** — één bedieningsentiteit per ruimte, waarmee de gewenste
  temperatuur en stand rechtstreeks op een gewone thermostaatkaart te bedienen zijn. De
  director kiest daar dan de bron bij.
- **`number`-entiteiten voor de drempels** — aan- en uitpunten en dode banden op een
  dashboard te verschuiven zonder de options flow te openen.
- **Overrides via acties** — `climate_director.set_override` (met een duur of tot de
  volgende gebeurtenis) en `climate_director.clear_override`, plus knoppen die ze
  aanroepen. `climate_director.evaluate` bestaat al.
- **`select` voor het seizoen** — het seizoen met de hand omzetten zonder de options flow.
- **Poortinstellingen per zone** — nu gelden `GateSettings` voor de hele installatie. Een
  slaapkamer wil andere aanwezigheids- en slaapregels dan een woonkamer.
- **Suggestie voor circuitgroepering** — voorstellen welke binnenunits een buitenunit delen
  op basis van gedeeld `device` / `via_device` / fabrikant, uitdrukkelijk als voorstel en
  niet als feit, omdat de meeste klimaatintegraties die relatie niet blootgeven.

## Could have

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

- **A virtual `climate` per zone** — one control entity per room, so the target temperature
  and mode can be set straight from an ordinary thermostat card. The director then picks the
  source to match.
- **`number` entities for the thresholds** — switch-on/off points and dead bands adjustable
  from a dashboard without opening the options flow.
- **Overrides through actions** — `climate_director.set_override` (with a duration or
  until the next event) and `climate_director.clear_override`, plus buttons calling them.
  `climate_director.evaluate` already exists.
- **A `select` for the season** — flipping the season by hand without the options flow.
- **Per-zone gate settings** — `GateSettings` currently applies to the whole installation.
  A bedroom wants different presence and sleep rules from a living room.
- **Suggested circuit grouping** — propose which indoor units share an outdoor unit based on
  shared `device` / `via_device` / manufacturer, explicitly as a proposal rather than a
  fact, since most climate integrations do not expose that relationship.

## Could have

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
- **Inclusion in the HACS default list** — so the integration becomes findable in HACS
  without adding it as a custom repository by hand. Only worth submitting once it has
  proven itself in practice for a while.
