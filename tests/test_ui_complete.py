"""Elk stukje UI dat een gebruiker ziet, in elke taal.

Every piece of UI a user sees, in every language.

Een veld zonder vertaling valt niet om: Home Assistant zet er gewoon de sleutel
neer. Je krijgt dan `precondition_start` op je scherm in plaats van "Vooruit
verwarmen vanaf", en niets in de code merkt daar iets van. Dat is precies het
soort fout dat pas opvalt als iemand het scherm openslaat - dus lezen we het
formulier uit de broncode en leggen we het naast elk vertaalbestand.

A field without a translation does not break anything: Home Assistant simply
prints the key. You get `precondition_start` on screen instead of
"Pre-conditioning from", and nothing in the code notices. That is exactly the
kind of fault that only shows when somebody opens the screen - so we read the
form out of the source and lay it beside every translation file.
"""

from __future__ import annotations

import ast
import json
import pathlib
import re

import pytest
import yaml

COMPONENT = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "climate_director"

#: Velden waarvan de naam uit een constante komt in plaats van uit een letterlijke.
#: Fields whose name comes from a constant rather than from a literal.
CONSTANTS = {"CONF_NAME": "name", "CONF_SHADOW_MODE": "shadow_mode", "_EXIT": "when_done"}


def translation_files() -> list[pathlib.Path]:
    return [COMPONENT / "strings.json", *sorted((COMPONENT / "translations").glob("*.json"))]


def _flatten(data: object, prefix: str = "") -> dict[str, object]:
    """Return one translation tree as a flat {dotted key: text} mapping."""
    if not isinstance(data, dict):
        return {prefix: data}
    found: dict[str, object] = {}
    for key, value in data.items():
        found.update(_flatten(value, f"{prefix}.{key}" if prefix else key))
    return found


def load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def fields_per_step() -> dict[str, set[str]]:
    """Return every field the flow asks for, per step, read from the source.

    Uit de broncode en niet uit een lijstje: een lijstje raakt achter zodra
    iemand een veld toevoegt, en dan bewijst deze test niets meer.

    From the source rather than from a list: a list falls behind the moment
    somebody adds a field, and then this test proves nothing.
    """
    tree = ast.parse((COMPONENT / "config_flow.py").read_text(encoding="utf-8"))
    found: dict[str, set[str]] = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or getattr(node.func, "attr", "") != "async_show_form":
            continue
        step = next((kw.value.value for kw in node.keywords if kw.arg == "step_id"), None)
        if not isinstance(step, str):
            continue

        keys: set[str] = set()
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            if getattr(inner.func, "attr", "") not in {"Required", "Optional"} or not inner.args:
                continue
            arg = inner.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                keys.add(arg.value)
            elif isinstance(arg, ast.Name):
                keys.add(CONSTANTS.get(arg.id, arg.id))
        found.setdefault(step, set()).update(keys)

    return found


def step_block(data: dict, step: str) -> dict | None:
    for section in ("options", "config"):
        block = data.get(section, {}).get("step", {}).get(step)
        if block:
            return block
    return None


STEPS = fields_per_step()
FILES = translation_files()
IDS = [path.name for path in FILES]


class TestEveryFormField:
    """Nineteen screens, eighty-six fields, seven files."""

    def test_the_source_yields_steps_at_all(self) -> None:
        """Guards the reader itself: an empty sweep would pass everything below."""
        assert len(STEPS) >= 15
        assert sum(len(keys) for keys in STEPS.values()) >= 80

    @pytest.mark.parametrize("path", FILES, ids=IDS)
    def test_every_step_exists(self, path: pathlib.Path) -> None:
        data = load(path)
        missing = [step for step in STEPS if step_block(data, step) is None]
        assert not missing, missing

    @pytest.mark.parametrize("path", FILES, ids=IDS)
    def test_every_field_has_a_label(self, path: pathlib.Path) -> None:
        data = load(path)
        missing = [
            f"{step}.{key}"
            for step, keys in STEPS.items()
            for key in keys
            if key not in (step_block(data, step) or {}).get("data", {})
        ]
        assert not missing, missing

    @pytest.mark.parametrize("path", FILES, ids=IDS)
    def test_every_field_has_an_explanation(self, path: pathlib.Path) -> None:
        """The grey line under the input is the only place a setting can explain itself."""
        data = load(path)
        missing = [
            f"{step}.{key}"
            for step, keys in STEPS.items()
            for key in keys
            if key not in (step_block(data, step) or {}).get("data_description", {})
        ]
        assert not missing, missing

    @pytest.mark.parametrize("path", FILES, ids=IDS)
    def test_no_label_is_a_bare_key(self, path: pathlib.Path) -> None:
        """A label that reads like a key is a translation somebody forgot to write."""
        data = load(path)
        suspects = []
        for step in STEPS:
            for key, label in (step_block(data, step) or {}).get("data", {}).items():
                if label == key or re.fullmatch(r"[a-z0-9]+(_[a-z0-9]+)+", label):
                    suspects.append(f"{step}.{key} = {label}")
        assert not suspects, suspects


