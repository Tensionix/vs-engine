"""The console command vs_cli.cmd: its answers, its refusals, its codes, its outcome file, its layout and texts.

Nothing here starts vspipe: a wrong call is refused before it, a dry run says its commands. The runs of the engine are
in tests\\test_run_live.py.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from system_core.core import form_pages, operation_model as model, program_map, window_layout
from system_core.core.manifest import load_manifest, manifest_path
from system_core.engine import encoding, runner
from system_core.services.vs_service import profiles
from system_core.core.preflight import profile_problem

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = load_manifest(manifest_path(ROOT))
PYTHON = ROOT / "runtime" / "python.exe"


def cli(*arguments: str, tmp: Path, timeout: int = 120, rtx: str = "") -> subprocess.CompletedProcess:
    env = {**os.environ, "AUDION_LOGS": str(tmp / "logs"), "AUDION_REPORT": str(tmp / "report"), "PYTHONIOENCODING": "utf-8"}
    if rtx:
        env["AUDION_VS_RTX"] = rtx
    return subprocess.run([str(PYTHON), "-X", "utf8", str(ROOT / "system_core" / "cli.py"), *arguments],
                          capture_output=True, text=True, encoding="utf-8", env=env, timeout=timeout)


def test_describe_tells_the_program_the_operations_and_the_layout(tmp_path):
    done = cli("describe", tmp=tmp_path)
    assert done.returncode == 0
    told = json.loads(done.stdout)
    # One program since 18.10.2026: no edition, the neural part by what the machine has.
    assert told["tool"] == {"id": "audion_vs_engine", "name": "Audion VS Engine"}
    assert set(told["machine"]) == {"rtx", "mlrt", "neural"}
    assert set(told["operations"]) == {node.id for node in model.all_nodes(MANIFEST) if node.service and not node.children}
    assert [section["id"] for section in told["layout"]["sections"]] == ["precision", "film_looks", "retro", "restoration",
                                                                         "profiles"]
    field = next(item for item in told["operations"]["mild_denoise"]["fields"] if item["id"] == "encode_backend")
    assert field["visible_if"] == {"encode_family": ["x264", "x265"]}


@pytest.mark.parametrize("arguments, words", [
    (["--operation", "nope"], "no operation"),
    (["--operation", "mild_denoise", "--set", "strength=huge"], "no such choice"),
    (["--operation", "shadow_denoise_sota", "--set", "sigma=9"], "is outside 1.0..4.0"),
    (["--operation", "deband_safe", "--set", "range=12.5"], "a whole number"),
    (["--operation", "mild_denoise", "--set", "nothing=1"], "has no field"),
    (["--operation", "mild_denoise", "--set", "strength"], "name=value"),
    (["--operation", "mild_denoise", "--encoder", "h264_crf18"], "no encoder"),
    (["--operation", "doctor", "--dry-run"], "no dry run"),
    (["--operation", "profile_save", "--set", "profile_preset=film_35mm"], "Fill in"),
    (["--operation", "mild_denoise", "--result", "x.txt"], ".json"),
])
def test_a_wrong_call_is_refused_with_code_2_and_runs_nothing(arguments, words, tmp_path):
    done = cli("run", *arguments, tmp=tmp_path)
    assert done.returncode == 2
    assert words in done.stderr
    assert not (tmp_path / "report").exists()


def test_a_refused_run_writes_its_outcome_too(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = tmp_path / "outcome.json"
    done = cli("run", "--operation", "mild_denoise", "--source", str(empty), "--target", str(tmp_path / "out"),
               "--result", str(result), tmp=tmp_path)
    assert done.returncode == 2
    assert "[PREFLIGHT] FAIL Source" in done.stdout
    told = json.loads(result.read_text(encoding="utf-8"))
    assert told["outcome"] == "refused" and told["processed"] == 0 and told["log_file"]
    assert not (tmp_path / "out").exists()


def test_the_layout_places_every_operation_once():
    assert window_layout.problems(window_layout.load(ROOT / "config"), MANIFEST) == []


def test_every_text_has_both_languages():
    assert program_map.build(ROOT, MANIFEST)["missing"] == []


def test_every_choice_field_is_a_row_of_switches_never_a_list():
    for node in model.all_nodes(MANIFEST):
        for field in node.fields:
            assert model.field_kind(field) not in model.LISTS, (node.id, model.field_id(field))


def test_every_profile_names_a_preset_its_fields_and_an_encoder_the_engine_has():
    for name, profile in profiles(ROOT).items():
        assert profile_problem(ROOT, profile) == "", name
        assert profile["encoder"] in runner.ENCODERS, name


@pytest.mark.parametrize("encoder", runner.list_encoders())
def test_the_cards_give_back_every_encoder(encoder):
    for container in ("mp4", "mkv"):
        cards = encoding.cards_of(encoder, container)
        assert encoding.encoder_from_cards(cards) == encoder
        suffix = encoding.extension(encoder, container)
        assert suffix == (".mxf" if encoder.endswith("_mxf") else ".mov" if encoder.startswith(("prores", "dnxhr"))
                          else "." + container)


def test_the_machine_is_one_for_every_page_and_a_profile_sets_the_cards():
    pages = form_pages.Pages(ROOT, MANIFEST)
    pages.open("a", "mild_denoise", None)
    pages.open("b", "film_35mm", None)
    told = pages.click("a", "choose", "encode_family", "prores")
    assert told["values"]["encode_family"] == "prores"
    assert "encode_backend" not in told["shown"] and "prores_profile" in told["shown"]
    assert pages.state("b")["values"]["encode_family"] == "prores"
    pages.open("p", "profile_run", None)
    told = pages.click("p", "choose", "profile", "vhs_dreamy")
    assert encoding.encoder_from_cards(told["values"]) == profiles(ROOT)["vhs_dreamy"]["encoder"]
    assert pages.state("a")["values"]["encode_family"] == "x264"


def test_a_hardware_encoder_this_machine_did_not_pass_is_off_with_the_reason(tmp_path):
    node = model.find_node(MANIFEST, "mild_denoise")
    form = model.Form(node, ROOT)
    form.cache = {"encoders": {"h264_nvenc": {"status": "MISS", "detail": "Cannot load nvcuda.dll"},
                               "hevc_nvenc": {"status": "OK"}}}
    form.open().fill({"encode_backend": "nvenc"})
    assert form.values["encode_backend"] == "cpu"
    assert "nvcuda" in form.off_reasons()["encode_backend"]["nvenc"]
    form.click("choose", "encode_family", "x265")
    form.click("choose", "encode_backend", "nvenc")
    assert form.values["encode_backend"] == "nvenc"


def test_the_command_file_keeps_crlf_and_calls_the_command_by_its_path():
    raw = (ROOT / "vs_cli.cmd").read_bytes()
    assert raw.count(b"\r\n") == raw.count(b"\n")
    assert b'"%BASE_DIR%\\system_core\\cli.py"' in raw


def test_the_menus_call_the_console_command_and_not_main_py():
    menus = [*(ROOT / "cli").glob("launcher_*.cmd"), ROOT / "launcher_project.cmd", ROOT / "launcher_project_ru.cmd"]
    for menu in menus:
        text = menu.read_bytes().decode("utf-8")
        assert "main.py" not in text, menu.name
        assert "vs_cli.cmd" in text, menu.name


def test_processing_is_in_sight_only_where_it_moves_something_and_says_what():
    told = model.describe(MANIFEST)["operations"]

    def accel(operation):
        return next(field for field in told[operation]["fields"] if field["id"] == "vs_accel")

    assert accel("film_35mm")["hidden"] is True
    assert accel("shadow_denoise_sota")["hidden"] is False and "BM3D" in accel("shadow_denoise_sota")["tooltip"]
    neural = accel("dpir_denoise")
    assert neural["hidden"] is False and "TensorRT" in neural["tooltip"] and "TensorRT" in neural["tooltip_ru"]
    assert "ONNX Runtime" in next(option for option in neural["options"] if option["value"] == "cpu")["tooltip"]
    assert accel("profile_run")["hidden"] is False
    page = form_pages.Pages(ROOT, MANIFEST)
    shown = page.handle({"do": "open", "page": "film", "operation": "film_35mm"})["shown"]
    assert "vs_accel" not in shown
    assert "vs_accel" in page.handle({"do": "open", "page": "sota", "operation": "shadow_denoise_sota"})["shown"]


def test_the_neural_presets_say_they_need_mlrt_and_the_others_do_not():
    told = model.describe(MANIFEST)["operations"]
    neural = {name for name, node in told.items() if node.get("needs") == "mlrt"}
    assert neural == {"dpir_denoise", "vsmlrt_realesrgan_2x", "soft_hd_rebuild_2x"}
    assert all(told[name]["accel"] == "mlrt" for name in neural)


def test_an_rtx_card_offers_the_neural_part(tmp_path):
    told = json.loads(cli("describe", tmp=tmp_path, rtx="NVIDIA GeForce RTX 5070").stdout)
    assert told["machine"]["rtx"] == "NVIDIA GeForce RTX 5070" and told["machine"]["neural"] is True
    assert "install_mlrt" in told["layout"]["setup"] and "install_mlrt" in told["plans"]


def test_a_neural_preset_without_mlrt_is_refused_with_the_reason(tmp_path):
    if (ROOT / "system_core" / "vapoursynth" / ".audion-mlrt.marker").exists():
        pytest.skip("MLRT is installed here")
    done = cli("run", "--operation", "dpir_denoise", "--dry-run", tmp=tmp_path)
    assert done.returncode == 2
    assert "[PREFLIGHT] FAIL MLRT: not installed" in done.stdout


def test_mlrt_is_not_installed_without_an_rtx_card(tmp_path):
    done = cli("run", "--operation", "install_mlrt", tmp=tmp_path, rtx="0")
    assert done.returncode == 2
    assert "[PREFLIGHT] FAIL NVIDIA RTX: not found" in done.stdout


def test_the_queue_names_camera_raw_once_for_the_window_and_in_its_language(tmp_path):
    source, target = tmp_path / "in", tmp_path / "out"
    source.mkdir()
    target.mkdir()
    (source / "clip.braw").write_bytes(b"\0" * 64)
    pages = form_pages.Pages(ROOT, MANIFEST, language="ru")
    told = pages.folders(str(source), str(target))["queue"]
    assert [one["name"] for one in told["raw"]] == ["Blackmagic RAW"]
    assert told["raw"][0]["file"].endswith("clip.braw") and told["raw"][0]["hint"].startswith("откройте в ")
    assert told["files"] == [] and told["count"] == 0
