"""How the form of an operation becomes what the operation is run with.

One copy of the rules for the window and the console command, on the pattern of Audion Media Tools 3.0.0
(core\\operation_model.py there): until 3.0.0 the window on NiceGUI held them (ui_nicegui\\app.py) and the console took a
finished name of an encoder and nothing else. The record of what that window built is tests\\former_window_commands.json.

The rules of a form:

- a field takes its default when it is drawn; a switch on a choice that is off or gone moves to the first one allowed;
- a field is in sight by its `visible_if` - the cards of the encoder by the codec;
- a hardware encoder this machine has not passed (config\\hardware_capabilities_cache.json, SERVICE - Hardware
  capabilities) is off, with the reason;
- a profile chosen sets its encoder on the cards, as the former window did;
- a number outside its range and a choice that is none of its field's are a wrong call, not a value quietly moved
  (engine\\presets.py PresetSpec.resolve clamped the numbers and fell over a wrong choice with a trace).

A `Form` goes through the steps of a person: `open` draws the form, `click` does what the control does and draws again.
The console command fills a form the same way and runs what it holds.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any, Iterable

from .manifest import Operation

SWITCHES = frozenset({"radio", "radiobuttons", "radio-buttons"})
LISTS = frozenset({"select", "choice"})
NUMBERS = frozenset({"number", "int", "integer", "float"})
TICKS = frozenset({"checkbox", "bool", "boolean", "toggle"})

LANGUAGES = ("en", "ru")
WORDS = {
    "en": {"name": "Fill in: {field}", "profiles": "There is no profile in config\\profiles yet.",
           "backend": "{backend} did not pass the check of this machine for {codec}: {detail}"},
    "ru": {"name": "Заполните: {field}", "profiles": "В config\\profiles пока нет ни одного профиля.",
           "backend": "{backend} не прошёл проверку этой машины для {codec}: {detail}"},
}

# The cards of the encoder: a profile chosen sets them (encoding.cards_of).
CARD_FIELDS = ("encode_family", "encode_backend", "encode_quality", "encode_container", "prores_profile",
               "prores_wrapper", "dnxhr_profile")
HARDWARE_CACHE = "hardware_capabilities_cache.json"


def safe_language(language: str | None) -> str:
    return language if language in LANGUAGES else "en"


# --- a field ---------------------------------------------------------------------------------


def field_id(field: dict[str, Any]) -> str:
    return str(field.get("id") or field.get("name") or "").strip()


def field_kind(field: dict[str, Any]) -> str:
    return str(field.get("type", field.get("kind", "text"))).lower()


def field_label(field: dict[str, Any], language: str = "en") -> str:
    if language == "ru" and field.get("label_ru"):
        return str(field["label_ru"])
    return str(field.get("label") or field.get("title") or field_id(field))


def form_fields(node: Any) -> list[dict[str, Any]]:
    return [field for field in node.fields if field_id(field)]


def option_value(option: Any) -> Any:
    if isinstance(option, dict):
        return option.get("value", option.get("id", option.get("label", "")))
    return option


def field_default(field: dict[str, Any]) -> Any:
    if "default" in field:
        return field["default"]
    options = field.get("options", [])
    if isinstance(options, list) and options:
        return option_value(options[0])
    return ""


def step_is_whole(field: dict[str, Any]) -> bool:
    try:
        return float(field.get("step", 1)).is_integer()
    except (TypeError, ValueError):
        return True


def is_whole_number(field: dict[str, Any]) -> bool:
    return field_kind(field) in NUMBERS and field_kind(field) != "float" and step_is_whole(field)


def normalize(field: dict[str, Any], value: Any) -> Any:
    """A number as its field holds it: 2.0 of a whole field is 2, 1 of a fractional one is 1.0."""
    if value is None or value == "" or field_kind(field) not in NUMBERS:
        return value
    try:
        number = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return value
    if is_whole_number(field):
        return int(number) if number.is_integer() else number
    return number


def refreshes_layout(field: dict[str, Any]) -> bool:
    return bool(field.get("refresh_on_change") or field.get("refresh_layout") or field.get("affects_layout"))


def is_advanced(field: dict[str, Any]) -> bool:
    return bool(field.get("advanced", False))


def section_of(field: dict[str, Any]) -> str:
    return str(field.get("group") or "").strip().lower() or "parameters"


def sections(fields: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    """The fields in the blocks of the form, in the order they first come."""
    groups: list[tuple[str, list[dict[str, Any]]]] = []
    index: dict[str, int] = {}
    for field in fields:
        name = section_of(field)
        if name not in index:
            index[name] = len(groups)
            groups.append((name, [field]))
        else:
            groups[index[name]][1].append(field)
    return groups


# --- the conditions of the manifest ----------------------------------------------------------


def _matches_value(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        if "not" in expected:
            return not _matches_value(actual, expected["not"])
        if "in" in expected:
            return _matches_value(actual, expected["in"])
    if isinstance(expected, (list, tuple, set)):
        wanted = {str(item).strip().lower() for item in expected}
        return str(actual).strip().lower() in wanted
    if isinstance(expected, bool):
        return bool(actual) is expected
    return str(actual).strip().lower() == str(expected).strip().lower()


# --- dynamic choices -----------------------------------------------------------------------------


def dynamic_options(field: dict[str, Any], root: Path) -> list[Any]:
    """Choices a function of the engine gives (`options_source`): the profiles of config\\profiles, the presets."""
    source = str(field.get("options_source") or "").strip()
    if not source:
        return []
    try:
        module_name, function_name = source.split(":", 1)
        provider = getattr(importlib.import_module(module_name), function_name)
        options = provider(root)
        if not isinstance(options, list):
            raise RuntimeError(f"{source} gave {type(options).__name__}, a list was expected")
        return options
    except Exception as exc:  # noqa: BLE001 - the failure is shown as the one choice, nothing is run with it
        message = f"Option source failed: {exc.__class__.__name__}: {exc}"
        return [{"value": "", "label": message, "label_ru": message}]


# --- the machine -----------------------------------------------------------------------------


def hardware_cache(root: Path) -> dict[str, Any]:
    """What SERVICE - Hardware capabilities found on this machine; {} when it never ran or does not read."""
    try:
        told = json.loads((Path(root) / "config" / HARDWARE_CACHE).read_text(encoding="utf-8"))
        return told if isinstance(told, dict) else {}
    except (OSError, ValueError):
        return {}


def backend_off(cache: dict[str, Any], family: str, backend: str) -> str:
    """Why a hardware encoder may not be chosen for a codec; "" when it may (the CPU, or a check never made)."""
    if backend == "cpu" or family not in ("x264", "x265"):
        return ""
    found = (cache.get("encoders") or {}).get(f"{'h264' if family == 'x264' else 'hevc'}_{backend}")
    if not isinstance(found, dict) or str(found.get("status", "")).upper() == "OK":
        return ""
    return str(found.get("detail") or found.get("status") or "not passed")


# --- a form ----------------------------------------------------------------------------------


class Form:
    """The form of one operation: its values, what it drew, the machine it is drawn on."""

    def __init__(self, node: Operation, root: Path, source: Path | str | None = None,
                 target: Path | str | None = None) -> None:
        self.node = node
        self.root = Path(root)
        self.source = Path(source) if source else self.root / "input"
        self.target = Path(target) if target else self.root / "output"
        self.values: dict[str, Any] = {}
        self._fields = {field_id(field): field for field in node.fields if field_id(field)}
        self.cache = hardware_cache(self.root)

    # ---- reading the form -------------------------------------------------------------------
    def field(self, key: str) -> dict[str, Any]:
        return self._fields.get(key, {})

    def actual(self, key: str) -> Any:
        if key in self.values:
            return self.values[key]
        field = self._fields.get(key)
        return field_default(field) if field is not None else None

    def holds(self, condition: Any) -> bool:
        if not condition:
            return False
        if isinstance(condition, dict):
            if "all" in condition:
                return all(self.holds(item) for item in condition.get("all") or [])
            if "any" in condition:
                return any(self.holds(item) for item in condition.get("any") or [])
            if "not" in condition:
                return not self.holds(condition["not"])
            return all(_matches_value(self.actual(str(key)), expected) for key, expected in condition.items())
        if isinstance(condition, (list, tuple, set)):
            return all(self.holds(item) for item in condition)
        return False

    def visible(self, field: dict[str, Any]) -> bool:
        if bool(field.get("hidden", False)):
            return False
        # PROCESSING moves BM3D or a neural network: a preset with neither runs on the CPU whatever it says.
        if field_id(field) == "vs_accel" and not getattr(self.node, "accel", ""):
            return False
        shown_if = field.get("visible_if")
        if shown_if and not self.holds(shown_if):
            return False
        hidden_if = field.get("hidden_if")
        return not (hidden_if and self.holds(hidden_if))

    def options(self, field: dict[str, Any]) -> list[Any]:
        dynamic = dynamic_options(field, self.root)
        if dynamic:
            return dynamic
        options = field.get("options", [])
        return options if isinstance(options, list) else []

    def why_off(self, field: dict[str, Any], option: Any) -> str:
        """Why a choice is off; "" when it may be chosen."""
        if isinstance(option, dict):
            disabled_if = option.get("disabled_if")
            if disabled_if and self.holds(disabled_if):
                return str(option.get("disabled_why") or "off")
        if field_id(field) == "encode_backend":
            return backend_off(self.cache, str(self.actual("encode_family")), str(option_value(option)))
        return ""

    def choices(self, field: dict[str, Any]) -> list[tuple[Any, bool]]:
        return [(option_value(option), bool(self.why_off(field, option))) for option in self.options(field)]

    def shown_fields(self) -> list[dict[str, Any]]:
        return [field for field in form_fields(self.node) if self.visible(field)]

    # ---- what a control does ----------------------------------------------------------------
    def set(self, key: str, value: Any) -> None:
        self.values[key] = normalize(self.field(key), value)
        if key == "profile":
            # A profile chosen: its encoder on the cards (the former window: profile_encoder).
            from system_core.engine import encoding
            from system_core.services.vs_service import profile_of

            profile = profile_of(self.root, str(value or ""))
            if profile:
                self.values.update(encoding.cards_of(str(profile.get("encoder") or "")))

    # ---- the form drawn ----------------------------------------------------------------------
    def draw(self) -> None:
        for field in form_fields(self.node):
            key = field_id(field)
            if key not in self.values:
                self.set(key, field_default(field))
            if field_kind(field) in SWITCHES | LISTS and self.visible(field):
                choices = self.choices(field)
                allowed = [choice for choice, off in choices if not off]
                every = [choice for choice, _ in choices]
                value = self.values.get(key)
                if every and (value not in every or (value not in allowed and allowed)):
                    self.set(key, allowed[0] if allowed else every[0])

    def open(self) -> "Form":
        self.values = {}
        self.draw()
        return self

    def click(self, action: str, key: str, value: Any) -> None:
        if not self.field(key):
            raise ValueError(f"the operation has no field {key!r}")
        if action in {"choose", "select", "number", "type"}:
            self.set(key, value)
        elif action == "tick":
            self.set(key, bool(value))
        else:
            raise ValueError(f"unknown action {action!r}")
        self.draw()

    def fill(self, given: dict[str, Any]) -> "Form":
        """Values of a caller, set as a person sets them: the profile first - it sets the cards - then every other field
        in its order, so a card named by the caller wins over the profile's."""
        fields = [field for field in form_fields(self.node) if field_id(field) in given]
        first = [field for field in fields if field_id(field) == "profile"]
        for field in first + [field for field in fields if field not in first]:
            self.click(action_of(field), field_id(field), given[field_id(field)])
        self.draw()
        return self

    def changed(self, given: dict[str, Any]) -> list[tuple[str, Any, Any]]:
        """The values the form took otherwise than given: a choice that is off on this machine."""
        return [(key, value, self.values.get(key)) for key, value in given.items()
                if key in self.values and self.values.get(key) != normalize(self.field(key), value)]

    # ---- what is run ----------------------------------------------------------------------------
    def refusal(self, language: str = "en") -> str:
        """Why the form may not be run as it stands; "" when it may."""
        words = WORDS[safe_language(language)]
        for field in form_fields(self.node):
            key = field_id(field)
            if field.get("required") and not str(self.values.get(key, "") or "").strip():
                return words["name"].format(field=field_label(field, language))
        if "profile" in self._fields and not [choice for choice, _ in self.choices(self.field("profile")) if choice]:
            return words["profiles"]
        return ""

    def off_reasons(self, language: str = "en") -> dict[str, dict[str, str]]:
        """For every field in sight: its choices that are off and why."""
        told: dict[str, dict[str, str]] = {}
        for field in self.shown_fields():
            reasons = {str(option_value(option)): why for option in self.options(field)
                       if (why := self.why_off(field, option))}
            if reasons:
                if field_id(field) == "encode_backend":
                    codec = "H.264" if self.actual("encode_family") == "x264" else "H.265"
                    labels = {str(option_value(option)): str(option.get("label") or option_value(option))
                              for option in self.options(field) if isinstance(option, dict)}
                    reasons = {value: WORDS[safe_language(language)]["backend"].format(
                        backend=labels.get(value, value), codec=codec, detail=why) for value, why in reasons.items()}
                told[field_id(field)] = reasons
        return told

    def parameters(self) -> dict[str, Any]:
        """What the service of the operation is handed: the node's own parameters and every field."""
        parameters = dict(self.node.parameters)
        for field in form_fields(self.node):
            key = field_id(field)
            parameters[key] = normalize(field, self.values.get(key, field_default(field)))
        return parameters


