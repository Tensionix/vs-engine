"""The records of the window on NiceGUI (2.0.3): what it handed to the engine, and its texts. Taken once, never rewritten.

    <reference>\\runtime\\python.exe -X utf8 tests\\capture_former_window.py <REFERENCE_ROOT> <OUT_DIR>

The reference is the program as it was (E:\\TOOLS\\Audion VS Engine NiceGUI, ...Lite NiceGUI) - only read: its system_core
and config are copied to a temporary folder first, because importing the window writes config\\gui_settings.yaml,
config\\path_history.json and config\\profiles\\*.json (the inventory, 3.14). The engine is not started: the window
builds every command by pure functions of its state (build_run_preset_command, build_apply_profile_command,
build_batch_command, encoder_from_parts), and those are called with the state a person would have set.

former_window_commands.json - for every state: the clicks it stands for (palette, preset, the parameter changed, the
encoder cards, CPU|CUDA, the decoder, the batch ticks) and the argv the window would start, with the temporary root
written <ROOT>. Every preset: its defaults, every choice of every choice parameter, both ends of every range; one preset
with every encoder the cards can give, CPU|CUDA and the four decoders; every profile alone and in a batch with every
combination of the three ticks.

former_window_map.json - the texts the window showed and where they lived: the labels of parameters and choices, the
friendly names of presets, the dictionary TEXT, the labels of the cards, the summary and doc of every preset.
"""
import itertools
import json
import shutil
import sys
import tempfile
from pathlib import Path

