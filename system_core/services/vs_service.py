"""The services of the operations of config\\tool_manifest.yaml: a preset, a profile, SERVICE.

A preset runs on the Source - one file, or a folder with every video under it - into
<Target>\\<Palette>\\<preset>_<encoder>\\<the folders of the Source>\\<name>.<ext>; a profile into
<Target>\\Profiles\\<profile>_<encoder>\\... The name of the source is kept, the folder says what made the file.

A result is written under "<name>.writing-<pid>-<token>.<ext>" and takes its own name only whole: STOP, a failure or a
window that fell leave no half-written file where a finished one is looked for (until 3.0.0 a batch took the file left
by a stop for done). A result that is there is passed over ([SKIP], `skipped`) unless `overwrite`.
"""
from __future__ import annotations

import json
import os
import platform
import re
import secrets
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from system_core.core.jobs import JobContext, OperationCancelled, hidden_subprocess_kwargs, run_process
from system_core.core.camera_raw import camera_raw, ffmpeg_reads, hint, raw_of
from system_core.core.sources import relative_folder, source_files

# The folder of a palette under the Target: its name in the ribbon of the window, as a person reads it.
PALETTE_FOLDERS = {"precision": "Precision", "film_looks": "Film Looks", "retro": "Retro", "restoration": "Restoration"}
PROFILES_FOLDER = "Profiles"
# vs_accel: where BM3D runs (audion_lib.bm3d reads AUDION_VS_BM3D). auto names none: audion_lib takes bm3dvk when the core
# sees a Vulkan device, else bm3d on the CPU.
ACCEL_BM3D = {"auto": "", "cpu": "cpu", "gpu": "vulkan"}
PROFILE_NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


# --- the choices the engine makes ---------------------------------------------------------------------------------


def profiles_dir(root: Path) -> Path:
    return Path(root) / "config" / "profiles"


def profiles(root: Path) -> dict[str, dict[str, Any]]:
    """The profiles of config\\profiles (the built-ins are written there on first use, as before)."""
    from system_core.engine import profile as _profile

    return _profile.all_profiles(profiles_dir(root))


def profile_of(root: Path, name: str) -> dict[str, Any] | None:
    return profiles(root).get(name) if name else None


def profile_options(root: Path) -> list[dict[str, Any]]:
    return [{"value": name, "label": name, "label_ru": name, "tooltip": str(data.get("description") or ""),
             "tooltip_ru": str(data.get("description_ru") or data.get("description") or "")}
            for name, data in sorted(profiles(root).items())]


def preset_options(root: Path) -> list[dict[str, Any]]:
    from system_core.core.manifest import load_manifest, manifest_path
    from system_core.core.operation_model import presets

    return [{"value": node.id, "label": node.title, "label_ru": node.title_ru}
            for node in presets(load_manifest(manifest_path(root)))]


# --- a run of a preset on the Source ------------------------------------------------------------------------------


def _draft(final: Path) -> Path:
    while True:
        draft = final.with_name(f"{final.stem}.writing-{os.getpid()}-{secrets.token_hex(3)}{final.suffix}")
        if not draft.exists():
            return draft


def _clock(seconds: float) -> str:
    whole = max(0, int(round(seconds)))
    hours, rest = divmod(whole, 3600)
    return f"{hours}:{rest // 60:02d}:{rest % 60:02d}" if hours else f"{rest // 60:02d}:{rest % 60:02d}"


