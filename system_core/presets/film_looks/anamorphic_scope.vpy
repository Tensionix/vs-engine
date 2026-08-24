# Audion VS Engine -- Film Looks palette
# Preset: anamorphic_scope
# Stack:  Highlight mask -> horizontal-only blur (anamorphic streak) ->
#         blue tint -> additive merge + subtle blue shadow tint + light grain
# Goal:   Hollywood-style cinemascope (2.39:1) anamorphic look. The signature
#         feature: bright lights produce LONG HORIZONTAL BLUE STREAKS (the
#         classic "lens flare" of Panavision / ARRI Master Anamorphic / Hawk
#         lenses). Combined with subtle teal-cool shadows for the J.J. Abrams /
#         Christopher Nolan aesthetic.
#
#         What this gives you that Adobe / DaVinci do NOT:
#         - directional anamorphic streak (NLEs only do circular halation /
#           radial blur; horizontal-only requires either custom shader or
#           expensive plugin like Optical Flares)
#         - blue-tinted streak only on highlights with smooth threshold
#         - everything in 16-bit linear-ish domain so streaks don't clip
#         - reproducible from CLI, easy to batch
#
#         Note: this preset does NOT crop the frame to 2.39:1 -- that's a
#         creative decision (some users want letterboxing, some want full
#         frame for re-frame in NLE). Add ffmpeg crop=W:floor(W/2.39):0:Y in
#         post if you want true scope aspect.
#
# Required:
#   AUDION_VS_INPUT       absolute path to source media
# Optional:
#   AUDION_VS_INTENSITY   float 0.0..2.0 -- master scale.        default 1.0
#   AUDION_VS_FLARE_LEN   int 32..256 -- streak length in px.    default 96
#   AUDION_VS_FLARE_THR   float 0.0..1.0 -- highlight cut-in
#                         threshold (luma above this triggers
#                         streak; lower = more pixels flare).    default 0.78
#   AUDION_VS_TEAL_SHADOW float 0.0..1.0 -- amount of teal-cool
#                         shift in shadows (J.J.Abrams / Nolan
#                         aesthetic).                            default 0.35
#
import os
import vapoursynth as vs
core = vs.core

import audion_lib as al

INPUT        = os.environ["AUDION_VS_INPUT"]
INTENSITY    = max(0.0, min(2.0, float(os.environ.get("AUDION_VS_INTENSITY",    "1.0"))))
FLARE_LEN    = max(32, min(256, int(os.environ.get("AUDION_VS_FLARE_LEN",       "96"))))
FLARE_THR    = max(0.0, min(1.0, float(os.environ.get("AUDION_VS_FLARE_THR",    "0.78"))))
TEAL_SHADOW  = max(0.0, min(1.0, float(os.environ.get("AUDION_VS_TEAL_SHADOW",  "0.35"))))


src = al.load_source(INPUT)
src = al.tag_bt709(src)

# Work in 16-bit RGB so the streak math is unambiguous (per-channel)
clip16 = core.fmtc.bitdepth(src, bits=16)
rgb16  = core.resize.Bicubic(clip16, format=vs.RGB48, matrix_in_s="709")

# 1. Build highlight mask in 16-bit (max-of-RGB > threshold).
#    Threshold in 16-bit domain = THR * 65535.
thr16 = int(FLARE_THR * 65535)
luma_proxy = core.std.Expr([rgb16], [f"x {thr16} - 0 max 65535 {65535 - thr16} / *"])
# luma_proxy has full range 0..65535 only where each channel exceeded threshold

# 2. Horizontal-only blur for the anamorphic streak.
#    fmtconv resize is the cheapest separable kernel we have. Stretch X by FLARE_LEN
#    via downscale-then-upscale (loses high freq horizontally, keeps vertical).
w, h = rgb16.width, rgb16.height
# Horizontal low-pass: shrink X by FLARE_LEN/8, restore. Vertical untouched.
shrunk_w = max(8, w // max(1, FLARE_LEN // 8))
streak = core.resize.Bilinear(luma_proxy, width=shrunk_w, height=h)
streak = core.resize.Bilinear(streak,     width=w,         height=h)

# 3. Tint the streak blue. Anamorphic flares from Panavision-style lenses are
#    typically a desaturated cool blue (C-A around 480-520nm, slight purple
#    edge). RGB scale: R=0.10, G=0.55, B=1.00 -- gives the classic
#    "blue but not cartoon-blue" hue.
intensity_factor = 0.65 * INTENSITY
streak_r = core.std.Expr([streak], [f"x 0.10 * {intensity_factor} *"])
streak_g = core.std.Expr([streak], [f"x 0.55 * {intensity_factor} *"])
streak_b = core.std.Expr([streak], [f"x 1.00 * {intensity_factor} *"])

streak_rgb = core.std.ShufflePlanes([streak_r, streak_g, streak_b], [0, 0, 0], vs.RGB)

# 4. Additive blend -- the streak ADDS light to the picture, never darkens.
#    expr: clamp(orig + streak, 0, 65535)
flared = core.std.Expr([rgb16, streak_rgb], ["x y + 0 max 65535 min"])

# 5. Subtle teal-cool shadow tint. "Teal" in RGB ~ R: -10%, G: +5%, B: +12%
#    in shadow zones only (luma < 0.4). Use a smooth shadow mask.
if TEAL_SHADOW > 0.0:
    yuv16 = core.resize.Bicubic(flared, format=vs.YUV444P16, matrix_s="709")
    luma  = core.std.ShufflePlanes(yuv16, 0, vs.GRAY)
    # Build smooth shadow mask: 1.0 at luma=0, fading to 0.0 at luma=0.4 (16-bit: 26214)
    shadow_mask = core.std.Expr([luma], ["26214 x - 26214 / 0 max 1 min 65535 *"])
    # Apply tint per channel via MaskedMerge with biased copies
    teal_strength = TEAL_SHADOW * INTENSITY
    # Bias: scale R by (1 - 0.10*ts), G by (1 + 0.05*ts), B by (1 + 0.12*ts)
    r_scale = 1.0 - 0.10 * teal_strength
    g_scale = 1.0 + 0.05 * teal_strength
    b_scale = 1.0 + 0.12 * teal_strength
    biased = core.std.Expr(
        [flared],
        [f"x {r_scale} * 0 max 65535 min",
         f"x {g_scale} * 0 max 65535 min",
         f"x {b_scale} * 0 max 65535 min"],
    )
    flared = core.std.MaskedMerge(flared, biased, shadow_mask, planes=[0, 1, 2])

# 6. Convert back to YUV420P10 + add subtle film-style fine grain
out16 = core.resize.Bicubic(flared, format=vs.YUV420P16, matrix_s="709")
if INTENSITY > 0.0:
    out16 = al.luma_zoned_grain(
        out16,
        shadow=0.5 * INTENSITY,
        mid=0.30 * INTENSITY,
        high=0.20 * INTENSITY,
    )

out = core.fmtc.bitdepth(out16, bits=10)
out = core.std.SetFrameProps(out, _Matrix=1, _Transfer=1, _Primaries=1, _Range=1)
out.set_output()
