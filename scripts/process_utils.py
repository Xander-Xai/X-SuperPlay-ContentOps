"""Unified subprocess helper for Windows no-popup background execution.

Provides:
  - hidden_run(): subprocess.run with Windows console window suppressed
  - interactive_run(): subprocess.run with console visible (for auth, debug)
  - get_hidden_kwargs(): platform-safe kwargs for CREATE_NO_WINDOW

Interactive processes (gh auth login, OAuth, manual debug) MUST stay visible.
Background processes (ffmpeg, ffprobe, git read, helper Python) default hidden.

Debug override: set CONTENTOPS_SHOW_SUBPROCESS_WINDOWS=1 to force visible.
"""

import os
import subprocess
import sys
from typing import Optional

# Feature-detect Windows-only constants (importable on all platforms)
def _get_hidden_kwargs() -> dict:
    """Return kwargs that suppress console window on Windows; no-op on other OS."""
    if os.name != "nt":
        return {}

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE

    kwargs = {
        "startupinfo": startupinfo,
    }
    # CREATE_NO_WINDOW = 0x08000000 — feature-detect in case of non-standard Python
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kwargs


def _is_debug_visible() -> bool:
    """Check if CONTENTOPS_SHOW_SUBPROCESS_WINDOWS env var forces visible windows."""
    return os.environ.get("CONTENTOPS_SHOW_SUBPROCESS_WINDOWS", "").strip() in ("1", "true", "True", "TRUE")


def hidden_run(
    cmd: list,
    *,
    cwd: Optional[str] = None,
    timeout: Optional[int] = 120,
    capture_output: bool = True,
    text: bool = True,
    encoding: str = "utf-8",
    errors: str = "replace",
    env: Optional[dict] = None,
    shell: bool = False,
) -> subprocess.CompletedProcess:
    """Run a background subprocess with no console window popup on Windows.

    Always:
      - shell=False (never shell=True for background)
      - captures stdout + stderr
      - explicit UTF-8 encoding
      - returns CompletedProcess with returncode

    Never use for interactive commands (gh auth login, OAuth, manual debug).
    """
    run_kwargs = {
        "cwd": cwd,
        "capture_output": capture_output,
        "text": text,
        "timeout": timeout,
        "shell": False,  # always False for background
    }
    if text:
        run_kwargs["encoding"] = encoding
        run_kwargs["errors"] = errors
    if env is not None:
        run_kwargs["env"] = env

    if not _is_debug_visible():
        run_kwargs.update(_get_hidden_kwargs())

    return subprocess.run(cmd, **run_kwargs)


def interactive_run(
    cmd: list,
    *,
    cwd: Optional[str] = None,
    timeout: Optional[int] = None,
    env: Optional[dict] = None,
) -> subprocess.CompletedProcess:
    """Run an interactive subprocess with console visible (auth, OAuth, debug).

    No CREATE_NO_WINDOW, no SW_HIDE. The user's terminal stays visible.
    """
    return subprocess.run(
        cmd,
        cwd=cwd,
        timeout=timeout,
        env=env,
    )


def is_background_command(cmd: list) -> bool:
    """Classify whether a command is background (should be hidden) or interactive."""
    if not cmd:
        return False
    exe = str(cmd[0]).lower()
    # Strip path prefix
    exe = exe.replace("\\", "/").split("/")[-1]
    # Interactive commands that MUST stay visible
    interactive = {"gh", "git", "claude", "code", "python", "python3"}
    # gh auth login is interactive; gh api is background
    if exe == "gh" and len(cmd) > 1 and cmd[1] in ("auth", "login"):
        return False
    # Background commands
    background = {"ffmpeg", "ffprobe", "node", "powershell", "pwsh", "cmd"}
    if exe in background:
        return True
    # Default: treat as background (hidden) for safety
    return True
