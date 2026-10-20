"""What the neural presets need of the machine: an NVIDIA RTX card, and vs-mlrt installed into the engine.

The owner, 18.10.2026: "мы избавляемся от ДВУХ приложений. Теперь это VS Engine - система определяет наличие RTX и
добавляет кнопку установки MLRT." Until 3.0.0 the full edition carried MLRT and Lite did not; now one program shows the
installation of MLRT (SETUP and the question at the start, the card of a neural preset) when it finds an RTX card, and the neural presets
when it finds the card or MLRT already installed - MLRT installed on a machine with RTX runs on another after the folder
moves: the preset picks TensorRT, DirectML or the CPU itself.
"""
from __future__ import annotations

import os
from pathlib import Path

# A name of a card for a check of the window and of the console on a machine without one; "0" - no card where there is one.
RTX_OVERRIDE = "AUDION_VS_RTX"
MARKER = Path("system_core") / "vapoursynth" / ".audion-mlrt.marker"


def rtx() -> str:
    """The name of the first NVIDIA RTX card nvidia-smi names; "" - none. Only nvidia-smi is asked: without the driver
    that brings it TensorRT does not run either."""
    named = os.environ.get(RTX_OVERRIDE, "").strip()
    if named:
        return "" if named == "0" else named
    from .components import _quiet

    for line in _quiet(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], timeout=10).splitlines():
        name = line.strip()
        if "NVIDIA" in name.upper() and "RTX" in name.upper():
            return name
    return ""


def mlrt(root: Path) -> str:
    """The release of vs-mlrt installed into the engine ("v15.16"); "" - not installed. install\\Install-VS-mlrt.ps1
    writes its marker last, after its own check of the backends, so a broken installation has none."""
    try:
        first = (Path(root) / MARKER).read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return ""
    return (first[0].strip() if first else "") or "installed"


def neural_shown(root: Path, card: str | None = None) -> bool:
    """The neural presets are offered: an RTX card is here, or MLRT already is."""
    return bool(rtx() if card is None else card) or bool(mlrt(root))
