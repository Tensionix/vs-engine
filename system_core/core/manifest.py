"""config\\tool_manifest.yaml read: the operations, their fields and their texts.

The reading of Audion Media Tools 3.0.0, with one difference: a preset puts its own fields first and those of its palette
- the machine and the run - after them, so the form opens with the parameters of the preset.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import load_yaml_or_json

# The texts of a node besides its title and description: what it is for, a few words (the second line of a mode).
EXTRA_TEXTS = ("about", "about_ru")


@dataclass(frozen=True)
class Operation:
    id: str
    title: str
    description: str
    service: str
    kind: str = "safe"
    title_ru: str = ""
    description_ru: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    fields: tuple[dict[str, Any], ...] = ()
    texts: dict[str, str] = field(default_factory=dict)
    children: tuple["Operation", ...] = ()
    # What of the preset the block PROCESSING moves: bm3d, mlrt, any; "" - nothing, the block is not shown.
    accel: str = ""
    # What the preset needs beyond the engine: mlrt - vs-mlrt (core\machine.py).
    needs: str = ""

    def display_title(self, language: str) -> str:
        return self.title_ru if language == "ru" and self.title_ru else self.title

    def display_description(self, language: str) -> str:
        return self.description_ru if language == "ru" and self.description_ru else self.description

    def with_parameters(self, parameters: dict[str, Any]) -> "Operation":
        return Operation(self.id, self.title, self.description, self.service, self.kind, self.title_ru,
                         self.description_ru, dict(parameters), self.fields, self.texts, (), self.accel, self.needs)


@dataclass(frozen=True)
class ToolManifest:
    raw: dict[str, Any]
    operations: list[Operation]          # the service operations (SERVICE)
    operation_groups: list[Operation]    # the palettes and PROFILES, their operations as children


def _fields(item: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    value = item.get("fields", [])
    return tuple(dict(entry) for entry in value if isinstance(entry, dict)) if isinstance(value, list) else ()


def _parse(item: dict[str, Any], inherited_parameters: dict[str, Any] | None = None,
           inherited_fields: tuple[dict[str, Any], ...] = ()) -> Operation:
    parameters = dict(inherited_parameters or {})
    own = item.get("parameters", {})
    parameters.update(own if isinstance(own, dict) else {})
    children_raw = [child for child in item.get("children", []) or [] if isinstance(child, dict)]
    # A group hands its fields down; a leaf puts its own first.
    fields = (*_fields(item), *inherited_fields) if not children_raw else ()
    handed = (*_fields(item), *inherited_fields) if children_raw else ()
    children = tuple(_parse(child, parameters, handed) for child in children_raw)
    return Operation(
        id=str(item.get("id", "")).strip(),
        title=str(item.get("title", "")).strip(),
        description=str(item.get("description", "")).strip(),
        service=str(item.get("service", "")).strip(),
        kind=str(item.get("kind", "safe")).strip() or "safe",
        title_ru=str(item.get("title_ru", "")).strip(),
        description_ru=str(item.get("description_ru", "")).strip(),
        parameters=parameters,
        fields=fields,
        texts={key: str(item[key]).strip() for key in EXTRA_TEXTS if key in item},
        children=children,
        accel=str(item.get("accel", "")).strip(),
        needs=str(item.get("needs", "")).strip(),
    )


def load_manifest(path: Path) -> ToolManifest:
    raw = load_yaml_or_json(path)
    operations = [_parse(item) for item in raw.get("operations", []) or [] if isinstance(item, dict)]
    groups = [_parse(item) for item in raw.get("operation_groups", []) or [] if isinstance(item, dict)]

    def check(node: Operation) -> None:
        if not node.id:
            raise ValueError("an operation without an id")
        for child in node.children:
            check(child)
        if not node.children and ":" not in node.service:
            raise ValueError(f"the service of an operation is module:function: {node.id}")

    for node in [*operations, *groups]:
        check(node)
    return ToolManifest(raw=raw, operations=operations, operation_groups=groups)


def manifest_path(root: Path) -> Path:
    return Path(root) / "config" / "tool_manifest.yaml"
