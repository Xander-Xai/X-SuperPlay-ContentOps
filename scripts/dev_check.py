#!/usr/bin/env python3
"""Unified developer gate for humans and Claude Code.

Runs before every commit / PR.

Order:
  1. repo_policy_check
  2. check_docs
  3. check_i18n
  4. test_basic
  5. git diff --check (whitespace)

All must pass. All checks are read-only and deterministic.

Usage:
  python scripts/dev_check.py          # full check
  python scripts/dev_check.py --quick  # skip repo policy (for speed)
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_check(name: str, cmd: list[str]) -> bool:
    print(f"\n=== {name} ===")
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=120)
    if r.stdout:
        print(r.stdout[:2000])
    if r.returncode != 0 and r.stderr:
        print(r.stderr[:1000])
    ok = r.returncode == 0
    print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    return ok


def main():
    p = argparse.ArgumentParser(description="Unified developer gate")
    p.add_argument("--quick", action="store_true", help="Skip repo policy check")
    args = p.parse_args()

    checks = [
        ("repo_policy", ["python", "scripts/check_repo_policy.py"]) if not args.quick else None,
        ("docs_check",  ["python", "scripts/check_docs.py"]),
        ("i18n_check",  ["python", "scripts/check_i18n.py"]),
        ("basic_tests", ["python", "scripts/test_basic.py"]),
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
