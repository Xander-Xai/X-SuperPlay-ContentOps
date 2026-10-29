"""Platform safe-publishing policy: one plan, checked before upload.

A platform is not a place a finished video happens to go; it has its own title
length, CTA discipline, disclosure rules and rights expectations. Encoding those
as data means a plan can be refused before anyone records a cover or writes a
description, and the refusal names the platform.

This does not promise a platform will accept the post. It checks the plan
against the rules this account has chosen to follow.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

SCHEMA = "contentops.publish-plan/v1"
POLICY_SCHEMA = "contentops.platform-policy/v1"

RIGHTS_STATUSES = ("owned", "licensed", "public_domain", "permission", "unknown")

DEFAULT_POLICY: Dict[str, Any] = {
    "schema": POLICY_SCHEMA,
    "platforms": {
        "douyin": {"max_title_chars": 55, "max_hashtags": 5,
                   "allowed_rights": ["owned", "licensed", "public_domain", "permission"]},
        "bilibili": {"max_title_chars": 80, "max_hashtags": 10,
                     "allowed_rights": ["owned", "licensed", "public_domain", "permission"]},
        "xiaohongshu": {"max_title_chars": 20, "max_hashtags": 10,
                        "allowed_rights": ["owned", "licensed", "public_domain", "permission"]},
    },
    "forbidden_claim_phrases": ("保证", "稳赚", "100%", "全网最", "永久有效"),
    "rules": [
        "exactly one CTA per post",
        "AI-generated media requires an AI disclosure",
        "paid promotion requires a commercial disclosure",
        "an unknown rights status may not be published",
    ],
}


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def validate_plan(plan: Any, policy: Optional[Dict[str, Any]] = None) -> List[str]:
    policy = policy or DEFAULT_POLICY
    if not isinstance(plan, dict):
        return ["publish plan must be a JSON object"]
    if plan.get("schema") != SCHEMA:
        return [f"publish plan schema must be {SCHEMA!r}"]
    errors: List[str] = []

    platform = plan.get("platform")
    rules = (policy.get("platforms") or {}).get(platform)
    if rules is None:
        return [f"unknown platform {platform!r}"]

    title = _text(plan.get("title"))
    if not title:
        errors.append("title must be a non-empty string")
    elif len(title) > rules["max_title_chars"]:
        errors.append(f"title is {len(title)} chars, over the {platform} limit "
                      f"of {rules['max_title_chars']}")

    hashtags = plan.get("hashtags") or []
    if not isinstance(hashtags, list):
        errors.append("hashtags must be an array")
    elif len(hashtags) > rules["max_hashtags"]:
        errors.append(f"{len(hashtags)} hashtags, over the {platform} limit "
                      f"of {rules['max_hashtags']}")
    elif any(not _text(tag) for tag in hashtags):
        errors.append("hashtags must all be non-empty strings")

    cta_count = plan.get("cta_count")
    if cta_count != 1:
        errors.append(f"cta_count must be exactly 1, got {cta_count!r}")
    if not _text(plan.get("cta")):
        errors.append("cta must be a non-empty string")

    if plan.get("contains_generated_media") and not plan.get("ai_disclosure"):
        errors.append("AI-generated media requires ai_disclosure=true")
    if plan.get("commercial") and not plan.get("commercial_disclosure"):
        errors.append("paid promotion requires commercial_disclosure=true")

    rights = plan.get("rights_status")
    if rights not in RIGHTS_STATUSES:
        errors.append(f"rights_status must be one of {RIGHTS_STATUSES}")
    elif rights not in rules["allowed_rights"]:
        errors.append(f"rights_status {rights!r} is not publishable on {platform}")

    if not _text(plan.get("evidence_plan")):
        errors.append("evidence_plan must say which real material supports the claims")

    haystack = " ".join(_text(plan.get(key)) for key in ("title", "description", "cta"))
    for phrase in policy.get("forbidden_claim_phrases") or ():
        if phrase and phrase in haystack:
            errors.append(f"forbidden claim phrase {phrase!r} in the published copy")
    return errors


def plan_verdict(plan: Any, policy: Optional[Dict[str, Any]] = None) -> str:
    return "BLOCKED" if validate_plan(plan, policy) else "READY_FOR_APPROVAL"
