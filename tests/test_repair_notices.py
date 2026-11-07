"""Elke reparatiemelding verdwijnt bij het uitladen van de installatie.

Every repair notice disappears when the installation unloads.

Een functie als `problems.async_clear_bypassed_openings` kan bestaan zonder dat
iets hem aanroept. Dan wordt die melding bij het uitladen niet opgeruimd - een
overbruggingsmelding blijft staan nadat de entry weg is - en is de functie
ernaast dode code die precies dat gat markeert.

De vorige bewaking hing aan de **naam** van de fabriek (`async_report_*` in
`problems.py`). Gemeten: een melding die je onder een andere naam
opzet (`async_note_probe`, of dezelfde aanroep in `state_store.py`) glipte er
langs - de unload-bewaking bleef groen. Daarom loopt deze test nu met een AST
over **álle** `ir.async_create_issue`-aanroepen in het hele pakket, haalt het
issue-id-hulpje eruit (`_issue_id(entry_id)`, of een moduleconstante zoals
`UNWATCHED_ISSUE`), en eist dat `async_unload_entry` - direct of via een functie
die het aanroept - een `ir.async_delete_issue` op **datzelfde** hulpje bereikt.
Zo hangt de bewaking aan de eigenschap en niet aan hoe een melding heet of in
welk bestand hij woont.

Een id dat de bewaking niet kán volgen - een f-string, een samenvoeging, een
variabele - zou **stil overgeslagen** worden, en zo'n melding zou dan zonder
één woord uit de controle vallen. Dat is een fout met bestand en regelnummer
(`_refuse_unfollowable`), dezelfde regel als voor een berekende
`translation_key`. Volgbaar is: een hulpje (`_issue_id(entry_id)`),
een moduleconstante die op moduleniveau een letterlijke string krijgt
(`UNWATCHED_ISSUE`), of een letterlijke string. Al het andere meldt zich.

`UNWATCHED_ISSUE` is de bewuste uitzondering: dat is één melding voor de hele
integratie in plaats van één per installatie, dus hij gaat pas weg als de laatste
installatie verdwijnt (`async_clear_watchers`, en die is wel vanuit
`async_unload_entry` bereikbaar). De bewaking eist daarom ook van die melding dat
er een bereikbare delete is, maar niet dat hij bij élke unload verdwijnt.

A function such as `problems.async_clear_bypassed_openings` can exist while
nothing calls it. Then that notice is not cleaned up on unload - a bypass
notice stays behind after the entry is gone - and the function next to it is
dead code marking exactly that gap.

The previous guard hung on the **name** of the factory (`async_report_*` in
`problems.py`). Measured: a notice set up under another name
(`async_note_probe`, or the same call in `state_store.py`) slipped past it - the
unload guard stayed green. This test therefore walks **every**
`ir.async_create_issue` call in the whole package with an AST, pulls the issue-id
helper out of it (`_issue_id(entry_id)`, or a module constant such as
`UNWATCHED_ISSUE`), and demands that `async_unload_entry` - directly or through a
function it calls - reaches an `ir.async_delete_issue` on **that same** helper.
That way the guard hangs on the property, not on what a notice is called or which
file it lives in.

An id the guard **cannot** follow - an f-string, a concatenation, a variable -
would be **silently skipped**, and such a notice would drop out of the check
without a word. That is an error with file and line number
(`_refuse_unfollowable`), the same rule as for a computed `translation_key`.
Followable is: a helper (`_issue_id(entry_id)`), a
module constant that gets a literal string at module level (`UNWATCHED_ISSUE`),
or a literal string. Anything else reports itself.

`UNWATCHED_ISSUE` is the deliberate exception: it is one notice for the whole
integration rather than one per installation, so it only goes when the last
installation does (`async_clear_watchers`, which is reachable from
`async_unload_entry`). The guard therefore demands a reachable delete for it too,
but not that it disappears on every unload.

De match zelf woont in `tests/_ast_helpers.py`. Vier lezers
in de testset gebruiken daar dezelfde definitie — attribuut én kale naam, met
opgeloste import-aliassen — in plaats van vier keer hun eigen
`ast.Attribute`-variant.

The match itself lives in `tests/_ast_helpers.py`. Four
readers in the suite use the same definition there — attribute and bare name,
with resolved import aliases — instead of four of their own `ast.Attribute`
variants.

De match kent geen aanroep onder een eigen naam
(`_create = ir.async_create_issue`), en een derde spelling in de helper zou
alleen de vólgende spelling openlaten. Daarom staat er een
**structurele afspraak** naast: `test_the_issue_registry_is_only_used_as_ir` eist
dat `issue_registry` alleen als `ir` geïmporteerd en alleen rechtstreeks
aangeroepen wordt — geen alias, geen `functools.partial`, geen callback, geen
`getattr`. De runtime-kant staat in `tests/test_repair_notices_live.py`, dat de
échte meldingsfuncties omhult en geen enkele regel bron leest.

The match does not know a call under its own name
(`_create = ir.async_create_issue`), and a third spelling in the helper would
only leave the *next* spelling open. Hence a **structural agreement** stands
beside it: `test_the_issue_registry_is_only_used_as_ir` demands
that `issue_registry` is imported only as `ir` and called only directly — no
alias, no `functools.partial`, no callback, no `getattr`. The runtime side lives
in `tests/test_repair_notices_live.py`, which wraps the real notice functions and
reads no source line.
"""

