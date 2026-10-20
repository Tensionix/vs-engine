"""Where every operation stands in the window: config\\window_layout.yaml read and checked.

The manifest says what an operation is, the layout - where it stands: a section of the ribbon (a palette, PROFILES) and
inside it the ribbon of its modes (the presets). The console command hands the layout to the window in `describe`; the
window draws what it is told and knows no operation by its name. The reading of Audion Media Tools 3.0.0.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import load_yaml_or_json

SECTION_TEXTS = ("title", "title_ru", "about", "about_ru", "icon")


def load(config: Path) -> dict[str, Any]:
    path = Path(config) / "window_layout.yaml"
    raw = load_yaml_or_json(path) if path.is_file() else {}
    return raw if isinstance(raw, dict) else {}


def _names(items: Any) -> list[str]:
    return [str(item).strip() for item in items or [] if str(item).strip()]


MODE_TEXTS = ("title", "title_ru", "icon", "group", "short", "short_ru")


def describe(layout: dict[str, Any]) -> dict[str, Any]:
    """The layout as written: every mode with its operation, the groups of a section by the kind of processing."""
    sections = []
    for section in layout.get("sections") or []:
        told = {key: str(section.get(key, "")) for key in ("id", *SECTION_TEXTS)}
        told["groups"] = [{key: str(group.get(key, "")).strip() for key in ("id", "title", "title_ru")}
                          for group in section.get("groups") or [] if isinstance(group, dict)]
        told["modes"] = [{"op": str((mode if isinstance(mode, dict) else {"op": mode}).get("op") or "").strip(),
                          **{key: str(mode.get(key, "")).strip() if isinstance(mode, dict) else "" for key in MODE_TEXTS}}
                         for mode in section.get("modes") or []]
        sections.append(told)
    return {"sections": sections, "setup": _names(layout.get("setup")), "service": _names(layout.get("service")),
            "details": _names(layout.get("details")), "buttons": _buttons(layout.get("buttons"))}


def _buttons(value: Any) -> list[dict[str, Any]]:
    """Operations a page runs with its own values, as a button of the page: [{op, icon, sections}]; sections - the
    sections it stands on, every section when none is named. (Not `on`: YAML reads that word as "true".)"""
    return [{"op": str(item.get("op") or "").strip(), "icon": str(item.get("icon") or "").strip(),
             "sections": _names(item.get("sections"))}
            for item in value or [] if isinstance(item, dict)]


def placed(layout: dict[str, Any]) -> list[str]:
    told = describe(layout)
    names = [mode["op"] for section in told["sections"] for mode in section["modes"]]
    return names + told["setup"] + told["service"] + told["details"] + [button["op"] for button in told["buttons"]]


def problems(layout: dict[str, Any], manifest: Any) -> list[str]:
    """What is wrong between the layout and the manifest; nothing when every operation stands once."""
    from . import operation_model as model

    operations = {node.id for node in model.all_nodes(manifest) if node.service and not node.children}
    names = placed(layout)
    wrong = [f"stands nowhere in the window: {name}" for name in sorted(operations - set(names))]
    wrong += [f"is not an operation of the manifest: {name}" for name in sorted(set(names) - operations)]
    wrong += [f"stands more than once: {name}" for name in sorted({name for name in names if names.count(name) > 1})]
    told = describe(layout)
    ids = [section["id"] for section in told["sections"]]
    wrong += [f"a section without an id or with one taken: {name!r}" for name in sorted({i for i in ids if not i or ids.count(i) > 1})]
    for section in told["sections"]:
        wrong += [f"the section {section['id']} has no {key}" for key in SECTION_TEXTS if not section[key]]
        if not section["modes"]:
            wrong.append(f"the section {section['id']} has no mode")
        groups = [group["id"] for group in section["groups"]]
        for group in section["groups"]:
            wrong += [f"the group {section['id']}/{group['id']} has no {key}" for key in ("id", "title", "title_ru") if not group[key]]
            if not any(mode["group"] == group["id"] for mode in section["modes"]):
                wrong.append(f"the group {section['id']}/{group['id']} has no mode")
        for mode in section["modes"]:
            if groups and mode["group"] not in groups:
                wrong.append(f"{mode['op']} stands in no group of {section['id']}: {mode['group']!r}")
            if mode["short"] and not mode["short_ru"] or mode["short_ru"] and not mode["short"]:
                wrong.append(f"{mode['op']}: a short name in one language only")
    for button in told["buttons"]:
        wrong += [f"the button {button['op']} stands on no section {name!r}" for name in button["sections"] if name not in ids]
    return wrong


def for_window(layout: dict[str, Any], manifest: Any) -> dict[str, Any]:
    """The layout as the window reads it: every mode with its title and its line «what for» in both languages."""
    from . import operation_model as model

    told = describe(layout)
    sections = []
    for section in told["sections"]:
        modes = []
        for mode in section["modes"]:
            node = model.find_node(manifest, mode["op"])
            if node is None:
                raise ValueError(f"the layout names an operation the manifest does not have: {mode['op']}")
            modes.append({**mode, "title": mode["title"] or node.title, "title_ru": mode["title_ru"] or node.title_ru,
                          "about": node.texts.get("about", ""), "about_ru": node.texts.get("about_ru", "")})
        sections.append({**section, "modes": modes})
    return {"sections": sections, "setup": told["setup"], "service": told["service"], "details": told["details"],
            "buttons": told["buttons"]}
