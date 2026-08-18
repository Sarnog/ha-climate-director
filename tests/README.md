# Tests

## NL

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

**De Home Assistant-laag** wordt op twee manieren getest:

- `test_ha_helpers.py` — de pure helpers: seizoensnamen, getalconversie, de eventpayload en
  de formulierlogica van de config flow
- `test_ha_layer.py` — de laag zelf, met een nagebouwde Home Assistant eromheen: entiteiten
  uitlezen tot een momentopname (inclusief `unavailable`, `unknown`, een ontbrekende
  entiteit en een `weather`-entiteit), de service calls van de applier en wat er gebeurt als
  er één faalt, de gebeurtenissen op de bus, alle entiteiten met een echt plan eronder, en
  het vangnet als een bron onbereikbaar wordt

### Waarom niet tegen een draaiende hass

De gangbare testomgeving voor custom components,
[`pytest-homeassistant-custom-component`](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component),
importeert bij het laden `homeassistant.runner`, dat op module-niveau Unix-only
stdlib-modules gebruikt (`fcntl`, `resource`). Op het Windows-ontwikkelsysteem waarop dit
project gebouwd is bestaan die niet, en er is geen WSL of Docker beschikbaar.

De gewone `homeassistant`-package is wél geïnstalleerd, dus imports en API-signaturen
worden echt gecontroleerd.

### Wat dus niet automatisch gedekt is

Alleen nog wat Home Assistant zélf aanstuurt:

- de stappen van de config flow en de options flow (de formulierlogica erachter wél)
- `async_setup_entry`: het opzetten van de platforms en de volgorde daarvan
- de debouncer en het inplannen van een uitgestelde herberekening
- het registreren van entiteiten en het herstellen van schakelaarstanden na een herstart

Deze zijn met de hand gereviewd tegen de geïnstalleerde `homeassistant`-broncode
(signaturen met `grep` geverifieerd, niet uit het geheugen aangenomen). Ze worden in de
praktijk getest door de integratie in een echte Home Assistant te installeren — en dat
kan veilig, omdat schaduwmodus standaard aanstaat en er dan geen enkele service call
uitgaat.

### Draaien

```bash
pip install -r requirements_test.txt
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

## EN

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

**The Home Assistant layer** is tested in two ways:

- `test_ha_helpers.py` — the pure helpers: season names, number conversion, the event
  payload and the config flow's form logic
- `test_ha_layer.py` — the layer itself, with a stand-in Home Assistant around it: reading
  entities into a snapshot (including `unavailable`, `unknown`, a missing entity and a
  `weather` entity), the applier's service calls and what happens when one fails, the
  events on the bus, every entity with a real plan under it, and the safety net when a
  source becomes unreachable

### Why not against a running hass

The usual test environment for custom components,
[`pytest-homeassistant-custom-component`](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component),
imports `homeassistant.runner` on load, which uses Unix-only stdlib modules (`fcntl`,
`resource`) at module level. On the Windows development machine this project was built on
those do not exist, and no WSL or Docker is available.

The plain `homeassistant` package *is* installed, so imports and API signatures are
genuinely checked.

### What is therefore not covered automatically

Only what Home Assistant itself drives:

- the config flow and options flow steps (the form logic behind them is covered)
- `async_setup_entry`: setting up the platforms and the order of that
- the debouncer and scheduling a deferred re-evaluation
- registering entities and restoring switch states after a restart

These were reviewed by hand against the installed `homeassistant` source (signatures
verified with `grep`, not assumed from memory). They are tested in practice by installing
the integration in a real Home Assistant — which is safe to do, because shadow mode is on
by default and no service call goes out while it is.

### Running

```bash
pip install -r requirements_test.txt
python -m pytest
python -m ruff check .
python -m ruff format --check .
```
