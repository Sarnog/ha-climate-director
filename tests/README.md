# Tests

## NL

> **Alle tijd in deze testset is gesimuleerd.** Een simulatie van een half jaar is een
> nagebouwd huis met een nagebouwde klok, doorlopen in seconden. Het zegt niets over
> draaiuren in een echte installatie, en mag nergens zo opgeschreven worden.

### Twee soorten tests

**De engine** (`custom_components/climate_director/engine/`) importeert Home Assistant
nergens. Die is dus volledig te testen: elk klimaatscenario is een gewoon dataobject, en
de hele suite draait in een halve seconde. Dat is de reden dat die scheidslijn bestaat.

- `test_families.py` — `hvac_mode` naar compressorbedrijf, inclusief `dry` als koelbedrijf
- `test_models.py` — vensters, tijdvensters, opzoekfuncties en `validate()`
- `test_gates.py` — hoofdschakelaar, override, openingen, aanwezigheid, slaap, rooster
- `test_hysteresis.py` — de dode band, en het pendelen dat hij voorkomt
- `test_sources.py` — bronkeuze en de cutover tussen cv-ketel en warmtepomp
- `test_circuits.py` — de vier installatievoorbeelden, conflictbeleiden, capaciteit,
  taakwisselvertraging en kortcyclusbescherming
- `test_decide.py` — de pijplijn als geheel
- `test_legacy_behaviour.py` — de twintig automatiseringen en vier scripts die vervangen
  worden, stuk voor stuk als scenario
- `test_serialise.py` — heen en terug tussen config entry en dataclasses
- `test_diff.py` — welke service calls er nodig zijn, en wanneer geen
- `test_random_installations.py` — tweeduizend geldige huizen met elke optie erin, elk in
  een willekeurige wereld, plus de weg van het formulier naar een besluit
- `test_month_simulation.py` en `test_seasons_simulation.py` — hele maanden in gesloten
  lus: wat de director aanzet gaat draaien, wat draait warmt de kamer op, en de volgende
  ronde ziet het gevolg. Pas daar tellen de regels die alleen in de tijd bestaan. De motor
  eronder staat in `simulation.py`

**De Home Assistant-laag** wordt op drie manieren getest:

- `test_ha_helpers.py` — de pure helpers: seizoensnamen, getalconversie, de eventpayload en
  de formulierlogica van de config flow
- `test_ha_layer.py` — de laag zelf, met een nagebouwde Home Assistant eromheen: entiteiten
  uitlezen tot een momentopname (inclusief `unavailable`, `unknown`, een ontbrekende
  entiteit en een `weather`-entiteit), de service calls van de applier en wat er gebeurt als
  er één faalt, de gebeurtenissen op de bus, alle entiteiten met een echt plan eronder, en
  het vangnet als een bron onbereikbaar wordt
- de `test_campaign_*`-bestanden — dezelfde laag, maar dan in een **echt draaiende** Home
  Assistant. `harness_live.py` zet er een op in het geheugen, met deze integratie als custom
  component erin

### De echte Home Assistant

`harness_live.py` bouwt een `HomeAssistant` op, laadt de registers, en zet de config entry
op langs de gewone weg: `async_setup_entry`, de platforms omhoog, de entiteiten in het
register, de acties geregistreerd. De klimaatapparaten zijn nagebouwd —
`climate.set_hvac_mode` en `climate.set_temperature` schrijven de toestand terug — waardoor
de lus rond is: de director stuurt, de apparaten veranderen, en dat leidt tot een volgende
beslissing.

- `test_campaign_live_ha.py` — opzetten, afbreken, herladen, de drie acties met hun velden
  en grenzen, de schakelaars, de getallen, de knop, alle sensoren, de gebeurtenissen, de
  schaduwmodus, en een verzoek dat een herstart overleeft
- `test_campaign_live_flows.py` — de wizard en de options flow stap voor stap, de
  reparatiemelding bij een foute configuratie, standen die een herstart moeten overleven, en
  temperaturen uit een `weather`-entiteit of uit de binnenunit zelf
- `test_campaign_settings.py` — elke instelling die een gebruiker kan zetten, van seizoen en
  vakantie-agenda tot vertragingen, conflictbeleiden en de gedeelde ketel, telkens
  gecontroleerd op het gevolg in plaats van op de opslag. De klok wordt daarbij vooruit
  gezet in plaats van afgewacht
- `test_campaign_outages.py` — elke combinatie van uitgevallen apparaten in een huis met
  reservebronnen, en dezelfde gevallen als `unavailable`, `unknown` en helemaal weg in een
  draaiende Home Assistant
- `test_campaign_year.py` — twee halve jaren **gesimuleerde tijd** in een groot huis met
  twee buitenunits, een gedeelde ketel, een uitsluitende groep, een handbediende airco en
  een verplicht rooster. Samen met de andere simulaties komt elke maand van het jaar aan
  bod

### Waarom niet met `pytest-homeassistant-custom-component`

De gangbare testomgeving voor custom components,
[`pytest-homeassistant-custom-component`](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component),
importeert bij het laden `homeassistant.runner`, dat op module-niveau Unix-only
stdlib-modules gebruikt (`fcntl`, `resource`). Op het Windows-ontwikkelsysteem waarop dit
project gebouwd is bestaan die niet, en er is geen WSL of Docker beschikbaar.

Een `HomeAssistant` zelf opbouwen kan wél, en dat is precies wat `harness_live.py` doet.
Daarmee draait de echte kern: de config entries, de registers, de bus, de acties en de
entiteitsplatforms.

### Wat dus niet automatisch gedekt is

- de echte klimaatintegraties en de apparaten eronder: hier staan nagebouwde acties die de
  toestand netjes terugschrijven, en een echte airco doet dat trager en soms anders
