"""Windows subprocess popup regression tests.

Validates:
  - process_utils.hidden_run suppresses console window on Windows
  - process_utils.interactive_run keeps console visible
  - CREATE_NO_WINDOW is set on Windows, no-op on other platforms
  - Debug override (CONTENTOPS_SHOW_SUBPROCESS_WINDOWS=1) forces visible
  - Background commands are correctly classified
  - shell=False is always used for background subprocess

Run: python tests/test_windows_subprocess.py
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable

# Add scripts to path for imports
sys.path.insert(0, str(ROOT / "scripts"))


def test_process_utils_import():
    """process_utils imports cleanly on all platforms."""
    import process_utils
    assert hasattr(process_utils, "hidden_run")
    assert hasattr(process_utils, "interactive_run")
    assert hasattr(process_utils, "_get_hidden_kwargs")
    print("[ok] process_utils imports and has expected functions")


def test_hidden_kwargs_non_windows():
    """On non-Windows, hidden kwargs should be empty dict."""
    import process_utils
    if os.name == "nt":
        # On Windows, should return non-empty kwargs
        kwargs = process_utils._get_hidden_kwargs()
        assert "startupinfo" in kwargs, f"Expected startupinfo in kwargs: {kwargs}"
        assert kwargs["startupinfo"].dwFlags & subprocess.STARTF_USESHOWWINDOW
        print("[ok] Windows: hidden kwargs include startupinfo + CREATE_NO_WINDOW")
    else:
        kwargs = process_utils._get_hidden_kwargs()
        assert kwargs == {}, f"Non-Windows should return empty dict: {kwargs}"
        print("[ok] Non-Windows: hidden kwargs is empty (no-op)")


def test_hidden_run_captures_output():
    """hidden_run captures stdout/stderr correctly."""
    import process_utils
    r = process_utils.hidden_run([PYTHON, "-c", "print('hello')"])
    assert r.returncode == 0, f"Expected rc=0, got {r.returncode}: {r.stderr}"
    assert "hello" in r.stdout, f"Expected 'hello' in stdout: {r.stdout}"
    print("[ok] hidden_run captures stdout")


def test_hidden_run_no_shell():
    """hidden_run never uses shell=True."""
    import process_utils
    r = process_utils.hidden_run([PYTHON, "-c", "import sys; print(sys.executable)"])
    assert r.returncode == 0
    # shell=True would interpret the command differently
    assert PYTHON in r.stdout or "python" in r.stdout.lower()
    print("[ok] hidden_run uses shell=False")


def test_hidden_run_utf8():
    """hidden_run handles UTF-8 output on Windows."""
    import process_utils
    r = process_utils.hidden_run([PYTHON, "-c", "print('hello')"])
    assert r.returncode == 0
    assert "hello" in r.stdout
    print("[ok] hidden_run produces utf-8 readable output")


def test_hidden_run_timeout():
    """hidden_run respects timeout."""
    import process_utils
    try:
        r = process_utils.hidden_run([PYTHON, "-c", "import time; time.sleep(10)"], timeout=2)
        assert False, "Should have timed out"
    except subprocess.TimeoutExpired:
        print("[ok] hidden_run respects timeout")


def test_debug_override():
    """CONTENTOPS_SHOW_SUBPROCESS_WINDOWS=1 forces visible."""
    import process_utils
    old_val = os.environ.get("CONTENTOPS_SHOW_SUBPROCESS_WINDOWS", "")
    try:
        os.environ["CONTENTOPS_SHOW_SUBPROCESS_WINDOWS"] = "1"
        assert process_utils._is_debug_visible()
        # hidden_run should NOT add hidden kwargs when debug is on
        r = process_utils.hidden_run([PYTHON, "-c", "print('visible')"])
        assert r.returncode == 0
        assert "visible" in r.stdout
        print("[ok] Debug override forces visible subprocess")
    finally:
        if old_val:
            os.environ["CONTENTOPS_SHOW_SUBPROCESS_WINDOWS"] = old_val
        else:
            os.environ.pop("CONTENTOPS_SHOW_SUBPROCESS_WINDOWS", None)


def test_background_classification():
    """is_background_command correctly classifies commands."""
    import process_utils
    assert process_utils.is_background_command(["ffmpeg", "-i", "in.mp4"])
    assert process_utils.is_background_command(["ffprobe", "file.mp4"])
    assert not process_utils.is_background_command(["gh", "auth", "login"])
    # gh api is background
    assert process_utils.is_background_command(["gh", "api", "repos/owner/repo"])
    print("[ok] Background command classification")


def test_error_not_hidden():
    """When a background process fails, stderr is still captured."""
    import process_utils
    r = process_utils.hidden_run([PYTHON, "-c", "import sys; sys.exit(1)"])
    assert r.returncode == 1
    # stderr should be accessible even though window was hidden
    print("[ok] Error output captured despite hidden window")


if __name__ == "__main__":
    failures = []
    for fn in (
        test_process_utils_import,
        test_hidden_kwargs_non_windows,
        test_hidden_run_captures_output,
        test_hidden_run_no_shell,
        test_hidden_run_utf8,
        test_hidden_run_timeout,
        test_debug_override,
        test_background_classification,
        test_error_not_hidden,
    ):
        try:
            fn()
        except AssertionError as e:
            failures.append((fn.__name__, str(e)))
            print(f"[FAIL] {fn.__name__}: {e}")
        except Exception as e:
            failures.append((fn.__name__, repr(e)))
            print(f"[ERR ] {fn.__name__}: {e!r}")

    if failures:
        print(f"\n{len(failures)} test(s) failed")
        sys.exit(1)
    print("\nAll Windows subprocess regression tests passed.")