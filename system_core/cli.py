"""The console command of Audion VS Engine: vs_cli.cmd.

A button of the window and the command line run the same thing: an operation of the manifest (a preset, a profile, a
service), by the same runner (core\\jobs.py execute_operation), with the same rules of its form (core\\operation_model.py),
on the pattern of Audion Media Tools 3.0.0.

  vs_cli.cmd describe
  vs_cli.cmd run --operation mild_denoise --set strength=light
  vs_cli.cmd run --operation film_35mm --set stock=500T --encoder prores_lt --source D:\\Footage --target D:\\Out
  vs_cli.cmd run --operation profile_run --set profile=archival_master --dry-run
  vs_cli.cmd list presets
  vs_cli.cmd version

The output of `run`: a plain line is a line of the operation's journal; a line that starts with `::vs::` is a service
line and carries JSON - `started`, `progress` (the share of the work done, 0..1), `activity` (the one live line under the
journal), `finished`. Service lines go to a caller that reads the output by a pipe (the window, a script); a person at a
console does not get them and sees the bar `[PROGRESS]` with vspipe's own line `Frame: N/M (fps)` under it. A caller
that asks for it (`--live`: the window does) gets `activity` instead of those two lines.

Outcomes and exit codes: `done` 0; `failed` 1; `stopped` 130; a wrong call - 2, and nothing is run: a field the
operation has not, a choice that is none of its field's, a number outside its range, a form that may not be run as it
stands. A run its preflight refuses (no engine, no video in the Source) is `refused`, exit 2: its [PREFLIGHT] lines say
why. The outcome goes to the file of `--result` whatever it is.

Paths: a relative `--source` or `--target` is counted from the project folder, as the window shows them; a relative
`--params`, `--result` or `--cancel-file` - from the folder of the caller.

Stopping: the caller creates the file of `--cancel-file`; the operation ends vspipe and FFmpeg, the draft goes, exit 130.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from system_core.core import operation_model as model  # noqa: E402
from system_core.core import window_layout  # noqa: E402
from system_core.core.jobs import RunPaths, execute_operation  # noqa: E402
from system_core.core.manifest import load_manifest, manifest_path  # noqa: E402
from system_core.core.sources import ONLY_ENV  # noqa: E402

CONTROL = "::vs::"
EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_STOPPED = 0, 1, 2, 130
ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")

_nobody_listens = False


def strip_ansi(text: str) -> str:
    return ANSI.sub("", text)


def say(line: str) -> None:
    global _nobody_listens
    if _nobody_listens:
        return
    try:
        print(line, flush=True)
    except (OSError, ValueError):
        # The caller closed its end of the pipe: the run goes on, its journal file is written all the same.
        _nobody_listens = True


def control(payload: dict[str, Any]) -> None:
    if sys.stdout.isatty():
        return
    say(CONTROL + json.dumps(payload, ensure_ascii=False, default=str))


def usage_error(message: str) -> int:
    try:
        print("[ERR] " + message, file=sys.stderr, flush=True)
    except (OSError, ValueError):
        pass
    return EXIT_USAGE


# --- how far the engine is -------------------------------------------------------------------

# "[PROGRESS] clip.mov [##########--------------]  42% 1234/2940 9.81 fps ETA 02:10" - services\vs_service.py FrameBar.
BAR = re.compile(r"^\[PROGRESS\]\s+(?P<name>.*?)\s+\[[#-]+\]\s+(?P<share>\d{1,3})%\s+(?P<frame>\d+)/(?P<frames>\d+)"
                 r"\s+(?P<fps>[\d.]+)\s+fps(?:\s+ETA\s+(?P<eta>\S+))?\s*$")
NATIVE = re.compile(r"^Frame:\s*\d+/\d+")
LIVE_WORDS = {"en": ("Processing", "frames", "fps", "ETA"), "ru": ("Обработка", "кадров", "к/с", "осталось")}


class Progress:
    """The share of an operation done, told by its service, and the live line, told by vspipe's counter."""

    def __init__(self, live: bool, language: str) -> None:
        self.live, self.told = live, -1.0
        self.said, self.when = "", 0.0
        self.words = LIVE_WORDS.get(language, LIVE_WORDS["en"])

    def share(self, value: float) -> None:
        value = round(max(0.0, min(1.0, float(value))), 4)
        if value > self.told:
            self.told = value
            control({"progress": value})

    def activity(self, text: str, last: bool = False) -> None:
        now = time.monotonic()
        if text == self.said or (not last and now - self.when < 0.1):
            return
        self.said, self.when = text, now
        control({"activity": text})

    def line(self, text: str) -> bool:
        """True - a line of progress, told as the live line, not as a line of the journal."""
        if not self.live:
            return False
        plain = strip_ansi(text).strip()
        if NATIVE.match(plain):
            return True
        found = BAR.match(plain)
        if not found:
            return False
        processing, frames, fps, eta = self.words
        measures = [f"{found['share']}%", f"{found['frame']} / {found['frames']} {frames}", f"{found['fps']} {fps}"]
        if found["eta"]:
            measures.append(f"{eta} {found['eta']}")
        self.activity(f"{processing}: " + " · ".join(measures) + f" · {found['name']}", found["share"] == "100")
        return True


