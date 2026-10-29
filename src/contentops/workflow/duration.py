"""Duration policy: the length is a design decision, not a leftover.

A script that runs 40% over its window is not a pacing problem the editor can
fix; it is a scope problem. The source workflow encoded this as per-content-type
tiers with a rule: pick the content type's default, let evidence density
override it, never pad with repeated conclusions.

This module ports that rule as data plus one deterministic check. It does not
estimate speech duration -- `quality.script_rhythm` does that against the
declared rate. This decides whether the *target* itself is inside the band the
content type is allowed to occupy.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA = "contentops.duration-policy/v1"

#: Tiers are shared vocabulary, so a script's target can be compared across
#: accounts even when one account prefers shorter cuts.
DEFAULT_TIERS: Tuple[Dict[str, Any], ...] = (
    {"id": "one_minute", "label": "1分钟", "target_seconds": 60,
     "allowed_range_seconds": [45, 75]},
    {"id": "two_minute", "label": "2分钟", "target_seconds": 120,
     "allowed_range_seconds": [90, 150]},
    {"id": "three_minute", "label": "3分钟", "target_seconds": 180,
     "allowed_range_seconds": [150, 210]},
    {"id": "four_minute", "label": "4分钟", "target_seconds": 240,
     "allowed_range_seconds": [210, 270]},
    {"id": "five_minute", "label": "5分钟", "target_seconds": 300,
     "allowed_range_seconds": [270, 330]},
)

DEFAULT_CONTENT_TYPE_TIERS: Dict[str, str] = {
    "newsjacking": "one_minute",
    "tool_test": "two_minute",
    "technical_explainer": "two_minute",
    "comparison": "three_minute",
    "github_project": "three_minute",
    "monetization_case": "four_minute",
    "career_experiment": "three_minute",
    "business_experiment": "four_minute",
    "tutorial": "three_minute",
    "failure_review": "two_minute",
    "opinion": "one_minute",
}


def default_policy() -> Dict[str, Any]:
    return {
        "schema": SCHEMA,
        "tiers": [dict(item) for item in DEFAULT_TIERS],
        "content_type_defaults": dict(DEFAULT_CONTENT_TYPE_TIERS),
        "selection_rule": "content_type_default_then_evidence_density_override",
    }


def load_policy(path: Optional[Path]) -> Dict[str, Any]:
    if path is None:
        return default_policy()
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    return normalize_policy(document)


def normalize_policy(document: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate a policy document and return it in canonical shape."""
    if document is None:
        return default_policy()
    if not isinstance(document, dict):
        raise ValueError("duration policy must be a JSON object")
    if document.get("schema") != SCHEMA:
        raise ValueError(f"duration policy schema must be {SCHEMA!r}")
    tiers = document.get("tiers")
    if not isinstance(tiers, list) or not tiers:
        raise ValueError("duration policy tiers must be a non-empty array")
    seen = set()
    for index, tier in enumerate(tiers):
        if not isinstance(tier, dict):
            raise ValueError(f"tiers[{index}] must be an object")
        tier_id = tier.get("id")
        if not isinstance(tier_id, str) or not tier_id.strip():
            raise ValueError(f"tiers[{index}].id must be a non-empty string")
        if tier_id in seen:
            raise ValueError(f"duplicate tier id {tier_id!r}")
        seen.add(tier_id)
        target = tier.get("target_seconds")
        band = tier.get("allowed_range_seconds")
        if not isinstance(target, (int, float)) or target <= 0:
            raise ValueError(f"tiers[{index}].target_seconds must be positive")
        if not isinstance(band, list) or len(band) != 2:
            raise ValueError(f"tiers[{index}].allowed_range_seconds must be [min, max]")
        low, high = band
        if not (isinstance(low, (int, float)) and isinstance(high, (int, float))):
            raise ValueError(f"tiers[{index}].allowed_range_seconds must be numeric")
        if not low <= target <= high:
            raise ValueError(f"tiers[{index}].target_seconds must sit inside its band")
    defaults = document.get("content_type_defaults") or {}
    if not isinstance(defaults, dict):
        raise ValueError("content_type_defaults must be an object")
    for content_type, tier_id in defaults.items():
        if tier_id not in seen:
            raise ValueError(f"content_type {content_type!r} maps to unknown tier {tier_id!r}")
    return {
        "schema": SCHEMA,
        "tiers": [dict(item) for item in tiers],
        "content_type_defaults": dict(defaults),
        "selection_rule": document.get("selection_rule", ""),
    }


def tier_for_content_type(content_type: str, policy: Optional[Dict[str, Any]] = None) -> Optional[str]:
    policy = policy or default_policy()
    return policy["content_type_defaults"].get(content_type)


def _tier(policy: Dict[str, Any], tier_id: str) -> Optional[Dict[str, Any]]:
    return next((item for item in policy["tiers"] if item["id"] == tier_id), None)


def validate_duration(seconds: float,
                      *,
                      content_type: Optional[str] = None,
                      tier: Optional[str] = None,
                      policy: Optional[Dict[str, Any]] = None) -> List[str]:
    """Check a target duration against the tier its content type owns."""
    policy = normalize_policy(policy)
    errors: List[str] = []
    resolved = tier
    if content_type is not None:
        by_type = tier_for_content_type(content_type, policy)
        if by_type is None:
            errors.append(f"content_type {content_type!r} has no duration tier")
        elif resolved is not None and resolved != by_type:
            errors.append(f"content_type {content_type!r} maps to {by_type!r}, not {resolved!r}")
        else:
            resolved = by_type
    if resolved is None:
        errors.append("either content_type or tier must be supplied")
        return errors
    item = _tier(policy, resolved)
    if item is None:
        errors.append(f"unknown tier {resolved!r}")
        return errors
    low, high = item["allowed_range_seconds"]
    if not isinstance(seconds, (int, float)) or isinstance(seconds, bool):
        errors.append("duration must be a number")
    elif not low <= seconds <= high:
        errors.append(f"{seconds:g}s is outside the {resolved} band {low:g}-{high:g}s")
    return errors


def validate_script_duration(path: Path) -> List[str]:
    """Read a script document and check its declared target against its tier.

    A script with no ``content_type`` is not checked here: it may predate the
    policy, and guessing a type from its text would be exactly the invented
    metadata this repository refuses.
    """
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"script is not readable JSON: {exc}"]
    if not isinstance(document, dict):
        return ["script must be a JSON object"]
    content_type = document.get("content_type")
    if not content_type:
        return []
    target = document.get("target_seconds")
    if not isinstance(target, (int, float)):
        return ["script declares content_type but no numeric target_seconds"]
    return validate_duration(target, content_type=content_type, tier=document.get("tier"))
