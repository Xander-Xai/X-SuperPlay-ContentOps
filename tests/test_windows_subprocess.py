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
    r = hidden_run([PYTHON, "-c", "print('中文 \\u00e9\\u00e8')"])
    assert r.returncode == 0, r.stderr
    assert "中文" in r.stdout, f"UTF-8 mangled: {r.stdout!r}"
    print("[ok] 5. UTF-8 stdout decoded")


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


def test_policy_catches_forbidden_calls():
    sys.path.insert(0, str(ROOT / "scripts"))
    import check_subprocess_policy as policy

    for name, snippet in VIOLATION_SNIPPETS.items():
        with tempfile.TemporaryDirectory() as td:
            probe = Path(td) / "probe.py"
            probe.write_text(snippet, encoding="utf-8")
            found = policy.scan_file(probe)
            assert found, f"policy failed to flag {name}"
    print(f"[ok] 8. policy flags all {len(VIOLATION_SNIPPETS)} forbidden patterns")


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


def test_background_classification():
    for cmd in (
        ["gh", "api", "repos/o/r"],
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


def test_interactive_run_executes():
    r = process_utils.interactive_run([PYTHON, "-c", "print('interactive-ok')"])
    assert r.returncode == 0, r.stderr
    assert "interactive-ok" in r.stdout
    print("[ok] 9c. interactive_run executes and captures")


def test_interactive_run_does_not_suppress():
    """interactive_run must not add window-suppression kwargs."""
    import inspect
    src = inspect.getsource(process_utils.interactive_run)
    assert "_get_hidden_kwargs" not in src, (
        "interactive_run must leave the console visible"
    )
    print("[ok] 9d. interactive_run leaves the console visible")


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
    test_utf8_replacement_on_invalid_bytes,
    test_binary_mode_returns_bytes,
    test_timeout_raises,
    test_timeout_default_is_bounded,
    test_stderr_captured_on_success,
    test_stderr_captured_on_failure,
    test_stderr_to_file_handle,
    test_policy_catches_forbidden_calls,
    test_policy_allows_process_utils,
    test_policy_ignores_strings_and_comments,
    test_policy_passes_on_repository,
    test_policy_allowlist_entries_have_reasons,
    test_interactive_classification,
    test_background_classification,
    test_interactive_run_executes,
    test_interactive_run_does_not_suppress,
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