# --- the project -----------------------------------------------------------------------------


def project(root: str | None):
    folder = Path(root).resolve() if root else ROOT
    path = manifest_path(folder)
    if not path.is_file():
        raise ValueError(f"not a project folder, no manifest: {path}")
    try:
        return folder, load_manifest(path)
    except Exception as error:  # noqa: BLE001 - whatever the manifest stumbles over, nothing was run
        raise ValueError(f"the manifest does not read: {path}: {error}") from error


def project_version(root: Path) -> str:
    try:
        return str(json.loads((root / "config" / "version.json").read_text(encoding="utf-8")).get("version", ""))
    except (OSError, ValueError):
        return ""


def language_of(args: argparse.Namespace, root: Path) -> str:
    """The language named by the caller; without it - the one chosen in the window, English when none was."""
    if getattr(args, "language", ""):
        return model.safe_language(args.language)
    try:
        chosen = json.loads((root / "config" / "window_settings.json").read_text(encoding="utf-8-sig")).get("Lang", "")
    except (OSError, ValueError, AttributeError):
        chosen = ""
    return model.safe_language(str(chosen))


def command_describe(args: argparse.Namespace) -> int:
    root, manifest = project(args.root)
    from system_core.core.plans import PLANS

    payload = model.describe(manifest)
    payload["version"] = project_version(root)
    payload["language"] = language_of(args, root)
    payload["layout"] = window_layout.for_window(window_layout.load(root / "config"), manifest)
    payload["paths"] = {name: str(root / name) for name in ("input", "output", "logs", "report", "config")}
    payload["paths"]["root"] = str(root)
    # The installers: what they fetch is named before they run. Taking the engine away fetches nothing - it is asked about.
    payload["plans"] = sorted(PLANS - {"remove_vapoursynth"})
    # The neural presets and the installation of MLRT: the window shows them by what this machine has (core\machine.py).
    from system_core.core import machine

    card = machine.rtx()
    payload["machine"] = {"rtx": card, "mlrt": machine.mlrt(root), "neural": machine.neural_shown(root, card)}
    say(json.dumps(payload, ensure_ascii=False, default=str))
    return EXIT_OK


def command_map(args: argparse.Namespace) -> int:
    from system_core.core import program_map

    root, manifest = project(args.root)
    told = program_map.build(root, manifest, version=project_version(root))
    if getattr(args, "docs", False):
        from system_core.core import program_docs

        written = program_docs.write(told, root)
        for path in written:
            say(f"[DOCS] {path.relative_to(root)}")
        say(f"[DOCS] {len(written)} written, the others are as the map makes them")
        if not args.out:
            return EXIT_OK
    if args.out:
        trouble = write_result(own_file(args.out), told)
        if trouble:
            return usage_error(f"the map could not be written to {args.out}: {trouble}")
        say(f"[MAP] {own_file(args.out)}: {len(told['operations'])} operations, {len(told['missing'])} texts missing")
        return EXIT_OK
    say(json.dumps(told, ensure_ascii=False, default=str))
    return EXIT_OK


def command_form(args: argparse.Namespace) -> int:
    """The forms of the window, held while it is open (core\\form_pages.py): a JSON request a line on the input, a JSON
    answer a line on the output, until the input closes."""
    from system_core.core import form_pages

    root, manifest = project(args.root)
    os.chdir(root)
    answers = sys.stdout
    # Whatever the engine prints while a form is drawn goes to the errors: the output carries the answers alone.
    sys.stdout = sys.stderr
    try:
        sys.stdin.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    def write(text: str) -> None:
        answers.write(text)
        answers.flush()

    form_pages.serve(form_pages.Pages(root, manifest, language_of(args, root)), sys.stdin.readline, write)
    return EXIT_OK


