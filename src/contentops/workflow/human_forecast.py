"""Evidence feasibility forecast: decide before production, not after.

The expensive failure is a topic that is chosen and scripted before anyone asks
whether the evidence exists. A forecast is one page, written before the Brief:
which captures the claims need, who produces them, whether they are available,
and what to do if they are not.

This is not a production approval. A feasible forecast means "the evidence path
is declared", not "the evidence has been gathered", and not "the video is good".
"""

from __future__ import annotations

from typing import Any, Dict, List

SCHEMA = "contentops.evidence-feasibility/v1"

EVIDENCE_KINDS = (
    "screen_recording", "terminal_capture", "real_screenshot", "real_document",
    "measurement", "authoritative_source", "none",
)
OWNERS = ("human", "automated")
FAILURE_PLANS = ("change_topic", "change_claim", "stop", "degrade_and_declare")
VERDICTS = ("FEASIBLE", "DEGRADED", "BLOCKED")


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def validate_forecast(document: Any) -> List[str]:
    if not isinstance(document, dict):
        return ["forecast must be a JSON object"]
    if document.get("schema") != SCHEMA:
        return [f"forecast schema must be {SCHEMA!r}"]
    errors: List[str] = []
    if not _text(document.get("topic_id")):
        errors.append("topic_id must be a non-empty string")
    if not _text(document.get("assessment_basis")):
        errors.append("assessment_basis must state why this forecast is what it is")

    items = document.get("evidence")
    if not isinstance(items, list) or not items:
        errors.append("evidence must be a non-empty array")
        return errors
    any_missing = False
    for index, item in enumerate(items):
        where = f"evidence[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{where} must be an object")
            continue
        if item.get("kind") not in EVIDENCE_KINDS:
            errors.append(f"{where}.kind must be one of {EVIDENCE_KINDS}")
        if not isinstance(item.get("required"), bool):
            errors.append(f"{where}.required must be a boolean")
        if item.get("owner") not in OWNERS:
            errors.append(f"{where}.owner must be one of {OWNERS}")
        if not isinstance(item.get("available"), bool):
            errors.append(f"{where}.available must be a boolean")
        if item.get("required") is True and item.get("available") is False:
            any_missing = True
        if item.get("kind") == "none" and item.get("required") is True:
            errors.append(f"{where} declares required evidence of kind 'none'")

    plan = document.get("failure_plan")
    if plan not in FAILURE_PLANS:
        errors.append(f"failure_plan must be one of {FAILURE_PLANS}")
    if any_missing and plan == "degrade_and_declare" and not _text(document.get("degrade_note")):
        errors.append("degrade_and_declare requires a degrade_note that names the quality impact")
    return errors


def forecast_verdict(document: Any) -> str:
    """FEASIBLE / DEGRADED / BLOCKED, derived from what the document declares."""
    errors = validate_forecast(document)
    if errors:
        return "BLOCKED"
    items = document.get("evidence") or []
    required_missing = [item for item in items
                        if item.get("required") is True and item.get("available") is False]
    if not required_missing:
        return "FEASIBLE"
    if document.get("failure_plan") == "degrade_and_declare":
        return "DEGRADED"
    return "BLOCKED"


def required_evidence(document: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [item for item in (document.get("evidence") or [])
            if isinstance(item, dict) and item.get("required") is True]
