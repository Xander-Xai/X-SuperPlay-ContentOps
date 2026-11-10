#!/usr/bin/env python3
"""Validate config/governance/branch-registry.json (offline, no network).

Every non-persistent remote branch should carry a PR reference, a purpose, a
status and an ``expires`` value. An ``archived`` entry is a deliberate snapshot
that never had a PR (for example a worktree salvage committed straight to an
archive branch), so it is exempt from ``pr`` but still requires
created/purpose/status/expires.

``expires`` is a REVIEW DATE, not a deletion deadline. The registry is an audit
ledger of branches ever created, not a list of live remote branches, and merged
branches are auto-deleted by GitHub. Treating a past review date as a hard
failure would make every PR's required check go red on a fixed calendar date
regardless of code quality. Therefore:

  * ``status=merged`` past its review date -> report-only ``RETIRE DUE``
    (collected by ``retire_due()``, printed by the CLI, never a CI failure).
  * ``status=archived`` -> a deliberate permanent snapshot, exempt from
    ``max_age_days`` entirely.
  * any other non-persistent status past its review date -> hard ``EXPIRED``.

Invalid date strings remain a hard failure for every status.
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "config" / "governance" / "branch-registry.json"
SCHEMA = "contentops.branch-registry/v1"
REQUIRED = ("name", "purpose", "status")
NON_PERSISTENT_REQUIRED = ("name", "pr", "created", "purpose", "status", "expires")
ARCHIVED_REQUIRED = ("name", "created", "purpose", "status", "expires")


def validate(data, today=None):
    """Return a list of human-readable failures. Empty list means PASS."""
    today = today or date.today()
    errors = []
    if not isinstance(data, dict):
        return ["registry root must be an object"]
    if data.get("schema") != SCHEMA:
        errors.append("schema mismatch: expected %s" % SCHEMA)
    policy = data.get("policy") or {}
    if not isinstance(policy, dict) or not policy.get("persistent"):
        errors.append("policy.persistent is required")
    branches = data.get("branches")
    if not isinstance(branches, list) or not branches:
        return errors + ["branches must be a non-empty list"]
    names = set()
    persistent = []
    for i, b in enumerate(branches):
        if not isinstance(b, dict):
            errors.append("branches[%d] must be an object" % i)
            continue
        name = b.get("name")
        if not name:
            errors.append("branches[%d] missing name" % i)
            continue
        if name in names:
            errors.append("duplicate branch: %s" % name)
        names.add(name)
        status = b.get("status")
        is_persistent = status == "persistent"
        if is_persistent:
            persistent.append(name)
        if is_persistent:
            required = REQUIRED
        elif status == "archived":
            required = ARCHIVED_REQUIRED
        else:
            required = NON_PERSISTENT_REQUIRED
        for field in required:
            if b.get(field) in (None, ""):
                errors.append("%s missing %s" % (name, field))
        expires = b.get("expires")
        if expires:
            try:
                expires_date = date.fromisoformat(expires)
            except ValueError:
                errors.append("%s has invalid expires date: %s" % (name, expires))
                expires_date = None
            if expires_date and expires_date < today:
                if status in ("merged", "archived"):
                    pass  # report-only / permanent: see retire_due() and the docstring
                else:
                    errors.append("EXPIRED: %s (expires %s)" % (name, expires))
    expected = policy.get("persistent") or []
    if sorted(persistent) != sorted(expected):
        errors.append("persistent branches %s do not match policy %s" % (persistent, expected))
    if "main" not in names:
        errors.append("main is not registered")
    return errors


def retire_due(data, today=None):
    """Return report-only retirement candidates (merged entries past review date)."""
    today = today or date.today()
    out = []
    branches = data.get("branches") if isinstance(data, dict) else None
    if not isinstance(branches, list):
        return out
    for b in branches:
        if not isinstance(b, dict) or b.get("status") != "merged":
            continue
        expires = b.get("expires")
        if not expires:
            continue
        try:
            if date.fromisoformat(expires) < today:
                out.append("%s (review date %s, pr #%s)" % (
                    b.get("name"), expires, b.get("pr")))
        except ValueError:
            continue
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default=str(DEFAULT))
    ap.add_argument("--today", help="override today (YYYY-MM-DD), for tests")
    args = ap.parse_args()
    path = Path(args.registry)
    if not path.exists():
        print("FAIL: registry not found: %s" % path)
        return 1
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print("FAIL: invalid JSON: %s" % exc)
        return 1
    today = date.fromisoformat(args.today) if args.today else date.today()
    errors = validate(data, today)
    due = retire_due(data, today)
    for item in due:
        print("  [RETIRE DUE] %s" % item)
    if errors:
        for e in errors:
            print("  [FAIL] %s" % e)
        print("branch-registry FAIL: %d issue(s)" % len(errors))
        return 1
    print("branch-registry PASS: %d branches, %d persistent, %d retire-due (report-only)" % (
        len(data["branches"]),
        len([b for b in data["branches"] if b.get("status") == "persistent"]),
        len(due)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
