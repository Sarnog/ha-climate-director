"""R27-2: een opening zonder `opening_id` houdt zijn id in de interface.

R27-2: an opening without an `opening_id` keeps its id in the interface.

`serialise` leidt een ontbrekend `opening_id` af uit de `entity_id` van de
sensor; `config_flow.async_step_opening` leidde hem af uit de **naam**. De
options flow leest de ruwe opslag, dus voor een legacy-installatie (de vijf
productie-openingen hebben geen `opening_id` en geen naam) wisselde de eerste
bewerking in de UI het id - en daarmee de `unique_id` van de
overbruggingsschakelaar. Dit bestand pint de eigenschap vast in het live harnas,
met de échte entiteitenregistratie: er is precies één afleiding, dezelfde in de
opslaglezer en in de UI, en een bestaande schakelaar overleeft het toekennen van
een naam. Bovendien is de schakelaarnaam van een legacy-opening de friendly name
van de sensor, zodat de vijf productieschakelaars leesbaar heten zonder dat
iemand ze eerst hoeft te bewerken.

`serialise` derives a missing `opening_id` from the sensor's `entity_id`;
`config_flow.async_step_opening` derived it from the **name**. The options flow
reads the raw storage, so for a legacy installation (the five production
openings carry neither an `opening_id` nor a name) the first edit in the UI
switched the id around - and with it the bypass switch's `unique_id`. This file
pins the property down in the live harness, against the real entity registry:
there is exactly one derivation, the same one in the storage reader and in the
UI, and an existing switch survives being given a name. On top of that, the
switch of a legacy opening is named after the sensor's friendly name, so the
five production switches read properly without anybody having to edit them
first.
"""

from __future__ import annotations

from typing import Any

import pytest
from harness_live import LiveHome, settings, source, start_house, stop_house, zone

from custom_components.climate_director.const import CONF_INSTALLATION

BACK_DOOR = "binary_sensor.achterdeur"
SKYLIGHT = "cover.dakraam"


def installation() -> dict[str, Any]:
    """Return the production shape: legacy openings without an id or a name.

    Precies zoals de vijf productie-openingen er in de opslag staan: alleen een
    `entity_id`. De afleiding hoort ze allebei een id te geven dat niet meer
    verandert als iemand er later een naam aan hangt.

    Exactly as the five production openings sit in storage: an `entity_id` and
    nothing else. The derivation is supposed to give both of them an id that no
    longer changes once somebody hangs a name on it.
    """
    return {
        "zones": [
            zone(
                "woonkamer",
                sources=[source("woonkamer_ketel", "climate.woonkamer")],
                indoor_sensor="sensor.woonkamer",
                heat=settings(21.0, 20.0),
            )
        ],
        "outdoor_sensor": "sensor.buiten",
        "openings": [
            {"entity_id": BACK_DOOR, "zone_ids": ["woonkamer"], "open_state": "on", "delay": 0},
            {"entity_id": SKYLIGHT, "zone_ids": [], "open_state": "open", "delay": 0},
        ],
    }


def world() -> dict[str, tuple[str, dict[str, Any]]]:
    """Return a settled house with both openings closed."""
    return {
        "sensor.woonkamer": ("21.0", {}),
        "sensor.buiten": ("4.0", {}),
        "climate.woonkamer": ("off", {"hvac_modes": ["heat", "off"]}),
        BACK_DOOR: ("off", {"friendly_name": "Achterdeur contact"}),
        SKYLIGHT: ("closed", {"friendly_name": "Dakraam zolder"}),
    }


async def menu(home: LiveHome, step: str) -> Any:
    """Open the options flow and walk into one menu entry."""
    flow = home.hass.config_entries.options
    result = await flow.async_init(home.entry.entry_id)
    return await flow.async_configure(result["flow_id"], {"next_step_id": step})


async def save(home: LiveHome, flow_id: str) -> dict[str, Any]:
    """Save and hand back the installation as it was stored."""
    flow = home.hass.config_entries.options
    result = await flow.async_configure(flow_id, {"next_step_id": "save"})
    if result["type"] == "form":
        assert result["step_id"] == "save"
        result = await flow.async_configure(flow_id, {"when_done": "keep"})
    await home.hass.async_block_till_done()
    assert result["type"] == "create_entry"
    return home.entry.options[CONF_INSTALLATION]


def opening_of(stored: dict[str, Any], entity_id: str) -> dict[str, Any]:
    """Return the stored opening that watches `entity_id`."""
    return next(item for item in stored["openings"] if item["entity_id"] == entity_id)


def switch_name(home: LiveHome, entity_id: str) -> str:
    """Return the friendly name of one opening's bypass switch."""
    state = home.hass.states.get(home.by_key(f"opening_{entity_id}_bypass"))
    assert state is not None, "geen overbruggingsschakelaar voor deze opening"
    return state.name