def command_version(args: argparse.Namespace) -> int:
    root, _manifest = project(args.root)
    say(project_version(root))
    return EXIT_OK


def command_plan(args: argparse.Namespace) -> int:
    """What an installer of SETUP would download - its files, their source and size - with nothing fetched."""
    from system_core.core.plans import PLANS, plan

    root, _manifest = project(args.root)
    if args.operation not in PLANS:
        return usage_error(f"{args.operation!r} is no installer; installers: {', '.join(sorted(PLANS))}")
    say(json.dumps(plan(root, args.operation), ensure_ascii=False))
    return EXIT_OK


def command_components(args: argparse.Namespace) -> int:
    from system_core.core import components

    root, _manifest = project(args.root)
    say(json.dumps(components.report(root, latest=args.latest, refresh=args.refresh), ensure_ascii=False))
    return EXIT_OK


def command_list(args: argparse.Namespace) -> int:
    """What a person at a console asks: the presets, the encoders, the profiles, the folders - as lines to read."""
    root, manifest = project(args.root)
    language = language_of(args, root)
    if args.what == "presets":
        for node in model.presets(manifest):
            fields = ", ".join(f"{model.field_id(field)}={model.field_default(field)}" for field in node.fields
                               if not model.section_of(field) in {"processing", "encoding", "run"})
            say(f"  {node.parameters.get('palette', '') + '/' + node.id:<36} {node.display_title(language)}"
                + (f"  [{fields}]" if fields else ""))
    elif args.what == "encoders":
        from system_core.engine import encoding, runner

        for name in runner.list_encoders():
            cards = encoding.cards_of(name)
            shown = {key: value for key, value in cards.items() if key == "encode_family"
                     or cards["encode_family"] in encoding.SHOWN.get(key, ())}
            say(f"  {name:<18} {' '.join(f'{key}={value}' for key, value in shown.items())}")
    elif args.what == "profiles":
        from system_core.services.vs_service import profiles

        for name, data in sorted(profiles(root).items()):
            say(f"  {name:<22} {str(data.get('palette', '?')) + '/' + str(data.get('preset', '?')):<34} "
                f"{data.get('encoder', '?'):<16} {data.get('description', '')}")
    else:
        from system_core.engine.paths import PATHS

        for name in ("root", "runtime_python", "vs_python", "vspipe", "ffmpeg", "ffprobe", "presets_dir", "input_dir",
                     "output_dir", "logs_dir"):
            say(f"  {name:<15}: {getattr(PATHS, name)}")
    return EXIT_OK


# --- the values of a run ---------------------------------------------------------------------


def read_values(args: argparse.Namespace, node) -> dict[str, Any]:
    """The values of the fields: the cards of `--encoder`, over them the file of `--params`, over it every `--set`."""
    values: dict[str, Any] = {}
    if getattr(args, "encoder", ""):
        from system_core.engine import encoding, runner

        if args.encoder not in runner.ENCODERS:
            raise ValueError(f"--encoder: no encoder {args.encoder!r}; encoders: {', '.join(runner.list_encoders())}")
        container = "mkv" if any(item.strip().startswith("encode_container=mkv") for item in args.set or []) else "mp4"
        known = {model.field_id(field) for field in node.fields}
        values.update({key: value for key, value in encoding.cards_of(args.encoder, container).items() if key in known})
    if args.params:
        loaded = json.loads(Path(args.params).read_text(encoding="utf-8-sig"))
        if not isinstance(loaded, dict):
            raise ValueError("--params: a JSON object \"field name: value\" is expected")
        values.update(loaded)
    fields = {model.field_id(field): field for field in node.fields if model.field_id(field)}
    for item in args.set or []:
        name, separator, text = item.partition("=")
        name = name.strip()
        if not separator or not name:
            raise ValueError(f"--set: name=value is expected, got {item!r}")
        if name not in fields:
            raise ValueError(f"--set: the operation has no field {name!r}")
        try:
            values[name] = model.coerce(fields[name], text)
        except ValueError as error:
            raise ValueError(f"--set {name}: {error}") from error
    return values


