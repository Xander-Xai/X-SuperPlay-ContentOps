#!/usr/bin/env python3
"""Shared duration ladder and content-type selection rules for X•超玩1024.

The ladder uses target durations with bounded production windows.  A target
comes from the content type by default, but an explicit tier or target may
override that default when the evidence and narrative scope justify it.
"""

from __future__ import annotations

import math
from typing import Any


DEFAULT_TIERS: list[dict[str, Any]] = [
    {"id": "one_minute", "label": "1分钟", "target_seconds": 60, "allowed_range_seconds": [45, 75]},
    {"id": "two_minute", "label": "2分钟", "target_seconds": 120, "allowed_range_seconds": [90, 150]},
    {"id": "three_minute", "label": "3分钟", "target_seconds": 180, "allowed_range_seconds": [150, 210]},
    {"id": "four_minute", "label": "4分钟", "target_seconds": 240, "allowed_range_seconds": [210, 270]},
    {"id": "five_minute", "label": "5分钟", "target_seconds": 300, "allowed_range_seconds": [270, 330]},
]

DEFAULT_CONTENT_TYPE_DEFAULTS: dict[str, str] = {
    "newsjacking": "one_minute",
    "tool_test": "two_minute",
    "comparison": "three_minute",
    "github_project": "three_minute",
    "monetization_case": "four_minute",
    "tutorial": "three_minute",
    "failure_review": "two_minute",
    "opinion": "one_minute",
}

TIER_ALIASES = {
    "1": "one_minute",
    "1m": "one_minute",
    "60": "one_minute",
    "60s": "one_minute",
    "one-minute": "one_minute",
    "one_minute": "one_minute",
    "2": "two_minute",
    "2m": "two_minute",
    "120": "two_minute",
    "120s": "two_minute",
    "two-minute": "two_minute",
    "two_minute": "two_minute",
    "3": "three_minute",
    "3m": "three_minute",
    "180": "three_minute",
    "180s": "three_minute",
    "three-minute": "three_minute",
    "three_minute": "three_minute",
    "4": "four_minute",
    "4m": "four_minute",
    "240": "four_minute",
    "240s": "four_minute",
    "four-minute": "four_minute",
    "four_minute": "four_minute",
    "5": "five_minute",
    "5m": "five_minute",
    "300": "five_minute",
    "300s": "five_minute",
    "five-minute": "five_minute",
    "five_minute": "five_minute",
}


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _valid_tiers(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return [dict(item) for item in DEFAULT_TIERS]
    if not isinstance(raw, list) or len(raw) != len(DEFAULT_TIERS):
        raise ValueError("duration_policy.tiers must contain exactly five tier objects")
    tiers: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("duration_policy.tiers contains a non-object")
        tier_id = canonical_tier_id(item.get("id"))
        target = item.get("target_seconds")
        window = item.get("allowed_range_seconds")
        if not tier_id or tier_id in seen:
            raise ValueError(f"invalid or duplicate duration tier id: {item.get('id')}")
        if not _finite_number(target) or not isinstance(window, list) or len(window) != 2 or not all(_finite_number(value) for value in window):
            raise ValueError(f"invalid duration tier values: {tier_id or item.get('id')}")
        lower, upper = float(window[0]), float(window[1])
        target_value = float(target)
        if lower <= 0 or lower > target_value or target_value > upper:
            raise ValueError(f"duration tier window does not contain target: {tier_id}")
        seen.add(tier_id)
        tiers.append({
            "id": tier_id,
            "label": str(item.get("label") or tier_id),
            "target_seconds": int(target_value) if target_value.is_integer() else target_value,
            "allowed_range_seconds": [lower, upper],
        })
    expected = {item["id"] for item in DEFAULT_TIERS}
    if seen != expected:
        raise ValueError(f"duration_policy.tiers must define exactly {sorted(expected)}")
    tiers.sort(key=lambda item: float(item["target_seconds"]))
    for previous, current in zip(tiers, tiers[1:]):
        if float(previous["allowed_range_seconds"][1]) > float(current["allowed_range_seconds"][0]):
            raise ValueError("duration tier windows must be ordered and non-overlapping except at shared boundaries")
    return tiers


def policy_from_profile(profile: dict[str, Any]) -> dict[str, Any]:
    video = profile.get("video", {}) if isinstance(profile.get("video"), dict) else {}
    raw_value = video.get("duration_policy")
    if raw_value in (None, {}):
        raw: dict[str, Any] = {}
    elif isinstance(raw_value, dict):
        raw = raw_value
    else:
        raise ValueError("video.duration_policy must be an object")
    tiers = _valid_tiers(raw.get("tiers"))
    defaults = dict(DEFAULT_CONTENT_TYPE_DEFAULTS)
    configured = raw.get("content_type_defaults")
    if configured is not None and not isinstance(configured, dict):
        raise ValueError("duration_policy.content_type_defaults must be an object")
    if isinstance(configured, dict):
        for content_type, tier in configured.items():
            canonical = canonical_tier_id(tier)
            if not canonical or canonical not in {item["id"] for item in tiers}:
                raise ValueError(f"unknown duration tier for content type {content_type}: {tier}")
            defaults[str(content_type).strip().lower()] = canonical
    default_tier = canonical_tier_id(raw.get("default_tier")) or "two_minute"
    if default_tier not in {item["id"] for item in tiers}:
        raise ValueError(f"unknown default duration tier: {raw.get('default_tier')}")
    overall = video.get("duration_seconds")
    if overall is None:
        overall = [tiers[0]["allowed_range_seconds"][0], tiers[-1]["allowed_range_seconds"][1]]
    if not isinstance(overall, list) or len(overall) != 2 or not all(_finite_number(value) for value in overall):
        raise ValueError("video.duration_seconds must be a finite two-number range")
    overall_values = [float(overall[0]), float(overall[1])]
    tier_bounds = [float(tiers[0]["allowed_range_seconds"][0]), float(tiers[-1]["allowed_range_seconds"][1])]
    if overall_values[0] > overall_values[1] or overall_values[0] > tier_bounds[0] or overall_values[1] < tier_bounds[1]:
        raise ValueError("video.duration_seconds must cover the full five-tier ladder")
    return {
        "tiers": tiers,
        "default_tier": default_tier,
        "content_type_defaults": defaults,
        "overall_range_seconds": overall_values,
    }


def canonical_tier_id(value: Any) -> str:
    raw = str(value or "").strip().lower().replace(" ", "")
    return TIER_ALIASES.get(raw, raw if raw in {item["id"] for item in DEFAULT_TIERS} else "")


def tier_map(policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["id"]): item for item in policy.get("tiers", []) if isinstance(item, dict) and item.get("id")}


