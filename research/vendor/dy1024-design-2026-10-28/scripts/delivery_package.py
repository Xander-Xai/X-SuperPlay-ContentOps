#!/usr/bin/env python3
"""Build a platform-ready delivery bundle from an approved content package."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import workflow_gate

try:
    from canonical_workflow import CONTRACT_ID, SUPPORTED_CONTRACT_IDS
except ImportError:  # imported as scripts.delivery_package
    from scripts.canonical_workflow import CONTRACT_ID, SUPPORTED_CONTRACT_IDS


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as error:
        raise SystemExit(f"invalid or missing JSON: {path}: {error}") from error
    if not isinstance(value, dict):
        raise SystemExit(f"JSON must contain an object: {path}")
    return value


def copy_if_file(source: Path, target: Path, files: list[str]) -> None:
    if source.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        files.append(target.name)


def copy_tree_files(source: Path, target: Path, files: list[str]) -> None:
    if not source.is_dir():
        return
    target.mkdir(parents=True, exist_ok=True)
    excluded_parts = {"node_modules", ".native-runs", ".hyperframes", "renders", "snapshots", "public"}
    for item in source.rglob("*"):
        if not item.is_file():
            continue
        relative = item.relative_to(source)
        if any(part in excluded_parts for part in relative.parts):
            continue
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, destination)
        files.append(str(destination.relative_to(target.parent)).replace("\\", "/"))


def artifact_path(project: Path, value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        resolved = candidate.resolve()
        try:
            resolved.relative_to(project.resolve())
        except ValueError as error:
            raise SystemExit(f"artifact path must remain inside project: {value}") from error
        return resolved
    try:
        return workflow_gate.project_path(project, value)
    except ValueError as error:
        raise SystemExit(str(error)) from error


def fresh_gate_errors(project: Path, through: str | None = None) -> list[str]:
    """Re-run every required checker immediately before final delivery.

    A previously generated workflow-audit.json is evidence, not authority:
    files can change after it was written. Delivery therefore revalidates the
    current manifest and all required stages instead of trusting a stale or
    hand-edited audit report.
    """
    manifest = workflow_gate.load_manifest(project)
    if workflow_gate.refresh_stale(manifest, project):
        # Persist invalidation so a stale approval cannot reappear on the next
        # delivery attempt or be hidden by an old workflow-audit file.
        workflow_gate.save_manifest(project, manifest)
    errors: list[str] = []
    ordered_steps = workflow_gate.step_ids(manifest)
    if through is not None and through not in ordered_steps:
        return [f"unknown canonical preflight boundary: {through}"]
    selected_steps = ordered_steps[: ordered_steps.index(through) + 1] if through is not None else ordered_steps
    for step in selected_steps:
        state = manifest["workflow"]["steps"][step]
        if state.get("status") != "approved":
            errors.append(f"workflow step is not approved: {step}")
        try:
            result = workflow_gate.CHECKERS[step](project, manifest, workflow_gate.profile_for(str(manifest.get("account", ""))))
        except Exception as error:  # malformed artifacts must block delivery
            errors.append(f"{step} checker failed: {error}")
            continue
        errors.extend(f"{step}: {error}" for error in result.get("errors", []))
    return errors


def canonical_delivery(project: Path, manifest: dict[str, Any], args: argparse.Namespace) -> int:
    """Build the v2 Delivery only after the approved Quality hand-off."""
    if args.allow_unapproved:
        raise SystemExit("canonical Delivery cannot bypass Quality approval")
    paths = manifest.get("paths", {}) if isinstance(manifest.get("paths"), dict) else {}
    quality_path = artifact_path(project, str(paths.get("canonical_quality", "07_quality/quality-report.json")))
    quality = load(quality_path)
    errors = fresh_gate_errors(project, through="quality")
    if errors:
        raise SystemExit("fresh canonical gate failed; Delivery is blocked:\n- " + "\n- ".join(errors))
    destination = artifact_path(project, args.output)
    if destination.exists() and not args.force:
        raise SystemExit(f"delivery directory exists: {destination}; use --force to replace files")
    staging = destination.parent / f".{destination.name}.staging-{uuid.uuid4().hex}"
    staging.mkdir(parents=True, exist_ok=False)
    timeline_path = artifact_path(project, str(paths.get("canonical_master_timeline", "06_edit/master-timeline.json")))
    audio_path = artifact_path(project, str(paths.get("canonical_audio", "03_audio/audio-handoff.json")))
    timeline = load(timeline_path)
    audio = load(audio_path)
    required_sources: list[tuple[str, Path]] = [
        ("final.mp4", artifact_path(project, str(timeline.get("candidate_mp4", "")))),
        ("cover.png", artifact_path(project, str(quality.get("cover", "")))),
        ("captions.srt", artifact_path(project, str(audio.get("srt", "")))),
        ("narration.wav", artifact_path(project, str(audio.get("narration_wav", "")))),
        ("publish-copy.md", artifact_path(project, str(quality.get("publish_copy", "")))),
        ("evidence/master-timeline.json", timeline_path),
        ("evidence/audio-handoff.json", audio_path),
        ("evidence/asset-ledger.json", artifact_path(project, str(paths.get("canonical_asset_ledger", "05_assets/asset-ledger.json")))),
        ("evidence/claims.json", artifact_path(project, str(paths.get("canonical_claims", "01_research/claims.json")))),
        ("evidence/visual-plan.json", artifact_path(project, str(paths.get("canonical_visual_plan", "04_visual/visual-plan.json")))),
        ("evidence/quality-report.json", quality_path),
        ("evidence/render-receipt.json", artifact_path(project, str(timeline.get("render_receipt", "")))),
    ]
    if manifest.get("workflow_contract") == CONTRACT_ID and manifest.get("strict_media_execution") is True:
        required_sources.extend([
            ("evidence/visual-route.json", artifact_path(project, str(paths.get("canonical_visual_route", "04_visual/visual-route.json")))),
            ("evidence/director-material-plan.json", artifact_path(project, str(paths.get("canonical_director_material_plan", "04_visual/director-material-plan.json")))),
            ("evidence/image-generation-provenance.json", artifact_path(project, str(paths.get("canonical_image_generation_provenance", "05_assets/image-generation-provenance.json")))),
            ("evidence/i2v-job-specs.json", artifact_path(project, str(paths.get("canonical_i2v_job_specs", "05_assets/i2v-job-specs.json")))),
            ("evidence/human-operation-receipt.json", artifact_path(project, str(paths.get("canonical_human_operation_receipt", "05_assets/human-operation-receipt.json")))),
            ("evidence/visual-review.json", artifact_path(project, str(paths.get("canonical_visual_review", "07_quality/visual-review.json")))),
            ("evidence/plugin-native-visual-qc.json", artifact_path(project, str(paths.get("canonical_plugin_native_visual_qc", "07_quality/plugin-native-visual-qc.json")))),
        ])
    missing = [name for name, source in required_sources if not source.is_file()]
    if missing:
        shutil.rmtree(staging)
        raise SystemExit("canonical Delivery required files are missing: " + ", ".join(missing))
    files: list[dict[str, Any]] = []
    for name, source in required_sources:
        target = staging / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        relative = str((destination / name).relative_to(project)).replace("\\", "/")
        files.append({"path": relative, "sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "bytes": target.stat().st_size})
    report = {
        "schema_version": 1,
        "contract": str(manifest.get("workflow_contract") or CONTRACT_ID) if manifest.get("workflow_contract") in SUPPORTED_CONTRACT_IDS else CONTRACT_ID,
        "content_id": manifest.get("content_id", ""),
        "account": manifest.get("account", ""),
        "status": "ready_for_review",
        "files": files,
        "disclosures": {"digital_human": True, "voice_clone": True, "generated_visuals": True},
    }
    delivery_path = artifact_path(project, str(paths.get("canonical_delivery", "08_delivery/delivery-manifest.json")))
    delivery_path.parent.mkdir(parents=True, exist_ok=True)
    delivery_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if destination.exists():
        backup = destination.parent / f".{destination.name}.replaced-{uuid.uuid4().hex}"
        os.replace(destination, backup)
    os.replace(staging, destination)
    print(json.dumps({"output": str(delivery_path), "manifest": report}, ensure_ascii=False, indent=2))
    return 0


def build(args: argparse.Namespace) -> int:
    project = Path(args.project).expanduser().resolve()
    manifest = load(project / "content.json")
    if manifest.get("workflow_contract") in SUPPORTED_CONTRACT_IDS and workflow_gate.is_canonical_manifest(manifest):
        return canonical_delivery(project, manifest, args)
    quality_path = artifact_path(project, str(manifest.get("paths", {}).get("quality", "05_publish/quality.json")))
    quality = load(quality_path)
    required_quality = ("caption_safe", "rights_checked", "sync_checked", "audio_checked", "visual_checked")
    if any(quality.get(field) is not True for field in required_quality) and not args.allow_unapproved:
        raise SystemExit("quality sign-off is incomplete; use --allow-unapproved only for an internal preview")
    if not args.allow_unapproved:
        gate_errors = fresh_gate_errors(project)
        if gate_errors:
            raise SystemExit("fresh workflow gate failed; final delivery is blocked:\n- " + "\n- ".join(gate_errors))
    audit_path = artifact_path(project, str(manifest.get("paths", {}).get("workflow_audit", "05_publish/workflow-audit.json")))
    if not args.allow_unapproved:
        if not audit_path.is_file():
            raise SystemExit("workflow audit is missing; run scripts/workflow_audit.py --strict before final delivery")
        audit = load(audit_path)
        if audit.get("passed") is not True or audit.get("status") != "ready":
            raise SystemExit("workflow audit has not passed; final delivery is blocked")
    destination = artifact_path(project, args.output)
    if destination.exists() and not args.force:
        raise SystemExit(f"delivery directory exists: {destination}; use --force to replace files")
    staging = destination.parent / f".{destination.name}.staging-{uuid.uuid4().hex}"
    staging.mkdir(parents=True, exist_ok=False)
    files: list[str] = []
    paths = manifest.get("paths", {})
    deliverables = set(str(item) for item in manifest.get("deliverables", []))
    if manifest.get("deliverables") != ["video"] or manifest.get("platforms") != ["douyin"]:
        raise SystemExit("final delivery only supports a Douyin video package")
    direct: dict[str, str] = {
        "execution-plan.json": paths.get("execution_plan", "00_brief/execution-plan.json"),
        "skill-catalog.json": paths.get("skill_catalog", "05_publish/skill-catalog.json"),
        "visual-route.json": paths.get("visual_route", "04_video/visual-route.json"),
        "motion-plan.json": paths.get("motion_plan", "04_video/motion-plan.json"),
        "motion-check.json": paths.get("motion_check", "05_publish/motion-check.json"),
        "motion-provenance.json": paths.get("motion_provenance", "05_publish/motion-provenance.json"),
        "motion-render-report.json": paths.get("motion_render_report", "05_publish/motion-render-report.json"),
        "plugin-scene-brief.json": paths.get("plugin_scene_brief", "04_video/scene-brief.json"),
        "plugin-visual-profile.json": paths.get("visual_profile", "04_video/visual-profile.json"),
        "plugin-render-manifest.json": paths.get("plugin_render_manifest", "06_motion/plugin-render-manifest.json"),
        "plugin-native-qc.json": paths.get("plugin_native_qc", "05_publish/plugin-native-qc.json"),
        "plugin-native-concurrency-qc.json": paths.get("plugin_native_concurrency_qc", "05_publish/plugin-native-concurrency-qc.json"),
        "plugin-native-visual-qc.json": paths.get("plugin_native_visual_qc", "05_publish/plugin-native-visual-qc.json"),
        "plugin-native-audio-receipt.json": "04_video/render-project/04_audio/plugin-native-audio-receipt.json",
        "narration.wav": "04_video/render-project/04_audio/narration.wav",
        "captions.srt": "04_video/render-project/04_audio/captions.srt",
        "asr-verification.json": "04_video/render-project/04_audio/asr-verification.json",
        "hyperframes-plan.json": paths.get("hyperframes_plan", "06_motion/hyperframes-native/hyperframes-plan.json"),
        "remotion-plan.json": paths.get("remotion_plan", "06_motion/remotion-native/remotion-plan.json"),
        "video-script.md": paths.get("video_script", "04_video/video-script.md"),
        "teaching-contract.json": paths.get("teaching_contract", "04_video/teaching-contract.json"),
        "storyboard.csv": paths.get("storyboard", "04_video/storyboard.csv"),
        "director-material-plan.json": paths.get("director_plan", "04_video/director-material-plan.json"),
        "source-candidates.json": paths.get("source_candidates", "03_assets/source-candidates.json"),
        "broll-plan.json": paths.get("broll_plan", "04_video/broll-plan.json"),
        "broll-plan.md": paths.get("broll_plan_review", "04_video/broll-plan.md"),
        "asset-requests.md": paths.get("asset_requests") or paths.get("canonical_asset_requests", "03_assets/asset-requests.md"),
        "broll-manifest.json": paths.get("broll_manifest", "03_assets/broll/manifest.json"),
        "broll-qc.json": paths.get("broll_qc", "05_publish/broll-qc.json"),
    }
    direct.update({
        "asset-ledger.csv": paths.get("asset_ledger", "03_assets/asset-ledger.csv"),
        "rights-report.json": paths.get("rights_report", "05_publish/rights-report.json"),
        "distribution.json": paths.get("distribution", "05_publish/distribution.json"),
        "variants.json": paths.get("variants", "05_publish/variants.json"),
        "quality.json": paths.get("quality", "05_publish/quality.json"),
        "video-qc.json": paths.get("video_qc", "05_publish/video-qc.json"),
        "visual-qc.json": paths.get("visual_qc", "05_publish/visual-qc.json"),
        "teaching-qc.json": paths.get("teaching_qc", "05_publish/teaching-qc.json"),
        "naturalness-qc.json": paths.get("naturalness_qc", "05_publish/naturalness-qc.json"),
        "video-planning-audit.json": paths.get("video_planning_audit", "05_publish/video-planning-audit.json"),
        "visual-review.json": paths.get("visual_review", "05_publish/visual-review.json"),
        "subtitle-qc.json": paths.get("subtitle_qc", "05_publish/subtitle-qc.json"),
        "provenance-report.json": paths.get("provenance_report", "05_publish/provenance-report.json"),
        "skill-provenance.json": paths.get("skill_provenance", "05_publish/skill-provenance.json"),
        "design-lint.json": paths.get("design_lint", "05_publish/design-lint.json"),
        "workflow-audit.json": paths.get("workflow_audit", "05_publish/workflow-audit.json"),
        "publish-receipt.json": paths.get("publish_receipt", "05_publish/publish-receipt.json"),
        "sidecar-publish.json": paths.get("sidecar_publish", "05_publish/sidecar-publish.json"),
        "creator-ops.json": paths.get("creator_ops", "05_publish/creator-ops.json"),
        "metrics.json": paths.get("metrics", "06_metrics/metrics.json"),
        "comments.json": paths.get("comments", "06_metrics/comments.json"),
        "creator-sidecar.json": paths.get("creator_sidecar", "06_metrics/creator-sidecar.json"),
        "comment-recap.json": paths.get("comment_recap", "06_metrics/comment-recap.json"),
    })
    for name, relative in direct.items():
        copy_if_file(artifact_path(project, str(relative)), staging / name, files)
    if workflow_gate.plugin_native_enabled(manifest):
        plugin_manifest_path = artifact_path(project, str(paths.get("plugin_render_manifest", "06_motion/plugin-render-manifest.json")))
        if plugin_manifest_path.is_file():
            plugin_manifest = load(plugin_manifest_path)
            for source_root in ("06_motion/hyperframes-native", "06_motion/remotion-native", "06_motion/handoff"):
                copy_tree_files(artifact_path(project, source_root), staging / "plugin-native-sources" / source_root.replace("/", "_"), files)
            # ``public`` is intentionally excluded from generic source copies
            # to avoid shipping interop frame caches.  The final narration is
            # different: Remotion's Audio component must remain runnable from
            # the delivered source, so copy only this hash-bound asset.
            copy_if_file(
                artifact_path(project, "06_motion/remotion-native/public/audio/narration.wav"),
                staging / "plugin-native-sources" / "06_motion_remotion-native" / "public" / "audio" / "narration.wav",
                files,
            )
            execution = plugin_manifest.get("native_execution", {}) if isinstance(plugin_manifest.get("native_execution"), dict) else {}
            for receipt in execution.get("receipts", []) if isinstance(execution.get("receipts"), list) else []:
                artifact = receipt.get("artifact") if isinstance(receipt, dict) and isinstance(receipt.get("artifact"), dict) else None
                if artifact and artifact.get("path"):
                    source = artifact_path(project, str(artifact["path"]))
                    copy_if_file(source, staging / "plugin-native-artifacts" / source.name, files)
            # The snapshot receipt keeps its contact-sheet path in the visual
            # review draft rather than as a render artifact. Copy that exact
            # run-bound file too, otherwise the delivered review manifest
            # points at evidence that is absent from the bundle.
            visual_review = load(artifact_path(project, str(paths.get("visual_review", "05_publish/visual-review.json"))))
            contact_sheet = str(visual_review.get("contact_sheet") or "").strip() if isinstance(visual_review, dict) else ""
            if contact_sheet:
                copy_if_file(artifact_path(project, contact_sheet), staging / "plugin-native-artifacts" / "contact-sheet.jpg", files)
    video_manifest_path = artifact_path(project, str(paths.get("video", "04_video/video.json")))
    if "video" in deliverables and video_manifest_path.is_file():
        video = load(video_manifest_path)
        nested_value = str(video.get("project_path", "")).strip()
        if not nested_value:
            nested = project / "04_video" / "render-project"
        else:
            nested = artifact_path(project, nested_value)
        nested_final = nested / "08_exports" / "final"
        for name in ("master.mp4", "captions.srt", "cover.png", "delivery-manifest.json", "generated-media-disclosure.md"):
            copy_if_file(nested_final / name, staging / name, files)
        # A review-candidate preview is still a valid offline handoff when
        # finalization is intentionally held at the official publishing
        # boundary. Never rename it to master.mp4 or imply it was published.
        if not (staging / "master.mp4").is_file():
            copy_if_file(nested / "08_exports" / "preview" / "preview.mp4", staging / "preview.mp4", files)
        for name in ("captions.srt", "cover.png"):
            copy_if_file(nested / "04_audio" / name, staging / name, files)
    if not files:
        raise SystemExit("no delivery artifacts found")
    receipt = load(artifact_path(project, str(paths.get("publish_receipt", "05_publish/publish-receipt.json"))))
    publish_method = str(receipt.get("publish_method", ""))
    manual_publish_required = publish_method in {"", "manual", "manual-or-official", "draft"}
    report = {
        "schema_version": 1,
        "content_id": manifest.get("content_id", ""),
        "account": manifest.get("account", ""),
        "built_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "platforms": list(manifest.get("platforms", [])),
        "files": sorted(set(files)),
        "approved_quality": not args.allow_unapproved,
        "delivery_status": "final" if (staging / "master.mp4").is_file() and not args.allow_unapproved else "review-candidate",
        "publish_method": publish_method or "unknown",
        "manual_publish_required": manual_publish_required,
    }
    (staging / "delivery-manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if destination.exists():
        backup = destination.parent / f".{destination.name}.replaced-{uuid.uuid4().hex}"
        os.replace(destination, backup)
    os.replace(staging, destination)
    # The current destination is the only authoritative bundle.  The previous
    # bundle remains recoverable under a random, hidden sibling path and is
    # never consulted by delivery status or manifest generation.
    report["output"] = str(destination)
    print(json.dumps({"output": str(destination), "manifest": report}, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a Douyin content delivery bundle.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--output", default="08_delivery/package")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--allow-unapproved", action="store_true", help="Build an internal preview, never a final deliverable")
    parser.set_defaults(handler=build)
    return parser


if __name__ == "__main__":
    arguments = build_parser().parse_args()
    raise SystemExit(arguments.handler(arguments))
