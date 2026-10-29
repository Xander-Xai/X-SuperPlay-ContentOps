#!/usr/bin/env python3
"""Unified developer gate for humans and Claude Code.

Runs before every commit / PR.

Order:
  1. repo_policy_check
  2. subprocess_policy_check
  3. check_docs
  4. check_i18n
  5. check_account_dna
  6. check_script_quality (only projects that declare quality_gate: enforced)
  7. test_basic
  8. test_suites (every tests/test_*.py, discovered)
  9. git diff --check (whitespace)

All must pass. All checks are read-only and deterministic.

The suites are discovered rather than listed because this gate once printed
"ALL CHECKS PASSED" while a migration suite was failing: it had never been
called. A test file that is not executed cannot report a pass, and this gate is
the last thing standing between a change and a commit.

Usage:
  python scripts/dev_check.py          # full check
  python scripts/dev_check.py --quick  # skip repo policy + test suites (for speed)
"""

import argparse
import sys
from pathlib import Path

from process_utils import hidden_run, python_executable

ROOT = Path(__file__).resolve().parents[1]


def run_check(name: str, cmd: list[str], timeout: int = 300) -> bool:
    print(f"\n=== {name} ===")
    r = hidden_run(cmd, cwd=str(ROOT), timeout=timeout)
    if r.stdout:
        print(_console_safe(_clip(r.stdout)))
    if r.returncode != 0 and r.stderr:
        print(_console_safe(_clip(r.stderr, head=300, tail=700)))
    ok = r.returncode == 0
    print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    return ok


def _clip(text: str, head: int = 800, tail: int = 1200) -> str:
    """Keep both ends of a long check output, with the elision marked.

    A flat `stdout[:2000]` cut the tail off the suite run, which is exactly
    where the failing-suite names and the "N/M suites passed" line live: the
    gate failed and showed only the suites that had already passed.
    """
    if len(text) <= head + tail:
        return text
    omitted = len(text) - head - tail
    return f"{text[:head]}\n... [{omitted} chars omitted] ...\n{text[-tail:]}"


def _console_safe(text: str) -> str:
    """Make captured output printable whatever the console encoding is.

    A check that fails while printing non-ASCII (an em dash in a docs-check
    failure line was the measured case) used to crash this gate with
    UnicodeEncodeError *instead of reporting the failing check* -- a gate that
    dies while reporting is worse than the failure it was reporting. Encoding
    errors are replaced here, never raised.
    """
    encoding = sys.stdout.encoding or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def main():
    p = argparse.ArgumentParser(description="Unified developer gate")
    p.add_argument("--quick", action="store_true",
                   help="Skip repo policy check and the full test-suite run")
    args = p.parse_args()

    py = python_executable()
    checks = [
        ("repo_policy", [py, "scripts/check_repo_policy.py"]) if not args.quick else None,
        ("subprocess_policy", [py, "scripts/check_subprocess_policy.py"]),
        ("docs_check",  [py, "scripts/check_docs.py"]),
        ("i18n_check",  [py, "scripts/check_i18n.py"]),
        ("account_dna", [py, "scripts/check_account_dna.py"]),
        ("script_quality", [py, "scripts/check_script_quality.py", "--all-gated"]),
        ("basic_tests", [py, "scripts/test_basic.py"]),
        ("test_suites", [py, "scripts/run_tests.py"]) if not args.quick else None,
        ("whitespace",  ["git", "diff", "--check"]),
    ]

    results = []
    for entry in checks:
        if entry is None:
            continue
        name, cmd = entry
        # The discovered suite run is the long pole (the speech fixture suite
        # alone takes ~2 minutes); everything else stays on the 5-minute cap.
        timeout = 1800 if name == "test_suites" else 300
        results.append(run_check(name, cmd, timeout=timeout))

    print("\n" + "=" * 50)
    if all(results):
        print("ALL CHECKS PASSED")
        return 0
    else:
        print(f"SOME CHECKS FAILED ({sum(1 for r in results if not r)} of {len(results)})")
        return 1


if __name__ == "__main__":
    sys.exit(main())
