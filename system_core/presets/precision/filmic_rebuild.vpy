# Audion VS Engine -- Precision palette
# Preset: filmic_rebuild  (the flagship Stage 3 composition)
# Stack:  BM3D float denoise -> neo_f3kdb deband -> luma-zoned AddGrain
# Goal:   "rebuild a clean filmic look" -- digital noise gone, banding gone,
#         then reintroduce controlled fine grain that scales by luma zone:
#         heavier in shadows (where film grain is naturally most visible),
#         lighter in mids, lightest in highlights.
#
# Required:
#   AUDION_VS_INPUT             absolute path to source
# Optional:
#   AUDION_VS_SIGMA             float, BM3D luma sigma.        default 2.0  (range 1.0..3.5)
#   AUDION_VS_DEBAND_RANGE      int, neo_f3kdb range.          default 14
#   AUDION_VS_GRAIN_SHADOW      float, grain in shadow zone.   default 1.5
#   AUDION_VS_GRAIN_MID         float, grain in mid-tones.     default 0.9
#   AUDION_VS_GRAIN_HIGH        float, grain in highlights.    default 0.4
#   AUDION_VS_SHADOW_THRESHOLD  float [0..1], shadow zone end. default 0.30
#   AUDION_VS_HIGH_THRESHOLD    float [0..1], highlight start. default 0.65
#   AUDION_VS_NOISE             "auto" | "fixed".              default "auto"
#                                  auto: the noise measured in the source raises the sigma (never below SIGMA)
#
import os
import vapoursynth as vs
core = vs.core

import audion_lib as al

INPUT             = os.environ["AUDION_VS_INPUT"]
SIGMA             = float(os.environ.get("AUDION_VS_SIGMA", "2.0"))
DEBAND_RANGE      = int(os.environ.get("AUDION_VS_DEBAND_RANGE", "14"))
GRAIN_SHADOW      = float(os.environ.get("AUDION_VS_GRAIN_SHADOW", "1.5"))
GRAIN_MID         = float(os.environ.get("AUDION_VS_GRAIN_MID",    "0.9"))
GRAIN_HIGH        = float(os.environ.get("AUDION_VS_GRAIN_HIGH",   "0.4"))
SHADOW_THRESHOLD  = float(os.environ.get("AUDION_VS_SHADOW_THRESHOLD", "0.30"))
HIGH_THRESHOLD    = float(os.environ.get("AUDION_VS_HIGH_THRESHOLD",   "0.65"))


src = al.load_source(INPUT)

# BM3D's sigma is a standard deviation: it follows the measured noise, luma and chroma each their own.
NOISE = al.measured_noise(src)
SIGMA_Y = al.by_noise(SIGMA, NOISE and NOISE[0])
SIGMA_C = al.by_noise(SIGMA * 0.6, al.chroma_noise(NOISE))
al.report_noise("filmic_rebuild", NOISE, f"BM3D sigma {SIGMA_Y:.2f} / {SIGMA_C:.2f}")

# ============== STAGE 1: BM3D denoise (float) ==============
flt = core.fmtc.bitdepth(src, bits=32, flt=1)
sigma_yuv = [SIGMA_Y, SIGMA_C, SIGMA_C]
# The device - the processor or the video card - is AUDION_VS_BM3D, which the service sets from PROCESSING.
flt = al.bm3d(flt, sigma=sigma_yuv, radius=0)

# ============== STAGE 2: Deband (16-bit int) ==============
clip16 = core.fmtc.bitdepth(flt, bits=16)
clip16 = core.neo_f3kdb.Deband(
    clip16,
    range=DEBAND_RANGE,
    y=48, cb=32, cr=32,
    grainy=0, grainc=0,        # we'll add zoned grain ourselves
    sample_mode=2,
)

# ============== STAGE 3: Luma-zoned grain ==============
# Build smooth masks in 16-bit space (0..65535).
# Shadow mask: 1 below SHADOW_THRESHOLD, smooth ramp to 0 by SHADOW_THRESHOLD + 0.10
# High mask:   1 above HIGH_THRESHOLD,   smooth ramp from 0 starting HIGH_THRESHOLD - 0.10
# Mid mask  =  65535 - shadow - high (whatever is left)

T_shadow = int(SHADOW_THRESHOLD * 65535)
T_high   = int(HIGH_THRESHOLD   * 65535)
RAMP     = int(0.10 * 65535)  # 10% transition width

luma = core.std.ShufflePlanes(clip16, 0, vs.GRAY)

# Shadow: clamp((T_shadow + RAMP - x) / RAMP, 0, 1) * 65535
mask_shadow = core.std.Expr(
    [luma],
    f"{T_shadow + RAMP} x - {RAMP} / 0 max 1 min 65535 *"
)
# High:    clamp((x - (T_high - RAMP)) / RAMP, 0, 1) * 65535
mask_high = core.std.Expr(
    [luma],
    f"x {T_high - RAMP} - {RAMP} / 0 max 1 min 65535 *"
)
# Mid (whatever is left)
mask_mid = core.std.Expr(
    [mask_shadow, mask_high],
    "65535 x - y -",
)

# Apply different grain levels
def _grain(c, var):
    if var <= 0:
        return c
    return al.add_grain(c, var=var * 1.5, uvar=var * 0.4, constant=False)

g_shadow = _grain(clip16, GRAIN_SHADOW)
g_mid    = _grain(clip16, GRAIN_MID)
g_high   = _grain(clip16, GRAIN_HIGH)

# Compose: layer shadow, then mid, then high using their masks
result = core.std.MaskedMerge(clip16, g_shadow, mask_shadow)
result = core.std.MaskedMerge(result, g_mid,    mask_mid)
result = core.std.MaskedMerge(result, g_high,   mask_high)

# ============== Output 10-bit ==============
out = core.fmtc.bitdepth(result, bits=10)
out = core.std.SetFrameProps(out, _Matrix=1, _Transfer=1, _Primaries=1, _Range=al.source_range())
out.set_output()
