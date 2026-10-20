"""The engine and the machine: their versions, and which part has a newer release - the badges of the header.

    vs_cli.cmd components            the versions on this machine, the newest releases as last remembered
    vs_cli.cmd components --latest   the newest releases asked of GitHub when the remembered ones are a day old
    vs_cli.cmd components --refresh  asked of GitHub now

One line of JSON: {"components": [...], "checked": "<when GitHub was asked>"}. A component:

  id, name     vapoursynth, plugins, mlrt, ffmpeg, gpu - mlrt when an NVIDIA RTX card is here or MLRT already is
  version      as the part says it of itself ("" - it is not there); of the plugins - "N/M", the ones the core loads of
               install\\vs_plugins.json
  latest       the tag of its newest release ("" - not compared, or not known)
  state        fresh / old - compared (the plugins: all of them load / not all); own - not compared on purpose (the
               driver is the user's); limited - FFmpeg of an NVIDIA driver below the LTS 610.88: the older branch that
               keeps NVENC working, not every operation possible (`driver` says which); missing - not installed;
               unknown - GitHub did not answer
  source       where the newest release is read
  brand        the maker of a GPU: nvidia, intel, amd
  rtx          of a GPU: it is an NVIDIA RTX card - the one MLRT is installed for

The newest release is the tag github.com/<repo>/releases/latest sends the browser to - no API and no limit of requests,
as Audion Media Tools reads it. The answers are kept in config\\components_cache.json.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

CACHE = Path("config") / "components_cache.json"
FRESH_FOR = timedelta(days=1)
TIMEOUT = 8
RELEASES = {"vapoursynth": "vapoursynth/vapoursynth", "mlrt": "AmusementClub/vs-mlrt", "ffmpeg": "GyanD/codexffmpeg"}

# FFmpeg by the NVIDIA driver (install\Install-Portable-FFmpeg-Gyan.ps1 holds the same, 18.10.2026): the newest Gyan stable,
# FFMPEG_FLOOR at least, without an NVIDIA card and from the LTS driver GOLDEN_DRIVER; below it the branch that keeps NVENC
# working - and not every operation is possible. The owner: "600-я серия драйверов уже окрепла и 610.88 стала LTS golden
# версией... собирать на основе драйвера, предупреждая, что при отсутствии минимально допустимого драйвера 610.88 для
# всех возможностей, будут возможны не все операции"; "Закреплять не стоит. Если выйдет 9.1.0 - надо его ставить?"
FFMPEG_FLOOR = "9.0.2"
GOLDEN_DRIVER = "610.88"


def driver_below_golden(driver: str) -> bool:
    """An NVIDIA driver below the LTS one: its FFmpeg is an older branch, not every operation is possible."""
    return bool(driver) and _plain(driver) < _plain(GOLDEN_DRIVER)


def ffmpeg_for_driver(driver: str) -> str:
    """The branch an NVIDIA driver below the LTS one gets ("8.0.1", "7.1"); "" - the newest stable is its."""
    if not driver_below_golden(driver):
        return ""
    return "7.1" if _plain(driver) < (570,) else "8.0.1"


def ffmpeg_warning(driver: str, release: str) -> str:
    return (f"NVIDIA driver {driver} is below {GOLDEN_DRIVER}, the LTS driver the programs are built for: FFmpeg {release} "
            f"is installed so that NVENC works, and not every operation is possible - what needs FFmpeg {FFMPEG_FLOOR} or "
            "newer")


def _quiet(command: list[str], timeout: float = 30) -> str:
    try:
        creation = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        done = subprocess.run(command, capture_output=True, timeout=timeout, creationflags=creation)
    except (OSError, subprocess.SubprocessError):
        return ""
    return (done.stdout or b"").decode("utf-8", errors="replace") + (done.stderr or b"").decode("utf-8", errors="replace")


def _first(pattern: str, text: str) -> str:
    found = re.search(pattern, text, re.MULTILINE)
    return found.group(1) if found else ""


def plugins(root: Path) -> tuple[int, int, list[str]]:
    """The plugins of install\\vs_plugins.json the core loads: how many, of how many, which do not."""
    vs_python = root / "system_core" / "vapoursynth" / "python.exe"
    try:
        listed = json.loads((root / "install" / "vs_plugins.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0, 0, []
    wanted = [item for key in ("python_packages", "github_assets", "vsrepo_packages") for item in listed.get(key) or []]
    if not vs_python.exists():
        return 0, len(wanted), [str(item.get("id")) for item in wanted]
    probe = ("import json, importlib.util, vapoursynth as vs; "
             "ns = [p.namespace for p in vs.core.plugins()]; "
             f"mods = {json.dumps([item['name'] for item in wanted if item.get('probe') == 'module'])}; "
             "print('PLUGINS', json.dumps({'ns': ns, 'mods': [m for m in mods if importlib.util.find_spec(m)]}))")
    out = _quiet([str(vs_python), "-c", probe], timeout=60)
    try:
        found = json.loads(out[out.index("PLUGINS ") + 8:].splitlines()[0])
    except (ValueError, IndexError):
        return 0, len(wanted), [str(item.get("id")) for item in wanted]
    loaded = set(found.get("ns") or []) | set(found.get("mods") or [])
    absent = [str(item.get("id")) for item in wanted if item.get("name") not in loaded]
    return len(wanted) - len(absent), len(wanted), absent


def own_versions(root: Path) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    vspipe = root / "system_core" / "vapoursynth" / "Scripts" / "vspipe.exe"
    core = _first(r"^Core (R\d+(?:\.\d+)?)", _quiet([str(vspipe), "--version"])) if vspipe.exists() else ""
    found.append({"id": "vapoursynth", "name": "VapourSynth", "version": core})

    have, wanted, absent = plugins(root)
    found.append({"id": "plugins", "name": "Plugins", "version": f"{have}/{wanted}" if have else "",
                  "detail": ("not loaded: " + ", ".join(absent)) if absent and have else ""})

    from .machine import mlrt, rtx

    card, release = rtx(), mlrt(root)
    if card or release:
        found.append({"id": "mlrt", "name": "MLRT", "version": release if release != "installed" else "?"})

    ffmpeg = root / "Tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
    # "8.0.1-full_build-www.gyan.dev": the number is the version, the rest is whose build it is.
    build = _first(r"^ffmpeg version (\S+)", _quiet([str(ffmpeg), "-version"])) if ffmpeg.exists() else ""
    found.append({"id": "ffmpeg", "name": "FFmpeg", "version": build.split("-", 1)[0], "detail": build})
    cards = gpus()
    for gpu in cards:
        gpu["rtx"] = gpu.get("brand") == "nvidia" and "RTX" in str(gpu.get("name", "")).upper()
    found.extend(cards)
    return found


def gpus() -> list[dict[str, Any]]:
    """Every video card with its driver: NVIDIA by nvidia-smi, the others as Windows knows them."""
    cards: list[dict[str, Any]] = []
    smi = _quiet(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"], timeout=10)
    nvidia = [line.split(",") for line in smi.splitlines() if line.count(",") == 1 and "NVIDIA" in line.upper()]
    for name, driver in nvidia:
        cards.append({"id": "gpu", "name": name.strip(), "version": driver.strip(), "brand": "nvidia"})
    if sys.platform != "win32":
        return cards
    listed = _quiet(["powershell", "-NoLogo", "-NoProfile", "-Command",
                     "Get-CimInstance Win32_VideoController | Select-Object Name, DriverVersion | ConvertTo-Json -Compress"])
    try:
        controllers = json.loads(listed[listed.find("["):] if listed.lstrip().startswith("[") else listed[listed.find("{"):])
    except ValueError:
        controllers = []
    for controller in controllers if isinstance(controllers, list) else [controllers]:
        if not isinstance(controller, dict):
            continue
        name = str(controller.get("Name") or "").strip()
        lowered = name.lower()
        if not name or "nvidia" in lowered and nvidia or "basic display" in lowered or "remote" in lowered:
            continue
        brand = "nvidia" if "nvidia" in lowered else "intel" if "intel" in lowered else "amd" if "amd" in lowered or "radeon" in lowered else ""
        cards.append({"id": "gpu", "name": name, "version": str(controller.get("DriverVersion") or ""), "brand": brand})
    return cards


def latest_tag(repo: str) -> str:
    """The tag github.com/<repo>/releases/latest sends to; "" when GitHub does not answer."""

    class Stay(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401 - the place is read, not followed
            return None

    opener = urllib.request.build_opener(Stay)
    request = urllib.request.Request(f"https://github.com/{repo}/releases/latest", method="HEAD",
                                     headers={"User-Agent": "Audion-VS-Engine"})
    try:
        opener.open(request, timeout=TIMEOUT)
        return ""
    except urllib.error.HTTPError as answer:
        place = answer.headers.get("Location", "") if answer.code in {301, 302, 303, 307, 308} else ""
    except (urllib.error.URLError, OSError, ValueError):
        return ""
    return place.rstrip("/").rsplit("/tag/", 1)[-1] if "/tag/" in place else ""


def _load(root: Path) -> dict[str, Any]:
    try:
        cache = json.loads((root / CACHE).read_text(encoding="utf-8"))
        return cache if isinstance(cache, dict) else {}
    except (OSError, ValueError):
        return {}


def _plain(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version))


def report(root: Path, latest: bool = False, refresh: bool = False, now: datetime | None = None) -> dict[str, Any]:
    root = Path(root)
    now = now or datetime.now()
    cache = _load(root)
    known: dict[str, str] = dict(cache.get("latest") or {})
    checked = str(cache.get("checked") or "")
    try:
        stale = not checked or now - datetime.fromisoformat(checked) >= FRESH_FOR
    except ValueError:
        stale = True
    if refresh or (latest and stale):
        asked = {name: latest_tag(repo) for name, repo in RELEASES.items()}
        if any(asked.values()):
            known.update({name: tag for name, tag in asked.items() if tag})
            checked = now.isoformat(timespec="seconds")
            (root / CACHE).parent.mkdir(parents=True, exist_ok=True)
            (root / CACHE).write_text(json.dumps({"checked": checked, "latest": known}, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    components = own_versions(root)
    nvidia = next((card.get("version", "") for card in components if card["id"] == "gpu" and card.get("brand") == "nvidia"), "")
    for component in components:
        name = component["id"]
        component["latest"] = known.get(name, "")
        component["source"] = f"https://github.com/{RELEASES[name]}/releases/latest" if name in RELEASES else ""
        if not component["version"]:
            component["state"] = "missing"
        elif name == "plugins":
            have, wanted = (int(part) for part in component["version"].split("/"))
            component["state"] = "fresh" if have == wanted else "old"
        elif name not in RELEASES:
            component["state"] = "own"
        elif name == "ffmpeg" and driver_below_golden(nvidia):
            component["state"], component["driver"] = "limited", nvidia
        elif not component["latest"]:
            component["state"] = "unknown"
        else:
            component["state"] = "old" if _plain(component["version"]) < _plain(component["latest"]) else "fresh"
    return {"components": components, "checked": checked}
