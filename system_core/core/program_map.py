"""The map of the program, from its data alone: `vs_cli.cmd map`.

The sections and modes of the window, every operation with its fields and choices and their texts in both languages, the
condition a field is shown under in words, the call of the console command each operation is. The documents of the
program are built from it (core\\program_docs.py), never from a memory of the code. What has no text in one of the two
languages is named in `missing`; a test does not let it be.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import operation_model as model
from . import window_layout

WORDS = {
    "en": {"is": "is", "one_of": "is one of", "and": " and ", "shown": "shown when"},
    "ru": {"is": "=", "one_of": "- одно из", "and": " и ", "shown": "видно, когда"},
}


def condition_words(condition: Any, language: str = "en") -> str:
    words = WORDS[language]
    if not isinstance(condition, dict):
        return str(condition or "")
    parts = []
    for key, expected in condition.items():
        if isinstance(expected, (list, tuple)):
            parts.append(f"{key} {words['one_of']} {', '.join(str(item) for item in expected)}")
        else:
            parts.append(f"{key} {words['is']} {expected}")
    return words["and"].join(parts)


def as_text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return "" if value is None else str(value)


def _field(field: dict[str, Any], root: Path) -> dict[str, Any]:
    told: dict[str, Any] = {key: field[key] for key in ("label", "label_ru", "tooltip", "tooltip_ru", "min", "max", "step")
                            if key in field}
    told.update(id=model.field_id(field), kind=model.field_kind(field), default=model.field_default(field),
                section=model.section_of(field), hidden=bool(field.get("hidden", False)))
    if field.get("options_source"):
        told["choices_from"] = str(field["options_source"])
    elif isinstance(field.get("options"), list):
        told["choices"] = [{"value": model.option_value(option), "label": str(option.get("label", "")),
                            "label_ru": str(option.get("label_ru", ""))} for option in field["options"]
                           if isinstance(option, dict)]
    if field.get("visible_if"):
        told["when"] = f"{WORDS['en']['shown']} {condition_words(field['visible_if'], 'en')}"
        told["when_ru"] = f"{WORDS['ru']['shown']} {condition_words(field['visible_if'], 'ru')}"
    return told


def call_of(node: Any) -> str:
    return f"vs_cli.cmd run --operation {node.id}"


def build(root: Path, manifest: Any, version: str = "") -> dict[str, Any]:
    root = Path(root)
    layout = window_layout.for_window(window_layout.load(root / "config"), manifest)
    operations: dict[str, Any] = {}
    missing: list[str] = []

    def need(where: str, item: dict[str, Any], *keys: str) -> None:
        for key in keys:
            for name in (key, f"{key}_ru"):
                if not str(item.get(name) or "").strip():
                    missing.append(f"{where}: {name}")

    for section in layout["sections"]:
        need(f"section {section['id']}", section, "title", "about")
    for node in model.all_nodes(manifest):
        if not node.service or node.children:
            continue
        told = {"id": node.id, "title": node.title, "title_ru": node.title_ru, "description": node.description,
                "description_ru": node.description_ru, **node.texts, "palette": node.parameters.get("palette", ""),
                "service": node.service.rsplit(":", 1)[-1], "call": call_of(node), "needs": getattr(node, "needs", ""),
                "fields": [_field(field, root) for field in model.form_fields(node)]}
        operations[node.id] = told
        need(f"operation {node.id}", told, "title", "description")
        if told["service"] == "run_preset":
            need(f"preset {node.id}", told, "about")
        for field in told["fields"]:
            need(f"{node.id}.{field['id']}", field, "label", "tooltip")
            for choice in field.get("choices") or []:
                need(f"{node.id}.{field['id']}={choice['value']}", choice, "label")
    from system_core.engine import runner

    return {"tool": model.describe(manifest)["tool"], "version": version, "sections": layout["sections"],
            "setup": layout["setup"], "service": layout["service"], "details": layout["details"], "buttons": layout["buttons"],
            "operations": operations, "encoders": runner.list_encoders(), "missing": sorted(set(missing))}
