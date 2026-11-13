"""Run each mutation in a throwaway copy of the repo and report what stays green.

Elke mutatie draait in een kopie van de repo, en alleen tegen de toetsen die het
gemuteerde bestand raken (`tests/impact_map.json`, via `script/select_tests.py`);
zonder kaart de volledige suite. Een mutatie draait alleen als haar deel veranderde
(het gemuteerde bestand, een van haar toetsen, of de probe zelf) ten opzichte van
`CD_BASE`; zonder bekende basis draaien ze allemaal. Een mutatie die groen blijft is
een gat: geen enkele test bewaakt die eigenschap. De uitvoer is een lijst van die
gaten; de baan is niet-blokkerend, zodat een gat de rest van de CI niet tegenhoudt,
maar zichtbaar is.

Twee dingen houden de probe kort. Pytest stopt bij de eerste toets die valt (`-x`):
één rode toets is genoeg om een mutatie gevangen te noemen, de rest van de suite
zegt daar niets meer over. En de mutaties draaien naast elkaar, één per processor
(`CD_MUTATION_WORKERS` zet het aantal); elke mutatie heeft toch al haar eigen kopie.

Each mutation runs in a throwaway copy of the repo, and only against the tests that
touch the mutated file (`tests/impact_map.json`, through `script/select_tests.py`);
without a map the full suite. A mutation only runs when its part changed (the
mutated file, one of its tests, or the probe itself) against `CD_BASE`; without a
known base they all run. A mutation that stays green is a hole: no test guards that
property. The output is the list of those holes; the job is non-blocking, so a hole
does not hold up the rest of CI but stays visible.

Two things keep the probe short. Pytest stops at the first test that fails (`-x`):
one red test is enough to call a mutation caught, the rest of the suite says nothing
more about it. And the mutations run side by side, one per processor
(`CD_MUTATION_WORKERS` sets the number); every mutation has its own copy anyway.

Een mutatie kan pytest laten hangen (een lus die niet meer eindigt, een toets die
wacht op een klok die niet loopt). Daarom heeft elke mutatie een tijdslimiet
(`CD_MUTATION_TIMEOUT`, seconden): daarna wordt de hele procesgroep gestopt en telt de
mutatie als gevangen, want een mutant die de suite laat hangen is net zo merkbaar als
een rode toets. De uitvoer zegt dan `gevangen (timeout)`.

A mutation can make pytest hang (a loop that never ends, a test waiting on a clock
that does not run). So every mutation has a time limit (`CD_MUTATION_TIMEOUT`,
seconds): after it the whole process group is stopped and the mutation counts as
caught, since a mutant that hangs the suite is as noticeable as a red test. The
output then says `gevangen (timeout)`.
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
# Standaardlimiet per mutatie in seconden / default limit per mutation in seconds.
DEFAULT_TIMEOUT = 480
sys.path.insert(0, str(REPO / "script"))
import select_tests as sel  # noqa: E402

MUTATIONS = [
    {
        "name": "passed-over-meldt-alles",
        "file": "custom_components/climate_director/engine/sources.py",
        "old": (
            "not world.climate(source.entity_id).available\n"
            "            or source.entity_id in refused\n"
            "            or source.entity_id in blocked"
        ),
        "new": "True",
    },
    {
        "name": "duits-formeel-weer-toegestaan",
        "file": "custom_components/climate_director/translations/de.json",
        "old": "du ",
        "new": "Sie ",
    },
    {
        "name": "circuitlus-draait-niet",
        "file": "custom_components/climate_director/engine/grants.py",
        "old": "    while True:",
        "new": "    while False:",
    },
    {
        "name": "laatste-doorschuiving-blijft-liggen",
        "file": "custom_components/climate_director/engine/grants.py",
        "old": "        if not changed:\n            break",
        "new": "        if True:\n            break",
    },
    {
        "name": "bron-rusttijd-genegeerd",
        "file": "custom_components/climate_director/engine/grants.py",
        "old": 'circuit = _SOLO if not rest else Circuit("", "", (), True, min_cycle_time=rest)',
        "new": "circuit = _SOLO",
    },
    {
        "name": "weggevallen-kamer-niet-hersteld",
        "file": "custom_components/climate_director/room_presence.py",
        "old": (
            "            if (current is None or unreadable(current.state)) "
            "and zone_id in occupied:\n"
            "                self._empty_since[zone_id] = now"
        ),
        "new": "            if False:\n                self._empty_since[zone_id] = now",
    },
    {
        "name": "opgeslagen-hand-toch-weg",
        "file": "custom_components/climate_director/state_store.py",
        "old": (
            "                if zone in self.override_before_restore "
            "and self.zone_overrides.get(zone, False)"
        ),
        "new": "                if self.zone_overrides.get(zone, False)",
    },
    {
        "name": "handstart-poort-dicht",
        "file": "custom_components/climate_director/engine/hand_start.py",
        "old": "    return zone_id in world.zone_hand_starts and reason in HAND_START_BRAKES",
        "new": "    return False",
    },
    {
        "name": "handstart-vervalt-nooit",
        "file": "custom_components/climate_director/hand_start.py",
        "old": (
            "                    or (readable and not brakes_remaining(self.config, world, zone, "
            "previous))"
        ),
        "new": "                    or False",
    },
    {
        "name": "handstart-knop-zonder-rem",
        "file": "custom_components/climate_director/hand_start.py",
        "old": (
            "        if not brakes_remaining(self.config, self.build_world(), zone, self.data):\n"
            "            return"
        ),
        "new": "        if False:\n            return",
    },
    {
        "name": "handstart-bron-zonder-autostart",
        "file": "custom_components/climate_director/hand_start.py",
        "old": "                if source.entity_id != entity_id or not source.autostart:",
        "new": "                if source.entity_id != entity_id:",
    },
    {
        "name": "handstart-deelt-niet",
        "file": "custom_components/climate_director/hand_start.py",
        "old": "                for zone_id in (zone.zone_id, *source.covers_zones):",
        "new": "                for zone_id in (zone.zone_id,):",
    },
    {
        "name": "handstart-eigen-aanzet-telt",
        "file": "custom_components/climate_director/hand_start.py",
        "old": ("        if self.we_wanted_it_on(entity_id, duty):\n            return"),
        "new": "        if False:\n            return",
    },
    {
        "name": "handstart-niet-bewaard",
        "file": "custom_components/climate_director/state_store.py",
        "old": '            "hand_starts": self._hand_starts_payload(),',
        "new": '            "hand_starts": {},',
    },
    {
        "name": "gebiedsconflict-aanroep-weg",
        "file": "custom_components/climate_director/engine/candidates.py",
        "old": "kept, dropped = takeover.area_clash(config, wishes, takeovers)",
        "new": "kept, dropped = dict(wishes), {}",
    },
    {
        "name": "gebiedsconflict-overnemer-niet-overgeslagen",
        "file": "custom_components/climate_director/engine/takeover.py",
        "old": "if len(area) < 2 or entity_id in taking:",
        "new": "if len(area) < 2:",
    },
    {
        "name": "gebiedsconflict-verliezers-en-eigenaars-verwisseld",
        "file": "custom_components/climate_director/engine/takeover.py",
        "old": "for loser in rivals if best else owners:",
        "new": "for loser in owners if best else rivals:",
    },
    {
        "name": "gebiedsconflict-verliezer-blijft-in-de-wensen",
        "file": "custom_components/climate_director/engine/takeover.py",
        "old": "dropped[loser.zone.zone_id] = kept.pop(loser.zone.zone_id)",
        "new": "dropped[loser.zone.zone_id] = kept.get(loser.zone.zone_id)",
    },
    {
        "name": "gebiedsconflict-beste-eigenaar-wordt-slechtste",
        "file": "custom_components/climate_director/engine/takeover.py",
        "old": "best = min(owners, key=lambda r: r.rank).rank",
        "new": "best = max(owners, key=lambda r: r.rank).rank",
    },
    {
        "name": "gebiedsconflict-rivaal-buiten-het-gebied",
        "file": "custom_components/climate_director/engine/takeover.py",
        "old": (
            "r for r in kept.values() if r.source.entity_id != entity_id and r.zone.zone_id in area"
        ),
        "new": "r for r in kept.values() if r.source.entity_id != entity_id",
    },
]


def _apply(root: Path, mutation: dict) -> None:
    path = root / mutation["file"]
    text = path.read_text(encoding="utf-8")
    assert mutation["old"] in text, f"{mutation['name']}: patroon niet gevonden"
    path.write_text(text.replace(mutation["old"], mutation["new"], 1), encoding="utf-8")


def tests_for(mutation: dict, impact: dict[str, list[str]] | None) -> list[str]:
    """The test files that touch the mutated file; `[]` means the full suite."""
    chosen = sel.select({mutation["file"]: "M"}, impact)
    return [] if chosen == sel.ALL else list(chosen)


def relevant(mutation: dict, tests: list[str], changed: dict[str, str] | None) -> bool:
    """Return whether the mutation's part changed; without a known base, always."""
    if changed is None or not tests:
        return True
    own = {mutation["file"], "script/mutation_probe.py", *tests}
    return any(
        path in own or sel.touches_everything(path, status) for path, status in changed.items()
    )


