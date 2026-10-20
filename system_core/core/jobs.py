"""The run of an operation: its journal, its share done, its stop, its report.

On the pattern of Audion Media Tools 3.0.0 (core\\jobs.py there): a service gets a `JobContext` - `log` writes a line to the
journal of the run (logs\\<stamp>_<operation>.log) and to the caller, `units` and `progress` tell how far the operation
is, `progress_inside` moves the share inside the unit at work (a file: by vspipe's frame counter), `cancelled` asks the
stop signal. The outcome goes to report\\<stamp>_<operation>\\run_report.json and .md, whatever it is.

A service returns a dict: `ok`, `processed`, `skipped`, `failed`, and what else it has to say; `cancelled` - it stopped.
"""
from __future__ import annotations

import importlib
import json
import os
import queue
import subprocess
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .logging_utils import append_log, strip_ansi, timestamp
from .manifest import Operation

LogCallback = Callable[[str], None]
ProgressCallback = Callable[[float], None]
CancelCallback = Callable[[], bool]

# A process may name other folders for the journals and the reports: the tests do, so the program's own stay the person's.
LOGS_ENV = "AUDION_LOGS"
REPORT_ENV = "AUDION_REPORT"


def _named_or(name: str, fallback: Path) -> Path:
    given = os.environ.get(name, "").strip().strip('"')
    return Path(given) if given else fallback


@dataclass(frozen=True)
class RunPaths:
    """The folders of one run: the program, the Source (a file or a folder) and the Target it writes under."""
    root: Path
    source: Path
    target: Path

    @property
    def config(self) -> Path:
        return self.root / "config"

    @property
    def logs(self) -> Path:
        return _named_or(LOGS_ENV, self.root / "logs")

    @property
    def report(self) -> Path:
        return _named_or(REPORT_ENV, self.root / "report")


@dataclass
class JobContext:
    paths: RunPaths
    operation: Operation
    log_file: Path
    report_dir: Path
    log_callback: LogCallback | None = None
    progress_callback: ProgressCallback | None = None
    cancel_callback: CancelCallback | None = None
    commands: list[dict[str, Any]] = field(default_factory=list)
    told_share: float = 0.0
    unit_share: float | None = None

    def log(self, message: str) -> None:
        append_log(self.log_file, message)
        if self.log_callback:
            self.log_callback(message)

    def progress(self, value: float) -> None:
        """The share of the operation done, as the service tells it: the base of the unit that comes next."""
        self.told_share = max(0.0, min(1.0, float(value)))
        if self.progress_callback:
            self.progress_callback(self.told_share)

    def units(self, count: int) -> None:
        """How many units of work the operation has - files; the service tells the share after each."""
        self.unit_share = 1.0 / count if count > 0 else None

    def progress_inside(self, ratio: float) -> None:
        """How far the unit at work is, 0..1, moved into the share of the operation."""
        if self.unit_share is not None and self.progress_callback:
            self.progress_callback(min(1.0, self.told_share + self.unit_share * max(0.0, min(1.0, float(ratio)))))

    def cancelled(self) -> bool:
        return bool(self.cancel_callback and self.cancel_callback())


@dataclass
class JobResult:
    ok: bool
    message: str
    data: dict[str, Any]


class OperationCancelled(RuntimeError):
    """STOP: the child process was ended. Not a failure of the program - one line, no trace."""


class PreflightRefused(RuntimeError):
    """The run cannot begin - no engine, no video in the Source. Its [PREFLIGHT] lines say why."""


# --- a child process -------------------------------------------------------------------------------------------------


def hidden_subprocess_kwargs() -> dict[str, Any]:
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return {"startupinfo": startupinfo, "creationflags": int(getattr(subprocess, "CREATE_NO_WINDOW", 0))}


def format_command(command: list[str]) -> str:
    return " ".join(f'"{item}"' if " " in str(item) else str(item) for item in command)