def action_of(field: dict[str, Any]) -> str:
    kind = field_kind(field)
    for kinds, action in ((SWITCHES, "choose"), (LISTS, "select"), (NUMBERS, "number"), (TICKS, "tick")):
        if kind in kinds:
            return action
    return "type"


# --- a caller's values -------------------------------------------------------------------------


def unknown_values(node: Any, values: dict[str, Any]) -> list[str]:
    known = {field_id(field) for field in form_fields(node)}
    return sorted(name for name in values if name not in known)


def coerce(field: dict[str, Any], text: str) -> Any:
    """`--set name=value`: the text of a console as the value its field holds."""
    kind = field_kind(field)
    stripped = text.strip()
    if kind in TICKS:
        lowered = stripped.lower()
        if lowered in {"1", "true", "yes", "on", "да"}:
            return True
        if lowered in {"0", "false", "no", "off", "нет", ""}:
            return False
        raise ValueError(f"true or false is expected, got {text!r}")
    if kind in NUMBERS:
        try:
            number = float(stripped.replace(",", "."))
        except ValueError as error:
            raise ValueError(f"a number is expected, got {text!r}") from error
        return normalize(field, number)
    for option in field.get("options") or []:
        value = option_value(option)
        if str(value).lower() == stripped.lower():
            return value
    return text


