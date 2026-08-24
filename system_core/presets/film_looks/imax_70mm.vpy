# Audion VS Engine -- Film Looks palette
# Preset: imax_70mm
# Stack:  Subtle MTF soften -> minimal halation -> very fine grain -> 1px gate weave
# Goal:   Large-format 65/70mm IMAX feel. The opposite of Super 8: maximum
#         resolution preserved, almost no grain (large frame area means each
#         silver crystal is tiny relative to picture), gentle highlight halation
#         (large-format optics have less veiling flare than 35mm), and a barely
#         perceptible 1-pixel random gate weave to break the "too clean digital"
#         feel. Use on shots that should feel "epic", not "filmy".
#
#         What this gives you that Adobe / DaVinci do NOT:
#         - calibrated micro-grain plus gate weave (NLEs only do plate grain)
#         - zone-weighted gentle halation (most plugins do flat blur over highlights)
#
# Required:
#   AUDION_VS_INPUT      absolute path to source media
# Optional:
#   AUDION_VS_INTENSITY  float 0.0..2.0 -- master scale; 0 = passthrough,
#                        1 = tuned, 2 = exaggerated.            default 1.0
#   AUDION_VS_GATE_WEAVE int 0|1 -- enable 1px random gate weave.   default 1
#
import os
import random
import vapoursynth as vs
core = vs.core

import audion_lib as al

INPUT      = os.environ["AUDION_VS_INPUT"]
INTENSITY  = max(0.0, min(2.0, float(os.environ.get("AUDION_VS_INTENSITY", "1.0"))))
GATE_WEAVE = os.environ.get("AUDION_VS_GATE_WEAVE", "1") == "1"


src = al.load_source(INPUT)
src = al.tag_bt709(src)

# Work in 16-bit int domain.
clip16 = core.fmtc.bitdepth(src, bits=16)

# 1. Very subtle MTF softening -- IMAX optics have huge MTF area, so we hardly
#    soften at all. factor near 1.0 = passthrough; we drop just slightly.
soft = al.mtf_soften(clip16, factor=1.0 - 0.04 * INTENSITY)

# 2. Gentle highlight halation -- large-format prints bloom less than 35mm.
bloomed = al.halation_bloom(
    soft,
    threshold=int(48000 - 4000 * INTENSITY),  # higher threshold = only brightest highlights
    strength=0.10 * INTENSITY,
    blur_radius=12,
)

# 3. Very fine micro-grain. Even on real 70mm IMAX you can see *some* texture
#    if you look closely; we keep it audible but never distracting.
grained = al.luma_zoned_grain(
    bloomed,
    shadow=0.4 * INTENSITY,
    mid=0.25 * INTENSITY,
    high=0.15 * INTENSITY,
)

# 4. Gate weave -- subtle random offset per frame, simulating film moving in
#    the gate. AddBorders requires mod-2 dimensions on subsampled YUV (4:2:0
#    / 4:2:2), so steps must be EVEN -- a 1-pixel weave is invisible anyway,
#    we step in 2-pixel units and the eye still reads it as "alive".
#
#    Performance: there are at most 9 unique (dx, dy) ∈ {-2,0,+2}². We build
#    each variant clip ONCE outside the FrameEval lambda; per-frame the lambda
#    only does a dict lookup, so the GIL is held for microseconds and VS
#    workers parallelize properly across all cores. The previous version
#    did AddBorders+Crop *inside* the lambda, which kept the GIL across the
#    whole filter call and effectively serialized all VS workers behind one
#    Python thread -- CPU and GPU stayed at ~3% the whole render and a 30-
#    frame smoke took 700+ seconds. This rebuild brings it under 5 seconds.
if GATE_WEAVE and INTENSITY > 0.0:
    n_frames = grained.num_frames
    rng = random.Random(42)  # deterministic; same weave on re-run
    offsets = [(rng.choice((-2, 0, 2)), rng.choice((-2, 0, 2)))
               for _ in range(n_frames)]

    def _shifted(clip, dx, dy):
        if dx == 0 and dy == 0:
            return clip
        return core.std.Crop(
            core.std.AddBorders(clip, left=max(0, dx), right=max(0, -dx),
                                top=max(0, dy), bottom=max(0, -dy)),
            left=max(0, -dx), right=max(0, dx),
            top=max(0, -dy), bottom=max(0, dy),
        )

    variants = {key: _shifted(grained, key[0], key[1])
                for key in set(offsets)}
    grained = core.std.FrameEval(grained, lambda n: variants[offsets[n]])

# Output 10-bit for standard encoders.
out = core.fmtc.bitdepth(grained, bits=10)
out = core.std.SetFrameProps(out, _Matrix=1, _Transfer=1, _Primaries=1, _Range=1)
out.set_output()
