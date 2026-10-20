"""The frame of the card FRAME of the window: one moment of a video before and after a preset, as two PNG.

Media Tools works with files, VS Engine with the picture: a preset is chosen by eye. `vs_cli.cmd frame` takes the
operation of a page with its values, as `run` takes them - a preset of a palette, or a profile with the preset it
names - and renders one frame of a video of the Source through the same .vpy with the same environment
(engine\\frame_render.py in the Python of VapourSynth); "before" is the same frame of the source as the presets load it.
Nothing is encoded and nothing is written into the Target: the pictures go to ._runtime\\frame unless --out names a folder.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import operation_model as model

SIDES = ("both", "before", "after")
TIMEOUT = 900


def preset_of(root: Path, node: Any, parameters: dict[str, Any]) -> tuple[str, str, dict[str, Any], str]:
    """The palette, the preset, its values and the reason it cannot be pictured ("" - it can)."""
    service = node.service.rsplit(":", 1)[-1]
    if service == "run_preset":
        return str(parameters.get("palette") or ""), node.id, parameters, ""
    if service == "profile_run":
        from system_core.services.vs_service import profile_of

        name = str(parameters.get("profile") or "")
        profile = profile_of(root, name) or {}
        if not profile:
            return "", "", {}, f"no profile {name!r} in config\\profiles"
        values = {key: value for key, value in (profile.get("params") or {}).items() if key != "use_cuda"}
        return str(profile.get("palette") or ""), str(profile.get("preset") or ""), values, ""
    return "", "", {}, f"{node.id!r} is no preset and no profile: it has no picture"


def render(root: Path, node: Any, parameters: dict[str, Any], file: Path, at: float, out: Path,
           sides: str = "both", max_width: int = 1920) -> dict[str, Any]:
    """The pictures, or {"error": reason}. Refused before anything runs: no engine, no MLRT for a neural preset."""
    from system_core.engine import env as _env
    from system_core.engine import presets as _presets
    from system_core.engine.paths import PATHS
    from system_core.services.vs_service import _accel_env

    from .machine import mlrt
    from .camera_raw import hint, raw_of

    palette, preset, values, refusal = preset_of(root, node, parameters)
    if refusal:
        return {"error": refusal}
    if raw := raw_of(file):
        return {"error": f"{raw.name} is not read by the engine: {hint(raw)}"}
    if not PATHS.vs_python.exists():
        return {"error": f"VapourSynth is not installed ({PATHS.vs_python}): SETUP - install_vapoursynth"}
    preset_node = model.find_node(_manifest(root), preset)
    if getattr(preset_node, "needs", "") == "mlrt" and not mlrt(root):
        return {"error": f"{preset} runs on vs-mlrt, which is not installed: SETUP - install_mlrt"}
    spec = _presets.get(palette, preset)
    resolved = spec.resolve({key: value for key, value in values.items() if key in spec.params})
    env = {**os.environ, **_env.build_env(palette=palette, preset=preset, input_path=file, params=resolved),
           **_accel_env(str(parameters.get("vs_accel") or "auto"), preset)}
    env["PYTHONPATH"] = str(PATHS.presets_dir) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    out.mkdir(parents=True, exist_ok=True)
    for name in ("before.png", "after.png"):
        if sides in ("both", name.split(".")[0]):
            (out / name).unlink(missing_ok=True)
    command = [str(PATHS.vs_python), str(Path(__file__).resolve().parents[1] / "engine" / "frame_render.py"),
               str(spec.vpy), f"{min(1.0, max(0.0, at)):.6f}", str(out), sides, str(int(max_width))]
    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    try:
        done = subprocess.run(command, capture_output=True, env=env, timeout=TIMEOUT, cwd=str(root), creationflags=creation)
    except subprocess.TimeoutExpired:
        return {"error": f"the frame took longer than {TIMEOUT} s"}
    output = (done.stdout or b"").decode("utf-8", errors="replace")
    told: dict[str, Any] = {}
    for line in reversed(output.splitlines()):
        if line.strip().startswith("{"):
            try:
                told = json.loads(line)
            except ValueError:
                continue
            break
    if done.returncode != 0 or not told or told.get("error"):
        errors = (done.stderr or b"").decode("utf-8", errors="replace").strip().splitlines()
        reason = told.get("error") or (errors[-1] if errors else f"exit code {done.returncode}")
        return {"error": str(reason)}
    noise = [line.strip() for line in (done.stderr or b"").decode("utf-8", errors="replace").splitlines()
             if line.startswith("[NOISE]")]
    told.update({"palette": palette, "preset": preset, "file": str(file), "at": at, "params": resolved})
    if noise:
        told["noise"] = noise[-1]
    return told


def _manifest(root: Path) -> Any:
    from .manifest import load_manifest, manifest_path

    return load_manifest(manifest_path(Path(root)))