class FrameBar:
    """vspipe's counter as the bar of a file: `[PROGRESS] clip.mov [#####---] 42% 1234/2940 9.8 fps ETA 02:10`, every 5 %
    or 5 s, with vspipe's own line under it - the line a person at a console sees beside the bar."""

    def __init__(self, context: JobContext, name: str) -> None:
        self.context, self.name = context, name
        self.said_share, self.said_at = -1.0, 0.0
        self.last: tuple[int, int, float] | None = None
        self.began = time.monotonic()

    def __call__(self, frame: int, frames: int, fps: float) -> None:
        # vspipe tells its rate once a second of work has gone by; before that the rate is counted here.
        if fps <= 0 and frame > 0:
            fps = frame / max(time.monotonic() - self.began, 1e-3)
        self.last = (frame, frames, fps)
        share = frame / frames if frames else 0.0
        self.context.progress_inside(share)
        now = time.monotonic()
        if share >= self.said_share + 0.05 or now - self.said_at >= 5.0 or (frames and frame >= frames):
            self.say()
            self.said_share, self.said_at = share, now

    def say(self) -> None:
        if self.last is None:
            return
        frame, frames, fps = self.last
        share = frame / frames if frames else 0.0
        width = 24
        bar = "#" * int(round(share * width)) + "-" * (width - int(round(share * width)))
        eta = f" ETA {_clock((frames - frame) / fps)}" if fps > 0 and frames > frame else ""
        self.context.log(f"[PROGRESS] {self.name} [{bar}] {int(round(share * 100)):3d}% {frame}/{frames} {fps:.2f} fps{eta}")
        self.context.log(f"Frame: {frame}/{frames} ({fps:.2f} fps)")

    def end(self) -> None:
        if self.last is not None and self.said_share < 1.0:
            frame, frames, fps = self.last
            self.last = (frames, frames, fps)
            self.say()


def _accel_env(vs_accel: str, preset: str = "") -> dict[str, str]:
    """PROCESSING for the .vpy: BM3D by AUDION_VS_BM3D; a neural preset by AUDION_VS_BACKEND (auto | trt | ort_dml |
    ort_cpu) and AUDION_VS_HAS_CUDA, which puts TensorRT first in the chain of auto (audion_lib.vsmlrt_backend_chain)."""
    accel = str(vs_accel or "auto")
    if _accel_of(preset) == "mlrt":
        from system_core.core.machine import rtx

        card = bool(rtx())
        backend = {"cpu": "ort_cpu", "gpu": "trt" if card else "ort_dml"}.get(accel, "auto")
        return {"AUDION_VS_BACKEND": backend, **({"AUDION_VS_HAS_CUDA": "1"} if card else {})}
    wanted = ACCEL_BM3D.get(accel, "")
    return {"AUDION_VS_BM3D": wanted} if wanted else {}


def _accel_of(preset: str) -> str:
    """What of the preset PROCESSING moves (accel of the manifest): a profile names its preset, not its node."""
    if not preset:
        return ""
    from system_core.core.manifest import load_manifest, manifest_path
    from system_core.core.operation_model import find_node
    from system_core.engine.paths import PATHS

    node = find_node(load_manifest(manifest_path(PATHS.root)), preset)
    return str(getattr(node, "accel", "") or "")


