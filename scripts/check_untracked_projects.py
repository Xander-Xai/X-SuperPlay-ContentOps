#!/usr/bin/env python3
"""Fail when a new untracked experiment directory appears under ``projects/``.

Read-only. This never deletes, moves, stages or cleans anything -- it reports.

Why
---
``projects/<slug>/`` is where a production run writes. When the run's receipts
are worth keeping they get committed; when it is an experiment it should live in
``projects/_local/`` and stay out of Git entirely. In practice the third thing
happened: two dozen experiment directories piled up as untracked folders, each
one a plausible-looking project that no reviewer could tell apart from a real
one, and each one a single ``git add -A`` away from being published.

The guard in ``checkout_guard.py`` stops runs from dirtying a clean checkout.
This check covers the other direction: it makes the pile visible and refuses to
let it grow. The baseline in ``config/untracked-projects-baseline.txt`` is the
list of directories that already existed when the rule landed. Only removals are
welcome there; a new line means a new experiment leaked out of ``_local``.

Usage
-----
  python scripts/check_untracked_projects.py
  python scripts/check_untracked_projects.py --json

Exit 0 = no new untracked project; exit 1 = new untracked project present;
exit 2 = git could not be read, so the check cannot make a claim.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from process_utils import hidden_run

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "config" / "untracked-projects-baseline.txt"
LOCAL_SANDBOX = "projects/_local"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


def _git_status_paths() -> list[tuple[str, str]]:
    """Return [(status, path)] for every uncommitted path under projects/."""
    result = hidden_run(
        ["git", "-C", str(ROOT), "status", "--porcelain", "-z",
         "--untracked-files=normal", "--", "projects"],
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git status failed")
    entries: list[tuple[str, str]] = []
    for chunk in result.stdout.split("\0"):
        if len(chunk) < 4:
            continue
        entries.append((chunk[:2].strip() or "??", chunk[3:]))
    return entries


def _read_baseline() -> set[str]:
    if not BASELINE.is_file():
        return set()
    names: set[str] = set()
    for raw in BASELINE.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            names.add(line.strip("/"))
    return names


def _tracked_project_names() -> set[str]:
    """Top-level ``projects/<name>`` that git already tracks at least one file in."""
    result = hidden_run(
        ["git", "-C", str(ROOT), "ls-files", "-z", "--", "projects"],
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git ls-files failed")
    names: set[str] = set()
    for path in result.stdout.split("\0"):
        parts = path.split("/")
        if len(parts) >= 3 and parts[0] == "projects":
            names.add(f"{parts[0]}/{parts[1]}")
    return names


def collect() -> dict:
    baseline = _read_baseline()
    tracked = _tracked_project_names()
    candidate_dirs: set[str] = set()
    untracked_other: list[str] = []
    for status, path in _git_status_paths():
        if not path.startswith("projects/"):
            continue
        parts = path.split("/")
        if len(parts) < 3:
            untracked_other.append(path)
            continue
        name = f"{parts[0]}/{parts[1]}"
        if parts[1] == "_local":
            # Tracked edits inside the sandbox should not exist; they mean the
            # directory was force-added at some point.
            untracked_other.append(path)
        elif status == "??" and name not in tracked:
            candidate_dirs.add(name)
        elif status == "??":
            # A tracked project with new untracked output. Real work in progress,
            # but not a stray experiment directory, so it is reported, not judged.
            untracked_other.append(path)
    new = sorted(candidate_dirs - baseline)
    stale = sorted(baseline - candidate_dirs)
    return {
        "baseline_count": len(baseline),
        "untracked_count": len(candidate_dirs),
        "new": new,
        "stale_baseline": stale,
        "other": sorted(untracked_other),
        "local_sandbox_present": (ROOT / LOCAL_SANDBOX).is_dir(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = collect()
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"[ERROR] cannot read the working tree: {exc}", file=sys.stderr)
        return 2

    ok = not report["new"]
    if args.json:
        print(json.dumps({"ok": ok, **report}, ensure_ascii=False, indent=2))
    else:
        print(f"baseline    {report['baseline_count']} known untracked project(s)")
        print(f"untracked   {report['untracked_count']} present")
        if report["new"]:
            print("\n[FAIL] new untracked project direction(s) outside the baseline:")
            for name in report["new"]:
                print(f"    {name}/")
            print("\n  Move the experiment under projects/_local/ (gitignored) or commit it")
            print("  as a tracked project with receipts. This check never moves anything.")
        if report["stale_baseline"]:
            print("\n[note] baseline entries that no longer exist (safe to delete from the")
            print("       baseline file; keeping them only makes the list look bigger):")
            for name in report["stale_baseline"]:
                print(f"    {name}/")
        if report["other"]:
            print("\n[note] uncommitted non-directory paths under projects/ (not judged here):")
            for path in report["other"][:20]:
                print(f"    {path}")
            if len(report["other"]) > 20:
                print(f"    ... and {len(report['other']) - 20} more")
        print("\n[ok] no new untracked project" if ok
              else "\n[FAIL] untracked experiment directories grew")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