def wrong_values(node: Any, values: dict[str, Any], root: Path, language: str = "en") -> list[str]:
    """A value the window could not set and a caller can: none of the choices of its field, a number outside its range
    or of a fraction a whole field does not take."""
    form = Form(node, root)
    wrong: list[str] = []
    for field in form_fields(node):
        key = field_id(field)
        if key not in values:
            continue
        kind, value, label = field_kind(field), values[key], field_label(field, language)
        if kind in SWITCHES | LISTS:
            allowed = [option_value(option) for option in form.options(field)]
            if str(value) not in [str(item) for item in allowed]:
                wrong.append(f"{label} ({key}): no such choice - {value!r}; choices: {', '.join(map(str, allowed))}")
        elif kind in NUMBERS:
            number = normalize(field, value)
            if not isinstance(number, (int, float)) or isinstance(number, bool):
                wrong.append(f"{label} ({key}): a number is expected, got {value!r}")
                continue
            low, high = field.get("min"), field.get("max")
            if (low is not None and number < low) or (high is not None and number > high):
                wrong.append(f"{label} ({key}): {number} is outside {low}..{high}")
            elif is_whole_number(field) and not float(number).is_integer():
                wrong.append(f"{label} ({key}): a whole number is expected, got {number}")
    return wrong


# --- what the window draws -------------------------------------------------------------------