def write_result(path: str, payload: dict[str, Any]) -> str:
    """The outcome into its file, whole or not at all; the reason when it could not be written."""
    if not path:
        return ""
    target = Path(path)
    draft: Path | None = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, ensure_ascii=False, indent=1, default=str)
        while draft is None:
            candidate = target.with_name(f"{target.name}.{os.getpid()}-{secrets.token_hex(3)}.tmp")
            try:
                with candidate.open("x", encoding="utf-8") as stream:
                    stream.write(text)
                draft = candidate
            except FileExistsError:
                continue
        draft.replace(target)
        return ""
    except OSError as error:
        if draft is not None:
            draft.unlink(missing_ok=True)
        return str(error)


def _inside(path: Path, folder: Path) -> bool:
    try:
        Path(os.path.realpath(path)).relative_to(Path(os.path.realpath(folder)))
        return True
    except ValueError:
        return False


def result_refusal(result: str, source: Path, params: str, root: Path) -> str:
    """Why the outcome may not go where --result names it; "" - it may. A source, a file inside the Source, the --params
    file and the settings of the program are never written over by it."""
    if not result:
        return ""
    target = Path(result)
    if target.suffix.lower() != ".json":
        return f"--result names a .json file, and {target.name} is not one"
    if target.is_dir():
        return f"--result names a folder: {target}"
    own = _inside(target, root) and "._runtime" in Path(os.path.realpath(target)).parts
    if os.path.normcase(os.path.realpath(target)) == os.path.normcase(os.path.realpath(source)) or (
            source.is_dir() and _inside(target, source) and not own):
        return f"--result would be written into the Source: {target}"
    if params and os.path.normcase(os.path.realpath(target)) == os.path.normcase(os.path.realpath(params)):
        return "--result and --params name one file"
    if _inside(target, root / "config"):
        return f"--result would be written over a file of the program's settings: {target}"
    return ""


def expand_percent(text: str) -> str:
    return re.sub(r"%([^%\\/:*?\"<>|]+)%", lambda found: os.environ.get(found.group(1), found.group(0)), text)


def workbench_path(text: str, fallback: Path, root: Path) -> Path:
    """Source or Target as named by the caller; a relative one is counted from the project folder."""
    if not text:
        return fallback
    cleaned = text.strip().strip('"').strip()
    if '"' in cleaned:
        # `"E:\My Files\" --target D:\Out` reaches a program as one argument with a quote inside: the backslash before
        # the closing quote glued the next key to the path.
        raise ValueError(f"a quotation mark inside a path - was the path quoted with a backslash at its end? {text!r}")
    path = Path(expand_percent(cleaned)).expanduser()
    return path if path.is_absolute() else root / path


def own_file(text: str) -> str:
    return str(Path(text).expanduser().resolve()) if text else ""