def end_process_tree(process: subprocess.Popen) -> None:
    """Stop a child and what it started itself, and wait for its end, five seconds at most."""
    if process.poll() is None:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, **hidden_subprocess_kwargs())
        else:
            process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _decode(raw: bytes) -> str:
    """A line of a child: UTF-8, else the OEM page of the console (cmd and Windows PowerShell 5.1 speak cp866)."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp866", errors="replace")


def run_process(context: JobContext, command: list[str], *, cwd: Path | None = None,
                extra_env: dict[str, str] | None = None, check: bool = True,
                line_filter: Callable[[str], bool] | None = None) -> tuple[int, list[str]]:
    """Run a child hidden, every line of its output into the journal; STOP ends it within a fifth of a second.

    line_filter(line) -> True: the line was taken care of (a progress line) and is not written as it is."""
    working = Path(cwd or context.paths.root)
    context.log(f"[CMD] {format_command([str(item) for item in command])}")
    record: dict[str, Any] = {"cwd": str(working), "command": [str(item) for item in command], "started_at": timestamp()}
    context.commands.append(record)
    began = time.monotonic()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1", **(extra_env or {})}
    process = subprocess.Popen([str(item) for item in command], cwd=str(working), stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, **hidden_subprocess_kwargs())
    feed: queue.Queue = queue.Queue()

    def read() -> None:
        assert process.stdout is not None
        try:
            pending = b""
            while True:
                data = process.stdout.read1(65536) if hasattr(process.stdout, "read1") else process.stdout.read(4096)
                if not data:
                    break
                pending += data
                *pieces, pending = pending.replace(b"\r\n", b"\n").replace(b"\r", b"\n").split(b"\n")
                for piece in pieces:
                    feed.put(piece)
            if pending:
                feed.put(pending)
        finally:
            feed.put(None)

    reader = threading.Thread(target=read, name="process-output", daemon=True)
    reader.start()
    lines: list[str] = []
    while True:
        try:
            raw = feed.get(timeout=0.2)
        except queue.Empty:
            raw = b""
        if context.cancelled():
            context.log("[CANCEL] Ending the child process...")
            end_process_tree(process)
            raise OperationCancelled("Operation stopped by the user.")
        if raw is None:
            break
        line = strip_ansi(_decode(raw)).rstrip()
        if not line:
            continue
        lines.append(line)
        if line_filter is not None and line_filter(line):
            continue
        context.log(line)
    code = process.wait()
    reader.join(timeout=5)
    record.update(exit_code=code, duration_seconds=round(time.monotonic() - began, 3))
    context.log(f"[EXIT] {code}")
    if check and code != 0:
        raise RuntimeError(f"Command failed with exit code {code}.")
    return code, lines


# --- the report ------------------------------------------------------------------------------------------------------


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _write_report(context: JobContext, *, started_at: str, seconds: float, ok: bool, message: str,
                  preflight: dict[str, Any], data: dict[str, Any], error_traceback: str = "") -> dict[str, str]:
    report_json = context.report_dir / "run_report.json"
    report_md = context.report_dir / "run_report.md"
    payload: dict[str, Any] = {
        "operation": {"id": context.operation.id, "title": context.operation.title,
                      "title_ru": context.operation.title_ru, "service": context.operation.service},
        "status": "OK" if ok else "FAIL", "message": message, "started_at": started_at, "finished_at": timestamp(),
        "duration_seconds": round(seconds, 3), "source": str(context.paths.source), "target": str(context.paths.target),
        "log_file": str(context.log_file), "report_dir": str(context.report_dir),
        "parameters": _json_safe(context.operation.parameters), "preflight": _json_safe(preflight),
        "result": _json_safe(data), "commands": _json_safe(context.commands),
    }
    if error_traceback:
        payload["traceback"] = error_traceback
    report_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Audion VS Engine - run report", "",
             f"- Operation: `{context.operation.id}`", f"- Status: `{payload['status']}`", f"- Message: {message}",
             f"- Started: {started_at}", f"- Finished: {payload['finished_at']}", f"- Duration: {seconds:.1f} s",
             f"- Source: `{context.paths.source}`", f"- Target: `{context.paths.target}`", f"- Log: `{context.log_file}`",
             "", "## Preflight", ""]
    checks = preflight.get("checks", []) if isinstance(preflight, dict) else []
    lines += [f"- [{item.get('level', '?')}] {item.get('subject', '')}: {item.get('detail', '')}" for item in checks] or [
        "- No preflight checks recorded."]
    lines += ["", "## Result", "", "```json", json.dumps(_json_safe(data), ensure_ascii=False, indent=2), "```", "",
              "## Commands", ""]
    for index, command in enumerate(context.commands, start=1):
        lines += [f"### Command {index}", "", f"- Exit: `{command.get('exit_code')}`",
                  f"- Duration: `{command.get('duration_seconds')}` s", "", "```bat",
                  format_command(command.get("command") or []), "```", ""]
    if not context.commands:
        lines.append("- No child process commands were run.")
    if error_traceback:
        lines += ["", "## Traceback", "", "```text", error_traceback.rstrip(), "```", ""]
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return {"run_report_json": str(report_json), "run_report_md": str(report_md), "report_dir": str(context.report_dir),
            "log_file": str(context.log_file)}


def _load_callable(service: str) -> Callable[[JobContext], Any]:
    module_name, function_name = service.split(":", 1)
    return getattr(importlib.import_module(module_name), function_name)


def execute_operation(paths: RunPaths, operation: Operation, log_callback: LogCallback | None = None,
                      progress_callback: ProgressCallback | None = None,
                      cancel_callback: CancelCallback | None = None) -> JobResult:
    from .preflight import run_preflight

    stamp = datetime.now().strftime("%Y-%m-%d %H-%M-%S-%f")[:-3]
    log_file = paths.logs / f"{stamp}_{operation.id}.log"
    report_dir = paths.report / f"{stamp}_{operation.id}"
    report_dir.mkdir(parents=True, exist_ok=True)
    context = JobContext(paths, operation, log_file, report_dir, log_callback, progress_callback, cancel_callback)
    started_at, began = timestamp(), time.monotonic()
    preflight: dict[str, Any] = {}
    try:
        context.log(f"Starting operation: {operation.id}")
        if operation.parameters:
            context.log(f"Parameters: {json.dumps(_json_safe(operation.parameters), ensure_ascii=False, sort_keys=True)}")
        context.progress(0.0)
        preflight = run_preflight(context)
        if not preflight.get("ok", True):
            raise PreflightRefused("Preflight failed: the [PREFLIGHT] lines above say why.")
        result = _load_callable(operation.service)(context)
        data = dict(result) if isinstance(result, dict) else {}
        cancelled = bool(data.get("cancelled")) or context.cancelled()
        failed = data.get("failed", 0)
        failed = int(failed) if isinstance(failed, (int, float)) and not isinstance(failed, bool) else 0
        ok = bool(data.get("ok", True)) and failed == 0 and not cancelled
        if cancelled:
            data["cancelled"] = True
            message = "Operation stopped by the user."
            context.log(f"[STOPPED] {message}")
        else:
            context.progress(1.0)
            message = ("Operation finished." if ok else f"Operation finished with {failed} failed file(s)." if failed
                       else str(data.get("message") or "Operation reported failure."))
            context.log(f"Finished operation: {operation.id}")
        files = _write_report(context, started_at=started_at, seconds=time.monotonic() - began, ok=ok, message=message,
                              preflight=preflight, data=data)
        context.log(f"Run report: {files['run_report_md']}")
        data.update(files)
        return JobResult(ok, message, data)
    except Exception as exc:  # noqa: BLE001 - whatever stops a run, the report and the outcome are written
        error_text = ""
        if isinstance(exc, OperationCancelled) or context.cancelled():
            message = "Operation stopped by the user."
            context.log(f"[STOPPED] {message}")
            data: dict[str, Any] = {"cancelled": True}
        elif isinstance(exc, PreflightRefused):
            message = str(exc)
            context.log(f"[REFUSED] {message}")
            data = {"preflight_refused": True}
        else:
            error_text = traceback.format_exc()
            context.log(error_text)
            message = f"{exc.__class__.__name__}: {exc}"
            data = {}
        try:
            data.update(_write_report(context, started_at=started_at, seconds=time.monotonic() - began, ok=False,
                                      message=message, preflight=preflight, data=data, error_traceback=error_text))
            context.log(f"Run report: {data['run_report_md']}")
        except Exception as report_error:  # noqa: BLE001
            context.log(f"Could not write the run report: {report_error.__class__.__name__}: {report_error}")
        return JobResult(False, message, data)
