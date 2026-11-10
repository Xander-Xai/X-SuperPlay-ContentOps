#!/usr/bin/env python3
"""Characterize M5's observable behaviour before the orchestrator split.

Slice 1 of the M5 refactor roadmap (#140, per #133): lock what the M5 suites
say TODAY, so every later structural slice can be diffed against a recorded
baseline instead of a memory. The suites are the behavioural spec; this script
runs each one, parses its summary line, and writes a receipt.

What this is NOT: not a green/red gate, not a coverage metric, and not run in
CI (CI runs the suites themselves). It is a baseline generator: run it on a
clean checkout at a known commit, commit the receipt, and every slice after
that starts from recorded numbers rather than recollection.

Suite summary lines come in two repo-local dialects, both parsed:
- unittest:      ``Ran 14 tests in 0.198s`` followed by ``OK`` / ``FAILED (...)``
- custom runner: ``18/18 ok`` / ``Passed 29/30 M5 media-use workflow tests``

Usage:
  python scripts/m5_characterize.py                    # run + write receipts
  python scripts/m5_characterize.py --out DIR          # custom output dir
  python scripts/m5_characterize.py --list             # show suites, exit
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The M5 offline suites, in ci.yml order. A suite listed here and wired in CI
# (check_repo_policy enforces the wiring) is part of the behavioural contract
# the split must preserve.
M5_SUITES = [
    "tests/test_brief_to_m5.py",
    "tests/test_m5_asr_gate.py",
    "tests/test_m5_bundle_handoff.py",
    "tests/test_m5_evidence.py",
    "tests/test_m5_media_traceability.py",
    "tests/test_m5_media_use_workflow.py",
    "tests/test_m5_motion_integration.py",
    "tests/test_motion_build_reliability.py",
    "tests/test_motion_handoff.py",
    "tests/test_motion_sample.py",
]

BASELINE_SCHEMA = "contentops.m5-characterization/v1"

_RE_UNITTEST = re.compile(r"Ran (\d+) tests?(?: in [\d.]+s)?")
_RE_UNITTEST_OK = re.compile(r"^OK\b", re.MULTILINE)
_RE_CUSTOM = re.compile(r"(?:^|\s)(\d+)/(\d+)\s+ok")
_RE_PASSED = re.compile(r"Passed (\d+)/(\d+)")
_RE_ALL_PASSED = re.compile(r"^All (\d+) [\w -]*tests? passed", re.MULTILINE)


def parse_suite_output(text: str) -> dict:
    """Extract (total, passed, failed, dialect) from a suite's summary output."""
    total = passed = None
    dialect = None
    m = _RE_UNITTEST.search(text)
    if m:
        dialect = "unittest"
        total = int(m.group(1))
        passed = total if _RE_UNITTEST_OK.search(text) else 0
    if total is None:
        m = _RE_CUSTOM.search(text) or _RE_PASSED.search(text) or _RE_ALL_PASSED.search(text)
        if m:
            dialect = "custom"
            total = int(m.group(2))
            passed = int(m.group(1))
            failed = total - passed
            return {"total": total, "passed": passed, "failed": failed, "dialect": dialect}
    if total is None:
        return {"total": None, "passed": None, "failed": None, "dialect": None}
    failed = total - passed
    return {"total": total, "passed": passed, "failed": failed, "dialect": dialect}


def run_suite(suite: str, python: str = sys.executable, timeout: int = 600) -> dict:
    """Run one suite and return its characterization record."""
    proc = subprocess.run(
        [python, suite], cwd=str(ROOT), capture_output=True, text=True,
        timeout=timeout, encoding="utf-8", errors="replace",
    )
    text = (proc.stdout or "") + (proc.stderr or "")
    parsed = parse_suite_output(text)
    record = {
        "suite": suite,
        "exit_code": proc.returncode,
        **parsed,
    }
    if parsed["total"] is None:
        record["note"] = "no recognizable summary line; see suite_output tail"
        record["output_tail"] = text.strip()[-400:]
    return record


def characterize(out_dir: Path, python: str = sys.executable) -> dict:
    """Run every M5 suite and write the baseline receipt (json + md)."""
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True, text=True
    ).stdout.strip()
    records = []
    for suite in M5_SUITES:
        print(f"[run] {suite} ...", flush=True)
        records.append(run_suite(suite, python=python))

    total_tests = sum(r["total"] or 0 for r in records)
    total_passed = sum(r["passed"] or 0 for r in records)
    incomplete = [r["suite"] for r in records if r["total"] is None]
    receipt = {
        "schema": BASELINE_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": commit,
        "python": Path(python).name,
        "suites": records,
        "totals": {
            "suites": len(records),
            "tests": total_tests,
            "passed": total_passed,
            "failed": total_tests - total_passed,
        },
        "unparsed_suites": incomplete,
        "role": "BASELINE_ONLY",
        "cannot": [
            "a passing baseline is not an approval of any behaviour",
            "totals reflect the summary lines of the suites, not coverage",
            "this receipt does not authorize any structural change by itself",
        ],
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = receipt["generated_at"][:10]
    json_path = out_dir / f"m5-characterization-{stamp}.json"
    json_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        f"# M5 characterization baseline — {stamp}",
        "",
        f"- commit: `{commit[:12]}`",
        f"- suites: {len(records)}, tests: {total_tests}, passed: {total_passed},"
        f" failed: {total_tests - total_passed}",
        f"- unparsed suites: {len(incomplete)}" + (f" — {', '.join(incomplete)}" if incomplete else ""),
        "",
        "| suite | total | passed | failed | exit |",
        "|---|---|---|---|---|",
    ]
    for r in records:
        t = r["total"] if r["total"] is not None else "?"
        p = r["passed"] if r["passed"] is not None else "?"
        f = r["failed"] if r["failed"] is not None else "?"
        lines.append(f"| {r['suite']} | {t} | {p} | {f} | {r['exit_code']} |")
    lines.append("")
    lines.append("Slice-1 receipt for #140: structural refactor PRs must keep these")
    lines.append("suites at the recorded pass counts (or fix a named, reviewed defect).")
    md_path = out_dir / f"m5-characterization-{stamp}.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[done] {json_path}")
    print(f"[done] {md_path}")
    print(f"[totals] suites={len(records)} tests={total_tests} passed={total_passed}"
          f" failed={total_tests - total_passed} unparsed={len(incomplete)}")
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "docs" / "m5-baseline"))
    ap.add_argument("--list", action="store_true", help="print suites and exit")
    ap.add_argument("--python", default=sys.executable)
    args = ap.parse_args()
    if args.list:
        for s in M5_SUITES:
            print(s)
        return 0
    characterize(Path(args.out), python=args.python)
    return 0


if __name__ == "__main__":
    sys.exit(main())
