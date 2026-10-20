"""Preset registry: palette/name -> .vpy path + parameter schema, read from config\\tool_manifest.yaml.

Until 3.0.0 the registry was a copy of its own here, and the window kept the texts in a third place. The manifest is the
one source now: a preset is an operation of a palette there, its fields are the parameters of its .vpy. What the fields of
the machine (processing, the cards of the encoder, overwrite) are, the engine reads elsewhere: they are not parameters
of a preset.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .paths import PATHS

# The fields every preset has from its palette: the machine and the run, not the preset.
MACHINE_FIELDS = frozenset({"vs_accel", "encode_family", "encode_backend", "encode_quality", "encode_container",
                            "prores_profile", "prores_wrapper", "dnxhr_profile", "overwrite"})


@dataclass(frozen=True)
class PresetSpec:
    palette: str           # "precision" | "film_looks" | "retro" | "restoration"
    name: str              # short name, matches .vpy filename stem
    vpy: Path              # absolute path to the .vpy file
    summary: str           # one-line human description
    params: dict[str, Any] = field(default_factory=dict)
    """params: {param_name: {type, default, choices?, range?, doc}}"""

    def resolve(self, user_params: dict[str, Any]) -> dict[str, Any]:
        """Validate & default user params against the schema."""
        out: dict[str, Any] = {}
        for k, schema in self.params.items():
            v = user_params.get(k, schema.get("default"))
            if v is None:
                continue
            t = schema.get("type")
            if t == "float":
                v = float(v)
                lo, hi = schema.get("range", (None, None))
                if lo is not None and v < lo: v = lo
                if hi is not None and v > hi: v = hi
            elif t == "int":
                v = int(float(v))
                lo, hi = schema.get("range", (None, None))
                if lo is not None and v < lo: v = lo
                if hi is not None and v > hi: v = hi
            elif t == "bool":
                v = v if isinstance(v, bool) else str(v).strip().lower() in {"1", "true", "yes", "on"}
            elif t == "choice":
                choices = schema.get("choices", [])
                if v not in choices:
                    raise ValueError(f"{k}: {v!r} not in {choices}")
            out[k] = v
        # passthrough of unknown user params (engine-level options ignore here)
        return out


def _param(entry: dict[str, Any]) -> dict[str, Any]:
    """A field of the manifest as a parameter of the registry."""
    kind = str(entry.get("type", "text")).lower()
    told: dict[str, Any] = {"default": entry.get("default")}
    if kind == "radio":
        told.update(type="choice", choices=[str(option.get("value")) for option in entry.get("options") or []])
    elif kind == "checkbox":
        told.update(type="bool", default=bool(entry.get("default", False)))
    elif kind == "number":
        whole = float(entry.get("step", 1)).is_integer()
        told.update(type="int" if whole else "float", range=(entry.get("min"), entry.get("max")))
        told["default"] = int(entry["default"]) if whole else float(entry["default"])
    else:
        told["type"] = "text"
    if entry.get("tooltip"):
        told["doc"] = str(entry["tooltip"])
    return told


def _build_registry() -> dict[tuple[str, str], PresetSpec]:
    from system_core.core.manifest import load_manifest, manifest_path
    from system_core.core.operation_model import presets

    specs: dict[tuple[str, str], PresetSpec] = {}
    for node in presets(load_manifest(manifest_path(PATHS.root))):
        palette = str(node.parameters.get("palette") or "")
        params = {str(entry["id"]): _param(entry) for entry in node.fields
                  if entry.get("id") and entry["id"] not in MACHINE_FIELDS}
        specs[(palette, node.id)] = PresetSpec(palette=palette, name=node.id,
                                               vpy=PATHS.presets_dir / palette / f"{node.id}.vpy",
                                               summary=node.description, params=params)
    return specs


REGISTRY: dict[tuple[str, str], PresetSpec] = _build_registry()


def get(palette: str, name: str) -> PresetSpec:
    try:
        return REGISTRY[(palette, name)]
    except KeyError:
        avail = ", ".join(f"{p}/{n}" for (p, n) in REGISTRY)
        raise KeyError(f"preset {palette}/{name} not registered. Available: {avail}")


def by_name(name: str) -> PresetSpec:
    """The preset of the name, whatever its palette: a preset id is one across the palettes."""
    found = [spec for (_palette, preset), spec in REGISTRY.items() if preset == name]
    if not found:
        raise KeyError(f"preset {name} not registered. Available: {', '.join(sorted(n for _p, n in REGISTRY))}")
    return found[0]
