"""The Source of a run: one file, or a folder with every video under it, the tree kept.

Until 3.0.0 the window took the first video of input\\ and showed no name of it (the inventory, 3.4), the console took a
file and nothing else, and only a profile went over a folder (apply-profile-batch). Now every operation takes a file or a
folder, as every window of the family does.
"""
from __future__ import annotations

import os
from pathlib import Path

# The videos a run takes (main.py _VIDEO_EXTS of 2.0.3: mainstream, camcorder and broadcast, legacy and web, phones).
VIDEO_EXTENSIONS = frozenset({
    ".mp4", ".mov", ".mkv", ".m4v", ".avi", ".webm", ".mxf",
    ".mts", ".m2ts", ".ts", ".vob",
    ".3gp", ".ogv", ".flv", ".wmv", ".asf",
    ".lrv",
})
# The kinds a caller narrows the run to (`--only mov,mxf`).
ONLY_ENV = "AUDION_VS_ONLY_FORMATS"
# A result while it is written: "<name>.writing-<pid>-<token>.<ext>". Never a source.
DRAFT_MARK = ".writing-"


def only_kinds() -> frozenset[str]:
    given = os.environ.get(ONLY_ENV, "")
    return frozenset("." + part.strip().lower().lstrip(".") for part in given.split(",") if part.strip())


def _inside(path: Path, folder: Path) -> bool:
    try:
        Path(os.path.realpath(path)).relative_to(Path(os.path.realpath(folder)))
        return True
    except ValueError:
        return False


def is_video(path: Path) -> bool:
    kinds = only_kinds()
    suffix = path.suffix.lower()
    return suffix in VIDEO_EXTENSIONS and (not kinds or suffix in kinds) and DRAFT_MARK not in path.name


def source_files(source: Path, target: Path | None = None) -> list[Path]:
    """The videos of the Source in the order they are taken: a file is itself; a folder - every video under it, by path,
    without what lies in the Target (a Target inside the Source would feed a run its own results)."""
    source = Path(source)
    if source.is_file():
        return [source] if is_video(source) else []
    if not source.is_dir():
        return []
    found: list[Path] = []
    for folder, names, files in os.walk(source):
        here = Path(folder)
        if target is not None and _inside(here, target):
            names[:] = []
            continue
        names[:] = sorted(name for name in names if not name.startswith("._"))
        found += [here / name for name in sorted(files) if is_video(here / name)]
    return found


def relative_folder(file: Path, source: Path) -> Path:
    """Where under the Target the result of a file goes: the folder of the file inside the Source, nothing for a file."""
    source = Path(source)
    if source.is_file():
        return Path()
    try:
        return file.parent.relative_to(source)
    except ValueError:
        return Path()
