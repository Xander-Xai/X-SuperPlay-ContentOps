"""Unified subprocess layer for ContentOps.

Single source of truth for how ContentOps launches child processes, so that
Windows console popups can be governed in exactly one place.

Why this exists
---------------
On Windows, a console application launched from a process that has no console of
its own will allocate a **new visible console window** unless the caller passes
`CREATE_NO_WINDOW` and/or `STARTF_USESHOWWINDOW | SW_HIDE`. Every ffmpeg,
ffprobe, git, gh and child-Python call therefore flashed a CMD/conhost window.
Passing both flags covers the two distinct cases:

- ``STARTF_USESHOWWINDOW`` + ``SW_HIDE`` hides the window even when the child
  inherits an existing console.
- ``CREATE_NO_WINDOW`` prevents a console from being allocated at all, which is
  what a GUI/console-less parent needs.

On Linux/macOS both are meaningless, so the helpers are a strict no-op and
existing POSIX behaviour is unchanged.

Public API
----------
``hidden_run(cmd, ...)``          run to completion, no visible window
``hidden_popen(cmd, ...)``        start and stream, no visible window
``interactive_run(cmd, ...)``     run with the console left visible
``is_interactive_command(cmd)``   classify a command
``python_executable()``           ``sys.executable`` for child interpreters

Policy
------
- Background work must go through ``hidden_run`` / ``hidden_popen``.
- ``shell=True`` is rejected outright. It is not needed by any callsite.
- Child interpreters must use ``python_executable()``, never the bare string
  ``"python"``, which resolves differently under venv/WSL/Store installs.

Debug override: set ``CONTENTOPS_SHOW_SUBPROCESS_WINDOWS=1`` to disable window
suppression, which makes popup behaviour reproducible when debugging.

Enforcement: ``scripts/check_subprocess_policy.py`` fails CI if tracked code
calls ``subprocess`` directly instead of using this module.
"""

import os
import subprocess
import sys
from typing import IO, Any, Dict, List, Optional, Sequence

__all__ = [
    "hidden_run",
    "hidden_popen",
    "interactive_run",
    "interactive_run_captured",
    "is_interactive_command",
    "is_background_command",
    "python_executable",
    "window_suppression_enabled",
    "PIPE",
    "DEVNULL",
    "DEBUG_ENV_VAR",
]

# Re-exported so calling code never needs to import subprocess just for a
# sentinel constant. Using the helper is then the only route to a pipe.
PIPE = subprocess.PIPE
DEVNULL = subprocess.DEVNULL

DEBUG_ENV_VAR = "CONTENTOPS_SHOW_SUBPROCESS_WINDOWS"

_TRUTHY = {"1", "true", "yes", "on"}


def python_executable() -> str:
    """Return the interpreter to use for child Python processes.

    Always ``sys.executable``: the bare string ``"python"`` may resolve to a
    different interpreter than the one running ContentOps (Store installs,
    virtualenvs, WSL), which silently breaks reproducibility.
    """
    return sys.executable


def _is_debug_visible() -> bool:
    """True when the debug override forces subprocess windows to stay visible."""
    return os.environ.get(DEBUG_ENV_VAR, "").strip().lower() in _TRUTHY


def window_suppression_enabled() -> bool:
    """True when hidden window flags will actually be applied.

    False on non-Windows platforms, and False on Windows when the debug
    override is active. Tests assert on this to avoid asserting Windows-only
    behaviour on Linux CI.
    """
    return os.name == "nt" and not _is_debug_visible()


def _get_hidden_kwargs() -> Dict[str, Any]:
    """Return kwargs suppressing the console window on Windows; no-op elsewhere.

    Returns an empty dict on non-Windows platforms so callers can splat the
    result unconditionally without changing POSIX behaviour.
    """
    if not window_suppression_enabled():
        return {}

    kwargs: Dict[str, Any] = {}

    # Feature-detected: these exist on Windows builds of CPython only.
    if hasattr(subprocess, "STARTUPINFO") and hasattr(subprocess, "STARTF_USESHOWWINDOW"):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = startupinfo

    # CREATE_NO_WINDOW stops a console being allocated at all.
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    return kwargs


def _exe_name(cmd: Sequence[str]) -> str:
    """Return the lowercased basename of a command's executable."""
    if not cmd:
        return ""
    return str(cmd[0]).replace("\\", "/").rstrip("/").split("/")[-1].lower()


def _base_exe(exe: str) -> str:
    """Strip a trailing .exe so classification is extension-independent."""
    return exe[:-4] if exe.endswith(".exe") else exe


# "<exe> <subcommand>" pairs that require a human at the keyboard.
_INTERACTIVE_PAIRS = {
    ("gh", "auth"),
    ("mmx", "auth"),
}

# "<exe>" invocations that are always interactive, with or without a subcommand.
_INTERACTIVE_BARE = {"claude", "code"}

# Shells. Interactive only when launched bare; a script or an inline command is
# background work.
_SHELL_EXES = {"powershell", "pwsh", "cmd", "bash", "sh", "zsh", "fish", "dash", "ksh"}

