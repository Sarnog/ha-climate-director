"""Wie bij het apparaat zelf op uit drukt, krijgt die kamer terug.

Whoever presses off on the appliance itself gets that room back.

Het ergste wat deze integratie kan doen is iemand overstemmen die net met de
hand iets heeft uitgezet. Dan staat er twee seconden later weer een airco te
blazen die je expres stil had gezet, en is de conclusie terecht dat het ding
niet deugt. Dus: die zone valt stil tot dezelfde hand hem weer aanzet, of tot de
volgende dag - want een besluit van gisteravond hoort vanochtend niet te gelden.

The worst thing this integration can do is overrule somebody who just switched
something off by hand. Two seconds later an air conditioner you deliberately
silenced is blowing again, and the fair conclusion is that the thing is no good.
So: that zone falls silent until the same hand switches it back on, or until the
next day - since last night's decision should not still hold this morning.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from homeassistant.util import dt as dt_util

from custom_components.climate_director.coordinator import ClimateDirectorCoordinator
from custom_components.climate_director.engine import (
    DirectorConfig,
    ModeSettings,
    Source,
    Zone,
)
from custom_components.climate_director.engine.plan import Plan, Reason, UnitCommand

LIVING = "climate.huiskamer"
BEDROOM = "climate.master_bedroom"


def config(*, with_residents: bool = False) -> DirectorConfig:
    from custom_components.climate_director.engine import Resident

    residents = (
        (
            Resident(
                "danny",
                "Danny",
                presence_entity="person.danny",
                sleep_entity="sensor.danny_charger_type",
                sleep_state="wireless",
            ),
            Resident(
                "nancy",
                "Nancy",
                presence_entity="person.nancy",
                sleep_entity="sensor.nancy_charger_type",
                sleep_state="wireless",
            ),
        )
        if with_residents
        else ()
    )
    return DirectorConfig(
        residents=residents,
        zones=(
            Zone(
                "woonkamer",
                "Woonkamer",
                "sensor.woonkamer",
                sources=(Source("w", LIVING),),
                heat=ModeSettings(21.0, 20.0),
            ),
            Zone(
                "slaapkamer",
                "Slaapkamer",
                "sensor.slaapkamer",
                sources=(Source("s", BEDROOM),),
                heat=ModeSettings(21.0, 20.0),
            ),
        ),
    )


class _State:
    def __init__(self, state: str) -> None:
        self.state = state


class _Event:
    """A state change, shaped the way Home Assistant hands one over."""

    def __init__(self, entity_id: str, old: str | None, new: str | None) -> None:
        self.data = {
            "entity_id": entity_id,
            "old_state": None if old is None else _State(old),
            "new_state": None if new is None else _State(new),
        }


def shared_config(*, with_residents: bool = False) -> DirectorConfig:
    """Return two zones that both steer the same boiler thermostat."""
    from custom_components.climate_director.engine import Resident

    residents = (
        (
            Resident(
                "danny",
                "Danny",
                presence_entity="person.danny",
                sleep_entity="sensor.danny_charger_type",
                sleep_state="wireless",
            ),
        )
        if with_residents
        else ()
    )
    return DirectorConfig(
        residents=residents,
        zones=(
            Zone(
                "woonkamer",
                "Woonkamer",
                "sensor.woonkamer",
                sources=(Source("ketel", "climate.ketel"),),
                heat=ModeSettings(21.0, 20.0),
            ),
            Zone(
                "zolder",
                "Zolder",
                "sensor.zolder",
                sources=(Source("ketel", "climate.ketel"),),
                heat=ModeSettings(21.0, 20.0),
            ),
        ),
    )


def coordinator(
    plan: Plan | None = None,
    states: dict[str, str] | None = None,
    *,
    cfg: DirectorConfig | None = None,
):
    """Return a stand-in carrying only what the notice methods touch."""

    class Registry:
        def get(self, entity_id):
            value = (states or {}).get(entity_id)
            return None if value is None else _State(value)

    class Hass:
        def __init__(self) -> None:
            self.states = Registry()

    class StandIn:
        def __init__(self) -> None:
            self.config = cfg or config(with_residents=bool(states))
            self.zone_overrides: dict[str, bool] = {}
            self._handed_back: dict[str, date] = {}
            # `data` is het gepubliceerde besluit, `_issued` het besluit dat op
            # tafel ligt. Tijdens het uitvoeren zijn dat er twee; hier gaat het
            # om het plan dat de director net gaf, dus staan ze gelijk.
            #
            # `data` is the published decision, `_issued` the decision on the
            # table. While carrying one out those are two; here it is about the
            # plan the director just gave, so they are the same.
            self.data = plan
            self._issued = plan
            self.shadow = False
            self.hass = Hass()
            self.saved = 0

        def _async_save_state(self) -> None:
            self.saved += 1

        _notice_hand = ClimateDirectorCoordinator._notice_hand
        _zones_of = ClimateDirectorCoordinator._zones_of
        _we_wanted_it_off = ClimateDirectorCoordinator._we_wanted_it_off
        _zones_handed_back = ClimateDirectorCoordinator._zones_handed_back
        _overridden_zones = ClimateDirectorCoordinator._overridden_zones
        _everyone_asleep = ClimateDirectorCoordinator._everyone_asleep
        _house_is_empty = ClimateDirectorCoordinator._house_is_empty
        _state_is = ClimateDirectorCoordinator._state_is

    return StandIn()


def running_plan(entity_id: str = BEDROOM) -> Plan:
    """Return a plan in which that appliance is meant to be heating."""
    return Plan(commands=(UnitCommand(entity_id=entity_id, hvac_mode="heat"),))


def idle_plan(entity_id: str = BEDROOM) -> Plan:
    """Return a plan in which the director itself stood that appliance down."""
    return Plan(
        commands=(UnitCommand(entity_id=entity_id, hvac_mode="off", reason=Reason.SATISFIED),)
    )


class TestAHandSwitchingItOff:
    def test_the_zone_is_handed_back(self) -> None:
        item = coordinator(running_plan())
        item._notice_hand(_Event(BEDROOM, "heat", "off"))
        assert item._zones_handed_back() == {"slaapkamer"}

    def test_the_other_zones_carry_on(self) -> None:
        item = coordinator(running_plan())
        item._notice_hand(_Event(BEDROOM, "heat", "off"))
        assert "woonkamer" not in item._zones_handed_back()

    @pytest.mark.parametrize("was", ["heat", "cool", "dry", "auto", "heat_cool"])
    def test_from_any_running_mode(self, was: str) -> None:
        item = coordinator(running_plan())
        item._notice_hand(_Event(BEDROOM, was, "off"))
        assert item._zones_handed_back() == {"slaapkamer"}

    @pytest.mark.parametrize("now", ["off", "fan_only"])
    def test_to_any_idle_mode(self, now: str) -> None:
        """Fan only is not climate control either, whatever the appliance calls it."""
        item = coordinator(running_plan())
        item._notice_hand(_Event(BEDROOM, "heat", now))
        assert item._zones_handed_back() == {"slaapkamer"}


class TestASharedAppliance:
    """Eén apparaat onder meerdere zones: een hand telt voor elke zone.

    A hand at an appliance shared by several zones counts for every one of them.
    """

    def test_every_zone_it_serves_is_handed_back(self) -> None:
        item = coordinator(running_plan("climate.ketel"), cfg=shared_config())
        item._notice_hand(_Event("climate.ketel", "heat", "off"))
        assert item._zones_handed_back() == {"woonkamer", "zolder"}

    def test_every_zone_is_overridden_so_no_command_follows(self) -> None:
        """Two cold zones, one shared boiler off by hand: no set_hvac_mode after."""
        from conftest import make_world

        from custom_components.climate_director.engine import decide

        item = coordinator(running_plan("climate.ketel"), cfg=shared_config())
        item._notice_hand(_Event("climate.ketel", "heat", "off"))
        assert item._overridden_zones() == {"woonkamer": True, "zolder": True}

        world = make_world(
            indoor={"woonkamer": 15.0, "zolder": 15.0},
            climates={"climate.ketel": "off"},
            zone_overrides=item._overridden_zones(),
        )
        plan = decide(item.config, world)
        assert plan.command_for("climate.ketel") is None
        assert any(entry.entity_id == "climate.ketel" for entry in plan.untouched)

    def test_switching_it_back_on_clears_every_zone(self) -> None:
        item = coordinator(running_plan("climate.ketel"), cfg=shared_config())
        item._notice_hand(_Event("climate.ketel", "heat", "off"))
        item._notice_hand(_Event("climate.ketel", "off", "heat"))
        assert item._zones_handed_back() == set()
        assert item._handed_back == {}

    def test_the_next_day_forgets_every_zone(self) -> None:
        yesterday = date.today() - timedelta(days=1)
        item = coordinator(running_plan("climate.ketel"), cfg=shared_config())
        item._handed_back = {"woonkamer": yesterday, "zolder": yesterday}
        assert item._zones_handed_back() == set()


class TestWhatDoesNotCount:
    def test_our_own_command_is_not_a_hand(self) -> None:
        """Otherwise the director would silence every zone it ever switches off."""
        item = coordinator(idle_plan())
        item._notice_hand(_Event(BEDROOM, "heat", "off"))
        assert item._zones_handed_back() == set()

    def test_an_appliance_the_director_does_not_drive(self) -> None:
        item = coordinator(running_plan())
        item._notice_hand(_Event("climate.iets_anders", "heat", "off"))
        assert item._zones_handed_back() == set()

    def test_a_change_within_the_same_family(self) -> None:
        """Turning the setpoint up is not switching the thing off."""
        item = coordinator(running_plan())
        item._notice_hand(_Event(BEDROOM, "heat", "heat"))
        assert item._zones_handed_back() == set()

    @pytest.mark.parametrize("old", ["off", "fan_only"])
    def test_it_was_already_idle(self, old: str) -> None:
        item = coordinator(running_plan())
        item._notice_hand(_Event(BEDROOM, old, "off"))
        assert item._zones_handed_back() == set()

    def test_a_missing_state_is_survivable(self) -> None:
        """Entities come and go on a restart; none of that is a hand."""
        item = coordinator(running_plan())
        item._notice_hand(_Event(BEDROOM, None, "off"))
        item._notice_hand(_Event(BEDROOM, "heat", None))
        assert item._zones_handed_back() == set()

    def test_without_a_plan_yet(self) -> None:
        """Before the first decision there is nothing to compare against."""
        item = coordinator(None)
        item._notice_hand(_Event(BEDROOM, "heat", "off"))
        assert item._zones_handed_back() == {"slaapkamer"}


class TestGettingItBack:
    def test_switching_it_on_again_by_hand(self) -> None:
        item = coordinator(running_plan())
        item._notice_hand(_Event(BEDROOM, "heat", "off"))
        item._notice_hand(_Event(BEDROOM, "off", "heat"))
        assert item._zones_handed_back() == set()

    @pytest.mark.parametrize("mode", ["heat", "cool", "dry", "heat_cool"])
    def test_in_any_running_mode(self, mode: str) -> None:
        item = coordinator(running_plan())
        item._notice_hand(_Event(BEDROOM, "heat", "off"))
        item._notice_hand(_Event(BEDROOM, "off", mode))
        assert item._zones_handed_back() == set()

    def test_the_next_day(self) -> None:
        """Yesterday's decision should not still be holding this morning."""
        item = coordinator(running_plan())
        item._handed_back = {"slaapkamer": date.today() - timedelta(days=1)}
        assert item._zones_handed_back() == set()

    def test_today_it_still_holds(self) -> None:
        item = coordinator(running_plan())
        item._handed_back = {"slaapkamer": date.today()}
        assert item._zones_handed_back() == {"slaapkamer"}

    def test_a_day_older_still_counts_as_over(self) -> None:
        item = coordinator(running_plan())
        item._handed_back = {"slaapkamer": date.today() - timedelta(days=30)}
        assert item._zones_handed_back() == set()