def _run_files(context: JobContext, *, palette: str, preset: str, values: dict[str, Any], folder: Path,
               label: str) -> dict[str, Any]:
    """The preset on every video of the Source into `folder`: drafts, passes over, stops; the outcome counted."""
    from system_core.engine import encoding, env as _env, runner
    from system_core.engine import presets as _presets

    parameters = context.operation.parameters
    spec = _presets.get(palette, preset)
    resolved = spec.resolve({key: value for key, value in values.items() if key in spec.params})
    encoder = encoding.encoder_from_cards(parameters)
    extension = encoding.extension(encoder, str(parameters.get("encode_container") or "mp4"))
    overwrite = bool(parameters.get("overwrite"))
    dry = bool(parameters.get("dry_run"))
    accel = str(parameters.get("vs_accel") or "auto")
    source, target = Path(context.paths.source), Path(context.paths.target)
    files = source_files(source, target)

    context.log(f"[RUN] {label}: {palette}/{preset}, encoder {encoder}, BM3D {accel}")
    context.log(f"      parameters: {json.dumps(resolved, ensure_ascii=False, sort_keys=True)}")
    context.log(f"      into: {folder}")
    context.units(len(files))
    told: dict[str, Any] = {"ok": True, "processed": 0, "skipped": 0, "failed": 0, "encoder": encoder,
                            "palette": palette, "preset": preset, "params": resolved, "vs_accel": accel,
                            "output_folder": str(folder), "files": []}
    if dry:
        told["dry_run"], told["commands"] = True, []
    from system_core.engine.paths import PATHS

    reads = ffmpeg_reads(str(PATHS.ffprobe))
    for index, file in enumerate(files):
        final = folder / relative_folder(file, source) / f"{file.stem}{extension}"
        entry: dict[str, Any] = {"source": str(file), "result": str(final)}
        told["files"].append(entry)
        # Camera RAW: VapourSynth sees no video track in it - said in one line with what opens it, not a trace of vspipe.
        if raw := raw_of(file, reads):
            context.log(f"[FAIL] {file.name}: {raw.name} is not read by the engine - {hint(raw)}")
            entry.update(outcome="failed", error=f"{raw.name} is not read by the engine")
            told["failed"] += 1
            context.progress((index + 1) / len(files))
            continue
        if final.exists() and final.stat().st_size > 0 and not overwrite:
            context.log(f"[SKIP] {final}: already there (overwrite = true makes it again)")
            entry["outcome"] = "skipped"
            told["skipped"] += 1
            context.progress((index + 1) / len(files))
            continue
        env_extras = _env.build_env(palette=palette, preset=preset, input_path=file, params=resolved)
        env_extras.update(_accel_env(accel, preset))
        if dry:
            report = runner.run_pipeline(preset_path=spec.vpy, input_path=file, output_path=final,
                                         env_extras=env_extras, encoder=encoder, log_callback=context.log, dry_run=True)
            told["commands"].append({"source": str(file), "result": str(final), **report["commands"]})
            entry["outcome"] = "dry_run"
            continue
        context.log(f"[FILE] {index + 1}/{len(files)} {file.name}")
        draft = _draft(final)
        bar = FrameBar(context, file.name)
        try:
            report = runner.run_pipeline(preset_path=spec.vpy, input_path=file, output_path=draft,
                                         env_extras=env_extras, encoder=encoder, log_callback=context.log,
                                         progress=bar, cancelled=context.cancelled)
            bar.end()
            os.replace(draft, final)
        except runner.PipelineCancelled:
            draft.unlink(missing_ok=True)
            entry["outcome"] = "stopped"
            told["cancelled"] = True
            raise OperationCancelled("Operation stopped by the user.")
        except Exception as error:  # noqa: BLE001 - a file that fails is counted, the next one goes on
            draft.unlink(missing_ok=True)
            context.log(f"[FAIL] {file.name}: {error}")
            entry.update(outcome="failed", error=str(error)[-2000:])
            told["failed"] += 1
            context.progress((index + 1) / len(files))
            continue
        report = {**report, "output_path": str(final)}
        (context.report_dir / f"{index + 1:03d}_{file.stem}.json").write_text(
            json.dumps({"source": str(file), "palette": palette, "preset": preset, "params": resolved, **report},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        context.log(f"[OK] {final.name}: {report['output_size']:,} B in {report['elapsed_s']} s")
        entry.update(outcome="done", seconds=report["elapsed_s"], size=report["output_size"])
        if report.get("noise"):
            entry["noise"] = report["noise"]
        told["processed"] += 1
        context.progress((index + 1) / len(files))
    told["ok"] = told["failed"] == 0
    if dry:
        context.log(f"[DRY RUN] {len(told['commands'])} file(s) said, {told['skipped']} passed over; nothing was run")
    else:
        context.log(f"[DONE] {told['processed']} done, {told['skipped']} passed over, {told['failed']} failed")
    return told


def run_preset(context: JobContext) -> dict[str, Any]:
    parameters = context.operation.parameters
    palette, preset = str(parameters.get("palette") or ""), context.operation.id
    from system_core.engine import encoding

    encoder = encoding.encoder_from_cards(parameters)
    folder = Path(context.paths.target) / PALETTE_FOLDERS.get(palette, palette) / f"{preset}_{encoder}"
    return _run_files(context, palette=palette, preset=preset, values=parameters, folder=folder, label="preset")


def profile_run(context: JobContext) -> dict[str, Any]:
    from system_core.engine import encoding

    parameters = context.operation.parameters
    name = str(parameters.get("profile") or "")
    profile = profile_of(context.paths.root, name) or {}
    encoder = encoding.encoder_from_cards(parameters)
    folder = Path(context.paths.target) / PROFILES_FOLDER / f"{name}_{encoder}"
    values = {key: value for key, value in (profile.get("params") or {}).items() if key != "use_cuda"}
    told = _run_files(context, palette=str(profile.get("palette") or ""), preset=str(profile.get("preset") or ""),
                      values=values, folder=folder, label=f"profile {name}")
    told["profile"] = name
    return told


def profile_save(context: JobContext) -> dict[str, Any]:
    """The form of a preset and the encoder of the cards as config\\profiles\\<name>.json (preflight checked it)."""
    from system_core.engine import encoding, profile as _profile
    from system_core.engine import presets as _presets

    parameters = context.operation.parameters
    name = str(parameters.get("profile_name") or "").strip()
    spec = _presets.by_name(str(parameters.get("profile_preset") or ""))
    given = json.loads(str(parameters.get("profile_values") or "{}") or "{}")
    params = spec.resolve(given)
    encoder = encoding.encoder_from_cards(parameters)
    path = _profile.save_profile(profiles_dir(context.paths.root), name, palette=spec.palette, preset=spec.name,
                                 params=params, encoder=encoder,
                                 description=str(parameters.get("profile_description") or ""),
                                 force=bool(parameters.get("overwrite")))
    context.log(f"[OK] profile {name}: {spec.palette}/{spec.name}, encoder {encoder} -> {path}")
    return {"ok": True, "profile": name, "path": str(path), "preset": spec.name, "params": params, "encoder": encoder}


def profile_save_problem(root: Path, parameters: dict[str, Any]) -> str:
    """Why the profile may not be saved; "" when it may."""
    from system_core.core import operation_model as model
    from system_core.core.manifest import load_manifest, manifest_path

    name = str(parameters.get("profile_name") or "").strip()
    if not PROFILE_NAME.match(name):
        return f"the name {name!r} is not one of Latin letters, digits, - and _"
    if (profiles_dir(root) / f"{name}.json").exists() and not parameters.get("overwrite"):
        return f"the profile {name} is there already: overwrite = true replaces it"
    node = model.find_node(load_manifest(manifest_path(root)), str(parameters.get("profile_preset") or ""))
    if node is None or not node.service.endswith(":run_preset"):
        return f"no preset {parameters.get('profile_preset')!r}"
    try:
        given = json.loads(str(parameters.get("profile_values") or "{}") or "{}")
    except ValueError as error:
        return f"the settings of the preset are no JSON: {error}"
    if not isinstance(given, dict):
        return "the settings of the preset are a JSON object: {\"field\": value}"
    from system_core.engine.presets import MACHINE_FIELDS

    unknown = [key for key in model.unknown_values(node, given) if key not in MACHINE_FIELDS]
    if unknown:
        return f"the preset {node.id} has no fields " + ", ".join(unknown)
    return "; ".join(model.wrong_values(node, {k: v for k, v in given.items() if k not in MACHINE_FIELDS}, root))


# --- SERVICE --------------------------------------------------------------------------------------------------------


def _runtime_python(root: Path) -> Path:
    return Path(root) / "runtime" / "python.exe"


def _powershell(root: Path) -> str:
    """The PowerShell the installers run in: the program's own first, then the one of the machine."""
    for candidate in (Path(root) / "App" / "AudionPs.exe", Path(root) / "system_core" / "powershell" / "pwsh.exe"):
        if candidate.exists():
            return str(candidate)
    return shutil.which("pwsh.exe") or shutil.which("powershell.exe") or "powershell.exe"


def _script(context: JobContext, name: str, *arguments: str) -> dict[str, Any]:
    """A .cmd of install\\ without its pauses, called by its full path (a folder is no command path of cmd)."""
    script = Path(context.paths.root) / "install" / name
    code, lines = run_process(context, ["cmd.exe", "/d", "/c", "call", str(script), *arguments, "/NOPAUSE"],
                              extra_env={"AUDION_NO_PAUSE": "1"}, check=False)
    return {"ok": code == 0, "exit_code": code, "script": str(script), "message": lines[-1] if lines else ""}


def doctor(context: JobContext) -> dict[str, Any]:
    told = context.report_dir / "doctor.json"
    code, _lines = run_process(context, [str(_runtime_python(context.paths.root)), "-X", "utf8",
                                         str(Path(context.paths.root) / "system_core" / "doctor.py"), "--json", str(told)],
                               extra_env={"NO_COLOR": "1"}, check=False)
    data: dict[str, Any] = {}
    try:
        data = json.loads(told.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return {"ok": code == 0, "exit_code": code, **data}


def _probe_row(file: Path) -> dict[str, Any]:
    from system_core.engine.probe import video_summary

    summary = video_summary(file)
    video = summary.get("video") or {}
    return {"file": str(file), "width": video.get("width"), "height": video.get("height"), "fps": video.get("fps"),
            "duration_s": round(float(summary.get("duration_s") or 0), 3), "codec": video.get("codec"),
            "pix_fmt": video.get("pix_fmt"), "color_range": video.get("color_range"),
            "colour": "/".join(str(video.get(key) or "-") for key in ("color_primaries", "color_transfer", "color_space")),
            "audio": (summary.get("audio") or {}).get("codec") if summary.get("audio") else None,
            "size_bytes": summary.get("size_bytes")}


def probe_source(context: JobContext) -> dict[str, Any]:
    files = source_files(Path(context.paths.source), Path(context.paths.target))
    context.units(len(files))
    rows, failed = [], 0
    for index, file in enumerate(files):
        try:
            row = _probe_row(file)
            rows.append(row)
            context.log(f"[PROBE] {file.name} | {row['width']}x{row['height']} | {row['fps']} fps | {row['duration_s']} s | "
                        f"{row['codec']} {row['pix_fmt']} | range {row['color_range'] or '-'} | {row['colour']} | "
                        f"audio {row['audio'] or '-'}")
        except Exception as error:  # noqa: BLE001 - a file ffprobe cannot read is told and counted
            failed += 1
            context.log(f"[FAIL] {file.name}: {error}")
        context.progress((index + 1) / len(files))
    return {"ok": failed == 0, "processed": len(rows), "failed": failed, "files": rows}


def source_list(context: JobContext) -> dict[str, Any]:
    source = Path(context.paths.source)
    files = source_files(source, Path(context.paths.target))
    for file in files:
        context.log(f"[FILE] {file}")
    context.log(f"[LIST] {len(files)} video(s) in {source}")
    return {"ok": True, "count": len(files), "files": [str(file) for file in files]}


# The hardware encoders a run can be given (runner.ENCODERS), tried with a short encode of a test picture.
HARDWARE_ENCODERS = {"h264_nvenc": "h264_nvenc_q17", "hevc_nvenc": "h265_nvenc_q17", "h264_qsv": "h264_qsv_q17",
                     "hevc_qsv": "h265_qsv_q17", "h264_amf": "h264_amf_q17", "hevc_amf": "h265_amf_q17"}
UNAVAILABLE = ("cannot load", "no device", "no capable devices", "not available", "unsupported", "not supported",
               "failed to initialise", "failed to initialize", "error creating", "could not open encoder",
               "no nvenc capable", "driver does not support", "unknown encoder")


def hardware_capabilities(context: JobContext) -> dict[str, Any]:
    from system_core.engine import runner
    from system_core.engine.paths import PATHS

    listed = subprocess.run([str(PATHS.ffmpeg), "-hide_banner", "-encoders"], capture_output=True, text=True,
                            errors="replace", timeout=30, **hidden_subprocess_kwargs()).stdout
    encoders: dict[str, dict[str, str]] = {}
    context.units(len(HARDWARE_ENCODERS))
    for index, (name, profile) in enumerate(HARDWARE_ENCODERS.items()):
        if not re.search(rf"\s{re.escape(name)}\s", listed):
            encoders[name] = {"status": "MISS", "detail": "not in this FFmpeg build"}
        else:
            out = context.report_dir / f"{name}.mp4"
            command = [str(PATHS.ffmpeg), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                       "testsrc2=size=640x360:rate=30:duration=1", *runner.ENCODERS[profile], str(out)]
            code, lines = run_process(context, command, check=False)
            if code == 0:
                encoders[name] = {"status": "OK", "detail": "a test encode passed"}
            else:
                text = next((line for line in lines if any(mark in line.lower() for mark in UNAVAILABLE)),
                            lines[-1] if lines else f"exit {code}")
                encoders[name] = {"status": "MISS" if any(mark in text.lower() for mark in UNAVAILABLE) else "FAIL",
                                  "detail": text[:240]}
            out.unlink(missing_ok=True)
        context.log(f"[{encoders[name]['status']}] {name}: {encoders[name]['detail']}")
        context.progress((index + 1) / len(HARDWARE_ENCODERS))
    cache = Path(context.paths.root) / "config" / "hardware_capabilities_cache.json"
    cache.write_text(json.dumps({"updated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "machine": platform.node(),
                                 "encoders": encoders}, ensure_ascii=False, indent=2), encoding="utf-8")
    context.log(f"Hardware cache: {cache}")
    return {"ok": True, "encoders": encoders, "cache": str(cache),
            "working": sorted(name for name, found in encoders.items() if found["status"] == "OK")}


def _test_clip(context: JobContext) -> Path:
    """A clip for the checks when the Source has no video: two seconds of a test picture with a tone, made here, at
    29.97 frames a second - tivtc_ivtc takes NTSC only and refuses anything under 29."""
    from system_core.engine.paths import PATHS

    clip = context.report_dir / "test_clip.mp4"
    run_process(context, [str(PATHS.ffmpeg), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                          "testsrc2=size=1280x720:rate=30000/1001:duration=2", "-f", "lavfi", "-i", "sine=frequency=1000:duration=2",
                          "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac",
                          str(clip)])
    return clip


def bench_presets(context: JobContext) -> dict[str, Any]:
    files = source_files(Path(context.paths.source), Path(context.paths.target))
    clip = files[0] if files else _test_clip(context)
    frames = int(context.operation.parameters.get("frames") or 1)
    told = context.report_dir / "bench_all_presets.json"
    code, _lines = run_process(context, [_powershell(context.paths.root), "-NoLogo", "-NoProfile", "-ExecutionPolicy",
                                         "Bypass", "-File", str(Path(context.paths.root) / "install" / "Bench-AllPresets.ps1"),
                                         "-ProjectRoot", str(context.paths.root), "-InputFile", str(clip),
                                         "-Frames", str(frames), "-Cuda", "off", "-ReportJson", str(told)], check=False)
    data: Any = {}
    try:
        data = json.loads(told.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        pass
    return {"ok": code == 0, "exit_code": code, "clip": str(clip), "frames": frames, "report": str(told),
            "bench": data}


VSPIPE_DONE = re.compile(r"Output\s+(\d+)\s+frames\s+in\s+([\d.]+)\s+seconds\s+\(([\d.]+)\s+fps\)")


def bench_gpu(context: JobContext) -> dict[str, Any]:
    """BM3D through Vulkan against BM3D on the CPU: shadow_denoise_sota, the same frames, vspipe with no output."""
    from system_core.engine import env as _env, presets as _presets
    from system_core.engine.paths import PATHS

    # The first video the engine reads: camera RAW it does not (the preflight has said so).
    clip = next(file for file in source_files(Path(context.paths.source), Path(context.paths.target)) if not camera_raw(file))
    frames = int(context.operation.parameters.get("frames") or 24)
    probe = ("import vapoursynth as vs; c = vs.core; "
             "print('DEVICES', len(getattr(c, 'vulkan_devices', None) or []), hasattr(c, 'bm3dvk'))")
    found = subprocess.run([str(PATHS.vs_python), "-c", probe], capture_output=True, text=True, errors="replace",
                           timeout=60, **hidden_subprocess_kwargs()).stdout
    has_device = bool(re.search(r"DEVICES\s+[1-9]\d*\s+True", found))
    spec = _presets.get("precision", "shadow_denoise_sota")
    base = _env.build_env(palette=spec.palette, preset=spec.name, input_path=clip, params=spec.resolve({}))
    base["PYTHONPATH"] = str(PATHS.presets_dir)
    sides: dict[str, Any] = {}
    for side, wanted in (("cpu", "bm3d"), ("gpu", "vulkan")):
        if side == "gpu" and not has_device:
            sides[side] = {"status": "SKIP", "detail": "VapourSynth sees no Vulkan device, or bm3dvk is not loaded"}
            context.log(f"[SKIP] BM3D on the video card: {sides[side]['detail']}")
            continue
        command = [str(PATHS.vspipe), "-p", "-e", str(frames - 1), str(spec.vpy), "."]
        code, lines = run_process(context, command, extra_env={**base, "AUDION_VS_BM3D": wanted}, check=False,
                                  line_filter=lambda line: line.startswith("Frame:"))
        done = next((VSPIPE_DONE.search(line) for line in reversed(lines) if VSPIPE_DONE.search(line)), None)
        sides[side] = ({"status": "OK", "frames": int(done[1]), "seconds": float(done[2]), "fps": float(done[3])}
                       if code == 0 and done else {"status": "FAIL", "detail": lines[-1] if lines else f"exit {code}"})
        context.log(f"[{sides[side]['status']}] BM3D {side}: " + (f"{sides[side]['fps']} fps" if done else sides[side]["detail"]))
    if sides.get("gpu", {}).get("status") == "OK" and sides.get("cpu", {}).get("status") == "OK":
        ratio = sides["gpu"]["fps"] / sides["cpu"]["fps"] if sides["cpu"]["fps"] else 0
        context.log(f"[RESULT] the video card is {ratio:.2f} times the CPU on {clip.name}")
        sides["gpu_over_cpu"] = round(ratio, 3)
    return {"ok": all(side.get("status") in ("OK", "SKIP") for side in sides.values() if isinstance(side, dict)),
            "clip": str(clip), "frames": frames, **sides}


def install_vapoursynth(context: JobContext) -> dict[str, Any]:
    return _script(context, "Install-Portable-VapourSynth.cmd")


def install_vs_plugins(context: JobContext) -> dict[str, Any]:
    return _script(context, "Install-VS-Plugins.cmd")


def install_ffmpeg(context: JobContext) -> dict[str, Any]:
    return _script(context, "Install-Portable-FFmpeg-Gyan.cmd")


def install_mlrt(context: JobContext) -> dict[str, Any]:
    # LEAN: the TensorRT resources of this card's architecture alone and the models a preset uses; DROP-CACHE: the
    # archives of the download (about 3.5 GB) do not stay in install\download once the check of the backends passed.
    return _script(context, "Install-VS-mlrt.cmd", "/LEAN", "/DROP-CACHE")


def remove_vapoursynth(context: JobContext) -> dict[str, Any]:
    return _script(context, "Uninstall-Portable-VapourSynth.cmd")
