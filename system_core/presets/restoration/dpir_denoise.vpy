# Audion VS Engine -- Restoration palette
# Preset: dpir_denoise (Phase 18.B-ML)
# Stack:  vsmlrt.DPIR (TensorRT -> DirectML -> CPU) -> ML-denoise
# Goal:   Heavy-noise / high-ISO ML denoise. DPIR is a deep network trained
#         on a wide variety of noise types and PRESERVES skin texture and
#         fabric detail in a way that BM3D / DFTTest cannot match on really
#         dirty source. Use this when BM3D is "smearing" the picture.
#
#         What this gives you that Adobe / DaVinci do NOT:
#         - ML-denoise that survives high-ISO (12800+) without losing texture
#         - separate models for color and grayscale
#         - configurable strength via sigma (model is conditioned on noise
#           level estimate -- you tell it how bad the noise is)
#
# Required:
#   AUDION_VS_INPUT     absolute path to source media
# Optional:
#   AUDION_VS_STRENGTH  float 1..50 -- DPIR sigma (noise level estimate the
#                       model is conditioned on). Higher = stronger denoise.
#                         5   -- light shot noise (low ISO digital)
#                         10  -- medium (default; ISO 1600-3200 modern sensors)
#                         15  -- heavy (ISO 6400+)
#                         25  -- very heavy (ISO 12800, low-light phone)
#                         50  -- extreme (broken sensor / heavy compression)
#                       default 10
#   AUDION_VS_MODEL     "drunet_color"  -- color version (default)
#                       "drunet_gray"   -- grayscale (B&W footage)
#                       "drunet_deblocking_color" -- specifically for
#                                                    JPEG / MPEG block artifacts
#   AUDION_VS_TILE      int 256 / 384 / 512 -- input tile size.  default 384
#   AUDION_VS_BACKEND   "trt" | "ort_dml" | "ort_cpu" | "auto"  default auto
#
import os
import vapoursynth as vs
core = vs.core

import vsmlrt
import audion_lib as al

INPUT    = os.environ["AUDION_VS_INPUT"]
STRENGTH = float(os.environ.get("AUDION_VS_STRENGTH", "10"))
MODEL    = os.environ.get("AUDION_VS_MODEL", "drunet_color").lower()
TILE     = int(os.environ.get("AUDION_VS_TILE", "384"))
BACKEND  = os.environ.get("AUDION_VS_BACKEND", "auto").lower()

# Clamp sigma to a sane range
STRENGTH = max(1.0, min(50.0, STRENGTH))


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


def _fit_tile(clip: vs.VideoNode, requested: int, align: int = 16) -> int:
    limit = max(align, min(clip.width, clip.height))
    tile = min(max(align, requested), limit)
    return max(align, (tile // align) * align)


_DPIR_MAP = {
    "drunet_color":             getattr(vsmlrt.DPIRModel, "drunet_color", None),
    "drunet_gray":              getattr(vsmlrt.DPIRModel, "drunet_gray", None),
    "drunet_deblocking_color":  getattr(vsmlrt.DPIRModel, "drunet_deblocking_color", None),
    "drunet_deblocking_gray":   getattr(vsmlrt.DPIRModel, "drunet_deblocking_gray", None),
}
if MODEL not in _DPIR_MAP or _DPIR_MAP[MODEL] is None:
    raise ValueError(
        f"Unknown or unavailable AUDION_VS_MODEL={MODEL!r}. "
        f"Try: drunet_color | drunet_gray | drunet_deblocking_color | drunet_deblocking_gray"
    )
model_enum = _DPIR_MAP[MODEL]

if BACKEND == "auto":
    backend, picked = _auto_backend()
else:
    backend = _resolve_backend(BACKEND)
    picked = BACKEND

src = _load(INPUT)
src = core.std.SetFrameProps(src, _Matrix=1, _Transfer=1, _Primaries=1, _Range=1)

# DPIR color models work in RGB float; gray works in GRAY float
is_gray = "gray" in MODEL
target_fmt = vs.GRAYS if is_gray else vs.RGBS

if is_gray:
    work = core.resize.Bicubic(core.std.ShufflePlanes(src, 0, vs.GRAY), format=vs.GRAYS)
else:
    work = core.resize.Bicubic(src, format=vs.RGBS, matrix_in_s="709")

tile = _fit_tile(work, TILE)
denoised = vsmlrt.DPIR(
    work,
    strength=STRENGTH,
    model=model_enum,
    backend=backend,
    tilesize=tile,
    overlap=16,
)

# Back to YUV420P10
if is_gray:
    # If input was gray, recombine with original chroma so output is still YUV
    yuv_src = core.resize.Bicubic(src, format=vs.YUV420P10, matrix_s="709")
    out = core.std.ShufflePlanes(
        [core.resize.Bicubic(denoised, format=vs.GRAY16, range_in=1, range=1), yuv_src, yuv_src],
        [0, 1, 2], vs.YUV
    )
else:
    out = core.resize.Bicubic(denoised, format=vs.YUV420P10, matrix_s="709")

out = core.std.SetFrameProps(out, _Matrix=1, _Transfer=1, _Primaries=1, _Range=1)
out.set_output()
