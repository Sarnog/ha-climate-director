"""Het thuiskomstmoment van anker 13, gemeten in een draaiende Home Assistant.

Anchor 13's homecoming moment, measured inside a running Home Assistant.

`test_quiet_windows.py` legt de regel vast in de engine; dit bestand legt vast dat
het *moment* ook werkelijk daar aankomt, over zeven gevallen: iemand komt thuis
vóór het venster, iemand komt thuis in een leeg huis tijdens het venster, dat
moment overleeft een herstart mét opslag, het vervalt voor wie op dat moment weg
is, de terugval op `last_changed` doet wat besluit 4 zegt, de gastenmodus heft de
stilte op binnen zijn venster, en de diagnose lakt het af. Zonder deze laag bleef
een coördinatormutatie die het moment nooit vastlegt, of die het bij een herstart
opnieuw zet, volledig groen.

**Over de klok, want daar zit de enige subtiliteit.** Het moment van een bewoner is
`last_changed` van zijn aanwezigheidsentiteit: een *echt* tijdstip. De klok van de
integratie wordt hier verzet (`clock.place(...)`, `clock.advance(...)`), en de
vensters worden uit díe klok afgeleid ("begon tien minuten geleden"). De engine
vergelijkt twee tijdstippen, dus wat telt is of het venster in absolute zin vóór of
ná dat moment begon - en dat schuift mee met de klok die deze test verzet. Daarom
meet elke test hieronder op elk uur van de dag hetzelfde (H6 van ronde 13): een klok
vooruit zet het venster ná elk moment dat deze test vastlegt ("al thuis"), een klok
gelijk of terug zet het ervoor ("thuiskomer"). Elke test zegt welke van de twee hij
meet, met `home_before(...)` als bewijs in plaats van als aanname.

**About the clock, since that is the only subtlety.** A resident's moment is the
`last_changed` of their presence entity: a *real* timestamp. The integration's clock
is moved here (`clock.place(...)`, `clock.advance(...)`), and the windows are derived
from that clock ("began ten minutes ago"). The engine compares two instants, so what
counts is whether the window began before or after that moment in absolute terms -
and that shifts along with the clock this test moves. Every test below therefore
measures the same at any hour of the day (H6 of round 13): a clock moved forward puts
the window after every moment this test records ("already home"), a clock level or
moved back puts it before ("homecomer"). Each test says which of the two it measures,
with `home_before(...)` as proof instead of an assumption.

`test_quiet_windows.py` pins the rule down in the engine; this file pins down that
the *moment* really arrives there, across seven cases: somebody comes home before
the window, somebody comes home to an empty house inside the window, that moment
survives a restart with a store, it lapses for whoever is away at that moment, the
fallback to `last_changed` does what decision 4 says, guest mode lifts the quiet
inside its window, and the diagnostics redact it. Without this layer a coordinator
mutation that never records the moment, or that sets it anew on a restart, stayed
completely green.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from harness_live import (
    LiveHome,
    new_config_dir,
    settings,
    source,
    start_house,
    stop_house,
    zone,
)
from homeassistant.components.diagnostics.util import REDACTED
from homeassistant.helpers import issue_registry as ir

from custom_components.climate_director import coordinator as coordinator_module
from custom_components.climate_director.const import DOMAIN
from custom_components.climate_director.diagnostics import async_get_config_entry_diagnostics

LIVING = "climate.woonkamer"
PERSON = "person.danny"
CHARGER = "sensor.danny_lader"

#: Het venster loopt twaalf uur, dus het staat altijd open zodra het begonnen is.
LENGTH = timedelta(hours=12)

#: Hoe lang geleden het venster in deze tests begon.
AGO = 10


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch):
    """Return a handle that moves the integration's clock, forward and back.

    Alleen de klok van de integratie schuift; de tijdstempels van de entiteiten
    blijven staan waar Home Assistant ze zette. Dat is wat het verstrijken van tijd
    betekent, en het is ook wat "al thuis" van "thuiskomer" scheidt: het moment van
    de entiteit is echt, de klok is wat deze test verzet.

    Only the integration's clock moves; the entities' timestamps stay where Home
    Assistant put them. That is what elapsed time means, and it is also what
    separates "already home" from "homecomer": the entity's moment is real, the
    clock is what this test moves.
    """
    from homeassistant.util import dt as dt_util

    real = dt_util.now
    shift = {"by": timedelta()}

    def _now() -> datetime:
        return real() + shift["by"]

    monkeypatch.setattr(coordinator_module.dt_util, "now", _now)

    class Handle:
        """Zet de klok op een vaste verschuiving, of laat hem verder lopen."""

        def place(self, **kwargs: Any) -> None:
            shift["by"] = timedelta(**kwargs)

        def advance(self, **kwargs: Any) -> None:
            shift["by"] += timedelta(**kwargs)

    return Handle()


def quiet(start: datetime, end: datetime) -> dict[str, Any]:
    """Return a quiet window in stored form, read from two moments."""
    return {
        "start": start.strftime("%H:%M:%S"),
        "end": end.strftime("%H:%M:%S"),
        "weekdays": None,
        "holiday": False,
    }


def window_started(ago: int = AGO) -> dict[str, Any]:
    """Return a quiet window that opened `ago` minutes before the current clock."""
    start = coordinator_module.dt_util.now() - timedelta(minutes=ago)
    return quiet(start, start + LENGTH)


def guest_window(*, hours: int) -> dict[str, Any]:
    """Return a guest window of `hours` on either side of the current clock."""
    now = coordinator_module.dt_util.now()
    return quiet(now - timedelta(hours=hours), now + timedelta(hours=hours))


def installation(
    *,
    quiet_window: dict[str, Any] | None = None,
    guest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a cold single-zone house with one resident and one boiler."""
    gates: dict[str, Any] = {}
    if quiet_window is not None:
        gates["quiet_windows"] = [quiet_window]
    if guest is not None:
        gates["guest_window"] = guest
    found: dict[str, Any] = {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("woonkamer_ketel", LIVING)],
                indoor_sensor="sensor.woonkamer",
                heat=settings(21.0, 20.0),
            )
        ],
        "outdoor_sensor": "sensor.buiten",
        "residents": [
            {
                "resident_id": "danny",
                "name": "Danny",
                "presence_entity": PERSON,
                "sleep_entity": CHARGER,
                "sleep_state": "wireless",
            }
        ],
    }
    if gates:
        found["gates"] = gates
    return found


