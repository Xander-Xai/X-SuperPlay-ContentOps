"""Immutable review bundles: an approval must name the bytes it approved.

A human score is only meaningful for the exact cut that was watched. So the
bundle hashes every input that can change what the reviewer saw — the MP4,
narration, captions, citation cards, Claim Map, CutPlan, asset map, capture
proofs, QC report and target specification — and derives one fingerprint.

If any of those changes, the recorded review no longer applies. The bundle never
marks a cut published, never infers a score, and never turns passing automation
into a human decision.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from contentops.evidence._common import ContractError, fingerprint, require, require_text
from contentops.evidence.capture import CaptureProof
from contentops.evidence.claim_map import ClaimMap
from contentops.media.cut_plan import CutPlan
from contentops.media.media_paths import resolve_media_path

BUNDLE_SCHEMA = "contentops.review-bundle/v1"
MIN_SCORE = 80


class ReviewBindingError(ContractError):
    pass


def _sha(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _local(project: Path, ref: str) -> Path:
    return resolve_media_path(ref, repo_root=project.parents[1], project_root=project)


def _file_entry(project: Path, relative: str) -> Optional[Dict[str, Any]]:
    path = project / relative
    if not path.is_file():
        return None
    return {"path": f"project://{relative.replace(chr(92), '/')}", "sha256": _sha(path)}


def build_review_bundle(project: Path) -> Dict[str, Any]:
    project = project.resolve()
    claim_map = ClaimMap.from_dict(_read(project / "script" / "claim-map.json"))
    cut_plan = CutPlan.from_dict(_read(project / "script" / "cut-plan.json"))
    assets = _read(project / "script" / "assets.json")["assets"]

    inputs: Dict[str, Any] = {
        "video": _file_entry(project, "final/easel.mp4"),
        "narration": _file_entry(project, "work/narration.wav"),
        "captions": _file_entry(project, "assets/captions/cut.srt"),
        "claim_map": _file_entry(project, "script/claim-map.json"),
        "cut_plan": _file_entry(project, "script/cut-plan.json"),
        "asset_map": _file_entry(project, "script/assets.json"),
        "qc_report": _file_entry(project, "receipts/qc-report.json"),
        "build_receipt": _file_entry(project, "receipts/build-easel.json"),
        "target": cut_plan.target,
        "claim_map_fingerprint": claim_map.fingerprint(),
        "cut_plan_fingerprint": cut_plan.fingerprint(),
    }
    require(inputs["video"] is not None, "MISSING_VIDEO",
            "final/easel.mp4 must exist before a review bundle")
    require(inputs["qc_report"] is not None, "MISSING_QC",
            "a QC report must exist before a review bundle")

    cards = {}
    for asset_id, asset in assets.items():
        if asset.get("kind") == "card":
            entry = _file_entry(project, f"assets/cards/{Path(asset['png']).name}") \
                if asset.get("png") else None
            png = _local(project, asset["png"]) if asset.get("png") else None
            if png and png.is_file():
                entry = {"path": f"project://assets/cards/{png.name}", "sha256": _sha(png)}
            require(entry is not None, "MISSING_CARD", f"{asset_id} has no rendered PNG")
            cards[asset_id] = entry
    inputs["cards"] = cards

    cover_receipt = project / "receipts" / "cover.json"
    if cover_receipt.is_file():
        cover = _read(cover_receipt)
        cover_rel = cover["png"]["path"].replace("project://", "")
        inputs["cover"] = _file_entry(project, cover_rel)
        inputs["cover_receipt"] = _file_entry(project, "receipts/cover.json")

    captures: List[Dict[str, Any]] = []
    blocking: List[str] = []
    for asset_id, asset in assets.items():
        capture_id = asset.get("capture_id")
        if not capture_id:
            continue
        receipt_path = project.parent / "easel-evidence-capture" / "receipts" / "captures" / f"{capture_id}.json"
        require(receipt_path.is_file(), "MISSING_CAPTURE_PROOF",
                f"{asset_id} cites {capture_id} but its proof is missing")
        proof = CaptureProof.from_dict(_read(receipt_path))
        captures.append({"asset_id": asset_id, "capture_id": capture_id,
                         "evidence_class": proof.evidence_class,
                         "permission_scope": proof.permission_scope,
                         "recording_sha256": proof.recording["sha256"]})
        if proof.permission_scope != "publishable":
            blocking.append(f"{capture_id} is {proof.permission_scope}; a redaction "
                            f"receipt is required before distribution")
    inputs["captures"] = captures
    inputs["capture_proofs_present"] = bool(captures)

    redactions = []
    redaction_dir = project.parent / "easel-evidence-capture" / "receipts" / "redactions"
    if redaction_dir.is_dir():
        for path in sorted(redaction_dir.glob("*.json")):
            if path.name.endswith("-crops.json"):
                continue
            redactions.append({"path": path.name, "sha256": _sha(path)})
    inputs["redactions"] = redactions
    inputs["distribution_blocked"] = bool(blocking)
    inputs["distribution_block_reasons"] = blocking

    bundle = {
        "schema": BUNDLE_SCHEMA,
        "package_id": cut_plan.package_id,
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "inputs": inputs,
        "score": None,
        "reviewer": None,
        "reviewed_at": None,
        "hard_fail": None,
        "status": "PENDING_HUMAN_REVIEW",
        "production_ready": False,
    }
    bundle["review_bundle_fingerprint"] = fingerprint(bundle["inputs"])
    return bundle


def write_review_bundle(project: Path) -> Dict[str, Any]:
    bundle = build_review_bundle(project)
    receipts = project / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    (receipts / "review-bundle.json").write_text(
        json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    return bundle


def validate_review_binding(project: Path, fingerprint_value: str) -> Dict[str, Any]:
    current = build_review_bundle(project)
    ok = current["review_bundle_fingerprint"] == fingerprint_value
    return {"ok": ok, "current": current["review_bundle_fingerprint"],
            "recorded": fingerprint_value,
            "reason": "" if ok else "a fingerprinted input changed after review"}


def record_review(project: Path, reviewer: str, score: int, hard_fail: bool,
                  notes: str = "") -> Dict[str, Any]:
    """Record a human decision against the current bundle.

    Refuses to produce PRODUCTION_READY without a real reviewer, a score of at
    least 80, no hard fail, and a passing QC report. It never publishes.
    """
    require_text(reviewer, "reviewer")
    require(isinstance(score, int) and not isinstance(score, bool)
            and 0 <= score <= 100, "INVALID_SCORE", "score must be 0..100")
    bundle_path = project / "receipts" / "review-bundle.json"
    require(bundle_path.is_file(), "MISSING_BUNDLE",
            "build the review bundle before recording a review")
    bundle = _read(bundle_path)
    binding = validate_review_binding(project, bundle["review_bundle_fingerprint"])
    require(binding["ok"], "STALE_REVIEW_BUNDLE", binding["reason"])

    qc = _read(project / "receipts" / "qc-report.json")
    require(qc.get("overall") == "PASS", "QC_NOT_PASS",
            "a cut with a failing QC report cannot become production-ready")
    require(not hard_fail, "HARD_FAIL", "a hard fail cannot become production-ready")

    ready = score >= MIN_SCORE
    bundle.update({
        "score": score,
        "reviewer": reviewer,
        "reviewed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hard_fail": hard_fail,
        "notes": notes,
        "status": "PRODUCTION_READY" if ready else "HOLD",
        "production_ready": ready,
    })
    bundle["review_bundle_fingerprint"] = fingerprint(bundle["inputs"])
    bundle_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False),
                           encoding="utf-8")
    return bundle


def _read(path: Path) -> Dict[str, Any]:
    require(path.is_file(), "MISSING_FILE", f"{path} does not exist")
    return json.loads(path.read_text(encoding="utf-8"))
