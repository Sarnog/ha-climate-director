# Voortgang 7.7.9 (release B)

## NL

### Stand

- Basis: `main` op `01a0abd`, schone boom, `main == origin/main`.
- Productie draait 7.7.7. Daar is niets van deze release gemeten; alles hieronder
  is op de lokale boom en in de testomgeving gemeten.
- N14/N15 zijn **niet** gebouwd: de keuze in het bouwprompt is leeg. De vraag staat
  hieronder vast en gaat mee naar de volgende ronde.

### Openstaande vraag: N14 en N15

Het bouwprompt laat de keuze leeg:

```
Keuze: ____   (a = een handstart laat ook EVERYONE_ASLEEP en NOBODY_HOME passeren
zolang de oorzaak een onleesbare aanwezigheid is; b = een korte vasthoudtijd van de
laatst leesbare stand voor alle zones, met een ankerbesluit eerst; later = nu niet
bouwen)
```

Gemeten in de controle van 7.7.8: bij `danny-persoon` blijft de handstart staan,
maar leest het huis als slapend en gaat de airco uit (`cmds=[None, 'off', 'heat']`);
zonder handstart starten alle wachtende zones tijdens een weggevallen slaapsensor.
Optie (a) is smal en past bij N12; optie (b) raakt elke installatie en vraagt eerst
een ankerbesluit. Zonder keuze wordt geen van beide gebouwd.

### Werkwijze

- Per logisch onderdeel één commit, één push en één eigen CI-run; pas pushen na een
  groene Tests-run van de voorganger.
- Eerst een rode toets op de oude boom, daarna de bouw en de groene toets.
- Elke nieuwe `Problem`-code in de zeven tekstbestanden en de zes gidsen.
- Docs NL + EN en de zes gidsen samen; geen versienummers of datums in
  `ROADMAP.md`, `ARCHITECTURE.md` of de gidsen.

### Voortgang per punt

| punt | stand | bewijs |
|---|---|---|
| C. hygiëne `_unreadable` en `_restore_hand_starts` | gebouwd | `readability.py`; 322 gerichte toetsen groen (`/tmp/779/C-focused.log`); ruff en mypy groen (`/tmp/779/C-lint.log`) |
| A. N13 en het leesbaarheidsmodel | gebouwd | model in `WorldState.unreadable`; 185 handstarttoetsen groen; probe n7 oud `hand_starts=[]`/`cmds=[None,'off']`, nieuw `hand_starts=['woonkamer']`/`cmds=[None]` (`/tmp/779/A-probe-n7-old.log`, `/tmp/779/A-probe-n7-new.log`) |
| D. L1-L12 en P2 | nog niet begonnen | - |
| E. beschrijving | nog niet begonnen | - |
| release 7.7.9 | nog niet begonnen | - |

C: `unreadable()` staat nu publiek in `readability.py`; `world_builder.py` groeide
niet en daalde van 573 naar 559 regels. `state_store.py` roept
`_restore_hand_starts` gewoon aan. Het ROADMAP-idee over privé hulpjes is weg.
De volledige `script/test`-selectie van 59 bestanden is lokaal niet uitgelopen
(bij 29% gestopt wegens de looptijd); de CI meet die selectie.

A: de drie remmen lezen nu één verzameling onleesbare invoeren
(`ReadableInput.PRESENCE`, `SLEEP`, `HOLIDAY`) in `WorldState.unreadable`. De
koppelingslaag vult die in `readability.py`; `brakes_readable` leest haar. De
invoerentabel staat in ARCHITECTURE (NL + EN). `world_builder.py` daalde verder
naar 553 regels. Rode proef: n7 op de oude boom viel terug op `hand_starts=[]`
en `cmds=[None, 'off']`; op de nieuwe boom bleef de handstart staan en kwam er
geen `off`. De mutatie "agenda telt als leesbaar" volgt in de mutatieronde.

## EN

### State

- Base: `main` at `01a0abd`, clean tree, `main == origin/main`.
- Production runs 7.7.7. Nothing from this release has been measured there;
  everything below is measured on the local tree and in the test environment.
- N14/N15 are **not** built: the choice in the build prompt is blank. The question
  is recorded below and travels to the next round.

### Open question: N14 and N15

The build prompt leaves the choice blank:

```
Choice: ____   (a = a hand start also passes EVERYONE_ASLEEP and NOBODY_HOME while
the cause is an unreadable presence; b = a short hold of the last readable reading
for all zones, with an anchor decision first; later = do not build now)
```

Measured in the 7.7.8 control: with `danny-persoon` the hand start stays, but the
house reads as asleep and the air conditioner goes off
(`cmds=[None, 'off', 'heat']`); without a hand start every waiting zone starts
during a dropped sleep sensor. Option (a) is narrow and fits N12; option (b)
touches every installation and needs an anchor decision first. Without a choice
neither is built.

### Working method

- One commit, one push and one own CI run per logical part; push only after a green
  Tests run of the predecessor.
- First a red test on the old tree, then the build and the green test.
- Every new `Problem` code in the seven text files and the six guides.
- Docs NL + EN and the six guides together; no version numbers or dates in
  `ROADMAP.md`, `ARCHITECTURE.md` or the guides.

### Progress per point

| point | state | evidence |
|---|---|---|
| C. hygiene `_unreadable` and `_restore_hand_starts` | built | `readability.py`; 322 focused tests green (`/tmp/779/C-focused.log`); ruff and mypy green (`/tmp/779/C-lint.log`) |
| A. N13 and the readability model | built | model in `WorldState.unreadable`; 185 hand-start tests green; probe n7 old `hand_starts=[]`/`cmds=[None,'off']`, new `hand_starts=['woonkamer']`/`cmds=[None]` (`/tmp/779/A-probe-n7-old.log`, `/tmp/779/A-probe-n7-new.log`) |
| D. L1-L12 and P2 | not started | - |
| E. description | not started | - |
| release 7.7.9 | not started | - |

C: `unreadable()` now lives publicly in `readability.py`; `world_builder.py` did
not grow and fell from 573 to 559 lines. `state_store.py` calls
`_restore_hand_starts` directly. The ROADMAP idea about private helpers is gone.
The full `script/test` selection of 59 files did not finish locally (stopped at
29% because of the running time); CI measures that selection.

A: the three brakes now read one collection of unreadable inputs
(`ReadableInput.PRESENCE`, `SLEEP`, `HOLIDAY`) in `WorldState.unreadable`. The
binding layer fills it in `readability.py`; `brakes_readable` reads it. The input
table stands in ARCHITECTURE (NL + EN). `world_builder.py` fell further to 553
lines. Red proof: n7 on the old tree fell back to `hand_starts=[]` and
`cmds=[None, 'off']`; on the new tree the hand start stayed and no `off` came.
The mutation "calendar counts as readable" follows in the mutation round.