def cold_world(*, home: bool = True) -> dict[str, tuple[str, dict[str, Any]]]:
    """Return a world where the living room wants heat and Danny is home or out."""
    return {
        "sensor.woonkamer": ("18.0", {}),
        "sensor.buiten": ("4.0", {}),
        LIVING: ("off", {"temperature": 19.0}),
        PERSON: ("home" if home else "not_home", {}),
        CHARGER: ("none", {}),
    }


def moment_of(home: LiveHome) -> datetime:
    """Return the presence entity's own timestamp, the source of every moment."""
    state = home.hass.states.get(PERSON)
    assert state is not None, "de aanwezigheidsentiteit bestaat niet"
    return state.last_changed


def moment(home: LiveHome) -> datetime:
    """Return the recorded homecoming moment, which must be there."""
    found = home.coordinator._home_since.get("danny")
    assert found is not None, "er is geen thuiskomstmoment vastgelegd"
    return found


def home_before(home: LiveHome) -> bool:
    """Return whether the recorded moment lies before the open window's beginning.

    Dit is de vraag die anker 13 stelt, hier met dezelfde twee tijdstippen als de
    engine gebruikt: het moment uit de boekhouding en het begin van een venster dat
    `AGO` minuten geleden begon op de klok van de integratie. Een test die beweert
    "hij was al thuis" hoort dit waar te maken in plaats van het aan te nemen.

    This is the question anchor 13 asks, here with the same two instants the engine
    uses: the moment from the bookkeeping and the beginning of a window that started
    `AGO` minutes ago on the integration's clock. A test claiming "he was already
    home" should make this true rather than assume it.
    """
    now = home.coordinator.world.now
    return moment(home) < now - timedelta(minutes=AGO)


def stored(home: LiveHome) -> dict[str, Any]:
    """Return the moments as the store payload carries them."""
    return home.coordinator._store_payload().get("home_since", {})


async def moves(home: LiveHome, state: str = "home") -> None:
    """Put the presence entity in a state and let the integration act on it.

    `settle()` staat er met een reden: het toestandsevenement van `set(...)` komt in
    dit harnas pas op de volgende loop-ronde bij de listener, en zonder die stap
    bouwt `evaluate()` de wereld nog met de boekhouding van vóór de beweging - een
    test die dan "de listener legde het moment vast" beweert, meet in werkelijkheid
    de terugval van het opstarten.

    `settle()` is there for a reason: in this harness the state event from `set(...)`
    only reaches the listener on the next loop round, and without that step
    `evaluate()` builds the world with the bookkeeping from before the move - a test
    then claiming "the listener recorded the moment" in fact measures the startup
    fallback.
    """
    home.set(PERSON, state)
    await home.settle()
    await home.evaluate()