def command_run(args: argparse.Namespace) -> int:
    root, manifest = project(args.root)
    node = model.find_node(manifest, args.operation)
    if node is None:
        return usage_error(f"the manifest has no operation {args.operation!r}")
    language = language_of(args, root)
    args.params, args.result, args.cancel_file = own_file(args.params), own_file(args.result), own_file(args.cancel_file)
    try:
        given = read_values(args, node)
        source = workbench_path(args.source, root / "input", root).resolve()
        target = workbench_path(args.target, root / "output", root).resolve()
    except (OSError, ValueError) as error:
        return usage_error(str(error))
    refusal = result_refusal(args.result, source, args.params, root)
    if refusal:
        return usage_error(refusal)
    unknown = model.unknown_values(node, given)
    if unknown:
        return usage_error("the operation has no fields: " + ", ".join(unknown))
    wrong = model.wrong_values(node, given, root, language)
    if wrong:
        return usage_error("; ".join(wrong))
    only = ",".join(part.strip().lower().lstrip(".") for part in str(args.only or "").split(",") if part.strip())
    if only:
        os.environ[ONLY_ENV] = only
    else:
        os.environ.pop(ONLY_ENV, None)
    form = model.Form(node, root, source, target).open().fill(given)
    refused = form.refusal(language)
    if refused:
        return usage_error(refused)
    parameters = form.parameters()
    service = node.service.rsplit(":", 1)[-1]
    if args.dry_run:
        if service not in model.DRY_RUN_SERVICES:
            return usage_error(f"{args.operation!r} cannot say its commands without running them: it has no dry run")
        parameters["dry_run"] = True

    os.chdir(root)
    cancel_file = Path(args.cancel_file) if args.cancel_file else None
    progress = Progress(bool(args.live), language)
    colours = bool(args.colours)

    def tell(line: str) -> None:
        text = str(line)
        if progress.line(text):
            return
        say(text if colours or sys.stdout.isatty() else strip_ansi(text))

    for key, wanted, became in form.changed(given):
        reason = form.off_reasons(language).get(key, {}).get(str(wanted), "")
        tell(f"[NOTE] {key}: {wanted!r} became {became!r}" + (f" - {reason}" if reason else ""))

    operation = node.with_parameters(parameters)
    control({"started": {"operation": operation.id, "source": str(source), "target": str(target)}})
    began = time.monotonic()
    result = execute_operation(RunPaths(root, source, target), operation, tell, progress.share,
                               (lambda: cancel_file.exists()) if cancel_file is not None else None)
    stopped = bool(not result.ok and (result.data.get("cancelled") is True
                                      or (cancel_file is not None and cancel_file.exists())))
    refused = bool(not result.ok and not stopped and result.data.get("preflight_refused") is True)
    outcome = "stopped" if stopped else "done" if result.ok else "refused" if refused else "failed"
    seconds = round(time.monotonic() - began, 1)
    data = result.data
    trouble = write_result(args.result, {
        "operation": operation.id, "outcome": outcome, "ok": result.ok, "message": result.message,
        "processed": data.get("processed", 0), "skipped": data.get("skipped", 0), "failed": data.get("failed", 0),
        "parameters": parameters, "seconds": seconds, "log_file": data.get("log_file", ""),
        "source": str(source), "target": str(target), "data": data})
    if trouble:
        say(f"[WARN] The outcome could not be written to {args.result}: {trouble}")
    control({"finished": {"outcome": outcome, "message": result.message, "seconds": seconds}})
    return EXIT_STOPPED if stopped else EXIT_OK if result.ok else EXIT_USAGE if refused else EXIT_FAILED