class TestItReachesTheGates:
    """The whole point is that the zone stops being regulated, so check that."""

    def test_a_handed_back_zone_is_overridden(self) -> None:
        from conftest import make_world

        from custom_components.climate_director.engine import Reason as GateReason
        from custom_components.climate_director.engine import gates

        item = coordinator(running_plan())
        item._notice_hand(_Event(BEDROOM, "heat", "off"))

        overrides = {
            **dict.fromkeys(item._zones_handed_back(), True),
            **item.zone_overrides,
        }
        world = make_world(zone_overrides=overrides)
        bedroom = item.config.zone("slaapkamer")
        living = item.config.zone("woonkamer")
        assert bedroom is not None and living is not None
        assert gates.evaluate(item.config, world, bedroom).reason is GateReason.MANUAL_OVERRIDE
        assert gates.evaluate(item.config, world, living).allowed

    def test_the_switch_still_wins(self) -> None:
        """A user switching the override on outranks anything worked out here."""
        item = coordinator(running_plan())
        item.zone_overrides["woonkamer"] = True
        overrides = {
            **dict.fromkeys(item._zones_handed_back(), True),
            **item.zone_overrides,
        }
        assert overrides["woonkamer"] is True


class TestGoingToBedGivesItBack:
    """Iedereen op bed betekent dat de dag voorbij is, niet pas middernacht.

    De automatiseringen zetten de override uit zodra beiden op bed lagen. Tot
    middernacht wachten houdt de zone een paar uur langer stil dan iemand
    bedoelde, en dat merk je pas de volgende ochtend als er niets is voorverwarmd.

    Everybody in bed means the day is over, not midnight. The automations
    switched the override off the moment both had turned in. Waiting for midnight
    holds the zone still a few hours longer than anybody meant, and you only
    notice the next morning when nothing has warmed up.
    """

    HOME_AWAKE = {
        "person.danny": "home",
        "person.nancy": "home",
        "sensor.danny_charger_type": "none",
        "sensor.nancy_charger_type": "none",
    }

    def _with(self, **changes: str) -> dict[str, str]:
        return {**self.HOME_AWAKE, **changes}

    def test_both_asleep_hands_the_zone_back(self) -> None:
        states = self._with(
            **{"sensor.danny_charger_type": "wireless", "sensor.nancy_charger_type": "wireless"}
        )
        item = coordinator(running_plan(), states)
        item._notice_hand(_Event(BEDROOM, "heat", "off"))
        assert item._zones_handed_back() == set()

    def test_one_still_up_keeps_it(self) -> None:
        states = self._with(**{"sensor.danny_charger_type": "wireless"})
        item = coordinator(running_plan(), states)
        item._notice_hand(_Event(BEDROOM, "heat", "off"))
        assert item._zones_handed_back() == {"slaapkamer"}

    def test_the_one_who_is_away_does_not_have_to_sleep(self) -> None:
        """Somebody out is not somebody awake; the house is still turning in."""
        states = self._with(**{"person.nancy": "not_home", "sensor.danny_charger_type": "wireless"})
        item = coordinator(running_plan(), states)
        item._notice_hand(_Event(BEDROOM, "heat", "off"))
        assert item._zones_handed_back() == set()

    def test_an_empty_house_hands_it_back_as_well(self) -> None:
        """Nobody left means the case it was silenced for is over."""
        states = self._with(**{"person.danny": "not_home", "person.nancy": "not_home"})
        item = coordinator(running_plan(), states)
        item._notice_hand(_Event(BEDROOM, "heat", "off"))
        assert item._zones_handed_back() == set()

    def test_the_master_key_survives_an_empty_house(self) -> None:
        """De schakelaar is geen hand aan het apparaat en vervalt dus niet mee.

        Beide wegen naar een overgedragen zone staan los van elkaar: iemand die
        bij het apparaat op uit drukt, en de beheerder die de schakelaar omzet.
        Het eerste is een besluit van vanavond en hoort morgen niet meer te
        gelden; het tweede is een besluit dat je zelf terugdraait. Ze werden
        allebei bij bedtijd weggegooid, waardoor een zone die je met opzet had
        overgedragen de eerste nacht alweer meedeed - en het migratiedraaiboek,
        dat op die overdracht leunt, niet uitvoerbaar was.

        The switch is not a hand at the appliance and therefore does not lapse
        along with one. The two ways into a handed-over zone stand apart:
        somebody pressing off on the appliance, and the administrator throwing
        the switch. The first is tonight's decision and should not still hold
        tomorrow; the second is a decision you undo yourself. Both were thrown
        away at bedtime, so a zone you deliberately handed over rejoined on the
        first night - leaving the migration plan, which leans on that handover,
        impossible to carry out.
        """
        states = self._with(**{"person.danny": "not_home", "person.nancy": "not_home"})
        item = coordinator(running_plan(), states)
        item.zone_overrides["woonkamer"] = True
        item._zones_handed_back()
        assert item.zone_overrides == {"woonkamer": True}

    def test_the_master_key_survives_a_night(self) -> None:
        states = self._with(
            **{"sensor.danny_charger_type": "wireless", "sensor.nancy_charger_type": "wireless"}
        )
        item = coordinator(running_plan(), states)
        item.zone_overrides["woonkamer"] = True
        item._zones_handed_back()
        assert item.zone_overrides == {"woonkamer": True}

    def test_the_master_key_survives_a_house_in_use(self) -> None:
        item = coordinator(running_plan(), self.HOME_AWAKE)
        item.zone_overrides["woonkamer"] = True
        item._zones_handed_back()
        assert item.zone_overrides == {"woonkamer": True}

    def test_the_zone_stays_handed_over_through_the_night(self) -> None:
        """Wat de melders zien: de zone blijft van de beheerder."""
        states = self._with(
            **{"sensor.danny_charger_type": "wireless", "sensor.nancy_charger_type": "wireless"}
        )
        item = coordinator(running_plan(), states)
        item.zone_overrides["woonkamer"] = True
        assert item._overridden_zones() == {"woonkamer": True}

    def test_a_hand_at_the_appliance_still_lapses_beside_it(self) -> None:
        """De twee wegen staan los: de ene vervalt, de andere niet."""
        states = self._with(
            **{"sensor.danny_charger_type": "wireless", "sensor.nancy_charger_type": "wireless"}
        )
        item = coordinator(running_plan(), states)
        item.zone_overrides["woonkamer"] = True
        item._notice_hand(_Event(BEDROOM, "heat", "off"))
        assert item._overridden_zones() == {"woonkamer": True}

    def test_waking_up_does_not_hand_it_back_again(self) -> None:
        """Once given back it is gone; getting up cannot re-silence the zone."""
        asleep_states = self._with(
            **{"sensor.danny_charger_type": "wireless", "sensor.nancy_charger_type": "wireless"}
        )
        item = coordinator(running_plan(), asleep_states)
        item._notice_hand(_Event(BEDROOM, "heat", "off"))
        assert item._zones_handed_back() == set()
        assert item._handed_back == {}

    def test_without_residents_the_day_boundary_still_rules(self) -> None:
        """An installation nobody is tracked in falls back on the date."""
        item = coordinator(running_plan())
        item._notice_hand(_Event(BEDROOM, "heat", "off"))
        assert item._zones_handed_back() == {"slaapkamer"}


