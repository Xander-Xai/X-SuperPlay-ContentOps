#!/usr/bin/env python3
"""Build, validate and apply the Audience Lens v3 topic-level research contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

try:
    from console_encoding import configure_utf8_stdio
except ImportError:  # imported as scripts.audience_insight
    from scripts.console_encoding import configure_utf8_stdio

configure_utf8_stdio()

try:
    from runtime_context import ACCOUNT
except ImportError:  # imported as scripts.audience_insight
    from scripts.runtime_context import ACCOUNT

try:
    from canonical_workflow import LEGACY_CONTRACT_ID, SUPPORTED_CONTRACT_IDS
except ImportError:  # imported as scripts.audience_insight
    from scripts.canonical_workflow import LEGACY_CONTRACT_ID, SUPPORTED_CONTRACT_IDS

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "audience-segments.json"
DEFAULT_ARTIFACT_PATH = "01_research/audience-insight.json"
VIEWER_PROGRESS_STRUCTURE = "recognition-tension-promise-discovery-proof-meaning-action"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def project_path(project: Path, raw: str) -> Path:
    """Resolve a package artifact path and reject absolute or escaping paths."""
    value = str(raw).strip()
    if not value:
        raise ValueError("artifact path is empty")
    candidate = Path(value).expanduser()
    if candidate.is_absolute():
        raise ValueError(f"artifact path must be relative to project: {value}")
    project_root = project.expanduser().resolve()
    resolved = (project_root / candidate).resolve()
    try:
        resolved.relative_to(project_root)
    except ValueError as error:
        raise ValueError(f"artifact path escapes project: {value}") from error
    return resolved


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audience_config() -> dict[str, Any]:
    payload = load_json(CONFIG_PATH)
    if payload.get("schema_version") != 3:
        raise ValueError("audience segment config schema_version must be 3")
    return payload


def _segment_catalog(config: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    config = config or audience_config()
    segments = config.get("segments") if isinstance(config.get("segments"), dict) else {}
    return {str(key): value for key, value in segments.items() if isinstance(value, dict)}


def segment_candidates(content_type: str = "", pillar: str = "") -> list[dict[str, Any]]:
    """Suggest all three segments without selecting one on the editor's behalf."""
    segments = _segment_catalog()
    rows: list[dict[str, Any]] = []
    for segment_id, segment in segments.items():
        affinity = [str(item) for item in segment.get("content_type_affinity", [])]
        suggested = bool(content_type and content_type in affinity)
        affinity_rank = affinity.index(content_type) if suggested else len(affinity) + 100
        reason = (
            f"{content_type} 常见于该受众的进展任务；仍需受众证据确认"
            if suggested
            else "保留为候选；内容支柱不能自动排除或锁定该受众"
        )
        rows.append({
            "segment_id": segment_id,
            "label": str(segment.get("label", "")),
            "suggested": suggested,
            "suggestion_rank": affinity_rank if suggested else None,
            "reason": reason,
            "pillar_context": pillar,
        })
    return sorted(
        rows,
        key=lambda item: (
            not item["suggested"],
            item["suggestion_rank"] if item["suggestion_rank"] is not None else 999,
            item["segment_id"],
        ),
    )


