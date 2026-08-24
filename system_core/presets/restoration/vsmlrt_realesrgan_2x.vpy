# Audion VS Engine -- Restoration palette
# Preset: vsmlrt_realesrgan_2x (Phase 18.B-ML)
# Stack:  vsmlrt.RealESRGAN (TensorRT -> DirectML -> CPU) -> 2x upscale
# Goal:   ML-upscale 1080p source to ~3840x2160 (slightly over 4K) using
#         Real-ESRGAN -- the de-facto reference for video super-resolution.
#         Produces sharper, more textured output than Lanczos / Spline36 /
#         Resolve SuperScale, especially on faces and fine fabric texture.
#
#         What this gives you that Adobe / DaVinci do NOT:
#         - true ML upscale (NLE "AI scale" plugins are usually paid add-ons)
#         - choice of model variant: animevideov3 (clean cartoon/2D content)
#           vs general-x4v3 (live action / mixed content)
#         - TensorRT path on NVIDIA = 2-3x faster than DirectML / CPU EP
#         - reproducible from CLI, batch-friendly
#
# Required:
#   AUDION_VS_INPUT       absolute path to source media (must be RGB or YUV)
# Optional:
#   AUDION_VS_MODEL       which Real-ESRGAN model variant to use:
#                           "animevideov3"      -- 4-channel anime/2D model
#                                                  (sharp on cartoons, can
#                                                  over-sharpen real video)
#                           "general-x4v3"      -- general purpose, mild,
#                                                  best for live-action
#                                                  default
#                           "general-wdn-x4v3"  -- general with extra
#                                                  noise denoise
#                           "animejanaiV2-L1"   -- newer anime, lighter
#                           "animejanaiV2-L2"   -- newer anime, balanced
#                           "animejanaiV2-L3"   -- newer anime, heaviest
#   AUDION_VS_TILE        int 256 / 384 / 512 / 768 -- input tile size
#                         (smaller = less VRAM but slower).   default 384
#   AUDION_VS_TILE_PAD    int -- tile padding to hide seams.  default 16
#   AUDION_VS_BACKEND     "trt" (NVIDIA TensorRT, fastest) | "ort_dml"
#                         (DirectML; any DX12 GPU including Intel/AMF/NVIDIA) |
#                         "ort_cpu" (CPU fallback).         default auto
#                         (try trt -> ort_dml -> ort_cpu)
#
# Note on first-run TensorRT compile:
#   TensorRT compiles a model engine for the specific (model, GPU, resolution,
#   dtype) tuple the first time it runs that combination. This takes 30-120s
#   and is cached on disk. Subsequent runs of the same combination are
#   immediate. If you change tile size you trigger a recompile.
#
import os
import vapoursynth as vs
core = vs.core

import vsmlrt
import audion_lib as al

INPUT     = os.environ["AUDION_VS_INPUT"]
MODEL     = os.environ.get("AUDION_VS_MODEL", "general-x4v3")
TILE      = int(os.environ.get("AUDION_VS_TILE", "384"))
TILE_PAD  = int(os.environ.get("AUDION_VS_TILE_PAD", "16"))
BACKEND   = os.environ.get("AUDION_VS_BACKEND", "auto").lower()


def _load(path: str):
    try:
        return core.lsmas.LWLibavSource(path)
    except (vs.Error, AttributeError):
        return core.ffms2.Source(path)


# Map our short backend tag to a vsmlrt.Backend instance with sane defaults.
def _resolve_backend(tag: str):
    if tag == "trt":
        return vsmlrt.Backend.TRT(fp16=True, num_streams=1, force_regenerate_engine=False)
    if tag == "ort_dml":
        return vsmlrt.Backend.ORT_DML(fp16=True)
    if tag == "ort_cpu":
        return vsmlrt.Backend.ORT_CPU()
    raise ValueError(f"unknown backend tag: {tag}")


