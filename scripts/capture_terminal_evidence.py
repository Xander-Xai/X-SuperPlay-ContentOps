#!/usr/bin/env python3
"""Capture an allowlisted, read-only terminal session as evidence.

The plan file is the allowlist. This driver does not accept shell text, does not
build a command by string interpolation, and does not decide for itself that a
command is safe: a human-approved plan names an executable and an argv, and the
driver refuses anything that falls outside the rules below.

What it guarantees
------------------
- a **new visible console**, never this process's console and never the desktop;
- a recording bounded to that window's rectangle, with a rectangle re-check
  after the session so a moved window invalidates the capture instead of
  producing a silently mis-framed clip;
- stdout shown in the window (not piped away), the real exit code written by the
  wrapper, and a receipt on success *and* failure;
- a sanitized environment: only declared variables are inherited, so a stray
  token in the parent shell cannot be filmed by accident.

What it cannot guarantee
------------------------
That the command is harmless in every environment, or that a crop later hides
the line that changes the conclusion. The first is why the plan needs an
approval; the second is a human review on the redacted derivative.

Usage::

    python scripts/capture_terminal_evidence.py \
        projects/easel-evidence-capture/script/capture-plan.json --dry-run

    python scripts/capture_terminal_evidence.py \
        projects/easel-evidence-capture/script/capture-plan.json
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from process_utils import (  # noqa: E402
    PIPE,
    hidden_popen,
    hidden_run,
    python_executable,
    visible_console_popen,
)
from contentops.evidence._common import (  # noqa: E402
    ContractError,
    canonical_json,
    sha256_bytes,
    sha256_file,
)
from contentops.evidence.capture import CaptureProof  # noqa: E402

PLAN_SCHEMA = "contentops.capture-plan/v1"
PLAN_STATUSES = ("DRAFT", "APPROVED")

#: Executables the plan may name. Deliberately small: a capture should run the
#: repository's own verification tooling, git read-only commands, or a runtime
#: version probe, not an arbitrary binary.
ALLOWED_EXECUTABLES = {
    "python", "python.exe", "py", "py.exe",
    "git", "git.exe",
    "node", "node.exe",
    "npm", "npm.cmd",
    "ffmpeg", "ffmpeg.exe", "ffprobe", "ffprobe.exe",
    "pwsh", "pwsh.exe", "powershell", "powershell.exe",
}

#: Tokens that make a command mutating, network-facing, secret-bearing, or a
#: shell injection. Matching is case-insensitive on the joined argv.
DENIED_TOKENS = (
    "push", "--force", "reset --hard", "clean -fdx",
    "curl", "wget", "invoke-webrequest", "invoke-restmethod",
    "http://", "https://",
    "gh pr", "gh api", "gh release",
    "docker", "wsl", "ssh", "scp",
    "minimax", "dashscope", "openai",
    ".env", "credentials", "auth.json", "browser",
    "rm -rf", "rmdir", "del /", "format ", "shutdown", "reg add",
)

#: Tools a capture command may need on PATH even though it does not name them in
#: argv. Each entry contributes only that executable's own directory; the
#: parent's PATH is never inherited. A command run without a tool it needs
#: records a truthful failure about the capture environment, which is not
#: evidence about the repository.
ALLOWED_PATH_TOOLS = {"gh", "git", "node", "npm", "ffmpeg", "ffprobe"}

FORBIDDEN_SHELL_CHARS = ("&", "|", ">", "<", "%", "^", "\n", "\r", "`")

PREFLIGHT_FLAGS = (
    "notifications_disabled",
    "audio_disabled",
    "terminal_selected",
    "readable_dpi",
    "no_unrelated_desktop_content",
)

MIN_SECONDS = 5
MAX_SECONDS = 600
#: A readable result needs to stay on screen. The hold changes only how long the
#: already-approved command's result is recorded, never the command itself.
MAX_HOLD_AFTER_EXIT = 10
WINDOW_TITLE_PREFIX = "CONTENTOPS_CAP_"


class CaptureRefused(RuntimeError):
    """The plan or the session violated a rule; nothing was recorded."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


