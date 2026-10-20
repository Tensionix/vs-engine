"""Camera RAW in the Source: the engine reads none of it (VapourSynth sees no video track in ProRes RAW and ARRIRAW), and
says so in one line with what opens it - the programs and pages of config\\camera_raw.yaml.

The headers are made here: a MOV box by box, as Atomos lays it out - 'ftyp', 'wide', a large 'mdat', then 'moov' (the
sample of a Sony A7S III through a Ninja V gave "aprh" in its 'stsd'); an MXF KLV by KLV - the partition pack, a fill,
the descriptor with the label of its picture (the ALEXA 35 sample gave 04.01.02.01.02.01.01).
"""
from __future__ import annotations

import json
import struct
import subprocess
from pathlib import Path

import pytest

from system_core.core.camera_raw import camera_raw, raw_of, table

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "runtime" / "python.exe"


def box(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(body), kind) + body


def mov(codec: bytes, mdat: int = 4096, large: bool = False) -> bytes:
    """A MOV of one video track of the codec named: its picture is zeros, its header says the codec where 'stsd' does."""
    entry = box(codec, b"\0" * 70)
    stsd = box(b"stsd", b"\0\0\0\0" + struct.pack(">I", 1) + entry)
    trak = box(b"trak", box(b"mdia", box(b"minf", box(b"stbl", stsd))))
    moov = box(b"moov", box(b"mvhd", b"\0" * 100) + trak)
    picture = b"\0" * mdat
    data = struct.pack(">I4sQ", 1, b"mdat", 16 + len(picture)) + picture if large else box(b"mdat", picture)
    return box(b"ftyp", b"qt  \0\0\0\0qt  ") + box(b"wide", b"") + data + moov


@pytest.mark.parametrize("codec, said", [(b"aprh", "ProRes RAW HQ"), (b"aprn", "ProRes RAW"), (b"apch", ""), (b"avc1", "")])
def test_the_codec_of_a_mov_is_read_from_its_header(codec, said, tmp_path):
    for large in (False, True):
        clip = tmp_path / f"clip_{codec.decode()}_{large}.mov"
        clip.write_bytes(mov(codec, large=large))
        assert camera_raw(clip) == said


def test_only_a_mov_is_looked_into_and_a_broken_one_is_no_raw(tmp_path):
    other = tmp_path / "clip.mkv"
    other.write_bytes(mov(b"aprh"))
    broken = tmp_path / "broken.mov"
    broken.write_bytes(b"\0\0\0\x04moov")
    assert camera_raw(other) == "" and camera_raw(broken) == "" and camera_raw(tmp_path / "none.mov") == ""


def cli(*arguments: str, tmp: Path) -> subprocess.CompletedProcess:
    env = {"AUDION_LOGS": str(tmp / "logs"), "AUDION_REPORT": str(tmp / "report")}
    import os

    return subprocess.run([str(PYTHON), "-X", "utf8", str(ROOT / "system_core" / "cli.py"), *arguments],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
                          env={**os.environ, **env}, cwd=str(ROOT))


def test_a_source_of_prores_raw_alone_is_refused_with_the_reason(tmp_path):
    source = tmp_path / "in"
    source.mkdir()
    (source / "A001.mov").write_bytes(mov(b"aprh"))
    result = tmp_path / "outcome.json"
    done = cli("run", "--operation", "mild_denoise", "--source", str(source), "--target", str(tmp_path / "out"),
               "--result", str(result), tmp=tmp_path)
    assert done.returncode == 2, done.stdout[-2000:]
    assert "[PREFLIGHT] FAIL camera RAW: the engine does not read A001.mov (ProRes RAW HQ)" in done.stdout
    assert "Traceback" not in done.stdout + done.stderr
    assert json.loads(result.read_text(encoding="utf-8"))["outcome"] == "refused"


def test_prores_raw_among_other_videos_is_said_and_failed_by_itself(tmp_path):
    source = tmp_path / "in"
    source.mkdir()
    (source / "A001.mov").write_bytes(mov(b"aprn"))
    (source / "B001.mov").write_bytes(mov(b"avc1"))
    done = cli("run", "--operation", "mild_denoise", "--source", str(source), "--target", str(tmp_path / "out"),
               "--dry-run", tmp=tmp_path)
    assert "[PREFLIGHT] WARN camera RAW: the engine does not read A001.mov (ProRes RAW)" in done.stdout, done.stdout[-2000:]
    assert "[FAIL] A001.mov: ProRes RAW is not read by the engine" in done.stdout
    assert "B001.mov" in done.stdout and "Traceback" not in done.stdout + done.stderr