class TestComingHomeBeforeTheWindow:
    """Geval 1: wie vóór het begin thuiskomt, houdt het huis aan de gang.

    Case 1: whoever comes home before the beginning keeps the house going.
    """

    async def test_somebody_who_came_home_early_regulates_on(self, clock) -> None:
        # De klok staat een half uur vooruit, dus het venster begint in absolute zin
        # ná het moment van de entiteit: deze bewoner was er al.
        #
        # The clock stands half an hour ahead, so the window begins after the
        # entity's moment in absolute terms: this resident was already there.
        clock.place(minutes=30)
        home = await start_house(
            installation(quiet_window=window_started()), states=cold_world(home=False)
        )
        try:
            await moves(home)

            assert moment(home) == moment_of(home)
            assert home_before(home)
            assert home.state(LIVING) == "heat"
        finally:
            await stop_house(home)


class TestComingHomeInsideTheWindow:
    """Gevallen 2 en 6: een leeg huis dat ná het begin iemand binnenlaat blijft stil.

    Cases 2 and 6: an empty house that lets somebody in after the beginning stays
    quiet.
    """

    async def test_a_homecomer_in_an_empty_house_stays_quiet(self, clock) -> None:
        clock.place()
        home = await start_house(
            installation(quiet_window=window_started()), states=cold_world(home=False)
        )
        try:
            home.set(PERSON, "home")
            await home.evaluate()

            assert not home_before(home)
            assert home.state(LIVING) == "off"
        finally:
            await stop_house(home)

    async def test_guests_lift_the_quiet_inside_their_window(self, clock) -> None:
        """Besluit 5: met gasten binnen hun venster is een leeg huis geen reden."""
        clock.place()
        home = await start_house(
            installation(quiet_window=window_started(), guest=guest_window(hours=1)),
            states=cold_world(home=False),
        )
        try:
            await home.call("switch", "turn_on", {"entity_id": home.by_key("guest")})
            await home.evaluate()

            assert home.state(LIVING) == "heat"
        finally:
            await stop_house(home)

    async def test_outside_the_guest_window_the_quiet_returns(self, clock) -> None:
        """Buiten het gastenvenster geldt de gewone stilte weer, gastenmodus of niet."""
        clock.place()
        home = await start_house(
            installation(quiet_window=window_started(), guest=guest_window(hours=-2)),
            states=cold_world(home=False),
        )
        try:
            await home.call("switch", "turn_on", {"entity_id": home.by_key("guest")})
            await home.evaluate()

            assert home.state(LIVING) == "off"
        finally:
            await stop_house(home)


