#!/usr/bin/env python3
"""Check that installed content skills reference code this branch actually has.

Three failures, and each one means the same thing in a different way:

  UNDOCUMENTED_REFERENCE  A SKILL.md names a repository path that does not
                           exist here and that is not recorded in
                           runtime/content-skill-status.json. The skill
                           describes a capability nobody can find.
  RECORD_STALE            A recorded reference now exists on this branch. The
                           layer was merged and the record was not updated, so
                           the record is lying about the present.
  STATE_MISMATCH          A skill marked MERGED or DECLARED still references
                           code that is missing. It cannot be what it claims.

One warning:

  REFERENCE_REMOVED       A recorded reference is no longer named by the skill.
                           The record should be pruned, but a stale line is not
                           a false capability.

The skill store is host-local and absent on CI. When it is missing, the scan is
skipped and only the record-versus-branch checks still run.

Usage:
  python scripts/check_skill_references.py
  python scripts/check_skill_references.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS_FILE = ROOT / "runtime" / "content-skill-status.json"

# Repository-root directories a skill may legitimately point at. Anything else
# (01_research/, 04_video/, production/…) belongs to a content package layout
# or a retired workspace, not to this repository.
REPO_ROOTS = ("src", "scripts", "tests", "runtime", "config", "docs", "projects", "templates")

# The whole path must be the capture group: capturing only the root would make
# findall() return "scripts" for every reference, and `(ROOT / "scripts").exists()`
# is always true, so every reference would be silently skipped.
PATH_RE = re.compile(
    r"(?<![\w.-])"
    r"((?:" + "|".join(REPO_ROOTS) + r")[/\\][A-Za-z0-9_.-]+(?:[/\\][A-Za-z0-9_.-]+)*)"
)

MERGED_STATES = ("MERGED", "DECLARED")


def store_root() -> Path | None:
    """Locate the shared skill store, or None when it is not installed."""
    env = os.environ.get("CONTENTOPS_SKILL_STORE", "").strip()
    if env:
        candidate = Path(env).expanduser()
        return candidate if candidate.is_dir() else None
    candidate = Path.home() / ".agents" / "skills"
    return candidate if candidate.is_dir() else None


def referenced_paths(text: str) -> set[str]:
    """Repository-relative paths a skill document names."""
    found = set()
    for match in PATH_RE.findall(text):
        found.add(match.replace("\\", "/"))
    return found


def load_status() -> dict:
    if not STATUS_FILE.exists():
        raise SystemExit(f"missing status file: {STATUS_FILE.relative_to(ROOT)}")
    return json.loads(STATUS_FILE.read_text(encoding="utf-8"))


def check(status: dict, store: Path | None) -> tuple[list[dict], list[dict]]:
    failures: list[dict] = []
    warnings: list[dict] = []

    for skill in status.get("skills", []):
        skill_id = skill.get("id", "<unknown>")
        recorded = {
            ref["path"]: ref
            for ref in skill.get("references", [])
        }
        state = skill.get("state", "UNMERGED")

        # 1. The record must still describe this checkout.
        for path, ref in sorted(recorded.items()):
            exists = (ROOT / path).exists()
            if exists:
                failures.append({
                    "code": "RECORD_STALE",
                    "skill": skill_id,
                    "path": path,
                    "detail": (
                        f"{path} now exists on this branch. The layer carried by "
                        f"{ref.get('carried_by') or 'an unknown branch'} has landed, so this "
                        f"record is stale. Update runtime/content-skill-status.json and, if the "
                        f"skill is ready, declare it in runtime/skill-registry.json."
                    ),
                })
            elif state in MERGED_STATES:
                failures.append({
                    "code": "STATE_MISMATCH",
                    "skill": skill_id,
                    "path": path,
                    "detail": (
                        f"skill is marked {state} but {path} is missing from this branch."
                    ),
                })

        if store is None:
            continue

        skill_file = store / skill.get("file", f"{skill_id}/SKILL.md")
        if not skill_file.is_file():
            warnings.append({
                "code": "SKILL_NOT_INSTALLED",
                "skill": skill_id,
                "path": skill.get("file", ""),
                "detail": f"{skill_file} is not present in the store.",
            })
            continue

        text = skill_file.read_text(encoding="utf-8", errors="ignore")
        named = referenced_paths(text)

        # 2. Every absent path a skill names must be recorded.
        for path in sorted(named):
            if (ROOT / path).exists():
                continue
            if path in recorded:
                continue
            failures.append({
                "code": "UNDOCUMENTED_REFERENCE",
                "skill": skill_id,
                "path": path,
                "detail": (
                    f"{skill_file.name} names {path}, which does not exist on this branch and "
                    f"is not recorded in runtime/content-skill-status.json."
                ),
            })

        # 3. A recorded reference the skill no longer names should be pruned.
        for path in sorted(recorded):
            if path not in named:
                warnings.append({
                    "code": "REFERENCE_REMOVED",
                    "skill": skill_id,
                    "path": path,
                    "detail": f"{path} is recorded but the skill no longer names it.",
                })

    return failures, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Skill reference integrity check")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    status = load_status()
    store = store_root()
    failures, warnings = check(status, store)

    record = {
        "schema": "contentops.skill-reference-check/v1",
        "store": str(store) if store else None,
        "store_present": store is not None,
        "skills_checked": len(status.get("skills", [])),
        "failures": failures,
        "warnings": warnings,
        "ok": not failures,
    }

    if args.json:
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return 0 if not failures else 1

    print(f"skill store: {store if store else 'not present (reference scan skipped)'}")
    print(f"skills checked: {record['skills_checked']}")
    for warning in warnings:
        print(f"  [WARN] {warning['code']} {warning['skill']}: {warning['detail']}")
    for failure in failures:
        print(f"  [FAIL] {failure['code']} {failure['skill']}: {failure['detail']}")
    if failures:
        print(f"\n{len(failures)} skill reference failure(s)")
        return 1
    print("\nAll skill references match the recorded status.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
