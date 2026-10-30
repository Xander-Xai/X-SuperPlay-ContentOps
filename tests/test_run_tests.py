"""The suite runner's own guard: discovery and the CI drift check.

The failure this guards against is the one that started it: a test file that
exists but is never executed, while the gate reports green. That makes the
runner's ability to *tell* whether a suite runs a testable thing — a guard whose
own parser is untested is the same bug one level up.

Run: python tests/test_run_tests.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_tests  # noqa: E402


def test_every_suite_is_discovered_including_the_script_suite():
    names = {path.name for path in run_tests.discover()}
    assert "test_workflow_gate.py" in names, "a known suite is not discovered"
    assert "test_basic.py" in names, "scripts/test_basic.py must be part of the run"


def test_discovery_is_recursive():
    source = (ROOT / "scripts" / "run_tests.py").read_text(encoding="utf-8")
    assert "TESTS.rglob(" in source, "a suite in a tests subdirectory would be invisible"


def test_comments_are_not_commands():
    text = "        # TODO: wire tests/test_hidden.py later\n"
    assert "test_hidden.py" not in run_tests.executed_commands(text)


def test_a_block_scalar_ends_where_the_indent_ends():
    text = "\n".join([
        "      - name: Install",
        "        run: |",
        "          echo installing",
        "      - name: covers tests/test_foo.py (disabled)",
        "        run: echo nothing is executed",
    ])
    commands = run_tests.executed_commands(text)
    assert "echo installing" in commands
    assert "covers tests/test_foo.py" not in commands, commands


def test_a_python_invocation_wires_a_suite():
    assert run_tests.is_wired("test_real.py", "python tests/test_real.py")
    assert run_tests.is_wired("test_basic.py", "python scripts/test_basic.py")


def test_a_suite_named_in_a_step_name_is_not_wired():
    commands = "      - name: covers tests/test_foo.py\n        run: echo nothing"
    assert not run_tests.is_wired("test_foo.py", commands)


def test_a_suite_named_inside_an_echo_is_not_wired():
    commands = 'echo "tests/test_ab_sample_policy.py is not wired yet"'
    assert not run_tests.is_wired("test_ab_sample_policy.py", commands)


def test_a_suffixed_lookalike_file_does_not_wire_a_suite():
    assert not run_tests.is_wired("test_real.py", "python tests/test_real.py.bak")


def test_the_real_workflow_runs_every_suite():
    workflow = ROOT / ".github" / "workflows" / "ci.yml"
    commands = run_tests.executed_commands(workflow.read_text(encoding="utf-8"))
    missing = [p.name for p in run_tests.discover() if not run_tests.is_wired(p.name, commands)]
    assert missing == [], missing


def test_suite_runner_steps_are_separate_yaml_items():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "        run: python tests/test_run_tests.py\n      - name: Check every test suite is wired into CI\n" in workflow
    assert "        run: python scripts/run_tests.py --missing-from .github/workflows/ci.yml\n" in workflow


def main() -> int:
    tests = (
        test_every_suite_is_discovered_including_the_script_suite,
        test_discovery_is_recursive,
        test_comments_are_not_commands,
        test_a_block_scalar_ends_where_the_indent_ends,
        test_a_python_invocation_wires_a_suite,
        test_a_suite_named_in_a_step_name_is_not_wired,
        test_a_suite_named_inside_an_echo_is_not_wired,
        test_a_suffixed_lookalike_file_does_not_wire_a_suite,
        test_the_real_workflow_runs_every_suite,
        test_suite_runner_steps_are_separate_yaml_items,
    )
    failures = []
    for fn in tests:
        try:
            fn()
            print(f"[ok] {fn.__name__}")
        except AssertionError as exc:
            failures.append((fn.__name__, str(exc)))
            print(f"[FAIL] {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append((fn.__name__, repr(exc)))
            print(f"[ERR ] {fn.__name__}: {exc!r}")
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        return 1
    print("\nAll suite-runner tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
