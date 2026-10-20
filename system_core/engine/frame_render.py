"""One frame of a preset and of its source as PNG: the pictures of the card FRAME of the window (vs_cli.cmd frame).

Run by the Python of VapourSynth with the environment of a run - the AUDION_VS_* of the preset and PYTHONPATH on the
presets, as engine\\runner.py gives vspipe:

    system_core\\vapoursynth\\python.exe frame_render.py <preset.vpy> <at> <out folder> <both|before|after> <max width>

The preset is evaluated as vspipe evaluates it, and its output 0 is the picture "after"; "before" is the source as the
presets load it (audion_lib.load_source). Both are read at the same moment of the clip - `at`, a share of its length
from 0 to 1 - so a preset that changes the number of frames (TIVTC) is read at the same place. Each frame goes to RGB
8-bit by the matrix and the range of its own frame, wider than `max width` - scaled down, and is written as PNG by this
script itself (zlib of the standard library: no plugin of VapourSynth writes images in the set of the program).

One line of JSON at the end: {"before": {...}, "after": {...}, "seconds": N}; a side - path, frame, frames, width,
height (as the clip has them) and fps. A failure - {"error": "..."} and the code 1.
"""
from __future__ import annotations

import json
import os
import runpy
import struct
import sys
import time
import zlib

import vapoursynth as vs

core = vs.core


def png(path: str, width: int, height: int, planes: list[bytes]) -> None:
    """RGB 8-bit planes as a PNG: the bytes interleaved by slices, a filter byte 0 before every row."""
    raw = bytearray(width * height * 3)
    raw[0::3], raw[1::3], raw[2::3] = planes
    stride = width * 3
    view = memoryview(raw)
    rows = b"".join(b"\x00" + view[y * stride:(y + 1) * stride].tobytes() for y in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    with open(path, "wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\n")
        handle.write(chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)))
        handle.write(chunk(b"IDAT", zlib.compress(rows, 3)))
        handle.write(chunk(b"IEND", b""))


def frame_at(clip: vs.VideoNode, at: float) -> int:
    return min(clip.num_frames - 1, max(0, round(at * (clip.num_frames - 1))))


def picture(clip: vs.VideoNode, number: int, path: str, max_width: int) -> dict:
    one = clip[number]
    first = one.get_frame(0)
    family = one.format.color_family
    width, height = one.width, one.height
    shown_w, shown_h = width, height
    if max_width and width > max_width:
        shown_w = max_width & ~1
        shown_h = max(2, round(height * shown_w / width)) & ~1
    if family == vs.GRAY:
        gray = core.resize.Bicubic(one, shown_w, shown_h, format=vs.GRAY8)
        rgb = core.std.ShufflePlanes([gray, gray, gray], [0, 0, 0], vs.RGB)
    elif family == vs.RGB:
        rgb = core.resize.Bicubic(one, shown_w, shown_h, format=vs.RGB24, dither_type="error_diffusion")
    else:
        # The matrix of the frame; an untagged one by its size, as players take it: HD and up BT.709, SD BT.601.
        matrix = int(first.props.get("_Matrix", 2))
        if matrix in (0, 2, 3):
            matrix = 1 if height >= 720 else 6
        rgb = core.resize.Bicubic(one, shown_w, shown_h, format=vs.RGB24, matrix_in=matrix, dither_type="error_diffusion")
    frame = rgb.get_frame(0)
    png(path, shown_w, shown_h, [memoryview(frame[plane]).tobytes() for plane in range(3)])
    fps = float(clip.fps) if clip.fps.denominator else 0.0
    return {"path": path, "frame": number, "frames": clip.num_frames, "width": width, "height": height,
            "fps": round(fps, 3)}


def main() -> int:
    script, at, out, sides, max_width = sys.argv[1], float(sys.argv[2]), sys.argv[3], sys.argv[4], int(sys.argv[5])
    began = time.monotonic()
    os.makedirs(out, exist_ok=True)
    told: dict = {}
    if sides in ("both", "after"):
        vs.clear_outputs()
        runpy.run_path(script, run_name="__vapoursynth__")
        output = vs.get_output(0)
        clip = output.clip if hasattr(output, "clip") else output
        told["after"] = picture(clip, frame_at(clip, at), os.path.join(out, "after.png"), max_width)
    if sides in ("both", "before"):
        import audion_lib as al

        source = al.load_source(os.environ["AUDION_VS_INPUT"])
        told["before"] = picture(source, frame_at(source, at), os.path.join(out, "before.png"), max_width)
    told["seconds"] = round(time.monotonic() - began, 2)
    print(json.dumps(told, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:  # noqa: BLE001 - the reason goes back to the console command whole
        print(json.dumps({"error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
        sys.exit(1)
