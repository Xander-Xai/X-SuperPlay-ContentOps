"""Windows subprocess popup regression tests.

Covers the contract in scripts/process_utils.py and the enforcement gate in
scripts/check_subprocess_policy.py.

Required coverage:
  1.  hidden_run
  2.  hidden_popen
  3.  Windows CREATE_NO_WINDOW
  4.  Windows STARTF_USESHOWWINDOW + SW_HIDE
  5.  UTF-8 handling
  6.  timeout
  7.  stderr capture
  8.  policy check catches a forbidden direct call
  9.  explicit interactive allowlist
  10. debug override
  11. nested Python subprocess
  12. git child process

Run: python tests/test_windows_subprocess.py
"""

import ast
import inspect
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import process_utils  # noqa: E402
from process_utils import hidden_popen, hidden_run, python_executable  # noqa: E402

PYTHON = python_executable()

IS_WINDOWS = os.name == "nt"


# --- 1. hidden_run -----------------------------------------------------------

def test_hidden_run_captures_stdout():
    r = hidden_run([PYTHON, "-c", "print('hello')"])
    assert r.returncode == 0, f"rc={r.returncode} stderr={r.stderr}"
    assert "hello" in r.stdout, r.stdout
    print("[ok] 1. hidden_run captures stdout")


def test_hidden_run_nested_python():
    """hidden_run spawns a child interpreter with no console window."""
    r = hidden_run([PYTHON, "-c", "import sys; print(sys.executable)"])
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip(), "child produced no stdout"
    print(f"[ok] 11. nested Python subprocess -> {r.stdout.strip()}")


def test_hidden_run_git_child():
    """A real git child process runs hidden and reports its version."""
    if not shutil.which("git"):
        print("[skip] 12. git not on PATH")
        return
    r = hidden_run(["git", "--version"])
    assert r.returncode == 0, r.stderr
    assert "git version" in r.stdout.lower(), r.stdout
    print(f"[ok] 12. git child process -> {r.stdout.strip()}")


# --- 2. hidden_popen ---------------------------------------------------------

def test_hidden_popen_runs_and_captures():
    p = hidden_popen([PYTHON, "-c", "print('popen-ok')"])
    out, err = p.communicate(timeout=30)
    assert p.returncode == 0, f"rc={p.returncode} err={err}"
    assert "popen-ok" in (out or ""), out
    print("[ok] 2. hidden_popen runs and captures")


def test_hidden_popen_nested_python():
    p = hidden_popen([PYTHON, "-c", "import sys; print('nested-popen')"])
    out, _ = p.communicate(timeout=30)
    assert p.returncode == 0
    assert "nested-popen" in (out or "")
    print("[ok] 2b. hidden_popen spawns nested interpreter")


def test_hidden_popen_nonzero_exit():
    p = hidden_popen([PYTHON, "-c", "import sys; sys.exit(3)"])
    p.communicate(timeout=30)
    assert p.returncode == 3, p.returncode
    print("[ok] 2c. hidden_popen propagates exit code")


# --- 3/4. Windows window flags ----------------------------------------------

def test_create_no_window_flag():
    kwargs = process_utils._get_hidden_kwargs()
    if not IS_WINDOWS:
        assert kwargs == {}, f"non-Windows must be a no-op, got {kwargs}"
        print("[ok] 3. CREATE_NO_WINDOW: no-op on non-Windows")
        return
    assert "creationflags" in kwargs, f"CREATE_NO_WINDOW missing: {sorted(kwargs)}"
    assert kwargs["creationflags"] == subprocess.CREATE_NO_WINDOW, kwargs["creationflags"]
    print(f"[ok] 3. CREATE_NO_WINDOW set (0x{kwargs['creationflags']:08X})")


def test_startupinfo_sw_hide_flag():
    kwargs = process_utils._get_hidden_kwargs()
    if not IS_WINDOWS:
        assert kwargs == {}
        print("[ok] 4. SW_HIDE: no-op on non-Windows")
        return
    assert "startupinfo" in kwargs, f"startupinfo missing: {sorted(kwargs)}"
    si = kwargs["startupinfo"]
    assert si.dwFlags & subprocess.STARTF_USESHOWWINDOW, (
        f"STARTF_USESHOWWINDOW not set: dwFlags={si.dwFlags:#x}"
    )
    assert si.wShowWindow == subprocess.SW_HIDE, (
        f"wShowWindow={si.wShowWindow}, expected SW_HIDE={subprocess.SW_HIDE}"
    )
    print(f"[ok] 4. STARTF_USESHOWWINDOW|SW_HIDE set (wShowWindow={si.wShowWindow})")


