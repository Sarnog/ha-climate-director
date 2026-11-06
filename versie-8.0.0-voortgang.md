# Voortgang 8.0.0 — de opruimronde van de code-indeling

Deze release verandert geen gedrag. Elke stap hieronder is één commit, wordt
pas gepusht als de voorganger groen is, en houdt zijn eigen bewijs bij.

## Stand

- **Basis:** `main` op `05d59c5` (ontwerp, publieke namen, toetssplitsing,
validatie, opslag, hand, handstart, configuratiestroom en formulieren), schone
boom, `main == origin/main`.
- **Gebruikersbesluiten:** N14/N15 blijven **later**; N16 wordt **geen**
  7.7.10. Beide blijven in `ROADMAP.md` en `ARCHITECTURE.md` staan; 8.0.0
  verandert geen gedrag en geen tekst.
- **Productie:** draait 7.7.7. Alleen gelezen; niets geïnstalleerd, herstart of
  gewijzigd.
- **Nu:** stap 7 staat in de werkboom: `decide.py` is de ingang van 82 regels,
  de stappen wonen in `candidates.py`, `grants.py`, `commands.py`,
  `command_stops.py`, `command_reasons.py` en `zone_decisions.py`. Nog niet
  gecommit.

## Stappen

| Stap | Commit | Stand |
|---|---|---|
| Ontwerp | `6df44e2` | klaar: `ARCHITECTURE.md` “Code-indeling” NL + EN |
| 1. Publieke namen | `74f7c01` | klaar: mixins, helpers, schemaconstanten en opslaglezers zijn publiek |
| 2. Toetsen per onderwerp + impactkaart | `4c9f1cf` | klaar: 50 toetsbestanden verdeeld, hulpjes verhuisd, kaart bijgewerkt |
| 3. Validatie en `stored_state.py` | `79424dd` | klaar: `engine/validation.py` (1328 regels), `models.py` 2269 → 1154, `state_extra.py` → `stored_state.py` |
| 4. Opslag en serialisatie | `bb84325` (kaartherstel `fd26bce`) | klaar: `serialise.py` 152 regels, drie opslagmodules en `storage_values.py` |
| 5. Hand en handstart | `d27c3b6` | klaar: `hand.py`, `engine/quiet.py`, `engine/schedule.py`, `brakes_remaining` bij `gates.py` |
| 6. Configuratiestroom en formulieren | `05d59c5` | klaar: `config_flow.py` 456, `flow_validation.py` 380, `flow_*` en `form_*` |
| 7. `engine/decide.py` | deze commit | klaar: `decide.py` 82 regels en zes onderwerpsmodules |
| 8. `engine/models.py` | nog te maken | wacht |
| 9. `coordinator.py` | nog te maken | wacht |
| 10. `problems.py`, `texts.py`, `__init__.py` | nog te maken | wacht |
| Release 8.0.0 | nog te maken | wacht |

## Bewijs

Stap 1 is gemeten. De engine-probe (42 regels, 22:05:58) en de v1-probe
(64 regels, 22:06:13) zijn byte-gelijk op de basis en de werkboom. De E-probe
(107 regels, 08:07:52, parallel gedraaid), de N-probe (124 regels, 10m08s) en
de Q-probe (139 regels, 8m07s) zijn alle drie identiek. `--collect-only`
geeft 3936 toetsen aan beide kanten en een leeg verschil. De volledige suite
was 3935 passed en één rood op de maatratel doordat langere publieke namen
twee regels inspringen; de namen zijn korter gemaakt en de ratel is weer
groen.

