"""Het oppervlak van de optiesstroom dat de stappen en formulieren gebruiken.

The options-flow surface the steps and forms use.

De stappen staan als functies in de `flow_*`-modules en krijgen de stroom als
eerste argument. Zonder deze declaratie moest elke module `ClimateDirectorOptionsFlow`
uit `config_flow.py` terugimporteren onder `TYPE_CHECKING`, terwijl `config_flow.py`
die modules importeert: een kring die alleen het type raakte. Deze basisklasse
noemt alleen leden (de cursors, de lijsten en de stappen) en draagt geen
methodelichaam, dus er is bij het draaien niets dat een echte methode van de
stroom kan overschaduwen.

The steps stand as functions in the `flow_*` modules and receive the flow as their
first argument. Without this declaration every module had to import
`ClimateDirectorOptionsFlow` back from `config_flow.py` under `TYPE_CHECKING`, while
`config_flow.py` imports those modules: a cycle that touched only the type. This
base class names members only (the cursors, the lists and the steps) and carries no
method body, so at run time nothing comes about that could shadow a real method of
the flow.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.config_entries import ConfigFlowResult, OptionsFlow


class FlowSurface(OptionsFlow):
    """What the step functions and the forms read and call on the options flow."""

    _installation: dict[str, Any]
    _zone_index: int | None
    _source_index: int | None
    _circuit_index: int | None
    _priority_zone_id: str | None
    _resident_index: int | None
    _window_index: int | None
    _index: int | None
    _renamed_house_wide: set[str]

    _list: Callable[[str], list[dict[str, Any]]]
    _groups: Callable[[], list[list[str]]]
    _priority_clash: Callable[[str, int], bool]
    _current_circuit: Callable[[], dict[str, Any] | None]
    _current_resident: Callable[[], dict[str, Any] | None]
    _current_zone: Callable[[], dict[str, Any] | None]
    _zones_on: Callable[[dict[str, Any]], list[dict[str, Any]]]
    _drop_zone_references: Callable[[dict[str, Any]], None]
    _drop_source_references: Callable[[set[str]], None]

    async_step_circuit: Callable[..., Awaitable[ConfigFlowResult]]
    async_step_circuit_priorities: Callable[..., Awaitable[ConfigFlowResult]]
    async_step_circuit_priority: Callable[..., Awaitable[ConfigFlowResult]]
    async_step_circuits: Callable[..., Awaitable[ConfigFlowResult]]
    async_step_exclusive: Callable[..., Awaitable[ConfigFlowResult]]
    async_step_exclusives: Callable[..., Awaitable[ConfigFlowResult]]
    async_step_generator: Callable[..., Awaitable[ConfigFlowResult]]
    async_step_generators: Callable[..., Awaitable[ConfigFlowResult]]
    async_step_init: Callable[..., Awaitable[ConfigFlowResult]]
    async_step_opening: Callable[..., Awaitable[ConfigFlowResult]]
    async_step_openings: Callable[..., Awaitable[ConfigFlowResult]]
    async_step_quiet: Callable[..., Awaitable[ConfigFlowResult]]
    async_step_quiets: Callable[..., Awaitable[ConfigFlowResult]]
    async_step_resident: Callable[..., Awaitable[ConfigFlowResult]]
    async_step_residents: Callable[..., Awaitable[ConfigFlowResult]]
    async_step_source: Callable[..., Awaitable[ConfigFlowResult]]
    async_step_sources: Callable[..., Awaitable[ConfigFlowResult]]
    async_step_window: Callable[..., Awaitable[ConfigFlowResult]]
    async_step_windows: Callable[..., Awaitable[ConfigFlowResult]]
    async_step_zone: Callable[..., Awaitable[ConfigFlowResult]]
    async_step_zones: Callable[..., Awaitable[ConfigFlowResult]]
