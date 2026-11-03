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
- **Nu:** het ontwerp staat in `ARCHITECTURE.md` (NL + EN). Er is nog geen
  code verplaatst.

## Stappen

| Stap | Commit | Stand |
|---|---|---|
| Ontwerp | nog te maken | klaar in de werkboom: `ARCHITECTURE.md` “Code-indeling 8.0.0” NL + EN |
| 1. Publieke namen | nog te maken | wacht op het ontwerp |
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

Nog geen meting uitgevoerd. Per verhuiscommit worden hier vastgelegd:

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
- **Now:** the design stands in `ARCHITECTURE.md` (NL + EN). No code has been
  moved yet.

## Steps

| Step | Commit | State |
|---|---|---|
| Design | to be made | done in the working tree: `ARCHITECTURE.md` “Code layout 8.0.0” NL + EN |
| 1. Public names | to be made | waits for the design |
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

No measurement has been taken yet. Per move commit the following is recorded
here:

- the two engine probes and the three hand-start probes, with log path and
  time;
- `pytest --collect-only -q`, old → new;
- coverage, gate, map and the mutation list at 66 of 66;
- `git diff --stat -M`;
- the text files, `STORAGE_VERSION`, the `Problem` codes and the `Reason`
  values beside the base.
