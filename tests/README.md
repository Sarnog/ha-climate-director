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

**De Home Assistant-laag** wordt getest op zijn pure helpers (`test_ha_helpers.py`):
seizoensnamen, getalconversie, de eventpayload, en de formulierlogica van de config flow.

### Waarom niet tegen een draaiende hass

De gangbare testomgeving voor custom components,
[`pytest-homeassistant-custom-component`](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component),
importeert bij het laden `homeassistant.runner`, dat op module-niveau Unix-only
stdlib-modules gebruikt (`fcntl`, `resource`). Op het Windows-ontwikkelsysteem waarop dit
project gebouwd is bestaan die niet, en er is geen WSL of Docker beschikbaar.

De gewone `homeassistant`-package is wél geïnstalleerd, dus imports en API-signaturen
worden echt gecontroleerd.

### Wat dus niet automatisch gedekt is

- de stappen van de config flow en de options flow zelf
- de coordinator: entiteiten uitlezen, debouncen, uitgestelde herberekeningen
- de entiteitsplatforms en het herstellen van schakelaarstanden
- de daadwerkelijke service calls van de applier

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

**The Home Assistant layer** is tested on its pure helpers (`test_ha_helpers.py`): season
names, number conversion, the event payload, and the config flow's form logic.

### Why not against a running hass

The usual test environment for custom components,
[`pytest-homeassistant-custom-component`](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component),
imports `homeassistant.runner` on load, which uses Unix-only stdlib modules (`fcntl`,
`resource`) at module level. On the Windows development machine this project was built on
those do not exist, and no WSL or Docker is available.

The plain `homeassistant` package *is* installed, so imports and API signatures are
genuinely checked.

### What is therefore not covered automatically

- the config flow and options flow steps themselves
- the coordinator: reading entities, debouncing, deferred re-evaluations
- the entity platforms and switch state restoration
- the applier's actual service calls

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