def test_the_preview_of_prores_raw_says_why(tmp_path):
    clip = tmp_path / "A001.mov"
    clip.write_bytes(mov(b"aprh"))
    done = cli("frame", "--operation", "mild_denoise", "--source", str(clip), "--out", str(tmp_path / "frame"), tmp=tmp_path)
    told = json.loads(done.stdout.strip().splitlines()[-1])
    assert told["ok"] is False and told["error"].startswith("ProRes RAW HQ is not read by the engine")


ARRIRAW = bytes.fromhex("060e2b340401010d0401020102010103")


def klv(key: str, value: bytes) -> bytes:
    return bytes.fromhex(key) + b"\x83" + len(value).to_bytes(3, "big") + value


def mxf(picture_coding: bytes) -> bytes:
    """An MXF header: the partition pack, a fill, a Generic Picture Essence Descriptor naming the coding of its picture,
    then an element of the picture - zeros."""
    descriptor = struct.pack(">HH", 0x3201, 16) + picture_coding
    return (klv("060e2b34020501010d01020101020400", b"\0" * 88) + klv("060e2b34010101020301021001000000", b"\0" * 300)
            + klv("060e2b34025301010d01010101012700", descriptor) + klv("060e2b34010201010d01030115010501", b"\0" * 4096))


def test_arriraw_is_known_by_the_label_of_its_picture_and_refused_with_what_opens_it(tmp_path):
    source = tmp_path / "in"
    source.mkdir()
    (source / "A001.mxf").write_bytes(mxf(ARRIRAW))
    assert raw_of(source / "A001.mxf").kind == "arriraw"
    result = tmp_path / "outcome.json"
    done = cli("run", "--operation", "mild_denoise", "--source", str(source), "--target", str(tmp_path / "out"),
               "--result", str(result), tmp=tmp_path)
    assert done.returncode == 2, done.stdout[-2000:]
    assert "[PREFLIGHT] FAIL camera RAW: the engine does not read A001.mxf (ARRIRAW): open it in ARRI Reference Tool (https://" in done.stdout
    assert "Traceback" not in done.stdout + done.stderr


def test_files_no_run_takes_are_named_with_what_opens_them(tmp_path):
    source = tmp_path / "in"
    source.mkdir()
    (source / "A001.braw").write_bytes(b"\0" * 64)
    (source / "B001.mov").write_bytes(mov(b"avc1"))
    done = cli("run", "--operation", "mild_denoise", "--source", str(source), "--target", str(tmp_path / "out"),
               "--dry-run", tmp=tmp_path)
    assert "[PREFLIGHT] WARN camera RAW: 1 file(s) of Blackmagic RAW are not taken (A001.braw): open it in Blackmagic RAW Player (https://" in done.stdout, done.stdout[-2000:]


def test_the_preview_of_arriraw_says_what_opens_it(tmp_path):
    clip = tmp_path / "A001.mxf"
    clip.write_bytes(mxf(ARRIRAW))
    done = cli("frame", "--operation", "mild_denoise", "--source", str(clip), "--out", str(tmp_path / "frame"), tmp=tmp_path)
    told = json.loads(done.stdout.strip().splitlines()[-1])
    assert told["ok"] is False and told["error"].startswith("ARRIRAW is not read by the engine: open it in ARRI Reference Tool")


def test_the_table_is_the_one_of_media_tools_and_the_readme_holds_its_pages():
    readmes = [(ROOT / "docs" / name).read_text(encoding="utf-8") for name in ("README_RU.md", "README_EN.md")]
    for program in table()["programs"].values():
        assert program["page"].startswith("https://") and all(program["page"] in readme for readme in readmes), program
    media_tools = ROOT.parent / "Audion Media Tools" / "config" / "camera_raw.yaml"
    if media_tools.is_file():
        import yaml

        theirs = yaml.safe_load(media_tools.read_text(encoding="utf-8"))
        assert theirs["programs"] == table()["programs"] and theirs["kinds"] == table()["kinds"]
