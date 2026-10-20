"""The encoder of a run, put together from the cards of the window: family, backend, quality and container.

Until 3.0.0 this lived only in the window on NiceGUI (app.py: encoder_parts, encoder_from_parts, prores_encoder_name,
encoder_extension): the console took a finished name of runner.ENCODERS and nothing else. Now the console command and
the window hand the engine the same cards and the engine makes the name - one copy of the rule. The logic is the one of
the window, kept to its record (tests\\former_window_commands.json): a card the family does not show is ignored, a name
that is not in runner.ENCODERS falls back as the window fell back.
"""
from __future__ import annotations

from . import runner

FAMILIES = ("x264", "x265", "prores", "dnxhr")
BACKENDS = ("cpu", "nvenc", "qsv", "amf")
QUALITIES = ("14", "17", "21")
PRORES_PROFILES = ("lt", "422", "hq")
PRORES_WRAPPERS = ("mov", "mxf")
DNXHR_PROFILES = ("hq", "hqx", "lb", "sq")

# The cards and their defaults: the encoder of the window before a click - h264_crf14 (runner.DEFAULT_ENCODER).
DEFAULTS = {
    "encode_family": "x264",
    "encode_backend": "cpu",
    "encode_quality": "14",
    "encode_container": "mp4",
    "prores_profile": "lt",
    "prores_wrapper": "mov",
    "dnxhr_profile": "hq",
}

# Which card a family shows (the window drew the same: x.264 / x.265 - backend, quality, container; ProRes - profile and
# wrapper; DNxHR - profile). The window of 3.0.0 reads this from describe and draws nothing else.
SHOWN = {
    "encode_backend": ("x264", "x265"),
    "encode_quality": ("x264", "x265"),
    "encode_container": ("x264", "x265"),
    "prores_profile": ("prores",),
    "prores_wrapper": ("prores",),
    "dnxhr_profile": ("dnxhr",),
}


def encoder_from_cards(cards: dict[str, str]) -> str:
    """The name of runner.ENCODERS the cards make (app.py encoder_from_parts, unchanged)."""
    family = cards.get("encode_family") if cards.get("encode_family") in FAMILIES else "x264"
    if family == "prores":
        profile = cards.get("prores_profile") if cards.get("prores_profile") in PRORES_PROFILES else "lt"
        wrapper = cards.get("prores_wrapper") if cards.get("prores_wrapper") in PRORES_WRAPPERS else "mov"
        base = {"lt": "prores_lt", "422": "prores_422", "hq": "prores_422hq"}[profile]
        candidate = f"{base}_mxf" if wrapper == "mxf" else base
        return candidate if candidate in runner.ENCODERS else base
    if family == "dnxhr":
        profile = cards.get("dnxhr_profile") if cards.get("dnxhr_profile") in DNXHR_PROFILES else "hq"
        candidate = f"dnxhr_{profile}"
        return candidate if candidate in runner.ENCODERS else "dnxhr_hq"
    codec = "h265" if family == "x265" else "h264"
    backend = cards.get("encode_backend") if cards.get("encode_backend") in BACKENDS else "cpu"
    quality = cards.get("encode_quality") if cards.get("encode_quality") in QUALITIES else "17"
    candidate = f"{codec}_crf{quality}" if backend == "cpu" else f"{codec}_{backend}_q{quality}"
    return candidate if candidate in runner.ENCODERS else runner.DEFAULT_ENCODER


def cards_of(encoder: str, container: str = "mp4") -> dict[str, str]:
    """The cards a name of runner.ENCODERS stands for (app.py encoder_parts): a profile's encoder shown on the cards."""
    name = str(encoder or runner.DEFAULT_ENCODER)
    cards = dict(DEFAULTS, encode_quality="17", encode_container=container)
    if name.startswith("prores"):
        cards.update(encode_family="prores", prores_wrapper="mxf" if name.endswith("_mxf") else "mov",
                     prores_profile="hq" if "422hq" in name else "422" if "422" in name else "lt")
        return cards
    if name.startswith("dnxhr_"):
        profile = name.removeprefix("dnxhr_")
        cards.update(encode_family="dnxhr", dnxhr_profile=profile if profile in DNXHR_PROFILES else "hq")
        return cards
    for codec, family in (("h264", "x264"), ("h265", "x265")):
        if name.startswith(f"{codec}_crf"):
            cards.update(encode_family=family, encode_backend="cpu", encode_quality=name.rsplit("crf", 1)[-1])
            return cards
        for backend in ("nvenc", "qsv", "amf"):
            if name.startswith(f"{codec}_{backend}_q"):
                cards.update(encode_family=family, encode_backend=backend, encode_quality=name.rsplit("_q", 1)[-1])
                return cards
    return cards


def extension(encoder: str, container: str = "mp4") -> str:
    """The extension of the file an encoder writes (one copy: main.py _encoder_extension and app.py encoder_extension
    were two)."""
    if encoder.startswith(("h264_", "h265_")):
        return ".mkv" if container == "mkv" else ".mp4"
    if encoder.endswith("_mxf"):
        return ".mxf"
    if encoder.startswith(("prores", "dnxhr")):
        return ".mov"
    return ".mp4"