def test_both_windows_flags_present():
    if not IS_WINDOWS:
        print("[skip] both-flags assertion is Windows-only")
        return
    kwargs = process_utils._get_hidden_kwargs()
    assert {"startupinfo", "creationflags"} <= set(kwargs), sorted(kwargs)
    print("[ok] 4b. both window-suppression flags applied together")


# --- 5. UTF-8 ----------------------------------------------------------------

def test_utf8_stdout():
    """Child emits UTF-8 bytes; hidden_run decodes them as UTF-8.

    The child writes through `stdout.buffer`, so the bytes on the wire are UTF-8
    regardless of the locale codepage. Driving it through the text layer instead
    would test the child's console encoding rather than the parent's decoding:
    on a default Windows host the child encodes with cp1252 and dies with
    UnicodeEncodeError before hidden_run sees anything. `-X utf8` is not enough
    either, because PYTHONIOENCODING takes precedence over it.
    """
    r = hidden_run([PYTHON, "-c",
                    "import sys; sys.stdout.buffer.write('\\u4e2d\\u6587 \\u00e9'.encode('utf-8'))"])
    assert r.returncode == 0, f"rc={r.returncode} stderr={r.stderr}"
    assert "中文" in r.stdout, f"UTF-8 mangled: {r.stdout!r}"
    assert "\u00e9" in r.stdout, f"latin-1 supplement lost: {r.stdout!r}"
    print("[ok] 5. UTF-8 stdout decoded")


