#!/usr/bin/env python3
"""Unified developer gate for humans and Claude Code.

Runs before every commit / PR.

Order:
  1. repo_policy_check
  2. subprocess_policy_check
  3. check_docs
  4. check_i18n
  5. check_account_dna
  6. test_basic
  7. git diff --check (whitespace)

All must pass. All checks are read-only and deterministic.

Usage:
  python scripts/dev_check.py          # full check
  python scripts/dev_check.py --quick  # skip repo policy (for speed)
"""

import argparse
import sys
from pathlib import Path

from process_utils import hidden_run, python_executable

ROOT = Path(__file__).resolve().parents[1]


def run_check(name: str, cmd: list[str]) -> bool:
    print(f"\n=== {name} ===")
    r = hidden_run(cmd, cwd=str(ROOT), timeout=300)
    if r.stdout:
        print(_console_safe(r.stdout[:2000]))
    if r.returncode != 0 and r.stderr:
        print(_console_safe(r.stderr[:1000]))
    ok = r.returncode == 0
    print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    return ok


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
    p.add_argument("--quick", action="store_true", help="Skip repo policy check")
    args = p.parse_args()

    py = python_executable()
    checks = [
        ("repo_policy", [py, "scripts/check_repo_policy.py"]) if not args.quick else None,
        ("subprocess_policy", [py, "scripts/check_subprocess_policy.py"]),
        ("docs_check",  [py, "scripts/check_docs.py"]),
        ("i18n_check",  [py, "scripts/check_i18n.py"]),
        ("account_dna", [py, "scripts/check_account_dna.py"]),
        ("basic_tests", [py, "scripts/test_basic.py"]),
        ("whitespace",  ["git", "diff", "--check"]),
    ]

    results = []
    for entry in checks:
        if entry is None:
            continue
        name, cmd = entry
        results.append(run_check(name, cmd))

    print("\n" + "=" * 50)
    if all(results):
        print("ALL CHECKS PASSED")
        return 0
    else:
        print(f"SOME CHECKS FAILED ({sum(1 for r in results if not r)} of {len(results)})")
        return 1


if __name__ == "__main__":
    sys.exit(main())