from __future__ import annotations

from repair_helpers import (
    cleared_at_unload,
    created_issue_ids,
    created_issue_origins,
    functions_called_by,
    issue_registry_form_problems,
    unfollowable_issue_ids,
)


def test_every_created_notice_is_cleared_when_the_entry_unloads() -> None:
    """Bij het uitladen verdwijnt élke melding van deze installatie.

    On unload every notice of this installation disappears.
    """
    created = created_issue_ids()
    cleared = cleared_at_unload()

    assert created, "geen enkele `async_create_issue` gevonden; de AST leest het verkeerde pakket"
    assert "async_unload_entry" in functions_called_by(), (
        "`async_unload_entry` niet gevonden; de AST leest `__init__.py` niet"
    )

    missing = sorted(created - cleared)
    origins = created_issue_origins()
    detail = ", ".join(f"{name} ({origins.get(name, '?')})" for name in missing)
    assert not missing, (
        "deze meldingen worden aangemaakt maar op het uitlaadpad van "
        "`async_unload_entry` niet meer gewist, dus ze overleven het uitladen: " + detail
    )


def test_the_guard_reads_the_real_source() -> None:
    """De bewaking hangt aan de bron en niet aan een lijst hier.

    The guard hangs on the source, not on a list here.
    """
    created = created_issue_ids()
    cleared = cleared_at_unload()

    # De meldingen van vandaag, in beide vormen: een hulpje per installatie en
    # de ene constante voor de hele integratie.
    #
    # Today's notices, in both forms: a per-installation helper and the single
    # whole-integration constant.
    assert "bypassed_opening_issue_id" in created
    assert "UNWATCHED_ISSUE" in created

    # Elk gevonden hulpje wordt op het uitlaadpad ook werkelijk gewist.
    #
    # Every helper found is really cleared on the unload path.
    assert created <= cleared


def test_every_issue_id_can_be_followed() -> None:
    """Elke melding heeft een id dat de bewaking kan volgen.

    Een id dat ze niet kan volgen zou **stil overgeslagen** worden, en dan
    valt zo'n melding zonder één woord uit de unload-controle. Deze test is de
    expliciete kant daarvan; de twee verzamelfuncties weigeren zo'n id ook zelf.

    Every notice has an id the guard can follow. An id it could not follow
    would be **silently skipped**, and then such a notice
    dropped out of the unload check without a word. This test is the explicit
    side of that; the two collector functions refuse such an id themselves too.
    """
    offenders = unfollowable_issue_ids()
    assert not offenders, (
        "deze meldingen gebruiken een issue-id dat de bewaking niet kan volgen en "
        "vallen dus stil buiten de unload-controle: " + "; ".join(offenders)
    )


def test_the_issue_registry_is_only_used_as_ir() -> None:
    """De enige bestaande schrijfwijze is ook de enige die de bewaking dekt.

    De meldingsbewaking hierboven leest de bron, dus elke vorm die ze niet kent
    is een gat. In plaats van een derde spelling aan `_ast_helpers` toe te
    voegen — waardoor de volgende spelling de volgende ronde wordt — legt deze
    afspraak vast dat `issue_registry` alleen als `ir` geïmporteerd wordt en
    alleen rechtstreeks aangeroepen. Dan bestaat de rand niet meer, en de
    runtime-kant staat in `tests/test_repair_notices_live.py`: daar worden de
    échte meldingsfuncties omhuld en moet elke melding die een huis aanmaakt bij
    het uitladen ook weer gewist zijn — zonder één regel bron te lezen.

    The only existing spelling is also the only one the guard covers.
    The notice guard above reads the source, so every shape it does not know is a
    gap. Instead of adding a third spelling to `_ast_helpers` — which would make
    the next spelling the next round — this agreement pins down that
    `issue_registry` is imported only as `ir` and called only directly. Then the
    edge no longer exists, and the runtime side stands in
    `tests/test_repair_notices_live.py`: there the real notice functions are
    wrapped and every notice a house raises must be cleared again on unload —
    without reading a single source line.
    """
    problems = issue_registry_form_problems()
    assert problems == [], (
        "deze schrijfwijzen halen een meldingsaanroep uit de vorm die de bewaking "
        "hierboven leest, en dan is die bewaking stil groen over een melding die ze "
        "niet ziet:\n" + "\n".join(problems)
    )