class TestItSurvivesARestart:
    """Een besluit van een mens hoort niet in het werkgeheugen alleen.

    Tot 6.4.2 stond een handmatige uitzetting alleen in het geheugen van de
    coordinator. Herstart Home Assistant - een update, een herstart om iets
    heel anders - en de zone deed weer gewoon mee, terwijl er iemand met de
    hand had gezegd: laat maar. Precies de fout die de vooruit-verzoeken in
    6.4.0 al hadden.

    A person's decision does not belong in working memory alone.

    Up to 6.4.2 a hand-back only lived in the coordinator's memory. Restart
    Home Assistant - an update, a restart over something else entirely - and
    the zone simply took part again, while somebody had said by hand: leave it.
    Exactly the fault the pre-conditioning requests already had in 6.4.0.
    """

    def _coordinator(self, stored: dict | None = None):
        class FakeStore:
            def __init__(self) -> None:
                self.written: dict | None = None

            def async_delay_save(self, writer, delay: int) -> None:
                self.written = writer()

            async def async_load(self):
                return stored

        class StandIn:
            def __init__(self) -> None:
                self._precondition: dict = {}
                self._precondition_bypass: set[str] = set()
                self._handed_back: dict[str, date] = {}
                self._store = FakeStore()

            def _preconditions_expire_at(self, until) -> None:
                pass

            _async_save_state = ClimateDirectorCoordinator._async_save_state
            _async_restore_state = ClimateDirectorCoordinator._async_restore_state

        return StandIn()

    def test_the_day_is_written_away(self) -> None:
        item = self._coordinator()
        item._handed_back = {"slaapkamer": date(2026, 8, 18)}
        item._async_save_state()
        assert item._store.written["handed_back"] == {"slaapkamer": "2026-08-18"}

    async def test_today_comes_back(self) -> None:
        today = dt_util.now().date()
        item = self._coordinator({"handed_back": {"slaapkamer": today.isoformat()}})
        await item._async_restore_state()
        assert item._handed_back == {"slaapkamer": today}

    async def test_yesterday_does_not(self) -> None:
        """The date is the whole expiry, restart or no restart."""
        yesterday = dt_util.now().date() - timedelta(days=1)
        item = self._coordinator({"handed_back": {"slaapkamer": yesterday.isoformat()}})
        await item._async_restore_state()
        assert item._handed_back == {}

    async def test_an_older_file_without_the_key_reads_as_nothing(self) -> None:
        """No migration needed for a key that was never there."""
        item = self._coordinator({"until": {}, "bypass": []})
        await item._async_restore_state()
        assert item._handed_back == {}

    async def test_rubbish_in_the_file_does_not_stop_the_load(self) -> None:
        item = self._coordinator({"handed_back": {"slaapkamer": "not a date"}})
        await item._async_restore_state()
        assert item._handed_back == {}


