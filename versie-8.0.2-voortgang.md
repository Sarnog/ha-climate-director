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
  gewijzigd. Niets van deze release is in productie gemeten.
- **Bewijs:** de engine-, v1- en gebiedsprobe zijn op elke stap byte-gelijk met
  de basis; de E-, N- en Q-probes zijn identiek wanneer basis en werkboom
  tegelijk draaien (de E-reeks hangt van de klok af en week eenmaal af onder
  belasting, niet bij een herhaling zonder belasting).

### Stappen

| Stap | Commit | Stand |
|---|---|---|
| Ontwerp | `f52ab43` | `ARCHITECTURE.md` “Verdere indeling” NL + EN |
| 1. Geen `getattr`-terugval | `376af1d` (kaartherstel `941048c`) | klaar |
| 2. Geen kring texts / problems, bewaking E402 | `15ed638` | klaar |
| 3. Impactkaart samenvoegen | `4b0d3e1` | klaar |
| 4. `circuit_requests`, `circuit_policy`, `capacity` | `40ba0e8` | klaar |
| 5. Validatie per onderwerp | `7844dd7` | klaar |
| 6. Een oppervlak per laag | `41419cd` | klaar, poort van 75 naar 10 |
| 7a. Publieke namen van wat een mixin bezit | `dc15fd0` | klaar |
| 7b. Staatsklassen per onderdeel | `b9bb66b` | klaar, poort 0 |
| 8. Gebiedstoetsen, mutaties op `area_clash`, lijst in `script/` | `73e863e`, `6eb865c` | klaar |
| 9a. Melding bron zonder automatische start | `e7746d7` (kaartherstel `967cd69`) | klaar |
| 9b. Melding ketel zonder gebied | `e333769` | klaar |
| Documenten | zie `git log` | klaar |
| Release | zie `git log` | zie de release notes |

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
  Nothing of this release has been measured in production.
- **Proof:** the engine, v1 and area probes are byte-identical with the base at
  every step; the E, N and Q probes are identical when base and working tree run
  at the same time (the E series depends on the clock and differed once under
  load, not on a repeat without load).

### Steps

| Step | Commit | State |
|---|---|---|
| Design | `f52ab43` | `ARCHITECTURE.md` “Further layout” NL + EN |
| 1. No `getattr` fallback | `376af1d` (map repair `941048c`) | done |
| 2. No texts / problems cycle, E402 guard | `15ed638` | done |
| 3. Impact map merge | `4b0d3e1` | done |
| 4. `circuit_requests`, `circuit_policy`, `capacity` | `40ba0e8` | done |
| 5. Validation per subject | `7844dd7` | done |
| 6. A surface per layer | `41419cd` | done, gate from 75 to 10 |
| 7a. Public names for what a mixin owns | `dc15fd0` | done |
| 7b. State classes per part | `b9bb66b` | done, gate 0 |
| 8. Area tests, mutations on `area_clash`, list in `script/` | `73e863e`, `6eb865c` | done |
| 9a. Notice for a source without automatic start | `e7746d7` (map repair `967cd69`) | done |
| 9b. Notice for a boiler without an area | `e333769` | done |
| Documents | see `git log` | done |
| Release | see `git log` | see the release notes |
