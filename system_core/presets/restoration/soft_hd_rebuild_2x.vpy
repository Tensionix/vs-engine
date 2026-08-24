# Audion VS Engine -- Restoration palette
# Preset: soft_hd_rebuild_2x
# Stack:  light spectral cleanup -> vsmlrt.RealESRGAN -> controlled luma sharpen
# Goal:   Rebuild soft/undersampled HD sources into a cleaner 2x master without
#         exposing camera-brand assumptions in the preset name or UI.
#
# Required:
#   AUDION_VS_INPUT       absolute path to source media
# Optional:
#   AUDION_VS_REBUILD     "conservative" | "balanced" | "aggressive"
#                         default "balanced"
#   AUDION_VS_CLEANUP     "light" | "medium" | "strong" default "medium"
#   AUDION_VS_MODEL       Real-ESRGAN model variant, default "general-x4v3"
#   AUDION_VS_TILE        int 256 / 384 / 512 / 768, default 384
#   AUDION_VS_TILE_PAD    int, default 16
#   AUDION_VS_BACKEND     "auto" | "trt" | "ort_dml" | "ort_cpu", default auto
#
import os

import vapoursynth as vs
core = vs.core

import vsmlrt
import audion_lib as al


INPUT = os.environ["AUDION_VS_INPUT"]
REBUILD = os.environ.get("AUDION_VS_REBUILD", "balanced").lower()
CLEANUP = os.environ.get("AUDION_VS_CLEANUP", "medium").lower()
MODEL = os.environ.get("AUDION_VS_MODEL", "general-x4v3")
TILE = int(os.environ.get("AUDION_VS_TILE", "384"))
TILE_PAD = int(os.environ.get("AUDION_VS_TILE_PAD", "16"))
BACKEND = os.environ.get("AUDION_VS_BACKEND", "auto").lower()

CLEANUP_SIGMA = {"light": 2.0, "medium": 4.0, "strong": 7.0}
SHARP_AMOUNT = {"conservative": 0.05, "balanced": 0.12, "aggressive": 0.22}


def _load(path: str) -> vs.VideoNode:
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


def _luma_unsharp(clip: vs.VideoNode, amount: float) -> vs.VideoNode:
    if amount <= 0 or clip.format is None or clip.format.color_family != vs.YUV:
        return clip
    peak = (1 << clip.format.bits_per_sample) - 1
    y = core.std.ShufflePlanes(clip, 0, vs.GRAY)
    blur = core.std.BoxBlur(y, hradius=1, vradius=1)
    sharp = core.std.Expr([y, blur], f"x x y - {float(amount)} * + 0 max {peak} min")
    return core.std.ShufflePlanes([sharp, clip, clip], [0, 1, 2], vs.YUV)


_M = vsmlrt.RealESRGANv2Model
_MODEL_MAP = {
    "animevideov3":      getattr(_M, "animevideov3", None),
    "animevideo-xsx2":   getattr(_M, "animevideo_xsx2", None),
    "animevideo-xsx4":   getattr(_M, "animevideo_xsx4", None),
    "general-x4v3":      getattr(_M, "general_x4v3", getattr(_M, "animevideov3", None)),
    "general-wdn-x4v3":  getattr(_M, "general_wdn_x4v3", getattr(_M, "animevideov3", None)),
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

if BACKEND == "auto":
    backend, picked = _auto_backend()
else:
    backend = _resolve_backend(BACKEND)
    picked = BACKEND

src = _load(INPUT)
src = al.tag_bt709(src)

work = core.resize.Bicubic(src, format=vs.YUV420P10, matrix_s="709")
sigma = CLEANUP_SIGMA.get(CLEANUP, CLEANUP_SIGMA["medium"])
if sigma > 0:
    work = core.dfttest.DFTTest(work, sigma=sigma, tbsize=1, planes=[0, 1, 2])

rgb = core.resize.Bicubic(work, format=vs.RGBS, matrix_in_s="709")
tile = _fit_tile(rgb, TILE)

upscaled = vsmlrt.RealESRGAN(
    rgb,
    scale=2,
    model=model_enum,
    backend=backend,
    tiles=None,
    tilesize=tile,
    overlap=TILE_PAD,
)

out = core.resize.Bicubic(upscaled, format=vs.YUV420P10, matrix_s="709")
out = _luma_unsharp(out, SHARP_AMOUNT.get(REBUILD, SHARP_AMOUNT["balanced"]))
out = core.std.SetFrameProps(out, _Matrix=1, _Transfer=1, _Primaries=1, _Range=1)
out.set_output()