CONDITIONS = ("visible_if", "hidden_if", "disabled_if")
TEXTS = ("label", "label_ru", "tooltip", "tooltip_ru", "hint", "hint_ru", "description", "description_ru", "placeholder")


def window_option(option: Any) -> dict[str, Any]:
    given = option if isinstance(option, dict) else {}
    told = {"value": option_value(option), "label": str(given.get("label") or option_value(option))}
    for key in ("label_ru", "tooltip", "tooltip_ru", "tone", *CONDITIONS):
        if key in given:
            told[key] = given[key]
    return told


def window_field(field: dict[str, Any]) -> dict[str, Any]:
    """A field as the window draws it: what the manifest says, the default worked out, its block named."""
    kind = field_kind(field)
    told: dict[str, Any] = {
        "id": field_id(field), "kind": kind, "action": action_of(field), "default": field_default(field),
        "section": section_of(field), "advanced": is_advanced(field), "hidden": bool(field.get("hidden", False)),
        "redraws": refreshes_layout(field), "whole": is_whole_number(field),
        "style": str(field.get("style") or field.get("choice_style") or "").strip().lower(),
    }
    for key in (*TEXTS, *CONDITIONS, "min", "max", "step", "span", "layout", "pair", "pair_label", "pair_label_ru",
                "options_source", "required"):
        if key in field:
            told[key] = field[key]
    if isinstance(field.get("options"), list):
        told["options"] = [window_option(option) for option in field["options"]]
    return told


