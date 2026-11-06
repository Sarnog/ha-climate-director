"""Het seizoen als bron van de toegestane taak.

The season as the source of the allowed duty."""

from __future__ import annotations

import pytest
from harness_live import (
    start_house,
    stop_house,
)
from live_helpers import (
    LIVING,
    hot_world,
    summer_house,
)

from custom_components.climate_director.const import DOMAIN
from custom_components.climate_director.engine import Season


class TestTheSeasonSetting:
    """De vier manieren waarop het seizoen bepaald kan worden.

    The four ways the season can be settled.
    """

    async def test_pinned_to_summer_lets_the_room_cool(self) -> None:
        home = await start_house(summer_house({"source": "summer"}), states=hot_world())
        try:
            assert home.coordinator.world.season is Season.SUMMER
            assert home.state(LIVING) == "cool"
        finally:
            await stop_house(home)

    async def test_pinned_to_winter_refuses_to_cool(self) -> None:
        """Zesentwintig graden in de winter: de airco blijft uit.

        De gemelde reden is die van de koelkant (`season_blocks_mode`): een
        tevreden verwarmingskant mag een geblokkeerde koeltaak niet maskeren.

        Twenty-six degrees in winter: the air conditioner stays off. The
        reported reason is the cooling side's (`season_blocks_mode`): a
        satisfied heating duty must not mask a blocked cooling duty.
        """
        home = await start_house(summer_house({"source": "winter"}), states=hot_world())
        try:
            assert home.state(LIVING) == "off"
            assert home.values("zone_woonkamer_source")["granted"] == "neutral"
        finally:
            await stop_house(home)

    @pytest.mark.parametrize(
        ("reported", "cools"),
        [
            ("summer", True),
            ("zomer", True),
            ("Zomer", True),
            ("été", True),
            ("winter", False),
            ("herfst", False),
            ("lente", False),
            ("onzin", False),
            ("unavailable", False),
        ],
    )
    async def test_an_entity_may_name_the_season_in_several_languages(
        self, reported: str, cools: bool
    ) -> None:
        home = await start_house(
            summer_house({"source": "entity", "entity_id": "sensor.seizoen"}),
            states={**hot_world(), "sensor.seizoen": (reported, {})},
        )
        try:
            assert (home.state(LIVING) == "cool") is cools
        finally:
            await stop_house(home)

    async def test_the_month_table_decides_on_automatic(self) -> None:
        """Augustus staat in de standaard zomermaanden, dus koelen mag.

        August is in the default summer months, so cooling is allowed.
        """
        home = await start_house(
            summer_house({"source": "auto", "summer_months": [8]}), states=hot_world()
        )
        try:
            expected = Season.SUMMER if home.coordinator.world.now.month == 8 else Season.WINTER
            assert home.coordinator.world.season is expected
        finally:
            await stop_house(home)

    async def test_the_select_overrides_the_season(self) -> None:
        """Eén draai aan de select zet winter opzij, en terug op auto weer niet.

        One turn of the select overrides winter, and back to auto it no longer
        does.
        """
        home = await start_house(summer_house({"source": "winter"}), states=hot_world())
        try:
            assert home.state(LIVING) == "off"
            await home.call(
                "select",
                "select_option",
                {"entity_id": home.by_key("season"), "option": "summer"},
            )
            await home.evaluate()
            assert home.coordinator.season_override is Season.SUMMER
            assert home.coordinator.world.season is Season.SUMMER
            assert home.state(LIVING) == "cool"

            await home.call(
                "select",
                "select_option",
                {"entity_id": home.by_key("season"), "option": "auto"},
            )
            await home.evaluate()
            assert home.coordinator.season_override is None
            assert home.coordinator.world.season is Season.WINTER
        finally:
            await stop_house(home)

    async def test_the_select_reports_a_season_that_locks_a_duty_out(self) -> None:
        """Staat de select op een seizoen dat een taak uitsluit, dan valt dat op.

        The select standing on a season that locks a duty out gets reported.
        """
        from homeassistant.helpers import issue_registry as ir

        home = await start_house(summer_house({"source": "summer"}), states=hot_world())
        try:
            await home.evaluate()
            registry = ir.async_get(home.hass)
            issue_id = f"season_excludes_mode_{home.entry.entry_id}"
            assert registry.async_get_issue(DOMAIN, issue_id) is None

            await home.call(
                "select",
                "select_option",
                {"entity_id": home.by_key("season"), "option": "winter"},
            )
            await home.evaluate()
            assert registry.async_get_issue(DOMAIN, issue_id) is not None

            await home.call(
                "select",
                "select_option",
                {"entity_id": home.by_key("season"), "option": "auto"},
            )
            await home.evaluate()
            assert registry.async_get_issue(DOMAIN, issue_id) is None
        finally:
            await stop_house(home)
