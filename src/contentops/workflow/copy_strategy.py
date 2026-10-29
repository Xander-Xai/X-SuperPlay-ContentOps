"""Copy strategy card: choose an angle before writing a sentence.

The deterministic script checks can tell you a line is too long or unsupported.
They cannot tell you the episode has no angle. This card makes the editorial
choice explicit: which shelf, which viewer job, which angle, one thesis, three
hooks, and the argument beats the script must cover.

It is a contract, not a generator. Filling it is a human/model decision; passing
it only means the decision is complete and internally consistent.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from contentops.workflow.duration import default_policy
from contentops.workflow.topics import BROAD_TERMS, DEFAULT_SHELVES

SCHEMA = "contentops.copy-strategy/v1"

VIEWER_JOBS = ("understand", "decide", "act", "feel")
ARGUMENT_BEATS = (
    "problem", "hypothesis", "method", "evidence", "result",
    "limitation", "conclusion", "next_step",
)
REQUIRED_BEATS = ("problem", "evidence", "conclusion")

#: A small, curated catalogue. An angle is a promise about what the episode
#: does, so an unknown id is refused rather than free-formed.
ANGLE_LIBRARY = (
    {"id": "live-verification", "family": "现场验证", "shelf": "ai_tool_validation"},
    {"id": "limit-challenge", "family": "限制挑战", "shelf": "ai_tool_validation"},
    {"id": "ai-vs-ai", "family": "对照实验", "shelf": "ai_tool_validation"},
    {"id": "authority-compare", "family": "权威对照", "shelf": "ai_tool_validation"},
    {"id": "ai-traitor", "family": "反向验证", "shelf": "ai_tool_validation"},
    {"id": "failure-review", "family": "失败复盘", "shelf": "failure_boundary"},
    {"id": "process-reveal", "family": "过程揭秘", "shelf": "ai_real_business"},
    {"id": "job-challenge", "family": "岗位挑战", "shelf": "ai_real_business"},
    {"id": "role-swap", "family": "角色互换", "shelf": "ai_real_business"},
    {"id": "cost-breakdown", "family": "成本拆解", "shelf": "ai_native_one_person_company"},
    {"id": "user-test", "family": "用户测试", "shelf": "ai_native_one_person_company"},
    {"id": "payment-signal", "family": "付费信号", "shelf": "ai_native_one_person_company"},
    {"id": "counterfactual", "family": "后果推演", "shelf": "ai_native_one_person_company"},
    {"id": "audience-cocreation", "family": "观众共创", "shelf": "experimental"},
)
ANGLE_IDS = tuple(item["id"] for item in ANGLE_LIBRARY)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def validate_strategy(document: Any) -> List[str]:
    if not isinstance(document, dict):
        return ["copy strategy must be a JSON object"]
    if document.get("schema") != SCHEMA:
        return [f"copy strategy schema must be {SCHEMA!r}"]
    errors: List[str] = []
    for key in ("candidate_id", "thesis"):
        if not _text(document.get(key)):
            errors.append(f"{key} must be a non-empty string")
    if len(_text(document.get("thesis"))) > 60:
        errors.append("thesis is over 60 chars; a thesis is one sentence")

    if document.get("shelf") not in DEFAULT_SHELVES:
        errors.append(f"shelf must be one of {DEFAULT_SHELVES}")
    if document.get("viewer_job") not in VIEWER_JOBS:
        errors.append(f"viewer_job must be one of {VIEWER_JOBS}")

    angle_id = document.get("angle_id")
    angle = next((item for item in ANGLE_LIBRARY if item["id"] == angle_id), None)
    if angle is None:
        errors.append(f"angle_id must be one of {ANGLE_IDS}")
    elif document.get("shelf") and angle["shelf"] != document.get("shelf"):
        # An angle belongs to a shelf. Crossing them silently changes the promise.
        errors.append(f"angle {angle_id!r} belongs to shelf {angle['shelf']!r}, "
                      f"not {document.get('shelf')!r}")

    hooks = document.get("hook_variants")
    if not isinstance(hooks, list) or len(hooks) < 3:
        errors.append("hook_variants must hold at least three variants")
    else:
        cleaned = [_text(item) for item in hooks]
        if any(not item for item in cleaned):
            errors.append("hook variants must all be non-empty")
        if len(set(cleaned)) != len(cleaned):
            errors.append("hook variants must be distinct")
        for index, hook in enumerate(cleaned):
            if len(hook) > 30:
                errors.append(f"hook_variants[{index}] is over 30 chars")

    beats = document.get("argument_beats")
    if not isinstance(beats, list) or not beats:
        errors.append("argument_beats must be a non-empty array")
    else:
        unknown = [beat for beat in beats if beat not in ARGUMENT_BEATS]
        if unknown:
            errors.append(f"unknown argument beats: {unknown}")
        if len(set(beats)) != len(beats):
            errors.append("argument_beats must not repeat")
        missing = [beat for beat in REQUIRED_BEATS if beat not in beats]
        if missing:
            errors.append(f"argument_beats missing required beats: {missing}")

    claims = document.get("claim_ids")
    if not isinstance(claims, list) or not claims:
        errors.append("claim_ids must name the claims this script asserts")
    elif any(not _text(item) for item in claims):
        errors.append("claim_ids must all be non-empty strings")

    tier = document.get("duration_tier")
    known_tiers = {item["id"] for item in default_policy()["tiers"]}
    if tier not in known_tiers:
        errors.append(f"duration_tier must be one of {sorted(known_tiers)}")

    haystack = " ".join(_text(document.get(key)) for key in ("thesis", "shelf", "viewer_job"))
    for term in BROAD_TERMS:
        if term.lower() in haystack.lower():
            errors.append(f"broad audience term {term!r} does not identify who this is for")
    return errors


def angle(angle_id: str) -> Optional[Dict[str, str]]:
    return next((item for item in ANGLE_LIBRARY if item["id"] == angle_id), None)
