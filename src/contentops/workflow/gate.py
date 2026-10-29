"""The two-phase gate: a deterministic check, then a named human approval.

A stage has exactly two ways to move forward:

``check``
    Re-reads the artifact and every upstream artifact, runs optional validators
    and records the digests it looked at. Success moves the stage to
    ``ready_for_review``; failure moves it to ``blocked`` and lists why.

``approve``
    Requires a **fresh** successful check against the *same* digests, plus a
    named reviewer and an explicit ``confirm``. It cannot be called on a stage
    that was never checked, and it cannot survive a byte change.

There is no `--force`. Deliberately: the failure this gate exists to prevent is
a person in a hurry deciding that the gate is the obstacle.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from .contract import (
    WorkflowError,
    artifact_path,
    artifact_sha256,
    input_fingerprint,
    is_current,
    reconcile,
    stage_by_id,
)

Validator = Callable[[Path], Iterable[str]]

_JSON_SUFFIXES = (".json",)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stage(document: Dict[str, Any], stage_id: str) -> Dict[str, Any]:
    stage_by_id(stage_id)
    for item in document.get("stages", []):
        if item.get("id") == stage_id:
            return item
    raise WorkflowError("UNKNOWN_STAGE", f"{stage_id} is not in the workflow document")


def _validate_artifact(path: Path) -> List[str]:
    errors: List[str] = []
    if not path.is_file():
        return [f"artifact missing: {path.name}"]
    try:
        size = path.stat().st_size
    except OSError as exc:
        return [f"artifact unreadable: {exc}"]
    if size == 0:
        errors.append(f"artifact is empty: {path.name}")
    if path.suffix.lower() in _JSON_SUFFIXES:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            errors.append(f"artifact is not UTF-8: {path.name}")
        except json.JSONDecodeError as exc:
            errors.append(f"artifact is not valid JSON: {path.name}: {exc}")
        else:
            if not isinstance(document, (dict, list)):
                errors.append(f"artifact JSON must be an object or array: {path.name}")
    return errors


def check_stage(project: Path,
                document: Dict[str, Any],
                stage_id: str,
                validators: Optional[Sequence[Validator]] = None) -> Dict[str, Any]:
    """Run the deterministic half of the gate. Mutates ``document`` in place."""
    stage = stage_by_id(stage_id)
    item = _stage(document, stage_id)
    reconcile(project, document)

    errors: List[str] = []
    warnings: List[str] = []
    for dependency in stage.requires:
        ok, reason = is_current(project, document, dependency)
        if not ok:
            errors.append(f"upstream not current: {reason}")

    path = artifact_path(project, document, stage_id)
    errors.extend(_validate_artifact(path))

    for validator in validators or ():
        try:
            result = validator(path)
        except Exception as exc:  # a validator that crashes fails closed
            errors.append(f"validator {getattr(validator, '__name__', '?')} raised: {exc}")
            continue
        for message in result or ():
            if isinstance(message, str) and message:
                errors.append(message)

    sha = artifact_sha256(project, document, stage_id)
    inputs = input_fingerprint(project, document, stage_id)
    ok = not errors

    # A check that sees different bytes than the approval named retires the
    # approval instead of leaving a stale "approved" label beside fresh errors.
    approval = item.get("approval")
    if approval and sha != approval.get("artifact_sha256"):
        item["approval"] = None
        warnings.append("previous approval retired: artifact changed since it was approved")

    item["check"] = {
        "ok": ok,
        "errors": errors,
        "warnings": warnings,
        "artifact_sha256": sha,
        "inputs_sha256": inputs,
        "checked_at": _now(),
    }
    # Re-checking unchanged, already-approved bytes must not revoke an approval:
    # an idempotent check is not a new review.
    still_approved = bool(approval) and ok and sha == approval.get("artifact_sha256") \
        and inputs == approval.get("inputs_sha256")
    if still_approved:
        item["status"] = "approved"
    else:
        item["status"] = "ready_for_review" if ok else "blocked"
    item["stale"] = False if ok else bool(item.get("stale"))
    item["stale_reason"] = "" if ok else item.get("stale_reason", "")
    return {
        "stage": stage_id,
        "ok": ok,
        "errors": errors,
        "warnings": warnings,
        "artifact_sha256": sha,
        "inputs_sha256": inputs,
    }


def approve_stage(project: Path,
                  document: Dict[str, Any],
                  stage_id: str,
                  reviewer: str,
                  confirm: bool = False,
                  note: str = "") -> Dict[str, Any]:
    """Record an explicit approval of the bytes the last check inspected."""
    if not confirm:
        raise WorkflowError("CONFIRMATION_REQUIRED",
                            "approval requires --confirm; there is no implicit approval")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise WorkflowError("REVIEWER_REQUIRED", "approval requires a named reviewer")

    item = _stage(document, stage_id)
    reconcile(project, document)

    if item.get("status") != "ready_for_review":
        raise WorkflowError("CHECK_REQUIRED",
                            f"{stage_id} status is {item.get('status')!r}; run check successfully first")
    check = item.get("check")
    if not isinstance(check, dict) or not check.get("ok"):
        raise WorkflowError("CHECK_REQUIRED", f"{stage_id} has no successful check")

    current_sha = artifact_sha256(project, document, stage_id)
    current_inputs = input_fingerprint(project, document, stage_id)
    if current_sha != check.get("artifact_sha256"):
        raise WorkflowError("ARTIFACT_CHANGED",
                            f"{stage_id} artifact changed after the check; check again")
    if current_inputs != check.get("inputs_sha256"):
        raise WorkflowError("INPUTS_CHANGED",
                            f"{stage_id} upstream changed after the check; check again")

    stage = stage_by_id(stage_id)
    for dependency in stage.requires:
        ok, reason = is_current(project, document, dependency)
        if not ok:
            raise WorkflowError("UPSTREAM_NOT_CURRENT", reason)

    item["approval"] = {
        "reviewer": reviewer.strip(),
        "approved_at": _now(),
        "artifact_sha256": current_sha,
        "inputs_sha256": current_inputs,
        "note": note.strip(),
    }
    item["status"] = "approved"
    item["stale"] = False
    item["stale_reason"] = ""
    return {
        "stage": stage_id,
        "status": "approved",
        "reviewer": item["approval"]["reviewer"],
        "artifact_sha256": current_sha,
    }


def current_stage(document: Dict[str, Any]) -> Optional[str]:
    """The first stage that is not approved and current, in contract order."""
    for item in document.get("stages", []):
        if item.get("status") != "approved" or item.get("stale"):
            return item.get("id")
    return None