class TestALegacyOpeningKeepsItsId:
    """Een bestaande overbruggingsschakelaar overleeft het geven van een naam."""

    @pytest.mark.parametrize(
        ("index", "entity_id", "label", "zone_ids", "open_state"),
        [
            (0, BACK_DOOR, "Achterdeur beneden", ["woonkamer"], "on"),
            (1, SKYLIGHT, "Dakraam zolder", [], "open"),
        ],
    )
    async def test_giving_a_legacy_opening_a_name_keeps_its_switch(
        self, index: int, entity_id: str, label: str, zone_ids: list[str], open_state: str
    ) -> None:
        """Het id blijft de sensor, ook nu de opening een naam krijgt.

        De options flow laadt de ruwe opslag; zonder normalisatie leidt het
        bewerkscherm het id af uit de naam die je net intypt, en dan wisselt de
        `unique_id`. Daarom is de schakelaar van vóór en na het opslaan dezelfde
        entiteit, en staat de afgeleide id meteen in de opslag.

        The options flow loads the raw storage; without normalisation the edit
        screen derives the id from the name you just typed, and then the
        `unique_id` switches. Hence the switch is the same entity before and
        after saving, and the derived id stands in storage right away.
        """
        home = await start_house(installation(), states=world())
        try:
            before = home.registered()
            flow = home.hass.config_entries.options
            result = await flow.async_init(home.entry.entry_id)
            result = await flow.async_configure(result["flow_id"], {"next_step_id": "openings"})
            result = await flow.async_configure(result["flow_id"], {"opening": str(index)})
            assert result["step_id"] == "opening"
            result = await flow.async_configure(
                result["flow_id"],
                {
                    "name": label,
                    "entity_id": entity_id,
                    "zone_ids": zone_ids,
                    "open_state": open_state,
                    "delay": 0,
                    "delete": False,
                    "when_done": "keep",
                },
            )
            stored = await save(home, result["flow_id"])

            assert len(stored["openings"]) == len(installation()["openings"])
            edited = stored["openings"][index]
            assert edited["entity_id"] == entity_id, edited
            assert edited["opening_id"] == entity_id, edited
            assert edited["name"] == label, edited

            untouched = opening_of(stored, SKYLIGHT if entity_id == BACK_DOOR else BACK_DOOR)
            assert untouched["opening_id"] == untouched["entity_id"], untouched

            assert home.registered() == before
        finally:
            await stop_house(home)

    async def test_a_new_opening_still_gets_its_id_from_its_name(self) -> None:
        """Een nieuwe opening houdt zijn id uit de naam die je invult.

        De normalisatie raakt alleen bestaande opslag zonder id: een nieuwe
        opening is nog nergens bekend, dus daar blijft `config_flow._unique_id`
        op de naam staan.

        The normalisation only touches existing storage without an id: a new
        opening is not known anywhere yet, so there `config_flow._unique_id`
        stays on the name.
        """
        home = await start_house(installation(), states=world())
        try:
            flow = home.hass.config_entries.options
            result = await flow.async_init(home.entry.entry_id)
            result = await flow.async_configure(result["flow_id"], {"next_step_id": "openings"})
            result = await flow.async_configure(result["flow_id"], {"opening": "add_new"})
            result = await flow.async_configure(
                result["flow_id"],
                {
                    "name": "Voordeur",
                    "entity_id": "binary_sensor.voordeur",
                    "zone_ids": [],
                    "open_state": "on",
                    "delay": 0,
                    "delete": False,
                    "when_done": "keep",
                },
            )
            stored = await save(home, result["flow_id"])

            assert opening_of(stored, "binary_sensor.voordeur")["opening_id"] == "voordeur"
            for entity_id in (BACK_DOOR, SKYLIGHT):
                legacy = opening_of(stored, entity_id)
                assert legacy["opening_id"] == entity_id, legacy
        finally:
            await stop_house(home)


class TestTheSwitchNamesTheSensor:
    """De schakelaar van een legacy-opening heet naar de sensor."""

    async def test_a_legacy_opening_reads_as_its_sensor(self) -> None:
        """Zonder naam valt de schakelaar terug op de sensor, niet op zijn id.

        Een opening zonder naam heet in de opslag naar zijn `opening_id`, en dat
        is de `entity_id`. De schakelaar leest dan als "Overbrugging
        binary_sensor.achterdeur"; de friendly name van de sensor is de eerste
        leesbare aanduiding.

        Without a name the switch falls back to the sensor, not to its id. An
        opening without a name is called after its `opening_id` in storage, and
        that is the `entity_id`. The switch then reads as "Bypass
        binary_sensor.achterdeur"; the sensor's friendly name is the first
        readable label.
        """
        home = await start_house(installation(), states=world())
        try:
            name = switch_name(home, BACK_DOOR)
        finally:
            await stop_house(home)
        assert "Achterdeur contact" in name, name
        assert BACK_DOOR not in name, name

    async def test_a_named_opening_uses_its_own_name(self) -> None:
        """Een eigen naam van de opening gaat vóór de sensor.

        The opening's own name wins over the sensor.
        """
        data = installation()
        data["openings"][0]["name"] = "Achterdeur beneden"
        home = await start_house(data, states=world())
        try:
            name = switch_name(home, BACK_DOOR)
        finally:
            await stop_house(home)
        assert "Achterdeur beneden" in name, name
        assert "Achterdeur contact" not in name, name