# Shell flags that mean "run this and exit", so the shell is a tool, not a
# session the user types into. Compared against the lowercase first argument.
_SHELL_RUN_FLAGS = {
    # PowerShell
    "-command", "-encodedcommand", "-c", "-ec",
    # POSIX shells
    "-c", "-lc", "-ic", "-cl", "-lic", "-xc", "-e", "-eu",
}

# cmd.exe switches. /c executes and exits; /k executes and *keeps* the prompt.
_CMD_BACKGROUND_SWITCHES = {"/c"}
_CMD_INTERACTIVE_SWITCHES = {"/k", "/?"}


def _shell_is_interactive(exe: str, args: Sequence[str]) -> bool:
    """Decide whether a shell invocation is a session or a background command.

    ``powershell -NoProfile -Command ...`` and ``bash -c '...'`` run a payload
    and exit: they are BACKGROUND_HIDDEN and must not flash a window. A bare
    ``powershell`` or ``cmd`` opens a prompt the user drives: INTERACTIVE_VISIBLE.
    """
    base = _base_exe(exe)
    rest = [str(a).lower() for a in args[1:]]
    if not rest:
        return True  # bare shell: the user gets a prompt

    first = rest[0]

    if base == "cmd":
        if first in _CMD_BACKGROUND_SWITCHES:
            return False
        if first in _CMD_INTERACTIVE_SWITCHES:
            return True
        # `cmd some.exe ...` runs that program.
        return False

    if base == "powershell" or base == "pwsh":
        if first in _SHELL_RUN_FLAGS:
            return False
        if first in {"-nologo", "-noprofile", "-noninteractive", "-nologo",
                     "-mta", "-sta", "-windowstyle", "-executionpolicy",
                     "-outputformat", "-inputformat", "-workingdirectory", "-w"}:
            # A modifier flag on its own does not make it a session.
            return len(rest) > 1 and not any(
                a in _SHELL_RUN_FLAGS for a in rest[1:]
            )
        if first.startswith("-"):
            # Any remaining PowerShell parameter still runs a payload; treat
            # unknown flags as background rather than risking a hidden prompt.
            return False
        # A script path: `powershell script.ps1` executes it.
        return False

    # POSIX-like shells.
    if first in _SHELL_RUN_FLAGS:
        return False
    if first.startswith("-"):
        # Combined short flags such as -lc or -ic contain 'c' when they run a
        # command; otherwise a bare flag keeps an interactive session.
        return "c" not in first.lstrip("-")
    # A script path: `bash script.sh` executes it.
    return False


def is_interactive_command(cmd: Sequence[str]) -> bool:
    """True when the command needs a visible console for a human to use.

    Interactive means a person must drive it: ``gh auth login``,
    ``mmx auth login``, launching ``claude``, or opening a shell with no payload.

    Everything else is background work and must be hidden, including the shells
    used *as tools*: ``powershell -Command``, ``cmd /c``, ``bash -c`` and any
    script invocation. So is ``gh api``, every ``mmx`` subcommand other than
    ``auth``, ffmpeg, ffprobe, git and node.
    """
    if not cmd:
        return False
    exe = _exe_name(cmd)
    base = _base_exe(exe)
    sub = str(cmd[1]).lower() if len(cmd) > 1 else ""

    if (exe, sub) in _INTERACTIVE_PAIRS or base in _INTERACTIVE_BARE:
        return True
    if base in _SHELL_EXES:
        return _shell_is_interactive(exe, cmd)
    return False


def _reject_shell(shell: bool) -> None:
    if shell:
        raise ValueError(
            "shell=True is forbidden by ContentOps subprocess policy. "
            "Pass an argument list instead; if you genuinely need shell "
            "semantics, invoke the shell as an explicit executable argument "
            "(e.g. ['powershell', '-NoProfile', '-Command', ...]) and record "
            "the reason in docs/audits/windows-subprocess-audit.md."
        )


def _text_kwargs(text: bool, encoding: str, errors: str) -> Dict[str, Any]:
    if not text:
        return {}
    return {"encoding": encoding, "errors": errors}