def build_scaffold(
    content_id: str,
    topic: str,
    *,
    account: str = ACCOUNT,
    content_type: str = "",
    pillar: str = "",
) -> dict[str, Any]:
    return {
        "schema_version": 3,
        "content_id": content_id,
        "account": account,
        "topic": topic,
        "content_type_context": content_type,
        "pillar_context": pillar,
        "status": "pending",
        "fit_status": "pending",
        "candidate_segments": segment_candidates(content_type, pillar),
        "segment_decision": {
            "primary_segment_id": "",
            "secondary_segment_ids": [],
            "excluded_segment_ids": [],
            "identity_facets": [],
            "rationale": "",
        },
        "viewer_context": {
            "viewing_trigger": "",
            "situation": "",
            "current_workaround": "",
            "awareness_level": "",
            "existing_belief": "",
            "stakes": "",
        },
        "progress_contract": {
            "functional_job": "",
            "emotional_job": "",
            "social_job": "",
            "before_state": "",
            "desired_after_state": "",
        },
        "objections": [],
        "proof_expectations": [],
        "evidence": [],
        "language_bank": [],
        "value_contract": {
            "primary_dimension": "",
            "secondary_dimensions": [],
            "practical": "",
            "epistemic": "",
            "emotional": "",
            "social_identity": "",
            "participation": "",
            "primary_promise": "",
            "meaning_for_viewer": "",
        },
        "emotional_arc": {
            "start_state": "",
            "recognition_cue": "",
            "turning_evidence": "",
            "end_state": "",
        },
        "research_confidence": {"level": "unresearched", "reason": ""},
        "experiment_contract": {
            "hypothesis": "",
            "learning_question": "",
            "success_signal": "",
            "cta_learning_prompt": "",
        },
        "notes": [
            "候选受众不是已选受众；必须根据本主题的真实信号选择一个 primary segment。",
            "没有直接受众信号时可标记 exploratory，但必须保留来源、学习问题和反馈型 CTA。",
        ],
    }


def _nonempty(value: Any) -> bool:
    return bool(str(value).strip())


