"""Het rooster als poort.

The schedule as a gate.
"""

from __future__ import annotations

from .models import HOLIDAY_WEEKDAY, DirectorConfig
from .night import asleep
from .world import WorldState


def schedule_open(config: DirectorConfig, world: WorldState) -> bool:
    """Return whether the household's schedules allow regulating right now.

    Only residents who actually have a schedule take part. Someone without one
    neither opens the gate nor holds it shut: they have said nothing about when
    they want the house to join in, and silence is not a vote either way.

    A participant does two things. Awake, with their window open, they open the
    gate. At home and asleep, with their window not yet open, they hold it shut
    - which is what makes the house wait for the last sleeper on a weekend
    morning instead of starting the moment the first person is up. Once their
    own window opens, their sleeping stops counting: the schedule said they
    meant to be up by then.
    """
    moment = world.now.time()
    weekday = world.now.weekday()
    holiday = world.holiday_mode

    effective = HOLIDAY_WEEKDAY if holiday else weekday
    participants = [
        resident
        for resident in config.residents
        if resident.takes_part(holiday=holiday, weekday=effective)
    ]
    if not participants:
        return False

    for resident in participants:
        state = world.resident(resident.resident_id)
        if (
            state.home
            and asleep(resident, world)
            and not resident.wants_climate_at(moment, weekday, holiday=holiday)
        ):
            return False

    return any(
        resident.wants_climate_at(moment, weekday, holiday=holiday)
        for resident in participants
        if counts_towards_schedule(config, world, resident.resident_id)
    )


def counts_towards_schedule(config: DirectorConfig, world: WorldState, resident_id: str) -> bool:
    """Return whether a resident's own schedule may open the schedule gate.

    Being home is required outright: a schedule says when somebody wants the
    house warm, not that it should be warm without them. Sleep mirrors the
    sleep gate instead of being hard-coded, so with `require_awake` off a
    schedule still counts while its owner sleeps.
    """
    resident = next((item for item in config.residents if item.resident_id == resident_id), None)
    if resident is None or not world.resident(resident_id).home:
        return False
    return not (config.gates.require_awake and asleep(resident, world))
