#!/usr/bin/env python3
"""Small deterministic Audience–Problem–Trust candidate gate.

The module owns candidate evaluation only. Evidence, Audience Lens research,
Revenue Attribution, and the ten production stages remain owned by their
existing contracts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from runtime_context import ACCOUNT
except ImportError:  # imported as scripts.content_candidate
    from scripts.runtime_context import ACCOUNT

ROOT = Path(__file__).resolve().parents[1]
POSITIONING_PATH = ROOT / "configs" / "content-positioning-v1.json"
AUDIENCE_PATH = ROOT / "configs" / "audience-segments.json"
CONTRACT = "content-candidate-v2.1"
DECISIONS = {"ACCEPT", "EXPERIMENT", "DEFER", "REJECT"}
PENDING = "PENDING"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def positioning_config() -> dict[str, Any]:
    value = load_json(POSITIONING_PATH)
    if value.get("config_id") != "content-positioning-v1" or value.get("account") != ACCOUNT:
        raise ValueError("content positioning config identity is invalid")
    return value


def audience_config() -> dict[str, Any]:
    value = load_json(AUDIENCE_PATH)
    if value.get("account") != ACCOUNT or value.get("schema_version") != 3:
        raise ValueError("audience segment config identity is invalid")
    return value


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _nonempty(value: Any) -> bool:
    return bool(str(value or "").strip())


def _score(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 5


def _weighted(dimensions: dict[str, Any], weights: dict[str, Any], *, invert: set[str] | None = None) -> int | None:
    invert = invert or set()
    if any(not _score(dimensions.get(key)) for key in weights):
        return None
    total = sum((6 - int(dimensions[key]) if key in invert else int(dimensions[key])) * int(weight) for key, weight in weights.items())
    return int(round(total / 100))


def _level(score: int | None) -> str:
    if score is None:
        return "UNKNOWN"
    if score >= 4:
        return "HIGH"
    if score >= 3:
        return "MEDIUM"
    return "LOW"


def build_scaffold(content_id: str, *, topic: str = "", opc_task_id: str | None = None, content_type: str = "") -> dict[str, Any]:
    """Create the minimal editable candidate artifact before formal Brief."""
    candidate_id = f"{content_id}-candidate"
    return {
        "schema_version": 1,
        "contract": CONTRACT,
        "content_id": content_id,
        "account": ACCOUNT,
        "opc_task_id": opc_task_id,
        "topic": topic,
        "content_type": content_type,
        "status": "pending",
        "audience": {"primary_segment_id": "", "secondary_segment_ids": [], "stage": "", "context": ""},
        "problem": {"job_to_be_done": "", "pain_point": "", "desired_outcome": ""},
        "value": {"user_takeaway": "", "decision_enabled": "", "action_enabled": ""},
        "trust": {"level": "UNKNOWN", "reasons": [], "evidence_types": [], "proof_available": []},
        "business_fit": {"level": "UNKNOWN", "rationale": "", "related_service": "", "related_product": "", "related_opportunity": ""},
        "content_shelf": {"primary_shelf": "", "secondary_shelf": ""},
        "positioning_alignment": "EXPERIMENTAL",
        "content_strategy": "EXPERIMENT",
        "distribution_signal": {"potential": "UNKNOWN", "source_ref": ""},
        "content_value": {
            "demand": None, "audience_relevance": None, "problem_severity": None,
            "trust_evidence_strength": None, "business_fit": None, "production_cost": None,
            "aggregate": None, "confidence": "UNKNOWN",
        },
        "need_score": {
            "dimensions": {
                "problem_frequency": None, "problem_severity": None, "decision_value": None,
                "information_gap": None, "existing_solution_quality": None, "audience_relevance": None,
            },
            "aggregate": None, "level": "UNKNOWN", "confidence": "UNKNOWN",
        },
        "evaluation": {"decision": PENDING, "reason": "", "evaluated_by": "", "evaluated_at": ""},
        "override": None,
        "linkage": {
            "opc_task_id": opc_task_id,
            "content_candidate_id": candidate_id,
            "content_id": content_id,
            "production_run_id": None,
            "publication_id": None,
        },
    }


def effective_decision(candidate: dict[str, Any]) -> str:
    override = candidate.get("override") if isinstance(candidate.get("override"), dict) else None
    if override and str(override.get("final_decision", "")) in DECISIONS:
        return str(override["final_decision"])
    evaluation = candidate.get("evaluation") if isinstance(candidate.get("evaluation"), dict) else {}
    return str(evaluation.get("decision", PENDING))


def validate_candidate(candidate: dict[str, Any], *, require_ready: bool = True) -> list[str]:
    errors: list[str] = []
    config = positioning_config()
    segments = audience_config().get("segments", {})
    if candidate.get("schema_version") != 1 or candidate.get("contract") != CONTRACT:
        errors.append("content candidate contract must be content-candidate-v2.1/schema 1")
    if candidate.get("account") != ACCOUNT:
        errors.append(f"content candidate account must be {ACCOUNT}")
    if not _nonempty(candidate.get("content_id")):
        errors.append("content candidate content_id is required")
    audience = candidate.get("audience") if isinstance(candidate.get("audience"), dict) else {}
    primary = str(audience.get("primary_segment_id", "")).strip()
    secondary = audience.get("secondary_segment_ids")
    if not isinstance(secondary, list):
        errors.append("audience.secondary_segment_ids must be an array")
        secondary = []
    if len(secondary) > 1:
        errors.append("audience allows at most one secondary segment")
    valid_segments = set(segments) if isinstance(segments, dict) else set()
    if primary and primary not in valid_segments:
        errors.append("audience.primary_segment_id is not registered")
    if any(str(item) not in valid_segments for item in secondary):
        errors.append("audience.secondary_segment_ids contains an unknown segment")
    broad = {str(item).casefold() for item in config.get("broad_audience_terms", [])}
    if str(audience.get("primary", "")).strip().casefold() in broad or str(audience.get("context", "")).strip().casefold() in broad:
        errors.append("audience must not use a broad targeting phrase")

    problem = candidate.get("problem") if isinstance(candidate.get("problem"), dict) else {}
    value = candidate.get("value") if isinstance(candidate.get("value"), dict) else {}
    trust = candidate.get("trust") if isinstance(candidate.get("trust"), dict) else {}
    business = candidate.get("business_fit") if isinstance(candidate.get("business_fit"), dict) else {}
    shelf = candidate.get("content_shelf") if isinstance(candidate.get("content_shelf"), dict) else {}
    alignment = str(candidate.get("positioning_alignment", "EXPERIMENTAL"))
    if alignment not in set(config.get("positioning_alignment_levels", [])):
        errors.append("positioning_alignment is invalid")
    if str(trust.get("level", "UNKNOWN")) not in set(config.get("trust_levels", [])):
        errors.append("trust.level is invalid")
    evidence_types = trust.get("evidence_types")
    if not isinstance(evidence_types, list) or any(str(item) not in set(config.get("trust_evidence_types", [])) for item in evidence_types):
        errors.append("trust.evidence_types contains an invalid value")
    if str(trust.get("level")) == "HIGH" and not (trust.get("proof_available") and evidence_types and "NONE" not in evidence_types):
        errors.append("trust HIGH requires proof_available and non-NONE evidence_types")
    if str(business.get("level", "UNKNOWN")) not in set(config.get("business_fit_levels", [])):
        errors.append("business_fit.level is invalid")
    shelves = config.get("content_shelves", {})
    primary_shelf = str(shelf.get("primary_shelf", "")).strip()
    secondary_shelf = str(shelf.get("secondary_shelf", "")).strip()
    if primary_shelf and primary_shelf not in shelves:
        errors.append("content_shelf.primary_shelf is not in canonical positioning config")
    if secondary_shelf and secondary_shelf not in shelves:
        errors.append("content_shelf.secondary_shelf is not in canonical positioning config")
    if primary_shelf and secondary_shelf and primary_shelf == secondary_shelf:
        errors.append("content shelf primary and secondary must differ")
    if primary_shelf == "experimental" and effective_decision(candidate) not in {PENDING, "EXPERIMENT"}:
        errors.append("experimental shelf requires EXPERIMENT decision or pending evaluation")

    evaluation = candidate.get("evaluation") if isinstance(candidate.get("evaluation"), dict) else {}
    decision = str(evaluation.get("decision", PENDING))
    if decision not in DECISIONS | {PENDING}:
        errors.append("evaluation.decision is invalid")
    override = candidate.get("override")
    if override is not None:
        if not isinstance(override, dict) or str(override.get("original_decision")) not in DECISIONS | {PENDING} or str(override.get("final_decision")) not in DECISIONS or not _nonempty(override.get("reviewer")) or not _nonempty(override.get("reason")) or not _nonempty(override.get("timestamp")):
            errors.append("override must preserve original/final decision, reviewer, reason and timestamp")
        elif str(override.get("original_decision")) != decision:
            errors.append("override.original_decision must match evaluation.decision")

    content_value = candidate.get("content_value") if isinstance(candidate.get("content_value"), dict) else {}
    value_weights = config.get("content_value_weights", {})
    value_dimensions = {key: content_value.get(key) for key in value_weights}
    value_aggregate = _weighted(value_dimensions, value_weights, invert={"production_cost"})
    need = candidate.get("need_score") if isinstance(candidate.get("need_score"), dict) else {}
    need_dimensions = need.get("dimensions") if isinstance(need.get("dimensions"), dict) else {}
    need_aggregate = _weighted(need_dimensions, config.get("need_score_weights", {}))
    if require_ready:
        for label, payload, fields in (("problem", problem, ("job_to_be_done", "pain_point", "desired_outcome")), ("value", value, ("user_takeaway", "decision_enabled", "action_enabled"))):
            for field in fields:
                if not _nonempty(payload.get(field)):
                    errors.append(f"{label}.{field} is required for a ready candidate")
        if primary not in valid_segments:
            errors.append("ready candidate requires one registered primary audience segment")
        if not primary_shelf:
            errors.append("ready candidate requires a primary content shelf")
        if not isinstance(trust.get("reasons"), list) or not trust.get("reasons"):
            errors.append("trust.reasons is required for a ready candidate")
        if not isinstance(trust.get("proof_available"), list):
            errors.append("trust.proof_available must be an array")
        if str(business.get("level")) == "UNKNOWN" and decision == "ACCEPT":
            errors.append("ACCEPT requires a known business_fit level")
        if not _nonempty(business.get("rationale")):
            errors.append("business_fit.rationale is required for a ready candidate")
        if alignment == "OFF_POSITIONING" and effective_decision(candidate) == "ACCEPT" and not isinstance(candidate.get("override"), dict):
            errors.append("OFF_POSITIONING defaults to review/DEFER; ACCEPT requires a recorded human override")
        if value_aggregate is None or content_value.get("aggregate") != value_aggregate:
            errors.append("content_value.aggregate must equal the config-weighted 1-5 score")
        if need_aggregate is None or need.get("aggregate") != need_aggregate:
            errors.append("need_score.aggregate must equal the config-weighted 1-5 score")
        if decision not in DECISIONS:
            errors.append("ready candidate requires ACCEPT, EXPERIMENT, DEFER or REJECT")
        if not _nonempty(evaluation.get("reason")):
            errors.append("evaluation.reason is required")
        if decision in {"ACCEPT", "EXPERIMENT"} and str(business.get("level")) == "NONE":
            errors.append("NONE business_fit cannot be ACCEPT/EXPERIMENT without an explicit review override")
    return errors


def evaluate_candidate(candidate: dict[str, Any], *, reviewer: str = "") -> dict[str, Any]:
    """Produce an explainable default decision; a human may override it."""
    errors = validate_candidate(candidate, require_ready=False)
    if errors:
        decision, reason = "REJECT", "; ".join(errors)
    else:
        audience = candidate.get("audience", {})
        problem = candidate.get("problem", {})
        trust = candidate.get("trust", {})
        business = candidate.get("business_fit", {})
        content_value = candidate.get("content_value", {})
        need = candidate.get("need_score", {})
        if not _nonempty(audience.get("primary_segment_id")) or not _nonempty(problem.get("job_to_be_done")):
            decision, reason = "REJECT", "missing a specific audience or real problem"
        elif str(trust.get("level")) in {"UNKNOWN", "LOW"} and str(need.get("level")) in {"UNKNOWN", "LOW"}:
            decision, reason = "DEFER", "need and trust evidence are not yet strong enough"
        elif str(candidate.get("positioning_alignment", "EXPERIMENTAL")) == "OFF_POSITIONING":
            decision, reason = "DEFER", "内容偏离 Account Promise，需人工复核后再决定"
        elif str(business.get("level")) == "NONE":
            decision, reason = "DEFER", "the topic has no reasonable OPC business connection"
        elif str(business.get("level")) in {"LOW", "UNKNOWN"}:
            decision, reason = "EXPERIMENT", "business fit is limited or unknown; use a low-cost discovery test"
        elif content_value.get("aggregate") is not None and int(content_value["aggregate"]) >= 4 and str(need.get("level")) in {"HIGH", "MEDIUM"}:
            decision, reason = "ACCEPT", "specific audience, meaningful need, sufficient trust and business fit"
        else:
            decision, reason = "EXPERIMENT", "promising candidate requires a bounded test before full production"
    candidate.setdefault("evaluation", {})
    candidate["evaluation"].update({"decision": decision, "reason": reason, "evaluated_by": reviewer, "evaluated_at": now()})
    candidate["status"] = {"ACCEPT": "accepted", "EXPERIMENT": "experimental", "DEFER": "deferred", "REJECT": "rejected"}[decision]
    return candidate


def apply_override(candidate: dict[str, Any], final_decision: str, reviewer: str, reason: str, *, timestamp: str | None = None) -> dict[str, Any]:
    final_decision = str(final_decision).upper()
    if final_decision not in DECISIONS:
        raise ValueError("final_decision must be ACCEPT, EXPERIMENT, DEFER or REJECT")
    original = str((candidate.get("evaluation") or {}).get("decision", PENDING))
    candidate["override"] = {
        "original_decision": original,
        "final_decision": final_decision,
        "reviewer": str(reviewer).strip(),
        "reason": str(reason).strip(),
        "timestamp": timestamp or now(),
    }
    if not candidate["override"]["reviewer"] or not candidate["override"]["reason"]:
        raise ValueError("override requires reviewer and reason")
    candidate["status"] = {"ACCEPT": "accepted", "EXPERIMENT": "experimental", "DEFER": "deferred", "REJECT": "rejected"}[final_decision]
    return candidate


def validate_file(path: Path, *, require_ready: bool = True) -> list[str]:
    return validate_candidate(load_json(path), require_ready=require_ready)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate/evaluate a Workflow V2.1 Content Candidate")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check")
    check.add_argument("--input", required=True)
    check.add_argument("--allow-pending", action="store_true")
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("--input", required=True)
    evaluate.add_argument("--reviewer", default="")
    override = sub.add_parser("override")
    override.add_argument("--input", required=True)
    override.add_argument("--decision", required=True)
    override.add_argument("--reviewer", required=True)
    override.add_argument("--reason", required=True)
    args = parser.parse_args()
    path = Path(args.input).expanduser().resolve()
    try:
        candidate = load_json(path)
        if args.command == "check":
            errors = validate_candidate(candidate, require_ready=not args.allow_pending)
            print(json.dumps({"passed": not errors, "errors": errors}, ensure_ascii=False, indent=2))
            return 0 if not errors else 1
        if args.command == "evaluate":
            candidate = evaluate_candidate(candidate, reviewer=args.reviewer)
        else:
            candidate = apply_override(candidate, args.decision, args.reviewer, args.reason)
        path.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(candidate, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
