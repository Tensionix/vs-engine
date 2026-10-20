# Audion VS Engine -- Precision palette
# Preset: mild_denoise
# Stack:  DFTTest (spectral denoiser, pure CPU, hardware-agnostic)
# Goal:   universal mild denoise, safe default for "just clean my footage a bit"
#
# Why DFTTest over KNLMeansCL for the default:
#   KNLMeansCL needs a working OpenCL runtime on the GPU/CPU. On many Intel Xe / AMF
#   setups the OpenCL driver throws a fatal error. DFTTest is pure SIMD CPU, fast
#   enough for HD/4K and identical results everywhere.
#
# Read parameters from AUDION_VS_* env vars (engine fills these in).
# Required:
#   AUDION_VS_INPUT       absolute path to source media
# Optional:
#   AUDION_VS_STRENGTH    "light" | "medium" | "strong"   default "medium"
#   AUDION_VS_NOISE       "auto" | "fixed"                default "auto"
#                           auto: the noise measured in the source raises the sigma (never below the table)
#
import os
import vapoursynth as vs
core = vs.core

import audion_lib as al

INPUT    = os.environ["AUDION_VS_INPUT"]
STRENGTH = os.environ.get("AUDION_VS_STRENGTH", "medium").lower()

# sigma mapping: higher = more aggressive denoise
SIGMA_TABLE = {"light": 4.0, "medium": 8.0, "strong": 14.0}
SIGMA = SIGMA_TABLE.get(STRENGTH, 8.0)

clip = al.load_source(INPUT)

# DFTTest's sigma is a power: it follows the square of the measured noise.
NOISE = al.measured_noise(clip)
SIGMA = al.by_noise(SIGMA, NOISE and NOISE[0], power=2)
al.report_noise("mild_denoise", NOISE, f"DFTTest sigma {SIGMA:.1f}")

# DFTTest works on integer 8/9/10/12/14/16-bit YUV planes directly.
# tbsize=3 = mild temporal smoothing; tbsize=1 = spatial-only.
# For "mild" preset we use tbsize=3 to leverage frame-to-frame coherence.
clip = al.dfttest(
    clip,
    sigma=SIGMA,
    tbsize=3,
    planes=[0, 1, 2],
)

# Tag colorspace metadata; _Range is the source's (in R80+ 0 = limited, 1 = full).
clip = core.std.SetFrameProps(
    clip,
    _Matrix=1, _Transfer=1, _Primaries=1, _Range=al.source_range(),
)

clip.set_output()
