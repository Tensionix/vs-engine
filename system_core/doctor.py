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
        return 124, f"timeout after {timeout}s"
    except Exception as e:
        return 1, f"{type(e).__name__}: {e}"


def section(title: str) -> None:
    print()
    print(C("-" * 72))
    print(C(f"  {title}"))
    print(C("-" * 72))


def check(label: str, ok: bool, detail: str = "", warn: bool = False, info: bool = False) -> bool:
    """Render a single status line.

    ok=True            -> [OK]
    info=True, ok=*    -> [INFO]   (informational, not a problem; e.g. CPU-only machine)
    warn=True          -> [WARN]   (degraded but tolerated)
    otherwise ok=False -> [FAIL]
    """
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

    # ---------- 1. Template-owned tools ----------
    section("Template tools")
    fzf = ROOT / "system_core" / "fzf.exe"
    if not check("fzf.exe (system_core)", fzf.exists(), str(fzf)):
        failures += 1

    pwsh = ROOT / "system_core" / "powershell" / "pwsh.exe"
    if pwsh.exists():
        rc, out = run([str(pwsh), "--version"], timeout=5)
        check("portable pwsh", rc == 0, out.strip().splitlines()[0] if out else "")
    else:
        check("portable pwsh", False, "not installed (run install\\Install-Portable-PowerShell.cmd)", warn=True)
        warnings += 1

    # 7-Zip CLI (used by every install-* script for archive extraction).
    # Bootstrapped lazily by install\Ensure-7zip.ps1; absence is INFO, not a
    # failure -- they auto-install on first install-* run.
    z_dir = ROOT / "system_core" / "7zip"
    z_zr  = z_dir / "7zr.exe"
    z_za  = z_dir / "7za.exe"
    if z_zr.exists():
        rc, out = run([str(z_zr)], timeout=5)
        ver = ""
        for line in (out or "").splitlines():
            s = line.strip()
            if s.startswith("7-Zip"):
                ver = s
                break
        check("portable 7zr.exe", True, ver or str(z_zr))
    else:
        check("portable 7zr.exe", False,
              "not bootstrapped yet (auto-installs on first install-* run)",
              info=True)
    if z_za.exists():
        rc, out = run([str(z_za)], timeout=5)
        ver = ""
        for line in (out or "").splitlines():
            s = line.strip()
            if s.startswith("7-Zip"):
                ver = s
                break
        check("portable 7za.exe", True, ver or str(z_za))
    else:
        check("portable 7za.exe", False,
              "not bootstrapped yet (auto-installs on first install-* run)",
              info=True)

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
        rc, out = run([str(vspipe), "--version"], timeout=30)
        ver = ""
        for line in out.splitlines():
            if line.startswith("Core "):
                ver = line.strip()
                break
        if not check("vspipe runs", rc == 0, ver or out.strip().splitlines()[-1] if out.strip() else f"exit {rc}"):
            failures += 1

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
        required = {
            "lsmas":     "L-SMASH source",
            "ffms2":     "FFmpegSource fallback",
            "fmtc":      "fmtconv (bit-depth/matrix)",
            "neo_f3kdb": "neo_f3kdb (deband)",
            "grain":     "AddGrain (grain restore)",
            "knlm":      "KNLMeansCL (OpenCL denoise)",
            "bm3dcpu":   "BM3D CPU (shadow denoise)",
            "dfttest":   "DFTTest (spectral denoise)",
            "znedi3":    "ZNEDI3 / NNEDI3 interpolation (QTGMC)",
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
        }
        for module_name, label in required_modules.items():
            module_probe = (
                "import importlib.util,sys; "
                f"sys.exit(0 if importlib.util.find_spec('{module_name}') else 1)"
            )
            module_rc, _ = run([str(vspy), "-c", module_probe], timeout=20)
            if not check(f"module: {module_name}", module_rc == 0, label):
                failures += 1

        # bm3dcuda is bundled by default since Phase 18.A0. Absence on a
        # non-NVIDIA machine is normal (DLL silently fails to load without
        # cudart) -- presets fall back via hasattr check. Treat as INFO.
        bm3dcuda = "bm3dcuda" in plugins
        if bm3dcuda:
            check("plugin: bm3dcuda", True, "BM3D CUDA acceleration available")
        else:
            check("plugin: bm3dcuda", False,
                  "not loaded (CPU fallback active -- normal on non-NVIDIA hosts)",
                  info=True)

        # Live runtime smoke: distinguishes "DLL loaded" from "CUDA actually runs"
        if bm3dcuda:
            cuda_smoke = (
                "import vapoursynth as vs; core = vs.core; "
                "c = core.std.BlankClip(width=64, height=64, format=vs.YUV420PS, length=1, color=[0.5,0.5,0.5]); "
                "_ = core.bm3dcuda.BM3D(c, sigma=1.0, radius=0).get_frame(0); "
                "print('CUDA_OK')"
            )
            rc, out = run([str(vspy), "-c", cuda_smoke], timeout=30)
            cuda_ok = (rc == 0 and "CUDA_OK" in out)
            if cuda_ok:
                check("bm3dcuda runtime", True, "live BM3D CUDA invocation succeeded")
            else:
                has_nvidia_rc, has_nvidia_out = run(
                    ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                    timeout=5,
                )
                err = (out or "").strip().splitlines()
                tail = err[-1] if err else "(no stderr)"
                if has_nvidia_rc != 0 or not has_nvidia_out.strip():
                    check("bm3dcuda runtime", False,
                          "not usable on this host (no NVIDIA GPU detected; CPU/QuickSync path is expected)",
                          info=True)
                else:
                    # Plugin loaded but CUDA call failed on a host that DOES
                    # have NVIDIA. This is actionable.
                    check("bm3dcuda runtime", False,
                          f"plugin loaded but CUDA call failed -- install NVIDIA driver R525+ or CUDA Toolkit Runtime. Last line: {tail[:120]}",
                          warn=True)
                    warnings += 1

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
    rc, out = run(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"], timeout=5)
    if rc == 0 and out.strip():
        gpu = out.strip().splitlines()[0]
        check("NVIDIA + CUDA", True, gpu)
    else:
        check("NVIDIA + CUDA", False, "not available -- BM3D will use CPU fallback", info=True)

    # List video controllers via PowerShell CIM. wmic.exe is deprecated since
    # Win11 22H2 and absent on fresh 24H2+ images, so we never call it.
    # Prefer portable pwsh; fall back to built-in powershell.exe 5.1 (always
    # present on Win10+). Get-CimInstance lives in both.
    if sys.platform == "win32":
        ps_exe = None
        if pwsh.exists():
            ps_exe = str(pwsh)
        else:
            sys_ps = shutil.which("powershell.exe") or shutil.which("powershell")
            if sys_ps:
                ps_exe = sys_ps
        if ps_exe:
            ps_cmd = (
                "Get-CimInstance Win32_VideoController | "
                "ForEach-Object { '{0}|{1}' -f $_.Name, $_.DriverVersion }"
            )
            rc, out = run(
                [ps_exe, "-NoLogo", "-NoProfile", "-NonInteractive",
                 "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
                timeout=15,
            )
            if rc == 0:
                for line in (out or "").splitlines():
                    line = line.strip()
                    if not line or "|" not in line:
                        continue
                    name, drv = (line.split("|", 1) + [""])[:2]
                    detail = name.strip()
                    if drv.strip():
                        detail = f"{detail}  (driver {drv.strip()})"
                    check("GPU detected", True, detail)
            else:
                check("GPU enumeration", False,
                      "Get-CimInstance failed (CIM service down?)",
                      warn=True)
                warnings += 1
        else:
            check("GPU enumeration", False,
                  "no PowerShell available (portable pwsh not installed and powershell.exe missing)",
                  warn=True)
            warnings += 1

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
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