- de interface: hoe een formulier eruitziet, of een vertaling lekker loopt
- alles wat over uren of dagen aan een echte klok hangt; de tijd wordt in de tests verzet in
  plaats van afgewacht

Deze zijn met de hand gereviewd tegen de geïnstalleerde `homeassistant`-broncode
(signaturen met `grep` geverifieerd, niet uit het geheugen aangenomen). Beoordelen kan
alleen door de integratie in een echte Home Assistant te installeren, en **dat is nog niet
gebeurd** — er is nog nergens draaitijd. Wie eraan begint kan dat veilig doen, omdat
schaduwmodus standaard aanstaat en er dan geen enkele service call uitgaat.

### Draaien

```bash
pip install -r requirements_test.txt
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

## EN

> **All time in this test set is simulated.** A half-year simulation is a rebuilt house
> with a rebuilt clock, walked in seconds. It says nothing about running hours in a real
> installation, and must never be written up as though it did.

### Two kinds of test

**The engine** (`custom_components/climate_director/engine/`) imports Home Assistant
nowhere. It is therefore fully testable: every climate scenario is a plain data object,
and the whole suite runs in half a second. That is the reason the dividing line exists.

- `test_families.py` — `hvac_mode` to compressor duty, including `dry` as cooling duty
- `test_models.py` — windows, time windows, lookups and `validate()`
- `test_gates.py` — master switch, override, openings, occupancy, sleep, schedule
- `test_hysteresis.py` — the dead band, and the chattering it prevents
- `test_sources.py` — source selection and the boiler-to-heat-pump cutover
- `test_circuits.py` — the four installation examples, conflict policies, capacity, duty
  switch delay and short-cycle protection
- `test_decide.py` — the pipeline as a whole
- `test_legacy_behaviour.py` — the twenty automations and four scripts being replaced,
  each as a scenario
- `test_serialise.py` — round trips between config entry and dataclasses
- `test_diff.py` — which service calls are needed, and when none are
- `test_random_installations.py` — two thousand valid houses using every option, each in a
  random world, plus the road from the form to a decision
- `test_month_simulation.py` and `test_seasons_simulation.py` — whole months in a closed
  loop: what the director switches on runs, what runs warms the room, and the next round
  sees the consequence. Only there do the rules that exist solely in time count. The engine
  under them is `simulation.py`

**The Home Assistant layer** is tested in three ways:

- `test_ha_helpers.py` — the pure helpers: season names, number conversion, the event
  payload and the config flow's form logic
- `test_ha_layer.py` — the layer itself, with a stand-in Home Assistant around it: reading
  entities into a snapshot (including `unavailable`, `unknown`, a missing entity and a
  `weather` entity), the applier's service calls and what happens when one fails, the
  events on the bus, every entity with a real plan under it, and the safety net when a
  source becomes unreachable
- the `test_campaign_*` files — the same layer, but inside a **really running** Home
  Assistant. `harness_live.py` stands one up in memory with this integration in it as a
  custom component

### The real Home Assistant

`harness_live.py` builds a `HomeAssistant`, loads the registries, and sets the config entry
up along the ordinary road: `async_setup_entry`, the platforms up, the entities in the
registry, the actions registered. The climate appliances are stand-ins —
`climate.set_hvac_mode` and `climate.set_temperature` write the state back — which closes
the loop: the director steers, the appliances change, and that leads to the next decision.

- `test_campaign_live_ha.py` — setting up, tearing down, reloading, the three actions with
  their fields and limits, the switches, the numbers, the button, every sensor, the events,
  shadow mode, and a request surviving a restart
- `test_campaign_live_flows.py` — the wizard and the options flow step by step, the repair
  notice on a wrong configuration, states that have to survive a restart, and temperatures
  from a `weather` entity or from the indoor unit itself
- `test_campaign_settings.py` — every setting a user can pick, from the season and the
  holiday calendar to delays, conflict policies and the shared boiler, each checked on its
  consequence rather than on its storage. Time is moved forward there rather than waited out
- `test_campaign_outages.py` — every combination of failed appliances in a house with
  reserve sources, and the same cases as `unavailable`, `unknown` and gone altogether inside
  a running Home Assistant
- `test_campaign_year.py` — two half-years of **simulated time** in a large house with two
  outdoor units, a shared boiler, an exclusive group, a hand-operated air conditioner and a
  compulsory schedule. Together with the other simulations every month of the year is
  covered

### Why not with `pytest-homeassistant-custom-component`

The usual test environment for custom components,
[`pytest-homeassistant-custom-component`](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component),
imports `homeassistant.runner` on load, which uses Unix-only stdlib modules (`fcntl`,
`resource`) at module level. On the Windows development machine this project was built on
those do not exist, and no WSL or Docker is available.

Building a `HomeAssistant` directly *is* possible, and that is exactly what
`harness_live.py` does. That runs the real core: the config entries, the registries, the
bus, the actions and the entity platforms.

### What is therefore not covered automatically

- the real climate integrations and the devices under them: here stand-in actions write the
  state back neatly, and a real air conditioner does that more slowly and sometimes
  differently
- the interface: what a form looks like, whether a translation reads well
- anything hanging on a real clock over hours or days; time is moved in the tests rather
  than waited out

These were reviewed by hand against the installed `homeassistant` source (signatures
verified with `grep`, not assumed from memory). Judging them takes installing the
integration in a real Home Assistant, and **that has not happened yet** — there are no
running hours anywhere. Whoever starts can do so safely, because shadow mode is on by
default and no service call goes out while it is.

### Running

```bash
pip install -r requirements_test.txt
python -m pytest
python -m ruff check .
python -m ruff format --check .
```
