"""Feedback and metrics import: the loop that says whether a cut worked.

Publishing is not the end of the pipeline; it is the only place the account
learns anything. Two documents keep that learning honest:

- a **feedback** record per published item, with the platform metrics that were
  actually observed and the signals a human chose to record;
- a **metrics import** document, which is the raw hand-off from a platform
  export, kept separate so a later correction does not rewrite the learning.

Neither document may contain an inferred metric. A missing number stays missing;
a zero means the platform reported zero.
"""

from __future__ import annotations

from typing import Any, Dict, List

FEEDBACK_SCHEMA = "contentops.feedback/v1"
METRICS_SCHEMA = "contentops.metrics-import/v1"

FEEDBACK_STATUSES = ("drafted", "published", "failed", "removed")
METRIC_KEYS = ("views", "likes", "comments", "shares", "saves", "avg_watch_s")


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _metric_errors(metrics: Any, where: str) -> List[str]:
    if metrics is None:
        return []
    if not isinstance(metrics, dict):
        return [f"{where} must be an object"]
    errors: List[str] = []
    for key, value in metrics.items():
        if key not in METRIC_KEYS:
            errors.append(f"{where}.{key} is not a known metric")
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            errors.append(f"{where}.{key} must be a non-negative number")
    return errors


def validate_feedback(document: Any) -> List[str]:
    if not isinstance(document, dict):
        return ["feedback must be a JSON object"]
    if document.get("schema") != FEEDBACK_SCHEMA:
        return [f"feedback schema must be {FEEDBACK_SCHEMA!r}"]
    errors: List[str] = []
    if not _text(document.get("content_id")):
        errors.append("content_id must be a non-empty string")
    if not _text(document.get("platform")):
        errors.append("platform must be a non-empty string")
    status = document.get("status")
    if status not in FEEDBACK_STATUSES:
        errors.append(f"status must be one of {FEEDBACK_STATUSES}")
    if status == "published":
        if not _text(document.get("published_url")):
            errors.append("a published item must carry published_url")
        if not _text(document.get("published_at")):
            errors.append("a published item must carry published_at")
    errors.extend(_metric_errors(document.get("metrics"), "metrics"))
    signals = document.get("signals")
    if signals is not None:
        if not isinstance(signals, list) or any(not _text(item) for item in signals):
            errors.append("signals must be an array of non-empty strings")
    return errors


def validate_metrics_import(document: Any) -> List[str]:
    if not isinstance(document, dict):
        return ["metrics import must be a JSON object"]
    if document.get("schema") != METRICS_SCHEMA:
        return [f"metrics import schema must be {METRICS_SCHEMA!r}"]
    rows = document.get("rows")
    if not isinstance(rows, list) or not rows:
        return ["rows must be a non-empty array"]
    errors: List[str] = []
    for index, row in enumerate(rows):
        where = f"rows[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{where} must be an object")
            continue
        if not _text(row.get("content_id")):
            errors.append(f"{where}.content_id must be a non-empty string")
        if not _text(row.get("platform")):
            errors.append(f"{where}.platform must be a non-empty string")
        errors.extend(_metric_errors(row.get("metrics"), f"{where}.metrics"))
    return errors


def merge_metrics(feedback: Dict[str, Any], metrics_row: Dict[str, Any]) -> Dict[str, Any]:
    """Return a new feedback document with imported metrics applied.

    Only keys the platform actually reported are written. The original document
    is not mutated, so a bad import cannot silently rewrite the learning record.
    """
    if feedback.get("content_id") != metrics_row.get("content_id"):
        raise ValueError("metrics row does not belong to this feedback record")
    merged = dict(feedback)
    metrics = dict(feedback.get("metrics") or {})
    for key, value in (metrics_row.get("metrics") or {}).items():
        if key in METRIC_KEYS:
            metrics[key] = value
    merged["metrics"] = metrics
    return merged
