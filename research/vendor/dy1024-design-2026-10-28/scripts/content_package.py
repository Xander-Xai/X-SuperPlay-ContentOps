#!/usr/bin/env python3
"""Create and validate a Douyin-only X•超玩1024 content package."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from account_router import build_plan
try:
    from copy_strategy import build_seed, hotspot_eligible
except ImportError:  # imported as scripts.content_package
    from scripts.copy_strategy import build_seed, hotspot_eligible
try:
    from adaptive_copy_router import plan as adaptive_copy_plan
except ImportError:  # imported as scripts.content_package
    from scripts.adaptive_copy_router import plan as adaptive_copy_plan
try:
    from audience_insight import build_scaffold as build_audience_scaffold, lens_projection
except ImportError:  # imported as scripts.content_package
    from scripts.audience_insight import build_scaffold as build_audience_scaffold, lens_projection
try:
    from content_candidate import build_scaffold as build_content_candidate_scaffold
    from audience_relationship import build_scaffold as build_audience_relationship_scaffold
except ImportError:  # imported as scripts.content_package
    from scripts.content_candidate import build_scaffold as build_content_candidate_scaffold
    from scripts.audience_relationship import build_scaffold as build_audience_relationship_scaffold
try:
    from content_strategy import build_result as build_content_strategy
except ImportError:  # imported as scripts.content_package
    from scripts.content_strategy import build_result as build_content_strategy
from design_router import build_direction
from skill_provenance import required_routes
from workflow_gate import ensure_workflow, make_policy_lock, new_workflow, manifest_sha256, refresh_stale, save_manifest, invalidate_from
try:
    from canonical_workflow import CONTRACT_ID as CANONICAL_CONTRACT_ID, LEGACY_CONTRACT_ID as LEGACY_CANONICAL_CONTRACT_ID, SUPPORTED_CONTRACT_IDS as CANONICAL_CONTRACT_IDS, EXECUTION_CONTRACT_VERSION as CANONICAL_EXECUTION_VERSION, artifact_paths as canonical_artifact_paths, contract_from_environment as canonical_contract_from_environment, strict_artifact_keys as canonical_strict_artifact_keys, is_strict_execution as is_canonical_strict, new_execution_plan as canonical_execution_plan, new_workflow as canonical_new_workflow, policy_lock as canonical_policy_lock
except ImportError:  # imported as scripts.content_package
    from scripts.canonical_workflow import CONTRACT_ID as CANONICAL_CONTRACT_ID, LEGACY_CONTRACT_ID as LEGACY_CANONICAL_CONTRACT_ID, SUPPORTED_CONTRACT_IDS as CANONICAL_CONTRACT_IDS, EXECUTION_CONTRACT_VERSION as CANONICAL_EXECUTION_VERSION, artifact_paths as canonical_artifact_paths, contract_from_environment as canonical_contract_from_environment, strict_artifact_keys as canonical_strict_artifact_keys, is_strict_execution as is_canonical_strict, new_execution_plan as canonical_execution_plan, new_workflow as canonical_new_workflow, policy_lock as canonical_policy_lock
from digital_asset_inventory import ASSET_ROOT_ENV, required_asset_kinds, scan
from runtime_context import ACCOUNT, require_account
from voice_clone_policy import POLICY_VERSION, PROFILE_ID, REFERENCE_ID, SPEAKER_SIMILARITY_MIN, T0_GENERATION, voice_reference_required
try:
    from production_naming import DEFAULT_ARTIFACT_ROOT, POLICY_ID as PRODUCTION_NAMING_POLICY_ID, validate_project_layout
except ImportError:  # imported as scripts.content_package
    from scripts.production_naming import DEFAULT_ARTIFACT_ROOT, POLICY_ID as PRODUCTION_NAMING_POLICY_ID, validate_project_layout


ROOT = Path(__file__).resolve().parents[1]


def runtime_layout_roots() -> tuple[str, str]:
    """Read workspace/runtime roots from the canonical runtime layout."""
    layout_path = ROOT / "configs" / "runtime-layout.json"
    try:
        layout = json.loads(layout_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"runtime layout config is unavailable: {layout_path}") from error
    workspace_root = str(layout.get("workspace_root") or "").strip()
    runtime_root = str(layout.get("runtime_root") or "").strip()
    if not workspace_root or not runtime_root:
        raise ValueError("runtime layout must declare workspace_root and runtime_root")
    runtime_root = runtime_root.replace("${workspace_root}", workspace_root)
    return workspace_root, runtime_root


VOICE_PROVIDER = "index-tts-2.5"
TTS_MODEL = "IndexTTS2.5"
# Route-selection contract shared with workflow_start.py and workflow_gate.py:
# a production route must come from a user-confirmed decision, and the window
# it stays valid must cover the human steps the route itself authorizes
# (install, reproduce, screen-record, review).  Keep these three in sync.
APPROVED_SELECTION_SOURCES = {"user-interaction", "user-attested"}
ROUTE_VALIDITY_HOURS = 72


def canonical_identity(value: dict[str, Any]) -> str:
    """Hash a production profile without including its derived identity."""
    stable = dict(value)
    stable.pop("identity", None)
    encoded = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


PACKAGE_DIRS = (
    "00_brief",
    "01_research",
    "01_research/snapshots",
    "01_research/snapshots/screenshots",
    "03_assets/original",
    "03_assets/licensed",
    "03_assets/generated",
    "03_assets/broll/inbox",
    "03_assets/broll/raw",
    "03_assets/broll/selected",
    "03_assets/broll/proxies",
    "03_assets/broll/qc",
    "04_video",
    "04_video/analysis",
    "06_motion/hyperframes-native",
    "06_motion/remotion-native/src",
    "05_publish",
    "06_metrics",
    "02_script",
    "03_audio",
    "04_visual",
    "05_assets",
    "06_edit",
    "07_quality",
    "08_delivery",
    "09_feedback",
)

# Production packages are created directly from the canonical contract. The
# historical scaffold above is retained only for explicit caller-selected
# compatibility fixtures; it is never created for a normal production package.
CANONICAL_PACKAGE_DIRS = (
    "00_brief",
    "01_research",
    "02_script",
    "03_audio",
    "04_visual",
    "05_assets",
    "06_edit",
    "07_quality",
    "08_delivery",
    "09_feedback",
)

PATHS = {
    "workflow_route": "00_brief/workflow-route.json",
    "brief": "00_brief/brief.md",
    "topic_backlog": "00_brief/topic-backlog.json",
    "topic_contract": "00_brief/topic-contract.json",
    "human_operation_forecast": "00_brief/human-operation-forecast.json",
    "human_operation_guide": "00_brief/human-operation-guide.md",
    "sources_input": "01_research/sources-input.json",
    "sources": "01_research/sources.json",
    "claims": "01_research/claims.json",
    "claims_map": "01_research/claims-map.json",
    "evidence_plan": "01_research/evidence-plan.json",
    "evidence_provenance": "01_research/evidence-provenance.json",
    "evidence_lineage": "01_research/evidence-lineage.json",
    "asset_inventory": "01_research/asset-inventory.json",
    "human_operation_receipt": "03_assets/human-operation-receipt.json",
    "video_script": "04_video/video-script.md",
    "teaching_contract": "04_video/teaching-contract.json",
    "design_direction": "04_video/design-direction.json",
    "design_review": "04_video/design-direction.md",
    "execution_plan": "00_brief/execution-plan.json",
    "copy_brief": "04_video/copy-brief.json",
    "copy_strategy": "00_brief/copy-strategy.json",
    "audience_insight": "01_research/audience-insight.json",
    "content_strategy": "00_brief/content-strategy.json",
    "script_compile": "04_video/script-compilation.json",
    "audio_handoff": "04_video/audio-handoff.json",
    "component_execution": "05_publish/component-execution.json",
    "video": "04_video/video.json",
    "storyboard": "04_video/storyboard.csv",
    "director_plan": "04_video/director-material-plan.json",
    "director_plan_review": "04_video/director-material-plan.md",
    "model_runtime": "04_video/model-runtime.json",
    "production_profile": "04_video/production-profile.json",
    "asset_ledger": "03_assets/asset-ledger.csv",
    "asset_index": "03_assets/asset-index.json",
    "media_validation": "03_assets/media-validation.json",
    "material_canary": "04_video/material-canary.json",
    "material_visual_lock": "04_video/material-visual-lock.json",
    "runtime_plan": "04_video/runtime-plan.json",
    "source_candidates": "03_assets/source-candidates.json",
    "quality": "05_publish/quality.json",
    "subtitle_qc": "05_publish/subtitle-qc.json",
    "skill_catalog": "05_publish/skill-catalog.json",
    "workflow_audit": "05_publish/workflow-audit.json",
    "publish_plan": "05_publish/publish-plan.json",
    "design_lint": "05_publish/design-lint.json",
    "rights_report": "05_publish/rights-report.json",
    "provenance_report": "05_publish/provenance-report.json",
    "skill_provenance": "05_publish/skill-provenance.json",
    "video_qc": "05_publish/video-qc.json",
    "pipeline_integrity_qc": "05_publish/pipeline-integrity-qc.json",
    "feedback_report": "05_publish/feedback-report.json",
    "delivery_manifest": "05_publish/delivery/delivery-manifest.json",
    "distribution": "05_publish/distribution.json",
    "variants": "05_publish/variants.json",
    "publish_receipt": "05_publish/publish-receipt.json",
    "sidecar_publish": "05_publish/sidecar-publish.json",
    "creator_ops": "05_publish/creator-ops.json",
    "metrics": "06_metrics/metrics.json",
    "comments": "06_metrics/comments.json",
    "creator_sidecar": "06_metrics/creator-sidecar.json",
    "comment_recap": "06_metrics/comment-recap.json",
    "feedback_integrity": "06_metrics/feedback-integrity.json",
    # Canonical copy-to-video hand-offs.  Legacy paths above remain readable
    # for historical audit reports but are not used by the canonical gates.
    "canonical_brief": "00_brief/brief.json",
    "canonical_audience_insight": "01_research/audience-insight.json",
    "canonical_sources": "01_research/sources.json",
    "canonical_claims": "01_research/claims.json",
    "canonical_script": "02_script/script.json",
    "canonical_review": "02_script/review.json",
    "canonical_audio": "03_audio/audio-handoff.json",
    "canonical_visual_plan": "04_visual/visual-plan.json",
    "canonical_asset_ledger": "05_assets/asset-ledger.json",
    "canonical_master_timeline": "06_edit/master-timeline.json",
    "canonical_quality": "07_quality/quality-report.json",
    "canonical_delivery": "08_delivery/delivery-manifest.json",
    "canonical_publish_receipt": "09_feedback/publish-receipt.json",
    "canonical_feedback": "09_feedback/feedback.json",
    "design_history": "06_metrics/design-history.json",
    "trend_score": "01_research/trend-score.json",
    "source_snapshots": "01_research/snapshots/index.json",
    "source_screenshots": "01_research/snapshots/screenshots/index.json",
    "source_screenshot_visual_qc": "01_research/snapshots/screenshots/visual-qc.json",
    "hotspot_snapshot": "01_research/snapshots/hotspot-report.json",
    "scene_analysis": "04_video/analysis/scene-analysis.json",
    "reframe_plan": "04_video/analysis/reframe-plan.json",
    "runtime_demo_evidence": "04_video/analysis/runtime-demo-evidence.json",
    "visual_review": "05_publish/visual-review.json",
    "visual_qc": "05_publish/visual-qc.json",
    "creative_qc": "05_publish/creative-qc.json",
    "teaching_qc": "05_publish/teaching-qc.json",
    "naturalness_qc": "05_publish/naturalness-qc.json",
    "video_planning_audit": "05_publish/video-planning-audit.json",
    "best_practice_qc": "05_publish/best-practice-qc.json",
    "image_prompt_plan": "03_assets/image-prompt-plan.json",
    "i2v_requests": "03_assets/i2v-requests.json",
    "i2v_job_specs": "03_assets/i2v-job-specs.json",
    "image_generation_provenance": "05_publish/image-generation-provenance.json",
    "image_qc": "05_publish/image-qc.json",
    "visual_route": "04_video/visual-route.json",
    "visual_route_review": "04_video/visual-route.md",
    "broll_plan": "04_video/broll-plan.json",
    "broll_plan_review": "04_video/broll-plan.md",
    "human_operation_plan": "04_video/human-operation-plan.json",
    "human_operation_manual": "04_video/human-operation-manual.md",
    "asset_requests": "03_assets/asset-requests.md",
    "broll_manifest": "03_assets/broll/manifest.json",
    "openchatcut_asset_intake": "03_assets/broll/openchatcut-intake.json",
    "openchatcut_assets_board": "04_video/openchatcut-assets-board.md",
    "openchatcut_consumption_plan": "04_video/openchatcut-consumption-plan.json",
    "openchatcut_best_practice_plan": "04_video/openchatcut-best-practice-plan.md",
    "broll_qc": "05_publish/broll-qc.json",
    "motion_plan": "04_video/motion-plan.json",
    "motion_check": "05_publish/motion-check.json",
    "motion_provenance": "05_publish/motion-provenance.json",
    "hyperframes_plan": "06_motion/hyperframes-native/hyperframes-plan.json",
    "hyperframes_composition": "06_motion/hyperframes-native/index.html",
    "remotion_plan": "06_motion/remotion-native/remotion-plan.json",
    "motion_render_report": "05_publish/motion-render-report.json",
    "motion_adversarial_audit": "05_publish/motion-adversarial-audit.json",
    "digital_assets": "04_video/digital-assets.json",
    # Canonical motion route. These files are compatibility receipts; the
    # authoritative edit/render hand-off lives under 06_edit.
    "plugin_scene_brief": "04_video/scene-brief.json",
    "visual_profile": "04_video/visual-profile.json",
    "plugin_render_manifest": "06_motion/plugin-render-manifest.json",
    "plugin_native_qc": "05_publish/plugin-native-qc.json",
    "plugin_native_concurrency_qc": "05_publish/plugin-native-concurrency-qc.json",
    "plugin_native_visual_qc": "05_publish/plugin-native-visual-qc.json",
}

OPTIONAL_UNTIL_STAGE = {"execution_plan", "content_strategy", "copy_strategy", "copy_brief", "design_direction", "design_review", "script_compile", "audio_handoff", "teaching_contract", "teaching_qc", "naturalness_qc", "video_planning_audit", "design_lint", "rights_report", "provenance_report", "feedback_report", "delivery_manifest", "variants", "subtitle_qc", "design_history", "skill_catalog", "workflow_audit", "publish_plan", "trend_score", "source_snapshots", "scene_analysis", "visual_route", "broll_plan", "broll_plan_review", "human_operation_plan", "human_operation_manual", "asset_requests", "broll_manifest", "broll_qc", "source_candidates", "reframe_plan", "runtime_demo_evidence", "visual_review", "visual_qc", "sidecar_publish", "creator_ops", "creator_sidecar", "comment_recap", "image_prompt_plan", "i2v_requests", "i2v_job_specs", "image_generation_provenance", "image_qc", "digital_assets", "openchatcut_asset_intake", "openchatcut_assets_board", "openchatcut_consumption_plan", "openchatcut_best_practice_plan", "motion_plan", "motion_check", "motion_provenance", "hyperframes_plan", "hyperframes_composition", "remotion_plan", "remotion_project", "motion_render_report", "motion_adversarial_audit", "best_practice_qc", "plugin_scene_brief", "visual_profile", "plugin_render_manifest", "plugin_native_qc", "plugin_native_concurrency_qc", "plugin_native_visual_qc"}

# Bootstrap validation may tolerate a report before its producer runs, but it
# must stop treating that report as optional once the workflow reaches the
# producer/consumer gate.  This closes the old gap where every generated
# artifact stayed warning-only forever.
ARTIFACT_REQUIRED_STAGE = {
    "human_operation_forecast": "brief",
    "human_operation_guide": "brief",
    "human_operation_plan": "assets_plan",
    "human_operation_manual": "assets_plan",
    "execution_plan": "brief",
    "content_strategy": "brief",
    "copy_strategy": "script",
    "copy_brief": "script",
    "audience_insight": "brief",
    "script_compile": "script",
    "audio_handoff": "audio",
    "teaching_contract": "script",
    "teaching_qc": "quality",
    "naturalness_qc": "quality",
    "video_planning_audit": "quality",
    "design_lint": "design",
    "rights_report": "assets",
    "visual_route": "assets",
    "motion_plan": "video_production",
    "motion_check": "video_production",
    "motion_provenance": "video_production",
    "hyperframes_plan": "video_production",
    "hyperframes_composition": "video_production",
    "remotion_plan": "video_production",
    "motion_render_report": "video_production",
    "motion_adversarial_audit": "video_production",
    "provenance_report": "quality",
    "subtitle_qc": "quality",
    "video_qc": "quality",
    "visual_qc": "quality",
    "creative_qc": "quality",
    "visual_review": "quality",
    "variants": "quality",
    "delivery_manifest": "quality",
    "workflow_audit": "quality",
    "best_practice_qc": "quality",
    "openchatcut_asset_intake": "assets",
    "openchatcut_assets_board": "assets",
    "openchatcut_consumption_plan": "assets",
    "openchatcut_best_practice_plan": "assets",
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def image_policy_enabled(account: str) -> bool:
    """Require an explicit profile opt-in before any image route is planned."""
    if account != ACCOUNT:
        return False
    try:
        profile = json.loads((repo_root() / "profiles" / "profile.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    video = profile.get("video", {}) if isinstance(profile, dict) else {}
    policy = video.get("image_policy", {}) if isinstance(video, dict) else {}
    return isinstance(policy, dict) and policy.get("enabled") is True


def configured_minimax_h3() -> dict[str, Any]:
    """Read the local H3 profile without copying model/media into a package."""
    path = repo_root() / "local-runtime.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    profile = payload.get("minimax_h3", {}) if isinstance(payload, dict) else {}
    if not isinstance(profile, dict):
        return {}
    def expand(value: Any) -> Any:
        if isinstance(value, str):
            return os.path.expandvars(value)
        if isinstance(value, list):
            return [expand(item) for item in value]
        if isinstance(value, dict):
            return {key: expand(item) for key, item in value.items()}
        return value
    return expand(profile)


def configured_funasr() -> dict[str, Any]:
    """Read the pinned local FunASR runtime from local-runtime.json."""
    path = repo_root() / "local-runtime.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    profile = payload.get("funasr", {}) if isinstance(payload, dict) else {}
    if not isinstance(profile, dict):
        return {}
    def expand(value: Any) -> Any:
        if isinstance(value, str):
            return os.path.expandvars(value)
        if isinstance(value, list):
            return [expand(item) for item in value]
        if isinstance(value, dict):
            return {key: expand(item) for key, item in value.items()}
        return value
    return expand(profile)


def load_media_policy() -> tuple[dict[str, Any], str]:
    path = repo_root() / "local-media-policy.json"
    if not path.is_file():
        raise SystemExit(f"missing local media policy: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SystemExit(f"local media policy is invalid JSON: {error}") from error
    if not isinstance(value, dict) or value.get("policy") != "local-first-explicit-remote":
        raise SystemExit("media policy must declare local-first-explicit-remote")
    if not isinstance(value.get("blocked_provider_tokens"), list):
        raise SystemExit("local media policy must declare blocked_provider_tokens")
    return value, hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def canonical_paths() -> dict[str, str]:
    """Return canonical hand-offs plus explicit derived-artifact aliases.

    The ``canonical_*`` keys remain authoritative.  The unprefixed aliases
    below are deliberate compatibility pointers for planners that predate the
    canonical artifact map; they point into the current package instead of
    silently falling back to ``03_assets``/``04_video``/``05_publish``.
    """

    paths = {f"canonical_{key}": value for key, value in canonical_artifact_paths().items()}
    paths.update({
        "workflow_route": "00_brief/workflow-route.json",
        "topic_backlog": "00_brief/topic-backlog.json",
        "execution_plan": "00_brief/execution-plan.json",
        "human_operation_forecast": "00_brief/human-operation-forecast.json",
        "human_operation_guide": "00_brief/human-operation-guide.md",
        "audience_insight": "01_research/audience-insight.json",
        "sources": "01_research/sources.json",
        "claims": "01_research/claims.json",
        "script": "02_script/script.json",
        "review": "02_script/review.json",
        "audio_handoff": "03_audio/audio-handoff.json",
        "visual_plan": "04_visual/visual-plan.json",
        "visual_route": "04_visual/visual-route.json",
        "visual_route_review": "04_visual/visual-route.md",
        "design_direction": "04_visual/design-direction.json",
        "design_review": "04_visual/design-direction.md",
        "design_lint": "07_quality/design-lint.json",
        "runtime_demo_evidence": "04_visual/runtime-demo-evidence.json",
        "skill_catalog": "07_quality/skill-catalog.json",
        "director_plan": "04_visual/director-material-plan.json",
        "broll_plan": "04_visual/broll-plan.json",
        "broll_plan_review": "04_visual/broll-plan.md",
        "storyboard": "04_visual/storyboard.csv",
        "human_operation_plan": "04_visual/human-operation-plan.json",
        "human_operation_manual": "04_visual/human-operation-manual.md",
        "human_operation_receipt": "05_assets/human-operation-receipt.json",
        "asset_ledger": "05_assets/asset-ledger.csv",
        "asset_ledger_csv": "05_assets/asset-ledger.csv",
        "image_prompt_plan": "05_assets/image-prompt-plan.json",
        "image_generation_provenance": "05_assets/image-generation-provenance.json",
        "generation_plan": "05_assets/generation-plan.json",
        "generation_jobs": "05_assets/generation-jobs",
        "generation_history": "05_assets/history",
        "generated_media": "05_assets/generated",
        "i2v_job_specs": "05_assets/i2v-job-specs.json",
        "i2v_requests": "05_assets/i2v-requests.json",
        "plugin_scene_brief": "04_visual/plugin-scene-brief.json",
        "visual_profile": "04_visual/visual-profile.json",
        "plugin_render_manifest": "06_edit/plugin-render-manifest.json",
        "plugin_native_qc": "07_quality/plugin-native-qc.json",
        "plugin_native_concurrency_qc": "07_quality/plugin-native-concurrency-qc.json",
        "plugin_native_visual_qc": "07_quality/plugin-native-visual-qc.json",
        "visual_review": "07_quality/visual-review.json",
        "workflow_improvement_log": "09_feedback/workflow-improvement-log.json",
        "source_candidates": "01_research/source-candidates.json",
        "source_screenshots": "01_research/snapshots/screenshots/index.json",
        "source_screenshot_visual_qc": "01_research/snapshots/screenshots/visual-qc.json",
        # OpenChatCut inspection is an optional intermediate receipt.  Keep its
        # canonical destination explicit for operators without making a fresh
        # package fail validation before the visible editor roundtrip runs.
        # The intake/consumption hand-offs are also declared here so every
        # canonical package stays inside the V2 stage tree. Older packages
        # that do not carry these keys continue to use their historical
        # 03_assets/04_video compatibility locations in the planners.
        "canonical_openchatcut_asset_intake": "05_assets/openchatcut-intake.json",
        "canonical_openchatcut_assets_board": "04_visual/openchatcut-assets-board.md",
        "canonical_openchatcut_consumption_plan": "06_edit/openchatcut-consumption-plan.json",
        "canonical_openchatcut_best_practice_plan": "06_edit/openchatcut-best-practice-plan.md",
        "canonical_openchatcut_bridge": "06_edit/openchatcut-bridge.json",
        "canonical_openchatcut_timeline_snapshot": "06_edit/openchatcut-timeline-snapshot.json",
    })
    return paths


def write_canonical_scaffold(
    project: Path,
    args: argparse.Namespace,
    manifest: dict[str, Any],
    content_type: str,
    *,
    topic: str = "",
    pillar: str = "",
    route: dict[str, Any] | None = None,
) -> None:
    """Create a clean canonical package without bootstrapping a legacy tree."""

    content_id = args.content_id
    account = args.account
    contract = CANONICAL_CONTRACT_ID
    paths = canonical_paths()
    def strict_artifact_path(key: str) -> str:
        """Resolve a strict hand-off without widening legacy path aliases."""
        return str(paths.get(key) or paths.get(f"canonical_{key}") or canonical_artifact_paths()[key])
    write_json(project / paths["execution_plan"], canonical_execution_plan(content_id, args.title, account))
    route = route if isinstance(route, dict) else {}
    topic_id = str(route.get("topic_id") or getattr(args, "topic_id", "") or content_id).strip()
    scheduled_for = str(getattr(args, "scheduled_for", "") or "").strip()
    write_json(project / paths["topic_backlog"], {
        "schema_version": 1,
        "content_id": content_id,
        "account": account,
        "status": "active",
        "items": [{
            "topic_id": topic_id,
            "content_id": content_id,
            "title": topic or args.title,
            "account": account,
            "pillar": pillar,
            "format": "short-video",
            "priority": 3,
            "status": "queued" if scheduled_for else "idea",
            "evidence_floor": 2,
            "scheduled_for": scheduled_for,
            "experiment": "",
            "notes": "",
        }],
        "next_review": "",
    })
    write_json(project / paths["canonical_brief"], {
        "schema_version": 1, "contract": contract, "content_id": content_id,
        "account": account, "status": "pending", "content_pillar": "",
        "content_type": content_type, "primary_audience": "", "secondary_audience": "",
        "viewer_situation": "", "viewer_goal": "", "viewer_motivation": "",
        "promise": "", "expected_emotion_change": "", "cta": "", "duration_tier": "",
        "evidence_density_reason": "", "key_questions": [], "initial_evidence_plan": [],
        "production_disclosure": {"digital_human": True, "voice_clone": True, "synthetic_visuals": True},
    })
    # Audience Lens v3 is the research contract consumed by both the
    # audience-validation gate and the canonical Research gate.  Keep the
    # small top-level projection fields for the canonical checker and future
    # readers, but seed the complete v3 structure instead of the old v1
    # placeholder that could never pass audience_insight.py.
    audience_insight = build_audience_scaffold(
        content_id,
        topic or args.title,
        account=account,
        content_type=content_type,
        pillar=pillar,
    )
    audience_insight.update({
        "contract": contract,
        "primary_audience": "",
        "secondary_audience": "",
        "viewer_tasks": [],
        "practical_value": "",
        "emotional_value": "",
    })
    write_json(project / paths["canonical_audience_insight"], audience_insight)
    candidate = build_content_candidate_scaffold(
        content_id,
        topic=topic or args.title,
        opc_task_id=str(route.get("opc_task_id") or route.get("task_id") or "") or None,
        content_type=content_type,
    )
    write_json(project / paths["canonical_content_candidate"], candidate)
    forecast_path = project / paths["human_operation_forecast"]
    forecast_meta = route.get("operation_forecast") if isinstance(route.get("operation_forecast"), dict) else {}
    forecast_source = Path(str(forecast_meta.get("report", ""))).expanduser() if forecast_meta.get("report") else None
    if forecast_source and forecast_source.is_file():
        try:
            forecast = json.loads(forecast_source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise SystemExit(f"human operation forecast is invalid: {error}") from error
        if not isinstance(forecast, dict):
            raise SystemExit("human operation forecast must be a JSON object")
        write_json(forecast_path, forecast)
    elif not forecast_path.is_file():
        write_json(forecast_path, {
            "schema_version": 1,
            "content_id": content_id,
            "account": account,
            "topic": topic or args.title,
            "status": str(forecast_meta.get("status", "pending")),
            "risk_summary": {"level": "warn", "blocking_reasons": [], "warnings": ["Run human_operation_forecast.py draft before Brief approval."]},
            "operations": [],
            "human_acceptance": {"status": "pending", "reviewer": "", "accepted_at": "", "note": ""},
        })
    guide_path = project / paths["human_operation_guide"]
    guide_source = Path(str(forecast_meta.get("guide", ""))).expanduser() if forecast_meta.get("guide") else None
    if guide_source and guide_source.is_file():
        guide_path.write_text(guide_source.read_text(encoding="utf-8"), encoding="utf-8")
    elif not guide_path.is_file():
        write_text(guide_path, "# 人工操作可行性预判\n\n请先运行 `scripts/human_operation_forecast.py draft`，审核并接受报告后再进入 Brief。")
    write_json(project / paths["canonical_sources"], {
        "schema_version": 1, "contract": contract, "content_id": content_id,
        "sources": [], "status": "pending",
    })
    write_json(project / paths["canonical_claims"], {
        "schema_version": 1, "contract": contract, "content_id": content_id,
        "status": "pending", "claims": [],
    })
    write_json(project / paths["canonical_script"], {
        "schema_version": 1, "contract": contract, "content_id": content_id,
        "status": "pending", "title": args.title, "hook": "", "close": "",
        "beats": [], "script_sha256": "",
    })
    write_json(project / paths["canonical_review"], {
        "schema_version": 1, "contract": contract, "content_id": content_id,
        "status": "pending", "promise_match": False, "audience_clear": False,
        "practical_value_present": False, "emotional_value_present": False,
        "evidence_plan_complete": False, "no_generated_evidence_claims": True,
        "conclusion_limits_cta_clear": False, "natural_read": False, "script_sha256": "",
    })
    write_json(project / paths["canonical_audio"], {
        "schema_version": 1, "contract": contract, "content_id": content_id,
        "status": "pending", "narration_wav": "", "provider": VOICE_PROVIDER,
        "model": TTS_MODEL, "voice_mode": "voice-clone", "voice_authorization": "",
        "reference_audio_sha256": "", "script_sha256": "", "funasr_text": "",
        "srt": "", "audio_sha256": "", "duration_seconds": 0.0,
    })
    write_json(project / paths["canonical_visual_plan"], {
        "schema_version": 1, "contract": contract, "content_id": content_id,
        "status": "pending", "audio_sha256": "", "beats": [],
        "recording_policy": "claim-driven; no global ratio",
    })
    # v2 separates visual planning from route selection and material
    # ownership.  These hand-offs are deliberately pending; no provider is
    # called during package initialization.
    write_json(project / paths["canonical_visual_route"], {
        "schema_version": 1, "contract": contract, "content_id": content_id,
        "status": "pending", "routes": [], "fallback_policy": "none",
    })
    write_json(project / paths["canonical_director_material_plan"], {
        "schema_version": 1, "contract": contract, "content_id": content_id,
        "status": "pending", "scenes": [], "ownership": {}, "failure_policy": "block",
    })
    # Strict provider routing is an explicit plan artifact.  It is created at
    # bootstrap so a later editor cannot accidentally omit a provider and then
    # rely on a static/placeholder substitute.
    write_json(project / strict_artifact_path("provider_route_manifest"), {
        "schema_version": 1,
        "contract": contract,
        "content_id": content_id,
        "status": "pending",
        "fallback_policy": "none",
        "routes": {
            "digital_human": {
                "provider": "minimax-h3",
                "engine": "minimax_h3_ref2va",
                "required": True,
                "status": "pending",
                "failure_policy": "block",
                "audio_conditioning": {
                    "generation_mode": "continuous-audio-conditioned",
                    "generation_units": 1,
                    "input": "standalone Audio 1",
                    "frame_grid": "17k+5",
                    "fps": 24,
                    "native_av_required": True,
                    "delivered_audio": "h3-source-locked",
                    "audio_lock": {
                        "enabled": True,
                        "mode": "h3-audio-latent-zero-mask",
                        "waveform_fit": "fit-to-target-before-zero-mask",
                        "target_audio_latent_fps": 40,
                        "zero_noise_mask": True,
                        "max_unlocked_audio_latent_values": 0,
                        "delivery_stream": "same-normalized-source-waveform",
                    },
                },
            },
            "bridge_image": {"provider": "chatgpt-bridge", "required": True, "status": "pending", "failure_policy": "block", "output": "generated_image"},
            "gemini_broll": {"provider": "gemini-web-omni", "required": True, "status": "pending", "failure_policy": "block", "surface": "web", "omni_capability_required": True, "output": "illustrative_image_broll"},
            "i2v": {"provider": "gflow-cli", "required": True, "status": "pending", "failure_policy": "block", "mode": "i2v", "input": "approved-image-only"},
            "editor": {"provider": "openchatcut", "required": True, "status": "pending", "failure_policy": "block", "mode": "visible-ui-plus-mcp"},
            "renderer": {"provider": "remotion", "required": True, "status": "pending", "failure_policy": "block", "mode": "final-compositor"},
        },
    })
    write_json(project / paths["broll_plan"], {
        "schema_version": 1, "contract": contract, "content_id": content_id,
        "status": "pending", "source_precedence": ["real_screen_recording", "real_source", "gemini-web-omni", "chatgpt-bridge"],
        "beats": [], "rights_review": {"status": "pending", "reviewer": ""},
    })
    write_text(project / paths["canonical_openchatcut_best_practice_plan"], "# OpenChatCut 最佳实践规划\n\n等待 B-roll 与音频计划通过后，运行 `scripts/openchatcut_asset_intake.py` 和 `scripts/openchatcut_consumption_plan.py`，再由人工复核素材、轨道、字幕与旁白绑定。\n")
    write_text(project / strict_artifact_path("asset_requests"), "# B-roll 素材请求\n\n仅在已批准计划与真实获取回执齐全后清关。\n")
    write_json(project / paths["director_plan"], {
        "schema_version": 1, "contract": contract, "content_id": content_id,
        "status": "pending", "scenes": [], "notes": "Populate scene ownership after the approved script; no provider call is implied.",
    })
    (project / paths["storyboard"]).write_text("scene_id,start_frame,end_frame,shot,visual,narration\n", encoding="utf-8")
    write_json(project / paths["image_prompt_plan"], {
        "schema_version": 1, "contract": contract, "content_id": content_id,
        "status": "pending", "provider": "chatgpt-bridge", "text_policy": "generated-scene-text-free; all Chinese labels belong to Remotion/HTML", "items": [],
    })
    write_json(project / paths["image_generation_provenance"], {
        "schema_version": 1, "contract": contract, "content_id": content_id,
        "status": "pending", "provider": "chatgpt-bridge", "items": [],
    })
    write_json(project / paths["generation_plan"], {
        "schema_version": 1, "contract": contract, "content_id": content_id,
        "status": "pending", "jobs": [], "idempotency_policy": "reconcile-before-submit", "provider_switching": "forbidden",
    })
    write_json(project / paths["i2v_job_specs"], {
        "schema_version": 1, "contract": contract, "content_id": content_id,
        "status": "pending", "provider": "gflow-cli", "mode": "i2v", "jobs": [],
    })
    for key, provider in (("bridge_receipt", "chatgpt-bridge"), ("gemini_web_receipt", "gemini-web-omni"), ("gflow_receipt", "gflow-cli")):
        receipt = {
            "schema_version": 1, "contract": contract, "content_id": content_id,
            "provider": provider, "status": "pending", "technical": False, "job_id": "", "file": "", "sha256": "",
        }
        if key == "gemini_web_receipt":
            # Keep the pending scaffold explicit about the visual review
            # fields required by the Gemini illustrative-B-roll contract.
            receipt.update({
                "text_free_reviewed": False,
                "text_present": None,
                "logo_present": None,
                "watermark_present": None,
                "non_factual_broll_reviewed": False,
                "reviewer": "",
                "code_present": None,
                "digits_present": None,
                "product_ui_present": None,
                "fact_screenshot_present": None,
                "experiment_result_present": None,
            })
        elif key == "bridge_receipt":
            # The Bridge receipt is promoted only after a visible browser
            # preflight and explicit human acceptance.  Keep the required
            # aliases visible in the pending scaffold so a missing review
            # cannot be mistaken for a legacy export receipt.
            receipt.update({
                "generation_id": "",
                "output_sha256": "",
                "session_status": "",
                "page_assets": False,
                "manual_review": False,
                "text_free_reviewed": False,
                "text_free": False,
                "rights_reviewed": False,
                "facts_reviewed": False,
                "rights": False,
                "facts": False,
                "reviewer": "",
            })
        elif key == "gflow_receipt":
            receipt.update({
                "generation_id": "",
                "aspect_ratio": "9:16",
                "output_sha256": "",
                "provider_result": "",
                "provider_result_sha256": "",
                "provider_job_id": "",
                "provider_media_id": "",
                "gflow_probe": {
                    "version": "",
                    "tools_verified": False,
                    "auth_verified": False,
                    "passed": False,
                    "preflight": "",
                    "preflight_sha256": "",
                },
            })
        write_json(project / strict_artifact_path(key), receipt)
    write_json(project / strict_artifact_path("media_generation_receipt"), {
        "schema_version": 1, "contract": contract, "content_id": content_id,
        "status": "pending", "technical": False, "jobs": [], "all_required_routes_completed": False,
    })
    write_json(project / strict_artifact_path("h3_manifest"), {
        "schema_version": 1, "contract": contract, "content_id": content_id,
        "provider": "minimax-h3", "engine": "minimax_h3_ref2va", "status": "pending", "file": "", "sha256": "",
        "audio_sha256": "",
        "audio_conditioning": {
            "generation_mode": "continuous-audio-conditioned",
            "generation_units": 1,
            "input": "standalone Audio 1",
            "frame_grid": "17k+5",
            "fps": 24,
            "native_av_required": True,
            "delivered_audio": "h3-source-locked",
            "audio_lock": {
                "enabled": True,
                "mode": "h3-audio-latent-zero-mask",
                "waveform_fit": "fit-to-target-before-zero-mask",
                "target_audio_latent_fps": 40,
                "zero_noise_mask": True,
                "max_unlocked_audio_latent_values": 0,
                "delivery_stream": "same-normalized-source-waveform",
            },
        },
        "segments": [], "profile": "e4", "fps": 24,
    })
    write_json(project / strict_artifact_path("h3_qc"), {
        "schema_version": 1, "contract": contract, "content_id": content_id,
        "status": "pending", "passed": False, "technical": False, "manual_review": False, "reviewer": "",
        "dynamic_motion": False, "lip_sync": False, "frozen_frame_max_seconds": 0.0,
    })
    # The plan names a top-level 05_avatar hand-off.  A pending manifest/QC
    # pair is safe to scaffold so the strict gate has an explicit destination;
    # only a real H3 run may create 05_avatar/avatar.mp4 or mark those receipts
    # verified.  No media bytes are manufactured during package init.
    write_json(project / paths["canonical_asset_ledger"], {
        "schema_version": 1, "contract": contract, "content_id": content_id,
        # Assets is a plan/route hand-off at bootstrap.  It becomes populated
        # only after the approved provider plans have produced real receipts;
        # Edit & Render is the first gate that requires non-vacuous outputs.
        "status": "ready_for_review", "assets": [],
        "image_to_video_policy": {"provider": "gflow-cli", "mode": "i2v", "approved_image_required": True},
    })
    # CSV-based compatibility planners use this sidecar; the JSON ledger above
    # remains the only canonical Assets hand-off and is never replaced by it.
    (project / paths["asset_ledger_csv"]).write_text("asset_id,filename_or_url,status,output_sha256\n", encoding="utf-8")
    write_json(project / paths["human_operation_receipt"], {
        "schema_version": 1,
        "contract": contract,
        "workflow_stage": "assets_plan",
        "content_id": content_id,
        "account": account,
        "status": "pending",
        "files": [],
    })
    write_json(project / paths["canonical_master_timeline"], {
        "schema_version": 1, "contract": contract, "content_id": content_id,
        "status": "pending", "audio_source": paths["canonical_audio"], "audio_sha256": "",
        "openchatcut_owner": "timeline-editor", "hyperframes_owner": "transparent-overlay",
        "remotion_owner": "final-compositor", "openchatcut_project": "", "remotion_project": "",
        "render_receipt": "", "candidate_mp4": "", "candidate_sha256": "",
        "digital_human_segments": [], "fit": "contain", "tracks": [],
    })
    workspace_root, runtime_root = runtime_layout_roots()
    write_json(project / strict_artifact_path("runtime_preflight"), {
        "schema_version": 1,
        "contract": "dy-x1024-runtime-preflight-v1",
        "content_id": content_id,
        "status": "blocked",
        "passed": False,
        "strict": True,
        "checked_at": "not-run",
        "layout": "configs/runtime-layout.json",
        "workspace_root": workspace_root,
        "runtime_root": runtime_root,
        "checks": {},
        "errors": ["runtime preflight has not been executed"],
        "warnings": [],
    })
    write_json(project / strict_artifact_path("openchatcut_roundtrip"), {
        "schema_version": 1, "contract": contract, "content_id": content_id,
        "provider": "openchatcut", "status": "pending", "technical": False, "passed": False, "project": "", "export": "", "sha256": "",
    })
    write_json(project / strict_artifact_path("remotion_render_receipt"), {
        "schema_version": 1, "contract": contract, "content_id": content_id,
        "provider": "remotion", "status": "pending", "technical": False, "rendered": False, "renderer": "remotion",
        "remotion_version": "", "composition": "", "exit_code": None, "command": [], "inputs": [], "output": "", "sha256": "",
    })
    write_json(project / strict_artifact_path("render_receipt"), {
        "schema_version": 1, "contract": contract, "content_id": content_id,
        "provider": "remotion", "status": "pending", "technical": False, "rendered": False, "renderer": "remotion",
        "remotion_version": "", "composition": "", "inputs": [], "output": "", "sha256": "", "exit_code": None,
        "command": [],
    })
    write_json(project / paths["canonical_quality"], {
        "schema_version": 1, "contract": contract, "content_id": content_id,
        "status": "pending", "digital_human_present": False, "voice_clone_consistent": False,
        "direct_evidence_coverage": 0.0, "i2v_lineage_valid": False, "caption_sync": False,
        "contact_sheet_coverage": "not-verified",
        "media_qc_passed": False, "audio_lufs": 0.0, "true_peak_db": 0.0, "clipping_count": 0,
        "candidate_mp4": "", "candidate_mp4_sha256": "",
        "remotion_still": "", "remotion_still_sha256": "", "contact_sheet": "",
        "contact_sheet_sha256": "", "render_receipt": "", "render_receipt_sha256": "",
        "cover": "", "publish_copy": "", "human_review": False,
    })
    write_json(project / strict_artifact_path("visual_qc"), {
        "schema_version": 1, "contract": contract, "content_id": content_id,
        "status": "pending", "passed": False, "technical": False, "manual_review": False,
        "reviewer": "", "evidence": [], "candidate_mp4": "", "candidate_sha256": "",
        "metrics": {"glyph_errors": 0, "crop_errors": 0, "aigc_label_occlusion_count": 0, "caption_overlap_seconds": 0.0, "unintentional_freeze_max_seconds": 0.0}, "errors": [], "warnings": [],
    })
    write_json(project / strict_artifact_path("visual_review"), {
        "schema_version": 1, "contract": contract, "content_id": content_id,
        "status": "pending", "passed": False, "reviewer": "", "reviewed_at": "",
        "candidate_mp4": "", "candidate_sha256": "", "full_watch": False, "full_watch_seconds": 0.0, "contact_sheet": "", "mobile_review": {
            "safe_area_passed": False, "subtitle_readable": False, "cta_readable": False,
        }, "notes": "Complete a full human watch and bind the current render SHA-256 before Quality approval.",
    })
    write_json(project / strict_artifact_path("audio_timing_qc"), {
        "schema_version": 1, "contract": contract, "content_id": content_id,
        "status": "pending", "passed": False, "technical": False, "manual_review": False,
        "reviewer": "", "evidence": [], "audio_file": "", "audio_sha256": "",
        "max_beat_drift_seconds": None, "target_max_beat_drift_seconds": 0.25, "errors": [],
    })
    write_json(project / paths["plugin_native_visual_qc"], {
        "schema_version": 1, "contract": contract, "content_id": content_id,
        "status": "pending", "passed": False, "technical": False, "manual_review": False,
    })
    write_json(project / paths["canonical_delivery"], {
        "schema_version": 1, "contract": contract, "content_id": content_id,
        "account": account, "status": "pending", "files": [],
        "disclosures": {"digital_human": True, "voice_clone": True, "generated_visuals": True},
    })
    write_json(project / paths["canonical_publish_receipt"], {
        "schema_version": 1, "contract": contract, "content_id": content_id,
        "status": "not_published", "platform": "douyin", "external_id": "", "url": "", "published_at": "",
    })
    write_json(project / paths["canonical_feedback"], {
        "schema_version": 1, "contract": contract, "content_id": content_id,
        "status": "not_published", "snapshots": [], "learning": [],
    })
    relationship = build_audience_relationship_scaffold(
        content_id,
        candidate_id=str(candidate.get("linkage", {}).get("content_candidate_id") or "") or None,
    )
    write_json(project / paths["canonical_audience_relationship"], relationship)
    write_json(project / paths["canonical_workflow_improvement_log"], {
        "schema_version": 1,
        # Schema version 1 is retained for this append-only sidecar; its
        # workflow contract follows the owning V2 package.
        "contract": contract,
        "content_id": content_id,
        "status": "empty",
        "entries": [],
    })
    write_json(project / paths["canonical_aigc_manifest"], {
        "schema_version": 1,
        "contract": "workflow-v2-hardening-v1",
        "content_id": content_id,
        "assets": {
            name: {"required": True, "completed": False, "ai_assisted": name == "script", "ai_generated": name in {"voice", "image", "video", "music"}, "provider": "", "model": "", "artifact_ids": []}
            for name in ("script", "voice", "image", "video", "music")
        },
        "declaration": {"required": True, "completed": False, "location": "", "metadata_sha256": ""},
        "visible_label": {"required": True, "completed": False, "location": "", "metadata_sha256": ""},
        "metadata": {"required": True, "completed": False, "location": "", "metadata_sha256": ""},
    })
    write_json(project / paths["canonical_publish_approval"], {
        "contract": "workflow-v2-hardening-v1", "status": "pending", "reviewer": "", "approved_at": "",
        "workflow_version": CANONICAL_CONTRACT_ID, "policy_version": "", "artifact_sha256": "", "metadata_sha256": "", "artifacts": [],
    })
    (project / paths["canonical_publish_idempotency"]).parent.mkdir(parents=True, exist_ok=True)
    (project / paths["canonical_publish_idempotency"]).write_text("", encoding="utf-8")
    write_json(project / paths["canonical_revenue_attribution"], {
        "schema_version": 1, "contract": "workflow-v2-hardening-v1", "content_id": content_id,
        "origin": {"opc_task_id": None, "opportunity_id": None, "experiment_id": None},
        "production": {"cost": None, "labor_minutes": None},
        "content_metrics": {"views": None, "completion_rate": None, "saves": None, "comments": None},
        "intent_metrics": {"qualified_comments": None, "qualified_dm": None, "profile_visits": None, "inbound_leads": None},
        "business_metrics": {"opportunities": None, "deals": None, "revenue": None, "assisted_revenue": None},
    })
    manifest["paths"] = paths
    write_json(project / "content.json", manifest)


def copy_template(name: str, destination: Path) -> None:
    source = repo_root() / "templates" / name
    if not source.is_file():
        raise SystemExit(f"missing repository template: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def prune_noncanonical_scaffold(project: Path, manifest: dict[str, Any]) -> None:
    """Remove bootstrap-only historical artifacts from a new production package."""
    for directory in ("03_assets", "04_video", "05_publish", "06_metrics", "06_motion"):
        target = (project / directory).resolve()
        target.relative_to(project.resolve())
        if target.is_dir():
            shutil.rmtree(target)
    allowed_files = {
        "00_brief": {"brief.json", "topic-backlog.json", "workflow-route.json", "execution-plan.json"},
        "01_research": {"audience-insight.json", "sources.json", "claims.json"},
    }
    for directory, names in allowed_files.items():
        root = project / directory
        for item in root.iterdir() if root.is_dir() else []:
            if item.name in names or (directory == "01_research" and item.name == "snapshots"):
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
    # Keep the compatibility aliases that point into the canonical workflow
    # tree.  Planners such as image_prompt_plan.py and broll_plan.py still read
    # their historical unprefixed keys; dropping those aliases here silently
    # sends a strict package back to 03_assets/04_video.  The aliases are safe
    # because canonical_paths() contains no legacy directory targets.
    manifest["paths"] = canonical_paths()
    write_json(project / "content.json", manifest)


def init_package(args: argparse.Namespace) -> int:
    project = Path(args.project).expanduser().resolve()
    configured_root = os.environ.get("DY_ARTIFACT_ROOT", "").strip()
    allow_caller_selected = bool(getattr(args, "allow_caller_selected", False)) or os.environ.get("DY_ALLOW_CALLER_SELECTED", "").strip().lower() in {"1", "true", "yes"}
    try:
        selected_contract = canonical_contract_from_environment()
    except ValueError as error:
        raise SystemExit(str(error)) from error
    if selected_contract == LEGACY_CANONICAL_CONTRACT_ID:
        raise SystemExit(
            "content_package init creates new packages only under canonical-copy-to-video-v2; "
            "v1 is read/audit compatibility for existing packages"
        )
    # V1 package creation is intentionally unavailable. This separate
    # caller-selected scaffold mode exists only for isolated compatibility fixtures.
    use_legacy_scaffold = allow_caller_selected
    enforce_artifact_root = not allow_caller_selected
    if enforce_artifact_root:
        artifact_root = Path(configured_root).expanduser().resolve() if configured_root else DEFAULT_ARTIFACT_ROOT.resolve()
        try:
            validate_project_layout(project, args.content_id, artifact_root)
        except ValueError as error:
            raise SystemExit(str(error)) from error
    manifest_path = project / "content.json"
    if manifest_path.exists() and not args.force:
        raise SystemExit(f"content package already exists: {manifest_path}. Use --force only to reinitialize it.")
    require_account(args.account)
    media_policy, media_policy_sha256 = load_media_policy()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,80}", args.content_id):
        raise SystemExit("content_id must use lowercase letters, digits, dot, underscore or hyphen.")
    # Profile-only dependency preflight runs before package directories and
    # manifests are created. Project-specific skill provenance is regenerated
    # after initialization, once the execution plan exists.
    preflight_output = project / (canonical_paths().get("skill_catalog", "07_quality/skill-catalog.json") if not use_legacy_scaffold else PATHS["skill_catalog"])
    preflight = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "skill_catalog.py"),
            "--isolated",
            "--skill-root",
            str(ROOT / "skills"),
            "--output",
            str(preflight_output),
            "--strict",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if preflight.returncode != 0:
        detail = (preflight.stdout or preflight.stderr or "skill catalog preflight failed").strip()
        raise SystemExit(f"skill dependency preflight failed before package initialization:\n{detail[-4000:]}")
    deliverables = [item.strip() for item in args.deliverables.split(",") if item.strip()]
    if deliverables != ["video"]:
        raise SystemExit("this project produces Douyin video only; use --deliverables video")
    platforms = [item.strip() for item in args.platforms.split(",") if item.strip()] or ["douyin"]
    if platforms != ["douyin"]:
        raise SystemExit("this project targets Douyin only; use --platforms douyin")
    package_dirs = PACKAGE_DIRS if use_legacy_scaffold else CANONICAL_PACKAGE_DIRS
    for relative in package_dirs:
        (project / relative).mkdir(parents=True, exist_ok=True)
    routing_path = project / PATHS["workflow_route"]
    route: dict[str, Any] = {}
    if args.routing_file:
        routing_source = Path(args.routing_file).expanduser().resolve()
        if not routing_source.is_file():
            raise SystemExit(f"routing file does not exist: {routing_source}")
        try:
            route = json.loads(routing_source.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise SystemExit(f"routing file is invalid JSON: {error}") from error
        if not isinstance(route, dict) or route.get("status") != "approved":
            raise SystemExit("routing file must contain an approved route; run scripts/workflow_start.py route first")
        # A structurally approved route is not enough for a production copy
        # package.  Non-interactive routes intentionally carry
        # ``automation-ineligible`` and may be inspected, but they must not
        # bootstrap a package that looks ready enough for an editor to start
        # writing around the copy-strategy gate.  A route the user confirmed
        # off-terminal (``user-attested``) stays valid: its confirmation source
        # is recorded on ``user_confirmed_by``.
        if (
            route.get("selection_source") not in APPROVED_SELECTION_SOURCES
            or route.get("user_confirmed") is not True
            or route.get("approval_status") != "approved"
        ):
            raise SystemExit(
                "routing file requires fresh user-confirmed approval before package initialization; "
                "automation-ineligible routes are inspection-only"
            )
        if route.get("account") != args.account:
            raise SystemExit("routing file account does not match --account")
        if route.get("route_skill") != "content-copy-orchestrator":
            raise SystemExit("routing file must use the canonical content-copy-orchestrator route")
        if route.get("topic_mode") == "hotspot" and route.get("hotspot_source_adapter") != "scripts/hotspot_source.py":
            raise SystemExit("hotspot routing file must declare scripts/hotspot_source.py")
        route_content_id = str(route.get("content_id", "")).strip()
        if route_content_id and route_content_id != args.content_id:
            raise SystemExit("routing file content_id does not match --content-id")
        route_topic_id = str(route.get("topic_id", "")).strip()
        if args.topic_id and route_topic_id and args.topic_id != route_topic_id:
            raise SystemExit("--topic-id does not match routing file topic_id")
        route_content_type = str(route.get("content_type", "")).strip()
        if args.content_type and route_content_type and args.content_type != route_content_type:
            raise SystemExit("--content-type does not match routing file content_type")
        if route.get("selection_source") in APPROVED_SELECTION_SOURCES and not args.allow_stale_route:
            selected_at = str(route.get("selected_at", "")).strip()
            try:
                route_time = datetime.fromisoformat(selected_at.replace("Z", "+00:00"))
                age_seconds = (datetime.now(timezone.utc) - route_time).total_seconds()
            except ValueError:
                raise SystemExit("routing file selected_at is invalid; start a new route")
            if age_seconds > ROUTE_VALIDITY_HOURS * 60 * 60:
                raise SystemExit(
                    f"routing file is older than {ROUTE_VALIDITY_HOURS} hours; start a new route instead of reusing it"
                )
        write_json(routing_path, route)
    else:
        write_json(routing_path, {
            "schema_version": 1,
            "status": "pending",
            "content_id": args.content_id,
            "account": args.account,
            "message": "Run scripts/workflow_start.py route before brief approval.",
        })
    production = route.get("production") if isinstance(route.get("production"), dict) else {}
    topic_id = str(args.topic_id or route.get("topic_id", "") or args.content_id).strip()
    content_type = str(args.content_type or route.get("content_type", "")).strip()
    if args.account == ACCOUNT:
        # The account policy is fixed; package creation must not inherit a
        # legacy voiceover/synthetic selection from an expired route.
        production = {
            **production,
            "presenter_mode": "digital-human",
            "voice_mode": "voice-clone",
            "voice_provider": VOICE_PROVIDER,
            "tts_model": TTS_MODEL,
            "tts_policy": "local-only",
        }
    presenter_mode = str(production.get("presenter_mode", "")).strip()
    voice_mode = str(production.get("voice_mode", "")).strip()
    production_selected = presenter_mode in {"real-person", "digital-human", "voiceover-only"} and voice_mode in {"recorded", "voice-clone", "synthetic"}
    production_user_confirmed = route.get("selection_source") in APPROVED_SELECTION_SOURCES and route.get("user_confirmed") is True
    runtime_required = bool(args.use_runtime or presenter_mode == "digital-human" or voice_mode == "voice-clone" or args.account == ACCOUNT)
    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    manifest = {
        "content_id": args.content_id,
        "workspace_id": f"dy-{created_at.replace(':', '').replace('+00:00', 'z')}-{uuid.uuid4().hex[:12]}-{args.content_id}",
        "lifecycle": "active",
        "artifact_root_policy": "external-artifact-root" if enforce_artifact_root else "caller-selected-explicit-override",
        "production_naming_policy": PRODUCTION_NAMING_POLICY_ID,
        "account": args.account,
        "title": args.title,
        "status": "brief",
        "created_at": created_at,
        "deliverables": ["video"],
        "platforms": ["douyin"],
        "runtime_required": runtime_required,
        "workflow_contract": selected_contract,
        # Every normal production package uses the real-media execution
        # contract.  Historical/caller-selected fixtures keep their previous
        # semantics and are identified by the explicit override below.
        "execution_contract_version": CANONICAL_EXECUTION_VERSION if selected_contract == CANONICAL_CONTRACT_ID and not use_legacy_scaffold else 1,
        "strict_media_execution": selected_contract == CANONICAL_CONTRACT_ID and not use_legacy_scaffold,
        "media_execution_policy": {
            "fallback_policy": "none",
            "required_routes": ["digital_human", "bridge_image", "gemini_broll", "i2v", "editor", "renderer"],
            "h3_failure": "block",
            "provider_auth_failure": "block",
            "static_avatar": "block",
            "descriptor_only_render": "block",
        },
        "production": production if production_selected else {"status": "pending"},
        "route_id": str(route.get("route_id", "")) if route else "",
        "route_selection_source": str(route.get("selection_source", "")) if route else "",
        "digital_assets": (route.get("digital_assets", {}) if route else {"status": "pending", "local_only": True}),
        "publish_mode": args.mode,
        "workflow_v2_hardening": {
            "contract": "workflow-v2-hardening-v1",
            "enforce": True,
            "risk_tier": "HIGH" if content_type in {"github_project", "monetization_case", "comparison", "newsjacking"} else "MEDIUM",
        },
        "media_policy": {
            "path": "local-media-policy.json",
            "policy": media_policy.get("policy"),
            "sha256": media_policy_sha256,
        },
        "topic_id": topic_id,
        "scheduled_for": args.scheduled_for,
        "runtime_demo_policy": (route.get("runtime_demo_policy", {}) if isinstance(route, dict) else {}),
        "paths": dict(PATHS if use_legacy_scaffold else canonical_paths()),
        "workflow": canonical_new_workflow(selected_contract),
    }
    manifest["policy_lock"] = canonical_policy_lock(manifest["account"])
    write_json(manifest_path, manifest)
    if not use_legacy_scaffold:
        # Production initialization is canonical from the first write.  It
        # never creates historical 03_assets/04_video/05_publish trees and
        # therefore has nothing to prune or silently migrate.
        write_canonical_scaffold(
            project,
            args,
            manifest,
            content_type,
            topic=str(route.get("topic", "") or args.title),
            pillar=str(route.get("pillar", "")),
            route=route,
        )
        print(json.dumps({"project": str(project), "content_id": args.content_id, "account": args.account, "platform": "douyin"}, ensure_ascii=False))
        return 0
    copy_template("video/brief.md", project / PATHS["brief"])
    copy_template("video/video-script.md", project / PATHS["video_script"])
    if route.get("topic_mode") == "hotspot":
        snapshot = route.get("hotspot_snapshot")
        if not isinstance(snapshot, dict) or snapshot.get("passed") is not True or snapshot.get("freshness_verified") is not True:
            raise SystemExit("hotspot route requires a passed, freshness-verified hotspot snapshot")
        route["hotspot_snapshot_artifact"] = PATHS["hotspot_snapshot"]
        write_json(project / PATHS["hotspot_snapshot"], snapshot)
    else:
        write_json(project / PATHS["hotspot_snapshot"], {
            "schema_version": 1,
            "status": "not_applicable",
            "passed": False,
            "freshness_verified": False,
            "items": [],
        })
    # Human feasibility is a pre-Brief acceptance gate.  Package bootstrap
    # preserves the reviewed report/guide when supplied, but a missing or
    # pending forecast deliberately remains visible and blocks Brief approval.
    forecast_meta = route.get("operation_forecast") if isinstance(route.get("operation_forecast"), dict) else {}
    forecast_source = Path(str(forecast_meta.get("report", ""))).expanduser() if forecast_meta.get("report") else None
    guide_source = Path(str(forecast_meta.get("guide", ""))).expanduser() if forecast_meta.get("guide") else None
    if forecast_source and forecast_source.is_file():
        try:
            forecast = json.loads(forecast_source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise SystemExit(f"human operation forecast is invalid: {error}") from error
        if not isinstance(forecast, dict):
            raise SystemExit("human operation forecast must be a JSON object")
        write_json(project / PATHS["human_operation_forecast"], forecast)
    else:
        write_json(project / PATHS["human_operation_forecast"], {
            "schema_version": 1,
            "content_id": args.content_id,
            "account": args.account,
            "topic": str(route.get("topic", args.title)),
            "status": str(forecast_meta.get("status", "pending")),
            "risk_summary": {"level": "warn", "blocking_reasons": [], "warnings": ["Run human_operation_forecast.py draft before Brief approval."]},
            "operations": [],
            "human_acceptance": {"status": "pending", "reviewer": "", "accepted_at": "", "note": ""},
        })
    if guide_source and guide_source.is_file():
        (project / PATHS["human_operation_guide"]).write_text(guide_source.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        write_text(project / PATHS["human_operation_guide"], "# 人工操作可行性预判\n\n请先运行 `scripts/human_operation_forecast.py draft`，审核并接受报告后再进入 Brief。\n")
    # Persist the package-local handoff path so every downstream stage uses
    # the snapshot inside the content package rather than an external temp
    # report path.
    write_json(routing_path, route)
    topic_for_copy = str(route.get("topic", "") or args.title).strip()
    verified_hotspot = hotspot_eligible(route) if route.get("topic_mode") == "hotspot" else None
    classified_copy = adaptive_copy_plan(
        topic_for_copy,
        args.title,
        "local_test" if route.get("topic_mode") in {"hotspot", "user-document"} else "hypothesis",
        hot_topic=bool(verified_hotspot),
        forced_content_type=content_type,
        verified_hotspot=verified_hotspot if route.get("topic_mode") == "hotspot" else False,
    )
    if route.get("topic_mode") == "hotspot" and not verified_hotspot:
        # Keep an unverified hotspot visibly blocked rather than allowing
        # token-based classification to turn it into newsjacking copy.
        classified_copy["content_type"] = ""
        classified_copy["classification_source"] = "blocked-unverified-hotspot"
        classified_copy["hot_topic"] = False
        classified_copy["hot_topic_verified"] = False
    write_json(project / PATHS["content_strategy"], build_content_strategy(args.content_id, args.title))
    audience_insight = build_audience_scaffold(
        args.content_id,
        topic_for_copy,
        account=args.account,
        content_type=str(classified_copy.get("content_type", "")),
        pillar=str(classified_copy.get("pillar", "")),
    )
    audience_insight_path = project / PATHS["audience_insight"]
    write_json(audience_insight_path, audience_insight)
    audience_insight_sha256 = hashlib.sha256(audience_insight_path.read_bytes()).hexdigest()
    classified_copy["audience_lens"] = lens_projection(
        audience_insight,
        source_path=PATHS["audience_insight"],
        source_sha256=audience_insight_sha256,
    )
    classified_copy["value_contract"] = audience_insight["value_contract"]
    classified_copy["emotional_arc"] = audience_insight["emotional_arc"]
    write_json(project / PATHS["copy_brief"], {
        # Topic-level audience research is mandatory before a copy brief can
        # become ready.
        "schema_version": 3,
        "content_id": args.content_id,
        "account": args.account,
        "status": "pending",
        "title": args.title,
        "topic": topic_for_copy,
        "content_type": classified_copy.get("content_type", ""),
        "evidence_level": classified_copy.get("evidence_level", ""),
        "classification_source": classified_copy.get("classification_source", ""),
        "classification_reason": classified_copy.get("classification_reason", ""),
        "hot_topic": bool(classified_copy.get("hot_topic", False)),
        "hot_topic_verified": bool(classified_copy.get("hot_topic_verified", False)),
        "pillar": classified_copy.get("pillar", ""),
        "viewer_job": classified_copy.get("viewer_job", ""),
        "audience": classified_copy.get("audience", ""),
        "audience_lens": classified_copy.get("audience_lens", {}),
        "value_contract": classified_copy.get("value_contract", {}),
        "emotional_arc": classified_copy.get("emotional_arc", {}),
        "viewer_intent": classified_copy.get("viewer_intent", ""),
        "pillar_selection": classified_copy.get("pillar_selection", {}),
        "copy_direction_route": classified_copy.get("copy_direction_route", ""),
        "copy_direction_module": classified_copy.get("copy_direction_module", ""),
        "copy_direction": classified_copy.get("copy_direction", {}),
        "why_now": classified_copy.get("why_now", ""),
        "ai_relevance": classified_copy.get("ai_relevance", ""),
        "viewer_problem": classified_copy.get("viewer_problem", ""),
        "evidence_floor": classified_copy.get("evidence_floor", ""),
        "hotspot_contract": classified_copy.get("hotspot_contract", {}),
        "hook_type": classified_copy.get("hook_type", "结果先看"),
        "narrative_tension": classified_copy.get("narrative_tension", ""),
        "voice_contract": classified_copy.get("voice_contract", {}),
        "cta": classified_copy.get("cta", ""),
        "cta_mode": classified_copy.get("cta_mode", ""),
        "structure": classified_copy.get("structure", ""),
        "argument_structure": classified_copy.get("argument_structure", ""),
        "viewer_progress_structure": classified_copy.get("viewer_progress_structure", ""),
        "structure_role": classified_copy.get("structure_role", "beat_preset"),
        "structure_reason": classified_copy.get("structure_reason", ""),
        "packaging_contract": classified_copy.get("packaging_contract", {
            "structure": "hook-body-close",
            "hook_max_seconds": 6,
            "title_intro_match_required": True,
            "body_must_deliver_promise": True,
            "cta_count": 1,
            "evidence_policy_id": "douyin-copy-evidence-v1",
        }),
        "duration_tier": classified_copy.get("duration_tier", ""),
        "duration_label": classified_copy.get("duration_label", ""),
        "target_seconds": classified_copy.get("target_seconds"),
        "duration_range": classified_copy.get("duration_range", []),
        "duration_selection_reason": classified_copy.get("duration_selection_reason", ""),
        "ai_disclosure": classified_copy.get("ai_disclosure", {"required": True, "status": "pending", "location": "发布描述或画面显式标识"}),
        "claims": [],
        "voiceover": "",
        "strategy_ref": {
            "path": PATHS["copy_strategy"],
            "selected_angle_id": "",
            "selected_hook_id": "",
            "status": "pending",
        },
    })
    write_json(
        project / PATHS["copy_strategy"],
        build_seed(
            manifest,
            route,
            classified_copy,
            audience_insight=audience_insight,
            audience_insight_sha256=audience_insight_sha256,
        ),
    )
    copy_template("video/teaching-contract.json", project / PATHS["teaching_contract"])
    # Carry the audience and practical/emotional intent into the teaching
    # scaffold immediately.  Keep the contract pending: the editor still has
    # to supply the concrete example, claims and evidence before approval.
    teaching_contract_path = project / PATHS["teaching_contract"]
    teaching_contract = json.loads(teaching_contract_path.read_text(encoding="utf-8"))
    teaching_contract.update({
        "content_id": args.content_id,
        "learning_objective": classified_copy.get("viewer_intent", ""),
        "audience_starting_point": classified_copy.get("audience", ""),
        "audience_lens": classified_copy.get("audience_lens", {}),
        "value_contract": classified_copy.get("value_contract", {}),
    })
    write_json(teaching_contract_path, teaching_contract)
    copy_template("video/storyboard.csv", project / PATHS["storyboard"])
    copy_template("video/director-material-plan.json", project / PATHS["director_plan"])
    copy_template("video/director-material-plan.md", project / PATHS["director_plan_review"])
    write_json(project / PATHS["human_operation_plan"], {
        "schema_version": 1,
        "content_id": args.content_id,
        "account": args.account,
        "status": "pending",
        "source_broll_plan": PATHS["broll_plan"],
        "operations": [],
        "screen_recording": {"required": False, "beats": []},
        "human_acceptance": {"status": "pending", "reviewer": "", "accepted_at": "", "note": ""},
        "errors": ["Run scripts/human_operation_manual.py after the final audio and material plan are ready."],
    })
    write_text(project / PATHS["human_operation_manual"], "# 人工素材操作手册\n\n音频锁定并生成素材计划后，运行 `scripts/human_operation_manual.py`。\n")
    copy_template("assets/asset-ledger.csv", project / PATHS["asset_ledger"])
    write_json(project / PATHS["asset_index"], {"schema_version": 1, "content_id": args.content_id, "status": "pending", "records": [], "orphan_files": [], "errors": []})
    write_json(project / PATHS["media_validation"], {
        "schema_version": 1,
        "content_id": args.content_id,
        "status": "not-required",
        "passed": True,
        "checked_at": "",
        "records": [],
        "errors": [],
        "notes": "Promoted media changes this to required; run scripts/material_media_validator.py before final assets clearance.",
    })
    write_json(project / PATHS["material_canary"], {
        "schema_version": 1,
        "content_id": args.content_id,
        "status": "not-generated",
        "technical_passed": False,
        "human_decision": {"status": "pending", "reviewer": "", "decided_at": "", "note": ""},
        "representatives": [],
        "errors": ["Run scripts/material_canary.py after the B-roll plan is ready."],
    })
    write_json(project / PATHS["material_visual_lock"], {
        "schema_version": 1,
        "content_id": args.content_id,
        "status": "not-generated",
        "gate": "pending",
        "representative_beats": [],
        "errors": ["Run scripts/material_canary.py after the B-roll plan is ready."],
    })
    write_json(project / PATHS["runtime_plan"], {
        "schema_version": 1,
        "content_id": args.content_id,
        "status": "not-generated",
        "integration_mode": "dy1024-runtime-adapter",
        "production_profile_identity": "",
        "units": [],
        "errors": ["Run scripts/erduo_runtime_adapter.py after the B-roll plan is ready."],
    })
    write_json(project / PATHS["human_operation_receipt"], {
        "schema_version": 1,
        "content_id": args.content_id,
        "account": args.account,
        "status": "pending",
        "files": [],
        "notes": "After the user returns the required recordings, register them with scripts/human_operation_receipt.py.",
    })
    write_json(project / PATHS["source_candidates"], {
        "schema_version": 1,
        "content_id": args.content_id,
        "generated_at": "",
        "mode": "plan-only",
        "source": "none",
        "query": "",
        "candidates": [],
        "notes": ["Run scripts/material_candidates.py after the script and director plan are ready; no media is downloaded here."],
    })
    write_json(project / PATHS["claims"], {"schema_version": 1, "contract": selected_contract, "content_id": args.content_id, "status": "pending", "claims": []})
    write_json(project / PATHS["claims_map"], {"schema_version": 1, "content_id": args.content_id, "account": args.account, "status": "pending", "passed": False, "records": [], "errors": ["Run evidence-ingest during component execution."]})
    write_json(
        project / PATHS["sources"],
        {
            "schema_version": 1,
            "contract": selected_contract,
            "content_id": args.content_id,
            "sources": [],
            "screenshot_manifest": PATHS["source_screenshots"],
            "screenshot_policy": {
                "required": False,
                "visual_qc_required": False,
                "material_capture": {
                    "enabled": False,
                    "scope": "bound-or-all-declared",
                    "trigger_routes": ["product-ui"],
                    "automation_owner": "material-source-research",
                    "human_owner": "user",
                },
            },
        },
    )
    write_json(project / PATHS["sources_input"], {
        "content_id": args.content_id,
        "sources": [],
        "screenshot_policy": {"required": False, "require_focused": False, "visual_qc_required": False, "material_capture": {"enabled": False, "scope": "bound-or-all-declared", "trigger_routes": ["product-ui"], "automation_owner": "material-source-research", "human_owner": "user"}, "visual_qc": {"required": False, "min_vertical_coverage_ratio": 0.18, "context_min_vertical_coverage_ratio": 0.10, "safe_top_css": 180, "safe_bottom_css": 64}, "method": "playwright.chromium.page.screenshot", "note": "按当前主题 sources-input 显式启用 material_capture 后，素材计划才会生成自动截图请求；再运行视觉 QC 门。"},
        "instructions": "Populate sources with declared public URLs, then run scripts/capture_source_urls.py, adapters/research/source_snapshot.py, scripts/capture_source_screenshots.py, and scripts/source_screenshot_visual_qc.py; snapshot_file is required for Research approval and screenshot_file/visual-qc.json are required when screenshot_policy.required=true and visual_qc_required=true.",
    })
    write_json(project / PATHS["topic_contract"], {
        "schema_version": 1,
        "content_id": args.content_id,
        "account": args.account,
        "status": "pending",
        "canonical_topic": "",
        "in_scope": [],
        "out_scope": [],
        "drift_threshold": 0.2,
        "topic_sha256": "",
        "approved_by": "",
        "approved_at": "",
    })
    write_json(project / PATHS["evidence_plan"], {"schema_version": 1, "content_id": args.content_id, "status": "pending", "topic_sha256": "", "claims": [], "source_ids": []})
    write_json(project / PATHS["evidence_provenance"], {"schema_version": 1, "content_id": args.content_id, "status": "pending", "pack_sha256": "", "records": []})
    write_json(project / PATHS["evidence_lineage"], {"schema_version": 1, "content_id": args.content_id, "status": "pending", "topic_sha256": "", "pack_sha256": "", "links": []})
    write_json(project / PATHS["asset_inventory"], {
        "schema_version": 1,
        "content_id": args.content_id,
        "source_root": "",
        "status": "pending",
        "total_files": 0,
        "records": [],
        "errors": ["Run the source asset inventory before assets/video production approval."],
    })
    write_json(project / PATHS["trend_score"], {"schema_version": 1, "content_id": args.content_id, "status": "pending", "items": []})
    write_json(project / PATHS["source_snapshots"], {"schema_version": 1, "content_id": args.content_id, "passed": False, "records": []})
    write_json(project / PATHS["source_screenshots"], {"schema_version": 1, "content_id": args.content_id, "status": "pending", "passed": False, "records": [], "errors": ["Run scripts/capture_source_screenshots.py when rendered page evidence is required."]})
    write_json(project / PATHS["source_screenshot_visual_qc"], {"schema_version": 1, "content_id": args.content_id, "status": "pending", "passed": False, "human_review_required": True, "errors": ["Run scripts/source_screenshot_visual_qc.py after focused screenshots are captured."]})
    execution_plan = canonical_execution_plan(args.content_id, args.title, args.account)
    # Keep only non-authoritative runtime hints needed by existing adapters;
    # stage identity and ordering come exclusively from the canonical plan.
    execution_plan["video"] = {
        "runtime_required": runtime_required,
        "runtime_routes": ["runtime-media", "script-to-tts", "clean-talking-video", "remotion-captions"],
        "script_routes": ["content-copy-orchestrator"],
        "presenter_mode": "digital-human",
        "voice_mode": "voice-clone",
        "recording_policy": "claim-driven; no global ratio",
    }
    if route and route.get("topic_mode") in {"user-topic", "user-document"}:
        execution_plan["research_scope"] = "topic-local"
    if route:
        execution_plan["topic_route"] = {
            "route_id": route.get("route_id", ""),
            "topic_mode": route.get("topic_mode", ""),
            "topic": route.get("topic", ""),
            "topic_id": route.get("topic_id", ""),
            "experiment_id": route.get("experiment_id", ""),
            "route_skill": route.get("route_skill", "content-copy-orchestrator"),
            "research_route": "agent-reach" if route.get("topic_mode") == "hotspot" else "",
            "hotspot_source_adapter": route.get("hotspot_source_adapter", "") if route.get("topic_mode") == "hotspot" else "",
            "hotspot_snapshot_artifact": route.get("hotspot_snapshot_artifact", "") if route.get("topic_mode") == "hotspot" else "",
        }
    write_json(project / PATHS["execution_plan"], execution_plan)
    production_profile = {
        "schema_version": 1,
        "content_id": args.content_id,
        "status": "approved" if production_selected and production_user_confirmed else "pending",
        "selected_source": route.get("selection_source", "") or production.get("selection_source", ""),
        "presenter_mode": presenter_mode,
        "voice_mode": voice_mode,
        "voice_provider": production.get("voice_provider", VOICE_PROVIDER),
        "tts_model": production.get("tts_model", TTS_MODEL),
        "tts_profile_id": PROFILE_ID,
        "tts_reference_id": REFERENCE_ID,
        "tts_policy": production.get("tts_policy", "local-only"),
        "presenter_source": production.get("presenter_source", ""),
        "presenter_source_kind": production.get("presenter_source_kind", ""),
        "voice_reference": production.get("voice_reference", ""),
        "voice_emotion_reference": production.get("voice_emotion_reference", production.get("emotion_reference", "")),
        "avatar_prompt_config": str(ROOT / "configs" / "digital-human-scene-prompts.json"),
        "avatar_driving_audio_policy": "per-scene-final-narration-required",
        "avatar_window_policy": "enum-only; default-none; no-free-text-show",
        "avatar_scene_contract": {
            "allowed_windows": ["none", "hook", "transition", "verdict", "cta", "caution", "explainer"],
            "allowed_render_modes": ["none", "pip", "cutin"],
            "default_render_mode": "none",
            "duration_source": "final_narration",
            "max_scene_seconds": 14.9,
            "voice_reference_role": "authorized reference for voice-clone or digital-human synthetic routes only",
            "driving_audio_role": "final IndexTTS narration locked into H3 audio latent and delivered as the same target track",
        },
        "permissions": production.get("permissions", {}),
        "runtime_required": runtime_required,
        "digital_assets": route.get("digital_assets", {}) if route else {"status": "pending", "local_only": True},
    }
    production_profile["identity"] = canonical_identity(production_profile)
    write_json(project / PATHS["production_profile"], production_profile)
    write_json(project / PATHS["motion_plan"], {
        "schema_version": 1,
        "content_id": args.content_id,
        "account": args.account,
        "platform": "douyin",
        "status": "pending",
        "policy": {
            "enabled": True,
            "primary_component": "remotion-final-compositor",
            "overlay_component": "hyperframes-transparent-overlay",
            "require_provenance": True,
            "composition_mode": "canonical-master-timeline",
            "supported_composition_modes": ["canonical-master-timeline"],
            "overlay_alpha_required": False,
            "overlay_alpha_probe": "not-applicable-to-owner-route",
            "overlay_z_index": 0,
            "scene_crossfade": "master-timeline-owned",
        },
        "components": {
            "hyperframes": {"status": "pending", "role": "transparent information overlay", "output": "06_motion/hyperframes-native/index.html"},
            "remotion": {"status": "pending", "role": "final compositor and encoder", "output": "06_motion/remotion-native/src/Root.tsx"},
        },
        "failure_policy": "blocked-and-rerun-same-route",
        "routes": [],
        "notes": "Run scripts/motion_pipeline.py prepare after storyboard, director plan and visual route are ready.",
    })
    write_json(project / PATHS["motion_check"], {
        "schema_version": 1,
        "content_id": args.content_id,
        "account": args.account,
        "status": "pending",
        "passed": False,
        "errors": ["Run scripts/motion_pipeline.py prepare after visual routing."],
        "warnings": [],
    })
    write_json(project / PATHS["motion_provenance"], {
        "schema_version": 1,
        "content_id": args.content_id,
        "account": args.account,
        "status": "pending",
        "passed": False,
        "external_cli_invoked": False,
        "failure_policy": "blocked-and-rerun-same-route",
        "components": {},
    })
    write_json(project / PATHS["motion_render_report"], {
        "schema_version": 1,
        "content_id": args.content_id,
        "account": args.account,
        "status": "not_run",
        "passed": False,
        "external_cli_invoked": False,
        "errors": ["Run the canonical edit/render route and record its render receipt before Quality."],
        "warnings": [],
    })
    write_json(project / PATHS["motion_adversarial_audit"], {
        "schema_version": 1,
        "content_id": args.content_id,
        "account": args.account,
        "status": "not_run",
        "passed": False,
        "strict": False,
        "checks": [],
        "errors": ["Run scripts/motion_pipeline.py prepare, then render, then the strict motion adversarial audit."],
        "warnings": [],
    })
    write_json(project / PATHS["hyperframes_plan"], {
        "schema_version": 1,
        "content_id": args.content_id,
        "account": args.account,
        "status": "pending",
        "composition": "06_motion/hyperframes-native/index.html",
        "failure_policy": "blocked-and-rerun-same-route",
    })
    write_json(project / PATHS["remotion_plan"], {
        "schema_version": 1,
        "content_id": args.content_id,
        "account": args.account,
        "status": "pending",
        "composition_id": "SentinelVideo",
        "project": "06_motion/remotion-native",
        "failure_policy": "blocked-and-rerun-same-route",
    })
    write_json(project / PATHS["plugin_scene_brief"], {
        "schema_version": 1,
        "content_id": args.content_id,
        "account": args.account,
        "status": "pending",
        "authoring_engine": "canonical-master-timeline",
        "scenes": [],
    })
    write_json(project / PATHS["visual_profile"], {
        "schema_version": 1,
        "content_id": args.content_id,
        "account": args.account,
        "status": "pending",
        "source_design_direction": "04_video/design-direction.json",
        "family": "",
        "palette": {},
        "typography": {},
        "motion_language": {},
    })
    write_json(project / PATHS["plugin_render_manifest"], {
        "schema_version": 1,
        "content_id": args.content_id,
        "account": args.account,
        "status": "not_run",
        "route": "canonical-master-timeline",
        "scenes": [],
        "components": {},
    })
    write_json(project / PATHS["plugin_native_qc"], {
        "schema_version": 1,
        "content_id": args.content_id,
        "account": args.account,
        "status": "pending",
        "passed": False,
        "errors": ["Run scripts/plugin_native_motion.py plan before plugin-native authoring."],
        "warnings": [],
    })
    write_json(project / PATHS["plugin_native_concurrency_qc"], {
        "schema_version": 1,
        "content_id": args.content_id,
        "account": args.account,
        "status": "pending",
        "passed": False,
        "workers": 0,
        "run_ids": [],
        "run_roots": [],
        "artifact_paths": [],
        "errors": ["Run scripts/plugin_native_concurrency_test.py after native authoring."],
    })
    write_json(project / PATHS["plugin_native_visual_qc"], {
        "schema_version": 1,
        "content_id": args.content_id,
        "account": args.account,
        "status": "pending",
        "passed": False,
        "engine": "rapidocr_onnxruntime",
        "human_approval_required": True,
        "errors": ["Run scripts/plugin_native_visual_qc.py after native render."],
    })
    asset_root = Path(str(route.get("digital_assets", {}).get("asset_root", ""))).expanduser() if isinstance(route.get("digital_assets"), dict) and route.get("digital_assets", {}).get("asset_root") else None
    if asset_root and asset_root.is_dir():
        digital_report = scan(
            asset_root,
            content_id=args.content_id,
            account=args.account,
            required_kinds=required_asset_kinds(voice_mode=voice_mode, presenter_mode=presenter_mode),
        )
    else:
        required_kinds = required_asset_kinds(voice_mode=voice_mode, presenter_mode=presenter_mode)
        digital_report = {
            "schema_version": 1,
            "content_id": args.content_id,
            "account": args.account,
            "status": "not_required" if not runtime_required else "pending",
            "asset_root_env": ASSET_ROOT_ENV,
            "local_only": True,
            "do_not_commit_media": True,
            "required_kinds": sorted(required_kinds),
            "assets": [],
            "errors": [] if not runtime_required else ["Run workflow_start route to select local voice/avatar references."],
            "warnings": [],
        }
    write_json(project / PATHS["digital_assets"], digital_report)
    write_json(project / PATHS["design_history"], {"schema_version": 1, "content_id": args.content_id, "history": []})
    write_json(project / PATHS["design_direction"], build_direction(args.account, args.content_id, args.title, history=[]))
    write_text(project / PATHS["design_review"], "# 视觉方向审查\n\n请确认版式、令牌、素材混合比例和反审美疲劳规则。\n")
    permissions = production.get("permissions", {}) if isinstance(production.get("permissions"), dict) else {}
    h3 = configured_minimax_h3() if presenter_mode == "digital-human" else {}
    funasr = configured_funasr()
    if presenter_mode == "digital-human":
        # The approved route owns the selected presenter reference.  Do not
        # silently fall back to an old machine-local image when the route chose
        # one of the controlled assert/Fig*.png assets.
        selected_image = str(production.get("presenter_source") or h3.get("source_image") or "").strip()
        selected_audio = str(production.get("voice_reference") or h3.get("reference_audio") or "").strip()
        if selected_image:
            h3["source_image"] = selected_image
        if selected_audio:
            h3["reference_audio"] = selected_audio
    # Do not infer voice cloning while the route is still pending. An empty
    # mode is deliberately non-requiring; only an explicit voice-clone route
    # may require a reference asset.
    effective_voice_mode = voice_mode
    write_json(project / PATHS["video"], {
        "content_id": args.content_id,
        "runtime_required": runtime_required,
        "production": production,
        "permissions": permissions,
        "voice": {
            "provider": production.get("voice_provider", VOICE_PROVIDER),
            "model": production.get("tts_model", TTS_MODEL),
            "reference": production.get("voice_reference") or None,
            "profile_id": PROFILE_ID,
            "reference_id": REFERENCE_ID,
            "emotion_reference": production.get("voice_emotion_reference", production.get("emotion_reference")) or None,
            "output": "04_audio/narration.wav",
            "language": "ZH",
            "mode": effective_voice_mode,
            "reference_required": voice_reference_required(effective_voice_mode, presenter_mode),
            "policy_version": POLICY_VERSION,
            "generation_parameters": dict(T0_GENERATION),
            "segment_max_chars": 60,
            "segment_max_audio_seconds": 14.9,
            "segment_duration_comparison": "strictly-less-than",
            "segment_overlong_action": "split-approved-text-and-rerender",
            "max_text_tokens_per_segment": int(T0_GENERATION["max_text_tokens_per_segment"]),
            "speaker_similarity_min": SPEAKER_SIMILARITY_MIN,
            "segment_speaker_similarity_min": 0.70,
        },
        "avatar": {
            "enabled": presenter_mode == "digital-human",
            "engine": "minimax_h3_ref2va" if presenter_mode == "digital-human" else "",
            "source_video": None,
            "source_image": h3.get("source_image") or None,
            "source_image_asset_id": h3.get("source_image_asset_id", "avatar-reference"),
            "reference_audio": h3.get("reference_audio") or None,
            "reference_audio_asset_id": h3.get("reference_audio_asset_id", "voice-reference"),
            "output": "05_avatar/avatar.mp4",
            "model_version": "h3-e4",
            "h3_root": h3.get("root") or None,
            "h3_python": h3.get("python") or None,
            "comfy_url": h3.get("comfy_url", "http://127.0.0.1:8190"),
            "width": int(h3.get("width", 768)),
            "height": int(h3.get("height", 1024)),
            "steps": int(h3.get("steps", 20)),
            "acceleration": h3.get("acceleration", "e4"),
            "sampler": h3.get("sampler", "res_multistep"),
            "motion_profile": h3.get("motion_profile", "douyin_micro_gesture"),
            "seed": int(h3.get("seed", 20260814)),
            "voice_policy": POLICY_VERSION,
            "duration_source": "final_narration",
            "max_scene_seconds": 14.9,
            "duration_comparison": "strictly-less-than",
            "duration_policy": {
                "min_scene_seconds": 4.0,
                "max_scene_seconds": 14.9,
                "comparison": "strictly-less-than",
                "overlong_action": "split-approved-text-at-scene-boundary-and-rerun-h3",
            },
            "brightness_filter": h3.get("brightness_filter", "eq=brightness=0.025:contrast=1.02:gamma=1.08:saturation=1.03"),
        },
        "runtime": {
            "funasr_root": funasr.get("root") or None,
            "asr_python": funasr.get("python") or None,
            "funasr_model": funasr.get("model", "paraformer-zh"),
            "funasr_cache": funasr.get("cache") or None,
            "minimax_h3_root": h3.get("root") or None,
            "minimax_h3_python": h3.get("python") or None,
            "minimax_h3_comfy_url": h3.get("comfy_url", "http://127.0.0.1:8190") if presenter_mode == "digital-human" else None,
        },
        "project_path": "", "preview_path": "", "captions_path": "", "editable_project_path": "", "qc_report_path": "", "scenes": [], "approvals": {},
    })
    write_json(project / PATHS["model_runtime"], {"schema_version": 1, "content_id": args.content_id, "status": "not_required" if not runtime_required else "pending", "passed": not runtime_required, "checked_at": "", "mode": "", "model_root": "", "video_project": "", "components": {}, "permissions": permissions, "errors": [] if not runtime_required else ["Run model preflight because production mode requires local media runtime."], "warnings": []})
    director_plan = json.loads((project / PATHS["director_plan"]).read_text(encoding="utf-8"))
    director_plan.update({"content_id": args.content_id, "account": args.account, "platform": "douyin"})
    write_json(project / PATHS["director_plan"], director_plan)
    write_json(project / PATHS["distribution"], {"content_id": args.content_id, "account": args.account, "platforms": ["douyin"], "title": args.title, "digest": "", "cover": "", "hashtags": [], "comment_prompts": [], "publish_method": "draft", "scheduled_for": args.scheduled_for})
    topic_items = []
    if args.topic_id:
        topic_items.append({"topic_id": args.topic_id, "content_id": args.content_id, "title": args.title, "account": args.account, "pillar": "", "format": "short-video", "priority": 3, "status": "queued" if args.scheduled_for else "idea", "evidence_floor": 2, "scheduled_for": args.scheduled_for, "experiment": "", "notes": ""})
    write_json(project / PATHS["topic_backlog"], {"schema_version": 1, "content_id": args.content_id, "account": args.account, "status": "active", "items": topic_items, "next_review": ""})
    write_json(project / PATHS["variants"], {"schema_version": 1, "content_id": args.content_id, "account": args.account, "status": "pending", "platforms": {"douyin": []}})
    write_json(project / PATHS["quality"], {"content_id": args.content_id, "caption_safe": False, "rights_checked": False, "sync_checked": False, "audio_checked": False, "visual_checked": False, "reviewer": "", "reviewed_at": ""})
    write_json(project / PATHS["subtitle_qc"], {"schema_version": 1, "content_id": args.content_id, "status": "pending", "passed": False, "errors": [], "warnings": []})
    write_json(project / PATHS["script_compile"], {"schema_version": 1, "content_id": args.content_id, "status": "pending"})
    write_json(project / PATHS["audio_handoff"], {
        "schema_version": 1,
        "content_id": args.content_id,
        "account": args.account,
        "status": "pending",
        "audio_owner": "workflow-final-narration",
        "source_script": PATHS["video_script"],
        "script_sha256": "",
        "narration": "",
        "narration_metadata": "",
        "captions": "",
        "asr_verification": "",
        "audio_sha256": "",
        "duration_seconds": 0.0,
        "bindings": {
            "digital_human": {"required": presenter_mode == "digital-human", "audio": "same-as-narration"},
            "illustration": {"required": True, "audio": "timing-and-caption-only"},
            "cs_board": {"required": True, "audio": "timing-and-caption-only"},
            "hyperframes": {"required": True, "audio": "timing-only"},
            "remotion": {"required": True, "audio": "same-as-narration"},
            "final_delivery": {"required": True, "audio": "same-as-narration"},
        },
        "errors": ["Run scripts/audio_handoff.py after IndexTTS2.5 + FunASR."],
        "warnings": [],
    })
    write_json(project / PATHS["component_execution"], {"schema_version": 1, "content_id": args.content_id, "route": "content-copy-orchestrator", "status": "pending", "passed": False, "required_components": [], "optional_components": [], "records": [], "errors": ["Run scripts/component_execution.py record --confirm after applying all copy components."], "warnings": []})
    write_json(project / PATHS["design_lint"], {"schema_version": 1, "content_id": args.content_id, "passed": False, "errors": ["Run design lint before design approval."], "warnings": []})
    write_json(project / PATHS["skill_catalog"], {"schema_version": 1, "content_id": args.content_id, "passed": False, "missing_core": [], "records": []})
    write_json(project / PATHS["workflow_audit"], {"schema_version": 1, "content_id": args.content_id, "passed": False, "stages": []})
    write_json(project / PATHS["publish_plan"], {"schema_version": 1, "content_id": args.content_id, "platform": "douyin", "method": "manual-or-official", "status": "pending"})
    write_json(project / PATHS["scene_analysis"], {"schema_version": 1, "content_id": args.content_id, "status": "not_required", "passed": True, "scenes": []})
    write_json(project / PATHS["reframe_plan"], {"schema_version": 1, "content_id": args.content_id, "status": "not_required", "passed": True, "target": "9:16"})
    write_json(project / PATHS["runtime_demo_evidence"], {"schema_version": 1, "content_id": args.content_id, "status": "pending", "passed": False, "screen_recording_ratio": 0.0, "evidence_paths": [], "notes": "Provide a real product/app screen recording when the account route requires it."})
    write_json(project / PATHS["visual_review"], {"schema_version": 1, "content_id": args.content_id, "status": "pending", "passed": False, "reviewer_role": "", "reviewer": "", "reviewed_at": "", "contact_sheet": "", "reviewed_artifacts": [], "artifact_sha256": {}, "mobile_review": {"viewport_width": 390, "safe_area_passed": False, "subtitle_readable": False, "cta_readable": False}, "notes": "Human visual review is required after rendering; sign the current MP4, Remotion still and contact sheet with artifact_sha256."})
    write_json(project / PATHS["visual_qc"], {"schema_version": 1, "content_id": args.content_id, "status": "pending", "passed": False, "metrics": {}, "errors": [], "warnings": []})
    write_json(project / PATHS["creative_qc"], {"schema_version": 1, "content_id": args.content_id, "status": "pending", "passed": False, "metrics": {}, "errors": ["Run scripts/creative_qc.py before quality approval."], "warnings": []})
    write_json(project / PATHS["teaching_qc"], {"schema_version": 1, "content_id": args.content_id, "status": "pending", "passed": False, "required": True, "metrics": {}, "errors": ["Run scripts/creative_qc.py or scripts/teaching_qc.py before quality approval."], "warnings": []})
    write_json(project / PATHS["naturalness_qc"], {"schema_version": 1, "content_id": args.content_id, "status": "pending", "passed": False, "required": False, "metrics": {}, "errors": ["Run scripts/naturalness_qc.py after the controlled-colloquial copy pass."], "warnings": []})
    write_json(project / PATHS["video_planning_audit"], {"schema_version": 1, "content_id": args.content_id, "status": "pending", "passed": False, "checks": [], "blocked_count": 0})
    write_json(project / PATHS["best_practice_qc"], {
        "schema_version": 1,
        "content_id": args.content_id,
        "account": args.account,
        "status": "pending",
        "passed": False,
        "enforced": False,
        "errors": ["Run scripts/best_practice_qc.py after final audio, ASR captions, motion render and asset inventory."],
        "warnings": [],
    })
    image_enabled = image_policy_enabled(args.account)
    write_json(project / PATHS["image_prompt_plan"], {
        "schema_version": 1,
        "content_id": args.content_id,
        "account": args.account,
        "status": "pending" if image_enabled else "not_required",
        "image_required": False,
        # The provider is route-dependent and cannot be known at bootstrap.
        # Keep this empty until visual_route/image_prompt_plan selects it.
        "engine": "",
        "routes": [],
        "skill_routes": ["ian-xiaohei-illustrations", "ian-xiaohei-scenes"],
        "items": [],
        "text_policy": "per-item; inspect each image item's text_policy",
        "notes": "Run scripts/image_prompt_plan.py after the director plan. All Xiaohei, concept and generated still routes use ChatGPT Bridge in a standard Codex browser session, portrait 9:16 and text-free. Check pageAssets before submission; if the Bridge or export capability is unavailable, keep the scene-bound prompt planned and block production. Never silently downgrade to another provider. Add titles, labels, code, numbers, brands and captions in postproduction.",
    })
    write_json(project / PATHS["image_generation_provenance"], {
        "schema_version": 1,
        "content_id": args.content_id,
        "account": args.account,
        "status": "not_required",
        "passed": True,
        # Provenance is not ready at bootstrap; the generator adapter records
        # the actual route/provider after an approved asset is produced.
        "engine": "",
        "records": [],
        "errors": [],
        "warnings": [],
    })
    write_json(project / PATHS["image_qc"], {"schema_version": 1, "content_id": args.content_id, "status": "not_required", "passed": True, "metrics": {}, "errors": [], "warnings": []})
    write_json(project / PATHS["visual_route"], {
        "schema_version": 1,
        "rule_version": "visual-route-1.0",
        "content_id": args.content_id,
        "account": args.account,
        "platform": "douyin",
        "status": "pending",
        "routes": [],
        "route_ids": [],
        "generation_required": False,
        "generation_routes": [],
        "notes": "Run scripts/audio_handoff.py after review and the audio gate; then run scripts/visual_route.py after the approved script and director material plan. No visual media may be generated before assets approval.",
    })
    write_text(project / PATHS["visual_route_review"], "# 视觉路由审查\n\n请先运行 scripts/visual_route.py，再审核每个场景的表现形式、格式、技能路由和失败重跑策略。\n")
    write_json(project / PATHS["broll_plan"], {
        "schema_version": 1,
        "material_contract_version": 1,
        "content_id": args.content_id,
        "account": args.account,
        "platform": "douyin",
        "status": "pending",
        "mode": "plan-only",
        "generated_at": "",
        "candidate_manifest": PATHS["source_candidates"],
        "candidate_count": 0,
        "screen_recording_requirement": {
            "mode": "claim-driven",
            "status": "pending",
            "human_owner": "user",
            "coverage_requirement": 1.0,
        },
        "input_fingerprints": {},
        "beats": [],
        "approval": None,
        "errors": ["Run skills/broll-production/scripts/broll_plan.py after the director material plan is ready."],
        "notes": "No B-roll may be acquired before the assets_plan material-plan Gate is approved; final files still require the assets clearance Gate.",
    })
    write_text(project / PATHS["broll_plan_review"], "# B-roll 计划\n\n请运行 skills/broll-production/scripts/broll_plan.py，先审核镜头、来源策略、自动/人工责任、命名与失败重跑策略，并在 assets_plan Gate 通过后再执行素材获取。\n")
    write_text(project / PATHS["asset_requests"], "# B-roll 素材请求\n\n先生成并审批素材计划（assets_plan）；完成候选获取、权利确认、命名与技术/画面检查后，才可通过最终 assets Gate。\n")
    write_json(project / PATHS["openchatcut_consumption_plan"], {
        "schema_version": 1,
        "contract_version": "openchatcut-consumption-1.0",
        "content_id": args.content_id,
        "account": args.account,
        "status": "pending",
        "beats": [],
        "audio_policy": {"owner": "workflow-final-narration", "rule": "OpenChatCut edits visuals and timing only; it must not add a second narration or regenerate captions."},
        "notes": ["Run scripts/openchatcut_consumption_plan.py build after the OpenChatCut asset intake manifest exists."]
    })
    write_text(project / PATHS["openchatcut_best_practice_plan"], "# OpenChatCut 最佳实践初步规划\n\n请在 assets_plan 通过后，结合 `openchatcut-consumption-plan.json` 审核文案、音频、素材和人工复核边界。\n")
    write_json(project / PATHS["broll_manifest"], {
        "schema_version": 1,
        "content_id": args.content_id,
        "account": args.account,
        "status": "not_started",
        "assets": [],
        "notes": "Populated only after assets approval and real acquisition.",
    })
    write_json(project / PATHS["broll_qc"], {
        "schema_version": 1,
        "content_id": args.content_id,
        "status": "pending",
        "passed": False,
        "input": "",
        "checks": {},
        "warnings": [],
    })
    write_json(project / PATHS["rights_report"], {"schema_version": 1, "content_id": args.content_id, "passed": False, "errors": [], "warnings": []})
    write_json(project / PATHS["provenance_report"], {"schema_version": 1, "content_id": args.content_id, "passed": False, "errors": [], "warnings": []})
    provenance_seed = {"content_id": args.content_id, "account": args.account, "paths": PATHS, "_project_path": str(project)}
    write_json(project / PATHS["skill_provenance"], {"schema_version": 1, "content_id": args.content_id, "account": args.account, "status": "pending", "passed": False, "required_routes": required_routes(provenance_seed), "records": [], "errors": [], "warnings": []})
    write_json(project / PATHS["video_qc"], {"schema_version": 1, "content_id": args.content_id, "status": "pending", "passed": False, "input": "", "metrics": {}, "errors": [], "warnings": []})
    write_json(project / PATHS["pipeline_integrity_qc"], {"schema_version": 1, "content_id": args.content_id, "status": "pending", "passed": False, "errors": ["Run scripts/pipeline_integrity_qc.py --strict before quality approval."], "warnings": []})
    write_json(project / PATHS["feedback_report"], {"schema_version": 1, "content_id": args.content_id, "passed": False, "errors": [], "warnings": []})
    write_json(project / PATHS["publish_receipt"], {"schema_version": 1, "content_id": args.content_id, "status": "pending", "platform": "douyin", "media_id": "", "url": "", "publish_method": "manual-or-official", "operation_id": "", "publish_source": ""})
    write_json(project / PATHS["sidecar_publish"], {"schema_version": 1, "content_id": args.content_id, "status": "not_run", "adapter": "social-auto-upload"})
    write_json(project / PATHS["creator_ops"], {"schema_version": 1, "content_id": args.content_id, "status": "not_run", "adapter": "creator-ops"})
    write_json(project / PATHS["metrics"], {
        "schema_version": 1,
        "content_id": args.content_id,
        "platforms": [],
        "source_sha256": "",
        "learning_metrics": {
            "status": "pending",
            "experiment_id": "",
            "variant_order": ["result-first", "theory-first"],
            "measures": [
                "retention_3s", "retention_6s", "average_watch_seconds", "completion_rate", "rewatch_rate",
                "save_rate", "share_rate", "high_quality_comment_rate", "problem_signal_rate", "commercial_signal_rate",
                "reproduction_intent_rate", "task_understanding_rate", "reproduction_success_rate",
            ],
            "results": [],
            "notes": "Retention is not learning; collect comprehension or reproduction feedback for instructional videos."
        }
    })
    write_json(project / PATHS["comments"], {"schema_version": 1, "content_id": args.content_id, "platform": "douyin", "checkpoint": "post-publish", "status": "pending", "captured_at": "", "source": "", "source_sha256": "", "comments": []})
    write_json(project / PATHS["creator_sidecar"], {"schema_version": 1, "content_id": args.content_id, "status": "not_run", "adapter": "douyin-creator-tools"})
    write_json(project / PATHS["comment_recap"], {"schema_version": 1, "content_id": args.content_id, "status": "not_run", "topic_candidates": []})
    write_json(project / PATHS["feedback_integrity"], {"schema_version": 1, "content_id": args.content_id, "status": "pending", "producer": "dy-feedback-integrity-v1", "errors": ["Run scripts/approval_integrity.py sign-feedback after real publish feedback is collected."]})
    # Canonical workflow hand-offs. These are deliberately explicit and
    # separate from historical markdown/CSV artifacts above.  A new package
    # always starts blocked/pending at the first stage; no alternate provider
    # route or old-package migration is written into the runtime contract.
    write_json(project / PATHS["canonical_brief"], {
        "schema_version": 1,
        "contract": selected_contract,
        "content_id": args.content_id,
        "account": args.account,
        "status": "pending",
        "content_pillar": "",
        "content_type": content_type,
        "primary_audience": "",
        "secondary_audience": "",
        "viewer_situation": "",
        "viewer_goal": "",
        "viewer_motivation": "",
        "promise": "",
        "expected_emotion_change": "",
        "cta": "",
        "duration_tier": "",
        "evidence_density_reason": "",
        "key_questions": [],
        "initial_evidence_plan": [],
        "production_disclosure": {"digital_human": True, "voice_clone": True, "synthetic_visuals": True},
    })
    write_json(project / PATHS["canonical_audience_insight"], {
        "schema_version": 1, "contract": selected_contract, "content_id": args.content_id,
        "primary_audience": "", "secondary_audience": "", "viewer_tasks": [], "practical_value": "", "emotional_value": "", "status": "pending",
    })
    write_json(project / PATHS["canonical_script"], {
        "schema_version": 1, "contract": selected_contract, "content_id": args.content_id, "status": "pending", "title": args.title, "hook": "", "close": "", "beats": [], "script_sha256": "",
    })
    write_json(project / PATHS["canonical_review"], {
        "schema_version": 1, "contract": selected_contract, "content_id": args.content_id, "status": "pending", "promise_match": False, "audience_clear": False, "practical_value_present": False, "emotional_value_present": False, "evidence_plan_complete": False, "no_generated_evidence_claims": True, "conclusion_limits_cta_clear": False, "natural_read": False, "script_sha256": "",
    })
    write_json(project / PATHS["canonical_audio"], {
        "schema_version": 1, "contract": selected_contract, "content_id": args.content_id, "status": "pending", "narration_wav": "", "provider": "index-tts-2.5", "model": "IndexTTS2.5", "voice_mode": "voice-clone", "voice_authorization": "", "reference_audio_sha256": "", "script_sha256": "", "funasr_text": "", "srt": "", "audio_sha256": "", "duration_seconds": 0.0,
    })
    write_json(project / PATHS["canonical_visual_plan"], {
        "schema_version": 1, "contract": selected_contract, "content_id": args.content_id, "status": "pending", "audio_sha256": "", "beats": [], "recording_policy": "claim-driven; no global ratio",
    })
    write_json(project / PATHS["canonical_asset_ledger"], {
        "schema_version": 1, "contract": selected_contract, "content_id": args.content_id, "status": "pending", "assets": [], "image_to_video_policy": {"provider": "gflow-cli", "mode": "i2v", "approved_image_required": True},
    })
    write_json(project / PATHS["canonical_master_timeline"], {
        "schema_version": 1, "contract": selected_contract, "content_id": args.content_id, "status": "pending", "audio_source": PATHS["canonical_audio"], "audio_sha256": "", "openchatcut_owner": "timeline-editor", "hyperframes_owner": "transparent-overlay", "remotion_owner": "final-compositor", "openchatcut_project": "", "remotion_project": "", "render_receipt": "", "candidate_mp4": "", "candidate_sha256": "", "digital_human_segments": [], "fit": "contain", "tracks": [],
    })
    write_json(project / PATHS["canonical_quality"], {
        "schema_version": 1, "contract": selected_contract, "content_id": args.content_id, "status": "pending", "digital_human_present": False, "voice_clone_consistent": False, "direct_evidence_coverage": 0.0, "i2v_lineage_valid": False, "caption_sync": False, "media_qc_passed": False, "candidate_mp4": "", "candidate_mp4_sha256": "", "remotion_still": "", "remotion_still_sha256": "", "contact_sheet": "", "contact_sheet_sha256": "", "render_receipt": "", "render_receipt_sha256": "", "cover": "", "publish_copy": "", "human_review": False,
    })
    write_json(project / PATHS["canonical_delivery"], {
        "schema_version": 1, "contract": selected_contract, "content_id": args.content_id, "account": args.account, "status": "pending", "files": [], "disclosures": {"digital_human": True, "voice_clone": True, "generated_visuals": True},
    })
    write_json(project / PATHS["canonical_publish_receipt"], {"schema_version": 1, "contract": selected_contract, "content_id": args.content_id, "status": "not_published", "platform": "douyin", "external_id": "", "url": "", "published_at": ""})
    write_json(project / PATHS["canonical_feedback"], {"schema_version": 1, "contract": selected_contract, "content_id": args.content_id, "status": "not_published", "snapshots": [], "learning": []})
    if not use_legacy_scaffold:
        prune_noncanonical_scaffold(project, manifest)
    print(json.dumps({"project": str(project), "content_id": args.content_id, "account": args.account, "platform": "douyin"}, ensure_ascii=False))
    return 0


def load_manifest(project: Path) -> dict[str, Any]:
    path = project / "content.json"
    if not path.is_file():
        raise SystemExit(f"missing content.json: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SystemExit(f"invalid content.json: {error}") from error
    if not isinstance(value, dict):
        raise SystemExit("content.json must contain an object")
    return ensure_workflow(value, project.resolve())


def validate_package(args: argparse.Namespace) -> int:
    project = Path(args.project).expanduser().resolve()
    expected_manifest_sha256 = manifest_sha256(project)
    try:
        manifest = load_manifest(project)
    except (SystemExit, ValueError) as error:
        # Validation is an operator-facing audit command.  A stale policy
        # lock or malformed manifest must be reported as a structured blocked
        # result rather than an unhandled traceback, while the stricter
        # ``load_manifest`` API remains fail-closed for callers that mutate
        # workflow state.
        result = {
            "project": str(project),
            "content_id": "",
            "current_step": "",
            "errors": [str(error)],
            "warnings": [],
            "status": "blocked",
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1
    if manifest.get("workflow_contract") != LEGACY_CANONICAL_CONTRACT_ID:
        previous_current_step = str(manifest.get("workflow", {}).get("current_step", ""))
        stale_changed = refresh_stale(manifest, project)
        refreshed_current_step = str(manifest.get("workflow", {}).get("current_step", ""))
        if stale_changed or refreshed_current_step != previous_current_step:
            # Keep V2 package validation and workflow_gate status on the same
            # state machine. V1 validation is read-only to preserve its evidence.
            save_manifest(project, manifest, expected_manifest_sha256)
    errors: list[str] = []
    warnings: list[str] = []
    content_id = manifest.get("content_id")
    if not isinstance(content_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,80}", content_id):
        errors.append("content_id is invalid")
    configured_root = os.environ.get("DY_ARTIFACT_ROOT", "").strip()
    allow_caller_selected = bool(getattr(args, "allow_caller_selected", False)) or os.environ.get("DY_ALLOW_CALLER_SELECTED", "").strip().lower() in {"1", "true", "yes"}
    if not allow_caller_selected and isinstance(content_id, str):
        try:
            artifact_root = Path(configured_root).expanduser().resolve() if configured_root else DEFAULT_ARTIFACT_ROOT.resolve()
            validate_project_layout(project, content_id, artifact_root)
        except ValueError as error:
            errors.append(str(error))
    if manifest.get("account") != ACCOUNT:
        errors.append(f"account must be {ACCOUNT}")
    if manifest.get("deliverables") != ["video"]:
        errors.append("deliverables must be exactly ['video']")
    if manifest.get("platforms") != ["douyin"]:
        errors.append("platforms must be exactly ['douyin']")
    # v2 production packages always use the canonical path namespace.  A v1
    # rollback can be either an older canonical package (keep auditing it) or
    # the historical scaffold selected by WORKFLOW_CONTRACT_VERSION (fall
    # through to the legacy validator so it remains readable).
    manifest_paths = manifest.get("paths") if isinstance(manifest.get("paths"), dict) else {}
    canonical_namespace = "canonical_brief" in manifest_paths
    if (
        manifest.get("workflow_contract") in CANONICAL_CONTRACT_IDS
        and not allow_caller_selected
        and (manifest.get("workflow_contract") == CANONICAL_CONTRACT_ID or canonical_namespace)
    ):
        paths = manifest_paths
        expected = canonical_artifact_paths(str(manifest.get("workflow_contract") or CANONICAL_CONTRACT_ID))
        # Existing v1 packages remain auditable without being retroactively
        # rewritten.  Only strict production packages must carry the new
        # provider/runtime receipt set.
        if not is_canonical_strict(manifest):
            # A v1 rollback scaffold carries the ten historical stage
            # artifacts, but not the v2-only content/audience/feedback and
            # provider receipt sidecars.  Validate the historical stages that
            # are present without demanding files that v1 never produced.
            legacy_stage_artifacts = {
                "brief", "claims", "script", "review", "audio", "visual_plan",
                "asset_ledger", "master_timeline", "quality", "delivery",
            }
            expected = {key: value for key, value in expected.items() if key in legacy_stage_artifacts}
        for key, relative in expected.items():
            value = str(paths.get(f"canonical_{key}", relative))
            if not (project / value).is_file():
                # Top-level avatar hand-offs are materialized only after the
                # real MiniMax H3 execution.  Their absence at bootstrap is
                # intentional and must not be confused with a fake/static
                # placeholder; Media Generation and later gates require them.
                if key in {"avatar_video", "avatar_manifest", "avatar_qc"} and manifest.get("workflow", {}).get("current_step") in {"brief", "research", "script", "review", "audio", "visual_plan", "visual_route", "assets_plan", "assets"}:
                    continue
                errors.append(f"missing canonical artifact {key}: {project / value}")
        if args.strict:
            for stage_id, stage in manifest.get("workflow", {}).get("steps", {}).items():
                if not isinstance(stage, dict) or stage.get("status") != "approved":
                    errors.append(f"workflow step not approved: {stage_id}")
        result = {"project": str(project), "content_id": content_id, "current_step": manifest.get("workflow", {}).get("current_step"), "errors": errors, "warnings": warnings}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if errors else 0
    production_path = project / str((manifest.get("paths") or {}).get("production_profile", PATHS["production_profile"]))
    if not production_path.is_file():
        warnings.append("production profile is missing; choose presenter and voice mode before Brief approval")
    else:
        production = json.loads(production_path.read_text(encoding="utf-8"))
        if production.get("status") != "approved":
            warnings.append("production profile must be approved before Brief approval")
        if bool(production.get("runtime_required")) != bool(manifest.get("runtime_required")):
            errors.append("production profile runtime_required does not match content package")
    paths = manifest.get("paths") if isinstance(manifest.get("paths"), dict) else {}
    if not paths:
        errors.append("paths is missing")
    for contract_name in ("copy_brief", "copy_strategy"):
        relative = str(paths.get(contract_name, "")).strip()
        if not relative:
            errors.append(f"paths.{contract_name} is required")
            continue
        contract_path = project / relative
        if not contract_path.is_file():
            continue
        try:
            contract_payload = json.loads(contract_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(contract_payload, dict) or contract_payload.get("schema_version") != 3:
            errors.append(f"{contract_name} schema_version must be 3")
    workflow_steps = manifest.get("workflow", {}).get("steps", {}) if isinstance(manifest.get("workflow"), dict) else {}
    order_by_step = {str(step_id): int(step.get("order", 0)) for step_id, step in workflow_steps.items() if isinstance(step, dict)}
    current_step = str(manifest.get("workflow", {}).get("current_step", ""))
    current_order = order_by_step.get(current_step, 0)
    for name, relative in PATHS.items():
        file_path = project / str(paths.get(name, relative))
        if not file_path.is_file():
            producer = ARTIFACT_REQUIRED_STAGE.get(name)
            producer_order = order_by_step.get(producer, 0) if producer else 0
            reached = bool(producer and current_order and producer_order and current_order >= producer_order)
            if name in OPTIONAL_UNTIL_STAGE and not reached:
                warnings.append(f"bootstrap artifact not yet produced by stage {producer or 'unknown'}: {file_path}")
            elif name in OPTIONAL_UNTIL_STAGE and reached:
                errors.append(f"required artifact missing after stage {producer}: {file_path}")
            else:
                errors.append(f"missing {name}: {file_path}")
    claims_path = project / str(paths.get("claims", PATHS["claims"]))
    if claims_path.is_file():
        claims = json.loads(claims_path.read_text(encoding="utf-8"))
        claim_items = claims.get("claims", []) if isinstance(claims, dict) else []
        if not claim_items:
            warnings.append("claims.json has no claim items yet")
    ledger_path = project / str(paths.get("asset_ledger", PATHS["asset_ledger"]))
    if ledger_path.is_file() and ledger_path.stat().st_size <= 150:
        warnings.append("asset ledger has headers but no approved assets")
    if args.strict:
        errors.extend(warnings)
        steps = manifest.get("workflow", {}).get("steps", {})
        for step_id, step in steps.items():
            if step.get("required") is True and step.get("status") != "approved":
                errors.append(f"workflow step not approved: {step_id}")
    result = {"project": str(project), "content_id": content_id, "current_step": manifest.get("workflow", {}).get("current_step"), "errors": errors, "warnings": warnings}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if errors else 0


def refresh_policy(args: argparse.Namespace) -> int:
    """Refresh the package's local-media policy evidence after an explicit policy change.

    Policy changes are security-sensitive. The package keeps its content and
    route selection, but all stage approvals are invalidated so the new policy
    must pass the normal gates again instead of silently inheriting old consent.
    """
    project = Path(args.project).expanduser().resolve()
    manifest_path = project / "content.json"
    expected_manifest_sha256 = manifest_sha256(project)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"cannot load content.json: {error}") from error
    if not isinstance(manifest, dict):
        raise SystemExit("content.json must contain an object")
    media_policy, policy_sha256 = load_media_policy()
    current = manifest.get("media_policy") if isinstance(manifest.get("media_policy"), dict) else {}
    changed = str(current.get("sha256", "")) != policy_sha256
    manifest["media_policy"] = {
        "path": "local-media-policy.json",
        "policy": media_policy.get("policy"),
        "sha256": policy_sha256,
    }
    if changed and isinstance(manifest.get("workflow"), dict):
        invalidate_from(manifest, "brief", "local media policy refreshed; reapproval required")
    save_manifest(project, manifest, expected_manifest_sha256)
    print(json.dumps({"project": str(project), "policy_sha256": policy_sha256, "changed": changed, "approvals_invalidated": changed}, ensure_ascii=False, indent=2))
    return 0


def status(args: argparse.Namespace) -> int:
    project = Path(args.project).expanduser().resolve()
    print(json.dumps(load_manifest(project), ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Initialize and validate a Douyin-only content package.")
    sub = parser.add_subparsers(dest="command", required=True)
    init_parser = sub.add_parser("init")
    init_parser.add_argument("--project", required=True)
    init_parser.add_argument("--content-id", required=True)
    init_parser.add_argument("--account", required=True, choices=[ACCOUNT])
    init_parser.add_argument("--title", required=True)
    init_parser.add_argument("--deliverables", default="video")
    init_parser.add_argument("--platforms", default="douyin")
    init_parser.add_argument("--use-runtime", action="store_true")
    init_parser.add_argument("--mode", choices=["draft", "production"], default="draft")
    init_parser.add_argument("--topic-id", default="")
    init_parser.add_argument("--content-type", default="", help="explicit taxonomy lock; otherwise use the route content_type")
    init_parser.add_argument("--scheduled-for", default="")
    init_parser.add_argument("--routing-file", default="", help="Approved output from scripts/workflow_start.py route")
    init_parser.add_argument("--allow-stale-route", action="store_true", help="Explicitly reuse an older route; it remains ineligible for Brief approval unless re-confirmed.")
    init_parser.add_argument("--allow-caller-selected", action="store_true", help="Explicit non-production/test override for a project outside the production root")
    init_parser.add_argument("--force", action="store_true")
    init_parser.set_defaults(handler=init_package)
    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("--project", required=True)
    validate_parser.add_argument("--strict", action="store_true")
    validate_parser.add_argument("--allow-caller-selected", action="store_true", help="Explicit non-production/test override for a project outside the production root")
    validate_parser.set_defaults(handler=validate_package)
    refresh_policy_parser = sub.add_parser("refresh-policy", help="Refresh local-media policy evidence and invalidate stale approvals")
    refresh_policy_parser.add_argument("--project", required=True)
    refresh_policy_parser.set_defaults(handler=refresh_policy)
    status_parser = sub.add_parser("status")
    status_parser.add_argument("--project", required=True)
    status_parser.set_defaults(handler=status)
    return parser


if __name__ == "__main__":
    arguments = build_parser().parse_args()
    raise SystemExit(arguments.handler(arguments))