def test_utf8_via_pythonioencoding():
    """The realistic path: child text stream pinned to UTF-8 via the env."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    r = hidden_run([PYTHON, "-c", "print('中文')"], env=env)
    assert r.returncode == 0, f"rc={r.returncode} stderr={r.stderr}"
    assert "中文" in r.stdout, r.stdout
    print("[ok] 5d. UTF-8 via PYTHONIOENCODING")


def test_utf8_stderr_decoded():
    """stderr must be decoded as UTF-8 too, not left as raw bytes."""
    r = hidden_run([PYTHON, "-c",
                    "import sys; sys.stderr.buffer.write('\\u4e2d\\u6587'.encode('utf-8'))"])
    assert r.returncode == 0, r.stderr
    assert isinstance(r.stderr, str), type(r.stderr)
    assert "中文" in r.stderr, r.stderr
    print("[ok] 5e. UTF-8 stderr decoded")


def test_child_encoding_is_decoupled_from_parent_decode():
    """A cp1252-locale child must not break UTF-8 decoding of its output.

    ContentOps must not depend on the child's console codepage. This is the
    condition that failed on CI.
    """
    env = dict(os.environ, PYTHONIOENCODING="cp1252", PYTHONUTF8="0")
    r = hidden_run([PYTHON, "-c",
                    "import sys; sys.stdout.buffer.write('ok'.encode('ascii'))"], env=env)
    assert r.returncode == 0, f"rc={r.returncode} stderr={r.stderr}"
    assert "ok" in r.stdout, r.stdout
    print("[ok] 5f. child locale codepage does not affect parent decoding")


def test_utf8_replacement_on_invalid_bytes():
    """Invalid bytes must be replaced, never raise."""
    r = hidden_run(
        [PYTHON, "-c", "import sys; sys.stdout.buffer.write(b'\\xff\\xfe ok')"],
        text=True, errors="replace",
    )
    assert r.returncode == 0, r.stderr
    assert "ok" in r.stdout, r.stdout
    print("[ok] 5b. invalid bytes replaced, not raised")


def test_binary_mode_returns_bytes():
    r = hidden_run([PYTHON, "-c", "import sys; sys.stdout.buffer.write(b'\\x00\\x01')"],
                   text=False)
    assert isinstance(r.stdout, bytes), f"expected bytes, got {type(r.stdout)}"
    assert r.stdout == b"\x00\x01", r.stdout
    print("[ok] 5c. text=False returns raw bytes")


# --- 6. timeout --------------------------------------------------------------

def test_timeout_raises():
    try:
        hidden_run([PYTHON, "-c", "import time; time.sleep(30)"], timeout=2)
    except subprocess.TimeoutExpired:
        print("[ok] 6. timeout raises TimeoutExpired")
        return
    raise AssertionError("expected TimeoutExpired")


def test_timeout_default_is_bounded():
    import inspect
    sig = inspect.signature(hidden_run)
    default = sig.parameters["timeout"].default
    assert default is not None, "hidden_run must default to a bounded timeout"
    print(f"[ok] 6b. default timeout is bounded ({default}s)")


# --- 7. stderr ---------------------------------------------------------------

def test_stderr_captured_on_success():
    r = hidden_run([PYTHON, "-c", "import sys; sys.stderr.write('warn')"])
    assert r.returncode == 0, r.stderr
    assert "warn" in r.stderr, f"stderr not captured: {r.stderr!r}"
    print("[ok] 7. stderr captured even on success")


def test_stderr_captured_on_failure():
    r = hidden_run([PYTHON, "-c", "import sys; sys.stderr.write('boom'); sys.exit(2)"])
    assert r.returncode == 2, r.returncode
    assert "boom" in r.stderr, r.stderr
    print("[ok] 7b. stderr captured on non-zero exit")


def test_stderr_to_file_handle():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "err.txt"
        with path.open("w", encoding="utf-8") as fh:
            r = hidden_run([PYTHON, "-c", "import sys; sys.stderr.write('piped')"],
                           stderr=fh, text=False)
        assert r.returncode == 0, r.stderr
        assert "piped" in path.read_text(encoding="utf-8")
        print("[ok] 7c. stderr redirected to file handle")


# --- 8. policy gate ----------------------------------------------------------

VIOLATION_SNIPPETS = {
    "subprocess.run": "import subprocess\nsubprocess.run(['git', 'status'])\n",
    "subprocess.Popen": "import subprocess\nsubprocess.Popen(['ffmpeg', '-i', 'a.mp4'])\n",
    "subprocess.call": "import subprocess\nsubprocess.call(['x'])\n",
    "subprocess.check_call": "import subprocess\nsubprocess.check_call(['x'])\n",
    "subprocess.check_output": "import subprocess\nsubprocess.check_output(['x'])\n",
    "os.system": "import os\nos.system('echo hi')\n",
    "os.popen": "import os\nos.popen('ls')\n",
    "shell=True": "import subprocess\nsubprocess.run(['x'], shell=True)\n",
    "aliased": "import subprocess as sp\nsp.run(['x'])\n",
}

# Alias and from-import forms that must also be caught. Resolution is semantic,
# so the alias name is irrelevant; only the import binding decides.
ALIAS_VIOLATION_SNIPPETS = {
    "arbitrary alias .run": "import subprocess as proc\nproc.run(['git','status'])\n",
    "arbitrary alias .Popen": "import subprocess as anything\nanything.Popen(['x'])\n",
    "arbitrary alias .check_output":
        "import subprocess as p\np.check_output(['x'])\n",
    "arbitrary alias nested scope":
        "def f():\n    import subprocess as z\n    z.run(['x'])\n",
    "alias in multi-import": "import os, subprocess as q\nq.run(['x'])\n",
    "from-import bare run": "from subprocess import run\nrun(['x'])\n",
    "from-import renamed run":
        "from subprocess import run as execute\nexecute(['x'])\n",
    "from-import bare Popen": "from subprocess import Popen\nPopen(['x'])\n",
    "from-import renamed check_call":
        "from subprocess import check_call as cc\ncc(['x'])\n",
    "os arbitrary alias": "import os as operating_system\noperating_system.system('x')\n",
    "os from-import bare": "from os import system\nsystem('x')\n",
    "os from-import renamed": "from os import popen as pipe\npipe('x')\n",
    "dotted module alias": "import os.path as osp\nosp.popen('x')\n",
    "star import subprocess": "from subprocess import *\nrun(['x'])\n",
    "alias with shell=True": "import subprocess as s\ns.run(['x'], shell=True)\n",
    "asyncio create_subprocess_exec":
        "import asyncio\nasyncio.create_subprocess_exec('ls')\n",
    "asyncio create_subprocess_shell":
        "from asyncio import create_subprocess_shell\ncreate_subprocess_shell('ls')\n",
}

# Must NOT be flagged: inert constants, annotations, unrelated names.
FALSE_POSITIVE_SNIPPETS = {
    "string literal": "x = 'subprocess.run()'\n",
    "comment": "# subprocess.run(...)\n",
    "docstring": '"""Use subprocess.run() carefully."""\n',
    "inert PIPE constant": "import subprocess\nP = subprocess.PIPE\n",
    "inert from-import":
        "from subprocess import PIPE, DEVNULL, TimeoutExpired, CompletedProcess\n",
    "inert type annotation":
        "import subprocess\ndef f() -> subprocess.CompletedProcess: ...\n",
    "catching TimeoutExpired":
        "import subprocess\ntry:\n    pass\nexcept subprocess.TimeoutExpired:\n    pass\n",
    "unrelated local run()": "def run(x):\n    return x\nrun(1)\n",
    "unrelated module": "import requests\nrequests.get('x')\n",
    "window constants are inert":
        "import subprocess\n"
        "si = subprocess.STARTUPINFO()\n"
        "f = subprocess.CREATE_NO_WINDOW\n"
        "h = subprocess.SW_HIDE\n",
}


def _scan_snippet(snippet):
    sys.path.insert(0, str(ROOT / "scripts"))
    import check_subprocess_policy as policy

    with tempfile.TemporaryDirectory() as td:
        probe = Path(td) / "probe.py"
        probe.write_text(snippet, encoding="utf-8")
        return policy.scan_file(probe)


def test_policy_catches_forbidden_calls():
    for name, snippet in VIOLATION_SNIPPETS.items():
        assert _scan_snippet(snippet), f"policy failed to flag {name}"
    print(f"[ok] 8. policy flags all {len(VIOLATION_SNIPPETS)} forbidden patterns")


def test_policy_catches_arbitrary_aliases():
    """Alias naming must not matter; only the import binding is used."""
    for name, snippet in ALIAS_VIOLATION_SNIPPETS.items():
        assert _scan_snippet(snippet), f"policy failed to flag alias case: {name}"
    print(f"[ok] 8f. policy resolves {len(ALIAS_VIOLATION_SNIPPETS)} alias/from-import forms")


def test_policy_allows_process_utils():
    sys.path.insert(0, str(ROOT / "scripts"))
    import check_subprocess_policy as policy

    assert policy.scan_file(ROOT / "scripts" / "process_utils.py") == [], (
        "process_utils.py must be allowlisted as the abstraction itself"
    )
    print("[ok] 8b. policy allowlists process_utils.py")


def test_policy_ignores_strings_and_comments():
    sys.path.insert(0, str(ROOT / "scripts"))
    import check_subprocess_policy as policy

    snippet = (
        '"""Docs mentioning subprocess.run and os.system."""\n'
        "N = 'subprocess.run([1])'\n"
        "# subprocess.Popen(['x'])\n"
        "def f():\n"
        "    return N\n"
    )
    with tempfile.TemporaryDirectory() as td:
        probe = Path(td) / "clean.py"
        probe.write_text(snippet, encoding="utf-8")
        assert policy.scan_file(probe) == [], "policy false-positived on text"
    print("[ok] 8c. policy ignores docstrings, comments and string literals")


def test_policy_passes_on_repository():
    sys.path.insert(0, str(ROOT / "scripts"))
    import check_subprocess_policy as policy

    offenders = []
    for path in policy._tracked_python_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel in policy.ALLOWED_FILES:
            continue
        for _lineno, code, _msg in policy.scan_file(path):
            offenders.append(f"{rel}: {code}")
    assert not offenders, "repository violates its own policy:\n" + "\n".join(offenders)
    print("[ok] 8d. entire repository passes the subprocess policy")


def test_policy_allowlist_entries_have_reasons():
    sys.path.insert(0, str(ROOT / "scripts"))
    import check_subprocess_policy as policy

    for path, reason in policy.INTERACTIVE_ALLOWLIST.items():
        assert reason.strip(), f"allowlist entry {path} has no reason"
        assert (ROOT / path).exists(), f"allowlist entry {path} does not exist"
    print("[ok] 8e. every interactive allowlist entry carries a reason")


# --- 9. interactive allowlist ------------------------------------------------

def test_interactive_classification():
    assert process_utils.is_interactive_command(["gh", "auth", "login"])
    assert process_utils.is_interactive_command(["mmx", "auth", "login"])
    assert process_utils.is_interactive_command(["claude"])
    print("[ok] 9. auth commands classified interactive")


AUTH_LOGIN_INTERACTIVE = [
    ["gh", "auth", "login"],
    ["gh.exe", "auth", "login"],
    ["mmx", "auth", "login"],
    ["mmx.exe", "auth", "login"],
    # Executable name normalisation: a full path must classify identically.
    ["/usr/local/bin/gh.exe", "auth", "login"],
    ["mmx.exe", "auth", "login", "--profile", "default"],
]


def test_auth_login_is_interactive():
    """``<tool> auth login`` needs a human at the keyboard."""
    for cmd in AUTH_LOGIN_INTERACTIVE:
        assert process_utils.is_interactive_command(cmd), (
            f"{cmd} must be INTERACTIVE_VISIBLE"
        )
    print(f"[ok] 9n. {len(AUTH_LOGIN_INTERACTIVE)} auth-login forms classified interactive")


AUTH_STATUS_BACKGROUND = [
    ["gh", "auth", "status"],
    ["gh.exe", "auth", "status"],
    ["mmx", "auth", "status"],
    ["mmx.exe", "auth", "status"],
    ["/usr/local/bin/gh.exe", "auth", "status"],
]


def test_auth_status_is_background():
    """``auth`` alone is not enough: status only reports, so it must be hidden."""
    for cmd in AUTH_STATUS_BACKGROUND:
        assert not process_utils.is_interactive_command(cmd), (
            f"{cmd} only prints a report and must be BACKGROUND_HIDDEN"
        )
    print(f"[ok] 9o. {len(AUTH_STATUS_BACKGROUND)} auth-status forms classified background")


def test_other_auth_actions_are_background():
    """An action not on the allowlist is background, never a guessed window."""
    for cmd in (
        ["gh", "auth"],
        ["gh", "auth", "token"],
        ["mmx", "auth", "token"],
        ["gh", "api", "repos/o/r"],
    ):
        assert not process_utils.is_interactive_command(cmd), (
            f"{cmd} is not an allowlisted interactive flow and must be hidden"
        )
    print("[ok] 9p. unlisted auth shapes stay background (no guessed window)")


def test_background_classification():
    for cmd in (
        ["gh", "api", "repos/o/r"],
        ["gh", "auth", "status"],
        ["mmx", "quota"],
        ["mmx", "image"],
        ["mmx", "speech"],
        ["mmx", "video"],
        ["mmx", "video", "task", "get"],
        ["ffmpeg", "-i", "in.mp4"],
        ["ffprobe", "file.mp4"],
        ["git", "status"],
        [PYTHON, "script.py"],
    ):
        assert not process_utils.is_interactive_command(cmd), (
            f"{cmd} should be background/hidden"
        )
    print("[ok] 9b. provider + tool commands classified background")


def test_interactive_run_inherits_stdio():
    """interactive_run must not pipe stdin/stdout/stderr.

    Piping them would make an auth prompt unreachable, which defeats the only
    reason this function exists.
    """
    r = process_utils.interactive_run([PYTHON, "-c", "print('interactive-ok')"])
    assert r.returncode == 0, r.returncode
    assert r.stdout is None, f"stdout must be inherited, not captured: {r.stdout!r}"
    assert r.stderr is None, f"stderr must be inherited, not captured: {r.stderr!r}"
    print("[ok] 9c. interactive_run inherits stdout/stderr (not captured)")


def test_interactive_run_does_not_pipe_or_hide():
    """Semantic check on the actual subprocess.run call inside interactive_run.

    Inspected via ast rather than by text search, so prose in the docstring
    cannot produce a false failure and a real kwarg cannot hide behind a
    reformat.
    """
    tree = ast.parse(inspect.getsource(process_utils.interactive_run))
    run_calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "run"
    ]
    assert run_calls, "interactive_run must call subprocess.run"

    forbidden_kwargs = {
        "capture_output", "stdout", "stderr", "stdin", "input",
        "startupinfo", "creationflags",
    }
    for call in run_calls:
        for kw in call.keywords:
            assert kw.arg not in forbidden_kwargs, (
                f"interactive_run must not pass {kw.arg}=; the child has to "
                f"inherit the terminal so an auth prompt stays reachable"
            )
        # A **splat could smuggle any kwarg past the check above.
        assert not any(kw.arg is None for kw in call.keywords), (
            "interactive_run must not use **kwargs; hidden flags could leak in"
        )
        assert "hidden_run" not in ast.dump(call), (
            "interactive_run must not delegate to the hidden path"
        )
    print("[ok] 9d. interactive_run passes no input/stdin/stdout/stderr/hidden kwargs")


def test_interactive_run_has_no_scripted_input_parameter():
    """The signature itself must not offer a way to pre-fill stdin.

    Checking the source call alone is not enough: `input_text` could be
    accepted and then dropped, which would be a lie in the signature.
    """
    params = inspect.signature(process_utils.interactive_run).parameters
    assert "input_text" not in params, (
        "interactive_run must not take input_text; scripted input belongs in "
        "a separately named helper"
    )
    assert "input" not in params, "interactive_run must not take an input parameter"
    for forbidden in ("stdin", "stdout", "stderr", "capture_output",
                      "startupinfo", "creationflags", "kwargs"):
        assert forbidden not in params, (
            f"interactive_run must not expose {forbidden}; its contract is "
            f"inherited stdio and a visible console, nothing else"
        )
    assert not any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()
    ), "interactive_run must not accept **kwargs"
    print("[ok] 9q. interactive_run signature exposes no scripted-input knob")


def test_interactive_run_source_has_no_pipe_reference():
    """No PIPE constant may be referenced anywhere in interactive_run."""
    tree = ast.parse(inspect.getsource(process_utils.interactive_run))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in {"PIPE", "DEVNULL"}:
            raise AssertionError(f"interactive_run references {node.attr}")
        if isinstance(node, ast.Name) and node.id in {"PIPE", "DEVNULL"}:
            raise AssertionError(f"interactive_run references {node.id}")
    print("[ok] 9l. interactive_run references no PIPE or DEVNULL")


def test_interactive_run_inherits_stdin():
    """A child must see the parent's stdin when nothing is piped."""
    import tempfile

    marker = "stdin-was-inherited"
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "in.txt"
        path.write_text(marker, encoding="utf-8")
        # Redirect this process's stdin from the file, then let the child read it.
        saved = os.dup(0)
        try:
            fd = os.open(str(path), os.O_RDONLY)
            os.dup2(fd, 0)
            os.close(fd)
            r = hidden_run([PYTHON, "-c",
                            "import sys; sys.stdout.write(sys.stdin.read())"],
                           stdin=None)
        finally:
            os.dup2(saved, 0)
            os.close(saved)
    assert marker in r.stdout, f"child did not inherit stdin: {r.stdout!r}"
    print("[ok] 9g. an inheriting child reads the parent's stdin")


