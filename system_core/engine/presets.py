"""Preset registry: palette/name -> .vpy path + parameter schema."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .paths import PATHS


@dataclass(frozen=True)
class PresetSpec:
    palette: str           # "precision" | "film_looks" | "retro" | "utilities"
    name: str              # short name, matches .vpy filename stem
    vpy: Path              # absolute path to the .vpy file
    summary: str           # one-line human description
    params: dict[str, Any] = field(default_factory=dict)
    """params: {param_name: {type, default, choices?, range?, doc}}"""

    def resolve(self, user_params: dict[str, Any]) -> dict[str, Any]:
        """Validate & default user params against the schema."""
        out: dict[str, Any] = {}
        for k, schema in self.params.items():
            v = user_params.get(k, schema.get("default"))
            if v is None:
                continue
            t = schema.get("type")
            if t == "float":
                v = float(v)
                lo, hi = schema.get("range", (None, None))
                if lo is not None and v < lo: v = lo
                if hi is not None and v > hi: v = hi
            elif t == "int":
                v = int(v)
                lo, hi = schema.get("range", (None, None))
                if lo is not None and v < lo: v = lo
                if hi is not None and v > hi: v = hi
            elif t == "choice":
                choices = schema.get("choices", [])
                if v not in choices:
                    raise ValueError(f"{k}: {v!r} not in {choices}")
            out[k] = v
        # passthrough of unknown user params (engine-level options ignore here)
        return out


# ---------- Registry of presets we ship in v1 ----------
def _build_registry() -> dict[tuple[str, str], PresetSpec]:
    base = PATHS.presets_dir
    specs: list[PresetSpec] = [
        # =================== STAGE 1 -- DENOISE ===================
        PresetSpec(
            palette="precision", name="mild_denoise",
            vpy=base / "precision" / "mild_denoise.vpy",
            summary="DFTTest spectral denoise (CPU, hardware-agnostic)",
            params={
                "strength": {"type": "choice", "choices": ["light", "medium", "strong"], "default": "medium",
                             "doc": "DFTTest sigma: light=4.0, medium=8.0, strong=14.0"},
            },
        ),
        PresetSpec(
            palette="precision", name="shadow_denoise_sota",
            vpy=base / "precision" / "shadow_denoise_sota.vpy",
            summary="BM3D float SOTA denoise + shadow-only luma mask (CUDA pref, CPU fallback)",
            params={
                "sigma":            {"type": "float",  "default": 2.5, "range": (1.0, 4.0),
                                     "doc": "BM3D luma sigma; chroma is sigma*0.6"},
                "use_cuda":         {"type": "choice", "choices": ["0", "1"], "default": "0",
                                     "doc": "1 = use bm3dcuda if loaded; 0 = always CPU fallback"},
                "grain_back":       {"type": "float",  "default": 0.6, "range": (0.0, 2.0),
                                     "doc": "micro-grain restoration so denoised shadows are not plastic (0 = off)"},
                "shadow_threshold": {"type": "float",  "default": 0.20, "range": (0.0, 0.5),
                                     "doc": "luma cut where shadow zone ends (float, 0..1)"},
                "transition":       {"type": "float",  "default": 0.10, "range": (0.01, 0.40),
                                     "doc": "smooth transition width above the threshold"},
                "preview_mask":     {"type": "choice", "choices": ["0", "1"], "default": "0",
                                     "doc": "1 = output the shadow mask itself (debug / tuning)"},
            },
        ),
        PresetSpec(
            palette="precision", name="chroma_cleanup",
            vpy=base / "precision" / "chroma_cleanup.vpy",
            summary="DFTTest on chroma planes only -- kills chroma noise, leaves luma intact",
            params={
                "strength": {"type": "choice", "choices": ["light", "medium", "strong"], "default": "medium",
                             "doc": "chroma sigma: light=6, medium=12, strong=20"},
            },
        ),
        # =================== STAGE 2 -- DEBAND ===================
        PresetSpec(
            palette="precision", name="deband_safe",
            vpy=base / "precision" / "deband_safe.vpy",
            summary="neo_f3kdb light deband, no grain",
            params={
                "range": {"type": "int", "default": 12, "range": (8, 32),
                          "doc": "neo_f3kdb evaluation range"},
                "y":     {"type": "int", "default": 48, "range": (0, 128), "doc": "luma threshold"},
                "cb":    {"type": "int", "default": 32, "range": (0, 128), "doc": "Cb threshold"},
                "cr":    {"type": "int", "default": 32, "range": (0, 128), "doc": "Cr threshold"},
            },
        ),
        PresetSpec(
            palette="precision", name="deband_fine_grain",
            vpy=base / "precision" / "deband_fine_grain.vpy",
            summary="neo_f3kdb (medium) + AddGrain micro-texture restore",
            params={
                "range":     {"type": "int",   "default": 14, "range": (8, 32), "doc": "neo_f3kdb range"},
                "y":         {"type": "int",   "default": 48, "range": (0, 128)},
                "cb":        {"type": "int",   "default": 32, "range": (0, 128)},
                "cr":        {"type": "int",   "default": 32, "range": (0, 128)},
                "grain_var": {"type": "float", "default": 0.6, "range": (0.0, 2.0),
                              "doc": "AddGrain luma variance (chroma is var*0.27)"},
            },
        ),
        # =================== STAGE 3 -- COMPOSITIONS ===================
        PresetSpec(
            palette="precision", name="filmic_rebuild",
            vpy=base / "precision" / "filmic_rebuild.vpy",
            summary="BM3D denoise -> neo_f3kdb deband -> luma-zoned grain (flagship)",
            params={
                "sigma":            {"type": "float", "default": 2.0, "range": (1.0, 3.5),
                                     "doc": "BM3D luma sigma"},
                "use_cuda":         {"type": "choice", "choices": ["0", "1"], "default": "0"},
                "deband_range":     {"type": "int",   "default": 14, "range": (8, 32)},
                "grain_shadow":     {"type": "float", "default": 1.5, "range": (0.0, 3.0),
                                     "doc": "grain variance in shadow zone (heaviest)"},
                "grain_mid":        {"type": "float", "default": 0.9, "range": (0.0, 3.0)},
                "grain_high":       {"type": "float", "default": 0.4, "range": (0.0, 3.0)},
                "shadow_threshold": {"type": "float", "default": 0.30, "range": (0.0, 0.5),
                                     "doc": "where shadow zone ends (0..1)"},
                "high_threshold":   {"type": "float", "default": 0.65, "range": (0.5, 1.0),
                                     "doc": "where highlight zone begins (0..1)"},
            },
        ),
        PresetSpec(
            palette="precision", name="archive_clean",
            vpy=base / "precision" / "archive_clean.vpy",
            summary="DFTTest mild + neo_f3kdb light, NO grain (neutral master)",
            params={
                "denoise": {"type": "choice", "choices": ["light", "medium", "strong"], "default": "light",
                            "doc": "DFTTest sigma: light=4, medium=8, strong=14"},
                "range":   {"type": "int", "default": 10, "range": (8, 32),
                            "doc": "neo_f3kdb range"},
            },
        ),
        PresetSpec(
            palette="precision", name="pregrade_prep",
            vpy=base / "precision" / "pregrade_prep.vpy",
            summary="Very light DFTTest, no deband -- minimum-touch prep for Resolve grading",
            params={
                "strength": {"type": "choice", "choices": ["light", "medium"], "default": "light",
                             "doc": "DFTTest sigma: light=3.0, medium=6.0"},
            },
        ),
        # ============================================================
        #                    FILM LOOKS PALETTE
        # ============================================================
        PresetSpec(
            palette="film_looks", name="cinematic",
            vpy=base / "film_looks" / "cinematic.vpy",
            summary="Universal subtle filmic look -- safe default",
            params={
                "intensity": {"type": "float", "default": 1.0, "range": (0.0, 2.0),
                              "doc": "master scale: 0=off, 1=tuned, 2=heavy"},
            },
        ),
        PresetSpec(
            palette="film_looks", name="film_35mm",
            vpy=base / "film_looks" / "film_35mm.vpy",
            summary="Kodak 35mm emulation with stock variants (250D / 500T / 50D)",
            params={
                "stock":     {"type": "choice", "choices": ["250D", "500T", "50D"], "default": "250D",
                              "doc": "250D=daylight neutral; 500T=tungsten cooler; 50D=cleanest"},
                "intensity": {"type": "float", "default": 1.0, "range": (0.0, 2.0)},
            },
        ),
        PresetSpec(
            palette="film_looks", name="film_16mm",
            vpy=base / "film_looks" / "film_16mm.vpy",
            summary="16mm vibe -- heavier softness, visible grain, lifted blacks",
            params={
                "intensity": {"type": "float", "default": 1.0, "range": (0.0, 2.0)},
            },
        ),
        PresetSpec(
            palette="film_looks", name="super8",
            vpy=base / "film_looks" / "super8.vpy",
            summary="Super 8 -- heaviest grain, softest optics, faded 70s contrast",
            params={
                "intensity": {"type": "float", "default": 1.0, "range": (0.0, 2.0)},
            },
        ),
        PresetSpec(
            palette="film_looks", name="bleach_bypass",
            vpy=base / "film_looks" / "bleach_bypass.vpy",
            summary="High contrast, desaturated, harsh -- 'Se7en' / 'Saving Private Ryan'",
            params={
                "intensity": {"type": "float", "default": 1.0, "range": (0.0, 2.0)},
            },
        ),
        # ============================================================
        #                       RETRO PALETTE
        # ============================================================
        PresetSpec(
            palette="retro", name="vhs_crt",
            vpy=base / "retro" / "vhs_crt.vpy",
            summary="Composite-video / VHS / CRT -- chroma bleed, soft, analog noise",
            params={
                "intensity": {"type": "float", "default": 1.0, "range": (0.0, 2.0)},
            },
        ),
        PresetSpec(
            palette="retro", name="camcorder_90s",
            vpy=base / "retro" / "camcorder_90s.vpy",
            summary="Consumer camcorder feel -- softer than VHS, slight overexposure, mild bleed",
            params={
                "intensity": {"type": "float", "default": 1.0, "range": (0.0, 2.0)},
            },
        ),

        # =================== PHASE 18.B-ML (vs-mlrt presets) ===================
        # Require Install-VS-mlrt.cmd (TensorRT bundle + models pack).
        # Backend is auto-selected: TRT -> ORT_DML -> ORT_CPU.
        PresetSpec(
            palette="restoration", name="vsmlrt_realesrgan_2x",
            vpy=base / "restoration" / "vsmlrt_realesrgan_2x.vpy",
            summary="Real-ESRGAN ML 2x upscale (vs-mlrt) -- 1080p -> ~3840 with sharp face/fabric texture; TensorRT on NVIDIA",
            params={
                "model":    {"type": "choice",
                             "choices": ["animevideov3", "general-x4v3", "general-wdn-x4v3",
                                         "animejanaiV2-L1", "animejanaiV2-L2", "animejanaiV2-L3"],
                             "default": "general-x4v3",
                             "doc": "Real-ESRGAN model variant; general-x4v3 for live action, animevideov3 for 2D"},
                "tile":     {"type": "int",   "default": 384, "range": (256, 768),
                             "doc": "input tile size in px; smaller = less VRAM, slower"},
                "tile_pad": {"type": "int",   "default": 16,  "range": (4, 64),
                             "doc": "tile padding to hide seams"},
                "backend":  {"type": "choice", "choices": ["auto", "trt", "ort_dml", "ort_cpu"],
                             "default": "auto",
                             "doc": "auto = TRT on NVIDIA -> DirectML -> CPU"},
            },
        ),
        PresetSpec(
            palette="restoration", name="soft_hd_rebuild_2x",
            vpy=base / "restoration" / "soft_hd_rebuild_2x.vpy",
            summary="Soft HD Rebuild 2X -- cleanup + Real-ESRGAN reconstruction for soft/undersampled HD",
            params={
                "rebuild": {"type": "choice", "choices": ["conservative", "balanced", "aggressive"],
                            "default": "balanced",
                            "doc": "final detail recovery amount; conservative avoids halos, aggressive is for very soft sources"},
                "cleanup": {"type": "choice", "choices": ["light", "medium", "strong"], "default": "medium",
                            "doc": "pre-ML spectral cleanup so noise/compression is not amplified"},
                "model":   {"type": "choice",
                            "choices": ["animevideov3", "general-x4v3", "general-wdn-x4v3",
                                        "animejanaiV2-L1", "animejanaiV2-L2", "animejanaiV2-L3"],
                            "default": "general-x4v3",
                            "doc": "Real-ESRGAN model variant; keep default for mixed/live material"},
                "tile":    {"type": "int", "default": 384, "range": (256, 768),
                            "doc": "input tile size in px; smaller = less VRAM, slower"},
                "tile_pad": {"type": "int", "default": 16, "range": (4, 64),
                             "doc": "tile padding to hide borders"},
                "backend": {"type": "choice", "choices": ["auto", "trt", "ort_dml", "ort_cpu"],
                            "default": "auto",
                            "doc": "auto = TRT on NVIDIA -> DirectML -> CPU"},
            },
        ),
        PresetSpec(
            palette="restoration", name="vsmlrt_rife_60fps",
            vpy=base / "restoration" / "vsmlrt_rife_60fps.vpy",
            summary="RIFE ML frame interpolation (vs-mlrt) -- 24->60fps smooth motion; cleaner than Resolve Optical Flow",
            params={
                "fps_mul": {"type": "float", "default": 2.5, "range": (1.5, 8.0),
                            "doc": "FPS multiplier; 2.5 for 24->60, 2 for 24->48, 4 for slow-mo"},
                "model":   {"type": "choice",
                            "choices": ["rife_v4.4", "rife_v4.6", "rife_v4.9"],
                            "default": "rife_v4.6",
                            "doc": "RIFE model version; v4.6 is balanced, v4.9 is newest"},
                "backend": {"type": "choice", "choices": ["auto", "trt", "ort_dml", "ort_cpu"],
                            "default": "auto"},
            },
        ),
        PresetSpec(
            palette="restoration", name="dpir_denoise",
            vpy=base / "restoration" / "dpir_denoise.vpy",
            summary="DPIR ML-denoise (vs-mlrt) -- heavy noise / high-ISO source while preserving texture; better than BM3D on really dirty footage",
            params={
                "strength": {"type": "float", "default": 10.0, "range": (1.0, 50.0),
                             "doc": "noise level estimate sigma; 10 medium / 15 heavy / 25 very heavy"},
                "model":    {"type": "choice",
                             "choices": ["drunet_color", "drunet_gray",
                                         "drunet_deblocking_color", "drunet_deblocking_gray"],
                             "default": "drunet_color",
                             "doc": "drunet_color for color video; deblocking_color for JPEG/MPEG block artifacts"},
                "tile":     {"type": "int",   "default": 384, "range": (256, 512),
                             "doc": "input tile size"},
                "backend":  {"type": "choice", "choices": ["auto", "trt", "ort_dml", "ort_cpu"],
                             "default": "auto"},
            },
        ),

        # =================== PHASE 18.C looks (2026-04-28) ===================
        PresetSpec(
            palette="film_looks", name="imax_70mm",
            vpy=base / "film_looks" / "imax_70mm.vpy",
            summary="Large-format 65/70mm IMAX feel -- minimal grain, gentle highlight halation, subtle 1px gate weave",
            params={
                "intensity":  {"type": "float",  "default": 1.0, "range": (0.0, 2.0)},
                "gate_weave": {"type": "choice", "choices": ["0", "1"], "default": "1",
                               "doc": "1 = subtle 1px random per-frame offset; 0 = perfectly stable"},
            },
        ),
        PresetSpec(
            palette="film_looks", name="anamorphic_scope",
            vpy=base / "film_looks" / "anamorphic_scope.vpy",
            summary="Hollywood cinemascope look -- horizontal blue lens flares only on highlights + teal-cool shadows (Abrams / Nolan aesthetic)",
            params={
                "intensity":   {"type": "float", "default": 1.0,  "range": (0.0, 2.0)},
                "flare_len":   {"type": "int",   "default": 96,   "range": (32, 256),
                                "doc": "anamorphic streak length in pixels; longer = more dramatic"},
                "flare_thr":   {"type": "float", "default": 0.78, "range": (0.0, 1.0),
                                "doc": "highlight threshold for flare cut-in; lower = more pixels flare"},
                "teal_shadow": {"type": "float", "default": 0.35, "range": (0.0, 1.0),
                                "doc": "teal-cool tint strength in shadows (J.J.Abrams / Nolan)"},
            },
        ),
        PresetSpec(
            palette="retro", name="polaroid",
            vpy=base / "retro" / "polaroid.vpy",
            summary="1970s-80s Polaroid SX-70 feel -- heavy candy-bloom highlights, warm cream midtones, edge vignette",
            params={
                "intensity": {"type": "float", "default": 1.0, "range": (0.0, 2.0)},
                "vignette":  {"type": "float", "default": 0.55, "range": (0.0, 1.0),
                              "doc": "corner darkness; 0 = no vignette, 1 = corners go to black"},
            },
        ),

        # =================== RESTORATION (Phase 18.B) ===================
        # The "you cannot do this in Adobe / DaVinci out of the box" set.
        # Requires extra plugins from Install-VS-Plugins.cmd:
        # havsfunc, mvsfunc, mvtools, tivtc.
        PresetSpec(
            palette="restoration", name="qtgmc_deinterlace",
            vpy=base / "restoration" / "qtgmc_deinterlace.vpy",
            summary="QTGMC reference-quality deinterlace (NNEDI3 + MVTools); for legacy interlaced sources",
            params={
                "field_order": {"type": "choice", "choices": ["tff", "bff"], "default": "tff",
                                "doc": "tff = top-field-first (broadcast/HDV/DV-NTSC), bff = bottom-first (DV-PAL)"},
                "preset":      {"type": "choice",
                                "choices": ["Draft", "Ultra Fast", "Super Fast", "Very Fast",
                                            "Faster", "Fast", "Medium", "Slow", "Slower",
                                            "Very Slow", "Placebo"],
                                "default": "Medium",
                                "doc": "QTGMC speed/quality preset"},
                "output_fps":  {"type": "choice", "choices": ["single", "double"], "default": "single",
                                "doc": "single = same fps as source; double = 2x fps for smoothest motion"},
            },
        ),
        PresetSpec(
            palette="restoration", name="mvtools_mcdegrain",
            vpy=base / "restoration" / "mvtools_mcdegrain.vpy",
            summary="Motion-compensated temporal denoise (MVTools+MDegrain); kills noise without softening detail",
            params={
                "radius":  {"type": "int",   "default": 2, "range": (1, 3),
                            "doc": "temporal radius (frames before/after considered)"},
                "thsad":   {"type": "int",   "default": 200, "range": (100, 400),
                            "doc": "block-match SAD threshold; higher = more aggressive averaging"},
                "blksize": {"type": "choice", "choices": ["8", "16"], "default": "16",
                            "doc": "motion search block size; 16 for HD, 8 for 4K detail"},
            },
        ),
        PresetSpec(
            palette="restoration", name="dehaze_local_contrast",
            vpy=base / "restoration" / "dehaze_local_contrast.vpy",
            summary="Luma-only local contrast / clarity / haze removal with zone-weighted falloff (no color shift, no halos)",
            params={
                "strength": {"type": "float", "default": 1.0, "range": (0.0, 2.0),
                             "doc": "overall amount of local contrast added back; 0 = passthrough"},
                "radius":   {"type": "int",   "default": 8, "range": (1, 16),
                             "doc": "low-pass kernel size in pixels; bigger = haze, smaller = clarity"},
            },
        ),
        PresetSpec(
            palette="restoration", name="tivtc_ivtc",
            vpy=base / "restoration" / "tivtc_ivtc.vpy",
            summary="TIVTC inverse-telecine (NTSC 29.97 fps telecined -> 23.976 fps progressive); reference-quality 3:2 pulldown removal",
            params={
                "pp":    {"type": "int", "default": 6, "range": (0, 7),
                          "doc": "TFM post-processor mode (0=off..7=full deinterlace fallback)"},
                "cycle": {"type": "int", "default": 5, "range": (2, 25),
                          "doc": "TDecimate cycle length (5 = standard NTSC telecine)"},
                "rdrop": {"type": "int", "default": 1, "range": (1, 5),
                          "doc": "frames dropped per cycle (1 of 5 = NTSC default)"},
            },
        ),
        PresetSpec(
            palette="restoration", name="derainbow_decross",
            vpy=base / "restoration" / "derainbow_decross.vpy",
            summary="MVTools motion-compensated chroma-only smoothing -- removes NTSC composite rainbow / dot-crawl / cross-color (no luma softening)",
            params={
                "strength": {"type": "float", "default": 0.6, "range": (0.0, 1.0),
                             "doc": "chroma smoothing intensity; 0 = passthrough, 1 = full"},
                "blksize":  {"type": "choice", "choices": ["8", "16"], "default": "16",
                             "doc": "motion search block size; 16 for SD/HD, 8 for finer detail"},
            },
        ),
        PresetSpec(
            palette="restoration", name="deblock_h264_artefacts",
            vpy=base / "restoration" / "deblock_h264_artefacts.vpy",
            summary="havsfunc.Deblock_QED -- edge-aware deblocker for over-compressed H.264 / MPEG sources (YouTube rips, WhatsApp re-encodes, low-bitrate broadcast)",
            params={
                "quant1":  {"type": "int", "default": 24, "range": (16, 32),
                            "doc": "base quant strength on block edges; higher = stronger"},
                "quant2":  {"type": "int", "default": 26, "range": (16, 32),
                            "doc": "secondary quant for inner block area"},
                "aoffset": {"type": "int", "default": 1, "range": (0, 2),
                            "doc": "alpha offset (edge sensitivity)"},
                "boffset": {"type": "int", "default": 1, "range": (0, 2),
                            "doc": "beta offset (intra sensitivity)"},
            },
        ),
    ]
    return {(s.palette, s.name): s for s in specs}


REGISTRY: dict[tuple[str, str], PresetSpec] = _build_registry()


def get(palette: str, name: str) -> PresetSpec:
    try:
        return REGISTRY[(palette, name)]
    except KeyError:
        avail = ", ".join(f"{p}/{n}" for (p, n) in REGISTRY)
        raise KeyError(f"preset {palette}/{name} not registered. Available: {avail}")


def list_all() -> list[PresetSpec]:
    return [REGISTRY[k] for k in sorted(REGISTRY)]
