"""What an installer of SETUP would download - its files, their source and size - with nothing fetched: `vs_cli.cmd plan`.

The window names it before it runs the installer. The plan asks the same places the scripts of install\\ ask, the same way
(the GitHub API of the releases, PyPI, python.org, gyan.dev), and fetches only their answers and the sizes of the files
(HEAD). A file whose size the source does not say has `size` null. A token in GITHUB_TOKEN lifts the GitHub limit, as for
the scripts.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

PLANS = {"install_vapoursynth", "install_vs_plugins", "install_ffmpeg", "install_mlrt", "remove_vapoursynth"}
AGENT = "Audion-VS-Engine-Lite"
TIMEOUT = 20


def _headers(github: bool = False) -> dict[str, str]:
    headers = {"User-Agent": AGENT}
    if github and os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    return headers


def _json(url: str) -> Any:
    request = urllib.request.Request(url, headers=_headers("api.github.com" in url))
    with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:
        return json.loads(answer.read().decode("utf-8"))


def _size(url: str) -> int | None:
    """The size of a file by its HEAD; None when the source does not say."""
    try:
        request = urllib.request.Request(url, method="HEAD", headers=_headers())
        with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:
            length = answer.headers.get("Content-Length")
            return int(length) if length and length.isdigit() else None
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _file(name: str, url: str, size: int | None, source: str, note: str = "") -> dict[str, Any]:
    """A file of a plan: its name, where it comes from, its size (None - not said) and a word on why this one."""
    told = {"name": name, "url": url, "size": size, "source": source}
    if note:
        told["note"] = note
    return told


def _vapoursynth() -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    releases = sorted(_json("https://api.github.com/repos/vapoursynth/vapoursynth/releases?per_page=20"),
                      key=lambda release: str(release.get("published_at") or ""), reverse=True)
    for release in releases:
        if release.get("prerelease") or release.get("draft"):
            continue
        asset = next((item for item in release.get("assets") or []
                      if re.match(r"^VapourSynth64-Portable-.+\.zip$", str(item.get("name") or ""))), None)
        if asset:
            files.append(_file(asset["name"], asset["browser_download_url"], asset.get("size"),
                               "github.com/vapoursynth/vapoursynth", f"release {release.get('tag_name')}"))
            break
    found = None
    for patch in range(0, 31):
        url = f"https://www.python.org/ftp/python/3.12.{patch}/python-3.12.{patch}-embed-amd64.zip"
        size = _size(url)
        if size is None and found is not None:
            break
        if size is not None:
            found = (url, size, patch)
    if found:
        files.append(_file(Path(found[0]).name, found[0], found[1], "python.org", f"Python 3.12.{found[2]}"))
    # The core itself is the wheel inside the portable archive: pip installs it from there, nothing more is fetched.
    files.append(_file("get-pip.py", "https://bootstrap.pypa.io/get-pip.py", _size("https://bootstrap.pypa.io/get-pip.py"),
                       "bootstrap.pypa.io"))
    return files


def _wheel(package: str) -> dict[str, Any]:
    name, _, version = package.partition("==")
    data = _json(f"https://pypi.org/pypi/{name}/{version}/json" if version else f"https://pypi.org/pypi/{name}/json")
    urls = data.get("urls") or []
    pick = (next((item for item in urls if str(item.get("filename", "")).endswith("win_amd64.whl")), None)
            or next((item for item in urls if str(item.get("filename", "")).endswith("-none-any.whl")), None)
            or (urls[0] if urls else None))
    if pick is None:
        return _file(package, f"https://pypi.org/project/{name}/", None, "pypi.org")
    return _file(pick["filename"], pick["url"], pick.get("size"), "pypi.org", f"{name} {data['info']['version']}")


def _plugins(root: Path) -> list[dict[str, Any]]:
    told = json.loads((root / "install" / "vs_plugins.json").read_text(encoding="utf-8"))
    files: list[dict[str, Any]] = []
    for item in told.get("python_packages") or []:
        try:
            files.append(_wheel(str(item["package"])))
        except (urllib.error.URLError, OSError, ValueError, KeyError) as error:
            files.append(_file(str(item["package"]), "", None, "pypi.org", f"not asked: {error}"))
    for item in told.get("github_assets") or []:
        repo = str(item["repo"])
        try:
            releases = sorted(_json(f"https://api.github.com/repos/{repo}/releases?per_page=20"),
                              key=lambda release: str(release.get("published_at") or ""), reverse=True)
            asset, tag = None, ""
            for release in releases:
                asset = next((entry for entry in release.get("assets") or []
                              if re.match(str(item["asset"]), str(entry.get("name") or ""))), None)
                if asset:
                    tag = str(release.get("tag_name") or "")
                    break
            files.append(_file(asset["name"], asset["browser_download_url"], asset.get("size"), f"github.com/{repo}",
                               f"release {tag}; the newest the core loads, an older one when it does not")
                         if asset else _file(str(item["id"]), f"https://github.com/{repo}/releases", None, f"github.com/{repo}"))
        except (urllib.error.URLError, OSError, ValueError) as error:
            files.append(_file(str(item["id"]), f"https://github.com/{repo}/releases", None, f"github.com/{repo}",
                               f"not asked: {error}"))
    for item in told.get("vsrepo_packages") or []:
        files.append(_file(str(item["id"]), "https://github.com/vapoursynth/vsrepo", None, "vsrepo",
                           "by vsrepo from its catalogue; the size is the catalogue's"))
    return files


def _nvidia_driver() -> str:
    smi = shutil.which("nvidia-smi.exe") or str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "nvidia-smi.exe")
    if not Path(smi).exists():
        return ""
    try:
        out = subprocess.run([smi, "--query-gpu=driver_version", "--format=csv,noheader"], capture_output=True, text=True,
                             timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    found = re.search(r"(\d+(?:\.\d+)+)", out)
    return found[1] if found else ""


def _newest_gyan() -> str:
    """The newest Gyan stable, never below the floor: gyan.dev says it, else the place GitHub sends to - no API limit."""
    from .components import FFMPEG_FLOOR, _plain, latest_tag

    found = ""
    try:
        request = urllib.request.Request("https://www.gyan.dev/ffmpeg/builds/release-version", headers=_headers())
        with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:
            text = answer.read().decode("utf-8", errors="replace").strip()
        found = text if re.fullmatch(r"\d+(?:\.\d+)+", text) else ""
    except (urllib.error.URLError, OSError, ValueError):
        found = ""
    found = found or latest_tag("GyanD/codexffmpeg")
    return found if found and _plain(found) >= _plain(FFMPEG_FLOOR) else FFMPEG_FLOOR


def _ffmpeg() -> list[dict[str, Any]]:
    """The build install\\Install-Portable-FFmpeg-Gyan.ps1 takes by the NVIDIA driver (core\\components.py, the rule)."""
    from .components import FFMPEG_FLOOR, ffmpeg_for_driver, ffmpeg_warning

    driver = _nvidia_driver()
    older = ffmpeg_for_driver(driver)
    if older:
        version, why = older, f"NVIDIA driver {driver}: NVENC API {'11.1' if older == '7.1' else '13.0'}"
    else:
        version = _newest_gyan()
        why = (f"NVIDIA driver {driver}: the newest stable" if driver else "no NVIDIA card: the newest stable") + f", {FFMPEG_FLOOR} at least"
    name = f"ffmpeg-{version}-full_build.7z"
    url = f"https://www.gyan.dev/ffmpeg/builds/packages/{name}"
    note = f"Gyan {version}, {why}; github.com/GyanD/codexffmpeg when gyan.dev fails"
    if older:
        note += ". " + ffmpeg_warning(driver, version)
    return [_file(name, url, _size(url), "gyan.dev", note)]


def _mlrt() -> list[dict[str, Any]]:
    """The assets install\\Install-VS-mlrt.ps1 takes of the newest vs-mlrt release: the TensorRT bundle in its volumes,
    the scripts and the models."""
    release = _json("https://api.github.com/repos/AmusementClub/vs-mlrt/releases/latest")
    tag = str(release.get("tag_name") or "")
    files = []
    for pattern, what in (("vsmlrt-windows-x64-tensorrt", "TensorRT, ONNX Runtime and their runtimes"),
                          ("scripts", "vsmlrt.py"), ("models", "the ONNX models")):
        for asset in sorted(release.get("assets") or [], key=lambda item: str(item.get("name"))):
            name = str(asset.get("name") or "")
            if name.startswith(pattern) and ".7z" in name:
                files.append(_file(name, str(asset.get("browser_download_url") or ""), asset.get("size"),
                                   "github.com/AmusementClub/vs-mlrt", f"release {tag}: {what}"))
    return files


def _folder_size(folder: Path) -> int:
    total = 0
    for base, _names, files in os.walk(folder):
        for name in files:
            try:
                total += (Path(base) / name).stat().st_size
            except OSError:
                pass
    return total


def plan(root: Path, operation: str) -> dict[str, Any]:
    root = Path(root)
    if operation == "remove_vapoursynth":
        folder = root / "system_core" / "vapoursynth"
        return {"ok": True, "operation": operation, "files": [], "downloads": 0, "notes": [],
                "removes": {"folder": str(folder), "exists": folder.exists(),
                            "size": _folder_size(folder) if folder.exists() else 0, "to": "Recycle Bin"}}
    try:
        files = {"install_vapoursynth": _vapoursynth, "install_ffmpeg": _ffmpeg,
                 "install_mlrt": _mlrt}.get(operation, lambda: _plugins(root))()
    except (urllib.error.URLError, OSError, ValueError) as error:
        return {"ok": False, "operation": operation, "files": [], "error": f"{type(error).__name__}: {error}"}
    sizes = [item["size"] for item in files if isinstance(item.get("size"), int)]
    # Why this release - the words of a file that say it (the FFmpeg of the driver, the release of VapourSynth) - for the
    # question the window asks before the download.
    notes = [f"{item['name']}: {item['note']}" for item in files if item.get("note") and operation != "install_vs_plugins"]
    return {"ok": True, "operation": operation, "files": files, "downloads": len(files), "known_size": sum(sizes),
            "unknown_sizes": len(files) - len(sizes), "notes": notes}
