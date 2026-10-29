"""Shared material-plan contract and filename validation.

The material route has two distinct approvals:

* ``assets_plan`` approves a reviewable request list before acquisition;
* ``assets`` clears acquired files, rights and technical/visual evidence.

This module keeps the per-beat responsibility and naming contract in one
place so the planner and both gates cannot silently drift apart.
"""

from __future__ import annotations

import re
from pathlib import PurePath
from typing import Any


MATERIAL_CONTRACT_VERSION = 1
AUTOMATION_MODES = {"automatic", "hybrid", "human-required"}
HUMAN_CONFIRMATION_STATUSES = {"not-required", "pending", "confirmed", "rejected"}
NAMING_CHECK_STATUSES = {"planned", "pending", "passed", "failed"}
RECORDING_MODES = {"browser_evidence", "terminal_evidence", "whiteboard_excalidraw", "html_demo", "task_screen", "browser_behavior"}
DIRECT_OBSERVATION_RECORDING_MODES = {"browser_evidence", "terminal_evidence", "html_demo", "task_screen", "browser_behavior"}
MATERIAL_REQUIRED_FIELDS = (
    "scene_id",
    "viewer_job",
    "route",
    "visual_owner",
    "source_strategy",
    "rights_plan",
    "fallback",
    "fact_status",
    "automation_mode",
    "automation_owner",
    "human_owner",
    "human_confirmation_required",
    "human_confirmation_status",
    "filename_template",
    "expected_filename",
    "naming_check",
)


def slug(value: Any, fallback: str = "asset") -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(value or "").casefold()).strip("-")
    return text[:80] or fallback


def filename_template(content_id: Any, scene_id: Any, asset_id: Any, route: Any) -> str:
    return (
        f"{slug(content_id, 'content')}__{slug(scene_id, 'scene')}__"
        f"{slug(asset_id, 'asset')}__{slug(route, 'route')}__vNN.<ext>"
    )


def filename_pattern(template: str) -> re.Pattern[str]:
    """Compile a canonical template into a strict lower-ASCII filename regex."""
    escaped = re.escape(str(template or ""))
    escaped = escaped.replace(r"vNN", r"v\d{2}").replace("<ext>", r"[a-z0-9]{1,8}")
    return re.compile(r"^" + escaped + r"$")


def filename_matches(template: str, value: Any) -> bool:
    name = PurePath(str(value or "").replace("\\", "/")).name
    return bool(name and filename_pattern(template).fullmatch(name))


def concrete_filename(template: str, extension: str, version: int = 1) -> str:
    """Render a canonical ``vNN.<ext>`` template into a deterministic name."""
    suffix = str(extension or "").lstrip(".").casefold()
    if not re.fullmatch(r"[a-z0-9]{1,8}", suffix):
        suffix = "bin"
    return str(template).replace("vNN", f"v{int(version):02d}").replace("<ext>", suffix)


def naming_errors(template: str, value: Any) -> list[str]:
    name = PurePath(str(value or "").replace("\\", "/")).name
    errors: list[str] = []
    if not name:
        return ["filename is empty"]
    if not re.fullmatch(r"[a-z0-9._-]+", name):
        errors.append("filename must use lower ASCII, digits, dots and hyphens only")
    if not filename_matches(template, name):
        errors.append(f"filename does not match template: {template}")
    return errors


def plan_item_errors(item: dict[str, Any], index: int, *, final: bool = False) -> list[str]:
    errors: list[str] = []
    prefix = f"material beat {index}"
    for field in MATERIAL_REQUIRED_FIELDS:
        value = item.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append(f"{prefix} missing {field}")
    mode = str(item.get("automation_mode", "")).strip()
    if mode not in AUTOMATION_MODES:
        errors.append(f"{prefix} has invalid automation_mode: {mode}")
    confirmation_status = str(item.get("human_confirmation_status", "")).strip()
    if confirmation_status not in HUMAN_CONFIRMATION_STATUSES:
        errors.append(f"{prefix} has invalid human_confirmation_status")
    if not isinstance(item.get("human_confirmation_required"), bool):
        errors.append(f"{prefix} human_confirmation_required must be boolean")
    if item.get("human_confirmation_required") is True and not str(item.get("human_owner", "")).strip():
        errors.append(f"{prefix} requires human_owner")
    naming_status = str(item.get("naming_check", "")).strip()
    if naming_status not in NAMING_CHECK_STATUSES:
        errors.append(f"{prefix} has invalid naming_check")
    template = str(item.get("filename_template", "")).strip()
    if template and not re.fullmatch(r"[a-z0-9-]+(?:__[a-z0-9-]+){3}__vNN\.<ext>", template):
        errors.append(f"{prefix} filename_template is not canonical")
    if final:
        if naming_status != "passed":
            errors.append(f"{prefix} naming_check must be passed before assets clearance")
        if item.get("human_confirmation_required") is True and confirmation_status != "confirmed":
            errors.append(f"{prefix} human confirmation is not confirmed")
    return errors