class TestEveryDropdown:
    """A select without translated options shows its stored values instead."""

    _flow = (COMPONENT / "config_flow.py").read_text(encoding="utf-8")
    #: Twee vormen: rechtstreeks op de selector, en via `_choices`.
    #: Two shapes: straight on the selector, and by way of `_choices`.
    keys = set(re.findall(r'translation_key="(\w+)"', _flow)) | set(
        re.findall(r'_choices\([^"]*"(\w+)"\)', _flow)
    )

    def test_the_flow_uses_translation_keys(self) -> None:
        assert len(self.keys) >= 10

    @pytest.mark.parametrize("path", FILES, ids=IDS)
    def test_every_key_is_translated(self, path: pathlib.Path) -> None:
        present = set(load(path).get("selector", {}))
        assert not (self.keys - present), sorted(self.keys - present)

    @pytest.mark.parametrize("path", FILES, ids=IDS)
    def test_option_names_are_valid_keys(self, path: pathlib.Path) -> None:
        """Hassfest rejects a key that starts or ends with an underscore."""
        pattern = re.compile(r"^[a-z0-9]([a-z0-9_-]*[a-z0-9])?$")
        bad = [
            f"{key}.{option}"
            for key, block in load(path).get("selector", {}).items()
            for option in block.get("options", {})
            if not pattern.fullmatch(option)
        ]
        assert not bad, bad


class TestEveryAction:
    """Actions show up in the UI too, fields and all."""

    actions = yaml.safe_load((COMPONENT / "services.yaml").read_text(encoding="utf-8"))

    @pytest.mark.parametrize("path", FILES, ids=IDS)
    def test_each_one_is_named_and_described(self, path: pathlib.Path) -> None:
        services = load(path).get("services", {})
        missing = [
            f"{name}.{part}"
            for name in self.actions
            for part in ("name", "description")
            if part not in services.get(name, {})
        ]
        assert not missing, missing

    @pytest.mark.parametrize("path", FILES, ids=IDS)
    def test_each_field_is_named_and_described(self, path: pathlib.Path) -> None:
        services = load(path).get("services", {})
        missing = [
            f"{name}.{field}.{part}"
            for name, block in self.actions.items()
            for field in (block or {}).get("fields", {})
            for part in ("name", "description")
            if part not in services.get(name, {}).get("fields", {}).get(field, {})
        ]
        assert not missing, missing


class TestEveryEntity:
    """Every entity the integration creates needs a name in each language."""

    keys = {
        key
        for path in COMPONENT.glob("*.py")
        for key in re.findall(r'_attr_translation_key = "(\w+)"', path.read_text(encoding="utf-8"))
    }

    def test_there_are_entities_to_check(self) -> None:
        assert len(self.keys) >= 5

    @pytest.mark.parametrize("path", FILES, ids=IDS)
    def test_each_one_is_named(self, path: pathlib.Path) -> None:
        named = {key for domain in load(path).get("entity", {}).values() for key in domain}
        assert not (self.keys - named), sorted(self.keys - named)


