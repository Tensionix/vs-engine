"""The sound of a result: copied where the container takes it, made anew where it does not."""
from __future__ import annotations

from pathlib import Path

import pytest

from system_core.engine import runner


@pytest.mark.parametrize("encoder, suffix, source, args", [
    ("prores_422_mxf", ".mxf", "aac", ["-c:a", "pcm_s24le", "-ar", "48000"]),
    ("prores_422_mxf", ".mxf", "pcm_s24le", ["-c:a", "pcm_s24le", "-ar", "48000"]),
    ("prores_422", ".mov", "aac", ["-c:a", "copy"]),
    ("h264_crf17", ".mp4", "pcm_s24le", ["-c:a", "aac", "-b:a", "384k"]),
    ("h264_crf17", ".mp4", "aac", ["-c:a", "copy"]),
])
def test_the_sound_goes_as_the_container_takes_it(monkeypatch, encoder, suffix, source, args):
    monkeypatch.setattr(runner, "_source_media_codecs", lambda _path: {"video": "h264", "audio": source, "format": "mov"})
    told, _policy = runner._audio_output_args(Path("in.mp4"), Path("out" + suffix), encoder, True)
    assert told == args
