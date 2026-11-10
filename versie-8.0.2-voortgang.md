# Voortgang 8.0.2 / Progress 8.0.2

## NL

Deze release maakt de open punten van de opruimronde af. De verhuizingen
veranderen geen gedrag; alleen de twee gedragsbesluiten aan het eind doen dat.
Elke stap is één commit, wordt pas gepusht als de voorganger groen is, en houdt
zijn eigen bewijs bij.

### Stand

- **Basis:** `main` op `9f7198c` (de tag `v8.0.1` plus de controlecommits).
- **Gebruikersbesluiten:** de geweigerde winnaar van een gebied blijft zoals het
  is (alleen vastgelegd); een bron zonder `autostart` buiten een groep met de
  ketel krijgt een melding van `validate()`; een ketel in meer dan één zone
  zonder `covers_zones` krijgt een melding van `validate()`. N14, N15 en N16
  blijven later.
- **Productie:** draait 7.7.9; alleen gelezen, niets geïnstalleerd, herstart of
  gewijzigd.
- **Bewijs op de basis** (probes op een worktree van `9f7198c`, uitvoer in
  `%TEMP%/claude/…/scratchpad/logs/base`): engine 42 regels, v1 64 regels,
  gebied 66 regels, E 107 regels; N en Q volgen.

### Stappen

| Stap | Commit | Stand |
|---|---|---|
| Ontwerp | zie `git log` | `ARCHITECTURE.md` “Verdere indeling” NL + EN |
| 1. Geen `getattr`-terugval | | |
| 2. Geen kring texts / problems | | |
| 3. Impactkaart samenvoegen | | |
| 4. `circuit_requests`, `circuit_policy`, `capacity` | | |
| 5. Validatie per onderwerp | | |
| 6. Een protocol per laag | | |
| 7. Onderdelen zonder privé attributen | | |
| 8. Mutaties op `area_clash` in `script/` | | |
| 9. Twee gedragsbesluiten | | |
| Documenten | | |
| Release | | |

## EN

This release finishes the open points of the clean-up. The moves change no
behaviour; only the two behaviour decisions at the end do. Every step is one
commit, is pushed only when its predecessor is green, and keeps its own proof.

### State

- **Base:** `main` at `9f7198c` (the `v8.0.1` tag plus the review commits).
- **User decisions:** the refused winner of an area stays as it is (only
  recorded); a source without `autostart` outside a group with the boiler gets
  a `validate()` notice; a boiler in more than one zone without `covers_zones`
  gets a `validate()` notice. N14, N15 and N16 stay later.
- **Production:** runs 7.7.9; read only, nothing installed, restarted or changed.

### Steps

| Step | Commit | State |
|---|---|---|
| Design | see `git log` | `ARCHITECTURE.md` “Further layout” NL + EN |
| 1. No `getattr` fallback | | |
| 2. No texts / problems cycle | | |
| 3. Impact map merge | | |
| 4. `circuit_requests`, `circuit_policy`, `capacity` | | |
| 5. Validation per subject | | |
| 6. A protocol per layer | | |
| 7. Parts without private attributes | | |
| 8. `area_clash` mutations in `script/` | | |
| 9. Two behaviour decisions | | |
| Documents | | |
| Release | | |