Stap 2 is gemeten. De 3936 bestaande toetsnamen zijn identiek gebleven; de
collectie groeide naar 3977 door 38 nieuwe `test_timeless`-parameters voor de
nieuwe bestanden en 3 nieuwe selectietoetsen. De gerichte ronde over alle
gewijzigde toetsbestanden gaf 985 passed in 21m22s (log
`%TEMP%/800/step2-maprun.log`); de schermbewakingen gaven 259 passed in 18,52s
(log `%TEMP%/800/step2-final-guards.log`) en de selectietoetsen 73 passed in
1,76s (log `%TEMP%/800/select-final.log`). De volledige suite gaf 3975 passed
en twee rood in 32m05s (log `%TEMP%/800/step2-full.log`): de verouderde
impactkaart en een ontbrekende `Dekking`/`Coverage`-alinea in
`test_reporting_live.py`; beide zijn gedicht en daarna groen. Dekking 100 %
regels en takken (5927 regels, 2092 takken), de poort meldt 41 benoemde
uitsluitingen, en de kaart is bijgewerkt met de 50 gedraaide toetsbestanden.

Stap 3 is gemeten. `models.py` ging van 2269 naar 1154 regels; de controles,
`Problem`, `validate()` en de ene `RULES`-lijst staan in `engine/validation.py`
(1328 regels); `validation_extra.py` is opgegaan in die module en
`state_extra.py` heet nu `stored_state.py`. De engine-probe (42 regels), de
v1-probe (64 regels) en de E-probe (107 regels) zijn byte-gelijk op de basis en
de werkboom. De volledige suite gaf 3977 passed in 36m54s (log
`%TEMP%/800/step3-full.log`), de dekking is 100 % regels en takken (5926/2092),
de poort meldt 41 benoemde uitsluitingen en de kaart is bijgewerkt. De 54
`Problem`-codes zijn gelijk aan de basis. De mutatielijst was vóór de verhuizing
66 van 66 gevangen (logmap `%TEMP%/800/mutlogs`, vier lanes, 15m39s); de ronde
na de verhuizing volgt vóór de push. Afwijking: de CI-mutatiebaan van `74f7c01`
bleef 2u22m in `Run mutations` hangen zonder één regel uitvoer en is geannuleerd;
daarom is de lijst lokaal gedraaid. `manual_only_problems` woont voorlopig in
`validation.py` en verhuist in stap 8 naar `engine/manual_sources.py`, zoals de
tabel zegt.

Stap 4 is gemeten. `serialise.py` ging van 637 naar 152 regels; de vertaling
woont in `installation_storage.py` (233), `equipment_storage.py` (206) en
`resident_storage.py` (155), en `storage_helpers.py` heet nu
`storage_values.py` (159). De opslagronde gaf 434 passed in 27,91s (log
`%TEMP%/800/step4-tests.log`); de volledige suite gaf 3978 passed en één rood
in 34m34s (log `%TEMP%/800/step4-full.log`): de veldtabel zocht de schrijver nog
in `serialise.py`; die zoekt nu in de opslagmodules en de gerichte herhaling gaf
20 passed (log `%TEMP%/800/step4-field.log`). Dekking 100 % regels en takken
(5942/2092), de poort meldt 41 benoemde uitsluitingen en de kaart is bijgewerkt.
De engine-probe (42), v1-probe (64) en E-probe (107) zijn byte-gelijk. De
mutatielijst was vóór deze stap 66 van 66; de ronde erna volgt vóór de push.

Stap 5 is gemeten. `hand.py` (149 regels) draagt de vier publieke methodes,
`engine/quiet.py` (190) en `engine/schedule.py` (67) zijn afgesplitst,
`engine/gates.py` ging van 623 naar 432 regels en `brakes_remaining` woont
daar; `engine/hand_start.py` is 167 regels en heeft geen luie import meer, de
binding `hand_start.py` is 267. De volledige suite gaf 3982 passed in 26m51s
(log `%TEMP%/800/step5-full3.log`), de dekking is 100 % regels en takken
(5961/2092), de poort meldt 45 benoemde uitsluitingen en de kaart is
bijgewerkt. De engine-probe (42), v1-probe (64) en E-probe (107) zijn
byte-gelijk. De mutatielijst was vóór deze stap 66 van 66 (logmap
`%TEMP%/800/mutlogs-step4`); de ronde erna volgt vóór de push. De eerste
volledige ronde van deze stap gaf 3979 passed en drie rood: zes regels zonder
naam in de dekkingspoort en twee verouderde mutatiepatronen; die zijn hersteld
en de tweede ronde is groen.

