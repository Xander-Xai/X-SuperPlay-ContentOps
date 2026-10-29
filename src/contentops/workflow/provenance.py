"""Skill provenance: a run must name the skill bytes it executed.

The repository already declares which skill owns a step (account DNA
`skill_route`) and records that a step ran (stage receipts). Neither binds the
two: a receipt can say "motion" while the skill on disk changed underneath it.

So a provenance record carries the skill tree's fingerprint, the exact command,
the exit code, and the input/output digests. If the skill changes, the record no
longer describes the run, and a reviewer can see that without trusting prose.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA = "contentops.skill-provenance/v1"

_SHA = re.compile(r"^[0-9a-f]{64}$")
#: Files that define a skill's behaviour. Binary examples and vendored assets
#: are excluded so a re-download of a sample image cannot invalidate a run.
_TRACKED_SUFFIXES = (".md", ".py", ".js", ".mjs", ".cjs", ".ts", ".json", ".yaml", ".yml", ".html", ".css")


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def skill_tree_fingerprint(skill_dir: Path) -> Dict[str, Any]:
    """Deterministic fingerprint of a skill's text files."""
    root = Path(skill_dir).resolve()
    if not root.is_dir():
        raise ValueError(f"skill directory does not exist: {root}")
    entries = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _TRACKED_SUFFIXES:
            continue
        relative = path.relative_to(root).as_posix()
        if relative.startswith((".git/", "node_modules/", "assets/examples/")):
            continue
        entries.append({"path": relative, "sha256": _sha_file(path)})
    if not entries:
        raise ValueError(f"skill directory holds no tracked files: {root}")
    payload = json.dumps(entries, sort_keys=True, separators=(",", ":"))
    return {
        "skill_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "file_count": len(entries),
        "files": entries,
    }


def _iso_utc(value: Any, field: str) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return f"{field} must be an ISO-8601 UTC timestamp"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return f"{field} is not an ISO-8601 timestamp"
    if parsed.utcoffset() is None:
        return f"{field} must carry a UTC designator"
    return None


def validate_provenance(document: Any) -> List[str]:
    if not isinstance(document, dict):
        return ["provenance must be a JSON object"]
    if document.get("schema") != SCHEMA:
        return [f"provenance schema must be {SCHEMA!r}"]
    errors: List[str] = []
    if not isinstance(document.get("skill"), str) or not document["skill"].strip():
        errors.append("skill must be a non-empty string")
    if not _SHA.match(str(document.get("skill_sha256") or "")):
        errors.append("skill_sha256 must be 64 lowercase hex")

    invocation = document.get("invocation")
    if not isinstance(invocation, dict):
        errors.append("invocation must be an object")
    else:
        if not isinstance(invocation.get("command"), str) or not invocation["command"].strip():
            errors.append("invocation.command must be a non-empty string")
        if not isinstance(invocation.get("exit_code"), int) or isinstance(invocation.get("exit_code"), bool):
            errors.append("invocation.exit_code must be an integer")
        for key in ("started_at", "finished_at"):
            problem = _iso_utc(invocation.get(key), f"invocation.{key}")
            if problem:
                errors.append(problem)

    def _files(key: str, required: bool) -> None:
        items = document.get(key)
        if items is None and not required:
            return
        if not isinstance(items, list):
            errors.append(f"{key} must be an array")
            return
        if required and not items:
            errors.append(f"{key} must not be empty")
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f"{key}[{index}] must be an object")
                continue
            if not isinstance(item.get("path"), str) or not item["path"].strip():
                errors.append(f"{key}[{index}].path must be a non-empty string")
            if not _SHA.match(str(item.get("sha256") or "")):
                errors.append(f"{key}[{index}].sha256 must be 64 lowercase hex")

    _files("inputs", False)
    exit_code = (invocation or {}).get("exit_code") if isinstance(invocation, dict) else None
    _files("outputs", exit_code == 0)
    return errors


def bind_run(*, skill: str, skill_dir: Path, command: str, exit_code: int,
             started_at: str, finished_at: str,
             inputs: List[Dict[str, str]], outputs: List[Dict[str, str]]) -> Dict[str, Any]:
    fingerprint = skill_tree_fingerprint(skill_dir)
    return {
        "schema": SCHEMA,
        "skill": skill,
        "skill_sha256": fingerprint["skill_sha256"],
        "invocation": {
            "command": command,
            "exit_code": exit_code,
            "started_at": started_at,
            "finished_at": finished_at,
        },
        "inputs": inputs,
        "outputs": outputs,
    }
