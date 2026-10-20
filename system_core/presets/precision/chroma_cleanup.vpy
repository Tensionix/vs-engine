# Audion VS Engine -- Precision palette
# Preset: chroma_cleanup
# Stack:  DFTTest on chroma planes only (planes=[1,2]); luma untouched.
# Goal:   kill nasty chroma noise / chroma blotches without softening detail.
#
# Required:
#   AUDION_VS_INPUT       absolute path to source
# Optional:
#   AUDION_VS_STRENGTH    "light" | "medium" | "strong"   default "medium"
#                           sigma mapping for chroma: light=6, medium=12, strong=20
#   AUDION_VS_NOISE       "auto" | "fixed"                default "auto"
#                           auto: the chroma noise measured in the source raises the sigma (never below the table)
#
import os
import vapoursynth as vs
core = vs.core

import audion_lib as al

INPUT    = os.environ["AUDION_VS_INPUT"]
STRENGTH = os.environ.get("AUDION_VS_STRENGTH", "medium").lower()
SIGMA    = {"light": 6.0, "medium": 12.0, "strong": 20.0}.get(STRENGTH, 12.0)


clip = al.load_source(INPUT)

# DFTTest's sigma is a power: it follows the square of the measured chroma noise.
NOISE = al.measured_noise(clip)
SIGMA = al.by_noise(SIGMA, al.chroma_noise(NOISE), power=2)
al.report_noise("chroma_cleanup", NOISE, f"DFTTest chroma sigma {SIGMA:.1f}")

# DFTTest on chroma only -- chroma can take heavier sigma than luma
# without visible detail loss because chroma is subsampled.
clip = al.dfttest(clip, sigma=SIGMA, tbsize=3, planes=[1, 2])

clip = core.std.SetFrameProps(clip, _Matrix=1, _Transfer=1, _Primaries=1, _Range=al.source_range())
clip.set_output()