Stap 6 is gemeten. `config_flow.py` ging van 1492 naar 456 regels; de stappen
wonen in `flow_installation.py`, `flow_zones.py`, `flow_sources.py`,
`flow_circuits.py`, `flow_generators.py`, `flow_residents.py`,
`flow_windows.py` en `flow_openings.py`, de schermen in `form_common.py`,
`form_installation.py`, `form_zones.py`, `form_circuits.py`,
`form_residents.py` en `form_openings.py`, en `flow_validation.py` (380) draagt
de schermcontroles. `schemas.py` is een façade van 142 regels. De volledige
suite gaf 3997 passed in 26m57s (log `%TEMP%/800/step6-full2.log`), de dekking
is 100 % regels en takken (6133/2092), de poort meldt 63 benoemde
uitsluitingen en de kaart is bijgewerkt. De engine-probe (42), v1-probe (64)
en E-probe (107) zijn byte-gelijk. De mutatielijst was vóór deze stap 66 van
66; de ronde erna volgt vóór de push. De eerste volledige ronde stopte bij
de verzameling omdat een oud testbestand de private flowhelpers nog uit
`config_flow.py` haalde; die import is naar `flow_validation.py` verhuisd. De
typecontroleblokken in de nieuwe modules vroegen achttien benoemde
uitsluitingen; daarom staat de poort op 63 in plaats van 45.

Stap 7 is gemeten. `engine/decide.py` ging van 1800 naar 82 regels; de stappen
wonen in `candidates.py` (398), `grants.py` (361), `commands.py` (437),
`command_stops.py` (187), `command_reasons.py` (205) en `zone_decisions.py`
(238). De volledige suite gaf 4003 passed in 27m02s (log
`%TEMP%/800/step7-full2.log`), de dekking is 100 % regels en takken
(6183/2092), de poort meldt 63 benoemde uitsluitingen en de kaart is
bijgewerkt. De engine-probe (42), v1-probe (64) en E-probe (107) zijn
byte-gelijk. De mutatielijst was vóór deze stap 66 van 66; de ronde erna volgt
vóór de push. De eerste volledige ronde gaf 4000 passed en drie rood: drie
mutatiepatronen wezen nog naar `decide.py`; ze wijzen nu naar `grants.py` en
de tweede ronde is groen.

Per verhuiscommit worden hier vastgelegd:

- de twee engine-probes en de drie handstartprobes, met logpad en tijd;
- `pytest --collect-only -q`, oud → nieuw;
- dekking, poort, kaart en de mutatielijst van 66 van 66;
- `git diff --stat -M`;
- de tekstbestanden, `STORAGE_VERSION`, de `Problem`-codes en de
  `Reason`-waarden naast de basis.

---

# Progress 8.0.0 — the code-layout clean-up

This release changes no behaviour. Every step below is one commit, is pushed
only after its predecessor is green, and keeps its own proof.

## State

- **Base:** `main` at `05d59c5` (design, public names, test split, validation,
storage, hand, hand start, configuration flow and forms), clean tree,
`main == origin/main`.
- **User decisions:** N14/N15 stay **later**; N16 becomes **no** 7.7.10.
  Both stay in `ROADMAP.md` and `ARCHITECTURE.md`; 8.0.0 changes no behaviour
  and no text.
- **Production:** runs 7.7.7. Read only; nothing installed, restarted or
  changed.
- **Now:** step 7 stands in the working tree: `decide.py` is the entrance of
  82 lines, the steps live in `candidates.py`, `grants.py`, `commands.py`,
  `command_stops.py`, `command_reasons.py` and `zone_decisions.py`. Not
  committed yet.

## Steps