def validate_audience_insight(payload: dict[str, Any], *, require_ready: bool = True) -> list[str]:
    config = audience_config()
    segments = _segment_catalog(config)
    valid_segment_ids = set(segments)
    identity_facets = {str(item) for item in config.get("identity_facets", [])}
    value_dimensions = set((config.get("value_dimensions") or {}).keys())
    awareness_levels = {str(item) for item in config.get("awareness_levels", [])}
    emotional_jobs = {str(item) for item in config.get("emotional_jobs", [])}
    source_statuses = {str(item) for item in config.get("source_statuses", [])}
    source_types = {str(item) for item in config.get("source_types", [])}
    direct_source_types = {str(item) for item in config.get("direct_source_types", [])}
    policy = config.get("research_policy") if isinstance(config.get("research_policy"), dict) else {}
    errors: list[str] = []

    for field in ("content_id", "account", "topic", "status", "fit_status"):
        if not _nonempty(payload.get(field)):
            errors.append(f"audience insight {field} is required")
    if payload.get("account") != ACCOUNT:
        errors.append(f"audience insight account must be {ACCOUNT}")
    if payload.get("schema_version") != 3:
        errors.append("audience insight schema_version must be 3")

    candidates = payload.get("candidate_segments")
    candidate_ids = {
        str(item.get("segment_id", "")).strip()
        for item in candidates or []
        if isinstance(item, dict) and _nonempty(item.get("segment_id"))
    }
    if (
        not isinstance(candidates, list)
        or len(candidates) != len(valid_segment_ids)
        or candidate_ids != valid_segment_ids
    ):
        errors.append("candidate_segments must expose every registered audience segment without auto-selecting one")
    elif any(
        str(item.get("label", "")).strip() != str(segments[str(item.get("segment_id"))].get("label", "")).strip()
        for item in candidates
        if isinstance(item, dict)
    ):
        errors.append("candidate_segments labels must match the audience config")

    decision = payload.get("segment_decision") if isinstance(payload.get("segment_decision"), dict) else {}
    primary = str(decision.get("primary_segment_id", "")).strip()
    secondary = decision.get("secondary_segment_ids")
    excluded = decision.get("excluded_segment_ids")
    selected_facets = decision.get("identity_facets")
    if require_ready:
        if primary not in valid_segment_ids:
            errors.append("segment_decision.primary_segment_id must select one registered segment")
        if not _nonempty(decision.get("rationale")):
            errors.append("segment_decision.rationale is required")
    if not isinstance(secondary, list):
        errors.append("segment_decision.secondary_segment_ids must be an array")
        secondary = []
    if len(secondary) > int(policy.get("secondary_segment_max", 1)):
        errors.append("segment_decision allows at most one secondary segment")
    if any(str(item) not in valid_segment_ids for item in secondary):
        errors.append("segment_decision.secondary_segment_ids contains an unknown segment")
    if primary and primary in {str(item) for item in secondary}:
        errors.append("primary audience segment cannot also be secondary")
    if not isinstance(excluded, list) or any(str(item) not in valid_segment_ids for item in excluded or []):
        errors.append("segment_decision.excluded_segment_ids must contain registered segments")
    if primary and primary in {str(item) for item in excluded or []}:
        errors.append("primary audience segment cannot be excluded")
    if {str(item) for item in secondary}.intersection({str(item) for item in excluded or []}):
        errors.append("secondary audience segments cannot also be excluded")
    if not isinstance(selected_facets, list) or any(str(item) not in identity_facets for item in selected_facets or []):
        errors.append("segment_decision.identity_facets must use profile identity facets")

    viewer = payload.get("viewer_context") if isinstance(payload.get("viewer_context"), dict) else {}
    progress = payload.get("progress_contract") if isinstance(payload.get("progress_contract"), dict) else {}
    if require_ready:
        for field in ("viewing_trigger", "situation", "current_workaround", "awareness_level", "existing_belief", "stakes"):
            if not _nonempty(viewer.get(field)):
                errors.append(f"viewer_context.{field} is required")
        for field in ("functional_job", "emotional_job", "social_job", "before_state", "desired_after_state"):
            if not _nonempty(progress.get(field)):
                errors.append(f"progress_contract.{field} is required")
    if _nonempty(viewer.get("awareness_level")) and viewer.get("awareness_level") not in awareness_levels:
        errors.append("viewer_context.awareness_level is invalid")
    if _nonempty(progress.get("emotional_job")) and progress.get("emotional_job") not in emotional_jobs:
        errors.append("progress_contract.emotional_job is invalid")

    objections = payload.get("objections")
    proof_expectations = payload.get("proof_expectations")
    if require_ready and (not isinstance(objections, list) or not any(_nonempty(item) for item in objections)):
        errors.append("objections must contain at least one audience objection")
    if require_ready and (not isinstance(proof_expectations, list) or not any(_nonempty(item) for item in proof_expectations)):
        errors.append("proof_expectations must contain at least one proof requirement")

    evidence = payload.get("evidence")
    evidence = evidence if isinstance(evidence, list) else []
    source_refs: set[str] = set()
    independent_sources: set[str] = set()
    direct_sources = 0
    for index, item in enumerate(evidence, 1):
        if not isinstance(item, dict):
            errors.append(f"audience evidence {index} must be an object")
            continue
        for field in ("evidence_id", "source_type", "source_status", "source_ref", "insight"):
            if not _nonempty(item.get(field)):
                errors.append(f"audience evidence {index}.{field} is required")
        source_type = str(item.get("source_type", "")).strip()
        source_status = str(item.get("source_status", "")).strip()
        source_ref = str(item.get("source_ref", "")).strip()
        if source_type and source_type not in source_types:
            errors.append(f"audience evidence {index}.source_type is invalid")
        if source_status and source_status not in source_statuses:
            errors.append(f"audience evidence {index}.source_status is invalid")
        if source_ref:
            source_refs.add(source_ref)
            independent_sources.add(str(item.get("independent_source_id", "")).strip() or source_ref)
        if source_type in direct_source_types:
            direct_sources += 1

    language_bank = payload.get("language_bank")
    for index, item in enumerate(language_bank if isinstance(language_bank, list) else [], 1):
        if not isinstance(item, dict):
            errors.append(f"language_bank {index} must be an object")
            continue
        if not _nonempty(item.get("phrase")) or not _nonempty(item.get("source_ref")):
            errors.append(f"language_bank {index} requires phrase and source_ref")
        elif str(item.get("source_ref")) not in source_refs:
            errors.append(f"language_bank {index}.source_ref must point to audience evidence")

    fit_status = str(payload.get("fit_status", "")).strip()
    if require_ready and fit_status not in set(config.get("fit_statuses", [])):
        errors.append("fit_status must be validated, mixed or exploratory before copy strategy approval")
    if require_ready and fit_status == "validated":
        if len(independent_sources) < int(policy.get("validated_min_independent_sources", 2)):
            errors.append("validated audience fit requires at least two independent sources")
        if policy.get("validated_requires_direct_source") is True and direct_sources < 1:
            errors.append("validated audience fit requires at least one direct or owned source")
    if require_ready and fit_status in {"mixed", "exploratory"} and not evidence:
        errors.append(f"{fit_status} audience fit requires at least one documented source or research proxy")

    value = payload.get("value_contract") if isinstance(payload.get("value_contract"), dict) else {}
    primary_dimension = str(value.get("primary_dimension", "")).strip()
    secondary_dimensions = value.get("secondary_dimensions")
    if require_ready and primary_dimension not in value_dimensions:
        errors.append("value_contract.primary_dimension must select one registered value dimension")
    if not isinstance(secondary_dimensions, list):
        errors.append("value_contract.secondary_dimensions must be an array")
        secondary_dimensions = []
    if len(secondary_dimensions) > int(policy.get("secondary_value_dimension_max", 2)):
        errors.append("value_contract allows at most two secondary dimensions")
    if any(str(item) not in value_dimensions for item in secondary_dimensions):
        errors.append("value_contract.secondary_dimensions contains an unknown dimension")
    if primary_dimension and primary_dimension in {str(item) for item in secondary_dimensions}:
        errors.append("primary value dimension cannot also be secondary")
    if require_ready:
        for field in ("primary_promise", "meaning_for_viewer"):
            if not _nonempty(value.get(field)):
                errors.append(f"value_contract.{field} is required")
        for dimension in [primary_dimension, *[str(item) for item in secondary_dimensions]]:
            if dimension and not _nonempty(value.get(dimension)):
                errors.append(f"value_contract.{dimension} must explain how that selected value is delivered")

    arc = payload.get("emotional_arc") if isinstance(payload.get("emotional_arc"), dict) else {}
    if require_ready:
        for field in ("start_state", "recognition_cue", "turning_evidence", "end_state"):
            if not _nonempty(arc.get(field)):
                errors.append(f"emotional_arc.{field} is required")

    confidence = payload.get("research_confidence") if isinstance(payload.get("research_confidence"), dict) else {}
    if require_ready and confidence.get("level") not in {"low", "medium", "high"}:
        errors.append("research_confidence.level must be low, medium or high")
    if require_ready and not _nonempty(confidence.get("reason")):
        errors.append("research_confidence.reason is required")

    experiment = payload.get("experiment_contract") if isinstance(payload.get("experiment_contract"), dict) else {}
    if require_ready and fit_status == "exploratory":
        for field in ("hypothesis", "learning_question", "success_signal", "cta_learning_prompt"):
            if not _nonempty(experiment.get(field)):
                errors.append(f"exploratory audience fit requires experiment_contract.{field}")
    if require_ready and payload.get("status") not in {"ready", "approved"}:
        errors.append("audience insight status must be ready or approved")
    return errors


