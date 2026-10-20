"""
Audion VS Engine — Doctor

Probes the full stack:
  - orchestrator Python (this process)
  - portable PowerShell
  - fzf
  - VS-host Python (system_core/vapoursynth/python.exe)
  - vspipe + loaded plugins
  - ffmpeg + ffprobe
  - GPU acceleration (NVIDIA CUDA / Intel/AMF OpenCL)

Exit codes:
  0 = all green or only optional warnings
  1 = something required is missing

--json FILE: every check (label, level OK/INFO/WARN/FAIL, detail) and the counts written to FILE as well.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Force UTF-8 stdout/stderr regardless of console codepage (cp1251 on RU Windows)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
VS_DIR = ROOT / "system_core" / "vapoursynth"
FF_DIR = ROOT / "Tools" / "ffmpeg"

# Self-heal: if the project was moved, fix Scripts/*.exe shebangs before any
# vspipe/vsrepo call. See system_core/engine/selfheal.py.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
try:
    from system_core.engine.selfheal import ensure_pip_shims_repaired
    _heal_status = ensure_pip_shims_repaired()
    if _heal_status == "repaired":
        print("[selfheal] vspipe shim shebang updated to current python.exe")
    elif _heal_status.startswith("repair-failed"):
        print(f"[selfheal] WARN: Repair-PipShims exited with {_heal_status}")
except Exception as _e:
    print(f"[selfheal] skipped: {_e}")

# ---- Tiny color helpers (work in modern Windows Terminal / pwsh) ----
NO_COLOR = os.environ.get("NO_COLOR") or os.environ.get("AUDION_NO_COLOR")
def _c(code: str, s: str) -> str:
    return s if NO_COLOR else f"\033[{code}m{s}\033[0m"
def G(s):  return _c("32", s)
def R(s):  return _c("31", s)
def Y(s):  return _c("33", s)
def C(s):  return _c("36", s)
def DIM(s):return _c("2",  s)


def run(argv, timeout: int = 15) -> tuple[int, str]:
    try:
        cp = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout,
            errors="replace",
        )
        out = (cp.stdout or "") + (cp.stderr or "")
        return cp.returncode, out
    except FileNotFoundError:
        return 127, ""
    except subprocess.TimeoutExpired:
        return 124, ""
    except Exception as e:
        return 1, f"{type(e).__name__}: {e}"


def probe_nvidia() -> tuple[bool, str]:
    rc, out = run(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"], timeout=5)
    if rc == 0 and out.strip():
        return True, out.strip().splitlines()[0]
    return False, "not available"


def section(title: str) -> None:
    print()
    print(C("-" * 72))
    print(C(f"  {title}"))
    print(C("-" * 72))


# Every check as it was rendered: written to the file of --json, the outcome of SERVICE - Doctor.
CHECKS: list[dict[str, str]] = []


def check(label: str, ok: bool, detail: str = "", warn: bool = False, info: bool = False) -> bool:
    """Render a single status line.

    ok=True            -> [OK]
    info=True, ok=*    -> [INFO]   (informational, not a problem; e.g. CPU-only machine)
    warn=True          -> [WARN]   (degraded but tolerated)
    otherwise ok=False -> [FAIL]
    """
    CHECKS.append({"label": label, "level": "OK" if ok else "INFO" if info else "WARN" if warn else "FAIL",
                   "detail": detail})
    if ok:
        tag = G("[OK]   ")
    elif info:
        tag = C("[INFO] ")
    elif warn:
        tag = Y("[WARN] ")
    else:
        tag = R("[FAIL] ")
    print(f"  {tag} {label:<40} {DIM(detail)}")
    return ok


def main() -> int:
    failures = 0
    warnings = 0

    print()
    print(C("======================================================================"))
    print(C("  AUDION VS ENGINE -- DOCTOR"))
    print(C("======================================================================"))
    print(f"  Project root : {ROOT}")
    print(f"  Orchestrator : {sys.executable}")
    print(f"  Python (orch): {sys.version.split()[0]} on {sys.platform}")
    nvidia_available, nvidia_detail = probe_nvidia()

    # ---------- 1. The tools of the program ----------
    section("Program tools")
    fzf = ROOT / "system_core" / "fzf.exe"
    if not check("fzf.exe (system_core)", fzf.exists(), str(fzf)):
        failures += 1

    # The installers run on the PowerShell the program carries; built with the window (install\\Build-App.cmd).
    pwsh = ROOT / "App" / "AudionPs.exe"
    if pwsh.exists():
        rc, out = run([str(pwsh), "-NoLogo", "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"], timeout=20)
        check("PowerShell of the program", rc == 0, f"App\\AudionPs.exe {out.strip().splitlines()[0] if out.strip() else ''}")
    else:
        check("PowerShell of the program", False, "App\\AudionPs.exe is not built (install\\Build-App.cmd)", warn=True)
        warnings += 1

    # ---------- 2. VS Engine ----------
    section("VapourSynth Engine")
    vspy = VS_DIR / "python.exe"
    vspipe = VS_DIR / "Scripts" / "vspipe.exe"
    marker = VS_DIR / "portable.vs"

    if not check("VS-host Python", vspy.exists(), str(vspy)):
        failures += 1
    else:
        rc, out = run([str(vspy), "-V"], timeout=5)
        if rc == 0:
            check("VS-host Python version", True, out.strip())

    if not check("vspipe.exe", vspipe.exists(), str(vspipe)):
        failures += 1
    else:
        rc, out = run([str(vspipe), "--version"], timeout=10)
        ver = ""
        for line in out.splitlines():
            if line.startswith("Core "):
                ver = line.strip()
                break
        check("vspipe runs", rc == 0, ver)

    if marker.exists():
        info = marker.read_text(errors="replace").strip().splitlines()
        check("portable.vs marker", True, info[0] if info else "")
    else:
        check("portable.vs marker", False, "VS not fully installed", warn=True)
        warnings += 1

    # Probe loaded plugins via VS-host python
    if vspy.exists():
        probe = (
            "import vapoursynth as vs; "
            "ns = sorted([p.namespace for p in vs.core.plugins()]); "
            "import json; print(json.dumps(ns))"
        )
        rc, out = run([str(vspy), "-c", probe], timeout=20)
        plugins: list[str] = []
        if rc == 0:
            try:
                last = [l for l in out.splitlines() if l.startswith("[")][-1]
                plugins = json.loads(last)
            except Exception:
                pass
        # The namespaces the presets call (install\vs_plugins.json): API 4 builds, which VapourSynth R80+ requires.
        required = {
            "lsmas":        "L-SMASH source",
            "ffms2":        "FFmpegSource fallback",
            "fmtc":         "fmtconv (bit-depth/matrix)",
            "neo_f3kdb":    "neo_f3kdb (deband)",
            "grain":        "AddGrain (grain restore)",
            "bm3d":         "BM3D CPU (shadow denoise)",
            "dfttest2_cpu": "DFTTest2 CPU (spectral denoise)",
            "mv":           "MVTools (motion-compensated denoise, QTGMC)",
            "zsmooth":      "zsmooth (QTGMC temporal soften)",
            "tivtc":        "TIVTC (inverse telecine)",
            "deblock":      "Deblock (H.264 artefacts)",
            "dctf":         "DCTFilter (H.264 artefacts)",
            "znedi3":       "ZNEDI3 / NNEDI3 interpolation (QTGMC + clean 2x upscale)",
        }
        for ns_name, label in required.items():
            ok = ns_name in plugins
            if not check(f"plugin: {ns_name}", ok, label):
                failures += 1

        required_modules = {
            "vsutil": "havsfunc compatibility helpers",
            "havsfunc": "QTGMC and restoration helpers",
            "mvsfunc": "MVTools script helpers",
            "nnedi3_resample": "deterministic NNEDI3 2x helper",
            "dfttest2": "DFTTest interface of dfttest2",
        }
        for module_name, label in required_modules.items():
            module_probe = (
                "import importlib.util,sys; "
                f"sys.exit(0 if importlib.util.find_spec('{module_name}') else 1)"
            )
            module_rc, _ = run([str(vspy), "-c", module_probe], timeout=20)
            if not check(f"module: {module_name}", module_rc == 0, label):
                failures += 1

        # BM3D on the GPU of any vendor: bm3dvk on a Vulkan device of the core (R80+). Without one BM3D runs on the
        # CPU (bm3d) - normal, so INFO. A live call tells "plugin loaded" from "the device actually runs it".
        gpu_smoke = (
            "import vapoursynth as vs; core = vs.core; "
            "devices = getattr(core, 'vulkan_devices', None) or []; "
            "print('DEVICE', devices[0]['name'] if devices else ''); "
            "c = core.std.BlankClip(width=64, height=64, format=vs.YUV420PS, length=1, color=[0.5,0.5,0.5]); "
            "core.std.GPUDownload(core.bm3dvk.BM3D(core.std.GPUUpload(c), sigma=1.0, radius=0)).get_frame(0); "
            "print('VULKAN_OK')"
        ) if "bm3dvk" in plugins else ""
        rc, out = run([str(vspy), "-c", gpu_smoke], timeout=30) if gpu_smoke else (1, "")
        device = next((l[7:].strip() for l in out.splitlines() if l.startswith("DEVICE ")), "")
        if rc == 0 and "VULKAN_OK" in out:
            check("BM3D on GPU (bm3dvk)", True, f"live call on {device}")
        else:
            check("BM3D on GPU (bm3dvk)", False,
                  "no Vulkan device or bm3dvk not loaded -- BM3D runs on the CPU (bm3d)", info=True)

    # ---------- 3. FFmpeg ----------
    section("FFmpeg")
    ffmpeg = FF_DIR / "bin" / "ffmpeg.exe"
    ffprobe = FF_DIR / "bin" / "ffprobe.exe"
    if not check("ffmpeg.exe", ffmpeg.exists(), str(ffmpeg)):
        failures += 1
    else:
        rc, out = run([str(ffmpeg), "-hide_banner", "-version"], timeout=10)
        v = (out.splitlines() or [""])[0].strip()
        check("ffmpeg runs", rc == 0, v)
    if not check("ffprobe.exe", ffprobe.exists(), str(ffprobe)):
        failures += 1

    # ---------- 4. GPU acceleration ----------
    section("GPU acceleration")
    # NVIDIA / CUDA
    if nvidia_available:
        check("NVIDIA + CUDA", True, nvidia_detail)
    else:
        check("NVIDIA + CUDA", False, nvidia_detail, info=True)

    # OpenCL probe via WMI (Windows): just list video controllers
    if sys.platform == "win32":
        rc, out = run(
            ["wmic", "path", "win32_VideoController", "get", "Name,DriverVersion", "/FORMAT:LIST"],
            timeout=10,
        )
        if rc == 0:
            lines = [l.strip() for l in out.splitlines() if l.strip().startswith("Name=")]
            for line in lines:
                gpu_name = line.split("=", 1)[1]
                check(f"GPU detected", True, gpu_name)

    # ---------- 5. Disk ----------
    section("Disk")
    try:
        usage = shutil.disk_usage(ROOT)
        free_gb = usage.free / (1024 ** 3)
        ok = free_gb > 5.0
        check(f"free space on {ROOT.drive}", ok, f"{free_gb:.1f} GB free", warn=not ok)
        if not ok:
            warnings += 1
    except Exception as e:
        check("disk usage", False, str(e), warn=True)

    # ---------- Summary ----------
    print()
    print(C("======================================================================"))
    if failures == 0 and warnings == 0:
        print(G("  ALL GREEN. Stack is healthy."))
    elif failures == 0:
        print(Y(f"  HEALTHY with {warnings} warning(s) — see above."))
    else:
        print(R(f"  PROBLEMS: {failures} failure(s), {warnings} warning(s)."))
    print(C("======================================================================"))
    print()
    if "--json" in sys.argv[1:]:
        at = sys.argv.index("--json")
        if at + 1 < len(sys.argv):
            Path(sys.argv[at + 1]).write_text(
                json.dumps({"failures": failures, "warnings": warnings, "checks": CHECKS}, ensure_ascii=False, indent=2),
                encoding="utf-8")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