| Step | Commit | State |
|---|---|---|
| Design | `6df44e2` | done: `ARCHITECTURE.md` “Code layout” NL + EN |
| 1. Public names | `74f7c01` | done: mixins, helpers, schema constants and storage readers are public |
| 2. Tests per subject + impact map | `4c9f1cf` | done: 50 test files split, helpers moved, map updated |
| 3. Validation and `stored_state.py` | `79424dd` | done: `engine/validation.py` (1328 lines), `models.py` 2269 → 1154, `state_extra.py` → `stored_state.py` |
| 4. Storage and serialisation | `bb84325` (map fix `fd26bce`) | done: `serialise.py` 152 lines, three storage modules and `storage_values.py` |
| 5. Hand and hand start | `d27c3b6` | done: `hand.py`, `engine/quiet.py`, `engine/schedule.py`, `brakes_remaining` at `gates.py` |
| 6. Configuration flow and forms | `05d59c5` | done: `config_flow.py` 456, `flow_validation.py` 380, `flow_*` and `form_*` |
| 7. `engine/decide.py` | this commit | done: `decide.py` 82 lines and six subject modules |
| 8. `engine/models.py` | to be made | waits |
| 9. `coordinator.py` | to be made | waits |
| 10. `problems.py`, `texts.py`, `__init__.py` | to be made | waits |
| Release 8.0.0 | to be made | waits |

## Proof

Step 1 is measured. The engine probe (42 lines, 22:05:58) and the v1 probe
(64 lines, 22:06:13) are byte-identical on the base and the working tree. The
E probe (107 lines, 08:07:52, run in parallel), the N probe (124 lines,
10m08s) and the Q probe (139 lines, 8m07s) are all three identical.
`--collect-only` gives 3936 tests on both sides and an empty difference. The
full suite was 3935 passed and one red on the measure ratchet because longer
public names wrapped two lines; the names were shortened and the ratchet is
green again.

Step 2 is measured. The 3936 existing test names stayed identical; the
collection grew to 3977 through 38 new `test_timeless` parameters for the new
files and 3 new selection tests. The targeted round over every changed test
file gave 985 passed in 21m22s (log `%TEMP%/800/step2-maprun.log`); the source
guards gave 259 passed in 18.52s (log `%TEMP%/800/step2-final-guards.log`) and
the selection tests 73 passed in 1.76s (log `%TEMP%/800/select-final.log`). The
full suite gave 3975 passed and two red in 32m05s (log
`%TEMP%/800/step2-full.log`): the stale impact map and a missing
`Dekking`/`Coverage` paragraph in `test_reporting_live.py`; both were fixed and
then green. Coverage is 100% lines and branches (5927 lines, 2092 branches), the
gate reports 41 named exclusions, and the map is updated with the 50 test files
that ran.

Step 3 is measured. `models.py` went from 2269 to 1154 lines; the checks,
`Problem`, `validate()` and the one `RULES` list stand in `engine/validation.py`
(1328 lines); `validation_extra.py` was absorbed into that module and
`state_extra.py` is now `stored_state.py`. The engine probe (42 lines), the v1
probe (64 lines) and the E probe (107 lines) are byte-identical on the base and
the working tree. The full suite gave 3977 passed in 36m54s (log
`%TEMP%/800/step3-full.log`), coverage is 100% lines and branches (5926/2092),
the gate reports 41 named exclusions and the map is updated. The 54 `Problem`
codes equal the base. The mutation list was 66 of 66 caught before the move
(log directory `%TEMP%/800/mutlogs`, four lanes, 15m39s); the round after the
move follows before the push. Deviation: the CI mutation lane of `74f7c01` hung
for 2h22m in `Run mutations` without a single line of output and was cancelled;
that is why the list was run locally. `manual_only_problems` temporarily lives
in `validation.py` and moves to `engine/manual_sources.py` in step 8, as the
table says.

