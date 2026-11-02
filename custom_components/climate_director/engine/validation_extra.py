"""Validatieregels die niet in het model thuishoren.

Validation rules that do not belong in the model.

`models.py` draagt het model en de algemene regels; deze module draagt de
controles die een instelling als dood of als onmogelijk aanwijzen. Ze staan hier
zodat `models.py` niet verder groeit dan de maat toestaat, en zodat elke regel
apart te lezen en te toetsen is. `models._RULES` neemt ze onderaan over.

`models.py` carries the model and the general rules; this module carries the
checks that mark a setting as dead or impossible. They live here so that
`models.py` does not grow beyond the measure, and so that each rule can be read
and tested on its own. `models._RULES` adopts them at the bottom.
"""

from __future__ import annotations

from collections.abc import Iterator

from .models import DirectorConfig, Problem, TimeWindow


def _windows(config: DirectorConfig) -> Iterator[tuple[str, TimeWindow]]:
    """Yield every configured window with a readable label."""
    for window in config.gates.quiet_windows:
        yield "quiet window", window
    guest = config.gates.guest_window
    if guest is not None:
        yield "guest window", guest
    for resident in config.residents:
        if resident.sleep_window is not None:
            yield f"sleep window of {resident.name or resident.resident_id}", resident.sleep_window
        for window in resident.windows:
            yield f"schedule of {resident.name or resident.resident_id}", window


def _rule_dead_sleep_settings(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for a sleep setting that can never take effect.

    Een slaapvenster, uitslapen of uiterste tijd zonder slaapsensor kan nooit
    iets doen: de bewoner slaapt dan nooit. De opsta-rem is alleen dood als er
    ook een slaapvenster staat; zonder venster telt de slaapsensor de klok rond
    en remt de opsta-rem wel.

    A sleep window, sleeping in or a deadline without a sleep sensor can never
    do anything: the resident then never sleeps. The rise brake is dead only
    when a sleep window is set too; without a window the sleep sensor counts
    around the clock and the rise brake does brake.
    """
    for resident in config.residents:
        if resident.sleep_entity:
            continue
        dead: list[str] = []
        if resident.sleep_window is not None:
            dead.append("sleep window")
        if resident.sleep_in is not None:
            dead.append("sleep in until")
        if resident.wake_deadline is not None:
            dead.append("wait for this sleeper until")
        if resident.rise_brake is not None and resident.sleep_window is not None:
            dead.append("rise from")
        if dead:
            yield Problem(
                "resident_settings_without_sleep_sensor",
                f"resident {resident.resident_id} has sleep settings but no sleep sensor, "
                f"so they can never take effect: {', '.join(dead)}",
                resident=resident.name or resident.resident_id,
                settings=", ".join(dead),
            )


def _rule_windows_without_length(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for a window whose start equals its end.

    Zo'n venster is nooit open: het begin valt samen met het einde, en de
    vergelijking leest dat als een leeg venster. Dat is van buiten niet te
    onderscheiden van een venster dat iemand expres dicht liet.

    Such a window is never open: its start coincides with its end, and the
    comparison reads that as an empty window. From the outside that cannot be
    told apart from a window somebody deliberately left shut.
    """
    for label, window in _windows(config):
        if window.start == window.end:
            yield Problem(
                "window_without_length",
                f"{label} starts and ends at the same time, so it is never open",
                window=label,
            )


def _rule_guest_window_half_filled(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for a guest window with only one end filled in.

    Half een venster is geen venster: de gastenmodus geldt dan de hele dag.
    Dat is een stille verbreding van wat iemand invulde.

    Half a window is no window: guest mode then applies all day. That is a
    silent widening of what somebody filled in.
    """
    if config.gates.guest_window_incomplete:
        yield Problem(
            "guest_window_half_filled",
            "the guest window has only one end filled in, so guest mode applies all day",
        )


def _rule_cover_open_state(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint for a cover opening that never reports open.

    Een `cover` meldt `open`, geen `on`. Staat de openingsstand op `on`, dan
    telt het dakraam nooit als open en stookt de installatie er dwars doorheen.

    A `cover` reports `open`, not `on`. With the opening state on `on`, the
    skylight never counts as open and the installation heats straight through
    it.
    """
    for opening in config.openings:
        if opening.entity_id.startswith("cover.") and opening.open_state != "open":
            yield Problem(
                "cover_opening_without_open_state",
                f"opening {opening.entity_id} is a cover but its open state is "
                f"{opening.open_state!r}, so it never counts as open",
                opening=opening.name or opening.entity_id,
                open_state=opening.open_state,
            )


def _rule_stuck_below_configured_rest(config: DirectorConfig) -> Iterator[Problem]:
    """Yield a complaint when the stuck time is shorter than a configured rest.

    De vastloopmelder staat op de wachtredenen, en een ingestelde circuit- of
    bronrust staat daar ook op. Is de vastlooptijd korter, dan meldt de sensor
    een apparaat als vastgelopen terwijl het netjes zijn rust neemt.

    The stuck notice sits on the waiting reasons, and a configured circuit or
    source rest sits there too. With a shorter stuck time the sensor reports an
    appliance as stuck while it is simply taking its rest.
    """
    stuck = config.stuck_after.total_seconds()
    if stuck <= 0:
        return
    for circuit in config.circuits:
        for label, rest in (
            ("minimum cycle time", circuit.min_cycle_time),
            ("minimum switch interval", circuit.min_family_switch_interval),
        ):
            if rest.total_seconds() > stuck:
                yield Problem(
                    "stuck_after_below_configured_rest",
                    f"the stuck-detection time is below the circuit's {label}",
                    subject=circuit.name or circuit.circuit_id,
                    label=label,
                    rest=str(int(rest.total_seconds())),
                    stuck_after=str(int(stuck)),
                )
    for _zone, source in config.sources():
        source_rest = source.min_cycle_time
        if source_rest is not None and source_rest.total_seconds() > stuck:
            yield Problem(
                "stuck_after_below_configured_rest",
                "the stuck-detection time is below the source's minimum cycle time",
                subject=source.name or source.entity_id,
                label="minimum cycle time",
                rest=str(int(source_rest.total_seconds())),
                stuck_after=str(int(stuck)),
            )


def _timing_problems(config: DirectorConfig) -> list[Problem]:
    """Return a complaint about switch timings on a circuit that never switches.

    Een buitenunit die verwarmen en koelen tegelijk aankan wisselt nooit van
    taak, dus een omschakelpauze en een minimale looptijd voor die wissel doen
    daar niets. Ze staan er dan wel, en dan ga je ervan uit dat ze werken.

    De kortcyclustijd en de capaciteitsgrens blijven wél gelden; die gaan over
    losse units en niet over de taak van het circuit.

    An outdoor unit that can heat and cool at once never switches duty, so a
    switch pause and a minimum run before that switch do nothing there. They
    still sit in the settings, and then you assume they work.

    The short-cycle time and the capacity limit do still apply; those are about
    individual units rather than about the circuit's duty.
    """
    return [
        Problem(
            "switch_timings_without_a_switch",
            f"circuit {circuit.circuit_id} can run both duties at once, so its switch pause "
            "and minimum run before switching never apply",
            circuit=circuit.name or circuit.circuit_id,
        )
        for circuit in config.circuits
        if circuit.simultaneous_heat_cool
        and (circuit.family_switch_delay or circuit.min_family_switch_interval)
    ]


EXTRA_RULES = (
    _timing_problems,
    _rule_dead_sleep_settings,
    _rule_windows_without_length,
    _rule_guest_window_half_filled,
    _rule_cover_open_state,
    _rule_stuck_below_configured_rest,
)