class TestTheLanguagesAgree:
    """Same shape everywhere, so no language quietly falls behind."""

    def _shape(self, value, path: str = "") -> set[str]:
        if isinstance(value, dict):
            return {
                item for key, inner in value.items() for item in self._shape(inner, f"{path}.{key}")
            } | {path}
        return {path}

    @pytest.mark.parametrize("path", FILES, ids=IDS)
    def test_it_matches_the_english(self, path: pathlib.Path) -> None:
        english = self._shape(load(COMPONENT / "translations" / "en.json"))
        theirs = self._shape(load(path))
        assert not (english - theirs), sorted(english - theirs)

    @pytest.mark.parametrize("path", FILES, ids=IDS)
    def test_nothing_is_left_empty(self, path: pathlib.Path) -> None:
        def walk(value, trail: str = "") -> list[str]:
            if isinstance(value, dict):
                return [
                    item for key, inner in value.items() for item in walk(inner, f"{trail}.{key}")
                ]
            return [] if str(value).strip() else [trail]

        assert not walk(load(path)), walk(load(path))


class TestEveryScreenCanBeLeft:
    """No screen may trap somebody who only came to look.

    Home Assistant tekent precies één knop onder een formulier en laat een
    integratie er geen tweede bij zetten, dus een echte "Terug"-knop naast
    "Opslaan" bestaat niet. Wat wél kan is een regel in dezelfde lijstopmaak,
    en die hoort op élk scherm te staan - anders kom je ergens binnen waar
    alleen opslaan je nog weghelpt.

    Home Assistant draws exactly one button under a form and lets an integration
    add no second one, so a real "Back" button beside "Save" does not exist.
    What is possible is a row in the same list styling, and every screen should
    carry one - otherwise you walk into a place only saving gets you out of.
    """

    #: `user` is het eerste scherm van de installatiewizard en `init` is het
    #: hoofdmenu zelf; die twee sluit je met het kruisje, niet met een terugregel.
    #:
    #: `user` is the first screen of the setup wizard and `init` is the main menu
    #: itself; those two you leave with the cross, not with a back row.
    exempt = {"user", "init"}

    def _steps(self) -> dict[str, str]:
        """Return the source of each step's own method, keyed by step id."""
        source = (COMPONENT / "config_flow.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        lines = source.splitlines(keepends=True)
        found: dict[str, str] = {}

        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            body = "".join(lines[node.lineno - 1 : node.end_lineno])
            for step in re.findall(r'step_id="(\w+)"', body):
                found[step] = body
        return found

    def test_the_reader_finds_the_screens(self) -> None:
        assert len(self._steps()) >= 15

    def test_each_one_offers_a_way_back(self) -> None:
        trapped = [
            step
            for step, body in self._steps().items()
            if step not in self.exempt and "_back_option" not in body and "_EXIT" not in body
        ]
        assert not trapped, trapped

    @pytest.mark.parametrize("path", FILES, ids=IDS)
    def test_the_way_back_is_named(self, path: pathlib.Path) -> None:
        """Both shapes of it, so neither reads as a bare key on screen."""
        chooser = load(path).get("selector", {})
        assert "when_done" in chooser
        assert set(chooser["when_done"]["options"]) == {"keep", "discard"}
        lists = [key for key in chooser if key.endswith("_list")]
        assert lists
        missing = [key for key in lists if "back_to_menu" not in chooser[key]["options"]]
        assert not missing, missing


class TestNoScreenCanRefuseToBeLeft:
    """Leaving must never depend on having filled the screen in.

    Voluptuous keurt het hele formulier af vóór de handler draait, dus één leeg
    verplicht veld maakte "Verwerpen en teruggaan" onbereikbaar: je kreeg "Niet
    alle verplichte velden zijn ingevuld" en zat vast in een scherm waar je
    alleen uit kwam door het af te maken. Verplichte velden staan daarom als
    optioneel in het schema en worden in de handler gecontroleerd.

    Voluptuous refuses the whole form before the handler runs, so one empty
    required field made "Discard and go back" unreachable: you got "not all
    required fields are filled in" and were stuck in a screen you could leave
    only by finishing it. Required fields are therefore optional in the schema
    and checked in the handler.
    """

    def _forms(self) -> dict[str, ast.AsyncFunctionDef]:
        tree = ast.parse((COMPONENT / "config_flow.py").read_text(encoding="utf-8"))
        found = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            for call in ast.walk(node):
                if (
                    isinstance(call, ast.Call)
                    and getattr(call.func, "attr", "") == "async_show_form"
                ):
                    step = next((k.value.value for k in call.keywords if k.arg == "step_id"), None)
                    if isinstance(step, str):
                        found[step] = node
        return found

    def test_the_reader_finds_the_forms(self) -> None:
        assert len(self._forms()) >= 15

    def test_no_field_is_required_without_a_default(self) -> None:
        """A required field with no default is exactly what blocks the way out."""
        blocking = []
        for step, node in self._forms().items():
            for call in ast.walk(node):
                if not (
                    isinstance(call, ast.Call) and getattr(call.func, "attr", "") == "Required"
                ):
                    continue
                if any(keyword.arg == "default" for keyword in call.keywords):
                    continue
                if call.args and isinstance(call.args[0], ast.Constant):
                    blocking.append(f"{step}.{call.args[0].value}")
        assert not blocking, blocking

    def test_the_missing_field_error_is_translated(self) -> None:
        for path in FILES:
            data = load(path)
            for section in ("config", "options"):
                if section in data:
                    assert "required" in data[section].get("error", {}), f"{path.name}.{section}"

    def test_deleting_needs_no_filled_in_fields(self) -> None:
        """Throwing something away should not demand you complete it first."""
        source = (COMPONENT / "config_flow.py").read_text(encoding="utf-8")
        checks = source.count("errors = _missing(user_input,")
        guarded = source.count(
            'if not user_input.get("delete"):\n                errors = _missing('
        )
        assert checks >= 6
        assert guarded == checks, f"{checks - guarded} controles zonder verwijder-uitzondering"


class TestTheSaveScreenWarns:
    """Opslaan laat eerst zien wat er afwijkt, en houdt niets tegen.

    Een afwijkende installatie mag: soms wíl je een kamer anders laten werken
    dan de rest. Tegenhouden zou dat onmogelijk maken. Maar er stilzwijgend
    overheen gaan is net zo fout, want dan merk je het pas als er iets niet
    gebeurt - en dat is precies de fout die je nooit vindt.

    An unusual installation is allowed: sometimes you do want one room to work
    differently. Refusing would make that impossible. But passing over it in
    silence is just as wrong, since then you only notice when something fails to
    happen - and that is exactly the fault you never find.
    """

    def test_the_save_step_checks_before_writing(self) -> None:
        source = (COMPONENT / "config_flow.py").read_text(encoding="utf-8")
        start = source.index("async def async_step_save(")
        body = source[start : source.index("\n    async def ", start + 1)]
        assert "validate(" in body, "opslaan doet geen configuratiecontrole"
        assert "async_create_entry" in body, "opslaan schrijft niet meer weg"
        assert body.index("validate(") < body.index("async_create_entry")

    def test_it_can_be_saved_anyway(self) -> None:
        """The warning must be a warning, not a lock."""
        source = (COMPONENT / "config_flow.py").read_text(encoding="utf-8")
        start = source.index("async def async_step_save(")
        body = source[start : source.index("\n    async def ", start + 1)]
        assert "_EXIT_DROP" in body, "geen weg terug vanaf het opslaanscherm"
        assert "_exit_row()" in body, "geen keuze tussen opslaan en teruggaan"

    @pytest.mark.parametrize("path", FILES, ids=IDS)
    def test_the_warning_screen_is_translated(self, path: pathlib.Path) -> None:
        step = load(path).get("options", {}).get("step", {}).get("save")
        assert step, "de opslaanstap ontbreekt"
        assert step.get("title")
        assert "{problems}" in step.get("description", ""), "de lijst wordt niet ingevuld"
        assert "when_done" in step.get("data", {})


class TestEveryPickerCanBeBuilt:
    """Een kiezer die zijn eigen knop niet kan tekenen, opent helemaal niet.

    De toevoegregel haalt zijn terugvaltekst uit een tabel. Ontbreekt de sleutel,
    dan is het een `KeyError` bij het opbouwen van het scherm - en Home Assistant
    laat dan alleen "Fout" zien, zonder te zeggen waar. Een lege menuregel en een
    dialoog met één woord: dat is alles wat de gebruiker ervan merkt.

    A picker that cannot draw its own button does not open at all. The add row
    takes its fallback text from a table. With the key missing that is a
    `KeyError` while building the screen - and Home Assistant then shows only
    "Error", without saying where. A blank menu row and a one-word dialog: that
    is all the user gets to see.
    """

    _flow = (COMPONENT / "config_flow.py").read_text(encoding="utf-8")

    def test_every_add_row_has_a_fallback(self) -> None:
        used = set(re.findall(r'_add_option\("(\w+)"\)', self._flow))
        table = set(re.findall(r'^    "(\w+)": "\+ ', self._flow, re.M))
        assert used, "geen enkele toevoegregel gevonden"
        assert not (used - table), sorted(used - table)

    def test_an_unknown_key_does_not_raise(self) -> None:
        """Belt and braces: even a key nobody added may not break the screen."""
        assert "_ADD_FALLBACK.get(" in self._flow, "de terugval kan nog een KeyError geven"

    def test_every_menu_option_has_a_step(self) -> None:
        """A menu row without its own step is a dead end that reports nothing."""
        menu = re.search(r"menu_options=\[(.*?)\]", self._flow, re.S)
        assert menu
        options = re.findall(r'"(\w+)"', menu.group(1))
        assert len(options) >= 7
        for option in options:
            assert f"async def async_step_{option}(" in self._flow, option

    @pytest.mark.parametrize("path", FILES, ids=IDS)
    def test_every_menu_option_is_named(self, path: pathlib.Path) -> None:
        menu = re.search(r"menu_options=\[(.*?)\]", self._flow, re.S)
        assert menu
        options = set(re.findall(r'"(\w+)"', menu.group(1)))
        named = set(load(path)["options"]["step"]["init"]["menu_options"])
        assert not (options - named), sorted(options - named)


class TestProblemsAreTranslatable:
    """Een melding in het Engels tussen een Nederlands scherm leest als een fout.

    De engine kent geen Home Assistant en schrijft dus Engels. Draagt een melding
    een code, dan zoekt de HA-laag daar een vertaling bij; zonder code blijft de
    Engelse zin staan. Zo is niets ooit slechter af dan het was, en wordt alles
    wat een gebruiker daadwerkelijk tegenkomt in zijn eigen taal getoond.

    A complaint in English amid a Dutch screen reads as a fault. The engine knows
    no Home Assistant and therefore writes English. If a complaint carries a code
    the HA layer looks up a translation; without one the English sentence stays.
    Nothing is ever worse off than it was, and everything a user actually meets
    is shown in their own language.
    """

    def _codes(self) -> set[str]:
        source = (COMPONENT / "engine" / "models.py").read_text(encoding="utf-8")
        return set(re.findall(r'Problem\(\s*\n?\s*"(\w+)"', source))

    def test_the_engine_emits_codes(self) -> None:
        assert len(self._codes()) >= 8

    def _texts(self, path: pathlib.Path) -> dict[str, str]:
        """Return the complaint templates of one file, keyed by code.

        Ze wonen onder `exceptions`, in de vorm die Home Assistant voorschrijft:
        een blok per code met daarin `message`. Een zelf verzonnen blok op het
        hoogste niveau wordt door hassfest afgewezen.

        They live under `exceptions`, in the shape Home Assistant prescribes: a
        block per code holding `message`. A self-invented top-level block is
        rejected by hassfest.
        """
        block = load(path).get("exceptions", {})
        return {code: entry.get("message", "") for code, entry in block.items()}

    @pytest.mark.parametrize("path", FILES, ids=IDS)
    def test_every_code_is_translated(self, path: pathlib.Path) -> None:
        missing = sorted(self._codes() - set(self._texts(path)))
        assert not missing, missing

    @pytest.mark.parametrize("path", FILES, ids=IDS)
    def test_the_placeholders_line_up(self, path: pathlib.Path) -> None:
        """A template naming a placeholder the engine never passes renders raw."""
        english = self._texts(COMPONENT / "translations" / "en.json")
        for code, template in self._texts(path).items():
            expected = set(re.findall(r"\{(\w+)\}", english.get(code, "")))
            assert set(re.findall(r"\{(\w+)\}", template)) == expected, code

    def test_a_problem_still_reads_as_its_english_text(self) -> None:
        """Everything already treating these as plain strings must keep working."""
        from custom_components.climate_director.engine.models import Problem

        item = Problem("zone_without_sources", "zone z has no sources", zone="z")
        assert item == "zone z has no sources"
        assert "no sources" in item
        assert item.code == "zone_without_sources"
        assert item.params == {"zone": "z"}


#: De sleutels die Home Assistant op het hoogste niveau van een vertaalbestand
#: toestaat. Staat er iets anders, dan wijst hassfest het bestand af - en niet
#: een beetje: de hele integratie zakt door de controle, voor elke taal
#: tegelijk. Deze lijst komt uit het schema van HA zelf.
#:
#: The keys Home Assistant allows at the top level of a translation file.
#: Anything else and hassfest rejects the file - and not by halves: the whole
#: integration fails validation, for every language at once. This list comes
#: from HA's own schema.
ALLOWED_TOP_LEVEL = frozenset(
    {
        "title",
        "config",
        "config_subentries",
        "config_panel",
        "options",
        "device_automation",
        "issues",
        "entity",
        "entity_component",
        "device",
        "exceptions",
        "services",
        "selector",
        "triggers",
        "conditions",
        "common",
        "application_credentials",
        "system_health",
        "conversation",
    }
)


class TestEveryLanguageStandsUp:
    """Wat voor Nederlands en Engels geldt, geldt voor elke taal.

    Er zijn er nu zes en er komen er meer bij. Een taal die een sleutel mist
    valt in het Engels terug - vervelend maar te overzien. Een taal met een
    sleutel die niet bestaat, of een verzonnen blok bovenin, laat hassfest
    struikelen en dan is de héle integratie afgekeurd. Deze tests draaien over
    alles wat in `translations/` staat, dus een nieuwe taal doet vanzelf mee.

    What holds for Dutch and English holds for every language. There are six now
    and more are coming. A language missing a key falls back to English -
    annoying but survivable. A language with a key that does not exist, or an
    invented block at the top, trips hassfest, and then the whole integration is
    rejected. These tests run over everything in `translations/`, so a new
    language joins in by itself.
    """

    @pytest.mark.parametrize("path", FILES, ids=IDS)
    def test_no_invented_block_at_the_top(self, path: pathlib.Path) -> None:
        unknown = sorted(set(load(path)) - ALLOWED_TOP_LEVEL)
        assert not unknown, f"{path.name}: {unknown}"

    @pytest.mark.parametrize("path", FILES, ids=IDS)
    def test_the_same_keys_as_the_source(self, path: pathlib.Path) -> None:
        """Every language carries exactly what strings.json describes."""
        source = set(_flatten(load(COMPONENT / "strings.json")))
        here = set(_flatten(load(path)))
        assert not sorted(source - here), f"{path.name} mist: {sorted(source - here)}"
        assert not sorted(here - source), f"{path.name} heeft extra: {sorted(here - source)}"

    @pytest.mark.parametrize("path", FILES, ids=IDS)
    def test_the_placeholders_survive_translation(self, path: pathlib.Path) -> None:
        """A translation that renames {zone} shows the braces to the user."""
        source = _flatten(load(COMPONENT / "strings.json"))
        for key, text in _flatten(load(path)).items():
            if key not in source:
                continue
            expected = set(re.findall(r"\{(\w+)\}", str(source[key])))
            assert set(re.findall(r"\{(\w+)\}", str(text))) == expected, f"{path.name}: {key}"

    @pytest.mark.parametrize("path", FILES, ids=IDS)
    def test_nothing_was_left_in_english(self, path: pathlib.Path) -> None:
        """A sentence identical to the English one was never translated.

        Korte teksten mogen samenvallen - een merknaam, een eenheid, "OK". Een
        hele zin die letterlijk gelijk is, is vergeten werk.

        Short texts may coincide - a brand name, a unit, "OK". A whole sentence
        that is literally identical is forgotten work.
        """
        if path.stem in {"en", "strings"}:
            return
        english = _flatten(load(COMPONENT / "translations" / "en.json"))
        left = [
            key
            for key, text in _flatten(load(path)).items()
            if isinstance(text, str) and len(text) > 25 and text == english.get(key)
        ]
        assert not left, f"{path.name} is hier nog Engels: {sorted(left)[:8]}"