def _auto_backend():
    """Try the hardware-appropriate backend chain in order; return the first
    that initializes. The chain comes from `al.vsmlrt_backend_chain()` and
    skips TRT entirely on non-NVIDIA hardware -- otherwise vsmlrt would
    spend 30-120 s building a TensorRT engine that cannot run, then bail
    to ORT_DML, costing real wall time on every Intel/AMF invocation.
    """
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


# Map model name to vsmlrt model enum constant.
#
# vsmlrt exposes RealESRGANv2Model.<name>. The enum surface drifts between
# vsmlrt releases: v3.22 (shipped with vs-mlrt v15.16) DROPPED the
# SRVGGNet-general models (`general_x4v3`, `general_wdn_x4v3`) because they
# were retired upstream. We use getattr() everywhere so a missing entry
# becomes None, then map old "general-*" tokens to `animevideov3` -- the
# practical replacement that handles live-action and mixed content.
_M = vsmlrt.RealESRGANv2Model
_MODEL_MAP = {
    # Stable / current entries
    "animevideov3":      getattr(_M, "animevideov3", None),
    "animevideo-xsx2":   getattr(_M, "animevideo_xsx2", None),
    "animevideo-xsx4":   getattr(_M, "animevideo_xsx4", None),
    # Legacy SRVGGNet aliases -> closest live model
    "general-x4v3":      getattr(_M, "general_x4v3",     getattr(_M, "animevideov3", None)),
    "general-wdn-x4v3":  getattr(_M, "general_wdn_x4v3", getattr(_M, "animevideov3", None)),
    # Anime-Janai V2/V3 (anime-tuned)
    "animejanaiv2-l1":   getattr(_M, "animejanaiV2L1", None),
    "animejanaiv2-l2":   getattr(_M, "animejanaiV2L2", None),
    "animejanaiv2-l3":   getattr(_M, "animejanaiV2L3", None),
    "animejanaiv3-l1":   getattr(_M, "animejanaiV3_HD_L1", None),
    "animejanaiv3-l2":   getattr(_M, "animejanaiV3_HD_L2", None),
    "animejanaiv3-l3":   getattr(_M, "animejanaiV3_HD_L3", None),
}
model_key = MODEL.lower()
if model_key not in _MODEL_MAP or _MODEL_MAP[model_key] is None:
    available = sorted(k for k, v in _MODEL_MAP.items() if v is not None)
    raise ValueError(
        f"Unknown or unavailable AUDION_VS_MODEL={MODEL!r}. "
        f"Available in this vsmlrt build: {', '.join(available)}"
    )
model_enum = _MODEL_MAP[model_key]

# Resolve backend
if BACKEND == "auto":
    backend, picked = _auto_backend()
else:
    backend = _resolve_backend(BACKEND)
    picked = BACKEND

# Load and convert to RGBS (Real-ESRGAN ONNX expects 32-bit float RGB)
src = _load(INPUT)
src = core.std.SetFrameProps(src, _Matrix=1, _Transfer=1, _Primaries=1, _Range=1)
rgb = core.resize.Bicubic(src, format=vs.RGBS, matrix_in_s="709")
tile = _fit_tile(rgb, TILE)

# Run upscale. Real-ESRGAN models in vsmlrt are 4x by default; we downscale 2x
# back so the final result is ~2x of source (sharper than Lanczos at 2x).
upscaled = vsmlrt.RealESRGAN(
    rgb,
    scale=2,            # final scale factor
    model=model_enum,
    backend=backend,
    tiles=None,         # let tile size drive memory
    tilesize=tile,
    overlap=TILE_PAD,
)

# Convert back to YUV420P10 for our standard encoders
out = core.resize.Bicubic(upscaled, format=vs.YUV420P10, matrix_s="709")
out = core.std.SetFrameProps(out, _Matrix=1, _Transfer=1, _Primaries=1, _Range=1)
out.set_output()