Step 4 is measured. `serialise.py` went from 637 to 152 lines; the translation
lives in `installation_storage.py` (233), `equipment_storage.py` (206) and
`resident_storage.py` (155), and `storage_helpers.py` is now
`storage_values.py` (159). The storage round gave 434 passed in 27.91s (log
`%TEMP%/800/step4-tests.log`); the full suite gave 3978 passed and one red in
34m34s (log `%TEMP%/800/step4-full.log`): the field table still looked for the
writer in `serialise.py`; it now searches the storage modules and the targeted
rerun gave 20 passed (log `%TEMP%/800/step4-field.log`). Coverage is 100% lines
and branches (5942/2092), the gate reports 41 named exclusions and the map is
updated. The engine probe (42), v1 probe (64) and E probe (107) are
byte-identical. The mutation list was 66 of 66 before this step; the round after
it follows before the push.

Step 5 is measured. `hand.py` (149 lines) carries the four public methods,
`engine/quiet.py` (190) and `engine/schedule.py` (67) are split off,
`engine/gates.py` went from 623 to 432 lines and `brakes_remaining` lives
there; `engine/hand_start.py` is 167 lines with no lazy import left, the
binding `hand_start.py` is 267. The full suite gave 3982 passed in 26m51s (log
`%TEMP%/800/step5-full3.log`), coverage is 100% lines and branches (5961/2092),
the gate reports 45 named exclusions and the map is updated. The engine probe
(42), v1 probe (64) and E probe (107) are byte-identical. The mutation list was
66 of 66 before this step (log directory `%TEMP%/800/mutlogs-step4`); the round
after it follows before the push. The first full round of this step gave 3979
passed and three red: six lines without a name in the coverage gate and two
stale mutation patterns; they were fixed and the second round is green.

Step 6 is measured. `config_flow.py` went from 1492 to 456 lines; the steps
live in `flow_installation.py`, `flow_zones.py`, `flow_sources.py`,
`flow_circuits.py`, `flow_generators.py`, `flow_residents.py`,
`flow_windows.py` and `flow_openings.py`, the screens in `form_common.py`,
`form_installation.py`, `form_zones.py`, `form_circuits.py`,
`form_residents.py` and `form_openings.py`, and `flow_validation.py` (380)
carries the screen checks. `schemas.py` is a 142-line facade. The full suite
gave 3997 passed in 26m57s (log `%TEMP%/800/step6-full2.log`), coverage is
100% lines and branches (6133/2092), the gate reports 63 named exclusions and
the map is updated. The engine probe (42), v1 probe (64) and E probe (107) are
byte-identical. The mutation list was 66 of 66 before this step; the round
after it follows before the push. The first full round stopped at collection
because an old test file still took the private flow helpers from
`config_flow.py`; that import moved to `flow_validation.py`. The type-check
blocks in the new modules asked for eighteen named exclusions, hence the gate
stands at 63 instead of 45.

Step 7 is measured. `engine/decide.py` went from 1800 to 82 lines; the steps
live in `candidates.py` (398), `grants.py` (361), `commands.py` (437),
`command_stops.py` (187), `command_reasons.py` (205) and `zone_decisions.py`
(238). The full suite gave 4003 passed in 27m02s (log
`%TEMP%/800/step7-full2.log`), coverage is 100% lines and branches
(6183/2092), the gate reports 63 named exclusions and the map is updated. The
engine probe (42), v1 probe (64) and E probe (107) are byte-identical. The
mutation list was 66 of 66 before this step; the round after it follows before
the push. The first full round gave 4000 passed and three red: three mutation
patterns still pointed at `decide.py`; they now point at `grants.py` and the
second round is green.

Per move commit the following is recorded here:

- the two engine probes and the three hand-start probes, with log path and
  time;
- `pytest --collect-only -q`, old → new;
- coverage, gate, map and the mutation list at 66 of 66;
- `git diff --stat -M`;
- the text files, `STORAGE_VERSION`, the `Problem` codes and the `Reason`
  values beside the base.
