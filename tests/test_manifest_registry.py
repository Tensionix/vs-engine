"""The manifest, the registry of the engine and the defaults of the .vpy say one thing.

The registry is read from the manifest (engine\\presets.py); the .vpy keep their own defaults for a bare vspipe
(os.environ.get("AUDION_VS_X", "...")). Until 3.0.0 those were two sources with no check between them.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from system_core.core import operation_model as model
from system_core.core.manifest import load_manifest, manifest_path
from system_core.engine import presets as P

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = load_manifest(manifest_path(ROOT))
ENV_DEFAULT = re.compile(r'os\.environ\.get\("AUDION_VS_([A-Z0-9_]+)",\s*"([^"]*)"\)')
# What a .vpy reads that is no field of its preset: the backend of the network, which the service sets from PROCESSING.
ENGINE_KEYS = {"BACKEND"}
# The presets of Real-ESRGAN and the general models of 2.0.3 vs-mlrt does not carry.
ESRGAN = {("restoration", "vsmlrt_realesrgan_2x"), ("restoration", "soft_hd_rebuild_2x")}
GENERAL = {"general-x4v3", "general-wdn-x4v3"}


def test_every_preset_of_the_manifest_has_its_vpy_and_back():
    named = {(node.parameters["palette"], node.id) for node in model.presets(MANIFEST)}
    found = {(path.parent.name, path.stem) for path in (ROOT / "system_core" / "presets").glob("*/*.vpy")}
    assert named == found
    assert set(P.REGISTRY) == named


def test_the_registry_is_the_one_of_the_window_of_2_0_3():
    """Types, defaults, choices and ranges as the former registry had them (tests\\former_window_map.json; the seven
    presets of the full edition - tests\\former_full\\former_window_map.json); new since: `noise` of the seven denoise
    presets; gone: `use_cuda`, and `backend` of the neural presets - PROCESSING says where the network runs; `model` of
    the two Real-ESRGAN presets lost General and General, denoise - vs-mlrt has no general model of Real-ESRGAN, and the
    .vpy ran animevideov3 in their place; that is the default now."""
    former = {(item["palette"], item["name"]): item["params"]
              for item in json.loads((ROOT / "tests" / "former_full" / "former_window_map.json").read_text(encoding="utf-8"))["presets"]}
    former.update({(item["palette"], item["name"]): item["params"]
                   for item in json.loads((ROOT / "tests" / "former_window_map.json").read_text(encoding="utf-8"))["presets"]})
    for key, spec in P.REGISTRY.items():
        old = {name: schema for name, schema in former[key].items() if name not in ("use_cuda", "backend")}
        new = {name: schema for name, schema in spec.params.items() if name != "noise"}
        assert set(old) == set(new), key
        for name, schema in old.items():
            if key in ESRGAN and name == "model":
                assert new[name]["choices"] == [c for c in schema["choices"] if c not in GENERAL], key
                assert new[name]["default"] == "animevideov3", key
                continue
            if schema.get("choices") == ["0", "1"]:
                assert new[name]["type"] == "bool" and new[name]["default"] is (schema["default"] == "1"), (key, name)
                continue
            for part in ("type", "default", "choices"):
                assert schema.get(part) == new[name].get(part), (key, name, part)
            if schema.get("range"):
                assert tuple(schema["range"]) == tuple(new[name]["range"]), (key, name)


@pytest.mark.parametrize("node", model.presets(MANIFEST), ids=lambda node: node.id)
def test_the_defaults_of_a_vpy_are_the_manifest_s(node):
    vpy = ROOT / "system_core" / "presets" / node.parameters["palette"] / f"{node.id}.vpy"
    read = dict(ENV_DEFAULT.findall(vpy.read_text(encoding="utf-8")))
    fields = {model.field_id(field): field for field in node.fields}
    for key, text in read.items():
        if key in ENGINE_KEYS:
            continue
        field = fields.get(key.lower())
        assert field is not None, f"{node.id} reads AUDION_VS_{key}, which is no field of it"
        default = model.field_default(field)
        if model.field_kind(field) == "number":
            assert float(text) == float(default), (node.id, key)
        elif model.field_kind(field) == "checkbox":
            assert (text == "1") is bool(default), (node.id, key)
        else:
            assert text == str(default), (node.id, key)
    own = [model.field_id(field) for field in node.fields if model.section_of(field) == "parameters"]
    # noise is read by audion_lib.noise_mode, not by the .vpy
    assert {name.upper() for name in own if name != "noise"} <= set(read), node.id


def test_the_noise_field_is_on_the_seven_denoise_presets():
    with_noise = sorted(node.id for node in model.presets(MANIFEST) if any(model.field_id(f) == "noise" for f in node.fields))
    assert with_noise == sorted(["mild_denoise", "shadow_denoise_sota", "chroma_cleanup", "filmic_rebuild",
                                 "archive_clean", "pregrade_prep", "mvtools_mcdegrain"])
