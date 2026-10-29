#!/usr/bin/env python3
"""Validate the teaching/evidence contract for an instructional video.

The regular creative checks answer "does this look like a video?".  This
module answers the stricter question: "does every important claim show a
reproducible operation, evidence and bounded conclusion?" Every active package
uses the same current contract. ``review`` mode checks planned evidence slots;
``quality`` mode checks actual ledger-backed execution receipts.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any


EVIDENCE_TYPES = {
    "screen_recording",
    "terminal",
    "source_file",
    "before_after",
    "official_page",
    "user_owned",
    "data_chart",
    "editable_diagram",
    "concept_illustration",
    "digital_human_explain",
    "text_card",
}

# Storyboard producers have historically used two descriptive aliases for
# canonical evidence types.  Normalize them at the consumer boundary so a
# vocabulary spelling change cannot invalidate an otherwise valid storyboard.
EVIDENCE_TYPE_ALIASES = {
    "official_screen_recording": "screen_recording",
    "illustrative_concept": "concept_illustration",
}


def normalize_evidence_type(value: Any) -> str:
    evidence_type = str(value or "").strip().lower()
    return EVIDENCE_TYPE_ALIASES.get(evidence_type, evidence_type)


DIRECT_EVIDENCE_TYPES = {
    "screen_recording",
    "terminal",
    "source_file",
    "before_after",
    "official_page",
    "user_owned",
    "data_chart",
}
COMPARATIVE_MARKERS = ("更快", "更清晰", "更稳定", "更适合", "提升", "降低", "优于", "对比", "基准", "更好")
EVIDENCE_RANK = {"hypothesis": 0, "user_owned": 1, "local_test": 2, "official": 3}
REQUIRED_SCENE_FIELDS = (
    "viewer_job",
    "operation",
    "input_condition",
    "changed_variable",
    "checkpoint",
    "evidence_type",
    "evidence_asset_id",
    "metric",
    "result",
    "boundary",
    "conclusion_dependency",
)
REQUIRED_CLAIM_FIELDS = (
    "viewer_job",
    "operation",
    "input_condition",
    "changed_variable",
    "checkpoint",
    "metric",
    "result",
    "boundary",
    "conclusion_dependency",
)
TEACHING_STAGES = {"review", "quality"}


def load_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def metadata(text: str, key: str) -> str:
    match = re.search(rf"(?im)^-\s*{re.escape(key)}\s*:\s*([^\n]+)$", text)
    return match.group(1).strip() if match else ""


def _path(project: Path, manifest: dict[str, Any], key: str, default: str) -> Path:
    paths = manifest.get("paths", {}) if isinstance(manifest.get("paths"), dict) else {}
    value = str(paths.get(key, default))
    candidate = (project / value).resolve()
    candidate.relative_to(project.resolve())
    return candidate


def requirement(project: Path, manifest: dict[str, Any]) -> str:
    return str(_path(project, manifest, "teaching_contract", "04_video/teaching-contract.json"))


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _planned_asset_ids(project: Path, manifest: dict[str, Any]) -> set[str]:
    """Collect declared evidence slots without treating them as acquired media.

    The director plan is the canonical scene/asset plan.  The storyboard and
    evidence plan are accepted as compatibility sources so review can proceed
    before Assets creates rights-bearing ledger rows.
    """
    planned: set[str] = set()
    director_path = _path(project, manifest, "director_plan", "04_video/director-material-plan.json")
    director = load_json(director_path, {})
    scenes = director.get("scenes", []) if isinstance(director, dict) else []
    for scene in scenes if isinstance(scenes, list) else []:
        if isinstance(scene, dict):
            asset_id = str(scene.get("asset_id", "")).strip()
            if asset_id:
                planned.add(asset_id)
            for value in scene.get("evidence_asset_ids", []) if isinstance(scene.get("evidence_asset_ids"), list) else []:
                if str(value).strip():
                    planned.add(str(value).strip())
    evidence_path = _path(project, manifest, "evidence_plan", "01_research/evidence-plan.json")
    evidence = load_json(evidence_path, {})
    for claim in evidence.get("claims", []) if isinstance(evidence, dict) and isinstance(evidence.get("claims"), list) else []:
        if isinstance(claim, dict):
            values = claim.get("evidence_asset_ids", claim.get("asset_ids", []))
            if isinstance(values, list):
                planned.update(str(value).strip() for value in values if str(value).strip())
    for value in evidence.get("asset_ids", []) if isinstance(evidence, dict) and isinstance(evidence.get("asset_ids"), list) else []:
        if str(value).strip():
            planned.add(str(value).strip())
    storyboard_path = _path(project, manifest, "storyboard", "04_video/storyboard.csv")
    for row in _rows(storyboard_path):
        planned.update(_split_ids(row.get("evidence_asset_id", "")))
    return planned


def _duration(row: dict[str, str]) -> float:
    try:
        return max(0.0, float(row.get("out", 0) or 0) - float(row.get("in", 0) or 0))
    except (TypeError, ValueError):
        return 0.0


def _split_ids(value: Any) -> set[str]:
    if isinstance(value, list):
        items = value
    else:
        items = str(value or "").split("|")
    return {str(item).strip() for item in items if str(item).strip()}


def run_checks(
    project: Path,
    manifest: dict[str, Any] | None = None,
    *,
    strict: bool = True,
    stage: str = "quality",
) -> dict[str, Any]:
    project = project.resolve()
    manifest = manifest if isinstance(manifest, dict) else (load_json(project / "content.json", {}) or {})
    stage_mode = str(stage or "").strip().lower()
    if stage_mode not in TEACHING_STAGES:
        return {
            "schema_version": 1,
            "status": "blocked",
            "passed": False,
            "required": True,
            "stage_mode": stage_mode,
            "errors": [f"invalid teaching QC stage: {stage_mode or '<empty>'}; choose review or quality"],
            "warnings": [],
            "metrics": {},
        }
    contract_ref = requirement(project, manifest)
    errors: list[str] = []
    warnings: list[str] = []
    contract_path = Path(contract_ref)
    contract = load_json(contract_path)
    if not isinstance(contract, dict):
        errors.append(f"teaching contract is missing or invalid: {contract_path}")
        contract = {}
    if contract.get("status") not in {"ready", "approved"}:
        errors.append(f"teaching contract must be ready or approved before {stage_mode}")
    try:
        from copy_evidence_contract import validate as validate_copy_evidence
    except ImportError:  # imported as scripts.teaching_qc
        from scripts.copy_evidence_contract import validate as validate_copy_evidence
    for field in ("learning_objective", "audience_starting_point"):
        if not str(contract.get(field, "")).strip():
            errors.append(f"teaching contract missing {field}")

    claims = contract.get("core_claims") if isinstance(contract.get("core_claims"), list) else []
    claim_map: dict[str, dict[str, Any]] = {}
    evidence_floor = str(contract.get("evidence_floor", "hypothesis")).strip().lower()
    floor_rank = EVIDENCE_RANK.get(evidence_floor, 0)
    if evidence_floor not in EVIDENCE_RANK:
        errors.append(f"invalid evidence_floor: {evidence_floor}")
    for index, claim in enumerate(claims, 1):
        if not isinstance(claim, dict):
            errors.append(f"core_claims[{index}] is not an object")
            continue
        claim_id = str(claim.get("claim_id", "")).strip()
        if not claim_id:
            errors.append(f"core_claims[{index}] is missing claim_id")
            continue
        if claim_id in claim_map:
            errors.append(f"duplicate claim_id: {claim_id}")
        claim_map[claim_id] = claim
        if claim.get("status") != "verified":
            errors.append(f"claim {claim_id} is not verified")
        evidence_level = str(claim.get("evidence_level", "")).strip().lower()
        if evidence_level not in EVIDENCE_RANK:
            errors.append(f"claim {claim_id} has invalid evidence_level: {evidence_level or '<empty>'}")
        elif EVIDENCE_RANK[evidence_level] < floor_rank:
            errors.append(f"claim {claim_id} evidence_level {evidence_level} is below floor {evidence_floor}")
        for field in REQUIRED_CLAIM_FIELDS:
            if not str(claim.get(field, "")).strip():
                errors.append(f"claim {claim_id} missing {field}")
        assets = claim.get("evidence_asset_ids")
        if not isinstance(assets, list) or not any(str(item).strip() for item in assets):
            errors.append(f"claim {claim_id} needs at least one evidence_asset_id")

    conclusion = contract.get("conclusion") if isinstance(contract.get("conclusion"), dict) else {}
    for field in ("verdict", "next_step"):
        if not str(conclusion.get(field, "")).strip():
            errors.append(f"conclusion missing {field}")
    for field in ("if_then_rules", "costs", "boundaries"):
        value = conclusion.get(field)
        if not isinstance(value, list) or not any(str(item).strip() for item in value):
            errors.append(f"conclusion missing {field}")

    storyboard_path = _path(project, manifest, "storyboard", "04_video/storyboard.csv")
    rows = _rows(storyboard_path)
    if not rows:
        errors.append("teaching QC requires a non-empty storyboard")
    ledger_path = _path(project, manifest, "asset_ledger", "03_assets/asset-ledger.csv")
    ledger: set[str] = set()
    if ledger_path.is_file():
        with ledger_path.open("r", encoding="utf-8-sig", newline="") as handle:
            ledger = {str(row.get("asset_id", "")).strip() for row in csv.DictReader(handle) if str(row.get("asset_id", "")).strip()}
    claims_path = _path(project, manifest, "claims", "01_research/claims.json")
    claims_registry = load_json(claims_path, None) if claims_path.is_file() else None
    script_path = _path(project, manifest, "video_script", "04_video/video-script.md")
    script_text = script_path.read_text(encoding="utf-8", errors="replace") if script_path.is_file() else ""
    errors.extend(
        f"copy evidence contract: {item}"
        for item in validate_copy_evidence(
            project,
            manifest,
            contract,
            script_text,
            claims_registry,
            rows,
            stage=stage_mode,
            ledger_ids=ledger,
        )
    )
    planned_assets = _planned_asset_ids(project, manifest)
    required_asset_ids: set[str] = set()

    scene_claims: dict[str, list[dict[str, str]]] = {}
    proof_scene_count = 0
    avatar_explain_count = 0
    for row in rows:
        claim_id = str(row.get("claim_id", "")).strip()
        if not claim_id:
            if str(row.get("avatar_window", "none")).strip().lower() != "none":
                avatar_explain_count += 1
            continue
        scene_claims.setdefault(claim_id, []).append(row)
        missing = [field for field in REQUIRED_SCENE_FIELDS if not str(row.get(field, "")).strip()]
        if missing:
            errors.append(f"scene {row.get('scene_id', '?')} claim {claim_id} missing: {', '.join(missing)}")
        evidence_type = normalize_evidence_type(row.get("evidence_type", ""))
        if evidence_type not in EVIDENCE_TYPES:
            errors.append(f"scene {row.get('scene_id', '?')} has invalid evidence_type: {evidence_type or '<empty>'}")
        elif evidence_type in {"concept_illustration", "digital_human_explain", "text_card"}:
            warnings.append(f"scene {row.get('scene_id', '?')} uses non-direct evidence type {evidence_type}")
        else:
            proof_scene_count += 1
        asset_ids = _split_ids(row.get("evidence_asset_id", ""))
        required_asset_ids.update(asset_ids)
        if stage_mode == "quality":
            missing_assets = sorted(asset_ids - ledger) if ledger else sorted(asset_ids)
            if missing_assets:
                errors.append(f"scene {row.get('scene_id', '?')} evidence assets are not in asset ledger: {'|'.join(missing_assets)}")
        else:
            unplanned_assets = sorted(asset_ids - planned_assets)
            if unplanned_assets:
                errors.append(f"scene {row.get('scene_id', '?')} evidence assets are not declared in the director/evidence plan: {'|'.join(unplanned_assets)}")
        if str(row.get("avatar_window", "none")).strip().lower() != "none":
            avatar_explain_count += 1

    for claim_id in claim_map:
        if claim_id not in scene_claims:
            errors.append(f"claim {claim_id} has no storyboard scene")
        else:
            claim_assets = _split_ids(claim_map[claim_id].get("evidence_asset_ids", []))
            required_asset_ids.update(claim_assets)
            if stage_mode == "review":
                unplanned_claim_assets = sorted(claim_assets - planned_assets)
                if unplanned_claim_assets:
                    errors.append(f"claim {claim_id} evidence assets are not declared in the director/evidence plan: {'|'.join(unplanned_claim_assets)}")
            else:
                missing_claim_assets = sorted(claim_assets - ledger) if ledger else sorted(claim_assets)
                if missing_claim_assets:
                    errors.append(f"claim {claim_id} evidence assets are not in asset ledger: {'|'.join(missing_claim_assets)}")
            scene_assets = set().union(*(_split_ids(row.get("evidence_asset_id", "")) for row in scene_claims[claim_id]))
            if claim_assets and not claim_assets.intersection(scene_assets):
                errors.append(f"claim {claim_id} evidence assets are not linked from its scenes")
            if not any(normalize_evidence_type(row.get("evidence_type", "")) in DIRECT_EVIDENCE_TYPES for row in scene_claims[claim_id]):
                errors.append(f"claim {claim_id} has no direct evidence scene")
            statement = str(claim_map[claim_id].get("statement", ""))
            if any(marker in statement for marker in COMPARATIVE_MARKERS):
                evidence_types = {normalize_evidence_type(row.get("evidence_type", "")) for row in scene_claims[claim_id]}
                if not evidence_types.intersection({"before_after", "data_chart"}) and len(scene_claims[claim_id]) < 2:
                    errors.append(f"comparative claim {claim_id} needs before_after/data_chart or at least two evidence scenes")

    rhythm = contract.get("rhythm") if isinstance(contract.get("rhythm"), dict) else {}
    theory_limit = float(rhythm.get("theory_streak_max_seconds", 8) or 8)
    evidence_interval = float(rhythm.get("evidence_interval_seconds", 20) or 20)
    theory_streak = 0.0
    max_theory_streak = 0.0
    evidence_gap = 0.0
    since_evidence = 0.0
    for row in rows:
        duration = _duration(row)
        evidence_type = normalize_evidence_type(row.get("evidence_type", ""))
        is_direct = evidence_type in DIRECT_EVIDENCE_TYPES
        role = str(row.get("pacing_role", "")).strip().lower()
        is_theory = role in {"theory", "explain", "question", "method"} or (not is_direct and bool(str(row.get("voice", "")).strip()))
        theory_streak = theory_streak + duration if is_theory else 0.0
        max_theory_streak = max(max_theory_streak, theory_streak)
        since_evidence = 0.0 if is_direct else since_evidence + duration
        evidence_gap = max(evidence_gap, since_evidence)
    if rhythm.get("mode") == "validated" and max_theory_streak > theory_limit:
        errors.append(f"theory streak {max_theory_streak:.1f}s exceeds validated limit {theory_limit:g}s")
    if rhythm.get("mode") == "validated" and evidence_gap > evidence_interval:
        errors.append(f"evidence gap {evidence_gap:.1f}s exceeds validated interval {evidence_interval:g}s")
    if rhythm.get("mode") == "hypothesis":
        warnings.append("rhythm thresholds are hypotheses; run A/B and comprehension tests before marking validated")

    trust = contract.get("synthetic_trust") if isinstance(contract.get("synthetic_trust"), dict) else {}
    if avatar_explain_count and trust.get("evidence_exclusion") is not True:
        errors.append("synthetic presenter scenes require evidence_exclusion=true")
    if avatar_explain_count and trust.get("disclosure_required") is not True:
        errors.append("synthetic presenter scenes require disclosure_required=true")

    unresolved_planned = sorted(required_asset_ids - ledger)
    metrics = {
        "claim_count": len(claim_map),
        "mapped_claim_count": len(set(scene_claims).intersection(claim_map)),
        "proof_scene_count": proof_scene_count,
        "avatar_explain_scene_count": avatar_explain_count,
        "max_theory_streak_seconds": round(max_theory_streak, 3),
        "max_evidence_gap_seconds": round(evidence_gap, 3),
        "rhythm_mode": rhythm.get("mode", ""),
        "conclusion_complete": not any(f"conclusion missing {field}" in errors for field in ("verdict", "next_step", "if_then_rules", "costs", "boundaries")),
        "planned_asset_count": len(planned_assets),
        "required_evidence_asset_count": len(required_asset_ids),
        "registered_asset_count": len(ledger),
        "unresolved_planned_asset_count": len(unresolved_planned),
    }
    contract_payload = dict(contract)
    contract_payload.pop("status", None)
    contract_payload.pop("review", None)
    contract_sha256 = hashlib.sha256(json.dumps(contract_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    execution_receipt_sha256 = _sha256(ledger_path)
    return {
        "schema_version": 1,
        "status": ("review-ready" if stage_mode == "review" else "ready") if not errors else "blocked",
        "passed": not errors,
        "required": True,
        "stage_mode": stage_mode,
        "evidence_state": "planned" if stage_mode == "review" else "actual",
        "contract": str(contract_path),
        "contract_sha256": contract_sha256,
        "execution_receipt": {
            "asset_ledger": str(ledger_path),
            "asset_ledger_sha256": execution_receipt_sha256,
            "registered_asset_count": len(ledger),
            "state": "planned" if stage_mode == "review" else "actual",
        },
        "derived_report": {
            "kind": "teaching-qc",
            "stage_mode": stage_mode,
            "contract_layer": "immutable-contract",
            "execution_layer": "asset-ledger-and-provenance-receipts",
            "report_layer": "regenerable-derived-audit",
        },
        "storyboard": str(storyboard_path),
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
        "metrics": metrics,
    }


def main(args: argparse.Namespace) -> int:
    project = Path(args.project).expanduser().resolve()
    manifest = load_json(project / "content.json", {}) or {}
    report = run_checks(project, manifest, strict=args.strict, stage=args.stage)
    output_value = str((manifest.get("paths", {}) if isinstance(manifest.get("paths"), dict) else {}).get("teaching_qc", "05_publish/teaching-qc.json"))
    output = project / output_value
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] or not args.strict else 1


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Validate instructional claims, evidence, rhythm and conclusion coverage.")
    root.add_argument("--project", required=True)
    root.add_argument("--strict", action="store_true")
    root.add_argument("--stage", choices=sorted(TEACHING_STAGES), default="quality", help="review checks planned evidence; quality requires actual ledger/provenance evidence")
    root.set_defaults(handler=main)
    return root


if __name__ == "__main__":
    arguments = parser().parse_args()
    raise SystemExit(arguments.handler(arguments))