class TestItIsWrittenAwayWhenItChanges:
    """Bewaren op het moment zelf, niet bij het afsluiten: een herstart is zelden netjes.

    Saving as it happens rather than on shutdown: a restart is rarely tidy.
    """

    def test_switching_it_off_by_hand_is_saved(self) -> None:
        item = coordinator(running_plan())
        item._notice_hand(_Event(BEDROOM, "heat", "off"))
        assert item.saved == 1

    def test_switching_it_back_on_is_saved_too(self) -> None:
        item = coordinator(running_plan())
        item._notice_hand(_Event(BEDROOM, "heat", "off"))
        item._notice_hand(_Event(BEDROOM, "off", "heat"))
        assert item.saved == 2
        assert item._handed_back == {}

    def test_our_own_command_writes_nothing(self) -> None:
        """The director standing an appliance down is not a hand at the appliance."""
        item = coordinator(idle_plan())
        item._notice_hand(_Event(BEDROOM, "heat", "off"))
        assert item.saved == 0

    def test_a_day_that_already_stood_there_writes_nothing(self) -> None:
        """After a restore the same day is already known; nothing changed."""
        item = coordinator(running_plan())
        item._handed_back = {"slaapkamer": dt_util.now().date()}
        item._notice_hand(_Event(BEDROOM, "heat", "off"))
        assert item.saved == 0

    def test_on_and_off_again_are_both_written(self) -> None:
        """Two real changes, two writes: the second may not lean on the first."""
        item = coordinator(running_plan())
        item._notice_hand(_Event(BEDROOM, "heat", "off"))
        item._notice_hand(_Event(BEDROOM, "off", "cool"))
        item._notice_hand(_Event(BEDROOM, "cool", "off"))
        assert item.saved == 3
        assert set(item._handed_back) == {"slaapkamer"}

    def test_a_stale_day_falling_away_is_saved(self) -> None:
        item = coordinator(running_plan())
        item._handed_back = {"slaapkamer": dt_util.now().date() - timedelta(days=1)}
        assert item._zones_handed_back() == set()
        assert item.saved == 1

    def test_reading_it_again_writes_nothing(self) -> None:
        item = coordinator(running_plan())
        item._handed_back = {"slaapkamer": dt_util.now().date()}
        item._zones_handed_back()
        item._zones_handed_back()
        assert item.saved == 0
