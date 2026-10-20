"""What is checked before a run begins: a run that cannot begin is refused with the reason and starts nothing.

Each check is a line `[PREFLIGHT] LEVEL subject: detail` in the journal. FAIL refuses the run (exit 2, outcome `refused`);
WARN and OK only say.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .camera_raw import ffmpeg_reads, hint, raw_of, stray_raw
from .sources import source_files

# What a service needs. engine - VapourSynth, vspipe, FFmpeg, ffprobe; ffmpeg - FFmpeg and ffprobe; videos - a video in
# the Source; video - the first video of the Source.
NEEDS = {
    "run_preset": {"engine", "videos"},
    "profile_run": {"engine", "videos", "profile"},
    "bench_presets": {"engine"},
    "bench_gpu": {"engine", "videos"},
    "probe_source": {"ffmpeg", "videos"},
    "source_list": {"source"},
    "hardware_capabilities": {"ffmpeg"},
    "profile_save": {"profile_save"},
    "install_mlrt": {"rtx", "vapoursynth"},
}
INSTALLERS = {"VS-host Python": "install_vapoursynth", "vspipe.exe": "install_vapoursynth",
              "ffmpeg.exe": "install_ffmpeg", "ffprobe.exe": "install_ffmpeg"}


def _some(paths: list[Path], name=lambda path: path.name) -> str:
    return ", ".join(name(path) for path in paths[:3]) + (f" and {len(paths) - 3} more" if len(paths) > 3 else "")


def _camera_raw_checks(checks: list[dict[str, str]], context: Any, source: Path, files: list[Path]) -> None:
    """Camera RAW the engine does not read (core\\camera_raw.py, config\\camera_raw.yaml), said with what opens it: all of
    the Source - refused; some - said here, and failed one by one in the run; its own files, which no run takes - named."""
    from system_core.engine.paths import PATHS

    reads = ffmpeg_reads(str(PATHS.ffprobe)) if PATHS.ffprobe.exists() else None
    found: dict[str, list[tuple[Path, Any]]] = {}
    for file in files:
        if raw := raw_of(file, reads):
            found.setdefault(raw.kind, []).append((file, raw))
    every = sum(len(items) for items in found.values()) == len(files)
    for items in found.values():
        names = dict(items)
        _check(checks, context, "FAIL" if every else "WARN", "camera RAW",
               f"the engine does not read {_some(list(names), lambda file: f'{file.name} ({names[file].name})')}: {hint(items[0][1])}")
    for paths in stray_raw(source).values():
        if raw := raw_of(paths[0]):
            _check(checks, context, "WARN" if files else "FAIL", "camera RAW",
                   f"{len(paths)} file(s) of {raw.name} are not taken ({_some(paths)}): {hint(raw)}")


def _check(checks: list[dict[str, str]], context: Any, level: str, subject: str, detail: str) -> None:
    checks.append({"level": level, "subject": subject, "detail": detail})
    context.log(f"[PREFLIGHT] {level} {subject}: {detail}")


def run_preflight(context: Any) -> dict[str, Any]:
    from system_core.engine.paths import PATHS

    service = str(context.operation.service).rsplit(":", 1)[-1]
    needs = NEEDS.get(service, set())
    checks: list[dict[str, str]] = []
    if not needs and not getattr(context.operation, "needs", ""):
        return {"ok": True, "checks": checks}
    if "vapoursynth" in needs and not PATHS.vs_python.exists():
        _check(checks, context, "FAIL", "VapourSynth", f"not installed ({PATHS.vs_python}); SETUP - install_vapoursynth first")
    if "rtx" in needs:
        from .machine import rtx

        card = rtx()
        _check(checks, context, "OK" if card else "FAIL", "NVIDIA RTX",
               card or "not found: nvidia-smi names no RTX card - TensorRT of MLRT needs one")
    if getattr(context.operation, "needs", "") == "mlrt":
        from .machine import mlrt

        release = mlrt(context.paths.root)
        _check(checks, context, "OK" if release else "FAIL", "MLRT",
               f"vs-mlrt {release}" if release else "not installed - SETUP - install_mlrt (offered with an NVIDIA RTX card)")
    if "engine" in needs or "ffmpeg" in needs:
        wanted = [("VS-host Python", PATHS.vs_python), ("vspipe.exe", PATHS.vspipe)] if "engine" in needs else []
        wanted += [("ffmpeg.exe", PATHS.ffmpeg), ("ffprobe.exe", PATHS.ffprobe)]
        for label, path in wanted:
            if path.exists():
                continue
            _check(checks, context, "FAIL", label, f"not installed ({path}); SETUP - {INSTALLERS[label]}, or builder_main.cmd")
        if not any(item["level"] == "FAIL" for item in checks):
            _check(checks, context, "OK", "engine" if "engine" in needs else "FFmpeg", "installed")
    source = Path(context.paths.source)
    if needs & {"videos", "source"}:
        if not source.exists():
            _check(checks, context, "FAIL", "Source", f"not found: {source}")
        elif "videos" in needs:
            files = source_files(source, context.paths.target)
            if files:
                _check(checks, context, "OK", "Source", f"{len(files)} video(s) in {source}")
            else:
                _check(checks, context, "FAIL", "Source", f"no video in {source}")
            if "engine" in needs:
                _camera_raw_checks(checks, context, source, files)
    if "profile" in needs:
        from system_core.engine import runner
        from system_core.services.vs_service import profile_of

        name = str(context.operation.parameters.get("profile") or "")
        profile = profile_of(context.paths.root, name)
        if not profile:
            _check(checks, context, "FAIL", "Profile", f"no profile {name!r} in config\\profiles")
        else:
            problem = profile_problem(context.paths.root, profile)
            if problem:
                _check(checks, context, "FAIL", "Profile", f"{name}: {problem}")
            elif _needs_of(context.paths.root, str(profile.get("preset") or "")) == "mlrt":
                from .machine import mlrt

                if not mlrt(context.paths.root):
                    _check(checks, context, "FAIL", "MLRT", f"{name} runs the neural preset {profile.get('preset')}: vs-mlrt "
                                                            "is not installed - SETUP - install_mlrt")
            encoder = str(profile.get("encoder") or "")
            if encoder and encoder not in runner.ENCODERS:
                _check(checks, context, "WARN", "Profile", f"{name} names the encoder {encoder!r}, which the engine does "
                                                           "not have: the cards of the form say what is written")
    if "profile_save" in needs:
        from system_core.services.vs_service import profile_save_problem

        problem = profile_save_problem(context.paths.root, context.operation.parameters)
        _check(checks, context, "FAIL" if problem else "OK", "Profile", problem or "may be saved")
    return {"ok": not any(item["level"] == "FAIL" for item in checks), "checks": checks}


def _needs_of(root: Path, preset: str) -> str:
    from .manifest import load_manifest, manifest_path
    from .operation_model import find_node

    node = find_node(load_manifest(manifest_path(Path(root))), preset)
    return str(getattr(node, "needs", "") or "")


def profile_problem(root: Path, profile: dict[str, Any]) -> str:
    """What is wrong with a profile against the manifest: its preset, its fields, their values; "" - nothing."""
    from .manifest import load_manifest, manifest_path
    from . import operation_model as model

    manifest = load_manifest(manifest_path(root))
    node = model.find_node(manifest, str(profile.get("preset") or ""))
    if node is None or not node.service.endswith(":run_preset"):
        return f"no preset {profile.get('preset')!r}"
    if profile.get("palette") and profile["palette"] != node.parameters.get("palette"):
        return f"the preset {node.id} is of {node.parameters.get('palette')}, not of {profile['palette']}"
    params = profile.get("params") or {}
    if not isinstance(params, dict):
        return "params is not an object"
    from system_core.engine.presets import MACHINE_FIELDS

    # use_cuda of the profiles of 2.0.3: BM3DCUDA does not load on VapourSynth R80+, vs_accel took its place.
    given = {key: value for key, value in params.items() if key != "use_cuda"}
    unknown = [key for key in model.unknown_values(node, given) if key not in MACHINE_FIELDS]
    if unknown:
        return "the preset has no fields " + ", ".join(unknown)
    wrong = model.wrong_values(node, given, root)
    return "; ".join(wrong)
