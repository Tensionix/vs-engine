"""subprocess pipeline: vspipe -c y4m preset.vpy - | ffmpeg ... output."""
from __future__ import annotations

import subprocess
import time
from threading import Thread
from pathlib import Path
from typing import Mapping
import json
import os
import re

from .env import merged_env
from .paths import PATHS
from .probe import probe as _probe


# Encoder profile registry: name -> ffmpeg output args (BEFORE output path).
# Sources are y4m on stdin -- pix_fmt must be a 10-bit-capable yuv420p variant for SDR pipelines.
ENCODERS: dict[str, list[str]] = {
    # x264 -- 3-tier quality ladder (Audion-consolidated 2026-04-28):
    # 14 = semi-lossless archive, 17 = Audion default (almost invisible),
    # 21 = web / proxy / preview. Tiers spaced for clearly distinct quality.
    "h264_crf14":   ["-c:v", "libx264", "-preset", "slow",   "-crf", "14",
                     "-pix_fmt", "yuv420p10le"],
    "h264_crf17":   ["-c:v", "libx264", "-preset", "medium", "-crf", "17",
                     "-pix_fmt", "yuv420p10le"],
    "h264_crf21":   ["-c:v", "libx264", "-preset", "medium", "-crf", "21",
                     "-pix_fmt", "yuv420p10le"],

    # x265 -- 10-bit pipeline, same ladder as x264 (14/17/21).
    "h265_crf14":   ["-c:v", "libx265", "-preset", "slow",   "-crf", "14",
                     "-pix_fmt", "yuv420p10le"],
    "h265_crf17":   ["-c:v", "libx265", "-preset", "medium", "-crf", "17",
                     "-pix_fmt", "yuv420p10le"],
    "h265_crf21":   ["-c:v", "libx265", "-preset", "medium", "-crf", "21",
                     "-pix_fmt", "yuv420p10le"],

    # ProRes 422 -- LT is the Audion default (smaller, transparent for color work,
    # no need for HQ unless keying). HQ kept available for those who do keying.
    # *_mxf variants use the MXF wrapper for Adobe Premiere / Avid round-trip.
    "prores_lt":      ["-c:v", "prores_ks", "-profile:v", "1",
                       "-pix_fmt", "yuv422p10le", "-qscale:v", "13"],
    "prores_lt_mxf":  ["-c:v", "prores_ks", "-profile:v", "1",
                       "-pix_fmt", "yuv422p10le", "-qscale:v", "13",
                       "-f", "mxf"],
    "prores_422":     ["-c:v", "prores_ks", "-profile:v", "2",
                       "-pix_fmt", "yuv422p10le", "-qscale:v", "11"],
    "prores_422_mxf": ["-c:v", "prores_ks", "-profile:v", "2",
                       "-pix_fmt", "yuv422p10le", "-qscale:v", "11",
                       "-f", "mxf"],
    "prores_422hq":   ["-c:v", "prores_ks", "-profile:v", "3",
                       "-pix_fmt", "yuv422p10le", "-qscale:v", "9"],
    "prores_422hq_mxf": ["-c:v", "prores_ks", "-profile:v", "3",
                         "-pix_fmt", "yuv422p10le", "-qscale:v", "9",
                         "-f", "mxf"],

    # DNxHR -- broadcast / Avid-style. LB = Low Bandwidth, SQ = Standard, HQ = High,
    # HQX = 10/12-bit High. Avid DNxHR ships in MXF; .mov works in Resolve / Premiere too.
    "dnxhr_lb":     ["-c:v", "dnxhd", "-profile:v", "dnxhr_lb",
                     "-pix_fmt", "yuv422p"],
    "dnxhr_sq":     ["-c:v", "dnxhd", "-profile:v", "dnxhr_sq",
                     "-pix_fmt", "yuv422p"],
    "dnxhr_hq":     ["-c:v", "dnxhd", "-profile:v", "dnxhr_hq",
                     "-pix_fmt", "yuv422p"],
    "dnxhr_hqx":    ["-c:v", "dnxhd", "-profile:v", "dnxhr_hqx",
                     "-pix_fmt", "yuv422p10le"],

    # ===== NVENC -- NVIDIA hardware encode (Phase 18.B-cleanup, 2026-04-28) =====
    # Removes the libx264/libx265 CPU bottleneck. Quality is set via -cq (constant
    # quality, equivalent to CRF). Preset p7 = "Slowest" (best quality).
    # Tune "hq" = high quality (default); switch to "ll" for low-latency streaming.
    # Pascal+ for h264_nvenc (8-bit only on most cards), Pascal+ for hevc_nvenc 10-bit.
    # Verify availability via: ffmpeg -hide_banner -encoders | findstr nvenc
    #
    # h264_nvenc: same 14/17/21 ladder as software CRF.
    # 8-bit yuv420p (10-bit on Ada/Blackwell only via -pix_fmt yuv420p10le).
    "h264_nvenc_q14": ["-c:v", "h264_nvenc", "-preset", "p7", "-tune", "hq",
                       "-rc", "vbr", "-cq", "14", "-b:v", "0",
                       "-pix_fmt", "yuv420p"],
    "h264_nvenc_q17": ["-c:v", "h264_nvenc", "-preset", "p7", "-tune", "hq",
                       "-rc", "vbr", "-cq", "17", "-b:v", "0",
                       "-pix_fmt", "yuv420p"],
    "h264_nvenc_q21": ["-c:v", "h264_nvenc", "-preset", "p7", "-tune", "hq",
                       "-rc", "vbr", "-cq", "21", "-b:v", "0",
                       "-pix_fmt", "yuv420p"],

    # hevc_nvenc: 10-bit p010le (Pascal+).
    "h265_nvenc_q14": ["-c:v", "hevc_nvenc", "-preset", "p7", "-tune", "hq",
                      "-rc", "vbr", "-cq", "14", "-b:v", "0",
                      "-pix_fmt", "p010le"],
    "h265_nvenc_q17": ["-c:v", "hevc_nvenc", "-preset", "p7", "-tune", "hq",
                      "-rc", "vbr", "-cq", "17", "-b:v", "0",
                      "-pix_fmt", "p010le"],
    "h265_nvenc_q21": ["-c:v", "hevc_nvenc", "-preset", "p7", "-tune", "hq",
                      "-rc", "vbr", "-cq", "21", "-b:v", "0",
                      "-pix_fmt", "p010le"],

    # QuickSync -- Intel hardware encode. Same GUI quality ladder, using
    # global_quality as the QSV constant-quality control.
    "h264_qsv_q14": ["-c:v", "h264_qsv", "-preset", "slow", "-global_quality", "14",
                     "-pix_fmt", "nv12"],
    "h264_qsv_q17": ["-c:v", "h264_qsv", "-preset", "medium", "-global_quality", "17",
                     "-pix_fmt", "nv12"],
    "h264_qsv_q21": ["-c:v", "h264_qsv", "-preset", "medium", "-global_quality", "21",
                     "-pix_fmt", "nv12"],
    "h265_qsv_q14": ["-c:v", "hevc_qsv", "-preset", "slow", "-global_quality", "14",
                     "-pix_fmt", "p010le"],
    "h265_qsv_q17": ["-c:v", "hevc_qsv", "-preset", "medium", "-global_quality", "17",
                     "-pix_fmt", "p010le"],
    "h265_qsv_q21": ["-c:v", "hevc_qsv", "-preset", "medium", "-global_quality", "21",
                     "-pix_fmt", "p010le"],

    # AMF hardware encode. CQP maps the same 14/17/21 quality ladder
    # onto I/P/B quantizers.
    "h264_amf_q14": ["-c:v", "h264_amf", "-quality", "quality", "-rc", "cqp",
                     "-qp_i", "14", "-qp_p", "14", "-qp_b", "14",
                     "-pix_fmt", "yuv420p"],
    "h264_amf_q17": ["-c:v", "h264_amf", "-quality", "quality", "-rc", "cqp",
                     "-qp_i", "17", "-qp_p", "17", "-qp_b", "17",
                     "-pix_fmt", "yuv420p"],
    "h264_amf_q21": ["-c:v", "h264_amf", "-quality", "quality", "-rc", "cqp",
                     "-qp_i", "21", "-qp_p", "21", "-qp_b", "21",
                     "-pix_fmt", "yuv420p"],
    "h265_amf_q14": ["-c:v", "hevc_amf", "-quality", "quality", "-rc", "cqp",
                     "-qp_i", "14", "-qp_p", "14", "-qp_b", "14",
                     "-pix_fmt", "p010le"],
    "h265_amf_q17": ["-c:v", "hevc_amf", "-quality", "quality", "-rc", "cqp",
                     "-qp_i", "17", "-qp_p", "17", "-qp_b", "17",
                     "-pix_fmt", "p010le"],
    "h265_amf_q21": ["-c:v", "hevc_amf", "-quality", "quality", "-rc", "cqp",
                     "-qp_i", "21", "-qp_p", "21", "-qp_b", "21",
                     "-pix_fmt", "p010le"],
}

