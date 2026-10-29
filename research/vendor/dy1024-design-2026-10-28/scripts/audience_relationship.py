#!/usr/bin/env python3
"""Validate nullable four-layer audience relationship metrics.

This is a content-side projection. Revenue Attribution remains the canonical
business attribution source; missing platform data is intentionally null.
"""

from __future__ import annotations

from typing import Any

NUMERIC_FIELDS = {
    "views", "impressions", "reach", "watch_time_seconds", "average_watch_seconds",
    "completion_rate", "save", "share", "comment", "first_time_viewers", "repeat_viewers",
    "followers_from_content", "profile_visits", "qualified_interactions", "inbound_intent",
    "qualified_intent", "lead", "opportunity", "deal", "revenue", "assisted_revenue",
    "target_audience_exposures", "repeat_viewer_rate",
}
RATIO_FIELDS = {"completion_rate", "repeat_viewer_rate"}


def _valid_nullable_number(value: Any, *, ratio: bool = False) -> bool:
    if value is None:
        return True
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        return False
    return not ratio or value <= 1


def _walk(section: Any, path: str, errors: list[str]) -> None:
    if not isinstance(section, dict):
        errors.append(f"{path} must be an object")
        return
    for key, value in section.items():
        if key in NUMERIC_FIELDS and not _valid_nullable_number(value, ratio=key in RATIO_FIELDS):
            errors.append(f"{path}.{key} must be a non-negative number or null")
        elif isinstance(value, dict):
            _walk(value, f"{path}.{key}", errors)


def validate_relationship(value: Any, *, content_id: str | None = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["audience relationship must be an object"]
    if value.get("schema_version") != 1 or value.get("contract") != "audience-relationship-v1":
        errors.append("audience relationship contract must be audience-relationship-v1/schema 1")
    if content_id and value.get("content_id") != content_id:
        errors.append("audience relationship content_id does not match content package")
    if value.get("source") not in {None, "official-api", "creator-export", "manual"}:
        errors.append("audience relationship source is invalid")
    layers = value.get("layers")
    if not isinstance(layers, dict):
        errors.append("audience relationship layers are required")
    else:
        for name in ("L1_distribution", "L2_content_quality", "L3_audience_relationship", "L4_business"):
            if name not in layers:
                errors.append(f"audience relationship is missing {name}")
        _walk(layers, "layers", errors)
    repeated = value.get("repeated_exposure")
    if not isinstance(repeated, dict):
        errors.append("repeated_exposure is required")
    else:
        _walk(repeated, "repeated_exposure", errors)
    if not str(value.get("attribution_ref", "")).strip():
        errors.append("attribution_ref must point to Revenue Attribution")
    return errors


def build_scaffold(content_id: str, *, candidate_id: str | None = None) -> dict[str, Any]:
    nulls = {
        "views": None, "impressions": None, "reach": None,
        "watch_time_seconds": None, "average_watch_seconds": None, "completion_rate": None,
        "save": None, "share": None, "comment": None,
        "first_time_viewers": None, "repeat_viewers": None, "followers_from_content": None,
        "profile_visits": None, "qualified_interactions": None, "inbound_intent": None,
        "qualified_intent": None, "lead": None, "opportunity": None, "deal": None,
        "revenue": None, "assisted_revenue": None,
    }
    return {
        "schema_version": 1,
        "contract": "audience-relationship-v1",
        "content_id": content_id,
        "content_candidate_id": candidate_id,
        "publication_id": None,
        "captured_at": None,
        "source": None,
        "layers": {
            "L1_distribution": {key: nulls[key] for key in ("views", "impressions", "reach")},
            "L2_content_quality": {key: nulls[key] for key in ("watch_time_seconds", "average_watch_seconds", "completion_rate", "save", "share", "comment")},
            "L3_audience_relationship": {key: nulls[key] for key in ("first_time_viewers", "repeat_viewers", "followers_from_content", "profile_visits", "qualified_interactions", "inbound_intent")},
            "L4_business": {key: nulls[key] for key in ("qualified_intent", "lead", "opportunity", "deal", "revenue", "assisted_revenue")},
        },
        "repeated_exposure": {"target_audience_exposures": None, "repeat_viewer_rate": None, "method": None},
        "attribution_ref": "09_feedback/revenue-attribution.json",
        "notes": ["null means unavailable; zero is only valid when the source explicitly confirmed none occurred.", "No user-level tracking, fingerprinting or inferred repeat viewers."],
    }