def default_responsibility(route: str, visual_owner: str, source_strategy: str, asset_type: str) -> dict[str, Any]:
    combined = " ".join((route, visual_owner, source_strategy, asset_type)).casefold()
    if route == "cultural":
        return {"automation_mode": "human-required", "automation_owner": "broll-production", "human_owner": "user", "human_confirmation_required": True}
    if route == "product-ui" or any(token in combined for token in ("screen recording", "录屏", "github")):
        return {"automation_mode": "hybrid", "automation_owner": "material-source-research", "human_owner": "user", "human_confirmation_required": True}
    if route == "generated-gap" or asset_type == "generated":
        generator = "chatgpt-bridge"
        return {"automation_mode": "automatic", "automation_owner": generator, "human_owner": "content-reviewer", "human_confirmation_required": True}
    if route == "concept-motion" or visual_owner in {"remotion", "hyperframes"}:
        return {"automation_mode": "automatic", "automation_owner": visual_owner or "remotion", "human_owner": "content-reviewer", "human_confirmation_required": True}
    return {"automation_mode": "hybrid", "automation_owner": "material-source-research", "human_owner": "content-reviewer", "human_confirmation_required": True}


def validate_screen_recording_requirement(plan: dict[str, Any], minimum_ratio: float) -> list[str]:
    if minimum_ratio <= 0:
        return []
    requirement = plan.get("screen_recording_requirement") if isinstance(plan.get("screen_recording_requirement"), dict) else {}
    errors: list[str] = []
    if requirement.get("required") is not True:
        errors.append("screen_recording_requirement.required must be true when minimum ratio is positive")
    try:
        recorded_ratio = float(requirement.get("minimum_ratio", -1))
    except (TypeError, ValueError):
        recorded_ratio = -1
    if recorded_ratio != minimum_ratio:
        errors.append("screen_recording_requirement.minimum_ratio does not match locked route policy")
    beats = plan.get("beats") if isinstance(plan.get("beats"), list) else []
    if not any(
        str(item.get("route", "")) == "product-ui"
        and item.get("human_confirmation_required") is True
        and isinstance(item.get("recording_recommendation"), dict)
        and str(item["recording_recommendation"].get("primary_mode", "")) in DIRECT_OBSERVATION_RECORDING_MODES
        for item in beats
        if isinstance(item, dict)
    ):
        errors.append("screen-recording requirement needs a human-confirmed direct-observation beat (browser, terminal, local HTML, or task screen)")
    return errors


def recording_recommendation_errors(item: dict[str, Any], index: int) -> list[str]:
    """Validate the derived per-beat recording recommendation shape.

    The recommendation is a planning receipt, not proof that a user has
    already supplied media.  Shape validation is therefore strict while
    readiness remains governed by the audio/material gates.
    """
    recommendation = item.get("recording_recommendation")
    if not isinstance(recommendation, dict):
        return [f"material beat {index} missing recording_recommendation"]
    errors: list[str] = []
    prefix = f"material beat {index} recording_recommendation"
    for field in ("schema_version", "status", "primary_mode", "surface", "capture_method", "layout", "evidence_level", "source_ratio", "delivery_ratio", "audio_binding", "screenshot_binding"):
        if field not in recommendation:
            errors.append(f"{prefix} missing {field}")
    if recommendation.get("schema_version") != 1:
        errors.append(f"{prefix}.schema_version must be 1")
    if str(recommendation.get("primary_mode", "")) not in RECORDING_MODES:
        errors.append(f"{prefix}.primary_mode is invalid")
    if str(recommendation.get("status", "")) not in {"ready", "pending-audio-handoff"}:
        errors.append(f"{prefix}.status is invalid")
    for field in ("audio_binding", "screenshot_binding"):
        if not isinstance(recommendation.get(field), dict):
            errors.append(f"{prefix}.{field} must be an object")
    if not isinstance(recommendation.get("must_show"), list) or not recommendation.get("must_show"):
        errors.append(f"{prefix}.must_show must be a non-empty list")
    if recommendation.get("human_required") is True:
        try:
            if float(recommendation.get("minimum_seconds", 0)) <= 0:
                errors.append(f"{prefix}.minimum_seconds must be positive for human capture")
        except (TypeError, ValueError):
            errors.append(f"{prefix}.minimum_seconds must be numeric")
    return errors