DEFAULT_ENCODER = "h264_crf14"


class PipelineError(RuntimeError):
    pass


def _read_pipe(pipe, chunks: list[bytes]) -> None:
    if pipe is None:
        return
    data = pipe.read()
    if data:
        chunks.append(data)


_MP4_AUDIO_COPY_CODECS = {"aac", "mp3", "alac", "ac3", "eac3"}
_LOSSY_H26_ENCODERS = ("h264_", "h265_")


def _source_media_codecs(input_path: Path) -> dict[str, str]:
    cmd = [
        str(PATHS.ffprobe),
        "-v", "error",
        "-show_entries", "stream=codec_type,codec_name:format=format_name",
        "-of", "json",
        str(input_path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
        if proc.returncode != 0:
            return {"video": "", "audio": "", "format": ""}
        data = json.loads(proc.stdout or "{}")
    except Exception:
        return {"video": "", "audio": "", "format": ""}
    result = {"video": "", "audio": "", "format": ""}
    fmt = data.get("format", {}) if isinstance(data, dict) else {}
    if isinstance(fmt, dict):
        result["format"] = str(fmt.get("format_name") or "").lower()
    streams = data.get("streams", []) if isinstance(data, dict) else []
    for stream in streams:
        if not isinstance(stream, dict):
            continue
        codec_type = str(stream.get("codec_type") or "").lower()
        if codec_type in {"video", "audio"} and not result[codec_type]:
            result[codec_type] = str(stream.get("codec_name") or "").lower()
    return result


def _target_container(output_path: Path, encoder: str) -> str:
    encoder_args = ENCODERS.get(encoder, [])
    for i, token in enumerate(encoder_args[:-1]):
        if token == "-f":
            return str(encoder_args[i + 1]).lower()
    suffix = output_path.suffix.lower().lstrip(".")
    if suffix == "m4v":
        return "mp4"
    if suffix:
        return suffix
    if encoder.endswith("_mxf"):
        return "mxf"
    if encoder.startswith(("prores", "dnxhr")):
        return "mov"
    return "mp4"


def _audio_output_args(input_path: Path, output_path: Path, encoder: str, audio_passthrough: bool) -> tuple[list[str], str]:
    if not audio_passthrough:
        return [], "none"
    media = _source_media_codecs(input_path)
    audio_codec = media["audio"]
    target_container = _target_container(output_path, encoder)
    if not audio_codec:
        return ["-c:a", "copy"], "copy_no_audio_or_unknown"
    # MXF of FFmpeg takes PCM at 48 kHz alone ("only 48khz is implemented"): AAC or 44.1 kHz copied in stopped the run
    # before its first frame. PCM 24 bit at 48 kHz is what Premiere and Avid read; a PCM source goes over unchanged.
    if target_container == "mxf":
        return ["-c:a", "pcm_s24le", "-ar", "48000"], f"pcm_s24le_48k_for_mxf_from_{audio_codec}"
    if target_container == "mp4" and audio_codec not in _MP4_AUDIO_COPY_CODECS:
        return ["-c:a", "aac", "-b:a", "384k"], f"aac_384k_for_mp4_from_{audio_codec}"
    if (
        media["video"] == "prores"
        and encoder.startswith(_LOSSY_H26_ENCODERS)
        and audio_codec not in _MP4_AUDIO_COPY_CODECS
    ):
        return ["-c:a", "aac", "-b:a", "384k"], f"aac_384k_from_prores_{audio_codec}_to_lossy"
    return ["-c:a", "copy"], f"copy_{audio_codec}_to_{target_container}"


class PipelineCancelled(RuntimeError):
    """The caller asked to stop: vspipe and ffmpeg were ended, what they wrote is the caller's to take away."""


# vspipe -p: "Frame: 123/2940 (9.81 fps)" - written to stderr with a carriage return between updates.
_VSPIPE_FRAME = re.compile(r"Frame:\s*(\d+)/(\d+)(?:\s*\(([\d.]+)\s*fps\))?")


def _end_tree(proc: subprocess.Popen) -> None:
    """End a process with everything it started (taskkill /T /F), then reap it."""
    if proc.poll() is not None:
        return
    try:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=10,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    try:
        proc.wait(timeout=5)
    except Exception:
        pass


def _read_progress(pipe, chunks: list[bytes], progress) -> None:
    """vspipe's stderr as it comes: the frame counter goes to `progress`, every byte is kept for the report."""
    if pipe is None:
        return
    pending = b""
    while True:
        data = pipe.read1(65536) if hasattr(pipe, "read1") else pipe.read(4096)
        if not data:
            break
        chunks.append(data)
        pending += data
        *pieces, pending = re.split(rb"[\r\n]", pending)
        for piece in pieces:
            found = _VSPIPE_FRAME.search(piece.decode("utf-8", errors="replace"))
            if found and progress is not None:
                progress(int(found[1]), int(found[2]), float(found[3]) if found[3] else 0.0)


def _source_range(input_path: Path) -> str:
    """"pc" for a full-range source, else "tv": the presets keep the range of their source (audion_lib.source_range,
    the _Range L-SMASH reads - full for color_range=pc and for the yuvj formats), and y4m does not carry it to FFmpeg,
    so it is handed over here. Unknown is limited, as L-SMASH takes it."""
    try:
        video = next(s for s in _probe(input_path).get("streams", []) if s.get("codec_type") == "video")
    except Exception:  # noqa: BLE001 - an unreadable probe leaves the default, as an unknown range does
        return "tv"
    full = video.get("color_range") in ("pc", "jpeg") or str(video.get("pix_fmt", "")).startswith("yuvj")
    return "pc" if full else "tv"


def run_pipeline(
    *,
    preset_path: Path,
    input_path: Path,
    output_path: Path,
    env_extras: Mapping[str, str],
    encoder: str = DEFAULT_ENCODER,
    audio_passthrough: bool = True,
    log_callback=None,
    progress=None,
    cancelled=None,
    dry_run: bool = False,
) -> dict:
    """Run vspipe -> ffmpeg pipe.

    Returns a report dict:
      {ok, vspipe_rc, ffmpeg_rc, encoder, elapsed_s, output_size, vspipe_stderr_tail}

    progress(frame, frames, fps) - vspipe's own counter (-p), as it comes; cancelled() - asked every 0.2 s, True ends
    vspipe and ffmpeg and raises PipelineCancelled; dry_run - the two commands and the environment come back in the
    report under "commands", nothing is started.

    Raises FileNotFoundError if preset/input missing,
    PipelineError if either subprocess fails non-zero.
    """
    if not preset_path.exists():
        raise FileNotFoundError(f"preset not found: {preset_path}")
    if not input_path.exists():
        raise FileNotFoundError(f"input not found: {input_path}")
    if encoder not in ENCODERS:
        raise PipelineError(f"unknown encoder: {encoder}. Available: {sorted(ENCODERS)}")

    env = merged_env(env_extras)
    presets_path = str(PATHS.presets_dir)
    env["PYTHONPATH"] = presets_path + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

    vspipe_argv = [
        str(PATHS.vspipe),
        "-c", "y4m",
        # -p: vspipe's own frame counter on stderr, the progress of a run (until 3.0.0 the window counted it from the
        # clock: 95 % after 28 minutes, whatever the frames).
        "-p",
        str(preset_path),
        "-",
    ]
    # The range on both sides: on the input alone the encoder would not mark it, on the output alone FFmpeg's own
    # conversion (4:4:4 -> 4:2:0, 12 -> 10 bit) would take the untagged input for limited and stretch or squeeze the
    # levels to the range asked for.
    color_range = _source_range(input_path)
    ffmpeg_argv = [
        str(PATHS.ffmpeg),
        "-hide_banner", "-loglevel", "warning", "-y",
        "-color_range", color_range,
        "-i", "-",
    ]
    # Audio passthrough: if input has audio, mux it from input file (-i input + -map for video from pipe + audio from input)
    audio_policy = "none"
    if audio_passthrough:
        audio_args, audio_policy = _audio_output_args(input_path, output_path, encoder, audio_passthrough)
        ffmpeg_argv += ["-i", str(input_path), "-map", "0:v:0", "-map", "1:a:0?", *audio_args]
    ffmpeg_argv += ENCODERS[encoder]
    ffmpeg_argv += ["-color_range", color_range, str(output_path)]

    if log_callback:
        log_callback(f"vspipe: {' '.join(vspipe_argv)}")
        log_callback(f"ffmpeg: {' '.join(ffmpeg_argv)}")
    if dry_run:
        return {"ok": True, "dry_run": True, "encoder": encoder, "audio_policy": audio_policy, "color_range": color_range,
                "commands": {"vspipe": vspipe_argv, "ffmpeg": ffmpeg_argv,
                             "env": {k: v for k, v in env_extras.items() if k.startswith("AUDION_VS_")}}}

    # The folder only for a run that writes: a dry run leaves the Target as it was.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()

    # Start vspipe with stdout=PIPE; ffmpeg consumes it as stdin.
    vspipe_proc = subprocess.Popen(
        vspipe_argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        bufsize=0,
    )
    ffmpeg_proc = subprocess.Popen(
        ffmpeg_argv,
        stdin=vspipe_proc.stdout,
        stderr=subprocess.PIPE,
        env=env,
    )
    # Allow vspipe to receive SIGPIPE if ffmpeg dies first
    if vspipe_proc.stdout is not None:
        vspipe_proc.stdout.close()

    vs_stderr_chunks: list[bytes] = []
    ff_stderr_chunks: list[bytes] = []
    vs_stderr_thread = Thread(target=_read_progress, args=(vspipe_proc.stderr, vs_stderr_chunks, progress), daemon=True)
    ff_stderr_thread = Thread(target=_read_pipe, args=(ffmpeg_proc.stderr, ff_stderr_chunks), daemon=True)
    vs_stderr_thread.start()
    ff_stderr_thread.start()

    # Both stderr streams are read by their threads while this one watches for a stop.
    stopped = False
    while ffmpeg_proc.poll() is None:
        if cancelled is not None and cancelled():
            stopped = True
            _end_tree(vspipe_proc)
            _end_tree(ffmpeg_proc)
            break
        time.sleep(0.2)
    ffmpeg_rc = ffmpeg_proc.wait()
    vspipe_rc = vspipe_proc.wait()
    if stopped:
        ff_stderr_thread.join(timeout=5)
        vs_stderr_thread.join(timeout=5)
        raise PipelineCancelled("stopped by the caller")
    ff_stderr_thread.join(timeout=5)
    vs_stderr_thread.join(timeout=5)

    elapsed = time.perf_counter() - t0
    output_size = output_path.stat().st_size if output_path.exists() else 0

    ff_stderr_b = b"".join(ff_stderr_chunks)
    vs_stderr_b = b"".join(vs_stderr_chunks)
    vs_err = vs_stderr_b.decode("utf-8", errors="replace")
    ff_err = ff_stderr_b.decode("utf-8", errors="replace")

    report = {
        "ok": (vspipe_rc == 0 and ffmpeg_rc == 0 and output_size > 0),
        "vspipe_rc": vspipe_rc,
        "ffmpeg_rc": ffmpeg_rc,
        "encoder": encoder,
        "audio_policy": audio_policy,
        "color_range": color_range,
        "elapsed_s": round(elapsed, 3),
        "output_path": str(output_path),
        "output_size": output_size,
        "vspipe_stderr_tail": vs_err[-2000:].strip(),
        "ffmpeg_stderr_tail": ff_err[-2000:].strip(),
    }
    # The denoise presets say what noise they measured and what they made of it (audion_lib.report_noise). The frame
    # counter fills the stderr tail, so the lines are kept on their own.
    noise = [line.strip() for line in vs_err.replace("\r", "\n").splitlines() if line.startswith("[NOISE]")]
    if noise:
        report["noise"] = noise
        if log_callback:
            for line in noise:
                log_callback(line)

    if not report["ok"]:
        msg_parts = [f"pipeline failed: vspipe_rc={vspipe_rc} ffmpeg_rc={ffmpeg_rc}"]
        if vs_err.strip():
            msg_parts.append(f"vspipe stderr:\n{vs_err.strip()}")
        if ff_err.strip():
            msg_parts.append(f"ffmpeg stderr (tail):\n{ff_err.strip()[-1500:]}")
        raise PipelineError("\n\n".join(msg_parts))

    return report


def list_encoders() -> list[str]:
    return sorted(ENCODERS)
