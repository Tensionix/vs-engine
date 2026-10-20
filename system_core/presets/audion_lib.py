from __future__ import annotations

import hashlib
import os
from pathlib import Path

import vapoursynth as vs

core = vs.core

# AddGrain draws its seed from the clock unless one is given: two renders of one file had different grain, and a
# before/after comparison of a look compared two draws of noise. With a seed the same file gives the same frames.
GRAIN_SEED = 1


def index_file(path: str, extension: str) -> str:
    """Where the index of a source lives: in the program's folder (._runtime\\index, or AUDION_VS_INDEX_DIR), not beside
    the source - L-SMASH and FFMS2 write their .lwi / .ffindex next to the file by default, into the person's folder.
    One index per source path: a source whose size or time changed gets a new one and the old one is removed."""
    source = Path(path).resolve()
    stat = source.stat()
    named = os.environ.get("AUDION_VS_INDEX_DIR", "").strip()
    folder = Path(named) if named else Path(__file__).resolve().parents[2] / "._runtime" / "index"
    folder.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(str(source).lower().encode("utf-8")).hexdigest()[:16]
    stamp = hashlib.sha1(f"{stat.st_size}:{stat.st_mtime_ns}".encode("ascii")).hexdigest()[:8]
    name = f"{source.stem[:40]}.{key}.{stamp}{extension}"
    for stale in folder.glob(f"*.{key}.*{extension}"):
        if stale.name != name:
            try:
                stale.unlink()
            except OSError:
                pass
    return str(folder / name)


_SOURCE_RANGE = vs.Range.RANGE_LIMITED


def load_source(path: str) -> vs.VideoNode:
    global _SOURCE_RANGE
    try:
        clip = core.lsmas.LWLibavSource(path, cachefile=index_file(path, ".lwi"))
    except (vs.Error, AttributeError):
        clip = core.ffms2.Source(path, cachefile=index_file(path, ".ffindex"))
    _SOURCE_RANGE = clip.get_frame(0).props.get("_Range", vs.Range.RANGE_LIMITED)
    return clip


def source_range() -> int:
    """The _Range of the source load_source opened, for the output's frame props: the presets keep the levels of
    their source (fmtc goes to float and back with the same mapping), so a full-range source stays full range.
    In R80+ _Range is 0 = limited, 1 = full - the deprecated _ColorRange had them the other way round."""
    return int(_SOURCE_RANGE)


def range_name() -> str:
    """The range of the source as resize names it ("full" / "limited"): a preset that goes to RGB and back gives YUV the
    range it came with - without it resize returns limited, and a full-range source came back squeezed."""
    return "full" if source_range() == vs.Range.RANGE_FULL else "limited"


def add_grain(clip: vs.VideoNode, *, var: float, uvar: float, constant: bool = False) -> vs.VideoNode:
    return core.grain.Add(clip, var=var, uvar=uvar, constant=constant, seed=GRAIN_SEED)


_NOISE_BLOCK = 16


def _plane_values(node: vs.VideoNode, n: int) -> list[float]:
    frame = node.get_frame(n)
    return [v for row in frame[0].tolist() for v in row]


# fmtc.bitdepth to float maps limited-range YUV to 0..1 (luma) and -0.5..0.5 (chroma): 219 and 224 codes of 8 bits.
_CODES = (219.0, 224.0, 224.0)
# The lower tenth of the blocks reads white noise 5-6 % low (measured 0.94-0.98 of added AddGrain noise).
_LOW_TENTH = 1.06


