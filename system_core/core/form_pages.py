"""The forms of the window, held while the window is open: `vs_cli.cmd form`.

The window draws the forms and runs nothing itself; the rules of a form live in operation_model.Form. So the window keeps
this process open and asks it: a page opened, a control used, the folders changed; it answers with the form as it stands.
One JSON object a line, each way - the protocol of Audion Media Tools 3.0.0.

A page is a mode of the ribbon - a preset, a profile operation - with a form of its own. The fields of the machine -
where BM3D runs and the cards of the encoder - are one for the whole window: set on one page, they are set on all.

The state of a page:

  values   every field of the form with the value it has now
  shown    the fields in sight, in the order of the form
  blocks   the fields in sight by the blocks of the form: name, advanced, fields
  choices  for every field in sight with choices: [value, off] each, and the label of a choice the engine made
           (the profiles of config\\profiles)
  off      for a choice that is off: why (a hardware encoder this machine has not passed)
  refusal  why the form may not be run now; "" when it may
  set      the values a person would type: what differs from the form as it opened
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import operation_model as model

# One value for the whole window: the machine, not the task.
SHARED = frozenset({"vs_accel", *model.CARD_FIELDS})


def as_text(value: Any) -> str:
    """A value as `--set` takes it."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return "" if value is None else str(value)


class Page:
    def __init__(self, node: Any, root: Path, source: str, target: str) -> None:
        self.node, self.root = node, root
        self.form = model.Form(node, root, source or None, target or None).open()
        self.baseline = dict(self.form.values)


class Pages:
    def __init__(self, root: Path, manifest: Any, language: str = "en") -> None:
        self.root = Path(root)
        self.manifest = manifest
        self.language = model.safe_language(language)
        self.pages: dict[str, Page] = {}
        self.source, self.target = "", ""

    def state(self, key: str) -> dict[str, Any]:
        page = self.pages[key]
        form = page.form
        fields = model.form_fields(page.node)
        shown = form.shown_fields()
        choices: dict[str, list[list[Any]]] = {}
        for field in shown:
            options = form.options(field)
            if not options:
                continue
            made = bool(field.get("options_source"))
            told = []
            for option in options:
                entry: list[Any] = [model.option_value(option), bool(form.why_off(field, option))]
                if made:
                    entry.append(str(option.get("label") or model.option_value(option)) if isinstance(option, dict) else str(option))
                told.append(entry)
            choices[model.field_id(field)] = told
        blocks = [{"name": name, "advanced": rare, "fields": [model.field_id(field) for field in block]}
                  for rare in (False, True)
                  for name, block in model.sections([field for field in shown if model.is_advanced(field) == rare])]
        values = {model.field_id(field): form.values.get(model.field_id(field), model.field_default(field)) for field in fields}
        typed = {name: as_text(value) for name, value in values.items()
                 if page.baseline.get(name, model.field_default(form.field(name))) != value}
        return {"page": key, "operation": page.node.id, "values": values, "shown": [model.field_id(field) for field in shown],
                "blocks": blocks, "choices": choices, "off": form.off_reasons(self.language),
                "refusal": form.refusal(self.language), "set": typed}

    def open(self, key: str, operation: str, values: dict[str, Any] | None) -> dict[str, Any]:
        node = model.find_node(self.manifest, operation)
        if node is None:
            raise ValueError(f"the manifest has no operation {operation!r}")
        page = Page(node, self.root, self.source, self.target)
        self.pages[key] = page
        # The machine as the other pages hold it.
        shared = next(({name: other.form.values[name] for name in SHARED if name in other.form.values and page.form.field(name)}
                       for other_key, other in self.pages.items() if other_key != key), {})
        given = {**shared, **{name: value for name, value in (values or {}).items() if page.form.field(name)}}
        if given:
            page.form.fill(given)
        return self.state(key)

    def click(self, key: str, action: str, field: str, value: Any) -> dict[str, Any]:
        page = self.pages[key]
        page.form.click(action, field, value)
        changed = [name for name in SHARED if name == field or (field == "profile" and name in model.CARD_FIELDS)]
        for name in changed:
            for other_key, other in self.pages.items():
                if other_key != key and other.form.field(name) and name in page.form.values:
                    other.form.click(model.action_of(other.form.field(name)), name, page.form.values[name])
        return self.state(key)

    def reset(self, key: str) -> dict[str, Any]:
        page = self.pages[key]
        shared = {name: page.form.values[name] for name in SHARED if name in page.form.values}
        page.form = model.Form(page.node, self.root, self.source or None, self.target or None).open().fill(shared)
        return self.state(key)

    def folders(self, source: str, target: str) -> dict[str, Any]:
        """The Source and the Target the window points at; the answer names what a run would take from them."""
        self.source, self.target = source or self.source, target or self.target
        for page in self.pages.values():
            page.form.source = Path(self.source) if self.source else page.form.source
            page.form.target = Path(self.target) if self.target else page.form.target
        return {"folders": {"source": self.source, "target": self.target}, "queue": self.queue()}

    def queue(self) -> dict[str, Any]:
        """The videos a run takes from the Source, as it takes them (core\\sources.py): how many, the first names, and
        the paths of the first thousand - the preview of the window steps through them; and the camera RAW among them and
        beside them that the engine does not read, with what opens it: the window names it once when the Source is given
        and keeps it out of the preview (a run fails such a file by itself, the others go on)."""
        from .camera_raw import hint, raw_of, stray_raw
        from .sources import source_files

        if not self.source:
            return {"count": 0, "first": [], "files": [], "raw": []}
        source = Path(self.source)
        files = source_files(source, Path(self.target) if self.target else None)
        first = [str(file.relative_to(source)) if source.is_dir() else file.name for file in files[:12]]
        raw: list[dict[str, str]] = []
        for file in files[:1000] + [path for paths in stray_raw(source).values() for path in paths[:100]]:
            if found := raw_of(file):
                raw.append({"file": str(file), "name": found.name, "hint": hint(found, self.language)})
        return {"count": len(files), "first": first, "files": [str(file) for file in files[:1000]], "raw": raw}

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        do = str(request.get("do") or "")
        key = str(request.get("page") or "")
        if "language" in request:
            self.language = model.safe_language(str(request.get("language")))
        if do == "open":
            return self.open(key, str(request.get("operation") or ""), request.get("values"))
        if key not in self.pages and do in {"click", "reset", "state"}:
            raise ValueError(f"no page {key!r} is open")
        if do == "click":
            return self.click(key, str(request.get("action") or ""), str(request.get("field") or ""), request.get("value"))
        if do == "reset":
            return self.reset(key)
        if do == "state":
            return self.state(key)
        if do == "folders":
            return self.folders(str(request.get("source") or ""), str(request.get("target") or ""))
        if do == "queue":
            return {"queue": self.queue()}
        if do == "language":
            return {"language": self.language}
        raise ValueError(f"unknown request {do!r}")


def serve(pages: Pages, read, write) -> None:
    """Lines in, lines out, until the window closes its end. A request that fails is answered with why."""
    for line in iter(read, ""):
        line = line.strip()
        if not line:
            continue
        ident: Any = None
        try:
            request = json.loads(line)
            ident = request.get("id")
            answer = {"id": ident, "ok": True, **pages.handle(request)}
        except Exception as error:  # noqa: BLE001 - the window is told, the process goes on
            answer = {"id": ident, "ok": False, "error": f"{type(error).__name__}: {error}"}
        write(json.dumps(answer, ensure_ascii=False, default=str) + "\n")