def lens_projection(
    insight: dict[str, Any],
    *,
    source_path: str = DEFAULT_ARTIFACT_PATH,
    source_sha256: str = "",
) -> dict[str, Any]:
    segments = _segment_catalog()
    decision = insight.get("segment_decision") if isinstance(insight.get("segment_decision"), dict) else {}
    viewer = insight.get("viewer_context") if isinstance(insight.get("viewer_context"), dict) else {}
    progress = insight.get("progress_contract") if isinstance(insight.get("progress_contract"), dict) else {}
    value = insight.get("value_contract") if isinstance(insight.get("value_contract"), dict) else {}
    primary = str(decision.get("primary_segment_id", "")).strip()
    return {
        "status": "applied" if primary and source_sha256 else "pending",
        "source_path": source_path,
        "source_sha256": source_sha256,
        "fit_status": str(insight.get("fit_status", "pending")),
        "primary_segment_id": primary,
        "primary_segment_label": str((segments.get(primary) or {}).get("label", "")),
        "secondary_segment_ids": list(decision.get("secondary_segment_ids", [])) if isinstance(decision.get("secondary_segment_ids"), list) else [],
        "identity_facets": list(decision.get("identity_facets", [])) if isinstance(decision.get("identity_facets"), list) else [],
        "viewing_trigger": str(viewer.get("viewing_trigger", "")),
        "current_workaround": str(viewer.get("current_workaround", "")),
        "awareness_level": str(viewer.get("awareness_level", "")),
        "existing_belief": str(viewer.get("existing_belief", "")),
        "stakes": str(viewer.get("stakes", "")),
        "functional_job": str(progress.get("functional_job", "")),
        "emotional_job": str(progress.get("emotional_job", "")),
        "social_job": str(progress.get("social_job", "")),
        "before_state": str(progress.get("before_state", "")),
        "desired_after_state": str(progress.get("desired_after_state", "")),
        "desired_progress": f"{progress.get('before_state', '')} → {progress.get('desired_after_state', '')}" if progress.get("before_state") or progress.get("desired_after_state") else "",
        "objections": list(insight.get("objections", [])) if isinstance(insight.get("objections"), list) else [],
        "proof_expectations": list(insight.get("proof_expectations", [])) if isinstance(insight.get("proof_expectations"), list) else [],
        "primary_value_dimension": str(value.get("primary_dimension", "")),
        "primary_value_promise": str(value.get("primary_promise", "")),
        "meaning_for_viewer": str(value.get("meaning_for_viewer", "")),
        "research_confidence": dict(insight.get("research_confidence", {})) if isinstance(insight.get("research_confidence"), dict) else {},
        "experiment_contract": dict(insight.get("experiment_contract", {})) if isinstance(insight.get("experiment_contract"), dict) else {},
    }