# The services that can say their commands and run none (--dry-run), and those that need the engine to run.
DRY_RUN_SERVICES = frozenset({"run_preset", "profile_run"})
ENGINE_SERVICES = frozenset({"run_preset", "profile_run", "bench_presets", "bench_gpu"})


def accel_words(told: dict[str, Any], accel: str, texts: dict[str, Any]) -> None:
    """PROCESSING as a preset shows it: hidden where it moves nothing, with the words of what it moves (accel_texts of
    the manifest; bm3d - the words of the field itself)."""
    if not accel:
        told["hidden"] = True
        return
    words = texts.get(accel) if isinstance(texts.get(accel), dict) else {}
    for key in ("tooltip", "tooltip_ru"):
        if words.get(key):
            told[key] = words[key]
    options = words.get("options") if isinstance(words.get("options"), dict) else {}
    for option in told.get("options") or []:
        own = options.get(str(option.get("value"))) or {}
        for key in ("tooltip", "tooltip_ru"):
            if own.get(key):
                option[key] = own[key]


def window_node(node: Operation, accel_texts: dict[str, Any] | None = None) -> dict[str, Any]:
    service = node.service.rsplit(":", 1)[-1]
    fields = [window_field(field) for field in form_fields(node)]
    for told in fields:
        if told["id"] == "vs_accel":
            accel_words(told, node.accel, accel_texts or {})
    return {
        "id": node.id, "title": node.title, "title_ru": node.title_ru,
        "description": node.description, "description_ru": node.description_ru,
        **node.texts, "kind": node.kind, "parameters": dict(node.parameters), "runs": bool(node.service),
        "dry_run": service in DRY_RUN_SERVICES, "engine": service in ENGINE_SERVICES,
        "accel": node.accel, "needs": node.needs, "fields": fields,
    }


def describe(manifest: Any) -> dict[str, Any]:
    tool = manifest.raw.get("tool", {}) if isinstance(manifest.raw.get("tool"), dict) else {}
    texts = manifest.raw.get("accel_texts") if isinstance(manifest.raw.get("accel_texts"), dict) else {}
    operations = [node for node in all_nodes(manifest) if node.service and not node.children]
    return {"tool": {"id": tool.get("id", ""), "name": tool.get("name", "")},
            "operations": {node.id: window_node(node, texts) for node in operations}}


# --- the manifest ----------------------------------------------------------------------------


def iter_nodes(nodes: Iterable[Any]) -> Iterable[Any]:
    for node in nodes:
        yield node
        yield from iter_nodes(getattr(node, "children", ()))


def all_nodes(manifest: Any) -> list[Any]:
    return [*iter_nodes(manifest.operation_groups), *manifest.operations]


def find_node(manifest: Any, operation_id: str) -> Any | None:
    """The operation of the name: a preset, a profile operation or a service."""
    for node in all_nodes(manifest):
        if node.id == operation_id and node.service and not node.children:
            return node
    return None


def presets(manifest: Any) -> list[Operation]:
    """The operations that are presets: the leaves of a palette, in the order of the manifest."""
    return [node for group in manifest.operation_groups for node in group.children
            if node.service.endswith(":run_preset")]
