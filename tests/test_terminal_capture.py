"""Capture driver contract tests.

No real window is opened and no recording is made here: these tests cover the
plan allowlist, the sanitized environment, wrapper generation and dry-run
behaviour. The one manual Windows capability proof lives in the preflight
receipt.

Run: python tests/test_terminal_capture.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import capture_terminal_evidence as capture_mod  # noqa: E402

CAPTURE = {
    "capture_id": "CAP-20261027-01",
    "command_id": "doctor-json",
    "evidence_class": "EXECUTED",
    "expected_result": "success",
    "read_only": True,
    "cwd": ".",
    "argv": ["python", "scripts/doctor.py", "--json"],
    "env_allow": ["PYTHONUTF8"],
    "max_seconds": 60,
    "fixture_or_cache": "none",
}


def plan(**overrides):
    document = {
        "schema": "contentops.capture-plan/v1",
        "status": "APPROVED",
        "plan_id": "PLAN-20261027-01",
        "project_id": "easel-evidence-capture",
        "permission_scope": "internal_review",
        "environment": {"name": "windows-11"},
        "approved_by": "Founder",
        "approved_at": "2026-10-27T10:00:00Z",
        "preflight": {
            "notifications_disabled": True,
            "audio_disabled": True,
            "terminal_selected": True,
            "readable_dpi": True,
            "no_unrelated_desktop_content": True,
            "checked_by": "Founder",
            "checked_at": "2026-10-27T10:00:00Z",
        },
        "captures": [dict(CAPTURE)],
    }
    document.update(overrides)
    return document


def refuses(code, **overrides):
    try:
        capture_mod.validate_plan(plan(**overrides))
    except capture_mod.CaptureRefused as exc:
        assert exc.code == code, f"expected {code}, got {exc.code}: {exc}"
        return
    raise AssertionError(f"a plan with {overrides} was accepted")


def test_a_draft_plan_is_valid_but_not_executable():
    draft = {
        "schema": "contentops.capture-plan/v1",
        "status": "DRAFT",
        "plan_id": "PLAN-DRAFT-01",
        "project_id": "easel-evidence-capture",
        "captures": [],
    }
    capture_mod.validate_plan(draft)
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "plan.json"
        path.write_text(json.dumps(draft), encoding="utf-8")
        result = capture_mod.run(path, Path(td))
    assert result["status"] == "BLOCKED", result
    assert "DRAFT" in result["reason"]
    print("[ok] 1. a DRAFT plan validates but cannot execute")


def test_preflight_must_be_confirmed_before_capture():
    asserts = dict(plan()["preflight"])
    concerns = [
        ("notifications_disabled", "PREFLIGHT_NOT_CONFIRMED"),
        ("audio_disabled", "PREFLIGHT_NOT_CONFIRMED"),
        ("terminal_selected", "PREFLIGHT_NOT_CONFIRMED"),
        ("readable_dpi", "PREFLIGHT_NOT_CONFIRMED"),
        ("no_unrelated_desktop_content", "PREFLIGHT_NOT_CONFIRMED"),
    ]
    for flag, code in concerns:
        broken = dict(asserts)
        broken[flag] = False
        refuses(code, preflight=broken)
    print("[ok] 2. every preflight flag must be true")


def test_dangerous_commands_are_refused():
    for argv, code in (
        (["curl", "https://example.com"], "EXECUTABLE_NOT_ALLOWED"),
        (["git", "push", "origin", "main"], "COMMAND_DENIED"),
        (["python", "-c", "print('x')"], "COMMAND_DENIED"),
        (["git", "status", "&&", "dir"], "SHELL_METACHARACTER"),
        (["cmd", "/c", "dir"], "EXECUTABLE_NOT_ALLOWED"),
    ):
        refuses(code, captures=[{**CAPTURE, "argv": argv}])
    print("[ok] 3. network, mutation, shell and secret commands are refused")


def test_a_secret_environment_variable_cannot_be_inherited():
    refuses("SECRET_ENV_ALLOWED",
            captures=[{**CAPTURE, "env_allow": ["MINIMAX_API_KEY"]}])
    refuses("SECRET_ENV_ALLOWED",
            captures=[{**CAPTURE, "env_allow": ["GITHUB_TOKEN"]}])
    print("[ok] 4. a key/token/secret variable cannot be allowlisted")


def test_path_tools_are_a_small_allowlist():
    refuses("PATH_TOOL_NOT_ALLOWED",
            captures=[{**CAPTURE, "path_tools": ["curl"]}])
    capture_mod.validate_plan(plan(captures=[{**CAPTURE, "path_tools": ["gh"]}]))
    print("[ok] 4b. only declared helper tools may be added to PATH")


def test_the_hold_after_exit_is_bounded():
    refuses("INVALID_HOLD", captures=[{**CAPTURE, "hold_after_exit_s": 11}])
    refuses("INVALID_HOLD", captures=[{**CAPTURE, "hold_after_exit_s": -1}])
    capture_mod.validate_plan(plan(captures=[{**CAPTURE, "hold_after_exit_s": 5}]))
    print("[ok] 4c. the result hold is bounded and does not change the command")


def test_cwd_and_timeout_are_bounded():
    refuses("CWD_ESCAPE", captures=[{**CAPTURE, "cwd": "../elsewhere"}])
    refuses("INVALID_TIMEOUT", captures=[{**CAPTURE, "max_seconds": 2}])
    refuses("INVALID_TIMEOUT", captures=[{**CAPTURE, "max_seconds": 900}])
    refuses("NOT_READ_ONLY", captures=[{**CAPTURE, "read_only": False}])
    print("[ok] 5. cwd, timeout and read-only are bounded")


def test_the_environment_is_sanitized_to_the_allowlist():
    with tempfile.TemporaryDirectory() as td:
        os.environ["CONTENTOPS_TEST_SECRET"] = "do-not-inherit"
        try:
            env = capture_mod.sanitized_env(
                {"env_allow": ["PYTHONUTF8"], "argv": ["git", "--version"]},
                Path(td))
        finally:
            del os.environ["CONTENTOPS_TEST_SECRET"]
    assert "CONTENTOPS_TEST_SECRET" not in env, env.keys()
    assert env["PYTHONUTF8"] == "1"
    assert env["TEMP"] == td
    for required in ("SYSTEMROOT", "PATH", "COMSPEC"):
        assert required in env, required
    git_dir = Path(shutil.which("git") or "").parent
    if git_dir.name:
        assert str(git_dir) in env["PATH"], (
            "the declared executable's directory is not on the sanitized PATH")
    assert len(env["PATH"].split(os.pathsep)) < 10, (
        "the parent PATH was inherited instead of resolved per executable")
    print("[ok] 6. the environment is minimal and reaches the declared executable")


def test_the_recording_range_starts_at_its_own_zero():
    text = capture_mod._monotonic_range(100.0, 104.5)
    assert text == "00:00.000-00:04.500", text
    print("[ok] 6b. a recording range never reports equal start and end")


def test_the_wrapper_waits_for_go_and_records_the_real_exit_code():
    with tempfile.TemporaryDirectory() as td:
        project = Path(td)
        wrapper, go_file, exit_file = capture_mod.write_wrapper(
            project, dict(CAPTURE), project / "work" / "sessions" / "CAP-1")
        text = wrapper.read_text(encoding="utf-8")
    assert "title CONTENTOPS_CAP_CAP-20261027-01" in text
    assert f'cd /d "{ROOT}"' in text
    assert "wait_for_start" in text
    assert str(go_file) in text
    assert "RC=%ERRORLEVEL%" in text
    assert str(exit_file) in text
    assert "scripts/doctor.py --json" in text
    assert "timeout /t" in text
    print("[ok] 7. the wrapper waits for a start marker and records the exit code")


def test_an_argv_with_spaces_is_quoted_not_interpolated():
    quoted = capture_mod._list2cmdline(
        ["python", "-c", "print('a b')"])
    assert quoted.startswith("python "), quoted
    assert '"' in quoted, quoted
    print("[ok] 8. argv is quoted by list2cmdline, not by string interpolation")


def test_dry_run_writes_no_recording():
    with tempfile.TemporaryDirectory() as td:
        project = Path(td) / "project"
        project.mkdir()
        path = project / "plan.json"
        path.write_text(json.dumps(plan()), encoding="utf-8")
        result = capture_mod.run(path, project, dry_run=True)
        assert result["status"] == "DRY_RUN", result
        assert not (project / "work" / "raw").exists(), (
            "a dry run produced raw media")
        assert result["captures"][0]["argv"] == CAPTURE["argv"]
    print("[ok] 9. a dry run previews the session and records nothing")


def main() -> int:
    failures = []
    tests = (
        test_a_draft_plan_is_valid_but_not_executable,
        test_preflight_must_be_confirmed_before_capture,
        test_dangerous_commands_are_refused,
        test_a_secret_environment_variable_cannot_be_inherited,
        test_path_tools_are_a_small_allowlist,
        test_the_hold_after_exit_is_bounded,
        test_cwd_and_timeout_are_bounded,
        test_the_environment_is_sanitized_to_the_allowlist,
        test_the_recording_range_starts_at_its_own_zero,
        test_the_wrapper_waits_for_go_and_records_the_real_exit_code,
        test_an_argv_with_spaces_is_quoted_not_interpolated,
        test_dry_run_writes_no_recording,
    )
    for fn in tests:
        try:
            fn()
        except AssertionError as exc:
            failures.append((fn.__name__, str(exc)))
            print(f"[FAIL] {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append((fn.__name__, repr(exc)))
            print(f"[ERR ] {fn.__name__}: {exc!r}")
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        return 1
    print(f"\nAll {len(tests)} terminal-capture tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
