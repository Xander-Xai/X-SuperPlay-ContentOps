"""Fill the editorial fields the growth skill deliberately leaves out.

The growth skill maps an operator draft to a record that says, honestly, that it
is incomplete: ``PARTIAL_CONTRACT`` with no theses, no recovery fields and no
review. The X Post Gate refuses that record by name. This module is the data
transformation between them.

It does not write copy, invent evidence, or approve anything:

- every thesis must cite an ``evidence_id`` from the caller's own evidence list;
- ``unique_artifact_ref`` must be one of those artifacts;
- the review is read from a separate file inside the project, never from the
  growth draft, and the file's provenance is recorded as unverified. This is a
  structural boundary, not an identity check: a caller who can write the review
  file can still record a review. A repository without an approval service can
  only make that act explicit and separate, not authenticated.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List

from contentops.publish.x_paths import (
    is_single_component,
    resolve_inside,
    safe_relative,
)
from contentops.x_growth_contract import SUPPORTED_ACCOUNTS, X_POST_SCHEMA

SCHEMA = "contentops.x-growth-bridge/v1"
REVIEW_PROVENANCE = "EXTERNAL_REVIEW_FILE_UNVERIFIED"
PROOF_GRADES = ("P0", "P1", "P2", "P3")
REQUIRED_SCALARS = (
    "content_id", "mode", "audience_job", "proof_grade", "unique_artifact_ref",
    "experiment_variable", "label", "image_brief", "alt_text",
)


class BridgeBlocked(ValueError):
    """The enrichment is incomplete; the caller has to supply the field."""

    def __init__(self, reasons: List[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


def _review(project: Path, source: Any, account_slug: str) -> Dict[str, Any]:
    relative = safe_relative(source)
    if relative is None:
        raise BridgeBlocked(
            ["review_source must be a project-relative path; an inline review "
             "cannot be told apart from an agent-written one"])
    path = resolve_inside(project, relative.as_posix(), must_be_file=True)
    if path is None:
        raise BridgeBlocked(
            [f"review_source {relative.as_posix()!r} is not a regular file inside "
             "the project; links and escaping paths are refused"])
    try:
        if path.stat().st_size > 1_048_576:
            raise BridgeBlocked(["review_source is larger than 1 MiB"])
        review = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BridgeBlocked([f"review_source is not readable JSON: {exc}"]) from exc
    if not isinstance(review, dict):
        raise BridgeBlocked(["review_source must be a JSON object"])
    if review.get("decision") != "APPROVED":
        raise BridgeBlocked(
            [f"review decision is {review.get('decision')!r}; only APPROVED is a review"])
    if not str(review.get("reviewer") or "").strip():
        raise BridgeBlocked(["review names no reviewer"])
    if not str(review.get("reviewed_at") or "").strip():
        raise BridgeBlocked(["review has no reviewed_at date"])
    if not isinstance(review.get("dimensions"), dict):
        raise BridgeBlocked(["review.dimensions is not an object"])
    if not isinstance(review.get("score"), int) or isinstance(review.get("score"), bool):
        raise BridgeBlocked(["review.score is not an integer"])
    scoped = str(review.get("account_slug") or "").strip()
    if scoped and scoped != account_slug:
        raise BridgeBlocked(
            [f"review is scoped to {scoped!r}, not {account_slug!r}"])
    recorded = {
        "reviewer": review["reviewer"],
        "reviewed_at": review["reviewed_at"],
        "dimensions": dict(review["dimensions"]),
        "score": review["score"],
        "opinion": str(review.get("opinion") or ""),
        "source": relative.as_posix(),
        "provenance": REVIEW_PROVENANCE,
    }
    if review.get("synthetic") is True:
        recorded["synthetic"] = True
    return recorded


def enrich(partial: Dict[str, Any], enrichment: Dict[str, Any], project: Path,
           account: Dict[str, Any]) -> Dict[str, Any]:
    """Return a gate-shaped record, or raise :class:`BridgeBlocked`.

    ``partial`` is the growth skill's mapped record. ``enrichment`` is supplied
    by the operator or the supervising agent; its evidence may not be invented
    by this function.
    """
    project = Path(project)
    reasons: List[str] = []

    if not isinstance(partial, dict) or partial.get("schema") != X_POST_SCHEMA:
        raise BridgeBlocked([f"partial record must declare {X_POST_SCHEMA!r}"])
    account_slug = str(partial.get("account_slug") or "")
    if account_slug not in SUPPORTED_ACCOUNTS:
        raise BridgeBlocked([f"account_slug {account_slug!r} is not supported"])
    if not isinstance(enrichment, dict):
        raise BridgeBlocked(["enrichment must be an object"])

    for key in REQUIRED_SCALARS:
        if not str(enrichment.get(key) or "").strip():
            reasons.append(f"enrichment has no {key!r}")

    content_id = str(enrichment.get("content_id") or "").strip()
    if content_id and not is_single_component(content_id):
        reasons.append(
            f"content_id {content_id!r} is not one safe file-name component; it "
            "becomes a path under posts/ and may not contain separators or dots")

    grade = str(enrichment.get("proof_grade") or "")
    if grade and grade not in PROOF_GRADES:
        reasons.append(f"proof_grade {grade!r} is not one of {list(PROOF_GRADES)}")

    modes = [str(pillar.get("name")) for pillar in
             (account.get("content_pillars") or []) if isinstance(pillar, dict)]
    mode = str(enrichment.get("mode") or "")
    if mode and modes and mode not in modes:
        reasons.append(f"mode {mode!r} is not one of {modes}")

    evidence = enrichment.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        reasons.append("enrichment has no evidence list")
        evidence = []
    artifacts: Dict[str, str] = {}
    for index, item in enumerate(evidence, start=1):
        if not isinstance(item, dict):
            reasons.append(f"evidence {index} is not an object")
            continue
        identifier = str(item.get("id") or "").strip()
        artifact = str(item.get("artifact_ref") or "").strip()
        if not identifier or not artifact:
            reasons.append(f"evidence {index} needs an id and an artifact_ref")
            continue
        if identifier in artifacts:
            reasons.append(f"evidence id {identifier!r} is repeated")
            continue
        artifacts[identifier] = artifact

    artifact_ref = str(enrichment.get("unique_artifact_ref") or "")
    if artifacts and artifact_ref and artifact_ref not in artifacts.values():
        reasons.append(
            "unique_artifact_ref does not appear in the evidence list; the "
            "artifact the post rests on must be one of its sources")

    theses = enrichment.get("theses")
    if not isinstance(theses, list) or len(theses) < 3:
        reasons.append("enrichment needs at least three theses")
        theses = []
    gate_theses = []
    for index, thesis in enumerate(theses, start=1):
        if not isinstance(thesis, dict):
            reasons.append(f"thesis {index} is not an object")
            continue
        for field in ("thesis", "counterexample", "reader_action"):
            if not str(thesis.get(field) or "").strip():
                reasons.append(f"thesis {index} has no {field!r}")
        evidence_id = str(thesis.get("evidence_id") or "").strip()
        if evidence_id not in artifacts:
            reasons.append(
                f"thesis {index} cites evidence_id {evidence_id!r}, which is not "
                "in the evidence list")
            evidence_text = ""
        else:
            evidence_text = f"{evidence_id}: {artifacts[evidence_id]}"
        gate_theses.append({
            "thesis": str(thesis.get("thesis") or ""),
            "evidence": evidence_text,
            "counterexample": str(thesis.get("counterexample") or ""),
            "reader_action": str(thesis.get("reader_action") or ""),
        })

    red_team = enrichment.get("red_team")
    if not isinstance(red_team, list) or len(red_team) < 3 or any(
            not str(item or "").strip() for item in red_team):
        reasons.append("enrichment needs three answered red-team questions")
        red_team = [str(item or "") for item in (red_team or [])]

    image = enrichment.get("image")
    image_value = image.get("path") if isinstance(image, dict) else None
    image_path = safe_relative(image_value)
    if image_path is None:
        reasons.append("enrichment.image.path must be project-relative")
    elif resolve_inside(project, image_path.as_posix(), must_be_file=True) is None:
        reasons.append(
            f"image {image_path.as_posix()!r} is not a regular file inside the "
            "project; links and escaping paths are refused")

    review: Dict[str, Any] = {}
    if not str(enrichment.get("review_source") or "").strip():
        reasons.append("enrichment has no review_source; a review is a separate file")
    else:
        try:
            review = _review(project, enrichment.get("review_source"), account_slug)
        except BridgeBlocked as blocked:
            reasons.extend(blocked.reasons)

    if reasons:
        raise BridgeBlocked(reasons)

    record = deepcopy(partial)
    record.update({
        "content_id": str(enrichment["content_id"]),
        "mode": mode,
        "topic": str(enrichment.get("topic") or partial.get("post_copy", {}).get(
            "parts", [""])[0])[:120],
        "sources": [item.get("artifact_ref") for item in evidence
                    if isinstance(item, dict) and item.get("artifact_ref")],
        "audience_job": str(enrichment["audience_job"]),
        "proof_grade": grade,
        "unique_artifact_ref": artifact_ref,
        "experiment_variable": str(enrichment["experiment_variable"]),
        "label": str(enrichment["label"]),
        "theses": gate_theses,
        "red_team": red_team,
        "image_brief": str(enrichment["image_brief"]),
        "image": {"path": image_path.as_posix()},
        "image_status": str(enrichment.get("image_status") or "generated"),
        "alt_text": str(enrichment["alt_text"]),
        "review": review,
        "enrichment": {
            "schema": SCHEMA,
            "evidence_ids": sorted(artifacts),
            "evidence_provenance": "USER_SUPPLIED_UNVERIFIED",
            "review_source": review["source"],
            "review_provenance": REVIEW_PROVENANCE,
            "review_trust": "NOT_VERIFIED",
        },
    })
    return record