def validate_lens_projection(payload: dict[str, Any], *, required: bool = False) -> list[str]:
    lens = payload.get("audience_lens")
    if lens is None:
        return ["missing copy contract field: audience_lens"] if required else []
    if not isinstance(lens, dict):
        return ["audience_lens must be an object"]
    if not required and lens.get("status") == "pending":
        return []
    errors: list[str] = []
    segments = _segment_catalog()
    for field in (
        "source_path", "source_sha256", "fit_status", "primary_segment_id", "primary_segment_label",
        "viewing_trigger", "current_workaround", "functional_job", "emotional_job", "social_job", "before_state",
        "desired_after_state", "primary_value_dimension", "primary_value_promise", "meaning_for_viewer",
    ):
        if not _nonempty(lens.get(field)):
            errors.append(f"audience_lens.{field} is required")
    if lens.get("status") != "applied":
        errors.append("audience_lens.status must be applied")
    if not re.fullmatch(r"[a-f0-9]{64}", str(lens.get("source_sha256", ""))):
        errors.append("audience_lens.source_sha256 must be a 64-character sha256")
    primary = str(lens.get("primary_segment_id", ""))
    if primary not in segments:
        errors.append("audience_lens.primary_segment_id is not registered")
    elif lens.get("primary_segment_label") != segments[primary].get("label"):
        errors.append("audience_lens.primary_segment_label does not match the audience config")
    if lens.get("fit_status") not in {"validated", "mixed", "exploratory"}:
        errors.append("audience_lens.fit_status is invalid")
    if not isinstance(lens.get("objections"), list) or not lens.get("objections"):
        errors.append("audience_lens.objections must not be empty")
    if not isinstance(lens.get("proof_expectations"), list) or not lens.get("proof_expectations"):
        errors.append("audience_lens.proof_expectations must not be empty")
    return errors


