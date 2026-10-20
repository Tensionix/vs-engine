"""The console command runs what the window on NiceGUI ran: the record of its commands (tests\\former_window_commands.json,
253 states of the forms of Lite, taken once from the reference and never rewritten; tests\\former_full\\ - the same of
the full edition, for the seven presets Lite did not have, taken 18.10.2026 when the two became one program) against the
forms of the manifest.

For every state the values the window handed to the engine (its argv) are given to the form of the operation as a
person sets them; what the form makes of them must be the same preset, the same parameters of the .vpy and the same
encoder.

The changes on purpose:
- noise: a field of the seven denoise presets since 17.10.2026, after the record; `auto` by default;
- vs_accel: CPU | CUDA became auto | cpu | gpu - BM3DCUDA does not load on VapourSynth R80+, the video card of any maker
  runs BM3D through Vulkan; the window's `cuda` is `gpu` here, AUDION_VS_USE_CUDA became AUDION_VS_BM3D;
- backend of the neural presets (auto | trt | ort_dml | ort_cpu): no field of its own - PROCESSING says where the network
  runs, and the service hands AUDION_VS_BACKEND to the .vpy (auto - auto, cpu - ort_cpu, gpu - TensorRT or DirectML);
- the decoder ("DEC EXP"): gone - the engine decodes on the CPU whatever it is asked;
- the models General and General, denoise of Real-ESRGAN: gone - vs-mlrt has no general model of Real-ESRGAN, and the
  .vpy of 2.0.3 ran animevideov3 in their place; a record with one of them is the run of animevideov3;
- the place of the result: a folder by the preset and the encoder, the name of the source kept, where it was
  output\\<name>__<preset>.<ext>; the extension is the same;
- a folder of a profile: every video under it with the tree kept - the flat walk (no --recursive) and --no-mirror are gone;
- a result that is there: passed over unless `overwrite`, as the batch did; a single file was written over with -y.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from system_core.core import operation_model as model
from system_core.core.manifest import load_manifest, manifest_path
from system_core.engine import encoding, env as _env
from system_core.engine import presets as P
from system_core.services.vs_service import profile_of

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = load_manifest(manifest_path(ROOT))
RECORDS = json.loads((ROOT / "tests" / "former_window_commands.json").read_text(encoding="utf-8"))["records"]
_LITE = {r["clicks"]["preset"] for r in RECORDS if r["kind"] == "preset"}
# Presets of the former window left out on purpose, with why. The records stay as they were taken.
LEFT_OUT = {
    # RIFE on TensorRT gives wrong frames between the frames on an RTX 5070 (any TensorRT, fp16 and fp32), and on the
    # processor through OpenVINO a new 4K frame takes 1.28 s; out until a right way on the video card (the owner,
    # 20.10.2026; docs\DECISIONS_EN.md, "No frame interpolation").
    "vsmlrt_rife_60fps",
}
RECORDS += [r for r in json.loads((ROOT / "tests" / "former_full" / "former_window_commands.json").read_text(encoding="utf-8"))["records"]
            if r["kind"] == "preset" and r["clicks"]["preset"] not in _LITE and r["clicks"]["preset"] not in LEFT_OUT]
ENGINE_FLAGS = {"--palette", "--preset", "--input", "--output", "--encoder", "--decode-backend", "--vs-accel", "--name",
                "--input-dir", "--output-dir", "--container"}
SWITCHES = {"--recursive", "--no-mirror", "--overwrite", "--no-audio"}
ACCEL = {"cpu": "cpu", "cuda": "gpu"}
# The backend of a neural preset as PROCESSING says it, and the card that makes "gpu" TensorRT or DirectML.
BACKEND_ACCEL = {"auto": ("auto", ""), "trt": ("gpu", "NVIDIA GeForce RTX 5070"), "ort_dml": ("gpu", "0"),
                 "ort_cpu": ("cpu", "0")}


def parse(argv: list[str]) -> tuple[dict[str, str], dict[str, str], set[str]]:
    """The argv of main.py: its own options, the parameters of the preset (as fields of the manifest), its switches."""
    words = argv[3:]
    own, params, switches = {}, {}, set()
    index = 0
    while index < len(words):
        word = words[index]
        if word in SWITCHES:
            switches.add(word)
            index += 1
            continue
        value = words[index + 1]
        if word in ENGINE_FLAGS:
            own[word] = value
        else:
            params["preset" if word == "--qtgmc-preset" else word[2:].replace("-", "_")] = value
        index += 2
    return own, params, switches


def env_of(palette: str, preset: str, resolved: dict) -> dict[str, str]:
    told = _env.build_env(palette=palette, preset=preset, input_path=Path(__file__), params=resolved)
    return {key: value for key, value in told.items() if key not in {"AUDION_VS_INPUT"}}


def fill(operation: str, given: dict) -> dict:
    node = model.find_node(MANIFEST, operation)
    assert not model.unknown_values(node, given), (operation, model.unknown_values(node, given))
    assert not model.wrong_values(node, given, ROOT), (operation, model.wrong_values(node, given, ROOT))
    form = model.Form(node, ROOT)
    # The window offered every hardware encoder on any machine: the check of this one does not take them back here.
    form.cache = {}
    form.open().fill(given)
    assert not form.changed(given), form.changed(given)
    return form.parameters()


def cards(encoder: str, output: str) -> dict:
    return encoding.cards_of(encoder, "mkv" if output.endswith(".mkv") else "mp4")


@pytest.mark.parametrize("record", [r for r in RECORDS if r["kind"] == "preset"],
                         ids=lambda r: "-".join(str(v) for v in r["clicks"].values() if not isinstance(v, dict)))
def test_a_preset_runs_as_the_window_ran_it(record):
    own, params, _switches = parse(record["argv"])
    palette, preset, encoder = own["--palette"], own["--preset"], own["--encoder"]
    # The backend of a neural preset is PROCESSING now.
    backend = params.pop("backend", None)
    if params.get("model") in ("general-x4v3", "general-wdn-x4v3"):
        params["model"] = "animevideov3"
    spec = P.get(palette, preset)
    node = model.find_node(MANIFEST, preset)
    fields = {model.field_id(field): field for field in node.fields}
    given = {key: model.coerce(fields[key], value) for key, value in params.items()}
    given.update(cards(encoder, own["--output"]))
    given["vs_accel"] = ACCEL[own["--vs-accel"]] if backend is None else BACKEND_ACCEL[backend][0]
    parameters = fill(preset, given)

    assert parameters["palette"] == palette
    assert encoding.encoder_from_cards(parameters) == encoder
    assert encoding.extension(encoder, parameters["encode_container"]) == Path(own["--output"]).suffix
    new = env_of(palette, preset, spec.resolve({k: v for k, v in parameters.items() if k in spec.params}))
    old = env_of(palette, preset, spec.resolve(params))
    if "AUDION_VS_NOISE" in new:
        assert new.pop("AUDION_VS_NOISE") == "auto"
        old.pop("AUDION_VS_NOISE", None)
    assert new == old
    if backend is None:
        assert parameters["vs_accel"] == ACCEL[own["--vs-accel"]]
        return
    from system_core.services import vs_service

    card = BACKEND_ACCEL[backend][1]
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("AUDION_VS_RTX", card) if card else patch.delenv("AUDION_VS_RTX", raising=False)
        told = vs_service._accel_env(parameters["vs_accel"], preset)
    assert told["AUDION_VS_BACKEND"] == backend or (backend == "auto" and told["AUDION_VS_BACKEND"] == "auto")


@pytest.mark.parametrize("record", [r for r in RECORDS if r["kind"] in ("profile", "batch")],
                         ids=lambda r: "-".join(f"{k}={v}" for k, v in r["clicks"].items()))
def test_a_profile_runs_as_the_window_ran_it(record):
    own, _params, switches = parse(record["argv"])
    name, encoder = own["--name"], own["--encoder"]
    output = own.get("--output", "x." + own.get("--container", "mp4"))
    given = {"profile": name, **cards(encoder, output), "vs_accel": ACCEL[own["--vs-accel"]],
             "overwrite": "--overwrite" in switches}
    parameters = fill("profile_run", given)
    assert encoding.encoder_from_cards(parameters) == encoder
    assert parameters["overwrite"] is ("--overwrite" in switches)
    profile = profile_of(ROOT, name)
    spec = P.get(profile["palette"], profile["preset"])
    # The parameters of the preset are the profile's, as main.py apply-profile took them.
    resolved = spec.resolve({k: v for k, v in (profile.get("params") or {}).items() if k != "use_cuda"})
    assert env_of(spec.palette, spec.name, resolved) == env_of(spec.palette, spec.name, spec.resolve(profile.get("params") or {}))


def test_the_record_covers_every_preset_and_every_profile():
    from system_core.services.vs_service import profile_options

    presets = {(r["clicks"]["palette"], r["clicks"]["preset"]) for r in RECORDS if r["kind"] == "preset"}
    assert presets == set(P.REGISTRY)
    recorded = {r["clicks"]["profile"] for r in RECORDS if r["kind"] == "profile"}
    assert recorded <= {option["value"] for option in profile_options(ROOT)}
