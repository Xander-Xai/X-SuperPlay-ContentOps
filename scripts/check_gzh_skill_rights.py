#!/usr/bin/env python3
"""Fail closed when a GZH route selects a skill whose rights are not cleared.

The vendored 公众号 workflow is a verbatim import, so its own allowlist cannot be
edited here. This gate sits on the ContentOps side: every skill present under
`vendor/gzh-thinktank/gzh_未来智能/skills/` must have a rights record in
`config/gzh-skill-rights.json`, and every `routing.yaml` under `projects/` must
select a skill whose `dispatch` is allowed.

A `RIGHTS_UNKNOWN` skill is not an infringement finding. It means no author,
source or licence evidence was found, so the route fails closed instead of
guessing. `RESTRICTED` records a known obligation; only a reviewed
`allowed_agpl` dispatch is accepted.

This is an engineering gate, not a legal opinion.

A routing.yaml selection is not the only way to reach a skill. The gate also
fails closed when ContentOps-owned code (`scripts/`, `src/`) references a blocked
skill by path (`skills/<name>`), and when a held or blocked skill's `SKILL.md` is
copied byte-for-byte into a distributable location outside the vendored tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "gzh-skill-rights.json"
SKILLS = ROOT / "vendor" / "gzh-thinktank" / "gzh_未来智能" / "skills"
NOTICE = ROOT / "vendor" / "gzh-thinktank" / "THIRD_PARTY_NOTICES.md"

SCHEMA = "contentops.gzh-skill-rights/v1"
CLASSES = {
    "OWNED_AND_CLEARED",
    "OWNER_ATTESTED",
    "THIRD_PARTY_LICENSE_VERIFIED",
    "RESTRICTED",
    "RIGHTS_UNKNOWN",
}
DISPATCH = {"allowed", "allowed_agpl", "blocked"}
DISTRIBUTION = {"allowed", "allowed_agpl", "hold", "blocked"}
SELECTED = re.compile(r"^\s+selected_skill:\s*['\"]?([A-Za-z0-9._/-]+)")

# Where a ContentOps-owned callsite could reach a vendored skill directly, and
# where a held/blocked skill must not be re-packaged for distribution.
CALLSITE_DIRS = ("scripts", "src")
CALLSITE_SUFFIXES = {".py", ".yaml", ".yml", ".json"}
REPACKAGE_SKIP_PREFIXES = (
    "vendor/gzh-thinktank", "research", ".git", "node_modules", ".venv",
    ".runtime", "__pycache__",
)
ALLOWED_DISPATCH = {"allowed", "allowed_agpl"}


class RightsError(Exception):
    """A configuration error that is not a skill finding."""


def skill_paths(root: Path = ROOT) -> List[str]:
    base = root / "vendor" / "gzh-thinktank" / "gzh_未来智能" / "skills"
    if not base.is_dir():
        raise RightsError("VENDOR_SKILLS_MISSING")
    names: List[str] = []
    for child in sorted(base.iterdir(), key=lambda item: item.name):
        if not child.is_dir():
            continue
        if child.name == "_archive":
            names.extend(
                f"_archive/{item.name}" for item in sorted(child.iterdir())
                if item.is_dir() and (item / "SKILL.md").is_file())
        elif (child / "SKILL.md").is_file() or (child / "package.json").is_file():
            names.append(child.name)
    return names


def load_config(path: Path = CONFIG) -> Dict[str, Any]:
    if not path.is_file():
        raise RightsError("CONFIG_MISSING")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != SCHEMA:
        raise RightsError("CONFIG_SCHEMA_INVALID")
    skills = data.get("skills")
    if not isinstance(skills, dict) or not skills:
        raise RightsError("CONFIG_SKILLS_MISSING")
    return data


def _selected_skills(root: Path) -> List[tuple[str, str]]:
    found: List[tuple[str, str]] = []
    for path in sorted((root / "projects").glob("**/routing.yaml")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            match = SELECTED.match(line)
            if match:
                found.append((path.relative_to(root).as_posix(), match.group(1)))
    return found


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _callsites(root: Path, skills: Dict[str, Any]) -> List[Dict[str, str]]:
    """A ContentOps-owned script must not reach a blocked skill directly.

    The routing.yaml check only sees declared selections; a runner can still call
    a skill by path. Scan ContentOps-owned code for `skills/<path>` references to
    any skill whose dispatch is not allowed.
    """
    failures: List[Dict[str, str]] = []
    blocked = {
        name: entry.get("path")
        for name, entry in skills.items()
        if isinstance(entry, dict) and entry.get("dispatch") not in ALLOWED_DISPATCH
    }
    if not blocked:
        return failures
    for directory in CALLSITE_DIRS:
        base = root / directory
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in CALLSITE_SUFFIXES:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for name, rel in blocked.items():
                if isinstance(rel, str) and f"skills/{rel}" in text:
                    failures.append({
                        "id": "callsite_blocked_skill",
                        "file": path.relative_to(root).as_posix(),
                        "skill": name,
                    })
    return failures


def _repackaged(root: Path, skills: Dict[str, Any]) -> List[Dict[str, str]]:
    """A held or blocked skill must not be copied into a distributable location.

    Identity is the exact bytes of the skill's SKILL.md, so a same-named but
    different skill (for example an unrelated archival copy) is not flagged.
    """
    failures: List[Dict[str, str]] = []
    held = {
        name: entry.get("path")
        for name, entry in skills.items()
        if isinstance(entry, dict) and entry.get("distribution") in {"blocked", "hold"}
    }
    if not held:
        return failures
    gzh = root / "vendor" / "gzh-thinktank" / "gzh_未来智能" / "skills"
    held_shas: Dict[str, str] = {}
    for name, rel in held.items():
        candidate = gzh / str(rel) / "SKILL.md"
        if candidate.is_file():
            held_shas[name] = _sha256_bytes(candidate.read_bytes())
    if not held_shas:
        return failures
    for path in root.rglob("SKILL.md"):
        rel = path.relative_to(root).as_posix()
        if any(rel == prefix or rel.startswith(prefix + "/")
               for prefix in REPACKAGE_SKIP_PREFIXES):
            continue
        try:
            digest = _sha256_bytes(path.read_bytes())
        except OSError:
            continue
        for name, held_sha in held_shas.items():
            if digest == held_sha:
                failures.append({"id": "repackaged_skill", "file": rel, "skill": name})
    return failures


def check(root: Path = ROOT, config: Path | None = None) -> Dict[str, Any]:
    if config is None:
        config = root / "config" / "gzh-skill-rights.json"
    data = load_config(config)
    skills = data["skills"]
    failures: List[Dict[str, str]] = []

    actual = skill_paths(root)
    for name in actual:
        if name not in skills:
            failures.append({"id": "unlisted_skill", "skill": name})
    for name, entry in sorted(skills.items()):
        if not isinstance(entry, dict):
            failures.append({"id": "entry_not_object", "skill": name})
            continue
        if entry.get("class") not in CLASSES:
            failures.append({"id": "class_invalid", "skill": name})
        if entry.get("dispatch") not in DISPATCH:
            failures.append({"id": "dispatch_invalid", "skill": name})
        if entry.get("distribution") not in DISTRIBUTION:
            failures.append({"id": "distribution_invalid", "skill": name})
        rel = entry.get("path")
        if not isinstance(rel, str) or not (
                root / "vendor" / "gzh-thinktank" / "gzh_未来智能" / "skills" / rel).exists():
            failures.append({"id": "path_missing", "skill": name})

    for route, selected in _selected_skills(root):
        entry = skills.get(selected)
        if entry is None:
            failures.append({"id": "route_unknown_skill", "route": route, "skill": selected})
            continue
        dispatch = entry.get("dispatch")
        if dispatch not in {"allowed", "allowed_agpl"}:
            failures.append({
                "id": "route_blocked_skill", "route": route, "skill": selected,
                "class": str(entry.get("class")),
            })

    if any(entry.get("notice_required") for entry in skills.values() if isinstance(entry, dict)):
        if not (root / "vendor" / "gzh-thinktank" / "THIRD_PARTY_NOTICES.md").is_file():
            failures.append({"id": "notice_missing",
                             "path": "vendor/gzh-thinktank/THIRD_PARTY_NOTICES.md"})

    # A route is not the only way to reach a skill: scan direct callsites and
    # repackaged copies too, so a restricted component cannot slip past the gate.
    failures.extend(_callsites(root, skills))
    failures.extend(_repackaged(root, skills))

    return {
        "schema": "contentops.gzh-skill-rights-check/v1",
        "ok": not failures,
        "skills": len(skills),
        "routes": len(_selected_skills(root)),
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    config = args.config or (args.root / "config" / "gzh-skill-rights.json")
    try:
        result = check(args.root, config)
    except (RightsError, json.JSONDecodeError) as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        else:
            print(f"gzh-skill-rights REFUSED: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["ok"]:
        print(f"gzh-skill-rights PASS: {result['skills']} skills, "
              f"{result['routes']} route selections, 0 blocked")
    else:
        print("gzh-skill-rights FAILED")
        for item in result["failures"]:
            print("  " + " ".join(f"{key}={value}" for key, value in item.items()))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