def _refuse(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise CaptureRefused(code, detail)


def _require_text(value: Any, field: str) -> str:
    _refuse(isinstance(value, str) and value.strip() != "", "MISSING_FIELD",
            f"{field} must be a non-empty string")
    return value


def _iso(value: Any, field: str) -> str:
    text = _require_text(value, field)
    _refuse(text.endswith("Z") or text.endswith("+00:00"), "NON_UTC_TIMESTAMP",
            f"{field} must be UTC")
    return text


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def validate_plan(document: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a capture plan. Does not read the filesystem or launch anything."""
    _refuse(isinstance(document, dict), "MALFORMED_PLAN", "plan must be an object")
    _refuse(document.get("schema") == PLAN_SCHEMA, "UNSUPPORTED_SCHEMA",
            f"expected {PLAN_SCHEMA!r}, got {document.get('schema')!r}")
    status = document.get("status", "DRAFT")
    _refuse(status in PLAN_STATUSES, "INVALID_STATUS",
            f"status must be one of {PLAN_STATUSES}")
    _require_text(document.get("plan_id"), "plan_id")
    _require_text(document.get("project_id"), "project_id")
    captures = document.get("captures")
    _refuse(isinstance(captures, list), "MISSING_CAPTURES",
            "captures must be a list")
    if status == "DRAFT":
        _refuse(not captures, "DRAFT_HAS_CAPTURES",
                "a DRAFT plan may describe no executable captures")
        return document

    preflight = document.get("preflight") or {}
    _refuse(isinstance(preflight, dict), "MISSING_PREFLIGHT",
            "preflight must be an object")
    for flag in PREFLIGHT_FLAGS:
        _refuse(preflight.get(flag) is True, "PREFLIGHT_NOT_CONFIRMED",
                f"preflight.{flag} must be true before any capture")
    _require_text(preflight.get("checked_by"), "preflight.checked_by")
    _iso(preflight.get("checked_at"), "preflight.checked_at")

    environment = document.get("environment") or {}
    _require_text(environment.get("name"), "environment.name")
    _refuse(document.get("permission_scope", "internal_review")
            in ("publishable", "internal_review", "restricted"),
            "INVALID_PERMISSION_SCOPE",
            "permission_scope must be publishable, internal_review or restricted")
    if document.get("permission_scope") == "publishable":
        _require_text(document.get("approval_reviewer"), "approval_reviewer")
        _iso(document.get("approval_at"), "approval_at")

    _refuse(bool(captures), "EMPTY_PLAN", "an APPROVED plan must contain a capture")
    _require_text(document.get("approved_by"), "approved_by")
    _iso(document.get("approved_at"), "approved_at")

    seen = set()
    for index, capture in enumerate(captures):
        _validate_capture(capture, index, seen)
    return document


def _validate_capture(capture: Any, index: int, seen: set) -> None:
    where = f"captures[{index}]"
    _refuse(isinstance(capture, dict), "INVALID_CAPTURE", f"{where} must be an object")
    capture_id = _require_text(capture.get("capture_id"), f"{where}.capture_id")
    _refuse(capture_id not in seen, "DUPLICATE_CAPTURE_ID",
            f"duplicate capture_id {capture_id!r}")
    seen.add(capture_id)
    _require_text(capture.get("command_id"), f"{where}.command_id")
    _refuse(capture.get("read_only") is True, "NOT_READ_ONLY",
            f"{where}.read_only must be true; capture never mutates state")
    _refuse(capture.get("evidence_class") in ("EXECUTED", "HISTORICAL", "DOCUMENTED"),
            "INVALID_EVIDENCE_CLASS", f"{where}.evidence_class is not supported")
    _refuse(capture.get("expected_result") in ("success", "failure", "either"),
            "INVALID_EXPECTED_RESULT",
            f"{where}.expected_result must be success, failure or either")

    seconds = capture.get("max_seconds")
    _refuse(isinstance(seconds, int) and not isinstance(seconds, bool)
            and MIN_SECONDS <= seconds <= MAX_SECONDS, "INVALID_TIMEOUT",
            f"{where}.max_seconds must be {MIN_SECONDS}..{MAX_SECONDS}")

    hold = capture.get("hold_after_exit_s", 0)
    _refuse(isinstance(hold, (int, float)) and not isinstance(hold, bool)
            and 0 <= hold <= MAX_HOLD_AFTER_EXIT, "INVALID_HOLD",
            f"{where}.hold_after_exit_s must be 0..{MAX_HOLD_AFTER_EXIT}")

    cwd = capture.get("cwd", ".")
    _require_text(cwd, f"{where}.cwd")
    cwd_path = (ROOT / cwd).resolve()
    _refuse(_inside(cwd_path, ROOT), "CWD_ESCAPE",
            f"{where}.cwd escapes the repository: {cwd!r}")
    _refuse(cwd_path.is_dir(), "CWD_MISSING", f"{where}.cwd is not a directory")

    argv = capture.get("argv")
    _refuse(isinstance(argv, list) and argv, "INVALID_ARGV",
            f"{where}.argv must be a non-empty list")
    _refuse(all(isinstance(item, str) and item for item in argv), "INVALID_ARGV",
            f"{where}.argv items must be non-empty strings")
    executable = Path(argv[0]).name.lower()
    _refuse(executable in ALLOWED_EXECUTABLES, "EXECUTABLE_NOT_ALLOWED",
            f"{where} names {argv[0]!r}, which is not an allowlisted executable")
    lowered_args = [item.lower() for item in argv[1:]]
    if executable.startswith(("python", "py")):
        _refuse("-c" not in lowered_args, "COMMAND_DENIED",
                f"{where} runs inline code; a capture must run a repository "
                f"script whose source can be reviewed")
    if executable.startswith(("powershell", "pwsh")):
        _refuse(not any(flag in lowered_args for flag in
                        ("-command", "-encodedcommand", "-c")),
                "COMMAND_DENIED",
                f"{where} runs an inline PowerShell payload; capture runs a "
                f"script path or an argv, not a string program")

    joined = " ".join(argv).lower()
    for token in DENIED_TOKENS:
        _refuse(token not in joined, "COMMAND_DENIED",
                f"{where} contains {token!r}, which is not allowed in a capture")
    for item in argv:
        for char in FORBIDDEN_SHELL_CHARS:
            _refuse(char not in item, "SHELL_METACHARACTER",
                    f"{where}.argv contains {char!r}; a capture runs an argv, not a "
                    f"shell command")

    env_allow = capture.get("env_allow") or []
    _refuse(isinstance(env_allow, list) and all(isinstance(x, str) for x in env_allow),
            "INVALID_ENV_ALLOW", f"{where}.env_allow must be a list of strings")
    for name in env_allow:
        for marker in ("KEY", "TOKEN", "SECRET", "PASSWORD", "COOKIE", "AUTH"):
            _refuse(marker not in name.upper(), "SECRET_ENV_ALLOWED",
                    f"{where}.env_allow must not inherit {name!r}")

    path_tools = capture.get("path_tools") or []
    _refuse(isinstance(path_tools, list)
            and all(isinstance(x, str) for x in path_tools),
            "INVALID_PATH_TOOLS", f"{where}.path_tools must be a list of strings")
    for tool in path_tools:
        _refuse(tool in ALLOWED_PATH_TOOLS, "PATH_TOOL_NOT_ALLOWED",
                f"{where}.path_tools names {tool!r}; allowed: "
                f"{', '.join(sorted(ALLOWED_PATH_TOOLS))}")


def sanitized_env(capture: Dict[str, Any], work_dir: Path) -> Dict[str, str]:
    """A minimal environment plus only the variables the plan declares.

    Inheriting the parent environment is how a capture ends up filming an API
    key that happened to be exported in that shell. The allowlist is explicit.
    """
    base = {
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
        "WINDIR": os.environ.get("WINDIR", r"C:\Windows"),
        "SYSTEMDRIVE": os.environ.get("SYSTEMDRIVE", "C:"),
        "COMSPEC": os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe"),
        "PATHEXT": os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD"),
        "TEMP": str(work_dir),
        "TMP": str(work_dir),
        "TMPDIR": str(work_dir),
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    system32 = Path(base["SYSTEMROOT"]) / "System32"
    search = [
        str(system32),
        str(system32 / "WindowsPowerShell" / "v1.0"),
        str(Path(python_executable()).parent),
        str(Path(python_executable()).parent / "Scripts"),
    ]
    # Add only the directory of the executable this capture is allowed to run,
    # never the parent's whole PATH. That keeps `git`/`node` reachable without
    # inheriting a shell whose PATH happens to include a credential-bearing tool.
    resolved = shutil.which(capture["argv"][0])
    if resolved:
        directory = str(Path(resolved).parent)
        if directory not in search:
            search.insert(0, directory)
    for tool in capture.get("path_tools") or []:
        found = shutil.which(tool)
        if found:
            directory = str(Path(found).parent)
            if directory not in search:
                search.append(directory)
    base["PATH"] = os.pathsep.join(search)
    # Recorded so a receipt can explain which tools were reachable.
    base["CONTENTOPS_CAPTURE_PATH_TOOLS"] = os.pathsep.join(
        sorted(capture.get("path_tools") or []))
    for name in capture.get("env_allow") or []:
        if name in os.environ:
            base[name] = os.environ[name]
    return base


def _list2cmdline(argv: Sequence[str]) -> str:
    """Quote an argv for cmd.exe without invoking a shell to do it."""
    return subprocess.list2cmdline(list(argv))


def build_session_dir(project: Path, capture_id: str) -> Path:
    return project / "work" / "sessions" / capture_id


def write_wrapper(project: Path, capture: Dict[str, Any],
                  session_dir: Path) -> Tuple[Path, Path, Path]:
    """Write the .cmd wrapper. Returns (wrapper, go_file, exit_file)."""
    session_dir.mkdir(parents=True, exist_ok=True)
    go_file = session_dir / "go.marker"
    exit_file = session_dir / "exit-code.txt"
    wrapper = session_dir / "session.cmd"
    title = WINDOW_TITLE_PREFIX + capture["capture_id"]
    cwd = (ROOT / capture.get("cwd", ".")).resolve()
    command = _list2cmdline(capture["argv"])
    hold = max(int(capture.get("max_seconds", 120)), 8)
    lines = [
        "@echo off",
        "setlocal",
        f'title {title}',
        f'cd /d "{cwd}"',
        ":wait_for_start",
        f'if not exist "{go_file}" (',
        "  >nul timeout /t 1 /nobreak",
        "  goto wait_for_start",
        ")",
        command,
        'set "RC=%ERRORLEVEL%"',
        f'> "{exit_file}" echo %RC%',
        "echo.",
        "echo CONTENTOPS_EXIT_CODE=%RC%",
        f">nul timeout /t {hold} /nobreak",
        "endlocal",
    ]
    wrapper.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    return wrapper, go_file, exit_file


# --- Windows window geometry -------------------------------------------------

if os.name == "nt":
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    _user32.EnumWindows.argtypes = [_EnumWindowsProc, wintypes.LPARAM]
    _user32.EnumWindows.restype = wintypes.BOOL
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsWindowVisible.restype = wintypes.BOOL
    _user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetWindowTextW.restype = ctypes.c_int
    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _user32.GetWindowRect.restype = wintypes.BOOL
    _user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    _user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]
    _dwmapi = ctypes.WinDLL("dwmapi")
    _dwmapi.DwmGetWindowAttribute.argtypes = [
        wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
    ]
    _dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long

DWMWA_EXTENDED_FRAME_BOUNDS = 9

SW_RESTORE = 9
HWND_TOPMOST = -1
SWP_SHOWWINDOW = 0x0040


def find_window(title_suffix: str) -> int:
    """Handle of the first visible top-level window whose title ends with suffix.

    Console windows are owned by the console host, not by the child process, and
    an elevated session prefixes the title with the localised administrator
    label. Matching the suffix is therefore the only reliable join.
    """
    _refuse(os.name == "nt", "UNSUPPORTED_PLATFORM",
            "window capture is implemented for Windows only")
    found = {"handle": 0}

    def callback(hwnd, _lparam):
        if not _user32.IsWindowVisible(hwnd):
            return True
        buffer = ctypes.create_unicode_buffer(512)
        _user32.GetWindowTextW(hwnd, buffer, len(buffer))
        if buffer.value.rstrip().endswith(title_suffix):
            found["handle"] = int(hwnd)
            return False
        return True

    _user32.EnumWindows(_EnumWindowsProc(callback), 0)
    return found["handle"]


def window_rect(handle: int) -> Tuple[int, int, int, int]:
    """Visible window bounds, excluding the invisible resize border.

    ``GetWindowRect`` includes the ~7 px transparent resize frame Windows 10/11
    draws around a window. Capturing that rectangle filmed slivers of whatever
    window sat behind it (verified in a real frame: fragments of another
    console appeared along the right and bottom edges). ``DWMWA_EXTENDED_FRAME_BOUNDS``
    is the compositor's visible bounds, so it contains only this window.
    """
    rect = wintypes.RECT()
    result = _dwmapi.DwmGetWindowAttribute(
        handle, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), ctypes.sizeof(rect))
    if result != 0:
        rect = wintypes.RECT()
        _refuse(bool(_user32.GetWindowRect(handle, ctypes.byref(rect))),
                "WINDOW_GONE", "the capture window disappeared")
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    _refuse(width > 0 and height > 0, "INVALID_WINDOW_RECT",
            f"window rect is {width}x{height}")
    return rect.left, rect.top, width, height


def place_window(handle: int, x: int = 40, y: int = 40,
                 width: int = 1100, height: int = 700) -> None:
    _user32.ShowWindow(handle, SW_RESTORE)
    _user32.SetWindowPos(handle, ctypes.c_void_p(HWND_TOPMOST),
                         x, y, width, height, SWP_SHOWWINDOW)
    _user32.SetForegroundWindow(handle)


def even_size(width: int, height: int) -> Tuple[int, int]:
    return width + (width % 2), height + (height % 2)


# --- recording ---------------------------------------------------------------

def start_recorder(rect: Tuple[int, int, int, int], output: Path,
                   seconds: int):
    x, y, width, height = rect
    even_w, even_h = even_size(width, height)
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "gdigrab", "-draw_mouse", "0",
        "-offset_x", str(x), "-offset_y", str(y),
        "-video_size", f"{even_w}x{even_h}",
        "-framerate", "15", "-i", "desktop",
        "-t", str(min(seconds + 15, MAX_SECONDS + 15)),
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        str(output),
    ]
    return hidden_popen(command, stdin=PIPE, text=True)


def stop_recorder(process, timeout: float = 20.0) -> int:
    if process.poll() is None:
        try:
            process.stdin.write("q\n")
            process.stdin.flush()
        except (BrokenPipeError, OSError, ValueError):
            pass
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        return process.wait(timeout=5)


def _close_console(process) -> None:
    """Close our own wrapper and the console it owns, never another process."""
    if process.poll() is not None:
        return
    try:
        hidden_run(["taskkill", "/PID", str(process.pid), "/T", "/F"], timeout=20)
    except Exception:  # noqa: BLE001 - cleanup must not mask the capture result
        pass
    try:
        process.kill()
    except OSError:
        pass


def _monotonic_range(start: float, end: float) -> str:
    """Time range inside the recording, which always begins at its own zero."""
    total_ms = max(1, int(round((end - start) * 1000)))
    return "00:00.000-" + _end_marker(total_ms)


def _end_marker(total_ms: int) -> str:
    minutes, rest = divmod(total_ms, 60000)
    seconds, millis = divmod(rest, 1000)
    return f"{minutes:02d}:{seconds:02d}.{millis:03d}"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def capture_one(project: Path, plan: Dict[str, Any], capture: Dict[str, Any],
                keep_window: bool = False) -> Dict[str, Any]:
    """Run one plan entry and emit a Capture Proof.

    Returns a result dict with ``status`` OK or BLOCKED. A command that exits
    non-zero still returns OK with ``exit_code`` preserved; only a broken capture
    (no window, moved window, no recording) is BLOCKED.
    """
    capture_id = capture["capture_id"]
    session_dir = build_session_dir(project, capture_id)
    for stale in (session_dir / "go.marker", session_dir / "exit-code.txt"):
        if stale.exists():
            stale.unlink()

    wrapper, go_file, exit_file = write_wrapper(project, capture, session_dir)
    env = sanitized_env(capture, session_dir)
    title = WINDOW_TITLE_PREFIX + capture_id
    raw_path = project / "work" / "raw" / f"{capture_id}.mp4"

    started_wall = _now()
    process = visible_console_popen(
        ["cmd.exe", "/c", str(wrapper)], cwd=str(ROOT), env=env)

    handle = 0
    recorder = None
    try:
        for _ in range(40):
            time.sleep(0.25)
            handle = find_window(title)
            if handle:
                break
        if not handle:
            raise CaptureRefused("WINDOW_NOT_FOUND",
                                 f"no visible console titled *{title} appeared")

        place_window(handle)
        time.sleep(0.4)
        rect = window_rect(handle)
        recorder = start_recorder(rect, raw_path, capture["max_seconds"])
        record_start = time.monotonic()

        go_file.write_text("go", encoding="utf-8")

        exit_code: Optional[int] = None
        deadline = time.monotonic() + capture["max_seconds"]
        while time.monotonic() < deadline:
            if exit_file.exists():
                text = exit_file.read_text(encoding="utf-8", errors="replace").strip()
                if text.lstrip("-").isdigit():
                    exit_code = int(text)
                    break
            if process.poll() is not None and exit_file.exists():
                break
            time.sleep(0.2)

        time.sleep(0.5 + float(capture.get("hold_after_exit_s", 0)))
        final_rect = window_rect(handle)
        record_end = time.monotonic()
        stop_recorder(recorder)
        recorder = None
    finally:
        if recorder is not None:
            stop_recorder(recorder)
        if not keep_window:
            _close_console(process)

    if final_rect != rect:
        rejected = project / "work" / "rejected" / f"{capture_id}.mp4"
        rejected.parent.mkdir(parents=True, exist_ok=True)
        if raw_path.exists():
            shutil.move(str(raw_path), str(rejected))
        raise CaptureRefused(
            "WINDOW_MOVED",
            f"window rect changed during capture ({rect} -> {final_rect}); "
            f"recording quarantined at {rejected}",
        )
    if not raw_path.exists() or raw_path.stat().st_size < 1024:
        raise CaptureRefused("NO_RECORDING",
                             f"ffmpeg produced no usable recording at {raw_path}")
    if exit_code is None:
        raise CaptureRefused("EXIT_CODE_MISSING",
                             "the session never reported an exit code; the "
                             "recording cannot prove what the command returned")

    command_sha = sha256_bytes(canonical_json(capture["argv"]).encode("utf-8"))
    logical = f"project://work/raw/{capture_id}.mp4"
    proof = CaptureProof(
        capture_id=capture_id,
        session_id=session_dir.name,
        evidence_class=capture["evidence_class"],
        repository_revision=capture.get("repository_revision") or _repo_revision(),
        working_tree_state=capture.get("working_tree_state") or _working_tree_state(),
        target_environment={
            "name": plan["environment"]["name"],
            **({"description_digest": plan["environment"]["description_digest"]}
               if plan["environment"].get("description_digest") else {}),
        },
        command={
            "display": _list2cmdline(capture["argv"]),
            "sha256": command_sha,
        },
        read_only=True,
        fixture_or_cache=capture.get("fixture_or_cache", "none"),
        started_at=started_wall,
        finished_at=_now(),
        exit_code=exit_code,
        recording={
            "logical_path": logical,
            "sha256": sha256_file(raw_path),
            "time_range": _monotonic_range(record_start, record_end),
        },
        permission_scope=plan.get("permission_scope", "internal_review"),
        notes=list(capture.get("notes") or []),
    ).validate()
    proof.verify_recording(raw_path)

    receipts = project / "receipts" / "captures"
    receipts.mkdir(parents=True, exist_ok=True)
    (receipts / f"{capture_id}.json").write_text(
        json.dumps(proof.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    expected = capture["expected_result"]
    observed = "success" if exit_code == 0 else "failure"
    unexpected = expected != "either" and expected != observed
    result = {
        "status": "OK",
        "capture_id": capture_id,
        "exit_code": exit_code,
        "expected_result": expected,
        "observed_result": observed,
        "unexpected_result": unexpected,
        "recording": logical,
        "recording_sha256": proof.recording["sha256"],
        "window_rect": list(rect),
        "receipt": f"project://receipts/captures/{capture_id}.json",
    }
    (session_dir / "run.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def _repo_revision() -> str:
    proc = hidden_run(["git", "rev-parse", "HEAD"], cwd=str(ROOT), timeout=30)
    revision = (proc.stdout or "").strip()
    _refuse(proc.returncode == 0 and bool(revision), "REVISION_UNKNOWN",
            "the repository revision could not be read; a capture without a "
            "revision cannot say what it observed")
    return revision


def _working_tree_state() -> str:
    proc = hidden_run(["git", "status", "--porcelain"], cwd=str(ROOT), timeout=30)
    _refuse(proc.returncode == 0, "WORKING_TREE_UNKNOWN",
            "the working-tree state could not be read")
    text = (proc.stdout or "").strip()
    if not text:
        return "clean"
    return "dirty:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def run(plan_path: Path, project: Path, only: Optional[str] = None,
        dry_run: bool = False, keep_window: bool = False) -> dict:
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    validate_plan(plan)
    if plan.get("status") != "APPROVED":
        return {"status": "BLOCKED", "reason":
                "plan is DRAFT; a human must approve it before capture"}

    selected = [c for c in plan["captures"] if only in (None, c["capture_id"])]
    if not selected:
        return {"status": "BLOCKED", "reason": f"no capture matches {only!r}"}

    if dry_run:
        preview = []
        for capture in selected:
            session_dir = build_session_dir(project, capture["capture_id"])
            wrapper, go_file, exit_file = write_wrapper(project, capture, session_dir)
            preview.append({
                "capture_id": capture["capture_id"],
                "wrapper": str(wrapper),
                "go_file": str(go_file),
                "exit_file": str(exit_file),
                "argv": capture["argv"],
                "env_keys": sorted(sanitized_env(capture, session_dir)),
            })
        return {"status": "DRY_RUN", "captures": preview}

    results = []
    for capture in selected:
        try:
            results.append(capture_one(project, plan, capture, keep_window))
        except CaptureRefused as exc:
            results.append({"status": "BLOCKED", "capture_id": capture["capture_id"],
                            "code": exc.code, "reason": exc.detail})
    overall = "OK" if all(item["status"] == "OK" for item in results) else "BLOCKED"
    return {"status": overall, "results": results}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", help="capture-plan.json")
    parser.add_argument("--project", default="projects/easel-evidence-capture")
    parser.add_argument("--only", default=None, help="single capture_id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--keep-window", action="store_true",
                        help="leave the console open after the session")
    args = parser.parse_args()
    project = Path(args.project)
    if not project.is_absolute():
        project = (ROOT / project).resolve()
    try:
        result = run(Path(args.plan), project, only=args.only,
                     dry_run=args.dry_run, keep_window=args.keep_window)
    except (CaptureRefused, ContractError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)},
                         indent=2, ensure_ascii=False))
        return 4
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("status") in ("OK", "DRY_RUN") else 4


if __name__ == "__main__":
    sys.exit(main())
