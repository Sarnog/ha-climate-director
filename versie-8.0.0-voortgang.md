# Voortgang 8.0.0 — de opruimronde van de code-indeling

Deze release verandert geen gedrag. Elke stap hieronder is één commit, wordt
pas gepusht als de voorganger groen is, en houdt zijn eigen bewijs bij.

## Stand

- **Basis:** `main` op `a5957a5` (tag `v7.7.9` op `a69bf76` plus de
  controlecommits van 2026-11-02), schone boom, `main == origin/main`.
- **Gebruikersbesluiten:** N14/N15 blijven **later**; N16 wordt **geen**
  7.7.10. Beide blijven in `ROADMAP.md` en `ARCHITECTURE.md` staan; 8.0.0
  verandert geen gedrag en geen tekst.
- **Productie:** draait 7.7.7. Alleen gelezen; niets geïnstalleerd, herstart of
  gewijzigd.
- **Nu:** het ontwerp is gecommit; de publieke namen zijn in de werkboom
  hernoemd en wachten op hun eigen commit en push. Er is nog geen bestand
  verplaatst.

## Stappen

| Stap | Commit | Stand |
|---|---|---|
| Ontwerp | `6df44e2` | klaar: `ARCHITECTURE.md` “Code-indeling” NL + EN |
| 1. Publieke namen | nog te maken | klaar in de werkboom: de mixins, de helpers, de schemaconstanten en de opslaglezers zijn publiek; nog niet gecommit |
| 2. Toetsen per onderwerp + impactkaart | nog te maken | wacht |
| 3. Validatie en `stored_state.py` | nog te maken | wacht |
| 4. Opslag en serialisatie | nog te maken | wacht |
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
groen. Per verhuiscommit worden hier vastgelegd:

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

- **Base:** `main` at `a5957a5` (tag `v7.7.9` at `a69bf76` plus the control
  commits of 2026-11-02), clean tree, `main == origin/main`.
- **User decisions:** N14/N15 stay **later**; N16 becomes **no** 7.7.10.
  Both stay in `ROADMAP.md` and `ARCHITECTURE.md`; 8.0.0 changes no behaviour
  and no text.
- **Production:** runs 7.7.7. Read only; nothing installed, restarted or
  changed.
- **Now:** the design is committed; the public names are renamed in the
  working tree and wait for their own commit and push. No file has been moved
  yet.

## Steps

| Step | Commit | State |
|---|---|---|
| Design | `6df44e2` | done: `ARCHITECTURE.md` “Code layout” NL + EN |
| 1. Public names | to be made | done in the working tree: the mixins, helpers, schema constants and storage readers are public; not committed yet |
| 2. Tests per subject + impact map | to be made | waits |
| 3. Validation and `stored_state.py` | to be made | waits |
| 4. Storage and serialisation | to be made | waits |
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
green again. Per move commit the following is recorded here:

- the two engine probes and the three hand-start probes, with log path and
  time;
- `pytest --collect-only -q`, old → new;
- coverage, gate, map and the mutation list at 66 of 66;
- `git diff --stat -M`;
- the text files, `STORAGE_VERSION`, the `Problem` codes and the `Reason`
  values beside the base.