def hidden_run(
    cmd: Sequence[str],
    *,
    cwd: Optional[str] = None,
    timeout: Optional[float] = 120,
    capture_output: bool = True,
    text: bool = True,
    encoding: str = "utf-8",
    errors: str = "replace",
    env: Optional[Dict[str, str]] = None,
    stdin: Optional[IO[Any]] = None,
    stdout: Optional[IO[Any]] = None,
    stderr: Optional[IO[Any]] = None,
    check: bool = False,
    shell: bool = False,
) -> subprocess.CompletedProcess:
    """Run a background command to completion with no visible console window.

    Defaults are tuned for ContentOps background work: output captured, UTF-8
    decoded with replacement, and a timeout so a hung child cannot wedge a
    pipeline.

    ``stdout``/``stderr``/``stdin`` may be file handles for streaming payloads
    (for example piping a tarball straight to disk). Supplying any of them
    implies ``capture_output=False``, because CPython rejects the combination.

    Set ``text=False`` for binary payloads such as ffmpeg ``rawvideo`` output.

    Raises:
        ValueError: if ``shell=True`` is passed.
        subprocess.TimeoutExpired: if ``timeout`` elapses.
    """
    _reject_shell(shell)

    if not cmd:
        raise ValueError("hidden_run() requires a non-empty command")

    streams = {"stdin": stdin, "stdout": stdout, "stderr": stderr}
    if any(v is not None for v in streams.values()):
        capture_output = False

    run_kwargs: Dict[str, Any] = {
        "cwd": cwd,
        "capture_output": capture_output,
        "text": text,
        "timeout": timeout,
        "check": check,
        "shell": False,
    }
    run_kwargs.update(_text_kwargs(text, encoding, errors))
    if env is not None:
        run_kwargs["env"] = env
    run_kwargs.update(streams)
    run_kwargs.update(_get_hidden_kwargs())

    return subprocess.run(list(cmd), **run_kwargs)


def hidden_popen(
    cmd: Sequence[str],
    *,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    stdin: Optional[IO[Any]] = None,
    stdout: Optional[int] = subprocess.PIPE,
    stderr: Optional[int] = subprocess.PIPE,
    text: bool = True,
    encoding: str = "utf-8",
    errors: str = "replace",
    shell: bool = False,
) -> subprocess.Popen:
    """Start a background command with no visible console window.

    For long-running work where output must be streamed while the process runs
    (``iter_lines``, polling ``poll()``, streaming to a file). Pipes default to
    ``subprocess.PIPE`` so the child cannot block on a full buffer.

    Raises:
        ValueError: if ``shell=True`` is passed.
    """
    _reject_shell(shell)

    if not cmd:
        raise ValueError("hidden_popen() requires a non-empty command")

    popen_kwargs: Dict[str, Any] = {
        "cwd": cwd,
        "stdin": stdin,
        "stdout": stdout,
        "stderr": stderr,
        "text": text,
        "shell": False,
    }
    popen_kwargs.update(_text_kwargs(text, encoding, errors))
    if env is not None:
        popen_kwargs["env"] = env
    popen_kwargs.update(_get_hidden_kwargs())

    return subprocess.Popen(list(cmd), **popen_kwargs)


def interactive_run(
    cmd: Sequence[str],
    *,
    cwd: Optional[str] = None,
    timeout: Optional[float] = None,
    env: Optional[Dict[str, str]] = None,
    input_text: Optional[str] = None,
    check: bool = False,
) -> subprocess.CompletedProcess:
    """Run a command the user must interact with, inheriting this terminal.

    Reserved for flows a human has to complete: ``gh auth login``,
    ``mmx auth login``, a bare shell, manual debug.

    Default behaviour, and it is deliberate:

    - the console stays **visible** (no ``CREATE_NO_WINDOW``, no ``SW_HIDE``)
    - **stdin, stdout and stderr are inherited** from the parent process, not
      piped, so the prompt is reachable and the user's terminal shows the
      session live

    Capturing the streams here would break the one thing this function exists
    for: a device-code or browser login prompt that the user has to see and
    answer. If you need a visible window *and* captured output, call
    :func:`interactive_run_captured` explicitly instead of changing this
    default.

    ``input_text`` feeds stdin while still leaving stdout/stderr inherited,
    which suits a token pasted into a prompt.
    """
    if not cmd:
        raise ValueError("interactive_run() requires a non-empty command")

    return subprocess.run(
        list(cmd),
        cwd=cwd,
        timeout=timeout,
        env=env,
        input=input_text,
        check=check,
        # No capture_output, no text/encoding, no hidden kwargs: the child owns
        # the inherited console and the parent stays out of the data path.
    )


def interactive_run_captured(
    cmd: Sequence[str],
    *,
    cwd: Optional[str] = None,
    timeout: Optional[float] = None,
    env: Optional[Dict[str, str]] = None,
    input_text: Optional[str] = None,
    check: bool = False,
) -> subprocess.CompletedProcess:
    """Run a command with a **visible console** but **captured** output.

    The explicit opt-in for the rare case that genuinely needs both: the user
    watches the session in its own window while the parent also records the
    transcript for a receipt or a log.

    Output is decoded as UTF-8 with replacement, matching :func:`hidden_run`.
    Prefer :func:`interactive_run` for anything a human must type into, because
    a captured stream is not interactive.
    """
    if not cmd:
        raise ValueError("interactive_run_captured() requires a non-empty command")

    return subprocess.run(
        list(cmd),
        cwd=cwd,
        timeout=timeout,
        env=env,
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=check,
        # Window stays visible: no hidden kwargs by design.
    )


def is_background_command(cmd: Sequence[str]) -> bool:
    """Inverse of :func:`is_interactive_command`. Kept for existing callers."""
    return not is_interactive_command(cmd)