def noise_sigma(clip: vs.VideoNode, *, frames: int = 5) -> list[float] | None:
    """The noise of a clip per plane, as a standard deviation in 8-bit codes of the source.

    Measured where the picture is flat: a plane minus its own 9x9 blur leaves noise and texture, and its standard
    deviation over blocks of 16x16 is taken; the lower tenth of the blocks is the noise, texture and edges sit higher.
    Blocks whose luma is within 3 % of black or white are left out: the noise is clipped there. `frames` frames are
    spread over the clip and the median taken. None when too few blocks are left to tell.

    Measured over the whole frame, not in one zone: in the shadows of clean footage few blocks are flat, and their
    lower tenth reads texture as noise (Canon EOS 90D: 0.27 over the frame, 7.9 in the shadows).
    """
    flt = core.fmtc.bitdepth(clip, bits=32, flt=1)
    # fmtc reads integer YUV as limited range; a full-range source (_Range = RANGE_FULL) has its black below 0.
    full = int(clip.get_frame(0).props.get("_Range", vs.Range.RANGE_LIMITED)) == int(vs.Range.RANGE_FULL)
    black, white = (-16 / 219, 239 / 219) if full else (0.0, 1.0)
    lo = black + (white - black) * 0.03
    hi = white - (white - black) * 0.03

    luma = core.std.ShufflePlanes(flt, 0, vs.GRAY)
    maps = []
    for p in range(clip.format.num_planes):
        plane = luma if p == 0 else core.std.ShufflePlanes(flt, p, vs.GRAY)
        rest = core.std.Expr([plane, core.std.BoxBlur(plane, hradius=4, vradius=4)], "x y - dup *")
        local = core.std.BoxBlur(rest, hradius=_NOISE_BLOCK // 2, vradius=_NOISE_BLOCK // 2)
        width, height = max(1, plane.width // _NOISE_BLOCK), max(1, plane.height // _NOISE_BLOCK)
        level = core.resize.Point(core.std.BoxBlur(luma, hradius=_NOISE_BLOCK // 2, vradius=_NOISE_BLOCK // 2),
                                  width, height)
        maps.append((core.resize.Point(local, width, height), level))

    count = clip.num_frames
    picks = sorted({min(count - 1, int(count * (i + 0.5) / frames)) for i in range(frames)})
    per_plane: list[list[float]] = [[] for _ in maps]
    for n in picks:
        for p, (local, level) in enumerate(maps):
            values = _plane_values(local, n)
            sigmas = sorted(v ** 0.5 for v, y in zip(values, _plane_values(level, n)) if lo <= y <= hi and v > 1e-12)
            if len(sigmas) >= max(24, len(values) // 50):
                per_plane[p].append(sigmas[len(sigmas) // 10] * _CODES[min(p, 2)] * _LOW_TENTH)
    if not all(per_plane):
        return None
    return [sorted(values)[len(values) // 2] for values in per_plane]


# The strength settings of the denoise presets were made for noise of about 2 codes of 8 bits: there their light,
# medium and strong do what they were made for. Measured noise above that scales a setting - BM3D's sigma and MVTools'
# thresholds with the noise, DFTTest's sigma (a power) with its square - and never takes it below the setting.
NOISE_REFERENCE = 2.0


def noise_mode() -> str:
    """AUDION_VS_NOISE: "auto" (default) - the strength follows the measured noise; "fixed" - the setting as it is."""
    return "fixed" if os.environ.get("AUDION_VS_NOISE", "auto").strip().lower() == "fixed" else "auto"


def measured_noise(clip: vs.VideoNode) -> list[float] | None:
    """noise_sigma of the clip in the auto mode; None in the fixed mode, and the settings stay as they are."""
    return noise_sigma(clip) if noise_mode() == "auto" else None


def by_noise(value: float, noise: float | None, power: int = 1) -> float:
    if not noise or noise <= NOISE_REFERENCE:
        return value
    return value * (noise / NOISE_REFERENCE) ** power


def chroma_noise(noise: list[float] | None) -> float | None:
    return None if not noise else max(noise[1:] or noise[:1])


def report_noise(name: str, sigma: list[float] | None, chosen: str) -> None:
    """One line on stderr for the engine's report, in the auto mode: what was measured and what the preset made of it.
    vspipe's stdout carries the frames, so nothing else may be printed there."""
    if noise_mode() != "auto":
        return
    import sys

    measured = "not measured" if sigma is None else "noise " + " / ".join(f"{s:.2f}" for s in sigma) + " (8-bit, Y/U/V)"
    sys.stderr.write(f"[NOISE] {name}: {measured} -> {chosen}\n")
    sys.stderr.flush()


def tag_bt709(clip: vs.VideoNode) -> vs.VideoNode:
    return core.std.SetFrameProps(clip, _Matrix=1, _Transfer=1, _Primaries=1, _Range=source_range())


def mtf_soften(clip: vs.VideoNode, factor: float) -> vs.VideoNode:
    factor = max(0.5, min(1.0, float(factor)))
    if factor >= 0.995:
        return clip
    width = max(16, int(clip.width * factor)) & ~1
    height = max(16, int(clip.height * factor)) & ~1
    soft = core.resize.Spline36(clip, width, height)
    return core.resize.Spline36(soft, clip.width, clip.height)


def _box_blur(clip: vs.VideoNode, radius: float) -> vs.VideoNode:
    r = max(1, int(round(radius)))
    try:
        return core.std.BoxBlur(clip, hradius=r, vradius=r)
    except Exception:
        return clip


def halation_bloom(
    clip: vs.VideoNode,
    *,
    threshold: int,
    strength: float,
    blur_radius: float = 2.0,
) -> vs.VideoNode:
    if strength <= 0 or clip.format is None or clip.format.color_family != vs.YUV:
        return clip
    peak = (1 << clip.format.bits_per_sample) - 1
    threshold = max(0, min(peak - 1, int(threshold)))
    luma = core.std.ShufflePlanes(clip, 0, vs.GRAY)
    glow = _box_blur(luma, blur_radius)
    expr = f"x y {threshold} - 0 max {float(strength)} * + {peak} min"
    luma_out = core.std.Expr([luma, glow], expr)
    return core.std.ShufflePlanes([luma_out, clip, clip], [0, 1, 2], vs.YUV)


def luma_zoned_grain(
    clip: vs.VideoNode,
    *,
    shadow: float,
    mid: float,
    high: float,
    t_shadow: float = 0.30,
    t_high: float = 0.70,
    ramp: float = 0.10,
) -> vs.VideoNode:
    var = max(0.0, float(shadow), float(mid), float(high))
    if var <= 0:
        return clip
    return add_grain(clip, var=var * 1.2, uvar=var * 0.35, constant=False)


def gamma_curve(clip: vs.VideoNode, gamma: float) -> vs.VideoNode:
    try:
        return core.std.Levels(clip, gamma=float(gamma), planes=[0])
    except Exception:
        return clip


def lift_blacks(clip: vs.VideoNode, lift: float) -> vs.VideoNode:
    if lift <= 0 or clip.format is None or clip.format.color_family != vs.YUV:
        return clip
    peak = (1 << clip.format.bits_per_sample) - 1
    add = int(max(0.0, min(1.0, float(lift))) * peak)
    luma = core.std.ShufflePlanes(clip, 0, vs.GRAY)
    lifted = core.std.Expr([luma], f"x {add} + {peak} min")
    return core.std.ShufflePlanes([lifted, clip, clip], [0, 1, 2], vs.YUV)


def desaturate(clip: vs.VideoNode, amount: float) -> vs.VideoNode:
    amount = max(0.0, min(1.0, float(amount)))
    if amount <= 0 or clip.format is None or clip.format.color_family != vs.YUV:
        return clip
    neutral = 1 << (clip.format.bits_per_sample - 1)
    keep = 1.0 - amount
    u = core.std.ShufflePlanes(clip, 1, vs.GRAY)
    v = core.std.ShufflePlanes(clip, 2, vs.GRAY)
    u = core.std.Expr([u], f"x {neutral} - {keep} * {neutral} +")
    v = core.std.Expr([v], f"x {neutral} - {keep} * {neutral} +")
    return core.std.ShufflePlanes([clip, u, v], [0, 0, 0], vs.YUV)


def bm3d(clip: vs.VideoNode, *, sigma, radius: int = 0) -> vs.VideoNode:
    """BM3D on float YUV 4:4:4, by the first implementation this VapourSynth loads.

    VapourSynth R80 (16 September 2026) dropped API 3 plugins, and BM3DCPU/BM3DCUDA of WolframRhodium are API 3 builds
    still (R2.17, 26 September 2026). So: bm3dcpu when it loads (VapourSynth R79 and older); else bm3dvk - BM3D on the
    Vulkan device of the core (R80+), with the interface of bm3dcuda (sigma per plane, radius), measured 17 October 2026
    at 1.96 s for a 4K frame on Intel Iris Xe; else bm3d of mawen1250 (API 4, CPU), its Basic estimate on the planes
    as they are. AUDION_VS_BM3D=cpu|vulkan|bm3d names one of them.
    """
    wanted = os.environ.get("AUDION_VS_BM3D", "").strip().lower()
    if wanted in ("", "cpu") and hasattr(core, "bm3dcpu"):
        return core.bm3dcpu.BM3D(clip, sigma=sigma, radius=radius)
    if wanted in ("", "vulkan") and hasattr(core, "bm3dvk") and getattr(core, "vulkan_devices", None):
        done = core.bm3dvk.BM3D(core.std.GPUUpload(clip), sigma=sigma, radius=radius)
        return core.std.GPUDownload(done)
    if hasattr(core, "bm3d"):
        # bm3d takes no subsampled clip with chroma, and the presets hand BM3D float 4:2:0 (bm3dcpu and bm3dvk take it
        # and treat every plane alone): every plane goes through as a gray clip with its own sigma, as they do it.
        sigmas = list(sigma) if isinstance(sigma, (list, tuple)) else [sigma]
        planes = []
        for p in range(clip.format.num_planes):
            plane = core.std.ShufflePlanes(clip, p, vs.GRAY)
            s = sigmas[min(p, len(sigmas) - 1)]
            if radius > 0:
                plane = core.bm3d.VAggregate(core.bm3d.VBasic(plane, sigma=[s], radius=radius), radius=radius)
            else:
                plane = core.bm3d.Basic(plane, sigma=[s])
            planes.append(plane)
        if len(planes) == 1:
            return planes[0]
        return core.std.ShufflePlanes(planes, [0, 0, 0], clip.format.color_family)
    raise vs.Error("BM3D: none of bm3dcpu, bm3dvk, bm3d is installed")


_HAVSFUNC = None


def havsfunc():
    """havsfunc (33, archived upstream), able to run where focus2 does not load.

    QTGMC of havsfunc smooths the bobbed clip with focus2.TemporalSoften2 - an API 3 plugin VapourSynth R80+ no longer
    loads. Its call is TemporalSoften2(radius, luma, chroma, scenechange, 2) with the luma threshold at 255 of 8-bit -
    no threshold, a plain mean of the window; zsmooth.TemporalSoften(radius, [luma, chroma, chroma], scenechange) is the
    same mean, its threshold read in the clip's own bit depth (havsfunc has scaled it already), 0 = the plane copied, as
    TemporalSoften2 does with a chroma threshold of 0. The installed havsfunc is not touched: its source is read and only
    those calls are changed in this copy, and only when focus2 is not there.
    """
    global _HAVSFUNC
    if _HAVSFUNC is not None:
        return _HAVSFUNC
    import havsfunc as original

    if hasattr(core, "focus2") or not hasattr(core, "zsmooth"):
        _HAVSFUNC = original
        return original
    import re
    import types

    source = open(original.__file__, encoding="utf-8").read()
    pattern = re.compile(r"\.focus2\.TemporalSoften2\(([^,()]+),\s*([^,()]+),\s*([^,()]+),\s*([^,()]+),\s*2\)")
    patched, count = pattern.subn(r".zsmooth.TemporalSoften(\1, [\2, \3, \3], \4)", source)
    module = types.ModuleType("havsfunc_zsmooth")
    module.__file__ = original.__file__
    exec(compile(patched, original.__file__ + " (focus2 -> zsmooth)", "exec"), module.__dict__)
    module.AUDION_PATCHED_CALLS = count
    _HAVSFUNC = module
    return module


def dfttest(clip: vs.VideoNode, **kwargs) -> vs.VideoNode:
    """DFTTest by HolyWu when it loads (VapourSynth R79 and older - an API 3 build), else dfttest2 on the CPU, whose
    DFTTest "is compatible with core.dfttest.DFTTest by HolyWu" (AmusementClub/vs-dfttest2)."""
    if hasattr(core, "dfttest"):
        return core.dfttest.DFTTest(clip, **kwargs)
    import dfttest2

    return dfttest2.DFTTest(clip, backend=dfttest2.Backend.CPU(), **kwargs)


def vsmlrt_backend_chain() -> list[str]:
    return ["trt", "ort_dml", "ort_cpu"] if os.environ.get("AUDION_VS_HAS_CUDA") == "1" else ["ort_dml", "ort_cpu"]
