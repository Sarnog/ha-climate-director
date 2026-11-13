"""Formulieropbouw: de ingang die de configuratiecode al kent.

Form building: the entrance the configuration code already knows.
"""

from __future__ import annotations

from .form_circuits import (
    circuit as circuit,
)
from .form_circuits import (
    circuit_priorities as circuit_priorities,
)
from .form_circuits import (
    circuit_priority as circuit_priority,
)
from .form_circuits import (
    circuits as circuits,
)
from .form_circuits import (
    generator as generator,
)
from .form_circuits import (
    generators as generators,
)
from .form_common import (
    ADD as ADD,
)
from .form_common import (
    BACK as BACK,
)
from .form_common import (
    CONF_NAME as CONF_NAME,
)
from .form_common import (
    EXIT as EXIT,
)
from .form_common import (
    EXIT_DROP as EXIT_DROP,
)
from .form_common import (
    EXIT_KEEP as EXIT_KEEP,
)
from .form_common import (
    add_option as add_option,
)
from .form_common import (
    back_option as back_option,
)
from .form_common import (
    exit_row as exit_row,
)
from .form_common import (
    group_label as group_label,
)
from .form_common import (
    managed_entities as managed_entities,
)
from .form_common import (
    save as save,
)
from .form_common import (
    source_options as source_options,
)
from .form_common import (
    user as user,
)
from .form_common import (
    window_label as window_label,
)
from .form_installation import (
    energy as energy,
)
from .form_installation import (
    exclusive as exclusive,
)
from .form_installation import (
    exclusives as exclusives,
)
from .form_installation import (
    quiet as quiet,
)
from .form_installation import (
    quiets as quiets,
)
from .form_installation import (
    settings as settings,
)
from .form_openings import opening as opening
from .form_openings import openings as openings
from .form_residents import (
    resident as resident,
)
from .form_residents import (
    residents as residents,
)
from .form_residents import (
    window as window,
)
from .form_residents import (
    windows as windows,
)
from .form_zones import source as source
from .form_zones import sources as sources
from .form_zones import zone as zone
from .form_zones import zones as zones

__all__ = [
    "ADD",
    "BACK",
    "CONF_NAME",
    "EXIT",
    "EXIT_DROP",
    "EXIT_KEEP",
    "add_option",
    "back_option",
    "circuit",
    "circuit_priorities",
    "circuit_priority",
    "circuits",
    "exclusive",
    "exclusives",
    "exit_row",
    "generator",
    "generators",
    "group_label",
    "managed_entities",
    "opening",
    "openings",
    "quiet",
    "quiets",
    "resident",
    "residents",
    "save",
    "energy",
    "settings",
    "source",
    "source_options",
    "sources",
    "user",
    "window",
    "window_label",
    "windows",
    "zone",
    "zones",
]
