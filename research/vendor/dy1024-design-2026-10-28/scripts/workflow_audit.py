#!/usr/bin/env python3
"""Run every workflow checker and write a stage-by-stage audit report.

This command never approves a stage and never changes the package manifest. It
is intentionally read-only with respect to workflow state so a reviewer can
inspect the full delivery readiness before approving the next serial gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import workflow_gate  # noqa: E402


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# 工作流阶段审计：{report.get('content_id', '')}",
        "",
        f"- 生成时间：{report.get('audited_at', '')}",
        f"- 总体状态：`{report.get('status', '')}`",
        f"- 严格模式：`{str(report.get('strict', False)).lower()}`",
        "",
        "| 顺序 | 阶段 | 门禁状态 | 本次检查 | 阻塞原因 |",
        "| ---: | --- | --- | --- | --- |",
    ]
    for item in report.get("stages", []):
        blockers = "; ".join(item.get("blocked_by", [])) or "—"
        errors = "; ".join(item.get("errors", [])) or "通过"
        lines.append(
            f"| {item.get('order', '')} | {item.get('label', item.get('id', ''))} | "
            f"`{item.get('workflow_status', '')}` | {('通过' if item.get('check_passed') else '未通过')} | "
            f"{blockers if blockers != '—' else errors} |"
        )
    lines.extend([
        "",
        "## 子阶段执行审计",
        "",
        "| 子阶段 | 是否必做 | 执行状态 | 证据/阻塞 |",
        "| --- | --- | --- | --- |",
    ])
    for item in report.get("sub_stages", []):
        reason = "; ".join(item.get("errors", [])) or "通过"
        lines.append(f"| {item.get('id', '')} | {('是' if item.get('required') else '否')} | `{item.get('status', '')}` | {reason} |")
    lines.extend([
        "",
        "## 使用规则",
        "",
        "审计只读，不会替代人工批准。必须先修复当前阶段错误，再执行 `workflow_gate.py approve --confirm`；任何已批准输入发生变化都会使该阶段及下游阶段回到 pending。",
        "",
    ])
    return "\n".join(lines)


def audit_sub_stages(project: Path, manifest: dict[str, Any], profile: dict[str, Any]) -> list[dict[str, Any]]:
    if manifest.get("workflow_contract") in workflow_gate.CANONICAL_CONTRACT_IDS:
        result: list[dict[str, Any]] = []
        for stage_id in workflow_gate.step_ids(manifest, required_only=False):
            definition = manifest["workflow"]["steps"][stage_id]
            try:
                checked = workflow_gate.CHECKERS[stage_id](project, manifest, profile)
                errors = list(checked.get("errors", []))
            except Exception as error:
                errors = [f"checker exception: {error}"]
            result.append({"id": stage_id, "required": True, "status": "executed" if not errors else "blocked", "errors": errors})
        return result
    plan, _, contract_errors, _ = workflow_gate.execution_plan_contract(project, manifest, profile)
    stages = plan.get("required_execution_stages", {}) if isinstance(plan.get("required_execution_stages"), dict) else {}
    successful, _, provenance_errors = workflow_gate.successful_skill_routes(project, manifest)
    current_step = str((manifest.get("workflow", {}) if isinstance(manifest.get("workflow"), dict) else {}).get("current_step", "brief")).strip().lower()
    teaching_stage = "quality" if current_step in {"quality", "publish_feedback"} else "review"
    result: list[dict[str, Any]] = []
    for stage_id, stage in stages.items():
        if not isinstance(stage, dict):
            continue
        required = bool(stage.get("required"))
        if not required:
            result.append({"id": stage_id, "required": False, "status": "not_required", "errors": []})
            continue
        errors: list[str] = []
        required_routes = workflow_gate.external_routes(stage.get("routes", []))
        if stage_id in {"copywriting", "voice", "presenter", "motion_authoring"}:
            missing = sorted(required_routes - successful)
            if missing:
                errors.append("missing route evidence: " + ", ".join(missing))
            errors.extend(provenance_errors)
        stage_status = "executed"
        if stage_id == "audio":
            audio = workflow_gate.check_audio(project, manifest, profile)
            errors.extend(audio.get("errors", []))
        elif stage_id == "visual_routing":
            _, visual_errors = workflow_gate.visual_execution_evidence(project, manifest)
            errors.extend(visual_errors)
        elif stage_id == "motion_render":
            motion_path = workflow_gate.project_path(project, str(manifest["paths"].get("motion_render_report", "05_publish/motion-render-report.json")))
            if not motion_path.is_file():
                errors.append("motion render report is missing")
            else:
                motion = workflow_gate.load_json(motion_path, "motion render report")
                if motion.get("passed") is not True or motion.get("status") not in {"ready", "conditional"}:
                    errors.append("motion render report is not ready/conditional-passed")
                elif motion.get("status") == "conditional":
                    stage_status = "conditional"
        elif stage_id == "assembly":
            delivery = workflow_gate.project_path(project, str(manifest["paths"].get("delivery_manifest", "05_publish/delivery/delivery-manifest.json")))
            if not delivery.is_file():
                errors.append("delivery manifest is missing")
        elif stage_id == "automated_qc":
            for key in ("subtitle_qc", "video_qc", "visual_qc", "creative_qc"):
                path = workflow_gate.project_path(project, str(manifest["paths"].get(key, f"05_publish/{key}.json")))
                if not path.is_file():
                    errors.append(f"{key} is missing")
                else:
                    report = workflow_gate.load_json(path, key)
                    if report.get("passed") is not True:
                        errors.append(f"{key} has not passed")
        elif stage_id == "human_review":
            review = workflow_gate.project_path(project, str(manifest["paths"].get("visual_review", "05_publish/visual-review.json")))
            if not review.is_file():
                errors.append("visual review is missing")
            else:
                value = workflow_gate.load_json(review, "visual review")
                reviewer_role = str(value.get("reviewer_role", "")).strip().lower()
                allowed_reviewers = {"user"} if str(manifest.get("publish_mode", "draft")) == "production" else {"user", "operator", "codex"}
                if value.get("status") != "approved" or value.get("passed") is not True or reviewer_role not in allowed_reviewers:
                    errors.append("visual review is not approved for the current publish mode")
        elif stage_id == "publish_feedback":
            errors.extend(workflow_gate.check_publish_feedback(project, manifest, profile).get("errors", []))
        result.append({"id": stage_id, "required": True, "status": stage_status if not errors else "blocked", "errors": sorted(set(errors))})
    image = plan.get("image_generation", {}) if isinstance(plan.get("image_generation"), dict) else {}
    if "image_generation" not in {item.get("id") for item in result}:
        image_required = bool(image.get("required"))
        result.append({"id": "image_generation", "required": image_required, "status": "not_required" if not image_required else str(image.get("status", "blocked")), "errors": [] if not image_required else (["image generation execution is not complete"] if image.get("status") not in {"ready", "executed"} else [])})
    # Keep the best-practice contract visible as a first-class sub-stage in
    # read-only audits; a green motion/render report alone must not hide copy,
    # ASR, inventory or configuration-card failures.
    try:
        import best_practice_qc
        best = best_practice_qc.run_checks(project, enforce=True, teaching_stage=teaching_stage)
        result.append({"id": "best_practice_qc", "required": True, "status": "executed" if best.get("passed") else "blocked", "teaching_stage": teaching_stage, "errors": list(best.get("errors", []))})
    except Exception as error:
        result.append({"id": "best_practice_qc", "required": True, "status": "blocked", "errors": [f"best-practice QC exception: {error}"]})
    try:
        try:
            import teaching_qc
        except ImportError:
            from scripts import teaching_qc
        teaching = teaching_qc.run_checks(project, manifest, strict=True, stage=teaching_stage)
        if teaching.get("required"):
            result.append({"id": "teaching_qc", "required": True, "status": "executed" if teaching.get("passed") else "blocked", "teaching_stage": teaching_stage, "evidence_state": teaching.get("evidence_state", ""), "errors": list(teaching.get("errors", []))})
    except Exception as error:
        result.append({"id": "teaching_qc", "required": True, "status": "blocked", "errors": [f"teaching QC exception: {error}"]})
    try:
        try:
            import video_planning_audit
        except ImportError:
            from scripts import video_planning_audit
        planning = video_planning_audit.check(project)
        teaching_required = any(item.get("id") == "teaching_qc" and item.get("required") for item in result)
        if teaching_required:
            result.append({"id": "video_planning_audit", "required": True, "status": "executed" if planning.get("passed") else "blocked", "errors": [item.get("details", item.get("label", "")) for item in planning.get("checks", []) if item.get("status") == "blocked"]})
    except Exception as error:
        result.append({"id": "video_planning_audit", "required": True, "status": "blocked", "errors": [f"video planning audit exception: {error}"]})
    try:
        try:
            import naturalness_qc
        except ImportError:
            from scripts import naturalness_qc
        naturalness = naturalness_qc.run_checks(project, manifest, strict=True)
        if naturalness.get("required"):
            result.append({"id": "naturalness_qc", "required": True, "status": "executed" if naturalness.get("passed") else "blocked", "errors": list(naturalness.get("errors", []))})
    except Exception as error:
        result.append({"id": "naturalness_qc", "required": True, "status": "blocked", "errors": [f"naturalness QC exception: {error}"]})
    if contract_errors and not result:
        result.append({"id": "execution_contract", "required": True, "status": "blocked", "errors": contract_errors})
    elif contract_errors:
        result.insert(0, {"id": "execution_contract", "required": True, "status": "blocked", "errors": contract_errors})
    return result


def run(args: argparse.Namespace) -> int:
    project = Path(args.project).expanduser().resolve()
    manifest = workflow_gate.load_manifest(project)
    expected_manifest_sha256 = workflow_gate.manifest_sha256(project)
    if workflow_gate.refresh_stale(manifest, project):
        # The audit is also a state-observation entry point.  Persist route
        # expiry/fingerprint invalidation so a stale approval cannot remain
        # visible to the next command after this read-only audit.
        workflow_gate.save_manifest(project, manifest, expected_manifest_sha256)
    profile = workflow_gate.profile_for(str(manifest["account"]))
    stages: list[dict[str, Any]] = []
    all_passed = True
    ordered = workflow_gate.step_ids(manifest, required_only=False)
    for step_id in ordered:
        definition = manifest["workflow"]["steps"][step_id]
        if not definition.get("required"):
            stages.append({
                "id": step_id,
                "order": definition.get("order"),
                "label": definition.get("label", step_id),
                "required": False,
                "workflow_status": "not_required",
                "check_passed": True,
                "errors": [],
                "warnings": [],
                "blocked_by": [],
            })
            continue
        index = ordered.index(step_id)
        blocked_by = [
            previous
            for previous in ordered[:index]
            if manifest["workflow"]["steps"][previous].get("required")
            and manifest["workflow"]["steps"][previous].get("status") != "approved"
        ]
        try:
            result = workflow_gate.CHECKERS[step_id](project, manifest, profile)
            errors = list(result.get("errors", []))
            warnings = list(result.get("warnings", []))
            check_passed = not errors
        except Exception as error:  # a malformed stage must be visible in the audit
            errors = [f"checker exception: {error}"]
            warnings = []
            check_passed = False
        workflow_status = str(definition.get("status", "pending"))
        if blocked_by:
            workflow_status = "blocked"
        elif workflow_status != "approved" and check_passed:
            workflow_status = "pending-approval"
        elif not check_passed:
            workflow_status = "failed"
        stage = {
            "id": step_id,
            "order": definition.get("order"),
            "label": definition.get("label", step_id),
            "required": True,
            "workflow_status": workflow_status,
            "check_passed": check_passed,
            "errors": errors,
            "warnings": warnings,
            "blocked_by": blocked_by,
        }
        stages.append(stage)
        all_passed = all_passed and check_passed and not blocked_by and workflow_status == "approved"
    report = {
        "schema_version": 1,
        "content_id": manifest.get("content_id", ""),
        "account": manifest.get("account", ""),
        "audited_at": now(),
        "strict": bool(args.strict),
        "status": "ready" if all_passed else "blocked",
        "passed": all_passed,
        "stages": stages,
        "sub_stages": audit_sub_stages(project, manifest, profile),
    }
    output = Path(args.output or manifest["paths"].get("workflow_audit", "05_publish/workflow-audit.json")).expanduser()
    if not output.is_absolute():
        output = project / output
    output = output.resolve()
    write_json(output, report)
    output.with_suffix(".md").write_text(markdown(report), encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] or not args.strict else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit all serial content-production gates without approving them.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--output")
    parser.add_argument("--strict", action="store_true")
    parser.set_defaults(handler=run)
    return parser


if __name__ == "__main__":
    arguments = build_parser().parse_args()
    raise SystemExit(arguments.handler(arguments))
