"""Noteer per toetsbestand wat het bij het draaien uitvoert en opent.

Note per test file what it executes and opens while running.

Alleen actief als `CD_IMPACT_LOG` gezet is (`script/run_tests.py` doet dat). Dan:

* krijgt elk toetsbestand een eigen coverage-context (zijn pad), van het importeren
  van de module tot de laatste teardown, ook voor code die in een andere taak van de
  event loop draait - de ingebouwde `dynamic_context = test_function` van coverage
  verliest die bij elke `await`;
* noteert een omhulsel om `open`, `io.open`, `os.listdir` en `os.scandir` elk
  bestand en elke map **binnen de repo** die het toetsbestand opent of doorloopt
  (zonder `.venv`, `.git`, caches en de coverage-bestanden), met een map als
  `pad/`; `io.open_code` telt alleen voor `script/`, want een module-import hoort
  bij wie hem als eerste importeert en zegt dus niets vast over één toetsbestand.

Bij het einde van de sessie gaat de verzameling als JSON naar `CD_IMPACT_LOG`.
`script/run_tests.py` voegt de coverage-contexten erbij en vergelijkt het geheel met
`tests/impact_map.json`.

Only active when `CD_IMPACT_LOG` is set (`script/run_tests.py` does that). Then:

* every test file gets a coverage context of its own (its path), from importing the
  module up to the last teardown, also for code running in another task of the
  event loop - coverage's built-in `dynamic_context = test_function` loses that at
  every `await`;
* a wrapper around `open`, `io.open`, `os.listdir` and `os.scandir` notes every
  file and every directory **inside the repository** that the test file opens or
  walks (without `.venv`, `.git`, caches and the coverage files), with a directory
  as `path/`; `io.open_code` only counts for `script/`, since a module import
  belongs to whoever imports it first and so says nothing fixed about one test
  file.

At the end of the session the collection goes to `CD_IMPACT_LOG` as JSON.
`script/run_tests.py` adds the coverage contexts and compares the whole with
`tests/impact_map.json`.
"""

from __future__ import annotations

import builtins
import glob
import io
import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
_ROOT_TEXT = os.path.normcase(str(ROOT)) + os.sep
_SKIP = (".venv/", ".git/", ".pytest_cache/", ".mypy_cache/", ".ruff_cache/", ".coverage")

_current: str | None = None
_reads: dict[str, set[str]] = {}
_originals: dict[str, Any] = {}


def active() -> bool:
    """Return whether recording is switched on for this session."""
    return bool(os.environ.get("CD_IMPACT_LOG"))


def _relative(target: Any) -> str | None:
    """The repository path of `target`, or `None` when it falls outside."""
    if isinstance(target, int):
        return None
    try:
        text = os.fspath(target)
    except TypeError:
        return None
    if isinstance(text, bytes):
        text = os.fsdecode(text)
    # Vergelijk genormaliseerd (Windows kent geen hoofdletters in paden), maar bewaar
    # het pad zoals het is: de kaart noemt `ARCHITECTURE.md`, niet `architecture.md`.
    # Compare normalised (Windows ignores case in paths), but keep the path as it
    # is: the map names `ARCHITECTURE.md`, not `architecture.md`.
    full = os.path.abspath(text)
    if not os.path.normcase(full).startswith(_ROOT_TEXT):
        return None
    relative = full[len(_ROOT_TEXT) :].replace(os.sep, "/")
    if "__pycache__" in relative or relative.startswith(_SKIP):
        return None
    return relative


def _note(target: Any, directory: bool = False) -> None:
    if _current is None:
        return
    relative = _relative(target)
    if relative:
        _reads.setdefault(_current, set()).add(
            relative.rstrip("/") + "/" if directory else relative
        )


def _wrap_open(original: Any) -> Any:
    """Note a file opened for reading; writing (pytest's own cache, say) is no input."""

    def wrapper(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if not any(flag in str(mode) for flag in "wax+"):
            _note(file)
        return original(file, mode, *args, **kwargs)

    return wrapper


def _wrap_code(original: Any) -> Any:
    """Note only scripts loaded by path; a module import belongs to its first importer."""

    def wrapper(path: Any) -> Any:
        relative = _relative(path)
        if relative and relative.startswith("script/"):
            _note(path)
        return original(path)

    return wrapper


def _wrap_listing(original: Any) -> Any:
    def wrapper(path: Any = ".", *args: Any, **kwargs: Any) -> Any:
        _note(path, directory=True)
        return original(path, *args, **kwargs)

    return wrapper


def start() -> None:
    """Install the wrappers."""
    _originals.update(
        open=builtins.open, open_code=io.open_code, listdir=os.listdir, scandir=os.scandir
    )
    wrapped = _wrap_open(_originals["open"])
    builtins.open = wrapped
    io.open = wrapped
    io.open_code = _wrap_code(_originals["open_code"])
    os.listdir = _wrap_listing(_originals["listdir"])
    os.scandir = _wrap_listing(_originals["scandir"])
    # `Path.glob` en `Path.rglob` lopen via `glob._StringGlobber`, dat bij het
    # importeren een eigen verwijzing naar `os.scandir` vastlegt; zonder deze regel
    # zag de kaart niet dat `test_timeless` de map `tests/` doorloopt.
    # `Path.glob` and `Path.rglob` run through `glob._StringGlobber`, which captures
    # its own reference to `os.scandir` at import; without this line the map did
    # not see that `test_timeless` walks the directory `tests/`.
    globber = getattr(glob, "_StringGlobber", None)
    if globber is not None and "scandir" in vars(globber):
        _originals["globber_scandir"] = vars(globber)["scandir"]
        globber.scandir = staticmethod(_wrap_listing(_originals["scandir"]))


def switch(test_file: str | None) -> None:
    """Make `test_file` the owner of what follows, in the notes and in coverage."""
    global _current
    if test_file == _current:
        return
    _current = test_file
    try:
        from coverage import Coverage
    except ImportError:
        return
    measuring = Coverage.current()
    if measuring is not None:
        measuring.switch_context(test_file or "")


def owner(path: Path) -> str | None:
    """The repository path of a test module, or `None` outside the repository."""
    return _relative(path)


def stop() -> None:
    """Put the originals back."""
    switch(None)
    if _originals:
        builtins.open = _originals["open"]
        io.open = _originals["open"]
        io.open_code = _originals["open_code"]
        os.listdir = _originals["listdir"]
        os.scandir = _originals["scandir"]
        if "globber_scandir" in _originals:
            glob._StringGlobber.scandir = _originals.pop("globber_scandir")


def finish() -> None:
    """Restore the originals and write the notes to `CD_IMPACT_LOG`."""
    stop()
    target = os.environ["CD_IMPACT_LOG"]
    with open(target, "w", encoding="utf-8") as handle:
        json.dump({key: sorted(value) for key, value in sorted(_reads.items())}, handle)
