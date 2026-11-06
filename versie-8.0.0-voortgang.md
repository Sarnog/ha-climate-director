# Voortgang 8.0.0 — de opruimronde van de code-indeling

Deze release verandert geen gedrag. Elke stap hieronder is één commit, wordt
pas gepusht als de voorganger groen is, en houdt zijn eigen bewijs bij.

## Stand

- **Basis:** `main` op `79424dd` (ontwerp, publieke namen, toetssplitsing en
validatie), schone boom, `main == origin/main`.
- **Gebruikersbesluiten:** N14/N15 blijven **later**; N16 wordt **geen**
  7.7.10. Beide blijven in `ROADMAP.md` en `ARCHITECTURE.md` staan; 8.0.0
  verandert geen gedrag en geen tekst.
- **Productie:** draait 7.7.7. Alleen gelezen; niets geïnstalleerd, herstart of
  gewijzigd.
- **Nu:** stap 4 staat in de werkboom: `serialise.py` is de ingang, de
  vertaling woont in `installation_storage.py`, `equipment_storage.py`,
  `resident_storage.py` en `storage_values.py`. Nog niet gecommit.

## Stappen

| Stap | Commit | Stand |
|---|---|---|
| Ontwerp | `6df44e2` | klaar: `ARCHITECTURE.md` “Code-indeling” NL + EN |
| 1. Publieke namen | `74f7c01` | klaar: mixins, helpers, schemaconstanten en opslaglezers zijn publiek |
| 2. Toetsen per onderwerp + impactkaart | `4c9f1cf` | klaar: 50 toetsbestanden verdeeld, hulpjes verhuisd, kaart bijgewerkt |
| 3. Validatie en `stored_state.py` | deze commit | klaar: `engine/validation.py` (1328 regels), `models.py` 2269 → 1154, `state_extra.py` → `stored_state.py` |
| 4. Opslag en serialisatie | deze commit | klaar: `serialise.py` 152 regels, drie opslagmodules en `storage_values.py` |
| 5. Hand en handstart | nog te maken | wacht |
| 6. Configuratiestroom en formulieren | nog te maken | wacht |
| 7. `engine/decide.py` | nog te maken | wacht |
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

- **Base:** `main` at `79424dd` (design, public names, test split and
validation), clean tree, `main == origin/main`.
- **User decisions:** N14/N15 stay **later**; N16 becomes **no** 7.7.10.
  Both stay in `ROADMAP.md` and `ARCHITECTURE.md`; 8.0.0 changes no behaviour
  and no text.
- **Production:** runs 7.7.7. Read only; nothing installed, restarted or
  changed.
- **Now:** step 4 stands in the working tree: `serialise.py` is the entrance, the
  translation lives in `installation_storage.py`, `equipment_storage.py`,
  `resident_storage.py` and `storage_values.py`. Not committed yet.

## Steps

| Step | Commit | State |
|---|---|---|
| Design | `6df44e2` | done: `ARCHITECTURE.md` “Code layout” NL + EN |
| 1. Public names | `74f7c01` | done: mixins, helpers, schema constants and storage readers are public |
| 2. Tests per subject + impact map | `4c9f1cf` | done: 50 test files split, helpers moved, map updated |
| 3. Validation and `stored_state.py` | this commit | done: `engine/validation.py` (1328 lines), `models.py` 2269 → 1154, `state_extra.py` → `stored_state.py` |
| 4. Storage and serialisation | this commit | done: `serialise.py` 152 lines, three storage modules and `storage_values.py` |
| 5. Hand and hand start | to be made | waits |
| 6. Configuration flow and forms | to be made | waits |
| 7. `engine/decide.py` | to be made | waits |
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

Per move commit the following is recorded here:

- the two engine probes and the three hand-start probes, with log path and
  time;
- `pytest --collect-only -q`, old → new;
- coverage, gate, map and the mutation list at 66 of 66;
- `git diff --stat -M`;
- the text files, `STORAGE_VERSION`, the `Problem` codes and the `Reason`
  values beside the base.
