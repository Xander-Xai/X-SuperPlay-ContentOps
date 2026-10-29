#!/usr/bin/env python3
"""Cross-artifact claim, evidence and platform-packaging contract.

The workflow already has separate research, copy and teaching checks.  This
module supplies the shared contract between them so a planned proof slot can
never be silently promoted to an observed result, and so the title/hook/body
cannot drift away from the selected claim.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

try:
    from teaching_qc import DIRECT_EVIDENCE_TYPES, normalize_evidence_type
except ImportError:  # imported as scripts.copy_evidence_contract
    from scripts.teaching_qc import DIRECT_EVIDENCE_TYPES, normalize_evidence_type


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "configs" / "copy-evidence-policy.json"
CLAIM_STATUSES = {"verified", "approved", "confirmed", "primary"}
FACT_STATUSES = {"planned", "observed", "verified", "inference", "hypothesis"}
EVIDENCE_STATES = {"planned", "captured", "verified", "not_applicable"}
CLAIM_MODES = {"exact", "evidence", "explanation", "illustrative", "transition"}
NARRATIVE_ROLES = {"hook", "body", "close"}


def load_policy() -> dict[str, Any]:
    value = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("copy-evidence policy must be an object")
    return value


def _norm(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").casefold())


def _metadata(text: str, key: str) -> str:
    match = re.search(rf"(?im)^[-*]\s*{re.escape(key)}\s*:\s*(.+?)\s*$", text)
    return match.group(1).strip() if match else ""


def _split_ids(value: Any) -> set[str]:
    if isinstance(value, list):
        values = value
    else:
        values = str(value or "").split("|")
    return {str(item).strip() for item in values if str(item).strip()}


def _path(project: Path, manifest: dict[str, Any], key: str, default: str) -> Path:
    paths = manifest.get("paths", {}) if isinstance(manifest.get("paths"), dict) else {}
    candidate = (project / str(paths.get(key, default))).resolve()
    candidate.relative_to(project.resolve())
    return candidate


def _rows(path: Path) -> list[dict[str, str]]:
    import csv

    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def validate(
    project: Path,
    manifest: dict[str, Any],
    contract: dict[str, Any],
    script_text: str,
    claims_registry: dict[str, Any] | None,
    storyboard_rows: list[dict[str, str]],
    *,
    stage: str = "review",
    ledger_ids: set[str] | None = None,
) -> list[str]:
    """Return deterministic errors for the current claim/evidence contract."""
    policy = load_policy()
    errors: list[str] = []
    if contract.get("schema_version") != 3:
        errors.append("teaching contract schema_version must be 3")
    stage = str(stage or "review").strip().lower()
    if stage not in {"review", "quality"}:
        errors.append(f"copy evidence contract stage is invalid: {stage or '<empty>'}")

    evidence_policy = contract.get("evidence_policy") if isinstance(contract.get("evidence_policy"), dict) else {}
    for field in ("title_promise", "primary_claim_id", "hook_claim_id", "packaging_structure"):
        if not str(evidence_policy.get(field, "")).strip():
            errors.append(f"evidence_policy missing {field}")
    if evidence_policy.get("packaging_structure") != policy["platform_packaging"]["structure"]:
        errors.append("evidence_policy.packaging_structure must be hook-body-close")
    if evidence_policy.get("claim_to_scene_required") is not True:
        errors.append("evidence_policy.claim_to_scene_required must be true")
    policy_status = str(evidence_policy.get("status", "")).strip().lower()
    if stage == "quality" and policy_status != "verified":
        errors.append("quality copy evidence contract must have evidence_policy.status=verified")
    elif stage == "review" and policy_status not in {"planned", "verified"}:
        errors.append("review copy evidence contract must have evidence_policy.status=planned or verified")

    script_fields = policy["cross_artifact_fields"]["script"]
    for field in script_fields:
        if not _metadata(script_text, field):
            errors.append(f"canonical script must declare {field} for copy evidence contract")
    if _metadata(script_text, "packaging_structure") != policy["platform_packaging"]["structure"]:
        errors.append("canonical script packaging_structure must be hook-body-close")
    if _metadata(script_text, "title_promise") and _norm(_metadata(script_text, "title_promise")) != _norm(evidence_policy.get("title_promise")):
        errors.append("canonical script title_promise does not match evidence_policy.title_promise")
    for field in ("primary_claim_id", "hook_claim_id"):
        script_value = _metadata(script_text, field)
        contract_value = str(evidence_policy.get(field, "")).strip()
        if script_value and contract_value and script_value != contract_value:
            errors.append(f"canonical script {field} does not match evidence_policy")
    if _metadata(script_text, "evidence_policy_status") and _metadata(script_text, "evidence_policy_status") != policy_status:
        errors.append("canonical script evidence_policy_status does not match evidence_policy")

    claims = contract.get("core_claims") if isinstance(contract.get("core_claims"), list) else []
    claim_map = {str(item.get("claim_id", "")).strip(): item for item in claims if isinstance(item, dict) and str(item.get("claim_id", "")).strip()}
    if not claim_map:
        errors.append("copy evidence contract requires at least one core claim")
    primary = str(evidence_policy.get("primary_claim_id", "")).strip()
    hook = str(evidence_policy.get("hook_claim_id", "")).strip()
    if primary and primary not in claim_map:
        errors.append("evidence_policy.primary_claim_id is not in core_claims")
    if hook and hook not in claim_map:
        errors.append("evidence_policy.hook_claim_id is not in core_claims")
    if len([item for item in claims if isinstance(item, dict) and item.get("importance") == "primary"]) > int(policy["claim_contract"]["max_primary_claims"]):
        errors.append("copy evidence contract allows at most one primary claim")

    registry_map: dict[str, dict[str, Any]] = {}
    if claims_registry is None:
        errors.append("copy evidence contract requires claims registry")
    else:
        for item in claims_registry.get("claims", []) if isinstance(claims_registry.get("claims"), list) else []:
            if isinstance(item, dict) and str(item.get("claim_id", "")).strip():
                registry_map[str(item["claim_id"]).strip()] = item
    for claim_id, claim in claim_map.items():
        if claim_id not in registry_map:
            errors.append(f"core claim {claim_id} is missing from research claims registry")
            continue
        registry_status = str(registry_map[claim_id].get("status", "")).strip().lower()
        if registry_status not in CLAIM_STATUSES:
            errors.append(f"research claim {claim_id} has unaccepted status {registry_status or '<empty>'}")
        if not str(registry_map[claim_id].get("text", registry_map[claim_id].get("statement", ""))).strip():
            errors.append(f"research claim {claim_id} has no source statement")
        if str(claim.get("evidence_level", "")).strip().lower() == "official" and not _split_ids(registry_map[claim_id].get("sources", [])):
            errors.append(f"official claim {claim_id} must reference at least one source")

    storyboard_columns = set(storyboard_rows[0].keys()) if storyboard_rows else set()
    for field in policy["cross_artifact_fields"]["storyboard"]:
        if field not in storyboard_columns:
            errors.append(f"storyboard must declare {field} for copy evidence contract")
    scene_claims: dict[str, list[dict[str, str]]] = {}
    for index, row in enumerate(storyboard_rows, 1):
        scene_id = str(row.get("scene_id", index)).strip() or str(index)
        role = str(row.get("narrative_role", "")).strip().lower()
        state = str(row.get("evidence_state", "")).strip().lower()
        mode = str(row.get("claim_mode", "")).strip().lower()
        fact_status = str(row.get("fact_status", "")).strip().lower()
        claim_id = str(row.get("claim_id", "")).strip()
        if role not in NARRATIVE_ROLES:
            errors.append(f"scene {scene_id} narrative_role must be hook, body or close")
        if state not in EVIDENCE_STATES:
            errors.append(f"scene {scene_id} evidence_state must be planned, captured, verified or not_applicable")
        if mode not in CLAIM_MODES:
            errors.append(f"scene {scene_id} claim_mode is invalid")
        if fact_status not in FACT_STATUSES:
            errors.append(f"scene {scene_id} fact_status is invalid")
        if claim_id:
            scene_claims.setdefault(claim_id, []).append(row)
            if claim_id not in claim_map:
                errors.append(f"scene {scene_id} references unknown claim_id {claim_id}")
        evidence_type = normalize_evidence_type(row.get("evidence_type", ""))
        is_direct = evidence_type in DIRECT_EVIDENCE_TYPES
        if is_direct:
            if mode not in {"exact", "evidence"}:
                errors.append(f"scene {scene_id} direct evidence requires claim_mode=exact or evidence")
            if not claim_id:
                errors.append(f"scene {scene_id} direct evidence requires claim_id")
            if not str(row.get("evidence_asset_id", "")).strip():
                errors.append(f"scene {scene_id} direct evidence requires evidence_asset_id")
            if stage == "quality" and state != "verified":
                errors.append(f"scene {scene_id} direct evidence must have evidence_state=verified in quality")
            if stage == "review" and state == "planned" and fact_status in {"observed", "verified"}:
                errors.append(f"scene {scene_id} planned evidence cannot have fact_status={fact_status}")
        elif claim_id and mode in {"exact", "evidence"}:
            errors.append(f"scene {scene_id} non-direct visual cannot carry exact/evidence claim_mode")
        if stage == "quality" and state == "verified" and ledger_ids is not None:
            missing = _split_ids(row.get("evidence_asset_id", "")) - ledger_ids
            if missing:
                errors.append(f"scene {scene_id} verified evidence assets missing from ledger: {'|'.join(sorted(missing))}")

    if storyboard_rows:
        first_role = str(storyboard_rows[0].get("narrative_role", "")).strip().lower()
        last_role = str(storyboard_rows[-1].get("narrative_role", "")).strip().lower()
        if first_role != "hook":
            errors.append("storyboard first scene must be narrative_role=hook")
        if last_role != "close":
            errors.append("storyboard last scene must be narrative_role=close")
        first_claim = str(storyboard_rows[0].get("claim_id", "")).strip()
        if hook and first_claim != hook:
            errors.append("storyboard hook scene claim_id does not match evidence_policy.hook_claim_id")

    for claim_id in claim_map:
        mapped = scene_claims.get(claim_id, [])
        if not mapped:
            errors.append(f"core claim {claim_id} has no storyboard scene")
        elif not any(normalize_evidence_type(row.get("evidence_type", "")) in DIRECT_EVIDENCE_TYPES for row in mapped):
            errors.append(f"core claim {claim_id} has no direct evidence scene")
    return sorted(set(errors))
