#!/usr/bin/env python3
"""Plan text-free ChatGPT Bridge images and scene-bound browser handoffs.

Planning never invokes a provider. The actual dispatch must verify the Codex
browser session and pageAssets capability; missing capabilities block instead
of silently selecting another provider.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from canonical_workflow import LEGACY_CONTRACT_ID, SUPPORTED_CONTRACT_IDS
except ImportError:  # imported as scripts.image_prompt_plan
    from scripts.canonical_workflow import LEGACY_CONTRACT_ID, SUPPORTED_CONTRACT_IDS

try:
    from console_encoding import configure_utf8_stdio
except ImportError:  # imported as scripts.image_prompt_plan
    from scripts.console_encoding import configure_utf8_stdio

configure_utf8_stdio()

try:
    from runtime_context import ACCOUNT, IDENTITY_ACCOUNTS, IDENTITY_ACCOUNT
    from xiaohei_ip import profile_metadata, prompt_instructions
    from branding import IP_NAME, WORKFLOW_NAME
    from image_policy_contract import (
        TEXT_FREE_POLICY,
        IMAGE_ENGINE,
        IMAGE_ROUTE,
        XIAOHEI_IMAGE_ROUTE,
        XIAOHEI_TEXT_POLICY,
    )
    from generation_guidance import metadata as generation_guidance_metadata
except ModuleNotFoundError:  # imported as scripts.image_prompt_plan
    from scripts.runtime_context import ACCOUNT, IDENTITY_ACCOUNTS, IDENTITY_ACCOUNT
    from scripts.xiaohei_ip import profile_metadata, prompt_instructions
    from scripts.branding import IP_NAME, WORKFLOW_NAME
    from scripts.image_policy_contract import (
        TEXT_FREE_POLICY,
        IMAGE_ENGINE,
        IMAGE_ROUTE,
        XIAOHEI_IMAGE_ROUTE,
        XIAOHEI_TEXT_POLICY,
    )
    from scripts.generation_guidance import metadata as generation_guidance_metadata


ENGINE = IMAGE_ENGINE
ROUTE = IMAGE_ROUTE
XIAOHEI_ROUTE = XIAOHEI_IMAGE_ROUTE
BRIDGE_XIAOHEI_ROUTE = "bridge-xiaohei"
XIAOHEI_RENDERERS = {"ian-xiaohei-illustrations", "ian-xiaohei-scenes"}
MIXED_TEXT_POLICY = "per-item; inspect each image item's text_policy"
BRIDGE_CONCEPT_ROUTE = "bridge-concept"
TEXT_POLICY = TEXT_FREE_POLICY
MARKERS = ("architecture", "架构", "diagram", "架构图", "illustration", "插图", "概念图", "generated-illustration", "generated-architecture")


def load(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SystemExit(f"invalid JSON: {path}: {error}") from error


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def package_path(project: Path, value: str, label: str) -> Path:
    """Resolve a manifest path while keeping every planner output package-local."""

    candidate = Path(str(value or ""))
    resolved = (candidate if candidate.is_absolute() else project / candidate).resolve()
    try:
        resolved.relative_to(project.resolve())
    except ValueError as error:
        raise SystemExit(f"{label} must stay inside the content package: {value}") from error
    return resolved


LEDGER_FIELDS = [
    "asset_id", "planned_time_in", "planned_time_out", "role", "filename_or_url",
    "source_type", "creator_or_owner", "license", "attribution_text", "fact_status",
    "generation_prompt", "edit_notes", "approved_by", "status", "prompt_sha256",
    "provenance_path", "provider", "provider_skill", "source_ratio", "delivery_ratio",
    "output_sha256", "text_policy", "text_required", "text_reviewed", "text_present",
    "text_free_reviewed", "english_text_reviewed", "english_text_present", "chinese_text_reviewed", "chinese_text_present", "placeholder_id", "placeholder_marker", "generation_route", "reference_policy", "ip_profile_id", "ip_profile_sha256",
    "ip_reference_env", "ip_reference_status", "ip_reference_sha256",
]


def sync_asset_ledger(project: Path, manifest: dict[str, Any], items: list[dict[str, Any]]) -> None:
    """Pre-register generated assets without bypassing human asset approval."""
    paths = manifest.get("paths", {}) if isinstance(manifest.get("paths"), dict) else {}
    # The canonical asset ledger is JSON and remains empty until real provider
    # receipts are reconciled. This planner only pre-registers prompt slots
    # in the compatibility CSV; writing CSV rows to asset-ledger.json would
    # corrupt the strict hand-off and falsely turn planning into execution.
    canonical_package = manifest.get("workflow_contract") in SUPPORTED_CONTRACT_IDS
    # Caller-selected/historical packages may carry the v2 workflow contract
    # for auditability while retaining their explicit legacy path map.  Honor
    # that declared CSV path instead of silently relocating rows into the
    # canonical 05_assets tree.
    declared_csv = paths.get("asset_ledger_csv") or paths.get("asset_ledger")
    ledger_path = package_path(
        project,
        str(declared_csv or ("05_assets/asset-ledger.csv" if canonical_package else "03_assets/asset-ledger.csv")),
        "asset ledger CSV",
    )
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    if ledger_path.is_file():
        with ledger_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    fieldnames = list(LEDGER_FIELDS)
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    by_id = {str(row.get("asset_id", "")): row for row in rows if str(row.get("asset_id", ""))}
    for item in items:
        asset_id = str(item.get("asset_id", "")).strip()
        if not asset_id:
            continue
        row = by_id.setdefault(asset_id, {key: "" for key in fieldnames})
        row.setdefault("status", "")
        prompt_sha256 = str(item.get("prompt_sha256", ""))
        if row.get("prompt_sha256") and row.get("prompt_sha256") != prompt_sha256:
            # A changed prompt invalidates prior human approval and output.
            row["status"] = "requested"
            row["approved_by"] = ""
            row["output_sha256"] = ""
        provider_route = str(item.get("generation_provider") or ROUTE)
        route_renderer = str(item.get("route_renderer") or "").strip()
        xiaohei_item = route_renderer in XIAOHEI_RENDERERS
        provider_label = "ChatGPT Bridge"
        attribution = (
            "Ian Xiaohei Illustrations by Ian; AI-generated illustrative asset; not factual evidence"
            if route_renderer in XIAOHEI_RENDERERS
            else "AI-generated illustrative asset; not factual evidence"
        )
        row.update({
            "asset_id": asset_id,
            "role": row.get("role") or "illustration",
            "filename_or_url": str(item.get("output", "")),
            "source_type": "generated",
            # This is generated-asset provenance, not a user-editable display
            # caption.  Always rewrite it from the current route so a policy
            # migration cannot leave an old provider attribution behind.
            "creator_or_owner": f"{provider_label} via {item.get('route_renderer', '')}",
            "license": row.get("license") or "internal-policy:local-media-policy.json#generated_asset_rights",
            "attribution_text": row.get("attribution_text") or attribution,
            "fact_status": "illustrative",
            "edit_notes": (
                f"{item.get('source_ratio') or item.get('ratio') or '9:16'} source; Remotion/HTML delivery at 9:16; "
                + "text-free generated image; all text added in postproduction"
            ),
            "status": row.get("status") or "requested",
            "provenance_path": str(item.get("provenance", "")),
            "prompt_sha256": prompt_sha256,
            "provider": str(item.get("generation_provider", "")),
            "provider_skill": str(item.get("skill_path", "")),
            "source_ratio": str(item.get("source_ratio") or item.get("ratio") or "9:16"),
            "delivery_ratio": str(item.get("delivery_ratio", "9:16")),
            "text_policy": str(item.get("text_policy", TEXT_POLICY)),
            "text_required": "true" if item.get("text_required") is True else "false",
            "text_reviewed": "true" if item.get("text_reviewed") is True else "false",
            "text_present": "true" if item.get("text_present") is True else "false",
            "text_free_reviewed": "true" if item.get("text_free_reviewed") is True else "false",
            "english_text_reviewed": "true" if item.get("english_text_reviewed") is True else "false",
            "english_text_present": "true" if item.get("english_text_present") is True else "false",
            "chinese_text_reviewed": "true" if item.get("chinese_text_reviewed") is True else "false",
            "chinese_text_present": "true" if item.get("chinese_text_present") is True else "false",
            "placeholder_id": str(item.get("placeholder_id", "")),
            "placeholder_marker": str(item.get("placeholder_marker", "")),
            "generation_route": str(item.get("generation_route", "")),
            "reference_policy": "remote-upload-and-text-review-required" if item.get("reference_assets") else "no-reference-assets",
            "ip_profile_id": str(item.get("ip_profile_id", "")),
            "ip_profile_sha256": str(item.get("ip_profile_sha256", "")),
            "ip_reference_env": str(item.get("ip_reference_env", "")),
            "ip_reference_status": str(item.get("ip_reference_status", "")),
            "ip_reference_sha256": str(item.get("ip_reference_sha256", "")),
        })
    rows = list(by_id.values())
    with ledger_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sync_image_provenance(project: Path, manifest: dict[str, Any], items: list[dict[str, Any]]) -> None:
    """Create a truthful pending provenance receipt before any image exists.

    A prompt-only handoff is still an auditable workflow state.  It must not
    leave the aggregate report at ``not_required`` (or claim success), and a
    later planner refresh must preserve a hash-matching successful execution.
    """
    paths = manifest.get("paths", {}) if isinstance(manifest.get("paths"), dict) else {}
    report_path = package_path(
        project,
        str(paths.get("image_generation_provenance", "05_publish/image-generation-provenance.json")),
        "image generation provenance",
    )
    previous = load(report_path, {})
    previous_records = {
        str(record.get("asset_id")): record
        for record in previous.get("records", [])
        if isinstance(record, dict) and str(record.get("asset_id", ""))
    } if isinstance(previous, dict) else {}
    records: list[dict[str, Any]] = []
    for item in items:
        asset_id = str(item.get("asset_id", ""))
        output_value = str(item.get("output", ""))
        output_path = project / output_value if output_value and not Path(output_value).is_absolute() else Path(output_value)
        old = previous_records.get(asset_id, {})
        old_hash = str(old.get("output_sha256", ""))
        prompt_hash = str(item.get("prompt_sha256", ""))
        if (
            old.get("status") == "success"
            and str(old.get("prompt_sha256", "")) == prompt_hash
            and output_path.is_file()
            and old_hash
            and digest(output_path) == old_hash
        ):
            records.append(old)
            continue
        xiaohei = str(item.get("route_renderer", "")) in XIAOHEI_RENDERERS
        requested_provider = XIAOHEI_ROUTE if xiaohei else ROUTE
        records.append({
            "schema_version": 1,
            "asset_id": asset_id,
            "content_id": manifest.get("content_id", ""),
            "account": manifest.get("account", ""),
            "route": requested_provider,
            "provider_route": requested_provider,
            "requested_provider_route": requested_provider,
            "generation_provider": requested_provider,
            "engine": ENGINE,
            "generation_route": str(item.get("generation_route", "")),
            "visual_route_id": str(item.get("visual_route", "")),
            "visual_route_renderer": str(item.get("route_renderer", "")),
            "skill_route": str(item.get("skill_route", "")),
            "skill_path": str(item.get("skill_path", "")),
            "skill_sha256": str(item.get("skill_sha256", "")),
            "prompt_sha256": prompt_hash,
            "source_ratio": str(item.get("source_ratio") or item.get("ratio") or ""),
            "delivery_ratio": str(item.get("delivery_ratio", "9:16")),
            "text_policy": str(item.get("text_policy", "")),
            "text_required": item.get("text_required") is True,
            "text_reviewed": item.get("text_reviewed") is True,
            "text_present": item.get("text_present") is True,
            "english_text_reviewed": item.get("english_text_reviewed") is True,
            "english_text_present": item.get("english_text_present") is True,
            "chinese_text_reviewed": item.get("chinese_text_reviewed") is True,
            "chinese_text_present": item.get("chinese_text_present") is True,
            "placeholder_id": str(item.get("placeholder_id", "")),
            "placeholder_marker": str(item.get("placeholder_marker", "")),
            "placeholder_asset_slot": str(item.get("placeholder_asset_slot", "")),
            "input_origin": "prompt-only",
            "response_mode": "prompt-only",
            "provider_preflight": item.get("provider_preflight", {}),
            "blocked_by": list(item.get("provider_preflight", {}).get("missing", [])) if isinstance(item.get("provider_preflight"), dict) else [],
            "human_decision_required": str(item.get("status")) == "blocked-awaiting-human-decision",
            "status": (
                "blocked"
                if str(item.get("status")) == "blocked-awaiting-human-decision"
                else "prompt-only" if str(item.get("status")) == "prompt-only" else "planned"
            ),
            "passed": False,
        })
    statuses = [str(record.get("status", "")) for record in records]
    if records and all(status == "success" for status in statuses):
        status, passed = "ready", True
    elif any(status in {"failed", "dry-run", "blocked"} for status in statuses):
        status, passed = "blocked", False
    elif any(status == "prompt-only" for status in statuses):
        status, passed = "prompt-only", False
    else:
        status, passed = "planned", False
    routes = sorted({str(record.get("provider_route", "")) for record in records if str(record.get("provider_route", ""))})
    report = {
        "schema_version": 1,
        "contract": manifest.get("workflow_contract", ""),
        "content_id": manifest.get("content_id", ""),
        "account": manifest.get("account", ""),
        "status": status,
        "passed": passed,
        "engine": routes[0] if len(routes) == 1 and routes else ("multi-provider" if routes else ""),
        "routes": routes,
        "requested_routes": routes,
        "records": records,
        "errors": [],
        "warnings": ["image generation is planned but not yet executed"] if not passed else [],
    }
    write(report_path, report)


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def skill_metadata(renderer: str) -> dict[str, Any]:
    """Return the installed Skill binding used by a first-class route."""
    if renderer not in XIAOHEI_RENDERERS:
        return {"skill_route": "", "skill_path": "", "skill_sha256": "", "skill_reference_paths": []}
    skill_path = Path(__file__).resolve().parents[1] / "skills" / renderer / "SKILL.md"
    if not skill_path.is_file():
        raise SystemExit(f"installed X•超玩 skill is missing: {skill_path}")
    reference_names = (
        (
            "style-dna.md",
            "xiaohei-ip.md",
            "story-extraction.md",
            "object-patterns.md",
            "master-selection.md",
            "prompt-template.md",
            "qa-checklist.md",
        )
        if renderer == "ian-xiaohei-scenes"
        else ("style-dna.md", "qa-checklist.md")
    )
    refs = [skill_path.parent / "references" / name for name in reference_names]
    missing = [str(path) for path in refs if not path.is_file()]
    if missing:
        raise SystemExit(f"installed X•超玩 skill references are missing: {', '.join(missing)}")
    return {
        "skill_route": renderer,
        "skill_path": str(skill_path),
        "skill_sha256": digest(skill_path),
        "skill_reference_paths": [str(path) for path in refs],
        "skill_reference_sha256": {str(path): digest(path) for path in refs},
    }


def scene_text(scene: dict[str, Any], row: dict[str, str]) -> str:
    values = [scene.get(key, "") for key in ("asset_type", "visual_owner", "viewer_job", "source_strategy", "rights_plan", "visual_theme")]
    values.extend(row.get(key, "") for key in ("visual", "shot", "visual_treatment", "source_or_prompt", "subtitle", "overlay_text"))
    return " ".join(str(value) for value in values).lower()


def requested(scene: dict[str, Any], row: dict[str, str]) -> bool:
    asset_type = str(scene.get("asset_type", "")).lower()
    owner = str(scene.get("visual_owner", "")).lower()
    return asset_type.startswith("generated") or "image-generation" in owner or "illustration" in owner or any(marker in scene_text(scene, row) for marker in MARKERS)


def prompt_for(
    account: str,
    title: str,
    scene: dict[str, Any],
    row: dict[str, str],
    architecture: bool,
    renderer: str = "",
) -> str:
    subject = str(scene.get("viewer_job") or row.get("visual") or title).strip()
    environment = str(scene.get("source_strategy") or row.get("shot") or "clean explanatory studio environment").strip()
    style = str(scene.get("visual_theme") or ("precise technical editorial illustration" if architecture else "high-end editorial concept illustration")).strip()
    xiaohei = renderer in XIAOHEI_RENDERERS
    parts = [
        "Use case: scientific-educational" if architecture else "Use case: illustration-story",
        "Asset type: short-video scene illustration",
        f"Primary request: {subject}",
        f"Scene/backdrop: {environment}",
        f"Subject: {subject}",
        f"Style/medium: {style}",
        "Composition/framing: Native portrait 9:16; reserve mobile-safe whitespace for postproduction overlays",
        'Text (verbatim): ""',
        "Constraints: one cognitive anchor; one core action; illustration, not factual evidence",
        "Avoid: text, letters, labels, numbers, logos, watermarks, UI, code, formulas",
        "Generate no text, letters, labels, numbers, logos, watermarks, UI, code or formulas",
    ]
    if xiaohei:
        parts += [
            f"First-class Skill: {renderer} (visual style only; workflow no-text policy takes precedence).",
            f"Preserve {IP_NAME}: black hand-drawn figure, white dot eyes, pure white background, restrained accent color.",
            "Use the approved character reference; preserve proportions and object identity.",
            "One real object or compact object group and one physical action with generous whitespace.",
        ]
    return "; ".join(parts)


def placeholder_for(scene_id: str, asset_id: str) -> tuple[str, str]:
    """Return a stable scene/asset-bound insertion token for external image handoff."""
    safe_scene = "".join(char if char.isalnum() or char in "-_" else "-" for char in scene_id).strip("-") or "scene"
    safe_asset = "".join(char if char.isalnum() or char in "-_" else "-" for char in asset_id).strip("-") or "asset"
    placeholder_id = f"IMAGE__{safe_scene}__{safe_asset}"
    return placeholder_id, f"[[IMAGE:{placeholder_id}]]"


def main(args: argparse.Namespace) -> int:
    if getattr(args, "command", "plan") == "approve":
        return command_approve(args)
    project = Path(args.project).expanduser().resolve()
    manifest = load(project / "content.json", {})
    if not manifest:
        raise SystemExit(f"missing content.json: {project}")
    paths = manifest.get("paths", {}) if isinstance(manifest.get("paths"), dict) else {}
    plan_path = package_path(project, str(paths.get("director_plan", "04_video/director-material-plan.json")), "director material plan")
    storyboard_path = package_path(project, str(paths.get("storyboard", "04_video/storyboard.csv")), "storyboard")
    visual_route_path = package_path(project, str(paths.get("visual_route", "04_video/visual-route.json")), "visual route")
    output = package_path(project, str(paths.get("image_prompt_plan", "03_assets/image-prompt-plan.json")), "image prompt plan")
    previous_plan = load(output, {})
    previous_items = {
        str(entry.get("asset_id")): entry
        for entry in previous_plan.get("items", [])
        if isinstance(entry, dict) and str(entry.get("asset_id", ""))
    } if isinstance(previous_plan, dict) else {}
    execution_path = package_path(project, str(paths.get("execution_plan", "00_brief/execution-plan.json")), "execution plan")
    profile_path = Path(__file__).resolve().parents[1] / "profiles" / "profile.json"
    profile = load(profile_path, {})
    profile_video = profile.get("video", {}) if isinstance(profile, dict) else {}
    image_policy = profile_video.get("image_policy", {}) if isinstance(profile_video, dict) else {}
    ip_metadata = profile_metadata()
    image_policy_enabled = isinstance(image_policy, dict) and image_policy.get("enabled") is True
    visual_route = load(visual_route_path, {}) if visual_route_path.is_file() else {}
    canonical_package = manifest.get("workflow_contract") in SUPPORTED_CONTRACT_IDS
    generated_media_root = str(paths.get("generated_media", "05_assets/generated" if canonical_package else "03_assets/generated"))
    # Keep generated-image slots inside the manifest-owned package.  The old
    # planner defaulted to 03_assets even for canonical packages, which made a
    # real Bridge export invisible to the strict ledger.
    generated_media_root = generated_media_root.replace("\\", "/").strip("/")
    selected_xiaohei = {
        str(item.get("renderer"))
        for item in visual_route.get("routes", [])
        if isinstance(item, dict) and str(item.get("renderer")) in XIAOHEI_RENDERERS
    }
    # Preserve the account-level fail-closed behavior for ordinary image
    # requests, but do not erase an explicitly selected first-class X•超玩
    # route.  It remains planned/blocked until policy and provider approval.
    if manifest.get("account") not in IDENTITY_ACCOUNTS or (not image_policy_enabled and not selected_xiaohei):
        report = {
            "schema_version": 1,
            "contract": manifest.get("workflow_contract", ""),
            "content_id": manifest.get("content_id", ""),
            "account": manifest.get("account", ""),
            "status": "not_required",
            "image_required": False,
            "engine": "",
            "routes": [],
            "items": [],
            "notes": "Image generation is reserved for accounts with image_policy enabled.",
        }
        write(output, report)
        print(json.dumps(report, ensure_ascii=True, indent=2))
        return 0

    director = load(plan_path, {})
    scenes = director.get("scenes", []) if isinstance(director, dict) else []
    if canonical_package and not scenes:
        # Canonical packages derive scene slots from the JSON Visual Plan; the
        # legacy director-material-plan tree is not a source of truth.
        scenes = [
            {
                "scene_id": str(item.get("scene_id")),
                "viewer_job": str(item.get("label") or item.get("route_id") or "Make the visual point clear"),
                "visual_owner": "generated" if item.get("requires_generation") is True else str(item.get("renderer") or ""),
                "asset_type": "generated_image" if item.get("requires_generation") is True else "",
                "claim_ids": item.get("claim_ids", []) if isinstance(item.get("claim_ids"), list) else [],
            }
            for item in (visual_route.get("routes", []) if isinstance(visual_route, dict) else [])
            if isinstance(item, dict) and str(item.get("scene_id") or "").strip()
        ]
    if visual_route.get("status") not in {"ready", "ready_for_review", "approved", "blocked"} and not args.force_required:
        raise SystemExit("visual route is not ready; run scripts/visual_route.py after the approved script before planning images")
    route_by_scene = {
        str(item.get("scene_id")): item
        for item in visual_route.get("routes", [])
        if isinstance(item, dict) and item.get("scene_id")
    }
    rows: dict[str, dict[str, str]] = {}
    if storyboard_path.is_file():
        with storyboard_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = {str(row.get("scene_id", "")): row for row in csv.DictReader(handle)}
    mode = args.mode
    candidates: list[tuple[dict[str, Any], dict[str, str]]] = []
    for scene in scenes if isinstance(scenes, list) else []:
        if not isinstance(scene, dict):
            continue
        row = rows.get(str(scene.get("scene_id", "")), {})
        route = route_by_scene.get(str(scene.get("scene_id", "")), {})
        # Once visual_route.py has produced a ready plan, it is authoritative:
        # architecture, formula, UI and evidence scenes must never be sent to
        # a raster image model merely because their text contains “diagram”.
        if visual_route.get("status") in {"ready", "ready_for_review", "approved"} and route:
            route_requests_generation = route.get("requires_generation") is True
            # `--mode required` cannot override a semantic hard ban.  It only
            # changes the decision when no authoritative route exists.
            should_add = mode != "none" and route_requests_generation
        else:
            should_add = mode != "none" and (mode == "required" or requested(scene, row))
        if should_add:
            candidates.append((scene, row))
    if args.force_required and not candidates:
        candidates.append(({"scene_id": "hero", "viewer_job": manifest.get("title", "AI 原理解释"), "asset_type": "generated-illustration", "visual_owner": "ian-xiaohei-illustrations"}, {}))

    policy = {"default_size": "2K", "vertical_ratio": "9:16", "architecture_ratio": "9:16", "text_policy": TEXT_POLICY}
    policy.update(image_policy if isinstance(image_policy, dict) else {})
    guidance_info = generation_guidance_metadata("chatgpt-bridge-image-v1")
    items: list[dict[str, Any]] = []
    for index, (scene, row) in enumerate(candidates, 1):
        scene_id = str(scene.get("scene_id") or f"scene-{index:02d}")
        text = scene_text(scene, row)
        route = route_by_scene.get(scene_id, {})
        architecture = any(marker in text for marker in ("architecture", "架构", "diagram", "架构图"))
        explicit_renderer = str(scene.get("visual_owner", "")).strip()
        renderer = str(route.get("renderer") or (explicit_renderer if explicit_renderer in XIAOHEI_RENDERERS else ROUTE))
        skill_info = skill_metadata(renderer)
        asset_prefix = "xczw" if renderer in XIAOHEI_RENDERERS else "bridge"
        asset_id = str(scene.get("asset_id") or f"{asset_prefix}-{scene_id}")
        references = scene.get("reference_assets", []) if isinstance(scene.get("reference_assets"), list) else []
        generation_mode = "multi-image" if len(references) > 1 else "image-to-image" if references else "text-to-image"
        purpose = "cover-background" if route.get("route_id") in {"cover_background", "cover"} else "explanatory-illustration"
        prompt_text = prompt_for(str(manifest.get("account", IDENTITY_ACCOUNT)), str(manifest.get("title", "")), scene, row, architecture, renderer)
        prompt_sha256 = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()
        previous = previous_items.get(asset_id, {})
        same_prompt = str(previous.get("prompt_sha256", "")) == prompt_sha256
        xiaohei_route = renderer in XIAOHEI_RENDERERS
        generation_provider = str(route.get("generation_provider") or (XIAOHEI_ROUTE if xiaohei_route else ROUTE))
        generation_route = BRIDGE_XIAOHEI_ROUTE if xiaohei_route else BRIDGE_CONCEPT_ROUTE
        placeholder_id, placeholder_marker = placeholder_for(scene_id, asset_id)
        item_ip_metadata = {key: value for key, value in ip_metadata.items() if key != "ip_profile_path"}
        if renderer not in XIAOHEI_RENDERERS:
            item_ip_metadata = {
                "ip_profile_id": "",
                "ip_profile_sha256": "",
                "ip_reference_env": "",
                "ip_reference_status": "",
                "ip_reference_sha256": "",
            }
        items.append({
            "asset_id": asset_id,
            "scene_id": scene_id,
            "purpose": purpose,
            "mode": generation_mode,
            "prompt": prompt_text,
            "prompt_sha256": prompt_sha256,
            "size": str(policy.get("default_size", "2K")),
            "ratio": str(route.get("aspect_ratio") or policy.get("architecture_ratio" if architecture else "vertical_ratio", "9:16")),
            "source_ratio": str(route.get("aspect_ratio") or policy.get("architecture_ratio" if architecture else "vertical_ratio", "9:16")),
            "delivery_ratio": str(route.get("delivery_aspect_ratio") or "9:16"),
            "reframe": {
                "mode": "cover",
                "focal_point": [0.5, 0.5],
                "safe_area": "center-column",
            },
            "reference_assets": [str(item) for item in references],
            "reference_remote_upload_approved": scene.get("reference_remote_upload_approved") is True or (same_prompt and previous.get("reference_remote_upload_approved") is True),
            "reference_text_reviewed": scene.get("reference_text_reviewed") is True or (same_prompt and previous.get("reference_text_reviewed") is True),
            "reference_text_free_reviewed": scene.get("reference_text_free_reviewed") is True or (same_prompt and previous.get("reference_text_free_reviewed") is True),
            "text_required": False,
            "text_reviewed": scene.get("text_reviewed") is True or (same_prompt and previous.get("text_reviewed") is True),
            "text_present": scene.get("text_present") is True or (same_prompt and previous.get("text_present") is True),
            "text_free_reviewed": scene.get("text_free_reviewed") is True or (same_prompt and previous.get("text_free_reviewed") is True),
            "english_text_reviewed": scene.get("english_text_reviewed") is True or (same_prompt and previous.get("english_text_reviewed") is True),
            "english_text_present": scene.get("english_text_present") is True or (same_prompt and previous.get("english_text_present") is True),
            "chinese_text_reviewed": scene.get("chinese_text_reviewed") is True or (same_prompt and previous.get("chinese_text_reviewed") is True),
            "chinese_text_present": scene.get("chinese_text_present") is True or (same_prompt and previous.get("chinese_text_present") is True),
            "placeholder_id": placeholder_id,
            "placeholder_marker": placeholder_marker,
            "placeholder_insert_after_scene": scene_id,
            "placeholder_asset_slot": f"{generated_media_root}/{asset_id}.png",
            "execution_mode": "codex-browser-plugin",
            "output": f"{generated_media_root}/{asset_id}.png",
            "provenance": f"{generated_media_root}/{asset_id}.json",
            "status": (
                "blocked-awaiting-human-decision"
                if str(route.get("status", "")) == "blocked"
                else "planned"
            ),
            "text_policy": str(route.get("text_policy") or (XIAOHEI_TEXT_POLICY if xiaohei_route else TEXT_FREE_POLICY)),
            "visual_route": route.get("route_id", "concept_illustration"),
            "route_renderer": renderer,
            "generation_provider": generation_provider,
            "generation_route": generation_route,
            "provider_preflight": route.get("provider_preflight", {}),
            "blocked_by": list(route.get("blocked_by", [])),
            "guidance": guidance_info,
            **skill_info,
            "route_decision_trace": route.get("decision_trace", []),
            **item_ip_metadata,
        })
    required = bool(candidates)
    allowed_routes = {str(item).strip() for item in image_policy.get("allowed_routes", []) if str(item).strip()} if isinstance(image_policy, dict) else set()
    if isinstance(image_policy, dict):
        allowed_routes.update(str(item).strip() for item in image_policy.get("english_text_routes", []) if str(item).strip())
        allowed_routes.update(str(item).strip() for item in image_policy.get("no_text_routes", []) if str(item).strip())
    allowed_providers = {str(item).strip() for item in image_policy.get("allowed_providers", []) if str(item).strip()} if isinstance(image_policy, dict) else set()
    if not allowed_providers and isinstance(image_policy, dict) and str(image_policy.get("provider_route", "")).strip():
        allowed_providers.add(str(image_policy.get("provider_route")).strip())
    route_policy_ok = all(
        str(item.get("route_renderer", "")) in allowed_routes
        and str(item.get("generation_provider", "")) in allowed_providers
        for item in items
    ) if items else True
    references_blocked = any(
        bool(item.get("reference_assets"))
        and (item.get("reference_remote_upload_approved") is not True or not (item.get("reference_text_reviewed") is True or item.get("reference_text_free_reviewed") is True))
        for item in items
    )
    runtime_blocked = required and any(
        str(item.get("status", "")) == "blocked-awaiting-human-decision" for item in items
    )
    policy_blocked = required and (not image_policy_enabled or not allowed_routes or not allowed_providers or not route_policy_ok or references_blocked)
    blocked_by = sorted({
        str(reason)
        for item in items
        for reason in (
            (item.get("provider_preflight", {}) or {}).get("missing", [])
            if isinstance(item.get("provider_preflight"), dict) and item.get("provider_preflight", {}).get("missing")
            else item.get("blocked_by", [])
        )
        if str(reason).strip()
    })
    selected_skills = sorted({str(item.get("skill_route")) for item in items if str(item.get("skill_route"))})
    report = {
        "schema_version": 1,
        "contract": manifest.get("workflow_contract", ""),
        "content_id": manifest.get("content_id", ""),
        "account": manifest.get("account", ""),
        "provider": "chatgpt-bridge" if required else "",
        "status": "blocked" if policy_blocked or runtime_blocked else ("planned" if required else "not_required"),
        "image_required": required,
        "engine": "multi-provider" if len({str(item.get("generation_provider")) for item in items}) > 1 else (str(items[0].get("generation_provider")) if items else ""),
        "routes": sorted({str(item.get("generation_provider") or ROUTE) for item in items}) if required else [],
        "generation_routes": sorted({str(item.get("generation_route")) for item in items if str(item.get("generation_route"))}),
        "prompt_only_items": [str(item.get("asset_id")) for item in items if item.get("status") == "prompt-only"],
        "placeholder_markers": [{"asset_id": str(item.get("asset_id")), "scene_id": str(item.get("scene_id")), "marker": str(item.get("placeholder_marker")), "slot": str(item.get("placeholder_asset_slot"))} for item in items],
        "skill_routes": selected_skills,
        "generation_guidance": guidance_info,
        "items": items,
        "generated_at": now(),
        "text_policy": (
            items[0].get("text_policy", TEXT_POLICY)
            if len({str(item.get("text_policy", TEXT_POLICY)) for item in items}) == 1 and items
            else MIXED_TEXT_POLICY
        ),
        "policy_blocked": policy_blocked,
        "runtime_blocked": runtime_blocked,
        "blocked_by": blocked_by,
        "human_decision_required": bool(runtime_blocked),
        "xiaohei_ip": {key: value for key, value in ip_metadata.items() if key != "ip_profile_path"},
    }
    write(output, report)
    sync_asset_ledger(project, manifest, items)
    sync_image_provenance(project, manifest, items)
    execution = load(execution_path, {})
    if required:
        execution["image_mode"] = "required"
        execution["image_routes"] = sorted({str(item.get("generation_provider") or ROUTE) for item in items} | set(selected_skills))
        execution["image_generation"] = {"required": True, "status": "blocked" if report["status"] == "blocked" else ("prompt-only" if report["prompt_only_items"] else "planned"), "engine": report["engine"], "skills": selected_skills, "prompt_plan": str(output.relative_to(project)).replace("\\", "/"), "generation_routes": report["generation_routes"], "placeholder_markers": report["placeholder_markers"], "blocked_by": report["blocked_by"], "human_decision_required": report["human_decision_required"]}
    else:
        execution["image_mode"] = "auto"
        execution["image_routes"] = []
        execution["image_generation"] = {"required": False, "status": "not_required", "engine": ""}
    if execution_path.is_file() or required:
        write(execution_path, execution)
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 2 if report["status"] == "blocked" else 0


def validate_prompt_plan(project: Path, plan: dict[str, Any]) -> list[str]:
    """Validate the human-reviewable Bridge prompt hand-off.

    Approval records a review decision only; it never calls ChatGPT Bridge or
    creates an image.  Keeping this check here makes the approval command
    useful in both the CLI and the canonical Assets gate.
    """

    errors: list[str] = []
    manifest = load(project / "content.json", {}) or {}
    if not isinstance(plan, dict):
        return ["image prompt plan must be an object"]
    if plan.get("schema_version") != 1:
        errors.append("image prompt plan schema_version must equal 1")
    if plan.get("content_id") != manifest.get("content_id"):
        errors.append("image prompt plan content_id does not match content package")
    if plan.get("provider") != "chatgpt-bridge":
        errors.append("image prompt plan provider must be chatgpt-bridge")
    if plan.get("text_policy") != "generated-scene-text-free; all Chinese labels belong to Remotion/HTML":
        errors.append("image prompt plan must keep generated imagery text-free")
    items = plan.get("items")
    if not isinstance(items, list) or not items:
        errors.append("image prompt plan requires at least one item")
        return errors
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            errors.append(f"image prompt item {index} must be an object")
            continue
        asset_id = str(item.get("asset_id") or "").strip()
        prompt = str(item.get("prompt") or "")
        prompt_sha = str(item.get("prompt_sha256") or "").strip().lower()
        if not asset_id:
            errors.append(f"image prompt item {index} requires asset_id")
        if not prompt.strip():
            errors.append(f"image prompt item {index} requires prompt")
        if hashlib.sha256(prompt.encode("utf-8")).hexdigest() != prompt_sha:
            errors.append(f"image prompt item {index} prompt_sha256 does not match prompt")
        if item.get("generation_provider") != "chatgpt-bridge":
            errors.append(f"image prompt item {index} generation_provider must be chatgpt-bridge")
        if item.get("status") in {"blocked-awaiting-human-decision", "blocked", "failed"}:
            errors.append(f"image prompt item {index} is blocked and cannot be approved")
        for field in ("output", "provenance"):
            value = str(item.get(field) or "").strip()
            if not value or Path(value).is_absolute() or ".." in Path(value).parts:
                errors.append(f"image prompt item {index} {field} must be a package-relative path")
    return errors


def command_approve(args: argparse.Namespace) -> int:
    if not getattr(args, "confirm", False):
        raise SystemExit("image prompt approval is a human action; pass --confirm after reviewing the prompts")
    reviewer = str(getattr(args, "reviewer", "") or "").strip()
    if not reviewer:
        raise SystemExit("--reviewer is required")
    project = Path(args.project).expanduser().resolve()
    manifest = load(project / "content.json", {}) or {}
    paths = manifest.get("paths", {}) if isinstance(manifest.get("paths"), dict) else {}
    declared = str(getattr(args, "plan", "") or paths.get("image_prompt_plan", "05_assets/image-prompt-plan.json"))
    plan_path = Path(declared)
    if not plan_path.is_absolute():
        plan_path = project / plan_path
    plan = load(plan_path, {}) or {}
    if plan.get("status") == "approved":
        approval = plan.get("approval") if isinstance(plan.get("approval"), dict) else {}
        print(json.dumps({"project": str(project), "plan": str(plan_path), "approved": True, "idempotent": True, "reviewer": approval.get("reviewer", reviewer)}, ensure_ascii=False, indent=2))
        return 0
    errors = validate_prompt_plan(project, plan)
    if errors:
        raise SystemExit("image prompt plan is not approvable: " + "; ".join(errors))
    if plan.get("status") not in {"planned", "ready"}:
        raise SystemExit("image prompt plan must have status=planned or ready before approval")
    plan["status"] = "approved"
    plan["approval"] = {
        "status": "approved",
        "decision": "approved",
        "reviewer": reviewer,
        "approved_at": now(),
        "note": str(getattr(args, "note", "") or "").strip(),
    }
    write(plan_path, plan)
    print(json.dumps({"project": str(project), "plan": str(plan_path), "approved": True, "reviewer": reviewer}, ensure_ascii=False, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=f"Plan explicitly enabled {WORKFLOW_NAME} image/illustration scenes.")
    root.add_argument("command", nargs="?", choices=["plan", "approve"], default="plan")
    root.add_argument("--project", required=True)
    root.add_argument("--mode", choices=["auto", "required", "none"], default="auto")
    root.add_argument("--force-required", action="store_true", help="Create a hero illustration request when the director plan has no image scene.")
    root.add_argument("--plan", default="", help="Image prompt plan path for approval (defaults to the manifest path).")
    root.add_argument("--confirm", action="store_true", help="Confirm that a human reviewed the prompts.")
    root.add_argument("--reviewer", default="")
    root.add_argument("--note", default="")
    root.set_defaults(handler=main)
    return root


if __name__ == "__main__":
    arguments = parser().parse_args()
    raise SystemExit(arguments.handler(arguments))
