"""Elke melding van het pakket wordt in een echt huis aangemaakt en weer gewist.

Every notice of the package is raised in a real house and cleared again on unload.

De bewaking in `test_repair_notices.py` leest de **bron**: hij zoekt elke
`async_create_issue`-aanroep en eist dat het uitlaadpad een `async_delete_issue`
op hetzelfde id bereikt. Dat is een bewaking op de vorm, en sinds ronde 36
(R36-1) staat daar de structurele afspraak naast dat `issue_registry` alleen als
`ir` geïmporteerd en alleen direct aangeroepen wordt. Deze test doet het
omgekeerde: hij leest **geen enkele regel bron**, maar omhult de échte
`ir.async_create_issue` en `ir.async_delete_issue` op moduleniveau en laat een
paar echte huizen elke melding van het pakket minstens één keer aanmaken. Daarna
laadt elk huis uit, en elk aangemaakt id moet ook gewist zijn.

Elke melding van het pakket telt mee: de negen die er vandaag zijn, in één huis
per situatie — een fout in de configuratie en een handbediend-only taak, een
onleesbare sensor met een bron die een onmogelijke stand vraagt, een seizoen dat
een taak uitsluit, een overbrugde open deur, een apparaat dat zijn commando niet
aanneemt, een onleesbare opslag, en de luistermelding. De verzameling die de
AST-inventarisatie van `test_repair_notices.py` kent is de maat: komt er een
melding bij, dan is deze test rood totdat het live-scenario hem ook aanmaakt.

The guard in `test_repair_notices.py` reads the **source**: it looks for every
`async_create_issue` call and demands that the unload path reaches an
`async_delete_issue` on the same id. That is a guard on the form, and since round
36 (R36-1) a structural agreement stands beside it: `issue_registry` is imported
only as `ir` and called only directly. This test does the opposite: it reads **no
source line at all**, but wraps the real `ir.async_create_issue` and
`ir.async_delete_issue` at module level and lets a few real houses raise every
notice of the package at least once. Then each house unloads, and every id raised
must also be cleared.

Every notice of the package counts: today's nine, in one house per situation — a
mistake in the configuration and a hand-operated-only duty, an unreadable sensor
with a source asking an impossible mode, a season that locks a duty out, a
bypassed open door, an appliance that does not take its command, an unreadable
store, and the listener notice. The set the AST inventory of
`test_repair_notices.py` knows is the yardstick: when a notice is added, this
test is red until the live scenario raises it too.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from harness_live import LiveHome, settings, source, start_house, stop_house, zone
from homeassistant.core import ServiceCall
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from custom_components.climate_director import coordinator as coordinator_module
from custom_components.climate_director import problems

LIVING = "climate.woonkamer"
SPARE = "climate.woonkamer_reserve"
ATTIC = "climate.zolder"
HAND = "climate.handbediend"
BACK_DOOR = "binary_sensor.achterdeur"


def _wrap(monkeypatch: pytest.MonkeyPatch) -> tuple[set[str], set[str]]:
    """Omhul de échte meldingsfuncties; houd bij wat aangemaakt en gewist wordt.

    Wrap the real notice functions; record what is raised and cleared.
    """
    created: set[str] = set()
    cleared: set[str] = set()
    real_create = ir.async_create_issue
    real_delete = ir.async_delete_issue

    def create(hass, domain, issue_id, **kwargs):
        created.add(issue_id)
        return real_create(hass, domain, issue_id, **kwargs)

    def delete(hass, domain, issue_id):
        cleared.add(issue_id)
        return real_delete(hass, domain, issue_id)

    monkeypatch.setattr(ir, "async_create_issue", create)
    monkeypatch.setattr(ir, "async_delete_issue", delete)
    return created, cleared


async def _age(home: LiveHome, minutes: float) -> None:
    """Laat de coordinator geloven dat er tijd voorbij is, en beslis opnieuw.

    Let the coordinator believe time has passed, and decide again.
    """
    moved = dt_util.now() + timedelta(minutes=minutes)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(coordinator_module.dt_util, "now", lambda: moved)
        await home.evaluate()


async def _rounds(home: LiveHome, count: int) -> None:
    """Beslis `count` keer, telkens een minuut later — de vangnetklok.

    Decide `count` times, each a minute later — the safety-net clock.
    """
    start = dt_util.now()
    for step in range(1, count + 1):
        moved = start + timedelta(minutes=step)
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(coordinator_module.dt_util, "now", lambda moved=moved: moved)
            await home.evaluate()


def _go_deaf(home: LiveHome) -> None:
    """Laat het apparaat elke aanroep aannemen en niets uitvoeren.

    Let the appliance accept every call and carry out none of them.
    """

    async def swallow(call: ServiceCall) -> None:
        home.calls.append((call.service, dict(call.data)))

    home.hass.services.async_register("climate", "set_hvac_mode", swallow)
    home.hass.services.async_register("climate", "set_temperature", swallow)


async def _a_configuration_mistake_and_a_hand_operated_duty() -> None:
    """Een fout in de configuratie, een handbediende taak en de luistermelding.

    A mistake in the configuration, a hand-operated duty and the listener notice.

    Zonder recorder op de bus: de luistermelding gaat juist over het ontbreken
    van een luisteraar, dus dit huis luistert zelf nergens naar.

    Without a recorder on the bus: the listener notice is exactly about a missing
    listener, so this house listens to nothing itself.
    """
    installation = {
        "zones": [
            zone(
                "handbediend",
                sources=[source("hand", HAND, autostart=False)],
                heat=settings(21.0, 20.0),
            ),
            zone("zonder_bron", sources=[]),
        ],
    }
    states = {
        "sensor.handbediend": ("18.0", {}),
        HAND: ("off", {"hvac_modes": ["heat", "off"]}),
    }
    home = await start_house(installation, states=states, entry_id="fouten", watch_events=False)
    try:
        await home.evaluate()
    finally:
        await stop_house(home)


async def _unreadable_unsupported_season_and_bypass() -> None:
    """Vier meldingen in één huis, elk met zijn eigen oorzaak.

    Four notices in one house, each with its own cause.
    """
    installation = {
        "zones": [
            zone(
                "koelzone",
                sources=[source("koelbron", SPARE, role="heat_cool")],
                indoor_sensor="sensor.koelzone",
                cool=settings(22.0, 24.0, seasons=["summer"]),
                heat=settings(21.0, 18.0),
            )
        ],
        "outdoor_sensor": "sensor.buiten",
        "seasons": {"source": "summer"},
        "openings": [
            {
                "entity_id": BACK_DOOR,
                "opening_id": "achterdeur",
                "name": "Achterdeur",
                "zone_ids": ["koelzone"],
                "open_state": "on",
                "delay": 0,
            }
        ],
    }
    states = {
        "sensor.koelzone": ("unavailable", {}),
        "sensor.buiten": ("4.0", {}),
        SPARE: ("off", {"hvac_modes": ["heat", "off"]}),
        BACK_DOOR: ("on", {}),
    }
    home = await start_house(installation, states=states, entry_id="onleesbaar")
    try:
        # De onleesbare sensor en de onmogelijke stand hebben allebei hun wachttijd.
        await _age(home, 10)
        # De overbrugging staat aan terwijl de deur werkelijk openstaat.
        await home.call(
            "switch", "turn_on", {"entity_id": home.by_key("opening_achterdeur_bypass")}
        )
        await home.evaluate()
        # De seizoensselect op een seizoen dat de koeltaak uitsluit.
        await home.call(
            "select",
            "select_option",
            {"entity_id": home.by_key("season"), "option": "winter"},
        )
        await home.evaluate()
    finally:
        await stop_house(home)


async def _an_appliance_that_never_takes_its_command() -> None:
    """Een apparaat dat de aanroep aanneemt en niets doet.

    An appliance that accepts the call and does nothing.
    """
    installation = {
        "zones": [
            zone(
                "zolder",
                sources=[source("zolderketel", ATTIC)],
                indoor_sensor="sensor.zolder",
                heat=settings(21.0, 20.0),
            )
        ],
        "outdoor_sensor": "sensor.buiten",
    }
    states = {
        "sensor.zolder": ("22.0", {}),
        "sensor.buiten": ("4.0", {}),
        ATTIC: ("off", {"hvac_modes": ["heat", "off"]}),
    }
    home = await start_house(installation, states=states, entry_id="doof")
    try:
        _go_deaf(home)
        home.set("sensor.zolder", "18.0")
        await _rounds(home, 12)
    finally:
        await stop_house(home)


async def _an_unreadable_store() -> None:
    """Een opslagbestand dat niet te lezen is.

    A state file that cannot be read.
    """
    original = Store.async_load

    async def unreadable(store) -> Any:
        if store.key.startswith("climate_director"):
            raise OSError("onleesbaar")
        return await original(store)

    installation = {
        "zones": [
            zone("woonkamer", sources=[source("ketel", LIVING)], heat=settings(21.0, 20.0)),
        ],
    }
    states = {"sensor.woonkamer": ("18.0", {}), LIVING: ("off", {})}
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Store, "async_load", unreadable)
        home = await start_house(installation, states=states, entry_id="opslag")
        try:
            await home.evaluate()
        finally:
            await stop_house(home)


class TestEveryNoticeIsRaisedLiveAndClearedAtUnload:
    """Het runtime-net onder de meldingsbewaking (ronde 36, R36-1).

    The runtime net under the notice guard (round 36, R36-1).
    """

    async def test_every_notice_is_raised_live_and_cleared_at_unload(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from test_repair_notices import created_issue_ids

        created, cleared = _wrap(monkeypatch)

        await _a_configuration_mistake_and_a_hand_operated_duty()
        await _unreadable_unsupported_season_and_bypass()
        await _an_appliance_that_never_takes_its_command()
        await _an_unreadable_store()

        expected = {
            problems._issue_id("fouten"),
            problems._manual_issue_id("fouten"),
            problems.UNWATCHED_ISSUE,
            problems._unreadable_issue_id("onleesbaar"),
            problems._unsupported_modes_issue_id("onleesbaar"),
            problems._season_excludes_mode_issue_id("onleesbaar"),
            problems._bypassed_opening_issue_id("onleesbaar"),
            problems._command_not_taking_issue_id("doof"),
            problems._corrupt_storage_issue_id("opslag"),
        }

        known = created_issue_ids()
        assert len(known) == len(expected), (
            "het pakket heeft nu een andere verzameling meldingen dan dit live-scenario "
            f"aanmaakt: {sorted(known)}"
        )
        assert expected <= created, (
            "deze meldingen zijn in geen enkel huis werkelijk aangemaakt: "
            + ", ".join(sorted(expected - created))
        )
        assert not created - cleared, (
            "deze meldingen zijn aangemaakt maar bij het uitladen niet gewist: "
            + ", ".join(sorted(created - cleared))
        )