class TestTheMomentSurvivesARestart:
    """Gevallen 3 en 4: de opslag draagt het moment, en laat het vallen voor wie weg is.

    Cases 3 and 4: the store carries the moment, and drops it for whoever is away.
    """

    async def test_the_store_keeps_the_moment_without_making_a_new_one(self, clock) -> None:
        """Hetzelfde moment komt terug uit de opslag, niet uit een nieuwe meting.

        De entiteit krijgt bij de tweede start een vers tijdstempel - dat is wat
        opzetten doet - dus de terugval zou een *ander* moment opleveren dan de
        opslag. Dat verschil is de eigenschap van besluit 3: een herstart is geen
        thuiskomst. Of de stiltepoort dat verschil ook ziet hangt aan de klok, want
        beide momenten liggen seconden uit elkaar; daarom meet deze test het moment
        zelf en niet alleen de uitkomst.

        The entity gets a fresh timestamp on the second start - that is what setting
        up does - so the fallback would yield a *different* moment than the store.
        That difference is decision 3's property: a restart is not a homecoming.
        Whether the quiet gate sees that difference too hangs on the clock, since both
        moments lie seconds apart; this test therefore measures the moment itself, not
        just the outcome.
        """
        config_dir = new_config_dir()
        clock.place(minutes=30)
        home = await start_house(
            installation(quiet_window=window_started()),
            states=cold_world(home=False),
            entry_id="stilte",
            config_dir=config_dir,
        )
        try:
            await moves(home)
            first = moment(home)
            assert stored(home)["danny"] == first.isoformat()
            assert home.state(LIVING) == "heat"
        finally:
            await stop_house(home)

        # Dezelfde verschuiving als de eerste start: de tweede start hergebruikt de
        # opgeslagen installatie en dus het venster van de eerste. Binnen diezelfde
        # verschuiving ligt het bewaarde moment nog steeds vóór het begin, en de
        # terugval van de tweede start ook - daarom meet de rest van deze test het
        # moment zelf en niet alleen de uitkomst.
        #
        # The same shift as the first start: the second start reuses the stored
        # installation and hence the first one's window. Within that same shift the
        # stored moment still lies before the beginning, and so does the second
        # start's fallback - which is why the rest of this test measures the moment
        # itself and not just the outcome.
        clock.place(minutes=30)
        again = await start_house(
            installation(quiet_window=window_started()),
            states=cold_world(),
            entry_id="stilte",
            config_dir=config_dir,
        )
        try:
            assert again.coordinator._home_since["danny"] == first
            assert stored(again)["danny"] == first.isoformat()
            assert moment_of(again) != first
            assert again.state(LIVING) == "heat"
        finally:
            await stop_house(again)

    async def test_a_moment_of_somebody_who_is_away_lapses(self, clock) -> None:
        """Gevals 4: opslag draagt een moment, maar de bewoner is weg bij het opzetten.

        Het moment verdwijnt dan uit de opslag, en wie daarna thuiskomt is een gewone
        thuiskomer: stil. Zonder dat verval zou het oude moment blijven staan en zou
        het huis gewoon gaan stoken.

        The moment then disappears from the store, and whoever comes home after that
        is an ordinary homecomer: quiet. Without that lapse the old moment would stay
        put and the house would simply start heating.
        """
        config_dir = new_config_dir()
        # De tweede start hergebruikt de opgeslagen installatie, dus het venster van
        # de eerste start - en daarom blijft de klok hier staan waar hij stond. Met
        # een verschoven klok in de eerste start zou hetzelfde venster in de tweede
        # start ergens anders liggen.
        #
        # The second start reuses the stored installation, hence the first start's
        # window - so the clock stays where it was here. With a shifted clock on the
        # first start the same window would lie elsewhere on the second.
        clock.place()
        home = await start_house(
            installation(quiet_window=window_started()),
            states=cold_world(home=False),
            entry_id="weg",
            config_dir=config_dir,
        )
        try:
            await moves(home)
            earlier = moment(home)
            assert stored(home)["danny"] == earlier.isoformat()
        finally:
            await stop_house(home)

        again = await start_house(
            installation(quiet_window=window_started()),
            states=cold_world(home=False),
            entry_id="weg",
            config_dir=config_dir,
        )
        try:
            assert again.coordinator._home_since.get("danny") is None
            assert "danny" not in stored(again)

            await moves(again)

            assert moment(again) != earlier
            assert not home_before(again)
            assert again.state(LIVING) == "off"
        finally:
            await stop_house(again)


class TestTheFallbackOnLastChanged:
    """Gevals 5: zonder opslag is het moment van de entiteit zelf de bron.

    Case 5: without a store the entity's own moment is the source.
    """

    async def test_an_old_last_changed_counts_as_already_home(self, clock) -> None:
        """Een klok vooruit zet het venster ná het tijdstempel: de bewoner was er al."""
        clock.place(minutes=30)
        home = await start_house(installation(quiet_window=window_started()), states=cold_world())
        try:
            assert moment(home) == moment_of(home)
            assert home_before(home)
        finally:
            await stop_house(home)

    async def test_an_unshifted_clock_puts_the_window_over_the_moment(self, clock) -> None:
        """Zonder opslag en met een vers tijdstempel binnen het venster: stil.

        Op de onverschoven klok begint het venster vóór het tijdstempel van de
        entiteit, en dan leest de bewoner als net thuis. Dit is de terugval die
        "hooguit één keer bijt" uit besluit 4: een herstart zet alles op hetzelfde
        moment.

        On the unshifted clock the window begins before the entity's timestamp, and
        then the resident reads as just home. This is the fallback that "bites at most
        once" from decision 4: a restart puts everything on the same moment.
        """
        clock.place()
        home = await start_house(installation(quiet_window=window_started()), states=cold_world())
        try:
            assert moment(home) == moment_of(home)
            assert not home_before(home)
            assert home.state(LIVING) == "off"
        finally:
            await stop_house(home)


class TestTheDiagnostics:
    """Gevals 7: het thuiskomstmoment is een bewonersgegeven, dus het wordt gelakt."""

    async def test_the_homecoming_moment_is_redacted(self, clock) -> None:
        clock.place(minutes=30)
        home = await start_house(installation(quiet_window=window_started()), states=cold_world())
        try:
            recorded = moment(home)

            data = await async_get_config_entry_diagnostics(home.hass, home.entry)

            assert data["world"]["residents"]["danny"]["home_since"] == REDACTED
            assert recorded.isoformat() not in json.dumps(data)
        finally:
            await stop_house(home)