reference, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
temp = Path(tempfile.mkdtemp(prefix="vs-engine-former-"))
try:
    for part in ("system_core", "config"):
        shutil.copytree(reference / part, temp / part,
                        ignore=shutil.ignore_patterns("vapoursynth", "powershell", "7zip", "fzf.exe", "__pycache__", "license"))
    for folder in ("input", "output", "logs", "report"):
        (temp / folder).mkdir(exist_ok=True)
    clip = temp / "input" / "clip.mov"
    clip.write_bytes(b"")
    sys.path.insert(0, str(temp))

    from system_core.ui_nicegui import app as w  # noqa: E402  (the window of the copy)
    from system_core.engine import presets as P  # noqa: E402
    from system_core.engine import runner as R  # noqa: E402

    root_text = str(temp)

    def norm(argv):
        return [a.replace(root_text, "<ROOT>") for a in argv]

    base = dict(w.state)
    records = []

    def capture(kind, clicks, setup):
        w.state.clear()
        w.state.update(json.loads(json.dumps({k: v for k, v in base.items() if k not in ("pins",)}, default=str)))
        w.state["pins"] = set()
        w.state["params_by_preset"] = {}
        w.state["input_path"] = str(clip)
        w.state["source_path"] = str(temp / "input")
        w.state["destination_path"] = str(temp / "output")
        w.state["path_cache"] = {"source_path": str(temp / "input"), "output_path": str(temp / "output")}
        setup()
        try:
            builder = {"preset": w.build_run_preset_command, "profile": w.build_apply_profile_command,
                       "batch": w.build_batch_command}[kind]
            argv = norm(builder())
            records.append({"kind": kind, "clicks": clicks, "argv": argv})
        except Exception as exc:  # what the window refused, it refused with this message
            records.append({"kind": kind, "clicks": clicks, "refused": str(exc).replace(root_text, "<ROOT>")})

    def preset_state(spec, param=None, value=None, **extra):
        def setup():
            w.state["palette"], w.state["preset"] = spec.palette, spec.name
            w.ensure_current_params()
            if param is not None:
                w.set_param(param, value)
            w.state.update(extra)
        return setup

    specs = list(P.list_all())
    for spec in specs:
        capture("preset", {"palette": spec.palette, "preset": spec.name}, preset_state(spec))
        for key, schema in spec.params.items():
            if key == "use_cuda":
                continue
            values = []
            if schema.get("type") == "choice":
                values = list(schema.get("choices") or [])
            elif schema.get("range"):
                values = list(schema["range"])
            for value in values:
                capture("preset", {"palette": spec.palette, "preset": spec.name, "param": key, "value": value},
                        preset_state(spec, key, value))

    first = specs[0]
    families = list(w.ENCODER_FAMILY_LABELS)
    for family, backend, quality, mux, pp, pc, dp in itertools.product(
            families, list(w.ENCODER_BACKEND_LABELS), list(w.ENCODER_QUALITY_LABELS), list(w.MUX_CONTAINER_LABELS),
            list(w.PRORES_PROFILE_LABELS), list(w.PRORES_CONTAINER_LABELS), list(w.DNXHR_PROFILE_LABELS)):
        # Only the cards a family shows: x264/x265 - backend, quality, container; ProRes - profile, wrapper; DNxHR - profile.
        if family in ("x264", "x265") and (pp, pc, dp) != ("lt", "mov", "hq"):
            continue
        if family == "prores" and (backend, quality, mux, dp) != ("cpu", "17", "mp4", "hq"):
            continue
        if family == "dnxhr" and (backend, quality, mux, pp, pc) != ("cpu", "17", "mp4", "lt", "mov"):
            continue
        encoder = w.encoder_from_parts(family, backend, quality, pp, pc, dp)
        cards = {"family": family, "backend": backend, "quality": quality, "mux_container": mux,
                 "prores_profile": pp, "prores_container": pc, "dnxhr_profile": dp}
        capture("preset", {"palette": first.palette, "preset": first.name, "cards": cards, "encoder": encoder},
                preset_state(first, encoder=encoder, mux_container=mux, prores_profile=pp, prores_container=pc, dnxhr_profile=dp))
    for accel, decode in itertools.product(list(w.VS_ACCEL_LABELS), list(w.DECODE_BACKEND_LABELS)):
        capture("preset", {"palette": first.palette, "preset": first.name, "vs_accel": accel, "decode_backend": decode},
                preset_state(first, vs_accel=accel, decode_backend=decode))

    profiles = w.profile_names()
    for name in profiles:
        def setup(name=name):
            w.state["profile"] = name
            w.state["encoder"] = w.profile_encoder(name)  # what choosing the profile did to the cards
        capture("profile", {"profile": name}, setup)
        for recursive, mirror, overwrite in itertools.product((True, False), repeat=3):
            def setup(name=name, recursive=recursive, mirror=mirror, overwrite=overwrite):
                w.state["profile"] = name
                w.state["encoder"] = w.profile_encoder(name)
                w.state.update(recursive=recursive, mirror_tree=mirror, overwrite=overwrite)
            capture("batch", {"profile": name, "recursive": recursive, "mirror_tree": mirror, "overwrite": overwrite}, setup)

    texts = {
        "PARAM_LABELS": w.PARAM_LABELS, "CHOICE_LABELS": w.CHOICE_LABELS, "PRESET_TOKEN_LABELS": w.PRESET_TOKEN_LABELS,
        "PALETTE_LABELS": w.PALETTE_LABELS, "MODE_LABELS": w.MODE_LABELS, "MODULE_META": w.MODULE_META,
        "ENCODER_FAMILY_LABELS": w.ENCODER_FAMILY_LABELS, "ENCODER_BACKEND_LABELS": w.ENCODER_BACKEND_LABELS,
        "DECODE_BACKEND_LABELS": w.DECODE_BACKEND_LABELS, "VS_ACCEL_LABELS": w.VS_ACCEL_LABELS,
        "PRORES_PROFILE_LABELS": w.PRORES_PROFILE_LABELS, "PRORES_CONTAINER_LABELS": w.PRORES_CONTAINER_LABELS,
        "DNXHR_PROFILE_LABELS": w.DNXHR_PROFILE_LABELS, "TEXT": w.TEXT,
    }
    presets = [{"palette": s.palette, "name": s.name, "friendly": w.display_preset_name(s.name), "summary": s.summary,
                "params": {k: v for k, v in s.params.items()}} for s in specs]
    window_map = {
        "where": {"labels": "system_core\\ui_nicegui\\app.py (dictionaries of the window)",
                  "presets": "system_core\\engine\\presets.py (summary, doc - English only)"},
        "texts": texts, "presets": presets, "profiles": profiles, "encoders": sorted(R.ENCODERS),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "former_window_commands.json").write_text(
        json.dumps({"reference": reference.name, "records": records}, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8", newline="\n")
    (out_dir / "former_window_map.json").write_text(
        json.dumps(window_map, ensure_ascii=False, indent=1, default=str), encoding="utf-8", newline="\n")
    refused = sum(1 for r in records if "refused" in r)
    print(f"{reference.name}: {len(records)} states ({refused} refused), {len(specs)} presets, {len(profiles)} profiles")
finally:
    shutil.rmtree(temp, ignore_errors=True)