def apply_to_project(project: Path) -> dict[str, Any]:
    project = project.expanduser().resolve()
    manifest = load_json(project / "content.json")
    paths = manifest.get("paths") if isinstance(manifest.get("paths"), dict) else {}
    insight_relative = str(
        paths.get("audience_insight", paths.get("canonical_audience_insight", ""))
    ).strip()
    if not insight_relative:
        return {"status": "blocked", "passed": False, "errors": ["content package paths.audience_insight is required"]}
    try:
        insight_path = project_path(project, insight_relative)
    except ValueError as error:
        return {"status": "blocked", "passed": False, "errors": [str(error)]}
    insight = load_json(insight_path)
    errors = validate_audience_insight(insight, require_ready=True)
    if insight.get("content_id") != manifest.get("content_id"):
        errors.append("audience insight content_id does not match content package")
    if insight.get("account") != manifest.get("account"):
        errors.append("audience insight account does not match content package")
    if errors:
        return {"status": "blocked", "passed": False, "errors": errors}

    digest = sha256_file(insight_path)
    lens = lens_projection(insight, source_path=insight_relative, source_sha256=digest)
    value = dict(insight.get("value_contract", {}))
    arc = dict(insight.get("emotional_arc", {}))

    # Canonical packages intentionally contain only the ten production-stage
    # directories, so they do not have the historical copy-brief,
    # copy-strategy, or teaching-contract paths that older packages expose.
    # Project the approved Audience Lens into the canonical audience artifact
    # and Brief instead of forcing a legacy package layout or asking callers to
    # bypass the production root.
    if manifest.get("workflow_contract") in SUPPORTED_CONTRACT_IDS:
        segments = _segment_catalog()
        secondary_ids = lens.get("secondary_segment_ids", [])
        secondary_labels = [
            str((segments.get(str(segment_id)) or {}).get("label", "")).strip()
            for segment_id in secondary_ids
            if str((segments.get(str(segment_id)) or {}).get("label", "")).strip()
        ]
        insight["contract"] = str(manifest.get("workflow_contract") or LEGACY_CONTRACT_ID)
        insight["primary_audience"] = lens["primary_segment_label"]
        insight["secondary_audience"] = ", ".join(secondary_labels)
        insight["viewer_tasks"] = [lens["functional_job"]]
        insight["practical_value"] = str(value.get("practical") or value.get("primary_promise", ""))
        insight["emotional_value"] = str(value.get("emotional") or lens["emotional_job"])
        insight["audience_lens"] = lens
        write_json(insight_path, insight)
        updated = [str(insight_path)]

        brief_relative = str(paths.get("canonical_brief", "00_brief/brief.json")).strip()
        try:
            brief_path = project_path(project, brief_relative)
        except ValueError as error:
            return {"status": "blocked", "passed": False, "errors": [str(error)]}
        if brief_path.is_file():
            brief = load_json(brief_path)
            brief["primary_audience"] = lens["primary_segment_label"]
            brief["secondary_audience"] = ", ".join(secondary_labels)
            brief["viewer_situation"] = str((insight.get("viewer_context") or {}).get("situation", ""))
            brief["viewer_goal"] = lens["functional_job"]
            brief["viewer_motivation"] = lens["emotional_job"]
            brief["promise"] = str(value.get("primary_promise", ""))
            brief["expected_emotion_change"] = f"{arc.get('start_state', '')} → {arc.get('end_state', '')}".strip(" →")
            write_json(brief_path, brief)
            updated.append(str(brief_path))

        digest = sha256_file(insight_path)
        return {
            "status": "applied",
            "passed": True,
            "audience_insight": str(insight_path),
            "audience_insight_sha256": digest,
            "primary_segment_id": lens["primary_segment_id"],
            "updated": updated,
            "errors": [],
        }

    updated: list[str] = []
    staged: list[tuple[Path, dict[str, Any]]] = []
    targets: list[tuple[str, Path, dict[str, Any]]] = []

    for key in ("copy_brief", "copy_strategy"):
        relative = str(paths.get(key, "")).strip()
        if not relative:
            return {"status": "blocked", "passed": False, "errors": [f"content package paths.{key} is required"]}
        try:
            target = project_path(project, relative)
        except ValueError as error:
            return {"status": "blocked", "passed": False, "errors": [str(error)]}
        if not target.is_file():
            return {"status": "blocked", "passed": False, "errors": [f"missing {key}: {target}"]}
        payload = load_json(target)
        if payload.get("content_id") != manifest.get("content_id"):
            return {"status": "blocked", "passed": False, "errors": [f"{key} content_id does not match content package"]}
        if payload.get("account") != manifest.get("account"):
            return {"status": "blocked", "passed": False, "errors": [f"{key} account does not match content package"]}
        if payload.get("schema_version") != 3:
            return {"status": "blocked", "passed": False, "errors": [f"{key} schema_version must be 3"]}
        targets.append((key, target, payload))

    teaching_relative = str(paths.get("teaching_contract", "")).strip()
    if not teaching_relative:
        return {"status": "blocked", "passed": False, "errors": ["content package paths.teaching_contract is required"]}
    try:
        teaching_path = project_path(project, teaching_relative)
    except ValueError as error:
        return {"status": "blocked", "passed": False, "errors": [str(error)]}
    if not teaching_path.is_file():
        return {"status": "blocked", "passed": False, "errors": [f"missing teaching_contract: {teaching_path}"]}
    teaching_payload = load_json(teaching_path)
    teaching_content_id = str(teaching_payload.get("content_id", "")).strip()
    if teaching_content_id and teaching_content_id != str(manifest.get("content_id", "")):
        return {"status": "blocked", "passed": False, "errors": ["teaching_contract content_id does not match content package"]}

    for key, target, payload in targets:
        payload["audience"] = lens["primary_segment_label"]
        payload["viewer_intent"] = lens["functional_job"]
        payload["audience_lens"] = lens
        payload["value_contract"] = value
        payload["emotional_arc"] = arc
        if key == "copy_brief":
            payload["viewer_progress_structure"] = VIEWER_PROGRESS_STRUCTURE
        else:
            structure = payload.setdefault("structure_contract", {})
            structure["viewer_progress_structure"] = VIEWER_PROGRESS_STRUCTURE
            positioning = payload.setdefault("positioning", {})
            positioning["audience"] = lens["primary_segment_label"]
            positioning["audience_segment_id"] = lens["primary_segment_id"]
            positioning["audience_lens"] = lens
            classification = payload.setdefault("classification", {})
            classification["audience"] = lens["primary_segment_label"]
            classification["viewer_intent"] = lens["functional_job"]
            teaching = payload.setdefault("teaching_contract", {})
            teaching["learning_objective"] = lens["functional_job"]
            teaching["practical_value"] = str(value.get("practical") or value.get("primary_promise", ""))
            teaching["value_contract"] = value
            usage = payload.setdefault("method_usage", {})
            usage["audience_research"] = True
            receipt = payload.setdefault("method_receipt", {})
            receipt["audience_research"] = {
                "status": "applied",
                "evidence": f"{insight_relative}#{digest}",
            }
        staged.append((target, payload))

    teaching_payload["learning_objective"] = lens["functional_job"]
    teaching_payload["audience_starting_point"] = lens["before_state"]
    teaching_payload["audience_lens"] = lens
    teaching_payload["value_contract"] = value
    staged.append((teaching_path, teaching_payload))

    for target, payload in staged:
        write_json(target, payload)
        updated.append(str(target))

    return {
        "status": "applied",
        "passed": True,
        "audience_insight": str(insight_path),
        "audience_insight_sha256": digest,
        "primary_segment_id": lens["primary_segment_id"],
        "updated": updated,
        "errors": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audience Lens v3 research contract")
    sub = parser.add_subparsers(dest="command", required=True)
    seed = sub.add_parser("seed")
    seed.add_argument("--content-id", required=True)
    seed.add_argument("--topic", required=True)
    seed.add_argument("--content-type", default="")
    seed.add_argument("--pillar", default="")
    seed.add_argument("--output", required=True)
    check = sub.add_parser("check")
    check.add_argument("--input", required=True)
    check.add_argument("--allow-pending", action="store_true")
    apply_parser = sub.add_parser("apply")
    apply_parser.add_argument("--project", required=True)
    args = parser.parse_args()

    if args.command == "seed":
        result = build_scaffold(args.content_id, args.topic, content_type=args.content_type, pillar=args.pillar)
        write_json(Path(args.output), result)
        errors: list[str] = []
    elif args.command == "check":
        result = load_json(Path(args.input))
        errors = validate_audience_insight(result, require_ready=not args.allow_pending)
    else:
        result = apply_to_project(Path(args.project))
        errors = list(result.get("errors", []))
    output = {"passed": not errors, "errors": errors, "result": result}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