class TestAStoreThatIsNotToBeTrusted:
    """Eigen variant E4: onleesbare rommel in de opslag wordt genegeerd.

    Own variant E4: unreadable junk in the store is ignored.

    De lezer is net zo vergevingsgezind als de rest van `state_store.py`: een waarde
    met een andere vorm dan verwacht telt als afwezig, en dat is geen reden om de hele
    opslag opzij te zetten of een `corrupt_storage`-melding te doen.
    """

    async def test_junk_in_the_store_costs_nobody_a_notice(self, clock) -> None:
        config_dir = new_config_dir()
        clock.place()
        home = await start_house(
            installation(quiet_window=window_started()),
            states=cold_world(home=False),
            entry_id="rommel",
            config_dir=config_dir,
        )
        try:
            path = Path(home.coordinator._store.path)
        finally:
            await stop_house(home)

        written = json.loads(path.read_text(encoding="utf-8"))
        written["data"]["home_since"] = {
            "danny": "geen datum",
            "onbekend": "2026-08-10T18:00:00+00:00",
        }
        path.write_text(json.dumps(written), encoding="utf-8")

        again = await start_house(
            installation(quiet_window=window_started()),
            states=cold_world(),
            entry_id="rommel",
            config_dir=config_dir,
        )
        try:
            # De rommel telt als afwezig, dus de bewoner valt terug op zijn eigen
            # tijdstempel - en niet op iets uit het bestand.
            #
            # The junk counts as absent, so the resident falls back on their own
            # timestamp - not on anything from the file.
            assert moment(again) == moment_of(again)
            assert stored(again)["danny"] == moment_of(again).isoformat()
            assert "onbekend" not in stored(again)
            notice = ir.async_get(again.hass).async_get_issue(
                DOMAIN, f"corrupt_storage_{again.entry.entry_id}"
            )
            assert notice is None
        finally:
            await stop_house(again)


class TestTwoResidentsOnOnePresenceEntity:
    """Eigen variant: twee bewoners die dezelfde aanwezigheidsentiteit delen.

    Own variant: two residents sharing one presence entity.

    Een huishouden met één "is er iemand thuis"-sensor levert twee bewoners op
    dezelfde entiteit op, en dan hoort elk van hen het moment te krijgen. Wie in de
    listener bij de eerste treffer stopt, laat de tweede bewoner voor eeuwig als
    onbekend thuis achter - en dan remt het stiltevenster voor hem.
    """

    async def test_both_residents_get_the_moment(self, clock) -> None:
        clock.place(minutes=30)
        rooms = installation(quiet_window=window_started())
        rooms["residents"].append(
            {
                "resident_id": "nancy",
                "name": "Nancy",
                "presence_entity": PERSON,
                "sleep_entity": CHARGER,
                "sleep_state": "wireless",
            }
        )
        home = await start_house(rooms, states=cold_world(home=False))
        try:
            await moves(home)

            assert home.coordinator._home_since["danny"] == moment_of(home)
            assert home.coordinator._home_since["nancy"] == moment_of(home)
            assert stored(home)["nancy"] == moment_of(home).isoformat()
            assert home.state(LIVING) == "heat"
        finally:
            await stop_house(home)


class TestNoWriteWhileClosing:
    """Eigen variant E5: een thuiskomst tijdens het afsluiten schrijft niet meer weg.

    Own variant E5: a homecoming during shutdown no longer writes anything away.

    `_async_save_state` weigert te plannen zodra `_closing` waar is, zodat een ronde
    die het afsluiten overleeft het bestand niet ná `async_remove_entry` terugschrijft.
    De listener die het moment vastlegt loopt langs dezelfde deur, en dat is hier te
    meten: met `_closing` waar komt er geen uitgestelde schrijfactie meer bij.
    """

    async def test_a_homecoming_while_closing_schedules_no_write(self, clock, monkeypatch) -> None:
        clock.place()
        home = await start_house(
            installation(quiet_window=window_started()), states=cold_world(home=False)
        )
        try:
            writes: list[str] = []
            monkeypatch.setattr(
                home.coordinator._store,
                "async_delay_save",
                lambda *_, **__: writes.append("write"),
            )

            await moves(home)
            assert writes == ["write"]
            assert moment(home) == moment_of(home)

            # Met `_closing` waar loopt de opname langs dezelfde deur, maar die
            # zwaait niet meer open: geen enkele uitgestelde schrijfactie erbij.
            #
            # With `_closing` true the recording walks through the same door, but it
            # no longer opens: not a single delayed write is added.
            home.coordinator._closing = True
            await moves(home, "not_home")
            await moves(home)
            assert writes == ["write"]
        finally:
            home.coordinator._closing = False
            await stop_house(home)