def mutation_timeout() -> float:
    """Seconds one mutation may take: `CD_MUTATION_TIMEOUT`, else `DEFAULT_TIMEOUT`."""
    try:
        wanted = float(os.environ.get("CD_MUTATION_TIMEOUT", ""))
    except ValueError:
        return DEFAULT_TIMEOUT
    return wanted if wanted > 0 else DEFAULT_TIMEOUT


def run_limited(command: list[str], cwd: Path, timeout: float) -> int | None:
    """Run a command in its own process group; `None` when it overran `timeout`.

    The whole group is killed on overrun, so a hanging pytest and the processes it
    started do not keep running (or keep the job open).
    """
    with subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    ) as process:
        try:
            return process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            return None


def caught(mutation: dict, tests: list[str]) -> str:
    """Run the tests against a mutated copy: `caught`, `timeout` or `uncaught`.

    A test that fails catches the mutation; so does a run that hangs past the limit.
    """
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "repo"
        shutil.copytree(
            REPO,
            target,
            ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache"),
        )
        _apply(target, mutation)
        code = run_limited(
            [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *tests],
            target,
            mutation_timeout(),
        )
        if code is None:
            return "timeout"
        return "caught" if code != 0 else "uncaught"


def workers() -> int:
    """How many mutations run side by side: `CD_MUTATION_WORKERS`, else the processors."""
    try:
        wanted = int(os.environ.get("CD_MUTATION_WORKERS", ""))
    except ValueError:
        wanted = os.cpu_count() or 1
    return max(1, wanted)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="alleen deze mutaties, komma-gescheiden")
    parser.add_argument(
        "--plan",
        action="store_true",
        help="alleen tonen of er iets draait (CI: `run=` naar $GITHUB_OUTPUT), zonder pytest",
    )
    args = parser.parse_args()
    only = set(args.only.split(",")) if args.only else None

    impact = sel.load_map()
    base = sel.base_ref()
    changed = sel.changed_files(base) if base is not None else None
    planned: list[tuple[dict, list[str]]] = []
    for mutation in MUTATIONS:
        if only and mutation["name"] not in only:
            continue
        tests = tests_for(mutation, impact)
        if not only and not relevant(mutation, tests, changed):
            print(f"{mutation['name']}: overgeslagen, niets veranderd / skipped, nothing changed")
            continue
        planned.append((mutation, tests))

    if args.plan:
        # Zonder afhankelijkheden: de CI installeert pytest en Home Assistant alleen
        # als er echt een mutatie draait.
        # Without dependencies: CI installs pytest and Home Assistant only when a
        # mutation really runs.
        line = f"run={'true' if planned else 'false'}"
        output = os.environ.get("GITHUB_OUTPUT")
        if output:
            with open(output, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        print(line)
        return 0

    uncaught: list[str] = []
    with ThreadPoolExecutor(max_workers=workers()) as pool:
        # De uitslagen komen in de volgorde van de lijst, hoe snel elke mutatie ook is.
        # The outcomes come in the order of the list, however fast each mutation is.
        outcomes = pool.map(lambda item: caught(*item), planned)
        for (mutation, _tests), outcome in zip(planned, outcomes, strict=True):
            if outcome == "timeout":
                print(f"{mutation['name']}: gevangen (timeout)", flush=True)
            elif outcome == "caught":
                print(f"{mutation['name']}: gevangen", flush=True)
            else:
                uncaught.append(mutation["name"])
                print(f"{mutation['name']}: NIET gevangen", flush=True)

    if uncaught:
        print("ongedekt: " + ", ".join(uncaught))
    else:
        print("ongedekt: geen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
