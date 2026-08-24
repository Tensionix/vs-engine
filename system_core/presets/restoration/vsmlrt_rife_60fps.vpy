# Audion VS Engine -- Restoration palette
# Preset: vsmlrt_rife_60fps (Phase 18.B-ML)
# Stack:  vsmlrt.RIFE (TensorRT -> DirectML -> CPU) -> 2x or 2.5x fps
# Goal:   ML-based frame interpolation. Produces visibly smoother motion than
#         optical-flow methods because RIFE understands content (not just
#         pixel motion) -- handles occlusion, transparent objects, fades.
#
#         What this gives you that Adobe / DaVinci do NOT:
#         - true ML interpolation (Resolve "Optical Flow" is per-pixel motion,
#           breaks on fast/complex motion; RIFE handles it)
#         - RIFE 4.x family: very fast, modern, well-tested
#         - configurable target FPS multiplier (2x, 2.5x for 24->60, 4x for
#           cinematic slow-mo from 24)
#         - reproducible from CLI, batch-friendly
#
# Required:
#   AUDION_VS_INPUT     absolute path to source media
# Optional:
#   AUDION_VS_FPS_MUL   float -- target FPS multiplier:
#                         "2"   -> 24 -> 48 fps  (smooth playback)
#                         "2.5" -> 24 -> 60 fps  (60 Hz monitor target;
#                                                 default for "60 fps mode")
#                         "3"   -> 24 -> 72 fps
#                         "4"   -> 24 -> 96 fps  (slow-mo source)
#                       default 2.5
#   AUDION_VS_MODEL     RIFE model variant:
#                         "rife_v4.6"  default; modern, balanced
#                         "rife_v4.4"  older but proven
#                         "rife_v4.9"  newest in vs-mlrt
#   AUDION_VS_BACKEND   "trt" | "ort_dml" | "ort_cpu" | "auto"  default auto
#
# Note: RIFE produces 2x output frames per input frame at multiplier=2; for
#   non-integer multipliers the output is interpolated to the target rate
#   using vsmlrt's built-in fractional-rate handling.
#
import os
from fractions import Fraction
import vapoursynth as vs
core = vs.core

import vsmlrt
import audion_lib as al

INPUT    = os.environ["AUDION_VS_INPUT"]
FPS_MUL  = float(os.environ.get("AUDION_VS_FPS_MUL", "2.5"))
MODEL    = os.environ.get("AUDION_VS_MODEL", "rife_v4.6").lower()
BACKEND  = os.environ.get("AUDION_VS_BACKEND", "auto").lower()


def _load(path: str):
    try:
        return core.lsmas.LWLibavSource(path)
    except (vs.Error, AttributeError):
        return core.ffms2.Source(path)


def _resolve_backend(tag: str):
    if tag == "trt":
        return vsmlrt.Backend.TRT(fp16=True, num_streams=1, force_regenerate_engine=False)
    if tag == "ort_dml":
        return vsmlrt.Backend.ORT_DML(fp16=True)
    if tag == "ort_cpu":
        return vsmlrt.Backend.ORT_CPU()
    raise ValueError(f"unknown backend tag: {tag}")


def _auto_backend():
    """Try the hardware-appropriate backend chain. See vsmlrt_realesrgan_2x
    for why we skip TRT on non-NVIDIA boxes."""
    for tag in al.vsmlrt_backend_chain():
        try:
            return _resolve_backend(tag), tag
        except Exception:
            continue
    raise RuntimeError("No vsmlrt backend available -- check Install-VS-mlrt.cmd")


# Pick RIFE model enum
_RIFE_MAP = {
    "rife_v4.4": getattr(vsmlrt.RIFEModel, "v4_4", None),
    "rife_v4.6": getattr(vsmlrt.RIFEModel, "v4_6", None),
    "rife_v4.9": getattr(vsmlrt.RIFEModel, "v4_9", None),
}
if MODEL not in _RIFE_MAP or _RIFE_MAP[MODEL] is None:
    raise ValueError(
        f"Unknown or unavailable AUDION_VS_MODEL={MODEL!r}. "
        f"Try: rife_v4.4 | rife_v4.6 | rife_v4.9"
    )
model_enum = _RIFE_MAP[MODEL]

if BACKEND == "auto":
    backend, picked = _auto_backend()
else:
    backend = _resolve_backend(BACKEND)
    picked = BACKEND

src = _load(INPUT)
src = core.std.SetFrameProps(src, _Matrix=1, _Transfer=1, _Primaries=1, _Range=1)

# RIFE expects RGB float
rgb = core.resize.Bicubic(src, format=vs.RGBS, matrix_in_s="709")

# RIFE network demands BOTH dimensions be multiples of 32 (the model's
# downsample-then-upsample stack uses 5 levels of stride-2). 4K (3840x2160)
# is a common source where 2160 % 32 = 16. Pad to the next mod-32 frame,
# run RIFE, then crop the padding away. We pad on the bottom/right so that
# integer luma alignment with chroma planes is preserved (ALL planes pad
# the same amount, so 4:2:0 stays valid).
ALIGN = 32
pad_w = (ALIGN - rgb.width  % ALIGN) % ALIGN
pad_h = (ALIGN - rgb.height % ALIGN) % ALIGN
if pad_w or pad_h:
    rgb_pad = core.std.AddBorders(rgb, right=pad_w, bottom=pad_h)
else:
    rgb_pad = rgb

# vsmlrt.RIFE requires `multi` to be an int OR fractions.Fraction.
# Floats throw TypeError as of vsmlrt 3.22. Convert: integer multipliers
# stay int, fractional ones become Fraction(numerator, denominator) by
# limit_denominator(100) to keep the ratio sane (2.5 -> 5/2 etc.).
if FPS_MUL == int(FPS_MUL):
    multi = int(FPS_MUL)
else:
    multi = Fraction(FPS_MUL).limit_denominator(100)

interpolated = vsmlrt.RIFE(
    rgb_pad,
    multi=multi,
    model=model_enum,
    backend=backend,
)

# Strip the padding back off so the interpolated clip matches source
# resolution byte-for-byte.
if pad_w or pad_h:
    interpolated = core.std.Crop(interpolated, right=pad_w, bottom=pad_h)

# Convert back to YUV420P10 for standard encoders
out = core.resize.Bicubic(interpolated, format=vs.YUV420P10, matrix_s="709")
out = core.std.SetFrameProps(out, _Matrix=1, _Transfer=1, _Primaries=1, _Range=1)
out.set_output()
