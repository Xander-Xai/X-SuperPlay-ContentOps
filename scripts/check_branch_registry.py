#!/usr/bin/env python3
"""Validate config/governance/branch-registry.json (offline, no network).

Every non-persistent remote branch should carry a PR reference, a purpose, a
status and an expiry. An expired entry is a governance failure: either the work
landed and the branch was removed, or the entry is stale and must be reviewed.

An ``archived`` entry is a deliberate snapshot that never had a PR (for example
a worktree salvage committed straight to an archive branch), so it is exempt
from ``pr`` but still requires created/purpose/status/expires.
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
                if date.fromisoformat(expires) < today:
                    errors.append("EXPIRED: %s (expires %s)" % (name, expires))
            except ValueError:
                errors.append("%s has invalid expires date: %s" % (name, expires))
    expected = policy.get("persistent") or []
    if sorted(persistent) != sorted(expected):
        errors.append("persistent branches %s do not match policy %s" % (persistent, expected))
    if "main" not in names:
        errors.append("main is not registered")
    return errors


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
    if errors:
        for e in errors:
            print("  [FAIL] %s" % e)
        print("branch-registry FAIL: %d issue(s)" % len(errors))
        return 1
    print("branch-registry PASS: %d branches, %d persistent" % (
        len(data["branches"]), len([b for b in data["branches"] if b.get("status") == "persistent"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
