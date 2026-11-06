"""Bereikbare uitzonderingen in de dekkingsmeting.

Reachable exclusions in the coverage measurement."""

from __future__ import annotations

import dataclasses
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from conftest import house
from coverage_helpers import named_exclusion_problems
from flow_helpers import cold, two_rooms
from homeassistant.util import dt as dt_util
from override_helpers import OverrideHost

import script.coverage_gate as coverage_gate
from custom_components.climate_director.coordinator import ClimateDirectorCoordinator
from custom_components.climate_director.engine import serialise
from custom_components.climate_director.switch import _DirectorSwitch

PACKAGE = Path(__file__).resolve().parents[1] / "custom_components" / "climate_director"


class TestTheLastSixExcludedLines:
    """De zes regels die eerder met een pragma waren afgevangen.

    The six lines that used to be caught with a pragma.

    Alle zes stonden met de reden "onbereikbaar in een test" in de bron, en alle
    zes zijn met een monkeypatch, een stand-in of een rechtstreekse aanroep te
    bereiken — precies de techniek die voor de vijf eerdere pragma's werd
    gebruikt. Ze verliezen daarom hun `# pragma: no cover`: de bewaking is dat
    ze gedekt zijn, niet dat ze uitgesloten zijn.

    All six stood in the source with the reason "unreachable in a test", and all
    six can be reached with a monkeypatch, a stand-in or a direct call — exactly
    the technique used for the five earlier pragmas. They therefore
    lose their `# pragma: no cover`: the guard is that they are covered, not
    that they are excluded.
    """

    async def test_a_failing_apply_is_logged_and_the_round_goes_on(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """coordinator.py: een ronde waarin `apply` gooit wordt gemeld en gaat door."""
        from harness_live import start_house, stop_house

        from custom_components.climate_director import coordinator as coordinator_module

        logged: list[str] = []
        monkeypatch.setattr(
            coordinator_module._LOGGER,
            "exception",
            lambda message, *args: logged.append(message % args),
        )

        async def refuse(*_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("kapot")

        monkeypatch.setattr(coordinator_module, "apply", refuse)

        live = await start_house(two_rooms(), states=cold())
        try:
            await live.evaluate()
            assert live.coordinator.last_changes, "deze ronde hoort iets te willen sturen"
            assert logged, "een mislukte `apply` hoort gemeld te worden"
            assert "Applying the climate plan failed" in logged[0]
            assert live.coordinator.last_applied == ()
            assert live.coordinator.data is not None, "de ronde hoort gewoon door te gaan"
        finally:
            await stop_house(live)

    def test_a_configured_sensor_that_is_not_tracked_is_skipped(self) -> None:
        """coordinator.py: een geconfigureerde sensor die niet gevolgd wordt."""
        config = dataclasses.replace(house(), outdoor_sensor="sensor.buiten")
        coordinator = SimpleNamespace(
            config=config,
            hass=SimpleNamespace(states=SimpleNamespace(get=lambda _entity_id: None)),
            tracked_entities=lambda: set(),
        )
        assert ClimateDirectorCoordinator.unusable_entities(coordinator) == {}

    def test_a_guest_window_that_is_no_mapping_is_dropped(self) -> None:
        """serialise.py: een gastenvenster dat geen mapping is bestaat niet."""
        assert serialise._guest_window("x") is None

    def test_an_override_without_a_source_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """overrides.py: zonder bron weigert de override en meldt dat."""
        host = OverrideHost(house())
        monkeypatch.setattr(host, "override_source", lambda *_args, **_kwargs: None)
        assert host.async_set_override("woonkamer", "heat", 21.0, 60, "turn_off") is False

    def test_an_override_that_expired_between_two_readings_waits_for_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """overrides.py: de tweede kloklezing valt ná `until`, dus niets in te plannen."""
        now = dt_util.utcnow()
        readings = iter([now, now + timedelta(hours=2)])
        monkeypatch.setattr(dt_util, "now", lambda: next(readings))

        host = OverrideHost(house())
        zone_id = house().zones[0].zone_id
        host.zone_overrides[zone_id] = True
        host.zone_override_until[zone_id] = now + timedelta(hours=1)
        host._override_wake_at_first_expiry()
        assert host._cancel_override_wake is None

    def test_the_base_switch_refuses_to_push(self) -> None:
        """switch.py: de basis van de schakelaars is abstract en zegt dat."""
        switch = _DirectorSwitch.__new__(_DirectorSwitch)
        with pytest.raises(NotImplementedError):
            switch._push()


def test_nothing_is_hidden_from_the_measurement() -> None:
    """Het pakket draagt geen enkele `pragma: no cover`.

    De dekkingspoort (`script/coverage_gate.py`) kan alleen zien wat coverage
    meekrijgt: een `pragma: no cover` haalt een regel uit de meting, en dan zegt
    "nul gemiste regels" niets meer over die regel. Daarom is de eigenschap die
    hier vastligt: het pakket sluit geen enkele regel uit. Wie er ooit een nodig
    heeft, past deze test aan met de reden erbij — en dat is dan een bewuste
    beslissing in plaats van een stilzwijgende uitsluiting.

    The coverage gate (`script/coverage_gate.py`) can only see what coverage is
    given: a `pragma: no cover` takes a line out of the measurement, and then
    "zero missed lines" no longer says anything about that line. Hence the
    property pinned here: the package excludes no line at all. Whoever needs one
    someday edits this test and adds the reason — making it a deliberate
    decision instead of a silent exclusion.
    """
    offenders = [
        f"{path.relative_to(PACKAGE)}:{number}: {line.strip()}"
        for path in sorted(PACKAGE.rglob("*.py"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if "pragma: no cover" in line
    ]
    assert not offenders, (
        "deze regels zijn uit de dekkingsmeting gehouden in plaats van gemeten: "
        + ", ".join(offenders)
    )


def test_every_line_outside_the_measurement_has_a_name() -> None:
    """Elke regel die buiten de meting valt heeft een naam.

    De poort (`script/coverage_gate.py`) kan alleen zien wat coverage meekrijgt,
    en coverage houdt drie soorten regels buiten de telling op een patroon. Een
    patroon verbergt stil, en daarom noemt de poort elke regel met naam en
    toenaam in `NAMED_EXCLUSIONS`. Deze test eist dat die lijst **precies** klopt
    met wat de meting overslaat: geen regel zonder naam, geen naam zonder regel.

    De meting heeft daar geen gegevensbestand voor nodig — wat coverage uitsluit
    hangt aan het bestand en het patroon, niet aan wat er gedraaid is. Zonder
    enige uitsluiting zou deze test niets meten, en dat is dan ook een fout.

    Die meting krijgt `data_file=None` mee, en dat is geen
    detail. `Coverage()` zonder dat argument wijst naar het standaardbestand
    `.coverage`, en `hidden_lines()` roept `analysis2()` aan; gemeten liet dat het
    bestaande `.coverage` leeg achter (39 → 0 gemeten bestanden), waarna
    `coverage report` en de poort "de meting is leeg" meldden. `Coverage` zelf
    beschrijft `data_file=None` als "geen gegevensbestand": dan wordt er niets
    gelezen en niets geschreven. Een test hoort de meting waar hij naast staat
    niet aan te raken; `test_the_guards_themselves.py` pint dat met een verzonnen
    meetbestand vast.

    Every line that falls outside the measurement has a name.
    The gate (`script/coverage_gate.py`) can only see what coverage is given, and
    coverage keeps three kinds of lines out of the count on a pattern. A pattern
    hides silently, so the gate names every line in `NAMED_EXCLUSIONS`. This test
    demands that the list matches **exactly** what the measurement skips: no line
    without a name, no name without a line.

    That measurement needs no data file — what coverage excludes hangs on the file
    and the pattern, not on what ran. Without any exclusion this test would
    measure nothing, and that too is an error.

    That measurement takes `data_file=None`, and that is no
    detail. `Coverage()` without that argument points at the default
    `.coverage`, and `hidden_lines()` calls `analysis2()`; measured, that left
    the existing `.coverage` empty (39 → 0 measured files), after which
    `coverage report` and the gate said "the measurement is empty". `Coverage`
    itself describes `data_file=None` as "no data file at all": then nothing is
    read and nothing is written. A test should not touch the measurement next to
    it; `test_the_guards_themselves.py` pins that down with an invented
    measurement.
    """
    assert named_exclusion_problems() == []


NAMED_EXCLUSIONS_BUDGET = 41


def test_the_named_exclusions_are_a_ratchet() -> None:
    """Het aantal benoemde uitsluitingen mag alleen dalen.

    De whitelist is er voor regels die de meting niet kán meenemen; elke regel die
    erbij komt is er één die de meting niet meer dekt. Zonder deze ratel groeit dat
    stil door — gemeten: een nieuwe dode stub plus zijn naam in
    `NAMED_EXCLUSIONS` liet de hele suite én de poort groen, terwijl de maat in
    `test_the_measure.py` alleen de modulegrootte zag. Wordt het getal groter, dan
    is deze test rood en somt hij de huidige inhoud op (met de nieuwe naam erbij);
    wordt het kleiner, dan is hij óók rood met de vraag het getal te verlagen. Zo
    kan de whitelist alleen korter worden.

    The number of named exclusions may only go down. The
    whitelist exists for lines the measurement cannot include; every line added to
    it is one the measurement no longer covers. Without this ratchet that grows
    silently — measured: a new dead stub plus its name in
    `NAMED_EXCLUSIONS` left the whole suite and the gate green, while the measure
    in `test_the_measure.py` only saw the module size. When the number grows, this
    test is red and lists the current content (with the new name in it); when it
    shrinks, it is red too, asking for the number to be lowered. That way the
    whitelist can only get shorter.
    """
    counted = sum(len(entries) for entries in coverage_gate.NAMED_EXCLUSIONS.values())
    if counted == NAMED_EXCLUSIONS_BUDGET:
        return
    listed = "; ".join(
        f"{name}: {', '.join(entries)}"
        for name, entries in sorted(coverage_gate.NAMED_EXCLUSIONS.items())
    )
    if counted > NAMED_EXCLUSIONS_BUDGET:
        raise AssertionError(
            f"de whitelist van de poort is gegroeid: {counted} benoemde uitsluitingen, "
            f"genoteerd {NAMED_EXCLUSIONS_BUDGET}. Elke regel erbij is een regel die de "
            f"meting niet meer dekt; haal hem eruit of verantwoord hem. Nu: {listed}"
        )
    raise AssertionError(
        f"de whitelist van de poort is korter geworden: {counted}, genoteerd "
        f"{NAMED_EXCLUSIONS_BUDGET}. Zet het nieuwe getal erin (lager mag altijd). Nu: {listed}"
    )
