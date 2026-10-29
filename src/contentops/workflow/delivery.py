"""Delivery manifest: the bundle is only as good as its listed bytes.

A delivery is not "the folder beside the video". It is an explicit list of
files, each with a role and a digest, plus a statement that the stage gates
were current when the bundle was made. Anything not listed is not delivered.

The manifest never marks a video published. Publication is a separate human
approval; this only says the bundle is complete and internally consistent.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from contentops.workflow.naming import validate_content_id

SCHEMA = "contentops.delivery-manifest/v1"

ROLES = ("video", "cover", "caption", "copy", "receipt", "evidence")
HUMAN_REVIEW = ("PENDING", "APPROVED", "REJECTED")
_SHA = re.compile(r"^[0-9a-f]{64}$")


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def validate_manifest(document: Any) -> List[str]:
    if not isinstance(document, dict):
        return ["delivery manifest must be a JSON object"]
    if document.get("schema") != SCHEMA:
        return [f"delivery manifest schema must be {SCHEMA!r}"]
    errors: List[str] = []
    content_id = document.get("content_id")
    try:
        validate_content_id(content_id)
    except ValueError as exc:
        errors.append(str(exc))
    if not _text(document.get("platform")):
        errors.append("platform must be a non-empty string")

    files = document.get("files")
    if not isinstance(files, list) or not files:
        errors.append("files must be a non-empty array")
        files = []
    seen = set()
    roles = set()
    for index, item in enumerate(files):
        where = f"files[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{where} must be an object")
            continue
        path = _text(item.get("path"))
        if not path:
            errors.append(f"{where}.path must be a non-empty string")
        elif path.startswith(("/", "\\")) or ":" in path:
            errors.append(f"{where}.path must be relative, not absolute")
        elif path in seen:
            errors.append(f"{where}.path duplicates {path!r}")
        else:
            seen.add(path)
        if not _SHA.match(str(item.get("sha256") or "")):
            errors.append(f"{where}.sha256 must be 64 lowercase hex")
        role = item.get("role")
        if role not in ROLES:
            errors.append(f"{where}.role must be one of {ROLES}")
        else:
            roles.add(role)
    if files and "video" not in roles:
        errors.append("delivery must include at least one file with role 'video'")

    gate = document.get("gate")
    if not isinstance(gate, dict):
        errors.append("gate must be an object recording the stage state")
    else:
        if not _text(gate.get("contract")):
            errors.append("gate.contract must name the production contract")
        if gate.get("stages_current") is not True:
            errors.append("gate.stages_current must be true at delivery time")

    review = document.get("human_review")
    if review not in HUMAN_REVIEW:
        errors.append(f"human_review must be one of {HUMAN_REVIEW}")
    return errors


def summary(document: Dict[str, Any]) -> Dict[str, Any]:
    files = [item for item in (document.get("files") or []) if isinstance(item, dict)]
    return {
        "content_id": document.get("content_id"),
        "file_count": len(files),
        "roles": sorted({str(item.get("role")) for item in files if item.get("role")}),
        "human_review": document.get("human_review"),
    }
