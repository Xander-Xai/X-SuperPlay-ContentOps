"""Workflow improvement log: problems are recorded, not worked around.

A gate that fails during production has two possible responses: fix the gate in
the same run (and lose the evidence of what happened), or record the problem
with a reproduction and a hash-bound evidence pointer, then fix it through a
reviewed change.

This module owns the second response. It is deliberately not a production gate:
an open entry does not block delivery, and closing one does not approve a video.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List

SCHEMA = "contentops.workflow-improvement-log/v1"
STATUSES = ("reported", "triaged", "reproduced", "planned", "fixed", "verified", "wont_fix")
TRANSITIONS = {
    "reported": ("triaged", "wont_fix"),
    "triaged": ("reproduced", "planned", "wont_fix"),
    "reproduced": ("planned", "fixed", "wont_fix"),
    "planned": ("fixed", "wont_fix"),
    "fixed": ("verified", "reproduced"),
    "verified": (),
    "wont_fix": (),
}
CATEGORIES = ("gate", "path", "logic", "render", "provider", "docs", "content", "environment")
SEVERITIES = ("low", "medium", "high", "critical")

_SHA = re.compile(r"^[0-9a-f]{64}$")


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def validate_entry(entry: Any, index: int = 0) -> List[str]:
    where = f"entries[{index}]"
    if not isinstance(entry, dict):
        return [f"{where} must be an object"]
    errors: List[str] = []
    for key in ("entry_id", "summary", "observed", "expected", "reproduction"):
        if not _text(entry.get(key)):
            errors.append(f"{where}.{key} must be a non-empty string")
    if entry.get("stage") not in (
            "brief", "audience", "research", "script", "audio", "storyboard",
            "assets", "compose", "quality", "delivery", "workflow"):
        errors.append(f"{where}.stage is not a known stage")
    if entry.get("category") not in CATEGORIES:
        errors.append(f"{where}.category must be one of {CATEGORIES}")
    if entry.get("severity") not in SEVERITIES:
        errors.append(f"{where}.severity must be one of {SEVERITIES}")
    if entry.get("status") not in STATUSES:
        errors.append(f"{where}.status must be one of {STATUSES}")
    if entry.get("status") == "wont_fix" and not _text(entry.get("reason")):
        errors.append(f"{where} is wont_fix but gives no reason")
    evidence = entry.get("evidence") or []
    if not isinstance(evidence, list):
        errors.append(f"{where}.evidence must be an array")
    else:
        for offset, item in enumerate(evidence):
            if not isinstance(item, dict):
                errors.append(f"{where}.evidence[{offset}] must be an object")
                continue
            if not _text(item.get("path")):
                errors.append(f"{where}.evidence[{offset}].path must be a non-empty string")
            if not _SHA.match(str(item.get("sha256") or "")):
                errors.append(f"{where}.evidence[{offset}].sha256 must be 64 lowercase hex")
    return errors


def validate_log(document: Any) -> List[str]:
    if not isinstance(document, dict):
        return ["improvement log must be a JSON object"]
    if document.get("schema") != SCHEMA:
        return [f"improvement log schema must be {SCHEMA!r}"]
    entries = document.get("entries")
    if not isinstance(entries, list):
        return ["entries must be an array"]
    errors: List[str] = []
    seen = set()
    for index, entry in enumerate(entries):
        errors.extend(validate_entry(entry, index))
        if isinstance(entry, dict):
            entry_id = entry.get("entry_id")
            if entry_id in seen:
                errors.append(f"duplicate entry_id {entry_id!r}")
            seen.add(entry_id)
    return errors


def new_entry(*, entry_id: str, stage: str, category: str, severity: str,
              summary: str, observed: str, expected: str, reproduction: str,
              evidence: List[Dict[str, str]], proposed_change: str = "",
              verification_plan: str = "") -> Dict[str, Any]:
    return {
        "entry_id": entry_id,
        "stage": stage,
        "category": category,
        "severity": severity,
        "status": "reported",
        "summary": summary,
        "observed": observed,
        "expected": expected,
        "reproduction": reproduction,
        "evidence": evidence,
        "proposed_change": proposed_change,
        "verification_plan": verification_plan,
        "reason": "",
        "created_at": _now(),
    }


def append_entry(document: Dict[str, Any], entry: Dict[str, Any]) -> Dict[str, Any]:
    errors = validate_entry(entry, len(document.get("entries") or []))
    if errors:
        raise ValueError("; ".join(errors))
    existing = {item.get("entry_id") for item in document.get("entries") or []}
    if entry.get("entry_id") in existing:
        raise ValueError(f"duplicate entry_id {entry.get('entry_id')!r}")
    document.setdefault("entries", []).append(entry)
    return document


def advance(document: Dict[str, Any], entry_id: str, status: str, reason: str = "") -> Dict[str, Any]:
    if status not in STATUSES:
        raise ValueError(f"unknown status {status!r}")
    for entry in document.get("entries") or []:
        if entry.get("entry_id") != entry_id:
            continue
        current = entry.get("status")
        if status not in TRANSITIONS.get(current, ()):
            raise ValueError(f"{entry_id}: cannot move {current!r} -> {status!r}")
        if status == "wont_fix" and not reason.strip():
            raise ValueError(f"{entry_id}: wont_fix requires a reason")
        entry["status"] = status
        if reason:
            entry["reason"] = reason.strip()
        return document
    raise ValueError(f"no entry {entry_id!r}")