def command_frame(args: argparse.Namespace) -> int:
    """One frame before and after the operation of a page with its values (core\\frame.py): one line of JSON."""
    from system_core.core import frame as _frame
    from system_core.core.sources import source_files

    root, manifest = project(args.root)
    node = model.find_node(manifest, args.operation)
    if node is None:
        return usage_error(f"the manifest has no operation {args.operation!r}")
    language = language_of(args, root)
    args.params = own_file(args.params)
    try:
        given = read_values(args, node)
        source = workbench_path(args.source, root / "input", root).resolve()
    except (OSError, ValueError) as error:
        return usage_error(str(error))
    if args.side not in _frame.SIDES:
        return usage_error(f"--side: one of {', '.join(_frame.SIDES)}")
    if not 0.0 <= args.at <= 1.0:
        return usage_error("--at: a share of the length, from 0 to 1")
    unknown = model.unknown_values(node, given)
    if unknown:
        return usage_error("the operation has no fields: " + ", ".join(unknown))
    wrong = model.wrong_values(node, given, root, language)
    if wrong:
        return usage_error("; ".join(wrong))
    # A folder is pictured by its first video, as a run would take it first.
    file = source if source.is_file() else next(iter(source_files(source, root / "output")), None) if source.is_dir() else None
    if file is None:
        return usage_error(f"no video to picture in {source}")
    form = model.Form(node, root, source, root / "output").open().fill(given)
    out = Path(args.out) if args.out else root / "._runtime" / "frame"
    told = _frame.render(root, node, form.parameters(), Path(file), float(args.at), out, args.side, int(args.max_width))
    say(json.dumps({"ok": not told.get("error"), **told}, ensure_ascii=False, default=str))
    return EXIT_FAILED if told.get("error") else EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vs_cli", description="Audion VS Engine: the console command.")
    parser.add_argument("--root", default="", help="The project folder; this one when not named.")
    parser.add_argument("--language", default="", help="en or ru; the language of the window when not named")
    commands = parser.add_subparsers(dest="command", required=True)

    describe = commands.add_parser("describe", help="The program, the operations, their fields, the layout of the window and the machine as one line of JSON")
    describe.add_argument("--language", default=argparse.SUPPRESS)
    describe.set_defaults(func=command_describe)

    run = commands.add_parser("run", help="Run an operation of the manifest: a preset, a profile, a service")
    run.add_argument("--operation", required=True)
    run.add_argument("--source", default="", help="A file or a folder; `input` of the program when not named")
    run.add_argument("--target", default="", help="A folder; `output` of the program when not named")
    run.add_argument("--set", action="append", default=[], metavar="NAME=VALUE")
    run.add_argument("--encoder", default="", help="A name of the encoders (list encoders) put on the cards; --set of a card wins")
    run.add_argument("--params", default="", help="A JSON file \"field name: value\"")
    run.add_argument("--result", default="", help="A file the outcome is written to")
    run.add_argument("--cancel-file", default="", help="A file whose appearance stops the operation")
    run.add_argument("--dry-run", action="store_true", help="Say the commands of vspipe and FFmpeg, run none")
    run.add_argument("--only", default="", help="The kinds of file to take, e.g. mov or mov,mxf; every video when not named")
    run.add_argument("--language", default=argparse.SUPPRESS)
    run.add_argument("--live", action="store_true", help="Tell the progress of vspipe as service lines, not as its lines")
    run.add_argument("--colours", action="store_true", help="Leave the colour codes in the lines")
    run.set_defaults(func=command_run)

    picture = commands.add_parser("frame", help="One frame before and after a preset with its values, as two PNG: the card FRAME of the window")
    picture.add_argument("--operation", required=True, help="A preset, or profile_run with --set profile=NAME")
    picture.add_argument("--source", default="", help="A video, or a folder - its first video; `input` of the program when not named")
    picture.add_argument("--at", type=float, default=0.5, help="Where in the clip: a share of its length, 0 to 1")
    picture.add_argument("--side", default="both", help="both, before or after")
    picture.add_argument("--out", default="", help="The folder of before.png and after.png; ._runtime\\frame when not named")
    picture.add_argument("--max-width", type=int, default=1920, help="A wider frame is scaled down to it; 0 - as it is")
    picture.add_argument("--set", action="append", default=[], metavar="NAME=VALUE")
    picture.add_argument("--encoder", default="", help=argparse.SUPPRESS)
    picture.add_argument("--params", default="", help="A JSON file \"field name: value\"")
    picture.add_argument("--language", default=argparse.SUPPRESS)
    picture.set_defaults(func=command_frame)

    form = commands.add_parser("form", help="The forms of the window: a JSON request a line in, a JSON answer a line out")
    form.add_argument("--language", default=argparse.SUPPRESS)
    form.set_defaults(func=command_form)

    program = commands.add_parser("map", help="The map of the program from its data, the texts in both languages and what has none")
    program.add_argument("--out", default="", help="A JSON file to write it to; one line on the output when not named")
    program.add_argument("--docs", action="store_true",
                         help="Write the reference part of the documents from the map: docs\\OPERATIONS_*.md and the tables "
                              "between <!-- map:NAME --> and <!-- /map -->")
    program.set_defaults(func=command_map)

    commands.add_parser("version", help="The version number").set_defaults(func=command_version)

    parts = commands.add_parser("components", help="VapourSynth, the plugins, FFmpeg and the GPU driver, and the newest releases")
    parts.add_argument("--latest", action="store_true", help="Ask GitHub for the newest releases when the remembered ones are a day old")
    parts.add_argument("--refresh", action="store_true", help="Ask GitHub now")
    parts.set_defaults(func=command_components)

    plan = commands.add_parser("plan", help="What an installer of SETUP would download: the files, their source and size")
    plan.add_argument("--operation", required=True, help="install_vapoursynth, install_vs_plugins, install_ffmpeg or remove_vapoursynth")
    plan.set_defaults(func=command_plan)

    listing = commands.add_parser("list", help="The presets, the encoders, the profiles or the folders, as lines to read")
    listing.add_argument("what", choices=["presets", "encoders", "profiles", "paths"])
    listing.add_argument("--language", default=argparse.SUPPRESS)
    listing.set_defaults(func=command_list)
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as stop:
        return EXIT_OK if stop.code in (0, None) else EXIT_USAGE
    # Self-heal: a project moved to another folder leaves the shebangs of Scripts\*.exe pointing at the old python.exe,
    # and vspipe exits 1 without a word.
    if args.command == "run":
        from system_core.engine.selfheal import ensure_pip_shims_repaired

        status = ensure_pip_shims_repaired()
        if status == "repaired":
            say("[selfheal] vspipe shim shebang updated to current python.exe")
        elif status.startswith("repair-failed"):
            say(f"[selfheal] WARN: Repair-PipShims exited with {status}")
    try:
        return args.func(args)
    except ValueError as error:
        return usage_error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