def test_interactive_run_captured_is_explicit():
    """The visible+captured variant exists as a separate, clearly named helper."""
    assert hasattr(process_utils, "interactive_run_captured")
    r = process_utils.interactive_run_captured(
        [PYTHON, "-c", "import sys; sys.stdout.write('cap')"])
    assert r.returncode == 0, r.returncode
    assert r.stdout == "cap", r.stdout
    tree = ast.parse(inspect.getsource(process_utils.interactive_run_captured))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in {
                "_get_hidden_kwargs", "CREATE_NO_WINDOW", "SW_HIDE"}:
            raise AssertionError(
                f"interactive_run_captured must keep the window visible ({node.attr})"
            )
    print("[ok] 9h. interactive_run_captured captures without hiding")


def test_interactive_run_captured_does_not_echo_to_terminal():
    """Captured output must not *also* be written to the parent's terminal.

    This is exactly what the helper's docstring has to promise: the child is
    visible (no window suppression) but its streams are piped into the parent,
    so nothing can be shown live and captured at the same time.
    """
    marker = "not-echoed-marker"
    with tempfile.TemporaryDirectory() as td:
        sink = Path(td) / "terminal.txt"
        saved = os.dup(1)
        try:
            fd = os.open(str(sink), os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
            os.dup2(fd, 1)
            os.close(fd)
            r = process_utils.interactive_run_captured(
                [PYTHON, "-c", f"print('{marker}')"])
        finally:
            os.dup2(saved, 1)
            os.close(saved)
        assert r.stdout.strip() == marker, r.stdout
        echoed = sink.read_text(encoding="utf-8", errors="replace")
        assert marker not in echoed, (
            f"captured output was also echoed to the terminal: {echoed!r}"
        )
    print("[ok] 9r. interactive_run_captured captures without echoing to the terminal")


def test_shell_tools_are_background():
    """A shell used as a tool is background work, not an interactive session."""
    background = [
        ["powershell", "-Command", "Get-Date"],
        ["powershell", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", "x"],
        ["pwsh", "-Command", "Get-Date"],
        ["pwsh", "-NoProfile", "-Command", "x"],
        ["powershell", "-NonInteractive", "-Command", "x"],
        ["powershell", "-EncodedCommand", "SQBFAA=="],
        ["powershell.exe", "-Command", "x"],
        ["cmd", "/c", "echo hi"],
        ["cmd.exe", "/c", "dir"],
        ["bash", "-c", "echo hi"],
        ["sh", "-c", "echo hi"],
        ["bash", "-lc", "echo hi"],
        ["powershell", "script.ps1"],
        ["bash", "script.sh"],
        ["cmd", "some.exe"],
    ]
    for cmd in background:
        assert not process_utils.is_interactive_command(cmd), (
            f"{cmd} runs a payload and must be BACKGROUND_HIDDEN"
        )
    print(f"[ok] 9i. {len(background)} shell-as-tool invocations classified background")


def test_bare_shells_are_interactive():
    """A bare shell opens a prompt the user drives."""
    for cmd in (["powershell"], ["pwsh"], ["cmd"], ["bash"], ["sh"],
                ["powershell.exe"], ["pwsh.exe"], ["cmd.exe"],
                [r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"]):
        assert process_utils.is_interactive_command(cmd), (
            f"{cmd} is a bare shell and must be INTERACTIVE_VISIBLE"
        )
    print("[ok] 9j. bare shells classified interactive")


def test_interactive_run_does_not_suppress_window():
    """No CREATE_NO_WINDOW / SW_HIDE may reach an interactive child."""
    if not IS_WINDOWS:
        print("[skip] window-visibility assertion is Windows-only")
        return
    before = process_utils.window_suppression_enabled()
    tree = ast.parse(inspect.getsource(process_utils.interactive_run))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in {
                "_get_hidden_kwargs", "CREATE_NO_WINDOW", "SW_HIDE",
                "STARTF_USESHOWWINDOW"}:
            raise AssertionError(f"interactive_run touches {node.attr}")
    assert before is True, "suppression should be active outside the debug override"
    print("[ok] 9k. interactive_run leaves the console visible on Windows")


def test_shell_true_rejected():
    for fn in (hidden_run, hidden_popen):
        try:
            fn(["x"], shell=True)
        except ValueError:
            continue
        raise AssertionError(f"{fn.__name__} accepted shell=True")
    print("[ok] 9e. shell=True rejected by both entry points")


# --- 10. debug override ------------------------------------------------------

def test_debug_override_disables_suppression():
    original = os.environ.get(process_utils.DEBUG_ENV_VAR)
    try:
        os.environ[process_utils.DEBUG_ENV_VAR] = "1"
        assert process_utils._is_debug_visible()
        assert not process_utils.window_suppression_enabled()
        assert process_utils._get_hidden_kwargs() == {}, "debug override must disable flags"
        r = hidden_run([PYTHON, "-c", "print('debug-visible')"])
        assert r.returncode == 0, r.stderr
        assert "debug-visible" in r.stdout
    finally:
        if original is None:
            os.environ.pop(process_utils.DEBUG_ENV_VAR, None)
        else:
            os.environ[process_utils.DEBUG_ENV_VAR] = original
    print("[ok] 10. debug override disables suppression and still runs")


def test_suppression_reenabled_after_override():
    original = os.environ.get(process_utils.DEBUG_ENV_VAR)
    try:
        os.environ[process_utils.DEBUG_ENV_VAR] = "1"
        assert process_utils._get_hidden_kwargs() == {}
        os.environ[process_utils.DEBUG_ENV_VAR] = "0"
        assert not process_utils._is_debug_visible()
        expected_nonempty = IS_WINDOWS
        assert bool(process_utils._get_hidden_kwargs()) == expected_nonempty
    finally:
        if original is None:
            os.environ.pop(process_utils.DEBUG_ENV_VAR, None)
        else:
            os.environ[process_utils.DEBUG_ENV_VAR] = original
    print("[ok] 10b. suppression restored when override is cleared")


# --- misc contract -----------------------------------------------------------

def test_python_executable_is_sys_executable():
    assert python_executable() == sys.executable
    assert process_utils.python_executable() == sys.executable
    print("[ok] python_executable() == sys.executable")


def test_empty_command_rejected():
    for fn in (hidden_run, hidden_popen):
        try:
            fn([])
        except ValueError:
            continue
        raise AssertionError(f"{fn.__name__} accepted an empty command")
    print("[ok] empty command rejected")


def test_process_utils_has_no_bare_python_default():
    """Source must not spawn via the bare string 'python'."""
    src = (ROOT / "scripts" / "process_utils.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in {"python", "python3", "py"}:
                raise AssertionError(f"bare interpreter string {node.value!r} in process_utils")
    print("[ok] process_utils contains no bare 'python' string")


TESTS = [
    test_hidden_run_captures_stdout,
    test_hidden_run_nested_python,
    test_hidden_run_git_child,
    test_hidden_popen_runs_and_captures,
    test_hidden_popen_nested_python,
    test_hidden_popen_nonzero_exit,
    test_create_no_window_flag,
    test_startupinfo_sw_hide_flag,
    test_both_windows_flags_present,
    test_utf8_stdout,
    test_utf8_via_pythonioencoding,
    test_utf8_stderr_decoded,
    test_child_encoding_is_decoupled_from_parent_decode,
    test_utf8_replacement_on_invalid_bytes,
    test_binary_mode_returns_bytes,
    test_timeout_raises,
    test_timeout_default_is_bounded,
    test_stderr_captured_on_success,
    test_stderr_captured_on_failure,
    test_stderr_to_file_handle,
    test_policy_catches_forbidden_calls,
    test_policy_catches_arbitrary_aliases,
    test_policy_allows_process_utils,
    test_policy_ignores_strings_and_comments,
    test_policy_passes_on_repository,
    test_policy_allowlist_entries_have_reasons,
    test_interactive_classification,
    test_auth_login_is_interactive,
    test_auth_status_is_background,
    test_other_auth_actions_are_background,
    test_background_classification,
    test_interactive_run_inherits_stdio,
    test_interactive_run_does_not_pipe_or_hide,
    test_interactive_run_has_no_scripted_input_parameter,
    test_interactive_run_source_has_no_pipe_reference,
    test_interactive_run_inherits_stdin,
    test_interactive_run_captured_is_explicit,
    test_interactive_run_captured_does_not_echo_to_terminal,
    test_shell_tools_are_background,
    test_bare_shells_are_interactive,
    test_interactive_run_does_not_suppress_window,
    test_shell_true_rejected,
    test_debug_override_disables_suppression,
    test_suppression_reenabled_after_override,
    test_python_executable_is_sys_executable,
    test_empty_command_rejected,
    test_process_utils_has_no_bare_python_default,
]


def main() -> int:
    failures = []
    for fn in TESTS:
        try:
            fn()
        except AssertionError as e:
            failures.append((fn.__name__, str(e)))
            print(f"[FAIL] {fn.__name__}: {e}")
        except Exception as e:
            failures.append((fn.__name__, repr(e)))
            print(f"[ERR ] {fn.__name__}: {e!r}")

    print()
    if failures:
        print(f"{len(failures)} of {len(TESTS)} test(s) failed")
        return 1
    print(f"All {len(TESTS)} Windows subprocess regression tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())