def infer_tier_id(policy: dict[str, Any], target_seconds: float | int | None) -> str:
    tiers = [item for item in policy.get("tiers", []) if isinstance(item, dict)]
    if not tiers:
        return "two_minute"
    if target_seconds is None:
        return str(policy.get("default_tier") or tiers[0]["id"])
    if not _finite_number(target_seconds) or float(target_seconds) <= 0:
        raise ValueError("target_seconds must be a positive finite number")
    target = float(target_seconds)
    overall = policy.get("overall_range_seconds", [tiers[0]["allowed_range_seconds"][0], tiers[-1]["allowed_range_seconds"][1]])
    if target < float(overall[0]) or target > float(overall[1]):
        raise ValueError(f"target_seconds {target:g} is outside the overall duration ladder")
    containing = [
        item for item in tiers
        if float(item["allowed_range_seconds"][0]) <= target <= float(item["allowed_range_seconds"][1])
    ]
    candidates = containing or tiers
    selected = min(candidates, key=lambda item: abs(float(item["target_seconds"]) - target))
    return str(selected["id"])


def resolve_tier(
    policy: dict[str, Any],
    content_type: str = "",
    requested_tier: str = "",
    target_seconds: float | int | None = None,
) -> dict[str, Any]:
    tiers = tier_map(policy)
    requested = canonical_tier_id(requested_tier)
    content_key = str(content_type or "").strip().lower()
    if requested_tier and not requested:
        raise ValueError(f"unknown duration tier: {requested_tier}")
    if requested in tiers:
        selected_id = requested
        selection_reason = "explicit duration tier"
    elif target_seconds is not None:
        selected_id = infer_tier_id(policy, target_seconds)
        selection_reason = "tier inferred from target seconds"
    else:
        selected_id = str(policy.get("content_type_defaults", {}).get(content_key, policy.get("default_tier", "two_minute")))
        if selected_id not in tiers:
            selected_id = str(policy.get("default_tier", "two_minute"))
        selection_reason = f"default for content type: {content_key or 'unknown'}"
    if selected_id not in tiers:
        raise ValueError(f"duration tier is not configured: {selected_id}")
    selected = dict(tiers[selected_id])
    if target_seconds is not None:
        target = float(target_seconds)
        lower, upper = [float(value) for value in selected["allowed_range_seconds"]]
        if target < lower or target > upper:
            raise ValueError(f"target_seconds {target:g} is outside {selected['id']} range {lower:g}–{upper:g}")
    selected["selection_reason"] = selection_reason
    selected["content_type"] = content_key
    return selected


def tier_for_target(policy: dict[str, Any], target_seconds: float | int) -> dict[str, Any]:
    return resolve_tier(policy, target_seconds=target_seconds)


def adjust_for_complexity(
    policy: dict[str, Any],
    tier: dict[str, Any],
    *,
    evidence_count: int = 0,
    step_count: int = 0,
    comparison_dimensions: int = 0,
) -> dict[str, Any]:
    """Promote a default tier when the brief declares extra production scope."""
    counts = (evidence_count, step_count, comparison_dimensions)
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts):
        raise ValueError("complexity counts must be non-negative integers")
    should_promote = evidence_count >= 4 or step_count >= 6 or comparison_dimensions >= 3
    tiers = list(policy.get("tiers", []))
    index = next((index for index, item in enumerate(tiers) if item.get("id") == tier.get("id")), 0)
    selected = dict(tiers[min(index + (1 if should_promote else 0), len(tiers) - 1)])
    selected["content_type"] = tier.get("content_type", "")
    if should_promote:
        selected["selection_reason"] = (
            f"complexity override: evidence={evidence_count}, steps={step_count}, dimensions={comparison_dimensions}"
        )
    else:
        selected["selection_reason"] = tier.get("selection_reason", "content type default")
    return selected


def format_range(tier: dict[str, Any]) -> str:
    lower, upper = tier.get("allowed_range_seconds", [0, 0])
    def fmt(value: Any) -> str:
        number = float(value)
        return str(int(number)) if number.is_integer() else f"{number:g}"
    return f"{fmt(lower)}–{fmt(upper)}s"
