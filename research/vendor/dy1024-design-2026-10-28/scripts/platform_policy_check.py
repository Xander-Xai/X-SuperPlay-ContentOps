#!/usr/bin/env python3
"""Fail-closed preflight for multi-platform topic and copy plans.

This checker is an internal safety baseline, not a promise that a platform will
approve a post. It blocks known risky patterns and incomplete disclosure or
evidence metadata before a topic can enter a production package. Final manual
review against the current platform notice remains mandatory.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "configs" / "platform-policies" / "multi-platform-safe-publishing-v1.json"


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def text_blob(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(text_blob(item) for item in value)
    if isinstance(value, dict):
        return " ".join(text_blob(item) for item in value.values())
    return str(value) if value is not None else ""


def check_plan(plan: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    policy_id = str(policy.get("policy_id", ""))
    if plan.get("policy_id") != policy_id:
        errors.append(f"policy_id must be {policy_id}")
    if not str(plan.get("policy_verified_at", "")).strip():
        errors.append("policy_verified_at is required")

    supported = set(policy.get("supported_platforms", []))
    platforms = plan.get("platforms", [])
    if not isinstance(platforms, list) or not platforms:
        errors.append("platforms must be a non-empty list")
        platforms = []
    unknown = sorted(set(str(item) for item in platforms) - supported)
    if unknown:
        errors.append(f"unsupported platforms: {', '.join(unknown)}")

    topics = plan.get("topics", [])
    if not isinstance(topics, list) or len(topics) < 7:
        errors.append("the weekly plan must contain at least 7 topics")
        topics = []

    universal = policy.get("universal_guardrails", {})
    universal_blocked = [str(item) for item in universal.get("universal_blocked_patterns", [])]
    policy_platforms = policy.get("platforms", {})
    for index, topic in enumerate(topics, start=1):
        if not isinstance(topic, dict):
            errors.append(f"topics[{index}] must be an object")
            continue
        topic_id = str(topic.get("topic_id", f"index-{index}"))
        audience = topic.get("audience_validation")
        if not isinstance(audience, dict):
            errors.append(f"{topic_id}: audience_validation is required before a topic can be queued")
        else:
            if audience.get("status") != "approved":
                errors.append(f"{topic_id}: audience_validation.status must be approved before queueing")
            for field in ("viewer_quote", "viewer_trigger", "current_workaround", "pain_or_stakes", "desired_progress"):
                if not str(audience.get(field, "")).strip():
                    errors.append(f"{topic_id}: audience_validation.{field} is required")
            source_refs = audience.get("source_refs")
            if not isinstance(source_refs, list) or not source_refs or not all(str(item).strip() for item in source_refs):
                errors.append(f"{topic_id}: audience_validation.source_refs must contain at least one source")
        target_platforms = topic.get("target_platforms", [])
        if set(target_platforms) != set(platforms):
            errors.append(f"{topic_id}: target_platforms must match plan platforms")
        variants = topic.get("platform_variants", {})
        if not isinstance(variants, dict):
            errors.append(f"{topic_id}: platform_variants must be an object")
            continue
        for platform in platforms:
            variant = variants.get(platform)
            if not isinstance(variant, dict):
                errors.append(f"{topic_id}/{platform}: missing platform variant")
                continue
            required = ("safe_title", "hook", "body_beats", "cta", "evidence_plan", "rights_status", "ai_disclosure", "commercial_disclosure")
            for field in required:
                if field not in variant or variant.get(field) in (None, "", []):
                    errors.append(f"{topic_id}/{platform}: missing {field}")
            beats = variant.get("body_beats", [])
            if not isinstance(beats, list) or len(beats) < 3:
                errors.append(f"{topic_id}/{platform}: body_beats must contain at least 3 beats")
            cta_count = variant.get("cta_count", 1)
            if cta_count != 1:
                errors.append(f"{topic_id}/{platform}: exactly one CTA is required")
            if variant.get("rights_status") not in {"pending_review", "approved"}:
                errors.append(f"{topic_id}/{platform}: rights_status must be pending_review or approved")
            ai = variant.get("ai_disclosure")
            if not isinstance(ai, dict) or ai.get("is_ai_or_major_edit") is not True or not str(ai.get("label", "")).strip() or not str(ai.get("location", "")).strip():
                errors.append(f"{topic_id}/{platform}: AI disclosure is incomplete")
            commercial = variant.get("commercial_disclosure")
            if not isinstance(commercial, dict) or "is_promotional" not in commercial or not str(commercial.get("status", "")).strip():
                errors.append(f"{topic_id}/{platform}: commercial disclosure is incomplete")
            if variant.get("publish_status", "draft") != "draft":
                errors.append(f"{topic_id}/{platform}: planning variants must remain draft")
            if variant.get("human_review", {}).get("required") is not True:
                errors.append(f"{topic_id}/{platform}: human_review.required must be true")

            text = text_blob({
                "safe_title": variant.get("safe_title"),
                "hook": variant.get("hook"),
                "body_beats": variant.get("body_beats"),
                "cta": variant.get("cta"),
            }).casefold()
            blocked = universal_blocked + [str(item) for item in policy_platforms.get(platform, {}).get("blocked_patterns", [])]
            for phrase in blocked:
                if phrase and phrase.casefold() in text:
                    errors.append(f"{topic_id}/{platform}: blocked pattern detected: {phrase}")
            if variant.get("rights_status") == "pending_review":
                warnings.append(f"{topic_id}/{platform}: rights review is still pending")
            if variant.get("current_platform_notice_checked") is not True:
                warnings.append(f"{topic_id}/{platform}: current platform notice still needs manual verification")

        if str(topic.get("signal_status", "")) != "validated":
            errors.append(f"{topic_id}: signal_status must be validated before queueing a topic")

    return {
        "passed": not errors,
        "policy_id": policy_id,
        "project_id": plan.get("project_id", ""),
        "topic_count": len(topics),
        "platforms": platforms,
        "errors": errors,
        "warnings": warnings,
        "release_status": "blocked" if errors else "manual_review_required",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a multi-platform topic plan.")
    parser.add_argument("--input", required=True, help="topic plan JSON")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY), help="platform policy JSON")
    parser.add_argument("--strict", action="store_true", help="return non-zero on warnings too")
    args = parser.parse_args()
    try:
        result = check_plan(load_json(Path(args.input).expanduser().resolve()), load_json(Path(args.policy).expanduser().resolve()))
    except ValueError as error:
        print(json.dumps({"passed": False, "errors": [str(error)], "warnings": []}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if not result["passed"] or (args.strict and result["warnings"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
