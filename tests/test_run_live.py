"""Runs of the engine through the console command: a folder with its tree, the result passed over, the stop.

The engine must be installed (builder_main.cmd [10] [11] [13]); without it these are skipped. The clips are made here,
small, from a test picture of FFmpeg; the Source and the Target are temporary folders.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "runtime" / "python.exe"
FFMPEG = ROOT / "Tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
VSPIPE = ROOT / "system_core" / "vapoursynth" / "Scripts" / "vspipe.exe"

pytestmark = pytest.mark.skipif(not (FFMPEG.exists() and VSPIPE.exists()), reason="the engine is not installed")


def clip(path: Path, frames: int, size: str = "320x180") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    f"testsrc2=size={size}:rate=25:duration={frames / 25}", "-c:v", "libx264", "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def run(tmp: Path, *arguments: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "AUDION_LOGS": str(tmp / "logs"), "AUDION_REPORT": str(tmp / "report")}
    return subprocess.run([str(PYTHON), "-X", "utf8", str(ROOT / "system_core" / "cli.py"), "run", *arguments],
                          capture_output=True, text=True, encoding="utf-8", env=env, timeout=600)


def test_a_folder_runs_with_its_tree_and_a_second_run_passes_over(tmp_path):
    source, target = tmp_path / "src", tmp_path / "out"
    clip(source / "a.mp4", 10)
    clip(source / "deep" / "b.mov", 8)
    result = tmp_path / "first.json"
    done = run(tmp_path, "--operation", "deband_safe", "--source", str(source), "--target", str(target), "--result", str(result))
    assert done.returncode == 0, done.stdout[-3000:]
    folder = target / "Precision" / "deband_safe_h264_crf14"
    assert sorted(path.relative_to(folder).as_posix() for path in folder.rglob("*") if path.is_file()) == ["a.mp4", "deep/b.mp4"]
    assert not [path for path in target.rglob("*") if ".writing-" in path.name]
    told = json.loads(result.read_text(encoding="utf-8"))
    assert (told["outcome"], told["processed"], told["skipped"], told["failed"]) == ("done", 2, 0, 0)
    assert "[PROGRESS] a.mp4 [" in done.stdout and "Frame: " in done.stdout

    again = tmp_path / "second.json"
    done = run(tmp_path, "--operation", "deband_safe", "--source", str(source), "--target", str(target), "--result", str(again))
    told = json.loads(again.read_text(encoding="utf-8"))
    assert done.returncode == 0 and (told["processed"], told["skipped"]) == (0, 2)

    done = run(tmp_path, "--operation", "deband_safe", "--source", str(source / "a.mp4"), "--target", str(target),
               "--set", "overwrite=true", "--result", str(again))
    assert json.loads(again.read_text(encoding="utf-8"))["processed"] == 1


def test_a_dry_run_says_the_commands_and_leaves_the_target_as_it_was(tmp_path):
    source = clip(tmp_path / "src" / "a.mp4", 5)
    result = tmp_path / "dry.json"
    done = run(tmp_path, "--operation", "film_35mm", "--source", str(source), "--target", str(tmp_path / "out"),
               "--encoder", "prores_lt", "--set", "stock=500T", "--dry-run", "--result", str(result))
    assert done.returncode == 0
    command = json.loads(result.read_text(encoding="utf-8"))["data"]["commands"][0]
    assert command["env"]["AUDION_VS_STOCK"] == "500T"
    assert command["vspipe"][1:4] == ["-c", "y4m", "-p"]
    assert command["ffmpeg"][-1].endswith(str(Path("Film Looks") / "film_35mm_prores_lt" / "a.mov"))
    assert not (tmp_path / "out").exists()


def test_stop_ends_vspipe_and_ffmpeg_and_leaves_no_draft(tmp_path):
    source = clip(tmp_path / "src" / "long.mp4", 250, "1280x720")
    flag, result = tmp_path / "stop.flag", tmp_path / "stop.json"
    env = {**os.environ, "AUDION_LOGS": str(tmp_path / "logs"), "AUDION_REPORT": str(tmp_path / "report")}
    process = subprocess.Popen([str(PYTHON), "-X", "utf8", str(ROOT / "system_core" / "cli.py"), "run", "--operation",
                                "shadow_denoise_sota", "--set", "vs_accel=cpu", "--source", str(source), "--target",
                                str(tmp_path / "out"), "--live", "--result", str(result), "--cancel-file", str(flag)],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    lines: list[str] = []
    reader = threading.Thread(target=lambda: lines.extend(raw.decode("utf-8", "replace") for raw in process.stdout), daemon=True)
    reader.start()
    began = time.monotonic()
    while process.poll() is None and time.monotonic() - began < 120:
        if any('"activity"' in line for line in lines):
            flag.write_text("stop")
            break
        time.sleep(0.2)
    code = process.wait(timeout=60)
    reader.join(timeout=5)
    assert code == 130, "".join(lines)[-3000:]
    assert json.loads(result.read_text(encoding="utf-8"))["outcome"] == "stopped"
    assert not [path for path in (tmp_path / "out").rglob("*") if path.is_file()]
    assert not any(line.startswith("[PROGRESS]") for line in lines)
